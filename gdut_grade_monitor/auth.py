from __future__ import annotations

import json
import os
import shutil
import subprocess
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


class BrowserLaunchError(RuntimeError):
    def __init__(self):
        super().__init__(
            "无法启动用于登录的浏览器。请先关闭本工具打开的 Chrome/Edge 登录窗口，"
            "然后在设置页点击“重新登录/初始化”再试；如果仍失败，请重启电脑后重试。"
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
        cleanup_dir: Path | None = None
        with sync_playwright() as p:
            launch_options = {
                "headless": False,
                "no_viewport": True,
                "ignore_https_errors": True,
                "args": ["--start-maximized", "--disable-blink-features=AutomationControlled"],
            }
            context, cleanup_dir = self._launch_login_context(p, launch_options)
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
            if cleanup_dir:
                shutil.rmtree(cleanup_dir, ignore_errors=True)
        session = self._build_session(cookies)
        if not self.is_logged_in(session):
            raise SessionExpiredError("Login completed but session validation failed.")
        return session

    def _launch_login_context(self, playwright, launch_options: dict):
        primary_dir = self.login_browser_data_dir
        errors = []
        for user_data_dir, cleanup in [(primary_dir, None), (self._temporary_login_browser_data_dir(), "remove")]:
            user_data_dir.mkdir(parents=True, exist_ok=True)
            for executable_path in [None, *find_system_browsers()]:
                try:
                    kwargs = dict(launch_options)
                    if executable_path:
                        kwargs["executable_path"] = executable_path
                    context = playwright.chromium.launch_persistent_context(
                        user_data_dir=str(user_data_dir),
                        **kwargs,
                    )
                    return context, user_data_dir if cleanup else None
                except Exception as exc:
                    errors.append(exc)
                    if _is_missing_browser_error(exc) and executable_path is None:
                        continue
                    continue

        if errors and all(_is_missing_browser_error(error) for error in errors):
            raise PlaywrightBrowserMissingError() from errors[-1]
        raise BrowserLaunchError() from (errors[-1] if errors else None)

    @property
    def login_browser_data_dir(self) -> Path:
        return self.paths.root / "browser_data"

    def _temporary_login_browser_data_dir(self) -> Path:
        return self.paths.root / f"browser_login_tmp_{int(time.time() * 1000)}"

    def open_url_with_login_profile(self, url: str) -> bool:
        self.paths.ensure()
        browser = find_system_browser()
        if not browser:
            return False
        subprocess.Popen(
            [
                browser,
                f"--user-data-dir={self.login_browser_data_dir}",
                "--new-window",
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
        )
        return True

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
        self._try_enable_extended_login(page)
        for selector in ("button[type='submit']", "#login_submit", "text=登录"):
            try:
                page.locator(selector).first.click(timeout=2000)
                return
            except Exception:
                continue

    @staticmethod
    def _try_enable_extended_login(page) -> bool:
        script = """
        () => {
            const keywords = ["7天", "七天", "保持登录", "免登录", "记住", "remember"];
            const boxes = Array.from(document.querySelectorAll("input[type='checkbox']"));
            for (const box of boxes) {
                const id = box.id || "";
                let forLabel = "";
                if (id && window.CSS && CSS.escape) {
                    const label = document.querySelector(`label[for="${CSS.escape(id)}"]`);
                    forLabel = label ? label.innerText : "";
                }
                const text = [
                    box.name || "",
                    box.id || "",
                    box.value || "",
                    box.getAttribute("aria-label") || "",
                    box.closest("label") ? box.closest("label").innerText : "",
                    box.parentElement ? box.parentElement.innerText : "",
                    forLabel,
                ].join(" ");
                if (keywords.some((keyword) => text.includes(keyword))) {
                    if (!box.checked) {
                        box.click();
                    }
                    return true;
                }
            }
            return false;
        }
        """
        try:
            return bool(page.evaluate(script))
        except Exception:
            return False

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
    browsers = find_system_browsers(candidates)
    return browsers[0] if browsers else None


def find_system_browsers(candidates: list[str | Path] | None = None) -> list[str]:
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
    browsers = []
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            value = str(path)
            if value not in browsers:
                browsers.append(value)
    return browsers
