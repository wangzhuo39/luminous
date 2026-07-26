# Luminous 前端开发交接文档

> 更新时间：2026-07-26
> 当前阶段：S1–S5 已全部关闭，前端总体架构已按当前契约交付
> 用途：新对话或新工程 agent 读完本文即可从当前工作树继续，不应从 S1 重新开始

## 1. 长期目标与角色分工

Luminous（栖光）是情感陪伴项目。前端首先表达“有人安静地在场”，生活流操作其次。它不是生产力 Dashboard、CRM、普通聊天列表或任务打卡工具。

持续目标是依据设计理念、架构和 S1 经验逐步完成 S2–S5：

1. 每个复杂阶段先让 Gemini 形成一份或多份详细设计；
2. 依据设计和当前代码拆成可验证 implementation batches；
3. Gemini 负责视觉设计、美化方案和多模态视觉复核；
4. Codex 负责 JS、状态机、接口编排、无状态调用上下文、集成、契约审查、测试、浏览器截图和返工；
5. 设计或实现发现问题时，随时更新 living architecture；
6. 持续执行到 S2–S5 完整交付，不把局部测试通过误报为全目标完成。

有关美观、构图、材质、组件视觉层级的判断交给 Gemini。Codex 不应凭空把页面改成通用卡片墙或后台界面。

## 2. 必读资料顺序

新对话先读：

1. `docs/front_design/FRONTEND_AGENT_HANDOFF.md`（本文）
2. `docs/front_design/S2_S5_IMPLEMENTATION_TRACKER.md`
3. `docs/front_design/luminous_frontend_design_spec_v1.md`
4. `docs/front_design/frontend_architecture_v1.md`
5. `docs/front_design/S1_EXECUTION_RETROSPECTIVE_AND_STAGE_PLAYBOOK.md`
6. 当前阶段的设计与实施文档
7. `docs/front_design/frontend_api_contract_v1.md`
8. `docs/front_design/GEMINI_API_OUTPUT_BOUNDARY_AND_BATCHING.md`
9. `docs/front_design/crystal_solarium_v2_implementation_spec.md`

S3 当前设计基线：

- `s3_01_today_space_design_v1.md`
- `s3_02_tasks_routines_design_v1.md`
- `s3_03_activities_diary_design_v1.md`
- `s3_04_scheduling_action_confirmation_design_v1.md`
- `s3_05_implementation_plan_v1.md`

旧稿位于 `docs/front_design/archive/`，只用于追溯，不作为实现权威。

## 3. 产品结构决策

当前前端采用原生 HTML/CSS/ES Modules，零构建、零第三方运行时依赖。

页面模型是**单主场景 + 空间覆盖层**：

```text
主场景
├── 陪伴者与环境
├── 对话与输入水面
├── Today 入口
│   └── 唯一 #today-overlay dialog
│       ├── 今日摘要
│       ├── Timeline
│       ├── Task / Step
│       ├── Routine / Check-in
│       ├── Activity
│       ├── Diary
│       ├── Reminder
│       └── Calendar
├── 来信
├── 记忆
└── 隐私

聊天前景
└── Action Preview / Confirm 光签
```

S3 会新增许多原生 JS View/Controller 组件，但**不新增顶层页面、URL 路由或第二个 Today dialog**。这是为了保持主场景和陪伴者始终可感知，不是遗漏页面。

重新评估多页面/框架的条件已记录在 `frontend_architecture_v1.md`，当前未满足。

## 4. Gemini 无状态调用规则

Gemini 是 OpenAI-compatible API 调用，不是 code agent：

- 看不到本地文件；
- 没有上一次调用历史；
- 不能直接修改仓库；
- prompt 中必须包含实际需求、接口、hooks 和相关源码内容；
- 不能只写“请查看 `/path/file.js`”。

统一调用器：

```text
/home/wz/gemini-api-traces/run_gemini_logged.py
```

prompt 和所有 request/response/manifest 保存在项目外：

```text
/home/wz/gemini-api-traces/
```

环境配置从 `/home/wz/luminous/.env` 读取：

- 主端点：`GOOGLE_GEMINI_BASE_URL`、`GEMINI_API_KEY`、`GEMINI_MODEL`
- 备用端点：`GOOGLE_GEMINI_BACKUP_BASE_URL`、`GEMINI_API_BACKUP_KEY`、`GEMINI_BACKUP_MODEL`

不要打印或写入这些值。

每次实现调用必须有唯一 suffix：

```bash
--expect-suffix LUMINOUS_COMPLETE_<TASK>
```

HTTP 200 不代表完整。只有命中 suffix、代码结构闭合、集成审查和测试通过才可接纳。

当前经验输出边界：

- 稳定目标约 4.5–7 KB、120–200 行代码；
- 7–10 KB 风险明显上升；
- 超过 10 KB 或两个中型文件应按自然领域拆分；
- 偶发 15–24 KB 完整响应不可作为计划依据；
- 独立且无文件冲突的 2–3 个任务可并发；有上下文依赖的调用必须顺序执行。

详见 `GEMINI_API_OUTPUT_BOUNDARY_AND_BATCHING.md`。

失败处理：

- 网络/TLS/空 stdout：同一 prompt 主备切换重试；
- 非空 stdout 但无 suffix：视为截断，按文件或领域缩小输出；
- 整次最终失败且无可用交付：删除整个 run 目录；
- 成功 run 内部的失败 attempts 保留；
- 完整但逻辑有错：保留成功 trace，Codex 做小型无设计判断修正，重大视觉/业务问题交 Gemini 局部重做。

## 5. 已完成阶段

### S1：静态主场景垂直切片——完成

已交付：

- 人物主体、远中前景、输入水面、默认对话；
- Today、来信、记忆、隐私四个安静入口与 dialog；
- fixture 驱动、本地对话切换；
- 桌面与 390×844 响应式；
- reduced-motion、键盘、基础可访问性；
- 项目外浏览器 harness 与项目内截图证据。

验收：

```text
docs/front_design/acceptance/static-prototype-s1/
```

流程复盘：

```text
docs/front_design/S1_EXECUTION_RETROSPECTIVE_AND_STAGE_PLAYBOOK.md
```

### S2：核心陪伴联通——完成

已交付：

- 默认 API 模式，`?mode=fixture` 保留 S1；
- `GET /api/state` 和 `POST /api/chat`；
- raw response 严格映射为 scene/conversation 安全 ViewModel；
- 非乐观发送、重复提交保护、Abort/timeout/offline/503/error；
- 失败时字节级恢复草稿；
- `body[data-tone]` / app status 环境表达；
- 桌面、移动、键盘、慢响应、错误、离线和 reduced-motion 验收；
- Gemini 截图多模态终审。

验收：

```text
docs/front_design/acceptance/core-companion-s2/
```

### S3 设计——完成

Design 01–05 均已完成并经过 Codex 契约审查，实施按 B1–B9 推进。

### S3 B1：共享纯逻辑——完成

关键文件：

```text
apps/companion-web/companion-ui/js/shared/time.js
apps/companion-web/companion-ui/js/shared/validation.js
apps/companion-web/companion-ui/js/shared/operation.js
apps/companion-web/companion-ui/js/features/life-flow/life-flow-state.js
apps/companion-web/companion-ui/js/features/action-proposal/action-state.js
```

已覆盖严格 ISO、本地 datetime/all-day、DST、JSON-safe clone、single-flight gate、Today 五类算法和资源/action 状态机。

### S3 B2：安全 API/fixture 双数据源——完成

关键文件：

```text
apps/companion-web/companion-ui/js/adapters/life-flow-adapter.js
apps/companion-web/companion-ui/js/adapters/scheduling-action-adapter.js
apps/companion-web/companion-ui/js/services/life-flow-api.js
apps/companion-web/companion-ui/js/life-flow-datasource.js
apps/companion-web/companion-ui/js/adapters/life-flow-fixture-adapter.js
```

API 与 fixture 均提供 32 个同名方法。fixture 不导入 API client、不会 fetch。raw response 只在 adapter 边界存在。

已固化真实后端差异：

- Routine check-in 实际为 `/api/routines/{id}/checkins`；
- Diary response 兼容 `diary_entry` 与 `entry`；
- Diary draft 已持久化；
- Reminder snooze 必须显式 `due_at`；
- Reminder cancel 使用 POST `/cancel`；
- Activity 无 DELETE；
- Calendar 无单项 GET，也没有前端可用 description；
- Action confirm body 只发送 `{action,payload,confirmed:true}`。

B2 完成时全量 Node 回归为 114/114。

## 6. 最近完成：S3 B3 Today 壳、摘要与 Timeline

### 6.1 已交付能力

- `index.html` 把 S1 Today 静态列表升级为同一 dialog 内的 Today/Timeline 双面板，并保留无 JS fallback；
- `main.js` 已收集 hooks，在 API/fixture DataSource 间选择，初始化 View/Controller、参与全局 render，并在 pagehide 销毁；
- fixture seed 复用 S1 两条 Today 文案，映射为活动、日历和 Timeline，fixture 模式零 API 请求；
- `app-state.js` 的 `lifeFlow` slice 只保留 `key/kind/title/status/occurredAt` 与有限分类，raw/private/description/source ID 不落状态；
- `today-view.js` 实现五类摘要、每类前三条、Completed 折叠、loading/refreshing/empty/error/retry 与 Timeline；
- `life-flow-controller.js` 实现首次打开懒加载、ready cache、手动刷新、Timeline 显式加载、独立 gate/Abort/stale/offline/online；
- `life-flow.css` 实现桌面左上 420px 浮层、移动 85dvh bottom sheet、内部滚动、44px 控件与 reduced-motion；
- `overlays.js` 打开后可靠聚焦关闭按钮，关闭后焦点返回入口；
- Timeline 多模态复验中发现并消除了透明背景叠加形成的近黑“嵌套面板”。

主要文件：

```text
apps/companion-web/companion-ui/index.html
apps/companion-web/companion-ui/js/main.js
apps/companion-web/companion-ui/js/app-state.js
apps/companion-web/companion-ui/js/overlays.js
apps/companion-web/companion-ui/js/features/life-flow/today-view.js
apps/companion-web/companion-ui/js/features/life-flow/life-flow-controller.js
apps/companion-web/companion-ui/styles/life-flow.css
tests/frontend/s3-today-runtime.test.mjs
tests/frontend/s3-browser-acceptance.mjs
docs/front_design/acceptance/today-timeline-s3-b3/README.md
```

### 6.2 验收证据

- Node 全量回归：120/120；
- 浏览器：desktop 1440×1000、mobile 390×844、fixture 零 API、Timeline、empty、503 error；
- 6 张最终截图和机器可读结果位于 `acceptance/today-timeline-s3-b3/`；
- 焦点进入/返回、无横向溢出、reduced-motion、无内部错误正文泄漏均有自动断言；
- `node --check` 覆盖产品 JS 与前端测试，结果 `B3_SYNTAX_OK`。

### 6.3 B3 成功 Gemini traces

```text
/home/wz/gemini-api-traces/runs/20260725T045259.023526Z_luminous-s3-impl-b3a2-today-view-compact_5471a19c/
/home/wz/gemini-api-traces/runs/20260725T045259.038509Z_luminous-s3-impl-b3b2-controller-compact_160fcf5c/
/home/wz/gemini-api-traces/runs/20260725T045259.035756Z_luminous-s3-impl-b3c1-today-markup_f4d9c69f/
/home/wz/gemini-api-traces/runs/20260725T045554.306742Z_luminous-s3-impl-b3c2-today-css_5df29e0d/
/home/wz/gemini-api-traces/runs/20260725T050255.419888Z_luminous-s3-impl-b3d-app-state-extension_68aabade/
/home/wz/gemini-api-traces/runs/20260725T050949.279336Z_luminous-s3-b3-runtime-tests_11905735/
/home/wz/gemini-api-traces/runs/20260726T014330.983607Z_luminous-s3-b3-visual-audit_3b209ff0/
```

Runtime tests 调用主端点首试无输出，备用端点第 2 次成功；视觉审核主端点首试虽为 HTTP 200 但未满足结束标记，备用端点第 2 次成功。成功 run 均保留内部失败尝试。重复启动产生、从未发出 attempt 的无效 trace 已按用户授权删除。

### 6.4 B4 Task / Routine 完成状态

- Task：列表、详情、创建/编辑、状态变更、归档确认、Step 添加/切换；
- Routine：列表、详情、创建/编辑、当次会话 check-in、停用确认与 inactive 只读；
- 写失败恢复精确草稿，pending 阻止重复提交，离线中止并恢复；
- opaque key 只保存在 View/Controller 闭包，不进入 DOM；
- Today 条目可进入资源详情，写成功后回刷 Today；
- 全量 Node 回归 136/136；B4 浏览器 3 场景、6 张截图。

### 6.5 晶格温室视觉基线

用户指出 v1 仍只是冷色材质与人物图，不足以称为“晶格温室”，该判断成立。v2 现已增加：

- 内联 SVG 穹顶、收束肋线、体积光、前景凝露、透视水面与中景人物融合；
- 今日时间切片、记忆晶体、隐私拉片、来信信笺四个实体入口；
- Today/Memory/Outbox/Privacy 四种差异物态，不再同构为深色矩形 dialog；
- `scene-environment.js` 的晨昼昏夜、tone、activity、匿名晶体和未读光核安全映射；
- 弹层打开时视差归零，移动端沿折线光轨错落布局，reduced-motion 降级；
- 专项 3 场景、8 张截图；Gemini 初审 50/100 后修正 P0/P1，复审 86/100、无 P0。

权威说明见 `crystal_solarium_v2_implementation_spec.md` 与 `acceptance/crystal-solarium-v2/README.md`。S4 前 `memoryCount=0`、`dnd=false` 是安全 fallback；待安全 ViewModel 到位后只接聚合值。后续组件必须继承 v2，禁止回到黑色矩形 dialog、水平 Tab Bar 或卡片墙。

### 6.6 B5 Activity 完成状态

- Today 同一 dialog 内增加 Activity 列表、创建和“时间晶体”详情，没有新增页面/overlay；
- AppState 严格保存 ActivityVM 白名单，并在写入前校验 planned/active/paused 合法状态图；
- Controller 接通 `GET /api/activities?limit=100`、`POST /api/activities` 与五个 transition action，使用 gate/Abort/stale-response/草稿恢复；
- completed/cancelled/expired/unknown 只读；无 DELETE、archive、timer、progress 或伪时长；
- Today 初始只从 `active_activities` 推导 active，列表加载或本次 pause 成功后才推导 paused，且不覆盖 offline/error；
- `activity-view.js` 与 `crystal-solarium.css` 落下晶体簇、planned 缺口、active 冰蓝呼吸、paused 月雾和终态凝结；
- 桌面生命周期、API error/exact contract、390px keyboard/reduced-motion 共 3 场景、8 张截图；Gemini 多模态结论“通过”、无 P0/P1；
- 全量 Node 回归 140/140；B3、B4 与晶格温室专项浏览器回归同时通过。

权威实现契约与证据：

```text
docs/front_design/s3_07_b5_activity_implementation_contract_v1.md
docs/front_design/acceptance/activities-s3-b5/README.md
tests/frontend/s3-activity-b5.test.mjs
tests/frontend/s3-b5-browser-acceptance.mjs
```

Gemini traces：

```text
/home/wz/gemini-api-traces/runs/20260726T035707.345390Z_luminous-b5-activity-visual-v1_e3d71ff1/
/home/wz/gemini-api-traces/runs/20260726T041058.607468Z_luminous-b5-activity-audit-v1_fec88953/
```

视觉设计调用首试成功；多模态审核前两次失败，主端点第 3 次成功，成功 run 内保留失败 attempts。Gemini 的契约外 kind 与不可访问 pending CSS 未采用。

### 6.7 B6 Diary 完成状态

- 在同一个 Today dialog 内实现 Diary 列表、详情、手动创建、编辑和删除确认；
- generated draft 使用服务端返回 key 执行 PATCH 保存，不重复 POST；
- operation gate、Abort/stale response、防重复提交、失败输入恢复与删除成功后移出均已覆盖；
- 纸面/光影视觉延续晶格温室，没有新增页面或嵌套 dialog；
- fixture desktop、mobile long body、API generated PATCH/delete、API manual error 共 4 场景、6 张截图；
- 全量 Node 回归在晶格温室环境测试加入后为 151/151。

权威契约与证据：`s3_08_b6_diary_implementation_contract_v1.md`、`acceptance/diary-s3-b6/README.md`。

### 6.8 B7 Reminder / Calendar 完成状态

- 在同一个 Today dialog 内增加 Reminder“提醒光尘”和 Calendar“窗框刻度”，没有新增页面、路由或嵌套 dialog；
- Reminder 覆盖 mixed list、活跃/终态分区、创建、编辑、完成、精确 datetime snooze、取消确认与 cancelled 终态保留；
- Reminder cancel 固定 POST `/cancel`，snooze 只发送明确 `{due_at}`，编辑 PATCH 只发送实际变化字段；
- Calendar 覆盖定时/全天列表与表单、开始/结束校验、IANA timezone/UTC fallback、详情编辑与移出确认；
- Calendar 不调用单项 GET，不渲染 description，只有返回 `status=deleted` 后才从列表移除；
- 新增 `reminder-view.js`、`calendar-view.js`，继续遵循 View 不访问 raw HTTP、Controller 管 operation gate、AppState 只收安全 ViewModel；
- Chromium 桌面 Reminder、桌面 Calendar、390px keyboard/reduced-motion 共 3 场景、7 张截图；
- Gemini 终审总分 92、桌面 94、移动 89、隐喻 96，可交付且无 P0；4 条非阻塞 P1 修正后浏览器回归通过；
- 全量 Node 回归 156/156。

权威契约与证据：

```text
docs/front_design/s3_09_b7_reminder_calendar_implementation_contract_v1.md
docs/front_design/acceptance/reminder-calendar-s3-b7/README.md
tests/frontend/s3-reminder-calendar-b7.test.mjs
tests/frontend/s3-b7-browser-acceptance.mjs
```

Gemini traces：

```text
/home/wz/gemini-api-traces/runs/20260726T072536.024453Z_luminous-b7-reminder-calendar-visual-v1_1381e473/
/home/wz/gemini-api-traces/runs/20260726T074358.169906Z_luminous-b7-multimodal-audit-v1_8385810e/
```

### 6.9 B8 Action 光签完成状态

- 新增 `action-controller.js` 与 `action-view.js`，扩展 `action-state.js` 五类 action allowlist；
- proposal 在网络前归一化，未知字段剔除；complete_task/checkin_routine 缺失安全 VM 映射时不发 preview；
- preview/confirm 使用同一冻结 requestSnapshot；双击由 operation gate 拒绝，失败重试不重组 payload；
- confirming 同时禁用确认/婉拒；View 只消费 summaryLines，opaque ID 不进入 DOM/console；
- draft_diary 确认结果进入已持久化 DiaryEditor，后续保存仍走 PATCH；
- API 模式没有注入入口，fixture 只暴露 propose/status 测试钩子；
- Chromium preview/success/cancelled/missing mapping/draft editor/mobile reduced-motion 共 3 场景、6 图；
- Gemini 终审总分 96、桌面 97、移动 94、隐喻 98，可交付且无 P0；
- 全量 Node 162/162。

权威契约与证据：`s3_10_b8_action_light_tag_implementation_contract_v1.md`、`acceptance/action-light-tag-s3-b8/README.md`。

### 6.10 B9 与 S3 关闭状态

- B3、B4、B5、B6、B7、B8、Crystal 共 7 套 Chromium 脚本在最终工作树串行重跑，全部通过；
- 新增 B9 集成脚本验证 API/生产模式无 proposal 注入、S2 chat/Today 未回归、320×568 Action、门户恢复；
- 最终 Node 162/162；
- Gemini 9 图终审：总分 96、视觉一致性 98、陪伴感 95、桌面 96、移动 95；明确 S3 可正式关闭，无 P0；
- 44px Action 触控区已有自动化断言；长列表边缘折光在 S4 数据增长时继续复核。

最终证据：`acceptance/s3-final-integration-b9/README.md`。

### 6.11 S4 静默空间关闭状态

- Outbox 首次打开懒加载并保持会话缓存，不轮询；支持 read receipt、helpful/not_needed 反馈和 HTTP 失败显式重试；
- Memory 仅在主动查询后显现，ViewModel 只保留 key/content/kind/occurredAt；修订和软忘却均等待服务端成功，忘却使用原晶体内联确认；
- Privacy 接通通知总开关、每日上限和静默时段；初次加载失败不展示伪默认值，保存失败保留草稿；
- `dnd_until` 只读。当前没有 DND 写接口，未提供虚假按钮；threads/links/evidence、export、trace、score/reason/payload 等内部数据均被 adapter 隔离；
- Gemini 视觉蓝图经四图多模态审阅为 88/100、无 P0；隐私控件、反馈文案、晶体搜索框与移动触控间距已经按 P1/P2 修正；
- 全量 Node 168/168；S4 Chromium 4 场景/5 图，Crystal 3 场景/8 图回归通过。

权威契约与证据：`s4_01_silent_spaces_implementation_contract_v1.md`、`acceptance/silent-spaces-s4-b1/README.md`。

### 6.12 S5 产品化能力关闭状态

- 保持 Vanilla HTML/CSS/ES Modules、无构建链和单文档空间模型；新增的 router 只同步 `?space=today|outbox|memory|privacy`；
- Manifest、192/512 maskable 图标和 Service Worker 静态壳已实现；`/api/*` 永远 network-only；
- 安装入口只由真实 `beforeinstallprompt` 解锁，更新只在 worker waiting 后显示且由用户确认；
- sessionStorage 只保存 v1 未发送草稿，8000 字、24h TTL，成功发送清除；不保存消息历史或 raw response；
- 离线 API 模式隐藏对话、禁用发送并保留温室轮廓，不提供 Background Sync 或伪发送；
- 系统通知、Push/VAPID、角标、离线写队列、历史读取、资源深链和跨设备同步均明确延期；
- Gemini 初审 72/100 的离线示例对话、安装文案、隐私材质和草稿对比度问题已修复；复审 98/100、无 P0/P1/P2；
- 最终 Node 175/175，九套 Chromium 跨阶段脚本全部通过。

权威文档与证据：`s5_01_productization_scope_and_architecture_v1.md`、`s5_02_install_offline_update_experience_design_v1.md`、`s5_03_implementation_plan_v1.md`、`acceptance/productization-s5-b1/README.md`。

## 7. 下一次对话的直接执行顺序

不要重新做 S1–S5 或晶格温室 v2。后续只在出现新产品需求、后端 user-safe DTO、身份/部署契约或真实回归问题时继续：

1. 先读 S5 三份文档和本交接，确认能力是否已实现或被明确延期；
2. 新后端能力必须先更新 `frontend_api_contract_v1.md`，再扩 adapter/ViewModel；
3. 视觉和美化继续交 Gemini，JS/状态/API/测试由 Codex 集成；
4. 每次 Gemini 请求仍附完整原文上下文和当前真实截图，不提供路径代替内容；
5. 任何 Push、历史、账号、同步或公开部署需求都必须重新做隐私和认证架构审计；
6. 修改 Service Worker shell 资源时同步提升 cache version，并重跑 S5 离线验收。

## 8. 测试与运行

全量 Node tests：

```bash
rtk node --test tests/frontend/*.test.mjs
```

当前证据（2026-07-26，S5 完成）：

```text
tests 175
pass 175
fail 0
```

启动网页与后端：

```bash
rtk proxy luminous-api --host 127.0.0.1 --port 8000
```

只验证 UI、避免真实模型调用：

```bash
rtk proxy luminous-api --host 127.0.0.1 --port 8000 --mock
```

浏览器打开：

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/?mode=fixture
```

## 9. 安全与交互不变量

- 初始启动只加载 `/api/state`；Today 仅首次打开后加载；Timeline 仅显式点击后加载；
- raw response 不进入 View、AppState、DOM、日志或 storage；
- opaque key 只用于内存寻址，不显示、不进 tooltip、不进错误文本、不写 data-*；
- 写操作不做假乐观成功；
- Action 影响现实生活时必须 preview → 用户明确 confirm；
- 一个 Today dialog，不增加嵌套 dialog；
- 所有可见操作使用真实 button，触控区至少 44×44；
- 移动端 390×844、safe area、键盘和内部滚动必须验收；
- reduced-motion 下无持续位移/呼吸；
- 不使用红色警报、KPI、进度条、卡片墙、checkbox 墙、toast、spinner、粒子或无意义渐变；
- 错误时保留稳定缓存，不清空、不模糊旧内容；
- 不自动轮询或在窗口 focus 时刷新。
- Service Worker 只缓存静态壳，`/api/*` 永远 network-only；
- storage 只允许版本化未发送草稿，禁止 raw response、历史、opaque key、token 和密钥；
- 安装和更新均由浏览器资格/worker waiting 加用户明确手势驱动，不自动弹出或刷新。

## 10. 工作树注意事项

当前工作树不是干净分支，包含大量此前整理、归档、删除和新增。它们属于当前项目工作，不要使用：

```text
git reset --hard
git checkout -- .
```

不要恢复已归档的旧设计文件，也不要删除无关用户改动。只对当前 batch 的文件做最小、可审计修改。

仓库根目录存在 `.codegraph/`；理解或定位代码时先使用 CodeGraph，CSS/HTML 或文档定位不足时再用 `rtk rg`。

所有 shell 命令必须以 `rtk` 开头；文件修改使用 `apply_patch`。

## 11. 后续阶段

S1–S5 已全部完成并关闭。当前没有自动进入的下一阶段；后续工作由新的产品需求或后端契约触发。被延期的系统通知、Push、聊天历史、跨设备同步和公开部署不得仅凭前端本地状态补齐。

## 12. 停止条件

用户要求：如果可见的调用/对话额度只剩 3%，立即停止新增实现，把当时已完成部分、未验证风险和下一步写入本文及 tracker，等待下周继续。若系统不提供可见额度，不要臆测百分比。
