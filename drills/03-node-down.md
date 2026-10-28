# 03 · 节点宕机（worker 失联）

- **日期**：2026-10-28
- **类型**：主动演练（节点不可用）
- **影响**：业务 500 约 1 分 45 秒；**监控栈同时失联，全程无法观测**
- **环境**：k3s v1.36.5，worker `k3s-node1`

## 目的

1. 节点失联后，业务多久受影响、`kubectl` 看到什么
2. 监控和告警在这种"自身也挂了"的场景里还剩多少能力
3. 恢复需要多久

## 注入

```bash
# 在 worker 上
systemctl stop k3s-agent
```

比 `shutdown` 温和：SSH 仍可用，能随时拉回来；同时 kubelet 停止上报，
效果等价于节点宕机（NotReady → 后续驱逐）。

## 时间线

| 时间 | 事件 |
|---|---|
| 13:24:16 | 停止 worker 的 `k3s-agent` |
| ~13:24:56 | 节点变 `NotReady`（40 秒宽限期） |
| 13:25:00 | `/api/time` 两个节点 IP **全部 500** |
| 13:25:51 | 想查告警状态 → **Grafana 连不上**（它在 worker 上） |
| 13:25:58 | 恢复：`systemctl start k3s-agent` |
| 13:26:08 | 节点回到 `Ready` |
| 13:26:41 | 业务恢复 200 |
| 13:28:10 | 钉钉收到 **1 条迟到的 5xx 告警**（此时业务已恢复 1.5 分钟） |
| 13:31:06 | 5xx 规则 `inactive` |
| 13:31:10 | 钉钉收到恢复通知 |

受影响时长约 **1 分 45 秒**（13:24:56 → 13:26:41）。

## 现象与证据

**Pod 显示 Running，但业务已经挂了**：

```bash
$ kubectl -n demo get pods -o wide
mysql-0               1/1  Running  0  44m  10.42.2.69  k3s-node1   # 状态是旧的
web-7bc97b9b-hwj77    1/1  Running  0  50m  10.42.0.14  master
web-7bc97b9b-wfkn9    1/1  Running  0  50m  10.42.2.68  k3s-node1
```

kubelet 已经死了，Pod 状态停留在最后一刻，**`get pods` 在节点故障时不可信**。

**为什么两个 web 副本都 500**：MySQL 只在 worker 上（local-path 绑节点），
worker 失联后，master 上的 web 也连不上库 —— 业务不是"降级一半"，而是"全挂"。

**监控同时失联**：Prometheus、Grafana、Alertmanager、blackbox-exporter 全在 worker，
节点一挂，这四个一起消失。想看一眼告警状态，得到的是 `Connection refused`。

## 根因

1. **MySQL 单副本 + local-path**：存储钉死在 worker，节点不在 Pod 就不在，无法漂移。
2. **监控栈与业务同节点**：观测系统没有独立性，被观测对象故障时它一起故障。
3. **5xx 规则窗口 5 分钟**：故障只有 1 分 45 秒，规则靠 5 分钟窗口里的残留比例才勉强触发，
   送达时业务早已恢复。

## 恢复

```bash
systemctl start k3s-agent      # 节点约 10 秒恢复 Ready
```

值得记的一点：**MySQL 容器全程没有重启**（`RESTARTS=0`）—— containerd 的进程还在跑，
只是 kubelet 不在了。节点回来后它立刻重新 Ready，数据无恙，
所以这次不是"数据库崩溃恢复"，而是"网络与控制面中断"。

## 经验

- **节点故障时 `kubectl get pods` 会骗人**：状态是最后上报的快照。
  判断节点健康只能看 `kubectl get nodes` 和 events 里的 `NodeNotReady`。
- **监控不能和被监控对象同生共死**：这是本次最值钱的发现。
  Prometheus/Grafana/blackbox 全在 worker，worker 挂了就"既看不见、也不告警"。
- **告警可能比故障晚到**：13:28 才收到 5xx 告警，业务 13:26 就恢复了。
  值班同学收到时会一脸问号 —— 这就是长窗口 `rate()` 的副作用。
- **单节点承载有状态服务 = 单点**，这已经不是第一次踩（07 号演练同款结论）。

## 改进项

- [ ] **监控拆分**：Prometheus 放 master，Grafana 留 worker（或反之），
      避免单节点故障同时带走"存储指标"和"展示"两件事
- [ ] **引入集群外探活**：外部定时 `curl` 入口（或云监控），不依赖集群内任何组件 ——
      这是唯一能在"整节点挂掉"时还响的告警
- [ ] **5xx 窗口 5m → 2m**，并把「入口不可用」作为节点级故障的主告警
- [ ] 评估 MySQL 存储换成云盘（可跨节点漂移），或用外部 RDS
- [ ] 节点故障时自动 `cordon` + 记录事件，便于事后统计 MTTR

> 备注：本次演练与 07 号（节点停机变配）结论一致但角度不同 ——
> 07 是"计划内变更引发意外"，本次是"受控条件下测量影响面与观测能力"。
