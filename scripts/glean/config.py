"""Config loading for glean. Frozen dataclass, loaded from ${CLAUDE_PLUGIN_DATA}/config.json."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Optional


DEFAULTS = {
    "schema_version": 1,
    "output_mode": "obsidian",
    "vault_path": "",
    "vault_folder": "Fragments",
    "output_dir": "",
    "extraction_model": "haiku",
    "prompt_path": None,
    "prompt_version": 1,
    "min_text_bytes": 2048,
    "max_text_bytes": 819200,
    "max_fragments_per_session": 3,
    "retry_limit": 3,
    "notification_enabled": True,
}


@dataclass(frozen=True)
class Config:
    schema_version: int = 1
    output_mode: str = "obsidian"
    vault_path: str = ""
    vault_folder: str = "Fragments"
    output_dir: str = ""
    extraction_model: str = "haiku"
    prompt_path: Optional[str] = None
    prompt_version: int = 1
    min_text_bytes: int = 2048
    max_text_bytes: int = 819200
    max_fragments_per_session: int = 3
    retry_limit: int = 3
    notification_enabled: bool = True

    # Derived runtime paths (populated at load time)
    plugin_root: str = ""
    plugin_data: str = ""

    @property
    def queue_dir(self) -> Path:
        return Path(self.plugin_data) / "queue"

    @property
    def delivered_dir(self) -> Path:
        return Path(self.plugin_data) / "delivered"

    @property
    def outbox_dir(self) -> Path:
        return Path(self.plugin_data) / "outbox"

    @property
    def hashes_path(self) -> Path:
        return Path(self.plugin_data) / "hashes.jsonl"

    @property
    def feedback_path(self) -> Path:
        return Path(self.plugin_data) / "feedback.jsonl"

    @property
    def worker_log_path(self) -> Path:
        return Path(self.plugin_data) / "worker.log"

    @property
    def worker_lock_path(self) -> Path:
        return Path(self.plugin_data) / "worker.lock"


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, default)
    return os.path.expanduser(value) if value else default


def _coerce(key: str, value):
    """Coerce values from config.json / env vars to proper types."""
    int_keys = {
        "schema_version", "prompt_version", "min_text_bytes",
        "max_text_bytes", "max_fragments_per_session", "retry_limit",
    }
    bool_keys = {"notification_enabled"}
    if key in int_keys:
        try:
            return int(value)
        except (TypeError, ValueError):
            return DEFAULTS.get(key, 0)
    if key in bool_keys:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)
    return value


def load_config(
    plugin_data: Optional[str] = None,
    plugin_root: Optional[str] = None,
) -> Config:
    """Load config from ${CLAUDE_PLUGIN_DATA}/config.json with env var overrides."""
    plugin_data = plugin_data or _env("CLAUDE_PLUGIN_DATA")
    plugin_root = plugin_root or _env("CLAUDE_PLUGIN_ROOT")

    if not plugin_data:
        # Fallback used only for import testing
        plugin_data = os.path.expanduser("~/.claude/plugins/glean/data")

    merged = dict(DEFAULTS)

    config_path = Path(plugin_data) / "config.json"
    if config_path.is_file():
        try:
            with config_path.open("r", encoding="utf-8") as handle:
                user_cfg = json.load(handle)
            if isinstance(user_cfg, dict):
                for key, value in user_cfg.items():
                    if key in merged:
                        merged[key] = _coerce(key, value)
        except (OSError, json.JSONDecodeError):
            pass

    # Env var overrides (GLEAN_*)
    env_map = {
        "GLEAN_OUTPUT_MODE": "output_mode",
        "GLEAN_VAULT_PATH": "vault_path",
        "GLEAN_VAULT_FOLDER": "vault_folder",
        "GLEAN_OUTPUT_DIR": "output_dir",
        "GLEAN_EXTRACTION_MODEL": "extraction_model",
        "GLEAN_PROMPT_PATH": "prompt_path",
        "GLEAN_PROMPT_VERSION": "prompt_version",
        "GLEAN_MIN_TEXT_BYTES": "min_text_bytes",
        "GLEAN_MAX_TEXT_BYTES": "max_text_bytes",
        "GLEAN_MAX_FRAGMENTS": "max_fragments_per_session",
        "GLEAN_RETRY_LIMIT": "retry_limit",
        "GLEAN_NOTIFICATION_ENABLED": "notification_enabled",
    }
    for env_name, key in env_map.items():
        if env_name in os.environ:
            merged[key] = _coerce(key, os.environ[env_name])

    # Expand ~
    for path_key in ("vault_path", "prompt_path", "output_dir"):
        value = merged.get(path_key)
        if isinstance(value, str) and value:
            merged[path_key] = os.path.expanduser(value)

    known = {f.name for f in fields(Config)}
    filtered = {k: v for k, v in merged.items() if k in known}
    filtered["plugin_data"] = plugin_data
    filtered["plugin_root"] = plugin_root or ""

    return Config(**filtered)


def ensure_dirs(config: Config) -> None:
    """Create required data directories."""
    for path in (
        config.queue_dir,
        config.delivered_dir,
        config.outbox_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)
