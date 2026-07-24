你是「栖光 luminous」前端体验与视觉重构的主设计师。请为已生成的 Batch 2B-1 补充一小节：Calendar Events / 日程 API 的精确工程映射。不要重复 TodaySheet 全文，只输出补充节。

方向：晶格温室。日程是时间光带/晶格刻度，不是日历表格。

必须覆盖 API：
- GET /api/calendar-events
- POST /api/calendar-events
- PATCH /api/calendar-events/{id}
- DELETE /api/calendar-events/{id}

请输出 Markdown：

# Batch 2B-1 Supplement：Calendar Events 精确映射

## 1. Calendar Event 视觉与信息模型
## 2. API 到 UI 行为映射表
## 3. 创建、编辑、删除日程流程
## 4. 状态与错误：calendar-empty、calendar-loading、calendar-conflict、calendar-saving、calendar-error
## 5. 与 TodaySheet / NotificationBoundary 的关系

要求具体、可实施、可验收，不要写完整代码补丁。
