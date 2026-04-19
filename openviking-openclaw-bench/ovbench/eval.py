from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .http_api import send_response
from .util import ensure_dir, write_json


@dataclass
class EvalArgs:
    mode: str
    input: Path
    output_dir: Path
    base_url: str
    token: str
    group_id: str
    run_label: str
    user_template: str
    sample: int | None
    sessions: tuple[int, int] | None
    tail: str
    count: int | None
    parallel: int
    timeout: int
    retries: int


def format_locomo_message(msg: dict[str, Any]) -> str:
    speaker = msg.get("speaker", "unknown")
    text = msg.get("text", "")
    line = f"{speaker}: {text}"
    img_urls = msg.get("img_url", [])
    if isinstance(img_urls, str):
        img_urls = [img_urls]
    blip = msg.get("blip_caption", "")
    if img_urls:
        for url in img_urls:
            caption = f": {blip}" if blip else ""
            line += f"\n{url}{caption}"
    elif blip:
        line += f"\n({blip})"
    return line



def load_locomo_data(path: Path, sample_index: int | None = None) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if sample_index is None:
        return data
    if sample_index < 0 or sample_index >= len(data):
        raise SystemExit(f"sample index {sample_index} is out of range 0..{len(data)-1}")
    return [data[sample_index]]



def build_session_messages(item: dict[str, Any], session_range: tuple[int, int] | None, tail: str) -> list[dict[str, Any]]:
    conv = item["conversation"]
    session_keys = sorted(
        [k for k in conv if k.startswith("session_") and not k.endswith("_date_time")],
        key=lambda key: int(key.split("_")[1]),
    )
    sessions: list[dict[str, Any]] = []
    for session_key in session_keys:
        session_num = int(session_key.split("_")[1])
        if session_range is not None:
            lo, hi = session_range
            if session_num < lo or session_num > hi:
                continue
        date_time = conv.get(f"{session_key}_date_time", "")
        parts = [f"[group chat conversation: {date_time}]"]
        for message in conv[session_key]:
            parts.append(format_locomo_message(message))
        if tail:
            parts.append(tail)
        sessions.append(
            {
                "message": "\n\n".join(parts),
                "meta": {
                    "sample_id": item["sample_id"],
                    "session_key": session_key,
                    "date_time": date_time,
                },
            }
        )
    return sessions



def parse_session_range(raw: str | None) -> tuple[int, int] | None:
    if not raw:
        return None
    if "-" in raw:
        left, right = raw.split("-", 1)
        return int(left), int(right)
    value = int(raw)
    return value, value



def resolve_user(*, group_id: str, sample_id: str, run_label: str, user_template: str) -> str:
    return user_template.format(group_id=group_id, sample_id=sample_id, run_label=run_label)



def normalize_usage(records: list[dict[str, Any]]) -> dict[str, int]:
    total = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for record in records:
        usage = record.get("usage", {})
        for key in total:
            total[key] += int(usage.get(key, 0) or 0)
    return total



def ingest_one_sample(item: dict[str, Any], args: EvalArgs) -> list[dict[str, Any]]:
    sample_id = item["sample_id"]
    user = resolve_user(group_id=args.group_id, sample_id=sample_id, run_label=args.run_label, user_template=args.user_template)
    sessions = build_session_messages(item, args.sessions, args.tail)
    result_path = args.output_dir / f"ingest.{sample_id}.jsonl"
    records: list[dict[str, Any]] = []
    print(f"[ingest] {sample_id} -> {len(sessions)} session(s), user={user}", file=sys.stderr)
    with result_path.open("w", encoding="utf-8") as f:
        for index, session in enumerate(sessions, start=1):
            reply, usage, response_json = send_response(
                base_url=args.base_url,
                token=args.token,
                user=user,
                message=session["message"],
                timeout=args.timeout,
                retries=args.retries,
            )
            record = {
                "kind": "ingest",
                "sample_id": sample_id,
                "user": user,
                "ordinal": index,
                "session": session["meta"]["session_key"],
                "date_time": session["meta"]["date_time"],
                "reply": reply,
                "usage": usage,
                "response_json": response_json,
            }
            records.append(record)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(
                f"  [ingest] {sample_id} {session['meta']['session_key']}: in={usage['input_tokens']} total={usage['total_tokens']}",
                file=sys.stderr,
            )
    return records


async def qa_one_sample(item: dict[str, Any], args: EvalArgs, semaphore: asyncio.Semaphore) -> list[dict[str, Any]]:
    sample_id = item["sample_id"]
    user = resolve_user(group_id=args.group_id, sample_id=sample_id, run_label=args.run_label, user_template=args.user_template)
    qas = [qa for qa in item.get("qa", []) if str(qa.get("category", "")) != "5"]
    if args.count is not None:
        qas = qas[: args.count]
    result_path = args.output_dir / f"qa.{sample_id}.jsonl"
    async with semaphore:
        print(f"[qa] {sample_id} -> {len(qas)} question(s), user={user}", file=sys.stderr)
        records: list[dict[str, Any]] = []
        with result_path.open("w", encoding="utf-8") as f:
            for index, qa in enumerate(qas, start=1):
                question = str(qa["question"])
                response, usage, response_json = await asyncio.to_thread(
                    send_response,
                    base_url=args.base_url,
                    token=args.token,
                    user=user,
                    message=question,
                    timeout=args.timeout,
                    retries=args.retries,
                )
                record = {
                    "kind": "qa",
                    "sample_id": sample_id,
                    "user": user,
                    "qi": index,
                    "question": question,
                    "expected": str(qa["answer"]),
                    "response": response,
                    "category": qa.get("category", ""),
                    "evidence": qa.get("evidence", []),
                    "usage": usage,
                    "response_json": response_json,
                }
                records.append(record)
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(
                    f"  [qa] {sample_id} Q{index}/{len(qas)} in={usage['input_tokens']} total={usage['total_tokens']}",
                    file=sys.stderr,
                )
        return records



def summarize(kind: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    by_sample: dict[str, dict[str, int]] = {}
    for record in records:
        sample_id = record["sample_id"]
        slot = by_sample.setdefault(sample_id, {"count": 0, "input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
        slot["count"] += 1
        usage = record.get("usage", {})
        slot["input_tokens"] += int(usage.get("input_tokens", 0) or 0)
        slot["output_tokens"] += int(usage.get("output_tokens", 0) or 0)
        slot["total_tokens"] += int(usage.get("total_tokens", 0) or 0)
    return {
        "kind": kind,
        "record_count": len(records),
        "usage": normalize_usage(records),
        "per_sample": by_sample,
    }



def run_ingest(args: EvalArgs) -> None:
    samples = load_locomo_data(args.input, args.sample)
    ensure_dir(args.output_dir)
    all_records: list[dict[str, Any]] = []
    for item in samples:
        all_records.extend(ingest_one_sample(item, args))
    summary = summarize("ingest", all_records)
    write_json(args.output_dir / "ingest.summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False), file=sys.stderr)



def run_qa(args: EvalArgs) -> None:
    samples = load_locomo_data(args.input, args.sample)
    ensure_dir(args.output_dir)

    async def _inner() -> list[list[dict[str, Any]]]:
        semaphore = asyncio.Semaphore(max(1, args.parallel))
        tasks = [qa_one_sample(item, args, semaphore) for item in samples]
        return await asyncio.gather(*tasks)

    result_lists = asyncio.run(_inner())
    all_records = [record for records in result_lists for record in records]
    summary = summarize("qa", all_records)
    write_json(args.output_dir / "qa.summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False), file=sys.stderr)



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Patched OpenClaw evaluator for the LoCoMo/OpenViking benchmark")
    parser.add_argument("mode", choices=["ingest", "qa"], help="ingest sessions or ask QA questions")
    parser.add_argument("input", help="Path to LoCoMo JSON dataset")
    parser.add_argument("--output-dir", required=True, help="Directory for per-sample JSONL outputs")
    parser.add_argument("--base-url", default="http://127.0.0.1:18789", help="OpenClaw Gateway base URL")
    parser.add_argument("--token", required=True, help="OpenClaw Gateway bearer token")
    parser.add_argument("--group-id", required=True, help="Experiment group label such as g1/g2/g3/g4")
    parser.add_argument("--run-label", default="full", help="Run label, used in output paths and user IDs")
    parser.add_argument(
        "--user-template",
        default="{run_label}-{group_id}-{sample_id}",
        help="Python format string for the OpenClaw user key",
    )
    parser.add_argument("--sample", type=int, default=None, help="0-based sample index; omit for all samples")
    parser.add_argument("--sessions", default=None, help="Session range like 1-4 or 3")
    parser.add_argument("--tail", default="[]", help="Tail string appended after each bundled session")
    parser.add_argument("--count", type=int, default=None, help="Limit QA count for smoke tests")
    parser.add_argument("--parallel", type=int, default=1, help="QA concurrency across samples")
    parser.add_argument("--timeout", type=int, default=300, help="HTTP timeout seconds")
    parser.add_argument("--retries", type=int, default=2, help="HTTP retry count")
    return parser



def main() -> None:
    parser = build_parser()
    ns = parser.parse_args()
    args = EvalArgs(
        mode=ns.mode,
        input=Path(ns.input).expanduser(),
        output_dir=Path(ns.output_dir).expanduser(),
        base_url=ns.base_url,
        token=ns.token,
        group_id=ns.group_id,
        run_label=ns.run_label,
        user_template=ns.user_template,
        sample=ns.sample,
        sessions=parse_session_range(ns.sessions),
        tail=ns.tail,
        count=ns.count,
        parallel=ns.parallel,
        timeout=ns.timeout,
        retries=ns.retries,
    )
    if args.mode == "ingest":
        run_ingest(args)
    else:
        run_qa(args)


if __name__ == "__main__":
    main()
