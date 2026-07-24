# 后续候选：共读活动与内容记忆锚点

> 状态（2026-07-23）：明确后置，当前持续开发不实施。本文件保留为候选设计，不构成已批准的下一轮计划。

## 结论

在后续阶段做 **共读（shared reading）**：让用户与栖光围绕一本本地文本持续阅读、停留、批注、续读和回顾。它是“陪伴生活流”之后可选的第一种内容型共同活动。

不先做积分/奖励、语音、Live2D、多人格或数据迁移：

- 任务、例行、打卡、今天页、日记和时间线已完成；Phosphene 式积分/审核是更深的游戏化分支，不是当前功能闭环的缺口。
- AIRI 证明语音和具身表现已是独立的大系统（实时音频、ASR/TTS、设备与视觉模型），现在引入会跨越 runtime 输入输出边界，不能直接复用刚建成的活动数据。
- 多人格和迁移仍会改变所有历史数据作用域；按当前决定继续后置。
- 共读恰好复用 `ActivitySession.content_ref`、任务、提醒、时间线、日记和 action preview/confirm，扩展成本最低，且可用本地 fixture 完成端到端验证。

## 参考项目与取舍

| 项目 | 当前可借鉴点 | 本轮采用 | 本轮不采用 |
| --- | --- | --- | --- |
| [co-reading-mcp](https://github.com/idleprocesscc/co-reading-mcp) | 本地书籍、稳定 chunk、阅读进度、锚定边注、用户笔记可选择性分享、同段停留卡片和完读仪式。 | chunk/progress/annotation/note/续读；一次只把当前片段和新笔记交给模型。 | MCP 部署形态不是产品内核；不把整本书或私人笔记自动送入模型。 |
| [reading-nook](https://github.com/zzyyksl/reading-nook) / 共读书房 | 人与 AI 共读、章节上下文、批注和恢复阅读位置。 | 阅读会话和章节位置是业务真相；阅读 UI 只消费 API。 | 不复制其完整阅读器或直接耦合外部模型工具。 |
| [Journal](https://github.com/BomBomLab/Journal) | timeline/diary/todo 是可替换数据契约。 | 阅读开始、进度、批注、完读进入现有 timeline 与日记来源。 | 不新建第二个“阅读时间线”数据库。 |
| [Phosphene](https://github.com/3lmglow/Phosphene) | 任务实例、连续记录、审计、持久化的生活参与。 | 阅读计划可关联已有 Task/Routine/Reminder，所有完成和取消均审计。 | 积分、扣分、强制连击、图片审核、兑换商城。 |
| [AIRI](https://github.com/moeru-ai/airi) | 语音/Live2D/VRM/实时交互是后续可替换的呈现入口。 | 为未来语音朗读保留 `ReadingSegment` 和朗读位置。 | 本轮不接 STT/TTS、流式音频或角色模型。 |

## 本轮范围

### 交付的用户闭环

> 导入一份本地文本 → 创建/恢复共读会话 → 读到一个稳定片段 → 写一条私密或共享的边注 → 让角色只基于当前片段与显式共享笔记回应 → 更新进度 → 创建今晚续读提醒 → 完读后得到可编辑回顾，并在今天页、时间线和日记中可见。

### 首批内容格式

1. UTF-8 `.txt` 与 `.md`：必须完整支持，作为可测试、无复杂依赖的第一格式。
2. `.epub`：作为可选第二格式；仅在可稳定保留 spine/chapter 边界、无网络加载和有大小限制时开放。
3. 不支持 PDF、扫描件、DRM、在线书城、网页抓取、云盘、OCR 或任何受登录态保护的内容。

### 明确不纳入

- 自动长篇总结、全文向量化、全文直接注入 prompt。
- 版权内容分发、公共书库、账号、同步分享和外部 OAuth。
- 多人实时协作、多人格群聊、共听音乐、语音朗读。
- 用阅读时长/批注数量推断亲密度，或以积分/惩罚驱动阅读。

## 领域模型与边界

新增 `luminous/runtime/domain/reading.py`，活动模型只描述“读什么、读到哪、留下什么”，不保存模型推断出的角色记忆。

| 对象 | 核心字段 | 业务规则 |
| --- | --- | --- |
| `ReadingBook` | `book_id`、title、source_type、content_hash、imported_at、chapter_count、metadata | 本地内容清单；原文件与解析结果置于私有 runtime 目录，不进入 export JSON 正文。 |
| `ReadingChapter` | `chapter_id`、book_id、ordinal、title、source_ref | 稳定章节顺序；TXT/MD 至少有一个默认 chapter。 |
| `ReadingChunk` | `chunk_id`、chapter_id、ordinal、text、prev_id、next_id、start_offset、end_offset、content_hash | 稳定可定位片段；重导入相同内容不会改变 ID。 |
| `ReadingProgress` | `book_id`、session_id、current_chunk_id、last_read_at、completed_at | 一个共读会话的恢复位置；不能用聊天历史猜测。 |
| `ReadingAnnotation` | `annotation_id`、chunk_id、author、text、visibility、created_at | `visibility=private/shared`；private 笔记永不进入模型上下文。 |
| `ReadingNoteBatch` | `session_id`、chunk_id、shared_annotation_ids、sent_at、trace_id | 记录哪些共享笔记已经给过模型；同一会话同一 chunk 不重复发送完整文本。 |
| `ReadingSession` | 复用 `ActivitySession(kind="reading")`，关联 `book_id`、`current_chunk_id`、`reading_progress_id` | 生命周期沿用 `planned → active → paused → completed/cancelled`。 |

### 内容与隐私规则

- 文本是用户私有数据，模型只接收当前 chunk、上一/下一 chunk 标题以及用户明确选择共享的笔记。
- annotation 默认 private；切换为 shared 是一次明确写操作，并记录 event/trace。
- 任何导入文件先检查 MIME、扩展名、UTF-8、解压后大小、文件数量、路径穿越和重复内容 hash。
- chunk 只作为定位与上下文预算单元，不能替代原始内容；点击引用必须能回到章节和偏移。

## 服务、存储与 API

### 服务划分

新增 `ReadingService`，由 `CompanionRuntime` 聚合；它调用 `LifeFlowService` 创建/推进 reading activity，并只通过既有 `SchedulingService` 建立续读提醒。

`ReadingStore` 与 `LifeFlowStore` 一样位于 runtime 输出目录，可单独做 schema 迁移。所有写操作产生 event，timeline 由现有 projector 读取 event 和 activity，不引入独立 timeline 表。

### API 草案

| 能力 | API |
| --- | --- |
| 安全导入与预检 | `POST /api/reading/books/preview`、`POST /api/reading/books` |
| 书籍/章节列表 | `GET /api/reading/books`、`GET /api/reading/books/{book_id}`、`GET /api/reading/books/{book_id}/chapters` |
| 片段阅读与检索 | `GET /api/reading/chunks/{chunk_id}`、`GET /api/reading/books/{book_id}/continue`、`GET /api/reading/books/{book_id}/search?q=…` |
| 共读会话 | `POST /api/reading/sessions`、`GET /api/reading/sessions/{id}`、`POST /api/reading/sessions/{id}/start|pause|resume|complete` |
| 更新位置 | `POST /api/reading/sessions/{id}/progress` |
| 边注 | `GET/POST /api/reading/chunks/{chunk_id}/annotations`、`PATCH/DELETE /api/reading/annotations/{id}` |
| 与角色讨论 | `POST /api/reading/sessions/{id}/discuss-preview`、`POST /api/reading/sessions/{id}/discuss-confirm` |
| 续读计划 | `POST /api/reading/sessions/{id}/reminders` |

所有产生新状态的模型动作继续走 `/api/actions/preview` + confirm 语义；`discuss` 只读操作可直接调用，但必须回传引用 chunk、共享笔记 ID 和 trace ID。

## Web 体验

在现有“今天 · 一起做”面板旁新增 **共读书房**，而不是重写聊天页：

1. **书架**：导入文本、展示最近阅读、继续阅读。
2. **阅读台**：当前 chunk、章节进度、上一段/下一段；长文本不一次渲染全书。
3. **页边**：私密/共享笔记显式区分，分享前有状态提示。
4. **一起聊这段**：将当前片段和已共享笔记生成可见 preview；回复展示引用来源。
5. **收尾**：暂停、创建续读提醒、完成一本书、写入日记草稿。

移动端优先保证“继续阅读、添加笔记、切换 shared、创建续读提醒”；章节管理和导入预检先保持桌面优先。

## 分阶段实施

### 切片 1：本地内容与稳定分块

- 实现 TXT/MD 预检、导入、私有文件存储、hash 去重、章节和稳定 chunks。
- 实现 book/chapter/chunk API、continue、简单全文包含搜索。
- 创建阅读 fixture：短文本、多章节 Markdown、非法编码、超大文件、路径穿越压缩包。

验收：同一文件重复导入不产生第二份内容；任何 chunk 均可经 `prev_id/next_id` 恢复；不合规文件不会写入数据库或私有目录。

### 切片 2：进度、会话与边注

- 扩展 `ActivitySession` 支持 `reading`，并实现 `ReadingProgress`、annotation CRUD、private/shared 状态。
- 创建/暂停/恢复/完成 reading session；更新位置幂等且带事件。
- timeline、today 和 diary draft 显示阅读会话与完读事件。

验收：重启后从上一个 chunk 恢复；private annotation 不进入 discuss payload；重复 progress 请求不会复制 timeline item。

### 切片 3：受控讨论与续读提醒

- 构建只含当前 chunk、章节标题、共享笔记的 discuss prompt；回复必须带引用信息。
- 讨论前展示 preview，记录 note batch 与 trace，避免同一会话反复附带整段文本。
- 创建续读 task/reminder，沿用 DND、daily limit、安全门和 outbox 回执。

验收：聊天不能直接改变进度/annotation/reminder；确认后只写一次；通知被拦截时有可解释 hold，解除后能由既有 worker 投递。

### 切片 4：完读回顾与 EPUB 评估

- 完读时生成基于 reading event 的日记草稿；用户编辑保存后才进入日记。
- 在文本闭环稳定后评估 EPUB parser：仅实现章节边界、文本抽取和安全解压；不做样式阅读器。
- 更新 export bundle 的 reading 分区（元数据、进度、笔记；原文件按用户显式选择导出）。

验收：完成一本 fixture 书能从时间线跳到阅读记录和日记草稿；EPUB 失败不会影响 TXT/MD 功能或损坏已有书籍。

## 功能验证（不做角色/记忆质量评估）

新增 `luminous-dev/tests/test_shared_reading.py` 和 `luminous-dev/evals/companion_foundation/shared_reading.py`：

- 导入安全、hash 去重、稳定 chunk、章节/位置恢复、搜索。
- session 状态迁移、并发/重复 progress、private/shared annotation 边界。
- discuss preview/confirm、上下文预算、note batch 去重和 trace。
- reading → task/reminder → worker → outbox → receipt，及 quiet-hours/每日上限 hold。
- 完读 → timeline → 日记 draft → save 的端到端路径。
- HTTP contract、网页脚本语法、mock API 服务 smoke test。

## 后续排序

1. **共听/共享内容**：复用 `ActivitySession` 和 content artifact contract，不接入外部账号。
2. **语音朗读与语音聊天**：以 reading segment 为第一个明确的 TTS 测试场景；先做输入输出 adapter，再考虑 Live2D/VRM。
3. **多人格与数据迁移**：在内容、活动和历史都已稳定后再引入隔离与迁移。
4. **质量优化**：角色一致性、记忆召回和主动策略在拥有更多功能轨迹后单独评估。
