from __future__ import annotations

import importlib.util
import platform
import sys
from dataclasses import dataclass

from .auth import find_system_browser
from .storage import AppPaths, load_config
from .task import autostart_exists


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str
    required: bool = True


def run_checks(paths: AppPaths | None = None) -> list[CheckResult]:
    paths = paths or AppPaths()
    results = [
        _check_python(),
        _check_platform(),
        _check_import("click"),
        _check_import("requests"),
        _check_import("keyring"),
        _check_import("playwright"),
        _check_import("winotify", required=False),
        _check_browser(),
        _check_data_dir(paths),
        _check_config(paths),
        _check_autostart(),
    ]
    return results


def overall_ok(results: list[CheckResult]) -> bool:
    return all(result.ok for result in results if result.required)


def render_results(results: list[CheckResult]) -> str:
    lines = []
    for result in results:
        if result.ok:
            prefix = "[OK]"
        elif result.required:
            prefix = "[FAIL]"
        else:
            prefix = "[WARN]"
        lines.append(f"{prefix} {result.name} - {result.message}")
    return "\n".join(lines)


def _check_python() -> CheckResult:
    version = sys.version_info
    ok = version >= (3, 10)
    return CheckResult("Python", ok, platform.python_version())


def _check_platform() -> CheckResult:
    system = platform.system()
    return CheckResult("Windows", system == "Windows", system)


def _check_import(module: str, required: bool = True) -> CheckResult:
    found = importlib.util.find_spec(module) is not None
    return CheckResult(module, found, "installed" if found else "not installed", required=required)


def _check_browser() -> CheckResult:
    browser = find_system_browser()
    if browser:
        return CheckResult("Browser", True, browser)
    return CheckResult(
        "Browser",
        False,
        "Chrome/Edge not found. Run: python -m playwright install chromium",
        required=False,
    )


def _check_data_dir(paths: AppPaths) -> CheckResult:
    try:
        paths.ensure()
        probe = paths.root / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return CheckResult("Data directory", True, str(paths.root))
    except OSError as exc:
        return CheckResult("Data directory", False, str(exc))


def _check_config(paths: AppPaths) -> CheckResult:
    config = load_config(paths)
    student_id = config.get("student_id")
    interval = config.get("poll_interval_minutes")
    if student_id:
        return CheckResult("Configuration", True, f"student_id set, interval {interval} minutes")
    return CheckResult("Configuration", False, "student_id not set; run setup", required=False)


def _check_autostart() -> CheckResult:
    installed = autostart_exists()
    return CheckResult("Autostart", installed, "installed" if installed else "not installed", required=False)
