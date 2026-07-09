from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import DEFAULT_DATA_DIR, DEFAULT_POLL_INTERVAL_MINUTES

SENSITIVE_CONFIG_KEYS = {"password", "cookie", "cookies", "secret", "secrets", "token", "sendkey", "send_key"}


@dataclass(frozen=True)
class AppPaths:
    root: Path = DEFAULT_DATA_DIR

    @property
    def config_file(self) -> Path:
        return self.root / "config.json"

    @property
    def cookies_file(self) -> Path:
        return self.root / "cookies.json"

    @property
    def state_file(self) -> Path:
        return self.root / "state.json"

    @property
    def log_dir(self) -> Path:
        return self.root / "logs"

    @property
    def log_file(self) -> Path:
        return self.log_dir / "monitor.log"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


def default_config() -> dict[str, Any]:
    return {
        "poll_interval_minutes": DEFAULT_POLL_INTERVAL_MINUTES,
        "startup_enabled": False,
        "log_level": "INFO",
        "student_id": "",
        "first_run_wizard_seen": False,
        "close_action": "ask",
        "last_seen_version": "",
        "notifications": {
            "windows": {"enabled": True, "privacy": "detailed"},
            "pushplus": {"enabled": False, "privacy": "private"},
            "serverchan": {"enabled": False, "privacy": "private"},
            "ntfy": {"enabled": False, "privacy": "private", "server_url": "https://ntfy.sh", "topic": ""},
            "smtp": {
                "enabled": False,
                "privacy": "private",
                "host": "",
                "port": 587,
                "username": "",
                "sender": "",
                "recipient": "",
                "security": "starttls",
            },
        },
    }


def load_config(paths: AppPaths) -> dict[str, Any]:
    if not paths.config_file.exists():
        return default_config()
    data = _read_json(paths.config_file, default_config())
    config = default_config()
    config.update(_strip_sensitive_config(data))
    return config


def save_config(paths: AppPaths, config: dict[str, Any]) -> None:
    paths.ensure()
    safe_config = _strip_sensitive_config(config)
    paths.config_file.write_text(
        json.dumps(safe_config, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def reset_config(paths: AppPaths) -> dict[str, Any]:
    current = load_config(paths)
    config = default_config()
    for key in ("student_id", "first_run_wizard_seen"):
        if current.get(key):
            config[key] = current[key]
    save_config(paths, config)
    return config


def set_poll_interval(paths: AppPaths, minutes: int) -> dict[str, Any]:
    config = load_config(paths)
    config["poll_interval_minutes"] = max(1, min(1440, int(minutes)))
    save_config(paths, config)
    return config


def load_state(paths: AppPaths) -> dict[str, Any]:
    return _read_json(paths.state_file, {})


def save_state(paths: AppPaths, state: dict[str, Any]) -> None:
    paths.ensure()
    paths.state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default.copy()


def _strip_sensitive_config(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_sensitive_config(item)
            for key, item in value.items()
            if str(key).lower() not in SENSITIVE_CONFIG_KEYS
        }
    if isinstance(value, list):
        return [_strip_sensitive_config(item) for item in value]
    return value
