# 网关在 launchd 服务定义刷新后宕掉（PM 运行时迁移踩坑）

触发场景：Mark 从手建 checkout 迁移到 PM 托管运行时后，执行 `hermes gateway start` 或 `install`。

## 症状
`hermes gateway start` 输出 `✓ Service started`，但网关根本没起来：
`launchctl list | grep hermes.gateway` 显示 `-  1  ai.hermes.gateway`（无 PID，上次退出码 1），
`curl http://127.0.0.1:8642/health` 无响应，Telegram 离线。

## 根因链（读 gateway.error.log 确认，不要猜）
1. `hermes gateway start` 把 `ProgramArguments` 重写成
   `…/installs/<id>/environments/<id>/workspace/.hermes/bin/hermes`。
2. 这个 shim 硬编码 **store Python**（`~/.hermes/tools/python-…/bin/python3`）。
3. `pm/environments.py::_require_own_dependencies` 在 `committed_venv(project_root)` 为 None 时
   拒绝任何 store-Python 启动 → 报 `hermes: no dependency environment is committed for this install;
   run 'hermes pm repair'` → launchd 退出码 1。
4. `committed_venv()` 为 None 的原因：workspace 快照漏了 **git 跟踪** 的 `pm/` 文件
   （`uv.lock`、`environments_adopt.py`、`plugin_eviction.py`）；缺 `pm/uv.lock` 时连
   `hermes pm <任何子命令>` 都会 `FileNotFoundError: …/workspace/pm/uv.lock`。

## 已验证的修复（macOS launchd）
把 `ProgramArguments` 指向 **env venv** 入口（venv 解释器能让守卫直接放行），并保留 stderr 时间戳包装。
注意 `--run-module` 是 shim 专有开关，在 venv 入口上会报
`'hermes_cli.stderr_timestamp' is not a hermes command`，必须改用 `-m` 加载模块：

```
do shell script "exec <ENV>/venv/bin/python3 -m hermes_cli.stderr_timestamp \
  --error-log ~/.hermes/logs/gateway.error.log \
  -- <ENV>/venv/bin/hermes gateway run --external-supervisor \
  >> ~/.hermes/logs/gateway.log 2>> ~/.hermes/logs/gateway.error.log"
```

实施步骤（顺序不可颠倒）：
1. 备份 plist 到 scratch；
2. 用 `plistlib` 读写（**绝不手写 XML**），只替换 `ProgramArguments[2]`，其余键保持不变；
3. `launchctl bootout gui/$UID/ai.hermes.gateway`；
4. `launchctl bootstrap gui/$UID /Users/<user>/Library/LaunchAgents/ai.hermes.gateway.plist`；
5. 核验三件套：`/health` 返回 ok、日志出现 `Connected to Telegram (polling mode)`、
   `~/.hermes/cron/ticker_heartbeat` mtime 是新时间（证明 cron ticker 也活了）。

## 需长期记住的事实
- `hermes update` 用 `launchctl kickstart` 重启网关，**不重写** `ProgramArguments`；
  只有 `hermes gateway start/install` 会重写。手工修好的定义能挺过后续更新。
- `hermes gateway status` 会一直提示 `Service definition is stale` —— 因为手修定义与 Hermes
  自己会铸造的启动器不同。属提示性；只要 /health 与 Telegram 正常，服务就是健康的。
- 补回缺失的 `pm/` 跟踪文件后 `hermes pm status/doctor/repair` 恢复可用，这才是走上"提交依赖环境"
  的正规路线。但要权衡：PM 按 lock 重建依赖树，可能剪掉手工装的 mem0 extra
  （见 `mem0-oss-operations` Pitfall #9）→ 放在维护窗口做。
- **绝不要**在 workspace 快照与 checkout 之间手工拷代码文件（两者有成百个文件内容不同）；
  只允许拷同一提交下内容一致的 lock / 模块文件。

## 顺带清理：retired-WAL 捕获目录
`state.db.retired-wal-<ts>-<pid>/` 是 WAL 世代取证捕获（每个 ~275 MB + manifest），被 Hermes
备份流程显式排除、且没有自动清理机制，会无声堆积到数 GB。删除前必须先证明"零独有数据"：
只读打开每个捕获的 `<dir>/state.db`，断言
`set(捕获.sessions) - set(现役.sessions)` 与 `messages` 的同名差值都为空
（列名是 `sessions.id`，不是 `session_id`）。差值全为 0 才可 `rm -rf`；删完复查现役库
`PRAGMA integrity_check`。
