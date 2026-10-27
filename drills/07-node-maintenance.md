# 07 · 节点停机升配引发的级联故障

- **日期**：2026-10-26
- **类型**：计划内变更 → 非预期故障
- **影响**：业务中断约 40 分钟，master SSH 一度无法登录
- **环境**：k3s v1.36.5，master 2C2G / worker 2C2G

## 背景

为给监控组件腾出内存，决定把 worker 从 2C2G 升配到 2C4G。阿里云变更实例规格需要先停机。

## 时间线

| 时间 | 事件 |
|---|---|
| 19:10 | 停止 worker 实例，准备变配 |
| 19:12 | 业务 `/api/time` 不可用，80 端口关闭 |
| 19:15 | 尝试 SSH master，密码后立即 `Connection reset` |
| 19:20 | 端口探测：master 22/6443 开、80 关；worker 22 开、80/6443 不通 |
| 19:25 | worker 变配完成并启动，k3s-agent 自动恢复 |
| 19:30 | 通过控制台 Workbench 登入 master |
| 19:31 | `kubectl get nodes` 两节点 Ready，Pod 自动重建（各重启 1 次） |
| 19:33 | 缩容 web 至 1 副本缓解内存压力 |
| 19:35 | 业务恢复，`/api/time` 返回 200 |

## 根因分析

1. **单 master 且承担业务 Pod**：worker 下线后，master 独自承载控制面 + 业务，2C2G 内存被压到 400M 以下
2. **内存压力导致 sshd 会话被杀**：`Connection reset` 不是网络问题，是内核在内存紧张时终止新会话
3. **MySQL 使用 local-path 存储**：PVC 绑定 worker 节点，节点下线期间 Pod 无法在其他节点重建，业务必然中断
4. **Traefik 的 svclb 副本随节点下线**，80 端口短时不可用

## 处置

1. 用控制台 **Workbench / VNC** 绕过 sshd 进入系统（关键动作）
2. `kubectl -n demo scale deploy web --replicas=1` 降低内存压力
3. 等 worker 变配完成、k3s-agent 重新注册
4. 确认 Pod 重建、业务端口恢复

## 经验

- **计划内停机也要按故障标准对待**：先评估单点依赖，再动手
- **SSH 连不上不代表机器挂了**：先做端口探测（22/6443/80），区分「进程问题」与「网络问题」
- **云控制台的 VNC 是最后的救命通道**，务必提前记住入口
- **local-path 存储天然钉死节点**，生产环境需用云盘/分布式存储才能跨节点漂移
- 单 master + 业务混跑是学习环境的妥协，不是生产架构

## 改进项

- [ ] master 升配至 2C4G，避免控制面被业务挤占
- [ ] 监控组件全部调度到 worker（已通过 nodeSelector 实现）
- [ ] 评估把 MySQL 存储换成阿里云云盘（StorageClass 可跨节点）
- [ ] 演练报告归档，作为面试时的真实案例
