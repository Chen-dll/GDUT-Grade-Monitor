from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .constants import TASK_NAME

STARTUP_SCRIPT_NAME = f"{TASK_NAME}.vbs"


@dataclass(frozen=True)
class TaskInstallResult:
    mode: str
    returncode: int
    stdout: str = ""
    stderr: str = ""


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
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
            **_hidden_subprocess_kwargs(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return subprocess.CompletedProcess(command, 1, "", f"{type(exc).__name__}: {exc}")


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


def install_startup_script(startup_dir: Path | None = None, pythonw: str | None = None) -> TaskInstallResult:
    directory = startup_dir or globals()["startup_dir"]()
    directory.mkdir(parents=True, exist_ok=True)
    startup_script_path(directory).write_text(build_startup_script(pythonw), encoding="utf-8")
    return TaskInstallResult(mode="startup", returncode=0)


def startup_script_exists(directory: Path | None = None) -> bool:
    return startup_script_path(directory).exists()


def autostart_exists(include_schtasks: bool = False) -> bool:
    if startup_script_exists():
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
    if "Access is denied" in (result.stderr or "") or "拒绝访问" in (result.stderr or ""):
        return install_startup_script(startup_dir=startup_dir, pythonw=pythonw)
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
    if skip_schtasks:
        return TaskInstallResult(mode="startup", returncode=0)
    result = uninstall_task(task_name)
    if result.returncode == 0:
        return TaskInstallResult(mode="schtasks", returncode=0, stdout=result.stdout, stderr=result.stderr)
    if removed_startup:
        return TaskInstallResult(mode="startup", returncode=0, stdout=result.stdout, stderr=result.stderr)
    return TaskInstallResult(mode="failed", returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
