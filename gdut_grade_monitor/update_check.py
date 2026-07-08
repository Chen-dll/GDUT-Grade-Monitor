from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests

from .constants import APP_VERSION

GITHUB_REPO = "Chen-Dll/GDUT-Grade-Monitor"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"


class UpdateCheckError(RuntimeError):
    pass


@dataclass(frozen=True)
class GitHubRelease:
    tag_name: str
    name: str
    url: str
    body: str
    is_newer: bool


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


def check_latest_release(current_version: str = APP_VERSION, requests_module: Any = requests) -> GitHubRelease:
    try:
        response = requests_module.get(
            LATEST_RELEASE_API,
            headers={"Accept": "application/vnd.github+json", "User-Agent": "GDUT-Grade-Monitor"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        raise UpdateCheckError(f"无法检查更新：{exc}") from exc

    tag = str(payload.get("tag_name") or "")
    name = str(payload.get("name") or tag or "最新版本")
    url = str(payload.get("html_url") or RELEASES_URL)
    body = str(payload.get("body") or "")
    if not tag:
        raise UpdateCheckError("无法检查更新：GitHub 返回的数据缺少版本号。")

    return GitHubRelease(
        tag_name=tag,
        name=name,
        url=url,
        body=body,
        is_newer=is_newer_version(tag, current_version),
    )
