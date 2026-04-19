from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .judge_util import grade_answers, load_answers
from .util import write_json


async def run(
    *,
    input_path: Path,
    output_path: Path | None,
    base_url: str | None,
    token: str | None,
    model: str,
    max_concurrency: int,
) -> dict:
    answers = load_answers(str(input_path))
    print(f"Loaded {len(answers)} answers from {input_path}", file=sys.stderr)
    graded = await grade_answers(
        answers,
        base_url=base_url,
        api_key=token,
        model=model,
        max_concurrency=max_concurrency,
    )

    correct = sum(1 for item in graded if item["grade"])
    total = len(graded)
    score = correct / total if total else 0.0

    categories: dict[str, dict[str, int]] = {}
    for item in graded:
        cat = str(item.get("category", "unknown"))
        slot = categories.setdefault(cat, {"correct": 0, "total": 0})
        slot["total"] += 1
        if item["grade"]:
            slot["correct"] += 1

    payload = {
        "score": score,
        "correct": correct,
        "total": total,
        "per_category": {
            key: {
                **value,
                "score": (value["correct"] / value["total"] if value["total"] else 0.0),
            }
            for key, value in categories.items()
        },
        "grades": graded,
    }
    if output_path is not None:
        write_json(output_path, payload)
        print(f"Wrote grades to {output_path}", file=sys.stderr)
    print(f"Results: {correct}/{total} correct ({score:.2%})")
    return payload



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Grade OpenClaw QA responses with an LLM judge")
    parser.add_argument("input", help="Path to merged answers JSONL/JSON")
    parser.add_argument("--output", default=None, help="Where to write judge JSON")
    parser.add_argument("--base-url", default=None, help="Judge API base URL")
    parser.add_argument("--token", default=None, help="Judge API token")
    parser.add_argument("--model", default="gpt-4o-mini", help="Judge model")
    parser.add_argument("--max-concurrency", type=int, default=20, help="Judge concurrency")
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    asyncio.run(
        run(
            input_path=Path(args.input).expanduser(),
            output_path=Path(args.output).expanduser() if args.output else None,
            base_url=args.base_url,
            token=args.token,
            model=args.model,
            max_concurrency=args.max_concurrency,
        )
    )


if __name__ == "__main__":
    main()
