from __future__ import annotations

try:
    from winotify import Notification
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    Notification = None

from .constants import APP_NAME

NOTIFICATION_PRIVACY_PRIVATE = "private"
NOTIFICATION_PRIVACY_SUMMARY = "summary"
NOTIFICATION_PRIVACY_DETAILED = "detailed"
NOTIFICATION_PRIVACY_MODES = {
    NOTIFICATION_PRIVACY_PRIVATE,
    NOTIFICATION_PRIVACY_SUMMARY,
    NOTIFICATION_PRIVACY_DETAILED,
}


class WindowsNotifier:
    def __init__(self, app_id: str = APP_NAME):
        self.app_id = app_id

    def send(self, title: str, body: str) -> None:
        if Notification is None:
            return
        toast = Notification(app_id=self.app_id, title=title, msg=body)
        toast.show()


def format_change_message(change: dict, privacy_mode: str = NOTIFICATION_PRIVACY_DETAILED) -> tuple[str, str]:
    if privacy_mode not in NOTIFICATION_PRIVACY_MODES:
        privacy_mode = NOTIFICATION_PRIVACY_DETAILED
    grade = change["grade"]
    course_name = grade.get("course_name", "")
    semester = grade.get("semester", "")
    score = grade.get("score", "")
    if change.get("kind") == "changed":
        title = "GDUT 成绩更新"
        if privacy_mode == NOTIFICATION_PRIVACY_PRIVATE:
            return "GDUT 成绩提醒", "有成绩发生变化，请打开电脑查看。"
        if privacy_mode == NOTIFICATION_PRIVACY_SUMMARY:
            return title, f"{semester} {course_name}: 成绩有变化"
        body = f"{semester} {course_name}: {change.get('old_score', '')} -> {score}"
    else:
        title = "GDUT 新成绩"
        if privacy_mode == NOTIFICATION_PRIVACY_PRIVATE:
            return "GDUT 成绩提醒", "有新成绩，请打开电脑查看。"
        if privacy_mode == NOTIFICATION_PRIVACY_SUMMARY:
            return title, f"{semester} {course_name}: 有新成绩"
        body = f"{semester} {course_name}: {score}"
    return title, body
