from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Protocol

from .grades import diff_grades
from .notify import format_change_message
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
        checked_at = datetime.now().isoformat(timespec="seconds")

        for change in changes:
            title, body = format_change_message(change)
            self.notifier.send(title, body)

        state["grades"] = snapshot
        state["last_check_status"] = "ok"
        state["last_change_count"] = len(changes)
        state["monitor"] = {
            "last_check_at": checked_at,
            "heartbeat_at": checked_at,
            "poll_interval_minutes": int(config.get("poll_interval_minutes", 30)),
        }
        if changes:
            history = state.get("history", [])
            history_entries = [_history_entry(change, checked_at) for change in changes]
            state["history"] = (history_entries + history)[:100]
        save_state(self.paths, state)
        return changes

    def run_forever(self) -> None:
        while True:
            try:
                self.run_once()
            except Exception as exc:
                self.logger.exception("Grade check failed: %s", exc)
            config = load_config(self.paths)
            interval_seconds = int(config.get("poll_interval_minutes", 30)) * 60
            time.sleep(interval_seconds)


def _history_entry(change: dict, checked_at: str) -> dict:
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
    return entry
