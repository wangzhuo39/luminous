# Qwen3-7B SFT Preparation

This repository prepares HER-style chat-message data locally. Training should run on the GPU server where Qwen3-7B is already downloaded.

## Local Data Freeze

After `outputs/all/sft_messages_her.jsonl` is ready, freeze a split:

```bash
python luminous/training/data/sft_messages.py inspect \
  --input outputs/all/sft_messages_her.jsonl \
  --out outputs/all/sft_inspect_summary.jsonl

python luminous/training/data/sft_messages.py split \
  --input outputs/all/sft_messages_her.jsonl \
  --out outputs/all/sft_splits \
  --train 0.9 \
  --valid 0.05 \
  --test 0.05

python luminous/training/data/sft_messages.py export-llamafactory \
  --input-dir outputs/all/sft_splits \
  --out outputs/all/llamafactory_dataset \
  --dataset-prefix yezhen_her \
  --base-model Qwen3-7B
```

The exported directory contains:

- `train.jsonl`, `valid.jsonl`, `test.jsonl`
- `dataset_info.json`
- `manifest.json` with row counts and SHA-256 hashes

Copy the exported directory and the YAML files in `luminous/training/finetune/configs/` to the training server.

## Server Setup

Install or activate LLaMA-Factory on the server, then copy `dataset_info.json` into the dataset directory used by LLaMA-Factory. The JSONL files use ShareGPT-style `messages` rows:

```json
{"messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}
```

In the YAML config, replace:

- `model_name_or_path`: absolute path to the downloaded Qwen3-7B model.
- `dataset_dir`: absolute path to the exported dataset directory.
- `output_dir`: server output directory for the LoRA adapter.

## Sanity Training

Run the sanity config first:

```bash
llamafactory-cli train luminous/training/finetune/configs/qwen3_7b_lora_sanity.yaml
```

Expected checks:

- Training starts without dataset parsing errors.
- Loss decreases on the small sample.
- Generated samples keep HER tags: `<system_thinking>`, `<role_thinking>`, `<role_action>`.
- The assistant does not copy the user prompt.

## Full Training

After sanity passes:

```bash
llamafactory-cli train luminous/training/finetune/configs/qwen3_7b_lora_full.yaml
```

The full config uses `yezhen_her_train` for training and `yezhen_her_valid` for evaluation. Keep `test.jsonl` untouched for post-training manual evaluation.

## Notes

- These configs assume LoRA SFT, not full-parameter training.
- `cutoff_len: 4096` matches the current SFT-message generation limit.
- If GPU memory is tight, lower `cutoff_len`, increase `gradient_accumulation_steps`, or switch the server setup to QLoRA.
- Track the planned post-run annotation psychology review in [annotation_psychology_followup.md](annotation_psychology_followup.md).
