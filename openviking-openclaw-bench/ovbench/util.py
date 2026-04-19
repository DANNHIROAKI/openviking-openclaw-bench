from __future__ import annotations

import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable, Mapping


def ensure_dir(path: str | Path) -> Path:
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p


def remove_tree(path: str | Path) -> None:
    p = Path(path).expanduser()
    if p.exists():
        shutil.rmtree(p)


def write_json(path: str | Path, data: object) -> None:
    p = Path(path).expanduser()
    ensure_dir(p.parent)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: str | Path) -> object:
    p = Path(path).expanduser()
    return json.loads(p.read_text(encoding="utf-8"))


def write_text(path: str | Path, text: str) -> None:
    p = Path(path).expanduser()
    ensure_dir(p.parent)
    p.write_text(text, encoding="utf-8")


def append_text(path: str | Path, text: str) -> None:
    p = Path(path).expanduser()
    ensure_dir(p.parent)
    with p.open("a", encoding="utf-8") as f:
        f.write(text)


def load_env_file(path: str | Path) -> dict[str, str]:
    p = Path(path).expanduser()
    if not p.exists():
        return {}
    env: dict[str, str] = {}
    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def write_env_file(path: str | Path, items: Mapping[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in items.items()]
    write_text(path, "\n".join(lines) + "\n")


def env_with_updates(base: Mapping[str, str] | None = None, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(base or os.environ)
    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return env


def generate_token() -> str:
    return secrets.token_hex(32)


class CommandError(RuntimeError):
    """Raised when a subprocess fails."""


class CommandResult:
    def __init__(self, completed: subprocess.CompletedProcess[str]):
        self.returncode = completed.returncode
        self.stdout = completed.stdout or ""
        self.stderr = completed.stderr or ""



def run_command(
    cmd: Iterable[str],
    *,
    env: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    check: bool = True,
    capture_output: bool = True,
    quiet: bool = False,
) -> CommandResult:
    cmd_list = [str(x) for x in cmd]
    if not quiet:
        print("$", " ".join(cmd_list), file=sys.stderr)
    completed = subprocess.run(
        cmd_list,
        cwd=str(Path(cwd).expanduser()) if cwd else None,
        env=dict(env or os.environ),
        text=True,
        capture_output=capture_output,
    )
    if check and completed.returncode != 0:
        raise CommandError(
            f"command failed ({completed.returncode}): {' '.join(cmd_list)}\n"
            f"stdout:\n{completed.stdout}\n"
            f"stderr:\n{completed.stderr}"
        )
    return CommandResult(completed)


def bash_pipe(script: str, *, env: Mapping[str, str] | None = None, cwd: str | Path | None = None) -> CommandResult:
    return run_command(["bash", "-lc", script], env=env, cwd=cwd)


def first_existing(paths: Iterable[str | Path]) -> Path | None:
    for path in paths:
        p = Path(path).expanduser()
        if p.exists():
            return p
    return None
