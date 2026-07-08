from __future__ import annotations

import os
import sys
import threading
import ctypes
from datetime import date
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
from .diagnostics import create_diagnostics_zip
from .doctor import overall_ok, run_checks
from .errors import user_friendly_error_message
from .gui_model import about_text, doctor_table_rows, filter_grades, first_run_wizard_pages, grade_analytics, grade_table_rows
from .gui_model import help_sections, history_table_rows
from .gui_model import onboarding_steps, recent_change_rows, semester_options
from .gui_model import setup_guidance, status_summary
from .monitor import GradeMonitor
from .notify import WindowsNotifier
from .official_transcript import OFFICIAL_TRANSCRIPT_PORTAL_URL, official_transcript_guidance
from .setup_flow import FirstRunSetupResult, run_first_run_setup
from .storage import AppPaths, load_config, load_state, save_config, set_poll_interval
from .task import autostart_exists, install_task_or_startup, uninstall_task_and_startup
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
        widget = QWidget()
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
        return widget

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
        heading = QVBoxLayout()
        heading.addWidget(title)
        heading.addWidget(self.status_label)
        top.addLayout(heading, 1)
        check = QPushButton("立即检查")
        check.setObjectName("primaryButton")
        check.clicked.connect(self.check_now)
        top.addWidget(check)
        page.layout().addLayout(top)

        self.status_panel = QFrame()
        self.status_panel.setObjectName("statusPanel")
        status_layout = QHBoxLayout(self.status_panel)
        status_layout.setContentsMargins(24, 22, 24, 22)
        main_status = QVBoxLayout()
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
        next_layout = QVBoxLayout(next_box)
        next_label = QLabel("下一次检查")
        next_label.setObjectName("nextLabel")
        self.next_check_label = QLabel("按设置频率")
        self.next_check_label.setObjectName("nextValue")
        next_layout.addWidget(next_label)
        next_layout.addWidget(self.next_check_label)
        status_layout.addWidget(next_box)
        page.layout().addWidget(self.status_panel)
        page.layout().addWidget(self._onboarding_card())

        middle = QHBoxLayout()
        self.recent_card = _card()
        recent_layout = QVBoxLayout(self.recent_card)
        recent_layout.setContentsMargins(18, 18, 18, 18)
        recent_layout.setSpacing(12)
        recent_title = QLabel("最近变化")
        recent_title.setObjectName("cardTitle")
        recent_layout.addWidget(recent_title)
        self.recent_list = QVBoxLayout()
        self.recent_list.setSpacing(8)
        recent_layout.addLayout(self.recent_list)
        recent_layout.addStretch(1)
        middle.addWidget(self.recent_card, 6)

        self.config_card = _card()
        config_layout = QVBoxLayout(self.config_card)
        config_title = QLabel("本机配置")
        config_title.setObjectName("cardTitle")
        config_layout.addWidget(config_title)
        self.summary_grid = QGridLayout()
        self.summary_grid.setHorizontalSpacing(18)
        self.summary_grid.setVerticalSpacing(12)
        config_layout.addLayout(self.summary_grid)
        middle.addWidget(self.config_card, 5)
        page.layout().addLayout(middle)

        actions_card = _card()
        actions = QHBoxLayout(actions_card)
        for label, callback, secondary in [
            ("一键配置本机", self.one_click_setup, False),
            ("新手向导", self.open_first_run_wizard, True),
            ("导出诊断包", self.export_diagnostics, True),
            ("安装自启动", self.install_startup, True),
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
            name = QLabel(label)
            name.setObjectName("muted")
            value_label.setObjectName("largeMetric")
            layout.addWidget(name)
            layout.addWidget(value_label)
            metrics.addWidget(card)

        charts = QHBoxLayout()
        trend_card = _card()
        trend_layout = QVBoxLayout(trend_card)
        trend_title = QLabel("平均绩点变化")
        trend_title.setObjectName("cardTitle")
        self.trend_chart = TrendChart()
        trend_layout.addWidget(trend_title)
        trend_layout.addWidget(self.trend_chart)
        charts.addWidget(trend_card, 6)

        distribution_card = _card()
        distribution_layout = QVBoxLayout(distribution_card)
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
        self.history_table = QTableWidget(0, 5)
        self.history_table.setHorizontalHeaderLabels(["时间", "类型", "学期", "课程", "成绩"])
        self._prepare_table(self.history_table)
        self.history_table.setColumnWidth(0, 170)
        self.history_table.setColumnWidth(1, 90)
        self.history_table.setColumnWidth(2, 100)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
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
        page.layout().addWidget(title)
        page.layout().addWidget(intro)
        page.layout().addWidget(form_card)
        actions_card = _card()
        row = QHBoxLayout(actions_card)
        row.setContentsMargins(14, 12, 14, 12)
        for button in [save, login, install, uninstall, open_dir, update]:
            row.addWidget(button)
        row.addStretch(1)
        page.layout().addWidget(actions_card)
        page.layout().addStretch(1)
        return page

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
        card_layout.addWidget(body)
        update = QPushButton("检查更新")
        update.setObjectName("secondaryButton")
        update.clicked.connect(self.check_for_updates)
        card_layout.addWidget(update, 0, Qt.AlignLeft)
        page.layout().addWidget(title)
        page.layout().addWidget(card)
        page.layout().addStretch(1)
        return page

    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = None
            return
        self.tray = QSystemTrayIcon(QIcon(str(app_icon_path())), self)
        menu = QMenu()
        show_action = QAction("打开主界面", self)
        show_action.triggered.connect(self.showNormal)
        check_action = QAction("立即检查", self)
        check_action.triggered.connect(self.check_now)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(show_action)
        menu.addAction(check_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.show()

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
        self._set_recent_changes(recent_change_rows(state))
        self._set_summary_cards(state, config, installed)

    def _set_recent_changes(self, recent: list[tuple[str, str, str]]) -> None:
        while self.recent_list.count():
            item = self.recent_list.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        if not recent:
            empty = QFrame()
            empty.setObjectName("recentEmpty")
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

        for course, score, semester in recent:
            row = QFrame()
            row.setObjectName("recentRow")
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

    def _set_summary_cards(self, state: dict, config: dict, installed: bool) -> None:
        while self.summary_grid.count():
            item = self.summary_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        grades = state.get("grades", {})
        monitor = state.get("monitor", {})
        values = [
            ("成绩数量", str(len(grades) if isinstance(grades, dict) else 0), "metric"),
            ("查询频率", f"{config.get('poll_interval_minutes', 30)} 分钟", "metric"),
            ("最近检查", str(monitor.get("last_check_at", "尚未检查")).replace("T", "\n"), "metricCompact"),
            ("安全边界", "严格只读", "metricCompact"),
        ]
        for index, (label, value, style_name) in enumerate(values):
            card = QFrame()
            card.setObjectName("metricTile")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(4)
            name = QLabel(label)
            name.setObjectName("muted")
            number = QLabel(value)
            number.setObjectName(style_name)
            number.setWordWrap(True)
            layout.addWidget(name)
            layout.addWidget(number)
            self.summary_grid.addWidget(card, index // 2, index % 2)

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
        self._fill_table(self.grades_table, grade_table_rows(filtered))

    def refresh_history(self) -> None:
        self._fill_table(self.history_table, history_table_rows(load_state(self.paths)))

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
        self._run_background(
            lambda: self._one_click_setup_worker(dialog.options()),
            self._one_click_setup_complete,
        )

    def _one_click_setup_worker(self, options: dict) -> tuple[list[dict], FirstRunSetupResult]:
        result = run_first_run_setup(paths=self.paths, **options)
        return list(load_state(self.paths).get("grades", {}).values()), result

    def _one_click_setup_complete(self, payload: tuple[list[dict], FirstRunSetupResult]) -> None:
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

    def check_now(self) -> None:
        self._run_background(self._check_now_worker, self._check_complete)

    def _check_now_worker(self) -> tuple[list[dict], list[dict]]:
        config = load_config(self.paths)
        student_id = config.get("student_id", "")
        password = CredentialStore().get_password(student_id) if student_id else None
        session = AuthManager(self.paths).get_session(auto_login=True, student_id=student_id, password=password)
        fetcher = GradeApiClient(session)
        monitor = GradeMonitor(self.paths, fetcher=fetcher, notifier=WindowsNotifier())
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
        self._run_background(lambda: self._one_click_setup_worker(options), self._one_click_setup_complete)

    def save_interval(self) -> None:
        config = set_poll_interval(self.paths, self.interval.value())
        self.interval.setValue(int(config["poll_interval_minutes"]))
        self.refresh_status()
        QMessageBox.information(self, "设置", f"查询频率已设置为每 {config['poll_interval_minutes']} 分钟。")

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

    def _run_background(self, target: Callable[[], object], on_success: Callable[[object], None]) -> None:
        signals = _Signals()
        self._signals.append(signals)

        def cleanup() -> None:
            if signals in self._signals:
                self._signals.remove(signals)

        signals.success.connect(lambda result: (cleanup(), on_success(result)))
        signals.error.connect(lambda message: (cleanup(), QMessageBox.critical(self, "GDUT 成绩提醒", message)))

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
            #aboutBody { color: #334155; line-height: 155%; }
            QScrollArea#helpScroll, QWidget#helpContent { background: transparent; }
            QFrame#helpSection { background: white; border: 1px solid #e3e8f0; border-radius: 16px; }
            #helpSectionTitle { color: #0f172a; font-size: 18px; font-weight: 800; }
            #helpBody { color: #475569; }
            QFrame#helpItem { background: #f8fafc; border: 1px solid #edf2f7; border-radius: 10px; }
            #helpBullet { background: #2563eb; border-radius: 4px; }
            #helpItemText { color: #334155; }
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
            QMessageBox, QDialog { background: #ffffff; color: #111827; }
            QMessageBox QLabel, QDialog QLabel { color: #111827; }
            QMessageBox QLabel#muted, QDialog QLabel#muted { color: #64748b; }
            QMessageBox QPushButton, QDialogButtonBox QPushButton { min-width: 78px; padding: 9px 16px; border-radius: 9px; background: #2563eb; color: white; }
            QMessageBox QPushButton:hover, QDialogButtonBox QPushButton:hover { background: #1d4ed8; }
            QLineEdit, QComboBox, QSpinBox { background: white; border: 1px solid #dbe3ef; border-radius: 9px; padding: 8px 10px; }
            QCheckBox { color: #334155; spacing: 8px; }
            QTableWidget { background: white; border: 1px solid #e3e8f0; border-radius: 12px; gridline-color: #eef2f7; }
            QTableWidget::item:alternate { background: #fbfdff; }
            QTableWidget::item:selected { background: #dbeafe; color: #111827; }
            QHeaderView::section { background: #f8fafc; padding: 8px; border: 0; border-bottom: 1px solid #e5e7eb; color: #64748b; font-weight: 600; }
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
