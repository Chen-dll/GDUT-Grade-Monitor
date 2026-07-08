import re
import unittest
from pathlib import Path

from gdut_grade_monitor.constants import APP_VERSION
from gdut_grade_monitor.gui_model import about_text


class VersionAndAboutTests(unittest.TestCase):
    def test_single_version_matches_pyproject_and_installer(self):
        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
        installer = Path("packaging/installer/GDUTGradeMonitor.iss").read_text(encoding="utf-8")

        pyproject_version = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE).group(1)

        self.assertEqual(APP_VERSION, pyproject_version)
        self.assertEqual(APP_VERSION, "0.2.4")
        self.assertIn(f'#define AppVersion "{APP_VERSION}"', installer)

    def test_about_text_includes_author_version_and_readonly_boundary(self):
        text = about_text()

        self.assertIn(f"版本: {APP_VERSION}", text)
        self.assertIn("作者: Chen-Dll", text)
        self.assertIn("严格只读", text)
        self.assertIn("不会保存密码到配置文件", text)
        self.assertIn("xskccjxx!getDataList.action", text)


if __name__ == "__main__":
    unittest.main()
