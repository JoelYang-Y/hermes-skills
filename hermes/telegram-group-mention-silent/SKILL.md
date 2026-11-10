---
name: telegram-group-mention-silent
description: "Use when 群里 @Bot 无响应. 查白名单+隐私模式."
version: 1.0.0
author: skill-keeper
license: MIT
metadata:
  hermes:
    tags: [hermes, telegram, gateway, botfather, diagnostics]
    related_skills: [bot-tooling-provisioning, hermes-operations]
---

# 群聊里 @Bot 无响应：双拦截定位

Hermes 的 Telegram 适配器在群聊里有两道各自独立、都会「静默丢弃」（不打日志、不建会话）的拦截。先把两道都排掉，再去怀疑网络或 token。

## When to Use（适用条件）

- 某个 Bot 在私聊正常，但在群里 @ 它 / 叫它名字完全没有反应，`session_search` 里也没有该群的新会话。
- 典型触发：新 Bot 上线后第一次进群；某 Bot 改名或换群后突然「失联」。
- 不适用：私聊也失联（走 `proxy-chain-diagnostics` / `hermes-operations` 的网关排查）。

## 前置依赖

1. 能读到目标 profile 的 `config.yaml`（`telegram.allowed_chats`、`require_mention`）。
2. 能读 `~/.hermes/telegram_update_receipts_*.json` 与 `~/.hermes/logs/gateway.log`。
3. 能 `getMe`（只需要 bot token 已在环境里，**不要**把 token 打印出来）。
4. 群 id 形如 `-100xxxxxxxxxx`（与会话 id `telegram:group:-100…` 对应）。

## 输入 → 输出

- 输入：目标 profile 名 + 群 id + 失联时间窗。
- 输出：判定属于哪一道拦截（或两道叠加），以及一份「改一行 + 重启一次」的修复提案（改配置与重启须另行获批）。

## 诊断步骤（按代价从低到高）

1. **先看是否只是被白名单挡掉**：读目标 profile 的 `telegram.allowed_chats`，只有逗号分隔的 chat id 才放行；私聊 id（`19…`）不等于群 id（`-100…`）。
2. **确认消息确实到达了本机**：`telegram_update_receipts_*.json` 里该群的时间戳正常、`gateway.log` 里没有该群的 `inbound message` 行 —— 说明 update 收到了但被适配器层丢弃，不是网络问题。这一步能把「没收到」与「收到但被滤」彻底分开。
3. **查适配器源码确认语义**：`plugins/platforms/telegram/adapter.py` 的 `_should_process_message()` 首条校验即 `if allowed and chat_id_str not in allowed: return guest_mention`，即白名单已设且群不在其中时只放行 guest-mode 显式提及，普通消息一律丢弃且**不写日志**。
4. **查隐私模式**：`getMe` 返回 `can_read_all_group_messages: false` 说明 BotFather 隐私模式开着，群里非 @ 的消息它本来就收不到；此时群名、「记忆管家」这类中文称呼都**不是** mention，只有真正 `@<bot_username>` 或回复它的消息才算。

两道都命中时，白名单是确定性死因，隐私模式是「即使开放白名单，不 @ 也不触发」的第二道限制。

## 修复（**待验证**：从未实际执行）

- 在目标 profile 的 `config.yaml` 里把群 id 追加进白名单：`allowed_chats: '<私聊CHAT_ID>,-100xxxxxxxxxx'`（两个都是占位符，实际取值现场读配置），改前先把 `config.yaml` 复制一份备份。
- 重启该 profile 的网关 `hermes -p <profile> gateway restart`（约 15 秒）—— 必须由 Joel 在外部终端执行，会话内不得重启。
- 验证：在群里发 `@<bot_username> 测试`，应新建 `telegram:group:-100…` 会话；仍无响应则说明隐私模式仍在滤消息，再到 BotFather `/setprivacy → Disable`（只能在 Telegram 里由用户点）。
- 代价要在提案里写明：开放白名单后该群的对话会进这个 Bot 的会话库，日后的记忆提取会把它当素材读。

## 风险与安全边界

- 只读诊断可自由做；改 `config.yaml` 与重启网关属于配置变更，须先给精确 diff 并取得 Joel 确认。
- **chat id 一律写占位符**（`<私聊CHAT_ID>`、`-100xxxxxxxxxx`）：本技能库每晚 23:30 镜像到**公开** GitHub 仓库，写真实 chat id 等于把个人信息发布出去。现场取值时现读配置，不抄进文档。
- 不要把 bot token、群邀请链接、成员信息写进简报或技能。
- 不因排障去改 `require_mention`、不擅自把 Bot 移出隐私模式之外的配置。

## 失败停止条件

- 白名单已含该群、`getMe` 也显示可读群消息，但仍无任何 update → 停止，转 `proxy-chain-diagnostics`（可能是出网/端点问题），不要继续改配置。
- 修改后仍无响应 → 停在该步并如实报告，不要连环改第二处配置来「试出来」。

## 回滚

- `config.yaml` 从改前备份还原（去掉追加的群 id），再重启一次网关即可；不删任何会话，已产生的群会话可保留或另行归档。

## 来源

- 2026-11-09 00:33 会话（default profile，第二手实测）：@session:default/20261109_003303_8e4cd5fe —— 该会话里 `allowed_chats` 仅含一个**私聊 chat id**（本文件一律用 `<私聊CHAT_ID>` 占位）、`adapter.py:6412 _should_process_message()`、`telegram_update_receipts` 与 `gateway.log` 的「11 条更新 / 零会话 / 零 inbound 日志」对照、`getMe` 的 `can_read_all_group_messages: false` 均为真实工具输出。
- 事实：两道拦截的判定逻辑、白名单取值、隐私模式状态、静默丢弃无日志的行为均有上述输出佐证。
- 推断 / 待验证：修复 diff 与重启只被提出而**未执行**，因此「改白名单 + 重启即可恢复」仍是假设；隐私模式与 `require_mention` 的叠加效果同理。
