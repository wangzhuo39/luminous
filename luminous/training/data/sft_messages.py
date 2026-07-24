from __future__ import annotations

import argparse
import hashlib
import json
import random
import shutil
import sys
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from luminous.training.pipeline.jsonl import read_jsonl as _read_jsonl
from luminous.training.pipeline.jsonl import write_jsonl as _write_jsonl


ALLOWED_ROLES = ("system", "user", "assistant")
DEFAULT_SAMPLE_COUNT = 5
DEFAULT_BASE_MODEL = "Qwen3-7B"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return _read_jsonl(path)


def write_jsonl(path: Path, rows: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> int:
    return _write_jsonl(path, rows)


def inspect_sft_file(input_path: Path, out_path: Path | None = None, sample_count: int = DEFAULT_SAMPLE_COUNT) -> dict[str, Any]:
    rows = read_jsonl(input_path)
    summary = _build_inspect_summary(input_path, rows, sample_count)
    if out_path is not None:
        write_jsonl(out_path, [summary])
    return summary


def split_sft_file(
    input_path: Path,
    out_dir: Path,
    train_ratio: float,
    valid_ratio: float,
    test_ratio: float,
    seed: int = 42,
) -> dict[str, Any]:
    ratios = {"train": train_ratio, "valid": valid_ratio, "test": test_ratio}
    if not _ratios_sum_to_one(ratios):
        raise ValueError("split ratios must sum to 1")

    rows = read_jsonl(input_path)
    strategy = "chapter" if any(str(row.get("chapter_id", "")).strip() for row in rows) else "row"
    targets = _allocate_counts(len(rows), ratios)
    rng = random.Random(seed)
    shuffled = rows[:]
    rng.shuffle(shuffled)

    if strategy == "row":
        split_rows = {
            "train": shuffled[: targets["train"]],
            "valid": shuffled[targets["train"] : targets["train"] + targets["valid"]],
            "test": shuffled[targets["train"] + targets["valid"] :],
        }
    else:
        split_rows = _split_by_group(
            shuffled,
            targets,
            seed=seed,
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    file_paths = {}
    counts = {}
    for split_name in ("train", "valid", "test"):
        split_path = out_dir / f"{split_name}.jsonl"
        counts[split_name] = write_jsonl(split_path, split_rows[split_name])
        file_paths[split_name] = str(split_path)

    summary = {
        "input": str(input_path),
        "strategy": strategy,
        "seed": seed,
        "ratios": ratios,
        "counts": counts,
        "files": {
            **file_paths,
            "summary": str(out_dir / "split_summary.jsonl"),
        },
    }
    write_jsonl(out_dir / "split_summary.jsonl", [summary])
    return summary


def export_llamafactory_dataset(
    input_dir: Path,
    out_dir: Path,
    dataset_prefix: str = "yezhen_her",
    base_model: str = DEFAULT_BASE_MODEL,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)

    dataset_info: dict[str, dict[str, Any]] = {}
    manifest_files: dict[str, dict[str, Any]] = {}

    for split_name in ("train", "valid", "test"):
        source_path = input_dir / f"{split_name}.jsonl"
        target_path = out_dir / f"{split_name}.jsonl"
        if source_path.exists():
            shutil.copy2(source_path, target_path)
        else:
            write_jsonl(target_path, [])
        stats = _build_file_stats(target_path)
        dataset_name = f"{dataset_prefix}_{split_name}"
        dataset_info[dataset_name] = {
            "file_name": target_path.name,
            "formatting": "sharegpt",
            "columns": {"messages": "messages"},
            "tags": {
                "role_tag": "role",
                "content_tag": "content",
                "user_tag": "user",
                "assistant_tag": "assistant",
                "system_tag": "system",
            },
        }
        manifest_files[split_name] = {
            "dataset": dataset_name,
            "file_name": target_path.name,
            **stats,
        }

    dataset_info_path = out_dir / "dataset_info.json"
    dataset_info_path.write_text(json.dumps(dataset_info, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = {
        "base_model": base_model,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_prefix": dataset_prefix,
        "format": "sharegpt_messages_jsonl",
        "files": manifest_files,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "output_dir": str(out_dir),
        "datasets": sorted(dataset_info),
        "dataset_info": str(dataset_info_path),
        "manifest": str(manifest_path),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="roleplay-data")
    subparsers = parser.add_subparsers(dest="command")

    inspect = subparsers.add_parser("inspect", help="Summarize an SFT messages JSONL file")
    inspect.add_argument("--input", required=True, type=Path)
    inspect.add_argument("--out", type=Path, default=None)
    inspect.add_argument("--samples", type=int, default=DEFAULT_SAMPLE_COUNT)

    split = subparsers.add_parser("split", help="Split an SFT messages JSONL file")
    split.add_argument("--input", required=True, type=Path)
    split.add_argument("--out", required=True, type=Path)
    split.add_argument("--train", required=True, type=float)
    split.add_argument("--valid", required=True, type=float)
    split.add_argument("--test", required=True, type=float)
    split.add_argument("--seed", type=int, default=42)

    export = subparsers.add_parser("export-llamafactory", help="Export a split directory for LLaMA-Factory")
    export.add_argument("--input-dir", required=True, type=Path)
    export.add_argument("--out", required=True, type=Path)
    export.add_argument("--dataset-prefix", default="yezhen_her")
    export.add_argument("--base-model", default=DEFAULT_BASE_MODEL)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "inspect":
            summary = inspect_sft_file(args.input, args.out, sample_count=args.samples)
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        if args.command == "split":
            summary = split_sft_file(args.input, args.out, args.train, args.valid, args.test, seed=args.seed)
            counts = summary["counts"]
            print(f"train={counts['train']} valid={counts['valid']} test={counts['test']} strategy={summary['strategy']}")
            return 0
        if args.command == "export-llamafactory":
            summary = export_llamafactory_dataset(
                args.input_dir,
                args.out,
                dataset_prefix=args.dataset_prefix,
                base_model=args.base_model,
            )
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:  # noqa: BLE001 - keep the CLI compact and explicit.
        print(str(exc), file=sys.stderr)
        return 1

    parser.print_help()
    return 0


def _build_inspect_summary(input_path: Path, rows: list[dict[str, Any]], sample_count: int) -> dict[str, Any]:
    chapter_counts: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    lengths: dict[str, list[int]] = {role: [] for role in ALLOWED_ROLES}
    invalid_role_rows = 0
    missing_messages = 0

    for row in rows:
        messages = row.get("messages")
        if not isinstance(messages, list) or not messages:
            missing_messages += 1
            continue

        row_roles: list[str] = []
        row_valid = True
        for message in messages:
            if not isinstance(message, dict):
                row_valid = False
                continue
            role = str(message.get("role", "")).strip()
            content = message.get("content", "")
            if role:
                role_counts[role] += 1
                row_roles.append(role)
                if isinstance(content, str):
                    lengths.setdefault(role, []).append(len(content))
                else:
                    row_valid = False
            else:
                row_valid = False

        expected_roles = list(ALLOWED_ROLES)
        if row_roles != expected_roles or not row_valid:
            invalid_role_rows += 1

        chapter_id = str(row.get("chapter_id", "")).strip()
        if chapter_id:
            chapter_counts[chapter_id] += 1

    return {
        "input": str(input_path),
        "rows": len(rows),
        "chapters": len(chapter_counts),
        "chapter_counts": dict(sorted(chapter_counts.items())),
        "role_counts": dict(sorted(role_counts.items())),
        "invalid_role_rows": invalid_role_rows,
        "missing_messages": missing_messages,
        "lengths": {role: _length_summary(lengths.get(role, [])) for role in ALLOWED_ROLES},
        "sample_indices": _sample_indices(len(rows), sample_count),
    }


def _build_file_stats(path: Path) -> dict[str, Any]:
    summary = inspect_sft_file(path, sample_count=1)
    data = path.read_bytes()
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "rows": summary["rows"],
        "chapters": summary["chapters"],
        "invalid_role_rows": summary["invalid_role_rows"],
        "missing_messages": summary["missing_messages"],
    }


def _length_summary(lengths: list[int]) -> dict[str, Any]:
    if not lengths:
        return {"min": 0, "max": 0, "avg": 0.0, "over_1000": 0, "over_2000": 0}
    total = sum(lengths)
    return {
        "min": min(lengths),
        "max": max(lengths),
        "avg": round(total / len(lengths), 2),
        "over_1000": sum(1 for value in lengths if value > 1000),
        "over_2000": sum(1 for value in lengths if value > 2000),
    }


def _sample_indices(total: int, sample_count: int) -> list[int]:
    if total <= 0 or sample_count <= 0:
        return []
    sample_count = min(sample_count, total)
    if sample_count == 1:
        return [0]

    raw = [round(index * (total - 1) / (sample_count - 1)) for index in range(sample_count)]
    result: list[int] = []
    seen: set[int] = set()
    for value in raw:
        candidate = int(value)
        while candidate in seen and candidate < total - 1:
            candidate += 1
        while candidate in seen and candidate > 0:
            candidate -= 1
        if candidate not in seen:
            seen.add(candidate)
            result.append(candidate)

    if len(result) < sample_count:
        for candidate in range(total):
            if candidate not in seen:
                seen.add(candidate)
                result.append(candidate)
            if len(result) == sample_count:
                break
    return sorted(result)


def _ratios_sum_to_one(ratios: dict[str, float]) -> bool:
    return abs(sum(ratios.values()) - 1.0) <= 1e-6


def _allocate_counts(total: int, ratios: dict[str, float]) -> dict[str, int]:
    raw = {name: total * ratio for name, ratio in ratios.items()}
    counts = {name: int(value) for name, value in raw.items()}
    remainder = total - sum(counts.values())
    order = sorted(ratios, key=lambda name: (-((raw[name]) - counts[name]), {"train": 0, "valid": 1, "test": 2}[name]))
    for name in order:
        if remainder <= 0:
            break
        counts[name] += 1
        remainder -= 1
    return counts


def _split_by_group(rows: list[dict[str, Any]], targets: dict[str, int], seed: int) -> dict[str, list[dict[str, Any]]]:
    groups: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    for index, row in enumerate(rows):
        chapter_id = str(row.get("chapter_id", "")).strip() or f"__row_{index}"
        groups.setdefault(chapter_id, []).append(row)

    group_items = list(groups.items())
    rng = random.Random(seed)
    rng.shuffle(group_items)
    group_items.sort(key=lambda item: -len(item[1]))

    splits: dict[str, list[dict[str, Any]]] = {"train": [], "valid": [], "test": []}
    counts = {"train": 0, "valid": 0, "test": 0}
    split_order = ("train", "valid", "test")

    for _, group_rows in group_items:
        chosen = max(
            split_order,
            key=lambda name: (targets[name] - counts[name], -split_order.index(name)),
        )
        splits[chosen].extend(group_rows)
        counts[chosen] += len(group_rows)

    return splits
