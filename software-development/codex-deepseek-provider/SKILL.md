---
name: codex-deepseek-provider
description: 把 Codex CLI 接到 DeepSeek 等第三方模型时使用。
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [codex, deepseek, provider, cli, toml]
---

# Codex CLI 接第三方模型（DeepSeek）

## When to Use

- 用户说「把 DeepSeek 接到 Codex」「Codex 换模型」「用 DeepSeek 跑 codex」
- 要给 Codex 加任何非 OpenAI 的 OpenAI 兼容端点（LiteLLM、New API、本地 vLLM）
- `codex` 报 `wire_api = "chat" is no longer supported`

把 Codex CLI 指向 DeepSeek 官方 API，同时保留原有 ChatGPT 登录配置不动。

## 关键事实（Codex 0.165 实测）

1. **`wire_api` 只接受 `"responses"`**。传 `"chat"` 会直接报错退出：
   `Error loading config.toml: wire_api = "chat" is no longer supported.`
   不要按网上老教程写 `chat`。
2. **`-p/--profile` 语义变了**：0.165 下 `codex -p deepseek` 叠加的是
   `$CODEX_HOME/deepseek.config.toml`（**独立文件**），而不是 config.toml 里的 `[profiles.deepseek]` 段。
   用错位置会静默不生效。
3. **DeepSeek 官方支持 `/v1/responses`**（2026-11 实测 HTTP 200，返回标准 Responses 对象，
   含 `reasoning` + `output_text`），所以不必退化到 chat/completions。
4. **`model_max_output_tokens` 不是合法键**，0.165 会警告并忽略；合法的是 `model_context_window`。
5. 自定义模型不在内置 catalog 里，必然出现
   `warning: Model metadata for <model> not found`——**无法靠配置消除**，不影响功能。

## 方案 A：设为默认（推荐，直接 `codex` 就走 DeepSeek）

改 `~/.codex/config.toml`，根键必须写在第一个 `[table]` 之前：

```toml
model = "deepseek-flash"
model_provider = "deepseek"
model_context_window = 1048576
```

文件末尾追加：

```toml
[model_providers.deepseek]
name = "DeepSeek"
base_url = "https://api.deepseek.com/v1"
env_key = "DEEPSEEK_API_KEY"
wire_api = "responses"
```

`env_key` 只读进程环境，Codex 不会自己读 `.env`，所以在 `~/.zshrc` 里注入：

```bash
if [ -f "$HOME/.hermes/.env" ]; then
  export DEEPSEEK_API_KEY=$(sed -n 's/^DEEPSEEK_API_KEY=//p' "$HOME/.hermes/.env" | tr -d '"' | head -1)
fi
```

> 不用 `tr -d '"'\''` 这种嵌套引号写法：zsh 会报 `unmatched "`，key 静默变空，让人误以为配置没生效。

切回 OpenAI：建 `~/.codex/openai.config.toml`（`model = "gpt-6-astra"`、`model_provider = "openai"`），用 `codex -p openai`。

## 方案 B：独立 profile（不动默认）

`~/.codex/deepseek.config.toml` 内容同上面的 provider 段，用 `codex -p deepseek` 调用；
配 wrapper 自动注入密钥：

```bash
#!/bin/bash
set -a; . "$HOME/.hermes/.env" 2>/dev/null; set +a
exec /opt/homebrew/bin/codex -p deepseek "$@"
```

## 坑：Codex 应用会写回 config.toml

在 Codex TUI/桌面端里切模型时，它会**改写 config.toml 的 `model` 字段**，把 `deepseek-flash` 覆盖回 `gpt-6-x`（实测 gpt-6-astra → gpt-6.1-sol）。
发现“模型又变回去了”，先 `head -8 ~/.codex/config.toml` 看是不是被 Codex 自身写回。

## 怎样确认真的切过去了

`codex exec` 的会话头会打印 `model:` 与 `provider:`，两行都对才算通。
最硬的证据：把 key 换成无效值再跑，应当报
`401 Unauthorized ... url: https://api.deepseek.com/v1/responses`；
如果仍然正常回答，说明根本没走 DeepSeek（或 key 仍是旧值）。

## 验证方法

```bash
cd /tmp && codex-deepseek exec --skip-git-repo-check --sandbox read-only "回复两个字：正常"
```

会话头必须显示 `model: deepseek-flash` + `provider: deepseek`，且能出答案即通。

**陷阱**：问模型「你是什么模型」时它会答 GPT-5/Codex——那是 Codex 内置 base_instructions
让它扮演 Codex 所致，**不代表后端没换成 DeepSeek**。要判断后端，看会话头的 provider 行，
或临时把 key 改错看是否 401。

## 排查顺序

1. `wire_api` 是不是 `chat` → 改 `responses`
2. `-p` 找的文件是否存在：`~/.codex/<name>.config.toml`
3. `env_key` 指向的环境变量是否真的在进程里：`codex-deepseek` 里先 echo 判断
4. base_url 是否带 `/v1`（DeepSeek 需要 `https://api.deepseek.com/v1`）
5. 先裸 curl `/v1/responses` 确认账号可用，再排查 Codex 侧
