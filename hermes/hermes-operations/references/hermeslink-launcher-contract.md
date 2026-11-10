# HermesLink 不可用：启动器载荷契约断裂

用户报「HermesPilot 无法使用」时的完整排查与修复流程。2026-10-09 实测过一次。

## 症状

- 手机 App 上 Link 在线、Relay 已连接，但会话/项目/Cron 全部不可用
- `hermeslink status` 看着正常（守护在跑、Relay 已连接）
- `hermeslink doctor` 报：
  ```
  tui_gateway JSON-RPC：无法确认电脑上的 Hermes 服务状态。
  诊断代码：hermes_backend_discovery_failed。
  Could not verify Hermes backend process records and session ownership
  ```
- 日志 `~/.hermeslink/logs/hermeslink.log`（**JSON Lines，时间是 UTC**）连续出现：
  ```
  hermes_backend_discovery_failed  stage=resolve_runtime
  hermes_project_rpc_failed        method=projects.list
  hermes_cron_read_failed
  conversation_run_failed / conversation_run_worker_failed
  http_request_failed GET /api/v1/conversations → 503 project_profile_unavailable
  ```
- 统一根因字段：`"error":"Hermes returned an invalid Python runtime command"`

## 关键判据：不要被 `/internal/status` 误导

`/internal/status`（127.0.0.1:52379）**硬编码 `connect: false`**，所以空闲时永远显示
`available:false, state:closed, backend_state:stopped` —— 这是设计如此，**不是故障证据**。
真正的健康判据是 `hermeslink doctor` 中 tui_gateway 一行是否报「可用」。

## 根因：HermesLink 的严格解析器 vs Hermes 的启动器载荷

HermesLink 调 `hermes --print-runtime-command` 拿 JSON，然后用严格解析器校验
（`dist/chunk-*.js` 内 `parsePublishedRuntimeCommand`）：

```js
const codeIndex = command.indexOf("-c");
const entry = code.slice(code.lastIndexOf("import hermes_bootstrap;") + 24).trim();
if (codeIndex < 1 || codeIndex !== command.length - 2) throw ...;
if (!entry.startsWith("runpy.run_module(") && !entry.startsWith("exec(")) throw
  new Error("Hermes returned an invalid Python runtime command");
```

而 Hermes 自提交 `fd73042f2d`（2026-10-04, "launchers reach the launch-time repair
before any other checkout module"）起，把「默认 HERMES_HOME 落定」语句从
`import hermes_bootstrap;` **之前**移到了**之后**（为了让 `hermes_constants` 的导入发生在
`_early_recovery.restore_interrupted_pull` 之后），正好插在解析器要求的位置：

```
import hermes_bootstrap; os.environ.get('HERMES_HOME') or os.environ.__setitem__(...); runpy.run_module(...)
                         ^^^^^^^^^^^^^^ entry 从这里开始 → 以 os.environ 开头 → 解析器抛错
```

**为什么整个后端会挂**：`resolvePublishedHermesRuntime` 的 catch 只对「unrecognized
argument」错误 return null（兼容旧版 Hermes），其余一律 `throw`。所以解析失败**不会回退**到
managed-runtime / shebang / venv 探测，`resolveHermesEntrypointRuntime` 直接中断，
整个 profile 判定不可用。

## 修复（抗更新，2026-10-09 验证）

不要改 Hermes 核心（每 6h 自动 `hermes update` 会冲掉/冲突），改用用户自有代理：

1. `~/.hermes/scripts/hermes_link_runtime_fix.py` — 载荷重写器。把
   `import hermes_bootstrap;` 与 `runpy.run_module(` 之间的落定语句折进
   `exec("…"); `，使 entry 以 `exec(` 开头。
   - **幂等**：已合规则原样透传（上游修复后自动失效）
   - **健壮**：任何解析异常一律原样透传，绝不破坏正常输出
   - **注意**：原句已自带结尾分号，别再加一个，否则 `;;` 触发 SyntaxError
2. `~/.hermes/scripts/hermes-link-shim.sh` — 透传代理。仅拦截
   `--print-runtime-command`，其余调用 `exec` 给真实 hermes；原命令失败时原样转发
   stderr 与退出码，不掩盖错误。
3. 让 `~/.local/bin/hermes` 转发到代理 —— **这是真正让修复立即生效的一步**：
   运行中的 hermeslink 守护每次调用都重新 exec 这个路径，所以无需重启守护。
4. plist `HERMES_BIN` 指向代理（防御性，供未来重启使用）：
   `~/Library/LaunchAgents/com.hermespilot.link.plist`

### 为什么代理不需要改 `entry` 的实际语义

HermesLink 只取 `import hermes_bootstrap;` **之前**的部分当 `bootstrapCode`，
再拼自己的入口（`buildHermesPythonLaunch`）；Hermes 自己的 `entry` 它**根本不执行**。
所以缩进/折进 exec 对运行零影响，只是为了让解析器过闸。

## 验证清单

1. 解析器复检（5 项全过）：数组全字符串 / `command[0]` 绝对路径 /
   `-c` 索引 == `len-2` / 含 `import hermes_bootstrap;` / entry 以 `runpy.run_module(` 或 `exec(` 开头
2. **真的执行一遍改写后的命令**（`--version`）——只验解析不验执行会漏掉 `;;` 这类语法错误
3. `hermeslink doctor` → `tui_gateway JSON-RPC：可用`
4. 日志不再新增 `resolve_runtime` 失败；`/api/v1/conversations` 不再 503

## 操作红线

- **`launchctl submit/bootstrap` 在 Hermes 网关内部被安全守卫硬拦截**（防止间接网关重启死循环），
  无法从会话内重启 LaunchAgent。要么由用户外部终端执行，要么走「改
  `~/.local/bin/hermes` 转发」这条无需重启的路径。
- **不要在会话内跑 `hermeslink restart` / `stop`** —— HermesLink 自带的
  `hermes-link` 技能明文禁止；重启可能掐断正承载当前响应的 Link/tui_gateway 进程。
  需要重启时让用户在外部终端执行。
- `/internal/status` 的 `available:false` 是空闲态，别当成故障。
