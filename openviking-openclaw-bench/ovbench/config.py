from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ModelSpec:
    base_url: str
    api_key_env: str
    model_id: str | None = None
    model_name: str | None = None
    endpoint_id: str | None = None
    provider_id: str | None = None
    compatibility: str = "openai"
    provider: str | None = None
    lancedb_provider: str | None = None
    multimodal_url: str | None = None
    prefer_model_name: bool = True

    def api_key(self) -> str:
        value = os.environ.get(self.api_key_env, "")
        if not value:
            raise RuntimeError(
                f"missing API key env var {self.api_key_env!r}; export it before running bench commands"
            )
        return value

    def identifier(self) -> str:
        if self.model_id:
            return self.model_id
        if self.prefer_model_name and self.model_name:
            return self.model_name
        if self.endpoint_id:
            return self.endpoint_id
        if self.model_name:
            return self.model_name
        raise RuntimeError("model spec has no usable identifier")

    def embedding_identifier(self) -> str:
        if self.prefer_model_name and self.model_name:
            return self.model_name
        if self.endpoint_id:
            return self.endpoint_id
        if self.model_name:
            return self.model_name
        raise RuntimeError("embedding spec has no usable model_name or endpoint_id")

    def embedding_url(self) -> str:
        return self.multimodal_url or f"{self.base_url.rstrip('/')}/embeddings/multimodal"


@dataclass
class GroupSpec:
    group_id: str
    context_engine: str
    memory_plugin: str
    gateway_port: int
    bench_root: Path
    openviking_port: int | None = None
    profile: str | None = None
    notes: str = ""

    @property
    def base_dir(self) -> Path:
        return self.bench_root / self.group_id

    @property
    def state_dir(self) -> Path:
        return self.base_dir / "state"

    @property
    def config_path(self) -> Path:
        return self.state_dir / "openclaw.json"

    @property
    def workspace(self) -> Path:
        return self.base_dir / "workspace"

    @property
    def logs_dir(self) -> Path:
        return self.base_dir / "logs"

    @property
    def outputs_dir(self) -> Path:
        return self.base_dir / "outputs"

    @property
    def openviking_home(self) -> Path:
        return self.base_dir / "openviking"

    @property
    def gateway_token_file(self) -> Path:
        return self.state_dir / "gateway.token"

    @property
    def gateway_env_file(self) -> Path:
        return self.state_dir / "gateway.env"

    @property
    def openviking_env_file(self) -> Path:
        return self.state_dir / "openviking.env"

    @property
    def needs_openviking(self) -> bool:
        return self.context_engine == "openviking"

    @property
    def run_dir_default(self) -> Path:
        return self.outputs_dir / "full"


@dataclass
class BenchConfig:
    source_path: Path
    bench_root: Path
    data_path: Path
    openclaw_version: str
    openclaw_prefix: Path
    openclaw_install_script: str
    openviking_version: str
    openviking_runtime_dir: Path
    openviking_plugin_source: Path | None
    front_model: ModelSpec
    judge_model: ModelSpec
    embedding_model: ModelSpec
    ov_vlm_model: ModelSpec
    groups: dict[str, GroupSpec] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> "BenchConfig":
        src = Path(path).expanduser()
        raw = json.loads(src.read_text(encoding="utf-8"))
        bench_root = Path(raw.get("bench_root", "~/ov-bench")).expanduser()
        openclaw = raw.get("openclaw", {})
        openviking = raw.get("openviking", {})
        models = raw.get("models", {})

        front = ModelSpec(**models["front"])
        judge = ModelSpec(**models["judge"])
        embedding = ModelSpec(**models["embedding"])
        ov_vlm = ModelSpec(**models["ov_vlm"])

        cfg = cls(
            source_path=src,
            bench_root=bench_root,
            data_path=Path(raw["dataset"]["path"]).expanduser(),
            openclaw_version=str(openclaw.get("version", "2026.4.14")),
            openclaw_prefix=Path(openclaw.get("prefix", str(bench_root / "tools" / "openclaw"))).expanduser(),
            openclaw_install_script=str(openclaw.get("install_script_url", "https://openclaw.ai/install-cli.sh")),
            openviking_version=str(openviking.get("version", "0.3.8")),
            openviking_runtime_dir=Path(openviking.get("runtime_dir", str(bench_root / "tools" / "openviking-runtime"))).expanduser(),
            openviking_plugin_source=(
                Path(openviking["plugin_source"]).expanduser() if openviking.get("plugin_source") else None
            ),
            front_model=front,
            judge_model=judge,
            embedding_model=embedding,
            ov_vlm_model=ov_vlm,
        )

        default_groups: dict[str, Any] = {
            "g1": {
                "context_engine": "legacy",
                "memory_plugin": "memory-core",
                "gateway_port": 18791,
                "notes": "OpenClaw(memory-core)",
            },
            "g2": {
                "context_engine": "legacy",
                "memory_plugin": "memory-lancedb",
                "gateway_port": 18792,
                "notes": "OpenClaw + LanceDB (-memory-core)",
            },
            "g3": {
                "context_engine": "openviking",
                "memory_plugin": "none",
                "gateway_port": 18793,
                "openviking_port": 19333,
                "notes": "OpenClaw + OpenViking Plugin (-memory-core)",
            },
            "g4": {
                "context_engine": "openviking",
                "memory_plugin": "memory-core",
                "gateway_port": 18794,
                "openviking_port": 19334,
                "notes": "OpenClaw + OpenViking Plugin (+memory-core)",
            },
        }
        group_data = raw.get("groups", default_groups)
        if not group_data:
            group_data = default_groups

        for group_id, item in group_data.items():
            merged = dict(default_groups.get(group_id, {}))
            merged.update(item)
            cfg.groups[group_id] = GroupSpec(
                group_id=group_id,
                context_engine=merged["context_engine"],
                memory_plugin=merged["memory_plugin"],
                gateway_port=int(merged["gateway_port"]),
                openviking_port=(int(merged["openviking_port"]) if merged.get("openviking_port") is not None else None),
                bench_root=bench_root,
                profile=str(merged.get("profile", group_id)),
                notes=str(merged.get("notes", "")),
            )
        return cfg

    def get_group(self, group_id: str) -> GroupSpec:
        try:
            return self.groups[group_id]
        except KeyError as exc:
            known = ", ".join(sorted(self.groups))
            raise RuntimeError(f"unknown group {group_id!r}; choose one of: {known}") from exc

    def openclaw_bin(self) -> Path:
        return self.openclaw_prefix / "bin" / "openclaw"

    def openviking_python(self) -> Path:
        return self.openviking_runtime_dir / ".venv" / "bin" / "python"

    def require_dataset(self) -> None:
        if not self.data_path.exists():
            raise RuntimeError(f"dataset not found: {self.data_path}")

    def require_plugin_source(self) -> Path:
        if not self.openviking_plugin_source:
            raise RuntimeError(
                "openviking.plugin_source is required for g3/g4 setup; point it to your local plugin directory"
            )
        if not self.openviking_plugin_source.exists():
            raise RuntimeError(f"OpenViking plugin source not found: {self.openviking_plugin_source}")
        return self.openviking_plugin_source
