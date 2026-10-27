# 08 · 主机名变更引发的节点重复注册与入口中断

- **日期**：2026-10-27
- **类型**：配置变更 → 非预期故障（未按故障流程执行）
- **影响**：业务入口不可用约 **4.5 小时**（12:41 → 17:15），Master 上的 kube-system 组件部分失效
- **数据**：无丢失，MySQL 未重启（Pod 最后一次重启是 10-26 21:00 前后的节点维护）
- **环境**：k3s v1.36.5，master 2C4G / worker 2C4G

## 背景

master 的主机名是云厂商默认的 `iZ2vcih52kdnj152u1buo0Z`，不好认。当天中午为方便识别，
在 master 上把主机名改成了 `master` —— **只改了运行时主机名，`/etc/hostname` 没动**，
并且随后重启了 k3s。

k3s 用主机名作为节点名。于是它认为这是一台**新机器**，注册出一个新的节点对象，
而旧节点对象还留在集群里。

## 时间线

| 时间 | 事件 |
|---|---|
| 12:40 | 执行 `hostname master`（仅运行时生效，静态主机名仍是 `iZ2vcih52kdnj152u1buo0Z`） |
| 12:41:37 | `systemctl restart k3s` |
| 12:41:43 | 新节点对象 `master` 注册成功，分到新网段 `10.42.0.0/24`；旧节点保留 `10.42.1.0/24` |
| 12:41:42–44 | Traefik 与各 agent 的 informer 报 `apiserver not ready`，Traefik 此后**再没有成功 watch 过 API** |
| 12:48:10 | 旧节点上的 5 个 Pod 进入 `Terminating` 并永久卡住（kubelet 已不认它们） |
| 13:23 | 开始做 OOM 演练（`memhog`），完全没察觉业务入口已经挂了 |
| 13:42 | 演练残留 Pod `crash` 反复 CrashLoopBackOff |
| 16:58 | 人工探测 `http://<node-ip>/api/time`，得到 **404**，才发现故障 |
| 17:05 | 开始处置：固化主机名 → 强删 5 个 Pod → 删除幽灵节点 |
| 17:11 | 重建 `svclb-traefik`，80/443 重新绑定到新网段 Pod |
| 17:12 | 重建 Traefik，informer 恢复，Ingress 路由重建 |
| 17:14 | 仍然超时 —— 定位到跨节点 Pod 网络，worker 侧手工补 FDB 表项 |
| 17:15 | 三处入口（两个节点 IP + 127.0.0.1）全部返回 200，业务恢复 |

## 现象

```bash
$ curl -s -o /dev/null -w '%{http_code}\n' http://172.26.13.50/api/time
404                      # Traefik 默认 404，不是应用返回
$ curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1/api/time
000                      # 超时
$ kubectl get nodes
NAME                      STATUS     ROLES           AGE
iz2vcih52kdnj152u1buo0z   NotReady   control-plane   3d5h     # 幽灵节点
k3s-node1                 Ready      <none>          3d5h
master                    Ready      control-plane   21h       # 新身份
```

两个控制面节点**内网 IP 相同**（172.26.13.50），是同一台机器。

## 排查过程

1. **先分清 404 与超时**：404 说明请求已经到了 Traefik，只是没有匹配的路由；超时说明更底层。
2. **查 Traefik 日志**：最后一条日志停在 12:41:44，内容是 `apiserver not ready`，
   之后有一串 `clusterrole.rbac... not found`。核对后 82 个 ClusterRole 都在，
   那串 RBAC 报错是 apiserver 重启窗口内的**瞬时**错误，不是真被删了 —— 但它导致
   Traefik 的 informer 缓存彻底失效，且不会自愈。
3. **查节点表**：发现幽灵节点，且新旧节点网段不同（`10.42.1.0/24` vs `10.42.0.0/24`）。
4. 重建 svclb 与 Traefik 后，404 变成超时 —— 说明路由层修好了，但**流量到不了后端**。
5. **逐层定位网络**：
   - `curl <ClusterIP>` 超时 → 排除 Ingress 层
   - `curl 10.42.0.12:8000`（Traefik Pod IP）超时 → 排除 Service 层
   - `ping 10.42.2.39`（worker 上的 web Pod）100% 丢包 → 问题在 **Pod 跨节点网络**
6. **查 flannel 转发表**：

   ```bash
   # master 上：有 worker 的表项
   aa:92:bb:aa:b9:b6 ...  # 反了，master 上的是 worker 的 VTEP
   bridge fdb show dev flannel.1
   26:ef:40:38:92:f9 dst 172.26.13.51 self permanent

   # worker 上：空的
   bridge fdb show dev flannel.1
   （无输出）
   ```

   worker 的 flannel 日志显示 17:11 明确收到了 master 的新 VTEP 事件
   （`VtepMAC: aa:92:bb:aa:b9:b6`），但**没有写进 FDB 表**。
   vxlan 是 `nolearning` 模式，没有表项就直接丢包 —— 于是 worker → master 单向不通。

## 根因

三层叠加，缺一层都不会这么严重：

1. **主机名只改运行时**：`hostname` 命令只改 transient hostname，`/etc/hostname` 不变。
   k3s 重启后按新主机名注册，产生第二个节点对象；旧对象连同它占用的 `10.42.1.0/24` 网段一起残留。
2. **Traefik informer 不自愈**：apiserver 重启窗口内 watch 失败后，client 的缓存进入坏状态，
   即使 APIServer 恢复、RBAC 正常，它也不再重建路由 —— 表现为"Pod 正常但全站 404"。
3. **flannel FDB 未写入**：节点身份变更（VTEP MAC 变了）后，worker 收到新事件却没落表，
   跨节点 Pod 网络单方向断掉。这类故障 `kubectl get pods` 完全看不出来，Pod 依旧 `Running`。

## 恢复步骤

```bash
# 1. 固化主机名（否则下次重启会再造一个节点）
hostnamectl set-hostname master
hostname   # 确认 static / transient 都是 master

# 2. 强删幽灵节点上的 Pod，再删节点对象
kubectl delete pod -n kube-system --force --grace-period=0 \
  <coredns-旧> <local-path-旧> <metrics-server-旧> <svclb-旧>
kubectl delete pod -n monitoring --force --grace-period=0 <node-exporter-旧>
kubectl delete node iz2vcih52kdnj152u1buo0z

# 3. 重建 svclb，让 hostPort 绑到新网段；重建 Traefik，重建 informer
kubectl -n kube-system rollout restart ds/svclb-traefik-7e40d0e8
kubectl -n kube-system rollout restart deploy/traefik

# 4. 补 flannel 转发表项（关键一步，前面都做完仍然超时）
#    在 worker 上执行：
bridge fdb replace aa:92:bb:aa:b9:b6 dst 172.26.13.50 dev flannel.1
```

## 验证

```bash
for u in http://172.26.13.50/api/time http://172.26.13.51/api/time http://127.0.0.1/api/time; do
  curl -s -o /dev/null -w "$u -> %{http_code}\n" --max-time 5 "$u"
done
# 全部 200，返回 {"db_time":"2026-10-27 09:14:57","host":"web-759b9f5ffd-s6qzh"}

kubectl get nodes          # 只剩 master、k3s-node1，均 Ready
kubectl top nodes          # metrics-server 恢复（此前它的旧 Pod 卡在 Terminating）
```

## 经验

- **改主机名 = 换节点身份**，属于控制面变更。正确做法：先 `cordon` + `drain`，
  删旧节点对象，再改静态主机名，最后重启 k3s；或者干脆不改。
- **`hostname` 与 `hostnamectl set-hostname` 不是一回事**：前者只改运行时，后者改 `/etc/hostname`。
  只改运行时是这套故障中最隐蔽的一环 —— 重启前一切正常。
- **404 和超时是两个层次**：404 是路由没匹配上（控制面问题），超时是包到不了（数据面问题）。
  修完第一个会暴露第二个，不要以为"重启一下就好"。
- **网络排查顺序**：Pod IP → ClusterIP → NodePort → Ingress → 本地回环，逐层缩小。
- **`bridge fdb show dev flannel.1` 是 vxlan 集群的必备命令**，
  `kubectl` 里一切正常但跨节点不通时先看它。
- **最大的问题不是故障本身，是 4.5 小时没人发现**：现有 4 条告警规则
  （内存 / 磁盘 / Pod 重启 / 5xx）没有一条覆盖"入口不可用"。
  Pod 全是 Running、5xx 为 0，监控面板一片绿 —— 典型的"监控盲区"。

## 改进项

- [x] 固化主机名，清理幽灵节点与卡死 Pod
- [x] 记录本次复盘（本文）
- [x] **blackbox-exporter 探活 `/api/time`**，作为「入口可用性」的独立告警
      （`monitoring/blackbox.yaml` + Grafana 规则「入口不可用（探针失败）」，30s 探测，连续 2 分钟失败告警）
- [ ] FDB 修复是运行时的，不持久：安排一次 `systemctl restart k3s-agent` 并复查表项是否自动重建
- [ ] 变更检查清单：动控制面之前先记录 `kubectl get nodes`、Pod 分布、`curl` 基线
- [ ] 确认 6443 安全组是 `/32` 还是 `0.0.0.0/0`
