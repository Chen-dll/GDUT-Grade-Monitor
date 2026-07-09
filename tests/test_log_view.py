import logging
import tempfile
import unittest
from pathlib import Path

from gdut_grade_monitor.cli import _configure_logging
from gdut_grade_monitor.log_view import sanitize_log_text, write_log_view_file
from gdut_grade_monitor.storage import AppPaths


class LogViewTests(unittest.TestCase):
    def test_configure_logging_writes_utf8_and_suppresses_keyring_backend_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            root = logging.getLogger()
            old_handlers = root.handlers[:]
            old_level = root.level
            old_keyring_level = logging.getLogger("keyring.backend").level
            for handler in old_handlers:
                root.removeHandler(handler)
            try:
                _configure_logging(paths)
                logging.getLogger("gdut_grade_monitor").info("中文日志正常")
                for handler in root.handlers:
                    handler.flush()

                self.assertIn("中文日志正常", paths.log_file.read_text(encoding="utf-8"))
                self.assertEqual(logging.getLogger("keyring.backend").level, logging.CRITICAL)
            finally:
                for handler in root.handlers[:]:
                    handler.close()
                    root.removeHandler(handler)
                for handler in old_handlers:
                    root.addHandler(handler)
                root.setLevel(old_level)
                logging.getLogger("keyring.backend").setLevel(old_keyring_level)

    def test_log_view_hides_packaged_keyring_optional_backend_tracebacks(self):
        raw = "\n".join(
            [
                "2026-07-09 20:06:49,664 [ERROR] keyring.backend: Error initializing plugin EntryPoint(name='KWallet')",
                "Traceback (most recent call last):",
                "  File \"keyring\\backend.py\", line 244, in _load_plugins",
                "ModuleNotFoundError: No module named 'keyring.backends.kwallet'",
                "2026-07-09 20:07:00,000 [INFO] gdut_grade_monitor: Grade check started",
                "2026-07-09 20:07:01,000 [INFO] gdut_grade_monitor: 成绩检查完成",
            ]
        )

        cleaned = sanitize_log_text(raw)

        self.assertNotIn("KWallet", cleaned)
        self.assertNotIn("ModuleNotFoundError", cleaned)
        self.assertIn("已隐藏 1 段", cleaned)
        self.assertIn("2026-07-09 20:07:00 开始检查成绩", cleaned)
        self.assertIn("成绩检查完成", cleaned)

    def test_log_view_formats_grade_checks_for_normal_users(self):
        raw = "\n".join(
            [
                "2026-07-09 20:06:51,462 [INFO] gdut_grade_monitor: Grade check started",
                "2026-07-09 20:06:52,467 [INFO] gdut_grade_monitor: Grade check completed: grades=42 changes=0",
                "2026-07-09 20:25:35,449 [INFO] gdut_grade_monitor: Grade check started",
                "2026-07-09 20:25:36,499 [INFO] gdut_grade_monitor: Grade check completed: grades=43 changes=1",
                "2026-07-09 20:26:00,000 [ERROR] gdut_grade_monitor: Grade check failed: network down",
            ]
        )

        cleaned = sanitize_log_text(raw)

        self.assertIn("GDUT 成绩提醒运行日志", cleaned)
        self.assertIn("2026-07-09 20:06:51 开始检查成绩", cleaned)
        self.assertIn("2026-07-09 20:06:52 检查完成：共 42 门课程，未发现变化。", cleaned)
        self.assertIn("2026-07-09 20:25:36 检查完成：共 43 门课程，发现 1 项变化。", cleaned)
        self.assertIn("2026-07-09 20:26:00 检查失败：network down", cleaned)
        self.assertNotIn("Grade check completed", cleaned)

    def test_write_log_view_file_reads_legacy_bytes_with_replacement_and_writes_utf8_sig(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            paths.ensure()
            paths.log_file.write_bytes("2026 日志: \xff\n".encode("utf-8", errors="ignore") + b"\xff")

            view_file = write_log_view_file(paths)

            self.assertIsNotNone(view_file)
            self.assertEqual(view_file.name, "monitor-view.log")
            self.assertIn("2026 日志", view_file.read_text(encoding="utf-8-sig"))


if __name__ == "__main__":
    unittest.main()
