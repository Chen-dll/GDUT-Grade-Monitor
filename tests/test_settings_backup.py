import json
import tempfile
import unittest
from pathlib import Path

from gdut_grade_monitor.settings_backup import export_settings, import_settings
from gdut_grade_monitor.storage import AppPaths, load_config, reset_config, save_config


class SettingsBackupTests(unittest.TestCase):
    def test_export_settings_writes_only_non_sensitive_configuration(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp) / "data")
            save_config(
                paths,
                {
                    "student_id": "3210000000",
                    "poll_interval_minutes": 15,
                    "monitor_paused_until": "2026-07-09T12:00:00",
                    "notifications": {
                        "pushplus": {"enabled": True, "privacy": "summary", "token": "secret-token"},
                        "ntfy": {"enabled": True, "topic": "gdut-private-topic", "token": "secret-token"},
                    },
                    "password": "secret-password",
                },
            )

            output = Path(tmp) / "settings.json"
            export_settings(paths, output)

            text = output.read_text(encoding="utf-8")
            payload = json.loads(text)
            self.assertEqual(payload["kind"], "gdut-grade-monitor-settings")
            self.assertEqual(payload["version"], 1)
            self.assertEqual(payload["config"]["poll_interval_minutes"], 15)
            self.assertTrue(payload["config"]["notifications"]["pushplus"]["enabled"])
            self.assertNotIn("student_id", payload["config"])
            self.assertNotIn("monitor_paused_until", payload["config"])
            self.assertNotIn("password", text)
            self.assertNotIn("secret-token", text)
            self.assertNotIn("3210000000", text)

    def test_import_settings_merges_safe_values_and_preserves_local_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp) / "data")
            save_config(paths, {"student_id": "3210000000", "first_run_wizard_seen": True})
            source = Path(tmp) / "settings.json"
            source.write_text(
                json.dumps(
                    {
                        "kind": "gdut-grade-monitor-settings",
                        "version": 1,
                        "config": {
                            "student_id": "9999999999",
                            "poll_interval_minutes": 45,
                            "notifications": {
                                "windows": {"enabled": False, "privacy": "private"},
                                "pushplus": {"enabled": True, "privacy": "summary", "token": "leak"},
                            },
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            config = import_settings(paths, source)

            self.assertEqual(config["student_id"], "3210000000")
            self.assertTrue(config["first_run_wizard_seen"])
            self.assertEqual(config["poll_interval_minutes"], 45)
            self.assertTrue(config["notifications"]["pushplus"]["enabled"])
            self.assertEqual(config["notifications"]["pushplus"]["privacy"], "summary")
            self.assertNotIn("token", paths.config_file.read_text(encoding="utf-8"))

    def test_reset_config_restores_defaults_without_forgetting_saved_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            save_config(
                paths,
                {
                    "student_id": "3210000000",
                    "first_run_wizard_seen": True,
                    "poll_interval_minutes": 5,
                    "monitor_paused_until": "2026-07-09T12:00:00",
                    "notifications": {"windows": {"enabled": False, "privacy": "private"}},
                },
            )

            config = reset_config(paths)

            self.assertEqual(config["student_id"], "3210000000")
            self.assertTrue(config["first_run_wizard_seen"])
            self.assertEqual(config["poll_interval_minutes"], 30)
            self.assertTrue(config["notifications"]["windows"]["enabled"])
            self.assertNotIn("monitor_paused_until", config)


if __name__ == "__main__":
    unittest.main()
