import json
import unittest

import requests

from gdut_grade_monitor.auth import BrowserFillMismatchError, BrowserLaunchError, PlaywrightBrowserMissingError, SessionExpiredError
from gdut_grade_monitor.client import GradeResponseError
from gdut_grade_monitor.errors import user_friendly_error_message


class FakeResponse:
    text = "\n<html><title>统一身份认证</title><body>login page</body></html>"
    url = "https://authserver.gdut.edu.cn/authserver/login"
    status_code = 200


class FriendlyErrorMessageTests(unittest.TestCase):
    def test_maps_login_expired_to_relogin_guidance(self):
        message = user_friendly_error_message(SessionExpiredError("expired"))

        self.assertIn("登录状态已失效", message)
        self.assertIn("重新登录/初始化", message)

    def test_maps_html_grade_response_to_context_guidance_without_raw_html_dump(self):
        message = user_friendly_error_message(GradeResponseError(FakeResponse()))

        self.assertIn("教务系统没有返回成绩数据", message)
        self.assertIn("立即检查", message)
        self.assertNotIn("<html>", message.lower())

    def test_maps_missing_browser_to_one_click_install_guidance(self):
        message = user_friendly_error_message(PlaywrightBrowserMissingError())

        self.assertIn("没有找到可用于登录的浏览器", message)
        self.assertIn("Chrome 或 Edge", message)

    def test_maps_input_method_mismatch_to_english_input_hint(self):
        message = user_friendly_error_message(BrowserFillMismatchError())

        self.assertIn("输入法", message)
        self.assertIn("英文", message)

    def test_maps_browser_launch_error_without_raw_playwright_log(self):
        message = user_friendly_error_message(BrowserLaunchError())

        self.assertIn("登录浏览器启动失败", message)
        self.assertIn("关闭本工具打开的 Chrome/Edge", message)
        self.assertNotIn("TargetClosedError", message)
        self.assertNotIn("--remote-debugging-pipe", message)

    def test_maps_timeout_and_json_errors(self):
        timeout_message = user_friendly_error_message(requests.Timeout("slow"))
        json_message = user_friendly_error_message(json.JSONDecodeError("bad", "", 0))

        self.assertIn("网络超时", timeout_message)
        self.assertIn("重新登录", json_message)


if __name__ == "__main__":
    unittest.main()
