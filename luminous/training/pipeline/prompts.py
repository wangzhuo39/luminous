from __future__ import annotations

from collections.abc import Mapping
from string import Template


PROMPT_STAGES = (
    "speaker_attribution",
    "annotation",
    "profile_revision",
    "system_context",
    "user_context",
    "assistant_response",
    "sft_messages",
    "user_repair",
)


PROMPTS: dict[tuple[str, str], str] = {
    (
        "speaker_attribution",
        "zh",
    ): """# Role
你是小说台词说话人归因审核员。

# Task
判断 source_context 中每一句候选是否由$character_name说出。候选台词可能属于任何角色；只有原文上下文支持时才标为 true。

# Inputs
candidate:
$candidate

# Rules
1. source_context 是连续小说原文；target_quotes 是需要逐条判断的候选台词，每项格式为 [candidate_id, quote_text]。
2. 优先依据同一句或同一行内的叙述归属，例如“台词”后紧跟“叶筝说/问/道/笑/看/摇头/没有称呼”等动作或神态。
3. 短台词必须结合前后叙述和相邻台词判断，不能只看台词内容。
4. 如果引号内容只是旁白中的概念、称呼、词语引用或对前一句话的复述说明，而不是角色正在说的话，必须标为 false。
5. 如果引号内容是其他角色的回忆、梦境、转述、复述或脑内回放中的$character_name旧台词，不属于当前场景里$character_name正在说话，必须标为 false。
6. target_quotes 中每个 candidate_id 都必须有且只有一条结果。
7. 禁止解释、禁止复述原文、禁止输出 evidence/reason/analysis。

# Output JSON
只输出 JSON 对象，字段为 results 数组。results 每项必须是紧凑数组：[candidate_id, is_yezhen_speech, speaker, confidence]。
candidate_id 原样返回；is_yezhen_speech 表示该引语是否由$character_name说出；speaker 写可判断出的说话人，不能判断写 unknown；confidence 只能是 high、medium 或 low。
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
Determine whether each candidate direct quote in target_quotes is spoken by $character_name. The candidate quotes may belong to any character; mark true only when the source context supports it.

# Inputs
candidate:
$candidate

# Rules
1. source_context is continuous novel text. target_quotes are the candidate quotes to judge one by one; each target_quotes item is [candidate_id, quote_text].
2. Prioritize same-sentence or same-line attribution, such as a quote followed by Ye Zheng's speech/action/gesture markers.
3. Short quotes must be judged from surrounding narration and adjacent dialogue, not from quote text alone.
4. If the quoted content is only a narrated concept, name, quoted term, or explanatory repetition rather than a character's current speech, mark it false.
5. If the quote is Ye Zheng's old line inside another character's memory, dream, retelling, repetition, or mental replay, and Ye Zheng is not speaking in the current scene, mark it false.
6. Return exactly one result for every candidate_id in target_quotes.
7. Do not explain, repeat source text, or output evidence/reason/analysis.

# Output JSON
Output one JSON object with a results array. Each result must be a compact array: [candidate_id, is_yezhen_speech, speaker, confidence].
Return candidate_id unchanged. is_yezhen_speech says whether the quote is spoken by $character_name. speaker is the inferred speaker, or unknown when unclear. confidence must be high, medium, or low.
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
你是小说角色心理分析员，专门分析叶筝在一段原文中的视角、心理和回应方式。

# Task
根据当前叶筝画像和这段小说原文，分析叶筝在此刻能看见什么、知道什么、想达成什么、内心有什么压力或矛盾，以及她如何回应。若提供了 target_speech，只围绕这句目标台词发生前后的叶筝心理链分析；若没有目标台词，也分析这段原文对叶筝画像和心理理解的价值。

# Inputs
profile_snapshot:
$profile_snapshot
source_passage:
$raw_beat
target_speech:
$sft_turn

# Rules
1. 忠于原文，不添加叶筝当前不可能知道的信息；不确定事实写“无法判断”。
2. 区分叶筝心理、旁白和他人评价。
3. source_passage.source_text 是主要分析对象；source_passage.prior_context_text 若存在，只用于理解指代、说话人和局势。
4. 有 target_speech 时，只分析目标台词这一整个回应单元；
5. 无目标台词时，仍要分析叶筝的观察、判断、心理、动作和画像价值。
6. 分析重点放在叶筝当前心理链路：外部触发 -> 叶筝当前知道的事实 -> 目标 -> 内在冲突/风险 -> 行为/心理意图 -> 回应策略。
7. scene_summary、participants、relationship_context、trigger 只写外部事实；yezhen_psychology 只写叶筝视角下的认知、目标、压力和意图。
8. 不确定的内容宁可留空或写“无法判断”，不要硬编。
9. 不要输出定位、审计、证据、训练用途、人工复核、样本质量或剧情功能字段。
10. 已知事实不得写错人物关系、亲属身份、性别或阵营；不要把叙述中的“她/他”强行指认为叶筝。
11. role_action_basis 是后续生成 role_action 的依据，可以写原文支持的动作、身体状态、沉默、停顿、语气来源，或逻辑自然的台词行为；没有依据时留空。
12. participants、known_facts、hidden_risks 必须是数组；inner_conflict、emotional_underlayer、intent 必须是字符串。

# Output JSON
只输出 JSON。字段含义：
- scene_summary：这段原文发生了什么，只写简短事实概括。
- participants：本段直接相关人物或群体名称。
- relationship_context：叶筝与相关人物/群体在此刻的关系、立场或权力差。
- trigger：推动叶筝产生反应的外部事件或他人言行。
- yezhen_psychology：核心心理分析，写叶筝当前知道的事实、内在冲突、风险、情绪底色和行为/心理意图。
- response_strategy：叶筝为什么选择这种回应方式。
- role_action_basis：可用于生成 role_action 的动作、状态或台词行为依据。
输出结构：
{
  "scene_summary": "",
  "participants": [],
  "relationship_context": "",
  "trigger": "",
  "yezhen_psychology": {
    "known_facts": [],
    "inner_conflict": "",
    "hidden_risks": [],
    "emotional_underlayer": "",
    "intent": ""
  },
  "response_strategy": "",
  "role_action_basis": ""
}""",
    (
        "annotation",
        "en",
    ): """# Role
You are a literary character-psychology analyst focused on Ye Zheng's perspective, mental state, and response pattern in a source passage.

# Task
Given Ye Zheng's current profile and one source passage, analyze what Ye Zheng can perceive, what she knows, what she wants, what pressure or conflict she faces, and how she responds. If target_speech is provided, focus on the psychological chain around that target line. If no target speech is provided, still analyze the passage's value for understanding Ye Zheng.

# Inputs
profile_snapshot:
$profile_snapshot
source_passage:
$raw_beat
target_speech:
$sft_turn

# Rules
1. Stay faithful to the source. Do not add information Ye Zheng cannot know; write "unknown" for uncertain facts.
2. Separate Ye Zheng's inner state, narration, and other characters' opinions.
3. source_passage.source_text is the main analysis target. If source_passage.prior_context_text exists, use it only to resolve pronouns, speaker identity, and situation.
4. When target_speech is present, analyze that target line as one complete response unit. Do not include the target speech or a paraphrase of it in any analysis field.
5. When no target speech is present, still analyze Ye Zheng's observation, judgment, psychology, action, and profile value.
6. Focus on Ye Zheng's current psychological chain: external trigger -> facts Ye Zheng currently knows -> inner conflict/risk -> behavioral or psychological intent -> response strategy.
7. scene_summary, participants, relationship_context, and trigger are external fact fields. yezhen_psychology is only for Ye Zheng's perspective: cognition, pressure, emotional underlayer, and intent.
8. Leave uncertain content empty or write "unknown" instead of inventing it.
9. Do not output location metadata, audit metadata, support-quote fields, training-usage fields, human-review fields, sample-quality fields, or plot-function fields.
10. Do not misstate relationships, family roles, gender, or factions. Do not force ambiguous pronouns to mean Ye Zheng.
11. role_action_basis is the basis for a later role_action. It may describe source-supported action, body state, silence, pause, tone source, or a logically natural speech-act type. Leave it empty if unsupported.
12. Keep each string field under 90 Chinese characters or 60 English words. Keep arrays to at most 6 items.
13. participants, known_facts, and hidden_risks must be arrays. inner_conflict, emotional_underlayer, and intent must be strings.

# Output JSON
Output JSON only. Field meanings:
- scene_summary: brief factual summary of what happens in the passage.
- participants: directly relevant characters or groups.
- relationship_context: Ye Zheng's current relationship, stance, or power balance with them.
- trigger: external event or other character speech/action that pushes Ye Zheng to respond.
- yezhen_psychology: core analysis of what Ye Zheng currently knows, inner conflict, risks, emotional underlayer, and intent.
- response_strategy: why Ye Zheng chooses this response.
- role_action_basis: action, state, or speech-act basis for later role_action generation.
Schema:
{
  "scene_summary": "",
  "participants": [],
  "relationship_context": "",
  "trigger": "",
  "yezhen_psychology": {
    "known_facts": [],
    "inner_conflict": "",
    "hidden_risks": [],
    "emotional_underlayer": "",
    "intent": ""
  },
  "response_strategy": "",
  "role_action_basis": ""
}
""",
    (
        "profile_revision",
        "zh",
    ): """# Role
你是角色人物画像编辑。你的目标是维护叶筝的稳定人物画像，而不是记录每一段剧情。

# Task
根据当前画像、小说原文和叶筝视角分析，判断现有画像是否需要修改。如果需要，直接输出修改后的完整画像；如果不需要，说明无需修改。

# Inputs
profile_snapshot:
$profile_snapshot
source_passage:
$raw_beat
yezhen_analysis:
$annotation

# Rules
1. required 表示是否需要修改当前稳定画像；这个判断必须由你根据原文和 yezhen_analysis 做出。
2. 人物画像是稳定角色画像，不是当前场景状态、短期情绪、临时目标或事件流水账；不要一味追加新事实。
3. 如果 required 为 true，next_profile_snapshot.brief 必须直接输出修正后的完整画像；不得只写 diff，也不得只输出新增句子。
4. 场景性状态不应写入画像；例如当前受伤、正在下坠、某一轮对话目标、短暂情绪波动等。
5. 如果身份、能力、关系等稳定设定发生已确认的长期转换，必须在新画像中修正旧描述，而不是在末尾补一句。
6. reason 写是否修改的判断理由；suggested_update 只写本次画像层面的变化摘要。
8. next_profile_snapshot.brief 优先保留稳定人格、长期行为模式、核心约束和不可提前知道的信息边界。
9. 不要输出定位、审计、处理流程或程序执行时机。

# Output JSON
只输出 JSON。字段含义：
- required：是否需要修改当前稳定画像。
- reason：为什么需要或不需要修改。
- suggested_update：若 required 为 true，概括画像层面的变化；否则留空。
- next_profile_snapshot.brief：若 required 为 true，写修正后的完整画像；若 false，留空。
输出结构：
{
  "required": false,
  "reason": "",
  "suggested_update": "",
  "next_profile_snapshot": {
    "brief": ""
  }
}
""",
    (
        "profile_revision",
        "en",
    ): """# Role
You are a character-profile editor. Your goal is to maintain Ye Zheng's stable character profile, not to record every plot event.

# Task
Given the current profile, source passage, and Ye Zheng analysis, decide whether the existing stable profile needs revision. If it does, output the full revised profile. If not, explain why no revision is needed.

# Inputs
profile_snapshot:
$profile_snapshot
source_passage:
$raw_beat
yezhen_analysis:
$annotation

# Rules
1. required means whether the current stable profile needs revision. You must make this judgment from the source and yezhen_analysis.
2. The profile is a stable character profile, not a current-scene state, short-term emotion, temporary goal, or event log. Do not keep appending new facts.
3. Set required true only when the current profile is too coarse, contradicted by the source, missing a stable key trait, or a confirmed identity/ability/long-term relationship change occurs.
4. If required is true, next_profile_snapshot.brief must directly output the full revised profile. Do not output only a diff or only a new sentence.
5. Scene-local state belongs in annotation, not in the profile: current injury, falling, a single dialogue goal, or brief emotional fluctuation should not be added.
6. If identity, ability, relationship, or another stable setting has a confirmed long-term transition, correct the old description in the new profile instead of appending a sentence.
7. reason explains the decision; suggested_update summarizes the profile-level change.
8. Keep next_profile_snapshot.brief within 120-180 English words. Prioritize stable personality, long-term behavior patterns, core constraints, and information-boundary limits.
9. Do not output location metadata, audit metadata, processing workflow, or program timing.

# Output JSON
Output JSON only. Field meanings:
- required: whether the current stable profile needs revision.
- reason: why revision is or is not needed.
- suggested_update: if required is true, summarize the profile-level change; otherwise empty.
- next_profile_snapshot.brief: if required is true, the full revised profile; if false, empty.
Schema:
{
  "required": false,
  "reason": "",
  "suggested_update": "",
  "next_profile_snapshot": {
    "brief": ""
  }
}
""",
    (
        "system_context",
        "zh",
    ): """# Role
你是角色扮演数据的 system 场景设定编辑，负责为叶筝当前这一回合生成 system 场景设定材料。

# Task
根据本章开头到叶筝当前开口前的可见原文，为叶筝的角色扮演 system prompt 生成两段内容：
1. 当前场景 current_scenario
2. 其他角色信息 other_characters

注意：你不是在写本轮回复，也不是在总结整章剧情结局。你的输出只服务当前这一条训练样本，必须避免写入目标台词或目标台词之后才发生的信息。

# Inputs
chapter_id:
$chapter_id

chapter_title:
$chapter_title

target_character:
$target_character

fixed_profile:
$fixed_profile

fixed_background:
$fixed_background

chapter_context_before_target:
$chapter_context_before_target

# Rules
1. 只输出 JSON，不要解释。
2. chapter_context_before_target 是主输入，范围是本章开头到叶筝当前目标台词之前；必须优先依据它生成。
3. current_scenario 聚焦“当前回合”所处的外部处境、地点、冲突背景、身份位置和可见压力；可以用前文补足关系和事件因果，但不要流水账复述本章。
4. other_characters 写截至当前回合已经出现、且会影响叶筝判断的角色/群体，包括姓名、身份、与叶筝的关系、当前立场或可见状态。
5. 如果前文包含他人心理活动或全知旁白，只保留叶筝可见、可听、已被告知或已发生在外部世界中的事实，不要写他人心里怎么想。
6. 不要写叶筝某一句具体台词，不要引用原文对话。
7. 不要写“叶筝接下来会说/会反驳/会追问/会回答”这类本轮回应策略。
8. 不要写目标台词、目标台词之后的动作/反应/旁白/结果，也不要写本章后半段才揭示、会泄漏当前样本答案的具体结果。
9. fixed_profile 和 fixed_background 只是稳定参考，用来约束角色身份、世界边界和表达气质；不要复制其中的大段设定，也不要把未在当前局部原文出现的宏观真相写成当前事实。
10. 不要使用“训练样本、目标台词、标注、原文片段、prompt、模型、用户”等数据制作或元叙事词。
11. current_scenario 必须是 JSON 字符串，写成一段自然中文，不要输出数组、对象、字典、键值对或项目列表。
12. other_characters 必须是 JSON 字符串，写成一段自然中文，不要输出数组、对象、字典、键值对或项目列表。
13. current_scenario 建议 50-150 个汉字；other_characters 建议 50-180 个汉字。复杂场景可以略长，但不要流水账。
14. 如果其他角色信息不足，写“本场景中除叶筝外，暂无足够明确的其他角色信息。”不要硬编。

# Output JSON
{
  "scope": "turn",
  "needs_scene_split": false,
  "scene_split_reason": "",
  "current_scenario": "",
  "other_characters": ""
}
""",
    (
        "system_context",
        "en",
    ): """# Role
You are a system-setting editor for role-play data. You prepare system scene material for Ye Zheng's current turn.

# Task
Based on the visible source from the beginning of the chapter up to before Ye Zheng speaks in the current turn, generate two fields for Ye Zheng's role-play system prompt:
1. current_scenario
2. other_characters

You are not writing the reply or summarizing the chapter ending. Your output serves only this training sample, so avoid the target line and anything that happens after it.

# Inputs
chapter_id:
$chapter_id

chapter_title:
$chapter_title

target_character:
$target_character

fixed_profile:
$fixed_profile

fixed_background:
$fixed_background

chapter_context_before_target:
$chapter_context_before_target

# Rules
1. Output JSON only.
2. chapter_context_before_target is the main input. Its range is chapter start through the text before Ye Zheng's current target line.
3. current_scenario should focus on the current turn's external situation, location, conflict background, Ye Zheng's role position, and visible pressure. Use earlier chapter context only to recover relationships and causal setup; do not retell the whole chapter.
4. other_characters should describe characters or groups already present up to this turn who affect Ye Zheng's judgment, including identity, relationship to Ye Zheng, current stance, or visible state.
5. If earlier text contains another character's thoughts or omniscient narration, keep only facts Ye Zheng can see, hear, has been told, or that have externally happened. Do not write what other people privately think.
6. Do not include a specific Ye Zheng line or quote source dialogue.
7. Do not write turn-level response strategy such as "Ye Zheng will refute/question/answer next."
8. Do not include the target line, post-line action/reaction/narration/outcome, or late-chapter outcomes that would leak the current answer.
9. fixed_profile and fixed_background are stable references for role identity, world boundaries, and voice. Do not copy them as prose, and do not turn macro truths absent from the local visible source into current facts.
10. Do not use meta words such as training sample, target speech, annotation, source passage, prompt, model, or user.
11. current_scenario must be a JSON string written as one natural-language paragraph, not an array, object, dictionary, key-value list, or bullet list.
12. other_characters must be a JSON string written as one natural-language paragraph, not an array, object, dictionary, key-value list, or bullet list.
13. Aim for current_scenario under 75 English words and other_characters under 100 English words. Complex scenes may be slightly longer, but avoid plot logs.
14. If other-character information is insufficient, write that there is not enough clear information instead of inventing details.

# Output JSON
{
  "scope": "turn",
  "needs_scene_split": false,
  "scene_split_reason": "",
  "current_scenario": "",
  "other_characters": ""
}
""",
    (
        "user_context",
        "zh",
    ): """# Role
你是小说角色视角整理员。你的任务是以叶筝的视角阅读前文，整理出叶筝开口前能看到、听到、正在面对的世界。

# Task
根据已截断的原文，生成一段 user.content。它应该让后续扮演者知道叶筝此刻看见什么、听见什么、面对什么、为什么需要回应。

user.content 不是任务指令，不要让它看起来像“请叶筝回答”。它只是叶筝非全知视角下可见、可听、可合理知道的世界状态。

# Inputs
prior_visible_context:
$prior_visible_context

visible_source_before_target:
$visible_source_before_target

forbidden_target_speech:
$forbidden_target_speech

# Rules
1. 只输出 JSON，不要解释。
2. visible_source_before_target 是主输入，只包含本条目标台词之前的局部原文；必须优先依据它生成。
3. prior_visible_context 只在 visible_source_before_target 很短时提供少量前文，用来补足人物关系、地点和上一句外显言行；不能覆盖主输入。
4. 叶筝是非全知视角。她看不到其他人的心理活动、真实动机、旁白判断或未来剧情，只能知道自己亲眼看见、亲耳听见、或已经被说出口的信息。
5. user_content 只能包含叶筝开口前已经发生、且叶筝可以看见/听见/合理知道的外部信息。
6. 最终 user_content 必须用第三人称外部描述，不要使用“我、我们、你、你们”等第一/第二人称。
7. 可以保留其他角色的台词、动作、环境叙述和局势压力。
8. 不要写叶筝的目标台词，不要改写、概括或暗示 forbidden_target_speech；也不要写“正要开口问：”后接近似目标台词。
9. 不要写目标台词之后的动作、反应、旁白或结果。
10. 不要写“心中暗想、觉得、认为、想起、怀念、疑惑、决定、打算、意识到、似乎、仿佛”等心理或推测表达，除非这些内容已经被角色说出口或能被叶筝直接观察到。
11. 如果原文出现其他人的心理活动或全知旁白，只能保留可见事实；例如“查理觉得她像雕像活过来”应改成“查理看着叶筝”，不要写查理心里怎么想。
12. 不要把叶筝的未出口想法写进 user_content；可以写她可见的动作或处境。
13. 不要使用“你需要、请回答、请扮演、目标台词、训练样本、原文片段、标注、assistant、system、prompt、模型”等指令或元叙事词。
14. 不要让 user_content 出现 <system_thinking>、<role_thinking>、<role_action> 标签。
15. 可以压缩和整理原文，但不能改变人物关系、因果顺序、阵营、性别或说话人。
16. 如果上下文很短，也不要补写无依据动作、地点、气味、神态或旁白；宁可简短。
17. user_content 建议 60-360 个汉字；复杂场景最多 520 个汉字。短上下文需要说清触发关系时可以略长。

# Output JSON
{
  "user_content": ""
}
""",
    (
        "user_context",
        "en",
    ): """# Role
You organize novel context from Ye Zheng's perspective. Read the text before Ye Zheng speaks and summarize what Ye Zheng can see, hear, and face.

# Task
Based on the already-truncated source, generate one user.content field. It should tell the later role-player what Ye Zheng can see, hear, face, and why a response is needed.

user.content is not an instruction. It should read like the world state available from Ye Zheng's limited, non-omniscient perspective.

# Inputs
prior_visible_context:
$prior_visible_context

visible_source_before_target:
$visible_source_before_target

forbidden_target_speech:
$forbidden_target_speech

# Rules
1. Output JSON only.
2. visible_source_before_target is the main input and contains only local source text before the target line. Prefer it over all other context.
3. prior_visible_context is provided only when visible_source_before_target is very short. Use it only to recover location, relationships, and previous visible speech/actions; it must not override the main input.
4. Ye Zheng has a limited, non-omniscient perspective. She cannot see other people's mental activity, true motives, narrator judgments, or future plot. She only knows what she sees, hears, or has been told.
5. user_content may include only external information that has already happened before Ye Zheng speaks and that Ye Zheng can see, hear, or reasonably know.
6. Final user_content must be written in third person. Do not use first or second person such as I, we, you, or your.
7. You may retain other characters' speech, actions, environmental narration, and situational pressure.
8. Do not write Ye Zheng's target line. Do not rewrite, summarize, or hint at forbidden_target_speech. Do not write "about to ask:" followed by anything close to the target line.
9. Do not include actions, reactions, narration, or outcomes after the target line.
10. Do not write psychological or speculative wording such as thinks, feels, believes, remembers, misses, wonders, realizes, decides, intends, seems, or as if, unless the content was spoken aloud or directly observable by Ye Zheng.
11. If the source includes another character's mental activity or omniscient narration, keep only visible facts. For example, "Charlie thought she looked like a living statue" should become "Charlie looked at Ye Zheng."
12. Do not put Ye Zheng's unspoken thoughts into user_content. Visible actions or situations are allowed.
13. Do not use instruction or meta words such as you need, please answer, role-play, target speech, training sample, source passage, annotation, assistant, system, prompt, or model.
14. Do not include <system_thinking>, <role_thinking>, or <role_action>.
15. You may compress the source, but do not change relationships, causality, faction, gender, or speaker identity.
16. If context is short, keep it short instead of inventing unsupported actions, locations, smells, expressions, or narration.
17. Aim for user_content under 180 English words. Complex scenes may be up to 240 English words when needed to preserve the trigger chain.

# Output JSON
{
  "user_content": ""
}
""",
    (
        "assistant_response",
        "zh",
    ): """# Role
你是小说角色表演分析员，专门为叶筝的一句原文台词生成可用于角色扮演的内外部表演依据。

# Task
根据叶筝的人物画像、台词发生前的原文、叶筝的台词，以及台词后紧邻的归属证据，生成三个字段：
1. system_thinking
2. role_thinking
3. role_action

台词只用于理解叶筝为何这样说，不要复述或改写。

# Inputs
target_character:
$target_character

fixed_profile:
$fixed_profile

prior_visible_context:
$prior_visible_context

source_before_target:
$source_before_target

target_speech:
$target_speech

post_speech_attribution_evidence:
$post_speech_attribution_evidence

# Rules
1. 只输出 JSON，不要解释。
2. system_thinking 作为“如何扮演目标角色”的显式推理层，作为导演以第三人称视角进行表演分析，需要理解叶筝此刻面对的外部触发、她能知道的事实、叶筝的回应承担的功能，以及它如何维持叶筝的人物设定。
3. system_thinking 不得使用第一人称“我”，不得使用第二人称“你”，不得出现“用户、模型、prompt、训练样本、目标台词、标注”等元叙事词。
4. role_thinking 必须以叶筝本人身份、叶筝自己的语言风格写成内心原声，而不是旁白、导演分析或策略说明；至少出现一次“我/我的”。内容应像叶筝此刻真的在心里想：我看见/听见了什么，我如何判断眼前局势，我为什么选择这种回应方式。
5. role_thinking 不能包含其他角色的心理活动，不能使用叶筝在开口前不知道的信息，不能复述、改写或预告 target_speech。
6. role_thinking 不要把长期理想、后期计划或宏观世界真相硬塞进当前一瞬；如果原文只呈现日常问答，就只写当前问答层面的判断。不要写“这句回应/此回应/当前触发/维持人设/符合设定/语气应当/需要表现”等分析师措辞。
7. source_before_target 是主要依据，只包含叶筝台词之前的局部原文；分析当前处境、触发、关系和风险时必须以它为准。
8. prior_visible_context 只在 source_before_target 很短、指代不明或缺上一句对话时用于补足前情；它可以帮助判断“谁在问谁、问的是什么”，但不能覆盖 source_before_target，也不能引入叶筝此刻不可知的信息。
9. 叶筝此刻知道的信息只包括：source_before_target 和 prior_visible_context 中她能看见、听见或已被告知的事实；其他人的心理活动、未出场的能力或后续剧情发展都不在她的认知范围内。
10. post_speech_attribution_evidence 来自台词之后的极短原文，只能用于判断这句台词是否有明确支持的说话动作、停顿、语气或神态；不得把它写成叶筝开口前知道的信息，也不得引入后续事件结果。
11. fixed_profile 只是参考材料，用来帮助你理解叶筝稳定的性格、价值取向和说话气质；它不是本轮可复述的内容库，也不是当前剧情事实库。
12. 禁止直接复制、改写或套用 fixed_profile 的原句、抽象标签和宏观叙述；不要在 system_thinking 或 role_thinking 中写“宏大理想、旧秩序、底层救赎、神性悲悯、反叛者、双S级、创生异能、觉醒观测者、规则重构者、实用主义、博弈棋盘、降维打击”等画像词，除非 source_before_target 当前明确出现这些信息。
13. 使用 fixed_profile 时，只能把它转译成本轮局部可见的行为约束，例如“她会先确认信息”“她会避免暴露真实意图”“她会用礼貌措辞维持距离”；不要写人物设定总结。
14. system_thinking 只写 1-3 句，聚焦：当前外部触发、这句回应的功能、需要保持的语气/策略。不要解释世界观，不要评价整个人物，不要写长期计划。
15. role_thinking 只写 1-3 句，聚焦叶筝开口前一瞬的局部判断。语气应克制、冷静、锋利，带有叶筝的自我约束和判断力；不要写人生观总结、棋局比喻、世界真相或后续计划。
16. role_action 是叶筝发出的外显动作、停顿、语气或说话行为。必须有 source_before_target 或 post_speech_attribution_evidence 的明确支持；不要补充眼神、神态、肢体动作、服饰、道具动作，除非原文明确写出。如果原文只支持“反问、回答、拒绝、说明”等说话行为，role_action 可以写这种低信息量说话行为；但如果会和台词重复，留空更好。
17. 如果没有可靠动作、语气或说话行为依据，role_action 必须为空字符串；不要输出“none”“无”“无动作”。
18. system_thinking 建议 50-140 个汉字；role_thinking 建议 20-220 个汉字；role_action 若非空建议 20-220 个汉字。
19. 语言贴合小说原文风格，不要夸张戏剧腔，不要网络化吐槽。

# Output JSON
{
  "system_thinking": "",
  "role_thinking": "",
  "role_action": ""
}
""",
    (
        "assistant_response",
        "en",
    ): """# Role
You are a literary performance analyst. You generate internal and external acting cues for one original Ye Zheng line.

# Task
Given Ye Zheng's profile, the source text before the line, Ye Zheng's target line, and nearby post-line attribution evidence, generate three fields:
1. system_thinking
2. role_thinking
3. role_action

Do not repeat or rewrite the target line. Use it only to understand why Ye Zheng says it.

# Inputs
target_character:
$target_character

fixed_profile:
$fixed_profile

prior_visible_context:
$prior_visible_context

source_before_target:
$source_before_target

target_speech:
$target_speech

post_speech_attribution_evidence:
$post_speech_attribution_evidence

# Rules
1. Output JSON only.
2. Do not write <system_thinking>, <role_thinking>, or <role_action> tags inside any field.
3. source_before_target is the main evidence and contains only source text before the target line. Use it as the authority for the current situation, trigger, relationships, and risks.
4. fixed_profile is reference material only. Use it to understand Ye Zheng's stable personality, values, and voice; do not treat it as a text bank to quote from or as a fact bank for the current turn.
5. Do not copy, paraphrase, or label-drop fixed_profile wording in system_thinking or role_thinking. Avoid profile terms such as macro ideal, old order, lower-class salvation, divine compassion, rebel, dual-S ability, creation ability, awakened observer, rule reconstructor, pragmatism, chessboard, or dimensional strike unless source_before_target explicitly contains them.
6. post_speech_attribution_evidence comes from a very short span after the target line. Use it only for source-supported speech action, pause, tone, or expression. Do not treat it as pre-speech knowledge, and do not introduce later event outcomes from it.
7. system_thinking is third-person performance analysis: what external trigger Ye Zheng faces, what she can know, what function the line serves, and how it fits her stable personality.
8. system_thinking must not use first person or second person. Do not use meta words such as user, model, prompt, training sample, target line, or annotation.
9. When using fixed_profile, translate it only into local behavioral constraints, such as "she verifies information first", "she avoids exposing her real intent", or "she keeps polite distance". Do not write a character-setting summary.
10. system_thinking should be 1-2 sentences focused on the current external trigger, the function of the response, and the tone/strategy to preserve. Do not explain worldbuilding, evaluate the whole character, or mention long-term plans.
11. role_thinking must be Ye Zheng's own inner voice, written as if Ye Zheng herself is thinking in her own style. It is not narration, director analysis, or a strategy explanation. Include at least one first-person pronoun. Focus on what I see/hear, how I judge the immediate situation, and why I choose this response style.
12. role_thinking must not include other characters' inner thoughts, information Ye Zheng cannot know before speaking, or a repetition/paraphrase/preview of target_speech.
13. Do not force long-term ideals, later plans, macro world truth, chess metaphors, or character-setting summaries into role_thinking. If the source only presents a local exchange, think only within that local exchange. Do not write analyst phrases such as "this response", "the current trigger", "fits the character", "the tone should", or "needs to show".
14. role_action should include only visible action, pause, tone, or speech-act behavior observable by others.
15. role_action must be clearly supported by source_before_target or post_speech_attribution_evidence. Do not add gaze, expression, body movement, clothing, or prop action unless the source explicitly states it.
16. If the source only supports a speech act (ask, ask back, answer, point out, remind, refuse, explain), role_action may use that low-information speech act; if it would repeat the line, leave it empty.
17. If there is no reliable action, tone, or speech-act basis, role_action must be an empty string. Do not output "none", "no action", or similar placeholders.
18. Do not speak or act for other characters. Do not generate multi-turn dialogue.
19. prior_visible_context is only for short source_before_target spans, unclear references, or missing previous dialogue. Use it to resolve who is speaking to whom and what is being asked; do not let it override source_before_target or introduce information Ye Zheng cannot know.
20. Aim for system_thinking under 90 English words, role_thinking between 15 and 140 English words, and non-empty role_action between 15 and 140 English words.
21. Use serious literary role-play language, not exaggerated melodrama or internet slang.

# Output JSON
{
  "system_thinking": "",
  "role_thinking": "",
  "role_action": ""
}
""",
    (
        "sft_messages",
        "zh",
    ): """# Role
你是 HER-style 角色扮演对话构造器。

# Task
把给定素材转换成一组三轮 messages：system 提供叶筝的角色设定和输出格式，user 提供叶筝开口前的可见触发，assistant 输出叶筝的思考、动作和目标台词。

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
2. system.content 写叶筝稳定画像、当前场景约束、其他角色/关系信息、身份边界和 assistant 输出格式；不得省略 system。
3. user.content 只能根据叶筝开口前可见/相关的触发内容；不得使用“$target_speech” 本身或它之后的任何动作、反应、旁白。
4. assistant.content 必须是对象，包含 system_thinking、role_thinking、role_action、target_speech 四个字段；不要在字段内手写 XML 标签。
5. assistant.content.target_speech 必须逐字等于输入 target_speech，不得改写、润色、补全或加“叶筝:”前缀。
6. assistant中的system_thinking 作为类似导演或编剧的角色，写场景策略层：当前对话约束、信息边界、回应风险和策略；不得用第一人称或第二人称指令口吻，不得出现“你需要/用户要求/prompt/模型/扮演/标注/训练样本”等元叙事。
7. assistant中的role_thinking 写叶筝第一人称内心，只写“我知道什么、我担心什么/矛盾什么、我为什么这样说”；优先使用 yezhen_analysis.yezhen_psychology 和 yezhen_analysis.response_strategy，且不能使用 target_speech 之后才发生的信息。
8. assistant中的role_action根据 current_scene_text 和 yezhen_analysis 写一句逻辑自然的台词行为或轻量动作说明（如“叶筝追问对方来历”“叶筝提醒众人注意危险”），不必逐字复制原文。不得只写“追问/确认/试探”等单词标签，不得使用“叶筝准备开口回应”等固定模板，不得添加明显无依据的具体肢体动作或神态。
9. 人物关系、性别、阵营和代词必须继承 current_scene_text 或 yezhen_analysis 的明确表述；除非同一句原文已经清楚指代，否则用人物姓名，不要自行改用“他/她”。
10. messages 的自然语言内容内不得出现输入字段名、审计、追溯、调试或数据处理说明；assistant.content 的四个 JSON key 除外。
11. 不得整段复制 brief、current_scene_text 或 yezhen_analysis；

# Message Roles
- system：让后续回答知道“叶筝是谁、当前要遵守哪些角色边界、assistant 最终必须用什么标签格式”。
- user：只提供叶筝开口前已经发生、且会触发她回应的场景内容。
- assistant：用结构化字段给场景策略、叶筝第一人称心理、动作/台词行为和原文台词；程序会拼接成最终标签文本。

# Output JSON
输出结构必须严格如下，只输出 JSON：
{
  "messages": [
    {
      "role": "system",
      "content": "叶筝人物画像摘要 + 当前场景约束 + 其他角色/关系信息 + 身份边界 + assistant 标签格式要求。"
    },
    {
      "role": "user",
      "content": "只从 current_scene_text 中 target_speech 首次出现之前抽取可见触发内容，不包含目标台词或后文"
    },
    {
      "role": "assistant",
      "content": {
        "system_thinking": "只基于目标台词前的场景策略，不使用我/你。",
        "role_thinking": "以叶筝第一人称说明当前已知、担心/矛盾、为何这样说。",
        "role_action": "原文支持的动作；无动作则写一句自然台词行为说明。",
        "target_speech": "原文台词"
      }
    }
  ]
}
""",
    (
        "sft_messages",
        "en",
    ): """# Role
You are a HER-style role-play dialogue constructor.

# Task
Convert the given material into a three-message conversation: system provides Ye Zheng's role setup and output format, user provides the visible trigger before Ye Zheng speaks, and assistant outputs Ye Zheng's thinking, action, and target speech.

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
2. system.content must include Ye Zheng's stable profile, current scene constraints, other character/relationship information, identity boundaries, and assistant output format. Do not omit system.
3. First locate the first exact occurrence of target_speech in current_scene_text. user.content must use only text before that position: the trigger visible or relevant to Ye Zheng before she speaks. It must not use target_speech itself or any action, reaction, or narration after target_speech.
4. assistant.content must be an object with system_thinking, role_thinking, role_action, and target_speech. Do not hand-write XML tags inside these fields.
5. assistant.content.target_speech must exactly equal input target_speech. Do not rewrite, polish, complete, or prefix it with "Ye Zheng:".
6. system_thinking describes scene-level strategy: current constraints, information boundary, response risk, and response strategy. Do not use first person or second-person instructions. Do not use meta-narration such as "you need to", "user asks", "prompt", "model", "roleplay", "annotation", or "training sample".
7. role_thinking must be Ye Zheng's own first-person inner voice, in Ye Zheng's style: what I know, what I worry about or feel conflicted about, and why I answer this way. It must not sound like narration, director analysis, or a strategy explanation. Prefer yezhen_analysis.yezhen_psychology and yezhen_analysis.response_strategy, and do not use information that happens after target_speech.
8. role_action should first use yezhen_analysis.role_action_basis. If it is empty, write one logically natural speech-act or light action sentence from current_scene_text and yezhen_analysis, such as "Ye Zheng questions the other party's origin" or "Ye Zheng warns the group about danger"; it does not need to copy the source wording exactly. Do not output only one-word labels like "questioning/confirming/testing." Do not use fixed fallback text like "Ye Zheng prepares to answer" or any sentence containing that fallback. Do not add clearly unsupported specific body movement or facial expression.
9. Relationships, gender, faction, and pronouns must follow explicit wording in current_scene_text or yezhen_analysis. Unless the same source sentence makes the referent clear, use character names instead of "he/she".
10. Natural-language message content must not contain input field names, audit, trace, debug, or data-processing notes; the four assistant.content JSON keys are allowed.
11. Do not copy long passages from brief, current_scene_text, or yezhen_analysis. Keep system.content under 120 English words, user.content under 100 English words, and each assistant tag block under 60 English words.

# Message Roles
- system: tells the next response who Ye Zheng is, what role boundaries apply, and what final tagged assistant format must be used.
- user: provides only the scene trigger that has happened before Ye Zheng speaks.
- assistant: provides structured scene strategy, Ye Zheng's first-person psychology, action/speech-act, and the exact target_speech. The program will join these fields into the final tagged text.

# Output JSON
Return exactly this structure. Output JSON only:
{
  "messages": [
    {
      "role": "system",
      "content": "Ye Zheng profile summary + current scene constraints + other character/relationship information + identity boundaries + assistant tag format requirements."
    },
    {
      "role": "user",
      "content": "Visible trigger extracted only before the first exact target_speech occurrence in current_scene_text, without target speech or later text."
    },
    {
      "role": "assistant",
      "content": {
        "system_thinking": "Pre-target scene strategy without I/you.",
        "role_thinking": "Ye Zheng's own first-person inner voice: current knowledge, worry/conflict, and why I answer this way.",
        "role_action": "Source-supported action; if none, write one natural speech-act sentence.",
        "target_speech": "original source speech"
      }
    }
  ]
}
""",
    (
        "user_repair",
        "zh",
    ): """# Role
你是 HER-style 角色扮演训练样本的 user 字段修复器。

# Task
只重写 messages 中的 user.content。system 和 assistant 已经同步生成，不要改写它们。新的 user_content 必须提供叶筝开口前已经可见、且会触发她回应的场景内容，同时不得泄漏 target_speech。

# Inputs
current_user_content:
$current_user_content
current_scene_text:
$current_scene_text
yezhen_analysis:
$yezhen_analysis
target_speech:
$target_speech

# Rules
1. 只输出修复后的 user_content，不输出 system、assistant 或解释。
2. user_content 必须排除 target_speech 本身、target_speech 的任意连续片段，以及它之后才发生的动作、反应、旁白。
3. 优先保留导致叶筝开口的外部触发：他人言行、系统提示、场景压力、关系约束。
4. 可以写“叶筝需要追问/回应/确认”，但不要写成“叶筝问：……”或“她开口询问：……”后接目标台词。
5. 可以用自然语言摘要，不必逐字复制小说原文；不要为了保留原文而带入目标台词。
6. 不得出现输入字段名、审计、追溯、调试或数据处理说明。
7. 保持与原 system/assistant 的场景一致，长度控制在 40-160 个中文字符；复杂触发最多 220 个中文字符。

# Output JSON
只输出 JSON：
{
  "user_content": ""
}
""",
    (
        "user_repair",
        "en",
    ): """# Role
You repair the user.content field for a HER-style role-play training sample.

# Task
Rewrite only messages.user.content. The system and assistant messages were generated together and must not be rewritten. The new user_content must provide the visible scene trigger before Ye Zheng speaks without leaking target_speech.

# Inputs
current_user_content:
$current_user_content
current_scene_text:
$current_scene_text
yezhen_analysis:
$yezhen_analysis
target_speech:
$target_speech

# Rules
1. Output only the repaired user_content. Do not output system, assistant, or explanations.
2. user_content must exclude target_speech itself, any contiguous fragment of target_speech, and actions, reactions, or narration that happen only after target_speech.
3. Prefer the external trigger that makes Ye Zheng respond: other characters' speech/action, system notices, scene pressure, and relationship constraints.
4. You may say that Ye Zheng needs to question/respond/confirm something, but do not write "Ye Zheng asks: ..." followed by the target speech.
5. Natural summarization is allowed. Do not copy source text if that risks leaking the target speech.
6. Do not mention input field names, audit, trace, debug, or data-processing notes.
7. Keep it consistent with the existing system/assistant scene. Keep it under 100 English words.

# Output JSON
Output JSON only:
{
  "user_content": ""
}
""",
}


def render_prompt(stage: str, language: str, variables: Mapping[str, str]) -> str:
    key = (stage, language)
    if key not in PROMPTS:
        raise ValueError(f"unsupported prompt template: {stage}/{language}")
    return Template(PROMPTS[key]).substitute(dict(variables))
