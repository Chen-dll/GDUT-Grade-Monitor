# Multi-Device Notifications Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional PushPlus, Server Chan, ntfy, and SMTP notifications with per-channel privacy controls.

**Architecture:** Keep the monitor read-only and channel-agnostic. `notify.py` formats privacy-aware messages, and `notification_channels.py` builds/sends third-party notifications from local config plus keyring secrets. The Qt settings page opens a focused multi-device notification dialog.

**Tech Stack:** Python standard library, requests, keyring, PySide6, unittest.

---

### Task 1: Privacy-Aware Notification Messages

**Files:**
- Modify: `gdut_grade_monitor/notify.py`
- Test: `tests/test_monitor_and_notify.py`

- [ ] Add tests for `private`, `summary`, and `detailed` privacy modes.
- [ ] Run `python -m unittest tests.test_monitor_and_notify -v` and confirm the new tests fail.
- [ ] Add privacy mode constants and extend `format_change_message(change, privacy_mode="detailed")`.
- [ ] Re-run `python -m unittest tests.test_monitor_and_notify -v`.

### Task 2: Channel Implementations

**Files:**
- Create: `gdut_grade_monitor/notification_channels.py`
- Test: `tests/test_notification_channels.py`

- [ ] Add tests for PushPlus, Server Chan, ntfy, SMTP, secret storage names, config normalization, and failure isolation.
- [ ] Run `python -m unittest tests.test_notification_channels -v` and confirm the new module is missing.
- [ ] Implement channel classes, `NotificationSecretStore`, `MultiDeviceNotifier`, and `build_notifier`.
- [ ] Re-run `python -m unittest tests.test_notification_channels -v`.

### Task 3: Monitor Integration

**Files:**
- Modify: `gdut_grade_monitor/monitor.py`
- Modify: `gdut_grade_monitor/cli.py`
- Modify: `gdut_grade_monitor/gui.py`
- Modify: `gdut_grade_monitor/qt_gui.py`

- [ ] Add a monitor test proving a notifier with `send_change` receives raw changes.
- [ ] Run the focused monitor test and confirm it fails.
- [ ] Update `GradeMonitor.run_once()` to prefer `send_change(change)` and fall back to `send(title, body)`.
- [ ] Replace direct `WindowsNotifier()` construction in CLI/GUI paths with `build_notifier(paths)`.
- [ ] Re-run focused monitor and existing GUI packaging tests.

### Task 4: Config And GUI

**Files:**
- Modify: `gdut_grade_monitor/storage.py`
- Modify: `gdut_grade_monitor/qt_gui.py`
- Test: `tests/test_storage_and_task.py`
- Test: `tests/test_qt_gui_packaging.py`

- [ ] Add tests for recursive secret stripping and GUI labels.
- [ ] Run focused tests and confirm failures.
- [ ] Add notification defaults to config.
- [ ] Add the Qt multi-device notification dialog and settings entry.
- [ ] Re-run focused tests.

### Task 5: Version, Docs, And Release Readiness

**Files:**
- Modify: `pyproject.toml`
- Modify: `gdut_grade_monitor/__init__.py`
- Modify: `gdut_grade_monitor/constants.py`
- Modify: `packaging/installer/GDUTGradeMonitor.iss`
- Modify: `packaging/installer/InfoBefore.txt`
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Test: `tests/test_version_and_about.py`

- [ ] Bump local version to `0.3.0`.
- [ ] Document multi-device notification channels, privacy modes, and third-party service privacy warnings.
- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Run `python -m compileall gdut_grade_monitor tests packaging docs`.
