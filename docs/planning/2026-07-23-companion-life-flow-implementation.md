# 已完成实施记录：陪伴生活流

> 实现状态（2026-07-23）：已完成。活动数据以 `LifeFlowStore` 独立 SQLite 持久化在同一 runtime 输出目录中，并由 `LifeFlowService` 与既有运行时、日程服务、trace/outbox 衔接；这样避免继续扩大既有 `CompanionRuntimeStore` 的职责边界。

## 结论

下一轮目标是把栖光从“能聊天、能提醒”的伴侣运行时，变成一个可实际使用的 **陪伴生活流**：用户能和角色一起安排今天、推进共同事项、完成一次打卡、记录一天，并在合适的时候收到可操作的提醒。

当前不做数据迁移、外部平台导入、多人格、角色拟合优化或真实用户试验。功能是否完成只以可重复的端到端脚本、持久化恢复和网页操作闭环为准；“像不像角色”“记忆是否足够自然”作为后续质量优化议题，不阻塞本轮功能实现。

## 调研结论如何落到产品

| 参考项目 | 文档中的关键能力 | 栖光本轮的落点 | 不照搬的部分 |
| --- | --- | --- | --- |
| Aura / AI Companion Runtime | 关系状态、记忆、提醒、工具、trace 组成长期运行时。 | 复用现有 state、memory、scheduler、outbox、trace；活动只经由服务层写入。 | 不新建第二套聊天或通知运行时。 |
| `astrbot_plugin_private_companion` | 日程、重要日期、日记、低频主动消息形成生活节奏。 | 今天、例行打卡、每日回顾、活动驱动的提醒。 | 不推断敏感纪念日，也不提高消息频率。 |
| Phosphene | 任务、打卡、奖励和审计让共同完成有连续性。 | 共同任务、步骤、完成记录、连续天数与审计。 | 本轮不做积分、商城、强刺激奖励或关系数值化。 |
| Journal | `timeline + diary + todo` 是可替换 runtime 的结构化展示契约。 | 将现有事件、日程和任务投影为时间线；日记为可编辑的独立记录。 | 不把时间线做成新的业务真相，也不先重写独立前端。 |
| reading-nook / co-reading-kit | 内容切片、章节位置、批注和长期笔记支撑共读。 | 先抽象活动会话与内容引用；下一阶段接入共读。 | 本轮不处理长文档解析、版权内容、阅读器和向量检索。 |
| Duetto | 共享内容可成为日后回忆的锚点。 | 为活动保留 `content_ref` 与结果/感受字段。 | 本轮不接音乐平台或外部 OAuth。 |
| revive-companion / dylan-heartbeat | 主动联系需要上下文、频率限制和可解释原因。 | 活动创建的提醒仍经过现有偏好、quiet hours、每日上限和安全门。 | 本轮不做概率模型或基于真实用户行为的策略学习。 |

## 现有基础与缺口

已可复用：

- `CompanionRuntime` 的聊天、状态、记忆编辑/遗忘、事件、trace、outbox feedback/receipt。
- `SchedulingService` 的提醒、日程、延期、完成、取消、重复规则和 worker 到期投递。
- 通知偏好、quiet hours、每日上限、主动消息安全门及网页 Console 的“今天 / 提醒 / 日程 / 主动联系”区域。

尚缺：

- 可独立于 reminder 的任务、步骤、例行打卡、共同活动和日记领域对象。
- 从既有事件到“今天”和时间线的统一读取模型。
- 活动操作与提醒、日程、memory、outbox 的明确关联。
- 用户在网页发起、进行、完成、回顾一项共同活动的闭环。

因此本轮新增的是 `activity` 与 `life_flow` 能力层；不改变已有聊天、记忆、状态、scheduler 的职责。

## 产品主线：三段生活循环

```text
规划今天 → 一起推进 → 留下回顾
    │            │            │
日程/任务     打卡/步骤      时间线/日记
    │            │            │
提醒触发 ← 活动状态 ← 事件与证据
```

### 1. 规划今天

“今天”不是仅展示 calendar，而是把当天日程、待办、例行打卡和等待回应的共同事项汇总成一个可操作页面。用户或角色可从聊天中创建事项；网页也可直接创建。

首批用户动作：创建任务、拆分步骤、关联日程、设置提醒、延期、标记完成、取消。

### 2. 一起推进

“一起”不等于让模型替用户做事。角色扮演的是陪伴者：发起一次专注、询问进展、记录完成、在用户明确同意后创建下一次提醒。每一步都应有状态和来源，不能只存在于模型回复文本中。

首批活动模板：

1. **共同任务**：如“今晚整理房间”；可选步骤、截止时间和提醒。
2. **专注陪伴**：如“陪我学习 25 分钟”；开始、暂停、结束、简短回顾。
3. **每日打卡**：如喝水、散步、早睡；可设置频率和当天状态。
4. **晨间计划 / 睡前回顾**：受控问答模板，产生任务或日记草稿，不自动改写长期记忆。

### 3. 留下回顾

时间线汇合聊天事件、任务/打卡变化、提醒投递和日程事件；日记是用户可编辑、可删除的独立内容。系统可生成“今日草稿”，但只有用户保存后才成为日记；任何自动摘要都带来源事件 ID 和时间范围。

## 领域设计

### 边界原则

- `Reminder` 仍只负责“何时提醒/是否投递”，不能被用作任务数据库。
- `CalendarEvent` 仍只负责时间占位；可关联任务，但不是任务完成状态的唯一来源。
- `Outbox` 仍是消息投递与回执，不承担活动业务真相。
- `ConversationEvent` 是审计和时间线输入；活动本体由专用记录保存。
- 所有模型建议先以 draft 返回，涉及新任务、日程、提醒或日记写入必须显式确认。

### 新增领域对象

新增 `luminous/runtime/domain/activity.py`：

| 对象 | 关键字段 | 说明 |
| --- | --- | --- |
| `Task` | `task_id`、title、description、status、due_at、priority、source、calendar_event_id、reminder_ids、metadata | 一项可完成的共同事项；状态为 `open / in_progress / blocked / completed / cancelled / archived`。 |
| `TaskStep` | `step_id`、task_id、title、position、status、completed_at | 任务的有序可选步骤，不能独立投递通知。 |
| `Routine` | `routine_id`、title、schedule、active、reminder_policy、streak | 例行事项配置；不把每次完成都覆盖成一条任务。 |
| `RoutineCheckin` | `checkin_id`、routine_id、period_key、status、note、occurred_at | 某个周期内的真实打卡记录，`period_key` 保证幂等。 |
| `ActivitySession` | `session_id`、kind、title、status、started_at、ended_at、task_id、content_ref、summary | 泛化的共同活动会话；首批支持 `focus`、`checkin`、`planning`、`reflection`。 |
| `DiaryEntry` | `entry_id`、date、title、body、source_event_ids、status、created_at、updated_at | 用户保存的日记；`draft / saved / deleted`，自动草稿不可直接替代用户文本。 |
| `LifeTimelineItem` | `item_id`、occurred_at、kind、title、source_type、source_id、action_url | **只读投影**，由上述对象与既有 event/calendar/reminder/outbox 合并生成，不单独存储。 |

所有对象维持当前单用户默认作用域，并预留 `user_scope`。本轮不引入 `persona_id` 或迁移旧数据。

### 状态迁移

```text
Task: open → in_progress → completed
       └──────────────→ cancelled
       open/in_progress → blocked → in_progress

ActivitySession: planned → active → paused → active → completed
                                 └──────────────→ cancelled

RoutineCheckin: pending → completed | skipped
```

状态迁移必须幂等。`complete`、`cancel`、`check in` 和 session end 重复提交不重复记事件、连续天数或提醒；非法跳转返回结构化错误。

## 服务与存储设计

### 应用服务

新增 `luminous/runtime/application/life_flow_service.py`，由 `CompanionRuntime` 和 facade `CompanionService` 暴露；HTTP handler 只做参数校验和错误映射。

服务职责：

1. 任务、步骤、例行、打卡、活动会话、日记的 CRUD 与状态迁移。
2. 从任务/例行生成或关联 reminder/calendar event；取消和完成时同步更新关联提醒，但不删除历史审计。
3. 生成“今天”聚合：今日日程、过期任务、即将到期任务、待打卡例行、活动中的 session、今日已完成事项。
4. 生成 timeline：稳定排序、按天分组、返回 source ID 和可操作链接。
5. 生成日记草稿：仅收集当天结构化事件，写入 `DiaryEntry(status=draft)`；保存必须显式调用。
6. 把所有写操作追加为可追溯 event，并在 trace 中记录 trigger、结果和关联 ID。

### 存储

活动基础设施增加：

- `LifeFlowStore` 持有 `tasks`、`task_steps`、`routines`、`routine_checkins`、`activity_sessions`、`diary_entries` 表及必要索引；它与 `CompanionRuntimeStore` 共享 runtime 输出目录，避免活动数据继续堆进记忆/消息存储类。
- `task_id`、`routine_id`、`session_id` 等关联字段只允许存在于其业务表；reminder/calendar 的 metadata 仅保存反向引用，避免 JSON 成为查询主通道。
- `claim_due_routines(now)`：只返回本周期未生成 checkin 的例行项；worker 重跑安全。
- export bundle 暂只增加这些新本地数据分区，不做 import API 或外部迁移。

## API 草案

| 目的 | API |
| --- | --- |
| 今天聚合 | `GET /api/today?date=YYYY-MM-DD` |
| 任务列表/创建 | `GET/POST /api/tasks` |
| 任务读取/修改/归档 | `GET/PATCH/DELETE /api/tasks/{id}` |
| 任务步骤 | `POST /api/tasks/{id}/steps`、`PATCH /api/tasks/{id}/steps/{step_id}` |
| 推进任务状态 | `POST /api/tasks/{id}/start`、`/complete`、`/block`、`/cancel` |
| 例行与打卡 | `GET/POST /api/routines`、`PATCH/DELETE /api/routines/{id}`、`POST /api/routines/{id}/checkins` |
| 共同活动会话 | `GET/POST /api/activities`、`POST /api/activities/{id}/start|pause|resume|complete|cancel` |
| 日记 | `GET/POST /api/diary-entries`、`GET/PATCH/DELETE /api/diary-entries/{id}`、`POST /api/diary-entries/draft` |
| 时间线 | `GET /api/timeline?from=…&to=…&kind=…` |
| 聊天内确认动作 | `POST /api/actions/preview`、`POST /api/actions/confirm` |

`/api/actions/*` 采用明确的 action schema，例如 `create_task`、`complete_task`、`start_focus_session`、`create_reminder`。模型或聊天 UI 只能提交 preview；前端展示确认卡后才调用 confirm。这样同一机制也可复用已有日程/提醒工具。

## Web Console 信息架构

不重写 `apps/companion-web/companion-ui`，在现有侧栏/面板上扩展五个入口：

1. **今天**：时间轴上半区显示日程；下半区显示任务、例行和活动中 session；每项提供一个主操作。
2. **一起做**：快速开始专注、创建任务、今日打卡；活动进行时有最小计时和结束入口。
3. **回顾**：按日查看 timeline；创建、继续编辑、保存日记草稿。
4. **收件箱**：既有 outbox 保留，活动提醒须直接跳到任务/打卡/回顾操作，不只展示一段文案。
5. **聊天确认卡**：识别结构化 action preview，显示对象、时间、提醒和影响范围，确认后写入服务层。

移动端只保证“今天、快速打卡、完成任务、保存日记”四条高频路径；复杂任务编辑先留在桌面布局。

## Worker 与主动联系

在既有 worker 增加两个独立 job：

1. `routine_due_tick`：为今天到期的 routine 创建待打卡项，必要时由现有 reminder 流程投递。
2. `activity_expiry_tick`：处理已过期的专注 session、已过期任务和未保存的日记草稿；只标记/提示，不能擅自完成任务或写入长期记忆。

所有由活动产生的外发消息仍经过：通知总开关、类型开关、quiet hours、daily limit、安全策略、幂等 key、outbox feedback/receipt。`Task` 或 `Routine` 不得绕过 `SchedulingService` 直接发送。

## 交付切片

### 切片 1：任务与今天

- 增加 `Task`、`TaskStep`、迁移、store、`LifeFlowService`。
- 实现任务 CRUD、步骤、状态流转、提醒/日程关联和 `GET /api/today`。
- 在网页加入“今天”和任务操作。

完成标准：创建任务 → 关联提醒 → worker 到期 → outbox → 点击打开任务 → 完成任务，重启后仍一致；取消任务不会错误投递旧提醒。

### 切片 2：例行打卡与专注陪伴

- 增加 `Routine`、`RoutineCheckin` 和 `ActivitySession`。
- 实现周期计算、幂等打卡、连续天数、开始/暂停/结束专注会话。
- 接入 routine worker 与快速打卡 UI。

完成标准：同一周期重复 tick 或重复打卡不增加 streak；暂停/恢复/完成 session 均可审计；DND/上限下被抑制的提醒保留原因且可在下次合法 tick 重试。

### 切片 3：时间线与日记

- 实现 timeline projector，合并 conversation event、memory change、task/routine/session、calendar/reminder/outbox receipt。
- 增加 `DiaryEntry` 和基于当天事件的 draft；保存、编辑、删除均有来源和审计。
- 在网页提供按天查看和日记编辑。

完成标准：时间线项目可追溯到源记录；日记草稿不自动变成 memory；删除日记不会删除源事件或任务历史。

### 切片 4：聊天内活动确认与可运行演示

- 定义 action preview/confirm contract，接入任务、提醒、开始专注、记录打卡、创建日记草稿。
- 在 mock 与真实模型路径均支持结构化确认卡；模型的自由文本绝不直接写库。
- 提供一条从晨间计划到睡前回顾的 demo scenario。

完成标准：聊天提出“今晚提醒我整理房间”只产生 preview；确认后才建 task/calendar/reminder；晚间完成后出现在时间线和日记草稿中。

## 验证策略（功能，不做质量评测）

新增 `luminous-dev/tests/test_companion_life_flow.py` 与 `luminous-dev/evals/companion_foundation/life_flow.py`。覆盖：

- 任务、步骤、提醒、日程、outbox 的完整状态链与进程重启。
- duplicate HTTP 请求、worker 重跑、跨天 routine、时区边界、取消/延期后的幂等性。
- 提醒受 quiet hours、daily limit、安全门阻止时的 trace 和恢复路径。
- timeline 的来源完整性、排序、过滤和 diary draft/save/delete 的边界。
- action preview 未确认不得写库；确认后只写一次。
- HTTP contract、Web API 调用、前端脚本语法和 mock API 演示。

这里的 eval 只验证功能契约和确定性结果，不评价角色口吻、情感质量或记忆召回质量。

## 明确暂缓

- 数据迁移、导入向导、外部账号/OAuth 和多人格数据隔离。
- 共读解析器、音乐服务、图片/视频共享和第三方内容接入；它们后续只需实现 `ActivitySession(kind=...)` 适配器。
- 奖励积分、亲密度加分、连续打卡惩罚；先避免把陪伴关系游戏化。
- 自动写日记、自动把活动结论写入长期记忆、自动完成任务。
- 语音、感知、Live2D/VRM；作为后续输入输出适配层，不影响本轮领域闭环。

## 完成定义与后续顺序

本轮完成时，栖光应能跑通一条无需真实用户测试的完整生活流：

> 晨间创建计划 → 日间开始一次专注 → 打卡/完成任务 → 晚间收到合规提醒 → 在今天页完成事项 → 在时间线回看 → 保存一篇日记。

完成后再按此顺序扩展：

1. 共读（`ActivitySession + content_ref + note`）。
2. 共听/共享内容（同一活动会话协议）。
3. 语音输入输出（沿用聊天和 action preview）。
4. 多人格、数据迁移和外部平台兼容。
5. 角色表现、记忆可靠性与主动策略的质量优化。
