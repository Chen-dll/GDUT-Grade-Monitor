from __future__ import annotations

try:
    import keyring
except ImportError:  # pragma: no cover - exercised only when dependency is absent.
    keyring = None

from .constants import KEYRING_SERVICE


class PasswordInputError(ValueError):
    pass


def validate_password_input(password: str) -> str:
    if not password:
        raise PasswordInputError("密码不能为空。请切换到英文输入法后重新输入。")
    for char in password:
        code = ord(char)
        if (
            0x4E00 <= code <= 0x9FFF
            or 0x3000 <= code <= 0x303F
            or 0xFF00 <= code <= 0xFFEF
        ):
            raise PasswordInputError(
                "密码中检测到中文或全角字符。请切换到英文输入法，重新运行 setup 输入密码。"
            )
    return password


class CredentialStore:
    def __init__(self, service_name: str = KEYRING_SERVICE):
        self.service_name = service_name

    def set_credentials(self, student_id: str, password: str) -> None:
        self._require_keyring()
        password = validate_password_input(password)
        keyring.set_password(self.service_name, student_id, password)

    def get_password(self, student_id: str) -> str | None:
        self._require_keyring()
        return keyring.get_password(self.service_name, student_id)

    def delete_password(self, student_id: str) -> None:
        self._require_keyring()
        try:
            keyring.delete_password(self.service_name, student_id)
        except Exception:
            return

    @staticmethod
    def _require_keyring() -> None:
        if keyring is None:
            raise RuntimeError("keyring is required to store credentials securely.")
