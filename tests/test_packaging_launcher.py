import unittest
from pathlib import Path


class PackagingLauncherTests(unittest.TestCase):
    def test_launcher_uses_absolute_imports_for_pyinstaller_script_mode(self):
        text = Path("packaging/desktop_launcher.py").read_text(encoding="utf-8")

        self.assertIn("from gdut_grade_monitor.desktop import main", text)
        self.assertNotIn("from .", text)

    def test_build_script_uses_launcher_instead_of_package_module_file(self):
        text = Path("scripts/build_exe.ps1").read_text(encoding="utf-8")

        self.assertIn("packaging\\desktop_launcher.py", text)
        self.assertNotIn("gdut_grade_monitor\\desktop.py", text)

    def test_build_script_embeds_desktop_icon(self):
        text = Path("scripts/build_exe.ps1").read_text(encoding="utf-8")

        self.assertIn("--icon", text)
        self.assertIn("gdut_grade_monitor\\assets\\icon.ico", text)
        self.assertIn("--add-data", text)
        self.assertIn("gdut_grade_monitor\\assets\\icon.ico;gdut_grade_monitor\\assets", text)

    def test_icon_asset_is_packaged_with_python_package(self):
        pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

        self.assertTrue(Path("gdut_grade_monitor/assets/icon.ico").exists())
        self.assertIn('[tool.setuptools.package-data]', pyproject)
        self.assertIn('gdut_grade_monitor = ["assets/*.ico"]', pyproject)

    def test_source_install_script_opens_gui_for_one_click_setup(self):
        text = Path("scripts/install.ps1").read_text(encoding="utf-8")

        self.assertIn("python -m gdut_grade_monitor gui", text)
        self.assertIn("一键配置本机", text)
        self.assertNotIn("python -m gdut_grade_monitor setup", text)


if __name__ == "__main__":
    unittest.main()
