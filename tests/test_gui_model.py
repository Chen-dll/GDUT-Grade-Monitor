import unittest

from gdut_grade_monitor.doctor import CheckResult
from gdut_grade_monitor.gui_model import filter_grades, grade_analytics, grade_table_rows, recent_change_rows, semester_options
from gdut_grade_monitor.gui_model import status_summary
from gdut_grade_monitor.gui_model import doctor_table_rows, first_run_wizard_pages, help_sections, onboarding_steps, setup_guidance


class GuiModelTests(unittest.TestCase):
    def test_status_summary_describes_startup_and_last_check(self):
        state = {"last_check_status": "ok", "last_change_count": 2}

        summary = status_summary(startup_installed=True, state=state)

        self.assertIn("自启动: 已安装", summary)
        self.assertIn("检查状态: 正常", summary)
        self.assertIn("变化: 2", summary)

    def test_status_summary_handles_empty_state(self):
        summary = status_summary(startup_installed=False, state={})

        self.assertIn("自启动: 未安装", summary)
        self.assertIn("检查状态: 尚未检查", summary)

    def test_grade_table_rows_sort_by_semester_and_course(self):
        grades = [
            {"semester": "202401", "course_name": "体育", "score": "99", "credit": "1", "grade_point": "4.9"},
            {"semester": "202502", "course_name": "数据结构", "score": "95", "credit": "3", "grade_point": "4.5"},
        ]

        rows = grade_table_rows(grades)

        self.assertEqual(rows[0], ("202502", "数据结构", "95", "3", "4.5"))
        self.assertEqual(rows[1], ("202401", "体育", "99", "1", "4.9"))

    def test_grade_table_rows_derives_gpa_from_numeric_score_when_missing(self):
        rows = grade_table_rows([{"semester": "202502", "course_name": "工程制图", "score": "98", "credit": "2"}])

        self.assertEqual(rows[0], ("202502", "工程制图", "98", "2", "4.8"))

    def test_grade_table_rows_uses_raw_grade_point_before_deriving(self):
        rows = grade_table_rows(
            [
                {
                    "semester": "202502",
                    "course_name": "体育(4)",
                    "score": "99",
                    "credit": "1",
                    "grade_point": "",
                    "raw": {"cjjd": "4.9"},
                }
            ]
        )

        self.assertEqual(rows[0], ("202502", "体育(4)", "99", "1", "4.9"))

    def test_setup_guidance_invites_one_click_setup_for_new_computer(self):
        config = {"student_id": "", "poll_interval_minutes": 30}
        state = {}

        guidance = setup_guidance(startup_installed=False, config=config, state=state, required_checks_ok=True)

        self.assertEqual(guidance["tone"], "warning")
        self.assertEqual(guidance["title"], "需要首次配置")
        self.assertEqual(guidance["primary_action"], "一键配置本机")
        self.assertIn("输入学号和密码", guidance["body"])
        self.assertIn("建立成绩基线", guidance["body"])
        self.assertIn("安装自启动", guidance["body"])

    def test_setup_guidance_prioritizes_required_environment_failure(self):
        config = {"student_id": "3210000000", "poll_interval_minutes": 30}

        guidance = setup_guidance(startup_installed=True, config=config, state={}, required_checks_ok=False)

        self.assertEqual(guidance["tone"], "error")
        self.assertEqual(guidance["title"], "环境需要处理")
        self.assertEqual(guidance["primary_action"], "查看环境检查")

    def test_setup_guidance_reports_ready_state_with_frequency(self):
        config = {"student_id": "3210000000", "poll_interval_minutes": 15}
        state = {
            "grades": {"202502|CS101|数据结构": {"score": "95"}},
            "monitor": {"last_check_at": "2026-07-08T00:30:00"},
        }

        guidance = setup_guidance(startup_installed=True, config=config, state=state, required_checks_ok=True)

        self.assertEqual(guidance["tone"], "ok")
        self.assertEqual(guidance["title"], "现在已经可以后台提醒了")
        self.assertIn("每 15 分钟", guidance["body"])
        self.assertIn("2026-07-08 00:30:00", guidance["body"])

    def test_onboarding_steps_explain_first_run_flow(self):
        text = "\n".join(f"{step['title']} {step['body']}" for step in onboarding_steps())

        self.assertIn("先点击", text)
        self.assertIn("一键配置本机", text)
        self.assertIn("密码不会上传", text)
        self.assertIn("完成浏览器登录", text)
        self.assertIn("建立成绩基线", text)
        self.assertIn("第一次不会提醒", text)
        self.assertIn("后台自动提醒", text)
        self.assertIn("默认每 30 分钟", text)

    def test_first_run_wizard_pages_walk_user_to_setup(self):
        pages = first_run_wizard_pages()
        text = "\n".join(f"{page['title']} {page['body']} {' '.join(page['items'])}" for page in pages)

        self.assertEqual(pages[0]["title"], "欢迎使用 GDUT 成绩提醒")
        self.assertEqual(pages[0]["nav_title"], "欢迎使用")
        self.assertLessEqual(max(len(str(page["nav_title"])) for page in pages), 6)
        self.assertEqual(pages[-1]["primary_action"], "开始一键配置")
        self.assertIn("严格只读", text)
        self.assertIn("密码不会上传", text)
        self.assertIn("第一次不会提醒", text)
        self.assertIn("总览", text)
        self.assertIn("成绩", text)
        self.assertIn("提醒历史", text)
        self.assertIn("设置", text)
        self.assertIn("环境检查", text)
        self.assertIn("默认每 30 分钟", text)

    def test_help_sections_cover_usage_privacy_and_recovery(self):
        parts = []
        for section in help_sections():
            parts.extend([section["title"], section["body"], *section["items"]])
        text = "\n".join(parts)

        self.assertIn("严格只读", text)
        self.assertIn("一键配置本机", text)
        self.assertIn("默认每 30 分钟", text)
        self.assertIn("Windows 凭据管理器", text)
        self.assertIn("官方成绩单", text)
        self.assertIn("不会自动提交", text)
        self.assertIn("环境检查", text)
        self.assertIn("导出诊断包", text)

    def test_doctor_table_rows_adds_human_next_steps(self):
        results = [
            CheckResult("Python", True, "3.14.0"),
            CheckResult("Browser", False, "Chrome/Edge not found", required=False),
            CheckResult("Configuration", False, "student_id not set", required=False),
            CheckResult("Data directory", False, "permission denied", required=True),
        ]

        rows = doctor_table_rows(results)

        self.assertEqual(rows[0], ("正常", "Python", "3.14.0", "无需操作"))
        self.assertEqual(rows[1][0], "提示")
        self.assertIn("安装 Edge 或 Chrome", rows[1][3])
        self.assertIn("一键配置本机", rows[2][3])
        self.assertEqual(rows[3][0], "需要处理")

    def test_grade_analytics_computes_weighted_gpa_trend_and_distribution(self):
        grades = [
            {"semester": "202401", "course_name": "高数", "score": "90", "credit": "2", "grade_point": "4.0"},
            {"semester": "202401", "course_name": "英语", "score": "95", "credit": "1", "grade_point": "4.5"},
            {"semester": "202402", "course_name": "数据结构", "score": "98", "credit": "3", "grade_point": "4.8"},
            {"semester": "202402", "course_name": "等级课", "score": "优秀", "credit": "", "grade_point": ""},
        ]

        analytics = grade_analytics(grades)

        self.assertEqual(analytics["average_gpa"], 4.483)
        self.assertEqual(analytics["course_count"], 4)
        self.assertEqual(analytics["credit_course_count"], 3)
        self.assertEqual(analytics["numeric_gpa_count"], 3)
        self.assertEqual(analytics["counted_credit_total"], 6)
        self.assertEqual(analytics["uncounted_course_count"], 1)
        self.assertEqual(analytics["highest_score"], 98)
        self.assertEqual(analytics["highest_course"], "数据结构")
        self.assertEqual(analytics["semester_trend"], [("202401", 4.167), ("202402", 4.8)])
        self.assertEqual(analytics["distribution"], {"4-5": 3, "3-4": 0, "2-3": 0, "0-2": 0})

    def test_grade_analytics_uses_raw_grade_point_for_existing_snapshots(self):
        grades = [
            {"semester": "202502", "course_name": "数据结构", "score": "96", "credit": "3", "raw": {"cjjd": "4.6"}},
            {"semester": "202502", "course_name": "体育(4)", "score": "99", "credit": "1", "raw": {"cjjd": "4.9"}},
            {"semester": "202502", "course_name": "待出成绩", "score": "", "credit": "1", "raw": {}},
        ]

        analytics = grade_analytics(grades)

        self.assertEqual(analytics["average_gpa"], 4.675)
        self.assertEqual(analytics["numeric_gpa_count"], 2)
        self.assertEqual(analytics["counted_credit_total"], 4)
        self.assertEqual(analytics["uncounted_course_count"], 1)

    def test_grade_analytics_derives_gpa_from_score_when_grade_point_is_missing(self):
        grades = [
            {"semester": "202502", "course_name": "工程制图", "score": "98", "credit": "2", "grade_point": ""},
            {"semester": "202502", "course_name": "国家安全教育", "score": "90", "credit": "1"},
        ]

        analytics = grade_analytics(grades)

        self.assertEqual(analytics["average_gpa"], 4.533)
        self.assertEqual(analytics["distribution"], {"4-5": 2, "3-4": 0, "2-3": 0, "0-2": 0})

    def test_filter_grades_supports_semester_search_and_elective_toggle(self):
        grades = [
            {"semester": "202401", "course_code": "MATH", "course_name": "高数", "raw": {"课程性质": "必修"}},
            {"semester": "202402", "course_code": "ART", "course_name": "艺术选修", "raw": {"课程性质": "公共选修"}},
            {"semester": "202402", "course_code": "CS101", "course_name": "数据结构", "raw": {"课程性质": "必修"}},
        ]

        self.assertEqual(semester_options(grades), ["全部学期", "202402", "202401"])
        self.assertEqual([grade["course_code"] for grade in filter_grades(grades, semester="202402")], ["ART", "CS101"])
        self.assertEqual([grade["course_code"] for grade in filter_grades(grades, search_text="data")], [])
        self.assertEqual([grade["course_code"] for grade in filter_grades(grades, search_text="数据")], ["CS101"])
        self.assertEqual(
            [grade["course_code"] for grade in filter_grades(grades, semester="202402", include_electives=False)],
            ["CS101"],
        )

    def test_recent_change_rows_returns_latest_first(self):
        state = {
            "history": [
                {"course_name": "高数", "score": "90", "semester": "202401"},
                {"course_name": "英语", "score": "95", "semester": "202401"},
                {"course_name": "数据结构", "score": "98", "semester": "202402"},
            ]
        }

        self.assertEqual(
            recent_change_rows(state, limit=2),
            [("数据结构", "98", "202402"), ("英语", "95", "202401")],
        )


if __name__ == "__main__":
    unittest.main()
