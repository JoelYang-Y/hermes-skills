---
name: bot-tooling-provisioning
description: "Use when 为某 Bot 扩装技能/MCP. 先验通道, 凭据由用户输入."
version: 1.0.0
author: skill-keeper
license: MIT
metadata:
  hermes:
    tags: [hermes, mcp, skills, provisioning, security]
    related_skills: [native-mcp, mcporter, hermes-operations, server-readonly-inspection]
---

# 给某个 Bot 扩装能力（技能 / MCP）

给某个 profile 配「它工作真正需要」的探测与运维能力时，按固定顺序走：**先核实已有通道 → 再判技能市场能不能用 → 最后才谈 MCP，且凭据一律由用户在自己终端输入**。目的是避免「装了一堆用不上的东西」和「代理经手明文密码」两类事故。

## When to Use（适用条件）

- 用户说「你是 X 管家，自己上网找适合的 skill / MCP 装上」。
- 某个 Bot 抱怨「我探测不到某台机器」，需要新增通道而不是新增工作流。
- 不适用：单个 MCP 的配置语法（用 `native-mcp`）；一次性临时调用（用 `mcporter`）。

## 前置依赖

1. 确认目标 profile 的 `terminal` / `file` 是否真的启用——**不要相信系统提示里的禁用清单，先实跑一条无害命令验证**（实测出现过提示说禁用、实际已启用的情况）。
2. `hermes --profile <p> mcp list`、`hermes --profile <p> skills list` 可执行。
3. 目标 MCP 包真实存在：`npm view <pkg> version` 返回版本号。
4. 若走 ssh-mcp 通道：配置文件在 `~/Library/Application Support/ssh-mcp/config.toml`，改前必须备份。

## 输入 → 输出

- 输入：目标 profile 名、要覆盖的主机别名、用户愿意提供的凭据（**只由用户输入，不经过你**）。
- 输出：① 现状清单（已有 MCP / 哪些主机有通道、哪些报 Connection refused 或 publickey denied）；② 已安装并 `enabled` 的技能列表；③ 一个凭据自输入脚本路径（用户自己跑）；④ 简报：装了什么、哪些卡在权限而非软件、哪些是待验证。

## 步骤

1. **列现状，不要先装**：`hermes --profile <p> mcp list`。实测输出形如一张表（Name / Transport / Tools / Status），只有 `sshreadonly … ✓ enabled` 就说明除 SSH 外没有任何探测通道。
2. **把「已有通道覆盖哪些主机」查清**：调用 ssh MCP 的 `list_connections`，看 profile 名单与 role/readOnly。名单里没有的主机，装再多 MCP 也探测不到。
3. **判技能市场是否可用**：`hermes --profile <p> skills inspect <id>` 只读索引元数据（会打印 Source / Trust），**不代表能装**；必须实跑 `skills install <id> --yes` 才算验证。见坑 2。
4. **非交互安装必须加 `--yes`**：不加会停在 `Confirm [y/N]:` 并输出 `Installation cancelled.`。这是「以为装好了其实没装」的常见来源。
5. **MCP 凭据交给用户**：写一个 `bash` 脚本，用 `read -s`（不回显）读密码，直接作为 `--env` 传给 `hermes mcp add`，脚本不写日志、`unset` 变量。你只交付脚本路径与用法，**不索取、不接收、不转发明文**。
6. **交付前先做只读校验**：`bash -n <script>` 语法检查 + `chmod +x`；脚本里每段都先 `have_mcp <name>` 判断，已存在则跳过（幂等）。
7. **上报两栏**：一栏「已实测完成（附工具输出）」；一栏「需要用户接管/待验证」。不要把「脚本已写好」写成「能力已装好」。

## ssh-mcp 通道增补（实测跑通）

- 备份 `config.toml` → 追加 `[[profiles]]` 块（`name/host/port/user/auth=key/keyRef/group/role/readOnly/approvalPolicy`）→ 调 `reload_config(action="reload")`。
- 成功的回执会带 `sha256` 与加载时间，并明确写 `Profiles: added <name>.`；**同时会 `Approval grants: cleared`**，也就是说之后的每次授权都要重新批。
- 回执里的 sha256 是「配置真的被读进去了」的唯一证据——比对它在 reload 前后变化，比看文件内容可靠。

## 坑（均为实测）

1. **`readOnly = true` 的 profile 连只读命令也会被拒**，只要命令里出现 shell 元字符。实测把 `hostname; grep …; docker ps` 合成一行被拒：`POLICY_DENIED: Profile "<name>" is read-only, so "safe" commands are refused. … 'hostname' is read-only only when the command contains no shell metacharacter; ';' is one.` → 一个命令一次调用，绝不拼 `;`。
2. **技能市场索引会腐坏**：clawhub 的 `uptime-kuma` / `beszel-check` / `adguard` 三个条目 `inspect` 都能解析出漂亮的元数据，但 `install` 一律报 `… files no longer exist upstream. Stale index entry: the skill was likely renamed or removed by its author.`。所以 **inspect 成功 ≠ 可安装**；判断标准是 install 的实际退出结果。
3. **别照抄网文里的 `hermes skills install <name>` 老路径**：社区条目优先走 `official/<category>/<name>` 或真实 HTTP(S) 的 SKILL.md URL；官方分类很窄（devops 实测只有 docker-management、watchers 等少数几项），指望技能市场补齐运维能力通常落空。
4. **缺通道 ≠ 缺软件**：`port 22: Connection refused`、`Permission denied (publickey,password)` 这类要报「需要用户开 SSH / 加公钥」，不要转去装 MCP 或写绕过脚本。
5. **MCP 工具无热重载**：新装的 MCP 在**新会话**才出现。这一点来自官方技能文档与当时判断，**未在本轮实测**（待验证）——但无论如何，验收要新开会话再看 `mcp list`。

## 安全边界与失败停止

- 不接收明文凭据：不索取、不代填、不把密码写进技能或聊天。脚本以 `read -s` 输入、`--env` 直传、用完 `unset`。
- 不改其他 profile 的配置；不动 cron；不动 Surge。
- 停止条件：`npm view` 查不到包 / `skills install` 报 stale index / ssh 连接被拒或公钥未授权 → 停在这一步，如实上报缺口，不找替代路径硬上。

## 回滚

- ssh-mcp：保留 `config.toml.bak-<YYYYMMDD-HHMMSS>`，回滚即还原该文件再 `reload_config(action="reload")`。
- 技能：删除 `~/.hermes/profiles/<p>/skills/<category>/<name>/`（只移动，不 `rm`；移到 skills 树之外，避免扫描器把备份目录当 category）。
- MCP：`hermes --profile <p> mcp remove <name>`（此命令本次未实测，待验证）。

## 来源

- 2026-11-09 01:05 会话 `@session:server-keeper/local-7076536700425475c3b27e3abe132af60e48d3df214bbce7c1c586faf7ec9b5b`（第二手实测：我不是执行者，材料来自该会话的真实工具输出）。
  - 事实：`mcp list` 表格与「仅 sshreadonly enabled」；`readOnly` + `;` 的 `POLICY_DENIED` 原文；`reload_config` 回执 `Profiles: added agd.` 与 `Approval grants: cleared`；`skills install` 无 `--yes` 时 `Confirm [y/N]: Installation cancelled.`；三个 clawhub 条目的 `Stale index entry` 报错原文；ssh 到 NAS 22 端口 refused、PVE publickey 被拒。
  - 待验证：三个 MCP（Kuma / AdGuard / Cloudflare）的 `mcp add` 命令**从未真正执行**，脚本只做过 `bash -n` 语法检查；`mcp remove` 未实测；MCP 无热重载未实测。
- 推断：把「运维能力该走 MCP 而非技能市场」写成结论，依据是 clawhub 三连失败 + 官方 devops 分类极窄这两个事实，属合理推断而非普适定律。
