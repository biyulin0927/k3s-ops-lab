# 02 · Pod OOM（容器内存超限反复重启）

- **日期**：2026-10-28
- **类型**：主动演练（容器级内存超限）
- **影响**：单 Pod 反复重启，业务无感知（演练 Pod 与 web 隔离）
- **环境**：k3s v1.36.5，worker 2C4G

## 目的

验证三件事：

1. 容器被 cgroup OOM killer 杀掉时，`kubectl` 侧能不能看出"是 OOM 而不是普通崩溃"
2. 现有「Pod 频繁重启」告警要多久才能发现，以及**恢复后多久能解除**
3. 容器级 OOM 会不会触发节点内存告警（预期：不会）

## 注入

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: oom-demo
  namespace: demo
spec:
  restartPolicy: Always
  nodeSelector:
    kubernetes.io/hostname: k3s-node1
  containers:
    - name: hog
      image: python:3.12-alpine
      command: ["python", "-c", "b=bytearray(200*1024*1024); import time; time.sleep(3600)"]
      resources:
        requests: {memory: 32Mi}
        limits:   {memory: 64Mi}
```

申请 200 MiB，limit 只有 64 MiB —— 进程一碰内存就被 cgroup 杀掉，`restartPolicy: Always` 让它无限重启。

```bash
kubectl apply -f oom-demo.yaml
```

## 时间线

| 时间 | 事件 |
|---|---|
| 11:55:13 | 创建 Pod |
| 11:55:15 | 首次 `OOMKilled`（exit 137），kubelet 重启容器 |
| ~11:56:40 | 第 4 次重启，`increase(...[10m]) > 3` 条件满足 |
| 11:57:18 | 规则进入 `pending` |
| **11:58:18** | 规则 `firing`，**钉钉收到 1 条告警**（relay 回执 200） |
| 11:59:01 | 处置：`kubectl delete pod oom-demo` |
| 12:07:18 | 规则 `inactive`，钉钉收到恢复通知 |

## 现象与证据

**Pod 状态**：`RESTARTS` 一路涨（20 秒内就 2 次，3 分钟内 5 次），`STATUS` 在 `Running` 与 `CrashLoopBackOff` 之间来回。

```bash
$ kubectl -n demo get pod oom-demo
NAME       READY   STATUS             RESTARTS      AGE
oom-demo   0/1     CrashLoopBackOff   5 (30s ago)   3m48s
```

**判定是否 OOM 的关键字段**（光看 RESTARTS 不知道原因）：

```bash
$ kubectl -n demo get pod oom-demo \
    -o jsonpath='{.status.containerStatuses[0].lastState.terminated.reason} {.status.containerStatuses[0].lastState.terminated.exitCode}'
OOMKilled 137
```

**指标**：`kube_pod_container_status_restarts_total{namespace="demo",pod="oom-demo"}` 随重启递增，这是「Pod 频繁重启」规则的数据源。

**事件**：只有 `BackOff restarting failed container`，**事件里不会写 OOMKilled** —— 这点很坑，`kubectl describe` 的 Events 段落看不到根因，必须看 `lastState`。

**节点内存几乎没动**（一直 1671 MiB / 3623 MiB）：容器级 OOM 是 cgroup 层面的，宿主机不承压，所以「节点内存使用率过高」这条规则不会响。

## 根因

Python 进程一次性申请 200 MiB，超过 64 MiB 的 `limits.memory`。内核在 cgroup 内触发 OOM killer，容器以 SIGKILL 退出（`exit code 137`），kubelet 按 `restartPolicy` 重启，形成 CrashLoopBackOff。

## 恢复

```bash
kubectl -n demo delete pod oom-demo
```

真实场景的处置顺序：先止血（删 Pod / 回滚镜像 / 临时调大 limit），再查泄漏点。

## 经验

- **`exit 137` + `lastState.reason=OOMKilled` 是 OOM 的铁证**，只看到 `Restarts` 涨说明不了问题。
- **事件里没有 OOM 信息**，排障要直接读 Pod 的 `status.containerStatuses[].lastState`。
- **容器 OOM 不触发节点内存告警**，两条告警覆盖的是完全不同的故障面，不能互相替代。
- **恢复存在明显滞后**：11:59 就把 Pod 删了，直到 12:07 告警才解除，晚了 **8 分钟**。
  原因是规则用了 `increase(...[10m])`，历史上那几次重启要在 10 分钟窗口里滑出去才会归零，
  再加 `for: 1m`。这在真实故障里会让值班同学误以为"恢复了但还在报"。
- CrashLoopBackOff 的指数退避（10s → 20s → 40s…）也拉长了重启累计时间，演练时要有耐心。

## 改进项

- [ ] **缩短窗口**：`increase(...[10m]) > 3` 改为 `increase(...[3m]) > 2`，恢复滞后从 8 分钟压到 2 分钟内
- [ ] **加一条 OOM 专项告警**：`kube_pod_container_status_last_terminated_reason{reason="OOMKilled"} == 1`
      （已确认 kube-state-metrics v2.20.0 提供该指标，当前集群可查）
- [ ] 演练时顺手记录 `kubectl top pod` 与容器实际 RSS 曲线，作为扩容依据
- [x] 本次复盘归档
