from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from requests import ConnectionError, Timeout

from .auth import PlaywrightBrowserMissingError
from .client import GradeResponseError


@dataclass(frozen=True)
class RuntimeIssue:
    kind: str
    summary: str
    action: str
    severity: str = "warning"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def classify_error(exc: BaseException) -> RuntimeIssue:
    text = str(exc)
    if isinstance(exc, PlaywrightBrowserMissingError):
        return RuntimeIssue("browser_missing", "浏览器组件缺失", "请在设置页重新进行一键配置，或安装 Chrome/Edge。", "error")
    if isinstance(exc, (Timeout, ConnectionError)):
        return RuntimeIssue("network", "网络连接异常", "请检查网络、校园网或代理设置，稍后会自动重试。")
    if isinstance(exc, GradeResponseError):
        haystack = " ".join(
            [
                text,
                str(getattr(exc, "url", "") or ""),
                str(getattr(exc, "snippet", "") or ""),
            ]
        ).lower()
        if "authserver" in haystack or "统一身份认证" in haystack or "login" in haystack:
            return RuntimeIssue("login_expired", "登录状态可能已过期", "请点击重新登录/初始化，完成统一身份认证。", "error")
        return RuntimeIssue("school_system", "学校系统响应异常", "可能是教务系统临时异常，请稍后重试或导出诊断包。")
    return RuntimeIssue("unknown", "未知运行异常", "请导出诊断包并反馈错误摘要。", "error")


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
    for key in ("last_error_kind", "last_error_summary", "last_error_action"):
        monitor.pop(key, None)
    state["last_check_status"] = "ok"
    state.pop("last_error", None)


def record_monitor_failure(
    state: dict,
    exc: BaseException,
    *,
    checked_at: str,
    poll_interval_minutes: int,
) -> RuntimeIssue:
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


def notification_issue() -> RuntimeIssue:
    return RuntimeIssue("notification_failed", "通知渠道发送失败", "成绩检查已完成，请到多设备通知里检查失败渠道。")


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


def autostart_issue() -> RuntimeIssue:
    return RuntimeIssue("autostart_broken", "自启动路径失效", "请在设置页点击安装/修复自启动。")
