import unittest

from gdut_grade_monitor.grades import diff_grades, normalize_grade


class GradeNormalizationTests(unittest.TestCase):
    def test_normalizes_common_grade_fields_without_losing_raw_data(self):
        raw = {
            "xnxqdm": "202502",
            "kcbh": "CS101",
            "kcmc": "数据结构",
            "zcj": "95",
            "xf": "3.5",
            "jd": "4.5",
            "ignored": "kept",
        }

        grade = normalize_grade(raw)

        self.assertEqual(grade["semester"], "202502")
        self.assertEqual(grade["course_code"], "CS101")
        self.assertEqual(grade["course_name"], "数据结构")
        self.assertEqual(grade["score"], "95")
        self.assertEqual(grade["credit"], "3.5")
        self.assertEqual(grade["grade_point"], "4.5")
        self.assertEqual(grade["identity"], "202502|CS101|数据结构")
        self.assertEqual(grade["raw"], raw)

    def test_normalizes_new_education_grade_point_field(self):
        raw = {
            "xnxqdm": "202502",
            "kcbh": "PE004",
            "kcmc": "体育(4)",
            "zcj": "99",
            "xf": "1",
            "cjjd": "4.9",
        }

        grade = normalize_grade(raw)

        self.assertEqual(grade["score"], "99")
        self.assertEqual(grade["credit"], "1")
        self.assertEqual(grade["grade_point"], "4.9")

    def test_handles_missing_and_alternate_grade_fields(self):
        raw = {"xnxqmc": "2025-2026-2", "课程名称": "大学英语", "成绩": "优秀"}

        grade = normalize_grade(raw)

        self.assertEqual(grade["semester"], "2025-2026-2")
        self.assertEqual(grade["course_code"], "")
        self.assertEqual(grade["course_name"], "大学英语")
        self.assertEqual(grade["score"], "优秀")
        self.assertEqual(grade["identity"], "2025-2026-2||大学英语")


class GradeDiffTests(unittest.TestCase):
    def test_first_snapshot_builds_baseline_without_notifications(self):
        current = [normalize_grade({"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"})]

        changes, snapshot = diff_grades(previous_snapshot=None, current_grades=current)

        self.assertEqual(changes, [])
        self.assertEqual(snapshot[current[0]["identity"]]["score"], "95")

    def test_detects_new_grades_once(self):
        previous = {
            "202502|MATH|高数": normalize_grade({"xnxqdm": "202502", "kcbh": "MATH", "kcmc": "高数", "zcj": "88"})
        }
        current = list(previous.values()) + [
            normalize_grade({"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"})
        ]

        changes, snapshot = diff_grades(previous_snapshot=previous, current_grades=current)
        repeat_changes, _ = diff_grades(previous_snapshot=snapshot, current_grades=current)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["kind"], "new")
        self.assertEqual(changes[0]["grade"]["course_name"], "数据结构")
        self.assertEqual(repeat_changes, [])

    def test_detects_changed_scores(self):
        previous = {
            "202502|CS101|数据结构": normalize_grade(
                {"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "暂未录入"}
            )
        }
        current = [
            normalize_grade({"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"})
        ]

        changes, _ = diff_grades(previous_snapshot=previous, current_grades=current)

        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["kind"], "changed")
        self.assertEqual(changes[0]["old_score"], "暂未录入")
        self.assertEqual(changes[0]["grade"]["score"], "95")


if __name__ == "__main__":
    unittest.main()
