# HER Pipeline Analysis

本文档基于本地克隆的 HER 源码梳理：

- 源仓库：<https://github.com/cydu24/HER>
- 本地路径：`/home/wz/HER`
- 当前提交：`1e5fd85`
- 已在 `/home/wz/HER` 执行 `codegraph init`，可用 CodeGraph 继续追踪符号和调用链。

目标不是复述论文摘要，而是搞清楚 HER 的数据构建、训练流程、`messages` 字段职责，以及它对当前 `role-play` 项目的设计约束。

## 1. 总览

HER 可以拆成两条主线：

1. 数据构建线：从 CoSER 原始小说/对话数据生成带 `system_thinking`、`role_thinking`、`role_action` 的角色扮演 SFT 数据。
2. 训练线：先做 roleplay SFT，再用候选回复对构造 reward model 数据，随后准备 reward RL 和 roleplay RL 数据。

HER 的核心不是单纯把小说对话改成 `user -> assistant`，而是显式区分三层：

| 层级 | HER 标签/字段 | 视角 | 可见性 | 作用 |
|---|---|---|---|---|
| System Thinking | `<system_thinking>` | 第三人称/模型侧 | hidden | 分析如何扮演角色，保持角色一致性 |
| Role Thinking | `<role_thinking>` | 角色第一人称 | hidden to others | 角色内心想法 |
| Role Response | `<role_action>` + speech | 角色第一人称外显行为 | visible | 动作和台词 |

这里有一个关键点：`system.content` 和 `<system_thinking>` 不是同一层。

- `system.content` 是 chat message 的 system prompt，放角色设定、场景、输出协议。
- `<system_thinking>` 是 assistant 内容里每个回复前的第三人称推理块。

## 2. 数据构建流程

源码主文档：

- `/home/wz/HER/data_process_code/DATA_PIPELINE.md`
- `/home/wz/HER/data_process_code/step3_gen_systhinking/README.md`
- `/home/wz/HER/data_process_code/step4_setting_completion/README.md`

HER 自述的数据主线：

```text
CoSER 原始数据
  -> Step 1 数据清洗 + 格式转换
  -> sft_data_full.jsonl
  -> Step 2 Role Thinking 增强
  -> sft_data_enhanced.jsonl
  -> Step 3 System Thinking 生成 + 改写
  -> sft_data_final.jsonl
  -> Step 4 Setting Completion
  -> sft_data_final_enriched.jsonl / full prompt 数据
  -> SFT 数据构建与消融版本
```

HER 文档中给出的规模：

- 760 本书。
- 29,081 个对话样本。
- 约 371k 到 383k 对话轮次。
- 342,493 个 assistant turns。
- `sys_thinking` 覆盖接近 100%。
- `enhanced_speech` 覆盖约 88.2%。
- setting 增强覆盖约 98.32%。

这些数字说明 HER 的核心投入在数据合成和大规模自动增强，不只是训练脚本。

## 3. Step 1: 原始数据转 SFT messages

核心脚本：

- `/home/wz/HER/data_process_code/step1_data_process/convert_to_sft_format.py`

关键函数：

- `convert_to_standard_format`
- `remove_thoughts_and_convert_actions`
- `build_character_info`
- `get_character_prompt`
- `build_training_samples_sharegpt`
- `enrich_dialogues`
- `process_single_book`

### 3.1 格式标准化

HER 将 CoSER 风格标记转成自己的标签：

```text
[内心想法] -> <role_thinking>内心想法</role_thinking>
(动作) -> <role_action>动作</role_action>
```

对目标角色自己的 assistant 回复，保留完整的：

```text
角色名: <role_thinking>...</role_thinking><role_action>...</role_action>台词
```

对其他角色进入当前目标角色视野的内容，HER 会移除对方的内心想法，但保留动作：

```text
<role_thinking>...</role_thinking> 被删除
<role_action>...</role_action> 保留
speech 保留
```

这说明 HER 的 `user.content` 是“当前目标角色可见的世界”，而不是自然语言任务指令。

### 3.2 每个角色各自构造一份 messages

`build_training_samples_sharegpt` 会对对话中每个说话角色构造训练样本：

```text
messages = [
  {"role": "system", "content": system_prompt},
  {"role": "user", "content": other visible dialogue/actions},
  {"role": "assistant", "content": target character full response},
  ...
]
```

规则：

- 当前目标角色的发言进入 `assistant`。
- 非目标角色的发言和环境上下文进入 `user`。
- 其他角色的 hidden thoughts 不进入 `user`。
- `origin_id` 用于追溯原始 dialogue，不是模型语义。

## 4. HER 的 `system.content` 到底是什么

关键源码：

- `convert_to_sft_format.py:get_character_prompt`
- `step4_setting_completion/step4_3_rebuild_system_prompt.py:build_system_prompt`
- `step4_setting_completion/generate_training_samples.py:get_character_prompt_enriched`
- `step4_setting_completion/step4_4_add_prompt_config.py:PROMPT_CONFIG`

HER 的 system prompt 由角色数据集字段拼接而成，不由当前目标回复生成。

固定结构版本大致是：

```text
You are {character} from {book_name}.

==={character}'s Profile===
{description}
{character_profile}
experience: {experience}

===Background===
{background}

===Current Scenario===
{scenario}

===Information about other Characters===
{other_character_profiles}

===Your Inner Thoughts===
{motivation}

===Requirements===
{output_format}
```

其中 `Your Inner Thoughts` 容易和 assistant 里的 `<role_thinking>` 混淆。按 HER 源码，它来自角色数据集字段 `motivation` / `motivation_enriched`，含义更接近“角色在该场景中的长期动机、内在立场、心理驱动力或行动目标”，属于 system prompt 的设定材料。它不是本轮即时内心独白，也不是 assistant 输出里的 `<role_thinking>`。如果项目中没有稳定、可泛化的 motivation 字段，可以先不单列该 section，或把长期动机合并进 `{character}'s Profile`。

`output_format` 对 HER 模型要求：

```text
1. System Thinking:
   A single block at the very beginning, wrapped in
   <system_thinking>...</system_thinking>.
   This is the third-person analysis of how to portray the role.

2. Role-play Response:
   Use <role_thinking>...</role_thinking> for invisible thoughts.
   Use <role_action>...</role_action> for visible actions.
   Speech and action/thinking can be interleaved.
```

### 4.1 system.content 可以变化吗

可以，但变化来源有限：

- 角色不同，system 不同。
- 书籍/章节/对话 scenario 不同，system 可不同。
- Step 4 setting completion 后，profile/background/scenario/motivation 等字段被增强，system 会重建。
- `generate_training_samples.py` 里存在自然风格/结构化风格的轻量模板随机化。

但 system 不应该随每个 target speech 变化。

### 4.2 system.content 不应该包含什么

按 HER 源码边界，system 不应包含：

- 当前目标台词。
- `target_speech`、`annotation`、`source_text` 等数据制作字段名。
- 本轮 response strategy，比如“这次要反驳”“这次要追问”“这次要沉默”。
- 当前切片的答案小抄。
- assistant 的具体训练标签。

`Current Scenario` 可以存在，但应来自角色/对话场景字段，而不是从每个 SFT turn 的目标回复反推出来。

### 4.3 对当前 role-play 的结论

我们当前让 `sft_messages` 同时生成 `system/user/assistant` 的设计偏离 HER。

更接近 HER 的做法：

1. 单独生成或维护 `system.content`。
2. system 按角色 + 章节/大场景版本稳定引用。
3. 每条 SFT turn 不再让 LLM 临时写 system。
4. 当前可见上下文进入 `user.content`。
5. 目标角色本轮的思考、动作、台词进入 `assistant.content`。

当前项目进一步决定采用模块化消息构建：

- `system module` 单独负责 profile/background/scenario/other characters/requirements。
- `user module` 单独负责目标角色开口前的可见上下文。
- `assistant module` 单独负责 `<system_thinking>`、`<role_thinking>`、`<role_action>` 和原文目标台词。

拆分后，旧 `annotation` 不再作为默认主链路，因为 assistant module 可以在一个 prompt 中直接完成本轮心理分析。动态 `profile_revision` 也不再逐 turn 执行，避免把局部剧情状态或后文信息写入长期画像。详细方案见 `docs/training/modular_message_pipeline.md`。

## 5. Step 2: Role Thinking 增强

核心目录：

- `/home/wz/HER/data_process_code/step2_gen_rolethinking`

关键脚本：

- `construct_vulcan_data.py`
- `role_thinking_enhance_prompt.py`
- `merge_extract_results.py`
- `merge_enhanced_to_sft.py`
- `analyze_pattern_diversity.py`

目标：让模型基于章节级 dialogue list 增强角色心理活动，输出 `enhanced_standard_format`。

输入 dialogue 已有：

```json
{
  "character": "角色",
  "origin_id": [0],
  "standard_format": "<role_thinking>...</role_thinking><role_action>...</role_action>台词",
  "without_think": "<role_action>...</role_action>台词"
}
```

增强输出新增：

```json
{
  "enhanced_standard_format": "<role_action>动作</role_action><role_thinking>深层思考</role_thinking>对话...",
  "enhanced_reason": "修改原因说明",
  "enhanced_pattern": "act->think->speech"
}
```

`merge_enhanced_to_sft.py` 的关键动作：

- 用 `trace_id + origin_id` 建索引。
- 将增强结果写回 `dialogues[*].enhanced_standard_format`。
- 重建 `training_samples`。
- assistant 优先使用 `enhanced_standard_format`。
- user 继续使用 `without_think`，避免看到别人的内心。

这一阶段主要提升 `role_thinking` 的心理深度和表达模式多样性。

## 6. Step 3: System Thinking 生成与改写

核心目录：

- `/home/wz/HER/data_process_code/step3_gen_systhinking`

目标：为每个 assistant turn 生成第三人称的扮演策略，并与增强后的角色回复对齐。

主流程：

```text
sft_data_enhanced.jsonl
  -> step3_1_extract_sys_thinking_samples.py
  -> step3_2_construct_vulcan_data.py
  -> 模型推理
  -> step3_3_extract_model_think.py
  -> step3_6_merge_to_sft.py
  -> step3_7_construct_rewrite_data.py
  -> 模型改写
  -> step3_8 / step3_10 merge
  -> step3_11_merge_to_dialogues.py
  -> sft_data_final.jsonl
```

### 6.1 原始 system thinking 生成

`step3_1_extract_sys_thinking_samples.py` 对每个角色的每个 assistant 回复抽样：

```json
{
  "trace_id": "...",
  "character_name": "...",
  "context_before": [...],
  "current_assistant": {...},
  "context_after": [...]
}
```

其中：

- `context_before` 是当前 assistant 前的所有消息。
- `current_assistant` 是真实目标回复。
- `context_after` 只取少量后文用于参考。
- system prompt 中的 `Requirements` 会先移除，后续构造推理输入时单独添加。

### 6.2 提取模型 thinking

`step3_3_extract_model_think.py` 从模型输出中抽取：

- `model_thinking`
- `model_response`
- `extraction_method`
- `raw_text`

它支持多种 thinking 结束标签，如 `</think>`、`</thinking>`，也支持根据角色名或 `<role_thinking>` 位置切分。

### 6.3 改写与合并

HER 不是把模型第一次生成的 thinking 直接塞回最终数据，而是有 rewrite 阶段。

`step3_7_construct_rewrite_data.py` 构造改写数据，`step3_8_merge_rewrite_results_parallel.py` 或 `step3_10_fix_and_merge.py` 合并改写结果。

最终 assistant turn 中会有：

```json
{
  "role": "assistant",
  "content": "角色名: <role_thinking>...</role_thinking><role_action>...</role_action>台词",
  "sys_thinking_revised": "...",
  "sys_thinking_original": "..."
}
```

在训练转换阶段，`sys_thinking_revised` 被包装进 assistant 内容开头：

```text
<system_thinking>{sys_thinking_revised}</system_thinking>角色名: ...
```

重要边界：

- `system_thinking` 是 assistant 标签的一部分。
- 它不是 `system.content`。
- 它应是第三人称扮演策略，与 `role_thinking/action/speech` 对齐。

## 7. Step 4: Setting Completion

核心目录：

- `/home/wz/HER/data_process_code/step4_setting_completion`

目标：用原文和已增强的对话解释角色行为，补全角色设定。

HER 文档对这一步的原则是“需求驱动增强”：

1. 分析对话中出现的行为、情绪、动机。
2. 检查原设定是否足以解释这些行为。
3. 若缺失，从原文中找依据。
4. 将能解释行为的内容补回角色设定。

输入字段：

| 字段 | 说明 |
|---|---|
| `character_profile` | 角色描述 |
| `background` | 背景/剧情摘要 |
| `scenario` | 当前场景 |
| `motivation` | 角色动机 |
| `description` | 简短描述 |
| `experience` | 角色经历 |

输出增强字段：

| 字段 | 说明 |
|---|---|
| `character_profile_enriched` | 增强角色描述 |
| `background_enriched` | 增强背景 |
| `motivation_enriched` | 增强动机 |
| `description_enriched` | 增强描述 |
| `experience_enriched` | 增强经历 |
| `setting_enrichment_reasoning` | 为什么这样补充 |

后续 `step4_3_rebuild_system_prompt.py` 会用这些增强字段重建 `system.content`。

这进一步证明 HER 的 system 是设定线产物，而不是 SFT turn 线产物。

## 8. SFT 训练数据构建

核心目录：

- `/home/wz/HER/training_code/step1_roleplay_sft`

关键脚本：

- `sync_dialogues_to_training_samples.py`
- `convert_to_sft.py`
- `split_train_test.py`
- `split_by_purpose.py`
- `split_to_single_turn.py`

### 8.1 同步 dialogue 到 training_samples

`sync_dialogues_to_training_samples.py` 负责保证 `training_samples` 与 `dialogues` 中的增强字段一致：

- assistant：保留完整 `enhanced_standard_format`，包括 `<role_thinking>`。
- user：移除 `<role_thinking>`，保留可见动作和台词。

### 8.2 转标准 SFT messages

`convert_to_sft.py` 将每个角色的 `training_samples` 写成：

```json
{
  "trace_id": "...",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

它会找到最后一个 assistant message，并只在最后一个 assistant 前加：

```text
<system_thinking>{sys_thinking_revised}</system_thinking>
```

如果是多轮样本，历史 assistant 不额外加新 `system_thinking`。

### 8.3 多轮拆单轮

`split_to_single_turn.py` 将：

```text
system + user1 + asst1 + user2 + asst2 + ... + userN + asstN
```

拆成：

```text
sample1 = system + user1 + asst1
sample2 = system + user1 + asst1 + user2 + asst2
...
sampleN = system + full history + userN + asstN
```

这个设计保留历史上下文，不是孤立的单轮问答。

## 9. Reward SFT / Reward Model 数据

核心目录：

- `/home/wz/HER/training_code/step2_reward_sft`

主文档：

- `/home/wz/HER/training_code/step2_reward_sft/DATA_PIPELINE.md`

流程：

```text
多个推理结果文件
  -> merge_datasets_for_rm.py
  -> merged_for_rm_final.jsonl
  -> process_inference_results.py
  -> inference_data_choices_0_1.jsonl
  -> rm.py 执行模型评估
  -> model_processed_enhanced_result.jsonl
  -> filter_high_quality_sft.py
  -> sft_final.jsonl / rl_final.jsonl / test_final.jsonl
  -> construct_rm_training_data.py
  -> rm_training_sft.jsonl / rm_training_rl.jsonl / rm_training_test.jsonl
```

核心设计是两阶段：

1. 第一阶段评估：给评估模型明确 principles，让模型比较候选回复。
2. 第二阶段 RM 训练：不把 principles 作为输入，让 RM 学会自己生成原则、应用原则、判断更优回复。

`construct_rm_training_data.py` 输出的是普通 chat messages：

```json
{
  "messages": [
    {"role": "user", "content": "RM prompt with context/cand_1/cand_2"},
    {"role": "assistant", "content": "```json\n{evaluation result}\n```"}
  ],
  "metadata": {
    "better_response": "cand_1",
    "num_principles": 3,
    "source": "model_evaluation"
  }
}
```

## 10. Reward RL 与 Roleplay RL

核心目录：

- `/home/wz/HER/training_code/step3_reward_rl`
- `/home/wz/HER/training_code/step4_roleplay_rl`

主文档：

- `/home/wz/HER/training_code/PIPELINE.md`

### 10.1 Reward RL

`step3_reward_rl/extract_rm_data.py` 做：

1. 从 assistant message 里用正则抽取 `better_response`。
2. 提取 `candidate_1` / `candidate_2`。
3. 构造带 `reward_model` 的 RL 训练格式。

然后 `convert_to_parquet.py` 转成 parquet。

输出格式大致：

```json
{
  "data_source": "v3_tx_sft/tx_rl4rm",
  "prompt": [
    {"role": "user", "content": "dialogue context + candidates + instruction"}
  ],
  "reward_model": {
    "answer": "cand_1",
    "problem": "",
    "solution": "cand_1"
  }
}
```

### 10.2 Roleplay RL

`step4_roleplay_rl/main.py` 做：

1. 从 roleplay RL 数据中抽取 `better_response`。
2. 从 messages 构造多轮 prompt，排除最后一个 assistant 标签答案。
3. 从 `raw_record` 中取候选回复。
4. 构造 chosen/rejected 形式的 `reward_model.solution`。

输出格式大致：

```json
{
  "data_source": "roleplay_rl_20k",
  "prompt": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "reward_model": {
    "answer": "cand_1",
    "solution": "{\"prompt\": [...], \"chosen\": \"...\", \"rejected\": \"...\"}",
    "style": "rule"
  }
}
```

随后 `step4_roleplay_rl/convert_to_parquet.py` 转 parquet。

## 11. 推理与评估

相关目录：

- `/home/wz/HER/chat_demo`
- `/home/wz/HER/eval_code`

HER 仍使用标准 chat message：

```json
[
  {"role": "system", "content": "..."},
  {"role": "user", "content": "..."},
  {"role": "assistant", "content": "..."}
]
```

`eval_code/models/chat_templates.py` 支持 ChatML/Qwen/Llama3 等 chat template，`system/user/assistant` role 没有被 HER 自定义替换。

HER 自定义的是 `assistant.content` 内部的标签协议：

- `<system_thinking>`
- `<role_thinking>`
- `<role_action>`

`chat_demo` 里支持 `--show-think` 和 `--show-rolethink`，说明这些 thinking 块在交互展示上可隐藏/展示，但训练数据里它们是 assistant 内容的一部分。

## 12. 对 role-play 项目的设计校正

### 12.1 应该照搬的 HER 原则

1. system/user/assistant 三个 chat role 的职责要分清。
2. `system.content` 单独由角色设定线生成。
3. `user.content` 只放当前目标角色可见的外部上下文。
4. `assistant.content` 承载目标角色的 hidden reasoning、visible action、speech。
5. 其他角色内心不能进入 user。
6. 可见动作可以进入 user。
7. 每条 assistant 的 `system_thinking` 应在 assistant 内容开头，不是 system prompt。
8. 单轮 SFT 可以保留历史，不必退化成孤立一问一答。

### 12.2 当前设计需要修正的点

当前 `role-play` 的 `sft_messages` 一次性生成 `system/user/assistant`，导致：

- system 每条 turn 都不同。
- system 混入当前场景切片与本轮 response strategy。
- system 出现 `target_speech` 等数据制作字段。
- `system_thinking` 和 `system.content` 的边界容易混淆。

按 HER，应改成：

```text
profile/setting line
  -> stable profile/background system components

turn/scenario line
  -> Current Scenario
  -> Information about other Characters
  -> user context
  -> assistant response with system_thinking/role_thinking/role_action/speech
  -> attach stable system components + generated scenario components
```

当前决策：先固定 `{character}'s Profile` 与 `Background`，在 `sft_messages` 阶段只让 LLM 生成 `Current Scenario` 和 `Information about other Characters`。这样保留 HER 的 scenario 机制，同时避免 LLM 每轮重写人物画像和世界观背景，降低 target speech 与 response strategy 污染 system 的风险。

### 12.3 建议的新数据结构

章节/场景 system prompt：

```json
{
  "system_id": "ch001_yezhen_v1",
  "chapter_id": "ch001",
  "character": "叶筝",
  "content": "角色设定 + 背景 + 本章节大场景 + 关系信息 + 输出协议",
  "source_basis": {
    "profile_version": "v0001",
    "chapter_summary_ids": ["..."],
    "setting_revision_ids": ["..."]
  }
}
```

SFT turn：

```json
{
  "turn_id": "ch001_t006",
  "system_id": "ch001_yezhen_v1",
  "messages": [
    {"role": "system", "content": "... resolved from system_id ..."},
    {"role": "user", "content": "叶筝本轮前可见的上下文"},
    {"role": "assistant", "content": "<system_thinking>...</system_thinking><role_thinking>...</role_thinking><role_action>...</role_action>台词"}
  ]
}
```

### 12.4 system prompt 内容边界

建议 `system.content` 包含：

- 角色身份：叶筝是谁，来自哪部作品。
- 稳定人格：表层风格、深层动机、价值观、思维方式。
- 能力/身份约束：圣女身份、社会位置、已知能力限制。
- 背景设定：世界观、阶级秩序、异能/诡域/高维系统等稳定约束。
- Current Scenario：本训练样本或场景切片开始前已经成立的可见状态。
- Information about other Characters：当前场景相关人物及关系，只写本场景需要的信息。
- 信息边界：不能预知后文，不能知道未揭露信息。
- 输出协议：`<system_thinking>`、`<role_thinking>`、`<role_action>`、speech 的格式要求。

不应包含：

- 目标台词。
- 目标台词片段。
- 本轮 response_strategy。
- 本轮“应该如何答”的具体动词。
- 数据制作字段名。
- annotation/audit/QA 结论。

### 12.5 user prompt 内容边界

建议 `user.content` 包含：

- 本轮前可见的他人台词。
- 环境状态。
- 可见动作。
- 事件压力或已知事实。
- “轮到叶筝回应”可以作为轻量收束。

不应包含：

- 叶筝即将说出的目标台词。
- 叶筝已经决定如何回应。
- 叶筝 hidden role_thinking。
- 后文才出现的信息。

### 12.6 assistant 内容边界

建议 `assistant.content` 包含：

```text
<system_thinking>第三人称扮演策略</system_thinking>
<role_thinking>叶筝第一人称内心</role_thinking>
<role_action>可见动作</role_action>
目标台词
```

如果原文没有足够动作依据，`role_action` 应轻量化，避免编造具体肢体细节。

## 13. 后续落地顺序

建议按以下顺序调整 `role-play`：

1. 新增 chapter/system prompt 生成阶段。
2. 修改 SFT 生成：不再让 LLM 生成 `system.content`。
3. SFT turn 只生成 user + assistant，或 assistant 单独生成。
4. 在响应抽取阶段按 `system_id` 注入稳定 system。
5. QA 增加 system 检查：
   - 禁止 `target_speech`、`annotation`、`source_text`。
   - 禁止目标台词片段。
   - 检查同章节 system 是否稳定。
   - 检查 system 是否包含本轮策略动词。
6. 对前两章重跑，对比：
   - system unique 数量。
   - user leakage。
   - assistant 格式合规。
   - role_action 过拟合/编造率。

## 14. HER 源码索引入口

后续继续研究时优先用 CodeGraph：

```bash
cd /home/wz/HER
codegraph explore "build_training_samples_sharegpt get_character_prompt"
codegraph explore "step3 system thinking merge sys_thinking_revised"
codegraph explore "training step1 convert_to_sft split_to_single_turn"
codegraph explore "reward sft construct_rm_training_data filter_high_quality_sft"
```

关键源码文件：

```text
/home/wz/HER/data_process_code/step1_data_process/convert_to_sft_format.py
/home/wz/HER/data_process_code/step2_gen_rolethinking/merge_enhanced_to_sft.py
/home/wz/HER/data_process_code/step3_gen_systhinking/step3_1_extract_sys_thinking_samples.py
/home/wz/HER/data_process_code/step3_gen_systhinking/step3_10_fix_and_merge.py
/home/wz/HER/data_process_code/step4_setting_completion/step4_3_rebuild_system_prompt.py
/home/wz/HER/data_process_code/step4_setting_completion/generate_training_samples.py
/home/wz/HER/training_code/step1_roleplay_sft/convert_to_sft.py
/home/wz/HER/training_code/step1_roleplay_sft/split_to_single_turn.py
/home/wz/HER/training_code/step2_reward_sft/construct_rm_training_data.py
/home/wz/HER/training_code/step3_reward_rl/extract_rm_data.py
/home/wz/HER/training_code/step4_roleplay_rl/main.py
```
