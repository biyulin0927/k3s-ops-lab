# 01 · 节点磁盘打满（触发驱逐）

- **日期**：2026-10-28
- **类型**：主动演练（资源耗尽）
- **影响**：第一次注入把 worker 推到 97%，触发 **DiskPressure + 驱逐**，
  监控栈（Prometheus / Grafana / Alertmanager）被赶走，业务网页副本被驱逐但整体可用
- **环境**：k3s v1.36.5，worker 根分区 40 GiB（ext4）

## 目的

1. 磁盘水位到什么程度会触发 kubelet 驱逐
2. 「磁盘使用率过高」告警（>85%，`for: 5m`）能不能在驱逐之前叫出来
3. 驱逐之后怎么恢复、要多久

## 第一次注入：直接冲到 97%，翻车

```bash
fallocate -l 25G /var/lib/diskfill.bin      # 13:41:34
df -h /                                     # 36G used / 1.4G avail / 97%
```

**这里踩了第一个坑**：20 GiB 的盘面被 ext4 保留块吃掉一部分，
`fallocate 25G` 之后实际可用只剩 **1.4 GiB（3.4%）**，已经低于 kubelet 的 5% 驱逐线。

| 时间 | 事件 |
|---|---|
| 13:41:34 | 填充到 97% |
| 13:41:5x | 节点 `DiskPressure=True`，开始驱逐 |
| 13:42:00 | Prometheus / Grafana / Alertmanager / operator / web 副本陆续被驱逐 |
| 13:42:2x | 手工 `rm` 填充文件，磁盘回到 17% |
| 13:42–13:47 | `DiskPressure` 持续 **5 分钟**（kubelet 的状态过渡期）才转 False |
| 13:47:09 | 节点恢复可调度，Pod 开始重建 |
| 13:50 | Grafana 卡在 `0/1`（旧 Pod `ContainerStatusUnknown` 占着 `Recreate` 槽位），手工强删后恢复 |

**告警一次都没响** —— 不是规则写错，而是**监控组件自己在 30 秒内被驱逐了**。
规则要连续 5 分钟满足条件，而系统在 1 分钟内就把观测能力清空了。

## 第二次注入：停在 87%，成功观测

吸取教训，先算好水位：`23.5G` 填充 → **87.3%**，可用 5.0 GiB（12%），安全落在
「告警线 85%」和「驱逐线 5% 可用」之间。

| 时间 | 事件 |
|---|---|
| 13:49:31 | 填充到 87.3%，无 DiskPressure |
| 13:50:17 | 「磁盘使用率过高」进入 `pending` |
| **13:54:48** | 规则 `firing` |
| **13:55:13** | 钉钉收到 1 条告警（回执 200） |
| 13:56:08 | 处置：`rm /var/lib/diskfill.bin`，回到 24% |
| 13:56:44 | 规则 `inactive` |
| 13:57:13 | 钉钉收到恢复通知 |

发现耗时 **5 分 17 秒**（5 分钟 `for` + 1 分钟评估）。

## 根因与机制

- **kubelet 驱逐阈值**：`nodefs.available < 5%`、`imagefs.available < 5%`
  （用 `kubectl get --raw /api/v1/nodes/<node>/proxy/configz` 可查）。
  40 GiB 的盘，5% 只有 2 GiB —— 换算成使用率约 **88% 就要开始驱逐**。
- **告警阈值 85% + `for: 5m`** 与驱逐线只差 2–3 个百分点，窗口非常窄。
  真实故障里磁盘写满常常是分钟级的，等 5 分钟告警等于等驱逐。
- **ext4 保留块**让 `df` 的百分比和"可用空间"脱节：97% 时可用只剩 1.4 GiB，
  比按容量算出来的少。

## 恢复

```bash
rm -f /var/lib/diskfill.bin        # 释放空间（1 秒）
# 节点 DiskPressure 需要 5 分钟过渡期才会消除
# 卡住的旧 Pod（ContainerStatusUnknown）需要手工清理：
kubectl -n monitoring delete pod <stuck-pod> --force --grace-period=0
```

## 经验

- **填盘要看 `avail`，不要看百分比**：同样 87%，可用 5 GiB 和可用 1.4 GiB 是两回事。
- **告警阈值和驱逐阈值之间必须有足够缓冲区**。85% 告警 + 88% 驱逐，中间只有几分钟，
  等于"告警刚响就开始驱逐"。分层告警（80% warning / 85% critical）才有反应时间。
- **驱逐是"连坐"的**：它按资源压力挑 Pod，不区分业务和监控。
  监控组件没有 `priorityClassName`，被一视同仁地赶走 ——
  这已经是第三次出现"监控和被监控对象同生共死"（03、04、01）。
- **`ContainerStatusUnknown` 的僵尸 Pod 会卡住 `Recreate` 滚动**：
  新旧两个 Pod 同时存在，新 Pod 起不来也删不掉旧的，必须手工强删。
- **恢复动作只要 1 秒，系统自愈要 5 分钟**：MTTR 里很大一块是等待状态过渡。

## 改进项

- [ ] **磁盘分层告警**：80% warning、85% critical（现在只有 85% 一条）
- [ ] **关键组件加 `priorityClassName: system-cluster-critical`**，
      降低 Prometheus / Grafana / Alertmanager 被驱逐的概率
- [ ] **监控组件与业务分节点部署**（03 号结论，本次再次验证）
- [ ] **给 kubelet 设更保守的驱逐阈值**或给根分区留固定 reserve，避免"刚好卡在边界"
- [ ] 演练脚本化：先按 `avail` 计算目标水位，并在填充过程中每 10 秒检查 `DiskPressure`，
      超线立即回滚（本次第二次注入用了看门狗脚本，效果良好）
