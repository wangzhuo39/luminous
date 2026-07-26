你是「栖光 luminous」前端体验与视觉重构的主设计师。Codex 负责调度、工程集成和验收；本轮只展开 Batch 1A。

已通过的大纲方向：主推「晶格温室 (The Crystal Solarium)」。它是一个安静的、拥有纵深光窗的半透明伴侣空间；光线代表时间与情绪，记忆是晶体/信笺，输入像水面凝露。目标是把当前三栏工具台重构成沉浸式实体空间。

项目约束：
- 产品：栖光 luminous。定义：栖光，是在某个人身边停驻的一束光。
- 情感陪伴 AI / 长期 AI 伴侣运行时，不是 SaaS dashboard、普通聊天机器人或营销页。
- 当前前端：/home/wz/luminous/apps/companion-web/companion-ui/index.html，Python 静态托管，Vanilla HTML/CSS/JS，无 React/Vite/package.json。
- 当前已实现能力：聊天、presence、长期记忆、主动联系、提醒/日程、生活流、trace/ledger，但视觉偏三栏工具台。
- 后续 Batch 1B 会展开布局和视觉 token；本轮要把体验概念和信息架构定牢。

必须覆盖的能力/API：
- Chat：POST /api/chat，返回 role_thinking、role_action、reply、presence、memory、state、prompt、proactive。system_thinking 不得暴露。
- State：GET /api/state。
- Memory：GET /api/memory, /api/memory/threads, /api/memory/links, /api/memory/evidence；POST /api/memory/update, /api/memory/forget；GET /api/export。
- Proactive/Outbox：GET /api/outbox, POST /api/proactive/tick, POST /api/outbox/feedback, POST /api/outbox/receipt。
- Scheduling/Notifications：GET/POST /api/reminders, /api/calendar-events；GET/PATCH /api/settings/notifications；DND、quiet hours、daily_limit、allowed_kinds。
- Life Flow：GET /api/today, /api/timeline, /api/tasks, /api/routines, /api/activities, /api/diary-entries。
- Audit/Debug：GET /api/trace, /api/ledger, /api/jobs，必须深层化。

限制：
- 可用视觉语言：冷白、冰蓝、透明玻璃、水晶、微光、纱质、完整人物主体、纵深光窗、克制守候。
- 禁止直接复刻圣经、天平、审判、圣女、叶筝专属身份、宗教/法庭道具。抽象成光、窗、水、晶体、信笺、时间痕迹、呼吸。
- 避免三栏工具台、卡片墙、密集聊天气泡、通用 AI dashboard、浮夸玻璃拟态、纯蓝紫渐变。

请输出 Markdown，严格使用以下结构：

# Batch 1A：晶格温室的体验概念与信息架构

## 1. 产品体验愿景与设计原则
### 1.1 设计北极星
- 一句话愿景
- 用户打开首屏时的目标感受
- 工程验收时可观察的 5-8 个指标
### 1.2 从工具台到实体空间
- 解释当前三栏的哪些功能被转译到空间层级
- 原聊天区、左侧状态、右侧记忆、life-flow 浮层分别如何变成空间内的存在
### 1.3 陪伴气质如何进入视觉
- 安静在场、主动但克制、边界明确、长期记得、可审计分别如何表达
### 1.4 反模式清单
- 至少 12 条禁止的 UI/视觉/交互反模式，并说明原因
### 1.5 MVP 设计原则
- 在静态 HTML/CSS/JS 中先做什么，哪些留给 React/Live2D/VRM

## 2. 晶格温室空间隐喻
### 2.1 空间设定
- 前景、中景、远景、深层分别代表什么
### 2.2 时间、情绪、关系如何影响空间
- presence/state 如何改变光线、雾度、镜头、色温、物件状态
### 2.3 通用物件语言
- 光窗、水面、晶体、信笺、时间刻度、雾面帘、呼吸光分别承载哪些功能
### 2.4 角色泛化策略
- 如何支持未来不同伴侣角色，不绑定叶筝/圣女/审判者设定

## 3. 信息架构与功能分层
### 3.1 总体层级
- 存在层、共鸣层、回响层、生活层、边界层、基石层，逐层定义
### 3.2 功能分层矩阵
用表格列：功能/API、体验层级、默认显性程度、入口物件、数据来源、关闭/返回、为什么不工具化。
必须覆盖 Chat、Presence、Memory、Proactive、Scheduling、Life Flow、Diary/Timeline、Settings/Privacy/Export、Trace/Ledger/Jobs。
### 3.3 Diegetic UI 入口策略
- 每个入口的物件语言、位置、状态提示、空态、未读/错误提示方式
### 3.4 信息密度策略
- 如何让复杂功能可达但不压迫首屏
- 何时用 overlay、bottom sheet、deep drawer、debug panel
### 3.5 导航与返回模型
- 无顶栏/无侧栏时如何返回、关闭、维持焦点、处理多层浮层

## 4. Batch 1A 自检清单
- 12-16 条可验证标准。

质量要求：不要写代码，不要摘要化。保持方案可落地到当前 index.html，并为后续 Batch 1B/2/3 留接口。直接输出最终文档。
