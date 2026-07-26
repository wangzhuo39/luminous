# Luminous S2–S5 前端实现追踪表

> 状态：持续维护
> 启动日期：2026-07-25
> 执行依据：`frontend_architecture_v1.md`、`S1_EXECUTION_RETROSPECTIVE_AND_STAGE_PLAYBOOK.md`

## 全局完成规则

- 每阶段设计由 Gemini 输出候选，输入输出保存在 `/home/wz/gemini-api-traces/`。
- 每个实现批次依次通过完整性、安全、架构、语法、浏览器与截图关卡。
- API 原始响应不得直接进入 View 或 AppState；所有功能必须经过 user-safe adapter。
- 每阶段保留桌面、`390×844`、错误态、离线态、键盘和 reduced-motion 验收证据。
- 阶段状态只有在对应 acceptance README 和自动化证据齐全后才能标记完成。

## S2：核心陪伴联通

状态：已完成（2026-07-25）

- [x] 设计轮：真实加载、发送、等待、失败、离线与重试体验
- [x] 通用 API client：相对路径、JSON、AppError、timeout、AbortController、204/空正文/非法 JSON
- [x] `/api/state` 白名单 adapter 与启动控制器
- [x] `/api/chat` 请求 history、响应白名单 adapter 与发送控制器
- [x] 草稿备份、重复提交保护、成功与失败恢复
- [x] 请求替换/取消、超时、503、500、400、离线映射
- [x] 禁止内部字段进入 ViewModel、AppState、DOM、日志和存储
- [x] fixture 模式继续可用，S1 回归不破坏
- [x] 桌面、移动、慢响应、错误、离线、重试、键盘和 reduced-motion 浏览器验收
- [x] Gemini 实际截图多模态终审与阻塞项修正
- [x] `acceptance/core-companion-s2/README.md`

## S3：生活流联通

状态：已完成（2026-07-26）

- [x] Design 01：Today 晨光窗、五类摘要、Timeline 与单 dialog 导航
- [x] Design 02：Task/Step 与 Routine/Checkin 精确交互
- [x] Design 03：Activity 生命周期与 Diary 持久化
- [x] Design 04：Reminder、Calendar 与 Action Preview/Confirm
- [x] Design 05：跨域模块边界、9 个实现批次与验收方案
- [x] B1：时间/验证/operation gate/Today 与 Action 纯状态机（55/55 总回归通过）
- [x] B2：安全 API/fixture 双数据源（32 方法同构，114/114 总回归通过）
- [x] B3：Today 壳、摘要与 Timeline（120/120 Node 回归，6 张浏览器截图，多模态终审通过）
- [x] B4：Task 与 Routine（136/136 Node 回归，3 场景/6 张浏览器截图）
- [x] B5：Activity（140/140 Node 回归，3 场景/8 张浏览器截图，多模态终审通过）
- [x] B6：Diary（151/151 Node 回归，4 场景/6 张浏览器截图）
- [x] B7：Reminder 与 Calendar（156/156 Node 回归，3 场景/7 张浏览器截图，Gemini 终审 92/100）
- [x] B8：Action 光签（162/162 Node 回归，3 场景/6 张浏览器截图，Gemini 终审 96/100）
- [x] B9：集成、截图、多模态视觉终审与回归（162/162；8 套 Chromium 脚本；Gemini 终审 96/100）

- [x] Today 懒加载
- [x] 任务、步骤与状态变更
- [x] 习惯与打卡
- [x] 活动生命周期
- [x] 日记草稿、生成、创建、编辑与删除确认
- [x] 提醒、延后与日程
- [x] Today/Timeline 局部 pending/error/retry
- [x] preview/confirm 两阶段现实行动
- [x] 写失败后输入恢复与重复提交防护（Task/Routine）
- [x] B4 桌面/移动/错误路径/截图验收
- [x] B5 Activity 状态、请求、错误、移动/reduced-motion 与截图验收
- [x] B6 Diary draft→PATCH、手动 POST、删除确认、失败恢复、长正文、移动键盘与截图验收
- [x] B7 Reminder 精确 snooze/cancel 终态与 Calendar 定时/全天/保守删除、移动键盘与截图验收
- [x] B8 五类 Action allowlist、missing mapping、冻结 snapshot confirm/retry、draft diary editor 与光签多模态验收
- [x] 晶格温室 v2：穹顶、实体入口、差异物态、昼夜/tone 动态、匿名晶体、移动光轨、视差暂停与终审

## S4：静默空间联通

状态：已完成（按当前用户安全后端契约）

- [x] Outbox 首次打开懒加载、会话缓存/不轮询策略、显式错误重试和逐项回执/反馈边界
- [x] Memory 主动查询、修订与软忘却；threads/links/evidence 经契约复核确认为内部接口，不进入普通 UI
- [x] 通知设置：总开关、每日上限、静默时段
- [x] DND 从 `/api/state` 只读呈现；当前无写接口，不伪造操作
- [x] Privacy 通知边界操作、dirty/saving/saved/error 与失败草稿保留
- [x] Memory 忘却使用内联明确确认；所有写操作服务端成功前不乐观移除
- [x] 桌面/移动/API 500→重试/no-leak/reduced-motion/截图与 Gemini 多模态验收

## S5：产品化能力

状态：已完成（2026-07-26）

- [x] 根据现有契约审计 PWA、通知、深链、恢复和推送的可实现范围
- [x] 只实现具备产品需求与后端契约的能力；通知/Push/离线写队列/历史恢复明确延期
- [x] 重新评估框架、构建链、路由和前端测试归属：保持 Vanilla/无构建，增加轻量 `?space=` router，Playwright 留在仓库测试
- [x] Manifest、192/512 maskable 图标、静态离线壳、waiting update 和资格驱动安装体验
- [x] versioned session draft、24h TTL、刷新恢复、成功清理与空间 History 前进/后退
- [x] `/api/*` network-only；离线隐藏对话、禁用发送，不缓存历史、不排队写入
- [x] 全量安全、性能、可访问性与跨阶段回归：175/175 Node，9/9 Chromium scripts
- [x] Gemini 初审问题修复并复审 98/100、无 P0/P1/P2，最终架构和交付文档完成

## 产品分层调整：已完成（2026-07-26）

- [x] Today、来信、记忆、隐私保持一级辅助空间，继续从主场景首屏可达。
- [x] 任务、习惯、活动、日记、提醒、日历全部保留，并下沉到 Today 的“更多生活流”二级入口。
- [x] Today 默认先展示摘要和 Timeline；二级能力通过显式展开进入，不再默认等权平铺。
- [x] 入口层级、展开状态、视觉样式和 Chromium 验收脚本已同步更新。
- [x] 物理目录暂不迁移，先保持现有 feature、adapter、state 边界稳定；后续迁移必须独立批次完成并重新验收。

权威实施映射见 `frontend_product_layering_guidance_v1.md`，交接约束见 `FRONTEND_AGENT_HANDOFF.md`。

## 当前发现

1. I1 已将 `/api/chat` 和 `/api/state` 收口为后端公开 DTO；响应不再包含 `role_thinking`、`role_action`、memory、ledger、prompt、analysis、meta 或原始数据库字段。
2. `/api/state` 仍只提供展示层 `state`；`?include=history` 额外提供 `user`/`assistant` 的安全历史 DTO。
3. I1 已补 `GET /api/chat/history`，刷新后由 API 模式首屏恢复最近对话；fixture 路径继续独立保留。
4. S1 浏览器验收脚本禁止所有 API 请求；S2 需要保留 S1 fixture 回归脚本，并新增带受控 mock API 的 S2 脚本。
5. S2 API 边界测试位于 `tests/frontend/s2-api-boundary.test.mjs`，运行命令为 `node --test tests/frontend/s2-api-boundary.test.mjs`。
6. S3 B2 已按真实后端固化 `/checkins`、Reminder POST cancel、snooze 明确 `due_at`、Diary `diary_entry`/`entry` 双 wrapper、Activity 无 DELETE、Calendar 无单项 GET 等差异。
7. S3 API 与 fixture DataSource 均提供 32 个同名方法；fixture 不导入 API client 且在 fetch 抛错环境中完成读写，raw response 只在 adapter 边界内存在。
8. S1–S3 B8 与晶格温室 v2 全量 Node 回归命令为 `node --test tests/frontend/*.test.mjs`，当前 175/175 通过。
9. B3 使用一个 Today dialog 完成 Today/Timeline 双面板；首次打开懒加载、Timeline 显式加载、fixture 零 API、错误字段白名单、焦点进入/归还和 reduced-motion 已由 `acceptance/today-timeline-s3-b3/` 证明。
10. B4 已完成 Task/Step 与 Routine/Checkin 的列表、详情、创建、编辑、状态变更、归档/停用确认、失败草稿恢复、重复提交门禁和 Today 回刷；证据位于 `acceptance/tasks-routines-s3-b4/`。
11. 原视觉只实现冷色模糊，未兑现晶格温室。v1 只作为技术基线；感知完成基线已升级为 `crystal_solarium_v2_implementation_spec.md`，证据位于 `acceptance/crystal-solarium-v2/`。Gemini 复审 86/100、无 P0。B7–S5 不得退回黑色 dialog、水平 Tab Bar、卡片墙或单图背景。
12. B5 已完成 Activity 列表、创建、planned/active/paused/completed/cancelled 生命周期、terminal/unknown 只读、精确请求、保守写入和主场景 active/paused 事实派生；证据位于 `acceptance/activities-s3-b5/`。Activity 无 DELETE、timer、progress 或伪时长。
13. B6 已完成 Diary 列表、详情、手动 POST、generated draft→PATCH、编辑、删除确认、错误草稿恢复和长正文/移动键盘；证据位于 `acceptance/diary-s3-b6/`。
14. I1 后端验收位于 `tests/backend/test_i1_api.py`：公开 DTO、结构化错误、鉴权/CORS、幂等、重启持久化、生活流路由与 Worker 重试均通过；真实模式 Chromium 验收位于 `tests/frontend/i1-real-mode-browser-acceptance.mjs`。
14. `scene-environment.js` 只接收安全聚合值。S4 前主应用明确使用 `memoryCount=0`、`dnd=false`；不得为了点亮装饰读取 Memory 正文、opaque key 或 raw response。
15. B7 已完成 Reminder 光尘列表/详情/创建/编辑/精确 snooze/取消终态，以及 Calendar 窗框刻度/定时/全天/编辑/保守删除；证据位于 `acceptance/reminder-calendar-s3-b7/`。Gemini 7 图终审 92/100、无 P0，四项非阻塞 P1 修正后浏览器回归通过。
16. B8 已完成可注入、生产门控的 Action 光签；五类 proposal 在请求前 allowlist，目标映射失败不发网络请求，confirm 固定使用同一冻结 snapshot，draft diary 进入已持久化 editor。证据位于 `acceptance/action-light-tag-s3-b8/`，Gemini 终审 96/100、无 P0。
17. B9 已串行重跑 B3–B8 与 Crystal 共 7 套既有 Chromium 脚本，并新增生产 Action 门控/chat/Today/320px/门户恢复集成脚本；全部通过。Gemini 9 图终审 96/100，明确“S3 可正式关闭”、无 P0。证据位于 `acceptance/s3-final-integration-b9/`。
18. S4 已按真实契约完成三个静默空间：Outbox、Memory 和 Privacy/通知偏好。`adapters/silent-spaces-adapter.js` 严格丢弃内部字段，环境层只接收 count/boolean。Memory threads/links/evidence 与 export/trace 不进入 UI；DND 仅只读。证据位于 `acceptance/silent-spaces-s4-b1/`，Gemini 四图审阅 88/100、无 P0，P1/P2 已落实。
19. S5 已完成静态壳 PWA、用户确认更新、资格驱动安装、空间级深链和 session draft 恢复。仅静态资源进入 CacheStorage，`/api/*` 永远 network-only；系统通知、Push、Background Sync、离线写队列、聊天历史和跨设备同步均未伪造。证据位于 `acceptance/productization-s5-b1/`，最终 Node 175/175、9/9 Chromium scripts、Gemini 复审 98/100 且无 P0/P1/P2。
