from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .constants import APP_VERSION
from .storage import AppPaths, default_config, load_config, save_config

BACKUP_KIND = "gdut-grade-monitor-settings"
BACKUP_SCHEMA_VERSION = 1
EXPORTABLE_CONFIG_KEYS = {
    "poll_interval_minutes",
    "startup_enabled",
    "log_level",
    "first_run_wizard_seen",
    "notifications",
}
LOCAL_ONLY_KEYS = {"student_id", "monitor_paused_until"}


def export_settings(paths: AppPaths, output_path: Path) -> Path:
    paths.ensure()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "kind": BACKUP_KIND,
        "version": BACKUP_SCHEMA_VERSION,
        "app_version": APP_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "config": _exportable_config(load_config(paths)),
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def import_settings(paths: AppPaths, input_path: Path) -> dict[str, Any]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if payload.get("kind") != BACKUP_KIND:
        raise ValueError("这不是 GDUT 成绩提醒的设置备份文件。")
    imported = payload.get("config")
    if not isinstance(imported, dict):
        raise ValueError("设置备份文件缺少 config 字段。")

    current = load_config(paths)
    config = default_config()
    config.update(_exportable_config(imported))
    for key in LOCAL_ONLY_KEYS:
        if current.get(key):
            config[key] = current[key]
    if current.get("first_run_wizard_seen"):
        config["first_run_wizard_seen"] = current["first_run_wizard_seen"]
    save_config(paths, config)
    return load_config(paths)


def _exportable_config(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _strip_export_value(value)
        for key, value in config.items()
        if key in EXPORTABLE_CONFIG_KEYS and key not in LOCAL_ONLY_KEYS
    }


def _strip_export_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_export_value(item)
            for key, item in value.items()
            if str(key).lower() not in {"password", "cookie", "cookies", "secret", "secrets", "token", "sendkey", "send_key"}
        }
    if isinstance(value, list):
        return [_strip_export_value(item) for item in value]
    return value
