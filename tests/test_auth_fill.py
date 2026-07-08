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

    def locator(self, selector):
        return FakeLocator(self, selector)


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
        self.assertTrue(page.clicked)


if __name__ == "__main__":
    unittest.main()
