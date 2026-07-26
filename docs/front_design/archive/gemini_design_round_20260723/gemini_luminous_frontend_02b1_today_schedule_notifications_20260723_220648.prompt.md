你是「栖光 luminous」前端体验与视觉重构的主设计师。本轮只输出 Batch 2B-1：TodaySheet、提醒/日程、通知边界。

方向：晶格温室。TodaySheet 是“共同生活的光页/桌面纸页”，不是效率 dashboard。提醒和日程要像时间痕迹，不是表格列表。通知边界要克制、可理解。

工程现实：Vanilla HTML/CSS/JS 静态 index.html。

本轮 API：
- GET /api/today, GET /api/timeline。
- Reminders：GET/POST /api/reminders, PATCH/DELETE /api/reminders/{id}, POST /api/reminders/{id}/snooze|complete|cancel。
- Calendar：GET/POST /api/calendar-events, PATCH/DELETE /api/calendar-events/{id}。
- Notification settings：GET/PATCH /api/settings/notifications，DND、quiet hours、daily_limit、allowed_kinds。

请输出中文 Markdown，结构：

# Batch 2B-1：TodaySheet、提醒日程与通知边界规格

## 1. TodaySheet 体验原则
- 今日页如何从首屏入口打开。
- 今日、时间线、提醒、日程的层级关系。
- 如何避免效率工具感。

## 2. 组件规格：TodaySheet
写清职责、DOM 建议、API 映射、默认/加载/空/错误/禁用状态、交互、移动端、视觉细节、验收标准。
覆盖 /api/today、/api/timeline、今天的提醒、日程、未完成事项摘要。

## 3. 组件规格：Scheduling & Reminder Layer
覆盖 reminder 创建、snooze、complete、cancel、编辑、删除；calendar event 创建、编辑、删除；弱网/失败/重复提交。
写状态、交互、移动端键盘、确认机制。

## 4. 组件规格：NotificationBoundary
覆盖 DND、quiet hours、daily_limit、allowed_kinds、浏览器通知权限缺失/拒绝、主动联系静默。
写视觉、文案、可操作项。

## 5. 核心流程：查看今日与时间线
步骤写 UI 状态和 API 调用。

## 6. 核心流程：添加提醒/日程与修改通知偏好
步骤写 API 调用、preview/confirm 是否需要、成功、失败、取消、移动端。

## 7. 状态与错误矩阵
至少 16 个状态：today-loading、today-empty、today-error、timeline-empty、reminder-due、reminder-snoozed、reminder-completed、reminder-cancelled、calendar-empty、calendar-conflict、notification-denied、notification-enabled、dnd、quiet-hours、daily-limit、settings-saving、settings-error。
每个写视觉、文案、可操作项。

## 8. Batch 2B-1 自检清单
12-16 条。

要求：具体、可实施、可验收；不要写完整代码补丁；不要提问。
