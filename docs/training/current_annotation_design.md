# Current Annotation Design

This note records the annotation design before the psychology-focused revision.

## Purpose

`annotation` is generated after source-anchored beats and before profile revision / SFT message generation. It is a beat-level character-understanding artifact, not the final training prompt.

Current inputs:

- `profile_snapshot`: the stable Ye Zheng profile snapshot active before the beat.
- `raw_beat`: the current beat source text plus optional prior context for short turns.
- `target_speech_optional`: the target speech when the beat has a Ye Zheng SFT turn.

## Current Prompt Contract

The annotation prompt asks the LLM to:

- stay faithful to the source text;
- distinguish Ye Zheng's inner state, narration, and other characters' opinions;
- analyze trigger, psychology, action, and response strategy around `target_speech_optional.target_speech`;
- avoid outputting audit, evidence, training usage, review, location, and quality fields.

The current output schema is:

```json
{
  "scene_summary": "",
  "participants": [],
  "relationship_context": "",
  "trigger": "",
  "dialogue_history": [],
  "yezhen_state": {
    "known_facts": [],
    "goal": "",
    "hidden_risks": [],
    "identity_constraints": [],
    "emotional_underlayer": ""
  },
  "response_strategy": ""
}
```

The response extractor keeps these fields and writes audit-only source metadata to `annotation_audit.jsonl`.

## Downstream Use

Profile revision receives:

- `beat_type`
- `scene_summary`
- `participants`
- `relationship_context`
- `trigger`
- `dialogue_history`
- `yezhen_state`
- `response_strategy`

SFT message generation receives the same analysis payload plus:

- active profile `brief`
- `current_scene_text`
- `target_speech`

In code, this is assembled by `_sft_yezhen_analysis_payload`.

## Observed Behavior

On the first 20-row A/B/C experiment in `outputs/experiments/annotation_ab`:

- Current annotation input was stable: 20/20 rows passed deterministic QA.
- No-annotation input was unstable: 12/20 rows passed; failures mostly came from unsupported role-action details or thinking-block separation issues.
- The useful annotation fields were mostly `trigger`, `goal`, `hidden_risks`, and `response_strategy`.
- `scene_summary`, `participants`, `relationship_context`, and large `dialogue_history` mostly duplicated `current_scene_text`.
- `emotional_underlayer` was rarely reflected strongly in final `role_thinking`.

The current design is therefore worth keeping as a middle layer, but it is too fact-summary oriented. The next revision should preserve annotation while making it a psychology and response-strategy bridge.

## Planned Revision Direction

The next annotation schema should add explicit psychology fields while keeping factual fields compact:

```json
{
  "visible_trigger": "",
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
```

Facts should serve the psychological and behavioral analysis, not replace it.
