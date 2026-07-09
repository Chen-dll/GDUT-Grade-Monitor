from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Protocol

from .grades import diff_grades
from .notify import format_change_message
from .runtime_health import now_iso, record_monitor_failure, record_monitor_success, record_notification_failure
from .storage import AppPaths, load_config, load_state, save_state


class GradeFetcher(Protocol):
    def fetch_grades(self) -> list[dict]:
        ...


class Notifier(Protocol):
    def send(self, title: str, body: str) -> None:
        ...


class GradeMonitor:
    def __init__(self, paths: AppPaths, fetcher: GradeFetcher, notifier: Notifier):
        self.paths = paths
        self.fetcher = fetcher
        self.notifier = notifier
        self.logger = logging.getLogger("gdut_grade_monitor")

    def run_once(self) -> list[dict]:
        config = load_config(self.paths)
        state = load_state(self.paths)
        previous = state.get("grades")
        current = self.fetcher.fetch_grades()
        changes, snapshot = diff_grades(previous_snapshot=previous, current_grades=current)
        checked_at = now_iso()
        poll_interval = int(config.get("poll_interval_minutes", 30))

        delivery_by_change: list[list[dict]] = []
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
                notification_errors.extend(
                    row.get("detail", "")
                    for row in delivery
                    if not row.get("ok", False)
                )
                delivery_by_change.append(delivery)
            except Exception as exc:
                detail = str(exc)
                self.logger.warning("Notification failed: %s", exc)
                notification_errors.append(detail)
                delivery_by_change.append(
                    [{"channel_id": "unknown", "label": "通知渠道", "ok": False, "detail": detail}]
                )

        state["grades"] = snapshot
        record_monitor_success(state, checked_at=checked_at, poll_interval_minutes=poll_interval)
        state["last_change_count"] = len(changes)
        if changes:
            history = state.get("history", [])
            history_entries = [
                _history_entry(change, checked_at, delivery_by_change[index])
                for index, change in enumerate(changes)
            ]
            state["history"] = (history_entries + history)[:100]
        if notification_errors:
            detail = "; ".join(filter(None, notification_errors))[:300]
            record_notification_failure(state, checked_at=checked_at, detail=detail)
        save_state(self.paths, state)
        return changes

    def run_forever(self) -> None:
        while True:
            config = load_config(self.paths)
            interval_seconds = int(config.get("poll_interval_minutes", 30)) * 60
            pause_remaining = monitor_pause_remaining_seconds(config)
            if pause_remaining > 0:
                self._record_runtime_status("paused")
                time.sleep(min(interval_seconds, pause_remaining))
                continue
            try:
                self.run_once()
            except Exception as exc:
                self.logger.exception("Grade check failed: %s", exc)
                self._record_runtime_failure(exc)
            time.sleep(interval_seconds)

    def _record_runtime_failure(self, exc: BaseException) -> None:
        state = load_state(self.paths)
        checked_at = now_iso()
        poll_interval = int(load_config(self.paths).get("poll_interval_minutes", 30))
        record_monitor_failure(state, exc, checked_at=checked_at, poll_interval_minutes=poll_interval)
        save_state(self.paths, state)

    def _record_runtime_status(self, status: str, error: str = "") -> None:
        state = load_state(self.paths)
        monitor = state.get("monitor", {})
        checked_at = datetime.now().isoformat(timespec="seconds")
        monitor["heartbeat_at"] = checked_at
        monitor["poll_interval_minutes"] = int(load_config(self.paths).get("poll_interval_minutes", 30))
        state["monitor"] = monitor
        state["last_check_status"] = status
        if error:
            state["last_error"] = error
        save_state(self.paths, state)


def _history_entry(change: dict, checked_at: str, delivery: list[dict] | None = None) -> dict:
    grade = change["grade"]
    entry = {
        "at": checked_at,
        "kind": change.get("kind", ""),
        "semester": grade.get("semester", ""),
        "course_name": grade.get("course_name", ""),
        "score": grade.get("score", ""),
    }
    if "old_score" in change:
        entry["old_score"] = change["old_score"]
    if delivery:
        entry["delivery"] = delivery
    return entry


def _delivery_results(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    rows = []
    for item in value:
        if isinstance(item, dict):
            channel_id = str(item.get("channel_id", ""))
            label = str(item.get("label", channel_id))
            ok = bool(item.get("ok", False))
            detail = str(item.get("detail", ""))
        else:
            channel_id = str(getattr(item, "channel_id", ""))
            label = str(getattr(item, "label", channel_id))
            ok = bool(getattr(item, "ok", False))
            detail = str(getattr(item, "detail", ""))
        if channel_id:
            rows.append({"channel_id": channel_id, "label": label, "ok": ok, "detail": detail})
    return rows


def monitor_pause_remaining_seconds(config: dict, now_iso: str | None = None) -> int:
    paused_until = str(config.get("monitor_paused_until", "") or "").strip()
    if not paused_until:
        return 0
    try:
        until = datetime.fromisoformat(paused_until)
        now = datetime.fromisoformat(now_iso) if now_iso else datetime.now()
    except ValueError:
        return 0
    return max(0, int((until - now).total_seconds()))
