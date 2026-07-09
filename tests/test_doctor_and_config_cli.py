import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from gdut_grade_monitor.cli import main
from gdut_grade_monitor.doctor import CheckResult, overall_ok, render_results, run_checks
from gdut_grade_monitor.storage import AppPaths, load_config, save_config


class DoctorTests(unittest.TestCase):
    def test_overall_ok_requires_all_required_checks_to_pass(self):
        results = [
            CheckResult("Python", True, "ok", required=True),
            CheckResult("Optional browser", False, "missing", required=False),
        ]
        self.assertTrue(overall_ok(results))

        results.append(CheckResult("keyring", False, "missing", required=True))
        self.assertFalse(overall_ok(results))

    def test_render_results_marks_required_failures(self):
        rendered = render_results(
            [
                CheckResult("Python", True, "3.14", required=True),
                CheckResult("Browser", False, "not found", required=False),
            ]
        )

        self.assertIn("[OK] Python - 3.14", rendered)
        self.assertIn("[WARN] Browser - not found", rendered)

    def test_run_checks_reports_config_and_data_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            config = load_config(paths)
            config["student_id"] = "3210000000"
            save_config(paths, config)

            results = run_checks(paths=paths)
            names = [result.name for result in results]

            self.assertIn("Data directory", names)
            self.assertIn("Configuration", names)

    def test_run_checks_warns_about_stale_portable_startup_residue(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))

            with patch("gdut_grade_monitor.doctor.startup_script_is_stale", return_value=True):
                results = run_checks(paths=paths)

            residue = next(result for result in results if result.name == "Startup residue")
            self.assertFalse(residue.ok)
            self.assertFalse(residue.required)
            self.assertIn("清理残留", residue.message)

    def test_run_checks_warns_about_broken_autostart_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            broken = type("Health", (), {"ok": False, "message": "启动项路径失效，目标文件不存在。"})()
            with patch("gdut_grade_monitor.doctor.startup_health", return_value=broken):
                results = run_checks(paths=paths)

        self.assertIn("Autostart health", [result.name for result in results])
        row = next(result for result in results if result.name == "Autostart health")
        self.assertFalse(row.ok)
        self.assertFalse(row.required)
        self.assertIn("路径失效", row.message)

    def test_run_checks_warns_when_config_enabled_but_no_autostart_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            config = load_config(paths)
            config["startup_enabled"] = True
            save_config(paths, config)
            healthy_empty = type("Health", (), {"ok": True, "message": "未检测到当前用户启动项。"})()
            with patch("gdut_grade_monitor.doctor.autostart_exists", return_value=False):
                with patch("gdut_grade_monitor.doctor.startup_health", return_value=healthy_empty):
                    results = run_checks(paths=paths)

        row = next(result for result in results if result.name == "Autostart health")
        self.assertFalse(row.ok)
        self.assertIn("配置显示已开启", row.message)


class ConfigCliTests(unittest.TestCase):
    def test_config_show_outputs_non_sensitive_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            save_config(paths, {"student_id": "3210000000", "password": "secret", "poll_interval_minutes": 30})
            runner = CliRunner()

            with patch("gdut_grade_monitor.cli._paths", return_value=paths):
                result = runner.invoke(main, ["config", "show"])

            self.assertEqual(result.exit_code, 0)
            self.assertIn("321****000", result.output)
            self.assertNotIn("3210000000", result.output)
            self.assertIn("poll_interval_minutes", result.output)
            self.assertNotIn("secret", result.output)

    def test_doctor_command_exits_zero_when_required_checks_pass(self):
        runner = CliRunner()
        fake_results = [CheckResult("Python", True, sys.version.split()[0], required=True)]

        with patch("gdut_grade_monitor.cli.run_checks", return_value=fake_results):
            result = runner.invoke(main, ["doctor"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("[OK] Python", result.output)

    def test_doctor_command_exits_nonzero_when_required_checks_fail(self):
        runner = CliRunner()
        fake_results = [CheckResult("keyring", False, "missing", required=True)]

        with patch("gdut_grade_monitor.cli.run_checks", return_value=fake_results):
            result = runner.invoke(main, ["doctor"])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("[FAIL] keyring", result.output)

    def test_diagnostics_export_command_writes_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp) / "data")
            output = Path(tmp) / "support.zip"
            runner = CliRunner()

            with patch("gdut_grade_monitor.cli._paths", return_value=paths):
                with patch("gdut_grade_monitor.cli.run_checks", return_value=[CheckResult("Python", True, "3.14")]):
                    result = runner.invoke(main, ["diagnostics", "export", "--output", str(output)])

            self.assertEqual(result.exit_code, 0)
            self.assertTrue(output.exists())
            self.assertIn(str(output), result.output)

    def test_task_install_reports_run_key_fallback(self):
        runner = CliRunner()
        result_obj = type("InstallResult", (), {"mode": "run-key", "returncode": 0, "stdout": "", "stderr": ""})()
        with patch("gdut_grade_monitor.cli.install_task_or_startup", return_value=result_obj):
            result = runner.invoke(main, ["task", "install"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("Run", result.output)


if __name__ == "__main__":
    unittest.main()
