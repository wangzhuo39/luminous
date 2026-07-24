# 03 API Contract

## Chat

`POST /api/chat`

请求：

```json
{
  "message": "用户输入",
  "history": []
}
```

安全响应字段：

- `role_thinking`
- `role_action`
- `reply`
- `presence`
- `memory`
- `state`
- `prompt`
- `proactive`

前端禁止渲染：

- `system_thinking`

## State

`GET /api/state`

用于驱动：

- `PresenceHalo`
- 环境光
- 色温
- 风险边界
- DND / quiet 状态

## Memory

- `GET /api/memory`
- `GET /api/memory/threads`
- `GET /api/memory/links`
- `GET /api/memory/evidence`
- `POST /api/memory/update`
- `POST /api/memory/forget`
- `GET /api/export`

目标 UI：

- `MemoryConstellation`
- 记忆晶体
- thread / link / evidence 光痕
- 编辑、遗忘、导出确认

## Outbox / Proactive

- `GET /api/outbox`
- `POST /api/proactive/tick`
- `POST /api/outbox/feedback`
- `POST /api/outbox/receipt`

目标 UI：

- `OutboxGlint`
- 信笺
- 流光未读提示
- DND 下静默

## Scheduling / Notifications

- `GET/POST /api/reminders`
- `PATCH/DELETE /api/reminders/{id}`
- `POST /api/reminders/{id}/snooze`
- `POST /api/reminders/{id}/complete`
- `POST /api/reminders/{id}/cancel`
- `GET/POST /api/calendar-events`
- `PATCH/DELETE /api/calendar-events/{id}`
- `GET/PATCH /api/settings/notifications`

通知设置字段：

- `enabled`
- `daily_limit`
- `quiet_start`
- `quiet_end`
- `allowed_kinds`

## Life Flow

- `GET /api/today`
- `GET /api/timeline`
- `GET/POST /api/tasks`
- `PATCH/DELETE /api/tasks/{id}`
- `POST /api/tasks/{id}/steps`
- `PATCH /api/tasks/{id}/steps/{step_id}`
- `POST /api/tasks/{id}/start`
- `POST /api/tasks/{id}/complete`
- `POST /api/tasks/{id}/block`
- `POST /api/tasks/{id}/cancel`
- `GET/POST /api/routines`
- `PATCH/DELETE /api/routines/{id}`
- `POST /api/routines/{id}/checkins`
- `GET/POST /api/activities`
- `GET /api/activities/{id}`
- `POST /api/activities/{id}/start`
- `POST /api/activities/{id}/pause`
- `POST /api/activities/{id}/resume`
- `POST /api/activities/{id}/complete`
- `POST /api/activities/{id}/cancel`
- `GET/POST /api/diary-entries`
- `PATCH/DELETE /api/diary-entries/{id}`
- `POST /api/diary-entries/draft`

## Action Confirmation

- `POST /api/actions/preview`
- `POST /api/actions/confirm`

所有具有现实影响的动作优先走 preview / confirm。

## Audit / Debug

- `GET /api/trace`
- `GET /api/ledger`
- `GET /api/jobs`

目标 UI：

- `PrivacyAuditDrawer`
- `DebugTracePanel`

这些入口默认深层隐藏，不进入普通主体验。
