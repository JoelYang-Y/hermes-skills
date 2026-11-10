---
name: hermes-system-optimization
description: 用于 Hermes 全系统深度体检、Mem0 记忆精简及服务链路打通。
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [hermes, mem0, qdrant, health-check, optimization, cleanup, homelab]
---

# Hermes 及其全生态系统全量深度体检与优化工作流 (Hermes System Optimization)

本技能提供针对 Hermes Agent 核心、Mem0 Qdrant 向量记忆库、本地缓存日志、Cron 调度任务及全内网/云端基础设施的全链路深度体检、去重精简与加速打通的标准作业流（SOP）。

## When to Use

- 用户要求“全量优化 Hermes”、“清理精简记忆”、“检查系统健康状态”或“打通各服务链路”
- 用户要求“检测/体检云服务器”、“检查服务器有没有问题”——**不要只跑第四阶段的连通性探测就算完**，按 `references/server-fleet-audit.md` 逐台做主机级审计
- 发现 Hermes 向量检索变慢、上下文夹带陈旧重复事实或 System Prompt 膨胀时
- 经历大型项目迭代后，需清理临时执行缓存、归档大日志并执行容灾快照时
- 局域网服务或云端 VPS 发生网络/配置变动后，需执行毫秒级全链路端到端健康探测

---

## 四阶段标准化执行流程 (The 4-Stage Pipeline)

```
┌───────────────────────────┐     ┌───────────────────────────┐
│ 1. Mem0 向量记忆深度精简  │ ──> │ 2. 本地缓存与日志瘦身     │
│ (Qdrant 10.0.0.3:6333)    │     │ (~/.hermes/cache & logs)  │
└───────────────────────────┘     └───────────────────────────┘
              │                                 │
              ▼                                 ▼
┌───────────────────────────┐     ┌───────────────────────────┐
│ 3. Cron 任务与容灾备份测试│ ──> │ 4. 全内网/云端毫秒级体检  │
│ (hermes_backup_local.py)  │     │ (10.0.0.1~6 + Public VPS) │
└───────────────────────────┘     └───────────────────────────┘
```

---

### 第一阶段：Mem0 向量记忆库体检与深度精简

1. **连接 Qdrant 检查集合状态**：
   - 目标地址：`http://10.0.0.3:6333/collections/hermes_memories_v2_hybrid`；
   - 检查 `points_count` 与 `indexed_vectors_count`，健康基准为 100~130 条高密度黄金记忆。
2. **执行语义扫描与批量去重**：
   - 扫描重叠的临时爆料碎片、已被新架构覆盖的中间草稿及陈旧二级域名记录；
   - 调用 Qdrant `/points/delete` 批量清理，彻底消除向量稀释与 Token 冗余。

---

### 第二阶段：Hermes 本地运行时与日志缓存清理

1. **清理临时执行缓存**：
   ```bash
   rm -rf ~/.hermes/cache/terminal-output/*
   rm -rf ~/.hermes/audio_cache/* 2>/dev/null || true
   ```
2. **截断与归档过期历史日志**：
   - 检查 `~/.hermes/logs/` 占用；
   - 删除超过 7 天的滚动归档大日志（`*.log.*`），释放磁盘空间。
3. **配置基准核对**：
   - 确保 `~/.hermes/config.yaml` 主模型为 `google/gemini-3.7-flash` (Vertex AI Global)。

---

### 第三阶段：Cron 定时任务调度器与本地容灾备份

1. **遍历 Cron 任务执行状态**：
   - 调用 `cronjob(action='list')`，确认记忆自动整理（`9e45d46a3b58`）、每日状态推送（`0c61c44aba2f`）等 6 大任务处于 `scheduled` 活跃状态。
2. **手动触发本地全量快照备份**：
   ```bash
   python3 ~/.hermes/scripts/hermes_backup_local.py
   ```
   - 验证 Qdrant 向量点、实体库、`mem0.json`、`config.yaml`、`.env` 成功备份至 `~/hermes-backups-local/`。

---

### 第四阶段：全内网与云端服务毫秒级连通性实测

运行自动化探测脚本，覆盖全拓扑节点并输出诊断表格：

| 节点类型 | 探测目标 | 目标地址与端口 | 预期健康基准 |
| :--- | :--- | :--- | :--- |
| **主路由** | ASUS BE88U 路由器 | `http://10.0.0.1` | < 15ms (HTTP 200) |
| **本地网关** | Surge Web Controller | `http://10.0.0.2:6171` | < 20ms (HTTP 200) |
| **NAS 容器** | Qdrant / Sub-Store / Homelable / Kuma / Beszel / Emby | `10.0.0.3` 各服务端口 | < 5ms (HTTP 200) |
| **PVE 物理机** | PVE Web 控制台 | `https://10.0.0.4:8006` | < 15ms (HTTP 200/302) |
| **代码工作器** | 本机 DeepSeek Harness CLI（遵循 `local-dsh-coding`） | `/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh` | `--version` 已验证；不使用旧远程 WebUI 延迟指标 |
| **DNS 枢纽** | AdGuard Home 控制台 | `http://10.0.0.6:3000` | < 5ms (HTTP 200) |
| **云端主站** | 导航大屏与代码库 | `https://jhsweetheart.com` | CDN 边缘加速 (HTTP 200) |
| **云端密码库** | Vaultwarden | `https://oracle.jhsweetheart.com`| 专线直连 (HTTP 200) |
| **云端运维** | 搬瓦工 1Panel | `https://joel.jhsweetheart.com/Joel`| CN2 GIA (HTTP 200) |

**连通性只是底线，不是体检。** HTTP 200 只证明进程活着，不证明配置正确。主机级的服务/端口/容器/证书续期/Fail2ban 白名单/待装更新审计，以及两类高频配置漂移（证书续期矩阵、ignoreip 白名单漂移）的查法与报告形态，见 `references/server-fleet-audit.md`。
