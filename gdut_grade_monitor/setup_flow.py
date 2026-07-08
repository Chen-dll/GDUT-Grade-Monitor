from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from .auth import AuthManager
from .client import GradeApiClient
from .credentials import CredentialStore
from .monitor import GradeFetcher, GradeMonitor, Notifier
from .notify import WindowsNotifier
from .storage import AppPaths, load_config, load_state, save_config, set_poll_interval
from .task import TaskInstallResult, install_task_or_startup


class CredentialWriter(Protocol):
    def set_credentials(self, student_id: str, password: str) -> None:
        ...


class AuthSessionManager(Protocol):
    def get_session(self, **kwargs):
        ...


@dataclass(frozen=True)
class FirstRunSetupResult:
    grade_count: int
    change_count: int
    startup_mode: str


def run_first_run_setup(
    *,
    paths: AppPaths,
    student_id: str,
    password: str,
    interval_minutes: int,
    credential_store: CredentialWriter | None = None,
    auth_manager: AuthSessionManager | None = None,
    fetcher_factory: Callable[[object], GradeFetcher] | None = None,
    notifier: Notifier | None = None,
    install_autostart: bool = True,
    startup_installer: Callable[[], TaskInstallResult] | None = None,
) -> FirstRunSetupResult:
    paths.ensure()
    credential_store = credential_store or CredentialStore()
    auth_manager = auth_manager or AuthManager(paths)
    fetcher_factory = fetcher_factory or (lambda session: GradeApiClient(session))
    notifier = notifier or WindowsNotifier()
    startup_installer = startup_installer or (lambda: install_task_or_startup(prefer_startup=True))

    credential_store.set_credentials(student_id, password)

    config = load_config(paths)
    config["student_id"] = student_id
    save_config(paths, config)
    set_poll_interval(paths, interval_minutes)

    session = auth_manager.get_session(auto_login=True, student_id=student_id, password=password)
    fetcher = fetcher_factory(session)
    monitor = GradeMonitor(paths, fetcher=fetcher, notifier=notifier)
    changes = monitor.run_once()
    grades = load_state(paths).get("grades", {})

    startup_mode = "skipped"
    if install_autostart:
        result = startup_installer()
        startup_mode = result.mode if result.returncode == 0 else "failed"
        config = load_config(paths)
        config["startup_enabled"] = result.returncode == 0
        save_config(paths, config)

    return FirstRunSetupResult(
        grade_count=len(grades),
        change_count=len(changes),
        startup_mode=startup_mode,
    )
