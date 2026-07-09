from pathlib import Path

APP_NAME = "GDUT Grade Monitor"
APP_VERSION = "0.3.0"
APP_AUTHOR = "Chen-Dll"
KEYRING_SERVICE = "gdut-grade-monitor"
DEFAULT_BASE_URL = "https://jxfw.gdut.edu.cn"
CAS_LOGIN_URL = (
    "https://authserver.gdut.edu.cn/authserver/login"
    "?service=https%3A%2F%2Fjxfw.gdut.edu.cn%2Fnew%2FssoLogin"
)
WELCOME_PATH = "/login!welcome.action"
GRADE_PATH = "/xskccjxx!getDataList.action"
DEFAULT_POLL_INTERVAL_MINUTES = 30
DEFAULT_DATA_DIR = Path.home() / ".gdut-grade-monitor"
TASK_NAME = "GDUT Grade Monitor"
