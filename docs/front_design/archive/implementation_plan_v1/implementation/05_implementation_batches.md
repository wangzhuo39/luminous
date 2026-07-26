# 05 Implementation Batches

## Batch A：视觉骨架

目标：

- 拆掉三栏首屏。
- 建立 `ImmersiveStage`。
- 建立人物主体、背景、光效、字幕区、凝露输入。
- 暂时允许部分功能入口只打开占位 overlay。

必须保留：

- `/api/chat` 调用
- 输入发送
- mock 模式可用

验收：

- 首屏不再像 dashboard。
- 390x844 不遮挡人物脸和输入。
- 不出现密集聊天气泡。

## Batch B：Chat / State / Presence

目标：

- 接回 `POST /api/chat`。
- 接回 `GET /api/state`。
- 实现 `SubtitleDialogue`、`AirInput`、`PresenceHalo`。

验收：

- `role_action` 与 `reply` 正确显示。
- `role_thinking` 默认折叠。
- `system_thinking` 不在 DOM。
- loading / error / retry 可用。

## Batch C：Outbox / Memory

目标：

- 实现 `OutboxGlint`。
- 实现 `MemoryConstellation`。
- 接回 memory threads / links / evidence。
- 接回 feedback / receipt / forget / export。

验收：

- 主动联系不弹窗打扰。
- DND 下静默。
- 记忆可查看、编辑、遗忘、导出。

## Batch D：Today / Scheduling / Life Flow

目标：

- 实现 `TodaySheet`。
- 接回 reminders、calendar events、notification settings。
- 接回 tasks、routines、activities、diary。
- 接回 actions preview / confirm。

验收：

- 今日页不是任务 dashboard。
- 提醒/日程/任务/打卡/活动/日记都可达。
- 具有现实影响的动作有确认。

## Batch E：Audit / A11y / Polish

目标：

- 实现 `PrivacyAuditDrawer`。
- 实现 `DebugTracePanel`。
- 接回 `/api/trace`、`/api/ledger`、`/api/jobs`。
- 完成移动端、键盘、ARIA、reduced motion、弱网和性能打磨。

验收：

- debug 默认深层隐藏。
- trace / ledger / jobs 可审计。
- 390x844 通过。
- reduced motion 通过。
- 弱网和服务端错误不破坏主体验。
