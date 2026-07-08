import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from gdut_grade_monitor.diagnostics import create_diagnostics_zip, mask_student_id, redact_text
from gdut_grade_monitor.doctor import CheckResult
from gdut_grade_monitor.storage import AppPaths, save_config, save_state


class DiagnosticsTests(unittest.TestCase):
    def test_masks_student_id_but_keeps_it_useful_for_support(self):
        self.assertEqual(mask_student_id("3210000000"), "321****000")
        self.assertEqual(mask_student_id("12345"), "1***5")
        self.assertEqual(mask_student_id(""), "")

    def test_redacts_sensitive_words_and_long_student_ids_from_text(self):
        text = "student 3210000000 cookie=JSESSIONID=secret password=abc token=xyz"

        redacted = redact_text(text)

        self.assertIn("321****000", redacted)
        self.assertNotIn("3210000000", redacted)
        self.assertNotIn("JSESSIONID=secret", redacted)
        self.assertNotIn("password=abc", redacted)
        self.assertNotIn("token=xyz", redacted)

    def test_diagnostics_zip_contains_support_summary_without_secrets_or_grades(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp) / "data")
            paths.ensure()
            save_config(
                paths,
                {
                    "student_id": "3210000000",
                    "password": "secret",
                    "cookie": "JSESSIONID=secret",
                    "poll_interval_minutes": 30,
                },
            )
            save_state(
                paths,
                {
                    "grades": {
                        "202502|CS101|数据结构": {
                            "course_name": "数据结构",
                            "score": "95",
                            "raw": {"xh": "3210000000", "cookie": "JSESSIONID=secret"},
                        }
                    },
                    "history": [{"course_name": "数据结构", "score": "95"}],
                    "monitor": {"last_check_at": "2026-07-08T01:00:00"},
                },
            )
            paths.log_file.write_text(
                "failed for 3210000000 cookie=JSESSIONID=secret password=abc",
                encoding="utf-8",
            )
            output = Path(tmp) / "diagnostics.zip"

            result = create_diagnostics_zip(
                paths=paths,
                output_path=output,
                check_results=[CheckResult("Python", True, "3.14")],
            )

            self.assertEqual(result, output)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertIn("manifest.json", names)
                self.assertIn("config.json", names)
                self.assertIn("state-summary.json", names)
                self.assertIn("doctor.txt", names)
                self.assertIn("logs/monitor.log", names)
                combined = "\n".join(archive.read(name).decode("utf-8") for name in sorted(names))

            self.assertIn("321****000", combined)
            self.assertIn('"grade_count": 1', combined)
            self.assertNotIn("3210000000", combined)
            self.assertNotIn("JSESSIONID", combined)
            self.assertNotIn("password", combined.lower())
            self.assertNotIn("数据结构", combined)
            self.assertNotIn('"score"', combined)


if __name__ == "__main__":
    unittest.main()
