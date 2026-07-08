import tempfile
import unittest
from pathlib import Path

from gdut_grade_monitor.grades import normalize_grade
from gdut_grade_monitor.setup_flow import run_first_run_setup
from gdut_grade_monitor.storage import AppPaths, load_config, load_state
from gdut_grade_monitor.task import TaskInstallResult


class FakeCredentialStore:
    def __init__(self):
        self.calls = []

    def set_credentials(self, student_id, password):
        self.calls.append((student_id, password))


class FakeAuthManager:
    def __init__(self):
        self.calls = []

    def get_session(self, **kwargs):
        self.calls.append(kwargs)
        return "session"


class FakeFetcher:
    def __init__(self, rows):
        self.rows = rows

    def fetch_grades(self):
        return [normalize_grade(row) for row in self.rows]


class FakeNotifier:
    def __init__(self):
        self.sent = []

    def send(self, title, body):
        self.sent.append((title, body))


class SetupFlowTests(unittest.TestCase):
    def test_first_run_setup_saves_credentials_builds_baseline_and_installs_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))
            credentials = FakeCredentialStore()
            auth = FakeAuthManager()
            notifier = FakeNotifier()
            installed = []

            result = run_first_run_setup(
                paths=paths,
                student_id="3210000000",
                password="secret123",
                interval_minutes=12,
                credential_store=credentials,
                auth_manager=auth,
                fetcher_factory=lambda session: FakeFetcher(
                    [{"xnxqdm": "202502", "kcbh": "CS101", "kcmc": "数据结构", "zcj": "95"}]
                ),
                notifier=notifier,
                startup_installer=lambda: installed.append(True)
                or TaskInstallResult(mode="startup", returncode=0),
            )

            config = load_config(paths)
            state = load_state(paths)

            self.assertEqual(credentials.calls, [("3210000000", "secret123")])
            self.assertEqual(auth.calls[0]["student_id"], "3210000000")
            self.assertEqual(config["student_id"], "3210000000")
            self.assertEqual(config["poll_interval_minutes"], 12)
            self.assertTrue(config["startup_enabled"])
            self.assertEqual(result.grade_count, 1)
            self.assertEqual(result.change_count, 0)
            self.assertEqual(result.startup_mode, "startup")
            self.assertTrue(installed)
            self.assertEqual(notifier.sent, [])
            self.assertIn("202502|CS101|数据结构", state["grades"])

    def test_first_run_setup_can_skip_autostart_for_manual_testing(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = AppPaths(Path(tmp))

            result = run_first_run_setup(
                paths=paths,
                student_id="3210000000",
                password="secret123",
                interval_minutes=30,
                credential_store=FakeCredentialStore(),
                auth_manager=FakeAuthManager(),
                fetcher_factory=lambda session: FakeFetcher([]),
                notifier=FakeNotifier(),
                install_autostart=False,
                startup_installer=lambda: self.fail("startup installer should not run"),
            )

            self.assertEqual(result.startup_mode, "skipped")
            self.assertFalse(load_config(paths)["startup_enabled"])


if __name__ == "__main__":
    unittest.main()
