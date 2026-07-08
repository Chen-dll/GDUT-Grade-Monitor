import unittest

from gdut_grade_monitor.client import GradeApiClient, GradeResponseError


class FakeResponse:
    def __init__(self, payload=None, text="", json_error=None):
        self.payload = payload
        self.text = text
        self.json_error = json_error
        self.status_code = 200
        self.url = "https://jxfw.gdut.edu.cn/xskccjxx!getDataList.action"
        self.headers = {"content-type": "text/html;charset=UTF-8"}

    def raise_for_status(self):
        return None

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.headers = {}
        self.post_kwargs = None

    def post(self, url, **kwargs):
        self.post_kwargs = kwargs
        return self.response


class GradeApiClientTests(unittest.TestCase):
    def test_fetch_grades_sets_grade_referer_before_posting(self):
        session = FakeSession(FakeResponse(payload={"rows": [{"kcmc": "高数", "zcj": "88"}]}))

        grades = GradeApiClient(session).fetch_grades()

        self.assertEqual(
            session.headers["Referer"],
            "https://jxfw.gdut.edu.cn/xskccjxx!xskccjxx.action",
        )
        self.assertEqual(grades[0]["course_name"], "高数")

    def test_fetch_grades_raises_friendly_error_for_html_error_page(self):
        session = FakeSession(
            FakeResponse(
                text="<html><title>非法访问</title><body>你没有该权限</body></html>",
                json_error=ValueError("not json"),
            )
        )

        with self.assertRaises(GradeResponseError) as ctx:
            GradeApiClient(session).fetch_grades()

        self.assertIn("非法访问", str(ctx.exception))
        self.assertNotIn("Traceback", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
