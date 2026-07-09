from __future__ import annotations

import getpass
import json
import logging
import sys
from pathlib import Path

import click

from .auth import AuthManager, BrowserFillMismatchError, PlaywrightBrowserMissingError
from .client import GradeApiClient, GradeResponseError
from .cleanup import cleanup_residue, cleanup_summary
from .credentials import CredentialStore, PasswordInputError
from .diagnostics import create_diagnostics_zip, mask_student_id
from .doctor import overall_ok, render_results, run_checks
from .monitor import GradeMonitor
from .notification_channels import build_notifier
from .settings_backup import export_settings, import_settings
from .storage import AppPaths, load_config, reset_config, save_config, set_poll_interval
from .task import autostart_exists, install_task_or_startup, uninstall_task_and_startup


def _paths() -> AppPaths:
    paths = AppPaths()
    paths.ensure()
    return paths


def _configure_logging(paths: AppPaths) -> None:
    config = load_config(paths)
    logging.basicConfig(
        filename=str(paths.log_file),
        level=getattr(logging, str(config.get("log_level", "INFO")).upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _make_monitor(paths: AppPaths) -> GradeMonitor:
    config = load_config(paths)
    student_id = config.get("student_id", "")
    password = CredentialStore().get_password(student_id) if student_id else None
    session = AuthManager(paths).get_session(auto_login=True, student_id=student_id, password=password)
    return GradeMonitor(paths=paths, fetcher=GradeApiClient(session), notifier=build_notifier(paths))


@click.group()
def main():
    """GDUT read-only grade monitor."""


@main.command()
def doctor():
    """Check local environment and configuration."""
    results = run_checks(_paths())
    click.echo(render_results(results))
    if not overall_ok(results):
        sys.exit(1)


@main.command()
@click.option("--student-id", prompt=True, help="GDUT student id.")
def setup(student_id: str):
    """Store credentials, login, and create the initial grade baseline."""
    paths = _paths()
    _configure_logging(paths)
    password = getpass.getpass("Password: ")
    try:
        CredentialStore().set_credentials(student_id, password)
    except PasswordInputError as exc:
        raise click.ClickException(str(exc)) from exc
    config = load_config(paths)
    config["student_id"] = student_id
    save_config(paths, config)
    try:
        monitor = _make_monitor(paths)
        monitor.run_once()
    except (PlaywrightBrowserMissingError, BrowserFillMismatchError, GradeResponseError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("Setup complete. Initial grade baseline saved.")


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def check(as_json: bool):
    """Run one read-only grade check."""
    paths = _paths()
    _configure_logging(paths)
    config = load_config(paths)
    student_id = config.get("student_id", "")
    password = CredentialStore().get_password(student_id) if student_id else None
    try:
        session = AuthManager(paths).get_session(auto_login=True, student_id=student_id, password=password)
    except (PlaywrightBrowserMissingError, BrowserFillMismatchError) as exc:
        raise click.ClickException(str(exc)) from exc
    try:
        grades = GradeApiClient(session).fetch_grades()
    except GradeResponseError as exc:
        raise click.ClickException(str(exc)) from exc
    if as_json:
        click.echo(json.dumps(grades, ensure_ascii=False, indent=2))
    else:
        for grade in grades:
            click.echo(f"{grade['semester']} {grade['course_name']}: {grade['score']}")


@main.command()
@click.option("--once", is_flag=True, help="Run one monitor iteration and exit.")
def monitor(once: bool):
    """Monitor grades in the background."""
    paths = _paths()
    _configure_logging(paths)
    try:
        grade_monitor = _make_monitor(paths)
    except (PlaywrightBrowserMissingError, BrowserFillMismatchError) as exc:
        raise click.ClickException(str(exc)) from exc
    if once:
        try:
            changes = grade_monitor.run_once()
        except GradeResponseError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"Checked grades. Changes: {len(changes)}")
    else:
        grade_monitor.run_forever()


@main.group()
def task():
    """Manage Windows scheduled task."""


@task.command("install")
def task_install():
    result = install_task_or_startup()
    if result.returncode == 0:
        paths = _paths()
        config = load_config(paths)
        config["startup_enabled"] = True
        save_config(paths, config)
        if result.mode == "startup":
            click.echo("Scheduled task access was denied; installed user Startup fallback instead.")
        elif result.mode == "run-key":
            click.echo("Scheduled task and Startup folder were unavailable; installed current-user Run fallback instead.")
        else:
            click.echo("Scheduled task installed.")
    else:
        click.echo(result.stderr or result.stdout, err=True)
        sys.exit(result.returncode)


@task.command("uninstall")
def task_uninstall():
    result = uninstall_task_and_startup()
    if result.returncode == 0:
        paths = _paths()
        config = load_config(paths)
        config["startup_enabled"] = False
        save_config(paths, config)
        click.echo("Startup monitor removed.")
    else:
        click.echo(result.stderr or result.stdout, err=True)
        sys.exit(result.returncode)


@task.command("status")
def task_status():
    click.echo("installed" if autostart_exists(include_schtasks=True) else "not installed")


@main.group()
def config():
    """Manage monitor configuration."""


@config.command("interval")
@click.argument("minutes", type=int)
def config_interval(minutes: int):
    """Set polling interval in minutes."""
    paths = _paths()
    updated = set_poll_interval(paths, minutes)
    click.echo(f"Polling interval set to {updated['poll_interval_minutes']} minutes.")


@config.command("show")
def config_show():
    """Show non-sensitive configuration."""
    config = load_config(_paths())
    if config.get("student_id"):
        config["student_id"] = mask_student_id(str(config["student_id"]))
    click.echo(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True))


@config.command("export")
@click.option("--output", type=click.Path(dir_okay=False, path_type=Path), required=True, help="Output JSON path.")
def config_export(output: Path):
    """Export non-sensitive settings for migration."""
    result = export_settings(_paths(), output)
    click.echo(f"Settings exported: {result}")


@config.command("import")
@click.option("--input", "input_path", type=click.Path(exists=True, dir_okay=False, path_type=Path), required=True, help="Input JSON path.")
def config_import(input_path: Path):
    """Import non-sensitive settings without overwriting local credentials."""
    import_settings(_paths(), input_path)
    click.echo("Settings imported.")


@config.command("reset")
def config_reset():
    """Restore recommended defaults while keeping local account identity."""
    reset_config(_paths())
    click.echo("Settings reset to recommended defaults.")


@main.group()
def diagnostics():
    """Create support diagnostics without secrets."""


@diagnostics.command("export")
@click.option("--output", type=click.Path(dir_okay=False, path_type=Path), help="Output zip path.")
def diagnostics_export(output: Path | None):
    """Export a sanitized diagnostics zip for troubleshooting."""
    paths = _paths()
    result = create_diagnostics_zip(paths=paths, output_path=output, check_results=run_checks(paths))
    click.echo(f"Diagnostics exported: {result}")


@main.command()
def gui():
    """Open the desktop GUI."""
    from .qt_gui import main as gui_main

    gui_main()


@main.command("legacy-gui")
def legacy_gui():
    """Open the legacy Tkinter GUI."""
    from .gui import main as legacy_gui_main

    legacy_gui_main()


@main.command("cleanup")
@click.option("--remove-data", is_flag=True, help="Also delete local config, cookies, grade snapshot, and logs.")
def cleanup_command(remove_data: bool):
    """Remove leftover startup entries after deleting the portable folder."""
    result = cleanup_residue(remove_data=remove_data)
    click.echo(cleanup_summary(result))
    if remove_data:
        click.echo("提示：Windows 凭据管理器中的密码和通知密钥需要按需手动删除。")
