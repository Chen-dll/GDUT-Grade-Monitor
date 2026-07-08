from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from .constants import CAS_LOGIN_URL, DEFAULT_BASE_URL, WELCOME_PATH
from .readonly import ReadonlyHttpClient
from .storage import AppPaths

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


class SessionExpiredError(RuntimeError):
    pass


class PlaywrightBrowserMissingError(RuntimeError):
    def __init__(self):
        super().__init__(
            "Playwright 浏览器还没安装。请先运行: python -m playwright install chromium"
        )


class BrowserFillMismatchError(RuntimeError):
    def __init__(self):
        super().__init__(
            "浏览器密码框中的内容和保存的密码不一致。请确认输入法已切换到英文后重新运行 setup。"
        )


class AuthManager:
    def __init__(self, paths: AppPaths, base_url: str = DEFAULT_BASE_URL):
        self.paths = paths
        self.base_url = base_url.rstrip("/")

    def get_session(self, auto_login: bool = True, student_id: str | None = None, password: str | None = None):
        cookies = self._load_cookies()
        if cookies:
            session = self._build_session(cookies)
            if self.is_logged_in(session):
                return session
        if not auto_login:
            raise SessionExpiredError("Session expired. Run gdut-grade setup.")
        return self.login(student_id=student_id, password=password)

    def login(self, student_id: str | None = None, password: str | None = None):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("playwright is required for login. Run: playwright install chromium") from exc

        self.paths.ensure()
        user_data_dir = str(self.paths.root / "browser_data")
        with sync_playwright() as p:
            launch_options = {
                "headless": False,
                "no_viewport": True,
                "ignore_https_errors": True,
                "args": ["--start-maximized", "--disable-blink-features=AutomationControlled"],
            }
            try:
                context = p.chromium.launch_persistent_context(user_data_dir=user_data_dir, **launch_options)
            except Exception as exc:
                if _is_missing_browser_error(exc):
                    system_browser = find_system_browser()
                    if not system_browser:
                        raise PlaywrightBrowserMissingError() from exc
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=user_data_dir,
                        executable_path=system_browser,
                        **launch_options,
                    )
                else:
                    raise
            page = context.pages[0] if context.pages else context.new_page()
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            page.goto(CAS_LOGIN_URL, wait_until="domcontentloaded")
            if student_id and password:
                self._try_fill_login(page, student_id, password)
            page.wait_for_url(
                lambda url: "welcome" in url or ("jxfw.gdut.edu.cn" in url and "authserver" not in url),
                timeout=300_000,
            )
            page.wait_for_timeout(2000)
            cookies = [c for c in context.cookies() if "gdut.edu.cn" in c.get("domain", "")]
            self._save_cookies(cookies)
            time.sleep(1)
            context.close()
        session = self._build_session(cookies)
        if not self.is_logged_in(session):
            raise SessionExpiredError("Login completed but session validation failed.")
        return session

    def is_logged_in(self, session) -> bool:
        try:
            response = ReadonlyHttpClient(session, self.base_url).get(WELCOME_PATH, allow_redirects=True, timeout=10)
        except Exception:
            return False
        final_url = getattr(response, "url", "")
        text = getattr(response, "text", "")
        if "authserver" in final_url or "统一身份认证" in text or "请求超时" in text:
            return False
        return getattr(response, "status_code", 0) == 200

    def _try_fill_login(self, page, student_id: str, password: str) -> None:
        username_filled = self._fill_first_available(page, ("input[name='username']", "#username"), student_id)
        password_locator = self._fill_first_available(page, ("input[name='password']", "#password"), password)
        if password_locator is not None:
            try:
                if password_locator.input_value(timeout=1000) != password:
                    raise BrowserFillMismatchError()
            except BrowserFillMismatchError:
                raise
            except Exception:
                pass
        if not username_filled or password_locator is None:
            return
        for selector in ("button[type='submit']", "#login_submit", "text=登录"):
            try:
                page.locator(selector).first.click(timeout=2000)
                return
            except Exception:
                continue

    @staticmethod
    def _fill_first_available(page, selectors: tuple[str, ...], value: str):
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                locator.fill(value, timeout=2000)
                return locator
            except Exception:
                continue
        return None

    def _save_cookies(self, cookies: list[dict]) -> None:
        self.paths.ensure()
        self.paths.cookies_file.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_cookies(self) -> list[dict] | None:
        try:
            return json.loads(Path(self.paths.cookies_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _build_session(cookies: list[dict]):
        session = requests.Session()
        session.headers.update(DEFAULT_HEADERS)
        for cookie in cookies:
            session.cookies.set(
                cookie.get("name", ""),
                cookie.get("value", ""),
                domain=cookie.get("domain"),
                path=cookie.get("path", "/"),
            )
        return session


def _is_missing_browser_error(exc: Exception) -> bool:
    message = str(exc)
    return "Executable doesn't exist" in message and "playwright install" in message


def find_system_browser(candidates: list[str | Path] | None = None) -> str | None:
    if candidates is None:
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            Path(program_files) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(program_files_x86) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(program_files) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(program_files_x86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(local_app_data) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None
