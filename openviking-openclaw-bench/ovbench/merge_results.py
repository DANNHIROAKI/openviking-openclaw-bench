from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .util import ensure_dir, write_json



def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]



def merge_run_dir(run_dir: Path) -> dict[str, Any]:
    qa_files = sorted(run_dir.glob("qa.*.jsonl"))
    ingest_files = sorted(run_dir.glob("ingest.*.jsonl"))

    qa_records = [record for path in qa_files for record in load_jsonl(path)]
    ingest_records = [record for path in ingest_files for record in load_jsonl(path)]

    answers_all = run_dir / "answers.all.jsonl"
    with answers_all.open("w", encoding="utf-8") as f:
        for record in qa_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    ingest_all = run_dir / "ingest.all.jsonl"
    with ingest_all.open("w", encoding="utf-8") as f:
        for record in ingest_records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def total_usage(records: list[dict[str, Any]]) -> dict[str, int]:
        total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        for record in records:
            usage = record.get("usage", {})
            for key in total:
                total[key] += int(usage.get(key, 0) or 0)
        return total

    qa_usage = total_usage(qa_records)
    ingest_usage = total_usage(ingest_records)
    full_usage = {key: qa_usage[key] + ingest_usage[key] for key in qa_usage}

    payload = {
        "qa_only": qa_usage,
        "ingest_only": ingest_usage,
        "full_pipeline": full_usage,
        "qa_file_count": len(qa_files),
        "ingest_file_count": len(ingest_files),
        "qa_record_count": len(qa_records),
        "ingest_record_count": len(ingest_records),
        "answers_all": str(answers_all),
        "ingest_all": str(ingest_all),
    }
    write_json(run_dir / "usage.json", payload)
    return payload



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge per-sample benchmark results into group-level outputs")
    parser.add_argument("run_dir", help="Run directory containing qa.*.jsonl and ingest.*.jsonl")
    return parser



def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_dir = Path(args.run_dir).expanduser()
    ensure_dir(run_dir)
    payload = merge_run_dir(run_dir)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
