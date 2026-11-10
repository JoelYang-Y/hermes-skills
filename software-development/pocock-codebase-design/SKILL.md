---
name: pocock-codebase-design
description: 深模块化软件设计规范，小接口隐藏复杂逻辑，杜绝代码熵增与泥球架构。
version: 1.0.0
author: Matt Pocock / Hermes Adapted
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [architecture, deep-modules, software-design, modularity, refactoring]
---

# Pocock 深模块化与架构设计规范 (Deep Module Codebase Design)

本技能源自 Matt Pocock 与 John Ousterhout（《软件设计哲学》）的核心架构原则——“最好的模块是‘深模块’（Deep Modules）：通过极其简单、直观的小接口，提供强大丰富的功能；最差的模块是‘浅模块’（Shallow Modules）：接口复杂繁琐，内部却几乎没有实质逻辑”。

## When to Use

- 规划新系统、新建复杂功能模块或重构既有系统时
- 发现组件间高度耦合、改动一处引发多处断裂时
- 评估代码质量、消除冗余胶水层（Glue Code）时

## 核心设计法则

### 1. 追求深模块 (Deep Modules)
- **小接口 (Small Interface)**：对外暴露的 API/函数/配置极为精简、参数最少、心智负担为 0。
- **大功能 (Deep Implementation)**：所有复杂的状态流转、数据清洗、跨端适配、错误重试全部封装在模块内部，不让调用方感知。

### 2. 打造干净的接缝 (Clean Seams & Single Source of Truth)
- **数据与视图彻底解耦**：所有数据源必须抽离为单一的配置文件（如 `site.config.ts`、`docker-configs.ts`），UI 组件只负责接收数据并纯粹渲染，杜绝在 UI 模板里硬编码业务逻辑。
- **单向数据流**：状态变更自顶向下传递，杜绝全局变量污染与隐式副作用。

### 3. 消灭浅模块与过度包装 (Eliminate Shallow Abstractions)
- 如果一个 Wrapper 函数/类只是透传调用了底层 API 而没有增加任何实质价值，立即将其删除。
- 严禁为了“设计模式”而创建毫无业务逻辑的工厂与接口层。

### 4. 架构自检清单
每次完成代码编写后自问三题：
1. **接口够简单吗？** 一个新开发者/Agent 能在 10 秒内理解如何调用吗？
2. **知识被有效隐藏了吗？** 底层的特定实现细节（如特定平台路径、加密算法）泄漏给调用方了吗？
3. **改动被局部化了吗？** 当某个底层业务规则变更时，需要修改的文件数量是否被严格限制在 1 个以内？
