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
        gui_block = text.split('if "--monitor" in sys.argv:', 1)[1].split('if "--legacy-gui" in sys.argv:', 1)[0]
        self.assertIn("_configure_logging(paths)", gui_block)

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
        self.assertIn("手动补录", text)
        self.assertIn("撤销补录", text)
        self.assertIn("def clear_manual_score", text)
        self.assertIn("apply_manual_scores", text)
        self.assertIn("delete_manual_score", text)
        self.assertIn("set_manual_score", text)
        self.assertIn("score_source", text)
        self.assertIn("官方成绩单", text)
        self.assertIn("class GradeDetailDialog", text)
        self.assertIn("课程成绩详情", text)
        self.assertIn("cellDoubleClicked.connect(self.show_grade_detail)", text)
        self.assertIn("visible_grades", text)
        self.assertIn("def open_official_transcript_portal", text)
        self.assertIn("QDesktopServices.openUrl", text)
        self.assertIn("official_transcript_guidance", text)
        self.assertIn("build_transcript_html", text)
        self.assertIn("QMessageBox QLabel", text)
        self.assertIn("QDialogButtonBox QPushButton", text)
        self.assertIn("平均绩点: {value:.2f}", text)
        self.assertIn("def _set_recent_changes", text)
        self.assertIn("recentRow", text)
        self.assertIn("recentScroll", text)
        self.assertIn("最近变化 · {len(recent)} 条", text)
        self.assertIn("recent_change_rows(state, limit=20)", text)
        self.assertIn("setWidgetResizable(True)", text)
        self.assertIn("Qt.ScrollBarAsNeeded", text)
        self.assertIn("拖动右侧滚动条", text)
        self.assertIn("scoreBadge", text)
        self.assertIn("QSystemTrayIcon", text)
        self.assertIn("def closeEvent", text)
        self.assertIn("最小化到托盘", text)
        self.assertIn("后台提醒会继续运行", text)
        self.assertIn("退出程序", text)
        self.assertIn("def quit_application", text)
        self.assertIn("self._force_quit = True", text)
        self.assertIn("QTimer.singleShot", text)
        self.assertIn("class FirstRunWizardDialog", text)
        self.assertIn("wizardRail", text)
        self.assertIn("wizardPageScroll", text)
        self.assertIn("wizardPageContent", text)
        self.assertIn("wizardStepActive", text)
        self.assertIn("wizardStepDone", text)
        self.assertIn("def maybe_show_first_run_wizard", text)
        self.assertIn("def open_first_run_wizard", text)
        self.assertIn("first_run_wizard_seen", text)
        self.assertIn("first_run_wizard_pages", text)
        self.assertIn("start_requested", text)
        self.assertIn("稍后再说", text)
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
        self.assertIn("先点“一键配置本机”", text)
        self.assertIn("密码不会上传", text)
        self.assertIn("第一次不会提醒", text)
        self.assertIn("查看帮助", text)
        self.assertIn("新手向导", text)
        self.assertIn("关于", text)
        self.assertIn("aboutScroll", text)
        self.assertIn("aboutContent", text)
        self.assertIn("status_center_rows", text)
        self.assertIn("运行状态中心", text)
        self.assertIn("def _set_status_center", text)
        self.assertIn("runtimeTile", text)
        self.assertIn("查看运行状态", text)
        self.assertIn("暂停提醒 1 小时", text)
        self.assertIn("恢复后台检查", text)
        self.assertIn("查看日志", text)
        self.assertIn("def pause_monitor_for_one_hour", text)
        self.assertIn("def resume_monitor", text)
        self.assertIn("def open_log_file", text)
        self.assertIn("QProgressDialog", text)
        self.assertIn("def _run_background_with_progress", text)
        self.assertIn("已有一个操作正在进行", text)
        self.assertIn("正在连接 GitHub Release 检查新版本", text)
        self.assertIn("正在下载小补丁并校验 SHA256", text)
        self.assertIn("正在只读连接教务系统并检查成绩", text)
        self.assertIn("正在检查本机环境", text)
        self.assertIn("正在只读读取成绩并建立本地基线", text)
        self.assertIn("summaryNumber", text)
        self.assertIn("summaryBadge", text)
        self.assertIn("class NotificationSettingsDialog", text)
        self.assertIn("多设备通知", text)
        self.assertIn("PushPlus", text)
        self.assertIn("Server酱", text)
        self.assertIn("ntfy", text)
        self.assertIn("邮件 SMTP", text)
        self.assertIn("隐私模式", text)
        self.assertIn("发送测试通知", text)
        self.assertIn("QFrame#notificationCard", text)
        self.assertIn("QScrollArea#notificationScroll", text)
        self.assertIn("self.setMinimumSize(900, 700)", text)
        self.assertIn("privacy.setMinimumWidth(116)", text)
        self.assertIn("privacy.setMaximumWidth(128)", text)
        self.assertIn("class NotificationGuideDialog", text)
        self.assertIn("notificationGuideButton", text)
        self.assertIn("配置步骤", text)
        self.assertIn("PushPlus 微信通知配置指引", text)
        self.assertIn("Server酱 微信通知配置指引", text)
        self.assertIn("ntfy 手机/网页通知配置指引", text)
        self.assertIn("邮件 SMTP 通知配置指引", text)
        self.assertIn("打开官网/文档", text)
        self.assertIn("QMenu {", text)
        self.assertIn("QMenu::item:selected", text)
        self.assertIn("QToolTip {", text)
        self.assertIn("QComboBox QAbstractItemView", text)
        self.assertIn("配置自检", text)
        self.assertIn("notification_setup_checks", text)
        self.assertIn("notification_error_message", text)
        self.assertIn("notificationCheckCard", text)
        self.assertIn("notificationCheckSummary_warning", text)
        self.assertIn("def _current_notification_check_config", text)
        self.assertIn("def _preview_secret_store", text)
        self.assertIn("class NotificationTestResultDialog", text)
        self.assertIn("send_test(", text)
        self.assertIn("notificationTestRow", text)
        self.assertIn("个成功", text)
        self.assertIn("导出设置", text)
        self.assertIn("导入设置", text)
        self.assertIn("恢复默认", text)
        self.assertIn("export_settings", text)
        self.assertIn("import_settings", text)
        self.assertIn("reset_config", text)
        self.assertIn("def export_settings_file", text)
        self.assertIn("def import_settings_file", text)
        self.assertIn("def reset_settings_to_defaults", text)
        self.assertIn("通知渠道", text)
        self.assertIn("发送结果", text)
        self.assertIn("class CleanupAssistantDialog", text)
        self.assertIn("便携版提示", text)
        self.assertIn("检测到残留启动项", text)
        self.assertIn("一键清理残留", text)
        self.assertIn("卸载辅助", text)
        self.assertIn("open_cleanup_assistant", text)
        self.assertIn("cleanup_residue", text)
        self.assertIn("startup_script_is_stale", text)
        self.assertIn("安装小补丁", text)
        self.assertIn("预计下载", text)
        self.assertIn("本地配置、密码、Cookie、成绩快照和通知密钥不会被补丁覆盖", text)
        self.assertIn("def _format_bytes", text)
        self.assertIn("download_patch_package", text)
        self.assertIn("build_patch_apply_plan", text)
        self.assertIn("launch_patch_apply", text)
        self.assertIn("can_apply_patch", text)
        self.assertIn("SHA256", text)

    def test_first_run_wizard_auto_open_is_limited_to_unconfigured_users(self):
        text = Path("gdut_grade_monitor/qt_gui.py").read_text(encoding="utf-8")
        init_block = text.split("def __init__(self):", 1)[1].split("def _fit_to_current_screen", 1)[0]
        auto_block = text.split("def maybe_show_first_run_wizard", 1)[1].split(
            "def open_first_run_wizard", 1
        )[0]
        open_block = text.split("def open_first_run_wizard", 1)[1].split("def one_click_setup", 1)[0]

        self.assertIn("QTimer.singleShot", init_block)
        self.assertIn("student_id", auto_block)
        self.assertIn('state.get("grades")', auto_block)
        self.assertIn("first_run_wizard_seen", auto_block)
        self.assertIn("self.open_first_run_wizard(auto=True)", auto_block)
        self.assertIn("config[\"first_run_wizard_seen\"] = True", open_block)
        self.assertIn("save_config(self.paths, config)", open_block)
        self.assertIn("self.one_click_setup()", open_block)

    def test_qt_setup_completion_returns_to_dashboard_with_ready_message(self):
        text = Path("gdut_grade_monitor/qt_gui.py").read_text(encoding="utf-8")
        complete_block = text.split("def _one_click_setup_complete", 1)[1].split("def check_now", 1)[0]

        self.assertIn("self._set_page(0)", complete_block)
        self.assertIn("现在已经可以后台提醒了", complete_block)
        self.assertIn("首次配置已完成", complete_block)

    def test_qt_close_button_behavior_can_be_remembered_and_changed_in_settings(self):
        text = Path("gdut_grade_monitor/qt_gui.py").read_text(encoding="utf-8")
        close_block = text.split("def closeEvent", 1)[1].split("def quit_application", 1)[0]
        settings_block = text.split("def _settings_page", 1)[1].split("def _settings_action_card", 1)[0]

        self.assertIn("close_action", text)
        self.assertIn("每次询问", settings_block)
        self.assertIn("关闭按钮最小化到托盘", settings_block)
        self.assertIn("关闭按钮退出程序", settings_block)
        self.assertIn("self.close_action_combo", settings_block)
        self.assertIn("保存设置", settings_block)
        self.assertIn("不再提示，记住我的选择", close_block)
        self.assertIn("save_close_action_preference", close_block)
        self.assertIn("_handle_close_action", close_block)

    def test_qt_shows_update_success_message_after_version_changes(self):
        text = Path("gdut_grade_monitor/qt_gui.py").read_text(encoding="utf-8")
        init_block = text.split("def __init__(self):", 1)[1].split("def _fit_to_current_screen", 1)[0]
        update_block = text.split("def maybe_show_update_success", 1)[1].split(
            "def maybe_show_first_run_wizard", 1
        )[0]

        self.assertIn("QTimer.singleShot(700, self.maybe_show_update_success)", init_block)
        self.assertIn("last_seen_version", update_block)
        self.assertIn("已更新到", update_block)
        self.assertIn("APP_VERSION", update_block)
        self.assertIn("关闭窗口行为可以记住你的选择", update_block)
        self.assertIn("save_config(self.paths, config)", update_block)

    def test_qt_runs_one_safe_check_after_opening_for_configured_users(self):
        text = Path("gdut_grade_monitor/qt_gui.py").read_text(encoding="utf-8")
        init_block = text.split("def __init__(self):", 1)[1].split("def _fit_to_current_screen", 1)[0]
        auto_check_block = text.split("def maybe_run_startup_check", 1)[1].split(
            "def maybe_show_update_success", 1
        )[0]

        self.assertIn("QTimer.singleShot(1200, self.maybe_run_startup_check)", init_block)
        self.assertIn("student_id", auto_check_block)
        self.assertIn("self.check_now(silent=True)", auto_check_block)
        self.assertIn("not config.get(\"student_id\")", auto_check_block)

    def test_qt_keeps_checking_after_next_check_time_when_gui_stays_open(self):
        text = Path("gdut_grade_monitor/qt_gui.py").read_text(encoding="utf-8")
        init_block = text.split("def __init__(self):", 1)[1].split("def _fit_to_current_screen", 1)[0]
        scheduler_block = text.split("def _check_due_schedule", 1)[1].split("def maybe_run_startup_check", 1)[0]
        check_now_block = text.split("def check_now", 1)[1].split("def _check_now_worker", 1)[0]
        complete_block = text.split("def _scheduled_check_complete", 1)[1].split("def setup_login", 1)[0]

        self.assertIn("self._schedule_timer = QTimer(self)", init_block)
        self.assertIn("self._schedule_timer.timeout.connect(self._check_due_schedule)", init_block)
        self.assertIn("self._schedule_timer.start(15_000)", init_block)
        self.assertIn("next_check_at", scheduler_block)
        self.assertIn("datetime.now() < datetime.fromisoformat(next_check_at)", scheduler_block)
        self.assertIn("monitor_pause_remaining_seconds(config)", scheduler_block)
        self.assertIn("self._signals", scheduler_block)
        self.assertIn("self.check_now(silent=True, scheduled=True)", scheduler_block)
        self.assertIn("self._scheduled_check_running", check_now_block)
        self.assertIn("self._scheduled_check_running = False", complete_block)

    def test_qt_gui_mentions_repair_startup_wording(self):
        text = Path("gdut_grade_monitor/qt_gui.py").read_text(encoding="utf-8")
        install_block = text.split("def install_startup", 1)[1].split("def uninstall_startup", 1)[0]

        self.assertIn("安装/修复自启动", text)
        self.assertIn("修复自启动", text)
        self.assertIn("install_startup", text)
        self.assertIn("install_task_or_startup()", install_block)
        self.assertNotIn("prefer_startup=True", install_block)

    def test_dashboard_keeps_first_run_guide_out_of_main_overview(self):
        text = Path("gdut_grade_monitor/qt_gui.py").read_text(encoding="utf-8")
        dashboard_block = text.split("def _dashboard_page", 1)[1].split("def _runtime_status_card", 1)[0]

        self.assertNotIn("_onboarding_card()", dashboard_block)
        self.assertIn("_runtime_status_card()", dashboard_block)
        self.assertIn("打开数据目录", dashboard_block)
        self.assertNotIn("导出诊断包", dashboard_block)
        self.assertNotIn("安装自启动", dashboard_block)
        self.assertIn("status_rows = status_center_rows(config, state, installed)", text)
        self.assertIn("_set_status_center(status_rows[:3])", text)

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
        self.assertIn("opengl32sw.dll", text)
        self.assertIn("qdirect2d.dll", text)
        self.assertIn("qjpeg.dll", text)
        self.assertIn("qico.dll", text)
        self.assertIn("cryptography-48.0.0.dist-info", text)
        self.assertIn("qt_zh_CN.qm", text)
        self.assertIn("--onedir", text)
        self.assertIn("GDUTGradeMonitor-portable.zip", text)


if __name__ == "__main__":
    unittest.main()
