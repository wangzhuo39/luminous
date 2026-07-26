# Luminous S3 Design 04：提醒光尘、日历窗框与陪伴者光签

> 状态：实现基线 v1
> 设计：Gemini；工程边界与完整性审查：Codex
> 初稿 trace：`/home/wz/gemini-api-traces/runs/20260725T022454.669484Z_luminous-s3-design04-scheduling-actions_85e86ceb/`
> 修订 trace：`/home/wz/gemini-api-traces/runs/20260725T023418.728134Z_luminous-s3-design04-repair_be60c309/`

## 1. 体验隐喻与空间关系

- Reminder 是“提醒光尘”：轻盈地等待被安置，不用警报表达 due。
- Calendar 是“窗框刻度”：现实时间在温室光窗上的痕迹，不做大型月历或效率仪表盘。
- Companion Action Proposal 是对话前景的一枚“光签”：陪伴者提出意向，用户先看清影响，再明确确认或婉拒。

Reminder 与 Calendar 全部位于既有 `#today-overlay` 的子视图中；不新增路由、页面或第二 modal。光签属于聊天前景，不挤进 Today，也不打断对话。

## 2. 信息架构与概念组件

```text
Today 主视图
  ├─ ReminderList ─ ReminderDetail / ReminderEditor / SnoozeEditor
  └─ CalendarScaleList ─ CalendarEventDetail / CalendarEventEditor

Chat 前景
  └─ ActionProposal ─ ActionPreviewCard（同一内联区域展开）
```

- `SubviewHeader`：复用 S3 返回、标题和关闭语义。
- `ReminderList` / `ReminderDetail` / `ReminderEditor`：列表、详情和创建/编辑表单。
- `SnoozeEditor`：原详情内展开的精确新时间表单。
- `CalendarScaleList` / `CalendarEventDetail` / `CalendarEventEditor`：窗框刻度列表、详情和表单。
- `InlineConfirmation`：Calendar 移出确认；不打开新 dialog。
- `ActionProposal` / `ActionPreviewCard`：可复用的聊天内联光签。
- `LocalStatePanel` / `InlineErrorRegion`：局部加载、空、错误、重试和 `aria-live="polite"`。

## 3. Reminder 列表与表单

默认列表分为两个低密度区：

- 待照看：scheduled、due、snoozed，按 dueAt 升序；
- 已落定：本次已加载集合中的 completed、cancelled、expired，默认折叠。

due 只改变材料沉降和短文案，不使用红色、逾期天数、徽章或催促。

创建/编辑字段：

- title：必填、定长纯文本；
- dueAt：必填 `datetime-local`；
- description：可选、定长纯文本；
- recurrence：无、daily、weekly；
- timezoneName：由前端时间适配器生成，不让用户编辑内部字符串；
- kind：普通用户创建固定为 reminder，不提供内部 proactive kind 选择器。

## 4. Reminder 状态与动作

| 状态 | 可用动作 | 视图 |
| --- | --- | --- |
| `scheduled` | 完成、延后、取消提醒、编辑 | 冰蓝微光 |
| `due` | 完成、延后、取消提醒、编辑 | 落下的月雾光尘，不报警 |
| `snoozed` | 完成、再次延后、取消提醒、编辑 | 较弱冰蓝 |
| `completed` | 无 | 静态只读 |
| `cancelled` | 无 | 低对比只读 |
| `expired` | 无 | 低对比只读 |
| `unknown` | 无 | 安全只读降级 |

请求：

- 完成：`POST /api/reminders/{key}/complete`，body `{}`；
- 延后：展开 `datetime-local`，必须提交新的合法 `{due_at}` 到 `POST …/snooze`；没有相对 delay 快捷按钮；
- 取消：只使用 `POST /api/reminders/{key}/cancel`。UI 不再提供语义重复的 DELETE；
- 普通编辑：`PATCH /api/reminders/{key}`，只发送变化字段。

取消成功后以服务端 `status=cancelled` 为准，从待照看区移到当前集合的已落定区，不从内存无条件丢弃。

## 5. Calendar 窗框刻度

Calendar 使用按 startsAt 升序的纵向刻度，不做月历网格。全天事件排在同日定时事件之前，不显示虚构时间。

字段：

- title：必填；
- startsAt：必填；
- endsAt：可选，不能早于 startsAt；
- allDay：真实 checkbox/switch，标签“全天”；
- timezoneName：由时间适配器产生。

当前领域模型没有 description；不得渲染或提交该字段。详情直接使用列表返回的 CalendarEventVM，因为没有 GET 单条端点。

移出日历：

1. 在详情内展开 `InlineConfirmation`；
2. 文案：“从日历窗框移出这个刻度？” / “移出后，它将不再出现在当前日历列表中。”；
3. 调用 `DELETE /api/calendar-events/{key}`；
4. 只有服务端返回 `status=deleted` 才从 active 列表移出；
5. 当前无恢复端点，不承诺永久删除，也不提供虚假撤销。

## 6. 时间、时区与全天算法

禁止手工拼接时区偏移，也禁止直接截断后端 ISO 字符串的 `Z`。

### 6.1 timed 输入到请求

1. 从 `datetime-local` 严格解析 year、month、day、hour、minute。
2. 构造 `new Date(year, month - 1, day, hour, minute)`。
3. 使用本地 getter 将各部分读回，与输入逐项相等才有效。这会拒绝 DST 跳时被浏览器自动归一化的时间。
4. 通过 `date.toISOString()` 发送 UTC `Z` instant。
5. `timezone_name` 取 `Intl.DateTimeFormat().resolvedOptions().timeZone`；只有合法非空 IANA 名称才使用，否则降级 `UTC`。

后端 ISO 回显到编辑器时，先解析为有效 Date，再用本地 getter 补零组合 `YYYY-MM-DDTHH:mm`。不能使用 `iso.slice(0, 16)`。

错误：

- 格式无效：“请选择有效的日期和时间。”
- DST 不存在时间：“这个本地时间不存在，请换一个时间。”
- 结束早于开始：“结束光影不能早于开始。”

错误使用 `aria-describedby` 关联字段，并把焦点移至首个无效输入。

### 6.2 all-day

- 勾选 allDay 后显示 `<input type="date">`，不保留隐藏的旧时分作为提交依据。
- 把所选日期构造为本地午夜 Date，round-trip 校验日期后 `toISOString()`。
- 通过 `all_day:true` 保留全天语义；编辑时按浏览器本地日期回显。
- 可选结束日期不得早于开始日期。当前不自行定义“结束日是否排他”等契约外语义，只展示后端存储值。

## 7. Action Proposal 集成边界

当前 `/api/chat` 没有 action proposal 字段，因此生产界面不得假装自动收到建议，也不得给用户一个手写 action payload 的入口。

本阶段实现：

- 可复用 `ActionProposalController` 和 `ActionPreviewCard`；
- 接收已经过调用方边界检查的 proposal；
- fixture 和浏览器测试可注入 proposal；
- 生产触发器保持门控，待 chat/事件契约提供正式 proposal 来源后接入。

用户直接创建 Reminder、Calendar、Task 等仍走各自 CRUD，不走 action preview/confirm。

## 8. 五种 Action 的安全摘要

| action | 隐藏寻址/请求字段 | 可见摘要 | 缺失/未知处理 |
| --- | --- | --- | --- |
| `create_task` | 无 | title；合法 priority、dueAt 有值时才显示 | title 缺失拒绝预览 |
| `complete_task` | task_id | 已加载 TaskVM 的 title | 映射不到拒绝确认，不抓取、不显示 ID |
| `start_focus_session` | 无 | title | title 缺失拒绝；忽略输入 kind，服务端固定 focus |
| `checkin_routine` | routine_id | 已加载 RoutineVM 的 title；可选 note | 映射不到拒绝确认 |
| `draft_diary` | 无 | “为 {date/今天} 生成一份可编辑日记草稿” | date 无效拒绝；没有 title |

`draft_diary` 确认成功返回已持久化草稿，进入 DiaryEditor；后续保存必须 PATCH，不重复 action 或 POST。

## 9. ActionPreviewVM 与适配器

```text
ActionPreviewVM
  previewKey: opaque in-memory key
  action: one of 5 allowed actions
  requestSnapshot: deeply cloned, normalized, frozen allowlisted payload
  summaryLines: bounded plain text[]
```

- `previewKey` 可映射服务端 preview_id，但只存内存，不渲染，也不声称 confirm 会校验它。
- `requestSnapshot` 必须保留执行所需的 task_id/routine_id 等不透明寻址 key；“不显示 ID”不等于从请求快照删除 ID。
- 未允许字段在进入快照前剔除；ID 不进入 summaryLines、DOM 属性、console 或错误文案。
- 视图只用 `textContent` 渲染 summaryLines，不读取原始 payload。
- confirm 发送 snapshot 中完全相同的 action/payload 加 `confirmed:true`；不得在预览后静默改变。

## 10. Action 状态机

```text
proposal
  → previewing
  → preview_ready
      ├─ cancelled（本地收起，不 confirm）
      └─ confirming
           ├─ success
           └─ error → confirming（同一 snapshot 重试）
```

- previewing 调用 `/api/actions/preview`；失败保留 proposal，允许重试或忽略。
- preview_ready 才允许“确认”与“婉拒”。
- confirming 同时禁用确认和婉拒，因为服务端可能已经执行。
- 卸载/关闭可 abort 本地等待，但不得宣称服务端没有执行。
- 每次预览、确认或重试都有新 attempt token；token 只负责客户端单次提交与过时响应隔离，不等同服务端幂等保证。
- 快速双击只发一个请求；失败重试仍使用同一个冻结 snapshot。
- success 只根据真实响应更新对应 store；光签材料短暂凝结后安静收起，不用 toast。

## 11. 安全 ViewModel

```text
ReminderVM
  key, title, description, dueAt, timezoneName, recurrence, status

CalendarEventVM
  key, title, startsAt, endsAt, allDay, timezoneName, status
```

- Reminder status：scheduled/due/snoozed/completed/cancelled/expired/unknown。
- recurrence：daily/weekly/null；后端空字符串归一化为 null。
- Calendar status：active/deleted/unknown。
- 时间必须为有效 ISO instant，否则 adapter 拒绝该项或把可选 endsAt 归一化 null。
- 拒绝 metadata、source、source_ref、user_scope、delivery_count、last_delivered_at、reminder_ids、created_at、updated_at、audit event 和未知字段。
- key 只在内存请求层存在，不渲染、不日志化、不写入 `data-*`。

## 12. 非乐观写入与局部状态

- 每个列表首次打开才 GET；不轮询，不显示同步时间。
- 写入为 idle → pending → success/error；每次创建 attempt token 与 AbortController。
- pending 时 input/textarea readOnly，select/checkbox/button disabled；不得锁死整个 form。
- 只有当前 token 的安全响应能替换 store；过时或 aborted 响应无效。
- 失败精确恢复草稿、选择、展开状态和可操作性，使用局部安全错误。
- Reminder/Calendar 列表 empty/error 独立；一个写入错误不抹掉已加载集合。
- 反馈不声称本地、加密、云端或账号同步。

## 13. 视觉与动效

- 面板继续使用 S3 既有玻璃材料，不额外叠加大面积 blur。
- 光尘是 1–2 个低对比点/边缘光，不用粒子雨；due 以轻微下沉和月雾灰表达。
- 日历刻度使用 `rgba(255,255,255,.08)` 细线和冰蓝焦点，不画表格。
- 光签使用边框折光与少量阴影，不使用实心 CTA。
- 出现动效：opacity 0→1、最多 4px 位移、约 240–300ms；pending 呼吸不少于 5s 一次。
- reduced motion 下取消循环和位移，保留静态层级与可见焦点。

## 14. 响应式与无障碍

- Today 桌面 420px、移动不超过 85dvh；只滚动内部内容区。
- 软键盘出现后动作区进入普通文档流，聚焦时间/标题与提交按钮可滚入视口。
- 所有按钮和 checkbox label 至少 44×44；状态不只依赖颜色。
- `aria-live="polite"` 只包含短状态，不包裹列表。
- ActionPreviewCard 使用语义 section/group 和可见标题，不冒充系统 dialog。
- 返回和关闭恢复准确焦点；Action cancelled 恢复到对应对话触发位置。

## 15. 截图与自动化验收

截图矩阵：

| 区域 | 必须状态 |
| --- | --- |
| Reminder | list mixed / empty / error；create；edit；snooze；pending；error；cancelled terminal |
| Calendar | scale mixed/all-day；create；edit；invalid end；pending；error；inline remove；deleted success |
| Action | proposal；previewing；preview_ready；confirming；success；error；cancelled；missing mapping；reduced motion |
| Responsive | desktop 1440×900；mobile 390×844；两类表单软键盘；长标题 |

自动化断言：

1. Reminder snooze 只提交合法 due_at，没有相对 delay 按钮；取消只调用 POST `/cancel`。
2. Calendar 不渲染/提交 description；无 GET 单条请求；deleted 响应前不移出。
3. timed/all-day round-trip、ISO Z、timezone fallback、DST 非法时间和 end>=start 均被测试。
4. preview 与 confirm 的规范化 action/payload 深相等，confirm 额外只有 `confirmed:true`。
5. complete_task/checkin_routine 映射失败时不 confirm，DOM/console 不出现后端 ID。
6. start_focus_session 不显示 kind；draft_diary 不显示 title，成功后 PATCH 保存。
7. confirming 双按钮禁用；双击只发一次；abort/过时响应不更新状态；失败可用同一 snapshot 重试。
8. pending 锁定语义、草稿精确恢复、焦点返回、44×44、软键盘和 reduced motion 均通过浏览器验收。
9. 页面不存在 spinner、toast、月历网格、红点、第二 modal、轮询和无依据隐私承诺。

## 16. 工程门控

- Chat proposal 来源：当前响应契约缺失；组件/controller 可交付，生产触发保持门控。
- Calendar 单条读取：接口缺失；详情只用列表对象。
- Calendar description：领域字段缺失；不设计。
- Reminder 相对 snooze：接口只接受新 due_at；不设计相对参数。
- Calendar/Diary/Reminder 恢复：接口缺失；不提供假撤销。
- Notification Settings：属于 S4，不在本阶段展开。
