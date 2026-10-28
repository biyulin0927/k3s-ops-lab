# 06 · 镜像拉取失败（ImagePullBackOff）

- **日期**：2026-10-28
- **类型**：主动演练（配置错误 / 镜像不存在）
- **影响**：单 Pod 无法启动，业务无影响（演练 Pod 与 web 隔离）
- **环境**：k3s v1.36.5，worker 2C4G，镜像走 daocloud 加速

## 目的

1. 复现镜像拉取失败，确认 `kubectl` 侧的可观测信号
2. 检验现有告警能不能发现"Pod 起来了但永远起不来"
3. 如果发现不了，补一条规则并验证

## 注入

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: badimage-demo
  namespace: demo
spec:
  restartPolicy: Always
  nodeSelector:
    kubernetes.io/hostname: k3s-node1
  containers:
    - name: app
      image: docker.io/library/nginx:1.0.0-does-not-exist
      imagePullPolicy: Always
      resources:
        requests: {cpu: 10m, memory: 16Mi}
        limits:   {memory: 32Mi}
```

```bash
kubectl apply -f badimage.yaml
```

## 第一次注入：现有告警完全没反应

| 时间 | 事件 |
|---|---|
| 12:11:57 | 创建 Pod |
| ~12:12:10 | `ErrImagePull`（拉取被拒） |
| 12:13:26 | 进入 `ImagePullBackOff`，Pod 一直 `Pending` |
| 12:16:56 | **已过 5 分钟：5 条规则全部 `inactive`，钉钉零通知** |
| 12:17:02 | 删除 Pod（无恢复通知，因为本来就没告警） |

这 5 分钟里发生了什么：

```bash
$ kubectl -n demo get pod badimage-demo
NAME            READY   STATUS             RESTARTS   AGE
badimage-demo   0/1     ImagePullBackOff   0          4m59s
```

**`RESTARTS` 是 0** —— 所以「Pod 频繁重启」不会响；**没有流量** —— 所以 5xx 不会响；
容器根本没启动，节点内存/磁盘也没有任何波动 —— 另外两条也不会响。
这是一个纯粹的**监控盲区**，只要不主动 `kubectl get pods`，这个 Pod 可以躺一整天。

### 一个容易误判的细节：403 而不是 404

```
message=Back-off pulling image "docker.io/library/nginx:1.0.0-does-not-exist":
  failed to resolve reference ...: unexpected status from HEAD request to
  https://docker.m.daocloud.io/v2/library/nginx/manifests/1.0.0-does-not-exist?ns=docker.io: 403 Forbidden
```

加速镜像站对**不存在的 tag** 返回的是 **403 Forbidden**，不是 `manifest unknown`。
看到 `403` 很容易先怀疑"私有仓库没配 imagePullSecret / 认证过期"，实际只是 tag 写错了。
判据要看 `reason=ErrImagePull/ImagePullBackOff` 和 Pod 事件，而不是凭 HTTP 码猜。

## 改进：新增「Pod 镜像拉取失败」规则

kube-state-metrics v2.20.0 提供 `kube_pod_container_status_waiting_reason`，可直接判定：

```promql
kube_pod_container_status_waiting_reason{reason=~"ImagePullBackOff|ErrImagePull"} > 0
```

写进 `monitoring/grafana-standalone.yaml`，`for: 3m`，severity `warning`，`noDataState: OK`
（指标消失说明 Pod 已不在，不该报警）。

## 第二次注入：规则生效验证

| 时间 | 事件 |
|---|---|
| 12:17:52 | 重新创建同一个 Pod |
| ~12:18:30 | 进入 `ImagePullBackOff`，指标出现 |
| 12:21:52 | 规则 `pending` |
| **12:23:16** | 规则 `firing`，**钉钉收到 1 条告警**（relay 回执 200） |
| 12:23:52 | 处置：删除 Pod |
| 12:25:16 | 规则 `inactive`，钉钉收到恢复通知 |

发现耗时 **5 分 24 秒**（3 分钟 `for` + 1 分钟评估间隔 + 拉取重试），
恢复后 **1 分 24 秒**解除并发出恢复通知 —— 比 02 号那个 8 分钟滞后好得多，因为这里是瞬时指标。

## 根因

镜像 tag 不存在（写成 `1.0.0-does-not-exist`），且 `imagePullPolicy: Always` 强制每次拉取。
kubelet 重试按指数退避，最终停在 `ImagePullBackOff`，Pod 永远 `Pending`、`Ready=False`。

## 恢复

```bash
kubectl -n demo delete pod badimage-demo
# 或修正 image tag 后 apply
```

## 经验

- **"Pod 没起来"和"Pod 老重启"是两类故障**，前者的特征是 `RESTARTS=0` + `Pending`，
  只盯重启次数的告警一定漏。
- **镜像站的 403 会误导排障方向**：先看 pod events 与 `waiting.reason`，再谈认证。
- `ImagePullBackOff` 是**可观测的**，前提是有人去看；补规则的成本只有一条 PromQL。
- 新规则用瞬时指标，恢复判定快（1 分钟级），不像 `increase()` 那样有窗口滞后。

## 改进项

- [x] 新增「Pod 镜像拉取失败」告警规则并实测触发与恢复
- [x] 记录 403 与 manifest unknown 的差异，避免误判为认证问题
- [ ] 把 `imagePullPolicy` 与 CI 的 tag 规范绑起来（`latest` + `Always` 的组合最容易踩）
- [ ] 若后续接入 Loki，可对 `Failed to pull image` 事件做日志侧告警，与指标告警互备
