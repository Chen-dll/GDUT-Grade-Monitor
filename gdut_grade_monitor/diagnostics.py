from __future__ import annotations

import json
import platform
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .constants import APP_VERSION
from .doctor import CheckResult, render_results, run_checks
from .storage import AppPaths, load_config, load_state

SENSITIVE_KEYS = {"password", "cookie", "cookies", "token", "secret", "raw"}
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|cookie|cookies|token|secret|jsessionid)\s*[:=]\s*[^;\s,\]}]+"
)
STUDENT_ID_RE = re.compile(r"\b\d{8,14}\b")


def mask_student_id(student_id: str) -> str:
    value = str(student_id or "")
    if len(value) <= 2:
        return "*" * len(value)
    if len(value) <= 6:
        return value[0] + ("*" * (len(value) - 2)) + value[-1]
    return value[:3] + "****" + value[-3:]


def redact_text(text: str) -> str:
    redacted = SENSITIVE_ASSIGNMENT_RE.sub("<redacted>", text)
    return STUDENT_ID_RE.sub(lambda match: mask_student_id(match.group(0)), redacted)


def create_diagnostics_zip(
    *,
    paths: AppPaths,
    output_path: Path | None = None,
    check_results: Iterable[CheckResult] | None = None,
) -> Path:
    paths.ensure()
    output_path = output_path or _default_output_path(paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    config = _sanitize_config(load_config(paths))
    state = _state_summary(load_state(paths))
    checks = list(check_results) if check_results is not None else run_checks(paths)
    manifest = {
        "app_version": APP_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "executable": Path(sys.executable).name,
    }

    with zipfile.ZipFile(output_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        _write_json(archive, "manifest.json", manifest)
        _write_json(archive, "config.json", config)
        _write_json(archive, "state-summary.json", state)
        archive.writestr("doctor.txt", redact_text(render_results(checks)))
        if paths.log_file.exists():
            archive.writestr("logs/monitor.log", redact_text(paths.log_file.read_text(encoding="utf-8", errors="replace")))

    return output_path


def _default_output_path(paths: AppPaths) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return paths.root / f"gdut-grade-monitor-diagnostics-{stamp}.zip"


def _write_json(archive: zipfile.ZipFile, name: str, data: dict) -> None:
    archive.writestr(name, redact_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)))


def _sanitize_config(config: dict) -> dict:
    sanitized = {}
    for key, value in config.items():
        lowered = key.lower()
        if lowered in SENSITIVE_KEYS:
            continue
        if lowered == "student_id":
            sanitized[key] = mask_student_id(str(value))
        else:
            sanitized[key] = value
    return sanitized


def _state_summary(state: dict) -> dict:
    grades = state.get("grades", {})
    history = state.get("history", [])
    monitor = state.get("monitor", {})
    return {
        "grade_count": len(grades) if isinstance(grades, dict) else 0,
        "history_count": len(history) if isinstance(history, list) else 0,
        "last_check_status": state.get("last_check_status", ""),
        "last_change_count": state.get("last_change_count", 0),
        "monitor": {
            "last_check_at": monitor.get("last_check_at", ""),
            "heartbeat_at": monitor.get("heartbeat_at", ""),
            "poll_interval_minutes": monitor.get("poll_interval_minutes", ""),
        },
    }
