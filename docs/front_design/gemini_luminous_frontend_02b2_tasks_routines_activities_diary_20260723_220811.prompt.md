你是「栖光 luminous」前端体验与视觉重构的主设计师。本轮只输出 Batch 2B-2：任务、习惯、活动会话、日记回顾。

方向：晶格温室。任务/习惯/活动不是效率管理，而是共同生活里的轻量承诺和正在一起做的状态；日记回顾是一天结束时的回声，不替用户定义人生。

工程现实：Vanilla HTML/CSS/JS 静态 index.html。

本轮 API：
- Tasks：GET/POST /api/tasks, PATCH/DELETE /api/tasks/{id}, POST /api/tasks/{id}/steps, PATCH /api/tasks/{id}/steps/{step_id}, POST /api/tasks/{id}/start|complete|block|cancel。
- Routines：GET/POST /api/routines, PATCH/DELETE /api/routines/{id}, POST /api/routines/{id}/checkins。
- Activities：GET/POST /api/activities, GET /api/activities/{id}, POST /api/activities/{id}/start|pause|resume|complete|cancel。
- Diary：GET/POST /api/diary-entries, PATCH/DELETE /api/diary-entries/{id}, POST /api/diary-entries/draft。
- Actions：POST /api/actions/preview, POST /api/actions/confirm，用于用户确认。

请输出中文 Markdown，结构：

# Batch 2B-2：共同任务、例行习惯、活动会话与日记回顾规格

## 1. 共同生活动作原则
- 如何让任务/习惯/活动保持陪伴感，不变成 productivity dashboard。
- 用户控制权、确认、撤销、隐私边界。

## 2. 组件规格：Task Controls / 共同任务
覆盖创建、步骤、开始、完成、阻塞、取消、编辑、删除、错误恢复、移动端。
写 DOM 建议、API 映射、状态、交互、视觉细节、验收标准。

## 3. 组件规格：Routine Controls / 例行习惯
覆盖 routine 创建、编辑、删除、checkin、连续次数、错过、今日已完成、提醒策略。
写 API 映射、状态、移动端、视觉细节。

## 4. 组件规格：Activity Session / 一起做
覆盖 activity 创建、详情、开始、暂停、继续、完成、取消。说明 active 状态如何影响主场景 presence。
写 API 映射、状态、移动端、视觉细节。

## 5. 组件规格：DiaryReview / 今日回顾
覆盖 timeline 片段、diary draft、用户编辑、保存、删除、失败、隐私提示。强调草稿是可编辑建议，不替用户定性。

## 6. 组件规格：ActionPreviewConfirm / 行动确认
覆盖 /api/actions/preview 和 /api/actions/confirm。说明哪些动作必须确认，确认 UI 如何沉浸化，取消/失败如何处理。

## 7. 核心流程：创建共同任务并推进
步骤写 UI 状态和 API 调用。

## 8. 核心流程：习惯打卡与活动会话
步骤写 UI 状态和 API 调用。

## 9. 核心流程：日记草稿与今日回顾
步骤写 UI 状态和 API 调用。

## 10. 状态与错误矩阵
至少 20 个状态：task-open、task-in-progress、task-blocked、task-completed、task-cancelled、step-open、step-done、routine-due、routine-done、routine-missed、activity-planned、activity-active、activity-paused、activity-completed、activity-cancelled、diary-empty、diary-drafting、diary-draft-ready、diary-saving、diary-error、action-preview、action-confirming、action-denied。
每个写视觉、文案、可操作项。

## 11. Batch 2B-2 自检清单
12-16 条。

要求：具体、可实施、可验收；不要写完整代码补丁；不要提问。
