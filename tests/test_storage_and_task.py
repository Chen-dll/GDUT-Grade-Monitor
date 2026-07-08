import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from gdut_grade_monitor.auth import (
    PlaywrightBrowserMissingError,
    _is_missing_browser_error,
    find_system_browser,
)
from gdut_grade_monitor.credentials import CredentialStore, PasswordInputError, validate_password_input
from gdut_grade_monitor.storage import AppPaths, load_config, save_config
from gdut_grade_monitor.task import autostart_exists, build_install_command, task_exists
from gdut_grade_monitor.task import (
    build_startup_script,
    build_monitor_command,
    install_task_or_startup,
    startup_script_exists,
    uninstall_task_and_startup,
)


class StorageAndTaskTests(unittest.TestCase):
    def test_config_does_not_store_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))

            save_config(paths, {"student_id": "3210000000", "password": "secret", "poll_interval_minutes": 30})
            saved = json.loads(paths.config_file.read_text(encoding="utf-8"))

            self.assertEqual(saved["student_id"], "3210000000")
            self.assertEqual(saved["poll_interval_minutes"], 30)
            self.assertNotIn("password", saved)
            self.assertNotIn("secret", paths.config_file.read_text(encoding="utf-8"))

    def test_default_config_uses_thirty_minutes(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = load_config(AppPaths(Path(tmp)))

            self.assertEqual(config["poll_interval_minutes"], 30)

    @patch("gdut_grade_monitor.credentials.keyring")
    def test_credentials_use_keyring_service_without_returning_password_to_config(self, keyring_mock):
        keyring_mock.get_password.return_value = "secret"
        store = CredentialStore(service_name="gdut-grade-monitor")

        store.set_credentials("3210000000", "secret")
        password = store.get_password("3210000000")

        keyring_mock.set_password.assert_called_once_with("gdut-grade-monitor", "3210000000", "secret")
        self.assertEqual(password, "secret")

    def test_password_validation_rejects_cjk_or_full_width_input(self):
        with self.assertRaises(PasswordInputError):
            validate_password_input("密码abc")
        with self.assertRaises(PasswordInputError):
            validate_password_input("abc１２３")

        self.assertEqual(validate_password_input("abc123!@#"), "abc123!@#")

    @patch("gdut_grade_monitor.credentials.keyring")
    def test_credentials_do_not_save_password_with_cjk_or_full_width_input(self, keyring_mock):
        store = CredentialStore(service_name="gdut-grade-monitor")

        with self.assertRaises(PasswordInputError):
            store.set_credentials("3210000000", "密码abc")

        keyring_mock.set_password.assert_not_called()

    def test_install_command_uses_pythonw_module_monitor(self):
        command = build_install_command(task_name="GDUT Grade Monitor", pythonw="C:/Python/pythonw.exe")

        self.assertIn("/Create", command)
        self.assertIn("/SC", command)
        self.assertIn("ONLOGON", command)
        self.assertIn("C:/Python/pythonw.exe -m gdut_grade_monitor monitor", command)

    def test_install_command_quotes_pythonw_path_with_spaces(self):
        command = build_install_command(
            task_name="GDUT Grade Monitor",
            pythonw="F:/Program Files/Python314/pythonw.exe",
        )

        self.assertIn('"F:/Program Files/Python314/pythonw.exe" -m gdut_grade_monitor monitor', command)

    @patch("gdut_grade_monitor.task.subprocess.run")
    def test_task_status_is_read_only_query(self, run_mock):
        run_mock.return_value = Mock(returncode=0)

        self.assertTrue(task_exists("GDUT Grade Monitor"))

        args = run_mock.call_args.args[0]
        self.assertEqual(args[:3], ["schtasks", "/Query", "/TN"])
        self.assertTrue(run_mock.call_args.kwargs.get("capture_output"))
        self.assertIn("timeout", run_mock.call_args.kwargs)

    def test_startup_script_runs_pythonw_monitor_hidden(self):
        script = build_startup_script("F:/Program Files/Python314/pythonw.exe")

        self.assertIn('CreateObject("WScript.Shell")', script)
        self.assertIn('""F:/Program Files/Python314/pythonw.exe"" -m gdut_grade_monitor monitor', script)
        self.assertIn(", 0, False", script)

    def test_monitor_command_uses_frozen_exe_when_packaged(self):
        with patch("gdut_grade_monitor.task.is_frozen", return_value=True):
            with patch("gdut_grade_monitor.task.sys.executable", "C:/Apps/GDUTGradeMonitor.exe"):
                command = build_monitor_command()

        self.assertEqual(command, '"C:/Apps/GDUTGradeMonitor.exe" --monitor')

    @patch("gdut_grade_monitor.task.subprocess.run")
    def test_install_falls_back_to_startup_script_when_schtasks_access_denied(self, run_mock):
        run_mock.return_value = Mock(returncode=1, stdout="", stderr="ERROR: Access is denied.")
        with tempfile.TemporaryDirectory() as tmp:
            result = install_task_or_startup(startup_dir=Path(tmp), pythonw="C:/Python/pythonw.exe")

            self.assertEqual(result.mode, "startup")
            self.assertTrue((Path(tmp) / "GDUT Grade Monitor.vbs").exists())
            self.assertTrue(startup_script_exists(Path(tmp)))

    @patch("gdut_grade_monitor.task.subprocess.run")
    def test_prefer_startup_script_avoids_schtasks(self, run_mock):
        with tempfile.TemporaryDirectory() as tmp:
            result = install_task_or_startup(
                startup_dir=Path(tmp),
                pythonw="C:/Python/pythonw.exe",
                prefer_startup=True,
            )

            self.assertEqual(result.mode, "startup")
            self.assertTrue(startup_script_exists(Path(tmp)))
            run_mock.assert_not_called()

    @patch("gdut_grade_monitor.task.subprocess.run")
    def test_uninstall_removes_startup_script_even_when_schtasks_delete_fails(self, run_mock):
        run_mock.return_value = Mock(returncode=1, stdout="", stderr="ERROR: The system cannot find the file specified.")
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "GDUT Grade Monitor.vbs"
            script.write_text("x", encoding="utf-8")

            result = uninstall_task_and_startup(startup_dir=Path(tmp))

            self.assertEqual(result.mode, "startup")
            self.assertFalse(script.exists())

    @patch("gdut_grade_monitor.task.subprocess.run")
    def test_skip_schtasks_uninstall_removes_startup_without_querying_task_scheduler(self, run_mock):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "GDUT Grade Monitor.vbs"
            script.write_text("x", encoding="utf-8")

            result = uninstall_task_and_startup(startup_dir=Path(tmp), skip_schtasks=True)

            self.assertEqual(result.mode, "startup")
            self.assertEqual(result.returncode, 0)
            self.assertFalse(script.exists())
            run_mock.assert_not_called()

    @patch("gdut_grade_monitor.task.subprocess.run")
    def test_safe_autostart_check_does_not_query_schtasks_by_default(self, run_mock):
        run_mock.return_value = Mock(returncode=0)

        with patch("gdut_grade_monitor.task.startup_script_exists", return_value=False):
            self.assertFalse(autostart_exists())
        run_mock.assert_not_called()

    def test_missing_playwright_browser_error_is_detected(self):
        error = RuntimeError("Executable doesn't exist at C:/ms-playwright/chrome.exe\nplaywright install")

        self.assertTrue(_is_missing_browser_error(error))
        self.assertIn("python -m playwright install chromium", str(PlaywrightBrowserMissingError()))

    def test_find_system_browser_returns_first_existing_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.exe"
            existing = Path(tmp) / "chrome.exe"
            existing.write_text("", encoding="utf-8")

            self.assertEqual(find_system_browser([missing, existing]), str(existing))


if __name__ == "__main__":
    unittest.main()
