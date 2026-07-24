# Annotation Psychology Follow-up

## 背景

当前完整流程仍应先跑通一轮，再根据真实输出调整 prompt 和 schema。最近抽查 annotation 时观察到一个趋势：输出更容易集中在事实、关系和触发事件推断上，叶筝当前心理状态、压抑情绪、风险权衡和回应策略有时不够具体。

这个文档只记录后续修改方向，不代表当前已经修改 annotation prompt。

## 历史设计依据

早期已删除设计文档中，`annotation` 的定位不是最终 SFT prompt，而是从原文片段中抽取、归纳和解释出的样本注释，用来支撑：

- 定位叶筝反应 beat。
- 解释为什么该 beat 值得训练。
- 支撑 HER-style assistant 回复生成。
- 支持人工审核、筛选和人物画像修正。

历史 schema 的关键字段是：

```json
{
  "beat_type": "dialogue|event|observation|environment|inner_conflict",
  "scene_summary": "当前场景发生了什么",
  "participants": ["叶筝", "其他角色"],
  "relationship_context": "叶筝与对方的关系",
  "trigger": "对方说了什么/发生了什么",
  "dialogue_history": [],
  "yezhen_state": {
    "known_facts": ["叶筝此刻知道但未必说出的事实"],
    "goal": "她此刻想达成什么",
    "hidden_risks": ["她需要规避的风险"],
    "identity_constraints": ["身份带来的约束"],
    "emotional_underlayer": "表面平静下的真实情绪或波动"
  },
  "response_strategy": "她为什么选择这种心理、动作和台词",
  "evidence": []
}
```

早期 prompt 还明确要求：

- 区分叶筝真实心理、旁白信息和他人评价。
- 不把长期人物弧线提前写成当前明确目标。
- 重点分析目标、风险、身份约束、情绪底色和回应策略。
- evidence 只作为审核依据，不把大段原文堆进训练数据。

## 当前风险

现有 prompt 虽然保留了 `yezhen_state` 和 `response_strategy`，但心理相关内容主要压缩在 `goal` 和 `emotional_underlayer` 两个字符串字段中。LLM 在生成 annotation 时可能自然把篇幅让给：

- `scene_summary`
- `relationship_context`
- `trigger`
- `known_facts`

这会导致后续 `sft_messages` 的 `<role_thinking>` 更像事实复述，而不是叶筝当前内在判断。

另一个需要分清的边界是：人物画像应维护稳定角色画像，而不是当前场景状态。当前受伤、正在下坠、短期情绪、某一轮对话目标等应留在 annotation；只有稳定特质、长期行为模式、核心身份/能力边界、长期关系模式或旧画像错误，才应触发 profile revision。若需要修正画像，LLM 应直接输出完整新画像，而不是返回一条增量追加句。

## 暂缓修改原则

先不要在完整跑完前立即改 prompt，原因是：

- 当前流程还需要验证整本书规模下的稳定性、失败率、断点续传和最终 SFT message 质量。
- 单条或小样本里的 annotation 偏事实，不一定代表最终 `sft_messages_her.jsonl` 不可用。
- 过早扩 schema 会影响 tests、response parsing、profile revision 和 SFT message prompt，风险面较大。

## 完整跑完后的评估清单

完整生成 `outputs/all/sft_messages_her.jsonl` 后，优先抽查这些问题：

- `<role_thinking>` 是否只复述事实，缺少“我为什么这样说”的内在动机。
- `<system_thinking>` 是否能体现信息边界、身份约束、风险和策略。
- annotation 的 `emotional_underlayer` 是否经常为空、泛泛而谈或与原文无关。
- `response_strategy` 是否能连接“触发内容 -> 当前心理 -> 行动/台词选择”。
- 对没有强心理描写的片段，模型是否硬编眼神、冷意、杀意、微笑等原文不支持的状态。
- 人物画像修正后，后续 annotation 是否真正使用了稳定画像，而不是把当前场景状态写进画像。

## 候选修改方向

如果完整一轮结果确认心理分析不足，再考虑把 annotation 输出调整为更心理导向的结构：

```json
{
  "scene_summary": "",
  "participants": [],
  "relationship_context": "",
  "visible_trigger": "",
  "dialogue_history": [],
  "yezhen_state": {
    "known_facts": [],
    "goal": "",
    "inner_conflict": "",
    "hidden_risks": [],
    "identity_constraints": [],
    "emotional_underlayer": "",
    "behavioral_intent": ""
  },
  "response_strategy": ""
}
```

调整重点：

- 保留事实字段，但让事实字段服务于心理分析。
- 增加 `inner_conflict`，单独承载当前矛盾、压抑和风险权衡。
- 增加 `behavioral_intent`，描述她接下来为什么选择沉默、追问、回避、试探或正面回应。
- 不在 prompt 中写死与任务无关的人设信息。
- 不把 `evidence`、审计字段、训练用途字段重新塞进最终 SFT messages。

## 后续动作

1. 先完成整本书一轮 pipeline 输出。
2. 用抽样方式检查 annotation、profile snapshot 和最终 HER messages 是否一致。
3. 如果心理层确实不足，再改 annotation prompt、response parser 和相关 tests。
4. 改完后用同一批章节做 before/after 对比，重点比较 `<role_thinking>` 和 `<system_thinking>` 的角色状态质量。
