---
name: hermes-model-identity-audit
description: "Use when 回答当前模型身份/版本. 三层核对, 不信自述."
version: 1.0.0
author: skill-keeper
license: MIT
metadata:
  hermes:
    tags: [hermes, model, identity, config, state-db, troubleshooting]
    related_skills: [hermes-operations, hermes-system-optimization]
---

# Hermes 模型身份核对（三层法）

回答「你是什么模型 / 哪个版本 / 有没有走 fallback」时，不能只报会话里那行自述，也不能只读配置——**运行时、磁盘默认、会话落库三层各自可能不同**，必须分开取证再下结论。

## When to Use（适用条件）

- 用户问「你当前是什么模型」「模型版本是多少」「推理等级怎么选」。
- 怀疑实际在跑的模型与 `config.yaml` 的默认值不一致（换过 provider、会话被钉模型、fallback 生效）。
- 需要判断某条记忆里的模型描述是否适用于**当前环境**（Mac mini Hermes ≠ Muse/Meta 云端环境）。

## 前置依赖

1. 有 terminal，能读 `~/.hermes/config.yaml` 与对应 profile 的 `state.db`。
2. 知道当前会话跑在哪个 profile、哪个宿主环境（本机 / 云端 VM）。

## 输入 → 输出

- 输入：profile 名 + 当前会话 id（或由运行时自报的环境信息）。
- 输出：三层对照表（本会话实际在跑 / 磁盘默认 / 回退配置）+ 一句结论 + 未取到或未实测的项。

## 步骤

1. **运行时注入层**：取会话系统提示/会话头注入的 model、provider 行。这只代表**本会话**，不代表磁盘默认。
2. **磁盘默认层**：`grep -n -A5 '^model:' ~/.hermes/config.yaml`，并用 YAML 解析确认 `model.default`、`model.provider`、`fallback_providers`。**必须解析后再说结论**——报告配置不一致前先 grep + YAML 解析核实，不得肉眼目测（用户明确要求）。
3. **会话落库层**：查 `state.db` 的 `sessions.model`（该会话实际模型）、`session_model_usage`（调用次数，证明它真的在跑）、`fallback_active`（false/0 表示未走回退）。
4. **下结论**：以「本会话实际在跑」为身份口径；磁盘默认只说明「新会话会用什么」。两者不同就直说「本会话被钉在 X，配置默认 Y，未走 fallback」。
5. **分清环境**：同一用户在不同宿主会是不同模型（Mac mini 上 Hermes 走一个通道，Muse/Meta 云端是另一个模型）。问「你是什么模型」先确认跑在哪个环境，再用**该环境**的证据回答。

## 坑（均为实测）

1. **只报运行时注入会被追问**：2026-11-15 01:23 会话里用户先指出「上次只报了会话注入行，漏了磁盘默认和会话落库记录」，补做三层后才有可信结论。少一层就不算核对完。
2. **别拿别的环境的记忆当本环境身份**：Muse Spark 1.3 环境曾直接引用 Mac mini 上 grok-4.6/4.7 的记忆，属于跨环境误用；正确说法是「那是另一个环境的会话记录，不是本会话身份」。
3. **auxiliary.vision 一类的辅助模型不能凭记忆断言**：配置为 `auto`/模型名为空时，记忆里「图片走某模型」的说法若本会话没实测，标「待验证」，不写进结论。
4. **模型名与通道要一起报**：只说 `grok-4.6` 不说 `xAI OAuth → api.x.ai`、`api_mode`，会让人误以为是 api.x.ai 之外的入口；反之只报 provider 也不够。
5. **技能里不写死型号**：磁盘默认会变（2026-11-15 曾是 grok-4.7，后来统一切到 DeepSeek），每次都以当轮读数为准。

## 验证方法（只读）

- 三层读数互相对照即可离线验收；不重启网关、不改配置。
- 若要验证「改了配置新会话会不会用上」，另起新会话看运行时注入行，不在旧会话里推断。

## 风险与安全边界

- 只读 `config.yaml` 与 `state.db`；`state.db` 含会话正文，只取 model 相关字段，不导出正文。
- 不打印任何 API key / token 行；`grep` 结果里遇到密钥字段直接跳过。
- 不做配置修改；发现配置与预期不符只报告，改动另行批准。

## 失败停止

- `config.yaml` 解析失败或 `state.db` 被占用读不到：停在已确认的层，结论里写明「第 N 层未取到」，不猜测补齐。

## 回滚

- 无写入，无回滚动作。

## 来源

- `@session:default/local-56c55948b6bc3ae361838a015bf64a4a10b58616660b8e7914a59819948c21ed`（2026-11-15 01:23，grok-4.6 会话：运行时注入 + `config.yaml` `model.default: grok-4.7`/`provider: xai-oauth` + `state.db` 的 `model`/`session_model_usage` 6 次/`fallback_active=false` 三层对齐。**第二手实测**：工具输出由我在该会话中读取，未自行复现）。
- `@session:default/local-9ee38bda999cb6ef9e7de120490e9264f8467fd5091be8b80febdbb1855fcfa9`（2026-11-15 01:38，Muse Spark 1.3 环境身份隔离的反例）。
- `@session:default/local-65fdb9c4aac3780dd24eb1e4000e48053a8bd80a45d7b4cb84b4ef5792466221`（2026-11-15 02:31，Hermes 框架 / Muse 产品 / Grok 模型三层区分）。
- 事实：表格结构与三层字段均来自上述会话的真实工具输出；推断：`state.db` 表结构可能随版本变化，查不到 `session_model_usage`/`fallback_active` 时按「该层未取到」处理。
