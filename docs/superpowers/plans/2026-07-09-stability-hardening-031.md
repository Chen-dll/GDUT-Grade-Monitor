# Stability Hardening 0.3.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Windows grade monitor more resilient by classifying runtime failures, preserving successful grade snapshots when notification channels fail, detecting broken autostart entries, and improving diagnostics/status messages.

**Architecture:** Add a focused `runtime_health.py` module for error classification and monitor-health helpers. Keep `GradeMonitor` responsible for runtime state updates, keep `task.py` responsible for startup target inspection, and keep GUI display decisions in `gui_model.py`.

**Tech Stack:** Python 3.10+, stdlib `unittest`, `requests`, PySide6/Tkinter existing GUI layers, Windows Startup folder, Task Scheduler, HKCU Run key.

---

## File Structure

- Create `gdut_grade_monitor/runtime_health.py`: error classification, monitor runtime-state helpers, and notification failure detection helpers.
- Create `tests/test_runtime_health.py`: unit tests for classification and runtime-state helper behavior.
- Modify `gdut_grade_monitor/monitor.py`: use runtime-health helpers, record structured state, isolate notification failures.
- Modify `tests/test_monitor_and_notify.py`: cover notification failure isolation and successful snapshot persistence.
- Modify `tests/test_v11_v12.py`: cover consecutive failure increment/reset and new runtime fields.
- Modify `gdut_grade_monitor/task.py`: add startup target health inspection for Startup `.vbs` and HKCU Run key.
- Modify `tests/test_storage_and_task.py`: cover startup health reports using temp files and winreg mocks.
- Modify `gdut_grade_monitor/doctor.py`: add startup-health warnings.
- Modify `tests/test_doctor_and_config_cli.py`: cover doctor warnings for broken startup and config-enabled-without-entry.
- Modify `gdut_grade_monitor/diagnostics.py`: add sanitized `runtime-health.json`.
- Modify `tests/test_diagnostics.py`: cover runtime-health diagnostics and redaction.
- Modify `gdut_grade_monitor/gui_model.py`: render structured status rows and actions.
- Modify `tests/test_gui_model.py`: cover consecutive failures, notification issue, login/network/school statuses, and autostart broken.
- Modify `gdut_grade_monitor/qt_gui.py` and `gdut_grade_monitor/gui.py`: wire existing status table/actions to new model text without broad redesign.
- Modify `gdut_grade_monitor/__init__.py`, `gdut_grade_monitor/constants.py`, `pyproject.toml`, `CHANGELOG.md`, and `tests/test_version_and_about.py`: bump to `0.3.1`.

---

### Task 1: Runtime Error Classification

**Files:**
- Create: `gdut_grade_monitor/runtime_health.py`
- Test: `tests/test_runtime_health.py`

- [ ] **Step 1: Write failing classification tests**

Create `tests/test_runtime_health.py`:

```python
import unittest
from requests import ConnectionError, Timeout

from gdut_grade_monitor.auth import PlaywrightBrowserMissingError
from gdut_grade_monitor.client import GradeResponseError
from gdut_grade_monitor.runtime_health import classify_error


class RuntimeHealthTests(unittest.TestCase):
    def test_classifies_login_expired_from_grade_response(self):
        error = GradeResponseError(
            "成绩接口返回的不是 JSON，可能登录已过期。",
            status_code=200,
            url="https://authserver.gdut.edu.cn/authserver/login",
            snippet="<html>统一身份认证</html>",
        )

        result = classify_error(error)

        self.assertEqual(result.kind, "login_expired")
        self.assertIn("重新登录", result.action)

    def test_classifies_network_errors(self):
        for error in [Timeout("timed out"), ConnectionError("network down")]:
            with self.subTest(error=type(error).__name__):
                result = classify_error(error)
                self.assertEqual(result.kind, "network")
                self.assertEqual(result.severity, "warning")

    def test_classifies_school_system_payload_errors(self):
        error = GradeResponseError(
            "成绩接口返回的不是 JSON。",
            status_code=502,
            url="https://jxfw.gdut.edu.cn/xskccjxx!getDataList.action",
            snippet="<html>bad gateway</html>",
        )

        result = classify_error(error)

        self.assertEqual(result.kind, "school_system")
        self.assertIn("稍后", result.action)

    def test_classifies_browser_missing_and_unknown(self):
        self.assertEqual(classify_error(PlaywrightBrowserMissingError()).kind, "browser_missing")
        self.assertEqual(classify_error(RuntimeError("strange")).kind, "unknown")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m unittest tests.test_runtime_health -v
```

Expected: fail with `ModuleNotFoundError: No module named 'gdut_grade_monitor.runtime_health'`.

- [ ] **Step 3: Implement runtime classification**

Create `gdut_grade_monitor/runtime_health.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from requests import ConnectionError, Timeout

from .auth import PlaywrightBrowserMissingError
from .client import GradeResponseError


@dataclass(frozen=True)
class RuntimeIssue:
    kind: str
    summary: str
    action: str
    severity: str = "warning"


def classify_error(exc: BaseException) -> RuntimeIssue:
    text = str(exc)
    if isinstance(exc, PlaywrightBrowserMissingError):
        return RuntimeIssue("browser_missing", "浏览器组件缺失", "请在设置页重新进行一键配置，或安装 Chrome/Edge。", "error")
    if isinstance(exc, (Timeout, ConnectionError)):
        return RuntimeIssue("network", "网络连接异常", "请检查网络、校园网或代理设置，稍后会自动重试。")
    if isinstance(exc, GradeResponseError):
        haystack = " ".join([text, getattr(exc, "url", "") or "", getattr(exc, "snippet", "") or ""]).lower()
        if "authserver" in haystack or "统一身份认证" in haystack or "login" in haystack:
            return RuntimeIssue("login_expired", "登录状态可能已过期", "请点击重新登录/初始化，完成统一身份认证。", "error")
        return RuntimeIssue("school_system", "学校系统响应异常", "可能是教务系统临时异常，请稍后重试或导出诊断包。")
    return RuntimeIssue("unknown", "未知运行异常", "请导出诊断包并反馈错误摘要。", "error")


def notification_issue() -> RuntimeIssue:
    return RuntimeIssue("notification_failed", "通知渠道发送失败", "成绩检查已完成，请到多设备通知里检查失败渠道。")


def autostart_issue() -> RuntimeIssue:
    return RuntimeIssue("autostart_broken", "自启动路径失效", "请在设置页点击安装/修复自启动。")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
python -m unittest tests.test_runtime_health -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add gdut_grade_monitor/runtime_health.py tests/test_runtime_health.py
git commit -m "Classify monitor runtime failures"
```

---

### Task 2: Structured Monitor Runtime State

**Files:**
- Modify: `gdut_grade_monitor/runtime_health.py`
- Modify: `gdut_grade_monitor/monitor.py`
- Test: `tests/test_v11_v12.py`

- [ ] **Step 1: Add failing monitor-state tests**

Append to `VersionEnhancementTests` in `tests/test_v11_v12.py`:

```python
class FailingFetcher:
    def fetch_grades(self):
        raise RuntimeError("boom")


def test_monitor_records_structured_failure_and_resets_after_success(self):
    with tempfile.TemporaryDirectory() as tmp:
        paths = AppPaths(Path(tmp))
        monitor = GradeMonitor(paths=paths, fetcher=FailingFetcher(), notifier=Mock())

        monitor._record_runtime_failure(RuntimeError("boom"))
        monitor._record_runtime_failure(RuntimeError("boom again"))
        failed_state = load_state(paths)

        self.assertEqual(failed_state["monitor"]["consecutive_failures"], 2)
        self.assertEqual(failed_state["monitor"]["last_error_kind"], "unknown")
        self.assertIn("last_failure_at", failed_state["monitor"])
        self.assertEqual(failed_state["last_check_status"], "error")

        recovery = GradeMonitor(
            paths=paths,
            fetcher=FakeFetcher([{"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"}]),
            notifier=Mock(),
        )
        recovery.run_once()
        recovered_state = load_state(paths)

        self.assertEqual(recovered_state["monitor"]["consecutive_failures"], 0)
        self.assertIn("last_success_at", recovered_state["monitor"])
        self.assertNotIn("last_error", recovered_state)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_v11_v12.VersionEnhancementTests.test_monitor_records_structured_failure_and_resets_after_success -v
```

Expected: fail because `_record_runtime_failure` does not exist.

- [ ] **Step 3: Add runtime-state helpers**

Extend `gdut_grade_monitor/runtime_health.py`:

```python
from datetime import datetime


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def monitor_state(state: dict) -> dict:
    monitor = state.get("monitor")
    if not isinstance(monitor, dict):
        monitor = {}
    state["monitor"] = monitor
    return monitor


def record_monitor_success(state: dict, *, checked_at: str, poll_interval_minutes: int) -> None:
    monitor = monitor_state(state)
    monitor["last_check_at"] = checked_at
    monitor["heartbeat_at"] = checked_at
    monitor["last_success_at"] = checked_at
    monitor["poll_interval_minutes"] = poll_interval_minutes
    monitor["consecutive_failures"] = 0
    for key in ["last_error_kind", "last_error_summary", "last_error_action"]:
        monitor.pop(key, None)
    state["last_check_status"] = "ok"
    state.pop("last_error", None)


def record_monitor_failure(state: dict, exc: BaseException, *, checked_at: str, poll_interval_minutes: int) -> RuntimeIssue:
    issue = classify_error(exc)
    monitor = monitor_state(state)
    monitor["heartbeat_at"] = checked_at
    monitor["last_check_at"] = checked_at
    monitor["last_failure_at"] = checked_at
    monitor["poll_interval_minutes"] = poll_interval_minutes
    monitor["consecutive_failures"] = int(monitor.get("consecutive_failures", 0) or 0) + 1
    monitor["last_error_kind"] = issue.kind
    monitor["last_error_summary"] = issue.summary
    monitor["last_error_action"] = issue.action
    state["last_check_status"] = "error"
    state["last_error"] = issue.summary
    return issue
```

- [ ] **Step 4: Use helpers in `monitor.py`**

Modify imports in `gdut_grade_monitor/monitor.py`:

```python
from .runtime_health import now_iso, record_monitor_failure, record_monitor_success
```

Change `run_once` success-state block to:

```python
checked_at = now_iso()
poll_interval = int(config.get("poll_interval_minutes", 30))
...
record_monitor_success(state, checked_at=checked_at, poll_interval_minutes=poll_interval)
state["last_change_count"] = len(changes)
```

Add a new method:

```python
def _record_runtime_failure(self, exc: BaseException) -> None:
    state = load_state(self.paths)
    checked_at = now_iso()
    poll_interval = int(load_config(self.paths).get("poll_interval_minutes", 30))
    record_monitor_failure(state, exc, checked_at=checked_at, poll_interval_minutes=poll_interval)
    save_state(self.paths, state)
```

Change `run_forever` exception handling from `_record_runtime_status("error", str(exc))` to:

```python
self._record_runtime_failure(exc)
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m unittest tests.test_v11_v12 -v
```

Expected: all `VersionEnhancementTests` pass.

- [ ] **Step 6: Commit**

```powershell
git add gdut_grade_monitor/runtime_health.py gdut_grade_monitor/monitor.py tests/test_v11_v12.py
git commit -m "Record structured monitor runtime health"
```

---

### Task 3: Isolate Notification Failures From Grade Snapshot Updates

**Files:**
- Modify: `gdut_grade_monitor/monitor.py`
- Modify: `gdut_grade_monitor/runtime_health.py`
- Test: `tests/test_monitor_and_notify.py`

- [ ] **Step 1: Add failing notification-isolation test**

Append to `tests/test_monitor_and_notify.py`:

```python
class RaisingNotifier(ChangeAwareNotifier):
    def send_change(self, change):
        super().send_change(change)
        raise RuntimeError("pushplus failed")


def test_notification_exception_does_not_rollback_grade_snapshot(self):
    with tempfile.TemporaryDirectory() as tmp:
        paths = AppPaths(Path(tmp))
        baseline = GradeMonitor(
            paths=paths,
            fetcher=FakeFetcher([{"xnxqdm": "202502", "kcbh": "MATH", "kcmc": "高数", "zcj": "88"}]),
            notifier=Mock(),
        )
        baseline.run_once()

        changed = GradeMonitor(
            paths=paths,
            fetcher=FakeFetcher([{"xnxqdm": "202502", "kcbh": "MATH", "kcmc": "高数", "zcj": "89"}]),
            notifier=RaisingNotifier(),
        )

        changes = changed.run_once()
        state = load_state(paths)

        self.assertEqual(len(changes), 1)
        self.assertEqual(state["grades"]["202502:MATH"]["score"], "89")
        self.assertEqual(state["last_check_status"], "notification_failed")
        self.assertEqual(state["monitor"]["last_error_kind"], "notification_failed")
        self.assertIn("last_notification_failure_at", state["monitor"])
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_monitor_and_notify.MonitorAndNotifyTests.test_notification_exception_does_not_rollback_grade_snapshot -v
```

Expected: fail because `run_once` raises the notification exception.

- [ ] **Step 3: Add notification failure state helper**

Extend `gdut_grade_monitor/runtime_health.py`:

```python
def record_notification_failure(state: dict, *, checked_at: str, detail: str) -> None:
    issue = notification_issue()
    monitor = monitor_state(state)
    monitor["last_notification_failure_at"] = checked_at
    monitor["last_error_kind"] = issue.kind
    monitor["last_error_summary"] = issue.summary
    monitor["last_error_action"] = issue.action
    monitor["last_notification_error"] = detail
    state["last_check_status"] = "notification_failed"
    state["last_error"] = issue.summary
```

- [ ] **Step 4: Catch notifier exceptions in `monitor.py`**

Modify imports:

```python
from .runtime_health import now_iso, record_monitor_failure, record_monitor_success, record_notification_failure
```

Replace the notification loop with:

```python
notification_errors: list[str] = []
for change in changes:
    try:
        send_change = getattr(type(self.notifier), "send_change", None)
        if callable(send_change):
            result = send_change(self.notifier, change)
        else:
            title, body = format_change_message(change)
            result = self.notifier.send(title, body)
        delivery = _delivery_results(result)
        if any(not row.get("ok", False) for row in delivery):
            notification_errors.extend(row.get("detail", "") for row in delivery if not row.get("ok", False))
        delivery_by_change.append(delivery)
    except Exception as exc:
        self.logger.exception("Notification failed: %s", exc)
        notification_errors.append(str(exc))
        delivery_by_change.append([{"channel_id": "unknown", "label": "通知渠道", "ok": False, "detail": str(exc)}])
```

After history is written, before `save_state`:

```python
if notification_errors:
    record_notification_failure(state, checked_at=checked_at, detail="; ".join(filter(None, notification_errors))[:300])
```

- [ ] **Step 5: Run tests**

Run:

```powershell
python -m unittest tests.test_monitor_and_notify -v
python -m unittest tests.test_v11_v12 -v
```

Expected: all pass.

- [ ] **Step 6: Commit**

```powershell
git add gdut_grade_monitor/runtime_health.py gdut_grade_monitor/monitor.py tests/test_monitor_and_notify.py
git commit -m "Keep grade checks successful when notification channels fail"
```

---

### Task 4: Autostart Health Inspection

**Files:**
- Modify: `gdut_grade_monitor/task.py`
- Test: `tests/test_storage_and_task.py`

- [ ] **Step 1: Add failing startup-health tests**

Extend imports in `tests/test_storage_and_task.py`:

```python
from gdut_grade_monitor.task import startup_health
```

Add tests:

```python
def test_startup_health_detects_missing_startup_script_target(self):
    with tempfile.TemporaryDirectory() as tmp:
        startup = Path(tmp) / "Startup"
        startup.mkdir()
        missing = Path(tmp) / "Deleted" / "GDUTGradeMonitor.exe"
        (startup / "GDUT Grade Monitor.vbs").write_text(
            f'Set WshShell = CreateObject("WScript.Shell")\nWshShell.Run """{missing}"" --monitor", 0, False\n',
            encoding="utf-8",
        )

        report = startup_health(startup_dir=startup, include_schtasks=False)

        self.assertFalse(report.ok)
        self.assertEqual(report.entries[0].mode, "startup")
        self.assertFalse(report.entries[0].target_exists)
        self.assertIn("不存在", report.message)

@patch("gdut_grade_monitor.task.run_key_target", return_value=Path("C:/Deleted/GDUTGradeMonitor.exe"))
@patch("gdut_grade_monitor.task.startup_script_exists", return_value=False)
def test_startup_health_detects_missing_run_key_target(self, startup_exists_mock, run_key_target_mock):
    report = startup_health(include_schtasks=False)

    self.assertFalse(report.ok)
    self.assertEqual(report.entries[0].mode, "run-key")
    self.assertFalse(report.entries[0].target_exists)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m unittest tests.test_storage_and_task.StorageAndTaskTests.test_startup_health_detects_missing_startup_script_target tests.test_storage_and_task.StorageAndTaskTests.test_startup_health_detects_missing_run_key_target -v
```

Expected: fail because `startup_health` does not exist.

- [ ] **Step 3: Implement startup health**

Add to `gdut_grade_monitor/task.py`:

```python
@dataclass(frozen=True)
class StartupEntryHealth:
    mode: str
    target: str
    target_exists: bool
    message: str


@dataclass(frozen=True)
class StartupHealth:
    ok: bool
    message: str
    entries: list[StartupEntryHealth]


def run_key_target() -> Path | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, RUN_VALUE_NAME)
    except OSError:
        return None
    return startup_script_target(f'WshShell.Run "{str(value).replace(chr(34), chr(34) * 2)}", 0, False')


def _entry_health(mode: str, target: Path | None) -> StartupEntryHealth | None:
    if target is None:
        return None
    exists = target.exists()
    message = "目标存在" if exists else f"目标不存在: {target}"
    return StartupEntryHealth(mode=mode, target=str(target), target_exists=exists, message=message)


def startup_health(startup_dir: Path | None = None, include_schtasks: bool = False) -> StartupHealth:
    entries: list[StartupEntryHealth] = []
    script = startup_script_path(startup_dir)
    if script.exists():
        target = startup_script_target(script.read_text(encoding="utf-8", errors="ignore"))
        entry = _entry_health("startup", target)
        if entry:
            entries.append(entry)
    run_entry = _entry_health("run-key", run_key_target())
    if run_entry:
        entries.append(run_entry)
    broken = [entry for entry in entries if not entry.target_exists]
    if broken:
        return StartupHealth(False, "启动项路径失效，目标文件不存在。", entries)
    if entries or (include_schtasks and task_exists()):
        return StartupHealth(True, "自启动已配置。", entries)
    return StartupHealth(True, "未检测到当前用户启动项。", entries)
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m unittest tests.test_storage_and_task -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add gdut_grade_monitor/task.py tests/test_storage_and_task.py
git commit -m "Inspect user startup target health"
```

---

### Task 5: Doctor Warnings for Startup Health

**Files:**
- Modify: `gdut_grade_monitor/doctor.py`
- Test: `tests/test_doctor_and_config_cli.py`

- [ ] **Step 1: Add failing doctor tests**

Append to `tests/test_doctor_and_config_cli.py`:

```python
def test_run_checks_warns_about_broken_autostart_target(self):
    with tempfile.TemporaryDirectory() as tmp:
        paths = AppPaths(Path(tmp))
        broken = Mock(ok=False, message="启动项路径失效，目标文件不存在。")
        with patch("gdut_grade_monitor.doctor.startup_health", return_value=broken):
            results = run_checks(paths)

        self.assertIn("Autostart health", [result.name for result in results])
        row = next(result for result in results if result.name == "Autostart health")
        self.assertFalse(row.ok)
        self.assertFalse(row.required)
        self.assertIn("路径失效", row.message)

def test_run_checks_warns_when_config_enabled_but_no_autostart_entry(self):
    with tempfile.TemporaryDirectory() as tmp:
        paths = AppPaths(Path(tmp))
        config = load_config(paths)
        config["startup_enabled"] = True
        save_config(paths, config)
        healthy_empty = Mock(ok=True, message="未检测到当前用户启动项。")
        with patch("gdut_grade_monitor.doctor.autostart_exists", return_value=False):
            with patch("gdut_grade_monitor.doctor.startup_health", return_value=healthy_empty):
                results = run_checks(paths)

        row = next(result for result in results if result.name == "Autostart health")
        self.assertFalse(row.ok)
        self.assertIn("配置显示已开启", row.message)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m unittest tests.test_doctor_and_config_cli.DoctorTests.test_run_checks_warns_about_broken_autostart_target tests.test_doctor_and_config_cli.DoctorTests.test_run_checks_warns_when_config_enabled_but_no_autostart_entry -v
```

Expected: fail because `Autostart health` is not reported.

- [ ] **Step 3: Implement doctor check**

Modify import in `gdut_grade_monitor/doctor.py`:

```python
from .task import autostart_exists, startup_health, startup_script_is_stale
```

Add `_check_autostart_health(paths)`:

```python
def _check_autostart_health(paths: AppPaths) -> CheckResult:
    config = load_config(paths)
    health = startup_health()
    if not health.ok:
        return CheckResult("Autostart health", False, health.message, required=False)
    if config.get("startup_enabled") and not autostart_exists():
        return CheckResult(
            "Autostart health",
            False,
            "配置显示已开启自启动，但未检测到启动项；请在设置页点击安装/修复自启动。",
            required=False,
        )
    return CheckResult("Autostart health", True, health.message, required=False)
```

Insert `_check_autostart_health(paths)` immediately after `_check_autostart()` in `run_checks`.

- [ ] **Step 4: Run doctor tests**

Run:

```powershell
python -m unittest tests.test_doctor_and_config_cli -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add gdut_grade_monitor/doctor.py tests/test_doctor_and_config_cli.py
git commit -m "Warn when startup entries are broken"
```

---

### Task 6: Diagnostics Runtime Health Summary

**Files:**
- Modify: `gdut_grade_monitor/diagnostics.py`
- Test: `tests/test_diagnostics.py`

- [ ] **Step 1: Add failing diagnostics test**

Append to `tests/test_diagnostics.py`:

```python
def test_diagnostics_zip_contains_runtime_health_without_sensitive_values(self):
    with tempfile.TemporaryDirectory() as tmp:
        paths = AppPaths(Path(tmp))
        paths.ensure()
        save_config(paths, {"student_id": "3210000000", "password": "secret", "notifications": {"pushplus": {"token": "abc"}}})
        save_state(
            paths,
            {
                "grades": {"202502:CS101": {"course_name": "数据结构", "score": "95"}},
                "monitor": {
                    "last_success_at": "2026-07-09T12:00:00",
                    "last_failure_at": "2026-07-09T13:00:00",
                    "consecutive_failures": 3,
                    "last_error_kind": "login_expired",
                    "last_error_summary": "登录状态可能已过期",
                    "last_error_action": "请重新登录",
                    "last_notification_error": "token abc failed",
                },
            },
        )

        output = Path(tmp) / "diagnostics.zip"
        create_diagnostics_zip(paths=paths, output_path=output, check_results=[])

        with zipfile.ZipFile(output) as archive:
            names = archive.namelist()
            self.assertIn("runtime-health.json", names)
            text = archive.read("runtime-health.json").decode("utf-8")

        self.assertIn("login_expired", text)
        self.assertIn("consecutive_failures", text)
        self.assertNotIn("3210000000", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("abc", text)
        self.assertNotIn("数据结构", text)
        self.assertNotIn("95", text)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m unittest tests.test_diagnostics.DiagnosticsTests.test_diagnostics_zip_contains_runtime_health_without_sensitive_values -v
```

Expected: fail because `runtime-health.json` is missing.

- [ ] **Step 3: Add runtime health diagnostics**

In `gdut_grade_monitor/diagnostics.py`, add:

```python
def _runtime_health_summary(config: dict, state: dict) -> dict:
    monitor = state.get("monitor", {}) if isinstance(state.get("monitor"), dict) else {}
    notifications = config.get("notifications", {}) if isinstance(config.get("notifications"), dict) else {}
    channels = {}
    for channel_id, channel_config in notifications.items():
        if isinstance(channel_config, dict):
            channels[channel_id] = {
                "enabled": bool(channel_config.get("enabled", False)),
                "privacy": str(channel_config.get("privacy", "")),
            }
    return {
        "student_id": mask_student_id(str(config.get("student_id", ""))),
        "last_success_at": monitor.get("last_success_at", ""),
        "last_failure_at": monitor.get("last_failure_at", ""),
        "consecutive_failures": monitor.get("consecutive_failures", 0),
        "last_error_kind": monitor.get("last_error_kind", ""),
        "last_error_summary": monitor.get("last_error_summary", ""),
        "last_error_action": monitor.get("last_error_action", ""),
        "last_notification_failure_at": monitor.get("last_notification_failure_at", ""),
        "notifications": channels,
    }
```

In `create_diagnostics_zip`, keep raw config/state local variables and write:

```python
raw_config = load_config(paths)
raw_state = load_state(paths)
config = _sanitize_config(raw_config)
state = _state_summary(raw_state)
...
_write_json(archive, "runtime-health.json", _runtime_health_summary(raw_config, raw_state))
```

- [ ] **Step 4: Run diagnostics tests**

Run:

```powershell
python -m unittest tests.test_diagnostics -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add gdut_grade_monitor/diagnostics.py tests/test_diagnostics.py
git commit -m "Add sanitized runtime health diagnostics"
```

---

### Task 7: GUI Model Status Rows

**Files:**
- Modify: `gdut_grade_monitor/gui_model.py`
- Test: `tests/test_gui_model.py`

- [ ] **Step 1: Add failing GUI model tests**

Append to `tests/test_gui_model.py`:

```python
def test_status_center_rows_warns_after_three_failures(self):
    config = {"student_id": "3210000000", "poll_interval_minutes": 30}
    state = {
        "last_check_status": "error",
        "monitor": {
            "consecutive_failures": 3,
            "last_error_kind": "login_expired",
            "last_error_summary": "登录状态可能已过期",
            "last_error_action": "请重新登录",
        },
    }

    rows = status_center_rows(config=config, state=state, startup_installed=True, now_iso="2026-07-09T12:00:00")

    joined = " ".join(row["value"] + row["detail"] for row in rows)
    self.assertIn("连续 3 次", joined)
    self.assertIn("请重新登录", joined)

def test_status_center_rows_shows_notification_issue_as_warning(self):
    config = {"student_id": "3210000000", "poll_interval_minutes": 30}
    state = {
        "last_check_status": "notification_failed",
        "monitor": {
            "last_success_at": "2026-07-09T12:00:00",
            "last_error_kind": "notification_failed",
            "last_error_summary": "通知渠道发送失败",
            "last_error_action": "请检查失败渠道",
        },
    }

    rows = status_center_rows(config=config, state=state, startup_installed=True, now_iso="2026-07-09T12:00:00")

    status = rows[0]
    self.assertEqual(status["tone"], "warning")
    self.assertIn("通知", status["value"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m unittest tests.test_gui_model.GuiModelTests.test_status_center_rows_warns_after_three_failures tests.test_gui_model.GuiModelTests.test_status_center_rows_shows_notification_issue_as_warning -v
```

Expected: fail because rows do not include the new structured text.

- [ ] **Step 3: Update status-center rendering**

In `gdut_grade_monitor/gui_model.py`, update `status_center_rows` status map:

```python
status_map = {
    "ok": ("后台正常", "最近一次检查完成。", "ok"),
    "paused": ("暂停中", "自动后台检查已暂停，手动立即检查仍可使用。", "warning"),
    "error": ("检查失败", "后台检查遇到问题。", "error"),
    "notification_failed": ("通知异常", "成绩检查已完成，但至少一个通知渠道发送失败。", "warning"),
}
```

After `last_error` handling, prefer structured monitor fields:

```python
failure_count = int(monitor.get("consecutive_failures", 0) or 0)
summary = str(monitor.get("last_error_summary", "") or state.get("last_error", "") or "").strip()
action = str(monitor.get("last_error_action", "") or "可重新登录、打开环境检查或导出诊断包。").strip()
if summary:
    value = summary
    if failure_count >= 3:
        value = f"连续 {failure_count} 次失败: {summary}"
    rows.append({"label": "最近错误", "value": value, "detail": action, "tone": "error" if status == "error" else "warning"})
```

Remove or adapt the older `last_error` row so only one recent-error row appears.

- [ ] **Step 4: Run GUI model tests**

Run:

```powershell
python -m unittest tests.test_gui_model -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add gdut_grade_monitor/gui_model.py tests/test_gui_model.py
git commit -m "Show structured runtime health in the dashboard model"
```

---

### Task 8: GUI and CLI Repair Wording

**Files:**
- Modify: `gdut_grade_monitor/qt_gui.py`
- Modify: `gdut_grade_monitor/gui.py`
- Modify: `gdut_grade_monitor/cli.py`
- Test: `tests/test_qt_gui_packaging.py`
- Test: `tests/test_doctor_and_config_cli.py`

- [ ] **Step 1: Add failing text/CLI tests**

In `tests/test_qt_gui_packaging.py`, add:

```python
def test_qt_gui_mentions_repair_startup_wording(self):
    text = Path("gdut_grade_monitor/qt_gui.py").read_text(encoding="utf-8")

    self.assertIn("修复自启动", text)
    self.assertIn("install_startup", text)
```

In `tests/test_doctor_and_config_cli.py`, add:

```python
def test_task_install_reports_run_key_fallback(self):
    runner = CliRunner()
    with patch("gdut_grade_monitor.cli.install_task_or_startup") as install_mock:
        install_mock.return_value = Mock(mode="run-key", returncode=0, stdout="", stderr="")
        result = runner.invoke(main, ["task", "install"])

    self.assertEqual(result.exit_code, 0)
    self.assertIn("Run", result.output)
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m unittest tests.test_qt_gui_packaging.QtGuiPackagingTests.test_qt_gui_mentions_repair_startup_wording tests.test_doctor_and_config_cli.ConfigCliTests.test_task_install_reports_run_key_fallback -v
```

Expected: Qt text test fails if wording is absent; CLI test passes if already present, otherwise fails.

- [ ] **Step 3: Update GUI wording**

In `gdut_grade_monitor/qt_gui.py`, change the settings startup button text from:

```python
install = QPushButton("安装自启动")
```

to:

```python
install = QPushButton("安装/修复自启动")
install.setToolTip("修复自启动会重新写入当前用户启动项，不会删除本地成绩或凭据。")
```

In `gdut_grade_monitor/gui.py`, change the Tk button text from:

```python
ttk.Button(toolbar, text="安装自启动", command=self.install_startup)
```

to:

```python
ttk.Button(toolbar, text="安装/修复自启动", command=self.install_startup)
```

Ensure `cli.py` run-key fallback message still contains `Run fallback`.

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m unittest tests.test_qt_gui_packaging tests.test_doctor_and_config_cli -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add gdut_grade_monitor/qt_gui.py gdut_grade_monitor/gui.py gdut_grade_monitor/cli.py tests/test_qt_gui_packaging.py tests/test_doctor_and_config_cli.py
git commit -m "Make startup repair clearer in UI and CLI"
```

---

### Task 9: Version Bump and Release Notes

**Files:**
- Modify: `gdut_grade_monitor/__init__.py`
- Modify: `gdut_grade_monitor/constants.py`
- Modify: `pyproject.toml`
- Modify: `CHANGELOG.md`
- Test: `tests/test_version_and_about.py`

- [ ] **Step 1: Add/update version expectation**

In `tests/test_version_and_about.py`, make sure the expected version is read from files rather than hardcoded. If there is a hardcoded `0.3.0`, change it to `0.3.1`.

- [ ] **Step 2: Bump version**

Set all current version strings to `0.3.1`:

```python
# gdut_grade_monitor/__init__.py
__version__ = "0.3.1"
```

```python
# gdut_grade_monitor/constants.py
APP_VERSION = "0.3.1"
```

```toml
# pyproject.toml
version = "0.3.1"
```

- [ ] **Step 3: Add changelog entry**

At the top of `CHANGELOG.md`, add:

```markdown
## 0.3.1

- Added structured runtime health for background checks.
- Isolated notification-channel failures from successful grade snapshot updates.
- Added startup target health detection for Startup folder and HKCU Run entries.
- Improved diagnostics with sanitized runtime-health summaries.
- Improved dashboard and setup wording for startup repair and repeated failures.
```

- [ ] **Step 4: Run version tests**

Run:

```powershell
python -m unittest tests.test_version_and_about -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add gdut_grade_monitor/__init__.py gdut_grade_monitor/constants.py pyproject.toml CHANGELOG.md tests/test_version_and_about.py
git commit -m "Bump version for stability hardening release"
```

---

### Task 10: Final Verification

**Files:**
- No source changes unless verification exposes a bug.

- [ ] **Step 1: Run full unit suite**

Run:

```powershell
python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Run compile check**

Run:

```powershell
python -m compileall gdut_grade_monitor tests packaging docs scripts
```

Expected: exit code `0`.

- [ ] **Step 3: Run patch hygiene check**

Run:

```powershell
git diff --check
```

Expected: no output and exit code `0`.

- [ ] **Step 4: Run local environment smoke**

Run:

```powershell
python -m gdut_grade_monitor doctor
python -m gdut_grade_monitor monitor --once
```

Expected: `doctor` shows required checks OK; `monitor --once` prints `Checked grades. Changes: N`.

- [ ] **Step 5: Run Qt dialog smoke if PySide6 is available**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python - <<'PY'
from PySide6.QtWidgets import QApplication
from gdut_grade_monitor.qt_gui import GradeMonitorQtApp
app = QApplication.instance() or QApplication(["qt-smoke", "-platform", "offscreen"])
window = GradeMonitorQtApp()
window.show()
app.processEvents()
print(f"QT_OK {window.size().width()}x{window.size().height()}")
window.close()
PY
```

Expected: prints `QT_OK` with a nonzero size.

- [ ] **Step 6: Commit verification-only fixes if needed**

If a bug is found, make the smallest fix, rerun the affected tests plus full verification, and commit with a focused message. If no bug is found, do not create an empty commit.

---

## Self-Review Notes

- Spec coverage: failure classification is Task 1; runtime state is Task 2; notification isolation is Task 3; autostart health is Tasks 4-5; diagnostics is Task 6; GUI status is Tasks 7-8; release criteria are Task 10.
- Placeholder scan: this plan contains no unfinished markers or vague implementation-only instructions.
- Type consistency: stable names used throughout are `RuntimeIssue`, `classify_error`, `record_monitor_success`, `record_monitor_failure`, `record_notification_failure`, `StartupEntryHealth`, `StartupHealth`, and `startup_health`.
