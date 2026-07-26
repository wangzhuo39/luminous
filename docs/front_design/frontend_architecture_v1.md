# Luminous 前端架构设计 v1

> 状态：持续维护（Living Document）
> 首次整理：2026-07-25
> 适用目录：`apps/companion-web/companion-ui/`

本文档记录 Luminous（栖光）当前前端工程架构。它描述代码边界、数据流、状态管理、接口适配、安全约束与交付顺序，不规定最终视觉构图。具体页面设计和实现候选由 Gemini 完成，Codex 负责提供上下文、集成、验证，并在发现问题或更优方案时更新本文档。

S1 的实际设计、实现、失败恢复和验收流程记录在 [S1 全流程复盘与后续阶段执行手册](S1_EXECUTION_RETROSPECTIVE_AND_STAGE_PLAYBOOK.md)。后续阶段除遵循本文档的工程边界外，也应复用其中的分轮设计、分批实现、主备重试和分级验收方法。

接口事实以 `frontend_api_contract_v1.md` 为准；产品体验和视觉约束以 `FRONTEND_AGENT_HANDOFF.md`、`frontend_design_guidelines.md` 为准。若文档之间发生冲突，先停止扩展实现，修正文档后再继续联调。

## 1. 架构目标

前端首先承载“有人安静地在场”的陪伴体验，其次才承载具体操作。工程架构需要同时满足：

- 主场景、对话、Today、来信、记忆和隐私可以独立演进；
- 静态 fixture 与真实后端使用同一套展示模型；
- 接口字段变化只影响 adapter，不迫使视觉组件重写；
- 内部推理、审计和调试字段不会因组件误用而泄露；
- 桌面与 `390x844` 手机均可完整使用；
- 后续可以逐步加入 PWA、系统通知、语音或其他壳层，而不破坏现有 runtime；
- 当前原型保持低工具链成本，复杂度真正增长后再决定是否引入框架和构建系统。

## 2. 当前技术约束

- Python HTTP 服务同时提供 `/api/*` 与静态文件。
- 静态服务器按真实文件路径读取资源，没有 SPA History API fallback。
- 当前没有 Node.js 包、前端构建系统或组件框架。
- 默认采用原生 HTML、CSS、JavaScript 与 ES Modules。
- 请求使用同源相对路径，不写死 host 或 port。
- 当前 S1 是纯静态体验原型，禁止调用 `/api/*`；后续联通通过替换 adapter 数据源完成。
- 页面暂时使用单文档和空间覆盖层，不依赖服务端路由。若未来需要 URL 级路由，必须先补充静态 fallback 或部署路由规则。

## 3. 总体分层

```text
HTML 语义骨架
  ↓
Scene / Feature Views
  ↓
App State + Feature Controllers
  ↓
稳定的 Frontend ViewModels
  ↓
Fixture Adapter（静态阶段） / API Adapter（联通阶段）
  ↓
API Client
  ↓
Luminous HTTP API
```

各层职责：

| 层 | 职责 | 禁止事项 |
| --- | --- | --- |
| HTML | 语义结构、可访问性基线、无脚本时的最低内容 | 内联业务数据和大量事件逻辑 |
| View | 渲染展示模型、表达局部交互状态 | 直接读取 HTTP 原始字段 |
| Controller | 响应用户动作、调用 adapter、提交状态变更 | 操纵不属于本 feature 的内部 DOM |
| App State | 保存当前空间、稳定数据、pending/error/draft | 保存后端整包响应或内部审计数据 |
| Adapter | 白名单转换、字段归一化、默认值、兼容契约差异 | 将未知字段透传给视图 |
| API Client | JSON 请求、超时、取消、错误归一化 | 承担产品展示逻辑 |
| Fixture | 为静态原型提供与 ViewModel 一致的数据 | 模仿网络成功或混入 `fetch` |

## 4. 建议目录结构

当前目标结构如下。Gemini 可以在不破坏分层原则的前提下调整文件粒度；任何较大调整应同步更新本文档。

```text
apps/companion-web/companion-ui/
├── index.html
├── manifest.webmanifest
├── service-worker.js
├── assets/
│   ├── luminous-icon.svg
│   ├── luminous-icon-192.png
│   └── luminous-icon-512.png
├── styles/
│   ├── tokens.css
│   ├── base.css
│   ├── scene.css
│   ├── overlays.css
│   ├── responsive.css
│   ├── motion.css
│   ├── life-flow.css
│   ├── crystal-solarium.css
│   ├── silent-spaces.css
│   └── productization.css
└── js/
    ├── main.js
    ├── app-state.js
    ├── view-models.js
    ├── scene-parallax.js
    ├── scene-environment.js
    ├── fixtures/
    │   └── default-scene.js
    ├── adapters/
    │   ├── fixture-adapter.js
    │   └── api-adapter.js
    ├── services/
    │   └── api-client.js
    ├── shared/
    │   ├── dom.js
    │   ├── errors.js
    │   └── time.js
    └── features/
        ├── life-flow/
        │   ├── life-flow-controller.js
        │   ├── life-flow-state.js
        │   ├── today-view.js
        │   ├── task-view.js
        │   ├── routine-view.js
        │   └── activity-view.js
        ├── silent-spaces/
        └── productization/
            ├── draft-recovery.js
            ├── pwa-controller.js
            └── space-router.js
```

原型规模较小时可以合并文件，但必须继续保持 fixture、adapter、状态和渲染边界。不要为了看起来“模块化”而产生只有几行代码的大量文件。

## 5. 功能边界

### 5.1 Scene

负责人物、环境、presence 和当前空间状态。Scene 只接收安全、克制的展示字段，不显示关系数值或风险诊断。

```text
SceneViewModel
  presence: { caption, thought, activity, heartRate }
  relationshipTone: { mood, energy, supportNeed, riskLevel }
```

这些状态只用于环境光、距离、静默程度、动效节奏和文案语气。

### 5.2 Conversation

负责成功消息、当前草稿、发送状态、失败恢复和最新回应。历史只包含此前成功的用户消息与助手最终回答。

```text
ConversationViewModel
  messages: [{ id, role: 'user' | 'assistant', text, sentAt }]
  draft
  sending
  error
```

发送失败时恢复草稿，不保留伪成功消息。当前后端没有用户安全的历史对话读取接口，因此刷新只恢复符合 TTL 的未发送 session draft，不恢复已发送历史。

### 5.3 Today

负责“照看今天”，而不是复刻任务后台。

```text
TodayViewModel
  date
  calendarEvents
  overdueTasks
  dueTasks
  openTasks
  routines
  activeActivities
  completedTasks
```

任务、提醒、日程、习惯、活动和日记的写操作属于 Today 的次级流程，不进入默认首屏。

#### 5.3.1 Activity（B5 已实现）

Activity 继续使用同一个 Today dialog，View 只接收 `key/kind/title/status/startedAt/endedAt/summary` 白名单模型。`activity-view.js` 渲染列表、创建与时间晶体详情；共享 Controller 负责 list/create/transition 的 operation gate、Abort 与 stale response；AppState 在请求前再次校验 planned/active/paused 的合法转换，terminal/unknown 一律只读。

主场景的 `data-activity-presence` 只保存 `active | paused | none` 材料派生：Today 首次响应只能证明 active，paused 必须来自明确加载的 Activity 集合或本次成功 pause。该视觉标记不含 key，也不覆盖 offline/error 等环境优先级。

### 5.4 Outbox

负责主动来信、阅读状态、回执和用户反馈。入口必须低打扰，不使用强制弹窗或制造焦虑的红点。

```text
ArrivalViewModel
  items: [{ id, title, body, arrivedAt, status }]
```

当前没有推送、SSE 或 WebSocket 契约；首次联通采用按空间打开时刷新。是否加入低频轮询应在明确功耗和打扰边界后决定。

### 5.5 Memory / Privacy

负责用户可理解的记忆内容、查询、修订、遗忘和隐私说明。

```text
MemoryViewModel
  items: [{ id, content, summary, occurredAt, confidence }]
```

普通产品界面不显示原始证据、threads、links、内部关联图、trace 或 prompt。S4 已确认这些接口属于内部能力。遗忘操作必须先确认，成功后再从本地视图移除。

### 5.6 Settings / DND

负责通知开关、每日上限、静默时间、允许的通知类型与 DND 状态。它是边界空间，不是设置后台。主动联系必须服从这些设置。

## 6. 应用状态

推荐保持一个小型集中状态容器，不在当前阶段引入第三方状态库。

```text
AppState
  phase: 'booting' | 'ready' | 'offline' | 'fatal'
  activeSpace: null | 'today' | 'outbox' | 'memory' | 'privacy'
  scene
  conversation
  today
  outbox
  memory
  preferences
  pending: Record<operationKey, boolean>
  errors: Record<operationKey, AppError | null>
```

状态更新遵循：

1. Controller 发起用户意图；
2. 进入局部 pending，但不提前确认业务成功；
3. adapter 返回规范化 ViewModel；
4. 成功后原子更新相关 feature；
5. 失败时保留草稿和既有稳定数据，仅更新局部 error；
6. View 根据状态重新渲染相关区域，不进行整页重建。

## 7. Adapter 设计

Fixture adapter 与 API adapter 应暴露相同的面向产品接口，例如：

```js
export const companionData = {
  loadScene,
  sendMessage,
  loadToday,
  loadArrivals,
  loadMemories,
  updateMemory,
  forgetMemory,
  loadPreferences,
  updatePreferences,
  previewAction,
  confirmAction,
};
```

### 7.1 白名单转换

Adapter 必须逐字段构造展示模型，不允许：

```js
return { ...response };
```

正常界面只允许使用：

- 对话最终回答 `reply`；
- 安全 `presence`；
- 持久状态 `response.state` 中被允许的氛围字段；
- 用户可见业务资源。

必须丢弃并禁止持久化：

- `system_thinking`、`role_thinking`、`role_action`、`analysis`；
- prompt、ledger、trace ID、jobs、worker 和 export；
- memory evidence、threads、links 等内部结构。

### 7.2 命名与默认值

- Adapter 将后端 `snake_case` 转换为前端统一的 `camelCase`。
- View 不判断多个后端别名；兼容逻辑集中在 adapter。
- 空时间从空字符串规范化为 `null`，格式化集中在 `shared/time.js`。
- 不认识的枚举映射到安全的 `unknown`，不得导致整个场景崩溃。
- 列表接口统一读取 `items`；记忆查询等特殊响应在 adapter 内转换。

## 8. API Client 与异步策略

API client 统一负责：

- 同源相对路径；
- JSON 请求头和响应解析；
- HTTP 状态到 `AppError` 的转换；
- 超时与 `AbortController`；
- 组件销毁或请求被替代时取消旧请求；
- 对 `204`、空正文和非法 JSON 的安全处理；
- 不在日志中输出敏感响应正文。

建议错误类型：

```text
AppError
  kind: 'offline' | 'timeout' | 'validation' | 'not-found'
      | 'model-unavailable' | 'server' | 'cancelled' | 'unknown'
  status
  message
  retryable
```

启动时只读取 `/api/state`。Today、来信和记忆在对应空间首次打开时懒加载，并可保留当前会话缓存。网络恢复后只刷新当前可见且已加载的数据，不一次性请求全部资源。

聊天后端当前不是流式接口，最长等待可能明显高于普通请求。发送态需要保留草稿副本、提供克制的等待反馈，并避免重复发送。

## 9. 写操作和现实行动

- 所有写操作以 HTTP 成功和有效 JSON 响应为准。
- 可以显示 pending，不显示伪成功。
- 失败时保留输入、编辑内容和原有稳定数据。
- 删除、遗忘等不可逆操作先确认，成功后才从视图移除。
- 影响现实生活的陪伴建议必须执行：

```text
POST /api/actions/preview
  ↓
展示影响、内容、确认与取消入口
  ↓ 用户明确确认
POST /api/actions/confirm
```

- 不允许视觉组件绕过 preview/confirm 直接调用对应 CRUD。

## 10. HTML、CSS 与交互约束

### 10.1 HTML

- 使用 `main`、`section`、`form`、`dialog` 等语义结构；
- 使用真实 `button`、`input`、`textarea`，不使用可点击 `div`；
- 对动态回复和局部错误谨慎设置 `aria-live`，避免重复朗读；
- 表单具有可见或可访问名称；
- 不添加冗余 ARIA role。

### 10.2 CSS

- `tokens.css` 保存颜色、文字、间距、层级、动效时长和安全区变量；
- `crystal-solarium.css` 作为末级全局艺术指导层，统一拥有光窗/晶格/折射/凝露与共享材质；feature 样式继续拥有布局和行为，不得复制全局光学配方；
- 场景层级必须有可解释的 z-index 体系；
- 桌面和手机分别定义人物、回应、输入和入口的安全区；
- 使用 `env(safe-area-inset-*)`；
- 不禁止页面缩放；
- 长内容允许滚动，固定场景不得截断必要信息；
- 支持 `prefers-reduced-motion`，并提供低性能降级。
- `scene-parallax.js` 只能写装饰层 CSS 变量，不得读取 AppState、业务 key 或调用 API；页面隐藏、粗指针和 reduced-motion 时必须回正并停止。
- `scene-environment.js` 只接收有限 tone、时段、活动存在态、匿名 count/boolean 和 activeSpace，派生 CSS 变量与固定 seed 装饰；不得读取 raw response、正文、opaque key 或持久化数据。S4 只传 `memoryCount/outboxUnread/dnd` 聚合值；未知时仍回退 0/false，不伪造事实。

### 10.3 输入与移动键盘

- 中文 IME composition 期间 Enter 不发送；
- Enter 发送、Shift+Enter 换行的行为应与控件类型一致；
- 使用 `visualViewport` 时必须有无该 API 的回退；
- 键盘出现后输入与最新回应同时可见；
- 焦点不能因局部重渲染意外丢失。

## 11. 安全与隐私

前端的“不渲染”不是完整安全边界。当前 `/api/chat` 和 `/api/state` 仍可能在网络响应中包含内部数据，因此：

1. API adapter 必须执行严格白名单转换；
2. App State、localStorage、sessionStorage、CacheStorage、日志和错误上报不得保存原始响应；sessionStorage 的唯一例外是版本化未发送草稿；
3. 正常页面不能提供 ledger、trace、jobs、export、worker 或 proactive tick 入口；
4. 后续应评估由后端提供真正的 user-safe DTO，避免敏感字段到达浏览器；
5. 在认证和多用户隔离未设计前，不将当前服务直接暴露为公共互联网产品。

## 12. 验证策略

每个阶段至少完成：

- HTML、CSS、JavaScript 静态语法检查；
- fixture adapter 与 API adapter 的 ViewModel 契约检查；
- adapter 安全字段白名单测试；
- 写操作失败后的草稿恢复测试；
- 桌面真实浏览器截图；
- `390x844` 截图；
- 键盘导航和可见焦点检查；
- `prefers-reduced-motion` 检查；
- 移动键盘、长回复、空态、慢请求、离线和重试检查；
- 截图写入 `docs/front_design/acceptance/<阶段名>/`，不写入产品静态资源目录。

前端测试从 S2 起放在 `tests/frontend/`。当前 API client 与安全 adapter 边界测试运行命令为：

```bash
node --test \
  tests/frontend/s2-api-boundary.test.mjs \
  tests/frontend/s2-app-state.test.mjs \
  tests/frontend/s2-core-runtime.test.mjs \
  tests/frontend/s3-time.test.mjs \
  tests/frontend/s3-validation.test.mjs \
  tests/frontend/s3-operation.test.mjs \
  tests/frontend/s3-state-machines.test.mjs \
  tests/frontend/s3-today-runtime.test.mjs
```

历史 Playwright 验收工具保存在 `/home/wz/gemini-api-traces/browser-tools/`。从 B3 起，批次专属、可复现的浏览器断言可以作为 `tests/frontend/*-browser-acceptance.mjs` 随仓库维护；Playwright 仍只属于本地验收环境，不进入产品运行时、不要求构建步骤。README 中的历史测试数量不能替代当前验证结果；每个阶段都应在 acceptance README 中记录实际运行的命令和结果。

## 13. 分阶段实施

### S1：静态体验原型

- 由 fixture 驱动主场景、默认对话、Today、来信、记忆/隐私入口；
- 不调用 API，不实现 CRUD；
- 建立展示模型、状态和渲染边界；
- 完成桌面与手机截图验收。

### S2：核心陪伴联通

- 接入 `/api/state` 和 `/api/chat`；
- 实现安全 adapter、发送失败恢复、离线和慢模型状态；
- 验证后端不会通过前端状态或日志泄露内部字段。
- 使用 `body[data-tone]`、`body[data-app-status]` 与位于人物/前景之间的环境伪元素表达色温、雾化和暗化，不增加技术状态面板；
- API 为默认运行模式，`?mode=fixture` 保留 S1 无后端回归路径；
- 详细设计与验收分别见 `s2_environmental_state_design_v1.md` 和 `acceptance/core-companion-s2/README.md`。

### S3：生活流联通

- 接入 Today、任务、习惯、活动、日记、提醒和日程；
- 实现局部 pending/error/retry；
- 实现 preview/confirm 两阶段现实行动。
- 正式设计基线为 `s3_01_today_space_design_v1.md` 至
  `s3_05_implementation_plan_v1.md`；旧稿中与其冲突的乐观写入、计时器、
  月历网格、粒子、toast 和轮询不再有效。
- S3 复杂度隔离在 `features/life-flow/`、`features/action-proposal/`、
  `shared/time.js`、`shared/validation.js` 与独立 adapter/service 中，禁止回填到
  `main.js` 或 `overlays.js` 的大分支。
- B1 已建立严格 ISO instant、本地 datetime/all-day round-trip、JSON-safe clone、
  single-flight gate 和纯资源状态表。
- B2 已建立 32 方法同构的 API/fixture DataSource、严格响应白名单、真实 HTTP
  path/method/body service 与五类 Action preview/confirm 安全映射；fixture 模式不导入
  API client、不会发起网络请求。
- B3 已用一个 dialog 接通 Today/Timeline：AppState 只保存有限展示字段，Controller
  负责首次打开懒加载、独立缓存/gate/Abort/offline/online，View 负责五类摘要、折叠与局部
  状态；`main.js` 在 API/fixture DataSource 间选择。打开时焦点进入弹层，关闭时返回入口。
  B3 里程碑为 120/120 Node 测试通过，浏览器 populated/mobile/Timeline/empty/error
  共 6 张截图见 `acceptance/today-timeline-s3-b3/`；当前全量数字见后续 B4 条目。
- B4 已把 Task/Step 与 Routine/Checkin 接入同一 Life Flow 状态边界，继续使用严格白名单、operation gate、AbortController、草稿恢复和 View 闭包 key；当前全量为 136/136。
- B5 已把 Activity 列表、创建、详情、精确转换与主场景事实派生接入相同边界；独立 `activity-view.js` 不读取 HTTP raw，不渲染 timer/progress/delete，当前全量为 140/140，浏览器 3 场景/8 张截图见 `acceptance/activities-s3-b5/`。
- B6 已把 Diary 列表、详情、手动创建、generated draft→PATCH、编辑与删除确认接入相同边界；4 场景/6 张截图见 `acceptance/diary-s3-b6/`。
- B7 已把 Reminder 与 Calendar 接入相同资源边界：`reminders` 使用光尘活跃/终态列表与明确 snooze/cancel 转换，`calendarEvents` 使用 `calendar-events` 列表视图和窗框刻度；两者由独立 View 翻译 DOM 事件，Controller 负责本地时间严格转换、IANA 时区、变化字段 PATCH 与 conservative delete，AppState 只保留安全 VM。3 场景/7 张截图见 `acceptance/reminder-calendar-s3-b7/`，当前全量 156/156。
- B8 已交付生产门控的 Action Proposal 组件：`action-state.js` 在网络前规范化五类 allowlist，`action-controller.js` 隔离 preview/confirm gate、Abort 与冻结 snapshot，`action-view.js` 只渲染安全 summaryLines；确认结果通过 `commitConfirmedActionResult` 原子写入安全资源。fixture 注入钩子不在 API 模式出现。3 场景/6 张截图见 `acceptance/action-light-tag-s3-b8/`，当前全量 162/162。
- B9 已关闭 S3：B3–B8 与 Crystal 的 7 套浏览器脚本在最终工作树全部重跑通过，新增生产 proposal 门控、S2 chat/Today 回归、320px 与门户恢复集成验证；最终 9 图审计 96/100、无 P0。S3 证据索引见 `acceptance/s3-final-integration-b9/`。
- 全局视觉基线已升级为 `crystal_solarium_v2_implementation_spec.md`：装饰 DOM 与业务 DOM 分离，视差和环境映射均为独立可销毁模块；当前全量 162/162，专项证据见 `acceptance/crystal-solarium-v2/`。

### S4：静默空间联通

- 已接入 Outbox 首开懒加载/会话缓存/错误重试、回执与低压力反馈；
- 已接入 Memory 主动查询、修订和内联确认的软忘却；threads/links/evidence 保持内部；
- 已接入通知偏好；DND 只读，因为当前后端没有写接口；
- `silent-spaces-api` → `silent-spaces-adapter` → `silent-spaces-controller/view` 形成独立边界，fixture 不触网；
- 全量 168/168，Chromium 4 场景/5 图，Gemini 四图审阅 88/100、无 P0；证据见 `acceptance/silent-spaces-s4-b1/`。

### S5：产品化能力

- 已保持 Vanilla/无构建；Manifest、192/512 图标和版本化静态 app shell Service Worker 已实现；
- `/api/*` 永远 network-only，离线不缓存历史、不排队写入、不伪装发送；
- 安装只由 `beforeinstallprompt` 资格加用户手势驱动；waiting update 只由用户确认切换；
- `features/productization/` 隔离 PWA lifecycle、session draft 和 `?space=` History 同步；
- sessionStorage 只允许 v1 未发送草稿（8000 字、24h TTL、成功发送清除）；
- URL 只表达 today/outbox/memory/privacy 空间，不表达 opaque resource；
- 系统通知、Push/VAPID、Badging、Background Sync、历史恢复和跨设备同步延期；
- S5 设计、架构与验收见 `s5_01_productization_scope_and_architecture_v1.md` 至 `s5_03_implementation_plan_v1.md`。

## 14. 已知契约问题

以下问题不阻塞 S1，但在对应功能联调前必须确认并更新接口契约或后端：

1. 习惯打卡文档写作 `/api/routines/{routine_id}/checkin`，后端实际使用 `/checkins`。
2. 日记创建文档描述返回 `entry`，后端当前返回 `diary_entry`。
3. reminder snooze 文档提到“延后参数”，后端 HTTP 层当前只读取明确的 `due_at`。
4. `/api/chat` 返回的内部字段超出普通前端所需范围，需要前端白名单和后端安全 DTO 评估。
5. `/api/state` 返回完整 snapshot，前端只能读取其中的 `state`。
6. 缺少用户安全的历史对话读取接口，刷新恢复策略未定。
7. outbox 没有推送或流式更新契约。
8. 时区、分页、删除响应和部分资源完整 schema 尚未固定。

## 15. 架构决策与变更规则

修改本架构时遵循：

- 先记录要解决的问题，再修改目录或依赖；
- 优先选择能减少跨层耦合、提高安全性和可验证性的方案；
- 视觉偏好不应直接触发工程架构迁移；
- 引入框架、构建工具、路由、持久缓存或全局状态库前，必须写明收益、成本和迁移范围；
- Gemini 给出的结构是实现候选，必须经过本地代码审查、截图和验证；
- 修改完成后同步更新“当前决策”和“待决问题”。

### 当前决策

| 决策 | 当前选择 | 重新评估条件 |
| --- | --- | --- |
| UI 技术 | 原生 HTML/CSS/ES Modules | feature 数量和交互复杂度导致手工状态同步明显失控 |
| 页面模型 | 单文档空间覆盖层 + `?space=` History 同步 | 产品需要独立文档、资源级分享或服务端 History fallback |
| 状态管理 | 小型集中状态容器 | 出现复杂跨页面缓存、并发写入或状态回放需求 |
| 数据来源 | fixture/API 双 adapter | 保持长期决策 |
| 更新策略 | 局部保守更新 | 后端增加明确的版本、幂等和冲突处理协议 |
| 敏感数据 | adapter 严格白名单 | 后端 user-safe DTO 上线后仍保留最小白名单 |
| Presence 视觉 | 安全有限 tone + app status 驱动环境层 | 后端提供新的 user-safe presentation DTO |
| 浏览器验收 | 批次 Playwright 脚本位于 `tests/frontend/`，证据写入 acceptance；工具不进入运行时 | 需要 CI 并行、报告与长期多人维护时再引入正式 runner 配置 |
| S3 异步操作 | Controller 私有 AbortController + 纯 operation gate | 服务端提供幂等键/版本冲突协议后扩展 |
| 时间提交 | 本地控件经 Date round-trip 后发送 UTC `Z`，并附安全 IANA timezone | 后端发布统一的用户时区 DTO/Temporal 方案 |
| S3 模块边界 | Life-flow 与 Action Proposal 独立 feature；纯状态与 DOM/副作用分离 | 原生模块循环依赖或同步成本经测量失控 |
| PWA 缓存 | 显式版本化静态 shell；API network-only | 后端提供经审计的离线 DTO、冲突和幂等协议 |
| 本地持久化 | 仅 sessionStorage 未发送草稿 | 新类型必须先完成字段、TTL、删除和隐私审计 |
| URL 路由 | 轻量原生 History，仅四个空间 | 出现独立页面、资源分享或复杂嵌套路由 |

### 待决问题

- 用户安全的对话历史读取方式（未发送草稿恢复已完成）；
- outbox 的刷新、推送和通知深链方式；
- 跨设备“用户偏好时区”尚无服务端契约；当前仅使用浏览器本地时区并发送 UTC instant；
- 除当前未发送草稿外，是否允许任何新的本地持久化类型；
- 身份认证、多用户隔离和公开部署边界；
- 完整 API schema、错误码和并发冲突协议；
- 何时将现有项目外浏览器验收迁入 CI，以及是否同时引入构建链。
