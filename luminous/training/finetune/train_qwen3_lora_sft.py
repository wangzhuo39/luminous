from __future__ import annotations

import argparse
import json
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import torch
from peft import LoraConfig, PeftModel, TaskType, get_peft_model
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, get_cosine_schedule_with_warmup


IGNORE_INDEX = -100


@dataclass
class ExampleStats:
    rows: int = 0
    kept: int = 0
    skipped_no_labels: int = 0
    prefix_mismatch: int = 0
    truncated: int = 0
    max_length: int = 0


class ChatSftDataset(Dataset[dict[str, torch.Tensor]]):
    def __init__(
        self,
        path: Path,
        tokenizer: Any,
        cutoff_len: int,
        max_samples: int | None = None,
        seed: int = 42,
    ) -> None:
        rows = read_jsonl(path)
        if max_samples is not None and max_samples > 0 and len(rows) > max_samples:
            rng = random.Random(seed)
            rows = rng.sample(rows, max_samples)

        self.examples: list[dict[str, torch.Tensor]] = []
        self.stats = ExampleStats(rows=len(rows))
        for row in rows:
            encoded = encode_messages(row, tokenizer, cutoff_len)
            self.stats.prefix_mismatch += int(encoded.get("prefix_mismatch", False))
            self.stats.truncated += int(encoded.get("truncated", False))
            input_ids = encoded["input_ids"]
            labels = encoded["labels"]
            if not any(label != IGNORE_INDEX for label in labels):
                self.stats.skipped_no_labels += 1
                continue
            self.stats.max_length = max(self.stats.max_length, len(input_ids))
            self.examples.append(
                {
                    "input_ids": torch.tensor(input_ids, dtype=torch.long),
                    "labels": torch.tensor(labels, dtype=torch.long),
                    "attention_mask": torch.ones(len(input_ids), dtype=torch.long),
                }
            )
        self.stats.kept = len(self.examples)

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
        return self.examples[index]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def encode_messages(row: dict[str, Any], tokenizer: Any, cutoff_len: int) -> dict[str, Any]:
    messages = row.get("messages", [])
    if not isinstance(messages, list) or len(messages) < 3:
        raise ValueError("row must contain at least system/user/assistant messages")

    # Qwen3's chat template injects an empty native <think></think> block before
    # assistant content. Locate the actual HER assistant text in rendered text so
    # only <system_thinking>... and the role response become supervised labels.
    assistant_text = str(messages[-1].get("content", ""))
    full_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    answer_start = full_text.rfind(assistant_text)
    if answer_start < 0:
        raise ValueError("assistant content not found in rendered chat template")

    full_ids = tokenizer(full_text, add_special_tokens=False).input_ids
    prompt_len = len(tokenizer(full_text[:answer_start], add_special_tokens=False).input_ids)
    prefix_mismatch = False

    labels = [IGNORE_INDEX] * min(prompt_len, len(full_ids)) + full_ids[prompt_len:]
    truncated = len(full_ids) > cutoff_len
    if truncated:
        full_ids = full_ids[:cutoff_len]
        labels = labels[:cutoff_len]

    return {
        "input_ids": full_ids,
        "labels": labels,
        "prefix_mismatch": prefix_mismatch,
        "truncated": truncated,
    }


def collate_batch(features: list[dict[str, torch.Tensor]], pad_token_id: int) -> dict[str, torch.Tensor]:
    max_len = max(item["input_ids"].numel() for item in features)
    batch: dict[str, list[torch.Tensor]] = {"input_ids": [], "attention_mask": [], "labels": []}
    for item in features:
        pad_len = max_len - item["input_ids"].numel()
        batch["input_ids"].append(
            torch.nn.functional.pad(item["input_ids"], (0, pad_len), value=pad_token_id)
        )
        batch["attention_mask"].append(
            torch.nn.functional.pad(item["attention_mask"], (0, pad_len), value=0)
        )
        batch["labels"].append(
            torch.nn.functional.pad(item["labels"], (0, pad_len), value=IGNORE_INDEX)
        )
    return {key: torch.stack(value) for key, value in batch.items()}


def load_model_and_tokenizer(args: argparse.Namespace) -> tuple[Any, Any]:
    tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        args.model_name_or_path,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16 if args.bf16 else torch.float16,
        device_map={"": 0},
    )
    model.config.use_cache = False
    if args.gradient_checkpointing:
        model.gradient_checkpointing_enable()

    if args.adapter_name_or_path:
        model = PeftModel.from_pretrained(model, args.adapter_name_or_path, is_trainable=True)
    else:
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=args.lora_dropout,
            target_modules=args.lora_target_modules.split(","),
            bias="none",
        )
        model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model, tokenizer


@torch.no_grad()
def evaluate(model: Any, dataloader: DataLoader, device: torch.device, bf16: bool) -> float:
    model.eval()
    total_loss = 0.0
    total_batches = 0
    dtype = torch.bfloat16 if bf16 else torch.float16
    for batch in dataloader:
        batch = {key: value.to(device) for key, value in batch.items()}
        with torch.autocast(device_type="cuda", dtype=dtype):
            loss = model(**batch).loss
        total_loss += float(loss.detach().cpu())
        total_batches += 1
    model.train()
    return total_loss / max(total_batches, 1)


def save_state(output_dir: Path, state: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "trainer_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def train(args: argparse.Namespace) -> None:
    torch.manual_seed(args.seed)
    random.seed(args.seed)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    model, tokenizer = load_model_and_tokenizer(args)
    device = torch.device("cuda:0")
    pad_token_id = int(tokenizer.pad_token_id)

    train_dataset = ChatSftDataset(
        Path(args.train_file),
        tokenizer,
        cutoff_len=args.cutoff_len,
        max_samples=args.max_train_samples,
        seed=args.seed,
    )
    eval_dataset = ChatSftDataset(
        Path(args.valid_file),
        tokenizer,
        cutoff_len=args.cutoff_len,
        max_samples=args.max_eval_samples,
        seed=args.seed,
    )
    print("train_dataset", asdict(train_dataset.stats), flush=True)
    print("eval_dataset", asdict(eval_dataset.stats), flush=True)

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.per_device_train_batch_size,
        shuffle=True,
        collate_fn=lambda features: collate_batch(features, pad_token_id),
    )
    eval_loader = DataLoader(
        eval_dataset,
        batch_size=args.per_device_eval_batch_size,
        shuffle=False,
        collate_fn=lambda features: collate_batch(features, pad_token_id),
    )

    trainable_params = [param for param in model.parameters() if param.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=args.learning_rate, weight_decay=args.weight_decay)

    steps_per_epoch = math.ceil(len(train_loader) / args.gradient_accumulation_steps)
    total_steps = max(1, int(steps_per_epoch * args.num_train_epochs))
    warmup_steps = int(total_steps * args.warmup_ratio)
    scheduler = get_cosine_schedule_with_warmup(optimizer, warmup_steps, total_steps)

    state: dict[str, Any] = {
        "args": vars(args),
        "train_dataset": asdict(train_dataset.stats),
        "eval_dataset": asdict(eval_dataset.stats),
        "total_steps": total_steps,
        "warmup_steps": warmup_steps,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_state(output_dir, state)

    model.train()
    optimizer.zero_grad(set_to_none=True)
    global_step = 0
    running_loss = 0.0
    running_loss_count = 0
    dtype = torch.bfloat16 if args.bf16 else torch.float16

    for epoch in range(math.ceil(args.num_train_epochs)):
        for step, batch in enumerate(train_loader, start=1):
            batch = {key: value.to(device) for key, value in batch.items()}
            with torch.autocast(device_type="cuda", dtype=dtype):
                raw_loss = model(**batch).loss
                loss = raw_loss / args.gradient_accumulation_steps
            loss.backward()
            running_loss += float(raw_loss.detach().cpu())
            running_loss_count += 1

            if step % args.gradient_accumulation_steps != 0 and step != len(train_loader):
                continue

            torch.nn.utils.clip_grad_norm_(trainable_params, args.max_grad_norm)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad(set_to_none=True)
            global_step += 1

            if global_step % args.logging_steps == 0:
                avg_loss = running_loss / max(running_loss_count, 1)
                running_loss = 0.0
                running_loss_count = 0
                print(
                    json.dumps(
                        {
                            "event": "log",
                            "epoch": epoch + 1,
                            "global_step": global_step,
                            "loss": round(avg_loss, 6),
                            "lr": scheduler.get_last_lr()[0],
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

            if global_step % args.eval_steps == 0:
                eval_loss = evaluate(model, eval_loader, device, args.bf16)
                print(
                    json.dumps(
                        {
                            "event": "eval",
                            "global_step": global_step,
                            "eval_loss": round(eval_loss, 6),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

            if global_step % args.save_steps == 0:
                checkpoint_dir = output_dir / f"checkpoint-{global_step}"
                model.save_pretrained(checkpoint_dir)
                tokenizer.save_pretrained(checkpoint_dir)
                print(f"saved_checkpoint={checkpoint_dir}", flush=True)

            state.update(
                {
                    "global_step": global_step,
                    "last_epoch": epoch + 1,
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            save_state(output_dir, state)

            if global_step >= total_steps:
                break
        if global_step >= total_steps:
            break

    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    final_eval_loss = evaluate(model, eval_loader, device, args.bf16)
    state.update(
        {
            "global_step": global_step,
            "final_eval_loss": final_eval_loss,
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    save_state(output_dir, state)
    print(f"saved_final_adapter={output_dir}", flush=True)
    print(json.dumps({"event": "finished", "final_eval_loss": final_eval_loss}, ensure_ascii=False), flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Direct PEFT LoRA SFT for Qwen3 HER-style messages")
    parser.add_argument("--model-name-or-path", required=True)
    parser.add_argument(
        "--adapter-name-or-path",
        default="",
        help="Optional existing LoRA adapter to continue training.",
    )
    parser.add_argument("--train-file", required=True)
    parser.add_argument("--valid-file", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--cutoff-len", type=int, default=4096)
    parser.add_argument("--max-train-samples", type=int, default=0)
    parser.add_argument("--max-eval-samples", type=int, default=0)
    parser.add_argument("--num-train-epochs", type=float, default=2.0)
    parser.add_argument("--per-device-train-batch-size", type=int, default=1)
    parser.add_argument("--per-device-eval-batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=1.0e-4)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--warmup-ratio", type=float, default=0.03)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--logging-steps", type=int, default=10)
    parser.add_argument("--eval-steps", type=int, default=50)
    parser.add_argument("--save-steps", type=int, default=100)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--lora-dropout", type=float, default=0.05)
    parser.add_argument(
        "--lora-target-modules",
        default="q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj",
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--bf16", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--gradient-checkpointing", action=argparse.BooleanOptionalAction, default=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.max_train_samples <= 0:
        args.max_train_samples = None
    if args.max_eval_samples <= 0:
        args.max_eval_samples = None
    train(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
