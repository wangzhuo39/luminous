# 栖光 luminous 项目总览

栖光，是在某个人身边停驻的一束光。

`luminous` 是当前项目的产品名和英文名。项目当前阶段已经从“为小说角色制作训练数据”转向“实现长期情感陪伴 AI 伴侣底座”。训练管线仍然保留，但它现在服务于模型人格底座；产品主线是 `luminous/runtime/` 中的 companion runtime。

## 1. 项目目标

栖光要做的不是一个普通聊天页，也不是 prompt 驱动的一次性角色扮演。

目标是做一个长期 AI 伴侣系统：

- 人格稳定：角色性格尽量训练进模型内部，而不是靠长 prompt 临时塑形。
- 关系连续：能记住用户、理解边界、累积信任、识别关系变化。
- 情绪承接：能根据用户状态调整回应节奏，而不是机械问答。
- 主动但克制：会在合适的时候想起用户，也知道什么时候不该打扰。
- 可审计：记忆、状态变化、主动联系和模型上下文都能追溯。
- 可扩展：当前先做网页端，后续可迁移到 app、Live2D/VRM、语音和伴侣空间。

## 2. 当前阶段

当前已经进入“情感陪伴底座实现阶段”。

已经完成的主干能力：

- Memory：L0-L4 分层记忆、原文证据、threads/links、编辑/遗忘/导出。
- State Engine：intent / emotion / relationship / scene / memory signal / risk analyzers，关系弧、依恋、驱动力和可解释状态转移。
- Proactive：主动联系评分、DND、cooldown、用户可用性估计、概率触达、outbox、通知和反馈学习。
- PromptBuilder：state brief、relationship brief、memory menu、必要证据展开、输出协议和预算。
- Scheduling：提醒、日历、通知偏好、DND、重复规则与幂等投递。
- Life Flow：任务与步骤、例行与打卡、活动会话、日记、统一时间线和 Today 聚合。
- Worker：状态衰减、主动 tick、outbox 投递、记忆整理、reindex、例行到期与活动过期处理。
- Trace / Ledger：对话、记忆、状态、主动联系和 worker job 都有事件记录。
- Frontend S1–S5：晶格温室主场景、核心陪伴、Today 生活流、Outbox/Memory/Privacy 静默空间，以及可安装 PWA、静态离线壳、空间深链和未发送草稿恢复。

当前仍未完成的产品层能力：

- 浏览器系统通知、Push/VAPID 与通知资源深链；当前无订阅和安全投递契约，前端没有请求权限或伪造能力。
- 共读、共听歌等内容型共享活动；共同任务与日常打卡已具备基础闭环。
- 多角色 / 多关系槽位。
- 语音、外呼、语音信箱。
- 屏幕/OCR、位置、天气、日程、传感器等现实上下文。
- Live2D / VRM / app 壳层。

当前规划状态见 [docs/planning/README.md](planning/README.md)；调研基线和历史差距审计见 [docs/research/](research/)。

## 3. 系统分层

```text
模型人格 / 角色 adapter
  ↓
CompanionRuntime
  ↓
MemoryEngine + StateEngine + ProactiveEngine
  ↓
PromptBuilder + NotificationBridge + Worker + Ledger
  ↓
晶格温室网页端 / PWA 壳层
  ↓
未来 app / Live2D / Voice / Perception
```

### 3.1 人格与模型层

小说角色拟合仍然重要。它负责把叶筝这类角色的身份边界、心理逻辑、语气和行为模式训练进模型内部。

相关目录：

- `luminous/training/pipeline/`
- `luminous/training/data/`
- `luminous/training/finetune/`
- `docs/training/`

### 3.2 Companion Runtime

这是当前项目主线。

相关目录：

- `luminous/runtime/domain/`
- `luminous/runtime/application/`
- `luminous/runtime/infrastructure/`
- `luminous/runtime/worker.py`

核心职责：

- 保存长期状态。
- 召回和整理记忆。
- 更新关系/情绪/风险状态。
- 构建给 LLM 的上下文。
- 决定是否主动联系。
- 投递通知和接收反馈。
- 记录 trace 和导出用户数据。

### 3.3 Web / App 壳层

当前 `apps/companion-web/` 已是可运行的单文档网页端：包含核心对话、生活流、静默空间、PWA 安装、静态离线壳和空间级 URL。它仍不是最终平台边界，后续可以扩展或迁移为：

- app。
- Live2D / VRM。
- 语音 UI。
- 桌宠。
- 伴侣空间。

后端运行时应保持前端无关。

网页端只通过 adapter 白名单消费用户可见 DTO；内部 thinking、prompt、trace、memory evidence 和 raw response 不进入普通 UI、AppState 或 storage。完整前端状态见 [front_design/README.md](front_design/README.md)。

## 4. 当前 API

常用 API：

- `POST /api/chat`
- `GET /api/state`
- `GET /api/memory`
- `GET /api/memory/threads`
- `GET /api/memory/links`
- `GET /api/memory/evidence`
- `POST /api/memory/update`
- `POST /api/memory/forget`
- `GET /api/ledger`
- `GET /api/trace`
- `GET /api/outbox`
- `POST /api/proactive/tick`
- `POST /api/outbox/feedback`
- `POST /api/outbox/receipt`
- `GET /api/jobs`
- `GET /api/export`
- `GET/POST /api/reminders`
- `PATCH/DELETE /api/reminders/{id}`
- `POST /api/reminders/{id}/snooze`
- `POST /api/reminders/{id}/complete`
- `POST /api/reminders/{id}/cancel`
- `GET/POST /api/calendar-events`
- `PATCH/DELETE /api/calendar-events/{id}`
- `GET/PATCH /api/settings/notifications`
- `GET /api/today`
- `GET /api/timeline`
- `GET/POST /api/tasks`
- `GET/PATCH/DELETE /api/tasks/{id}`
- `POST /api/tasks/{id}/steps`
- `PATCH /api/tasks/{id}/steps/{step_id}`
- `POST /api/tasks/{id}/start|complete|block|cancel`
- `GET/POST /api/routines`
- `GET/PATCH/DELETE /api/routines/{id}`
- `POST /api/routines/{id}/checkins`
- `GET/POST /api/activities`
- `GET /api/activities/{id}`
- `POST /api/activities/{id}/start|pause|resume|complete|cancel`
- `GET/POST /api/diary-entries`
- `GET/PATCH/DELETE /api/diary-entries/{id}`
- `POST /api/diary-entries/draft`
- `POST /api/actions/preview`
- `POST /api/actions/confirm`

启动方式：

```bash
luminous-api --host 127.0.0.1 --port 8000
```

本地 mock：

```bash
luminous-api --host 127.0.0.1 --port 8000 --mock
```

## 5. 文档阅读顺序

如果你要理解当前产品主线：

1. [docs/product/luminous_identity.md](product/luminous_identity.md)
2. [docs/research/ai_companion_progress_gap_audit.md](research/ai_companion_progress_gap_audit.md)
3. [docs/research/ai_companion_landscape.md](research/ai_companion_landscape.md)
4. [docs/architecture/roleplay_companion_architecture.md](architecture/roleplay_companion_architecture.md)
5. [docs/architecture/companion_foundation_implementation_roadmap.md](architecture/companion_foundation_implementation_roadmap.md)
6. [docs/front_design/README.md](front_design/README.md)
7. [docs/front_design/FRONTEND_AGENT_HANDOFF.md](front_design/FRONTEND_AGENT_HANDOFF.md)
8. [docs/front_design/frontend_architecture_v1.md](front_design/frontend_architecture_v1.md)

如果你要理解模型人格训练底座：

1. [docs/training/her_pipeline_analysis.md](training/her_pipeline_analysis.md)
2. [docs/training/modular_message_pipeline.md](training/modular_message_pipeline.md)
3. [docs/cli_reference.md](cli_reference.md)
4. [docs/training/qwen3_7b_sft_preparation.md](training/qwen3_7b_sft_preparation.md)

## 6. 当前判断

栖光的底层方向已经从“能不能做出角色样本”转为“能不能形成长期陪伴关系”。

当前基础功能和 S1–S5 网页端已可端到端运行。下一轮尚未批准；共读、数据迁移、系统通知、Push、账号同步和公开部署均需新的产品需求与后端安全契约，不能仅靠前端本地状态补齐。

完整状态与候选边界见 [docs/planning/README.md](planning/README.md)。
