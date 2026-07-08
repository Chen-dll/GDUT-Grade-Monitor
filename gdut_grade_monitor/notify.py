from __future__ import annotations

try:
    from winotify import Notification
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    Notification = None

from .constants import APP_NAME


class WindowsNotifier:
    def __init__(self, app_id: str = APP_NAME):
        self.app_id = app_id

    def send(self, title: str, body: str) -> None:
        if Notification is None:
            return
        toast = Notification(app_id=self.app_id, title=title, msg=body)
        toast.show()


def format_change_message(change: dict) -> tuple[str, str]:
    grade = change["grade"]
    course_name = grade.get("course_name", "")
    semester = grade.get("semester", "")
    score = grade.get("score", "")
    if change.get("kind") == "changed":
        title = "GDUT 成绩更新"
        body = f"{semester} {course_name}: {change.get('old_score', '')} -> {score}"
    else:
        title = "GDUT 新成绩"
        body = f"{semester} {course_name}: {score}"
    return title, body
