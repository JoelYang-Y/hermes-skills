---
name: pocock-domain-modeling
description: 维护统一领域语言与 CONTEXT.md 规范，建立精准术语字典，大幅提升 Agent 理解效率。
version: 1.0.0
author: Matt Pocock / Hermes Adapted
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [domain-driven-design, context-md, architecture, terminology, ddd]
---

# Pocock 领域建模与 CONTEXT.md 规范

本技能源自 Matt Pocock 的领域建模思想——“通过统一领域语言（Ubiquitous Language），让 1 个专业术语替代 20 个废话描述，降低认知与 Token 消耗，确保多会话与跨 Agent 的极致一致性”。

## When to Use

- 进入新项目、创建核心功能模块或定义复杂数据关系时
- 发现 Agent 对项目特定术语理解模糊、反复解释概念时
- 编写或更新仓库根目录的 `CONTEXT.md` 或架构设计决策 (ADR) 时

## 核心规范体系

### 1. 建立项目专有 `CONTEXT.md`
在每个核心项目根目录维护轻量、高密度的 `CONTEXT.md`，包含三大板块：
1. **统一领域术语字典 (Glossary & Ubiquitous Language)**：
   - 明确定义核心实体的唯一标准名称（例如：“统一称呼为 `ServiceCard` 而非 item/tile/block”；“统一称呼为 `HostNode` 而非 server/machine/box”）。
2. **核心业务逻辑与级联规则 (Business Invariants)**：
   - 记录跨模块的关键约束（例如：“所有内网服务链接必须为 HTTPS 二级域名并由 Surge [Host] 接管”；“未授权域名在 Nginx 层由 default_server 444 丢弃”）。
3. **架构决策记录 (ADR - Architectural Decision Records)**：
   - 记录为什么选择 A 而非 B（例如：“为什么废弃 NAS 统一网关并回滚为直接 IP/Surge 映射”）。

### 2. 精准用词法则 (Precision over Verbosity)
- **拒绝模棱两可**：用具体领域术语指代对象，禁止用“那个服务”、“相关的配置”等模糊代词。
- **命名一致性**：文件路径、变量名、数据库字段、UI 组件必须 100% 映射领域字典。

### 3. 多 Agent 共享语境
- 在向本机 DeepSeek Harness（遵循 `local-dsh-coding`）或子 Agent 派发任务时，优先注入 `CONTEXT.md` 中的术语定义，实现跨 Agent 零偏差协作。
