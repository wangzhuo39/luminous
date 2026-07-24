from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from luminous.training.pipeline.role_setup import build_system_content  # noqa: E402


QWEN3_EMPTY_THINK_PREFIX = "<think>\n\n</think>\n\n"

DEFAULT_COMPANION_SCENARIO = (
    "叶筝正在与现实中的用户进行一对一陪伴对话。用户不是小说角色，也不属于她的世界；"
    "她需要保持叶筝的克制、理性、温柔和边界感，把圣女式的安静承接转译成现实陪伴，"
    "不要把教廷、异能、帝国或剧情设定强行投射到用户生活。"
)

DEFAULT_OTHER_CHARACTERS = (
    "当前只有用户与叶筝。用户可能表达疲惫、压力、孤独、迷茫或对关系的试探；"
    "叶筝应先看见对方的真实处境，再用简短、稳定、不说教的方式回应。"
)


TAG_PATTERN = re.compile(r"<(system_thinking|role_thinking|role_action)>(.*?)</\1>", re.DOTALL)
NATIVE_THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_model_and_tokenizer(args: argparse.Namespace) -> tuple[Any, Any]:
    tokenizer = AutoTokenizer.from_pretrained(args.model_name_or_path, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.bfloat16 if args.bf16 else torch.float16
    model = AutoModelForCausalLM.from_pretrained(
        args.model_name_or_path,
        trust_remote_code=True,
        torch_dtype=dtype,
        device_map={"": 0},
    )
    if args.adapter_name_or_path:
        model = PeftModel.from_pretrained(model, args.adapter_name_or_path)
    model.eval()
    return model, tokenizer


def build_default_system() -> str:
    return build_system_content(DEFAULT_COMPANION_SCENARIO, DEFAULT_OTHER_CHARACTERS)


def build_user_content(raw_user_content: str) -> str:
    content = raw_user_content.strip()
    if content.startswith("用户说"):
        return content
    return f"用户说：{content}"


def build_prompt(tokenizer: Any, system_text: str, user_text: str) -> str:
    messages = [
        {"role": "system", "content": system_text},
        {"role": "user", "content": build_user_content(user_text)},
    ]
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return rendered + QWEN3_EMPTY_THINK_PREFIX


def to_display_text(raw: str, show_role_thinking: bool = False) -> str:
    text = NATIVE_THINK_PATTERN.sub("", raw)

    def replace_tag(match: re.Match[str]) -> str:
        tag = match.group(1)
        content = match.group(2).strip()
        if tag == "system_thinking":
            return ""
        if tag == "role_thinking":
            return f"【内心】{content}\n" if show_role_thinking else ""
        if tag == "role_action":
            return f"（{content}）\n" if content else ""
        return ""

    text = TAG_PATTERN.sub(replace_tag, text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


@torch.no_grad()
def generate_one(model: Any, tokenizer: Any, args: argparse.Namespace, system_text: str, user_text: str) -> str:
    prompt = build_prompt(tokenizer, system_text, user_text)
    device = next(model.parameters()).device
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    generation_kwargs: dict[str, Any] = {
        "max_new_tokens": args.max_new_tokens,
        "do_sample": args.temperature > 0,
        "repetition_penalty": args.repetition_penalty,
        "eos_token_id": tokenizer.eos_token_id,
        "pad_token_id": tokenizer.pad_token_id,
    }
    if args.temperature > 0:
        generation_kwargs["temperature"] = args.temperature
        generation_kwargs["top_p"] = args.top_p
    output_ids = model.generate(**inputs, **generation_kwargs)
    new_ids = output_ids[0, inputs["input_ids"].shape[-1] :]
    return tokenizer.decode(new_ids, skip_special_tokens=True).strip()


def iter_prompts(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.prompts_file:
        return read_jsonl(Path(args.prompts_file))
    if not args.user:
        raise ValueError("pass --user or --prompts-file")
    return [{"id": "manual", "user": args.user}]


def main() -> int:
    parser = argparse.ArgumentParser(description="Inference helper for Qwen3 + Ye Zheng HER LoRA.")
    parser.add_argument("--model-name-or-path", default="/data01/home/wz/LLM_model/Qwen/Qwen3-14B")
    parser.add_argument(
        "--adapter-name-or-path",
        default="/data01/home/wz/role-play/outputs/training/qwen3_14b_yezhen_her_lora",
    )
    parser.add_argument("--user", default="")
    parser.add_argument("--prompts-file", default="")
    parser.add_argument("--output-file", default="")
    parser.add_argument("--system-file", default="")
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=0.9)
    parser.add_argument("--repetition-penalty", type=float, default=1.05)
    parser.add_argument("--show-role-thinking", action="store_true")
    parser.add_argument("--bf16", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()

    base_system = (
        Path(args.system_file).read_text(encoding="utf-8").strip()
        if args.system_file
        else build_default_system()
    )
    model, tokenizer = load_model_and_tokenizer(args)

    output_handle = None
    if args.output_file:
        output_path = Path(args.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_handle = output_path.open("w", encoding="utf-8")

    try:
        for index, row in enumerate(iter_prompts(args), start=1):
            user_text = str(row.get("user") or row.get("content") or "").strip()
            if not user_text:
                continue
            system_text = str(row.get("system") or base_system)
            raw = generate_one(model, tokenizer, args, system_text, user_text)
            result = {
                "id": row.get("id", f"prompt-{index:03d}"),
                "category": row.get("category", ""),
                "user": user_text,
                "raw": raw,
                "display": to_display_text(raw, show_role_thinking=args.show_role_thinking),
                "notes": row.get("notes", ""),
            }
            if output_handle is not None:
                output_handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                output_handle.flush()
            else:
                print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    finally:
        if output_handle is not None:
            output_handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
