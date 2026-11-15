---
name: mem0-full-export
description: "Use when 导出 Hermes 全部记忆. Qdrant 只读 scroll 三格式."
version: 1.0.0
author: skill-keeper
license: MIT
metadata:
  hermes:
    tags: [hermes, mem0, qdrant, export, backup]
    related_skills: [mem0-oss-operations, mem0-tiered-tidy-cron, session-digest-memory-cron]
---

# mem0 全量记忆导出（只读）

把「把所有记忆导出来」变成一次可核对、可复核的只读导出：分页 scroll 拉全量 → 三格式落盘 → MANIFEST 回读。

## When to Use（适用条件）

- Joel 说「导出全部记忆 / 个人信息 / 给记忆做个备份」。
- 换后端、审计、交接前需要离线快照。
- 不适用：只查某条记忆（用 `mem0_search`）；只想降条数/去重（用 `mem0-tiered-tidy-cron`）。

## 前置依赖

1. Qdrant 可达（NAS `10.0.0.3:6333`），`python3` 可用，`~/hermes-exports/` 可写。
2. 已知活跃集合名：读 `~/.hermes/mem0.json` 的 `oss.vector_store.config.collection_name`（当前 `hermes_memories_v2_hybrid`）。
3. 统计不要走 `mem0 get_all`：默认每页 20 条，会漏算。

## 输入 → 输出

- 输入：主库集合名 + 可选历史备份集合名。
- 输出：`~/hermes-exports/memories_<YYYYMMDD_HHMMSS>/` 下每集合 3 个文件（`.json` 全字段 / `.csv` UTF-8-BOM / `.md` 可读）+ `MANIFEST.json`（条数、字符数、缺失正文、渠道与归因分布、文件名）。

## 步骤

1. **确认真实存储**：读 `~/.hermes/mem0.json` 与 `~/.hermes/profiles/*/mem0.json`，确认所有 profile 共用同一 collection。`MEMORY.md` / `USER.md` 自 2026-08-10 起为 0 字节，系统提示里的记忆块由本库渲染——不要去导那两个文件，也不要声称存在遗漏。
2. **基线**：`GET /collections` 拿清单，`GET /collections/<c>` 取 `points_count`；只把活跃集合当“记忆正文”，历史备份集合单独标「历史备份」。
3. **全量只读 scroll**：`POST /collections/<c>/points/scroll`，body `{"limit":256,"with_payload":true,"with_vector":false}`，用返回的 `next_page_offset` 翻页直到为 null，拼接所有点。
4. **归一化**：每点取 `id / data / channel / user_id / agent_id / attributed_to / hash / created_at / updated_at`，时间转 CST；断言 `data` 非空，`missing_data` 必须是空数组。
5. **落三格式 + MANIFEST**：JSON（全字段）、CSV（`utf-8-sig`，否则 Excel 中文乱码）、Markdown（按创建时间排序、逐条正文），MANIFEST 记每集合 `count / total_chars / 渠道分布 / 归因分布 / 文件名`。
6. **回读验收**：`read_file MANIFEST.json` 确认可读且条数与脚本 stdout 一致；能跑就再与 live `points_count` 交叉比对。**交叉比对被审批拦截时，如实写「未做二次比对」**，只陈述脚本自身 scroll 的实际计数——不得把没跑成的校验说成通过。

## 口径与边界（“全部”到底含什么）

- 只含记忆正文：主库 `payload.data`。**不含** `*_entities` 图谱集合（mem0 自动派生，非正文）、不含 `midjourney` 集合（其他应用数据）、不含会话历史（`state.db` 与 FTS 是另一套数据）。
- 需要实体或会话时单独再导，不要混进同一份「记忆导出」冒充完整。
- **明文风险**：导出文件是明文记忆正文，含内网 IP、主机名与操作细节。默认只落本机 `~/hermes-exports/`，不进同步盘、不外发；交付用 `MEDIA:` 直接发给 Joel 本人。

## 实测事实（2026-11-15 02:22 CST）

- 主库 `hermes_memories_v2_hybrid`：**114 条 / 49,168 字符**，缺正文 0；渠道 desktop 40 / cron 29 / tui 27 / cli 8 / telegram 3 / 未标注 7；114 条全部 `user_id=zhaoyang`。
- 历史备份 `hermes_memories_v2`：69 条 / 17,104 字符，缺正文 0。
- 同库 `*_entities`：3,221 / 566 条；`midjourney`：5,417 条——均未纳入。
- 导出脚本 exit 0，`MANIFEST.json` 回读成功。

## 坑

1. `mem0 get_all` 默认 20 条/页——统计必须 scroll 翻页或用脚本。
2. 导出脚本曾放在 `~/.hermes/cache/scratch/`，**闲置 24 小时会被清理**；复用前先确认文件还在，不在就按步骤 3–5 重建。
3. `scroll` 不显式传 `with_vector:false` 会把 512 维向量一起拉回，体积暴涨且无意义。
4. 分页必须有终止条件：`next_page_offset` 为 null 才停；只按总条数循环会死循环或多拉。
5. 别在导出里顺手“整理”（删除/合并）——导出是只读操作，写操作要另走 `mem0-tiered-tidy-cron` 的快照流程。

## 安全边界与失败停止

- 全程只读（`GET` + `points/scroll`），不写 Qdrant、不改 mem0 配置、不动其他 profile 的任何东西。
- 停止条件：集合不可达 / scroll 累计与 `points_count` 差异无法解释 / 出现空 `data` / 输出目录不可写 → 停并如实报告，不产出“看起来完整”的残缺导出。
- 回滚：只读导出无副作用，无需回滚；仅删除导出目录本身，且先确认它不是唯一副本。

## 来源

- `@session:default/local-ffa46ed48fb62a94b37cb2a6be2d84cc0d2a236bfb1ad70f54a03afc8e77fa45`（2026-11-15 02:19「导出 Hermes 全部记忆」：集合清单、114/69 条实测、三格式导出、MANIFEST 回读）。**第二手实测**：工具输出由我读取该会话获得，未自行复现。
- 事实：集合名、点数、字符数、渠道分布、拦截文本均来自该会话真实工具输出。
- 推断/待验证：与 live `points_count` 的二次交叉比对当轮被审批超时拦截（BLOCKED），未执行；导出脚本位于 scratch，可能已被清理，脚本内容未二次核对。
