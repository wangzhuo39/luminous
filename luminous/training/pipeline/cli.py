from __future__ import annotations

import argparse
from pathlib import Path

from luminous.training.pipeline.llm import call_prompt_requests
from luminous.training.pipeline.pipeline import DEFAULT_PROFILE_PATH, run_staged_pipeline
from luminous.training.pipeline.quote_candidates import build_quote_candidates
from luminous.training.pipeline.requests import prepare_speaker_attribution_prompt_requests
from luminous.training.pipeline.responses import qa_sft_file


def _add_pipeline_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", required=True, type=Path, help="Input novel .txt file")
    parser.add_argument("--out", required=True, type=Path, help="Output directory for JSONL artifacts")
    parser.add_argument("--chapters", type=int, default=None, help="Number of chapters to process; omit for all")
    parser.add_argument("--language", choices=["zh", "en"], default="zh")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE_PATH, help="Profile markdown file")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=4,
        help="Parallel LLM calls inside each batch stage",
    )
    parser.add_argument(
        "--continue-on-failure",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Continue past speaker attribution LLM failures; use --no-continue-on-failure to stop before later stages",
    )


def _print_pipeline_summary(summary: object) -> None:
    counts = getattr(summary, "counts")
    output_dir = getattr(summary, "output_dir")
    print(f"trainable={counts['trainable']} review={counts['review']}")
    print(f"her_messages={output_dir / 'sft_messages_her.jsonl'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yezhen-pipeline")
    subparsers = parser.add_subparsers(dest="command")

    prepare = subparsers.add_parser("prepare-prompts", help="Render prompt request JSONL files")
    prepare.add_argument("--input", required=True, type=Path)
    prepare.add_argument("--out", required=True, type=Path)
    prepare.add_argument("--chapters", type=int, default=3)
    prepare.add_argument("--language", choices=["zh", "en"], default="zh")

    run = subparsers.add_parser("run", help="Run txt-to-HER-SFT automation")
    _add_pipeline_args(run)

    staged = subparsers.add_parser("run-staged", help="Alias for run; keeps traceable staged artifacts")
    _add_pipeline_args(staged)

    call_llm = subparsers.add_parser("call-llm", help="Call an OpenAI-compatible LLM for prompt request JSONL")
    call_llm.add_argument("--input", required=True, type=Path)
    call_llm.add_argument("--output", required=True, type=Path)
    call_llm.add_argument("--concurrency", type=int, default=1)

    qa = subparsers.add_parser("qa-sft", help="Run deterministic QA checks on SFT messages")
    qa.add_argument("--input", required=True, type=Path)
    qa.add_argument("--out", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "prepare-prompts":
        summary = build_quote_candidates(args.input, args.out, args.chapters, args.language)
        prepare_speaker_attribution_prompt_requests(args.out / "beat_candidates.jsonl", args.out, args.language)
        print(f"wrote {summary.counts['beat_candidates']} deterministic quote candidates")
        return 0
    if args.command in {"run", "run-staged"}:
        summary = run_staged_pipeline(
            args.input,
            args.out,
            args.chapters,
            args.language,
            profile_path=args.profile,
            concurrency=args.concurrency,
            continue_on_failure=args.continue_on_failure,
        )
        _print_pipeline_summary(summary)
        return 0
    if args.command == "call-llm":
        count = call_prompt_requests(args.input, args.output, show_progress=True, concurrency=args.concurrency)
        print(f"wrote {count} LLM responses")
        return 0
    if args.command == "qa-sft":
        summary = qa_sft_file(args.input, args.out)
        print(f"trainable={summary.counts['trainable']} review={summary.counts['review']}")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
