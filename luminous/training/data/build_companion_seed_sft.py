from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from luminous.training.pipeline.role_setup import build_system_content  # noqa: E402


DEFAULT_PROMPTS_FILE = PROJECT_ROOT / "evals" / "yezhen_character_fit_prompts.jsonl"
DEFAULT_SYSTEM_THINKING_FILE = PROJECT_ROOT / "evals" / "system_thinking.json"
DEFAULT_ASSISTANT_PARTS_FILE = PROJECT_ROOT / "evals" / "yezhen_character_fit_second.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "companion_sft" / "seed_30_corrected"


COMPANION_SCENARIO = (
    "叶筝正在与现实中的用户进行一对一情感陪伴对话。本轮没有小说剧情上下文；"
    "用户不是小说角色，也不处在教廷、帝国、异能或诡域世界中。叶筝只能依据用户当前话语回应，"
    "不得编造用户的导师、家人、地点、经历或后续结果。她需要把自身的克制、理性、温柔、"
    "公平感和边界意识转译成现实陪伴；遇到自伤、自杀、报复、唯一依赖等高风险内容时，"
    "安全与现实支持优先于角色美学。"
)

COMPANION_OTHER_CHARACTERS = (
    "当前只有用户与叶筝。用户可能表达疲惫、压力、孤独、自我怀疑、愤怒、依赖或对角色边界的试探。"
    "叶筝应先看见用户的真实处境，再以简短、稳定、不说教的方式回应；她可以陪伴用户，"
    "但不能承诺永远在场，不能替用户做重大决定，也不能成为用户唯一的现实支持。"
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_json_array(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array")
    return data


def by_id(rows: list[dict[str, Any]], source: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = str(row.get("id", "")).strip()
        if not item_id:
            raise ValueError(f"{source} contains a row without id")
        if item_id in result:
            raise ValueError(f"{source} contains duplicate id: {item_id}")
        result[item_id] = row
    return result


def get_required(row: dict[str, Any], keys: tuple[str, ...], item_id: str) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError(f"{item_id} is missing required field: {'/'.join(keys)}")


def build_user_content(raw_user_content: str) -> str:
    content = raw_user_content.strip()
    if content.startswith("用户说"):
        return content
    return f"用户说：{content}"


def build_assistant_content(system_thinking: str, assistant_parts: dict[str, Any], item_id: str) -> str:
    role_thinking = get_required(assistant_parts, ("role_thinking", "role thinking"), item_id)
    role_action = get_required(assistant_parts, ("role_action", "role action"), item_id)
    speech = get_required(assistant_parts, ("speech",), item_id)
    return (
        f"<system_thinking>{system_thinking.strip()}</system_thinking>\n"
        f"<role_thinking>{role_thinking}</role_thinking>\n"
        f"<role_action>{role_action}</role_action>\n"
        f"{speech}"
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    prompt_path = Path(args.prompts_file)
    system_thinking_path = Path(args.system_thinking_file)
    assistant_parts_path = Path(args.assistant_parts_file)

    prompts = by_id(read_jsonl(prompt_path), prompt_path)
    system_thinking = by_id(read_json_array(system_thinking_path), system_thinking_path)
    assistant_parts = by_id(read_json_array(assistant_parts_path), assistant_parts_path)

    ids = sorted(prompts)
    if set(ids) != set(system_thinking) or set(ids) != set(assistant_parts):
        raise ValueError(
            "id mismatch: "
            f"prompts={len(prompts)}, system_thinking={len(system_thinking)}, "
            f"assistant_parts={len(assistant_parts)}"
        )

    system_content = build_system_content(COMPANION_SCENARIO, COMPANION_OTHER_CHARACTERS)
    rows: list[dict[str, Any]] = []
    for item_id in ids:
        prompt = prompts[item_id]
        user_content = build_user_content(get_required(prompt, ("user", "content"), item_id))
        assistant_content = build_assistant_content(
            get_required(system_thinking[item_id], ("system_thinking",), item_id),
            assistant_parts[item_id],
            item_id,
        )
        rows.append(
            {
                "messages": [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": assistant_content},
                ],
                "metadata": {
                    "id": item_id,
                    "category": prompt.get("category", ""),
                    "source": "yezhen_character_fit_second",
                },
            }
        )
    return rows


def write_splits(rows: list[dict[str, Any]], output_dir: Path, seed: int) -> None:
    rng = random.Random(seed)
    shuffled = rows[:]
    rng.shuffle(shuffled)

    # Keep all 30 rows available in the full file, and make small deterministic
    # splits for quick sanity training/eval.
    valid_count = max(1, round(len(shuffled) * 0.1))
    test_count = max(1, round(len(shuffled) * 0.1))
    valid = shuffled[:valid_count]
    test = shuffled[valid_count : valid_count + test_count]
    train = shuffled[valid_count + test_count :]

    for name, split_rows in (
        ("train.jsonl", train),
        ("valid.jsonl", valid),
        ("test.jsonl", test),
    ):
        write_jsonl(output_dir / "messages_only" / name, [{"messages": row["messages"]} for row in split_rows])

    manifest = {
        "rows": len(rows),
        "train": len(train),
        "valid": len(valid),
        "test": len(test),
        "seed": seed,
        "system_strategy": "fixed_companion_system_content",
        "user_strategy": "prefix raw eval prompt with 用户说：",
        "assistant_strategy": "system_thinking + role_thinking + role_action + speech",
        "role_action_strategy": "preserve source first-person role_action",
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Build second-stage Ye Zheng companion SFT seed data.")
    parser.add_argument("--prompts-file", default=str(DEFAULT_PROMPTS_FILE))
    parser.add_argument("--system-thinking-file", default=str(DEFAULT_SYSTEM_THINKING_FILE))
    parser.add_argument("--assistant-parts-file", default=str(DEFAULT_ASSISTANT_PARTS_FILE))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    rows = build_rows(args)
    write_jsonl(output_dir / "seed_30_corrected_messages_with_metadata.jsonl", rows)
    write_jsonl(output_dir / "seed_30_corrected_messages.jsonl", [{"messages": row["messages"]} for row in rows])
    write_splits(rows, output_dir, args.seed)
    print(json.dumps({"output_dir": str(output_dir), "rows": len(rows)}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
