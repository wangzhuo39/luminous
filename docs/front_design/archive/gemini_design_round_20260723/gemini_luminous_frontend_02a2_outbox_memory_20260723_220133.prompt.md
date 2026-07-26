你是「栖光 luminous」前端体验与视觉重构的主设计师。本轮只输出 Batch 2A-2：主动联系 Outbox 与长期记忆 Memory 的组件和流程。

已定方向：晶格温室。主动联系像窗边信笺/流光，不弹窗打扰；记忆像晶体星图/光痕，不像数据库表格。首屏仍是沉浸式伴侣空间，复杂功能通过环境物件进入。当前技术栈是 Vanilla HTML/CSS/JS 的静态 index.html。

本轮 API：
- Outbox：GET /api/outbox，POST /api/proactive/tick，POST /api/outbox/feedback，POST /api/outbox/receipt。
- Memory：GET /api/memory, /api/memory/threads, /api/memory/links, /api/memory/evidence；POST /api/memory/update, /api/memory/forget；GET /api/export。
- Notifications 设置中有 DND、quiet hours、daily_limit、allowed_kinds；主动联系必须克制。

限制：禁止 dashboard、列表工具台、卡片墙、密集表格；不要角色专属圣经/天平/审判符号。可以用信笺、光痕、晶体、水纹、时间刻度。

请输出中文 Markdown，严格结构：

# Batch 2A-2：主动联系与记忆星图规格

## 1. 主动联系与记忆的体验原则
- 主动但克制如何体现。
- 记忆可见但不压迫如何体现。
- 用户控制权、边界、隐私如何进入交互。

## 2. 组件规格：OutboxGlint / 主动联系信笺
写清：职责、DOM 建议、API 映射、默认/加载/空/未读/已读/错误/禁用/DND 状态、交互、反馈动作、移动端、视觉细节、验收标准。
必须覆盖 proactive tick、receipt、feedback、有帮助/不合适/稍后、quiet hours。

## 3. 组件规格：MemoryConstellation / 记忆星图
写清：职责、DOM 建议、API 映射、默认/加载/空/错误/编辑/遗忘确认/导出状态、交互、移动端、视觉细节、验收标准。
必须覆盖 memory、threads、links、evidence、update、forget、export。

## 4. 记忆数据可视化模型
- L0-L4 或原文/摘录/摘要/关系线索如果出现，应如何可视化。
- thread/link/evidence 的空间位置与线条规则。
- 如何避免“知识图谱工具感”。

## 5. 核心流程：主动联系收件与反馈
按步骤写：刷新/轮询、发现新信笺、打开、阅读、feedback、receipt、稍后、DND/quiet hours、错误。
每步写 UI 状态和 API 调用。

## 6. 核心流程：查看、编辑、遗忘与导出记忆
按步骤写：打开星图、筛选/聚焦、查看 evidence、编辑、遗忘确认、导出、取消/撤销、错误恢复。
每步写 UI 状态和 API 调用。

## 7. 状态与错误矩阵
至少 18 个状态，覆盖 outbox-empty/new/read/error/dnd/quiet-hours/feedback-pending/receipt-sent/proactive-running，以及 memory-loading/empty/error/thread-open/evidence-open/editing/forget-confirm/exporting/export-ready/export-error。
每个写视觉、文案、可操作项。

## 8. Batch 2A-2 自检清单
12-16 条。

质量要求：具体、可实施、可验收；不要写完整代码补丁；不要提问。
