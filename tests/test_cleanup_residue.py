import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from gdut_grade_monitor.cleanup import cleanup_residue
from gdut_grade_monitor.task import STARTUP_SCRIPT_NAME


class CleanupResidueTests(unittest.TestCase):
    @patch("gdut_grade_monitor.cleanup.uninstall_run_key")
    @patch("gdut_grade_monitor.cleanup.run_key_exists", return_value=False)
    @patch("gdut_grade_monitor.cleanup.uninstall_task")
    def test_cleanup_residue_removes_only_this_tool_startup_file(
        self, uninstall_task_mock, run_key_exists_mock, uninstall_run_key_mock
    ):
        uninstall_task_mock.return_value = Mock(returncode=0, stdout="", stderr="")
        uninstall_run_key_mock.return_value = Mock(returncode=0)
        with tempfile.TemporaryDirectory() as tmp:
            startup = Path(tmp) / "Startup"
            startup.mkdir()
            target = startup / STARTUP_SCRIPT_NAME
            other = startup / "Other App.vbs"
            target.write_text("stale", encoding="utf-8")
            other.write_text("keep", encoding="utf-8")

            result = cleanup_residue(startup_dir=startup, remove_data=False, remove_scheduled_task=True)

            self.assertTrue(result.removed_startup)
            self.assertFalse(target.exists())
            self.assertTrue(other.exists())
            self.assertEqual(result.scheduled_task_returncode, 0)
            self.assertFalse(result.removed_run_key)
            uninstall_task_mock.assert_called_once()

    @patch("gdut_grade_monitor.cleanup.uninstall_run_key")
    @patch("gdut_grade_monitor.cleanup.run_key_exists", return_value=False)
    @patch("gdut_grade_monitor.cleanup.uninstall_task")
    def test_cleanup_residue_can_remove_local_data_when_explicitly_requested(
        self, uninstall_task_mock, run_key_exists_mock, uninstall_run_key_mock
    ):
        uninstall_task_mock.return_value = Mock(returncode=1, stdout="", stderr="not found")
        uninstall_run_key_mock.return_value = Mock(returncode=0)
        with tempfile.TemporaryDirectory() as tmp:
            startup = Path(tmp) / "Startup"
            data = Path(tmp) / "data"
            startup.mkdir()
            data.mkdir()
            (data / "state.json").write_text("{}", encoding="utf-8")

            result = cleanup_residue(startup_dir=startup, data_dir=data, remove_data=True)

            self.assertTrue(result.removed_data)
            self.assertFalse(data.exists())
            self.assertEqual(result.scheduled_task_returncode, 1)

    @patch("gdut_grade_monitor.cleanup.uninstall_run_key")
    @patch("gdut_grade_monitor.cleanup.run_key_exists", return_value=True)
    @patch("gdut_grade_monitor.cleanup.uninstall_task")
    def test_cleanup_residue_removes_run_key_fallback(self, uninstall_task_mock, run_key_exists_mock, uninstall_run_key_mock):
        uninstall_task_mock.return_value = Mock(returncode=1, stdout="", stderr="not found")
        uninstall_run_key_mock.return_value = Mock(returncode=0)
        with tempfile.TemporaryDirectory() as tmp:
            startup = Path(tmp) / "Startup"
            startup.mkdir()

            result = cleanup_residue(startup_dir=startup, remove_scheduled_task=True)

            self.assertTrue(result.removed_run_key)
            uninstall_run_key_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
