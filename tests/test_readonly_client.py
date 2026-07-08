import unittest

from gdut_grade_monitor.readonly import ReadonlyHttpClient, ReadonlyViolation


class FakeSession:
    def get(self, url, **kwargs):
        return {"method": "GET", "url": url, "kwargs": kwargs}

    def post(self, url, **kwargs):
        return {"method": "POST", "url": url, "kwargs": kwargs}


class ReadonlyHttpClientTests(unittest.TestCase):
    def test_allows_only_welcome_get_and_grade_post(self):
        client = ReadonlyHttpClient(FakeSession(), base_url="https://jxfw.gdut.edu.cn")

        welcome = client.get("/login!welcome.action", timeout=3)
        grades = client.post("/xskccjxx!getDataList.action", data={"rows": "200"})

        self.assertEqual(welcome["method"], "GET")
        self.assertEqual(welcome["url"], "https://jxfw.gdut.edu.cn/login!welcome.action")
        self.assertEqual(grades["method"], "POST")
        self.assertEqual(grades["url"], "https://jxfw.gdut.edu.cn/xskccjxx!getDataList.action")

    def test_blocks_non_readonly_paths_and_methods(self):
        client = ReadonlyHttpClient(FakeSession(), base_url="https://jxfw.gdut.edu.cn")

        unsafe_calls = [
            lambda: client.post("/jxpj!saveEvaluation.action", data={}),
            lambda: client.post("/password!change.action", data={}),
            lambda: client.get("/xskccjxx!getDataList.action"),
            lambda: client.post("/login!welcome.action", data={}),
        ]

        for call in unsafe_calls:
            with self.subTest(call=call):
                with self.assertRaises(ReadonlyViolation):
                    call()


if __name__ == "__main__":
    unittest.main()
