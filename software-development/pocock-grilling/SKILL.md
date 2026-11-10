---
name: pocock-grilling
description: 在动手编码或复杂架构决策前，对需求与边界进行深度审问式对齐，彻底杜绝 Agent 误解。
version: 1.0.0
author: Matt Pocock / Hermes Adapted
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [engineering, grilling, alignment, requirements, spec-driven]
---

# Pocock 审问式对齐规范 (Grilling Session)

本技能源自 Matt Pocock 的核心工程哲学——“软件开发最常见的失败模式是理解偏差”。在动手写代码或做出破坏性系统变更前，通过结构化的深度提问与边界探测，消除与用户的沟通鸿沟。

## When to Use

- 用户提出了一个复杂的功能需求、重构计划或架构方案
- 需求的边界条件、异常流、性能指标或交互细节尚不明确
- 在编写大型模块、修改生产基础设施或创建复杂数据结构前

## 核心执行四步法

### 1. 识别决策树分支 (Identify the Decision Tree)
在动手前，首先梳理当前需求存在的所有可能分叉点：
- **功能范围**：MVP 必须包含什么？明确不包含什么？
- **数据流与持久化**：数据存在哪？如何迁移？如何防止并发冲突？
- **异常与兜底**：网络断开、超时、404、权限不足时系统如何降级？
- **多端与环境**：在 Mac、iOS、Linux、Docker 下是否有特殊差异？

### 2. 深度提问法则 (The Grilling Rules)
- **拒绝宽泛套话**：严禁问“您有什么其他要求吗？”，必须问具体的技术选择（如“未匹配域名是返回 444 丢弃连接还是 301 重定向到主域名？”）。
- **给出推荐选项**：每个提问必须附带 2~3 个经过深思熟虑的具体实现选项，并标注 (Recommended)。
- **一次只聚焦一个核心决策域**：避免同时抛出 10 个无关问题淹没用户。

### 3. 固化共识至文档 (Solidify to Spec)
一旦完成对齐，立即将共识总结为结构化 Spec：
- **明确的输入/输出契约**
- **明确的边界与错误处理策略**
- **不可违背的红线与约束**

### 4. 验证与执行 (Execute with Verification)
在获得确认后，才进入实际的 TDD / 代码实现阶段，绝不在意图模糊时写第一行代码。
