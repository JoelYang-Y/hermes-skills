---
name: local-dsh-coding
description: 代码开发、Bug 修复、重构、复杂脚本、测试、代码审查或构建任务时，评估调用 Mac 本机 DeepSeek Harness；普通聊天和信息查询不调用。
---
# 本机 DSH 编程委派

## 路由与边界
- Hermes 负责需求澄清、编排与最终复核。仅编程相关任务评估 DSH；普通聊天、信息查询和简单文件操作由 Hermes 处理。
- 只使用本机 `/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh --profile headless`，不 SSH 到远程 DSH，不调用 dsh-url/dsh-web。
- 开始前确认用户指定的 Git 仓库根目录、现有代码、任务约束及验收条件。路径不明确先询问，禁止默认在 `~/.hermes`、HOME 或重要系统目录运行。
- 默认 `--permission-mode read-only`。只有用户明确要求改代码才可使用 `workspace-write`，并 `--add-dir` 明确指定仓库；不得加无关目录、不得使用 `danger-full-access`。
- DSH 禁止调用 Hermes、hermeslink 或本入口，禁止相互委派循环。不得自动部署生产、修改系统配置或读取凭据。

## 安全入口（任务仅经 stdin）
推荐用 terminal 的参数数组或 Python `subprocess`，调用：
`/opt/homebrew/bin/python3 -B /Users/macmini/.hermes/scripts/hermes_local_dsh.py --repo <已确认的仓库绝对路径> --timeout 600`

把任务、约束、目标文件、验收测试文本通过 stdin 传入，不拼接 shell 字符串或命令替换。入口实际传给 DSH 的参数包含 `--profile headless --permission-mode read-only --approval-policy never --json -`。

若用户明确要求修改代码：加 `--mode workspace-write --write-authorized`。入口要求干净工作区，先创建独立 `hermes-dsh/...` Git 分支，然后给 DSH 加 `--add-dir <仓库>`。脏工作区不得自动覆盖/stash/reset，先说明并确认可回滚方案。

可先加 `--plan` 检查路径与调用计划：不执行 DSH、不建分支、不创建任务日志。不得把 plan 当成真实任务成功。

## 验收与失败
- 入口设置 600 秒超时（明确需要时最多 1800 秒）；只取消本次启动的 DSH 进程组。禁止杀 Gateway、Link、WebUI。
- 收集退出码、NDJSON 事件、stderr、Git 前后状态、`git diff HEAD` 和未跟踪文件列表。日志私有保存于 `~/.hermes/output/dsh/<run-id>/`；不得把可能含秘密的原始输出直接外发。
- Hermes 必须复核修改范围与实际内容，按任务运行必要测试/Lint/构建，检查未跟踪文件。没有运行的测试必须注明，不能只凭退出码或成功文字交付。
- 超时、取消、非零退出或认证失败时先定位原因，不盲目重复执行。DSH 支持 `--session-id`，但仅在核实会话、cwd、权限与上次结果后才允许另行继续，不重复创建同一修改。
- DSH 不可用时 Hermes 自己回答、分析或给出明确降级方案；不得偷偷切回远程或扩大执行权限。
- 当前入口与 Skill 已配置不等于端到端已验收；真实任务可能产生模型费用，需遵守用户的费用授权。
