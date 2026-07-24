# Modular Message Pipeline Design

本文档记录下一版 SFT 数据构建设计：将 `system.content`、`user.content`、`assistant.content` 拆成三个独立模块生成，再由确定性 assembler 合并成 HER-style messages。

这个方案替代当前的 `annotation -> profile_revision -> sft_messages -> user_repair` 主链路。旧链路可以保留为历史基线和调试工具，但不再作为默认数据生产路径。

## 1. 为什么拆开

当前问题的根源是：一个 `sft_messages` prompt 同时生成 `system`、`user`、`assistant`，导致三个字段互相污染。

- `system.content` 会被当前切片和目标台词带偏，变成 per-turn response hint。
- `user.content` 容易包含目标台词或后文叙述，造成答案泄漏。
- `assistant.content` 依赖 annotation 中间字段，任务链条长、token 成本高，且 annotation 本身已经很重。
- 动态 profile revision 会把局部剧情状态写进长期画像，增加信息泄漏和人设漂移风险。

拆开后，每个模块只做一件事：

| 模块 | 负责内容 | 不负责内容 |
|---|---|---|
| system module | 角色设定、世界背景、章节/场景级设定、输出协议 | 当前目标台词、本轮回应策略 |
| user module | 叶筝开口前可见的外部上下文 | 叶筝目标台词、叶筝内心、后文答案 |
| assistant module | 叶筝本轮的系统思考、角色内心、可见动作、原文台词 | system 设定重写、user 上下文修补 |

## 2. 总体流程

```text
novel text
  -> quote_candidates
  -> speaker_attribution
  -> source_anchored_beats / sft_turns
  -> prepare system_context / user_context / assistant_response prompt files
  -> parallel LLM:
     - system_context
     - user_context
     - assistant_response
  -> assemble messages
  -> QA / trainable / review queue
```

保留的确定性前置阶段：

1. `quote_candidates`：从原文抽取候选引语。
2. `speaker_attribution`：判断哪些引语属于叶筝。
3. `source_anchored_beats` / `sft_turns`：将叶筝台词锚定到原文，形成目标训练 turn。
4. `system_context` / `user_context` / `assistant_response`：三类 prompt 都由 `sft_turns`、`coarse_beats` 和目标台词位置确定性生成。当前代码会同时运行三批 LLM 请求，完成后再统一抽取和装配。

废弃为默认主链路的阶段：

1. `annotation`：不再要求先生成心理分析中间件。
2. `profile_revision`：不再逐 beat 动态更新画像。
3. `user_repair`：拆出 user module 后，修补逻辑应前移到 user 生成和 QA 重试中。

## 3. System Module

### 3.1 职责

生成或装配每条样本要引用的 `system.content`。

`system.content` 是 HER 的角色设定 prompt，不是 assistant 中的 `<system_thinking>`。它应该提供“怎样扮演叶筝”的长期约束，而不是告诉模型这一轮要说什么。

### 3.2 当前设计

先固定三段内容：

- `叶筝的人物画像`
- `故事背景`
- `输出要求`

LLM 只负责生成当前回合的局部场景材料：

- `当前场景`
- `其他角色信息`

当前实验粒度为 turn-level。也就是说每条目标台词都会生成一份自己的 `current_scenario` 和 `other_characters`。输入范围是本章开头到当前目标台词之前的累计原文；它比 `user_context`、`assistant_response` 更宽，但同样不包含目标台词和后文。这样可以给 system 足够前情，同时避免章节后半段信息提前泄漏到前半段样本。

`user_context` 和 `assistant_response` 的 prompt 不读取 system/user 的自然语言输出，因此 stage 4/5/6 的 LLM 调用可以并行。`system_id` 在 prompt 预生成时用 `turn_id` 作为稳定 fallback，最终 assembler 仍按 `turn_id` / `system_id` 合并三类结果。

`current_scenario` 和 `other_characters` 都是 JSON 字符串字段。内容应写成自然中文段落，而不是数组、对象、字典、键值对或项目列表。提取阶段会对偶发的数组/对象输出做自然文本兜底转换，但 prompt 仍要求 LLM 直接输出字符串。

### 3.3 输出格式

建议中间产物：

```json
{
  "system_id": "ch001_t001",
  "chapter_id": "ch001",
  "turn_id": "ch001_t001",
  "beat_id": "ch001_b001",
  "scope": "turn",
  "current_scenario": "",
  "other_characters": "",
  "system_content": ""
}
```

最终 `system_content` 由程序拼接：

```text
你正在扮演《漫画万人嫌自救指南》中的叶筝。

===叶筝的人物画像===
{fixed_profile}

===故事背景===
{fixed_background}

===当前场景===
{current_scenario}

===其他角色信息===
{other_characters}

===输出要求===
{fixed_requirements}
```

### 3.4 QA

必须检查：

- 不包含 `target_speech` 或目标台词片段。
- 不包含“本轮要反驳/追问/回答”等 per-turn 策略。
- 不包含 `annotation`、`source_text`、`target_speech` 等数据制作字段名。
- 不泄漏目标台词之后或章节后半段才出现的剧情。

## 4. User Module

### 4.1 职责

生成 `user.content`：叶筝开口之前，叶筝可以看见/听见/知道的外部上下文。

HER 中 `user.content` 更接近“角色可见的世界状态”，不是用户给模型下达的任务指令。

### 4.2 输入

- 当前 `sft_turn`
- 当前 target speech 的 source span
- system module 输出的 `system_id`

`system_id` 只用于后续 assembler 关联，不进入 user prompt。`user_context` prompt 不接收 `system_context`，避免章节级摘要或其他角色设定回流到单条 user。

`visible_source_before_target` 是主输入，严格表示本条目标台词之前的局部原文。user module 不接收 `recent_dialogue_context`，避免过宽前文被误写进当前 `user.content`。若当前目标台词前文本很短，程序参照 annotation 的短输入处理补入 `prior_visible_context`，只用于恢复地点、人物关系和上一句外显言行。

### 4.3 生成原则

- 只写叶筝开口前已经发生的信息。
- 可以包含其他角色的台词、动作、环境叙述。
- 叶筝是非全知视角，看不到其他人的心理活动、真实动机、旁白判断或未来剧情。
- 如果原文中有全知旁白或其他角色心理，只保留叶筝可以看见、听见、或已经被说出口的信息；否则删除。
- 不包含叶筝即将说出的目标台词。
- 不写“请你扮演/请回答/目标台词是”这类训练指令。
- 可以对原文做轻量整理和压缩，但不能补充改变剧情因果的信息。

### 4.4 输出格式

建议中间产物：

```json
{
  "turn_id": "ch001_t001",
  "system_id": "ch001_t001",
  "user_content": "",
  "contains_target_speech": false,
  "uses_second_person_instruction": false
}
```

LLM 只输出 `user_content`。`contains_target_speech` 和 `uses_second_person_instruction` 是提取/QA 阶段由程序写入的质量字段，不让 LLM 自评。

### 4.5 QA

必须检查：

- `user.content` 不包含完整目标台词。
- `user.content` 不包含明显目标台词片段。
- 不包含 assistant 输出标签：`<system_thinking>`、`<role_thinking>`。
- 不包含二人称训练指令。
- 软检查是否含有“心中、内心、想起、怀念、觉得、认为、决定”等私密心理词。
- 不包含 target source span 之后才出现的关键信息。

## 5. Assistant Module

### 5.1 职责

生成 `assistant.content`：叶筝这一轮的 HER-style 回复。

由于 system 和 user 已经拆开，assistant module 可以一步完成心理分析，不再需要 annotation 先生成中间字段。

### 5.2 输入

- 固定人物画像和背景，或 system module 的结构化字段。
- `user.content`
- 当前原文片段，尤其是 target speech 前后的叙述证据。
- `target_speech`
- 可选：上一轮叶筝回复历史。

### 5.3 输出原则

assistant 必须以如下顺序生成：

1. `<system_thinking>...</system_thinking>`：第三人称扮演分析，说明叶筝在当前语境中如何保持角色一致性。
2. `<role_thinking>...</role_thinking>`：叶筝第一人称私密内心。
3. 可选 `<role_action>...</role_action>`：其他角色可见的动作、神态或行为。
4. 原文目标台词。

为了保证目标台词逐字正确，推荐让 LLM 只生成 thinking/action 字段，由程序把 `target_speech` 作为最终台词拼接进去。

建议中间产物：

```json
{
  "turn_id": "ch001_t001",
  "system_thinking": "",
  "role_thinking": "",
  "role_action": "",
  "speech": "{target_speech}"
}
```

最终 assembler 生成：

```text
<system_thinking>{system_thinking}</system_thinking><role_thinking>{role_thinking}</role_thinking><role_action>{role_action}</role_action>{target_speech}
```

如果原文没有支持具体动作，`role_action` 优先留空；如果原文只支持自然的说话行为，可以写极短的语气或言语行为。不要为了字段完整而写 `none`、`无`、`无动作`，也不要硬塞“目光、微笑、抬手”等无依据细节。空 `role_action` 不会进入最终 assistant，assembler 会直接省略 `<role_action>` 标签。

### 5.4 QA

必须检查：

- 以且仅以一个 `<system_thinking>` 开头。
- `<system_thinking>` 使用第三人称，不冒充叶筝内心。
- `<role_thinking>` 使用叶筝本人身份、叶筝自己的语言风格写成内心原声，不包含其他角色内心，不写旁白、导演分析或策略说明。
- `<role_thinking>` 至少包含一次“我/我的”，避免退化为第三人称人物分析。
- `<role_action>` 若非空，建议 20-220 个汉字；没有可靠动作、语气或说话行为依据时保持空字符串。
- 最终 speech 与 `target_speech` 逐字一致。
- 不代替其他角色说话或行动。
- 不生成多轮对话。
- 不提及训练数据、目标台词、原文片段、prompt 或标签设计。
- `analysis_sufficient` 对模块化样本检查 `assistant_response.content_parts.system_thinking` 和 `role_thinking` 是否存在；旧 annotation 样本仍按 annotation 字段检查。

## 6. Assembler

assembler 是确定性代码，不调用 LLM。

输入：

- `system_contexts.jsonl`
- `user_contexts.jsonl`
- `assistant_responses.jsonl`
- `sft_turns.jsonl`

输出：

- `sft_messages_draft.jsonl`
- `sft_messages_trainable.jsonl`
- `sft_messages_her.jsonl`
- `review_queue.jsonl`

职责：

- 按 `turn_id` 和 `system_id` 合并三类 message。
- 用固定模板拼接 `system.content`。
- 用 `target_speech` 覆盖 assistant 的最终台词。
- 写入 trace 字段，保留 source span 和模块输出，方便回溯。
- 执行 QA，并将硬失败样本送入 review queue。
- 语义类风险，例如目标台词轻微泄露、动作依据不足、`role_thinking` 分析师口吻，只写入 warning/audit，不自动删除 response 或打回重跑。

## 7. 对旧 annotation/profile 设计的结论

拆分后，annotation 不再是必要主链路。

原因：

- 旧 annotation 主要服务于 `assistant.content` 的心理链路。
- 新 assistant module 已经可以在一个 prompt 中同时看到 user context、target speech、原文证据和固定画像。
- 继续保留 annotation 会增加一次 LLM 调用、一次 schema 设计、一次误差传播。

动态 profile revision 也不再作为默认路径。

原因：

- 叶筝核心画像和世界背景已经可以人工固定。
- HER 的 setting completion 更像“设定补全线”，不是每个 SFT turn 都动态改画像。
- 动态画像容易把后文剧情或局部状态写入当前样本。

旧 annotation/profile 可以保留三个用途：

1. 作为历史实验对照，比较模块化链路的数据质量。
2. 作为人工审计工具，帮助分析某些样本为什么失败。
3. 未来如果要做 setting completion，再离线生成更稳定的全书/章节设定。

## 8. 实施顺序

当前代码已按以下顺序实现：

1. 增加固定 profile/background/requirements 配置。
2. 增加 `system_context` module，按 turn-level 生成 `system_contexts.jsonl`。
3. 增加 `user_context` module，直接输出 `user_contexts.jsonl`，替代 `user_repair`。
4. 增加 `assistant_response` module，输出 thinking/action 字段，由程序拼接 target speech。
5. 增加 assembler，将三个模块输出合并为 messages。
6. 修改 pipeline 默认路径，跳过 annotation/profile revision。
7. `speaker_attribution` 完成并生成 `sft_turns` 后，再依次生成 `system_context`、`user_context`、`assistant_response`。
8. 重跑前两章，与 `outputs/test-qwenplus` 和 `outputs/test-qwenplus-user-repair` 对比。

第一轮验收目标：

- 前两章仍能产生约 23 条叶筝 SFT 样本。
- `user.content` 目标台词泄漏为 0。
- `assistant.content` target speech 逐字匹配为 100%。
- `system.content` 不再包含 per-turn 策略或目标台词。
- `role_action` 的无依据具体动作显著减少。
