---
name: cron-delivery-verification
description: "Use when 建/验收 cron 投递与脚本任务. 不信字段, 显式地址."
version: 1.0.0
author: skill-keeper
license: MIT
metadata:
  hermes:
    tags: [cron, delivery, telegram, no_agent, verification]
    related_skills: [hermes-daily-status-cron, session-digest-memory-cron, cross-bot-skill-intake]
---

# cron 投递与脚本任务的验收规矩

建定时任务容易，敢说它”真的能用“难。本文件是踩出来的验收标准：每条都是从一次真实失败里回来的。

## When to Use（适用条件）

- 要新建一个会向外部渠道（Telegram 等）投递的定时任务。
- 或者：任务“显示成功”但人没收到，需要定位是没送、送错地方还是根本没跑。
- 不适用：纯本地会话内的对话测试（那种直接看屏幕即可）。

## 铁律（均为实测，不是推测）

### 1. 投递字段不是送达证据

`last_status: delivery_queued` + `last_delivery_error: null` + 没有 `BLOCKED` ——**三个字段全绿，仍然可能一个字都没送到**。队列接受不等于平台接受，平台接受不等于人收到。

**验收只能以接收端确认**：问人“收到没”，而不是引用字段。把字段当证据，就会在“已成功”的假前提上做后续决策。

### 2. `deliver: telegram` 靠 home channel，未设就静默不发

裸写 `deliver: telegram` 解析的是该 profile 的**默认投递会话**。未配置它时，任务排队“成功”、无报错、但消息无处可送。

**正确写法是显式地址**：`telegram:<chat_id>`（私聊场景 `chat_id` = 用户的 Telegram user id，跨 bot 通用，前提是用户已对该 bot 发过消息）。

### 3. `deliver` 指向不可达目标会让整轮不跑

preflight 发现投递目标不可达时，agent 根本不启动，任务状态 `BLOCKED (configuration)`（不扣费也不产出）。所以**改主力任务的投递前，先拿一个低风险任务试路**——用”多推一份“换”主力任务停摆“的交换不划算。

### 4. `script` 只收相对文件名，且建任务时就校验存在

cron 的 `script` 参数必须是 `~/.hermes/profiles/<profile>/scripts/` 下的**纯文件名**：绝对路径被拒（`Script path must be relative`），文件不存在也建不起来（`Script file not found`）。所以想用脚本，必须先把文件落好。

### 5. 无人值守脚本必须 ASCII-only

中文与全角标点经粘贴链路传输时会被腐蚀；一个脏字节就足以让 `set -u` 下的变量展开报 `AFTER\ufffd: 未绑定的变量` 而整轮崩掉。**脚本正文写英文/ASCII，中文只放在给人看的对话里**；落盘后跑 `LC_ALL=C grep -n '[^ -~]' <script>` 应无输出。

### 6. `no_agent` 模式：stdout 就是全部输出

脚本 stdout 原样投递；**空输出什么都不发**（watchdog 模式）；非零退出或超时会触发失败告警。所以脚本要保持安静——“无变更”这类话也应明确打印，否则人分不清“没事”与“没跑”。

### 7. 脚本自己必须自证成功

不信命令自己的输出：

- 推送类 → 回读远端（`git ls-remote origin HEAD` 比对本地 HEAD），不信 `git push` 的成功提示；
- 归档类 → 逐条检查源文件是否真的出现在目标里，缺一个就退非零；
- 镜像类 → 连跑两次，第二次必须“无变更且无空提交”（幂等是验收测试）。

### 8. 时区与命名

cron 表达式按 profile 时区解释；跨时区用户要显式传 `timezone`。profile 改名会让 `deliver: bot-chat` 报 `profile_mismatch`，需改成 `bot-chat:<新profile名>`。

## 验收清单

1. 任务建好先 `run` 一次，而不是等到点。
2. 看输出里有没有脚本自己的成功自证（远端回读 / 完整性检查）。
3. **让人确认收到**，才把“已启用”改成“已验证”。
4. 幂等任务连跑两次，第二次不应产生新提交。
5. 把 `paused=true` 建任务的本事用上：源或目标没核实前先暂停，别让它夜里自动跑一轮假成功。

## 安全边界与失败停止

- 不把密钥、token 写进脚本；需要凭据时依靠已有配置或环境变量。
- 投递目标不确定时宁可只写 `bot-chat`，也不搭一个可能静默失败的渠道。
- 发现“字段绿但未送达”立即回滚投递配置，不在错误前提上继续调。

## 来源

- 2026-11-08 实测：job `b8b8e2ef61f8`（技能库同步 GitHub）— 依次在源目录错误、坏字节、假成功投递上失败；最终用 `telegram:<chat_id>` 显式地址送达并获 Joel 确认。
- 2026-11-08 实测：job `f51267133b78`（每日会话沉淀）— 3 分钟硬上限下的预算纪律、`skill_manage` 在无人值守下未被 write_approval 拦截。
- 事实：字段表现、报错文本（`Script path must be relative`、`AFTER\ufffd: 未绑定的变量`、`BLOCKED (configuration)`）均来自真实回执。
- 推断/待验证：chat_id 跨 bot 通用仅在私聊场景成立（群聊每个群一个 id）；home channel 未设是“静默不发”的原因，未读到源码，属最合理推断。
