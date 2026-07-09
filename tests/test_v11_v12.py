import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from gdut_grade_monitor.grades import normalize_grade
from gdut_grade_monitor.gui_model import history_table_rows, next_check_summary
from gdut_grade_monitor.monitor import GradeMonitor, _sleep_with_config_refresh, monitor_pause_remaining_seconds
from gdut_grade_monitor.storage import AppPaths, load_config, load_state, save_config, save_state, set_poll_interval


class FakeFetcher:
    def __init__(self, rows):
        self.rows = rows

    def fetch_grades(self):
        return [normalize_grade(row) for row in self.rows]


class FailingFetcher:
    def fetch_grades(self):
        raise RuntimeError("boom")


class FakeClock:
    def __init__(self):
        self.now = 0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class VersionEnhancementTests(unittest.TestCase):
    def test_set_poll_interval_clamps_and_persists_minutes(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))

            config = set_poll_interval(paths, 5)
            too_low = set_poll_interval(paths, 0)
            too_high = set_poll_interval(paths, 9999)

            self.assertEqual(config["poll_interval_minutes"], 5)
            self.assertEqual(too_low["poll_interval_minutes"], 1)
            self.assertEqual(too_high["poll_interval_minutes"], 1440)
            self.assertEqual(load_config(paths)["poll_interval_minutes"], 1440)

    def test_monitor_records_heartbeat_last_check_and_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            config = load_config(paths)
            config["poll_interval_minutes"] = 7
            save_config(paths, config)

            monitor = GradeMonitor(
                paths=paths,
                fetcher=FakeFetcher([{"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"}]),
                notifier=Mock(),
            )

            with patch("gdut_grade_monitor.monitor.now_iso", return_value="2026-07-08T12:00:00"):
                monitor.run_once()
            state = load_state(paths)

            self.assertEqual(state["monitor"]["poll_interval_minutes"], 7)
            self.assertEqual(state["monitor"]["last_check_at"], "2026-07-08T12:00:00")
            self.assertIn("heartbeat_at", state["monitor"])
            self.assertEqual(state["monitor"]["next_check_at"], "2026-07-08T12:07:00")

    def test_monitor_logs_every_successful_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            monitor = GradeMonitor(
                paths=paths,
                fetcher=FakeFetcher([{"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"}]),
                notifier=Mock(),
            )

            with self.assertLogs("gdut_grade_monitor", level="INFO") as logs:
                monitor.run_once()

            log_text = "\n".join(logs.output)
            self.assertIn("Grade check started", log_text)
            self.assertIn("Grade check completed", log_text)
            self.assertIn("grades=1", log_text)
            self.assertIn("changes=0", log_text)

    def test_monitor_sleep_reacts_when_poll_interval_is_shortened(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            config = load_config(paths)
            config["poll_interval_minutes"] = 30
            save_config(paths, config)
            clock = FakeClock()

            def sleeper(seconds):
                clock.sleep(seconds)
                if len(clock.sleeps) == 1:
                    updated = load_config(paths)
                    updated["poll_interval_minutes"] = 5
                    save_config(paths, updated)

            _sleep_with_config_refresh(
                paths,
                initial_interval_seconds=30 * 60,
                sleeper=sleeper,
                monotonic=clock.monotonic,
                max_slice_seconds=60,
            )

            self.assertEqual(clock.now, 5 * 60)
            self.assertTrue(clock.sleeps)
            self.assertLessEqual(max(clock.sleeps), 60)

    def test_monitor_sleep_records_next_check_time_from_runtime_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            config = load_config(paths)
            config["poll_interval_minutes"] = 5
            save_config(paths, config)
            clock = FakeClock()

            _sleep_with_config_refresh(
                paths,
                initial_interval_seconds=5 * 60,
                sleeper=clock.sleep,
                monotonic=clock.monotonic,
                max_slice_seconds=60,
                started_at_wall_iso="2026-07-08T12:00:00",
            )

            state = load_state(paths)
            self.assertEqual(state["monitor"]["next_check_at"], "2026-07-08T12:05:00")

    def test_monitor_records_notification_history_for_changes(self):
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
                fetcher=FakeFetcher(
                    [
                        {"xnxqdm": "202502", "kcbh": "MATH", "kcmc": "高数", "zcj": "88"},
                        {"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"},
                    ]
                ),
                notifier=Mock(),
            )

            changed.run_once()
            state = load_state(paths)

            self.assertEqual(len(state["history"]), 1)
            self.assertEqual(state["history"][0]["course_name"], "数据结构")
            self.assertEqual(state["history"][0]["score"], "95")

    def test_monitor_clears_stale_last_error_after_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            monitor = GradeMonitor(
                paths=paths,
                fetcher=FakeFetcher([{"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"}]),
                notifier=Mock(),
            )

            state = load_state(paths)
            state["last_error"] = "登录已过期"
            save_state(paths, state)

            monitor.run_once()

            self.assertNotIn("last_error", load_state(paths))

    def test_monitor_records_structured_failure_and_resets_after_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            monitor = GradeMonitor(paths=paths, fetcher=FailingFetcher(), notifier=Mock())

            monitor._record_runtime_failure(RuntimeError("boom"))
            monitor._record_runtime_failure(RuntimeError("boom again"))
            failed_state = load_state(paths)

            self.assertEqual(failed_state["monitor"]["consecutive_failures"], 2)
            self.assertEqual(failed_state["monitor"]["last_error_kind"], "unknown")
            self.assertIn("last_failure_at", failed_state["monitor"])
            self.assertEqual(failed_state["last_check_status"], "error")

            recovery = GradeMonitor(
                paths=paths,
                fetcher=FakeFetcher([{"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"}]),
                notifier=Mock(),
            )
            recovery.run_once()
            recovered_state = load_state(paths)

            self.assertEqual(recovered_state["monitor"]["consecutive_failures"], 0)
            self.assertIn("last_success_at", recovered_state["monitor"])
            self.assertNotIn("last_error", recovered_state)

    def test_monitor_pause_remaining_seconds_handles_future_expired_and_invalid_values(self):
        now = "2026-07-08T12:00:00"

        self.assertEqual(monitor_pause_remaining_seconds({"monitor_paused_until": "2026-07-08T13:00:00"}, now_iso=now), 3600)
        self.assertEqual(monitor_pause_remaining_seconds({"monitor_paused_until": "2026-07-08T11:59:00"}, now_iso=now), 0)
        self.assertEqual(monitor_pause_remaining_seconds({"monitor_paused_until": "not-a-date"}, now_iso=now), 0)

    def test_gui_model_formats_next_check_and_history_rows(self):
        state = {
            "monitor": {
                "poll_interval_minutes": 30,
                "last_check_at": "2026-07-08T10:00:00",
                "next_check_at": "2026-07-08T10:37:00",
            },
            "history": [
                {"kind": "new", "semester": "202502", "course_name": "数据结构", "score": "95", "at": "2026-07-08T10:00:00"}
            ],
        }

        self.assertIn("2026-07-08 10:00:00", next_check_summary(state))
        self.assertIn("2026-07-08 10:37:00", next_check_summary(state))
        self.assertEqual(
            history_table_rows(state),
            [("2026-07-08 10:00:00", "新成绩", "202502", "数据结构", "95")],
        )


if __name__ == "__main__":
    unittest.main()
