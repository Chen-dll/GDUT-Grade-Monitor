import unittest
from pathlib import Path

from gdut_grade_monitor.official_transcript import (
    OFFICIAL_TRANSCRIPT_PORTAL_URL,
    official_transcript_guidance,
)


class OfficialTranscriptTests(unittest.TestCase):
    def test_official_transcript_guidance_marks_manual_readonly_boundary(self):
        guidance = official_transcript_guidance()

        self.assertEqual("https://e.gdut.edu.cn/infoplus/form/BKSZWCJD/start", OFFICIAL_TRANSCRIPT_PORTAL_URL)
        self.assertIn("全日制本科生中文成绩单申请", guidance)
        self.assertIn("手动", guidance)
        self.assertIn("7天", guidance)
        self.assertIn("登录资料", guidance)
        self.assertIn("不会自动提交", guidance)
        self.assertIn("不调用写入接口", guidance)
        self.assertIn("学校官方流程", guidance)

    def test_readme_documents_official_transcript_as_manual_portal(self):
        text = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("学校网上办事大厅官方成绩单入口", text)
        self.assertIn("用户手动查看或下载官方成绩单", text)
        self.assertIn("工具不会自动提交申请", text)

    def test_qt_gui_opens_official_transcript_with_login_profile_first(self):
        text = Path("gdut_grade_monitor/qt_gui.py").read_text(encoding="utf-8")

        self.assertIn("open_url_with_login_profile", text)
        self.assertIn("QDesktopServices.openUrl", text)


if __name__ == "__main__":
    unittest.main()
