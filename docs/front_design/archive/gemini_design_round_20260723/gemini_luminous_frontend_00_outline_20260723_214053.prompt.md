你是「栖光 luminous」前端体验与视觉重构的主设计师。Codex 只负责调度、工程集成和验收；你负责前端设计与视觉重构。

本轮不要写完整详细设计文档，也不要写代码。请先输出「完整设计文档的大纲 v0.1」，作为后续分阶段展开的目录蓝图。大纲要足够具体，能让 Codex 按章节继续委托你逐步扩写。

项目背景：
- 项目路径：/home/wz/luminous
- 当前网页端：/home/wz/luminous/apps/companion-web/companion-ui/index.html
- 当前不是 React/Vite；是 Python 后端静态托管单页 HTML/CSS/vanilla JS 原型。
- 当前原型已覆盖聊天、presence、长期记忆、主动联系、提醒/日程、生活流、trace/ledger，但视觉偏三栏工具台。
- 产品名称：栖光 luminous。一句话：栖光，是在某个人身边停驻的一束光。
- 产品类型：情感陪伴 AI / 长期 AI 伴侣运行时。不是 SaaS dashboard，不是普通聊天机器人，不是营销落地页。
- 产品气质：安静在场、长期记得、主动但克制、边界明确、情绪承接、现实支持、可审计。

已实现能力和 API：
- Chat：POST /api/chat，返回 role_thinking、role_action、reply、presence、memory、state、prompt、proactive。system_thinking 已后端剥离，前端绝不能暴露。
- State：GET /api/state。
- Memory：GET /api/memory, /api/memory/threads, /api/memory/links, /api/memory/evidence；POST /api/memory/update, /api/memory/forget；GET /api/export。
- Proactive / Outbox：GET /api/outbox, POST /api/proactive/tick, POST /api/outbox/feedback, POST /api/outbox/receipt。
- Scheduling / Notifications：GET/POST /api/reminders, /api/calendar-events；GET/PATCH /api/settings/notifications；DND、quiet hours、daily_limit、allowed_kinds。
- Life Flow：GET /api/today, /api/timeline, /api/tasks, /api/routines, /api/activities, /api/diary-entries。
- Audit / Debug：GET /api/trace, /api/ledger, /api/jobs。它们应是深层入口，不进入主体验。

设计参考与限制：
- 旧 PDF 的可借鉴方向：从“对话画布”转为“实体空间”；全屏场景；空间同步；镜头语言；电影字幕；凝露式输入；功能入口情境化/diegetic UI；MVP 可先用背景+人物+parallax+微动效。
- 人物主体图参考：冷白、冰蓝、透明玻璃、水晶、微光、纱质、完整人物主体、纵深光窗、安静克制的守候感。
- 禁止直接复刻角色特定符号：圣经、天平、审判、圣女、叶筝专属身份、宗教/法庭道具。请抽象为通用伴侣空间中的光、窗、水、晶体、信笺、时间痕迹、呼吸。
- 避免三栏工具台、卡片墙、密集聊天气泡、通用 AI dashboard、浮夸玻璃拟态、纯蓝紫渐变。

请输出：
1. 一个推荐的完整设计文档目录，按 12-16 个一级章节组织。
2. 每个一级章节下列出 3-8 个二级小节，并说明该节要回答什么设计问题。
3. 标出每个章节对应的后续 Gemini 展开批次，建议分为：
   - Batch 1：体验概念、信息架构、主界面布局、视觉系统。
   - Batch 2：组件规格、核心流程、状态/错误/空态。
   - Batch 3：响应式、可访问性、安全隐私、重构路线、验收清单。
4. 给出设计总方向的候选方案 2-3 个，并推荐其中 1 个作为主线。候选方案要明确视觉隐喻、风险、适配度。
5. 给出 Codex 后续验收大纲的检查点，帮助判断每个批次是否合格。
6. 给出最终文档文件命名建议。

请使用 Markdown。要求具体、可调度，不要只写泛泛目录。
