# 05 · 误删配置（删除告警转发链的 ConfigMap）

- **日期**：2026-10-28
- **类型**：主动演练（配置对象误删）
- **影响**：**告警通知链路静默失效 6 分钟**，业务本身无影响
- **环境**：k3s v1.36.5，`default` 命名空间的 `feishu-relay`

## 目的

1. 配置对象被删后，正在运行的 Pod 会不会立刻挂？（预期：不会）
2. 告警链路自己断了，能不能被发现？
3. 恢复需要多久、依赖什么

## 注入

`feishu-relay` 的源码是挂在 ConfigMap 里的（`feishu-relay-src`），当时是手工创建的：

```bash
kubectl -n default delete configmap feishu-relay-src
kubectl -n default delete pod -l app=feishu-relay
```

**必须删 Pod 才会炸** —— 这是配置类故障的典型特征：卷已经挂进容器，
删 ConfigMap 不影响运行中的进程，只有下次重启才会暴露。

## 时间线

| 时间 | 事件 |
|---|---|
| 12:48:17 | 删除 ConfigMap + relay Pod |
| 12:48:30 | 新 Pod 卡在 `ContainerCreating`，事件：`MountVolume.SetUp failed ... configmap "feishu-relay-src" not found` |
| 12:49:52 | 制造一次真实故障：把 blackbox-exporter 缩到 0 |
| 12:52:40 | 「入口不可用」规则 `firing` |
| **12:53:11** | Grafana 尝试通知：`connection refused` → **钉钉收到 0 条** |
| 12:54:09 | 恢复：重建 ConfigMap |
| 12:54:20 | relay Pod `Ready`，`/` 返回 `relay ok` |
| 12:54:52 | 探针恢复 |
| 12:55:11 | relay 重新收到并成功转发（钉钉回执 200） |
| 12:55:40 | 规则 `inactive` |

## 现象与证据

**Pod 起不来**：

```bash
$ kubectl -n default get pod -l app=feishu-relay
NAME                            READY   STATUS              RESTARTS   AGE
feishu-relay-5cf596c78c-75bm4   0/1     ContainerCreating   0          45s

$ kubectl -n default describe pod -l app=feishu-relay | grep FailedMount
Warning  FailedMount  ... MountVolume.SetUp failed for volume "src" : configmap "feishu-relay-src" not found
```

**告警真的发生了，但没人知道**：规则在 Grafana 里是 `firing`，钉钉群里一条没有。
唯一的痕迹在 Grafana 日志里：

```
level=error msg="Notify for alerts failed" num_alerts=1
  err="dingtalk/webhook[0]: notify retry canceled due to unrecoverable error after 1 attempts:
       Post \"...\": dial tcp 10.43.114.209:8080: connect: connection refused"
```

**失败的通知不会补发** —— Grafana 只试一次就放弃。也就是说，如果这次不是演练而是真实故障，
这一场事故从头到尾不会有任何推送，直到有人碰巧打开 Grafana。

## 根因

两层：

1. `feishu-relay-src` 是**手工 `kubectl create configmap --from-file`** 创建的，不在仓库里。
   误删之后没有任何"声明式"来源可以让它自动回来，只能靠人记得当初那条命令。
2. **告警链路自身没有监控**。`blackbox` 探的是业务入口，不探 relay；
   也没有 Watchdog 心跳。链路断了，系统看起来一切正常。

## 恢复

```bash
kubectl -n default create configmap feishu-relay-src \
  --from-file=app.py=monitoring/feishu-relay/app.py
```

Pod 会自动重试挂载，几秒内起来。恢复动作本身只要 1 分钟，
**难的是"知道它断了"** —— 这次是靠人盯着终端才发现的。

## 改进：把 relay 配置纳入仓库（已落地）

新增 `monitoring/feishu-relay/kustomization.yaml`：

```yaml
resources:
  - deploy.yaml
configMapGenerator:
  - name: feishu-relay-src
    files:
      - app.py
```

之后统一用声明式部署，ConfigMap 带内容哈希，改代码会自动触发滚动更新：

```bash
kubectl apply -k monitoring/feishu-relay/
```

已实际切换：ConfigMap 变为 `feishu-relay-src-hk2bc6f956`，Pod 滚动替换后 `relay ok`，
手工创建的那个已删除。

## 经验

- **删配置不会立刻炸**：运行中的 Pod 用的是已挂载的副本，重启才暴露 ——
  所以"改/删配置后一切正常"是假象，必须连带重启验证。
- **告警链路的可用性必须被监控**：没有心跳，链路断了和"系统很健康"长得一模一样。
  业界做法是 Alertmanager 的 **Watchdog**：一条永远 firing 的规则定期推送，
  **收不到**就说明链路断了（dead man's switch）。
- **通知失败不重试**：Grafana 单次失败即丢弃，依赖它自己恢复是不可靠的。
- **手工创建的配置 = 没有恢复预案**：凡是 `kubectl create` 出来的东西，都要么进仓库、要么写进脚本。

## 改进项

- [x] relay 的 ConfigMap 改为 kustomize 管理（`kubectl apply -k`）
- [x] 记录"删除配置不会立即生效"与通知不补发两个坑
- [ ] **加 Watchdog 心跳规则**：一条恒定 firing 的告警，每小时推一次，收不到即链路故障
- [ ] **blackbox 增加对 relay 的探活**：`http://feishu-relay.default.svc.cluster.local:8080/`
- [ ] 排查其它手工创建的对象（本次已确认 grafana / mysql 的配置都在仓库里）
