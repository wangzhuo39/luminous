# 栖光 luminous 当前进度与缺口审计

初版：2026-07-23

> 状态说明：本文是陪伴生活流实施前的差距基线，保留用于理解当时的决策背景；其中“日程、日记、任务/打卡、网页入口尚未产品化”等表述已不再适用。当前能力以 [项目总览](../project_overview.md) 和 [规划状态](../planning/README.md) 为准。

本文对照 [ai_companion_landscape.md](ai_companion_landscape.md)，记录 **栖光 luminous** 当时 AI 伴侣底座的完成情况与缺口。

栖光，是在某个人身边停驻的一束光。`role-play` 仍是仓库名，训练管线仍是人格/模型底座；产品主线已经切换到情感陪伴运行时。

结论先行：

1. **P0 底座已经基本闭环**：长期记忆、状态引擎、主动联系、trace/outbox/worker、数据导出都已经从“雏形”进入“可跑、可测、可解释”的阶段。
2. **P1 已完成一半左右**：个人偏好记忆、时间线、open loops、主动节奏、记忆编辑/遗忘已经具备；但日记、重要日程、共同活动、多角色/多关系槽位还没有产品化。
3. **P2 基本还未开始**：语音、外呼/接听、屏幕/OCR、传感器、位置/天气/日程等现实上下文入口尚未落地。
4. **P3 是明确后续方向**：共读、共听歌、任务奖励、纪念物、伴侣空间、Live2D/VRM 仍处于规划阶段。
5. 当前网页端已经适合作为测试入口；后续转 app / Live2D 时，现有后端底座不需要推倒重来。

## 1. 当前已完成的核心能力

### 1.1 长期记忆系统

对照 landscape 中的 P0「长期记忆：原文记录、事实记忆、主题记忆、事件记忆、可检索原句」，当前已经完成：

- SQLite runtime store。
- L0 原文层：`raw_messages`。
- L1 记忆抽取：`MemoryExtractor` 支持 LLM 抽取与启发式 fallback。
- L2/L3/L4 consolidation：`consolidate_memories()` 会生成画像层、主题线程层、长期归档层。
- 原文证据层：`memory_evidence` 保存 `source_event_id`、`source_excerpt`、`evidence_quote`、quote span、trace。
- 记忆图谱/线程：`memory_threads`、`memory_links`。
- FTS5/BM25 风格检索 fallback。
- 记忆编辑、软遗忘、硬删除、导出。
- memory guard：重复、冲突、修正、supersede 决策会进入 ledger。
- HTTP 能力：`/api/memory`、`/api/memory/threads`、`/api/memory/links`、`/api/memory/evidence`、`/api/memory/update`、`/api/memory/forget`、`/api/export`。

代表实现：

- [runtime_store.py](/home/wz/role-play/luminous/runtime/infrastructure/runtime_store.py)
- [memory.py](/home/wz/role-play/luminous/runtime/domain/memory.py)
- [memory_extractor.py](/home/wz/role-play/luminous/runtime/application/memory_extractor.py)

当前剩余缺口：

- 还没有 embedding/vector 检索，只是 FTS5 + 规则打分。
- 记忆召回反馈还没有独立 `memory_feedback` 表；目前更多通过 outbox feedback / ledger 间接观察。
- Dream Loop 还偏确定性规则，没有 LLM 反思式整理。
- 缺少记忆审计 UI / 可视化图谱。

### 1.2 State Engine

对照 landscape 中的 P0「关系状态、情绪状态、安全层」以及 AI Companion Runtime 的运行时骨架，当前已经完成：

- `StateEngine` 作为确定性状态权威。
- 独立 analyzer pipeline：
  - `IntentAnalyzer`
  - `EmotionAnalyzer`
  - `RelationshipAnalyzer`
  - `SceneAnalyzer`
  - `MemorySignalAnalyzer`
  - `RiskAnalyzer`
- `AnalyzerOutput` 和 `StateTransition`，每次状态变化都有 reason、evidence、changed fields。
- `CompanionState` 已扩展：
  - `user_affect`
  - `companion_affect`
  - `relationship_arc`
  - `attachment`
  - `drives`
  - `interaction_rhythm`
  - `open_loops`
  - `timeline`
  - `proactive_readiness`
- `risk` 已从 stub 升级为分层判定：
  - `normal` -> `risk_level=low`
  - `watch` -> `risk_level=elevated`
  - `hold` -> `risk_level=high`
- high risk 会阻断普通主动联系。
- 主动联系反馈会反向更新 state。
- 时间流逝会触发 state decay。

代表实现：

- [state_engine.py](/home/wz/role-play/luminous/runtime/application/state_engine.py)
- [state.py](/home/wz/role-play/luminous/runtime/domain/state.py)

当前剩余缺口：

- 风险层还不是完整 safety policy，只是 runtime risk engine；还缺危机响应模板、现实支持策略、边界政策文档和更系统的测试集。
- scene context 目前主要来自文本和时间；还没有设备、日程、位置、天气等真实上下文。
- 状态可视化回放还没有前端。
- emotion / intent / scene 仍是规则分析器，后续可以加入轻量模型或 LLM judge 作为辅助信号。

### 1.3 主动联系机制

对照 landscape 中的 P0「主动节奏」以及 revive-companion / dylan-heartbeat，当前已经完成：

- `ProactiveEngine` 生成结构化 `ProactiveSignal`。
- due / hold 原因可追溯。
- DND、quiet hours、cooldown、高风险 hold。
- Bayesian-like `UserAvailabilityEstimate`：
  - busy probability
  - sleep probability
  - available probability
  - support probability
  - confidence / evidence
- Poisson / longing 风格概率触达：
  - `touch_probability`
  - `probability_roll`
  - `probability_floor`
  - `sure_threshold`
- open loops / memory anchors 参与主动联系。
- outbox 存储主动消息。
- webhook / Telegram / Bark 通知桥。
- 投递 receipt 和用户 feedback 记录。
- feedback 会影响后续主动联系容忍度、DND 和 relationship/state。

代表实现：

- [proactive_engine.py](/home/wz/role-play/luminous/runtime/application/proactive_engine.py)
- [notification_bridge.py](/home/wz/role-play/luminous/runtime/application/notification_bridge.py)
- [runtime.py](/home/wz/role-play/luminous/runtime/application/runtime.py)

当前剩余缺口：

- Web Push / 手机原生通知未实现。
- 主动联系 A/B 测试与长期效果指标未实现。
- 没有日程/纪念日/地点等真实生活信号，所以主动联系还不能真正做到“现实感知”。
- 外部通知已支持，但网页端 UI 还没有完整的通知权限、订阅和设置页。

### 1.4 Prompt Builder / Context Budget

对照 landscape 中的「不要把所有记忆塞进 prompt，而是先给菜单、必要时展开证据」，当前已经完成：

- 独立 `PromptBuilder`。
- `PromptPackage` 包含：
  - state brief
  - relationship brief
  - memory menu
  - expanded memory evidence
  - recent event brief
  - response strategy
  - output contract
  - budget metadata
- Prompt 会注入 relationship arc、attachment、drives。
- 记忆默认以目录形式进入上下文，必要证据才展开。

代表实现：

- [prompt_builder.py](/home/wz/role-play/luminous/runtime/application/prompt_builder.py)

当前剩余缺口：

- 还没有模型可主动调用的 recall tool；目前是 runtime 预先 surface。
- context budget manager 仍是字符预算，不是 token-aware。
- 缺少不同场景下的 prompt 选择评测。

### 1.5 Worker / Runtime / Trace

当前已经完成：

- `CompanionRuntime` 编排 chat、memory、state、proactive、ledger。
- `CompanionWorker` 支持周期任务：
  - `state_decay_tick`
  - `proactive_tick`
  - `outbox_delivery`
  - `memory_consolidation`
  - `memory_reindex`
- ledger / trace 可查询。
- raw messages、events、jobs、outbox 可导出。
- HTTP API 已覆盖当前网页测试需要。

代表实现：

- [runtime.py](/home/wz/role-play/luminous/runtime/application/runtime.py)
- [worker.py](/home/wz/role-play/luminous/runtime/worker.py)
- [http.py](/home/wz/role-play/luminous/runtime/infrastructure/http.py)

当前剩余缺口：

- trace viewer / 调试面板没有前端。
- 成本、token、延迟统计不完整。
- worker 还不是生产级常驻服务，没有多实例调度协调、告警和健康监控。

## 2. 对照 landscape 的 P0-P3 完成度

| 层级 | landscape 功能 | 当前状态 | 判断 |
|---|---|---|---|
| P0 | 长期记忆：原文、事实、主题、事件、可检索原句 | L0-L4、evidence、threads/links、FTS5、编辑/遗忘/导出已完成 | 基本完成 |
| P0 | 关系状态：亲密度、信任、依赖、边界、共同历史 | relationship、relationship_arc、attachment、timeline 已完成 | 基本完成 |
| P0 | 情绪状态：mood、疲劳、兴奋、低落、稳定度 | user_affect、companion_affect、emotion analyzer 已完成 | 基本完成 |
| P0 | 主动节奏：心跳、低频打招呼、纪念日、长时间未互动关怀 | proactive tick、worker、outbox、通知、idle check 已完成；纪念日未完成 | 部分完成 |
| P0 | 数据主权：导入/导出、备份、迁移、审计 | 导出、编辑、遗忘、证据审计已完成；导入/迁移 UI 未完成 | 部分完成 |
| P0 | 安全层：风险识别、越界提醒、可回溯 trace | 分层 risk engine、trace、high-risk hold 已完成；完整 safety policy 未完成 | 部分完成 |
| P1 | 日记 / 时间线 / 重要日程 | timeline/open loops 已有；日记和日程未产品化 | 部分完成 |
| P1 | 睡前问候、早安、饭点提醒 | 可由 proactive signal 承载，但没有专门 reminder 类型 | 部分完成 |
| P1 | 共读、共听歌、共同任务、共同打卡 | 未实现 | 未开始 |
| P1 | 个人偏好记忆 | 已实现 preference / boundary / relationship memory | 基本完成 |
| P1 | 多角色 / 多关系槽位 | 未实现 | 未开始 |
| P1 | 记忆编辑与遗忘控制 | 已实现 API；缺前端管理页 | 部分完成 |
| P2 | 语音对话 | 未实现 | 未开始 |
| P2 | 外呼 / 接听 / 语音信箱 | 未实现 | 未开始 |
| P2 | 屏幕感知、OCR、网页/应用上下文 | 未实现 | 未开始 |
| P2 | 语气识别、情绪识别、心率/活动等传感器 | 未实现 | 未开始 |
| P2 | 位置 / 天气 / 通勤 / 日程等生活上下文 | 未实现 | 未开始 |
| P3 | 共读、批注、复盘 | 未实现 | 未开始 |
| P3 | 一起听歌、歌单 | 未实现 | 未开始 |
| P3 | 轻量任务和奖励系统 | 未实现 | 未开始 |
| P3 | 关系事件和纪念物 | 未实现 | 未开始 |
| P3 | 伴侣空间、桌宠、Live2D/VRM | 未实现 | 未开始 |

## 3. 当前最重要的未完成部分

按“离 AI 伴侣目标最近、且对后续 app/Live2D 有底座价值”的优先级排序：

### 3.1 前端管理与调试面板

后端已经有能力，但网页端还没有把这些能力产品化：

- 记忆列表、证据查看、编辑、遗忘。
- state dashboard：关系弧、依恋、驱动力、情绪曲线。
- proactive outbox：为什么发、为什么 hold、投递状态、用户反馈。
- trace viewer：一次对话里 memory / state / prompt / proactive 的完整链路。

这是下一步最应该做的，因为它能立刻提高调试效率，也为未来 app 提供信息架构。

### 3.2 Reminder / Calendar / 日常节奏层

当前 proactive 更像“想起你”的主动问候，还不是完整生活提醒：

- 纪念日。
- 日程。
- 饭点。
- 睡前/早安。
- 长 open loop 的自然追踪。

这部分适合参考 Aura、astrbot_plugin_private_companion、dylan-heartbeat。

### 3.3 评测入口

当前测试已经覆盖核心单元，但还没有公开数据集驱动的 companion eval：

- AMemGym：记忆写入/召回/使用。
- PersonaMem：用户偏好与画像演化。
- EmpatheticDialogues：情绪识别与回应策略。
- ProActEval / ProDial：何时主动、主动动作强度。

建议下一步先接 AMemGym 或做内部 `companion_scenarios.jsonl`，形成自动评测报告。

### 3.4 语音与具身壳

这是 P2/P3 的核心，但不应该早于调试面板：

- TTS/STT。
- Web 端语音模式。
- Live2D/VRM runtime bridge。
- avatar 状态由 `CompanionState` 驱动。

由于你后续想做自己的 app 和 Live2D，这部分最终要做，但现在先保持接口预留即可。

### 3.5 感知与现实上下文

当前 scene 只是文本 + 时间推断。未来要加入：

- 设备状态。
- 日程。
- 天气。
- 位置/通勤。
- 屏幕/OCR。
- 用户手动状态：忙碌、睡觉、勿扰、想被陪。

这会显著提升 proactive 的真实感，但也涉及隐私与授权，适合后置。

## 4. 与最初目标的关系

栖光的核心目标不是“把小说角色 prompt 成某个人”，而是做一个长期 AI 伴侣；小说角色拟合只是人格底座的一条路径。

按这个目标看，当前项目已经完成了 AI 伴侣的后端地基：

```text
模型人格 / adapter
  ↓
CompanionRuntime
  ↓
MemoryEngine + StateEngine + ProactiveEngine
  ↓
PromptBuilder / NotificationBridge / Worker / Ledger
  ↓
网页端测试入口
  ↓
未来 app + Live2D / VRM / voice / perception
```

也就是说：现在最关键的问题已经不是“有没有伴侣底层”，而是“如何把底层能力做成用户可见、可调试、可长期迭代的产品”。

## 5. 推荐下一步

### 下一步 1：做 Companion Console 网页调试台

优先级最高。建议新增或改造网页端页面：

- `/memory`：记忆、证据、编辑、遗忘、线程/链接。
- `/state`：state dashboard、关系弧、attachment、drives。
- `/proactive`：outbox、due/hold、通知状态、反馈。
- `/trace`：按 trace_id 查看完整链路。

### 下一步 2：做内部 companion 场景评测集

先不急着大规模接公开数据。建议先落：

- `evals/companion_scenarios.jsonl`
- `evals/companion_runtime_eval.py`

覆盖：

- 偏好变化。
- 边界修正。
- 孤独/疲惫/高风险。
- 久未联系。
- open loop 追踪。
- 记忆证据追溯。

之后再接 AMemGym。

### 下一步 3：补 Reminder / Calendar 抽象

把主动联系拆成：

- `checkin`
- `open_loop_followup`
- `reminder`
- `anniversary`
- `routine`
- `repair`

这样后续 app 通知和 Live2D 表现会更自然。

### 下一步 4：预留 avatar/voice bridge

先不要上复杂 Live2D，但可以定义：

- avatar mood。
- expression。
- motion。
- speaking state。
- voice style。

这些字段由 `CompanionState` 和回复结果驱动，未来网页端/app 都可复用。

## 6. 验证状态

当前完整回归：

```text
145 passed
```

后续如果进入前端管理台开发，需要补端到端测试或 API smoke test。
