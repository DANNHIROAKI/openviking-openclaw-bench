from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import BenchConfig
from .util import write_json, write_text



def build_group_row(group_id: str, run_dir: Path) -> dict[str, Any]:
    judge_path = run_dir / "judge.json"
    usage_path = run_dir / "usage.json"
    judge = json.loads(judge_path.read_text(encoding="utf-8")) if judge_path.exists() else {}
    usage = json.loads(usage_path.read_text(encoding="utf-8")) if usage_path.exists() else {}
    return {
        "group": group_id,
        "completion_rate": float(judge.get("score", 0.0)),
        "correct": int(judge.get("correct", 0)),
        "total": int(judge.get("total", 0)),
        "qa_input_tokens_total": int(usage.get("qa_only", {}).get("input_tokens", 0)),
        "full_input_tokens_total": int(usage.get("full_pipeline", {}).get("input_tokens", 0)),
        "notes": "",
    }



def render_markdown(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Group | Completion Rate | Correct / Total | QA Input Tokens Total | Full Input Tokens Total |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            "| {group} | {completion_rate:.2%} | {correct}/{total} | {qa_input_tokens_total} | {full_input_tokens_total} |".format(
                **row
            )
        )
    return "\n".join(lines) + "\n"



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a final Markdown/JSON report from all group runs")
    parser.add_argument("config", help="Path to bench config JSON")
    parser.add_argument("--run-label", default="full", help="Run label under each group outputs dir")
    parser.add_argument("--groups", nargs="*", default=None, help="Subset of groups, default all")
    parser.add_argument("--output-json", default=None, help="Output JSON path")
    parser.add_argument("--output-md", default=None, help="Output Markdown path")
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    cfg = BenchConfig.load(args.config)
    group_ids = args.groups or list(cfg.groups)
    rows: list[dict[str, Any]] = []
    for group_id in group_ids:
        group = cfg.get_group(group_id)
        run_dir = group.outputs_dir / args.run_label
        row = build_group_row(group_id, run_dir)
        row["notes"] = group.notes
        rows.append(row)

    markdown = render_markdown(rows)
    print(markdown)
    if args.output_json:
        write_json(Path(args.output_json).expanduser(), {"rows": rows})
    if args.output_md:
        write_text(Path(args.output_md).expanduser(), markdown)


if __name__ == "__main__":
    main()
