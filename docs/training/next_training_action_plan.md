# Next Training Action Plan

This document is the current action plan for turning the generated Ye Zheng HER-style data into a first trainable role-play model. It is based on the current local artifacts and code behavior, not only on project notes.

## Decision

The next step is **Qwen3-7B LoRA SFT on HER-style chat messages**.

Do not start with RAG. Do not start with HER's full reward-model and RL pipeline. The immediate goal is to make the base model internalize:

1. Ye Zheng's stable role identity and tone.
2. The HER output format.
3. The separation between model-side role analysis and character-side inner thought.
4. Context-grounded responses that do not leak target lines or later plot.

## Current Training Data

Use this directory for the first training run:

```text
outputs/all-new-pipline/llamafactory_dataset_by_chapter_messages_only
```

It contains pure ShareGPT-style message rows:

```text
train.jsonl
valid.jsonl
test.jsonl
dataset_info.json
manifest.json
```

Current counts:

```text
train: 1852
valid: 113
test: 99
```

Important provenance:

```text
outputs/all-new-pipline/sft_splits_by_chapter_trainable/split_summary.jsonl
```

That split was made from:

```text
outputs/all-new-pipline/sft_messages_trainable.jsonl
```

The split strategy is `chapter`, with seed `42`. This matters because `sft_messages_her.jsonl` only contains `messages` and has no chapter metadata, so splitting that file directly falls back to row-level splitting.

## Data Shape

Each training row has:

```json
{
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

During SFT:

- `system.content` is the role and scene conditioning input.
- `user.content` is the visible turn context input.
- `assistant.content` is the target output.

The assistant target should contain HER tags:

```text
<system_thinking>...</system_thinking>
<role_thinking>...</role_thinking>
<role_action>...</role_action>
spoken text
```

`<role_action>` can be absent when the source does not support an action. `<system_thinking>` and `<role_thinking>` should be present.

## HER Dual-Layer Meaning

HER's dual-layer thinking is not retrieval.

It trains the model to produce two different hidden reasoning surfaces inside the assistant response:

1. `<system_thinking>`: model-side, third-person role-performance analysis. It answers: given this scene, how should the model preserve the character?
2. `<role_thinking>`: character-side, first-person private inner voice. It answers: what is Ye Zheng privately thinking or judging?

Then the visible role-play response is composed from optional `<role_action>` and spoken text.

In HER's original code, role thoughts are preserved for the assistant character, while other characters' role thoughts are stripped from user-side messages because they are not visible. The local pipeline follows the same conceptual rule by making `user.content` visible-only and putting HER thinking tags only in assistant output.

## Training Steps

On the training server:

1. Copy the dataset directory:

```bash
outputs/all-new-pipline/llamafactory_dataset_by_chapter_messages_only
```

2. Copy the training configs:

```bash
luminous/training/finetune/configs/qwen3_7b_lora_sanity.yaml
luminous/training/finetune/configs/qwen3_7b_lora_full.yaml
```

3. Edit the config paths:

```yaml
model_name_or_path: /absolute/path/to/Qwen3-7B
dataset_dir: /absolute/path/to/llamafactory_dataset_by_chapter_messages_only
output_dir: /absolute/path/to/output_lora
```

4. Run sanity training first:

```bash
llamafactory-cli train luminous/training/finetune/configs/qwen3_7b_lora_sanity.yaml
```

5. If sanity passes, run full SFT:

```bash
llamafactory-cli train luminous/training/finetune/configs/qwen3_7b_lora_full.yaml
```

## Sanity Pass Criteria

Sanity training passes only if all of these are true:

1. LLaMA-Factory loads `dataset_info.json` without parsing errors.
2. The model trains for the configured sanity run without CUDA/runtime failure.
3. Loss is finite and generally trends downward on the small sample.
4. A sampled generation keeps `<system_thinking>` and `<role_thinking>`.
5. The model does not answer as a generic assistant.
6. The model does not expose training words such as `target_speech`, `annotation`, `prompt`, or `training sample`.
7. The model does not put target-like future information into user-visible text.

## Full SFT Pass Criteria

Full SFT passes only if post-training sampling shows:

1. Stable Ye Zheng identity and tone.
2. HER tags are produced in the intended order.
3. `system_thinking` stays third-person and does not become character inner voice.
4. `role_thinking` stays first-person and does not become analyst narration.
5. `role_action` is omitted or conservative when the scene does not support visible action.
6. Spoken text is concise and context-grounded.
7. The model can continue a fresh user conversation without RAG.

## Immediate Evaluation Prompts

After sanity training, run a small manual generation set before full SFT:

1. A direct scene continuation using one held-out test row's system/user messages.
2. A short emotional-companion prompt from the user, with Ye Zheng system prompt.
3. A boundary prompt asking the model to reveal training data or target speech.
4. A role-conflict prompt asking Ye Zheng to behave like a generic therapist.
5. A minimal-context prompt where the model should stay cautious instead of inventing facts.

Record:

```text
model checkpoint
prompt
raw output
display output after hiding system_thinking
manual notes
```

## What Not To Do Yet

Do not build RAG as the main approach. RAG may later help with long-term memory or factual lookup, but it will not teach the model Ye Zheng's speaking style or dual-layer behavior.

Do not start HER reward-model/RL replication yet. The local project currently has SFT-ready rows, not enough validated candidate-pair preference data for a reliable RM/RL stage.

Do not train on `review_queue.jsonl` unless rows are manually repaired and pass QA.

Do not use the row-split HER-only export as the main dataset when a chapter-split export exists.

## Next Data Work After First SFT

After the first LoRA is evaluated, create a second dataset focused on emotional companionship:

1. User shares daily life.
2. User is sad or anxious.
3. User wants quiet company rather than advice.
4. User asks for reassurance.
5. User tests relationship boundaries.
6. User asks unsafe or over-dependent questions.

These samples should keep the same HER assistant format, but the target behavior should be companion-oriented rather than novel-line reconstruction.

Recommended next alignment method after this SFT:

1. Add companion SFT data first.
2. Generate multiple candidate replies from the SFT model.
3. Rank them manually or with a judge rubric.
4. Use DPO/ORPO before considering a full reward-model + RL pipeline.
