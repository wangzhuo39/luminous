# Luminous S3 Design 05：跨域实现方案与分批交付计划

> 状态：实现基线 v1
> 工程方案候选：Gemini；完整性与架构审查：Codex
> trace：`/home/wz/gemini-api-traces/runs/20260725T023839.856026Z_luminous-s3-design05-implementation-plan_8470277b/`

## 1. 目标与边界

S3 在不破坏 S1 fixture 和 S2 核心聊天的前提下，完成 Today、Timeline、Task、Routine、Activity、Diary、Reminder、Calendar 与 Action Preview/Confirm。

工程约束：

- Vanilla HTML/CSS/ES modules，零构建、零新增运行时依赖；
- 一个 `#today-overlay` dialog；Action 光签在聊天前景内联；
- API/fixture 两套 DataSource 同构；
- 原始响应不进入 View 或 AppState；
- 所有写入非乐观、可取消、可重试、可恢复草稿；
- 初始启动仍只请求 `/api/state`；S3 按打开空间懒加载；
- 每个批次由一次或多次无历史 Gemini 调用实现，Codex 应用、审计、测试和截图。

## 2. 现有文件演进

保持 S2 语义不变：

- `js/services/api-client.js`：复用 request、timeout、JSON 和 AppError 边界；仅在确有测试证明的通用缺口时最小修改。
- `js/shared/errors.js`：不增加业务状态。
- `js/conversation.js`、`js/core-runtime.js`：不把 Life-flow 混入聊天/启动控制器。
- `styles/scene.css`、`styles/network-states.css`：不承载 S3 面板布局。

允许最小扩展：

- `index.html`：替换/扩展 Today 内容容器、加入 Action 光签锚点和 `today-s3.css`；不增加 dialog。
- `js/main.js`：只组合 `initLifeFlow()` / `initActionProposal()`，不写业务分支。
- `js/app-state.js`：增加安全稳定的 `lifeFlow` slice 与原子更新入口。
- `js/adapters/api-adapter.js`、`js/fixture-adapter.js`：聚合 S3 DataSource 或保持兼容导出；S2 方法行为不变。
- `js/overlays.js`：旧静态 overlay 初始化迁移到新 Today shell 时保留 S1 fixture 行为和焦点语义。

禁止把全部 S3 堆进 `main.js`、`overlays.js`、`presentation.js` 或单个新文件。

## 3. 目标目录

```text
companion-ui/
├── js/
│   ├── adapters/
│   │   ├── api-adapter.js
│   │   ├── life-flow-adapter.js
│   │   └── life-flow-fixture-adapter.js
│   ├── services/
│   │   ├── api-client.js
│   │   └── life-flow-api.js
│   ├── shared/
│   │   ├── errors.js
│   │   ├── time.js
│   │   ├── validation.js
│   │   └── operation.js
│   ├── features/
│   │   ├── life-flow/
│   │   │   ├── life-flow-controller.js
│   │   │   ├── life-flow-state.js
│   │   │   ├── today-view.js
│   │   │   ├── task-view.js
│   │   │   ├── routine-view.js
│   │   │   ├── activity-view.js
│   │   │   ├── diary-view.js
│   │   │   ├── reminder-view.js
│   │   │   └── calendar-view.js
│   │   └── action-proposal/
│   │       ├── action-controller.js
│   │       ├── action-state.js
│   │       └── action-view.js
│   └── life-flow-datasource.js
└── styles/
    └── life-flow.css
```

必要时可将过大的纯文件进一步拆分，但不得引入同义重复层。

## 4. 单向依赖

```text
main
  → feature controller
    → pure state + DOM view + DataSource interface
      → API or fixture implementation
        → safe adapter
          → API client
```

- View 只渲染安全 VM、收集用户输入和发出意图回调；不 fetch。
- Controller 管副作用、AbortController、attempt token 与视图生命周期。
- `life-flow-state.js` / `action-state.js` 只做纯状态迁移，不引用 DOM/fetch/AbortController。
- `operation.js` 只产生 token、判断 current token 和 single-flight 状态；不持有 AbortController map。
- Adapter 逐字段构造 VM，不导入 View/Controller。
- API service 只知道路径、method、body 和 signal，不知道 DOM。
- fixture 不导入 API client，也不得产生网络请求。

## 5. 状态边界

AppState 只保存可跨子视图共享的稳定安全状态：

```text
lifeFlow
  navigation: { activeSubview, selectedKind, selectedKey }
  today: TodayViewModel | null
  timeline: TimelineItemVM[] | null
  tasks/routines/activities/diaries/reminders/calendarEvents: safe VM collections
  loaded: per-collection booleans
```

不进入 AppState：

- DOM 节点、listener、AbortController、timeout；
- 原始响应、metadata、后端错误正文；
- form draft、selection、scroll position、focus target；
- pending request promise。

Controller 私有状态保存：每个 operation 的 controller、current token、表单提交前 snapshot、触发焦点和滚动位置。View 的未提交草稿保留在真实表单控件；提交前再复制一份用于失败核对。

## 6. 完整 DataSource 接口

API 与 fixture 必须实现同名、同参数、同安全返回：

```text
loadToday({ date, signal }) -> TodayViewModel
loadTimeline({ from, to, kind, limit, signal }) -> TimelineItemVM[]

loadTasks({ status, limit, signal }) -> TaskVM[]
createTask({ input, signal }) -> TaskVM
updateTask({ key, changes, signal }) -> TaskVM
addTaskStep({ taskKey, input, signal }) -> TaskVM or StepVM
updateTaskStep({ taskKey, stepKey, changes, signal }) -> TaskVM or StepVM
transitionTask({ key, action, input, signal }) -> TaskVM
archiveTask({ key, signal }) -> TaskVM

loadRoutines({ activeOnly, limit, signal }) -> RoutineVM[]
createRoutine({ input, signal }) -> RoutineVM
updateRoutine({ key, changes, signal }) -> RoutineVM
checkinRoutine({ key, input, signal }) -> RoutineCheckinResultVM
deactivateRoutine({ key, signal }) -> RoutineVM

loadActivities({ status, limit, signal }) -> ActivityVM[]
createActivity({ input, signal }) -> ActivityVM
transitionActivity({ key, action, input, signal }) -> ActivityVM

loadDiaryEntries({ date, limit, signal }) -> DiaryEntryVM[]
createDiaryEntry({ input, signal }) -> DiaryEntryVM
draftDiaryEntry({ date, signal }) -> DiaryEntryVM
updateDiaryEntry({ key, changes, signal }) -> DiaryEntryVM
removeDiaryEntry({ key, signal }) -> DiaryEntryVM

loadReminders({ status, limit, signal }) -> ReminderVM[]
createReminder({ input, signal }) -> ReminderVM
updateReminder({ key, changes, signal }) -> ReminderVM
transitionReminder({ key, action, input, signal }) -> ReminderVM

loadCalendarEvents({ limit, signal }) -> CalendarEventVM[]
createCalendarEvent({ input, signal }) -> CalendarEventVM
updateCalendarEvent({ key, changes, signal }) -> CalendarEventVM
removeCalendarEvent({ key, signal }) -> CalendarEventVM

previewAction({ proposal, lookup, signal }) -> ActionPreviewVM
confirmAction({ preview, signal }) -> ConfirmedActionResultVM
```

路径差异只在 API service：routine 使用实际 `/checkins`；Reminder cancel 只使用 POST `/cancel`；Calendar/Activity 不调用不存在的 GET 单条。

Action 方法只被门控 controller 调用；普通 CRUD 视图不得调用它们。

## 7. 批次 B1：共享纯逻辑

目标：建立后续所有批次可复用且无需 DOM 的确定性原语。

允许文件：

- 新增 `shared/time.js`、`shared/validation.js`、`shared/operation.js`；
- 新增 `features/life-flow/life-flow-state.js`、`features/action-proposal/action-state.js`；
- 新增对应 Node tests。

不做：HTTP、adapter、DOM、CSS、AppState 集成。

Gemini 上下文：Design 01–04 中时间、状态机、排序、token 规则；现有 errors/app-state 编码风格。

测试：

- local datetime parse/round-trip/ISO Z/回显；all-day；invalid/DST；end>=start；
- Today 固定类别与最多 4 类算法；
- operation single-flight 与 stale token；
-合法/非法业务状态迁移纯表。

完成：新测试全绿且 S2 19/19 不变。

## 8. 批次 B2：安全双数据源

目标：实现所有 S3 读写方法、严格响应适配和同构 fixture，不接 DOM。

允许文件：

- 新增 `services/life-flow-api.js`；
- 新增 `adapters/life-flow-adapter.js`、`life-flow-fixture-adapter.js`；
- 新增 `life-flow-datasource.js`；
- 仅为聚合导出最小修改现有 adapter；
- 新增 adapter/API/fixture tests。

不做：渲染、AppState、视觉。

Gemini 上下文：API contract、真实后端 mismatch 清单、Design 01–04 的所有 VM、现有 api-client/api-adapter/fixture 风格。

重点审计：

- 逐字段构造，后端 key 仅为内存寻址 key；
- `diary_entry`/`entry` 兼容；routine `/checkins`；snooze due_at；
- Diary draft 已持久化；Activity 无 DELETE；Calendar 无 description/GET 单条；
- action snapshot 保留隐藏寻址 key但不生成可见 ID；
- fixture 模式零 fetch，API/fixture 方法签名一致。

完成：路径/method/body 和 allowlist 单测全绿，S1 fixture 网络断言仍为 0。

## 9. 批次 B3：Today 壳、摘要与 Timeline

目标：把静态 Today 升级为可访问的单 dialog 导航壳，接入 `/api/today` 与显式 Timeline。

允许文件：

- 新增 `life-flow-controller.js`、`today-view.js`、`life-flow.css`；
- 最小修改 `index.html`、`main.js`、`app-state.js`、`overlays.js`；
- 新增 Today 纯逻辑和浏览器测试。

不做：资源写操作或各详情表单。

Gemini 上下文：Design 01、B1/B2 当前代码、index/overlays/main/app-state、既有 CSS tokens。

审计：首次启动不请求 Today；首次打开一次懒加载；最多 4 类；Timeline 显式加载；retry；一个 dialog；焦点/滚动恢复；不渲染 action_url/source ID。

完成：desktop/mobile Today populated、empty/error 截图；S1/S2 回归全绿。

## 10. 批次 B4：Task 与 Routine

目标：完整实现 Task/Step 和 Routine/Checkin 子视图与保守写入。

允许文件：

- 新增 `task-view.js`、`routine-view.js`；
- 扩展 controller/state/life-flow.css；
- 仅必要时扩展 AppState 原子更新；
- 新增纯状态和浏览器测试。

不做：Activity、Diary、Reminder、Calendar、Action。

Gemini 上下文：Design 02、B1–B3 当前文件、相关 DataSource 方法。

审计：精确 Task 转换、step `aria-pressed`、归档语义；Routine daily/weekly、none/remind、`/checkins`、deactivate；pending 时 readOnly/disabled；失败 draft 字节级恢复；无 streak KPI。

完成：desktop task/routine、mobile keyboard、pending/error、double-submit 验收通过。

## 11. 批次 B5：Activity

目标：Activity 列表、创建、会话/详情和主场景已知状态派生。

允许文件：

- 新增 `activity-view.js`；
- 扩展 controller/state/life-flow.css；
- 新增 Activity tests。

不做：timer、progress、Activity DELETE、轮询。

Gemini 上下文：Design 03 的 Activity 章节、B1–B4 当前接口/壳。

审计：状态按钮严格合法；unknown/terminal 只读；`/today` 初始不虚构 paused；已加载/本地 pause 后才派生；presence/offline/error 环境优先级不被覆盖。

完成：planned/active/paused/completed、reduced motion、mobile 截图和状态请求断言通过。

## 12. 批次 B6：Diary

目标：列表、手动创建、生成草稿、编辑、保存与移出。

允许文件：

- 新增 `diary-view.js`；
- 扩展 controller/state/life-flow.css；
- 新增 Diary tests。

不做：tags、打字机、永久删除或恢复承诺。

Gemini 上下文：Design 03 Diary 章节、B1–B5 当前接口/壳。

审计：手动 POST 有 date/title/body/saved；draft 捕获 key；保存只 PATCH；DELETE 等服务端 deleted；长正文、软键盘、草稿恢复；文案无本地/加密/云同步。

完成：draft→PATCH 网络断言、remove pending、desktop/mobile editor 截图通过。

## 13. 批次 B7：Reminder 与 Calendar

目标：光尘列表/状态、精确 snooze、窗框刻度、timed/all-day 表单和移出。

允许文件：

- 新增 `reminder-view.js`、`calendar-view.js`；
- 扩展 controller/state/life-flow.css；
- 新增资源和浏览器测试。

不做：通知 Settings、相对 snooze、月历、Calendar description/GET 单条、恢复。

Gemini 上下文：Design 04 Reminder/Calendar、B1 time、B2 API、现有壳。

审计：Reminder cancel 仅 POST；终结区；Calendar deleted 前不移出；datetime 不截 Z；all-day date；invalid end；IANA fallback。

完成：Reminder mixed/snooze/pending、Calendar all-day/invalid/remove、mobile keyboard 和 reduced motion 通过。

## 14. 批次 B8：Action 光签

目标：交付可注入但生产触发门控的 Proposal→Preview→Confirm 组件/controller。

允许文件：

- 新增 `action-controller.js`、`action-view.js`；
- 扩展 `action-state.js`、`life-flow.css`；
- 最小修改 `index.html`、`main.js` 加锚点/初始化；
- 新增 action tests/harness scenario。

不做：修改 chat response 契约、生产自动触发、用户 payload 编辑器、新 modal。

Gemini 上下文：Design 04 Action 全章、B1/B2 当前代码、conversation/main/index。

审计：五类 allowlist；ID 映射失败拒绝；preview/confirm snapshot 一致；confirming 不能婉拒；abort 不宣称未执行；双击单请求；draft diary 成功进入已持久化编辑器。

完成：所有 Action 状态截图/断言通过，S2 chat 行为不变。

## 15. 批次 B9：集成与视觉验收

目标：只修复集成、视觉、响应式、安全和回归问题，不新增功能。

允许：实际失败涉及的 S3 CSS/JS、acceptance harness/README、架构/tracker 文档。

流程：

1. 运行全部 Node tests；
2. 运行 S1 fixture、S2 API browser 回归；
3. 运行 S3 desktop/mobile/keyboard/reduced-motion harness；
4. 保存最低充分截图集；
5. 把高价值截图按组发给 Gemini 多模态终审；
6. 只修阻塞/高价值建议，再全量回归。

最低截图集建议 14 张：

- Today desktop populated、mobile、error；
- Task desktop、mobile keyboard/error；Routine checked；
- Activity active、paused reduced-motion；
- Diary generated draft、mobile editor/remove；
- Reminder snooze、Calendar all-day/invalid；
- Action preview_ready/confirming/error（可拼为同分辨率审查组，但原图分别保留）。

非截图断言覆盖请求数量/路径/body、无 ID/敏感字段、焦点返回、44×44、草稿恢复、stale response 和无 API fixture。

## 16. 每批 Gemini 无历史提示骨架

每次都必须包含：

```text
角色：Luminous Vanilla 前端实现工程师。
当前批次：Bx，且只完成列出的目标。
技术：HTML/CSS/ES modules，零构建、无第三方库。
现状：S1 fixture 与 S2 API 已交付，必须保持回归。
空间：唯一 #today-overlay；Action 只在聊天前景内联。
安全：raw response 不进 View/State；opaque key 不渲染/日志/data-*。
并发：非乐观；token + abort + stale guard + exact draft restore。
接口差异：重复与本批相关的真实后端路径、字段和语义。
允许文件：逐项列出；清单外禁止修改。
附件：当前版本相关代码 + 正式设计章节 + 上批测试结果。
输出：先文件 manifest；新文件给完整内容；现有文件给最小 unified diff；不得省略、不得使用“...”占位。
验收：列出本批 Node 与 browser 断言。
```

若输出接近长度上限，应主动停在文件边界并列出未输出文件；不得截断半个文件。

## 17. 测试划分

Node：

- `s3-time.test.mjs`：时间、全天、DST、range；
- `s3-operation.test.mjs`：single-flight、token、stale；
- `s3-today.test.mjs`：分类、排序、折叠；
- `s3-adapters.test.mjs`：全部 VM allowlist、unknown、wrapper；
- `s3-api-paths.test.mjs`：method/path/body/mismatch；
- `s3-resource-state.test.mjs`：Task/Routine/Activity/Diary/Reminder/Calendar；
- `s3-action-state.test.mjs`：五类摘要、mapping、snapshot、confirm。

fixture scenario 名：

- `today_five_clusters_max_four`、`today_partial_error`；
- `routine_checkins_actual_path`；
- `activity_no_delete_terminal_unknown`；
- `diary_entry_wrapper_persisted_draft`；
- `reminder_snooze_exact_due_at`；
- `calendar_no_detail_no_description`；
- `action_hidden_key_snapshot`、`action_missing_lookup_blocked`；
- `stale_response_after_subview_close`、`write_error_exact_draft_restore`。

## 18. 失败处理

- Gemini 截断：保留 trace，只请求从完整文件边界继续；不得拼接半截语法结构。
- 语法/导入小错：Codex 可做无设计判断的最小修正并测试；逻辑错把精确失败与相关文件交给 Gemini 局部修订。
- API 幻觉：拒绝对应文件，附真实 HTTP/domain 源码与契约差异，只重做 adapter/service 层。
- CSS 退化：保留截图，要求基于原图做局部修订；不得用破坏性 git checkout 覆盖用户工作树。
- S1/S2 回归：本批不完成；先定位最小耦合点，修复后全量重跑。
- Gemini API 不稳定：记录器自动主/备轮换；HTTP 200 但截断/乱码视为失败；保存每次 request/response/manifest。
- 后端不稳定：用 fixture 验 UI 状态机，同时用受控 Playwright route 验 API contract；不因 500 改写视觉或伪造成功。

## 19. S3 Definition of Done

- 9 个批次各自测试与审计完成；
- 所有 S1/S2/S3 Node tests 全绿；
- S1 fixture 与 S2 browser 回归全绿；
- S3 desktop/mobile/error/pending/keyboard/reduced-motion 通过；
- 截图和 README 位于 `docs/front_design/acceptance/life-flow-s3/`；
- DOM、AppState、console、错误文案无原始响应和后端 ID；
- 所有写入真实成功后才落定，失败无草稿丢失或永久 disabled；
- Gemini 多模态终审的阻塞项归零；
- 无新增页面、路由、modal、框架、构建链或运行时依赖；
- 回写 `frontend_architecture_v1.md`、`S2_S5_IMPLEMENTATION_TRACKER.md`、acceptance README，并新增 S3 retrospective/playbook。
