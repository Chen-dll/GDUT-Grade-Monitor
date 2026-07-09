from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from .constants import DEFAULT_DATA_DIR
from .task import (
    STARTUP_SCRIPT_NAME,
    run_key_exists,
    startup_dir as default_startup_dir,
    startup_script_path,
    uninstall_run_key,
    uninstall_task,
)


@dataclass(frozen=True)
class CleanupResult:
    removed_startup: bool
    removed_run_key: bool
    scheduled_task_returncode: int | None
    scheduled_task_message: str
    removed_data: bool


def cleanup_residue(
    *,
    startup_dir: Path | None = None,
    data_dir: Path | None = None,
    remove_data: bool = False,
    remove_scheduled_task: bool = True,
) -> CleanupResult:
    startup_directory = startup_dir or default_startup_dir()
    script = startup_script_path(startup_directory)
    removed_startup = False
    if script.name == STARTUP_SCRIPT_NAME and script.exists():
        script.unlink()
        removed_startup = True

    had_run_key = run_key_exists()
    run_key_result = uninstall_run_key()
    removed_run_key = had_run_key and run_key_result.returncode == 0

    scheduled_returncode: int | None = None
    scheduled_message = "未处理"
    if remove_scheduled_task:
        task_result = uninstall_task()
        scheduled_returncode = int(task_result.returncode)
        scheduled_message = (task_result.stderr or task_result.stdout or "").strip()

    removed_data = False
    data_path = data_dir or DEFAULT_DATA_DIR
    if remove_data and data_path.exists():
        shutil.rmtree(data_path)
        removed_data = True

    return CleanupResult(
        removed_startup=removed_startup,
        removed_run_key=removed_run_key,
        scheduled_task_returncode=scheduled_returncode,
        scheduled_task_message=scheduled_message,
        removed_data=removed_data,
    )


def cleanup_summary(result: CleanupResult) -> str:
    startup = "已删除" if result.removed_startup else "未发现"
    run_key = "已删除" if result.removed_run_key else "未发现"
    if result.scheduled_task_returncode is None:
        task = "未处理"
    elif result.scheduled_task_returncode == 0:
        task = "已删除"
    else:
        task = "未发现或删除失败"
    data = "已删除" if result.removed_data else "未删除"
    return f"启动文件: {startup}\n注册表启动项: {run_key}\n计划任务: {task}\n本地数据: {data}"
