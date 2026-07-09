import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from gdut_grade_monitor.grades import normalize_grade
from gdut_grade_monitor.notification_channels import (
    NotificationSecretStore,
    MultiDeviceNotifier,
    NtfyChannel,
    PushPlusChannel,
    ServerChanChannel,
    SmtpChannel,
    build_notifier,
    notification_error_message,
    notification_config,
    notification_setup_checks,
)
from gdut_grade_monitor.notify import NOTIFICATION_PRIVACY_DETAILED, NOTIFICATION_PRIVACY_PRIVATE, NOTIFICATION_PRIVACY_SUMMARY
from gdut_grade_monitor.storage import AppPaths, load_config, save_config


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {"code": 200, "message": "ok"}
        self.text = "ok"

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSMTP:
    def __init__(self, host, port, timeout=10):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args = None
        self.messages = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.closed = True

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.messages.append(message)


class NotificationChannelTests(unittest.TestCase):
    def test_notification_config_defaults_remote_channels_to_private(self):
        config = notification_config({})

        self.assertTrue(config["windows"]["enabled"])
        self.assertEqual(config["windows"]["privacy"], NOTIFICATION_PRIVACY_DETAILED)
        self.assertFalse(config["pushplus"]["enabled"])
        self.assertEqual(config["pushplus"]["privacy"], NOTIFICATION_PRIVACY_PRIVATE)
        self.assertEqual(config["ntfy"]["server_url"], "https://ntfy.sh")

    def test_notification_secret_store_uses_channel_specific_keyring_accounts(self):
        with patch("gdut_grade_monitor.notification_channels.keyring") as keyring_mock:
            store = NotificationSecretStore(service_name="gdut-grade-monitor-test")

            store.set_secret("pushplus", "token-123")
            value = store.get_secret("pushplus")
            store.delete_secret("pushplus")

        keyring_mock.set_password.assert_called_once_with(
            "gdut-grade-monitor-test", "notification:pushplus:token", "token-123"
        )
        keyring_mock.get_password.assert_called_once_with("gdut-grade-monitor-test", "notification:pushplus:token")
        keyring_mock.delete_password.assert_called_once_with("gdut-grade-monitor-test", "notification:pushplus:token")
        self.assertEqual(value, keyring_mock.get_password.return_value)

    def test_pushplus_channel_posts_expected_payload(self):
        post = Mock(return_value=FakeResponse(payload={"code": 200}))
        channel = PushPlusChannel(token="push-token", http_post=post)

        channel.send("标题", "正文")

        post.assert_called_once()
        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        self.assertEqual(url, "https://www.pushplus.plus/send")
        self.assertEqual(payload["token"], "push-token")
        self.assertEqual(payload["title"], "标题")
        self.assertEqual(payload["content"], "正文")
        self.assertEqual(payload["template"], "txt")

    def test_server_chan_channel_posts_expected_payload(self):
        post = Mock(return_value=FakeResponse())
        channel = ServerChanChannel(send_key="send-key", http_post=post)

        channel.send("标题", "正文")

        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "https://sctapi.ftqq.com/send-key.send")
        self.assertEqual(post.call_args.kwargs["data"], {"title": "标题", "desp": "正文"})

    def test_ntfy_channel_posts_topic_message_and_optional_bearer_token(self):
        post = Mock(return_value=FakeResponse())
        channel = NtfyChannel(server_url="https://ntfy.example.com/", topic="gdut-topic", token="secret", http_post=post)

        channel.send("标题", "正文")

        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "https://ntfy.example.com/gdut-topic")
        self.assertEqual(post.call_args.kwargs["data"], "正文".encode("utf-8"))
        self.assertEqual(post.call_args.kwargs["headers"]["Title"], "标题")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer secret")

    def test_smtp_channel_sends_text_email(self):
        created = []

        def smtp_factory(host, port, timeout=10):
            smtp = FakeSMTP(host, port, timeout)
            created.append(smtp)
            return smtp

        channel = SmtpChannel(
            host="smtp.example.com",
            port=587,
            username="user@example.com",
            password="smtp-pass",
            sender="user@example.com",
            recipient="phone@example.com",
            security="starttls",
            smtp_factory=smtp_factory,
        )

        channel.send("成绩提醒", "有新成绩")

        smtp = created[0]
        self.assertEqual((smtp.host, smtp.port), ("smtp.example.com", 587))
        self.assertTrue(smtp.started_tls)
        self.assertEqual(smtp.login_args, ("user@example.com", "smtp-pass"))
        message = smtp.messages[0]
        self.assertEqual(message["Subject"], "成绩提醒")
        self.assertEqual(message["From"], "user@example.com")
        self.assertEqual(message["To"], "phone@example.com")
        self.assertIn("有新成绩", message.get_content())

    def test_multi_device_notifier_uses_per_channel_privacy_and_ignores_remote_failures(self):
        change = {
            "kind": "new",
            "grade": normalize_grade({"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"}),
        }
        windows = Mock()
        private_remote = Mock()
        failing_remote = Mock()
        failing_remote.send.side_effect = RuntimeError("network down")
        notifier = MultiDeviceNotifier(
            channels=[
                ("windows", windows, NOTIFICATION_PRIVACY_DETAILED),
                ("pushplus", private_remote, NOTIFICATION_PRIVACY_PRIVATE),
                ("ntfy", failing_remote, NOTIFICATION_PRIVACY_SUMMARY),
            ]
        )

        notifier.send_change(change)

        windows.send.assert_called_once()
        self.assertIn("数据结构", windows.send.call_args.args[1])
        private_remote.send.assert_called_once()
        self.assertNotIn("数据结构", private_remote.send.call_args.args[1])
        failing_remote.send.assert_called_once()

    def test_multi_device_notifier_strict_mode_raises_for_test_notifications(self):
        failing_remote = Mock()
        failing_remote.send.side_effect = RuntimeError("bad token")
        notifier = MultiDeviceNotifier(
            channels=[("pushplus", failing_remote, NOTIFICATION_PRIVACY_PRIVATE)],
            suppress_errors=False,
        )

        with self.assertRaises(RuntimeError):
            notifier.send("测试", "正文")

    def test_multi_device_notifier_send_test_returns_per_channel_results(self):
        ok_channel = Mock()
        failing_channel = Mock()
        failing_channel.send.side_effect = ValueError("ntfy topic is not configured.")
        notifier = MultiDeviceNotifier(
            channels=[
                ("windows", ok_channel, NOTIFICATION_PRIVACY_DETAILED),
                ("ntfy", failing_channel, NOTIFICATION_PRIVACY_PRIVATE),
            ],
            suppress_errors=False,
        )

        results = notifier.send_test("测试", "正文")

        self.assertEqual([result.channel_id for result in results], ["windows", "ntfy"])
        self.assertTrue(results[0].ok)
        self.assertFalse(results[1].ok)
        self.assertEqual(results[1].label, "ntfy 手机/网页通知")
        self.assertIn("Topic 尚未配置", results[1].detail)
        ok_channel.send.assert_called_once_with("测试", "正文")
        failing_channel.send.assert_called_once_with("测试", "正文")

    def test_build_notifier_creates_enabled_channels_from_config_and_keyring(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            config = load_config(paths)
            config["notifications"] = {
                "windows": {"enabled": True, "privacy": NOTIFICATION_PRIVACY_DETAILED},
                "pushplus": {"enabled": True, "privacy": NOTIFICATION_PRIVACY_PRIVATE},
                "serverchan": {"enabled": True, "privacy": NOTIFICATION_PRIVACY_SUMMARY},
                "ntfy": {"enabled": True, "privacy": NOTIFICATION_PRIVACY_PRIVATE, "topic": "gdut-topic"},
                "smtp": {
                    "enabled": True,
                    "privacy": NOTIFICATION_PRIVACY_PRIVATE,
                    "host": "smtp.example.com",
                    "port": 587,
                    "username": "user@example.com",
                    "sender": "user@example.com",
                    "recipient": "phone@example.com",
                    "security": "starttls",
                },
            }
            save_config(paths, config)
            secret_store = Mock()
            secret_store.get_secret.side_effect = lambda channel: {
                "pushplus": "push-token",
                "serverchan": "send-key",
                "ntfy": "",
                "smtp": "smtp-pass",
            }.get(channel, "")

            notifier = build_notifier(paths, windows_notifier=Mock(), secret_store=secret_store, http_post=Mock())

        channel_ids = [channel_id for channel_id, _, _ in notifier.channels]
        self.assertEqual(channel_ids, ["windows", "pushplus", "serverchan", "ntfy", "smtp"])

    def test_notification_setup_checks_reports_missing_remote_configuration_without_secrets(self):
        config = {
            "notifications": {
                "windows": {"enabled": True},
                "pushplus": {"enabled": True},
                "serverchan": {"enabled": True},
                "ntfy": {"enabled": True, "server_url": "https://ntfy.sh", "topic": ""},
                "smtp": {
                    "enabled": True,
                    "host": "smtp.example.com",
                    "port": 587,
                    "username": "user@example.com",
                    "sender": "user@example.com",
                    "recipient": "",
                    "security": "starttls",
                },
            }
        }
        secret_store = Mock()
        secret_store.get_secret.return_value = ""

        rows = notification_setup_checks(config, secret_store=secret_store)

        by_id = {row.channel_id: row for row in rows}
        self.assertEqual(by_id["windows"].status, "ok")
        self.assertEqual(by_id["pushplus"].summary, "缺少 token")
        self.assertEqual(by_id["serverchan"].summary, "缺少 SendKey")
        self.assertEqual(by_id["ntfy"].summary, "缺少 Topic")
        self.assertIn("收件人", by_id["smtp"].summary)
        self.assertIn("SMTP 密码/授权码", by_id["smtp"].summary)

    def test_notification_setup_checks_marks_configured_channels_ready(self):
        config = {
            "notifications": {
                "pushplus": {"enabled": True},
                "serverchan": {"enabled": True},
                "ntfy": {"enabled": True, "server_url": "https://ntfy.sh", "topic": "gdut-topic"},
                "smtp": {
                    "enabled": True,
                    "host": "smtp.example.com",
                    "port": 587,
                    "username": "user@example.com",
                    "sender": "user@example.com",
                    "recipient": "me@example.com",
                    "security": "starttls",
                },
            }
        }
        secret_store = Mock()
        secret_store.get_secret.side_effect = lambda channel: {
            "pushplus": "push-token",
            "serverchan": "send-key",
            "ntfy": "",
            "smtp": "smtp-pass",
        }.get(channel, "")

        rows = notification_setup_checks(config, secret_store=secret_store)

        self.assertTrue(all(row.status == "ok" for row in rows if row.channel_id != "windows"))

    def test_notification_error_message_adds_actionable_next_steps(self):
        self.assertIn("PushPlus token 尚未配置", notification_error_message(ValueError("PushPlus token is not configured.")))
        self.assertIn("Topic 尚未配置", notification_error_message(ValueError("ntfy topic is not configured.")))
        self.assertIn("SMTP 配置不完整", notification_error_message(RuntimeError("SMTP host, sender, and recipient must be configured.")))


if __name__ == "__main__":
    unittest.main()
