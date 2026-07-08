import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class QtGuiPackagingTests(unittest.TestCase):
    def test_pyproject_declares_pyside6_dependency_for_modern_gui(self):
        text = Path("pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('"PySide6>=6.7"', text)

    def test_desktop_uses_qt_gui_by_default_and_keeps_tk_fallback(self):
        text = Path("gdut_grade_monitor/desktop.py").read_text(encoding="utf-8")

        self.assertIn("from .qt_gui import main as gui_main", text)
        self.assertIn("from .gui import main as legacy_gui_main", text)
        self.assertIn("--legacy-gui", text)

    def test_cli_exposes_qt_default_and_legacy_gui_command(self):
        text = Path("gdut_grade_monitor/cli.py").read_text(encoding="utf-8")

        self.assertIn("from .qt_gui import main as gui_main", text)
        self.assertIn('def legacy_gui()', text)

    def test_qt_gui_module_has_modern_shell_pages_and_tray(self):
        text = Path("gdut_grade_monitor/qt_gui.py").read_text(encoding="utf-8")

        self.assertIn("class GradeMonitorQtApp", text)
        self.assertIn("QLockFile", text)
        self.assertIn("def _acquire_single_instance_lock", text)
        self.assertIn("def _raise_existing_window", text)
        self.assertIn("def _fit_to_current_screen", text)
        self.assertIn("availableGeometry()", text)
        self.assertIn("QToolTip", text)
        self.assertIn("def mouseMoveEvent", text)
        self.assertIn("def _paint_summary", text)
        self.assertIn("当前平均绩点", text)
        self.assertIn("等待更多学期数据", text)
        self.assertIn("还差 1 个学期生成趋势", text)
        self.assertIn("趋势准备中", text)
        self.assertIn("def export_transcript", text)
        self.assertIn("class TranscriptExportDialog", text)
        self.assertIn("保存这些抬头信息", text)
        self.assertIn("导出成绩单", text)
        self.assertIn("官方成绩单", text)
        self.assertIn("def open_official_transcript_portal", text)
        self.assertIn("QDesktopServices.openUrl", text)
        self.assertIn("official_transcript_guidance", text)
        self.assertIn("build_transcript_html", text)
        self.assertIn("QMessageBox QLabel", text)
        self.assertIn("QDialogButtonBox QPushButton", text)
        self.assertIn("平均绩点: {value:.2f}", text)
        self.assertIn("def _set_recent_changes", text)
        self.assertIn("recentRow", text)
        self.assertIn("scoreBadge", text)
        self.assertIn("QSystemTrayIcon", text)
        self.assertIn("总览", text)
        self.assertIn("成绩", text)
        self.assertIn("提醒历史", text)
        self.assertIn("设置", text)
        self.assertIn("环境检查", text)
        self.assertIn("帮助", text)
        self.assertIn("def _help_page", text)
        self.assertIn("help_sections", text)
        self.assertIn("onboarding_steps", text)
        self.assertIn("新手引导", text)
        self.assertIn("查看帮助", text)
        self.assertIn("关于", text)

    def test_single_instance_lock_blocks_second_owner(self):
        from gdut_grade_monitor.qt_gui import _acquire_single_instance_lock
        from gdut_grade_monitor.storage import AppPaths

        with TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            first_lock = _acquire_single_instance_lock(paths)
            self.assertIsNotNone(first_lock)
            try:
                second_lock = _acquire_single_instance_lock(paths)
                self.assertIsNone(second_lock)
            finally:
                first_lock.unlock()

    def test_duplicate_qt_instance_focuses_existing_window_without_dialog(self):
        text = Path("gdut_grade_monitor/qt_gui.py").read_text(encoding="utf-8")
        duplicate_block = text.split("if single_instance_lock is None:", 1)[1].split(
            "window = GradeMonitorQtApp()", 1
        )[0]

        self.assertIn("_raise_existing_window()", duplicate_block)
        self.assertNotIn("QMessageBox.information", duplicate_block)

    def test_pdf_export_paginates_long_transcript_instead_of_shrinking_to_one_page(self):
        try:
            from pypdf import PdfReader
            from PySide6.QtWidgets import QApplication
        except ImportError as exc:
            self.skipTest(f"PDF export dependencies unavailable: {exc}")

        from gdut_grade_monitor.qt_gui import GradeMonitorQtApp
        from gdut_grade_monitor.transcript import build_transcript_html

        QApplication.instance() or QApplication([])
        grades = [
            {
                "semester": "2024-2025-2",
                "course_code": f"CS{i:03d}",
                "course_name": f"测试课程名称很长很长{i}",
                "score": str(60 + i % 40),
                "credit": "2",
                "grade_point": "4.0",
                "raw": {"课程性质": "专业必修", "考试性质": "正常考试"},
            }
            for i in range(1, 45)
        ]
        html = build_transcript_html(grades, {"student_id": "3124000864", "transcript_name": "陈同学"})

        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "transcript.pdf"
            GradeMonitorQtApp._write_transcript_pdf(None, output, html)

            self.assertGreaterEqual(len(PdfReader(output).pages), 2)

    def test_build_script_collects_only_needed_qt_modules_for_pyinstaller(self):
        text = Path("scripts/build_exe.ps1").read_text(encoding="utf-8")

        self.assertNotIn("--collect-submodules PySide6", text)
        self.assertNotIn("--collect-submodules keyring.backends", text)
        self.assertIn("--hidden-import keyring.backends.Windows", text)
        self.assertIn("--hidden-import win32timezone", text)
        self.assertIn("--hidden-import PySide6.QtCore", text)
        self.assertIn("--hidden-import PySide6.QtGui", text)
        self.assertIn("--hidden-import PySide6.QtPrintSupport", text)
        self.assertIn("--hidden-import PySide6.QtWidgets", text)
        self.assertIn("--exclude-module PySide6.QtQml", text)
        self.assertIn("--exclude-module PySide6.QtQuick", text)
        self.assertIn("Pruning unused packaged modules", text)
        self.assertIn("Qt6Quick.dll", text)
        self.assertIn("cryptography-48.0.0.dist-info", text)
        self.assertIn("qt_zh_CN.qm", text)
        self.assertIn("--onedir", text)
        self.assertIn("GDUTGradeMonitor-portable.zip", text)


if __name__ == "__main__":
    unittest.main()
