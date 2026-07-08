import unittest

from gdut_grade_monitor.auth import AuthManager, BrowserFillMismatchError


class FakeLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector
        self.first = self

    def fill(self, value, timeout=None):
        self.page.values[self.selector] = value

    def input_value(self, timeout=None):
        if self.selector == "input[name='password']" and self.page.force_password_mismatch:
            return "密码"
        return self.page.values.get(self.selector, "")

    def click(self, timeout=None):
        self.page.clicked = True


class FakePage:
    def __init__(self, force_password_mismatch=False):
        self.force_password_mismatch = force_password_mismatch
        self.values = {}
        self.clicked = False
        self.evaluate_scripts = []

    def locator(self, selector):
        return FakeLocator(self, selector)

    def evaluate(self, script):
        self.evaluate_scripts.append(script)
        return True


class AuthFillTests(unittest.TestCase):
    def test_try_fill_login_detects_password_mismatch_after_fill(self):
        page = FakePage(force_password_mismatch=True)

        with self.assertRaises(BrowserFillMismatchError):
            AuthManager(paths=None)._try_fill_login(page, "3210000000", "correct-password")

    def test_try_fill_login_clicks_submit_after_verified_fill(self):
        page = FakePage()

        AuthManager(paths=None)._try_fill_login(page, "3210000000", "correct-password")

        self.assertEqual(page.values["input[name='username']"], "3210000000")
        self.assertEqual(page.values["input[name='password']"], "correct-password")
        self.assertTrue(any("7天" in script and "保持登录" in script for script in page.evaluate_scripts))
        self.assertTrue(page.clicked)

    def test_try_enable_extended_login_ignores_missing_checkbox(self):
        class NoCheckboxPage(FakePage):
            def evaluate(self, script):
                self.evaluate_scripts.append(script)
                return False

        page = NoCheckboxPage()

        enabled = AuthManager(paths=None)._try_enable_extended_login(page)

        self.assertFalse(enabled)
        self.assertTrue(page.evaluate_scripts)


if __name__ == "__main__":
    unittest.main()
