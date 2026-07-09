from __future__ import annotations

import re
import shutil
import subprocess
import sys
import locale
from dataclasses import dataclass
from pathlib import Path

from .constants import TASK_NAME

STARTUP_SCRIPT_NAME = f"{TASK_NAME}.vbs"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = TASK_NAME


@dataclass(frozen=True)
class TaskInstallResult:
    mode: str
    returncode: int
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class StartupEntryHealth:
    mode: str
    target: str
    target_exists: bool
    message: str


@dataclass(frozen=True)
class StartupHealth:
    ok: bool
    message: str
    entries: list[StartupEntryHealth]


def _hidden_subprocess_kwargs() -> dict:
    kwargs: dict = {}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    return kwargs


def _run_schtasks(args: list[str]) -> subprocess.CompletedProcess:
    command = ["schtasks", *args]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            timeout=15,
            **_hidden_subprocess_kwargs(),
        )
        return subprocess.CompletedProcess(
            result.args,
            result.returncode,
            _decode_process_output(result.stdout),
            _decode_process_output(result.stderr),
        )
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError) as exc:
        return subprocess.CompletedProcess(command, 1, "", f"{type(exc).__name__}: {exc}")


def _decode_process_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    candidates = [
        "gbk",
        locale.getpreferredencoding(False),
        sys.getfilesystemencoding(),
        "mbcs",
        "utf-8",
    ]
    seen: set[str] = set()
    for encoding in candidates:
        if not encoding or encoding.lower() in seen:
            continue
        seen.add(encoding.lower())
        try:
            return value.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return value.decode(locale.getpreferredencoding(False) or "utf-8", errors="replace")


def _is_access_denied(result: subprocess.CompletedProcess) -> bool:
    text = f"{result.stderr or ''}\n{result.stdout or ''}"
    return "Access is denied" in text or "拒绝访问" in text


def find_pythonw() -> str:
    executable = sys.executable
    if executable.lower().endswith("python.exe"):
        candidate = executable[:-10] + "pythonw.exe"
        if shutil.which(candidate) or candidate:
            return candidate
    return executable


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def build_monitor_command(pythonw: str | None = None) -> str:
    if is_frozen():
        return f'"{sys.executable}" --monitor'
    pythonw = pythonw or find_pythonw()
    executable = f'"{pythonw}"' if " " in pythonw and not pythonw.startswith('"') else pythonw
    return f"{executable} -m gdut_grade_monitor monitor"


def build_install_command(task_name: str = TASK_NAME, pythonw: str | None = None) -> list[str]:
    task_run = build_monitor_command(pythonw)
    return [
        "schtasks",
        "/Create",
        "/TN",
        task_name,
        "/SC",
        "ONLOGON",
        "/TR",
        task_run,
        "/F",
    ]


def install_task(task_name: str = TASK_NAME) -> subprocess.CompletedProcess:
    return _run_schtasks(build_install_command(task_name)[1:])


def uninstall_task(task_name: str = TASK_NAME) -> subprocess.CompletedProcess:
    return _run_schtasks(["/Delete", "/TN", task_name, "/F"])


def task_exists(task_name: str = TASK_NAME) -> bool:
    result = _run_schtasks(["/Query", "/TN", task_name])
    return result.returncode == 0


def startup_dir() -> Path:
    appdata = Path.home() / "AppData" / "Roaming"
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def startup_script_path(directory: Path | None = None) -> Path:
    return (directory or startup_dir()) / STARTUP_SCRIPT_NAME


def build_startup_script(pythonw: str | None = None) -> str:
    command = build_monitor_command(pythonw).replace('"', '""')
    return (
        'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.Run "{command}", 0, False\n'
    )


def install_run_key(pythonw: str | None = None) -> TaskInstallResult:
    if not sys.platform.startswith("win"):
        return TaskInstallResult(mode="failed", returncode=1, stderr="Run key startup is only available on Windows.")
    try:
        import winreg

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, RUN_VALUE_NAME, 0, winreg.REG_SZ, build_monitor_command(pythonw))
        return TaskInstallResult(mode="run-key", returncode=0)
    except OSError as exc:
        return TaskInstallResult(mode="failed", returncode=1, stderr=f"{type(exc).__name__}: {exc}")


def uninstall_run_key() -> TaskInstallResult:
    if not sys.platform.startswith("win"):
        return TaskInstallResult(mode="run-key", returncode=0)
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, RUN_VALUE_NAME)
            except FileNotFoundError:
                pass
        return TaskInstallResult(mode="run-key", returncode=0)
    except FileNotFoundError:
        return TaskInstallResult(mode="run-key", returncode=0)
    except OSError as exc:
        return TaskInstallResult(mode="failed", returncode=1, stderr=f"{type(exc).__name__}: {exc}")


def run_key_exists() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, RUN_VALUE_NAME)
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def install_startup_script(startup_dir: Path | None = None, pythonw: str | None = None) -> TaskInstallResult:
    directory = startup_dir or globals()["startup_dir"]()
    directory.mkdir(parents=True, exist_ok=True)
    startup_script_path(directory).write_text(build_startup_script(pythonw), encoding="utf-8")
    return TaskInstallResult(mode="startup", returncode=0)


def startup_script_exists(directory: Path | None = None) -> bool:
    return startup_script_path(directory).exists()


def startup_script_target(script_text: str) -> Path | None:
    match = re.search(r'WshShell\.Run\s+"((?:[^"]|"")*)"', script_text, flags=re.IGNORECASE)
    if not match:
        return None
    command = match.group(1).replace('""', '"').strip()
    return _command_target(command)


def _command_target(command: str) -> Path | None:
    if not command:
        return None
    if command.startswith('"'):
        end = command.find('"', 1)
        if end <= 1:
            return None
        executable = command[1:end]
    else:
        executable = command.split(maxsplit=1)[0]
    if not executable.lower().endswith(".exe"):
        return None
    return Path(executable)


def run_key_target() -> Path | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            value, _kind = winreg.QueryValueEx(key, RUN_VALUE_NAME)
    except OSError:
        return None
    return _command_target(str(value))


def startup_script_is_stale(directory: Path | None = None) -> bool:
    script = startup_script_path(directory)
    try:
        if not script.exists():
            return False
        target = startup_script_target(script.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return False
    return target is not None and not target.exists()


def _entry_health(mode: str, target: Path | None) -> StartupEntryHealth | None:
    if target is None:
        return None
    exists = target.exists()
    message = "目标存在" if exists else f"目标不存在: {target}"
    return StartupEntryHealth(mode=mode, target=str(target), target_exists=exists, message=message)


def startup_health(startup_dir: Path | None = None, include_schtasks: bool = False) -> StartupHealth:
    entries: list[StartupEntryHealth] = []
    script = startup_script_path(startup_dir)
    if startup_script_exists(startup_dir):
        try:
            target = startup_script_target(script.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            target = None
        entry = _entry_health("startup", target)
        if entry:
            entries.append(entry)
    run_entry = _entry_health("run-key", run_key_target())
    if run_entry:
        entries.append(run_entry)
    broken = [entry for entry in entries if not entry.target_exists]
    if broken:
        return StartupHealth(False, "启动项路径失效，目标文件不存在。", entries)
    if entries or (include_schtasks and task_exists()):
        return StartupHealth(True, "自启动已配置。", entries)
    return StartupHealth(True, "未检测到当前用户启动项。", entries)


def autostart_exists(include_schtasks: bool = False) -> bool:
    if startup_script_exists() or run_key_exists():
        return True
    return task_exists() if include_schtasks else False


def install_task_or_startup(
    task_name: str = TASK_NAME,
    startup_dir: Path | None = None,
    pythonw: str | None = None,
    prefer_startup: bool = False,
) -> TaskInstallResult:
    if prefer_startup:
        return install_startup_script(startup_dir=startup_dir, pythonw=pythonw)
    result = _run_schtasks(build_install_command(task_name=task_name, pythonw=pythonw)[1:])
    if result.returncode == 0:
        return TaskInstallResult(mode="schtasks", returncode=0, stdout=result.stdout, stderr=result.stderr)
    if _is_access_denied(result):
        try:
            return install_startup_script(startup_dir=startup_dir, pythonw=pythonw)
        except OSError:
            return install_run_key(pythonw=pythonw)
    return TaskInstallResult(mode="failed", returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)


def uninstall_task_and_startup(
    task_name: str = TASK_NAME,
    startup_dir: Path | None = None,
    skip_schtasks: bool = False,
) -> TaskInstallResult:
    script = startup_script_path(startup_dir)
    removed_startup = False
    if script.exists():
        script.unlink()
        removed_startup = True
    had_run_key = run_key_exists()
    run_key_result = uninstall_run_key()
    if skip_schtasks:
        return TaskInstallResult(mode="startup", returncode=0)
    result = uninstall_task(task_name)
    if result.returncode == 0:
        return TaskInstallResult(mode="schtasks", returncode=0, stdout=result.stdout, stderr=result.stderr)
    if removed_startup or (had_run_key and run_key_result.returncode == 0):
        return TaskInstallResult(mode="startup", returncode=0, stdout=result.stdout, stderr=result.stderr)
    return TaskInstallResult(mode="failed", returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
