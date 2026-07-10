import tempfile
import unittest
from datetime import date
from pathlib import Path

from gdut_grade_monitor.transcript import TRANSCRIPT_NOTICE, build_transcript_html, write_transcript_html


class TranscriptExportTests(unittest.TestCase):
    def test_build_transcript_html_uses_local_snapshot_without_raw_sensitive_fields(self):
        grades = [
            {
                "semester": "202502",
                "course_code": "CS101",
                "course_name": "数据结构",
                "score": "96",
                "credit": "3",
                "raw": {"cjjd": "4.6", "课程性质": "专业基础课", "cookie": "JSESSIONID=secret"},
            },
            {
                "semester": "202401",
                "course_code": "PE",
                "course_name": "体育(4)",
                "score": "100",
                "credit": "1",
                "grade_point": "5",
            },
        ]

        html = build_transcript_html(
            grades,
            {
                "student_id": "3124000864",
                "transcript_name": "陈同学",
                "transcript_college": "自动化学院",
                "transcript_major": "自动化",
                "transcript_class": "自动化24(1)",
                "password": "secret",
            },
            generated_at=date(2026, 7, 8),
        )

        self.assertIn("本地成绩单", html)
        self.assertIn("3124000864", html)
        self.assertIn("陈同学", html)
        self.assertIn("自动化学院", html)
        self.assertIn("2026-07-08", html)
        self.assertIn("数据结构", html)
        self.assertIn("专业基础课", html)
        self.assertIn("平均绩点", html)
        self.assertIn("4.7", html)
        self.assertIn(TRANSCRIPT_NOTICE, html)
        self.assertIn("不会提交成绩单申请", html)
        self.assertNotIn("JSESSIONID", html)
        self.assertNotIn("password", html.lower())
        self.assertLess(html.index("202401"), html.index("202502"))

    def test_build_transcript_html_escapes_course_text(self):
        html = build_transcript_html(
            [{"semester": "202502", "course_name": "<script>alert(1)</script>", "score": "优秀"}],
            {"student_id": "321"},
            generated_at=date(2026, 7, 8),
        )

        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)

    def test_build_transcript_html_uses_pdf_friendly_print_styles(self):
        html = build_transcript_html([], {}, generated_at=date(2026, 7, 8))

        self.assertNotIn("@media screen", html)
        self.assertIn("page-break-inside: avoid", html)
        self.assertIn("background: #ffffff", html)

    def test_build_transcript_html_excludes_zero_score_placeholders_from_average_score(self):
        html = build_transcript_html(
            [
                {"semester": "202502", "course_code": "CS101", "course_name": "数据结构", "score": "0", "credit": "3"},
                {"semester": "202502", "course_code": "CS101", "course_name": "数据结构", "score": "90", "credit": "3"},
                {"semester": "202502", "course_code": "MATH101", "course_name": "高数", "score": "80", "credit": "2"},
            ],
            {},
            generated_at=date(2026, 7, 8),
        )

        self.assertIn("<th>平均成绩</th><td>86</td>", html)
        self.assertIn("<th>参与绩点统计学分</th><td>5</td>", html)

    def test_build_transcript_html_marks_manual_scores(self):
        html = build_transcript_html(
            [
                {
                    "semester": "202502",
                    "course_code": "CS101",
                    "course_name": "数据结构",
                    "score": "88",
                    "credit": "3",
                    "score_source": "manual",
                    "official_score": "0",
                }
            ],
            {},
            generated_at=date(2026, 7, 8),
        )

        self.assertIn("手动补录", html)
        self.assertIn("非官方", html)

    def test_write_transcript_html_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "transcript.html"

            result = write_transcript_html(path, [], {"student_id": "321"})

            self.assertEqual(result, path)
            self.assertTrue(path.exists())
            self.assertIn("暂无成绩快照", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
