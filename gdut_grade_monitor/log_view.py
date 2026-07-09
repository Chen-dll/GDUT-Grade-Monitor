from __future__ import annotations

import re
from pathlib import Path

from .storage import AppPaths

LOG_RECORD_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}")
KEYRING_OPTIONAL_BACKEND_RE = re.compile(r"keyring\.backend: Error initializing plugin EntryPoint")
LOG_LINE_RE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})(?:,\d+)?\s+"
    r"\[(?P<level>[A-Z]+)\]\s+(?P<logger>[^:]+):\s+(?P<message>.*)$"
)
GRADE_CHECK_COMPLETED_RE = re.compile(r"Grade check completed:\s+grades=(?P<grades>\d+)\s+changes=(?P<changes>\d+)")


def sanitize_log_text(text: str) -> str:
    lines = text.splitlines()
    cleaned: list[str] = []
    hidden_blocks = 0
    skipping_keyring_block = False

    for line in lines:
        is_record_start = bool(LOG_RECORD_RE.match(line))
        if is_record_start and KEYRING_OPTIONAL_BACKEND_RE.search(line):
            hidden_blocks += 1
            skipping_keyring_block = True
            continue
        if skipping_keyring_block:
            if not is_record_start:
                continue
            skipping_keyring_block = False

        cleaned.append(_format_user_log_line(line))

    if cleaned:
        cleaned.insert(0, "GDUT 成绩提醒运行日志")
    if hidden_blocks:
        cleaned.insert(1 if cleaned else 0, f"已隐藏 {hidden_blocks} 段 keyring 可选后端探测日志；这些不是成绩检查错误。")
    return "\n".join(cleaned).strip() + "\n" if cleaned else ""


def _format_user_log_line(line: str) -> str:
    match = LOG_LINE_RE.match(line)
    if not match:
        return line

    timestamp = match.group("time")
    message = match.group("message")
    if message == "Grade check started":
        return f"{timestamp} 开始检查成绩"

    completed = GRADE_CHECK_COMPLETED_RE.fullmatch(message)
    if completed:
        grade_count = int(completed.group("grades"))
        change_count = int(completed.group("changes"))
        change_text = "未发现变化。" if change_count == 0 else f"发现 {change_count} 项变化。"
        return f"{timestamp} 检查完成：共 {grade_count} 门课程，{change_text}"

    if message.startswith("Grade check failed:"):
        return f"{timestamp} 检查失败：{message.split(':', 1)[1].strip()}"

    if message.startswith("Notification failed:"):
        return f"{timestamp} 通知发送失败：{message.split(':', 1)[1].strip()}"

    level = match.group("level")
    return f"{timestamp} [{_level_label(level)}] {message}"


def _level_label(level: str) -> str:
    return {
        "INFO": "信息",
        "WARNING": "警告",
        "ERROR": "错误",
        "CRITICAL": "严重错误",
        "DEBUG": "调试",
    }.get(level, level)


def write_log_view_file(paths: AppPaths) -> Path | None:
    paths.ensure()
    if not paths.log_file.exists():
        return None
    text = paths.log_file.read_text(encoding="utf-8", errors="replace")
    view_file = paths.log_dir / "monitor-view.log"
    view_file.write_text(sanitize_log_text(text), encoding="utf-8-sig")
    return view_file
