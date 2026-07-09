import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from gdut_grade_monitor.grades import normalize_grade
from gdut_grade_monitor.monitor import GradeMonitor
from gdut_grade_monitor.notification_channels import NotificationTestResult
from gdut_grade_monitor.notify import NOTIFICATION_PRIVACY_DETAILED, NOTIFICATION_PRIVACY_PRIVATE, NOTIFICATION_PRIVACY_SUMMARY
from gdut_grade_monitor.notify import format_change_message
from gdut_grade_monitor.storage import AppPaths, load_state


class FakeFetcher:
    def __init__(self, rows):
        self.rows = rows

    def fetch_grades(self):
        return [normalize_grade(row) for row in self.rows]


class ChangeAwareNotifier:
    def __init__(self):
        self.changes = []
        self.sent = []

    def send_change(self, change):
        self.changes.append(change)

    def send(self, title, body):
        self.sent.append((title, body))


class ResultReturningNotifier(ChangeAwareNotifier):
    def send_change(self, change):
        super().send_change(change)
        return [
            NotificationTestResult("windows", "Windows 本机通知", True, "已发送"),
            NotificationTestResult("pushplus", "PushPlus 微信通知", False, "token 无效"),
        ]


class RaisingNotifier(ChangeAwareNotifier):
    def send_change(self, change):
        super().send_change(change)
        raise RuntimeError("pushplus failed")


class SecretRaisingNotifier(ChangeAwareNotifier):
    def send_change(self, change):
        super().send_change(change)
        raise RuntimeError("pushplus failed token=abc123SECRET bearer qwertySECRET")


class MonitorAndNotifyTests(unittest.TestCase):
    def test_monitor_baselines_first_run_and_notifies_new_grade_later(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            notifier = Mock()
            first = GradeMonitor(
                paths=paths,
                fetcher=FakeFetcher([{"xnxqdm": "202502", "kcbh": "MATH", "kcmc": "高数", "zcj": "88"}]),
                notifier=notifier,
            )

            first.run_once()
            notifier.send.assert_not_called()

            second = GradeMonitor(
                paths=paths,
                fetcher=FakeFetcher(
                    [
                        {"xnxqdm": "202502", "kcbh": "MATH", "kcmc": "高数", "zcj": "88"},
                        {"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"},
                    ]
                ),
                notifier=notifier,
            )

            changes = second.run_once()

            self.assertEqual(len(changes), 1)
            notifier.send.assert_called_once()

    def test_notification_message_excludes_student_id_and_cookie(self):
        change = {
            "kind": "new",
            "grade": normalize_grade(
                {
                    "xnxqdm": "202502",
                    "kcbh": "CS101",
                    "kcmc": "数据结构",
                    "zcj": "95",
                    "xh": "3210000000",
                    "cookie": "JSESSIONID=secret",
                }
            ),
        }

        title, body = format_change_message(change)

        self.assertIn("新成绩", title)
        self.assertIn("数据结构", body)
        self.assertIn("95", body)
        self.assertNotIn("3210000000", body)
        self.assertNotIn("JSESSIONID", body)

    def test_notification_message_private_mode_hides_course_and_score(self):
        change = {
            "kind": "new",
            "grade": normalize_grade({"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"}),
        }

        title, body = format_change_message(change, privacy_mode=NOTIFICATION_PRIVACY_PRIVATE)

        self.assertIn("成绩提醒", title)
        self.assertIn("有新成绩", body)
        self.assertIn("打开电脑查看", body)
        self.assertNotIn("数据结构", body)
        self.assertNotIn("95", body)

    def test_notification_message_summary_mode_hides_score_but_keeps_course(self):
        change = {
            "kind": "changed",
            "old_score": "88",
            "grade": normalize_grade({"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"}),
        }

        title, body = format_change_message(change, privacy_mode=NOTIFICATION_PRIVACY_SUMMARY)

        self.assertIn("成绩更新", title)
        self.assertIn("202502", body)
        self.assertIn("数据结构", body)
        self.assertIn("成绩有变化", body)
        self.assertNotIn("88", body)
        self.assertNotIn("95", body)

    def test_notification_message_detailed_mode_keeps_existing_content(self):
        change = {
            "kind": "changed",
            "old_score": "88",
            "grade": normalize_grade({"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"}),
        }

        title, body = format_change_message(change, privacy_mode=NOTIFICATION_PRIVACY_DETAILED)

        self.assertIn("成绩更新", title)
        self.assertIn("数据结构", body)
        self.assertIn("88 -> 95", body)

    def test_monitor_prefers_send_change_when_notifier_supports_per_channel_privacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            notifier = ChangeAwareNotifier()
            baseline = GradeMonitor(
                paths=paths,
                fetcher=FakeFetcher([{"xnxqdm": "202502", "kcbh": "MATH", "kcmc": "高数", "zcj": "88"}]),
                notifier=notifier,
            )
            baseline.run_once()

            changed = GradeMonitor(
                paths=paths,
                fetcher=FakeFetcher([{"xnxqdm": "202502", "kcbh": "MATH", "kcmc": "高数", "zcj": "89"}]),
                notifier=notifier,
            )
            changed.run_once()

            self.assertEqual(len(notifier.changes), 1)
            self.assertEqual(notifier.sent, [])

    def test_monitor_records_per_channel_delivery_results_in_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            baseline = GradeMonitor(
                paths=paths,
                fetcher=FakeFetcher([{"xnxqdm": "202502", "kcbh": "MATH", "kcmc": "高数", "zcj": "88"}]),
                notifier=ResultReturningNotifier(),
            )
            baseline.run_once()

            notifier = ResultReturningNotifier()
            changed = GradeMonitor(
                paths=paths,
                fetcher=FakeFetcher([{"xnxqdm": "202502", "kcbh": "MATH", "kcmc": "高数", "zcj": "89"}]),
                notifier=notifier,
            )
            changed.run_once()

            history = load_state(paths)["history"]
            self.assertEqual(history[0]["course_name"], "高数")
            self.assertEqual(
                history[0]["delivery"],
                [
                    {"channel_id": "windows", "label": "Windows 本机通知", "ok": True, "detail": "已发送"},
                    {"channel_id": "pushplus", "label": "PushPlus 微信通知", "ok": False, "detail": "token 无效"},
                ],
            )

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
            self.assertEqual(state["grades"]["202502|MATH|高数"]["score"], "89")
            self.assertEqual(state["last_check_status"], "notification_failed")
            self.assertEqual(state["monitor"]["last_error_kind"], "notification_failed")
            self.assertIn("last_notification_failure_at", state["monitor"])

    def test_notification_exception_details_are_redacted_before_state_and_logs(self):
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
                notifier=SecretRaisingNotifier(),
            )

            with self.assertLogs("gdut_grade_monitor", level="WARNING") as logs:
                changed.run_once()

            state_text = str(load_state(paths))
            log_text = "\n".join(logs.output)
            self.assertNotIn("abc123SECRET", state_text)
            self.assertNotIn("qwertySECRET", state_text)
            self.assertNotIn("abc123SECRET", log_text)
            self.assertNotIn("qwertySECRET", log_text)
            self.assertIn("<redacted>", state_text)


if __name__ == "__main__":
    unittest.main()
