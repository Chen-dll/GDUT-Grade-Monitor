from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import requests

from .constants import APP_NAME, APP_VERSION
from .storage import AppPaths
from .update_check import PatchUpdate


class PatchManifestError(RuntimeError):
    pass


class PatchDownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class PatchApplyPlan:
    command: list[str]
    manifest_path: Path
    archive_path: Path


def current_install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def can_apply_patch() -> bool:
    return getattr(sys, "frozen", False) and current_install_dir().joinpath("GDUTGradeMonitor.exe").exists()


def download_patch_package(
    patch: PatchUpdate,
    paths: AppPaths,
    current_version: str = APP_VERSION,
    requests_module: Any = requests,
) -> tuple[Path, dict[str, Any]]:
    update_dir = paths.root / "updates" / patch.to_version
    update_dir.mkdir(parents=True, exist_ok=True)
    manifest = _download_json(patch.manifest_url, requests_module)
    archive_path = update_dir / patch.archive_name
    _download_file(patch.archive_url, archive_path, requests_module)
    verify_patch_archive(archive_path, manifest, current_version=current_version, target_version=patch.to_version)
    return archive_path, manifest


def verify_patch_archive(
    archive_path: Path,
    manifest: dict[str, Any],
    current_version: str,
    target_version: str,
) -> Path:
    if int(manifest.get("schema", 0) or 0) != 1:
        raise PatchManifestError("补丁清单版本不受支持。")
    if str(manifest.get("app", APP_NAME) or APP_NAME) != APP_NAME:
        raise PatchManifestError("补丁清单不属于当前应用。")
    if _version_tag(str(manifest.get("from_version", ""))) != _version_tag(current_version):
        raise PatchManifestError("补丁来源版本与当前版本不匹配。")
    if _version_tag(str(manifest.get("to_version", ""))) != _version_tag(target_version):
        raise PatchManifestError("补丁目标版本与最新版本不匹配。")
    expected_hash = str(manifest.get("archive_sha256", "")).strip().lower()
    if not expected_hash:
        raise PatchManifestError("补丁清单缺少 SHA256 校验值。")
    actual_hash = _sha256(archive_path)
    if actual_hash != expected_hash:
        raise PatchManifestError("补丁包 SHA256 校验失败，已取消更新。")
    safe_patch_files(manifest.get("files", []))
    return archive_path


def safe_patch_files(files: Any) -> list[str]:
    if not isinstance(files, list) or not files:
        raise PatchManifestError("补丁清单缺少文件列表。")
    safe_files = []
    for item in files:
        text = str(item).replace("\\", "/").strip()
        path = PurePosixPath(text)
        if not text or ":" in text or path.is_absolute() or any(part == ".." for part in path.parts):
            raise PatchManifestError("补丁清单包含不安全路径。")
        safe_files.append(text)
    return safe_files


def build_patch_apply_plan(
    patch: PatchUpdate,
    archive_path: Path,
    manifest: dict[str, Any],
    data_dir: Path,
    install_dir: Path,
    current_pid: int | None = None,
    executable_path: Path | None = None,
) -> PatchApplyPlan:
    update_dir = data_dir / "updates" / patch.to_version
    update_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = update_dir / patch.manifest_name
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    helper = _patch_helper_path()
    pid = current_pid if current_pid is not None else os.getpid()
    exe = executable_path or install_dir / "GDUTGradeMonitor.exe"
    command = [
        "powershell.exe",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(helper),
        "-ArchivePath",
        str(archive_path),
        "-ManifestPath",
        str(manifest_path),
        "-InstallDir",
        str(install_dir),
        "-WaitPid",
        str(pid),
        "-ExecutablePath",
        str(exe),
    ]
    return PatchApplyPlan(command=command, manifest_path=manifest_path, archive_path=archive_path)


def launch_patch_apply(plan: PatchApplyPlan) -> None:
    subprocess.Popen(plan.command, close_fds=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _patch_helper_path() -> Path:
    packaged = current_install_dir() / "GDUTGradeMonitor-PatchUpdate.ps1"
    if packaged.exists():
        return packaged
    return Path(__file__).resolve().parents[1] / "scripts" / "apply_patch_update.ps1"


def _download_json(url: str, requests_module: Any) -> dict[str, Any]:
    try:
        response = requests_module.get(url, headers=_headers(), timeout=12)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise PatchDownloadError(f"无法下载补丁清单：{exc}") from exc
    if not isinstance(payload, dict):
        raise PatchDownloadError("补丁清单格式不正确。")
    return payload


def _download_file(url: str, path: Path, requests_module: Any) -> None:
    try:
        response = requests_module.get(url, headers=_headers(), timeout=30)
        response.raise_for_status()
        content = response.content
    except Exception as exc:
        raise PatchDownloadError(f"无法下载补丁包：{exc}") from exc
    path.write_bytes(content)


def _headers() -> dict[str, str]:
    return {"User-Agent": "GDUT-Grade-Monitor", "Accept": "application/octet-stream"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version_tag(version: str) -> str:
    text = version.strip()
    return text if text.lower().startswith("v") else f"v{text}"
