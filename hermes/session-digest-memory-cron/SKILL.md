---
name: session-digest-memory-cron
description: "Use when 建/改每日会话→mem0 记忆提取 cron. 只读素材+查重写入."
version: 1.1.0
author: skill-keeper
license: MIT
metadata:
  hermes:
    tags: [hermes, memory, mem0, cron, session-digest]
    related_skills: [hermes-daily-status-cron, mem0-oss-operations, hermes-operations]
---

# 每日会话 → 长期记忆提取管道

把「各 profile 一天的会话」压成素材，交给 agent 模式 cron 提炼后写入 mem0。
与 `hermes-daily-status-cron`（纯 shell + `no_agent`、零 LLM）互补：那条管道只报状态，不做语义提炼。

## When to Use（适用条件）

- 需要「自动从聊天里记住事情」，且写入目标是 mem0（OSS + Qdrant，单库多 profile 共享）。
- 会话权威源是 `~/.hermes/state.db`（`sessions` / `messages` 两表），**不是** `~/.hermes/sessions/*.jsonl`（后者停在 2026-09 前后，已非权威）。
- 不适合：只想要固定文本播报（用 `no_agent` 脚本），或需要实时响应（用每 30 分钟级巡检类任务）。

## 前置依赖

1. `state.db` 可读（只读连接即可，禁止写）。
2. 目标 profile 已配好 mem0（`plugins.enabled:[mem0]`、`memory.provider:mem0`、`.env` 的 `MEM0_MODE=oss`、且**该 profile 单独** `plugins install mem0`；插件不跨 profile 共享）。
3. cron 的投递目标在该 profile 真实可达（见「坑 3」）。

## 输入 → 输出

- 输入：时间窗口（建议 26h，含 2h 重叠防边界丢失）内的 `user`/`assistant` 消息。
- 输出：① 注入 agent prompt 的素材正文；② 归档 `~/.hermes/state/memory-digest/digest-<YYYYMMDD-HHMM>.md`（目录 `700`、文件 `600`，保留最近 14 份）；③ 一条简报（扫描量 / 新增 / 跳过原因）。

## 步骤

### 1. 写采集脚本（只读、可重复跑）

放 `~/.hermes/scripts/hermes_memory_extract.py`（profile 级脚本放 `~/.hermes/profiles/<p>/scripts/`）。核心规则：

- **只读打开**：`sqlite3.connect(f"file:{db}?mode=ro", uri=True)` — 采集器任何情况下都不该拿到写能力，`mode=ro` 是硬保证而不是约定。
- **排除 `role='tool'`**：实测近 24h 的 tool 输出约 500KB，而 user+assistant 正文仅 ~21KB；不排除会让 prompt 预算瞬间爆掉。
- **排除 `s.source='cron'`**：否则 bot 会提取自己的报告，形成自我循环。
- **裁剪预算**：单条 ≤1200 字符；总量 ≤45K 字符；user 消息全保，assistant 按时间倒序填剩余预算（用户原话是判断偏好的唯一可靠依据）。
- **噪声过滤**：纯 `MEDIA:/` 路径、以及「好/ok/继续/嗯」这类 <8 字符确认语直接丢。
- **空窗口要退出码 0 并打印「无需写入」**：让 cron 自己决定不投递，而不是报错重试。

主查询（实测 0.005–0.08s）：

```sql
SELECT m.id, m.session_id, m.role, m.content, m.timestamp,
       s.source, s.title, s.started_at
FROM messages m JOIN sessions s ON s.id = m.session_id
WHERE m.timestamp >= ?
  AND m.role IN ('user','assistant')
  AND m.content IS NOT NULL AND LENGTH(TRIM(m.content)) > 0
  AND COALESCE(m.active,1) = 1
  AND s.source <> 'cron'
ORDER BY m.timestamp ASC
```

### 2. 手动 dry-run（必须，先于注册 cron）

```bash
python3 ~/.hermes/scripts/hermes_memory_extract.py --hours 26 | head -40
python3 ~/.hermes/scripts/hermes_memory_extract.py --hours 0.01   # 空窗口边界
ls -l ~/.hermes/state/memory-digest | head -3                    # 期望 600 权限
```

### 3. 注册 agent 模式 cron

```python
cronjob_manage(
  action="create",
  name="Hermes 每日会话记忆提取",
  schedule="30 23 * * *",              # 当天会话结束后、次日 00:15 记忆整理之前
  script="hermes_memory_extract.py",    # 相对 ~/.hermes/scripts/
  deliver="<该 profile 可达的投递目标>",
  continuity=True,                     # 让每轮看见上次简报，天然去重
  # 不要传 enabled_toolsets —— 见坑 1
  prompt="<自包含的提取规则，见下>")
```

prompt 里必须写死的提取规则（缺一条就会污染记忆库）：

- 值得写：用户偏好/纠正/决策、环境与基础设施事实、项目状态与架构决策、反复出现的工作流约定。
- 不写：一次性问答、调试过程、任务流水账、cron 自动报告、常识、已在库中的内容。
- **写入前先 `mem0_search` 换 ≥2 种措辞查重**；已有相似条目用 `mem0_update` 合并，不新建。
- 单日上限（实测按 6 条）且**可以为 0 条**；每条自包含、日期开头、≤400 字符。
- **密码/密钥/token/私钥/助记词的值一律不入库**，只可记「某服务有凭据，存放位置 X」。
- 不删除任何记忆（压缩合并归 00:15 的全库整理任务）。

### 4. 验收

```python
cronjob_manage(action="run", job_id="<id>")   # 后台触发，结果自动回传
```

- 回传里 `Status: ok` + 有 API calls 与耗时，说明素材注入与 mem0 工具都通（实测 4 calls / 57s）。
- **写后回读**（不要相信「Fact stored」）：

```bash
curl -s -X POST "http://<nas-host>:6333/collections/<collection>/points/count" \
  -H "Content-Type: application/json" -d '{"exact":true}'
```

条数应等于轮次前的条数 + 本轮新增；实测 99 → 101 条、43,450 → 44,309 字符，与简报宣称的 2 条一致才算通过。

## 坑（均为实测，不是推测）

1. **`enabled_toolsets` 白名单必须含 `memory`**。mem0 是插件提供的工具，不在 `TOOLSETS` 表里：
   - 实测 A（2026-11-08 首建）：传 `enabled_toolsets=["terminal"]`，`mem0_search/mem0_add` 直接不可用，只能删任务重建。
   - 实测 B（2026-11-08 反例）：传 `["memory","terminal"]`，mem0 工具全部可用——同一 profile 的整理 cron 在该组合下完成 12 次 `mem0_update` + 15 次 `mem0_delete`，Qdrant 回读一致。
   - 结论：要么不传，要么显式带上 `"memory"`；只列 `terminal` 才会砍掉插件工具。
2. **cron 沙箱禁止代码执行**。无人值守会话里 `execute_code` 被 BLOCKED，`terminal` 的 heredoc（`python3 - <<'PY'`）同样被判危险而拦截；可行的替代是单条 `curl -s -X POST ... -d '<JSON>'` 加 `jq`。脚本逻辑必须预先落成文件，不要指望在 cron 里现拼多行命令。
3. **preflight 会因投递目标不可达整轮不跑**。若 `deliver` 指向该 profile 尚未连通平台，任务状态是 `BLOCKED (configuration)`，agent 根本不启动（不扣费）。为新建 profile 建 cron 时，先把 `deliver` 指向该 profile 确实存在的目标，或先接通平台。
4. **素材里可能有明文凭据**。用户会在聊天里贴密码/隧道命令，脚本按原样归档即等于把秘密落盘。因此：目录 700、文件 600；**禁止把 digest 原文投递到任何渠道**，只投简报；prompt 里再显式禁止入库。
5. **26h 窗口必然重叠**：重叠部分靠「先查重后写入」兜底，不要改成精确 24h（会丢跨零点会话）。
6. **容量红线**：记忆库参考上限 **80,000 字符**，80%（约 **64,000 字符**）为合并触发线 —— 2026-11-08 用户授权扩容，原 40,000 / 32,000 口径已作废。**不要再按旧值判断越线**：曾据此把当时的 101 条 / 44,309 字符误报成越线并触发不必要的合并提议。提取任务只增不删，一旦简报报出越线（>64,000），另行安排合并，不要在本管道里顺手删。

## 安全边界与失败停止

- 只读 `state.db`；不改任何 profile 配置、不改 cron 表达式以外的参数。
- mem0 后端未初始化（典型报错 `No module named 'sentence_transformers'`）：**停止本轮并如实报告**，由用户在外部终端补依赖 + `hermes gateway restart`；不要在本会话内重启 gateway，也不要改 config 去绕过。
- 素材导出失败 → 退出码 3、简报里报错，不静默。
- 写入条数超出预期、或回读条数与简报不符 → 停止后续写入并报告，不重试「补写」。

## 回滚

纯增量：脚本与归档目录删除即可复原；cron 用 `cronjob_manage(action="pause")` 停用（删除需用户确认）；已写入的记忆不回滚，按用户显式授权走 `mem0_delete`。

## 来源

- 2026-11-08 会话 `@session:default/local-74e97fc24909abb681ce42622e3a8e1e29a4e1ef2c14994803a0e2fd06427480`（创建脚本 + 建 job `1c1d9477760f` + 首次 run 实测 ok）。
- 2026-11-08 会话 `@session:memory-keeper/local-6e1e4ae23ee86e277aa739c713ec21212685c7957e82bcc2bc4e2750980826f7`（坑 2、坑 3 实测复现；本轮写入 2 条并回读核对）。
- 2026-11-08 反例修正（坑 1）：`@session:memory-keeper/local-0f32b3d15756639c4c7d610fd17b308245df61892bdce3c782e8efa1843a359b` 与 `@session:memory-keeper/local-e11f4669d9f2b3a10c07e0ebc74c077dc1801a40a3a6cb1ec3cb53f75981b4bc`——`enabled_toolsets=["memory","terminal"]` 下 mem0 工具正常，证明「传 enabled_toolsets 必砍 mem0」的旧结论过宽。
- 事实：脚本参数、cron 参数、run 结果、Qdrant 计数均来自上述真实工具输出。
- 推断/待验证：memory-keeper 侧脚本后续加了水位线与补查（据 mem0 记录，未核源码）；其简报称可跨 4 个 profile 聚合，机制未亲自验证。
