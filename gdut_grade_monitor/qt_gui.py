from __future__ import annotations

import os
import sys
import threading
import ctypes
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QLockFile, QMarginsF, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QPageLayout,
    QPageSize,
    QPainter,
    QPainterPath,
    QPen,
    QTextDocument,
)
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QTableWidget,
    QTableWidgetItem,
    QToolTip,
    QVBoxLayout,
    QWidget,
    QMenu,
)

from .auth import AuthManager, BrowserFillMismatchError, PlaywrightBrowserMissingError
from .client import GradeApiClient, GradeResponseError
from .constants import APP_AUTHOR, APP_VERSION
from .credentials import CredentialStore, PasswordInputError
from .cleanup import cleanup_residue, cleanup_summary
from .diagnostics import create_diagnostics_zip
from .doctor import overall_ok, run_checks
from .errors import user_friendly_error_message
from .gui_model import about_text, doctor_table_rows, filter_grades, first_run_wizard_pages, grade_analytics, grade_table_rows
from .gui_model import help_sections, history_table_rows
from .gui_model import onboarding_steps, recent_change_rows, semester_options
from .gui_model import setup_guidance, status_center_rows, status_summary
from .monitor import GradeMonitor
from .notification_channels import (
    NotificationSecretStore,
    build_notifier,
    notification_config,
    notification_error_message,
    notification_setup_checks,
)
from .notify import NOTIFICATION_PRIVACY_DETAILED, NOTIFICATION_PRIVACY_PRIVATE, NOTIFICATION_PRIVACY_SUMMARY
from .official_transcript import OFFICIAL_TRANSCRIPT_PORTAL_URL, official_transcript_guidance
from .setup_flow import FirstRunSetupResult, run_first_run_setup
from .settings_backup import export_settings, import_settings
from .storage import AppPaths, load_config, load_state, reset_config, save_config, set_poll_interval
from .task import autostart_exists, install_task_or_startup, startup_script_is_stale, uninstall_task_and_startup
from .transcript import TRANSCRIPT_NOTICE, build_transcript_html, write_transcript_html
from .update_check import GitHubRelease, check_latest_release


class _Signals(QObject):
    success = Signal(object)
    error = Signal(str)


class FirstRunSetupDialog(QDialog):
    def __init__(self, parent: QWidget, initial_interval: int):
        super().__init__(parent)
        self.setWindowTitle("一键配置本机")
        self.setModal(True)
        self.student_id = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.interval = QSpinBox()
        self.interval.setRange(1, 1440)
        self.interval.setValue(initial_interval)
        self.autostart = QCheckBox("配置完成后开启登录自启动")
        self.autostart.setChecked(True)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("学号", self.student_id)
        form.addRow("密码", self.password)
        form.addRow("检查频率(分钟)", self.interval)
        form.addRow("", self.autostart)
        layout.addLayout(form)
        hint = QLabel("密码只保存到 Windows 凭据管理器；如需验证码，请在弹出的浏览器里完成登录。")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._validate_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_accept(self) -> None:
        if not self.student_id.text().strip():
            QMessageBox.warning(self, "一键配置本机", "请填写学号。")
            return
        if not self.password.text():
            QMessageBox.warning(self, "一键配置本机", "请填写密码。")
            return
        self.accept()

    def options(self) -> dict:
        return {
            "student_id": self.student_id.text().strip(),
            "password": self.password.text(),
            "interval_minutes": self.interval.value(),
            "install_autostart": self.autostart.isChecked(),
        }


class FirstRunWizardDialog(QDialog):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setWindowTitle("新手向导")
        self.setModal(True)
        self.setMinimumSize(760, 500)
        self.pages_data = first_run_wizard_pages()
        self.start_requested = False

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        rail = QFrame()
        rail.setObjectName("wizardRail")
        rail.setFixedWidth(230)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(22, 22, 18, 22)
        rail_layout.setSpacing(12)
        rail_title = QLabel("GDUT 成绩提醒")
        rail_title.setObjectName("wizardRailTitle")
        rail_body = QLabel("首次使用向导")
        rail_body.setObjectName("wizardRailBody")
        rail_body.setWordWrap(True)
        rail_layout.addWidget(rail_title)
        rail_layout.addWidget(rail_body)
        rail_layout.addSpacing(10)

        self.step_labels: list[QLabel] = []
        for index, page in enumerate(self.pages_data, start=1):
            step = QLabel(f"{index:02d}  {page.get('nav_title') or page['title']}")
            step.setWordWrap(False)
            step.setObjectName("wizardStepPending")
            self.step_labels.append(step)
            rail_layout.addWidget(step)
        rail_layout.addStretch(1)

        safety = QLabel("本工具只读查询成绩，不修改教务系统数据。")
        safety.setObjectName("wizardRailBody")
        safety.setWordWrap(True)
        rail_layout.addWidget(safety)
        root.addWidget(rail)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(26, 24, 26, 20)
        layout.setSpacing(14)

        self.progress_label = QLabel("")
        self.progress_label.setObjectName("wizardProgress")
        layout.addWidget(self.progress_label)

        self.stack = QStackedWidget()
        self.stack.setObjectName("wizardStack")
        for page in self.pages_data:
            self.stack.addWidget(self._page_widget(page))
        layout.addWidget(self.stack, 1)

        buttons = QHBoxLayout()
        self.skip_button = QPushButton("稍后再说")
        self.skip_button.setObjectName("secondaryButton")
        self.back_button = QPushButton("上一步")
        self.back_button.setObjectName("secondaryButton")
        self.next_button = QPushButton("下一步")
        self.next_button.setObjectName("primaryButton")
        self.skip_button.clicked.connect(self.reject)
        self.back_button.clicked.connect(self._back)
        self.next_button.clicked.connect(self._next)
        buttons.addWidget(self.skip_button)
        buttons.addStretch(1)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.next_button)
        layout.addLayout(buttons)
        root.addWidget(content, 1)
        self._refresh_buttons()

    def _page_widget(self, page: dict[str, object]) -> QWidget:
        scroll = QScrollArea()
        scroll.setObjectName("wizardPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        widget = QWidget()
        widget.setObjectName("wizardPageContent")
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        title = QLabel(str(page["title"]))
        title.setObjectName("wizardTitle")
        body = QLabel(str(page["body"]))
        body.setObjectName("wizardBody")
        body.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(body)

        for item in page.get("items", []):
            row = QFrame()
            row.setObjectName("wizardItem")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(10)
            bullet = QLabel("")
            bullet.setObjectName("helpBullet")
            bullet.setFixedSize(8, 8)
            text = QLabel(str(item))
            text.setWordWrap(True)
            text.setObjectName("helpItemText")
            row_layout.addWidget(bullet, 0, Qt.AlignTop)
            row_layout.addWidget(text, 1)
            layout.addWidget(row)

        layout.addStretch(1)
        scroll.setWidget(widget)
        return scroll

    def _back(self) -> None:
        self.stack.setCurrentIndex(max(0, self.stack.currentIndex() - 1))
        self._refresh_buttons()

    def _next(self) -> None:
        if self.stack.currentIndex() >= self.stack.count() - 1:
            self.start_requested = True
            self.accept()
            return
        self.stack.setCurrentIndex(self.stack.currentIndex() + 1)
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        index = self.stack.currentIndex()
        page = self.pages_data[index]
        self.progress_label.setText(f"第 {index + 1} / {self.stack.count()} 步")
        self.back_button.setEnabled(index > 0)
        self.next_button.setText(str(page.get("primary_action") or "下一步"))
        for step_index, label in enumerate(self.step_labels):
            if step_index < index:
                label.setObjectName("wizardStepDone")
            elif step_index == index:
                label.setObjectName("wizardStepActive")
            else:
                label.setObjectName("wizardStepPending")
            label.style().unpolish(label)
            label.style().polish(label)


class TranscriptExportDialog(QDialog):
    PROFILE_FIELDS = [
        ("transcript_title", "标题", "本地成绩单"),
        ("student_id", "学号", ""),
        ("transcript_name", "姓名", ""),
        ("transcript_college", "学院", ""),
        ("transcript_major", "专业", ""),
        ("transcript_class", "班级", ""),
    ]

    def __init__(self, parent: QWidget, config: dict):
        super().__init__(parent)
        self.setWindowTitle("成绩单信息")
        self.setModal(True)
        self.inputs: dict[str, QLineEdit] = {}
        self.remember = QCheckBox("保存这些抬头信息，方便下次导出")
        self.remember.setChecked(False)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        for key, label, fallback in self.PROFILE_FIELDS:
            field = QLineEdit(str(config.get(key) or fallback))
            self.inputs[key] = field
            form.addRow(label, field)
        layout.addLayout(form)
        hint = QLabel("成绩单由本地快照生成，仅供个人核对；不会提交学校成绩单申请。")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(self.remember)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def profile(self) -> dict[str, str]:
        return {key: field.text().strip() for key, field in self.inputs.items()}


class NotificationSettingsDialog(QDialog):
    CHANNEL_LABELS = {
        "windows": "Windows 本机通知",
        "pushplus": "PushPlus 微信通知",
        "serverchan": "Server酱 微信通知",
        "ntfy": "ntfy 手机/网页通知",
        "smtp": "邮件 SMTP 通知",
    }
    PRIVACY_LABELS = [
        ("隐私模式", NOTIFICATION_PRIVACY_PRIVATE),
        ("摘要模式", NOTIFICATION_PRIVACY_SUMMARY),
        ("详细模式", NOTIFICATION_PRIVACY_DETAILED),
    ]

    def __init__(self, parent: QWidget, paths: AppPaths):
        super().__init__(parent)
        self.paths = paths
        self.secret_store = NotificationSecretStore()
        self.config = notification_config(load_config(paths))
        self.enabled_fields: dict[str, QCheckBox] = {}
        self.privacy_fields: dict[str, QComboBox] = {}
        self.value_fields: dict[tuple[str, str], QLineEdit | QSpinBox | QComboBox] = {}
        self.secret_fields: dict[str, QLineEdit] = {}
        self.check_rows_layout: QVBoxLayout | None = None

        self.setWindowTitle("多设备通知")
        self.setModal(True)
        self.setMinimumSize(900, 700)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel("多设备通知")
        title.setObjectName("detailTitle")
        intro = QLabel("电脑仍只读查询成绩；手机、邮箱和微信类服务只接收通知。微信类和 ntfy 会经过第三方服务，建议使用隐私模式。")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(self._notification_check_card())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("notificationScroll")
        content = QWidget()
        content.setObjectName("notificationContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(12)

        content_layout.addWidget(self._channel_card("windows", "保留原来的 Windows 系统通知。"))
        content_layout.addWidget(self._channel_card("pushplus", "关注 PushPlus 后填写 token，可通过微信收到提醒。", secret_label="PushPlus token"))
        content_layout.addWidget(self._channel_card("serverchan", "绑定 Server酱后填写 SendKey，可通过微信收到提醒。", secret_label="Server酱 SendKey"))
        content_layout.addWidget(
            self._channel_card(
                "ntfy",
                "适合 Android、iOS 或网页。公共 topic 不建议使用详细模式。",
                fields=[("server_url", "服务器地址", "https://ntfy.sh"), ("topic", "Topic", "")],
                secret_label="Bearer token（可选）",
            )
        )
        content_layout.addWidget(
            self._channel_card(
                "smtp",
                "通过邮箱把提醒发给自己，适合作为通用保底方案。",
                fields=[
                    ("host", "SMTP 服务器", ""),
                    ("port", "端口", 587),
                    ("username", "登录账号", ""),
                    ("sender", "发件人", ""),
                    ("recipient", "收件人", ""),
                    ("security", "连接安全", "starttls"),
                ],
                secret_label="SMTP 密码/授权码",
            )
        )
        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox()
        test_button = buttons.addButton("发送测试通知", QDialogButtonBox.ActionRole)
        save_button = buttons.addButton("保存", QDialogButtonBox.AcceptRole)
        cancel_button = buttons.addButton("取消", QDialogButtonBox.RejectRole)
        save_button.setObjectName("primaryButton")
        test_button.setObjectName("secondaryButton")
        cancel_button.setObjectName("secondaryButton")
        test_button.clicked.connect(self._send_test_notification)
        buttons.accepted.connect(self._save_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _channel_card(
        self,
        channel_id: str,
        description: str,
        *,
        fields: list[tuple[str, str, object]] | None = None,
        secret_label: str | None = None,
    ) -> QFrame:
        card = _card()
        card.setObjectName("notificationCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(12)
        enabled = QCheckBox(self.CHANNEL_LABELS[channel_id])
        enabled.setChecked(bool(self.config[channel_id].get("enabled")))
        enabled.setObjectName("channelEnabled")
        privacy = self._privacy_combo(str(self.config[channel_id].get("privacy") or NOTIFICATION_PRIVACY_PRIVATE))
        privacy.setMinimumWidth(116)
        privacy.setMaximumWidth(128)
        self.enabled_fields[channel_id] = enabled
        self.privacy_fields[channel_id] = privacy
        privacy_label = QLabel("通知内容")
        privacy_label.setObjectName("notificationPrivacyLabel")
        top.addWidget(enabled, 1)
        if channel_id != "windows":
            guide = QPushButton("指引")
            guide.setObjectName("notificationGuideButton")
            guide.setToolTip(f"查看 {self.CHANNEL_LABELS[channel_id]} 的配置步骤")
            guide.clicked.connect(lambda _checked=False, cid=channel_id: self._open_channel_guide(cid))
            top.addWidget(guide)
        top.addWidget(privacy_label)
        top.addWidget(privacy)
        layout.addLayout(top)

        detail = QLabel(description)
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        layout.addWidget(detail)

        if fields or secret_label:
            form = QFormLayout()
            form.setContentsMargins(0, 4, 0, 0)
            for key, label, default in fields or []:
                if key == "port":
                    field = QSpinBox()
                    field.setRange(1, 65535)
                    field.setValue(int(self.config[channel_id].get(key) or default))
                elif key == "security":
                    field = QComboBox()
                    for label_text, value in [("STARTTLS", "starttls"), ("SSL", "ssl"), ("不加密", "none")]:
                        field.addItem(label_text, value)
                    self._set_combo_value(field, str(self.config[channel_id].get(key) or default))
                else:
                    field = QLineEdit(str(self.config[channel_id].get(key) or default))
                self.value_fields[(channel_id, key)] = field
                form.addRow(label, field)
            if secret_label:
                secret = QLineEdit()
                secret.setEchoMode(QLineEdit.Password)
                secret.setPlaceholderText("已保存则留空不修改；需要更换时重新填写。")
                self.secret_fields[channel_id] = secret
                form.addRow(secret_label, secret)
            layout.addLayout(form)
        return card

    def _notification_check_card(self) -> QFrame:
        card = _card()
        card.setObjectName("notificationCheckCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("配置自检")
        title.setObjectName("notificationCheckTitle")
        refresh = QPushButton("刷新")
        refresh.setObjectName("notificationGuideButton")
        refresh.clicked.connect(self._refresh_notification_checks)
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(refresh)
        layout.addLayout(top)

        self.check_rows_layout = QVBoxLayout()
        self.check_rows_layout.setSpacing(8)
        layout.addLayout(self.check_rows_layout)
        self._refresh_notification_checks()
        return card

    def _refresh_notification_checks(self) -> None:
        if self.check_rows_layout is None:
            return
        while self.check_rows_layout.count():
            item = self.check_rows_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        rows = notification_setup_checks(self._current_notification_check_config(), self._preview_secret_store())
        for row in rows:
            self.check_rows_layout.addWidget(self._notification_check_row(row))

    def _current_notification_check_config(self) -> dict:
        config = load_config(self.paths)
        notifications = notification_config(config)
        for channel_id in self.CHANNEL_LABELS:
            if channel_id in self.enabled_fields:
                notifications[channel_id]["enabled"] = self.enabled_fields[channel_id].isChecked()
            if channel_id in self.privacy_fields:
                notifications[channel_id]["privacy"] = str(self.privacy_fields[channel_id].currentData())
        for (channel_id, key), field in self.value_fields.items():
            if isinstance(field, QSpinBox):
                notifications[channel_id][key] = field.value()
            elif isinstance(field, QComboBox):
                notifications[channel_id][key] = str(field.currentData())
            else:
                notifications[channel_id][key] = field.text().strip()
        config["notifications"] = notifications
        return config

    def _preview_secret_store(self):
        parent = self

        class PreviewSecretStore:
            def get_secret(self, channel: str) -> str:
                field = parent.secret_fields.get(channel)
                pending = field.text().strip() if field else ""
                return pending or parent.secret_store.get_secret(channel)

        return PreviewSecretStore()

    def _notification_check_row(self, row) -> QFrame:
        frame = QFrame()
        frame.setObjectName("notificationCheckRow")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        dot = QLabel()
        dot.setObjectName(f"notificationDot_{row.status}")
        dot.setFixedSize(9, 9)
        title = QLabel(row.label)
        title.setObjectName("notificationCheckLabel")
        summary = QLabel(row.summary)
        summary.setObjectName(f"notificationCheckSummary_{row.status}")
        detail = QLabel(row.detail)
        detail.setObjectName("notificationCheckDetail")
        detail.setWordWrap(True)
        layout.addWidget(dot)
        layout.addWidget(title)
        layout.addWidget(summary)
        layout.addWidget(detail, 1)
        return frame

    def _open_channel_guide(self, channel_id: str) -> None:
        dialog = NotificationGuideDialog(self, channel_id)
        dialog.exec()

    def _privacy_combo(self, value: str) -> QComboBox:
        combo = QComboBox()
        for label, mode in self.PRIVACY_LABELS:
            combo.addItem(label, mode)
        self._set_combo_value(combo, value)
        return combo

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _save_config(self) -> None:
        config = load_config(self.paths)
        notifications = notification_config(config)
        for channel_id in self.CHANNEL_LABELS:
            notifications[channel_id]["enabled"] = self.enabled_fields[channel_id].isChecked()
            notifications[channel_id]["privacy"] = str(self.privacy_fields[channel_id].currentData())
        for (channel_id, key), field in self.value_fields.items():
            if isinstance(field, QSpinBox):
                notifications[channel_id][key] = field.value()
            elif isinstance(field, QComboBox):
                notifications[channel_id][key] = str(field.currentData())
            else:
                notifications[channel_id][key] = field.text().strip()
        config["notifications"] = notifications
        save_config(self.paths, config)
        for channel_id, field in self.secret_fields.items():
            value = field.text().strip()
            if value:
                self.secret_store.set_secret(channel_id, value)
                field.clear()

    def _save_and_accept(self) -> None:
        try:
            self._save_config()
        except Exception as exc:
            QMessageBox.critical(self, "多设备通知", f"保存失败：{type(exc).__name__}: {exc}")
            return
        self._refresh_notification_checks()
        self.accept()

    def _send_test_notification(self) -> None:
        try:
            self._save_config()
            results = build_notifier(self.paths, suppress_errors=False).send_test(
                "GDUT 成绩提醒测试",
                "这是一条多设备通知测试。",
            )
        except Exception as exc:
            self._refresh_notification_checks()
            QMessageBox.critical(self, "发送测试通知", f"发送失败：\n\n{notification_error_message(exc)}")
            return
        self._refresh_notification_checks()
        NotificationTestResultDialog(self, results).exec()


class NotificationTestResultDialog(QDialog):
    def __init__(self, parent: QWidget, results):
        super().__init__(parent)
        self.setWindowTitle("发送测试通知")
        self.setModal(True)
        self.setMinimumSize(620, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        success_count = sum(1 for result in results if result.ok)
        failed_count = sum(1 for result in results if not result.ok)
        title = QLabel("测试结果")
        title.setObjectName("detailTitle")
        if results:
            intro_text = f"已测试 {len(results)} 个启用渠道：{success_count} 个成功，{failed_count} 个需要处理。"
        else:
            intro_text = "当前没有启用任何通知渠道。请先勾选至少一个渠道并保存配置。"
        intro = QLabel(intro_text)
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(intro)

        rows = QVBoxLayout()
        rows.setSpacing(9)
        for result in results:
            rows.addWidget(self._result_row(result))
        if not results:
            empty = QLabel("未启用通知渠道")
            empty.setObjectName("muted")
            rows.addWidget(empty)
        layout.addLayout(rows)
        layout.addStretch(1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _result_row(self, result) -> QFrame:
        frame = QFrame()
        frame.setObjectName("notificationTestRow")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        dot = QLabel()
        dot.setObjectName("notificationDot_ok" if result.ok else "notificationDot_warning")
        dot.setFixedSize(9, 9)
        label = QLabel(result.label)
        label.setObjectName("notificationCheckLabel")
        status = QLabel("成功" if result.ok else "失败")
        status.setObjectName("notificationCheckSummary_ok" if result.ok else "notificationCheckSummary_warning")
        detail = QLabel(result.detail)
        detail.setObjectName("notificationCheckDetail")
        detail.setWordWrap(True)
        layout.addWidget(dot)
        layout.addWidget(label)
        layout.addWidget(status)
        layout.addWidget(detail, 1)
        return frame


class NotificationGuideDialog(QDialog):
    GUIDES = {
        "pushplus": {
            "title": "PushPlus 微信通知配置指引",
            "url": "https://www.pushplus.plus/",
            "steps": [
                ("注册并关注", "打开 PushPlus 官网，用微信扫码登录或注册，并按页面提示关注公众号。"),
                ("复制 token", "进入个人中心或一对一推送页面，复制自己的 token。不要把 token 发给别人。"),
                ("填回应用", "回到本页，在 PushPlus token 中粘贴 token，勾选 PushPlus 微信通知。"),
                ("发送测试", "建议先保持隐私模式，点击发送测试通知。手机能收到后再保存。"),
            ],
        },
        "serverchan": {
            "title": "Server酱 微信通知配置指引",
            "url": "https://sct.ftqq.com/",
            "steps": [
                ("绑定微信", "打开 Server酱官网，登录后按页面提示完成微信绑定。"),
                ("复制 SendKey", "在发送消息页面复制 SendKey。SendKey 等同通知密钥，请不要公开。"),
                ("填回应用", "回到本页，在 Server酱 SendKey 中粘贴 SendKey，勾选 Server酱 微信通知。"),
                ("发送测试", "先用隐私模式测试。若提示失败，重点检查 SendKey、网络和 Server酱账号状态。"),
            ],
        },
        "ntfy": {
            "title": "ntfy 手机/网页通知配置指引",
            "url": "https://docs.ntfy.sh/",
            "steps": [
                ("选择服务器", "可先使用默认 https://ntfy.sh，也可以填写自建 ntfy 服务器地址。"),
                ("设置 Topic", "填写一个足够随机的 Topic，例如 gdut-grade-加一串随机字符。公共 Topic 不建议放详细成绩。"),
                ("手机订阅", "在手机 ntfy App 或网页中订阅同一个 Topic。需要鉴权时再填写 Bearer token。"),
                ("发送测试", "点击发送测试通知。公共服务器建议一直使用隐私模式或摘要模式。"),
            ],
        },
        "smtp": {
            "title": "邮件 SMTP 通知配置指引",
            "url": "https://support.qq.com/products/378101/faqs/104931",
            "steps": [
                ("准备授权码", "到邮箱设置中开启 SMTP/IMAP 服务，生成授权码。不要填写网页登录密码。"),
                ("填写服务器", "常见端口是 STARTTLS 587 或 SSL 465。发件人通常和登录账号一致。"),
                ("填写收件人", "收件人可以是自己的邮箱；想发到手机，建议使用常用邮箱 App 的推送。"),
                ("发送测试", "如果失败，检查服务器地址、端口、安全类型、授权码和邮箱服务是否开启。"),
            ],
        },
    }

    def __init__(self, parent: QWidget, channel_id: str):
        super().__init__(parent)
        self.guide = self.GUIDES[channel_id]
        self.step_index = 0
        self.setWindowTitle(self.guide["title"])
        self.setModal(True)
        self.setMinimumSize(620, 390)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel(self.guide["title"])
        title.setObjectName("detailTitle")
        layout.addWidget(title)

        intro = QLabel("按下面几步配置即可。通知密钥只会保存在本机系统凭据里，不会写入配置文件。")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.step_card = QFrame()
        self.step_card.setObjectName("notificationGuideStep")
        step_layout = QVBoxLayout(self.step_card)
        step_layout.setContentsMargins(18, 16, 18, 16)
        step_layout.setSpacing(10)

        self.progress = QLabel()
        self.progress.setObjectName("guideStepIndex")
        self.step_title = QLabel()
        self.step_title.setObjectName("guideStepTitle")
        self.step_body = QLabel()
        self.step_body.setObjectName("guideStepBody")
        self.step_body.setWordWrap(True)
        step_layout.addWidget(self.progress)
        step_layout.addWidget(self.step_title)
        step_layout.addWidget(self.step_body)
        step_layout.addStretch(1)
        layout.addWidget(self.step_card, 1)

        hint = QLabel("建议先用隐私模式完成测试；确认能收到通知后，再按需要改成摘要或详细模式。")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        self.open_button = QPushButton("打开官网/文档")
        self.open_button.setObjectName("secondaryButton")
        self.prev_button = QPushButton("上一步")
        self.prev_button.setObjectName("secondaryButton")
        self.next_button = QPushButton("下一步")
        self.next_button.setObjectName("primaryButton")
        close_button = QPushButton("关闭")
        close_button.setObjectName("secondaryButton")
        self.open_button.clicked.connect(self._open_url)
        self.prev_button.clicked.connect(self._prev_step)
        self.next_button.clicked.connect(self._next_step)
        close_button.clicked.connect(self.accept)
        buttons.addWidget(self.open_button)
        buttons.addStretch(1)
        buttons.addWidget(self.prev_button)
        buttons.addWidget(self.next_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self._render_step()

    def _render_step(self) -> None:
        steps = self.guide["steps"]
        title, body = steps[self.step_index]
        self.progress.setText(f"第 {self.step_index + 1} / {len(steps)} 步")
        self.step_title.setText(title)
        self.step_body.setText(body)
        self.prev_button.setEnabled(self.step_index > 0)
        self.next_button.setText("完成" if self.step_index == len(steps) - 1 else "下一步")

    def _prev_step(self) -> None:
        if self.step_index > 0:
            self.step_index -= 1
            self._render_step()

    def _next_step(self) -> None:
        if self.step_index >= len(self.guide["steps"]) - 1:
            self.accept()
            return
        self.step_index += 1
        self._render_step()

    def _open_url(self) -> None:
        QDesktopServices.openUrl(QUrl(str(self.guide["url"])))


class CleanupAssistantDialog(QDialog):
    def __init__(self, parent: QWidget, paths: AppPaths):
        super().__init__(parent)
        self.paths = paths
        self.setWindowTitle("卸载辅助")
        self.setModal(True)
        self.setMinimumSize(660, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel("卸载辅助")
        title.setObjectName("detailTitle")
        layout.addWidget(title)

        intro = QLabel("这里用于处理便携版目录被直接删除、自启动还残留，或卸载前想确认哪些数据会保留的情况。")
        intro.setObjectName("muted")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("cleanupStatus")
        layout.addWidget(self.status_label)

        guide = QFrame()
        guide.setObjectName("cleanupGuide")
        guide_layout = QVBoxLayout(guide)
        guide_layout.setContentsMargins(16, 14, 16, 14)
        guide_layout.setSpacing(10)
        guide_layout.addWidget(self._guide_item("便携版提示", "不要直接删除正在使用的便携版目录。先在设置页取消自启动，再删除程序目录会更干净。"))
        guide_layout.addWidget(self._guide_item("检测到残留启动项", "如果便携版目录已经删掉，应用会在环境检查里提示残留启动项；这里可以一键清理残留。"))
        guide_layout.addWidget(self._guide_item("卸载辅助", "清理启动项不会删除 Windows 凭据管理器中的密码和通知密钥；如需删除，请到系统凭据管理器手动处理。"))
        layout.addWidget(guide, 1)

        self.remove_data = QCheckBox("同时删除本地配置、Cookie、成绩快照和日志")
        self.remove_data.setToolTip("默认不删除本地数据。勾选后会删除 ~/.gdut-grade-monitor，之后需要重新配置。")
        layout.addWidget(self.remove_data)

        buttons = QHBoxLayout()
        cleanup_button = QPushButton("一键清理残留")
        cleanup_button.setObjectName("primaryButton")
        cleanup_button.clicked.connect(self._cleanup)
        open_data = QPushButton("打开数据目录")
        open_data.setObjectName("secondaryButton")
        open_data.clicked.connect(self._open_data_dir)
        close = QPushButton("关闭")
        close.setObjectName("secondaryButton")
        close.clicked.connect(self.accept)
        buttons.addWidget(cleanup_button)
        buttons.addWidget(open_data)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self._refresh_status()

    def _guide_item(self, title: str, body: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("cleanupGuideItem")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("cleanupGuideTitle")
        text = QLabel(body)
        text.setObjectName("muted")
        text.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(text)
        return frame

    def _refresh_status(self) -> None:
        if startup_script_is_stale():
            self.status_label.setText("检测到残留启动项：启动文件指向的程序已经不存在，可以点击“一键清理残留”。")
            self.status_label.setProperty("level", "warning")
        else:
            self.status_label.setText("未检测到明显残留启动项。仍可用于取消本工具创建的启动文件和计划任务。")
            self.status_label.setProperty("level", "ok")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _cleanup(self) -> None:
        remove_data = self.remove_data.isChecked()
        if remove_data:
            answer = QMessageBox.question(
                self,
                "一键清理残留",
                "将删除本地配置、Cookie、成绩快照和日志。\n\n确定继续吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        try:
            result = cleanup_residue(remove_data=remove_data)
        except Exception as exc:
            QMessageBox.critical(self, "一键清理残留", f"清理失败：{type(exc).__name__}: {exc}")
            return
        self._refresh_status()
        parent = self.parent()
        if hasattr(parent, "refresh_all"):
            parent.refresh_all()
        QMessageBox.information(self, "一键清理残留", cleanup_summary(result))

    def _open_data_dir(self) -> None:
        self.paths.ensure()
        os.startfile(self.paths.root)


class GradeDetailDialog(QDialog):
    def __init__(self, parent: QWidget, grade: dict):
        super().__init__(parent)
        self.setWindowTitle("课程成绩详情")
        self.setModal(True)
        self.setMinimumSize(560, 440)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)

        title = QLabel(str(grade.get("course_name") or "未命名课程"))
        title.setObjectName("detailTitle")
        title.setWordWrap(True)
        layout.addWidget(title)

        fields = [
            ("学期", grade.get("semester", "")),
            ("课程代码", grade.get("course_code", "")),
            ("成绩", grade.get("score", "")),
            ("学分", grade.get("credit", "")),
            ("绩点", grade_table_rows([grade])[0][4]),
        ]
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        for row, (label, value) in enumerate(fields):
            name = QLabel(label)
            name.setObjectName("detailLabel")
            data = QLabel(str(value or "暂无"))
            data.setObjectName("detailValue")
            data.setWordWrap(True)
            grid.addWidget(name, row, 0)
            grid.addWidget(data, row, 1)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        raw_title = QLabel("原始字段")
        raw_title.setObjectName("cardTitle")
        layout.addWidget(raw_title)

        scroll = QScrollArea()
        scroll.setObjectName("gradeDetailScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        raw_content = QWidget()
        raw_content.setObjectName("gradeDetailContent")
        raw_layout = QVBoxLayout(raw_content)
        raw_layout.setContentsMargins(0, 0, 8, 0)
        raw_layout.setSpacing(8)

        raw = grade.get("raw", {})
        if isinstance(raw, dict) and raw:
            for key in sorted(raw, key=str):
                row_frame = QFrame()
                row_frame.setObjectName("detailRawRow")
                row_layout = QHBoxLayout(row_frame)
                row_layout.setContentsMargins(12, 9, 12, 9)
                key_label = QLabel(str(key))
                key_label.setObjectName("detailLabel")
                key_label.setMinimumWidth(128)
                value_label = QLabel(str(raw.get(key, "")))
                value_label.setObjectName("detailValue")
                value_label.setWordWrap(True)
                row_layout.addWidget(key_label, 0, Qt.AlignTop)
                row_layout.addWidget(value_label, 1)
                raw_layout.addWidget(row_frame)
        else:
            empty = QLabel("暂无原始字段。")
            empty.setObjectName("muted")
            raw_layout.addWidget(empty)
        raw_layout.addStretch(1)
        scroll.setWidget(raw_content)
        layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox()
        close_button = buttons.addButton("关闭", QDialogButtonBox.RejectRole)
        close_button.setObjectName("primaryButton")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class TrendChart(QFrame):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(180)
        self.setObjectName("chart")
        self.setMouseTracking(True)
        self.setFont(QFont("Microsoft YaHei UI", 9))
        self.points: list[tuple[str, float]] = []

    def set_points(self, points: list[tuple[str, float]]) -> None:
        self.points = points
        self.update()

    def _plot_coordinates(self) -> list[tuple[float, float]]:
        if len(self.points) < 2:
            return []
        rect = self.rect().adjusted(20, 18, -20, -40)
        values = [value for _, value in self.points]
        low = min(values)
        high = max(values)
        if high == low:
            high += 0.5
            low -= 0.5
        coords = []
        for index, (_, value) in enumerate(self.points):
            x = rect.left() + index * rect.width() / max(1, len(self.points) - 1)
            y = rect.bottom() - (value - low) / (high - low) * rect.height()
            coords.append((x, y))
        return coords

    def mouseMoveEvent(self, event) -> None:
        hover_radius = 12
        for index, (x, y) in enumerate(self._plot_coordinates()):
            if (event.position().x() - x) ** 2 + (event.position().y() - y) ** 2 <= hover_radius**2:
                semester, value = self.points[index]
                QToolTip.showText(event.globalPosition().toPoint(), f"{semester}\n平均绩点: {value:.2f}", self)
                return
        QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        QToolTip.hideText()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if len(self.points) < 2:
            self._paint_summary(painter)
            return

        rect = self.rect().adjusted(20, 18, -20, -40)
        painter.setPen(QPen(QColor("#e5e7eb"), 1))
        for step in range(4):
            y = rect.top() + step * rect.height() / 3
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))

        coords = self._plot_coordinates()

        area = QPainterPath()
        area.moveTo(coords[0][0], rect.bottom())
        for x, y in coords:
            area.lineTo(x, y)
        area.lineTo(coords[-1][0], rect.bottom())
        area.closeSubpath()
        painter.fillPath(area, QColor(37, 99, 235, 28))

        path = QPainterPath()
        path.moveTo(coords[0][0], coords[0][1])
        for x, y in coords[1:]:
            path.lineTo(x, y)
        painter.setPen(QPen(QColor("#2563eb"), 3))
        painter.drawPath(path)
        painter.setBrush(QColor("#2563eb"))
        painter.setPen(Qt.NoPen)
        for x, y in coords:
            painter.drawEllipse(int(x) - 4, int(y) - 4, 8, 8)
        painter.setPen(QColor("#64748b"))
        for index, (semester, _) in enumerate(self.points):
            if index in (0, len(self.points) - 1) or len(self.points) <= 4:
                painter.drawText(int(coords[index][0]) - 30, self.rect().bottom() - 26, 60, 16, Qt.AlignCenter, semester[-4:])

    def _paint_summary(self, painter: QPainter) -> None:
        panel = self.rect().adjusted(24, 18, -24, -20)
        painter.setPen(QPen(QColor("#dbe7f6"), 1))
        painter.setBrush(QColor("#f8fbff"))
        painter.drawRoundedRect(panel, 16, 16)

        font = painter.font()
        if self.points:
            semester, value = self.points[-1]
            value_text = f"{value:.2f}"
            label = "当前平均绩点"
            note = "还差 1 个学期生成趋势"
            badge = "趋势准备中"
            title = "等待更多学期数据"
            detail_rows = [("当前学期", semester), ("趋势进度", "已记录 1/2 个学期")]
            progress = 0.5
        else:
            value_text = "--"
            label = "暂无成绩快照"
            note = "首次检查后显示概览"
            badge = "等待数据"
            title = "完成配置后自动统计"
            detail_rows = [("当前状态", "尚未建立成绩基线"), ("趋势条件", "至少需要 2 个学期")]
            progress = 0.0

        left_width = max(190, int(panel.width() * 0.36))
        left = panel.adjusted(18, 12, -(panel.width() - left_width), -12)
        right = panel.adjusted(left_width + 28, 14, -22, -14)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#eaf2ff"))
        painter.drawRoundedRect(left, 14, 14)

        value_font = painter.font()
        value_font.setPointSize(28)
        value_font.setBold(True)
        painter.setFont(value_font)
        painter.setPen(QColor("#0f172a"))
        painter.drawText(left.left(), left.top() + 14, left.width(), 42, Qt.AlignCenter, value_text)

        label_font = painter.font()
        label_font.setPointSize(10)
        label_font.setBold(True)
        painter.setFont(label_font)
        painter.setPen(QColor("#334155"))
        painter.drawText(left.left(), left.top() + 56, left.width(), 22, Qt.AlignCenter, label)

        note_font = painter.font()
        note_font.setPointSize(9)
        note_font.setBold(False)
        painter.setFont(note_font)
        painter.setPen(QColor("#64748b"))
        painter.drawText(left.left() + 14, left.top() + 82, left.width() - 28, 24, Qt.AlignCenter, note)

        badge_rect = right.adjusted(0, 0, -(right.width() - 92), -(right.height() - 24))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#dbeafe"))
        painter.drawRoundedRect(badge_rect, 12, 12)
        painter.setPen(QColor("#1d4ed8"))
        badge_font = painter.font()
        badge_font.setPointSize(9)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.drawText(badge_rect, Qt.AlignCenter, badge)

        title_font = painter.font()
        title_font.setPointSize(10)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#0f172a"))
        painter.drawText(right.left(), right.top() + 34, right.width(), 20, Qt.AlignLeft | Qt.AlignVCenter, title)

        progress_top = right.top() + 62
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#e2e8f0"))
        painter.drawRoundedRect(right.left(), progress_top, right.width(), 8, 4, 4)
        painter.setBrush(QColor("#2563eb"))
        painter.drawRoundedRect(right.left(), progress_top, int(right.width() * progress), 8, 4, 4)

        row_font = painter.font()
        row_font.setPointSize(9)
        row_font.setBold(False)
        painter.setFont(row_font)
        for index, (name, value) in enumerate(detail_rows):
            row_top = progress_top + 18 + index * 26
            painter.setPen(QColor("#64748b"))
            painter.drawText(right.left(), row_top, 72, 20, Qt.AlignLeft | Qt.AlignVCenter, name)
            painter.setPen(QColor("#334155"))
            painter.drawText(right.left() + 78, row_top, right.width() - 78, 20, Qt.AlignLeft | Qt.AlignVCenter, value)

        painter.setFont(font)


class DistributionChart(QFrame):
    COLORS = {
        "4-5": QColor("#2563eb"),
        "3-4": QColor("#22c55e"),
        "2-3": QColor("#f59e0b"),
        "0-2": QColor("#ef4444"),
    }

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(180)
        self.setObjectName("chart")
        self.distribution: dict[str, int] = {"4-5": 0, "3-4": 0, "2-3": 0, "0-2": 0}

    def set_distribution(self, distribution: dict[str, int]) -> None:
        self.distribution = distribution
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        total = sum(self.distribution.values())
        if total <= 0:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(self.rect(), Qt.AlignCenter, "暂无可统计绩点")
            return
        size = min(self.width() // 2, self.height() - 36, 132)
        x = 26
        y = (self.height() - size) // 2
        start = 90 * 16
        for bucket, count in self.distribution.items():
            span = int(-360 * 16 * count / total)
            painter.setBrush(self.COLORS[bucket])
            painter.setPen(Qt.NoPen)
            painter.drawPie(x, y, size, size, start, span)
            start += span
        inner = int(size * 0.54)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(x + (size - inner) // 2, y + (size - inner) // 2, inner, inner)

        legend_x = x + size + 24
        painter.setPen(QColor("#475569"))
        for index, bucket in enumerate(self.distribution):
            row_y = y + 18 + index * 28
            painter.setBrush(self.COLORS[bucket])
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(legend_x, row_y - 9, 10, 10)
            painter.setPen(QColor("#475569"))
            percent = self.distribution[bucket] / total * 100
            painter.drawText(legend_x + 18, row_y, f"{bucket}: {percent:.1f}%")


class GradeMonitorQtApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.paths = AppPaths()
        self.paths.ensure()
        self._signals: list[_Signals] = []
        self._last_guidance_action = "一键配置本机"
        self._setup_progress: QProgressDialog | None = None
        self._setup_progress_timer: QTimer | None = None
        self._setup_progress_index = 0
        self.setWindowTitle(f"GDUT 成绩提醒 v{APP_VERSION}")
        self.setWindowIcon(QIcon(str(app_icon_path())))
        self.setMinimumSize(1060, 640)

        self._build_ui()
        self._build_tray()
        self.refresh_all()
        self._fit_to_current_screen()
        QTimer.singleShot(350, self.maybe_show_first_run_wizard)

    def _fit_to_current_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1220, 720)
            return

        available = screen.availableGeometry()
        margin = 48
        width = min(1220, max(self.minimumWidth(), available.width() - margin))
        height = min(720, max(self.minimumHeight(), available.height() - margin))
        self.resize(width, height)
        self.move(
            available.x() + max(0, (available.width() - width) // 2),
            available.y() + max(0, (available.height() - height) // 2),
        )

    def _build_ui(self) -> None:
        shell = QWidget()
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.nav_buttons: list[QPushButton] = []
        root.addWidget(self._sidebar())

        self.pages = QStackedWidget()
        self.pages.setObjectName("content")
        root.addWidget(self.pages, 1)

        self.pages.addWidget(self._dashboard_page())
        self.pages.addWidget(self._grades_page())
        self.pages.addWidget(self._history_page())
        self.pages.addWidget(self._settings_page())
        self.pages.addWidget(self._doctor_page())
        self.pages.addWidget(self._help_page())
        self.pages.addWidget(self._about_page())

        self.setCentralWidget(shell)
        self._set_page(0)
        self._apply_style()

    def _sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(252)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 24, 20, 22)
        layout.setSpacing(8)

        brand = QHBoxLayout()
        icon = QLabel()
        icon.setObjectName("brandIcon")
        icon.setAlignment(Qt.AlignCenter)
        icon.setPixmap(QIcon(str(app_icon_path())).pixmap(34, 34))
        name_box = QVBoxLayout()
        name = QLabel("成绩提醒")
        name.setObjectName("brandName")
        version = QLabel(f"v{APP_VERSION}")
        version.setObjectName("brandVersion")
        name_box.addWidget(name)
        name_box.addWidget(version)
        brand.addWidget(icon)
        brand.addLayout(name_box)
        brand.addStretch(1)
        layout.addLayout(brand)
        layout.addSpacing(22)

        for index, label in enumerate(["总览", "成绩", "提醒历史", "设置", "环境检查", "帮助", "关于"]):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setObjectName("navButton")
            button.clicked.connect(lambda _checked=False, row=index: self._set_page(row))
            self.nav_buttons.append(button)
            layout.addWidget(button)
        layout.addStretch(1)

        safety = QFrame()
        safety.setObjectName("sidebarSafety")
        safety_layout = QVBoxLayout(safety)
        safety_layout.setContentsMargins(0, 14, 0, 0)
        safety_title = QLabel("严格只读")
        safety_title.setObjectName("safetyTitle")
        safety_body = QLabel("只查询成绩接口，密码保存在 Windows 凭据管理器。")
        safety_body.setObjectName("safetyBody")
        safety_body.setWordWrap(True)
        safety_layout.addWidget(safety_title)
        safety_layout.addWidget(safety_body)
        layout.addWidget(safety)
        return sidebar

    def _dashboard_page(self) -> QWidget:
        page = _page()
        title = QLabel("后台正在守着成绩")
        title.setObjectName("title")
        self.status_label = QLabel("正在加载...")
        self.status_label.setObjectName("muted")

        top = QHBoxLayout()
        top.setSpacing(16)
        heading = QVBoxLayout()
        heading.setSpacing(6)
        heading.addWidget(title)
        heading.addWidget(self.status_label)
        top.addLayout(heading, 1)
        check = QPushButton("立即检查")
        check.setObjectName("primaryButton")
        check.setFixedHeight(44)
        check.clicked.connect(self.check_now)
        top.addWidget(check, 0, Qt.AlignTop)
        page.layout().addLayout(top)

        self.status_panel = QFrame()
        self.status_panel.setObjectName("statusPanel")
        status_layout = QHBoxLayout(self.status_panel)
        status_layout.setContentsMargins(24, 22, 24, 22)
        status_layout.setSpacing(18)
        main_status = QVBoxLayout()
        main_status.setSpacing(4)
        status_eyebrow = QLabel("当前状态")
        status_eyebrow.setObjectName("statusEyebrow")
        self.guidance_title = QLabel("正在检查状态...")
        self.guidance_title.setObjectName("statusTitle")
        self.guidance_body = QLabel("")
        self.guidance_body.setWordWrap(True)
        self.guidance_body.setObjectName("statusBody")
        main_status.addWidget(status_eyebrow)
        main_status.addWidget(self.guidance_title)
        main_status.addWidget(self.guidance_body)
        status_layout.addLayout(main_status, 1)
        next_box = QFrame()
        next_box.setObjectName("nextBox")
        next_box.setFixedWidth(186)
        next_layout = QVBoxLayout(next_box)
        next_layout.setContentsMargins(16, 14, 16, 14)
        next_layout.setSpacing(4)
        next_label = QLabel("下一次检查")
        next_label.setObjectName("nextLabel")
        self.next_check_label = QLabel("按设置频率")
        self.next_check_label.setObjectName("nextValue")
        next_layout.addWidget(next_label)
        next_layout.addWidget(self.next_check_label)
        status_layout.addWidget(next_box, 0, Qt.AlignVCenter)
        page.layout().addWidget(self.status_panel)
        page.layout().addWidget(self._runtime_status_card())

        middle = QHBoxLayout()
        middle.setSpacing(16)
        self.recent_card = _card()
        self.recent_card.setMinimumHeight(166)
        recent_layout = QVBoxLayout(self.recent_card)
        recent_layout.setContentsMargins(18, 18, 18, 18)
        recent_layout.setSpacing(12)
        self.recent_title = QLabel("最近变化")
        self.recent_title.setObjectName("cardTitle")
        recent_layout.addWidget(self.recent_title)
        self.recent_scroll = QScrollArea()
        self.recent_scroll.setObjectName("recentScroll")
        self.recent_scroll.setWidgetResizable(True)
        self.recent_scroll.setFrameShape(QFrame.NoFrame)
        self.recent_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.recent_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.recent_scroll.setToolTip("有多条变化时，可拖动右侧滚动条查看更多。")
        self.recent_content = QWidget()
        self.recent_content.setObjectName("recentContent")
        self.recent_list = QVBoxLayout(self.recent_content)
        self.recent_list.setContentsMargins(0, 0, 8, 0)
        self.recent_list.setSpacing(8)
        self.recent_scroll.setWidget(self.recent_content)
        recent_layout.addWidget(self.recent_scroll, 1)
        middle.addWidget(self.recent_card, 6)

        self.config_card = _card()
        self.config_card.setMinimumHeight(166)
        config_layout = QVBoxLayout(self.config_card)
        config_layout.setContentsMargins(18, 18, 18, 18)
        config_layout.setSpacing(12)
        config_title = QLabel("本机配置")
        config_title.setObjectName("cardTitle")
        config_layout.addWidget(config_title)
        self.summary_area = QWidget()
        self.summary_area.setFixedHeight(76)
        self.summary_grid = QGridLayout(self.summary_area)
        self.summary_grid.setHorizontalSpacing(18)
        self.summary_grid.setVerticalSpacing(12)
        self.summary_grid.setContentsMargins(0, 2, 0, 0)
        config_layout.addWidget(self.summary_area)
        config_layout.addStretch(1)
        middle.addWidget(self.config_card, 5)
        page.layout().addLayout(middle)

        actions_card = _card()
        actions = QHBoxLayout(actions_card)
        actions.setContentsMargins(16, 14, 16, 14)
        actions.setSpacing(10)
        for label, callback, secondary in [
            ("一键配置本机", self.one_click_setup, False),
            ("新手向导", self.open_first_run_wizard, True),
            ("打开数据目录", self.open_data_dir, True),
        ]:
            button = QPushButton(label)
            button.setObjectName("secondaryButton" if secondary else "primaryButton")
            button.clicked.connect(callback)
            actions.addWidget(button)
        actions.addStretch(1)
        page.layout().addWidget(actions_card)
        page.layout().addStretch(1)
        return page

    def _runtime_status_card(self) -> QWidget:
        self.runtime_status_card = _card()
        self.runtime_status_card.setObjectName("runtimeCard")
        self.runtime_status_card.setMinimumHeight(190)
        layout = QVBoxLayout(self.runtime_status_card)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(12)
        title = QLabel("运行状态中心")
        title.setObjectName("cardTitle")
        hint = QLabel("看后台是否在查、下次什么时候查、最近有没有错误。")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        header_text = QVBoxLayout()
        header_text.setSpacing(4)
        header_text.addWidget(title)
        header_text.addWidget(hint)
        pause_button = QPushButton("暂停 1 小时")
        pause_button.setObjectName("secondaryButton")
        pause_button.clicked.connect(self.pause_monitor_for_one_hour)
        resume_button = QPushButton("恢复检查")
        resume_button.setObjectName("secondaryButton")
        resume_button.clicked.connect(self.resume_monitor)
        log_button = QPushButton("查看日志")
        log_button.setObjectName("secondaryButton")
        log_button.clicked.connect(self.open_log_file)
        for button in [pause_button, resume_button, log_button]:
            button.setFixedHeight(36)
            button.setMinimumWidth(88)
        top.addLayout(header_text, 1)
        top.addWidget(pause_button, 0, Qt.AlignTop)
        top.addWidget(resume_button, 0, Qt.AlignTop)
        top.addWidget(log_button, 0, Qt.AlignTop)
        layout.addLayout(top)

        self.status_center_grid = QGridLayout()
        self.status_center_grid.setHorizontalSpacing(10)
        self.status_center_grid.setVerticalSpacing(10)
        self.status_center_grid.setContentsMargins(0, 2, 0, 0)
        layout.addLayout(self.status_center_grid)
        return self.runtime_status_card

    def _onboarding_card(self) -> QWidget:
        card = _card()
        card.setObjectName("guideCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(14)

        intro = QVBoxLayout()
        title = QLabel("新手引导")
        title.setObjectName("cardTitle")
        body = QLabel("第一次打开时先点“一键配置本机”。密码不会上传，首次读取只建基线，第一次不会提醒；默认每 30 分钟检查一次。")
        body.setObjectName("muted")
        body.setWordWrap(True)
        intro.addWidget(title)
        intro.addWidget(body)
        layout.addLayout(intro, 2)

        for index, step in enumerate(onboarding_steps(), start=1):
            item = QFrame()
            item.setObjectName("guideStep")
            item_layout = QVBoxLayout(item)
            item_layout.setContentsMargins(12, 10, 12, 10)
            item_layout.setSpacing(4)
            step_title = QLabel(f"{index}. {step['title']}")
            step_title.setObjectName("guideStepTitle")
            step_body = QLabel(step["body"])
            step_body.setObjectName("guideStepBody")
            step_body.setWordWrap(True)
            item_layout.addWidget(step_title)
            item_layout.addWidget(step_body)
            layout.addWidget(item, 2)

        help_button = QPushButton("查看帮助")
        help_button.setObjectName("secondaryButton")
        help_button.clicked.connect(lambda: self._set_page(5))
        layout.addWidget(help_button)
        wizard_button = QPushButton("新手向导")
        wizard_button.setObjectName("secondaryButton")
        wizard_button.clicked.connect(self.open_first_run_wizard)
        layout.addWidget(wizard_button)
        return card

    def _grades_page(self) -> QWidget:
        page = _page()
        title = QLabel("成绩分析")
        title.setObjectName("title")
        subtitle = QLabel("从本地成绩快照计算，不额外请求教务系统接口。")
        subtitle.setObjectName("muted")
        self.grade_stats_note = QLabel("")
        self.grade_stats_note.setObjectName("muted")

        metrics = QHBoxLayout()
        self.avg_gpa_label = QLabel("--")
        self.counted_courses_label = QLabel("--")
        self.highest_score_label = QLabel("--")
        for label, value_label in [
            ("平均绩点", self.avg_gpa_label),
            ("参与统计课程", self.counted_courses_label),
            ("最高成绩", self.highest_score_label),
        ]:
            card = _card()
            layout = QVBoxLayout(card)
            layout.setContentsMargins(18, 16, 18, 16)
            layout.setSpacing(6)
            name = QLabel(label)
            name.setObjectName("muted")
            value_label.setObjectName("largeMetric")
            layout.addWidget(name)
            layout.addWidget(value_label)
            metrics.addWidget(card)

        charts = QHBoxLayout()
        trend_card = _card()
        trend_layout = QVBoxLayout(trend_card)
        trend_layout.setContentsMargins(18, 16, 18, 16)
        trend_layout.setSpacing(10)
        trend_title = QLabel("平均绩点变化")
        trend_title.setObjectName("cardTitle")
        self.trend_chart = TrendChart()
        trend_layout.addWidget(trend_title)
        trend_layout.addWidget(self.trend_chart)
        charts.addWidget(trend_card, 6)

        distribution_card = _card()
        distribution_layout = QVBoxLayout(distribution_card)
        distribution_layout.setContentsMargins(18, 16, 18, 16)
        distribution_layout.setSpacing(10)
        distribution_title = QLabel("绩点分布")
        distribution_title.setObjectName("cardTitle")
        self.distribution_chart = DistributionChart()
        distribution_layout.addWidget(distribution_title)
        distribution_layout.addWidget(self.distribution_chart)
        charts.addWidget(distribution_card, 4)

        filters = QHBoxLayout()
        self.semester_filter = QComboBox()
        self.semester_filter.currentTextChanged.connect(self.refresh_grades)
        self.include_electives = QCheckBox("包含选修")
        self.include_electives.setChecked(True)
        self.include_electives.stateChanged.connect(self.refresh_grades)
        self.course_search = QLineEdit()
        self.course_search.setPlaceholderText("搜索课程名称或代码")
        self.course_search.textChanged.connect(self.refresh_grades)
        export_transcript = QPushButton("导出成绩单")
        export_transcript.setObjectName("secondaryButton")
        export_transcript.setToolTip("从本地成绩快照生成 PDF 或 HTML，不提交学校成绩单申请。")
        export_transcript.clicked.connect(self.export_transcript)
        official_transcript = QPushButton("官方成绩单")
        official_transcript.setObjectName("secondaryButton")
        official_transcript.setToolTip("打开学校网上办事大厅，由你手动查看或下载官方成绩单。")
        official_transcript.clicked.connect(self.open_official_transcript_portal)
        filters.addWidget(self.semester_filter)
        filters.addWidget(self.include_electives)
        filters.addWidget(self.course_search, 1)
        filters.addWidget(export_transcript)
        filters.addWidget(official_transcript)

        self.grades_table = QTableWidget(0, 5)
        self.grades_table.setHorizontalHeaderLabels(["学期", "课程", "成绩", "学分", "绩点"])
        self._prepare_table(self.grades_table)
        self.grades_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.visible_grades: list[dict] = []
        self.grades_table.cellDoubleClicked.connect(self.show_grade_detail)
        page.layout().addWidget(title)
        page.layout().addWidget(subtitle)
        page.layout().addWidget(self.grade_stats_note)
        page.layout().addLayout(metrics)
        page.layout().addLayout(charts)
        page.layout().addLayout(filters)
        page.layout().addWidget(self.grades_table, 1)
        return page

    def _history_page(self) -> QWidget:
        page = _page()
        title = QLabel("提醒历史")
        title.setObjectName("title")
        subtitle = QLabel("这里只记录已经提醒过的新增成绩和成绩变化，不包含完整个人成绩明细。")
        subtitle.setObjectName("muted")
        self.history_table = QTableWidget(0, 7)
        self.history_table.setHorizontalHeaderLabels(["时间", "类型", "学期", "课程", "成绩", "通知渠道", "发送结果"])
        self._prepare_table(self.history_table)
        self.history_table.setColumnWidth(0, 170)
        self.history_table.setColumnWidth(1, 90)
        self.history_table.setColumnWidth(2, 100)
        self.history_table.setColumnWidth(4, 78)
        self.history_table.setColumnWidth(6, 110)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        page.layout().addWidget(title)
        page.layout().addWidget(subtitle)
        page.layout().addWidget(self.history_table, 1)
        return page

    def _settings_page(self) -> QWidget:
        page = _page()
        title = QLabel("设置")
        title.setObjectName("title")
        config = load_config(self.paths)
        self.interval = QSpinBox()
        self.interval.setRange(1, 1440)
        self.interval.setValue(int(config.get("poll_interval_minutes", 30)))
        intro = QLabel("调整后台检查频率、重新登录，或者管理 Windows 登录后的后台提醒。")
        intro.setObjectName("muted")
        form_card = _card()
        form = QFormLayout(form_card)
        form.setContentsMargins(18, 16, 18, 16)
        form.addRow("查询频率(分钟)", self.interval)
        save = QPushButton("保存频率")
        save.setObjectName("primaryButton")
        save.clicked.connect(self.save_interval)
        login = QPushButton("重新登录/初始化")
        login.setObjectName("secondaryButton")
        login.clicked.connect(self.setup_login)
        install = QPushButton("安装自启动")
        install.setObjectName("secondaryButton")
        install.clicked.connect(self.install_startup)
        uninstall = QPushButton("取消自启动")
        uninstall.setObjectName("secondaryButton")
        uninstall.clicked.connect(self.uninstall_startup)
        open_dir = QPushButton("打开数据目录")
        open_dir.setObjectName("secondaryButton")
        open_dir.clicked.connect(self.open_data_dir)
        update = QPushButton("检查更新")
        update.setObjectName("secondaryButton")
        update.clicked.connect(self.check_for_updates)
        cleanup = QPushButton("卸载辅助")
        cleanup.setObjectName("secondaryButton")
        cleanup.setToolTip("清理便携版残留启动项，或查看卸载前的数据保留说明。")
        cleanup.clicked.connect(self.open_cleanup_assistant)
        notifications = QPushButton("多设备通知")
        notifications.setObjectName("secondaryButton")
        notifications.clicked.connect(self.open_notification_settings)
        export_settings_button = QPushButton("导出设置")
        export_settings_button.setObjectName("secondaryButton")
        export_settings_button.setToolTip("导出可迁移的非敏感设置；不会导出学号、密码、Cookie 或通知密钥。")
        export_settings_button.clicked.connect(self.export_settings_file)
        import_settings_button = QPushButton("导入设置")
        import_settings_button.setObjectName("secondaryButton")
        import_settings_button.setToolTip("导入另一台电脑导出的非敏感设置；不会覆盖本机已保存账号。")
        import_settings_button.clicked.connect(self.import_settings_file)
        reset_settings = QPushButton("恢复默认")
        reset_settings.setObjectName("secondaryButton")
        reset_settings.setToolTip("恢复推荐配置，但保留已保存账号和新手向导状态。")
        reset_settings.clicked.connect(self.reset_settings_to_defaults)

        for button in [save, login, install, uninstall, open_dir, update, cleanup, notifications, export_settings_button, import_settings_button, reset_settings]:
            button.setMinimumWidth(108)

        page.layout().addWidget(title)
        page.layout().addWidget(intro)

        settings_grid = QGridLayout()
        settings_grid.setHorizontalSpacing(14)
        settings_grid.setVerticalSpacing(14)
        settings_grid.addWidget(form_card, 0, 0)
        settings_grid.addWidget(self._settings_action_card("账号", "重新登录或初始化本机配置。", [login]), 0, 1)
        settings_grid.addWidget(self._settings_action_card("后台启动", "控制 Windows 登录后是否自动检查成绩。", [install, uninstall]), 1, 0)
        settings_grid.addWidget(self._settings_action_card("多设备通知", "配置微信类、ntfy 或邮件提醒，并设置通知隐私级别。", [notifications]), 1, 1)
        settings_grid.addWidget(self._settings_action_card("配置迁移", "导出或导入非敏感设置，换电脑时不用重新调整偏好。", [export_settings_button, import_settings_button, reset_settings]), 2, 0, 1, 2)
        settings_grid.addWidget(self._settings_action_card("数据与更新", "打开本地数据目录、检查 GitHub 新版本，或处理卸载残留。", [open_dir, update, cleanup]), 3, 0, 1, 2)
        settings_grid.setColumnStretch(0, 1)
        settings_grid.setColumnStretch(1, 1)
        form_actions = QHBoxLayout()
        form_actions.addWidget(save)
        form_actions.addStretch(1)
        form.addRow("", form_actions)
        page.layout().addLayout(settings_grid)
        page.layout().addStretch(1)
        return page

    def _settings_action_card(self, title: str, body: str, buttons: list[QPushButton]) -> QFrame:
        card = _card()
        card.setMinimumHeight(132)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("cardTitle")
        detail = QLabel(body)
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for button in buttons:
            actions.addWidget(button)
        actions.addStretch(1)
        layout.addWidget(heading)
        layout.addWidget(detail)
        layout.addStretch(1)
        layout.addLayout(actions)
        return card

    def _doctor_page(self) -> QWidget:
        page = _page()
        top = QHBoxLayout()
        title = QLabel("环境检查")
        title.setObjectName("title")
        refresh = QPushButton("重新检查")
        refresh.clicked.connect(self.refresh_doctor)
        export = QPushButton("导出诊断包")
        export.clicked.connect(self.export_diagnostics)
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(refresh)
        top.addWidget(export)
        self.doctor_table = QTableWidget(0, 4)
        self.doctor_table.setHorizontalHeaderLabels(["状态", "检查项", "结果", "建议"])
        self._prepare_table(self.doctor_table)
        self.doctor_table.setColumnWidth(0, 80)
        self.doctor_table.setColumnWidth(1, 130)
        self.doctor_table.setColumnWidth(2, 220)
        self.doctor_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        page.layout().addLayout(top)
        page.layout().addWidget(self.doctor_table, 1)
        return page

    def _help_page(self) -> QWidget:
        page = _page()
        title = QLabel("帮助")
        title.setObjectName("title")
        subtitle = QLabel("这里集中放第一次使用、成绩提醒、数据隐私和排错说明。")
        subtitle.setObjectName("muted")
        top = QHBoxLayout()
        top.addWidget(title)
        top.addStretch(1)
        wizard = QPushButton("打开新手向导")
        wizard.setObjectName("secondaryButton")
        wizard.clicked.connect(self.open_first_run_wizard)
        top.addWidget(wizard)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("helpScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content.setObjectName("helpContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(14)

        for section in help_sections():
            card = _card()
            card.setObjectName("helpSection")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(18, 16, 18, 16)
            card_layout.setSpacing(10)

            section_title = QLabel(str(section["title"]))
            section_title.setObjectName("helpSectionTitle")
            body = QLabel(str(section["body"]))
            body.setObjectName("helpBody")
            body.setWordWrap(True)
            card_layout.addWidget(section_title)
            card_layout.addWidget(body)

            items = section.get("items", [])
            if isinstance(items, list):
                for item in items:
                    row = QFrame()
                    row.setObjectName("helpItem")
                    row_layout = QHBoxLayout(row)
                    row_layout.setContentsMargins(10, 8, 10, 8)
                    row_layout.setSpacing(10)
                    bullet = QLabel("")
                    bullet.setObjectName("helpBullet")
                    bullet.setFixedSize(8, 8)
                    text = QLabel(str(item))
                    text.setObjectName("helpItemText")
                    text.setWordWrap(True)
                    row_layout.addWidget(bullet, 0, Qt.AlignTop)
                    row_layout.addWidget(text, 1)
                    card_layout.addWidget(row)

            content_layout.addWidget(card)

        content_layout.addStretch(1)
        scroll.setWidget(content)

        page.layout().addLayout(top)
        page.layout().addWidget(subtitle)
        page.layout().addWidget(scroll, 1)
        return page

    def _about_page(self) -> QWidget:
        page = _page()
        title = QLabel("关于")
        title.setObjectName("title")
        body = QLabel(about_text())
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.setObjectName("aboutBody")
        card = _card()
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)
        card_layout.addWidget(body)
        update = QPushButton("检查更新")
        update.setObjectName("secondaryButton")
        update.clicked.connect(self.check_for_updates)
        card_layout.addWidget(update, 0, Qt.AlignLeft)

        scroll = QScrollArea()
        scroll.setObjectName("aboutScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("aboutContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.addWidget(card)
        content_layout.addStretch(1)
        scroll.setWidget(content)

        page.layout().addWidget(title)
        page.layout().addWidget(scroll, 1)
        return page

    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = QSystemTrayIcon(QIcon(str(app_icon_path())), self)
        menu = QMenu()
        show_action = QAction("打开主界面", self)
        show_action.triggered.connect(self.open_runtime_status)
        status_action = QAction("查看运行状态", self)
        status_action.triggered.connect(self.open_runtime_status)
        check_action = QAction("立即检查", self)
        check_action.triggered.connect(self.check_now)
        pause_action = QAction("暂停提醒 1 小时", self)
        pause_action.triggered.connect(self.pause_monitor_for_one_hour)
        resume_action = QAction("恢复后台检查", self)
        resume_action.triggered.connect(self.resume_monitor)
        log_action = QAction("查看日志", self)
        log_action.triggered.connect(self.open_log_file)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(show_action)
        menu.addAction(status_action)
        menu.addAction(check_action)
        menu.addSeparator()
        menu.addAction(pause_action)
        menu.addAction(resume_action)
        menu.addSeparator()
        menu.addAction(log_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.show()

    def open_runtime_status(self) -> None:
        self.showNormal()
        self._set_page(0)
        self.raise_()
        self.activateWindow()

    def _set_page(self, row: int) -> None:
        self.pages.setCurrentIndex(max(0, row))
        for index, button in enumerate(self.nav_buttons):
            button.setChecked(index == row)

    def refresh_all(self) -> None:
        self.refresh_status()
        self.refresh_grades()
        self.refresh_history()
        self.refresh_doctor()

    def refresh_status(self) -> None:
        config = load_config(self.paths)
        state = load_state(self.paths)
        installed = autostart_exists()
        results = run_checks(self.paths)
        guidance = setup_guidance(installed, config, state, overall_ok(results))
        self.status_label.setText(status_summary(installed, state))
        self.guidance_title.setText(guidance["title"])
        self.guidance_body.setText(guidance["body"])
        self._last_guidance_action = guidance["primary_action"]
        self.next_check_label.setText(f"每 {config.get('poll_interval_minutes', 30)} 分钟")
        self._set_recent_changes(recent_change_rows(state, limit=20))
        self._set_summary_cards(state, config, installed)
        self._set_status_center(status_center_rows(config, state, installed)[:3])

    def _set_recent_changes(self, recent: list[tuple[str, str, str]]) -> None:
        while self.recent_list.count():
            item = self.recent_list.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        if not recent:
            self.recent_title.setText("最近变化")
            self.recent_content.setMinimumHeight(74)
            empty = QFrame()
            empty.setObjectName("recentEmpty")
            empty.setMinimumHeight(68)
            layout = QVBoxLayout(empty)
            layout.setContentsMargins(14, 14, 14, 14)
            title = QLabel("暂无新的成绩变化")
            title.setObjectName("recentCourse")
            body = QLabel("首次运行只建立基线，之后有新增或变化才提醒。")
            body.setObjectName("recentMeta")
            body.setWordWrap(True)
            layout.addWidget(title)
            layout.addWidget(body)
            self.recent_list.addWidget(empty)
            self.recent_list.addStretch(1)
            return

        self.recent_title.setText(f"最近变化 · {len(recent)} 条")
        self.recent_content.setMinimumHeight(len(recent) * 72)
        for course, score, semester in recent:
            row = QFrame()
            row.setObjectName("recentRow")
            row.setMinimumHeight(64)
            row.setToolTip(f"{course}\n学期: {semester}\n成绩: {score or '已更新'}")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(14, 10, 12, 10)
            layout.setSpacing(12)

            text_box = QVBoxLayout()
            text_box.setSpacing(3)
            course_label = QLabel(course or "未命名课程")
            course_label.setObjectName("recentCourse")
            course_label.setWordWrap(True)
            meta_label = QLabel(f"{semester or '未知学期'} · 最新提醒")
            meta_label.setObjectName("recentMeta")
            text_box.addWidget(course_label)
            text_box.addWidget(meta_label)

            score_label = QLabel(score or "已更新")
            score_label.setObjectName("scoreBadge")
            score_label.setAlignment(Qt.AlignCenter)
            score_label.setMinimumWidth(74)

            layout.addLayout(text_box, 1)
            layout.addWidget(score_label)
            self.recent_list.addWidget(row)
        self.recent_list.addStretch(1)

    def _set_status_center(self, rows: list[dict[str, str]]) -> None:
        while self.status_center_grid.count():
            item = self.status_center_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        columns = 3
        min_height = 100
        if hasattr(self, "runtime_status_card"):
            self.runtime_status_card.setMinimumHeight(190)
        for column in range(columns):
            self.status_center_grid.setColumnStretch(column, 1)
        for index, row_data in enumerate(rows):
            tone = row_data.get("tone", "neutral").title()
            tile = QFrame()
            tile.setObjectName("runtimeTile")
            tile.setMinimumHeight(min_height)
            tile.setMinimumWidth(150)
            tile.setToolTip(
                f"{row_data.get('label', '')}\n{row_data.get('value', '')}\n{row_data.get('detail', '')}".strip()
            )
            layout = QVBoxLayout(tile)
            layout.setContentsMargins(14, 12, 14, 12)
            layout.setSpacing(5)

            label = QLabel(row_data.get("label", ""))
            label.setObjectName("runtimeLabel")
            value = QLabel(row_data.get("value", ""))
            value.setObjectName(f"runtimeValue{tone}")
            value.setWordWrap(True)
            detail = QLabel(row_data.get("detail", ""))
            detail.setObjectName("runtimeDetail")
            detail.setWordWrap(True)

            layout.addWidget(label)
            layout.addWidget(value)
            layout.addWidget(detail)
            self.status_center_grid.addWidget(tile, index // columns, index % columns)

    def _set_summary_cards(self, state: dict, config: dict, installed: bool) -> None:
        while self.summary_grid.count():
            item = self.summary_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        grades = state.get("grades", {})
        values = [
            ("成绩数量", str(len(grades) if isinstance(grades, dict) else 0), "metric"),
            ("提醒记录", str(len(state.get("history", [])) if isinstance(state.get("history", []), list) else 0), "metric"),
            ("安全边界", "严格只读", "metricCompact"),
        ]
        for column in range(len(values)):
            self.summary_grid.setColumnStretch(column, 1)
        for index, (label, value, style_name) in enumerate(values):
            card = QFrame()
            card.setObjectName("metricTile")
            card.setMinimumWidth(112)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(6, 2, 6, 2)
            layout.setSpacing(6)
            name = QLabel(label)
            name.setObjectName("summaryLabel")
            name.setAlignment(Qt.AlignCenter)
            number = QLabel(value)
            number.setObjectName("summaryBadge" if label == "安全边界" else "summaryNumber")
            number.setAlignment(Qt.AlignCenter)
            number.setWordWrap(True)
            layout.addWidget(name)
            layout.addWidget(number, 0, Qt.AlignCenter)
            self.summary_grid.addWidget(card, 0, index)

    def refresh_grades(self) -> None:
        grades = list(load_state(self.paths).get("grades", {}).values())
        current_semester = self.semester_filter.currentText() if self.semester_filter.count() else "全部学期"
        options = semester_options(grades)
        self.semester_filter.blockSignals(True)
        self.semester_filter.clear()
        self.semester_filter.addItems(options)
        if current_semester in options:
            self.semester_filter.setCurrentText(current_semester)
        self.semester_filter.blockSignals(False)

        filtered = filter_grades(
            grades,
            semester=self.semester_filter.currentText(),
            search_text=self.course_search.text(),
            include_electives=self.include_electives.isChecked(),
        )
        self.visible_grades = sorted(
            filtered,
            key=lambda grade: (str(grade.get("semester", "")), str(grade.get("course_name", ""))),
            reverse=True,
        )
        analytics = grade_analytics(filtered)
        self.avg_gpa_label.setText("--" if analytics["average_gpa"] is None else f"{analytics['average_gpa']:.2f}")
        self.counted_courses_label.setText(str(analytics["numeric_gpa_count"]))
        note_parts = [f"本地快照共 {analytics['course_count']} 门", f"参与统计学分 {analytics['counted_credit_total']:g}"]
        if analytics["uncounted_course_count"]:
            note_parts.append(f"{analytics['uncounted_course_count']} 门缺少成绩或绩点，暂不参与平均绩点")
        self.grade_stats_note.setText(" · ".join(note_parts))
        if analytics["highest_score"] is None:
            self.highest_score_label.setText("--")
        else:
            self.highest_score_label.setText(f"{analytics['highest_score']:.0f}")
        self.trend_chart.set_points(analytics["semester_trend"])
        self.distribution_chart.set_distribution(analytics["distribution"])
        self._fill_table(self.grades_table, grade_table_rows(self.visible_grades))

    def show_grade_detail(self, row: int, _column: int) -> None:
        if row < 0 or row >= len(self.visible_grades):
            return
        GradeDetailDialog(self, self.visible_grades[row]).exec()

    def refresh_history(self) -> None:
        self._fill_table(self.history_table, history_table_rows(load_state(self.paths), include_delivery=True))

    def refresh_doctor(self) -> None:
        self._fill_table(self.doctor_table, doctor_table_rows(run_checks(self.paths)))

    def _fill_table(self, table: QTableWidget, rows: list[tuple]) -> None:
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(str(value)))
        table.resizeRowsToContents()

    def _prepare_table(self, table: QTableWidget) -> None:
        table.verticalHeader().setVisible(False)
        table.setShowGrid(True)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setEditTriggers(QTableWidget.NoEditTriggers)

    def run_guidance_action(self) -> None:
        action = self._last_guidance_action
        if action == "查看环境检查":
            self._set_page(4)
        elif action == "立即检查":
            self.check_now()
        elif action == "安装自启动":
            self.install_startup()
        else:
            self.one_click_setup()

    def maybe_show_first_run_wizard(self) -> None:
        config = load_config(self.paths)
        state = load_state(self.paths)
        if config.get("student_id") or state.get("grades") or config.get("first_run_wizard_seen"):
            return
        self.open_first_run_wizard(auto=True)

    def open_first_run_wizard(self, auto: bool = False) -> None:
        dialog = FirstRunWizardDialog(self)
        result = dialog.exec()
        if auto or dialog.start_requested:
            config = load_config(self.paths)
            config["first_run_wizard_seen"] = True
            save_config(self.paths, config)
        if result == QDialog.Accepted and dialog.start_requested:
            self.one_click_setup()

    def one_click_setup(self) -> None:
        dialog = FirstRunSetupDialog(self, self.interval.value())
        if dialog.exec() != QDialog.Accepted:
            return
        self.interval.setValue(dialog.options()["interval_minutes"])
        self._show_setup_progress()
        self._run_background(
            lambda: self._one_click_setup_worker(dialog.options()),
            self._one_click_setup_complete,
            self._one_click_setup_failed,
        )

    def _show_setup_progress(self) -> None:
        self._close_setup_progress()
        self._setup_progress_index = 0
        self._setup_progress_steps = [
            "正在检查本机环境...",
            "正在保存账号到 Windows 凭据管理器...",
            "正在打开学校登录页面；如遇验证码，请在浏览器里完成。",
            "正在只读读取成绩并建立本地基线...",
            "正在配置后台自启动...",
        ]
        first_message = f"{self._setup_progress_steps[0]}\n请保持窗口打开；如浏览器弹出，请按学校页面完成登录。"
        self._setup_progress = QProgressDialog(first_message, "", 0, 0, self)
        self._setup_progress.setWindowTitle("一键配置本机")
        self._setup_progress.setCancelButton(None)
        self._setup_progress.setWindowModality(Qt.WindowModal)
        self._setup_progress.setMinimumWidth(480)
        self._setup_progress.setMinimumHeight(130)
        self._setup_progress.setMinimumDuration(0)
        self._setup_progress.setAutoClose(False)
        self._setup_progress.show()

        self._setup_progress_timer = QTimer(self)
        self._setup_progress_timer.timeout.connect(self._advance_setup_progress)
        self._setup_progress_timer.start(2200)

    def _advance_setup_progress(self) -> None:
        if not self._setup_progress:
            return
        self._setup_progress_index = min(self._setup_progress_index + 1, len(self._setup_progress_steps) - 1)
        self._setup_progress.setLabelText(
            f"{self._setup_progress_steps[self._setup_progress_index]}\n请保持窗口打开；如浏览器弹出，请按学校页面完成登录。"
        )

    def _close_setup_progress(self) -> None:
        if self._setup_progress_timer:
            self._setup_progress_timer.stop()
            self._setup_progress_timer.deleteLater()
            self._setup_progress_timer = None
        if self._setup_progress:
            self._setup_progress.close()
            self._setup_progress.deleteLater()
            self._setup_progress = None

    def _one_click_setup_worker(self, options: dict) -> tuple[list[dict], FirstRunSetupResult]:
        result = run_first_run_setup(paths=self.paths, **options)
        return list(load_state(self.paths).get("grades", {}).values()), result

    def _one_click_setup_complete(self, payload: tuple[list[dict], FirstRunSetupResult]) -> None:
        self._close_setup_progress()
        grades, result = payload
        self._fill_table(self.grades_table, grade_table_rows(grades))
        self.refresh_all()
        self._set_page(0)
        if result.startup_mode == "failed":
            QMessageBox.warning(self, "一键配置本机", "成绩基线已建立，但自启动安装失败。请稍后手动重试。")
            return
        QMessageBox.information(
            self,
            "首次配置已完成",
            f"现在已经可以后台提醒了。\n\n已建立 {result.grade_count} 条成绩基线；首次配置不会对已有成绩弹通知。",
        )

    def _one_click_setup_failed(self, message: str) -> None:
        self._close_setup_progress()
        QMessageBox.critical(self, "一键配置本机", message)

    def check_now(self) -> None:
        self._run_background(self._check_now_worker, self._check_complete)

    def _check_now_worker(self) -> tuple[list[dict], list[dict]]:
        config = load_config(self.paths)
        student_id = config.get("student_id", "")
        password = CredentialStore().get_password(student_id) if student_id else None
        session = AuthManager(self.paths).get_session(auto_login=True, student_id=student_id, password=password)
        fetcher = GradeApiClient(session)
        monitor = GradeMonitor(self.paths, fetcher=fetcher, notifier=build_notifier(self.paths))
        changes = monitor.run_once()
        return fetcher.fetch_grades(), changes

    def _check_complete(self, payload: tuple[list[dict], list[dict]]) -> None:
        grades, changes = payload
        self._fill_table(self.grades_table, grade_table_rows(grades))
        self.refresh_all()
        QMessageBox.information(self, "立即检查", f"检查完成，发现 {len(changes)} 项变化。")

    def setup_login(self) -> None:
        dialog = FirstRunSetupDialog(self, self.interval.value())
        dialog.autostart.setChecked(False)
        if dialog.exec() != QDialog.Accepted:
            return
        options = dialog.options()
        options["install_autostart"] = False
        self._show_setup_progress()
        self._run_background(lambda: self._one_click_setup_worker(options), self._one_click_setup_complete, self._one_click_setup_failed)

    def save_interval(self) -> None:
        config = set_poll_interval(self.paths, self.interval.value())
        self.interval.setValue(int(config["poll_interval_minutes"]))
        self.refresh_status()
        QMessageBox.information(self, "设置", f"查询频率已设置为每 {config['poll_interval_minutes']} 分钟。")

    def open_notification_settings(self) -> None:
        dialog = NotificationSettingsDialog(self, self.paths)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_status()
            QMessageBox.information(self, "多设备通知", "多设备通知设置已保存。")

    def open_cleanup_assistant(self) -> None:
        dialog = CleanupAssistantDialog(self, self.paths)
        dialog.exec()

    def install_startup(self) -> None:
        result = install_task_or_startup(prefer_startup=True)
        if result.returncode == 0:
            self.refresh_status()
            message = "已安装用户启动项，登录 Windows 后会自动后台检查。"
            QMessageBox.information(self, "自启动", message)
        else:
            QMessageBox.critical(self, "自启动失败", result.stderr or result.stdout)

    def uninstall_startup(self) -> None:
        result = uninstall_task_and_startup(skip_schtasks=True)
        if result.returncode == 0:
            self.refresh_status()
            QMessageBox.information(self, "自启动", "已取消自启动。")
        else:
            QMessageBox.critical(self, "取消失败", result.stderr or result.stdout)

    def open_data_dir(self) -> None:
        os.startfile(self.paths.root)

    def export_settings_file(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self,
            "导出设置",
            str(self.paths.root / "gdut-grade-monitor-settings.json"),
            "JSON 文件 (*.json)",
        )
        if not target:
            return
        try:
            result = export_settings(self.paths, Path(target))
        except Exception as exc:
            QMessageBox.critical(self, "导出设置失败", f"{type(exc).__name__}: {exc}")
            return
        QMessageBox.information(self, "导出设置", f"已导出非敏感设置:\n{result}\n\n不包含学号、密码、Cookie 或通知密钥。")

    def import_settings_file(self) -> None:
        source, _ = QFileDialog.getOpenFileName(
            self,
            "导入设置",
            str(self.paths.root),
            "JSON 文件 (*.json)",
        )
        if not source:
            return
        try:
            config = import_settings(self.paths, Path(source))
        except Exception as exc:
            QMessageBox.critical(self, "导入设置失败", f"{type(exc).__name__}: {exc}")
            return
        self.interval.setValue(int(config.get("poll_interval_minutes", 30)))
        self.refresh_all()
        QMessageBox.information(self, "导入设置", "已导入非敏感设置。本机已保存账号不会被覆盖，通知密钥仍需在凭据管理器中重新保存。")

    def reset_settings_to_defaults(self) -> None:
        answer = QMessageBox.question(
            self,
            "恢复默认",
            "是否恢复推荐配置？\n\n会重置查询频率、暂停状态和通知开关，但保留已保存账号和本地成绩快照。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        config = reset_config(self.paths)
        self.interval.setValue(int(config.get("poll_interval_minutes", 30)))
        self.refresh_all()
        QMessageBox.information(self, "恢复默认", "已恢复推荐配置。")

    def open_log_file(self) -> None:
        self.paths.ensure()
        if self.paths.log_file.exists():
            os.startfile(self.paths.log_file)
            return
        os.startfile(self.paths.log_dir)
        QMessageBox.information(self, "查看日志", "暂时还没有日志文件，已打开日志目录。")

    def pause_monitor_for_one_hour(self) -> None:
        config = load_config(self.paths)
        paused_until = datetime.now() + timedelta(hours=1)
        config["monitor_paused_until"] = paused_until.isoformat(timespec="seconds")
        save_config(self.paths, config)
        self.refresh_status()
        message = f"已暂停到 {paused_until.strftime('%H:%M')}，期间仍可手动立即检查。"
        if self.tray:
            self.tray.showMessage("GDUT 成绩提醒", message, QSystemTrayIcon.Information, 3000)
        else:
            QMessageBox.information(self, "暂停提醒", message)

    def resume_monitor(self) -> None:
        config = load_config(self.paths)
        config.pop("monitor_paused_until", None)
        save_config(self.paths, config)
        self.refresh_status()
        message = "已恢复后台自动检查。"
        if self.tray:
            self.tray.showMessage("GDUT 成绩提醒", message, QSystemTrayIcon.Information, 3000)
        else:
            QMessageBox.information(self, "恢复后台检查", message)

    def check_for_updates(self) -> None:
        self._run_background(lambda: check_latest_release(APP_VERSION), self._update_check_complete)

    def _update_check_complete(self, release: GitHubRelease) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("检查更新")
        box.setIcon(QMessageBox.Information)
        if release.is_newer:
            box.setText(f"发现新版本 {release.tag_name}")
            box.setInformativeText(f"当前版本: v{APP_VERSION}\n最新版本: {release.name}\n\n是否打开下载页面？")
            open_button = box.addButton("打开下载页", QMessageBox.AcceptRole)
            box.addButton("稍后", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is open_button:
                QDesktopServices.openUrl(QUrl(release.url))
            return
        box.setText("当前已经是最新版本")
        box.setInformativeText(f"当前版本: v{APP_VERSION}\n最新版本: {release.tag_name}")
        box.addButton(QMessageBox.Ok)
        box.exec()

    def export_diagnostics(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self,
            "导出诊断包",
            str(self.paths.root / "gdut-grade-monitor-diagnostics.zip"),
            "Zip 文件 (*.zip)",
        )
        if not target:
            return
        try:
            result = create_diagnostics_zip(paths=self.paths, output_path=Path(target))
        except Exception as exc:
            QMessageBox.critical(self, "导出诊断包失败", f"{type(exc).__name__}: {exc}")
            return
        QMessageBox.information(self, "导出诊断包", f"已导出诊断包:\n{result}\n\n已隐藏敏感信息。")

    def export_transcript(self) -> None:
        state = load_state(self.paths)
        grades = list(state.get("grades", {}).values())
        if not grades:
            QMessageBox.warning(self, "导出成绩单", "还没有本地成绩快照。请先完成一键配置或立即检查。")
            return

        config = load_config(self.paths)
        profile_dialog = TranscriptExportDialog(self, config)
        if profile_dialog.exec() != QDialog.Accepted:
            return
        profile = profile_dialog.profile()
        config.update(profile)
        if profile_dialog.remember.isChecked():
            saved_config = load_config(self.paths)
            saved_config.update(profile)
            save_config(self.paths, saved_config)

        default_name = f"GDUT本地成绩单_{date.today().strftime('%Y%m%d')}.pdf"
        target, selected_filter = QFileDialog.getSaveFileName(
            self,
            "导出成绩单",
            str(self.paths.root / default_name),
            "PDF 文件 (*.pdf);;网页文件 (*.html)",
        )
        if not target:
            return

        output = Path(target)
        if not output.suffix:
            output = output.with_suffix(".html" if "html" in selected_filter.lower() else ".pdf")

        try:
            if output.suffix.lower() == ".pdf":
                self._write_transcript_pdf(output, build_transcript_html(grades, config))
            else:
                write_transcript_html(output, grades, config)
        except Exception as exc:
            QMessageBox.critical(self, "导出成绩单失败", f"{type(exc).__name__}: {exc}")
            return

        QMessageBox.information(
            self,
            "导出成绩单",
            f"已导出成绩单:\n{output}\n\n{TRANSCRIPT_NOTICE}",
        )

    def open_official_transcript_portal(self) -> None:
        opened = AuthManager(self.paths).open_url_with_login_profile(OFFICIAL_TRANSCRIPT_PORTAL_URL)
        if not opened:
            QDesktopServices.openUrl(QUrl(OFFICIAL_TRANSCRIPT_PORTAL_URL))
        QMessageBox.information(self, "官方成绩单", official_transcript_guidance())

    def _write_transcript_pdf(self, output: Path, html: str) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(str(output))
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter)
        document = QTextDocument()
        document.setHtml(html)
        document.setPageSize(printer.pageRect(QPrinter.Point).size())
        document.print_(printer)

    def _run_background(
        self,
        target: Callable[[], object],
        on_success: Callable[[object], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        signals = _Signals()
        self._signals.append(signals)

        def cleanup() -> None:
            if signals in self._signals:
                self._signals.remove(signals)

        signals.success.connect(lambda result: (cleanup(), on_success(result)))
        signals.error.connect(
            lambda message: (
                cleanup(),
                on_error(message) if on_error else QMessageBox.critical(self, "GDUT 成绩提醒", message),
            )
        )

        def runner() -> None:
            try:
                signals.success.emit(target())
            except Exception as exc:
                signals.error.emit(user_friendly_error_message(exc))

        threading.Thread(target=runner, daemon=True).start()

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget { font-family: "Microsoft YaHei UI", "Microsoft YaHei", "SimSun", "Segoe UI"; font-size: 13px; color: #1f2937; }
            QStackedWidget#content, QWidget#page { background: #f6f8fb; }
            QWidget#sidebar { background: #101827; color: #e5e7eb; }
            #brandIcon { min-width: 46px; max-width: 46px; min-height: 46px; max-height: 46px; border-radius: 13px; background: #1f2937; color: #cbd5e1; font-size: 18px; }
            #brandName { color: white; font-size: 19px; font-weight: 800; }
            #brandVersion { color: #94a3b8; font-size: 13px; }
            QPushButton#navButton { text-align: left; padding: 13px 15px; border-radius: 12px; background: transparent; color: #cbd5e1; border: 0; font-size: 15px; }
            QPushButton#navButton:hover { background: #1f2937; color: white; }
            QPushButton#navButton:checked { background: #2563eb; color: white; font-weight: 700; }
            QFrame#sidebarSafety { border-top: 1px solid rgba(148, 163, 184, 0.18); }
            #safetyTitle { color: #cbd5e1; font-weight: 700; }
            #safetyBody { color: #94a3b8; font-size: 12px; line-height: 150%; }
            #title { font-size: 26px; font-weight: 800; margin-bottom: 4px; }
            #cardTitle { font-size: 17px; font-weight: 700; }
            #metric { font-size: 22px; font-weight: 800; color: #111827; }
            #metricCompact { font-size: 17px; font-weight: 800; color: #111827; }
            #largeMetric { font-size: 34px; font-weight: 900; color: #111827; }
            #muted { color: #6b7280; }
            #recentCourse { color: #0f172a; font-weight: 700; }
            #recentMeta { color: #64748b; font-size: 12px; }
            QFrame#recentRow { background: #f8fafc; border: 1px solid #e7edf5; border-radius: 12px; }
            QFrame#recentRow:hover { background: #eef4ff; border-color: #c7d8ff; }
            QFrame#recentEmpty { background: #f8fafc; border: 1px dashed #d7e0ec; border-radius: 12px; }
            QScrollArea#recentScroll, QWidget#recentContent { background: transparent; }
            QScrollArea#recentScroll QScrollBar:vertical { background: transparent; width: 8px; margin: 2px 0 2px 0; }
            QScrollArea#recentScroll QScrollBar::handle:vertical { background: #cbd5e1; border-radius: 4px; min-height: 26px; }
            QScrollArea#recentScroll QScrollBar::handle:vertical:hover { background: #94a3b8; }
            QScrollArea#recentScroll QScrollBar::add-line:vertical, QScrollArea#recentScroll QScrollBar::sub-line:vertical { height: 0; }
            QScrollArea#recentScroll QScrollBar::add-page:vertical, QScrollArea#recentScroll QScrollBar::sub-page:vertical { background: transparent; }
            QFrame#runtimeCard { background: white; border: 1px solid #e3e8f0; border-radius: 16px; }
            QFrame#runtimeTile { background: #f8fafc; border: 1px solid #e7edf5; border-radius: 12px; }
            QFrame#runtimeTile:hover { background: #eef4ff; border-color: #c7d8ff; }
            #runtimeLabel { color: #64748b; font-size: 12px; }
            #runtimeValueOk { color: #15803d; font-size: 16px; font-weight: 900; }
            #runtimeValueWarning { color: #b45309; font-size: 16px; font-weight: 900; }
            #runtimeValueError { color: #b91c1c; font-size: 16px; font-weight: 900; }
            #runtimeValueNeutral { color: #0f172a; font-size: 16px; font-weight: 900; }
            #runtimeDetail { color: #64748b; font-size: 12px; }
            #summaryLabel { color: #64748b; font-size: 13px; }
            #summaryNumber { color: #0f172a; font-size: 22px; font-weight: 800; }
            #summaryBadge { background: #ecfdf5; color: #047857; border: 1px solid #bbf7d0; border-radius: 9px; padding: 5px 9px; font-size: 15px; font-weight: 800; }
            QFrame#guideCard { background: white; border: 1px solid #e3e8f0; border-radius: 16px; }
            QFrame#guideStep { background: #f8fbff; border: 1px solid #e4edf8; border-radius: 12px; }
            #guideStepTitle { color: #0f172a; font-weight: 800; font-size: 13px; }
            #guideStepBody { color: #64748b; font-size: 12px; }
            QFrame#wizardRail { background: #111827; }
            #wizardRailTitle { color: white; font-size: 20px; font-weight: 900; }
            #wizardRailBody { color: #94a3b8; line-height: 150%; }
            #wizardStepActive { color: white; background: #2563eb; border-radius: 10px; padding: 10px 12px; font-weight: 800; }
            #wizardStepDone { color: #dbeafe; background: rgba(37, 99, 235, 0.28); border-radius: 10px; padding: 10px 12px; font-weight: 700; }
            #wizardStepPending { color: #94a3b8; background: transparent; border-radius: 10px; padding: 10px 12px; }
            #wizardProgress { color: #2563eb; font-weight: 800; }
            #wizardTitle { color: #0f172a; font-size: 24px; font-weight: 900; }
            #wizardBody { color: #475569; line-height: 155%; }
            QFrame#wizardItem { background: #f8fafc; border: 1px solid #edf2f7; border-radius: 10px; }
            #scoreBadge { background: #eaf2ff; color: #1d4ed8; border-radius: 9px; padding: 7px 10px; font-weight: 800; }
            #detailTitle { color: #0f172a; font-size: 22px; font-weight: 900; }
            #detailLabel { color: #64748b; font-size: 12px; }
            #detailValue { color: #0f172a; font-size: 14px; font-weight: 700; }
            QFrame#detailRawRow { background: #f8fafc; border: 1px solid #edf2f7; border-radius: 10px; }
            QScrollArea#gradeDetailScroll, QWidget#gradeDetailContent { background: transparent; }
            #aboutBody { color: #334155; line-height: 155%; }
            QScrollArea#wizardPageScroll, QWidget#wizardPageContent,
            QScrollArea#aboutScroll, QWidget#aboutContent { background: transparent; }
            QScrollArea#helpScroll, QWidget#helpContent { background: transparent; }
            QFrame#helpSection { background: white; border: 1px solid #e3e8f0; border-radius: 16px; }
            #helpSectionTitle { color: #0f172a; font-size: 18px; font-weight: 800; }
            #helpBody { color: #475569; }
            QFrame#helpItem { background: #f8fafc; border: 1px solid #edf2f7; border-radius: 10px; }
            #helpBullet { background: #2563eb; border-radius: 4px; }
            #helpItemText { color: #334155; }
            QScrollArea#notificationScroll, QWidget#notificationContent { background: transparent; }
            QFrame#notificationCard {
                background: #ffffff;
                border: 1px solid #e3e8f0;
                border-radius: 14px;
            }
            QFrame#notificationCard QLabel { color: #334155; }
            QFrame#notificationCard QLabel#muted { color: #64748b; }
            QFrame#notificationCard QCheckBox { color: #0f172a; font-weight: 700; spacing: 9px; }
            QFrame#notificationCard QLineEdit,
            QFrame#notificationCard QComboBox,
            QFrame#notificationCard QSpinBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #dbe3ef;
                border-radius: 9px;
                min-height: 24px;
                padding: 7px 10px;
            }
            QFrame#notificationCard QLineEdit:focus,
            QFrame#notificationCard QComboBox:focus,
            QFrame#notificationCard QSpinBox:focus {
                border: 1px solid #2563eb;
            }
            QPushButton#notificationGuideButton {
                min-width: 54px;
                padding: 6px 12px;
                border-radius: 8px;
                background: #eef4ff;
                color: #1d4ed8;
                font-weight: 800;
                border: 1px solid #dbe8ff;
            }
            QPushButton#notificationGuideButton:hover { background: #dbeafe; }
            QFrame#notificationGuideStep {
                background: #f8fafc;
                border: 1px solid #e3e8f0;
                border-radius: 14px;
            }
            QFrame#notificationCheckCard {
                background: #f8fafc;
                border: 1px solid #e3e8f0;
                border-radius: 14px;
            }
            #notificationCheckTitle { color: #0f172a; font-size: 15px; font-weight: 900; }
            QFrame#notificationCheckRow {
                background: #ffffff;
                border: 1px solid #edf2f7;
                border-radius: 10px;
            }
            QFrame#notificationTestRow {
                background: #f8fafc;
                border: 1px solid #e3e8f0;
                border-radius: 10px;
            }
            QFrame#cleanupGuide {
                background: #f8fafc;
                border: 1px solid #e3e8f0;
                border-radius: 14px;
            }
            QFrame#cleanupGuideItem {
                background: #ffffff;
                border: 1px solid #edf2f7;
                border-radius: 10px;
            }
            #cleanupGuideTitle { color: #0f172a; font-size: 14px; font-weight: 900; }
            QLabel#cleanupStatus[level="warning"] {
                background: #fffbeb;
                color: #92400e;
                border: 1px solid #fde68a;
                border-radius: 10px;
                padding: 10px 12px;
                font-weight: 800;
            }
            QLabel#cleanupStatus[level="ok"] {
                background: #ecfdf5;
                color: #047857;
                border: 1px solid #bbf7d0;
                border-radius: 10px;
                padding: 10px 12px;
                font-weight: 800;
            }
            #notificationCheckLabel { color: #0f172a; font-weight: 800; min-width: 118px; }
            #notificationCheckDetail { color: #64748b; font-size: 12px; }
            #notificationCheckSummary_ok { color: #047857; font-weight: 900; min-width: 78px; }
            #notificationCheckSummary_warning { color: #b45309; font-weight: 900; min-width: 96px; }
            #notificationCheckSummary_disabled { color: #64748b; font-weight: 800; min-width: 78px; }
            #notificationDot_ok { background: #22c55e; border-radius: 4px; }
            #notificationDot_warning { background: #f59e0b; border-radius: 4px; }
            #notificationDot_disabled { background: #cbd5e1; border-radius: 4px; }
            #guideStepIndex { color: #2563eb; font-size: 13px; font-weight: 800; }
            #guideStepTitle { color: #0f172a; font-size: 20px; font-weight: 900; }
            #guideStepBody { color: #334155; line-height: 155%; }
            QFrame#card { background: white; border: 1px solid #e3e8f0; border-radius: 16px; }
            QFrame#statusPanel { background: #111827; border-radius: 18px; }
            #statusEyebrow { color: #93c5fd; font-size: 13px; }
            #statusTitle { color: white; font-size: 30px; font-weight: 900; }
            #statusBody { color: #cbd5e1; }
            QFrame#nextBox { background: #1f2937; border: 1px solid rgba(255, 255, 255, 0.10); border-radius: 14px; }
            #nextLabel { color: #94a3b8; font-size: 12px; }
            #nextValue { color: white; font-size: 24px; font-weight: 900; }
            QFrame#metricTile { background: transparent; }
            QFrame#chart { background: #ffffff; border: 0; }
            QPushButton { padding: 9px 14px; border-radius: 9px; background: #2563eb; color: white; border: 0; }
            QPushButton:hover { background: #1d4ed8; }
            QPushButton#primaryButton { background: #2563eb; color: white; font-weight: 700; }
            QPushButton#secondaryButton { background: #eef4ff; color: #1d4ed8; }
            QPushButton#secondaryButton:hover { background: #dbeafe; }
            QMenu {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #dbe3ef;
                border-radius: 10px;
                padding: 6px;
            }
            QMenu::item {
                padding: 7px 28px 7px 24px;
                border-radius: 7px;
                background: transparent;
            }
            QMenu::item:selected { background: #eaf2ff; color: #1d4ed8; }
            QMenu::item:disabled { color: #94a3b8; }
            QMenu::separator { height: 1px; background: #e5e7eb; margin: 5px 8px; }
            QToolTip {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #dbe3ef;
                border-radius: 8px;
                padding: 6px 8px;
            }
            QMessageBox, QDialog { background: #ffffff; color: #111827; }
            QMessageBox QLabel, QDialog QLabel { color: #111827; }
            QMessageBox QLabel#muted, QDialog QLabel#muted { color: #64748b; }
            QMessageBox QPushButton, QDialogButtonBox QPushButton { min-width: 78px; padding: 9px 16px; border-radius: 9px; background: #2563eb; color: white; }
            QMessageBox QPushButton:hover, QDialogButtonBox QPushButton:hover { background: #1d4ed8; }
            QLineEdit, QComboBox, QSpinBox { background: white; border: 1px solid #dbe3ef; border-radius: 9px; padding: 8px 10px; }
            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #0f172a;
                selection-background-color: #eaf2ff;
                selection-color: #1d4ed8;
                border: 1px solid #dbe3ef;
                border-radius: 8px;
                padding: 4px;
                outline: 0;
            }
            QCheckBox { color: #334155; spacing: 8px; }
            QTableWidget { background: white; border: 1px solid #e3e8f0; border-radius: 12px; gridline-color: #eef2f7; }
            QTableWidget::item { padding: 7px 8px; }
            QTableWidget::item:alternate { background: #fbfdff; }
            QTableWidget::item:selected { background: #dbeafe; color: #111827; }
            QHeaderView::section { background: #f8fafc; padding: 9px 10px; border: 0; border-bottom: 1px solid #e5e7eb; color: #64748b; font-weight: 600; }
            """
        )


def _page() -> QWidget:
    page = QWidget()
    page.setObjectName("page")
    layout = QVBoxLayout(page)
    layout.setContentsMargins(24, 22, 24, 22)
    layout.setSpacing(14)
    return page


def _card() -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    card.setFrameShape(QFrame.StyledPanel)
    return card


def app_icon_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "gdut_grade_monitor" / "assets" / "icon.ico"
    return Path(__file__).resolve().parent / "assets" / "icon.ico"


def _dialog_stylesheet() -> str:
    return """
        QWidget { font-family: "Microsoft YaHei UI", "Microsoft YaHei", "SimSun", "Segoe UI"; }
        QMessageBox, QDialog { background: #ffffff; color: #111827; }
        QMessageBox QLabel, QDialog QLabel { color: #111827; }
        QMessageBox QPushButton, QDialogButtonBox QPushButton {
            min-width: 78px; padding: 9px 16px; border-radius: 9px;
            background: #2563eb; color: white;
        }
        QMessageBox QPushButton:hover, QDialogButtonBox QPushButton:hover { background: #1d4ed8; }
        QMenu {
            background: #ffffff;
            color: #0f172a;
            border: 1px solid #dbe3ef;
            border-radius: 10px;
            padding: 6px;
        }
        QMenu::item {
            padding: 7px 28px 7px 24px;
            border-radius: 7px;
            background: transparent;
        }
        QMenu::item:selected { background: #eaf2ff; color: #1d4ed8; }
        QMenu::item:disabled { color: #94a3b8; }
        QMenu::separator { height: 1px; background: #e5e7eb; margin: 5px 8px; }
        QToolTip {
            background: #ffffff;
            color: #0f172a;
            border: 1px solid #dbe3ef;
            border-radius: 8px;
            padding: 6px 8px;
        }
        QComboBox QAbstractItemView {
            background: #ffffff;
            color: #0f172a;
            selection-background-color: #eaf2ff;
            selection-color: #1d4ed8;
            border: 1px solid #dbe3ef;
            border-radius: 8px;
            padding: 4px;
            outline: 0;
        }
        QScrollArea#notificationScroll, QWidget#notificationContent { background: transparent; }
        QFrame#notificationCard {
            background: #ffffff;
            border: 1px solid #e3e8f0;
            border-radius: 14px;
        }
        QFrame#notificationCard QLabel { color: #334155; }
        QFrame#notificationCard QLabel#muted { color: #64748b; }
        QFrame#notificationCard QCheckBox { color: #0f172a; font-weight: 700; spacing: 9px; }
        QFrame#notificationCard QLineEdit,
        QFrame#notificationCard QComboBox,
        QFrame#notificationCard QSpinBox {
            background: #ffffff;
            color: #0f172a;
            border: 1px solid #dbe3ef;
            border-radius: 9px;
            min-height: 24px;
            padding: 7px 10px;
        }
        QFrame#notificationCard QLineEdit:focus,
        QFrame#notificationCard QComboBox:focus,
        QFrame#notificationCard QSpinBox:focus {
            border: 1px solid #2563eb;
        }
        QPushButton#primaryButton {
            min-width: 90px; padding: 9px 18px; border-radius: 9px;
            background: #2563eb; color: white; border: 0; font-weight: 800;
        }
        QPushButton#secondaryButton {
            min-width: 78px; padding: 9px 16px; border-radius: 9px;
            background: #eef4ff; color: #1d4ed8; border: 0; font-weight: 700;
        }
        QPushButton#notificationGuideButton {
            min-width: 54px; padding: 6px 12px; border-radius: 8px;
            background: #eef4ff; color: #1d4ed8; font-weight: 800;
            border: 1px solid #dbe8ff;
        }
        QPushButton#notificationGuideButton:hover, QPushButton#secondaryButton:hover { background: #dbeafe; }
        QFrame#notificationGuideStep {
            background: #f8fafc; border: 1px solid #e3e8f0; border-radius: 14px;
        }
        QFrame#notificationCheckCard {
            background: #f8fafc; border: 1px solid #e3e8f0; border-radius: 14px;
        }
        #notificationCheckTitle { color: #0f172a; font-size: 15px; font-weight: 900; }
        QFrame#notificationCheckRow {
            background: #ffffff; border: 1px solid #edf2f7; border-radius: 10px;
        }
        QFrame#notificationTestRow {
            background: #f8fafc; border: 1px solid #e3e8f0; border-radius: 10px;
        }
        #notificationCheckLabel { color: #0f172a; font-weight: 800; min-width: 118px; }
        #notificationCheckDetail { color: #64748b; font-size: 12px; }
        #notificationCheckSummary_ok { color: #047857; font-weight: 900; min-width: 78px; }
        #notificationCheckSummary_warning { color: #b45309; font-weight: 900; min-width: 96px; }
        #notificationCheckSummary_disabled { color: #64748b; font-weight: 800; min-width: 78px; }
        #notificationDot_ok { background: #22c55e; border-radius: 4px; }
        #notificationDot_warning { background: #f59e0b; border-radius: 4px; }
        #notificationDot_disabled { background: #cbd5e1; border-radius: 4px; }
        #guideStepIndex { color: #2563eb; font-size: 13px; font-weight: 800; }
        #guideStepTitle { color: #0f172a; font-size: 20px; font-weight: 900; }
        #guideStepBody { color: #334155; line-height: 155%; }
    """


def _acquire_single_instance_lock(paths: AppPaths) -> QLockFile | None:
    paths.ensure()
    lock = QLockFile(str(paths.root / "gdut-grade-monitor.lock"))
    lock.setStaleLockTime(30_000)
    if lock.tryLock(100):
        return lock
    return None


def _raise_existing_window() -> None:
    if sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        target_prefix = f"GDUT 成绩提醒 v{APP_VERSION}"
        found_hwnd = ctypes.c_void_p()

        enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def enum_proc(hwnd, _lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            if buffer.value.startswith(target_prefix):
                found_hwnd.value = hwnd
                return False
            return True

        user32.EnumWindows(enum_proc_type(enum_proc), 0)
        if found_hwnd.value:
            user32.ShowWindow(found_hwnd.value, 9)
            user32.SetForegroundWindow(found_hwnd.value)
    except Exception:
        return


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("GDUT 成绩提醒")
    app.setApplicationDisplayName("GDUT 成绩提醒")
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_AUTHOR)
    app.setStyleSheet(_dialog_stylesheet())

    single_instance_lock = _acquire_single_instance_lock(AppPaths())
    if single_instance_lock is None:
        _raise_existing_window()
        return

    window = GradeMonitorQtApp()
    window.show()
    sys.exit(app.exec())
