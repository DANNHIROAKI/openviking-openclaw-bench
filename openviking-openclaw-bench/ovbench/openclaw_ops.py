from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Mapping

from .config import BenchConfig, GroupSpec
from .util import (
    CommandError,
    bash_pipe,
    ensure_dir,
    env_with_updates,
    first_existing,
    generate_token,
    load_env_file,
    remove_tree,
    run_command,
    write_env_file,
    write_json,
)



def openclaw_cmd(cfg: BenchConfig, group: GroupSpec, *args: object) -> list[str]:
    cmd = [str(cfg.openclaw_bin())]
    if group.profile:
        cmd.extend(["--profile", group.profile])
    cmd.extend([str(a) for a in args])
    return cmd


def group_state_env_file(group: GroupSpec) -> Path:
    return group.state_dir / ".env"


def write_group_runtime_env(cfg: BenchConfig, group: GroupSpec, *, token: str) -> None:
    api_key = cfg.front_model.api_key()
    state_env: dict[str, str] = {
        "OPENCLAW_GATEWAY_TOKEN": token,
        # OpenClaw stores custom provider refs under CUSTOM_API_KEY in non-interactive ref mode.
        "CUSTOM_API_KEY": api_key,
        # Keep the caller's preferred env name available too for CLI diagnostics and parity.
        cfg.front_model.api_key_env: api_key,
    }
    write_env_file(group_state_env_file(group), state_env)
    gateway_env = {"OPENCLAW_GATEWAY_TOKEN": token, "CUSTOM_API_KEY": api_key, cfg.front_model.api_key_env: api_key}
    write_env_file(group.gateway_env_file, gateway_env)


def group_env(cfg: BenchConfig, group: GroupSpec, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict()
    env.update(env_with_updates())
    env["PATH"] = f"{cfg.openclaw_prefix / 'bin'}:{env.get('PATH', '')}"
    env["OPENCLAW_STATE_DIR"] = str(group.state_dir)
    env["OPENCLAW_CONFIG_PATH"] = str(group.config_path)
    env["OPENCLAW_HOME"] = str(group.state_dir)
    if group.profile:
        env["OPENCLAW_PROFILE"] = group.profile
    state_env = group_state_env_file(group)
    if state_env.exists():
        env.update(load_env_file(state_env))
    if group.gateway_env_file.exists():
        env.update(load_env_file(group.gateway_env_file))
    if group.openviking_env_file.exists():
        env.update(load_env_file(group.openviking_env_file))
    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return env


def ensure_group_layout(group: GroupSpec, *, reset: bool = False) -> None:
    if reset:
        remove_tree(group.base_dir)
    ensure_dir(group.state_dir)
    ensure_dir(group.workspace)
    ensure_dir(group.logs_dir)
    ensure_dir(group.outputs_dir)
    if group.needs_openviking:
        ensure_dir(group.openviking_home)


def write_gateway_token(group: GroupSpec) -> str:
    if group.gateway_token_file.exists():
        token = group.gateway_token_file.read_text(encoding="utf-8").strip()
    else:
        token = generate_token()
        group.gateway_token_file.write_text(token + "\n", encoding="utf-8")
    return token


def install_openclaw(cfg: BenchConfig) -> None:
    openclaw_bin = cfg.openclaw_bin()
    if openclaw_bin.exists():
        return
    ensure_dir(cfg.openclaw_prefix)
    script = (
        f"curl -fsSL --proto '=https' --tlsv1.2 {cfg.openclaw_install_script} | "
        f"bash -s -- --prefix '{cfg.openclaw_prefix}' --version {cfg.openclaw_version}"
    )
    bash_pipe(script)



def install_openviking_runtime(cfg: BenchConfig) -> None:
    python_bin = cfg.openviking_python()
    if python_bin.exists():
        return
    ensure_dir(cfg.openviking_runtime_dir)
    run_command(["python3", "-m", "venv", str(cfg.openviking_runtime_dir / ".venv")])
    run_command([str(python_bin), "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"])
    run_command([str(python_bin), "-m", "pip", "install", f"openviking=={cfg.openviking_version}"])

def ensure_workspace_templates(cfg: BenchConfig) -> None:
    root = openclaw_package_root(cfg)
    src = root / "docs" / "reference" / "templates"
    dst = root / "dist" / "docs" / "reference" / "templates"

    if not src.exists():
        raise RuntimeError(
            f"openclaw templates source missing: {src}. "
            "Cannot patch dist/docs/reference/templates."
        )

    src_files = [p for p in src.iterdir() if p.is_file()]
    if not src_files:
        raise RuntimeError(f"openclaw templates source is empty: {src}")

    ensure_dir(dst)

    missing = [p.name for p in src_files if not (dst / p.name).exists()]
    if not missing:
        return

    for p in src_files:
        shutil.copy2(p, dst / p.name)

def onboard_group(cfg: BenchConfig, group: GroupSpec) -> None:
    token = write_gateway_token(group)
    ensure_group_layout(group)
    write_group_runtime_env(cfg, group, token=token)
    api_key = cfg.front_model.api_key()
    env = group_env(
        cfg,
        group,
        {
            "CUSTOM_API_KEY": api_key,
            "OPENCLAW_GATEWAY_TOKEN": token,
        },
    )

    if not group.config_path.exists():
        run_command(
            openclaw_cmd(
                cfg,
                group,
                "onboard",
                "--non-interactive",
                "--mode",
                "local",
                "--auth-choice",
                "custom-api-key",
                "--custom-base-url",
                cfg.front_model.base_url,
                "--custom-model-id",
                cfg.front_model.identifier(),
                "--custom-provider-id",
                cfg.front_model.provider_id or "ark-custom",
                "--custom-compatibility",
                cfg.front_model.compatibility,
                "--secret-input-mode",
                "ref",
                "--gateway-auth",
                "token",
                "--gateway-token-ref-env",
                "OPENCLAW_GATEWAY_TOKEN",
                "--gateway-port",
                str(group.gateway_port),
                "--skip-channels",
                "--skip-skills",
                "--skip-search",
                "--skip-ui",
                "--skip-health",
                "--accept-risk",
            ),
            env=env,
        )
    run_command(openclaw_cmd(cfg, group, "config", "set", "agents.defaults.workspace", str(group.workspace)), env=env)
    run_command(openclaw_cmd(cfg, group, "setup", "--workspace", str(group.workspace)), env=env)
    # Always enable the HTTP API endpoints used by the evaluator.
    config_set(cfg, group, "gateway.http.endpoints.responses.enabled", True)
    config_set(cfg, group, "gateway.http.endpoints.chatCompletions.enabled", True)



def config_set(cfg: BenchConfig, group: GroupSpec, path: str, value: Any) -> None:
    env = group_env(cfg, group)
    if isinstance(value, bool):
        run_command(openclaw_cmd(cfg, group, "config", "set", path, json.dumps(value), "--strict-json"), env=env)
    elif isinstance(value, (int, float)):
        run_command(openclaw_cmd(cfg, group, "config", "set", path, str(value), "--strict-json"), env=env)
    elif isinstance(value, (list, dict)):
        run_command(openclaw_cmd(cfg, group, "config", "set", path, json.dumps(value), "--strict-json"), env=env)
    else:
        run_command(openclaw_cmd(cfg, group, "config", "set", path, str(value)), env=env)



def gateway_install(cfg: BenchConfig, group: GroupSpec, *, force: bool = False) -> None:
    cmd = openclaw_cmd(cfg, group, "gateway", "install", "--port", str(group.gateway_port))
    if force:
        cmd.append("--force")
    run_command(cmd, env=group_env(cfg, group))



def gateway_restart(cfg: BenchConfig, group: GroupSpec) -> None:
    run_command(openclaw_cmd(cfg, group, "gateway", "restart"), env=group_env(cfg, group))



def gateway_start(cfg: BenchConfig, group: GroupSpec) -> None:
    run_command(openclaw_cmd(cfg, group, "gateway", "start"), env=group_env(cfg, group))



def gateway_stop(cfg: BenchConfig, group: GroupSpec) -> None:
    run_command(openclaw_cmd(cfg, group, "gateway", "stop"), env=group_env(cfg, group), check=False)



def snapshot_runtime_config(cfg: BenchConfig, group: GroupSpec, dst_dir: Path) -> None:
    ensure_dir(dst_dir)
    if group.config_path.exists():
        shutil.copy2(group.config_path, dst_dir / "config.snapshot.json")
    if group.needs_openviking:
        ov_conf = group.openviking_home / "ov.conf"
        if ov_conf.exists():
            shutil.copy2(ov_conf, dst_dir / "ov.conf.snapshot.json")



def openclaw_package_root(cfg: BenchConfig) -> Path:
    candidates = [
        cfg.openclaw_prefix / "lib" / "node_modules" / "openclaw",
        cfg.openclaw_prefix / "node_modules" / "openclaw",
    ]
    root = first_existing(candidates)
    if not root:
        raise RuntimeError(f"could not locate openclaw package root under {cfg.openclaw_prefix}")
    return root



def apply_lancedb_workaround(cfg: BenchConfig) -> dict[str, str]:
    package_root = openclaw_package_root(cfg)
    extension_dir = first_existing(
        [
            package_root / "dist" / "extensions" / "memory-lancedb",
            package_root / "extensions" / "memory-lancedb",
        ]
    )
    if not extension_dir:
        raise RuntimeError("could not locate memory-lancedb extension directory")
    dist_package = package_root / "dist" / "package.json"
    if not dist_package.exists():
        ensure_dir(dist_package.parent)
        write_json(
            dist_package,
            {
                "name": "openclaw",
                "version": cfg.openclaw_version,
                "dependencies": {"@lancedb/lancedb": "*"},
            },
        )
    run_command(["npm", "install", "@lancedb/lancedb"], cwd=extension_dir)
    return {
        "package_root": str(package_root),
        "extension_dir": str(extension_dir),
        "dist_package": str(dist_package),
    }



def configure_group_slots(cfg: BenchConfig, group: GroupSpec) -> None:
    config_set(cfg, group, "plugins.slots.contextEngine", group.context_engine)
    config_set(cfg, group, "plugins.slots.memory", group.memory_plugin)



def configure_lancedb(cfg: BenchConfig, group: GroupSpec) -> None:
    api_key = cfg.embedding_model.api_key()
    emb = cfg.embedding_model
    config_set(cfg, group, "plugins.entries.memory-lancedb.enabled", True)
    config_set(
        cfg,
        group,
        "plugins.entries.memory-lancedb.config.embedding",
        {
            "apiKey": api_key,
            "model": emb.embedding_identifier(),
            "provider": emb.lancedb_provider or "doubao",
            "url": emb.embedding_url(),
        },
    )
    config_set(cfg, group, "plugins.entries.memory-lancedb.config.autoCapture", True)
    config_set(cfg, group, "plugins.entries.memory-lancedb.config.autoRecall", True)
    configure_group_slots(cfg, group)
    run_command(openclaw_cmd(cfg, group, "plugins", "enable", "memory-lancedb"), env=group_env(cfg, group))



def write_openviking_files(cfg: BenchConfig, group: GroupSpec) -> Path:
    if not group.needs_openviking:
        raise RuntimeError(f"group {group.group_id} does not use OpenViking")
    api_key = cfg.ov_vlm_model.api_key()
    embedding_api_key = cfg.embedding_model.api_key()
    ov_conf = group.openviking_home / "ov.conf"
    write_json(
        ov_conf,
        {
            "server": {"port": group.openviking_port},
            "storage": {"workspace": str(group.openviking_home)},
            "embedding": {
                "dense": {
                    "api_base": cfg.embedding_model.base_url,
                    "api_key": embedding_api_key,
                    "provider": cfg.embedding_model.provider or "volcengine",
                    "dimension": 1024,
                    "model": cfg.embedding_model.embedding_identifier(),
                    "input": "multimodal",
                }
            },
            "vlm": {
                "api_base": cfg.ov_vlm_model.base_url,
                "api_key": api_key,
                "provider": cfg.ov_vlm_model.provider or "volcengine",
                "max_retries": 2,
                "model": cfg.ov_vlm_model.identifier(),
            },
        },
    )
    write_env_file(
        group.openviking_env_file,
        {
            "OPENVIKING_PYTHON": str(cfg.openviking_python()),
            "OPENVIKING_CONFIG_FILE": str(ov_conf),
        },
    )
    return ov_conf



def install_openviking_plugin(cfg: BenchConfig, group: GroupSpec) -> None:
    plugin_source = cfg.require_plugin_source()
    env = group_env(cfg, group)
    run_command(
        openclaw_cmd(
            cfg,
            group,
            "plugins",
            "install",
            str(plugin_source),
            "--force",
            "--dangerously-force-unsafe-install",
        ),
        env=env,
    )
    run_command(openclaw_cmd(cfg, group, "plugins", "enable", "openviking"), env=env)



def configure_openviking(cfg: BenchConfig, group: GroupSpec) -> None:
    if not group.openviking_port:
        raise RuntimeError(f"group {group.group_id} needs openviking_port")
    ov_conf = write_openviking_files(cfg, group)
    config_set(cfg, group, "plugins.entries.openviking.enabled", True)
    config_set(cfg, group, "plugins.entries.openviking.config.mode", "local")
    config_set(cfg, group, "plugins.entries.openviking.config.configPath", str(ov_conf))
    config_set(cfg, group, "plugins.entries.openviking.config.port", group.openviking_port)
    config_set(cfg, group, "plugins.entries.openviking.config.agentId", "default")
    config_set(cfg, group, "plugins.entries.openviking.config.autoCapture", True)
    config_set(cfg, group, "plugins.entries.openviking.config.autoRecall", True)
    config_set(cfg, group, "plugins.entries.openviking.config.emitStandardDiagnostics", True)
    config_set(cfg, group, "plugins.entries.openviking.config.logFindRequests", True)
    configure_group_slots(cfg, group)



def disable_openviking(cfg: BenchConfig, group: GroupSpec) -> None:
    config_set(cfg, group, "plugins.entries.openviking.enabled", False)



def verify_group(cfg: BenchConfig, group: GroupSpec) -> dict[str, str]:
    env = group_env(cfg, group)
    checks: dict[str, str] = {}
    checks["context_engine"] = run_command(
        openclaw_cmd(cfg, group, "config", "get", "plugins.slots.contextEngine"), env=env
    ).stdout.strip()
    checks["memory_plugin"] = run_command(
        openclaw_cmd(cfg, group, "config", "get", "plugins.slots.memory"), env=env
    ).stdout.strip()
    checks["plugins_list"] = run_command(openclaw_cmd(cfg, group, "plugins", "list"), env=env).stdout
    if group.needs_openviking:
        checks["plugin_inspect"] = run_command(
            openclaw_cmd(cfg, group, "plugins", "inspect", "openviking"), env=env, check=False
        ).stdout
    elif group.memory_plugin == "memory-lancedb":
        checks["plugin_inspect"] = run_command(
            openclaw_cmd(cfg, group, "plugins", "inspect", "memory-lancedb"), env=env, check=False
        ).stdout
    return checks



def copy_best_effort_logs(cfg: BenchConfig, group: GroupSpec, dst_dir: Path) -> None:
    ensure_dir(dst_dir)
    # Try the CLI first.
    try:
        result = run_command(openclaw_cmd(cfg, group, "logs"), env=group_env(cfg, group), check=False)
        if result.stdout.strip() or result.stderr.strip():
            (dst_dir / "openclaw.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    except CommandError:
        pass

    if group.needs_openviking:
        candidates = [
            group.openviking_home / "data" / "log" / "openviking.log",
            group.openviking_home / "log" / "openviking.log",
        ]
        existing = first_existing(candidates)
        if existing:
            shutil.copy2(existing, dst_dir / "openviking.log")
