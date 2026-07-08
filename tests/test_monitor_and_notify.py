import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from gdut_grade_monitor.grades import normalize_grade
from gdut_grade_monitor.monitor import GradeMonitor
from gdut_grade_monitor.notify import format_change_message
from gdut_grade_monitor.storage import AppPaths


class FakeFetcher:
    def __init__(self, rows):
        self.rows = rows

    def fetch_grades(self):
        return [normalize_grade(row) for row in self.rows]


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


if __name__ == "__main__":
    unittest.main()
