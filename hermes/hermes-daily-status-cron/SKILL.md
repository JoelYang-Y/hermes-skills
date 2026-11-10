---
name: hermes-daily-status-cron
description: 模式——给 Hermes 配置一个每天固定时间、纯 shell采集的健康日报 cron job，推送到 Telegram 等渠道。零 LLM 开销、脚本 stdout 直接投递。
when_to_use: 用户要"每天XX点给我推送系统状态 / 健康报告 / 摘要"时；任务能用 hermes CLI + sqlite + 文件读取完成，不需要 LLM 推理时。
---

# 模式：Shell 采集脚本 + no_agent cron

## 适用场景

- 周期性健康检查、状态摘要、日报
- 任务能完全靠 `hermes status`、`hermes cron list`、`hermes mcp list`、`sqlite3 ~/.hermes/*.db` 这类 CLI + SQL 完成- 不需要 LLM 推理（这样选 `no_agent=True` 省 token / 零延迟）

## 三步落地

### 1. 写 shell 脚本到 `~/.hermes/scripts/xxx.sh`

要点：
- `set -u`（不要 `-e`，让 warn 不致命）
- 用 `hermes status --deep` 解析 Gateway / Telegram，用 `hermes mcp list` 解析 MCP——别用 `pgrep -f hermes`（launchd 管理的进程 pgrep 找不到）
- 输出格式：`✅ ok` / `⚠️ warn` / `🚨 fail` 三种前缀，一屏可读
- macOS 的 `wc -l` 输出含换行，统计行数用 `printf '%s\n' "$var" | grep -c .`，别用 `echo "$var" | wc -l`
- DB 完整性：`sqlite3 "$DB" "PRAGMA integrity_check"` 必须返回 `ok`

### 2. `chmod +x` 然后手动 dry-run

```bash
chmod +x ~/.hermes/scripts/xxx.sh
bash ~/.hermes/scripts/xxx.sh
```

跑通后再注册 cron，避免 scheduler 执行失败重试污染日志。

### 3. 注册 cron job（关键参数组合）

```python
cronjob(
  action="create",
  name="<人类可读名>",
  schedule="0 8 * * *",           # cron 表达式
  script="xxx.sh",                # 相对 ~/.hermes/scripts/，**不要带路径**
  no_agent=True,                  # 纯 shell，不调用 LLM
  deliver="telegram",             # stdout 直接投到 home channel
)
```

**重要陷阱**：
- `no_agent=True` 必须有 `script`——没有 script 时 API 返回 `requires a script`
- `script` 是**相对路径**，相对于 `~/.hermes/scripts/`
- prompt 在 no_agent 模式下被忽略，但 API 仍要求传非空字符串（传占位符即可）

### 4. 立即验证

```python
cronjob(action="run", job_id="<id>")  # 触发一次（不一定立刻执行）
sleep 15
hermes cron list  # 看 Last run 字段是否更新 + ok
```

`Last run: <时间> ok` 即代表脚本跑通 + Telegram 投递成功。

## 常见输出模板（可直接复用）

```
🤖 Hermes 日报 · 2026-06-10 06:44

✅ Gateway: 运行中 (PID 52682)
✅ Telegram: 已配置
✅ MCP (3): minimax-coding-plan, minimax-official, tavily
✅ 最近报错 (24h): 0

🧠 记忆索引
  条目分布：
    • fact: 7
    • profile: 1
✅  合计: 8 条
✅  向量索引: 8 条
✅  FTS5 索引: 8 条
✅  待压缩 (short): 0
✅  24h 新增: 6 条
✅  DB 完整性: ok

📅 Cron 任务
✅  活跃: 5  暂停: 0

──────────────
📡 Hermes 自动健康检查
```

## Pitfalls（踩过的坑）

- **macOS `wc -l` 多余换行**：`echo "$var" | wc -l` 在 macOS 给的是 `"<n>\n<empty>\n"` —— `[ "$n" -gt 0 ]` 报 `integer expression expected`。改用 `grep -c .` 或 `printf '%s\n' "$var" | grep -c .`
- **launchd 进程 pgrep 找不到**：macOS 下 Hermes gateway 由 launchd 管理，`pgrep -f hermes` 没结果。要从 `hermes status --deep` 解析 `Status: ✓ running` 和 `PID(s)`
- **MCP 列表要专门命令**：`hermes status` 不显示 MCP server，要用 `hermes mcp list`
- **API Server 字段不存在**：`hermes status --deep` 不会显示独立 API server 状态（已合并到 Gateway 行）。脚本里别单独查这条，否则永远 unknown
- **next_run 时间含义**：Hermes cron 的 `Next run` 是下一次"未触发的08:00"，如果当前是 06:45 它显示**当天** 08:00，不是次日。验证时要看当前时间 vs Next run 关系判断