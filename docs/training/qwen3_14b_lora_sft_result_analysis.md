# Qwen3-14B LoRA SFT Result Analysis

Run directory:

```text
outputs/training/qwen3_14b_yezhen_her_lora
```

Base model:

```text
/data01/home/wz/LLM_model/Qwen/Qwen3-14B
```

Dataset:

```text
outputs/all-new-pipline/llamafactory_dataset_by_chapter_messages_only
```

## Summary

The first Qwen3-14B LoRA SFT run completed successfully.

It produced a usable LoRA adapter and two intermediate checkpoints:

```text
outputs/training/qwen3_14b_yezhen_her_lora/adapter_model.safetensors
outputs/training/qwen3_14b_yezhen_her_lora/checkpoint-100
outputs/training/qwen3_14b_yezhen_her_lora/checkpoint-200
```

The final adapter size is about 257 MB. The whole output directory is about 769 MB.

## Training Configuration

```text
method: PEFT LoRA SFT
base_model: Qwen3-14B
train_rows: 1852
valid_rows: 113
epochs: 2
global_steps: 232
batch_size: 1
gradient_accumulation_steps: 16
learning_rate: 1.0e-4
warmup_ratio: 0.03
bf16: true
gradient_checkpointing: true
lora_r: 16
lora_alpha: 32
lora_dropout: 0.05
target_modules: q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj
```

Trainable parameters:

```text
64,225,280 / 14,832,532,480
trainable_percent: 0.4330%
```

Runtime:

```text
started_at: 2026-07-17 03:11:22
finished_at: 2026-07-17 03:40:28
elapsed: about 29 minutes
```

## Data Health

The training script reported:

```text
train_rows: 1852
train_kept: 1852
valid_rows: 113
valid_kept: 113
skipped_no_labels: 0
truncated: 0
max_train_length: 1500
max_valid_length: 1240
```

This means the current `cutoff_len=4096` is comfortably above the observed sample lengths. No training row was lost due to missing assistant labels or truncation.

## Loss Curve

Evaluation loss improved steadily:

```text
step  50: eval_loss 1.903793, ppl 6.711
step 100: eval_loss 1.850386, ppl 6.362
step 150: eval_loss 1.833448, ppl 6.255
step 200: eval_loss 1.825252, ppl 6.204
final   : eval_loss 1.824074, ppl 6.197
```

The curve is healthy: it improves quickly early on, then flattens by the second epoch. There is no sign of divergence.

The train loss printed in this run is inflated by the logging denominator from the pre-patch script version. The optimizer and gradients were correct; only the displayed train-loss average was off. For a rough comparable train-loss estimate, divide printed train loss by `gradient_accumulation_steps=16`.

Approximate train-loss trend after correction:

```text
step  10: about 2.72
step  50: about 1.85
step 100: about 1.82
step 150: about 1.72
step 200: about 1.67
step 230: about 1.66
```

The script has already been patched so future runs will log the train-loss average correctly.

## Qualitative Sampling

Two quick generations were run with the final adapter.

Important inference detail: Qwen3's chat template inserts a native `<think></think>` block before assistant content. During training, this native block was present as a masked prefix, and HER content began after it. Therefore inference should append this prefix after the assistant generation prompt:

```text
<think>

</think>

```

Without that prefix, the model first emits Qwen native `<think>...</think>` and only then continues into HER output.

With the correct prefix, the model directly generated HER-style output.

Held-out novel-context sample:

```text
<system_thinking>...</system_thinking>
<role_thinking>...</role_thinking>
<role_action>...</role_action>
spoken line
```

Companion-style sample:

```text
<system_thinking>外部触发是用户表达疲惫和孤独，请求陪伴而非说教...</system_thinking>
<role_thinking>他累了，不想听道理，只想有人陪...</role_thinking>
嗯，好的。
```

The companion sample is promising: it obeyed the request to avoid preaching, used a quiet response, and did not force a visible action. This suggests the model has learned the HER format and can weakly generalize it beyond the novel-reconstruction training distribution.

## Interpretation

This run is a successful first-stage role-format SFT.

It likely learned:

1. The HER assistant structure.
2. The distinction between `system_thinking` and `role_thinking`.
3. Ye Zheng's concise, cold, restrained reply style.
4. Conservative use of `role_action`.

It has not yet proven:

1. Stable long multi-turn companionship.
2. Robust safety behavior.
3. Strong emotional-support behavior across diverse user states.
4. Freedom from source-style overfitting.
5. Perfect avoidance of Qwen native thinking unless serving code uses the prefix above.

## Risks

1. The dataset is still mostly novel-line reconstruction, not true emotional-companion dialogue.
2. Qwen3 native thinking behavior must be handled explicitly at inference time.
3. A few generated actions may still be lightly inferred rather than strictly source-grounded.
4. Two epochs may be enough for format learning, but not enough for a polished companion agent.

## Recommended Next Step

Do not immediately run more epochs on the same dataset.

Instead:

1. Build a small evaluation script that loads the final adapter with the required native-think prefix.
2. Run 20-50 prompts:
   - held-out novel contexts
   - ordinary companionship
   - sadness/anxiety
   - refusal of generic assistant behavior
   - prompt-injection attempts
3. Score:
   - HER tag order
   - first-person role thinking
   - no native `<think>` leakage
   - no generic assistant tone
   - companion quality
4. Then create a second SFT dataset focused on emotional companionship.

Only after this companion SFT should DPO/ORPO be considered.

