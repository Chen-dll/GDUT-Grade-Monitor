from __future__ import annotations

from typing import Any

from .constants import DEFAULT_BASE_URL, GRADE_PATH
from .grades import normalize_grades
from .readonly import ReadonlyHttpClient

GRADE_REFERER_PATH = "/xskccjxx!xskccjxx.action"


class GradeResponseError(RuntimeError):
    def __init__(self, response):
        text = getattr(response, "text", "") or ""
        preview = " ".join(text.strip().split())[:300]
        self.status_code = getattr(response, "status_code", None)
        self.url = getattr(response, "url", "")
        self.snippet = preview
        super().__init__(f"成绩接口没有返回 JSON，可能登录态或访问上下文失效。响应摘要: {preview}")


class GradeApiClient:
    def __init__(self, session, base_url: str = DEFAULT_BASE_URL):
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.http = ReadonlyHttpClient(session, base_url=base_url)

    def fetch_grades(self, semester: str | None = None) -> list[dict[str, Any]]:
        self.session.headers["Referer"] = f"{self.base_url}{GRADE_REFERER_PATH}"
        response = self.http.post(
            GRADE_PATH,
            data={
                "xnxqdm": semester or "",
                "page": "1",
                "rows": "200",
                "sort": "xnxqdm",
                "order": "asc",
            },
            timeout=15,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise GradeResponseError(response) from exc
        rows = payload.get("rows", []) if isinstance(payload, dict) else []
        return normalize_grades(rows)
