# k3s 一体化运维平台

在 2 台 2C2G 阿里云 ECS 上搭建的轻量级业务运维平台：k3s 集群承载 Flask + MySQL 业务，配套 Ingress、监控告警、日志与故障演练。

> 这是一个**学习 + 简历**项目，目标是完整走一遍「部署 → 观测 → 故障 → 复盘」的运维闭环。

## 架构

```
开发者 push ──▶ GitHub Actions ──▶ 镜像仓库(ghcr.io / ACR)
                                      │ kubectl set image
                                      ▼
┌──────────────────────────────────────────────────────────┐
│ k3s 集群（2 节点，172.16.0.0/12）                          │
│                                                          │
│  ns: demo                      ns: monitoring            │
│  ┌─────────┐  ┌──────────┐     ┌────────────┐            │
│  │ web ×2  │─▶│ mysql    │     │ Prometheus │            │
│  │ Flask   │  │ Stateful │     │ Alertmgr   │──▶ 飞书    │
│  └────┬────┘  └──────────┘     │ Loki       │            │
│       │                        │ Grafana    │            │
│       ▼                        └────────────┘            │
│   Traefik Ingress（80/443）                               │
└──────────────────────────────────────────────────────────┘
```

## 技术栈

| 类别 | 组件 |
|---|---|
| 容器编排 | k3s v1.36.5（Kubernetes 轻量发行版） |
| 入口 | Traefik Ingress Controller |
| 业务 | Python Flask + PyMySQL |
| 数据库 | MySQL 8.0（StatefulSet + local-path 存储） |
| 监控 | Prometheus + Grafana + Alertmanager |
| 日志 | Loki + Promtail |
| 配置管理 | Ansible |
| 自动化 | GitHub Actions |

## 环境信息

| 角色 | 主机名 | 私网 IP | 公网 IP |
|---|---|---|---|
| master | iz2vcih52kdnj152u1buo0z | 172.26.13.50 | 8.156.73.132 |
| worker | k3s-node1 | 172.26.13.51 | 8.156.68.82 |

- 地域：华东/西南（cn-chengdu）
- 规格：2 vCPU / 2 GiB，Ubuntu 22.04
- 镜像加速：`/etc/rancher/k3s/registries.yaml`（docker.m.daocloud.io 等）

## 进度

- [x] 双节点 k3s 集群，节点 Ready
- [x] 配置镜像加速，解决 docker.io 超时
- [x] Traefik Ingress 贯通（nginx 验证，浏览器 200）
- [x] Flask + MySQL 业务部署（web:v1 镜像，2 副本跨节点，/api/time 返回数据库时间）
- [x] GitHub Actions 自动发布（push → 构建 ghcr 镜像 → kubectl set image 滚动更新 → 失败自动回滚）
- [x] Prometheus + Grafana 监控看板（8 个面板：CPU / 内存 / 磁盘 / 网络 / QPS / P95 / Pod 重启）
- [x] 告警链路（Grafana 告警规则 → Webhook → Relay → 钉钉，4 条规则已实测触发）
- [ ] Loki 日志查询
- [ ] 6 类故障演练（见 `drills/`）

## 当前状态（2026-10-27 收工）

**已完成**

| 项 | 说明 |
|---|---|
| 集群 | 2 节点 k3s v1.36.5，worker 2C4G |
| 业务 | Flask + MySQL，2 副本跨节点，`/api/time` 正常 |
| 入口 | Traefik Ingress，`pathType: Prefix` |
| 镜像 | ghcr.io 自动构建，k3s 配置了 docker.io / registry.k8s.io 加速 |
| CI/CD | GitHub Actions 全链路验证通过（kubeconfig 用 base64 存 Secret） |
| 监控 | Prometheus + 独立 Grafana（NodePort 30300），8 面板看板 |
| 告警 | Grafana 规则 → Webhook Relay → 钉钉，4 条规则实测触发与恢复 |
| 复盘 | `drills/00` Ingress 404、`drills/07` 节点停机级联故障 |

**进行中 / 待处理**

1. **Loki 日志**：未部署，Grafana 里还没有日志查询能力
2. **故障演练**：还差 5 个（磁盘打满、Pod OOM、节点宕机、MySQL 不可用、镜像拉取失败）
3. **master 仍是 2C2G**：暂不缺内存，但演练时跑大量 Pod 可能不够
4. **6443 安全组**：CI 验证后应改回 `118.113.89.85/32`
5. **GitHub Actions 部署 job 会失败**：6443 未对外开放，属预期；要长期自动部署需自托管 Runner

**下次开工顺序**

1. 确认环境：`kubectl get nodes`、`kubectl -n monitoring get pods`、`curl http://127.0.0.1/api/time`
2. 做故障演练，每个记三个时间点（注入 / 告警 / 恢复），写进 `drills/` 并更新 `演练记录表.md`
3. 装 Loki + Promtail，Grafana 加日志数据源
4. 补 README 截图与演练汇总（平均发现时间、MTTR）

## 目录结构

```
k3s-ops-lab/
├── README.md
├── ansible/                  # 节点初始化 playbook
├── app/                      # 业务应用
│   ├── app.py                # Flask 服务（/api/time 查 MySQL）
│   ├── requirements.txt
│   ├── Dockerfile
│   └── k8s/                  # K8s 清单
├── .github/workflows/        # CI/CD 流水线
├── monitoring/               # 监控配置
│   ├── values-prometheus.yaml
│   ├── alert-rules.yaml
│   ├── grafana-dashboard.json
│   └── feishu-relay/         # 告警转发到飞书
└── drills/                   # 故障演练与复盘记录
```

## 监控与告警效果

Grafana 看板（8 个面板，数据来自 Prometheus）：

![Grafana 监控看板](docs/grafana-dashboard.png)

告警经 Grafana 规则 → Webhook Relay → 钉钉群推送，触发与恢复各有一次通知：

![钉钉告警](docs/dingtalk-alert.png)

![钉钉告警恢复](docs/dingtalk-alert-resolved.png)

## 快速开始

```bash
# 1. 部署业务
kubectl apply -f app/k8s/

# 2. 验证
curl http://<node-ip>/api/time

# 3. 安装监控（待完成）
helm install kube-prom prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace -f monitoring/values-prometheus.yaml
```

## 故障演练记录

| 编号 | 主题 | 状态 |
|---|---|---|
| 00 | Ingress 404（pathType 不匹配） | ✅ |
| 01 | 节点磁盘打满 | ⬜ |
| 02 | Pod OOM | ⬜ |
| 03 | 节点宕机 | ⬜ |
| 04 | MySQL 不可用 | ⬜ |
| 05 | 误删配置 | ⬜ |
| 06 | 镜像拉取失败 | ⬜ |

## 备注

- 本项目为个人学习用途，节点为单点 master，不具备生产高可用能力
- 存储使用 local-path（本地盘），数据随节点丢失，生产环境应使用云盘或分布式存储
