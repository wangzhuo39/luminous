你是「栖光 luminous」前端体验与视觉重构的主设计师。本轮只输出 Batch 2A-1：对话、凝露输入、presence 状态组件与流程。

已定方向：晶格温室 (The Crystal Solarium)。首屏是沉浸式伴侣空间，不是三栏工具台。视觉语言是冷白、冰蓝、透明玻璃、水晶、微光、纱质、纵深光窗、安静克制守候感。输入像水面凝露；对话像电影字幕；状态像人物周围的呼吸光。禁止圣经/天平/审判/圣女/宗教法庭道具，避免 dashboard、卡片墙、密集聊天气泡。

工程现实：/home/wz/luminous/apps/companion-web/companion-ui/index.html，Vanilla HTML/CSS/JS，Python 静态托管，无 React/Vite。设计必须能先落到静态 index.html。

本轮 API：
- POST /api/chat：入参 message/history；返回 role_thinking、role_action、reply、presence、memory、state、prompt、proactive。system_thinking 不得进入 DOM。
- GET /api/state：驱动 presence、情绪、关系、风险、场景。

请输出中文 Markdown，严格结构：

# Batch 2A-1：对话、凝露输入与 Presence 规格

## 1. 对话场总体模型
- 当前片段、短期历史、长期记忆的视觉区分。
- 为什么字幕替代气泡，如何回看历史但不变聊天流。
- 超长回复、连续多轮、失败重试的原则。

## 2. 组件规格：SubtitleDialogue
用表格或分节写清：职责、DOM 建议、API 映射、默认/加载/空/错误/禁用状态、交互、键盘、移动端、视觉细节、验收标准。
必须覆盖 role_action、reply、role_thinking 折叠显示；明确 system_thinking 防线。

## 3. 组件规格：AirInput
覆盖：多行输入、发送、禁用、联网失败、模型等待、快捷提示 chips 是否保留/如何沉浸化、中文 IME、Enter/Shift+Enter、移动端键盘、焦点、ARIA、可访问性。

## 4. 组件规格：PresenceHalo / Companion Presence
覆盖：GET /api/state 与 /api/chat 返回 presence 如何更新；心跳、活动、情绪、关系、风险如何映射到光晕、雾度、色温、节奏。
给状态映射表：calm、thinking、warm、concerned、joy、dnd、risk、offline、loading。

## 5. 核心流程：日常对话
步骤必须包含：输入、乐观显示、发送、等待、返回、presence 更新、错误、重试、历史回看。每步写 UI 状态与 API 调用。

## 6. 状态与错误矩阵
列至少 14 个状态：idle、focused、typing、sending、waiting、replying、chat-error、offline、state-loading、state-error、empty-first-run、role-thinking-available、risk、dnd。每个写视觉、文案、可操作项。

## 7. Batch 2A-1 自检清单
12-16 条。

要求：具体、可实施、可验收；不要写完整代码补丁；不要提问。
