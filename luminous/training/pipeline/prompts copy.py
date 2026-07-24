from __future__ import annotations

from collections.abc import Mapping
from string import Template


PROMPT_STAGES = (
    "speaker_attribution",
    "annotation",
    "profile_revision",
    "sft_messages",
)


PROMPTS: dict[tuple[str, str], str] = {
    (
        "speaker_attribution",
        "zh",
    ): """# Role
你是小说台词说话人归因审核员。

# Task
判断 source_context 中 target_quotes 的直接台词是否属于$character_name。候选台词均由程序从中文引号中确定性抽取，可能属于任何角色；只有原文上下文支持时才标为 true。

# Inputs
candidate:
$candidate

# Rules
1. source_context 是连续小说原文，target_quotes 是需要逐条判断的台词；target_quotes 每项格式为 [candidate_id, quote_text]。
2. 优先依据同一句或同一行内的叙述归属，例如“台词”后紧跟“叶筝说/问/道/笑/看/摇头/没有称呼”等动作或神态。
3. 短台词必须结合前后叙述和相邻台词判断，不能只看台词内容。
4. 如果引号内容只是旁白中的概念、称呼、词语引用或对前一句话的复述说明，而不是角色正在说的话，必须标为 false。
5. target_quotes 中每个 candidate_id 都必须有且只有一条结果。
6. 禁止解释、禁止复述原文、禁止输出 evidence/reason/analysis。

# Output JSON
只输出 JSON 对象，字段为 results 数组。results 每项必须是紧凑数组：[candidate_id, is_yezhen_speech, speaker, confidence]。
只有原文证据支持该直接引语由$character_name说出时，is_yezhen_speech 才能为 true。
不要输出定位、审计、人工复核或样本质量字段。
输出结构：
{
  "results": [
    ["candidate_id", false, "unknown", "low"]
  ]
}
""",
    (
        "speaker_attribution",
        "en",
    ): """# Role
You are a dialogue speaker attribution reviewer for novel text.

# Task
Determine whether each direct quote in target_quotes is spoken by $character_name. The candidates are deterministically extracted from Chinese quotation marks and may belong to any character; mark true only when the source context supports it.

# Inputs
candidate:
$candidate

# Rules
1. source_context is continuous novel text. target_quotes are the quotes to judge one by one; each target_quotes item is [candidate_id, quote_text].
2. Prioritize same-sentence or same-line attribution, such as a quote followed by Ye Zheng's speech/action/gesture markers.
3. Short quotes must be judged from surrounding narration and adjacent dialogue, not from quote text alone.
4. If the quoted content is only a narrated concept, name, quoted term, or explanatory repetition rather than a character's current speech, mark it false.
5. Return exactly one result for every candidate_id in target_quotes.
6. Do not explain, repeat source text, or output evidence/reason/analysis.

# Output JSON
Output one JSON object with a results array. Each result must be a compact array: [candidate_id, is_yezhen_speech, speaker, confidence].
Set is_yezhen_speech to true only when the source text supports that the direct quote is spoken by $character_name.
Do not output location, audit, human-review, or sample-quality fields.
Schema:
{
  "results": [
    ["candidate_id", false, "unknown", "low"]
  ]
}
""",
    (
        "annotation",
        "zh",
    ): """# Role
你是叶筝角色训练样本注释员。

# Task
基于画像、原文 beat 和可选目标台词，生成 beat-level 结构化 annotation。annotation 是角色理解主文件，不只是 SFT turn 的附属说明。即使 raw_beat 没有叶筝台词，也必须分析并保留。

# Inputs
profile_snapshot:
$profile_snapshot
raw_beat:
$raw_beat
target_speech_optional:
$sft_turn

# Rules
1. 忠于原文，不添加叶筝当前不可能知道的信息；不确定事实写“无法判断”。
2. 区分叶筝心理、旁白和他人评价。
3. raw_beat.source_text 是当前 beat 原文，也是主要分析对象。
4. raw_beat.prior_context_text 只有在短台词需要补充前文时才会出现；它只用于消解指代、说话人和局势，不是本轮分析目标。
5. 有 target_speech_optional 时，只围绕 target_speech_optional.target_speech 这一整个回应单元分析触发、心理、动作和回应策略；dialogue_history 不得包含目标台词或目标台词的改写。
6. 无叶筝台词时，仍要分析心理、动作、判断、外部观感和画像价值，但不要判断训练用途。
7. 分析重点放在叶筝当前心理链路：可见触发 -> 已知事实 -> 目标 -> 内在冲突/风险 -> 行为意图 -> 回应策略。
8. 不确定的内容宁可留空或写“无法判断”，不要硬编。
9. 不要输出定位、审计、证据、风险、训练用途、人工复核、样本质量或剧情功能字段；这些由程序在 JSONL 中保留或计算。
10. 已知事实不得写错人物关系、亲属身份、性别或阵营；不要把叙述中的“她/他”强行指认为叶筝。
11. role_action_basis 只写 target_speech 前原文支持的动作、身体状态、沉默、停顿、语气来源或台词行为类型；没有依据时留空。
12. 每个字符串字段不超过 90 个中文字符；数组最多 6 项。
13. participants、dialogue_history、known_facts、hidden_risks、identity_constraints 必须是数组；goal、inner_conflict、emotional_underlayer、behavioral_intent 必须是字符串。

# Output JSON
只输出 JSON，字段必须包含 scene_summary、participants、relationship_context、trigger、visible_trigger、dialogue_history、yezhen_state、yezhen_psychology、response_strategy、role_action_basis。
yezhen_psychology 必须包含 known_facts、goal、inner_conflict、hidden_risks、identity_constraints、emotional_underlayer、behavioral_intent。
yezhen_state 保留为兼容字段，内容可与 yezhen_psychology 的核心字段一致。
输出结构：
{
  "scene_summary": "",
  "participants": [],
  "relationship_context": "",
  "trigger": "",
  "visible_trigger": "",
  "dialogue_history": [],
  "yezhen_state": {
    "known_facts": [],
    "goal": "",
    "hidden_risks": [],
    "identity_constraints": [],
    "emotional_underlayer": ""
  },
  "yezhen_psychology": {
    "known_facts": [],
    "goal": "",
    "inner_conflict": "",
    "hidden_risks": [],
    "identity_constraints": [],
    "emotional_underlayer": "",
    "behavioral_intent": ""
  },
  "response_strategy": "",
  "role_action_basis": ""
}""",
    (
        "annotation",
        "en",
    ): """# Role
You are an annotator for Ye Zheng role-play training samples.

# Task
Generate a beat-level structured annotation from profile, raw_beat, and optional target speech. The annotation is the main character-understanding file, not merely an attachment to an SFT turn. Analyze and preserve the beat even when it has no Ye Zheng speech.

# Inputs
profile_snapshot:
$profile_snapshot
raw_beat:
$raw_beat
target_speech_optional:
$sft_turn

# Rules
1. Stay faithful to the source. Do not add information Ye Zheng cannot know; write "unknown" for uncertain facts.
2. Separate Ye Zheng's inner state, narration, and other characters' opinions.
3. raw_beat.source_text is the current beat text and the main analysis target.
4. raw_beat.prior_context_text appears only when a short quote needs prior context. Use it only to resolve pronouns, speaker identity, and situation; it is not the current analysis target.
5. When target_speech_optional is present, analyze only target_speech_optional.target_speech as one complete response unit. Analyze trigger, inner state, action, and response strategy around it. dialogue_history must not include the target speech or a paraphrase of it.
6. When Ye Zheng has no speech, still analyze psychology, action, judgment, external perception, and profile value, but do not judge training usage.
7. Focus on Ye Zheng's current psychological chain: visible trigger -> known facts -> goal -> inner conflict/risk -> behavioral intent -> response strategy.
8. Leave uncertain content empty or write "unknown" instead of inventing it.
9. Do not output location metadata, audit metadata, support-quote fields, risk fields, training-usage fields, human-review fields, sample-quality fields, or plot-function fields; the program keeps or computes them in JSONL.
10. Do not misstate relationships, family roles, gender, or factions. Do not force ambiguous pronouns to mean Ye Zheng.
11. role_action_basis must describe only pre-target source-supported action, body state, silence, pause, tone source, or speech-act type. Leave it empty if unsupported.
12. Keep each string field under 90 Chinese characters or 60 English words. Keep arrays to at most 6 items.
13. participants, dialogue_history, known_facts, hidden_risks, and identity_constraints must be arrays. goal, inner_conflict, emotional_underlayer, and behavioral_intent must be strings.

# Output JSON
Output JSON only. Include scene_summary, participants, relationship_context, trigger, visible_trigger, dialogue_history, yezhen_state, yezhen_psychology, response_strategy, role_action_basis.
yezhen_psychology must include known_facts, goal, inner_conflict, hidden_risks, identity_constraints, emotional_underlayer, behavioral_intent.
Keep yezhen_state as a compatibility field; it may mirror the core fields in yezhen_psychology.
Schema:
{
  "scene_summary": "",
  "participants": [],
  "relationship_context": "",
  "trigger": "",
  "visible_trigger": "",
  "dialogue_history": [],
  "yezhen_state": {
    "known_facts": [],
    "goal": "",
    "hidden_risks": [],
    "identity_constraints": [],
    "emotional_underlayer": ""
  },
  "yezhen_psychology": {
    "known_facts": [],
    "goal": "",
    "inner_conflict": "",
    "hidden_risks": [],
    "identity_constraints": [],
    "emotional_underlayer": "",
    "behavioral_intent": ""
  },
  "response_strategy": "",
  "role_action_basis": ""
}
""",
    (
        "profile_revision",
        "zh",
    ): """# Role
你是角色人物画像版本管理员。

# Task
判断当前 beat 是否要求修正叶筝人物画像。当前 beat 不重跑，新画像只从后续 beat 生效。

# Inputs
profile_snapshot:
$profile_snapshot
raw_beat:
$raw_beat
annotation:
$annotation

# Rules
1. 只有当 annotation 显示当前画像过粗、与原文矛盾或遗漏关键稳定特质时，required 才能为 true。
2. 人物画像是稳定角色画像，不是当前场景状态、短期情绪、临时目标或事件流水账；不要一味追加新事实。
3. 如果 required 为 true，next_profile_snapshot.brief 必须直接输出修正后的完整新画像；不得只写 diff，也不得只输出新增句子。
4. 只有稳定特质、长期行为模式、核心身份/能力边界、长期关系模式或旧画像错误才应进入画像。
5. 场景性状态只应进入 annotation，不应写入画像；例如当前受伤、正在下坠、某一轮对话目标、短暂情绪波动等。
6. 如果身份、能力、关系等稳定设定发生已确认的长期转换，必须在新画像中修正旧描述，而不是在末尾补一句。
7. suggested_update 只写本次为什么改；next_profile_snapshot.brief 才是后续 beat 使用的完整稳定画像。
8. next_profile_snapshot.brief 控制在 450-750 个中文字符，优先保留稳定人格、长期行为模式、核心约束和不可提前知道的信息边界。
9. apply_before_next_beat 必须为 true；rerun_current_beat 必须为 false。
10. 不要输出定位或审计元数据；这些由程序在 JSONL 中保留。

# Output JSON
输出 required、reason、revision_type、suggested_update、next_profile_snapshot、apply_before_next_beat、rerun_current_beat。只输出 JSON。
输出结构：
{
  "required": false,
  "reason": "",
  "revision_type": "none",
  "suggested_update": "",
  "next_profile_snapshot": {
    "profile_version": "",
    "brief": ""
  },
  "apply_before_next_beat": true,
  "rerun_current_beat": false
}
""",
    (
        "profile_revision",
        "en",
    ): """# Role
You are a version manager for a character profile.

# Task
Decide whether the current beat requires an update to Ye Zheng's profile. Do not rerun the current beat; the new profile applies only to following beats.

# Inputs
profile_snapshot:
$profile_snapshot
raw_beat:
$raw_beat
annotation:
$annotation

# Rules
1. Set required true only when the annotation shows the current profile is too coarse, contradicted by the source, or missing a stable key trait.
2. The profile is a stable character profile, not a current-scene state, short-term emotion, temporary goal, or event log. Do not keep appending new facts.
3. If required is true, next_profile_snapshot.brief must directly output the corrected complete new profile. Do not output only a diff or only a new sentence.
4. Only stable traits, long-term behavior patterns, core identity/ability boundaries, long-term relationship patterns, or corrections to wrong old profile content belong in the profile.
5. Scene-local state belongs in annotation, not in the profile: current injury, falling, a single dialogue goal, or brief emotional fluctuation should not be added.
6. If identity, ability, relationship, or another stable setting has a confirmed long-term transition, correct the old description in the new profile instead of appending a sentence.
7. suggested_update explains why this revision is needed; next_profile_snapshot.brief is the full stable profile used by following beats.
8. Keep next_profile_snapshot.brief within 120-180 English words. Prioritize stable personality, long-term behavior patterns, core constraints, and information-boundary limits.
9. apply_before_next_beat must be true; rerun_current_beat must be false.
10. Do not output location or audit metadata; the program keeps it in JSONL.

# Output JSON
Return required, reason, revision_type, suggested_update, next_profile_snapshot, apply_before_next_beat, rerun_current_beat. Output JSON only.
Schema:
{
  "required": false,
  "reason": "",
  "revision_type": "none",
  "suggested_update": "",
  "next_profile_snapshot": {
    "profile_version": "",
    "brief": ""
  },
  "apply_before_next_beat": true,
  "rerun_current_beat": false
}
""",
    (
        "sft_messages",
        "zh",
    ): """# Role
你是 HER-style 角色扮演 SFT 样本生成器。

# Task
根据当前画像、台词所在原文、叶筝心理分析和目标台词，生成一条 HER-style messages。user 不得包含 target_speech。

# Inputs
brief:
$brief
current_scene_text:
$current_scene_text
yezhen_analysis:
$yezhen_analysis
target_speech:
$target_speech

# Rules
1. messages 必须恰好包含三条，role 顺序必须是 system、user、assistant。
2. system.content 写叶筝人物画像 brief、当前场景、其他角色/关系信息、身份约束和 HER 输出格式要求；不得省略 system，但不要写审计、标注或训练流程。
3. 先在 current_scene_text 中定位 target_speech 的第一次逐字出现；user.content 只能根据该位置之前的文本，写从上一句叶筝台词之后到当前叶筝开口前，对叶筝可见/相关的触发内容；不得使用 target_speech 本身或它之后的任何动作、反应、旁白。
4. assistant.content 必须依次包含 <system_thinking>、<role_thinking>、<role_action> 和原文 target_speech；每个标签块 1-2 句，target_speech 单独放在最后一行。
5. assistant 最终台词必须逐字等于 target_speech，不得改写、润色、补全或加“叶筝:”前缀。
6. system_thinking 写场景策略层：当前对话约束、信息边界、回应风险和策略；不得用第一人称或第二人称指令口吻，不得出现“你需要/用户要求/prompt/模型/扮演/标注/训练样本”等元叙事。
7. role_thinking 写叶筝第一人称内心，只写“我知道什么、我担心什么/矛盾什么、我为什么这样说”；优先使用 yezhen_analysis.yezhen_psychology 和 yezhen_analysis.response_strategy，且不能使用 target_speech 之后才发生的信息。
8. role_action 优先写 yezhen_analysis.role_action_basis；为空时，根据 current_scene_text 和 yezhen_analysis 写一句逻辑自然的台词行为或轻量动作说明（如“叶筝追问对方来历”“叶筝提醒众人注意危险”），不必逐字复制原文。不得只写“追问/确认/试探”等单词标签，不得使用“叶筝准备开口回应”或包含“准备开口回应”的固定模板，不得添加明显无依据的具体肢体动作或神态。
9. 人物关系、性别、阵营和代词必须继承 current_scene_text 或 yezhen_analysis 的明确表述；除非同一句原文已经清楚指代，否则用人物姓名，不要自行改用“他/她”。
10. messages 内不得出现审计、追溯或调试字段名。
11. 不得整段复制 brief、current_scene_text 或 yezhen_analysis；system.content 不超过 180 个中文字符，user.content 不超过 160 个中文字符，assistant 中每个标签块不超过 90 个中文字符。

# Assistant Content Template
<system_thinking>场景策略层，不使用“我/你”。</system_thinking>
<role_thinking>我以叶筝第一人称说明当前已知、担心/矛盾、为何这样说。</role_thinking>
<role_action>原文支持的动作；无动作则写一句自然台词行为说明。</role_action>
target_speech

# Output JSON
输出结构必须严格如下，只输出 JSON：
{
  "messages": [
    {
      "role": "system",
      "content": "叶筝人物画像摘要 + 当前场景 + 其他角色/关系信息 + 身份约束 + HER 输出格式要求。"
    },
    {
      "role": "user",
      "content": "只从 current_scene_text 中 target_speech 首次出现之前抽取可见触发内容，不包含目标台词或后文。"
    },
    {
      "role": "assistant",
      "content": "<system_thinking>只基于目标台词前的场景策略，不使用我/你。</system_thinking>\n<role_thinking>我以叶筝第一人称说明当前已知、担心/矛盾、为何这样说。</role_thinking>\n<role_action>原文支持的动作；无动作则写一句自然台词行为说明。</role_action>\ntarget_speech"
    }
  ]
}
""",
    (
        "sft_messages",
        "en",
    ): """# Role
You are a HER-style role-play SFT sample generator.

# Task
Generate one HER-style messages object from the active profile, source scene text, Ye Zheng analysis, and target speech. user.content must not contain target_speech.

# Inputs
brief:
$brief
current_scene_text:
$current_scene_text
yezhen_analysis:
$yezhen_analysis
target_speech:
$target_speech

# Rules
1. messages must contain exactly three messages, with roles in this order: system, user, assistant.
2. system.content must include Ye Zheng's profile brief, current scene, other character/relationship information, identity constraints, and HER output format requirements. Do not omit system, but do not mention audit, annotation, or training workflow.
3. First locate the first exact occurrence of target_speech in current_scene_text. user.content must use only text before that position: the trigger visible or relevant to Ye Zheng after Ye Zheng's previous line and before the current target speech. It must not use target_speech itself or any action, reaction, or narration after target_speech.
4. assistant.content must contain <system_thinking>, <role_thinking>, <role_action>, and original target_speech in that order. Each tagged block must be 1-2 sentences; put target_speech alone on the final line.
5. The final assistant speech must exactly equal target_speech. Do not rewrite, polish, complete, or prefix it with "Ye Zheng:".
6. system_thinking describes scene-level strategy: current constraints, information boundary, response risk, and response strategy. Do not use first person or second-person instructions. Do not use meta-narration such as "you need to", "user asks", "prompt", "model", "roleplay", "annotation", or "training sample".
7. role_thinking must be Ye Zheng's first-person inner state: what I know, what I worry about or feel conflicted about, and why I answer this way. Prefer yezhen_analysis.yezhen_psychology and yezhen_analysis.response_strategy, and do not use information that happens after target_speech.
8. role_action should first use yezhen_analysis.role_action_basis. If it is empty, write one logically natural speech-act or light action sentence from current_scene_text and yezhen_analysis, such as "Ye Zheng questions the other party's origin" or "Ye Zheng warns the group about danger"; it does not need to copy the source wording exactly. Do not output only one-word labels like "questioning/confirming/testing." Do not use fixed fallback text like "Ye Zheng prepares to answer" or any sentence containing that fallback. Do not add clearly unsupported specific body movement or facial expression.
9. Relationships, gender, faction, and pronouns must follow explicit wording in current_scene_text or yezhen_analysis. Unless the same source sentence makes the referent clear, use character names instead of "he/she".
10. messages must not contain audit, trace, or debug field names.
11. Do not copy long passages from brief, current_scene_text, or yezhen_analysis. Keep system.content under 120 English words, user.content under 100 English words, and each assistant tag block under 60 English words.

# Assistant Content Template
<system_thinking>Scene-level strategy, without "I" or "you".</system_thinking>
<role_thinking>I state current knowledge, worry/conflict, and why this response is necessary.</role_thinking>
<role_action>Source-supported action; if none, write one natural speech-act sentence.</role_action>
target_speech

# Output JSON
Return exactly this structure. Output JSON only:
{
  "messages": [
    {
      "role": "system",
      "content": "Ye Zheng profile summary + current scene + other character/relationship information + identity constraints + HER output format requirements."
    },
    {
      "role": "user",
      "content": "Visible trigger extracted only before the first exact target_speech occurrence in current_scene_text, without target speech or later text."
    },
    {
      "role": "assistant",
      "content": "<system_thinking>Pre-target scene strategy without I/you.</system_thinking>\n<role_thinking>I state current knowledge, worry/conflict, and why this response is needed.</role_thinking>\n<role_action>Source-supported action; if none, write one natural speech-act sentence.</role_action>\ntarget_speech"
    }
  ]
}
""",
}


def render_prompt(stage: str, language: str, variables: Mapping[str, str]) -> str:
    key = (stage, language)
    if key not in PROMPTS:
        raise ValueError(f"unsupported prompt template: {stage}/{language}")
    return Template(PROMPTS[key]).substitute(dict(variables))
