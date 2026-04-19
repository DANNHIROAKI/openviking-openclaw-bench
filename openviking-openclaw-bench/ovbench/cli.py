from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import sys
import time
from pathlib import Path
from typing import Any

from .config import BenchConfig, GroupSpec
from .eval import EvalArgs, parse_session_range, run_ingest, run_qa
from .http_api import send_response
from .judge import run as run_judge
from .merge_results import merge_run_dir
from .openclaw_ops import (
    apply_lancedb_workaround,
    config_set,
    configure_group_slots,
    configure_lancedb,
    configure_openviking,
    copy_best_effort_logs,
    ensure_group_layout,
    gateway_install,
    gateway_restart,
    gateway_start,
    gateway_stop,
    gateway_wait_healthy,
    install_openclaw,
    install_openviking_plugin,
    install_openviking_runtime,
    onboard_group,
    snapshot_runtime_config,
    verify_group,
)
from .report import render_markdown
from .util import ensure_dir, remove_tree, write_json, write_text


def gateway_base_url(group: GroupSpec) -> str:
    return f"http://127.0.0.1:{group.gateway_port}"


def group_gateway_token(group: GroupSpec) -> str:
    if not group.gateway_token_file.exists():
        raise RuntimeError(f"gateway token file missing: {group.gateway_token_file}")
    return group.gateway_token_file.read_text(encoding="utf-8").strip()


def setup_group(cfg: BenchConfig, group: GroupSpec, *, reset: bool) -> None:
    gateway_stop(cfg, group)
    ensure_group_layout(group, reset=reset)
    install_openclaw(cfg)
    if group.needs_openviking:
        install_openviking_runtime(cfg)
    onboard_group(cfg, group)

    if group.needs_openviking:
        install_openviking_plugin(cfg, group)
        configure_openviking(cfg, group)

    if group.memory_plugin == "memory-lancedb":
        workaround_info = apply_lancedb_workaround(cfg)
        write_json(group.logs_dir / "lancedb.workaround.json", workaround_info)
        configure_lancedb(cfg, group)
    else:
        configure_group_slots(cfg, group)

    gateway_install(cfg, group, force=True)
    try:
        gateway_start(cfg, group)
    except Exception:
        gateway_restart(cfg, group)

    verification = verify_group(cfg, group)
    write_json(group.logs_dir / "verify.json", verification)
    print(json.dumps(verification, indent=2, ensure_ascii=False))


def run_eval_step(
    *,
    mode: str,
    cfg: BenchConfig,
    group: GroupSpec,
    run_label: str,
    sample: int | None,
    sessions: str | None,
    count: int | None,
    parallel: int,
    tail: str,
) -> None:
    run_dir = group.outputs_dir / run_label
    ensure_dir(run_dir)
    args = EvalArgs(
        mode=mode,
        input=cfg.data_path,
        output_dir=run_dir,
        base_url=gateway_base_url(group),
        token=group_gateway_token(group),
        group_id=group.group_id,
        run_label=run_label,
        user_template="{run_label}-{group_id}-{sample_id}",
        sample=sample,
        sessions=parse_session_range(sessions),
        tail=tail,
        count=count,
        parallel=parallel,
        timeout=300,
        retries=2,
    )
    if mode == "ingest":
        run_ingest(args)
    else:
        run_qa(args)


def _iter_session_transcript_paths(group: GroupSpec) -> list[Path]:
    agents_root = group.state_dir / "agents"
    if not agents_root.exists():
        return []
    paths: list[Path] = []
    for path in agents_root.rglob("*.jsonl"):
        if "sessions" not in path.parts:
            continue
        if path.name == "sessions.json":
            continue
        paths.append(path)
    return sorted(set(paths))


def _session_snapshot(group: GroupSpec) -> dict[Path, tuple[int, int]]:
    snapshot: dict[Path, tuple[int, int]] = {}
    for path in _iter_session_transcript_paths(group):
        try:
            stat = path.stat()
            snapshot[path.resolve()] = (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            continue
    return snapshot


def _changed_paths(
    before: dict[Path, tuple[int, int]],
    after: dict[Path, tuple[int, int]],
) -> list[Path]:
    changed: list[Path] = []
    for path, meta in after.items():
        if before.get(path) != meta:
            changed.append(path)
    return changed


def _pick_latest_path(paths: list[Path], snapshot: dict[Path, tuple[int, int]]) -> Path | None:
    if not paths:
        return None
    return max(paths, key=lambda p: snapshot.get(p, (0, 0))[0])


def _wait_for_session_change(
    group: GroupSpec,
    before: dict[Path, tuple[int, int]],
    *,
    predicate: Any = None,
    timeout: float = 8.0,
    poll: float = 0.2,
) -> tuple[dict[Path, tuple[int, int]], list[Path]]:
    if predicate is None:
        predicate = lambda changed, after: bool(changed)

    deadline = time.monotonic() + timeout
    last_snapshot = before
    last_changed: list[Path] = []

    while time.monotonic() < deadline:
        after = _session_snapshot(group)
        changed = _changed_paths(before, after)
        if predicate(changed, after):
            return after, changed
        last_snapshot = after
        last_changed = changed
        time.sleep(poll)

    return last_snapshot, last_changed


def smoke_continuity(cfg: BenchConfig, group: GroupSpec, *, run_label: str = "smoke") -> dict[str, Any]:
    token = group_gateway_token(group)
    probe_tag = secrets.token_hex(4)
    unique = f"SMOKE_{secrets.token_hex(6)}"

    user_same = f"{run_label}-{group.group_id}-continuity-a-{probe_tag}"
    user_fresh = f"{run_label}-{group.group_id}-continuity-b-{probe_tag}"

    prompt1 = f"Remember this exact token: {unique}. Reply with ACK only."
    prompt2 = "What exact token did I ask you to remember? Reply with the token only."

    before0 = _session_snapshot(group)

    reply1, usage1, _ = send_response(
        base_url=gateway_base_url(group),
        token=token,
        user=user_same,
        message=prompt1,
    )
    after1, changed1 = _wait_for_session_change(group, before0)
    primary_session = _pick_latest_path(changed1, after1)

    reply2, usage2, _ = send_response(
        base_url=gateway_base_url(group),
        token=token,
        user=user_same,
        message=prompt2,
    )
    after2, changed2 = _wait_for_session_change(
        group,
        after1,
        predicate=lambda changed, after: (primary_session in changed) if primary_session else bool(changed),
    )
    same_user_session_reused = bool(primary_session and primary_session in changed2)

    reply3, usage3, _ = send_response(
        base_url=gateway_base_url(group),
        token=token,
        user=user_fresh,
        message=prompt2,
    )
    after3, changed3 = _wait_for_session_change(
        group,
        after2,
        predicate=lambda changed, after: any(path != primary_session for path in changed),
    )
    fresh_candidates = [path for path in changed3 if path != primary_session]
    fresh_session = _pick_latest_path(fresh_candidates, after3)
    fresh_user_new_session = fresh_session is not None

    passed = (unique in reply2) and same_user_session_reused and fresh_user_new_session

    payload = {
        "passed": passed,
        "probe_tag": probe_tag,
        "unique_token": unique,
        "same_user": user_same,
        "fresh_user": user_fresh,
        "step1_reply": reply1,
        "same_user_reply": reply2,
        "fresh_user_reply": reply3,
        "usage": {
            "step1": usage1,
            "step2": usage2,
            "step3": usage3,
        },
        "session_probe": {
            "sessions_dir": str(group.state_dir / "agents"),
            "primary_session_transcript": str(primary_session) if primary_session else None,
            "fresh_session_transcript": str(fresh_session) if fresh_session else None,
            "step1_changed_paths": [str(p) for p in changed1],
            "step2_changed_paths": [str(p) for p in changed2],
            "step3_changed_paths": [str(p) for p in changed3],
            "same_user_session_reused": same_user_session_reused,
            "fresh_user_new_session": fresh_user_new_session,
        },
    }

    run_dir = group.outputs_dir / run_label
    ensure_dir(run_dir)
    write_json(run_dir / "smoke.continuity.json", payload)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def run_group(
    cfg: BenchConfig,
    group: GroupSpec,
    *,
    run_label: str,
    sample: int | None,
    sessions: str | None,
    qa_count: int | None,
    parallel: int,
    tail: str,
    judge: bool,
    judge_concurrency: int,
) -> None:
    cfg.require_dataset()
    run_dir = group.outputs_dir / run_label
    if run_dir.exists():
        remove_tree(run_dir)
    ensure_dir(run_dir)
    gateway_restart(cfg, group)
    snapshot_runtime_config(cfg, group, run_dir)
    run_eval_step(
        mode="ingest",
        cfg=cfg,
        group=group,
        run_label=run_label,
        sample=sample,
        sessions=sessions,
        count=None,
        parallel=1,
        tail=tail,
    )
    run_eval_step(
        mode="qa",
        cfg=cfg,
        group=group,
        run_label=run_label,
        sample=sample,
        sessions=None,
        count=qa_count,
        parallel=parallel,
        tail=tail,
    )
    merge_run_dir(run_dir)
    if judge:
        asyncio.run(
            run_judge(
                input_path=run_dir / "answers.all.jsonl",
                output_path=run_dir / "judge.json",
                base_url=cfg.judge_model.base_url,
                token=cfg.judge_model.api_key(),
                model=cfg.judge_model.identifier(),
                max_concurrency=judge_concurrency,
            )
        )
    copy_best_effort_logs(cfg, group, run_dir)


def run_all(
    cfg: BenchConfig,
    *,
    groups: list[str],
    run_label: str,
    judge: bool,
    judge_concurrency: int,
) -> None:
    for group_id in groups:
        print(f"\n===== running {group_id} =====", file=sys.stderr)
        run_group(
            cfg,
            cfg.get_group(group_id),
            run_label=run_label,
            sample=None,
            sessions=None,
            qa_count=None,
            parallel=1,
            tail="[]",
            judge=judge,
            judge_concurrency=judge_concurrency,
        )


def judge_group(cfg: BenchConfig, group: GroupSpec, *, run_label: str, judge_concurrency: int) -> None:
    run_dir = group.outputs_dir / run_label
    asyncio.run(
        run_judge(
            input_path=run_dir / "answers.all.jsonl",
            output_path=run_dir / "judge.json",
            base_url=cfg.judge_model.base_url,
            token=cfg.judge_model.api_key(),
            model=cfg.judge_model.identifier(),
            max_concurrency=judge_concurrency,
        )
    )


def build_final_report(
    cfg: BenchConfig,
    *,
    groups: list[str],
    run_label: str,
    output_md: Path | None,
    output_json: Path | None,
) -> None:
    rows: list[dict[str, Any]] = []
    for group_id in groups:
        group = cfg.get_group(group_id)
        run_dir = group.outputs_dir / run_label
        judge_path = run_dir / "judge.json"
        usage_path = run_dir / "usage.json"
        judge = json.loads(judge_path.read_text(encoding="utf-8")) if judge_path.exists() else {}
        usage = json.loads(usage_path.read_text(encoding="utf-8")) if usage_path.exists() else {}
        rows.append(
            {
                "group": group_id,
                "completion_rate": float(judge.get("score", 0.0)),
                "correct": int(judge.get("correct", 0)),
                "total": int(judge.get("total", 0)),
                "qa_input_tokens_total": int(usage.get("qa_only", {}).get("input_tokens", 0)),
                "full_input_tokens_total": int(usage.get("full_pipeline", {}).get("input_tokens", 0)),
                "notes": group.notes,
            }
        )
    markdown = render_markdown(rows)
    print(markdown)
    if output_md:
        write_text(output_md, markdown)
    if output_json:
        write_json(output_json, {"rows": rows})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="OpenViking/OpenClaw benchmark controller")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_install = sub.add_parser("install-tools", help="Install shared OpenClaw CLI and OpenViking runtime")
    p_install.add_argument("--config", required=True)

    p_setup = sub.add_parser("setup-group", help="Create and configure one experiment group")
    p_setup.add_argument("--config", required=True)
    p_setup.add_argument("--group", required=True)
    p_setup.add_argument("--reset", action="store_true")

    p_verify = sub.add_parser("verify-group", help="Print effective slots and plugin state")
    p_verify.add_argument("--config", required=True)
    p_verify.add_argument("--group", required=True)

    p_smoke_c = sub.add_parser("smoke-continuity", help="Run same-user / fresh-user continuity check")
    p_smoke_c.add_argument("--config", required=True)
    p_smoke_c.add_argument("--group", required=True)
    p_smoke_c.add_argument("--run-label", default="smoke")

    p_smoke_s = sub.add_parser("smoke-sample", help="Run one-sample smoke: ingest + QA + optional judge")
    p_smoke_s.add_argument("--config", required=True)
    p_smoke_s.add_argument("--group", required=True)
    p_smoke_s.add_argument("--sample", type=int, default=0)
    p_smoke_s.add_argument("--sessions", default="1-2")
    p_smoke_s.add_argument("--qa-count", type=int, default=5)
    p_smoke_s.add_argument("--run-label", default="smoke")
    p_smoke_s.add_argument("--judge", action="store_true")

    p_run = sub.add_parser("run-group", help="Run a full group benchmark")
    p_run.add_argument("--config", required=True)
    p_run.add_argument("--group", required=True)
    p_run.add_argument("--run-label", default="full")
    p_run.add_argument("--sample", type=int, default=None)
    p_run.add_argument("--sessions", default=None)
    p_run.add_argument("--qa-count", type=int, default=None)
    p_run.add_argument("--parallel", type=int, default=1)
    p_run.add_argument("--tail", default="[]")
    p_run.add_argument("--judge", action="store_true")
    p_run.add_argument("--judge-concurrency", type=int, default=20)

    p_run_all = sub.add_parser("run-all", help="Run multiple groups sequentially")
    p_run_all.add_argument("--config", required=True)
    p_run_all.add_argument("--groups", nargs="*", default=None)
    p_run_all.add_argument("--run-label", default="full")
    p_run_all.add_argument("--judge", action="store_true")
    p_run_all.add_argument("--judge-concurrency", type=int, default=20)

    p_merge = sub.add_parser("merge-group", help="Rebuild usage.json + merged JSONL for one group run dir")
    p_merge.add_argument("--config", required=True)
    p_merge.add_argument("--group", required=True)
    p_merge.add_argument("--run-label", default="full")

    p_judge = sub.add_parser("judge-group", help="Run judge for one group after answers.all.jsonl exists")
    p_judge.add_argument("--config", required=True)
    p_judge.add_argument("--group", required=True)
    p_judge.add_argument("--run-label", default="full")
    p_judge.add_argument("--judge-concurrency", type=int, default=20)

    p_report = sub.add_parser("report", help="Build final Markdown/JSON report")
    p_report.add_argument("--config", required=True)
    p_report.add_argument("--groups", nargs="*", default=None)
    p_report.add_argument("--run-label", default="full")
    p_report.add_argument("--output-md", default=None)
    p_report.add_argument("--output-json", default=None)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    cfg = BenchConfig.load(args.config)

    if args.cmd == "install-tools":
        install_openclaw(cfg)
        install_openviking_runtime(cfg)
        return

    if args.cmd == "run-all":
        group_ids = args.groups or list(cfg.groups)
        run_all(
            cfg,
            groups=group_ids,
            run_label=args.run_label,
            judge=args.judge,
            judge_concurrency=args.judge_concurrency,
        )
        return

    if args.cmd == "report":
        group_ids = args.groups or list(cfg.groups)
        build_final_report(
            cfg,
            groups=group_ids,
            run_label=args.run_label,
            output_md=Path(args.output_md).expanduser() if args.output_md else None,
            output_json=Path(args.output_json).expanduser() if args.output_json else None,
        )
        return

    group = cfg.get_group(args.group)

    if args.cmd == "setup-group":
        setup_group(cfg, group, reset=args.reset)
    elif args.cmd == "verify-group":
        print(json.dumps(verify_group(cfg, group), indent=2, ensure_ascii=False))
    elif args.cmd == "smoke-continuity":
        smoke_continuity(cfg, group, run_label=args.run_label)
    elif args.cmd == "smoke-sample":
        run_group(
            cfg,
            group,
            run_label=args.run_label,
            sample=args.sample,
            sessions=args.sessions,
            qa_count=args.qa_count,
            parallel=1,
            tail="[]",
            judge=args.judge,
            judge_concurrency=20,
        )
    elif args.cmd == "run-group":
        run_group(
            cfg,
            group,
            run_label=args.run_label,
            sample=args.sample,
            sessions=args.sessions,
            qa_count=args.qa_count,
            parallel=args.parallel,
            tail=args.tail,
            judge=args.judge,
            judge_concurrency=args.judge_concurrency,
        )
    elif args.cmd == "merge-group":
        run_dir = group.outputs_dir / args.run_label
        print(json.dumps(merge_run_dir(run_dir), indent=2, ensure_ascii=False))
    elif args.cmd == "judge-group":
        judge_group(cfg, group, run_label=args.run_label, judge_concurrency=args.judge_concurrency)
    else:
        raise SystemExit(f"unknown command: {args.cmd}")


if __name__ == "__main__":
    main()