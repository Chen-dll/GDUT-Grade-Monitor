from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests

from .constants import APP_VERSION

GITHUB_REPO = "Chen-Dll/GDUT-Grade-Monitor"
GITEE_REPO = "chenpro/GDUT-Grade-Monitor"
GITHUB_LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
GITEE_LATEST_RELEASE_API = f"https://gitee.com/api/v5/repos/{GITEE_REPO}/releases/latest"
GITEE_RELEASES_URL = f"https://gitee.com/{GITEE_REPO}/releases"
LATEST_RELEASE_API = GITHUB_LATEST_RELEASE_API
RELEASES_URL = GITHUB_RELEASES_URL


class UpdateCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateSource:
    name: str
    api_url: str
    releases_url: str
    headers: dict[str, str]


@dataclass(frozen=True)
class PatchUpdate:
    from_version: str
    to_version: str
    manifest_name: str
    manifest_url: str
    archive_name: str
    archive_url: str
    archive_size: int


@dataclass(frozen=True)
class GitHubRelease:
    tag_name: str
    name: str
    url: str
    body: str
    is_newer: bool
    patch_update: PatchUpdate | None = None
    source_name: str = "GitHub"


DEFAULT_UPDATE_SOURCES = (
    UpdateSource(
        name="GitHub",
        api_url=GITHUB_LATEST_RELEASE_API,
        releases_url=GITHUB_RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "GDUT-Grade-Monitor"},
    ),
    UpdateSource(
        name="Gitee",
        api_url=GITEE_LATEST_RELEASE_API,
        releases_url=GITEE_RELEASES_URL,
        headers={"Accept": "application/json", "User-Agent": "GDUT-Grade-Monitor"},
    ),
)


def parse_version(version: str) -> tuple[int, int, int]:
    text = version.strip().lower()
    if text.startswith("v"):
        text = text[1:]
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", text)
    if not match:
        raise ValueError(f"Invalid semantic version: {version}")
    return tuple(int(part) for part in match.groups())


def is_newer_version(latest: str, current: str = APP_VERSION) -> bool:
    return parse_version(latest) > parse_version(current)


def check_latest_release(
    current_version: str = APP_VERSION,
    requests_module: Any = requests,
    sources: tuple[UpdateSource, ...] = DEFAULT_UPDATE_SOURCES,
) -> GitHubRelease:
    errors: list[str] = []
    for source in sources:
        try:
            return _check_release_source(source, current_version, requests_module)
        except Exception as exc:
            errors.append(f"{source.name}: {exc}")

    details = "；".join(errors) if errors else "没有可用更新源"
    raise UpdateCheckError(f"无法检查更新：{details}")


def _check_release_source(source: UpdateSource, current_version: str, requests_module: Any) -> GitHubRelease:
    try:
        response = requests_module.get(
            source.api_url,
            headers=source.headers,
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise UpdateCheckError(str(exc)) from exc

    tag = str(payload.get("tag_name") or "")
    name = str(payload.get("name") or tag or "最新版本")
    url = str(payload.get("html_url") or payload.get("url") or source.releases_url)
    body = str(payload.get("body") or payload.get("description") or "")
    if not tag:
        raise UpdateCheckError(f"{source.name} 返回的数据缺少版本号。")

    return GitHubRelease(
        tag_name=tag,
        name=name,
        url=url,
        body=body,
        is_newer=is_newer_version(tag, current_version),
        patch_update=_find_patch_update(_release_assets(payload), current_version, tag),
        source_name=source.name,
    )


def _version_tag(version: str) -> str:
    text = version.strip()
    return text if text.lower().startswith("v") else f"v{text}"


def _release_assets(payload: dict[str, Any]) -> Any:
    return payload.get("assets") or payload.get("attach_files") or payload.get("attachments") or []


def _find_patch_update(assets: Any, current_version: str, latest_version: str) -> PatchUpdate | None:
    if not isinstance(assets, list):
        return None
    from_tag = _version_tag(current_version)
    to_tag = _version_tag(latest_version)
    prefix = f"GDUTGradeMonitor-patch-{from_tag}-to-{to_tag}"
    manifest_name = f"{prefix}.json"
    archive_name = f"{prefix}.zip"
    by_name = {
        _asset_name(asset): asset
        for asset in assets
        if isinstance(asset, dict) and _asset_name(asset)
    }
    manifest = by_name.get(manifest_name)
    archive = by_name.get(archive_name)
    if not manifest or not archive:
        return None
    manifest_url = _asset_download_url(manifest)
    archive_url = _asset_download_url(archive)
    if not manifest_url or not archive_url:
        return None
    return PatchUpdate(
        from_version=from_tag,
        to_version=to_tag,
        manifest_name=manifest_name,
        manifest_url=manifest_url,
        archive_name=archive_name,
        archive_url=archive_url,
        archive_size=_asset_size(archive),
    )


def _asset_name(asset: dict[str, Any]) -> str:
    return str(asset.get("name") or asset.get("filename") or asset.get("path") or "")


def _asset_download_url(asset: dict[str, Any]) -> str:
    url = str(asset.get("browser_download_url") or asset.get("download_url") or asset.get("url") or "")
    if url.startswith("/"):
        return f"https://gitee.com{url}"
    return url


def _asset_size(asset: dict[str, Any]) -> int:
    try:
        return int(asset.get("size") or asset.get("filesize") or 0)
    except (TypeError, ValueError):
        return 0
