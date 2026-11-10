---
name: email-imap-mcp-setup
description: "Use when 接入邮箱到 Hermes(IMAP/MCP). 选型+认证+策略+坑."
version: 1.0.0
author: skill-keeper
license: MIT
metadata:
  hermes:
    tags: [email, imap, mcp, setup, auth, policy]
    related_skills: [mail-inbox-readonly-triage]
---

# 邮箱接入 Hermes（IMAP + MCP）

把用户的真实邮箱接进 Hermes：选对服务器、过厂商认证、钉住策略边界、验收到能收发。
配套技能：接入完成后做周期性巡检，见 `mail-inbox-readonly-triage`。

## When to Use（适用条件）

- 要把用户的个人邮箱（Gmail / QQ / Outlook 等）接入 Hermes，让它能读信、写信、跑巡检。
- 或者：已接入但报认证失败 / 发件后对方没收到 / 策略改了没生效，需要排错。
- 不适用：想要一个「agent 自己的信箱」而不是读用户邮箱——那是 Hermes 的 `platforms.email` 网关适配器，两回事。

## 前置依赖

- 目标 profile 已能跑 MCP server（本文件以 `mcp-email-server` 为例）。
- 厂商侧已开启 IMAP 服务并拿到**应用专用密码 / 授权码**（见下，两个都不一样）。
- 能读到该 profile 的 `config.yaml` 与 `~/.config/mcp-email-server/`（托管模式下策略存 `managed.sqlite3`）。

## 输入 → 输出

- 输入：厂商名、账号（**只用占位符**）、应用密码/授权码、期望的能力边界（能不能发、能不能删、能不能下载附件）。
- 输出：一份 `mcp_servers.mail` 配置 + 一个收窄过的策略 + 一份逐项实测的验收记录。

## 1. 选型（有反例，别踩）

- **首选 `mcp-email-server`**（PyPI，`uvx mcp-email-server@<pin> stdio`）：21 个工具、多账号、自带策略引擎与收件人白名单——策略是它最大的价值，别自己造。
- **Google 官方 Gmail MCP 对个人号不可用**：`gmailmcp.googleapis.com` 仍在 Developer Preview，仅限 Workspace 且需加入预览计划，**且工具集不含 send**。个人 Gmail 不要往这条路上试。
- Hermes 自带的 `platforms.email` 适配器是「给 agent 一个自己的信箱」，**不是读用户邮箱**，不要混用。

## 2. 三家邮箱的认证现实

- **Gmail**：开两步验证 → 生成 16 位应用密码 → **还必须在网页端「转发和 POP/IMAP」里启用 IMAP**。漏第三步会报认证失败，极容易误判成密码错——先查这一项再怀疑凭据。
- **QQ**：设置 → 开启 IMAP/SMTP 服务 → 微信扫码 → 生成 16 位授权码（**不是 QQ 密码**）。改 QQ 密码会让授权码立即失效。
- **Outlook / hotmail / live.com 个人号**：微软自 2024-09 关闭 SMTP/IMAP 基本认证，**应用密码同属基本认证，已失效**，报 `5.7.139 basic authentication is disabled` / `AUTHENTICATE failed`；SMTP AUTH 于 2026-04-30 全关。唯一路径是 Microsoft Graph（`Mail.Read`/`Mail.ReadWrite`/`Mail.Send` 委托权限，个人号可授权）+ 自建 Azure 应用注册；企业 M365 还需租户管理员同意。**不要在 Outlook 个人号上试应用密码，那是死路。**

## 3. 配置写法

```yaml
mcp_servers:
  mail:
    command: "/opt/homebrew/bin/uvx"              # 绝对路径
    args: ["mcp-email-server@<pin>", "stdio"]      # 钉版本
    trust: untrusted
    timeout: 180
    connect_timeout: 90
```

- **必须用 uvx 绝对路径**：MCP 子进程只继承过滤后的环境，`PATH` 缺 `/opt/homebrew/bin` 会**静默起不来**（没有明确报错，最难查）。
- **必须钉版本**：`allowed_recipients` 空白名单的语义在 1.7.0 变过（旧版「空 = 不限制」，新版「空 = 拒绝所有收件人」）。用 `@latest` 会在某次升级后**行为反转**。
- 凭据放服务器自己的 SQLite（`uvx ... ui` 录入），**不要进 config.yaml / .env**。
- **`hermes mcp add` 没有 `--trust` 参数**，装出来是 `trust: full`；要 `untrusted` 只能手写 config 字段。`hermes mcp configure` 也只切工具、不切 trust。

## 4. 发送控制的正确层次（这才是真防线）

`trust` 不是防线（见坑 1），真正的硬边界在服务器策略：

1. **`allowed_recipients`**：空 = 拒绝所有收件人（已实测）。要限定收件人就在这里写死。
2. **`allowed_mutations`**：默认含 `delete`；**移除 `delete` 即可在服务器层硬性禁止删信**，不需要任何审批机制配合（实测返回 `Mutation class 'delete' is not allowed`）。
3. **`enable_attachment_content` / `enable_attachment_download` 分开控制**：读附件内容可开，下载落盘保持关。

改策略（托管模式）：

```bash
unset PYTHONPATH PYTHONHOME VIRTUAL_ENV   # 不 unset 会继承 Hermes venv 的 pydantic_core，CLI 直接崩
uvx mcp-email-server@latest config policy            # 先读当前 revision 与各项值
uvx mcp-email-server@latest config update-policy --expected-revision <N> \
    --allowed-recipients '*' --allowed-mutations 'draft,organize,send'
```

- `--expected-revision <N>` 是乐观锁：**先 `config policy` 读当前值再写**，别猜 N。具体保留哪几项按你的需要定，原则是**不出现 `delete`**。
- V2 的 `ui` 界面只有「Email accounts」「Settings & help」两块，**没有策略面板**，别去界面里找白名单。

## 5. 坑（每条都真实踩过）

1. **`trust: untrusted` 在本版本不生效**：`send_email`/`email_command` 等写工具**不会**弹审批卡片。别把只读性寄托在 trust 上，只能靠服务器策略 + prompt 硬禁。
2. **验证审批门不要用 `hermes -p X -z`**：单次查询走 `single_query_mode=deny`，会伪造「用户未批准」的假象（已误判过）。要验就在**交互会话**里看有没有真弹出审批卡片，或看无人值守运行时是否实际被拒。
3. **QQ 报 `sent-copy: failed` 是假警报**：QQ 会把发件归档进 `Sent Messages`，而该文件夹**没有 `\Sent` 特殊标记**，服务器按默认名 `Sent` 找不到就报错。正解是 `account update <id> --no-save-to-sent`；**不要去修 APPEND**，修好了会产生**双副本**。Gmail 的已发不带此问题（有 `\Sent`，自动发现）。
4. **`email_command` 是后门**：它能跑 EXPUNGE/DELETE 原始 IMAP。其准入条件是 organize + delete + append + 附件内容全开——**移除 `delete` 就把这条后门永久关死**（实测返回 `policy_conflict`）。
5. **连续负向测试会触发 MCP 熔断**：`rejected the last 3 calls ... Paused ~60s`。负向测试要拉开间隔，暂停期间不要重试同一调用。
6. **`list_emails_metadata` 的 `subject` 过滤不可靠**：查到 0 条但邮件实际存在。查具体邮件改用「不带过滤的最新 N 封」或按发件人/时间。
7. **接口返回成功 ≠ 真的送到**：必须去「已发邮件」文件夹核对落盘。而且**部分厂商会改写 Message-Id**（实测腾讯改写成自有域名形式），不要拿接口返回的 ID 去比对。
8. **读正文必须显式 `mark_as_read=false`**：默认行为可能把邮件标已读，等于替用户改了状态。
9. **profile 改名会打断 cron 的 bot-chat 投递**：报 `profile_mismatch`，需把 `deliver` 改成显式的 `bot-chat:<新 profile 名>`；改名同时会让其他技能里 `@session:<旧名>/...` 的来源引用失效。

## 6. 验收清单（全部实测，不接受「应该可以」）

1. `list_available_accounts` → 各账号 `can_receive` / `can_send` 为 true。
2. 各账号列一次收件箱元数据 → 拿到真实 total。
3. 发一封自测信 → 去「已发邮件」核对落盘。
4. `delete_emails` 传假 ID → 必须被拒。
5. `email_command` 带账号 → 必须返回 `policy_conflict`。
6. 巡检类 cron `action='run'` 手动触发 → 回传 `Status: ok` 且投递到目标窗口。

## 安全边界与失败停止

- 技能与日志里**账号一律占位符**；不记录真实邮箱地址、账号名、授权码、应用密码、Message-Id 实测值。
- 策略改窄后先跑一次正/负向验收；任一项不符预期就停，不要「放宽一点试试」。
- 认证失败先按厂商清单逐步核对（Gmail 的 IMAP 开关最常漏），**不要先去重置密码**。
- 不代用户回复、不代归档；发送能力仅在明确授权下开启，并限定收件人。

## 回滚

- 配置：`config.yaml` 的 `mcp_servers.mail` 段改回原值（改前备份）。
- 策略：`config update-policy --expected-revision <当前值>` 改回原 mutations / recipients；每次改动前先 `config policy` 存档。
- 账号：`account` 相关命令增删；授权码失效只需在厂商侧重生成，不动 Hermes 配置。

## 来源

- **第二手实测**：2026-11-08 `mail-keeper`（原 `fleet-mail`）通过 `message_agent` 投递的接入与排错实测记录，包含选型反例、三家认证现实、配置写法、策略层次、9 条坑与 6 项验收清单。**本技能由 skill-keeper 整理成文，未经 skill-keeper 亲自复现**——与实测不符时以 mail-keeper 的现场输出为准，并回来改本文件。
- **可交叉印证的部分**：`trust: untrusted` 不生效、策略 revision 与 `allowed_mutations` 收窄到不含 `delete`、附件下载关/内容开——与 2026-11-08 已在 `mail-inbox-readonly-triage` 与 mem0 记录的落地事实一致。
- **待验证**：Outlook 个人号 Graph 路径的可授权范围与 Azure 应用注册细节，仅有查证结论、无本机实测；`--expected-revision` 号段的具体取值需现场读。
