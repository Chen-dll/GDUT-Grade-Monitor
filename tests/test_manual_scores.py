import tempfile
import unittest
from pathlib import Path

from gdut_grade_monitor.manual_scores import apply_manual_scores, delete_manual_score, set_manual_score
from gdut_grade_monitor.storage import AppPaths, load_state


class ManualScoreTests(unittest.TestCase):
    def test_manual_score_is_used_only_until_official_positive_score_arrives(self):
        grades = [
            {"identity": "202502|CS101|数据结构", "semester": "202502", "course_name": "数据结构", "score": "0"},
            {"identity": "202502|MATH|高数", "semester": "202502", "course_name": "高数", "score": ""},
            {"identity": "202502|PE4|体育(4)", "semester": "202502", "course_name": "体育(4)", "score": "99"},
        ]
        manual = {
            "202502|CS101|数据结构": {"score": "88"},
            "202502|MATH|高数": {"score": "91"},
            "202502|PE4|体育(4)": {"score": "60"},
        }

        applied = apply_manual_scores(grades, manual)

        self.assertEqual(applied[0]["score"], "88")
        self.assertEqual(applied[0]["official_score"], "0")
        self.assertEqual(applied[0]["manual_score"], "88")
        self.assertEqual(applied[0]["grade_point"], "3.8")
        self.assertEqual(applied[0]["score_source"], "manual")
        self.assertEqual(applied[1]["score"], "91")
        self.assertEqual(applied[1]["score_source"], "manual")
        self.assertEqual(applied[2]["score"], "99")
        self.assertEqual(applied[2]["score_source"], "official")

    def test_manual_score_does_not_replace_official_level_or_deferred_zero_record(self):
        grades = [
            {"identity": "202502|A|形势政策", "semester": "202502", "course_name": "形势政策", "credit": "1", "score": "优秀"},
            {"identity": "202502|B0|数据结构", "semester": "202502", "course_name": "数据结构", "credit": "3", "score": "0"},
            {"identity": "202502|B1|数据结构", "semester": "202502", "course_name": "数据结构", "credit": "3", "score": "88"},
        ]
        manual = {
            "202502|A|形势政策": {"score": "90"},
            "202502|B0|数据结构": {"score": "90"},
        }

        applied = apply_manual_scores(grades, manual)

        self.assertEqual(applied[0]["score"], "优秀")
        self.assertEqual(applied[0]["score_source"], "official")
        self.assertEqual(applied[1]["score"], "0")
        self.assertEqual(applied[1]["score_source"], "official")

    def test_set_and_delete_manual_score_persist_under_state_without_touching_grades(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            set_manual_score(paths, "202502|CS101|数据结构", "88")

            state = load_state(paths)
            self.assertEqual(state["manual_scores"]["202502|CS101|数据结构"]["score"], "88")
            self.assertNotIn("grades", state)

            delete_manual_score(paths, "202502|CS101|数据结构")

            self.assertNotIn("202502|CS101|数据结构", load_state(paths).get("manual_scores", {}))

    def test_manual_score_rejects_invalid_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))

            with self.assertRaises(ValueError):
                set_manual_score(paths, "202502|CS101|数据结构", "优秀")
            with self.assertRaises(ValueError):
                set_manual_score(paths, "202502|CS101|数据结构", "101")


if __name__ == "__main__":
    unittest.main()
