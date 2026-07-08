from __future__ import annotations

import json

import requests

from .auth import BrowserFillMismatchError, PlaywrightBrowserMissingError, SessionExpiredError
from .client import GradeResponseError
from .credentials import PasswordInputError
from .update_check import UpdateCheckError


def user_friendly_error_message(exc: Exception) -> str:
    if isinstance(exc, BrowserFillMismatchError):
        return (
            "登录填写时检测到密码框内容和保存的密码不一致。\n\n"
            "请把输入法切换到英文/半角后，在设置页点击“重新登录/初始化”再试。"
        )
    if isinstance(exc, PasswordInputError):
        return f"密码输入看起来不正确：{exc}\n\n请切换到英文/半角输入法后重新填写。"
    if isinstance(exc, PlaywrightBrowserMissingError):
        return (
            "没有找到可用于登录的浏览器。\n\n"
            "请先安装 Chrome 或 Edge，然后重新打开本工具；如果你使用源码运行，也可以执行 "
            "python -m playwright install chromium。"
        )
    if isinstance(exc, SessionExpiredError):
        return (
            "登录状态已失效，需要重新验证。\n\n"
            "请在设置页点击“重新登录/初始化”，按弹出的学校登录页完成认证。"
        )
    if isinstance(exc, GradeResponseError):
        return (
            "教务系统没有返回成绩数据，通常是登录状态过期、学校页面要求重新验证，或教务系统临时返回了网页。\n\n"
            "请先点击“重新登录/初始化”，登录完成后再点“立即检查”。"
        )
    if isinstance(exc, requests.Timeout):
        return "网络超时。请确认当前网络能访问学校统一认证和教务系统，然后稍后重试。"
    if isinstance(exc, requests.ConnectionError):
        return "网络连接失败。请检查校园网/VPN、DNS 或代理设置后重试。"
    if isinstance(exc, json.JSONDecodeError):
        return "成绩接口返回内容无法解析，可能需要重新登录。请在设置页重新登录后再检查。"
    if isinstance(exc, UpdateCheckError):
        return str(exc)
    return f"{type(exc).__name__}: {exc}"
