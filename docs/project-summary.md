# 项目总结 · 简历描述与面试准备

> 面向"运维 / SRE / DevOps / 云原生"岗位，内容全部来自本仓库的真实操作记录，
> 数字可在 `drills/` 和 `README.md` 中逐条核对。

---

## 一、简历版描述

### 一句话（简历标题行）

> 基于 k3s 的双节点云原生运维平台：容器化 Flask + MySQL 业务，配套 CI/CD、可观测性（指标/日志/告警）与 9 场故障演练闭环。

### 简历条目（建议 4 条，按岗位取舍）

```
· 在 2 台 2C4G 阿里云 ECS 上用 k3s 搭建双节点集群，部署 Flask + MySQL 业务，
  通过 Traefik Ingress 对外提供服务，用 local-path 提供持久化存储。
· 搭建 Prometheus + Grafana 可观测体系：8 个监控面板、6 类告警规则（9 条），
  经 Webhook Relay 推送钉钉，所有规则均实测「触发 → 恢复」全链路。
· 部署 Loki + Promtail 日志系统（CRI 日志采集、7 天保留）与 4 面板日志看板，
  支持按 namespace / Pod / 容器检索，补齐指标之外的排障手段。
· 设计并完成 9 场故障演练（Ingress 404、磁盘打满、Pod OOM、节点宕机、MySQL 不可用、
  配置误删、镜像拉取失败等），沉淀复盘文档，把「平均发现时间」从小时级压到 4 分钟级，
  并在演练中定位并修复 5 个监控盲区。
```

### 数字版（面试时口头用）

| 指标 | 数值 |
|---|---|
| 集群规模 | 2 节点，各 2 vCPU / 4 GiB / 40 GiB |
| 业务组件 | Flask（2 副本跨节点）+ MySQL 8.0（StatefulSet） |
| 告警规则 | 9 条，全部实测触发与恢复 |
| 可观测 | 指标 8 面板 + 日志 4 面板，7 天留存 |
| 故障演练 | 9 场（7 场主动 + 2 次真实故障） |
| 告警类故障平均发现时间 | **4 分 12 秒**（4 次统计） |
| 演练暴露并修复的缺陷 | 5 条（见下文） |

---

## 二、架构与关键决策（面试主线）

```
GitHub Actions ──▶ ghcr.io 镜像 ──▶ kubectl set image（默认跳过，受 6443 白名单限制）
                                          │
k3s 集群                                   ▼
├── demo ns        web ×2 (Flask) ──▶ mysql-0 (StatefulSet + local-path)
│                  Traefik Ingress → svclb（80/443）
└── monitoring ns  Prometheus / Grafana / Alertmanager / blackbox（worker）
                   Loki + Promtail（master，刻意分开）
                   Alert Relay（master）──▶ 钉钉
```

### 决策 1：为什么用 k3s 而不是 kubeadm

两节点 2C4G 的实验机跑不动标准控制面。k3s 把 etcd 换成 SQLite（默认）、组件打包成单进程，
空载内存约 500 MiB，适合边缘/学习环境。
**代价**：默认单点控制面，不具备生产高可用；SQLite 不支持多 master。面试要说清楚这是取舍而非无知。

### 决策 2：为什么存储用 local-path，以及它的坑

local-path 是 k3s 自带的最小实现，直接绑定节点本地盘，部署零成本。
**代价**：Pod 被"钉"在节点上——07 号演练里 worker 停机变配，MySQL 无法漂移，业务直接中断 40 分钟。
生产环境应换云盘 CSI（可跨节点挂载）或直接用 RDS。这是本项目最典型的"知道坑在哪"的案例。

### 决策 3：告警用 Grafana 内置规则，而不是 Alertmanager

kube-prometheus-stack 自带 Alertmanager，但两条链路（Grafana 规则 + Alertmanager）会让排障复杂。
统一到 Grafana：规则、路由、联系人、静默都在一处，且规则可随 ConfigMap 声明式下发（`Provisioned`）。
**代价**：Alertmanager 的 `inhibit_rules` 用不上，抑制只能写在 PromQL 里（见决策 4）。

### 决策 4：告警抑制为什么不用 Alertmanager 的 inhibition

需求：MySQL 挂掉时，5xx 和入口探针会同时报警，希望只留根因。
标准做法是 Alertmanager `inhibit_rules`，但 Grafana 内置 Alertmanager 的配置由 provisioning 接管，
改抑制规则会和声明式配置打架。于是改用**规则级抑制**：

```promql
# 根因：MySQL TCP 探针
min(probe_success{job="blackbox-mysql"}) < 1

# 5xx 只在 MySQL 最近 5 分钟持续可用时评估
... and on() (min_over_time(probe_success{job="blackbox-mysql"}[5m]) == 1)

# 入口：MySQL 挂了就把它顶成 1
min(probe_success{job="blackbox-web-http"}) + (1 - min(probe_success{job="blackbox-mysql"}))
```

实测：停库期间只有「MySQL 不可用」触发，恢复后也不会补发过期告警。
**面试价值**：能讲清"为什么不用标准方案"和"这个替代方案的边界"（可读性差、逻辑耦合在表达式里）。

### 决策 5：日志组件为什么放 master

03/04/01 三次演练都出现"节点故障 → Prometheus/Grafana 一起失联"。
Loki 放 master 与指标栈分开，至少不会同时丢两类观测数据。
但指标栈仍在 worker，属于已知限制（见第六节）。

### 决策 6：readiness 查库

04 号演练发现：MySQL 挂了，web Pod 仍然 `Ready`（`/healthz` 只证明进程活着），
Ingress 继续把流量打过去，用户拿到 500。
改造后新增 `/readyz` 执行 `SELECT 1`，DB 不可用 → Pod NotReady → Ingress 摘后端 → 用户拿到 **503**。
**503 和 500 的语义被分开了**：503 是"暂时没后端"，500 是"应用真出错"。

---

## 三、9 场演练的关键数据

| 编号 | 故障 | 发现方式 | 发现耗时 | 关键结论 |
|---|---|---|---|---|
| 00 | Ingress 404 | curl | 40 min | `pathType` 默认 Exact 的坑；用 port-forward 切割问题层 |
| 01 | 磁盘打满 | 钉钉 | 5m17s | 85% 告警与 88% 驱逐线太近；ext4 保留块让"可用"远小于"剩余" |
| 02 | Pod OOM | 钉钉 | 3m05s | `exit 137` + `lastState.reason` 才是判据；事件里不写 OOM |
| 03 | 节点宕机 | **无** | 未发现 | 监控栈与被监控对象同节点，一起失联 |
| 04 | MySQL 不可用 | 钉钉 | 3m01s | 5xx 规则从来没数据；headless Service 报 DNS 错；readiness 不查库 |
| 05 | 误删配置 | **无** | 未发现 | 删 ConfigMap 不影响运行中的 Pod；通知失败不重试 |
| 06 | 镜像拉取失败 | 补规则后 | 5m24s | 原规则全漏；镜像站对不存在 tag 返回 403 而非 404 |
| 07 | 节点停机变配 | 人工 | 2 min | 计划内变更也要按故障标准评估单点依赖 |
| 08 | 主机名变更（真实） | 人工 | 4h18m | 只改运行时主机名 → 节点重复注册；Traefik informer 不自杀；flannel FDB 缺失 |

### 演练暴露并修复的 5 条缺陷

1. **入口没有可用性探针**（08）→ 加 blackbox-exporter，30s 探测两个节点入口
2. **5xx 规则从没数据**（04）→ Prometheus 根本没采集业务 `/metrics`，补 ServiceMonitor
3. **镜像拉取失败无告警**（06）→ 基于 `kube_pod_container_status_waiting_reason` 新增规则
4. **告警配置无法声明式恢复**（05）→ relay 的 ConfigMap 改由 kustomize `configMapGenerator` 生成
5. **重启窗口过长 / 无 OOM 专项**（02）→ 窗口 10m→3m，新增 OOMKilled 规则与磁盘 80% 预警

---

## 四、踩过的坑（面试最爱问"你遇到过什么难题"）

### 1. 改主机名把集群搞挂了 4.5 小时
`hostname master` 只改运行时，`/etc/hostname` 没变。k3s 重启后以新名字注册出第二个节点，
旧节点对象残留且占着旧网段；Traefik 的 informer 在 apiserver 重启窗口坏掉后不自愈，全站 404；
worker 的 flannel FDB 表缺表项，跨节点 Pod 网络单向不通。
**修复**：固化静态主机名 → 删幽灵节点 → 重建 svclb/traefik → 补 FDB（事后验证 agent 重启会自动重建）。
**教训**：改主机名等于换节点身份，属于控制面变更，必须先 drain。

### 2. 磁盘告警"来不及响"
按容量算 87% 应该有 5G 可用，但 ext4 有保留块，实际只剩 1.4G，直接击穿 kubelet 5% 驱逐线。
监控组件被一起驱逐，告警根本没发出去。
**修复**：改看 `avail` 不看百分比；告警线降到 80% 做预警；演练时用看门狗脚本盯 `DiskPressure`。

### 3. "监控是绿的，但业务是挂的"
08 之前 Pod 全 Running、5xx 为 0，但入口 404 了 4.5 小时。
**根因**：监控只覆盖"资源"和"应用自报指标"，没有从外部视角验证"用户能不能访问"。
**修复**：blackbox 探针 + 告警规则；后来又发现 5xx 规则根本没数据（noDataState 把"无数据"伪装成"正常"）。

### 4. 通知链路自己断了，没人知道
删掉 relay 的 ConfigMap 后 Pod 起不来，Grafana 通知全部 `connection refused`，且**只失败一次就丢弃**。
**修复**：relay 改 kustomize 管理；记录"Watchdog 心跳"的必要性（还没做，是已知缺口）。

### 5. 镜像 tag 不存在，报的却是 403
加速镜像站对不存在的 tag 返回 403 而不是 manifest unknown，很容易误判成"私有仓库认证问题"。
**判据**：看 pod events 和 `waiting.reason`，不要凭 HTTP 码猜。

---

## 五、高频面试题与回答要点

### K8s / 架构

**Q1：为什么用 k3s？和 kubeadm 有什么区别？**
k3s 把控制面打包成单进程、默认 SQLite、内置 Traefik/ServiceLB/local-path，安装一条命令，空载约 500 MiB；
kubeadm 组件独立、默认 etcd、需要自己装 CNI/Ingress。小规模/边缘选 k3s，生产多 master 选 kubeadm。

**Q2：你的集群高可用吗？**
不高可用，且我知道差在哪：单 master（SQLite 不支持多 master）、MySQL 单副本 + local-path 绑定节点、
监控栈全在 worker。07/03/01 三次演练分别验证了这三种单点。

**Q3：Pod 一直 Pending 怎么排查？**
`describe pod` 看 Events：调度失败（资源不足/污点/亲和性）、镜像拉取失败（ImagePullBackOff）、
PVC 未绑定、节点 NotReady。06 号演练就是镜像拉取失败，特征 `RESTARTS=0`。

**Q4：CrashLoopBackOff 和 ImagePullBackOff 的区别？**
前者容器起来了但反复退出（看 `lastState.terminated.reason` 与 exit code）；后者容器根本没创建成功。
02 号 OOM 是前者（137/OOMKilled），06 号是后者。

**Q5：readiness 和 liveness 的区别？为什么要分开？**
liveness 失败重启容器，readiness 失败只是摘流量。把 DB 检查放在 liveness 里会导致数据库抖动时
把所有 Pod 重启一遍——所以本项目 liveness 用 `/healthz`，readiness 用查库的 `/readyz`。

**Q6：Service 有哪几种类型？headless 有什么用？**
ClusterIP / NodePort / LoadBalancer / ExternalName。headless（`clusterIP: None`）直接返回 Pod IP，
供 StatefulSet 做稳定 DNS。本项目 MySQL 用 headless，所以 Pod 一没，DNS 直接 NXDOMAIN——
04 号演练里这个报错一度让人以为 CoreDNS 挂了。

### 监控告警

**Q7：你们怎么保证告警"真的会响"？**
三条：每条规则上线后主动注入故障验证触发与恢复；定期核对 Prometheus 里是否有数据
（曾发现一条 5xx 规则从来没有数据）；对 noDataState 保持警惕——它会掩盖"规则已死"。

**Q8：告警太多怎么办？**
先降噪：分层（80% 预警 / 85% 严重）、抑制（根因触发时压掉症状）、分组（同 alertname 聚合）。
本项目用 PromQL 做根因抑制，因为 Grafana 内置 Alertmanager 的 inhibit_rules 与声明式配置冲突。

**Q9：为什么不用 Alertmanager？**
不是不用，是"不额外引入"。kube-prometheus-stack 自带 Alertmanager，但本项目把规则统一收敛到
Grafana 内置告警（可与 ConfigMap 一起声明式管理）。代价是失去 inhibit_rules，用 PromQL 替代。
如果规模更大、需要复杂路由/静默/抑制，会切到 Alertmanager。

**Q10：监控指标和日志怎么分工？**
指标回答"有没有问题/趋势如何"（Prometheus），日志回答"为什么"（Loki）。
本项目指标 8 面板、日志 4 面板；Loki 放 master 与指标栈分开，避免单节点故障一起丢。

### 故障排查

**Q11：入口 404 和 503 分别说明什么？**
404 = 路由没匹配（Ingress/Traefik 配置问题，00 号演练）；503 = 路由匹配但没有可用后端
（Pod 不 Ready / Endpoints 为空，readiness 改造后 DB 故障就返回 503）。

**Q12：跨节点 Pod 不通，但 kubectl 一切正常，怎么查？**
按层：Pod IP → ClusterIP → NodePort → Ingress。都正常就看 vxlan：`bridge fdb show dev flannel.1`，
缺表项会导致 nolearning 模式下直接丢包。08 号故障就是这么定位的。

**Q13：节点 NotReady 时 Pod 会怎样？**
kubelet 停止上报 → node controller 打 NotReady（默认 40s）→ 5 分钟后开始驱逐。
容器可能仍在 containerd 里跑，所以 `kubectl get pods` 显示的是最后上报的旧状态——03 号演练验证过。

### CI/CD

**Q14：你的 CI/CD 是怎么做的？为什么 deploy 会跳过？**
GitHub Actions：push → 构建镜像推 ghcr → `kubectl set image` 滚动更新 → 失败回滚。
但 6443 安全组只放行本机公网 IP（`/32`），托管 Runner 连不上 API Server，
所以 deploy job 加了 `ENABLE_DEPLOY` 开关，默认 `skipped`。真要自动部署需要自托管 Runner。

**Q15：滚动更新怎么保证不中断？**
`maxUnavailable: 0` + `maxSurge: 1`，配合 readiness 探针（现在会查库），新 Pod 就绪后旧 Pod 才下线。

### 反思类

**Q16：这个项目最大的不足是什么？**
三处单点（master、MySQL 存储、监控栈同节点），以及没有集群外探活——
节点整个挂掉时，集群内的告警链路也一起没了。还有 flannel FDB 的问题只是规避，没有根治。

**Q17：如果重做，你会改什么？**
① 存储换云盘 CSI，让 MySQL 能漂移；② 监控与业务分节点，或引入集群外探活；
③ 从第一天就把所有配置纳入 Git（05 号演练就是因为 ConfigMap 是手工创建的，误删后只能靠记忆恢复）；
④ 告警规则上线即做"注入验证"，而不是等演练才发现规则是死的。

---

## 六、已知限制（主动说出来，比被问出来好）

1. **单 master**：k3s + SQLite，控制面不具备高可用
2. **MySQL 单副本 + local-path**：节点故障时无法漂移（07 号演练实测中断 40 分钟）
3. **监控栈与业务同节点**：节点/磁盘故障时指标与看板一起失联（03/04/01 三次验证）
4. **没有集群外探活**：整节点挂掉时，告警发不出去
5. **告警抑制是 PromQL 级**：不如 Alertmanager `inhibit_rules` 通用
6. **CI 不能自动部署**：6443 白名单限制，需自托管 Runner

---

## 七、可以继续做的（面试时作为"下一步"讲）

- 存储换云盘 CSI，验证 MySQL 跨节点漂移
- 引入集群外 blackbox（或用云监控）做真正的"外部视角"
- Watchdog 心跳告警（收不到即链路故障）
- 自托管 GitHub Runner，打通自动部署
- 压测（k6/locust）+ HPA，把"容量"也纳入演练
