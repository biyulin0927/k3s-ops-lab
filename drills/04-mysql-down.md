# 04 · MySQL 不可用（数据库单点故障）

- **日期**：2026-10-28
- **类型**：主动演练（依赖服务不可用）
- **影响**：`/api/time` 全量 500，持续约 3.5 分钟；数据无丢失（PVC 保留）
- **环境**：k3s v1.36.5，MySQL 8.0 StatefulSet（local-path，单副本）

## 目的

1. MySQL 挂掉时，业务侧的报错长什么样、`kubectl` 能不能看出来
2. 哪些告警会响、响几条、多久响
3. 恢复后多久解除

## 注入

```bash
kubectl -n demo scale statefulset mysql --replicas=0
```

选 `scale 0` 而不是 `delete pod`：`delete pod` 会被 StatefulSet 立刻重建，只有十几秒窗口，测不出告警的 `for` 逻辑。

## 第一次注入：只有一个告警响了

| 时间 | 事件 |
|---|---|
| 12:30:10 | `scale --replicas=0` |
| 12:30:11 | `/api/time` 立刻 500 |
| ~12:31:00 | `probe_success` 变 0 |
| **12:33:11** | 「入口不可用」`firing`，钉钉收到 1 条 |
| 12:33:49 | 恢复：`scale --replicas=1` |
| 12:34:10 | MySQL Ready，业务恢复 200 |
| 12:35:11 | 钉钉收到恢复通知 |

**发现耗时 3 分 01 秒**（全靠 blackbox 探针）。

但「应用 5xx 比例过高」这条规则**从头到尾没有响**。查下来：

```bash
$ curl -s '.../api/v1/query?query=http_requests_total'
{"data":{"resultType":"vector","result":[]}}     # 空
```

**Prometheus 里根本没有 `http_requests_total`** —— 业务 Pod 从来没被采集过。
这条 5xx 规则从部署那天起就是死的，`noDataState: OK` 让它永远显示"正常"。
这是继 08 号"入口没探针"之后的**第二个监控盲区**，而且更隐蔽：规则存在、图表有、就是没数据。

### 两个容易误判的细节

**报错是 DNS，不是连接拒绝**：

```
{"error":"(2003, \"Can't connect to MySQL server on 'mysql' ([Errno -2] Name does not resolve)\")"}
```

MySQL 用的是 headless Service（`clusterIP: None`），Pod 一没，Endpoints 就空，
DNS 直接返回 NXDOMAIN。看到 `Name does not resolve` 容易先怀疑 CoreDNS 挂了。

**web 一直显示 Ready**：readiness 探针打的是 `/healthz`（只返回 "ok"，不查库），
所以数据库挂了，k8s 仍然认为这个 Pod 健康 —— `kubectl get pods` 一片绿，`/api/time` 全 500。
`记录表` 里那句"readiness 未覆盖数据库依赖"说的就是这个。

## 改进：补上业务指标采集

新增 `monitoring/servicemonitor-web.yaml`，并给 `demo/web` 这个 Service 补上 `app: web` 标签
（ServiceMonitor 靠标签选 Service）：

```yaml
spec:
  namespaceSelector:
    matchNames: [demo]
  selector:
    matchLabels: {app: web}
  endpoints:
    - port: http
      path: /metrics
```

应用后 1 分钟内就出现了数据：

```bash
$ curl -s '.../api/v1/query?query=http_requests_total'
{"metric":{"path":"/api/time","status":"200"},"value":"2"}   # 有数据了
```

> 副作用：`kubectl apply -f app/k8s/20-web.yaml` 同时把 web 副本数从 1 恢复成了清单里的 2
> （07 号演练时手动缩到 1 缓解内存，之后没改回去）。现在两个副本分布在两个节点上，符合原始设计。

## 第二次注入：两条告警同时响

| 时间 | 事件 |
|---|---|
| 12:36:39 | 再次 `scale --replicas=0` |
| ~12:38:00 | 「5xx 比例过高」`firing`（5xx 占比 **92.76%**） |
| 12:39:10 | 钉钉收到 5xx 告警 |
| 12:40:11 | 「入口不可用」也 `firing`，钉钉再收 1 条 |
| 12:41:34 | 恢复：`scale --replicas=1` |
| 12:41:55 | MySQL Ready，业务 200 |
| 12:43:11 | 钉钉收到「入口不可用」恢复 |
| 12:47:10 | 钉钉收到「5xx」恢复 |

## 根因

MySQL 单副本 + local-path 存储，`scale 0` 后 Endpoints 清空，headless Service 的 DNS 解析失败，
web 的连接池拿不到连接，每个 `/api/time` 都 500。业务层没有任何熔断/降级/缓存。

## 恢复

```bash
kubectl -n demo scale statefulset mysql --replicas=1
kubectl -n demo wait --for=condition=Ready pod/mysql-0 --timeout=120s
```

约 20 秒 MySQL 就绪，数据完好（PVC 未动）。

## 经验

- **headless Service + 单副本 = 硬依赖**：DB 一没，DNS 都没有，报错看起来像集群 DNS 故障。
- **`kubectl get pods` 全绿不等于业务可用**：readiness 只探进程存活，不探依赖。
- **规则存在 ≠ 规则有效**：`noDataState: OK` 会把"没有数据"伪装成"一切正常"。
  上线一条告警规则后，必须确认它真的有数据（Prometheus 里查得到序列、Grafana 里能看到评估值）。
- **一次故障触发多条告警**：MySQL 挂 → 5xx + 入口不可用，值班时会被轰炸。
  两条告警是同一个根因，需要抑制（inhibition）或分组，否则告警一多就没人细看。
- **5xx 规则恢复慢**：`rate(...[5m])` 的窗口让恢复通知比实际恢复晚了 **5 分钟**（12:41:55 恢复，12:47:10 才解除）。

## 改进项

- [x] 新增 `servicemonitor-web.yaml`，业务指标真正被采集，5xx 规则生效并实测
- [x] 给 `demo/web` Service 补 `app: web` 标签
- [ ] **readiness 覆盖数据库依赖**：`/readyz` 里查一次 `SELECT 1`，DB 挂了 web 变 NotReady，
      Ingress 会摘掉后端（返回 503 而不是 500），语义更准
- [ ] **告警抑制**：MySQL 不可用时抑制"入口不可用"/"5xx"，只保留根因告警
- [ ] **5xx 窗口 `[5m]` → `[2m]`**，缩短恢复判定
- [ ] **排查其它 `noDataState: OK` 的规则**：确认每一条都有真实数据，避免再有"僵尸规则"
