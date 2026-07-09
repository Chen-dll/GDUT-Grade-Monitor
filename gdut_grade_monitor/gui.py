from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .auth import AuthManager, BrowserFillMismatchError, PlaywrightBrowserMissingError
from .client import GradeApiClient, GradeResponseError
from .constants import APP_VERSION
from .credentials import CredentialStore, PasswordInputError
from .diagnostics import create_diagnostics_zip
from .doctor import overall_ok, run_checks
from .gui_model import about_text, doctor_table_rows, grade_table_rows, history_table_rows, next_check_summary, setup_guidance
from .gui_model import status_summary
from .monitor import GradeMonitor
from .notification_channels import build_notifier
from .setup_flow import FirstRunSetupResult, run_first_run_setup
from .storage import AppPaths, load_config, load_state, set_poll_interval
from .task import autostart_exists, install_task_or_startup, uninstall_task_and_startup


class FirstRunSetupDialog(simpledialog.Dialog):
    def __init__(self, parent: tk.Tk, initial_interval: int):
        self.initial_interval = initial_interval
        self.student_id_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.interval_var = tk.IntVar(value=initial_interval)
        self.autostart_var = tk.BooleanVar(value=True)
        self.result = None
        super().__init__(parent, "一键配置本机")

    def body(self, master):
        ttk.Label(master, text="学号").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        student_entry = ttk.Entry(master, textvariable=self.student_id_var, width=30)
        student_entry.grid(row=0, column=1, sticky=tk.EW, pady=4)

        ttk.Label(master, text="密码").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(master, textvariable=self.password_var, show="*", width=30).grid(row=1, column=1, sticky=tk.EW, pady=4)

        ttk.Label(master, text="检查频率").grid(row=2, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        interval_row = ttk.Frame(master)
        interval_row.grid(row=2, column=1, sticky=tk.W, pady=4)
        ttk.Spinbox(interval_row, from_=1, to=1440, textvariable=self.interval_var, width=8).pack(side=tk.LEFT)
        ttk.Label(interval_row, text="分钟").pack(side=tk.LEFT, padx=(6, 0))

        ttk.Checkbutton(master, text="配置完成后开启登录自启动", variable=self.autostart_var).grid(
            row=3,
            column=1,
            sticky=tk.W,
            pady=(6, 2),
        )
        ttk.Label(
            master,
            text="密码只保存到 Windows 凭据管理器；如果浏览器要求验证码，请在弹出的浏览器里完成登录。",
            wraplength=360,
        ).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=(8, 0))
        master.columnconfigure(1, weight=1)
        return student_entry

    def validate(self) -> bool:
        student_id = self.student_id_var.get().strip()
        password = self.password_var.get()
        if not student_id:
            messagebox.showwarning("一键配置本机", "请填写学号。", parent=self)
            return False
        if not password:
            messagebox.showwarning("一键配置本机", "请填写密码。", parent=self)
            return False
        try:
            interval = int(self.interval_var.get())
        except (TypeError, ValueError):
            messagebox.showwarning("一键配置本机", "检查频率需要是 1 到 1440 之间的分钟数。", parent=self)
            return False
        if interval < 1 or interval > 1440:
            messagebox.showwarning("一键配置本机", "检查频率需要是 1 到 1440 之间的分钟数。", parent=self)
            return False
        return True

    def apply(self) -> None:
        self.result = {
            "student_id": self.student_id_var.get().strip(),
            "password": self.password_var.get(),
            "interval_minutes": int(self.interval_var.get()),
            "install_autostart": bool(self.autostart_var.get()),
        }


class GradeMonitorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.paths = AppPaths()
        self.paths.ensure()
        self.root.title("GDUT 成绩提醒")
        self._set_window_icon()
        self.root.geometry("900x560")
        self.root.minsize(760, 460)

        self.status_var = tk.StringVar(value="正在加载...")
        self.message_var = tk.StringVar(value="准备就绪")
        self.guidance_title_var = tk.StringVar(value="正在检查状态...")
        self.guidance_body_var = tk.StringVar(value="")
        self.guidance_action_var = tk.StringVar(value="一键配置本机")
        self.interval_var = tk.IntVar(value=int(load_config(self.paths).get("poll_interval_minutes", 30)))
        self._last_guidance_action = "一键配置本机"

        self._build_ui()
        self.refresh_status()
        self.load_cached_grades()

    def _set_window_icon(self) -> None:
        icon = app_icon_path()
        if not icon.exists():
            return
        try:
            self.root.iconbitmap(default=str(icon))
        except tk.TclError:
            return

    def _build_ui(self) -> None:
        self._build_menu()
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(main)
        header.pack(fill=tk.X)
        ttk.Label(header, text=f"GDUT 成绩提醒 v{APP_VERSION}", font=("Microsoft YaHei UI", 16, "bold")).pack(
            side=tk.LEFT
        )
        ttk.Label(header, textvariable=self.status_var).pack(side=tk.RIGHT)

        guide = ttk.LabelFrame(main, text="当前状态", padding=10)
        guide.pack(fill=tk.X, pady=(10, 4))
        guide_text = ttk.Frame(guide)
        guide_text.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(guide_text, textvariable=self.guidance_title_var, font=("Microsoft YaHei UI", 11, "bold")).pack(
            anchor=tk.W
        )
        ttk.Label(guide_text, textvariable=self.guidance_body_var, wraplength=650).pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(guide, textvariable=self.guidance_action_var, command=self.run_guidance_action).pack(
            side=tk.RIGHT,
            padx=(12, 0),
        )

        toolbar = ttk.Frame(main)
        toolbar.pack(fill=tk.X, pady=(12, 8))
        ttk.Button(toolbar, text="一键配置本机", command=self.one_click_setup).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="立即检查", command=self.check_now).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="登录/初始化", command=self.setup_login).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="安装/修复自启动", command=self.install_startup).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="取消自启动", command=self.uninstall_startup).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="打开数据目录", command=self.open_data_dir).pack(side=tk.LEFT)
        ttk.Label(toolbar, text="频率(分钟):").pack(side=tk.LEFT, padx=(18, 4))
        ttk.Spinbox(toolbar, from_=1, to=1440, textvariable=self.interval_var, width=6).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="保存频率", command=self.save_interval).pack(side=tk.LEFT, padx=(6, 0))

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        grades_frame = ttk.Frame(self.notebook)
        history_frame = ttk.Frame(self.notebook)
        doctor_frame = ttk.Frame(self.notebook)
        self.notebook.add(grades_frame, text="成绩")
        self.notebook.add(history_frame, text="提醒历史")
        self.notebook.add(doctor_frame, text="环境检查")

        columns = ("semester", "course", "score", "credit", "point")
        self.tree = ttk.Treeview(grades_frame, columns=columns, show="headings", height=16)
        headings = {
            "semester": ("学期", 110),
            "course": ("课程", 360),
            "score": ("成绩", 100),
            "credit": ("学分", 80),
            "point": ("绩点", 80),
        }
        for column, (label, width) in headings.items():
            self.tree.heading(column, text=label)
            self.tree.column(column, width=width, anchor=tk.W)

        scrollbar = ttk.Scrollbar(grades_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        history_columns = ("at", "kind", "semester", "course", "score")
        self.history_tree = ttk.Treeview(history_frame, columns=history_columns, show="headings", height=16)
        history_headings = {
            "at": ("时间", 170),
            "kind": ("类型", 90),
            "semester": ("学期", 110),
            "course": ("课程", 360),
            "score": ("成绩", 100),
        }
        for column, (label, width) in history_headings.items():
            self.history_tree.heading(column, text=label)
            self.history_tree.column(column, width=width, anchor=tk.W)
        history_scrollbar = ttk.Scrollbar(history_frame, orient=tk.VERTICAL, command=self.history_tree.yview)
        self.history_tree.configure(yscrollcommand=history_scrollbar.set)
        self.history_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        doctor_toolbar = ttk.Frame(doctor_frame, padding=(0, 0, 0, 8))
        doctor_toolbar.pack(fill=tk.X)
        ttk.Button(doctor_toolbar, text="重新检查环境", command=self.refresh_doctor).pack(side=tk.LEFT)
        ttk.Button(doctor_toolbar, text="导出诊断包", command=self.export_diagnostics).pack(side=tk.LEFT, padx=(8, 0))
        doctor_columns = ("status", "item", "detail", "action")
        self.doctor_tree = ttk.Treeview(doctor_frame, columns=doctor_columns, show="headings", height=16)
        doctor_headings = {
            "status": ("状态", 90),
            "item": ("检查项", 150),
            "detail": ("结果", 280),
            "action": ("建议", 330),
        }
        for column, (label, width) in doctor_headings.items():
            self.doctor_tree.heading(column, text=label)
            self.doctor_tree.column(column, width=width, anchor=tk.W)
        doctor_scrollbar = ttk.Scrollbar(doctor_frame, orient=tk.VERTICAL, command=self.doctor_tree.yview)
        self.doctor_tree.configure(yscrollcommand=doctor_scrollbar.set)
        self.doctor_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        doctor_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        bottom = ttk.Frame(self.root, padding=(12, 0, 12, 10))
        bottom.pack(fill=tk.X)
        ttk.Label(bottom, textvariable=self.message_var).pack(side=tk.LEFT)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="导出诊断包...", command=self.export_diagnostics)
        file_menu.add_separator()
        file_menu.add_command(label="打开数据目录", command=self.open_data_dir)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.destroy)
        menubar.add_cascade(label="文件", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="关于 GDUT 成绩提醒", command=self.show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)
        self.root.config(menu=menubar)

    def refresh_status(self) -> None:
        config = load_config(self.paths)
        state = load_state(self.paths)
        installed = autostart_exists()
        self.status_var.set(status_summary(installed, state))
        self.message_var.set(next_check_summary(state))
        results = run_checks(self.paths)
        guidance = setup_guidance(
            startup_installed=installed,
            config=config,
            state=state,
            required_checks_ok=overall_ok(results),
        )
        self.guidance_title_var.set(guidance["title"])
        self.guidance_body_var.set(guidance["body"])
        self.guidance_action_var.set(guidance["primary_action"])
        self._last_guidance_action = guidance["primary_action"]

    def load_cached_grades(self) -> None:
        state = load_state(self.paths)
        snapshot = state.get("grades", {})
        self.set_grades(list(snapshot.values()))
        self.set_history(state)
        self.refresh_doctor()

    def set_grades(self, grades: list[dict]) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in grade_table_rows(grades):
            self.tree.insert("", tk.END, values=row)

    def set_history(self, state: dict) -> None:
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        for row in history_table_rows(state):
            self.history_tree.insert("", tk.END, values=row)

    def refresh_doctor(self) -> None:
        for item in self.doctor_tree.get_children():
            self.doctor_tree.delete(item)
        for row in doctor_table_rows(run_checks(self.paths)):
            self.doctor_tree.insert("", tk.END, values=row)

    def run_guidance_action(self) -> None:
        action = self._last_guidance_action
        if action == "查看环境检查":
            self.notebook.select(2)
            self.refresh_doctor()
        elif action == "立即检查":
            self.check_now()
        elif action in ("安装自启动", "安装/修复自启动"):
            self.install_startup()
        else:
            self.one_click_setup()

    def one_click_setup(self) -> None:
        dialog = FirstRunSetupDialog(self.root, self.interval_var.get())
        if not dialog.result:
            return
        self.interval_var.set(dialog.result["interval_minutes"])
        self.message_var.set("正在一键配置：保存凭据、登录、建立基线并配置后台提醒...")
        self._run_background(lambda: self._one_click_setup_worker(dialog.result))

    def _one_click_setup_worker(self, options: dict) -> None:
        result = run_first_run_setup(paths=self.paths, **options)
        grades = list(load_state(self.paths).get("grades", {}).values())
        self.root.after(0, lambda: self._one_click_setup_complete(grades, result))

    def _one_click_setup_complete(self, grades: list[dict], result: FirstRunSetupResult) -> None:
        self.set_grades(grades)
        self.refresh_status()
        self.refresh_doctor()
        self.set_history(load_state(self.paths))
        if result.startup_mode == "failed":
            self.message_var.set("配置完成，但自启动安装失败；可稍后手动点击安装/修复自启动。")
            messagebox.showwarning("一键配置本机", "成绩基线已建立，但自启动安装失败。请在主界面手动重试。")
            return
        startup_text = "已开启自启动" if result.startup_mode != "skipped" else "未开启自启动"
        self.message_var.set(f"一键配置完成：已建立 {result.grade_count} 条成绩基线，{startup_text}。")
        messagebox.showinfo("一键配置本机", f"配置完成。已建立 {result.grade_count} 条成绩基线，{startup_text}。")

    def check_now(self) -> None:
        self.message_var.set("正在检查成绩...")
        self._run_background(self._check_now_worker)

    def _check_now_worker(self) -> None:
        config = load_config(self.paths)
        student_id = config.get("student_id", "")
        password = CredentialStore().get_password(student_id) if student_id else None
        session = AuthManager(self.paths).get_session(auto_login=True, student_id=student_id, password=password)
        fetcher = GradeApiClient(session)
        monitor = GradeMonitor(self.paths, fetcher=fetcher, notifier=build_notifier(self.paths))
        changes = monitor.run_once()
        grades = fetcher.fetch_grades()
        self.root.after(0, lambda: self._check_complete(grades, changes))

    def _check_complete(self, grades: list[dict], changes: list[dict]) -> None:
        self.set_grades(grades)
        self.refresh_status()
        self.set_history(load_state(self.paths))
        self.message_var.set(f"检查完成，发现 {len(changes)} 项变化")

    def setup_login(self) -> None:
        student_id = simpledialog.askstring("登录/初始化", "请输入学号:", parent=self.root)
        if not student_id:
            return
        password = simpledialog.askstring("登录/初始化", "请输入密码（请切英文输入法）:", show="*", parent=self.root)
        if not password:
            return
        self.message_var.set("正在保存凭据并打开浏览器登录...")
        self._run_background(lambda: self._setup_worker(student_id, password))

    def _setup_worker(self, student_id: str, password: str) -> None:
        run_first_run_setup(
            paths=self.paths,
            student_id=student_id,
            password=password,
            interval_minutes=self.interval_var.get(),
            install_autostart=False,
        )
        grades = list(load_state(self.paths).get("grades", {}).values())
        self.root.after(0, lambda: self._setup_complete(grades))

    def _setup_complete(self, grades: list[dict]) -> None:
        self.set_grades(grades)
        self.refresh_status()
        self.set_history(load_state(self.paths))
        self.message_var.set("初始化完成，已建立成绩基线")

    def save_interval(self) -> None:
        config = set_poll_interval(self.paths, self.interval_var.get())
        self.interval_var.set(int(config["poll_interval_minutes"]))
        self.refresh_status()
        self.message_var.set(f"查询频率已设置为每 {config['poll_interval_minutes']} 分钟")

    def install_startup(self) -> None:
        result = install_task_or_startup()
        if result.returncode == 0:
            self.refresh_status()
            message = "已安装用户启动项，登录 Windows 后会自动后台检查。"
            self.message_var.set(message)
            messagebox.showinfo("自启动", message)
        else:
            messagebox.showerror("自启动失败", result.stderr or result.stdout)

    def uninstall_startup(self) -> None:
        result = uninstall_task_and_startup(skip_schtasks=True)
        if result.returncode == 0:
            self.refresh_status()
            self.message_var.set("已取消自启动")
            messagebox.showinfo("自启动", "已取消自启动")
        else:
            messagebox.showerror("取消失败", result.stderr or result.stdout)

    def open_data_dir(self) -> None:
        os.startfile(self.paths.root)

    def export_diagnostics(self) -> None:
        target = filedialog.asksaveasfilename(
            parent=self.root,
            title="导出诊断包",
            defaultextension=".zip",
            filetypes=[("Zip 文件", "*.zip")],
            initialfile="gdut-grade-monitor-diagnostics.zip",
        )
        if not target:
            return
        try:
            result = create_diagnostics_zip(paths=self.paths, output_path=Path(target))
        except Exception as exc:
            self._show_error(f"导出诊断包失败: {type(exc).__name__}: {exc}")
            return
        self.message_var.set(f"诊断包已导出: {result}")
        messagebox.showinfo("导出诊断包", f"已导出诊断包:\n{result}\n\n诊断包已隐藏学号、密码、Cookie 和完整成绩明细。")

    def show_about(self) -> None:
        messagebox.showinfo("关于 GDUT 成绩提醒", about_text())

    def _run_background(self, target) -> None:
        def runner():
            try:
                target()
            except (PasswordInputError, PlaywrightBrowserMissingError, BrowserFillMismatchError, GradeResponseError) as exc:
                self.root.after(0, lambda: self._show_error(str(exc)))
            except Exception as exc:
                self.root.after(0, lambda: self._show_error(f"{type(exc).__name__}: {exc}"))

        threading.Thread(target=runner, daemon=True).start()

    def _show_error(self, message: str) -> None:
        self.message_var.set(message)
        messagebox.showerror("GDUT 成绩提醒", message)


def main() -> None:
    root = tk.Tk()
    GradeMonitorApp(root)
    root.mainloop()


def app_icon_path() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "gdut_grade_monitor" / "assets" / "icon.ico"
    return Path(__file__).resolve().parent / "assets" / "icon.ico"
