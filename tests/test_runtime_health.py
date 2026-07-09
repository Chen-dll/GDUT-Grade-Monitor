import unittest
from unittest.mock import Mock

from requests import ConnectionError, Timeout

from gdut_grade_monitor.auth import PlaywrightBrowserMissingError
from gdut_grade_monitor.client import GradeResponseError
from gdut_grade_monitor.runtime_health import classify_error


def grade_response_error(status_code=200, url="https://jxfw.gdut.edu.cn/xskccjxx!getDataList.action", text=""):
    response = Mock(status_code=status_code, url=url, text=text)
    return GradeResponseError(response)


class RuntimeHealthTests(unittest.TestCase):
    def test_classifies_login_expired_from_grade_response(self):
        error = grade_response_error(
            url="https://authserver.gdut.edu.cn/authserver/login",
            text="<html>统一身份认证</html>",
        )

        result = classify_error(error)

        self.assertEqual(result.kind, "login_expired")
        self.assertIn("重新登录", result.action)

    def test_classifies_network_errors(self):
        for error in [Timeout("timed out"), ConnectionError("network down")]:
            with self.subTest(error=type(error).__name__):
                result = classify_error(error)
                self.assertEqual(result.kind, "network")
                self.assertEqual(result.severity, "warning")

    def test_classifies_school_system_payload_errors(self):
        error = grade_response_error(status_code=502, text="<html>bad gateway</html>")

        result = classify_error(error)

        self.assertEqual(result.kind, "school_system")
        self.assertIn("稍后", result.action)

    def test_classifies_browser_missing_and_unknown(self):
        self.assertEqual(classify_error(PlaywrightBrowserMissingError()).kind, "browser_missing")
        self.assertEqual(classify_error(RuntimeError("strange")).kind, "unknown")


if __name__ == "__main__":
    unittest.main()
