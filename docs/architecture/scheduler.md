# Scheduler / Background Worker 设计

> 日期：2026-07-23  
> 关联：[companion_foundation_implementation_roadmap.md](./companion_foundation_implementation_roadmap.md)  
> 说明：本文只聚焦第五阶段的后台调度层；记忆、PromptBuilder、State Engine、主动联系的总设计请先看总路线图。

## 1. 为什么需要 Scheduler

AI 伴侣不能只在用户开口时才“活着”。  
如果没有后台调度，以下事情都会退化成手动触发：

- 记忆整理与去重
- 状态自然衰减
- 主动联系判断
- 提醒投递与重试
- 夜间 consolidation
- trace 压缩与归档

所以 Scheduler 的角色不是“定时器”，而是一个小型后台运行时：

```text
runtime state  ->  scheduled jobs  ->  handlers  ->  trace / outbox / memory / state
```

它要做的事情有三件：

1. 把时间变成可处理的事件。
2. 把事件变成幂等 job。
3. 把 job 结果写回 state / memory / ledger / outbox。

---

## 2. 当前实现形态

当前实现已经落成在代码里：

- `luminous/runtime/worker.py`
- `luminous/runtime/infrastructure/runtime_store.py`
- `luminous/runtime/application/runtime.py`
- `luminous/runtime/application/proactive_engine.py`

对应能力：

- `CompanionWorker.tick()`
- `CompanionWorker.run_once()`
- `CompanionRuntimeStore.enqueue_job()`
- `CompanionRuntimeStore.claim_due_jobs()`
- `CompanionRuntimeStore.complete_job()` / `fail_job()`
- `CompanionRuntimeStore.consolidate_memories()`
- `CompanionRuntimeStore.reindex_memories()`
- `CompanionRuntime.proactive_tick(send=True/False)`
- `CompanionRuntime.state_engine.apply_time_decay()`

---

## 3. 设计目标

Scheduler 要满足这些目标：

- **幂等**：同一个时间窗口的 job 只能被执行一次。
- **可恢复**：worker 重启后可继续处理未完成 job。
- **可审计**：每次执行都要进 trace / ledger。
- **可扩展**：未来可以接 APScheduler / Celery / RQ / 独立守护进程。
- **低耦合**：业务逻辑不写在 cron 里，而写在 handler 里。
- **可降级**：没有 FTS5、没有外部队列、没有通知通道时，核心仍可运行。

---

## 4. 核心概念

### 4.1 Job

Job 是一个可执行单元，代表“在某个时刻应该发生的一件事”。

当前 job 类型：

| job_type | 作用 |
| --- | --- |
| `state_decay_tick` | 状态自然衰减、牵挂/疲劳/支持需求的时间推进 |
| `proactive_tick` | 判断是否需要主动联系 |
| `outbox_delivery` | 处理待投递消息 |
| `memory_consolidation` | 合并重复记忆、整理线程 |
| `memory_reindex` | 重建记忆索引 |
| `post_chat_memory_extract` | 对话后记忆抽取（当前主链路已内联，这个 job 作为兼容位保留） |

### 4.1.1 proactive_tick 的概率 gate

`proactive_tick` 不是简单 cron 阈值。当前实现会先计算：

- `opportunity`：长时间未联系带来的 Poisson-like 机会值
- `relationship_permission`：信任、亲密、熟悉、边界带来的触达许可
- `value`：support_need、longing、open_loop、recent_support 带来的本次价值
- `availability`：Bayesian-like 用户可用性估计，包含 busy / sleep / available / support probability
- `touch_probability`：综合 score、opportunity、value、relationship、attachment、initiative 得到的触达概率
- `probability_roll`：基于 trace/time/state 的可复现 roll

高价值场景会进入 `high_utility_ready`，稳定触达；边界场景则可能通过 `probabilistic_touch` 触发。未触发时 reason 会是 `probability_wait` 或 DND/quiet/cooldown/likely_busy/likely_sleeping 等明确 hold reason。

`availability` 当前使用时间先验、`state.user_context.likely_busy`、`interaction_rhythm.reply_latency_avg_minutes`、最近主动联系反馈和情绪支持需求综合估计。它不是最终版传感器融合，但已经能做到：

- 用户明显忙且支持需求不高时 hold；
- 用户需要支持时，不会因为“可能在忙”的先验直接错杀；
- 每次估计的 label、概率和证据都进入 trace。

### 4.2 Outbox

Outbox 是主动联系与通知投递的中间层。

它解决的问题是：

- 先生成草稿，再决定是否发送。
- 发送失败可以重试。
- 投递状态可以审计。
- 已有真实渠道适配层，接 webhook / Telegram / Bark 时不需要改 proactive 逻辑。

当前可配置的外部通知渠道：

```env
# 通用 webhook，适合自建网关、n8n、企业机器人等
ROLE_PLAY_NOTIFY_CHANNEL=webhook
ROLE_PLAY_NOTIFY_WEBHOOK_URL=https://example.com/notify

# Telegram Bot
ROLE_PLAY_NOTIFY_CHANNEL=telegram
ROLE_PLAY_NOTIFY_TELEGRAM_BOT_TOKEN=123456:token
ROLE_PLAY_NOTIFY_TELEGRAM_CHAT_ID=123456789

# Bark，建议填到 device_key 这一层
ROLE_PLAY_NOTIFY_CHANNEL=bark
ROLE_PLAY_NOTIFY_BARK_URL=https://api.day.app/<device_key>

ROLE_PLAY_NOTIFY_TIMEOUT=10
ROLE_PLAY_NOTIFY_ENABLED=true
```

### 4.3 Trace / Ledger

Scheduler 产生的每个 job 执行，都要进 ledger：

- `worker_job_completed`
- `worker_job_failed`
- `state_decay_tick`
- `outbox_delivery`
- `proactive_decision`

这样后续才能回答：

- 为什么这条主动消息发出去了？
- 为什么这次没发？
- 为什么状态变了？
- 为什么某条任务失败了？

---

## 5. 数据结构

### 5.1 jobs

SQLite 表：`jobs`

| 字段 | 作用 |
| --- | --- |
| `job_id` | 主键 |
| `job_type` | job 类型 |
| `payload_json` | job 参数 |
| `status` | queued / running / succeeded / failed |
| `run_after` | 允许执行的时间 |
| `locked_until` | lease 截止时间 |
| `attempts` | 已尝试次数 |
| `max_attempts` | 最大重试次数 |
| `idempotency_key` | 幂等键 |
| `last_error` | 最近错误 |
| `created_at` / `updated_at` | 记录时间 |

### 5.2 outbox

SQLite 表：`outbox`

| 字段 | 作用 |
| --- | --- |
| `message_id` | 主键 |
| `signal_id` | 主动联系信号或任务来源 |
| `trace_id` | 链路 trace |
| `channel` | 发送渠道 |
| `draft_text` | 草稿正文 |
| `status` | drafted / sent / failed / replied / canceled |
| `score` | 主动触发分数 |
| `reason` | 为什么触发 |
| `signal_type` | silence_checkin / emotional_followup / ... |
| `anchor_memory_ids_json` | 依据了哪些记忆 |
| `payload_json` | 原始上下文 |

`payload_json.delivery_receipts` 记录外部渠道和浏览器通知的投递回执，例如
`notification_delivered`、`notification_failed`、`browser_notification_created`。

### 5.3 events / raw_messages / memory_items

这些不由 Scheduler 独占，但 Scheduler 会写入：

- `events`：job 执行 trace
- `raw_messages`：来自 chat 的原文层
- `memory_items`：consolidation / extraction 结果

---

## 6. Job 生命周期

```text
enqueue
  -> queued
  -> claim
  -> running
  -> succeed / fail
  -> trace
  -> optionally outbox/state/memory update
```

### 6.1 enqueue

通过 `CompanionRuntimeStore.enqueue_job()`。

要求：

- 传入 `job_type`
- 传入 `payload`
- 传入 `run_after`
- 传入 `idempotency_key`

同一个幂等键重复 enqueue，不应该生成重复工作。

### 6.2 claim

通过 `CompanionRuntimeStore.claim_due_jobs()`。

只会领取：

- status = queued
- run_after <= now
- attempts < max_attempts
- 未被 lease 住

### 6.3 execute

通过 `CompanionWorker._run_job()`。

失败不影响其他 job；每个 job 单独 try/except。

### 6.4 complete / fail

通过 `complete_job()` / `fail_job()` 更新状态。

然后写入 trace 事件。

---

## 7. 执行流程

### 7.1 定时 tick

`CompanionWorker.tick()` 的流程：

1. 按 cadence 预先 enqueue 周期 job。
2. claim 到期 job。
3. 逐个执行。
4. 把结果写回 job 表和 trace。
5. 返回本轮摘要。

### 7.2 手动 run_once

`CompanionWorker.run_once(job_type)` 适合开发和测试：

- 直接跑一类任务。
- 不依赖守护进程。
- 便于单步验证 memory/state/proactive。

---

## 8. 周期策略

当前实现的默认 cadence：

| job_type | cadence |
| --- | --- |
| `state_decay_tick` | 60 分钟 |
| `proactive_tick` | 30 分钟 |
| `outbox_delivery` | 15 分钟 |
| `memory_consolidation` | 24 小时 |
| `memory_reindex` | 24 小时 |

这些 cadence 不是硬编码真理，只是一个适合本项目的初始值。

后续可按用户行为动态调整：

- 夜间减少主动联系频率
- 高支持需求用户缩短 decay 周期
- 长对话用户提高 consolidation 频率

---

## 9. 与 CompanionRuntime 的关系

Scheduler 不是另一个系统，而是 CompanionRuntime 的后台面。

它们之间的边界是：

- `CompanionRuntime`：处理一次聊天 / 一次主动判断。
- `CompanionWorker`：处理时间流逝后的后台工作。

共享的核心能力：

- `StateEngine`
- `MemoryEngine` / `RuntimeStore`
- `ProactiveEngine`
- `Trace / Ledger`

---

## 10. 与 PromptBuilder 的关系

Scheduler 不直接拼 prompt。  
如果 job 需要调用模型，它应该走 runtime 的标准链路：

```text
state + memory + context
  -> PromptBuilder
  -> ModelClient
```

这样可以保证：

- chat 和后台 job 用同一套上下文逻辑
- 微调模型接入时只改 adapter
- trace 能复用同一份 prompt package

---

## 11. API / CLI 暴露

### 11.1 CLI

当前入口：

```bash
luminous-worker --once
luminous-worker --job proactive_tick
luminous-worker
```

参数：

- `--once`：跑一轮后退出
- `--job`：直接执行指定 job
- `--interval`：常驻模式 tick 间隔
- `--mock`：不用真实 LLM

### 11.2 HTTP

当前 HTTP 接口：

- `POST /api/proactive/tick`
- `POST /api/worker/tick`
- `GET /api/jobs`
- `GET /api/outbox`
- `POST /api/outbox/receipt`
- `POST /api/outbox/feedback`

这些接口主要用于 demo / 调试，不是最终生产形态。

---

## 12. 现阶段已完成什么

已完成：

- SQLite runtime store
- jobs / outbox schema
- proactive decision trace
- webhook / Telegram / Bark 通知适配
- outbox delivery receipts
- state decay handler
- memory consolidation / reindex handler
- worker CLI
- HTTP 调试入口

还可以继续增强：

- 真实渠道投递（Push / Telegram / Bark / 站内通知）
- 更细的 job 优先级队列
- cron 配置外置化
- 任务重试退避
- 数据导出 / 管理 UI
- 更完整的时间感知和日历感知

---

## 13. 设计原则

1. **job 是事件，不是副作用本身。**
2. **handler 可以失败，状态不能乱。**
3. **主动联系先写 outbox，再谈发送。**
4. **每一次后台动作都要能解释。**
5. **Scheduler 只负责时间和执行，不负责人格。**

---

## 14. 下一步建议

如果要继续推进，优先级建议：

1. 把 outbox 接到真实渠道。
2. 给 jobs 加优先级和 backoff。
3. 把 consolidation 做成真正的线程/图谱整理。
4. 把 Scheduler 的 tick 频率外置为配置。
5. 给 worker 增加 dashboard / health endpoint。
