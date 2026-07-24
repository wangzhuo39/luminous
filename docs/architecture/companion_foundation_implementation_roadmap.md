# 栖光 luminous 伴侣底座五阶段实现路线图

> 日期：2026-07-23  
> 关联文档：[docs/research/final.md](../research/final.md)、[roleplay_companion_architecture.md](./roleplay_companion_architecture.md)

本文回答一个具体问题：`final.md` 里总结的缺失，尤其是记忆、完整 state engine、主动联系机制、PromptBuilder，应该按什么顺序实现；每一步参考哪些开源项目；最终在 **栖光 luminous** 中应该落成什么。

栖光是当前产品名，含义是“在某个人身边停驻的一束光”。`role-play` 仍是仓库名；训练管线提供人格/模型底座，本文聚焦情感陪伴运行时。

结论先行：

1. **Memory v2**
2. **PromptBuilder / Context Budget Manager**
3. **完整 State Engine**
4. **主动联系机制 v2**
5. **Scheduler / Background Worker**

安全和数据管理可以后置，但前四阶段的 schema 要预留 `risk_level`、`consent_scope`、`provenance`、`delete_state`、`audit_trace` 等字段，避免后续大重构。

---

## 0. 参考项目分层

这些项目可以分成两类：一类回答“AI 伴侣最终像什么”，另一类回答“底层工程怎么做”。

### 0.1 伴侣 / 数字生命类项目

| 项目 | 我们主要参考什么 | 对 `role-play` 的意义 |
| --- | --- | --- |
| [awesome-ai-companion](https://github.com/DasterProkio/awesome-ai-companion) | 伴侣生态总览：前端、后台心跳、记忆、身份、情绪状态、硬件/世界集成 | 用作功能地图，不直接照抄单项目 |
| [Aura](https://github.com/gqy20/Aura) | Android 伴侣闭环、长期记忆、Dream Loop、情绪状态机、关系模型、PromptBuilder | 很贴近“AI 伴侣产品”的目标，可以参考它的模块切分 |
| [AI Companion Runtime](https://github.com/yf0522/ai-companion-runtime) | intent / emotion / risk / memory / prompt builder / trace 的运行时管线 | 参考它的运行时顺序、风险门控和可观测性 |
| [revive-companion](https://github.com/pearthink123/revive-companion) | Poisson 主动触达、Bayesian 用户状态估计、quiet hours、回复反馈 | 主动联系机制最值得借鉴的项目 |
| [Alive-AI](https://github.com/vindepemarte/alive-ai) | 持续内在状态循环、layered memory compiler、inner-state compiler、proactive arbiter | 参考“像活着一样”的运行时状态和主动冲动仲裁 |
| [Waveary](https://github.com/K2st0r/Waveary) | continuity runtime：memory / relationship / emotion / timeline / voice / tools；SQLite + JSON archive | 参考最终层级架构和可迁移伴侣档案 |
| [Aethrion](https://github.com/simulacre7/aethrion) | 把权威状态放在 runtime，而不是让 LLM 即兴决定；事件驱动、规则系统、scheduler | 参考 State Engine 的工程边界 |
| [Nūr](https://github.com/balfiky/nur) | persistent state、relationship arc、beliefs、drives、affective modulators、open questions | 参考关系弧、未完成事项、自我演化状态 |

### 0.2 记忆 / Agent runtime 基建类项目

| 项目 | 我们主要参考什么 | 对 `role-play` 的意义 |
| --- | --- | --- |
| [Paramecium](https://github.com/Shitsuten/paramecium) | L0 原文归档、L1 摘录必须带逐字证据、supersede 不删除、FTS5 / BM25 / 向量混合检索、先给记忆目录再 recall 原文 | Memory v2 的核心参考 |
| [AgentMemory](https://github.com/smysle/agent-memory) | SQLite-first、typed memories、Write Guard、BM25-only fallback、hybrid recall、surface、reflect/reindex/feedback lifecycle | 记忆工程化生命周期的核心参考 |
| [Mem0](https://github.com/mem0ai/mem0) | User / Session / Agent 多层记忆、entity linking、多信号检索、temporal reasoning | 参考多信号召回和时序记忆 |
| [Memind](https://github.com/openmemind/memind) | raw context → structured memory → insight tree / graph / thread；compile context | 参考长期后续：记忆图谱、事件线、上下文包 |
| [Letta](https://github.com/letta-ai/letta) | Stateful agents、可学习/自我改进 memory runtime | 参考“模型外部状态长期存在”的产品边界 |

---

## 1. 阶段一：Memory v2

### 1.1 为什么第一阶段先做记忆

AI 伴侣的底层不是“每轮回答得温柔”，而是“长期连续地认识用户”。  
没有可信记忆，State Engine 会变成凭空估计；PromptBuilder 只能拼最近几轮；主动联系也只能按 idle 时间做粗糙触发。

记忆必须先成为“事实源”和“上下文供应系统”。

### 1.2 参考项目

| 参考项目 | 借鉴机制 | 具体落地方式 |
| --- | --- | --- |
| Paramecium | 原文不可丢；抽取记忆必须带逐字证据；召回先给目录，必要时再翻原文；supersede 旧记忆但不删除 | 每条 `MemoryItem` 必须绑定 `MemoryEvidence`；LLM 抽取后做 quote verification；旧记忆被替代时进入 `superseded`，不物理删除 |
| AgentMemory | SQLite-first；typed memory；Write Guard；BM25 fallback；recall/surface；reflect/reindex/feedback | 用 SQLite 替换 JSONL 主存储；先实现 FTS5/BM25，再接 embedding；将 `recall` 与 `surface` 分成两个接口 |
| Mem0 | User / Session / Agent state，多信号检索，entity linking，temporal reasoning | 记忆 schema 区分 `user`、`companion`、`relationship`、`session`；检索时融合关键词、时间、实体和使用反馈 |
| Memind | raw context、memory items、memory threads、insight tree、graph expansion | 先预留 `memory_threads`、`memory_links` 表；后续做事件线和关系图 |
| Aura | 对话后即时 insight、Dream Loop、MemoryRepository prompt selection | 第一阶段先做 post-chat extractor；第五阶段再做 Dream Loop / consolidation worker |

### 1.3 最终要实现什么

实现一个 `CompanionMemoryEngine`，它不是 RAG 插件，而是伴侣的长期认知层。

#### 数据层

建议使用 SQLite 作为 live runtime store：

| 表 | 作用 |
| --- | --- |
| `events` | 所有运行时事件，作为 trace/ledger 的主干 |
| `raw_messages` | L0 原文层：用户和 AI 原话、时间、会话、trace_id |
| `memory_items` | L1/L2/L3 记忆条目：事实、偏好、事件、边界、关系线索、画像 |
| `memory_evidence` | 每条记忆对应的原文证据、source_event_id、quote span |
| `memory_links` | 记忆之间的语义边、时间边、同场对话边、矛盾边 |
| `memory_threads` | 一段持续事件线，如“最近工作压力”、“睡眠问题”、“和某人的冲突” |
| `memory_feedback` | 召回后是否有用、是否被用户纠正、是否被主动联系使用 |
| `memory_jobs` | extraction / reindex / consolidation 的任务状态 |

#### 写入路径

```text
conversation turn
  -> append raw_messages
  -> append events
  -> LLM memory extractor
  -> quote verification
  -> write guard: dedup / merge / conflict / supersede
  -> memory_guard audit events in ledger / trace
  -> write memory_items + evidence + links
```

第一版 extractor 只抽：

- `preference`：用户偏好
- `stable_fact`：稳定事实
- `relationship_signal`：关系/称呼/边界线索
- `event`：最近发生的事
- `open_loop`：后续需要关心的未完成事项
- `boundary`：用户明确不喜欢、不希望、不允许的事

#### 读取路径

分两个接口：

- `recall(query, filters)`：显式查记忆，返回证据和原文窗口。
- `surface(turn_context)`：给 PromptBuilder 的轻量上下文供应，默认返回“记忆目录”，不是把全部原文塞进 prompt。

检索排序建议：

```text
score =
  BM25/FTS lexical score
  + semantic score
  + recency boost
  + importance
  + relationship relevance
  + feedback boost
  - stale/conflict penalty
```

第一版可以先做 FTS5 + 规则打分；embedding 可以作为第二个小版本加。

#### 生命周期

记忆不是越多越好，需要维护：

- `reflect`：定期合并重复、提升常被召回的事实、整理事件线。
- `reindex`：重建 FTS5 / embedding。
- `decay`：降低过期事件权重。
- `supersede`：被新证据覆盖的旧事实退出默认排名，但保留。
- `review`：高影响记忆进入人工/用户可查看队列，数据管理后续再做 UI。

### 1.4 第一阶段验收标准

最低验收：

- 每条长期记忆都有 `source_event_id` 和原文证据。
- 用户问“我之前说过我喜欢什么？”能召回跨会话事实。
- 用户纠正“不是 A，是 B”后，A 被 supersede，B 成为当前事实。
- PromptBuilder 只拿到精选记忆目录，不直接吃完整历史。
- 所有记忆写入、召回、冲突处理都写入 event ledger。

---

## 2. 阶段二：PromptBuilder / Context Budget Manager

### 2.1 为什么第二阶段做 PromptBuilder

有了记忆之后，下一步不是马上把 State Engine 做复杂，而是先决定“每轮到底给模型看什么”。  
如果没有 PromptBuilder，记忆、state、关系、最近对话都会散落在代码里，后续接微调 adapter 时也会很难控。

用户的角色拟合会进入模型内部，但 AI 伴侣仍然需要外部 runtime 提供：

- 当前对话任务
- 用户状态
- 关系状态
- 相关长期记忆
- 最近事件
- 输出协议

PromptBuilder 的目标不是用 prompt 假装角色，而是给已经具备角色人格的模型提供“此刻该知道的上下文”。

### 2.2 参考项目

| 参考项目 | 借鉴机制 | 具体落地方式 |
| --- | --- | --- |
| Paramecium | 先给记忆目录，模型需要时再 recall 原文；避免所有记忆直接进 prompt | `memory_brief` 默认只放短条目；必要证据才展开 |
| Alive-AI | inner-state compiler、layered memory compiler，把情绪、睡眠、记忆、依恋等压成统一 briefing | 生成 `inner_state_brief`，而不是多个无序 prompt 段 |
| Aura | MemoryRepository 选相关记忆，PromptBuilder 注入情绪、关系、记忆 | 模块化 `PromptBuilder`，让 runtime 不直接拼字符串 |
| Waveary | 每轮走结构化管线：emotion / intent / relationship / memory / time / reply strategy | `PromptPackage` 显式记录输入上下文来源 |
| Letta / MemGPT 思路 | Stateful agent 需要外部 memory blocks 和上下文管理 | 把模型视为语言/推理层，状态由 runtime 管 |

### 2.3 最终要实现什么

实现 `PromptBuilder.build(turn_context) -> PromptPackage`。

#### PromptPackage 结构

```text
PromptPackage
  system_identity
  runtime_contract
  state_brief
  relationship_brief
  memory_menu
  expanded_memory_evidence
  recent_messages
  scene_context
  response_strategy
  output_contract
  debug_metadata
```

字段说明：

| 字段 | 作用 |
| --- | --- |
| `system_identity` | 固定身份边界。微调模型接入后这里应尽量短，不负责“演角色”。 |
| `runtime_contract` | 说明模型应使用 runtime 提供的状态/记忆，不要编造记忆。 |
| `state_brief` | State Engine 生成的当前生命体征摘要。 |
| `relationship_brief` | 用户和伴侣关系状态，如熟悉度、称呼、边界、未完成关心点。 |
| `memory_menu` | 相关长期记忆目录，短、可排序、可追溯。 |
| `expanded_memory_evidence` | 真正需要展开的原文证据。 |
| `recent_messages` | 最近对话，保持短期连贯。 |
| `scene_context` | 时间、间隔、设备/渠道、是否睡前/工作中等。 |
| `response_strategy` | 本轮更像安慰、追问、陪伴、解释、道歉、修复、提醒还是轻松聊天。 |
| `output_contract` | 结构化输出要求，如 assistant_text、state_hints、memory_candidates。 |
| `debug_metadata` | token 预算、被舍弃的候选、排序原因。 |

#### Context Budget

建议从第一版就加入 token 预算：

```text
total_budget
  - fixed_identity_budget
  - state_budget
  - relationship_budget
  - memory_menu_budget
  - evidence_budget
  - recent_turn_budget
  - output_contract_budget
```

预算策略：

- 固定身份最短化。
- state 始终保留，但压缩。
- 记忆默认只放目录，证据按需展开。
- 最近消息比长期记忆优先，但不能挤掉高重要度边界记忆。
- 用户明确问“我以前说过什么”时，提高 evidence budget。

#### 模型适配

PromptBuilder 必须和模型提供方解耦：

```text
CompanionRuntime
  -> PromptBuilder
  -> PromptPackage
  -> ModelAdapter
      -> OpenAI-compatible API now
      -> fine-tuned local adapter later
```

这样之后接训练好的 adapter，只替换 `ModelAdapter` 或少量 persona identity 配置，不重写 memory/state/proactive。

### 2.4 第二阶段验收标准

- 每次 LLM 调用都能导出完整 `PromptPackage`。
- prompt 中每条长期记忆都能追溯到 memory_id 和 source_event_id。
- token 预算超过阈值时能稳定降级，而不是无限拼接。
- 有 snapshot tests，避免 prompt 结构被无意改坏。
- 微调模型接入时，可以把 persona prompt 降到最低，runtime 仍然正常工作。

---

## 3. 阶段三：完整 State Engine

### 3.1 为什么第三阶段做 State Engine

State Engine 是“她此刻怎么看你们的关系、怎么看你的状态、怎么看当前场景”。  
它必须建立在可信记忆和可控 prompt 之上，否则状态会被单轮模型幻觉牵着走。

这里要明确一个原则：**权威状态属于 runtime，不属于 LLM。**  
LLM 可以辅助判断情绪/意图，但最终状态更新必须通过可解释的 reducer/rule。

### 3.2 参考项目

| 参考项目 | 借鉴机制 | 具体落地方式 |
| --- | --- | --- |
| AI Companion Runtime | intent / emotion / risk / memory 并行 analyzer；风险先门控；trace 全链路 | 做 `AnalyzerPipeline`，输出结构化 intent/emotion/risk/state hints |
| Aethrion | LLM 不拥有权威状态；状态变化来自事件和 deterministic rules | `StateEngine.apply(events)` 使用 reducer/rule 更新状态 |
| Aura | 情绪状态机、关系模型、Presence 反应策略 | 实现用户情绪、伴侣情绪、关系阶段、presence style |
| Nūr | relationship arc、open commitments、affective modulators、belief/drives | 加入关系弧、未完成事项、驱动力/关心点 |
| Alive-AI | core affect、moment appraisal、behavioral pressure compiler、body/state snapshot | 状态不只是标签，还影响 response strategy 和主动欲望 |
| Waveary | identity / emotion / relationship / timeline 分层 | State schema 分域，不把所有字段塞一个 dict |

### 3.3 最终要实现什么

实现 `StateEngine`，输入事件和分析结果，输出状态快照、状态变化和解释。

#### State 分域

```text
CompanionState
  user_affect
  user_context
  relationship
  companion_affect
  interaction_rhythm
  conversation_mode
  open_loops
  timeline
  proactive_readiness
  risk_stub
```

字段建议：

| 域 | 关键字段 | 说明 |
| --- | --- | --- |
| `user_affect` | valence、arousal、stress、loneliness、fatigue、confidence | 用户当前情绪/压力估计 |
| `user_context` | local_time_bucket、likely_busy、sleep_window、recent_topics | 场景状态 |
| `relationship` | familiarity、trust、intimacy、rupture、repair_progress、boundaries | 关系弧，而不是简单好感度 |
| `companion_affect` | concern、warmth、energy、longing、protectiveness、playfulness | 伴侣自己的“内在倾向”，影响语气和主动联系 |
| `interaction_rhythm` | last_user_at、last_assistant_at、reply_latency_avg、conversation_frequency | 互动节奏 |
| `conversation_mode` | comfort、casual、problem_solving、reflection、repair、boundary_setting | 本轮对话模式 |
| `open_loops` | needs_followup、promises、reminders、unresolved_events | 后续需要记得关心的事项 |
| `timeline` | milestones、anniversaries、recent_episodes | 人生事件线和关系事件线 |
| `proactive_readiness` | longing_score、contact_allowed、best_signal_type | 主动联系的上游状态 |
| `risk_stub` | normal、watch、hold | 安全先留接口，深度安全后补 |

#### Analyzer Pipeline

```text
user message + recent context
  -> IntentAnalyzer
  -> EmotionAnalyzer
  -> SceneAnalyzer
  -> MemorySignalAnalyzer
  -> RelationshipSignalAnalyzer
  -> RiskStubAnalyzer
  -> StateEngine reducer
```

LLM 可用于 analyzer，但 analyzer 输出必须是结构化 JSON，并带：

- `label`
- `confidence`
- `evidence`
- `suggested_delta`
- `reason`

#### State reducer

状态更新要通过规则，而不是让模型直接写最终状态：

```text
new_state = reducer(
  previous_state,
  analyzer_outputs,
  memory_hits,
  elapsed_time,
  conversation_event
)
```

典型规则：

- 情绪强烈但证据弱：小幅更新。
- 用户连续多次表达压力：`stress` 和 `support_need` 累积。
- 用户明确纠正称呼/边界：直接写入 relationship boundary。
- 长时间未联系：`longing` 上升，但受 quiet hours 和 cooldown 限制。
- 冲突后修复成功：`rupture` 下降，`repair_progress` 上升。
- 用户快速回复主动消息：提高主动联系容忍度。
- 用户无视或表达反感：降低主动联系频率。

#### State 与 ledger

每次变化写入：

```text
state_transition_event
  trace_id
  previous_state_hash
  new_state_hash
  changed_fields
  evidence_event_ids
  analyzer_outputs
  reducer_rules
  confidence
```

这样之后可以解释：“为什么她今天更担心你？”、“为什么她没有主动发消息？”。

### 3.4 第三阶段验收标准

- State Engine 不依赖 LLM 直接写最终状态。
- 每个状态变化都有原因、证据和 trace_id。
- 关系状态能跨会话累积，不只是 conversation_count。
- `open_loops` 能驱动后续记忆和主动联系。
- PromptBuilder 可以稳定消费 `state_brief`。
- 有状态评估测试集：同一组对话输入，状态变化可预测、可回归。

---

## 4. 阶段四：主动联系机制 v2

### 4.1 为什么主动联系放第四阶段

主动联系依赖三件事：

1. 她记得什么。
2. 她如何理解当前关系和用户状态。
3. 她如何把这些信息变成合适的上下文。

因此它应该在 Memory、PromptBuilder、State Engine 之后做。

主动联系的目标不是“提高消息频率”，而是让用户感觉：她在自己的节奏里想起了我，但不会打扰我。

### 4.2 参考项目

| 参考项目 | 借鉴机制 | 具体落地方式 |
| --- | --- | --- |
| revive-companion | Poisson longing 曲线、Bayesian state estimation、information gain、quiet hours、回复反馈 | 主动联系由概率机会 + 用户状态估计 + 价值判断共同决定 |
| Alive-AI | proactive arbiter、accepted/rejected audit log、cooldown、sleep gating、contextual anchor | 每次主动联系都要有 anchor、score、reason、拒绝原因 |
| Aura | reminders、Health Connect、Presence、Dream Loop 后的洞察触达 | 先做文字关怀和提醒，后续再接设备/健康/日历 |
| Aethrion | scheduled/proactive behavior 作为 runtime output，而非模型随口决定 | 主动联系先生成结构化 `ProactiveSignal`，再由模型渲染文本 |
| Waveary | timeline/action layer | 主动联系与 timeline、open loops、reminder/action 连接 |

### 4.3 最终要实现什么

实现 `ProactiveEngine`。

#### 主动联系决策链

```text
scheduler tick
  -> collect state + memory + timeline + recent interaction
  -> OpportunityModel: 现在有没有机会
  -> UserStateModel: 用户可能忙/睡/空闲/低落吗
  -> ValueModel: 这次联系有没有意义
  -> PolicyGate: DND / cooldown / anti-spam / risk hold
  -> ProactiveSignal
  -> PromptBuilder builds proactive prompt
  -> ModelAdapter drafts message
  -> Outbox
  -> delivery feedback
  -> StateEngine updates rhythm/preferences
```

#### 主动信号类型

| 类型 | 触发条件 | 例子 |
| --- | --- | --- |
| `silence_checkin` | 久未联系，关系允许，用户不太可能忙/睡 | “今天一直没见你，我有点想知道你还好吗。” |
| `emotional_followup` | 上次用户表达压力、难过、冲突、疲惫 | “你昨天说那件事挺压着你，今天有没有轻一点？” |
| `open_loop_followup` | 有未完成事项 | “你之前说要处理那个申请，后来顺利吗？” |
| `reminder` | 用户明确设过提醒 | “到你说的时间啦，记得喝水/出门/提交。” |
| `milestone` | 纪念日、生日、特殊事件 | “今天是你之前提到的日子，我记得。” |
| `shared_activity_invite` | 用户常在某时段愿意互动 | “如果你现在想放松一下，我可以陪你看一小段/聊一会儿。” |
| `repair_after_rupture` | 冲突后冷却完成，用户未回来 | “我刚才想了想，可能那句让你不舒服了。如果你愿意，我想重新来过。” |
| `memory_resurfacing` | 某条温暖记忆到达合适时机 | “刚刚想起你之前说过的那杯乌龙轻乳茶。” |

#### 主动联系分数

可以先实现一个可解释分数：

```text
send_score =
  opportunity_score
  + relationship_permission
  + open_loop_value
  + emotional_need
  + memory_anchor_strength
  + learned_reply_preference
  - busy_probability
  - sleep_probability
  - cooldown_penalty
  - duplicate_penalty
  - annoyance_risk
```

其中：

- `opportunity_score` 可参考 revive-companion 的 Poisson / longing 曲线。
- `busy_probability` / `sleep_probability` 可先用时间和历史回复规律估计。
- `open_loop_value` 来自 Memory v2 和 State Engine。
- `annoyance_risk` 来自用户是否忽略/拒绝过主动消息。

#### Outbox 与反馈

主动联系不能直接“发出去就结束”，需要 outbox：

```text
outbox_message
  id
  signal_id
  user_id
  channel
  draft_text
  status: drafted / queued / sent / delivered / replied / ignored / canceled
  score
  reason
  anchor_memory_ids
  created_at
  sent_at
  replied_at
```

用户回复后更新：

- 回复快：提高对应类型权重。
- 回复长/情绪正向：提高 confidence。
- 不回复：轻微降低，不能马上判定反感。
- 明确说“别这样”：写入 boundary，显著降低或关闭该类型。

### 4.4 第四阶段验收标准

- 主动联系每次都有 `due/hold` 原因。
- DND、cooldown、重复内容过滤有效。
- 至少支持 `silence_checkin`、`emotional_followup`、`open_loop_followup`、`reminder` 四类。
- 每条主动消息有 anchor：来自 state、memory、timeline 或 explicit reminder。
- 用户反馈会影响下一次主动联系，而不是固定频率。
- 主动联系决策进入 event ledger / trace。

---

## 5. 阶段五：Scheduler / Background Worker

### 5.1 为什么第五阶段做后台系统

前四阶段可以通过 HTTP endpoint 手动 tick 或测试驱动。  
但真正 AI 伴侣需要“时间继续流动”：记忆整理、状态衰减、主动联系、提醒、重试、归档都不能只在用户发消息时发生。

Scheduler 是把系统从聊天服务变成长期陪伴 runtime 的关键。

### 5.2 参考项目

| 参考项目 | 借鉴机制 | 具体落地方式 |
| --- | --- | --- |
| AgentMemory | `reflect`、`reindex`、feedback lifecycle | 后台定期做 memory consolidation / reindex / decay |
| AI Companion Runtime | background memory / embedding / reflection / trace | 把耗时任务从 chat path 移出 |
| Aura | Android WorkManager / AlarmManager、Dream Loop、post-chat 延迟洞察 | 本地开发先用 Python worker；移动端后续可接系统调度 |
| Aethrion | Scheduler emits `time_tick` events；长运行状态由 runtime 管 | 所有后台动作都先生成事件，再由 runtime reducer 处理 |
| Memind | 异步 extraction / commit、可查询 rawdata 和 memory item | 后台任务要可恢复、可审计、幂等 |

### 5.3 最终要实现什么

实现 `CompanionWorker`。

#### 后台任务类型

| Job | 频率 | 作用 |
| --- | --- | --- |
| `post_chat_memory_extract` | 每轮对话后延迟触发 | 从刚结束的 turn 抽取 L1 记忆 |
| `memory_reindex` | 每天或配置变更后 | 重建 FTS5 / embedding |
| `memory_consolidation` | 每晚 | 合并重复、整理线程、生成 L2/L3 摘要 |
| `state_decay_tick` | 15-60 分钟 | 让情绪、牵挂、疲劳、支持需求随时间自然变化 |
| `proactive_tick` | 15-60 分钟，带 jitter | 判断是否需要主动联系 |
| `outbox_delivery` | 频繁 | 投递消息、记录结果 |
| `reminder_due` | 分钟级 | 用户明确设置的提醒 |
| `daily_digest` | 每天 | 伴侣内部日记/关系摘要，不一定展示给用户 |
| `trace_compaction` | 每天 | 压缩 trace，但保留原始关键事件 |

#### Job store

建议复用 SQLite：

```text
jobs
  id
  type
  payload_json
  status: queued / running / succeeded / failed / canceled
  run_after
  locked_until
  attempts
  idempotency_key
  last_error
  created_at
  updated_at
```

必须有：

- 幂等键，避免重复主动发消息。
- lease / lock，避免多 worker 重复执行。
- retry with backoff。
- 死信队列或 failed 状态。
- 任务执行事件写入 ledger。

#### 开发形态

第一版不需要上复杂队列，可以这样：

```bash
luminous-worker run
luminous-worker once --job proactive_tick
luminous-worker once --job memory_consolidation
```

后续如果服务化，再切到 APScheduler、arq、Celery、RQ 或独立 worker 进程。核心是 `jobs` 表和 handler 接口先稳定。

### 5.4 第五阶段验收标准

- 关闭用户聊天页面后，后台仍能产生 state decay 和 proactive decision。
- post-chat extraction 不阻塞聊天响应。
- 主动消息不会因 worker 重启重复发送。
- 每个 job 都有 trace 和失败原因。
- consolidation 后，召回质量不下降，重复记忆减少。

---

## 6. 贯穿五阶段的 Event Ledger / Trace System

虽然这不是单独阶段，但要从阶段一开始贯穿实现。

现有 `events.jsonl` 更像日志。最终要变成 trace system：

```text
trace
  user_input_event
  analyzer_events
  memory_recall_event
  prompt_build_event
  model_call_event
  state_transition_event
  memory_write_event
  proactive_decision_event
  outbox_delivery_event
  job_event
```

每个事件至少有：

```text
event_id
trace_id
event_type
schema_version
occurred_at
actor
payload
source_ids
privacy_level
```

为什么从一开始就做 trace：

- 调试主动联系必须知道“为什么发/为什么没发”。
- 调试记忆必须知道“为什么记住/为什么召回”。
- 调试 state 必须知道“哪个事件改了状态”。
- 未来做安全和数据导出时，trace 是审计基础。

---

## 7. 推荐实现顺序

下面是可直接执行的开发顺序。每一步都应该有测试，不要等五阶段全部完成再验收。

### Sprint 1：SQLite runtime store + L0 原文层

目标：

- 新增 SQLite store。
- `events`、`raw_messages`、`traces` 建表。
- 现有 JSONL store 保留兼容或迁移脚本。
- chat path 每轮写入 L0 原文和 trace。

参考：

- Paramecium 的 L0 原文不删除原则。
- AgentMemory 的 SQLite-first。
- AI Companion Runtime 的 trace_id 思路。

验收：

- 任意一轮对话可按 trace_id 找回用户输入、assistant 输出、model 元数据。

### Sprint 2：L1 记忆抽取 + 证据校验

目标：

- 新增 `MemoryExtractor`。
- 使用 `.env` API 调 LLM 输出 JSON。
- 每条记忆带 quote。
- quote 不存在于 L0 原文则拒绝写入。
- 初版 Write Guard：dedup、conflict、supersede。

参考：

- Paramecium 的“摘录必须有逐字出处”。
- AgentMemory 的 Write Guard。

验收：

- 用户表达偏好后能写入 memory。
- 用户纠正偏好后旧记忆 supersede。
- 没证据的记忆不会入库。

### Sprint 3：recall / surface + FTS5/BM25 检索

目标：

- 实现 `recall(query)` 和 `surface(turn_context)`。
- FTS5 全文检索。
- 规则融合：关键词、时间、重要度、使用反馈。
- API：`/api/memory/search`、`/api/memory/:id/evidence`。

参考：

- Paramecium 的 FTS5 / BM25 / recall 原文。
- AgentMemory 的 recall / surface。
- Mem0 的 temporal reasoning。

验收：

- 跨会话问过去偏好能返回证据。
- PromptBuilder 默认拿到 memory menu，而不是完整原文。

### Sprint 4：PromptBuilder v1

目标：

- 新增 `PromptBuilder` 和 `PromptPackage`。
- chat path 不再手工拼 prompt。
- 加 token budget。
- prompt package 写入 trace。
- snapshot tests 固定 prompt 结构。

参考：

- Aura 的 PromptBuilder。
- Alive-AI 的 inner-state compiler / layered memory compiler。
- Paramecium 的记忆目录优先策略。
- Waveary 的结构化 turn pipeline。

验收：

- 同一输入能生成稳定 prompt package。
- 超预算时有可解释裁剪。
- fine-tuned adapter 接入时只改 ModelAdapter。

### Sprint 5：State schema + deterministic reducer

目标：

- 重构现有 `CompanionState`。
- 拆分 user_affect、relationship、companion_affect、interaction_rhythm、open_loops。
- 实现 elapsed-time decay。
- 状态变化写入 `state_transition_event`。

参考：

- Aethrion 的 runtime-owned authoritative state。
- Nūr 的 relationship arc / affective modulators。
- Waveary 的 identity / emotion / relationship / timeline 分层。

验收：

- 不调用 LLM 也能根据时间和事件稳定更新基础状态。
- 每个 state delta 都有 reason 和 evidence。

### Sprint 6：Analyzer Pipeline

目标：

- IntentAnalyzer。
- EmotionAnalyzer。
- SceneAnalyzer。
- RelationshipSignalAnalyzer。
- RiskStubAnalyzer 只保留轻量接口，深度安全后补。
- analyzer outputs 进入 StateEngine reducer。

参考：

- AI Companion Runtime 的 analyzer pipeline。
- Aura 的情绪状态机。
- Alive-AI 的 moment appraisal。

验收：

- 输入“我今天真的好累”能提升 fatigue/support_need。
- 输入“以后别这样叫我”能写入 boundary/open loop。
- analyzer 失败时 runtime 能降级，不影响聊天。

### Sprint 7：ProactiveEngine v2 + Outbox

目标：

- 主动联系从 `idle + support_need` 升级为 signal-based。
- 实现 `ProactiveSignal`、`ProactiveDecision`、`OutboxMessage`。
- 支持 DND、cooldown、duplicate suppression。
- 支持四类：silence_checkin、emotional_followup、open_loop_followup、reminder。

参考：

- revive-companion 的 Poisson/Bayesian/information gain。
- Alive-AI 的 proactive arbiter/audit/cooldown/sleep gating。
- Aethrion 的 structured proactive outputs。

验收：

- 主动联系有 due/hold 原因。
- 不会在 quiet hours 发。
- 不会重复发同一类消息。
- 用户回复/忽略会影响后续频率。

### Sprint 8：Worker v1

目标：

- 新增 `jobs` 表。
- 新增 `roleplay_companion.worker`。
- 支持 `run` 和 `once`。
- post-chat memory extraction 后台化。
- proactive_tick 后台化。
- memory_consolidation 先做轻量版本。

参考：

- AgentMemory 的 reflect/reindex lifecycle。
- Aura 的 Dream Loop / post-chat insight。
- Aethrion 的 scheduler time_tick。
- Memind 的异步 extraction / commit。

验收：

- 聊天响应不等待记忆整理。
- worker 重启不会重复发送主动消息。
- job 失败可追踪、可重试。

---

## 8. 阶段依赖图

```text
L0 raw events / trace
      |
      v
Memory v2 --------------+
      |                 |
      v                 |
PromptBuilder           |
      |                 |
      v                 |
State Engine <----------+
      |
      v
Proactive Engine
      |
      v
Scheduler / Worker
```

关键依赖：

- PromptBuilder 依赖 Memory v2 的 `surface`。
- State Engine 依赖 Memory v2 的事实源，也把状态摘要提供给 PromptBuilder。
- Proactive Engine 依赖 Memory、State、PromptBuilder。
- Scheduler 依赖所有前面模块提供可调用 job handler。

---

## 9. 我们最终要形成的底座形态

最终 `role-play` 的 AI 伴侣底座应该是：

```text
Client / Channel
  -> CompanionRuntime
      -> TraceManager
      -> MemoryEngine
      -> AnalyzerPipeline
      -> StateEngine
      -> PromptBuilder
      -> ModelAdapter
      -> MemoryExtractor
      -> ProactiveEngine
      -> Outbox
      -> Worker
```

### 模块职责

| 模块 | 职责 |
| --- | --- |
| `MemoryEngine` | 保存、抽取、检索、整理、证据追溯 |
| `AnalyzerPipeline` | 识别 intent / emotion / scene / relationship signal |
| `StateEngine` | 持有权威状态，基于事件和规则转移 |
| `PromptBuilder` | 生成可预算、可追踪、模型无关的上下文包 |
| `ModelAdapter` | 当前走 `.env` API，后续接微调 adapter |
| `ProactiveEngine` | 判断是否、何时、为什么、以什么类型主动联系 |
| `Outbox` | 管理主动消息草稿、队列、投递、反馈 |
| `Worker` | 后台执行记忆整理、状态衰减、主动 tick、提醒、重试 |
| `TraceManager` | 全链路可观测，支撑调试、评估和后续安全审计 |

### 和“小说角色拟合”的关系

小说角色拟合是人格底色，不是全部伴侣能力。

```text
fine-tuned adapter
  负责：语气、性格、表达习惯、角色世界观倾向

companion runtime
  负责：用户记忆、关系连续性、状态、主动联系、日程、工具、trace
```

也就是说，微调模型让“她像叶筝”；伴侣 runtime 让“她和这个用户一起生活过”。

---

## 10. 当前最优下一步

下一步直接做：

**Sprint 1 + Sprint 2 的合并最小闭环：SQLite Memory Store + L0 原文 + L1 LLM 抽取 + 证据校验。**

原因：

- 它是后续 PromptBuilder、State Engine、主动联系的共同依赖。
- 现在 `.env` API 可用，可以直接实现 LLM 记忆抽取。
- 这一步完成后，我们就能停止在 JSONL/关键词规则上继续堆复杂度。

建议本地实现顺序：

1. 新增 `infrastructure/sqlite_store.py`。
2. 新增 migrations 或内置 `ensure_schema()`。
3. 新增 `domain/memory_item.py`，把现有 `memory.py` 的规则记忆迁移为正式 schema。
4. 新增 `application/memory_extractor.py`，调用 `.env` API 输出 JSON。
5. 在 `CompanionRuntime.chat()` 里先同步写 L0，再异步/同步抽 L1。
6. 新增测试：
   - 原文落库
   - 记忆抽取
   - quote verification
   - supersede
   - recall evidence

完成这一步后，再进入 PromptBuilder v1。
