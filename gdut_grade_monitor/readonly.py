from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

from .constants import GRADE_PATH, WELCOME_PATH


class ReadonlyViolation(RuntimeError):
    """Raised when code attempts a non-allowlisted教务 request."""


@dataclass(frozen=True)
class AllowedRequest:
    method: str
    path: str


class ReadonlyHttpClient:
    """Small HTTP wrapper that refuses every non-read-only教务 data request."""

    ALLOWED = {
        AllowedRequest("GET", WELCOME_PATH),
        AllowedRequest("POST", GRADE_PATH),
    }

    def __init__(self, session, base_url: str):
        self.session = session
        self.base_url = base_url.rstrip("/")

    def get(self, path: str, **kwargs):
        self._assert_allowed("GET", path)
        return self.session.get(self._url(path), **kwargs)

    def post(self, path: str, **kwargs):
        self._assert_allowed("POST", path)
        return self.session.post(self._url(path), **kwargs)

    def _assert_allowed(self, method: str, path: str) -> None:
        normalized = self._path(path)
        request = AllowedRequest(method.upper(), normalized)
        if request not in self.ALLOWED:
            raise ReadonlyViolation(f"Blocked non-read-only request: {method.upper()} {normalized}")

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return urljoin(f"{self.base_url}/", path.lstrip("/"))

    @staticmethod
    def _path(path: str) -> str:
        parsed = urlparse(path)
        candidate = parsed.path if parsed.scheme else path.split("?", 1)[0]
        if not candidate.startswith("/"):
            candidate = f"/{candidate}"
        return candidate
