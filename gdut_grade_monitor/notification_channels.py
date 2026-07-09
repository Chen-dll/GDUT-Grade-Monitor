from __future__ import annotations

import logging
import smtplib
from copy import deepcopy
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Callable, Protocol

import requests

try:
    import keyring
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    keyring = None

from .constants import KEYRING_SERVICE
from .notify import (
    NOTIFICATION_PRIVACY_DETAILED,
    NOTIFICATION_PRIVACY_MODES,
    NOTIFICATION_PRIVACY_PRIVATE,
    format_change_message,
    WindowsNotifier,
)
from .storage import AppPaths, load_config

HTTP_POST_TIMEOUT_SECONDS = 12
SMTP_TIMEOUT_SECONDS = 15

SECRET_ACCOUNTS = {
    "pushplus": "notification:pushplus:token",
    "serverchan": "notification:serverchan:sendkey",
    "ntfy": "notification:ntfy:token",
    "smtp": "notification:smtp:password",
}

DEFAULT_NOTIFICATIONS = {
    "windows": {"enabled": True, "privacy": NOTIFICATION_PRIVACY_DETAILED},
    "pushplus": {"enabled": False, "privacy": NOTIFICATION_PRIVACY_PRIVATE},
    "serverchan": {"enabled": False, "privacy": NOTIFICATION_PRIVACY_PRIVATE},
    "ntfy": {
        "enabled": False,
        "privacy": NOTIFICATION_PRIVACY_PRIVATE,
        "server_url": "https://ntfy.sh",
        "topic": "",
    },
    "smtp": {
        "enabled": False,
        "privacy": NOTIFICATION_PRIVACY_PRIVATE,
        "host": "",
        "port": 587,
        "username": "",
        "sender": "",
        "recipient": "",
        "security": "starttls",
    },
}

NOTIFICATION_CHANNEL_LABELS = {
    "windows": "Windows 本机通知",
    "pushplus": "PushPlus 微信通知",
    "serverchan": "Server酱 微信通知",
    "ntfy": "ntfy 手机/网页通知",
    "smtp": "邮件 SMTP 通知",
}


def notification_error_message(exc: Exception) -> str:
    message = _redact_notification_detail(str(exc))
    lower = message.lower()
    if isinstance(exc, requests.Timeout):
        return "通知发送超时。请检查网络是否能访问对应通知服务，稍后再试。"
    if isinstance(exc, requests.ConnectionError):
        return "通知服务连接失败。请检查网络、代理、防火墙，或稍后再试。"
    if isinstance(exc, requests.HTTPError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in {401, 403}:
            return "通知服务拒绝访问。请检查 token、SendKey、Bearer token 是否复制完整。"
        if status == 404:
            return "通知服务地址不存在。请检查 ntfy 服务器地址、Topic 或通知服务接口是否正确。"
        return f"通知服务返回 HTTP {status or '错误'}。请稍后重试，或检查对应服务状态。"
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "SMTP 登录失败。请检查邮箱账号和授权码，注意通常要填“授权码”，不是网页登录密码。"
    if isinstance(exc, smtplib.SMTPConnectError):
        return "SMTP 服务器连接失败。请检查服务器地址、端口和连接安全类型。"
    if isinstance(exc, smtplib.SMTPException):
        return "邮件发送失败。请检查 SMTP 服务器、端口、授权码、发件人和收件人。"
    if "pushplus token is not configured" in lower:
        return "PushPlus token 尚未配置。请点“指引”复制 token，填入后保存。"
    if "server chan sendkey is not configured" in lower:
        return "Server酱 SendKey 尚未配置。请点“指引”复制 SendKey，填入后保存。"
    if "ntfy topic is not configured" in lower:
        return "ntfy Topic 尚未配置。请填写一个随机 Topic，并在手机 ntfy App 中订阅同一个 Topic。"
    if "smtp host, sender, and recipient" in lower:
        return "SMTP 配置不完整。请填写 SMTP 服务器、发件人和收件人。"
    if "keyring is required" in lower:
        return "系统凭据服务不可用，无法安全保存通知密钥。请检查 Windows Credential Manager 是否正常。"
    return f"{type(exc).__name__}: {message}"


def _redact_notification_detail(text: str) -> str:
    from .runtime_health import redact_sensitive_detail

    return redact_sensitive_detail(text)


class NotificationChannel(Protocol):
    def send(self, title: str, body: str) -> None:
        ...


@dataclass(frozen=True)
class NotificationSetupCheck:
    channel_id: str
    label: str
    status: str
    summary: str
    detail: str


@dataclass(frozen=True)
class NotificationTestResult:
    channel_id: str
    label: str
    ok: bool
    detail: str


class NotificationSecretStore:
    def __init__(self, service_name: str = KEYRING_SERVICE):
        self.service_name = service_name

    def set_secret(self, channel: str, value: str) -> None:
        self._require_keyring()
        account = self._account(channel)
        if value:
            keyring.set_password(self.service_name, account, value)
        else:
            self.delete_secret(channel)

    def get_secret(self, channel: str) -> str:
        self._require_keyring()
        return keyring.get_password(self.service_name, self._account(channel)) or ""

    def delete_secret(self, channel: str) -> None:
        self._require_keyring()
        try:
            keyring.delete_password(self.service_name, self._account(channel))
        except Exception:
            return

    @staticmethod
    def _account(channel: str) -> str:
        if channel not in SECRET_ACCOUNTS:
            raise ValueError(f"Unsupported notification channel: {channel}")
        return SECRET_ACCOUNTS[channel]

    @staticmethod
    def _require_keyring() -> None:
        if keyring is None:
            raise RuntimeError("keyring is required to store notification secrets securely.")


class PushPlusChannel:
    def __init__(self, token: str, http_post: Callable = requests.post):
        self.token = token
        self.http_post = http_post

    def send(self, title: str, body: str) -> None:
        if not self.token:
            raise ValueError("PushPlus token is not configured.")
        response = self.http_post(
            "https://www.pushplus.plus/send",
            json={"token": self.token, "title": title, "content": body, "template": "txt"},
            timeout=HTTP_POST_TIMEOUT_SECONDS,
        )
        _raise_for_notification_response(response, expected_code=200)


class ServerChanChannel:
    def __init__(self, send_key: str, http_post: Callable = requests.post):
        self.send_key = send_key
        self.http_post = http_post

    def send(self, title: str, body: str) -> None:
        if not self.send_key:
            raise ValueError("Server Chan SendKey is not configured.")
        response = self.http_post(
            f"https://sctapi.ftqq.com/{self.send_key}.send",
            data={"title": title, "desp": body},
            timeout=HTTP_POST_TIMEOUT_SECONDS,
        )
        _raise_for_notification_response(response)


class NtfyChannel:
    def __init__(
        self,
        *,
        server_url: str,
        topic: str,
        token: str = "",
        http_post: Callable = requests.post,
    ):
        self.server_url = (server_url or "https://ntfy.sh").rstrip("/")
        self.topic = topic.strip("/")
        self.token = token
        self.http_post = http_post

    def send(self, title: str, body: str) -> None:
        if not self.topic:
            raise ValueError("ntfy topic is not configured.")
        headers = {"Title": title, "Tags": "mortar_board"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = self.http_post(
            f"{self.server_url}/{self.topic}",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=HTTP_POST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()


class SmtpChannel:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        recipient: str,
        security: str = "starttls",
        smtp_factory: Callable = smtplib.SMTP,
        smtp_ssl_factory: Callable = smtplib.SMTP_SSL,
    ):
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.sender = sender
        self.recipient = recipient
        self.security = security if security in {"starttls", "ssl", "none"} else "starttls"
        self.smtp_factory = smtp_factory
        self.smtp_ssl_factory = smtp_ssl_factory

    def send(self, title: str, body: str) -> None:
        if not self.host or not self.sender or not self.recipient:
            raise ValueError("SMTP host, sender, and recipient must be configured.")
        message = EmailMessage()
        message["Subject"] = title
        message["From"] = self.sender
        message["To"] = self.recipient
        message.set_content(body)

        factory = self.smtp_ssl_factory if self.security == "ssl" else self.smtp_factory
        with factory(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            if self.security == "starttls":
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)


@dataclass
class MultiDeviceNotifier:
    channels: list[tuple[str, NotificationChannel, str]]
    logger: logging.Logger | None = None
    suppress_errors: bool = True

    def send_change(self, change: dict) -> list[NotificationTestResult]:
        results: list[NotificationTestResult] = []
        for channel_id, channel, privacy in self.channels:
            title, body = format_change_message(change, privacy_mode=privacy)
            results.append(self._send_to_channel(channel_id, channel, title, body))
        return results

    def send(self, title: str, body: str) -> list[NotificationTestResult]:
        results: list[NotificationTestResult] = []
        for channel_id, channel, _privacy in self.channels:
            results.append(self._send_to_channel(channel_id, channel, title, body))
        return results

    def send_test(self, title: str, body: str) -> list[NotificationTestResult]:
        results: list[NotificationTestResult] = []
        for channel_id, channel, _privacy in self.channels:
            try:
                channel.send(title, body)
            except Exception as exc:
                results.append(
                    NotificationTestResult(
                        channel_id=channel_id,
                        label=NOTIFICATION_CHANNEL_LABELS.get(channel_id, channel_id),
                        ok=False,
                        detail=notification_error_message(exc),
                    )
                )
            else:
                results.append(
                    NotificationTestResult(
                        channel_id=channel_id,
                        label=NOTIFICATION_CHANNEL_LABELS.get(channel_id, channel_id),
                        ok=True,
                        detail="测试通知已发送。若手机或邮箱未收到，请检查对应 App、邮箱收件箱或第三方服务状态。",
                    )
                )
        return results

    def _send_to_channel(self, channel_id: str, channel: NotificationChannel, title: str, body: str) -> NotificationTestResult:
        try:
            channel.send(title, body)
        except Exception as exc:
            if not self.suppress_errors:
                raise
            logger = self.logger or logging.getLogger("gdut_grade_monitor")
            logger.warning("Notification channel %s failed: %s", channel_id, notification_error_message(exc))
            return NotificationTestResult(
                channel_id=channel_id,
                label=NOTIFICATION_CHANNEL_LABELS.get(channel_id, channel_id),
                ok=False,
                detail=notification_error_message(exc),
            )
        return NotificationTestResult(
            channel_id=channel_id,
            label=NOTIFICATION_CHANNEL_LABELS.get(channel_id, channel_id),
            ok=True,
            detail="已发送",
        )


def notification_config(config: dict) -> dict:
    configured = config.get("notifications", {}) if isinstance(config, dict) else {}
    normalized = deepcopy(DEFAULT_NOTIFICATIONS)
    if isinstance(configured, dict):
        for channel_id, values in configured.items():
            if channel_id not in normalized or not isinstance(values, dict):
                continue
            normalized[channel_id].update(values)
    for values in normalized.values():
        values["enabled"] = bool(values.get("enabled", False))
        if values.get("privacy") not in NOTIFICATION_PRIVACY_MODES:
            values["privacy"] = NOTIFICATION_PRIVACY_PRIVATE
    normalized["windows"]["privacy"] = (
        normalized["windows"].get("privacy")
        if normalized["windows"].get("privacy") in NOTIFICATION_PRIVACY_MODES
        else NOTIFICATION_PRIVACY_DETAILED
    )
    return normalized


def notification_setup_checks(config: dict, secret_store: NotificationSecretStore | None = None) -> list[NotificationSetupCheck]:
    notifications = notification_config(config)
    secret_store = secret_store or NotificationSecretStore()

    def secret(channel: str) -> str:
        try:
            return secret_store.get_secret(channel).strip()
        except Exception:
            return ""

    rows: list[NotificationSetupCheck] = []
    if notifications["windows"].get("enabled"):
        rows.append(
            NotificationSetupCheck(
                "windows",
                "Windows 本机通知",
                "ok",
                "已启用",
                "会通过 Windows 系统通知提醒；不需要额外配置。",
            )
        )
    else:
        rows.append(
            NotificationSetupCheck(
                "windows",
                "Windows 本机通知",
                "disabled",
                "未启用",
                "只关闭本机通知，不影响其他已启用的远程通知。",
            )
        )

    pushplus_secret = secret("pushplus")
    rows.append(
        _remote_secret_check(
            channel_id="pushplus",
            label="PushPlus 微信通知",
            enabled=bool(notifications["pushplus"].get("enabled")),
            secret_value=pushplus_secret,
            missing_summary="缺少 token",
            ok_detail="已保存 token；可点击“发送测试通知”确认微信是否收到。",
            missing_detail="请点“指引”打开 PushPlus 官网，复制 token 后填入并保存。",
        )
    )

    serverchan_secret = secret("serverchan")
    rows.append(
        _remote_secret_check(
            channel_id="serverchan",
            label="Server酱 微信通知",
            enabled=bool(notifications["serverchan"].get("enabled")),
            secret_value=serverchan_secret,
            missing_summary="缺少 SendKey",
            ok_detail="已保存 SendKey；可点击“发送测试通知”确认微信是否收到。",
            missing_detail="请点“指引”打开 Server酱，复制 SendKey 后填入并保存。",
        )
    )

    ntfy = notifications["ntfy"]
    if not ntfy.get("enabled"):
        rows.append(_disabled_check("ntfy", "ntfy 手机/网页通知"))
    elif not str(ntfy.get("server_url") or "").strip():
        rows.append(NotificationSetupCheck("ntfy", "ntfy 手机/网页通知", "warning", "缺少服务器地址", "可使用默认 https://ntfy.sh，或填写自己的 ntfy 服务器。"))
    elif not str(ntfy.get("topic") or "").strip():
        rows.append(NotificationSetupCheck("ntfy", "ntfy 手机/网页通知", "warning", "缺少 Topic", "请填写一个足够随机的 Topic，并在手机 ntfy App 中订阅同一个 Topic。"))
    else:
        rows.append(NotificationSetupCheck("ntfy", "ntfy 手机/网页通知", "ok", "配置完整", "Topic 已填写；Bearer token 是可选项。公共 Topic 建议保持隐私模式。"))

    smtp = notifications["smtp"]
    smtp_missing = []
    if not smtp.get("enabled"):
        rows.append(_disabled_check("smtp", "邮件 SMTP 通知"))
    else:
        if not str(smtp.get("host") or "").strip():
            smtp_missing.append("SMTP 服务器")
        if not str(smtp.get("sender") or smtp.get("username") or "").strip():
            smtp_missing.append("发件人")
        if not str(smtp.get("recipient") or "").strip():
            smtp_missing.append("收件人")
        if str(smtp.get("username") or "").strip() and not secret("smtp"):
            smtp_missing.append("SMTP 密码/授权码")
        if smtp_missing:
            rows.append(
                NotificationSetupCheck(
                    "smtp",
                    "邮件 SMTP 通知",
                    "warning",
                    "缺少 " + "、".join(smtp_missing),
                    "请补齐邮箱 SMTP 配置。多数邮箱需要填写授权码，而不是网页登录密码。",
                )
            )
        else:
            rows.append(NotificationSetupCheck("smtp", "邮件 SMTP 通知", "ok", "配置完整", "SMTP 字段已填写；建议点击“发送测试通知”确认邮箱能收到。"))

    return rows


def _disabled_check(channel_id: str, label: str) -> NotificationSetupCheck:
    return NotificationSetupCheck(channel_id, label, "disabled", "未启用", "当前不会通过此渠道发送提醒。")


def _remote_secret_check(
    *,
    channel_id: str,
    label: str,
    enabled: bool,
    secret_value: str,
    missing_summary: str,
    ok_detail: str,
    missing_detail: str,
) -> NotificationSetupCheck:
    if not enabled:
        return _disabled_check(channel_id, label)
    if not secret_value:
        return NotificationSetupCheck(channel_id, label, "warning", missing_summary, missing_detail)
    return NotificationSetupCheck(channel_id, label, "ok", "密钥已保存", ok_detail)


def build_notifier(
    paths: AppPaths,
    *,
    windows_notifier: NotificationChannel | None = None,
    secret_store: NotificationSecretStore | None = None,
    http_post: Callable = requests.post,
    smtp_factory: Callable = smtplib.SMTP,
    smtp_ssl_factory: Callable = smtplib.SMTP_SSL,
    suppress_errors: bool = True,
) -> MultiDeviceNotifier:
    config = notification_config(load_config(paths))
    secret_store = secret_store or NotificationSecretStore()
    windows_notifier = windows_notifier or WindowsNotifier()
    channels: list[tuple[str, NotificationChannel, str]] = []

    if config["windows"].get("enabled", True):
        channels.append(("windows", windows_notifier, str(config["windows"].get("privacy") or NOTIFICATION_PRIVACY_DETAILED)))

    if config["pushplus"].get("enabled"):
        channels.append(
            (
                "pushplus",
                PushPlusChannel(secret_store.get_secret("pushplus"), http_post=http_post),
                str(config["pushplus"].get("privacy")),
            )
        )

    if config["serverchan"].get("enabled"):
        channels.append(
            (
                "serverchan",
                ServerChanChannel(secret_store.get_secret("serverchan"), http_post=http_post),
                str(config["serverchan"].get("privacy")),
            )
        )

    if config["ntfy"].get("enabled"):
        channels.append(
            (
                "ntfy",
                NtfyChannel(
                    server_url=str(config["ntfy"].get("server_url") or "https://ntfy.sh"),
                    topic=str(config["ntfy"].get("topic") or ""),
                    token=secret_store.get_secret("ntfy"),
                    http_post=http_post,
                ),
                str(config["ntfy"].get("privacy")),
            )
        )

    if config["smtp"].get("enabled"):
        channels.append(
            (
                "smtp",
                SmtpChannel(
                    host=str(config["smtp"].get("host") or ""),
                    port=int(config["smtp"].get("port") or 587),
                    username=str(config["smtp"].get("username") or ""),
                    password=secret_store.get_secret("smtp"),
                    sender=str(config["smtp"].get("sender") or config["smtp"].get("username") or ""),
                    recipient=str(config["smtp"].get("recipient") or ""),
                    security=str(config["smtp"].get("security") or "starttls"),
                    smtp_factory=smtp_factory,
                    smtp_ssl_factory=smtp_ssl_factory,
                ),
                str(config["smtp"].get("privacy")),
            )
        )

    return MultiDeviceNotifier(channels, suppress_errors=suppress_errors)


def _raise_for_notification_response(response, expected_code: int | None = None) -> None:
    response.raise_for_status()
    if expected_code is None:
        return
    try:
        payload = response.json()
    except ValueError:
        return
    if isinstance(payload, dict) and int(payload.get("code", expected_code)) != expected_code:
        raise RuntimeError(str(payload.get("message") or payload))
