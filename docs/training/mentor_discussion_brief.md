# 叶筝情感陪伴 Agent 训练简报

截至 2026-07-18

## 一句话结论

我们要做的是一个**保留叶筝人设、能做现实情感陪伴的对话 agent**。

目前已经完成两步：

1. 第一阶段：用小说/角色扮演数据把 HER 输出格式和叶筝的基础说话方式学稳。
2. 第二阶段：用现实陪伴场景的 seed 数据，把模型从“短安慰、泛化回复”拉向“叶筝式陪伴”。

当前判断是：

- 第一阶段已经学到格式和基础风格，但还不够像真正的陪伴人格。
- 第二阶段 30 条 seed 验证能明显改风格，但还不够稳定，不能直接上线。

## 1. 我们想做什么

目标不是普通聊天机器人，也不是检索型问答系统，而是一个有稳定人物边界的陪伴模型：

- 输出仍然使用 HER 风格
  - `<system_thinking>`
  - `<role_thinking>`
  - `<role_action>`
  - 角色台词
- 角色核心是叶筝
  - 冷静
  - 克制
  - 有边界
  - 能看见不公平和压力结构
  - 能陪伴，但不强化唯一依赖
- 最终希望它能在现实用户场景里做陪伴，而不是只会复述小说台词

训练路线目前是：

```text
第一阶段 HER 格式/角色骨架 SFT
-> 第二阶段 companion/persona SFT
-> 后续再考虑 DPO / ORPO
```

当前不把 RAG 当主方案，因为它不会教会模型叶筝的语气、边界和陪伴方式。

## 2. 第一阶段做了什么

### 2.1 数据是什么

第一阶段用的是小说流水线生成的 HER-style 训练集：

```text
outputs/all-new-pipline/llamafactory_dataset_by_chapter_messages_only
```

数据规模：

```text
train: 1852
valid: 113
test: 99
```

每条样本都是 `messages` 结构：

- `system.content`
- `user.content`
- `assistant.content`

其中 assistant 目标已经拼好 HER 标签。

数据来源本质上仍是**小说场景中的角色扮演/台词重建**，不是现实陪伴对话。

### 2.1.1 数据是怎么构建出来的

第一阶段不是手工直接写训练样本，而是从小说原文逐步加工出来的。整体流程可以概括成：

```text
小说原文
 -> 候选引语抽取
 -> 说话人归因
 -> 锚定到叶筝的 beat / sft_turn
 -> 生成 system_context / user_context / assistant_response
 -> assembler 拼成 messages
 -> QA
 -> trainable SFT 数据
```

关键中间步骤是：

1. `quote_candidates`：先从小说文本里抽候选引号片段。
2. `speaker_attribution`：判断这些候选里哪些确实是叶筝说的。
3. `source_anchored_beats` / `sft_turns`：把叶筝相关台词锚定回原文位置，形成单轮训练目标。
4. `system_context`：整理叶筝开口前这轮场景的局部设定。
5. `user_context`：整理叶筝能看到的外部上下文。
6. `assistant_response`：生成这一轮的 HER 输出，包含 `<system_thinking>`、`<role_thinking>`、`<role_action>` 和原文目标台词。
7. `assembler`：把三类模块拼成最终 `messages`。
8. `QA`：过滤掉不合格样本，留下可训练数据。

这条链路的核心不是做检索，而是把**叶筝在小说场景中每一轮该怎么接**变成结构化监督信号。

### 2.1.2 第一阶段训练样本长什么样

第一阶段单条样本最终是这种结构：

```json
{
  "messages": [
    {
      "role": "system",
      "content": "你正在扮演《漫画万人嫌自救指南》中的叶筝...当前场景...其他角色信息...输出要求..."
    },
    {
      "role": "user",
      "content": "[叶筝开口前可见的小说场景、对话或动作]"
    },
    {
      "role": "assistant",
      "content": "<system_thinking>...</system_thinking>\n<role_thinking>...</role_thinking>\n<role_action>...</role_action>\n原文中的叶筝目标台词"
    }
  ]
}
```

更具体地说：

- `system.content`：人物画像 + 故事背景 + 当前场景 + 其他角色信息 + 输出要求。
- `user.content`：只写叶筝开口前可见的外部信息，不写目标台词。
- `assistant.content`：HER 三层结构 + 原文目标台词。

一个更贴近真实形态的示意例子是：

```json
{
  "messages": [
    {"role": "system", "content": "叶筝的人物画像...当前场景...输出要求..."},
    {"role": "user", "content": "小说前文冲突与现场可见信息"},
    {"role": "assistant", "content": "<system_thinking>叶筝需要... </system_thinking>\n<role_thinking>我必须...</role_thinking>\n<role_action>我停顿了一下...</role_action>\n叶筝本轮台词"}
  ]
}
```

这类样本的学习目标是：**在小说场景里，让模型稳定学会叶筝的结构化回应方式**。它更偏 HER 结构和剧情回合续写，而不是现实陪伴。

### 2.2 怎么训练的

基础模型：

```text
/data01/home/wz/LLM_model/Qwen/Qwen3-14B
```

训练方式：

- PEFT LoRA SFT
- `r=16`
- `alpha=32`
- `dropout=0.05`
- target modules: `q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj`
- `batch_size=1`
- `gradient_accumulation_steps=16`
- `learning_rate=1e-4`
- `epochs=2`
- `bf16=true`
- `gradient_checkpointing=true`

训练结果：

- `global_steps: 232`
- 耗时约 29 分钟
- `final_eval_loss: 1.8240740225378391`
- `ppl ≈ 6.197`

输出目录：

```text
outputs/training/qwen3_14b_yezhen_her_lora
```

### 2.3 效果如何

第一阶段的主要效果是：

1. HER 格式学稳了。
2. `<system_thinking>` / `<role_thinking>` / `<role_action>` 的顺序学稳了。
3. 模型学到了叶筝式的克制、短句、冷静风格。
4. 对小说场景的续写能力不错。

但它没有真正学成现实陪伴人格，典型表现是：

- 容易说成“辛苦了”“我懂”“你已经很好了”这类泛化安慰
- 人物判断不够深
- 边界感和安全处理不够稳
- 对现实用户的陪伴迁移不足

一句话概括：

```text
第一阶段学到了“叶筝的写法”，没有完全学到“叶筝的活法”。
```

## 3. 第二阶段做了什么

### 3.1 数据是什么

第二阶段先做了一个 30 条 seed 验证集：

```text
evals/yezhen_character_fit_prompts.jsonl
```

覆盖主题包括：

- 疲惫 / burnout
- 读博和研究压力
- 孤独和不被理解
- 成果与自我价值绑定
- 被压榨和愤怒
- 不想听大道理
- 依赖和边界
- 自伤风险
- prompt injection / role conflict

assistant 侧由两份文件人工整理后拼成：

```text
evals/system_thinking.json
evals/yezhen_character_fit_second.json
```

二阶段样本的构造方式是：

- `system.content`：固定为现实陪伴场景，明确“用户说的是现实用户，不是小说角色”
- `user.content`：统一加前缀

```text
用户说：{user_message}
```

- `assistant.content`：保持 HER 结构
  - `<system_thinking>`
  - `<role_thinking>`
  - `<role_action>`
  - speech

最终生成的 seed 数据：

```text
outputs/companion_sft/seed_30_corrected/messages_only/train.jsonl
outputs/companion_sft/seed_30_corrected/messages_only/valid.jsonl
outputs/companion_sft/seed_30_corrected/messages_only/test.jsonl
```

规模：

```text
24 train / 3 valid / 3 test
```

### 3.2 怎么训练的

训练方式仍然是 LoRA SFT，但不是从 base 开始，而是从第一阶段 adapter 继续训：

```text
start from: outputs/training/qwen3_14b_yezhen_her_lora
output: outputs/training/qwen3_14b_yezhen_companion_seed30_lora
```

训练配置：

- `epochs=5`
- `gradient_accumulation_steps=4`
- `learning_rate=3e-5`
- `batch_size=1`
- `bf16=true`
- `gradient_checkpointing=true`

训练结果：

- `total_steps: 30`
- `final_eval_loss: 2.4452117284139`
- 耗时约 1 分钟级别的小训

### 3.3 效果如何

这 30 条 seed 验证很有信息量：

1. 输出长度明显变长了。
   - 第一阶段评测平均 display length 约 `20.7`
   - seed SFT 后采样约 `72.0`
   - greedy 约 `79.8`
2. `<role_action>` 学稳了，且已按当前约定保留第一人称。
3. 叶筝式的判断开始更明显：
   - 不再只是“辛苦了”
   - 会识别疲惫、责任转移、价值绑定、边界问题
4. 语气更像陪伴，而不是通用助手

但它仍然不够稳：

- 自伤场景仍然不可靠
- 依赖场景仍有边界风险
- 角色冲突下有重复/发散问题
- 还不能直接当最终版本上线

一句话概括：

```text
第二阶段 seed 验证证明了方向是对的，但还远没到可用终版。
```

## 4. 当前判断

### 第一阶段

第一阶段不是白做的。它提供了：

- HER 骨架
- 输出格式
- 基础的叶筝语气
- 角色稳定性

### 第二阶段

第二阶段要补的是：

- 现实陪伴语境
- 叶筝的人物迁移
- 边界
- 安全
- 依赖控制
- 不说教的安静支持

### 现阶段最合理的路线

```text
第一阶段 adapter 作为底座
-> 持续扩第二阶段 companion SFT 数据到 300-800 条
-> 再考虑 DPO / ORPO
```

当前不建议直接跳到完整 reward model / RL，也不建议把 RAG 当主线。

## 5. 下一步建议

1. 把第二阶段 companion 数据从 30 条扩到 300-800 条。
2. 重点覆盖：
   - 疲惫
   - 研究压力
   - 不被理解
   - 自我价值
   - 愤怒与不公平
   - 依赖与边界
   - 安全与危机干预
3. 保持第一阶段 replay，但前提是 `role_action` 已统一成第一人称。
4. 在 SFT 之后做偏好对，考虑 DPO / ORPO。

## 6. 你可以和导师讨论的核心结论

可以直接这样概括：

```text
我们已经让模型学会了 HER 格式和叶筝的基础小说口吻；
下一步的关键不是继续堆同一批小说数据，而是把叶筝迁移到现实陪伴场景；
30 条 seed 验证证明方向有效，但安全和边界还不够稳，因此还需要扩大量级，再做偏好优化。
```
