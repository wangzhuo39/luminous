# Luminous 前端接口契约 v1

> 面向前端设计与实现。前端代理只需阅读本文件，不需要翻阅 Python 后端代码。
>
> 本文档以当前运行时 `luminous.runtime.infrastructure.http` 为准。它覆盖正常用户界面可用的接口；调试、审计和导出接口不属于产品前端。

## 1. 运行方式

- 前端静态文件与 API 同源，由同一个服务提供。
- 开发启动：

  ```bash
  cd /home/wz/luminous
  source .venv/bin/activate
  python -m luminous.runtime.infrastructure.http --mock --host 127.0.0.1 --port 8000
  ```

- 默认本地地址：`http://127.0.0.1:8000`。
- 前端请求使用相对路径，例如 `fetch('/api/state')`，不要写死主机和端口。
- JSON 写请求使用 `Content-Type: application/json`。
- 默认是 `local` 单用户模式。公开部署必须显式设置 `LUMINOUS_DEPLOYMENT_MODE=public`、
  `LUMINOUS_AUTH_TOKEN` 和 `LUMINOUS_CORS_ORIGINS`，并使用 `Authorization: Bearer <token>`。

## 2. 全局约定

### 响应与错误

- 成功读取和更新通常返回 `200`；创建通常返回 `201`，无内容返回 `204`。
- 错误统一为 `{"error":{"code":"invalid_request","message":"...","retryable":false}}`。
- 参数或状态不合法返回 `400`；未认证 `401`；来源不允许 `403`；不存在的路径或资源 `404`；状态冲突或重复提交冲突 `409`；模型/依赖不可用 `503`。
- 任何写操作只有在 HTTP 成功且 JSON 成功返回后才能在界面中确认成功。失败时保留用户输入，并给出重试机会。

### 列表与标识符

- 列表响应统一从 `items` 读取，**不要**读取 `tasks`、`routines` 等猜测字段。
- 资源 ID 不同：任务 `task_id`，习惯 `routine_id`，活动 `session_id`，日记 `entry_id`，提醒 `reminder_id`，日程 `event_id`。
- 所有时间值使用 ISO 8601 字符串；空时间以空字符串表示。
- 列表只支持 `limit` 分页，必须是服务端允许范围内的整数，当前 v1 不承诺 cursor/offset。
- 写请求可带最长 128 字符的 `Idempotency-Key`；同 key 重放首次结果，复用 key 但请求体不同返回 `409`。

### 正常用户界面的安全边界

只能使用下列字段驱动正常体验：最终回答 `reply`、安全陪伴状态 `presence`、持久状态 `state`、以及业务资源本身。

绝不读取、存储、渲染或通过 UI 暴露：

- `system_thinking`、`role_thinking`、`role_action`、`analysis`；
- `prompt`、`ledger`、trace ID、job、导出数据；
- `/api/ledger`、`/api/trace`、`/api/jobs`、`/api/export`；
- `/api/memory/threads`、`/api/memory/links`、`/api/memory/evidence`。

这些内容属于内部推理、审计或开发支持信息，不是用户可见的陪伴内容。

## 3. 前端展示模型边界

接口响应不应直接散落在组件中。建议前端在一个 adapter/service 层将 API 转换为以下展示模型：

```text
SceneViewModel
  presence: { caption, thought, activity, heartRate }
  relationshipTone: { mood, energy, supportNeed, riskLevel }

ConversationViewModel
  messages: [{ id, role: 'user' | 'assistant', text, sentAt }]
  draft, sending, error

TodayViewModel
  date, calendarEvents, overdueTasks, dueTasks, openTasks,
  routines, activeActivities, completedTasks

ArrivalViewModel
  items: [{ id, title, body, arrivedAt, status }]

MemoryViewModel
  items: [{ id, content, summary, occurredAt, confidence }]
```

字段命名由前端可以自行整理；真实接口字段只应在 adapter 层出现。静态原型阶段使用 fixture，后端联通阶段再替换 adapter 的数据来源。

## 4. 启动、场景与对话

### `GET /api/health`

仅用于低打扰的连接诊断，不作为用户可见功能入口。

```json
{"ok": true, "status": "ready"}
```

### `GET /api/state`

启动、刷新和网络恢复时调用。

响应重点：持久陪伴状态在 **`response.state`** 中，不在根部。

```json
{
  "state": {
    "mood": "steady",
    "energy": "...",
    "support_need": "...",
    "risk_level": "normal",
    "conversation_mode": "...",
    "relationship": {"trust": 0, "intimacy": 0},
    "dnd_until": "",
    "open_loops": []
  }
}
```

`mood`、`energy`、`support_need`、`risk_level` 只能转化为克制的光线、距离、静默感和文案语气，不能展示数值仪表盘或人格诊断。

首屏恢复可请求 `GET /api/state?include=history`，响应额外包含严格公开的
`history: {"limit","count","items":[{"message_id","role","content","created_at"}]}`。
也可用 `GET /api/chat/history?limit=10` 单独读取最近对话；历史只允许 `user` 和 `assistant`。

### `POST /api/chat`

请求：

```json
{
  "message": "今天有点累。",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

约束：

- `message` 是当前用户输入；`history` 仅发送之前成功的用户/助手最终消息。
- 发送期间保留输入草稿的副本；失败后恢复草稿。
- 成功后只渲染 `reply`。

安全可用的响应片段：

```json
{
  "reply": "我在，先陪你慢一点。",
  "presence": {
    "heart_rate": 69,
    "caption": "...",
    "thought": "...",
    "activity": "..."
  },
  "state": {"mood": "steady", "risk_level": "normal"}
}
```

`presence` 可驱动呼吸节奏、短字幕和环境细节；不必也不应展示完整内部状态包。

## 5. 今日、提醒和日程

### 读取

| 接口 | 查询参数 | 前端用途 |
| --- | --- | --- |
| `GET /api/today` | `date=YYYY-MM-DD` 可选 | Today 光窗的聚合数据：`calendar_events`、`overdue_tasks`、`due_tasks`、`open_tasks`、`routines`、`active_activities`、`completed_tasks`。 |
| `GET /api/reminders` | `status`、`limit` | 提醒列表，读取 `items`。 |
| `GET /api/calendar-events` | `limit` | 日程列表，读取 `items`。 |
| `GET /api/timeline` | `from`、`to`、`kind`、`limit` | 需要时间轴时按需加载。 |
| `GET /api/settings/notifications` | 无 | 通知与免打扰设置。 |

### 提醒 `reminders`

| 操作 | 接口 | 最小前端数据 |
| --- | --- | --- |
| 新建 | `POST /api/reminders` | `title`、`due_at`；可附加描述、关联资源、通知选项。 |
| 更新 | `PATCH /api/reminders/{reminder_id}` | 仅提交修改字段。 |
| 延后 | `POST /api/reminders/{reminder_id}/snooze` | 可提交新的时间或延后参数。 |
| 完成 | `POST /api/reminders/{reminder_id}/complete` | 空对象 `{}` 即可。 |
| 取消 | `POST /api/reminders/{reminder_id}/cancel` | 空对象 `{}` 即可。 |
| 删除 | `DELETE /api/reminders/{reminder_id}` | 以服务端返回为准。 |

### 日程 `calendar-events`

| 操作 | 接口 | 最小前端数据 |
| --- | --- | --- |
| 新建 | `POST /api/calendar-events` | `title`、`starts_at`；可附加 `ends_at`、`description`、提醒信息。 |
| 更新 | `PATCH /api/calendar-events/{event_id}` | 仅提交修改字段。 |
| 删除 | `DELETE /api/calendar-events/{event_id}` | 以服务端返回为准。 |

### 通知设置

`GET`、`POST`、`PATCH /api/settings/notifications`

可写字段：

```json
{
  "enabled": true,
  "daily_limit": 3,
  "quiet_start": "22:00",
  "quiet_end": "08:00",
  "allowed_kinds": ["checkin", "reminder"]
}
```

前端必须尊重 `enabled`、静默时间和 `dnd_until`；主动联系不可做成强制弹窗。

## 6. 生活流

### 读取

| 接口 | 常用查询参数 | 返回 |
| --- | --- | --- |
| `GET /api/tasks` | `status`、`limit` | `{"items":[Task]}` |
| `GET /api/routines` | `active_only`、`limit` | `{"items":[Routine]}` |
| `GET /api/activities` | `status`、`limit` | `{"items":[Activity]}` |
| `GET /api/diary-entries` | `date`、`limit` | `{"items":[DiaryEntry]}` |

任务核心字段：`task_id`、`title`、`description`、`status`、`due_at`、`priority`、`steps`。

### 任务 `tasks`

| 操作 | 接口 | 说明 |
| --- | --- | --- |
| 新建 | `POST /api/tasks` | 最小提交 `{"title":"..."}`；可附加 `description`、`due_at`、`priority`、`metadata`。返回 `task`。 |
| 更新 | `PATCH /api/tasks/{task_id}` | 提交 `title`、`description`、`due_at`、`priority`、`metadata`、`status` 等变更字段。 |
| 添加步骤 | `POST /api/tasks/{task_id}/steps` | 最小提交 `{"title":"..."}`。返回 `step`。 |
| 更新步骤 | `PATCH /api/tasks/{task_id}/steps/{step_id}` | 例如 `{"status":"completed"}`。 |
| 状态转换 | `POST /api/tasks/{task_id}/start`、`complete`、`block`、`cancel` | 可提交 `{}` 或该操作所需补充字段。 |
| 删除 | `DELETE /api/tasks/{task_id}` | 以服务端状态返回为准。 |

### 习惯 `routines`

| 操作 | 接口 | 说明 |
| --- | --- | --- |
| 新建 | `POST /api/routines` | 提交习惯标题及频率/目标等配置；返回 `routine`。 |
| 更新 | `PATCH /api/routines/{routine_id}` | 仅提交修改字段。 |
| 打卡 | `POST /api/routines/{routine_id}/checkins` | 可提交当次记录；返回更新后的习惯/打卡结果。 |
| 删除 | `DELETE /api/routines/{routine_id}` | 以服务端返回为准。 |

### 活动 `activities`

| 操作 | 接口 | 说明 |
| --- | --- | --- |
| 新建 | `POST /api/activities` | 提交活动标题、计划时间或时长等；返回 `activity`，ID 为 `session_id`。 |
| 状态转换 | `POST /api/activities/{session_id}/start`、`pause`、`resume`、`complete`、`cancel` | 活动状态：`planned`、`active`、`paused`、`completed`、`cancelled`、`expired`。 |
| 删除 | `DELETE /api/activities/{session_id}` | v1 不提供，返回 `404`；活动只允许状态转换。 |

### 日记 `diary-entries`

| 操作 | 接口 | 说明 |
| --- | --- | --- |
| 新建 | `POST /api/diary-entries` | 最小内容为 `body`；可附加标题、日期、标签等。返回 `entry`，ID 为 `entry_id`。 |
| 草稿 | `POST /api/diary-entries/draft` | 传入当前线索，得到草稿建议；前端必须允许用户编辑后再保存。 |
| 更新 | `PATCH /api/diary-entries/{entry_id}` | 仅提交修改字段。 |
| 删除 | `DELETE /api/diary-entries/{entry_id}` | 以服务端返回为准。 |

## 7. 来信与记忆

### 来信 / 主动联系

| 操作 | 接口 | 说明 |
| --- | --- | --- |
| 读取 | `GET /api/outbox?status=&limit=` | 返回来信及投递状态；在“信笺”空间低打扰呈现。 |
| 回执 | `POST /api/outbox/receipt` | 使用来信的 ID 与回执状态；以实际返回为准。 |
| 反馈 | `POST /api/outbox/feedback` | 使用来信的 ID 与用户反馈；以实际返回为准。 |

前端不要提供 `POST /api/proactive/tick` 的普通用户按钮；那是内部触发器。

### 记忆与隐私

| 操作 | 接口 | 说明 |
| --- | --- | --- |
| 查询 | `GET /api/memory?q=&limit=` | `q` 为查询文字；结果用于记忆空间而非首屏噪音。 |
| 修订 | `POST /api/memory/update` | 使用服务端返回的记忆 ID 和用户确认后的修改内容。 |
| 忘却 | `POST /api/memory/forget` | 使用记忆 ID；成功前显示确认，成功后从本地视图移除。 |

记忆内容涉及隐私。不要把原始检索证据或内部关联图暴露给正常用户。

## 8. 需要确认的陪伴建议

当陪伴者建议影响现实生活的操作时，必须走两步确认，不能直接写入：

1. `POST /api/actions/preview`
2. 呈现用户可理解的影响、内容和取消入口
3. 用户明确确认后 `POST /api/actions/confirm`

请求形状：

```json
{
  "action": "create_task",
  "payload": {"title": "..."}
}
```

确认请求在同一对象上增加：

```json
{"confirmed": true}
```

当前支持的 action：`create_task`、`complete_task`、`start_focus_session`、`checkin_routine`、`draft_diary`。

公开响应只保留最终内容和业务 DTO，不包含 `role_thinking`、`role_action`、`system_thinking`、
`analysis`、`prompt`、`trace`、`ledger`、`jobs`、`export` 或原始数据库字段。

内部审计/Worker 路由即使在后端存在，也不属于浏览器公开边界，统一返回 `404`。

## 9. 前端验收清单

- 启动只读取必要数据：`/api/state?include=history`；Today、记忆、来信等按用户打开的空间懒加载。
- 不对任何写操作做“已完成”的假乐观状态；可以显示进行中，但结果以服务端响应为准。
- 所有失败都具备局部、安静的错误与重试状态，且不丢失草稿。
- 常规导航不出现 ledger、trace、jobs、export、worker/proactive tick。
- 浏览器网络响应不得出现内部字段；服务重启后聊天历史、记忆和生活流数据仍可读。
- 使用固定 `Idempotency-Key` 重试写请求不会重复创建任务、来信或确认动作。
- 先做静态体验时，使用 fixture 和上述展示模型；真实联调默认不带 `?mode=fixture`。
