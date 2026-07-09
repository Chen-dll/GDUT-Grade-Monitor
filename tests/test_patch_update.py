import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from gdut_grade_monitor.patch_update import (
    PatchApplyPlan,
    PatchManifestError,
    build_patch_apply_plan,
    safe_patch_files,
    verify_patch_archive,
)
from gdut_grade_monitor.update_check import PatchUpdate


class PatchUpdateTests(unittest.TestCase):
    def test_verify_patch_archive_accepts_matching_manifest_and_hash(self):
        with TemporaryDirectory() as tmp:
            archive = Path(tmp) / "patch.zip"
            archive.write_bytes(b"patch bytes")
            manifest = {
                "schema": 1,
                "from_version": "v0.3.1",
                "to_version": "v0.3.2",
                "archive_sha256": hashlib.sha256(b"patch bytes").hexdigest(),
                "files": ["GDUTGradeMonitor.exe", "_internal/gdut_grade_monitor/gui_model.pyc"],
            }

            result = verify_patch_archive(archive, manifest, current_version="0.3.1", target_version="v0.3.2")

            self.assertEqual(result, archive)

    def test_verify_patch_archive_rejects_wrong_hash_or_version(self):
        with TemporaryDirectory() as tmp:
            archive = Path(tmp) / "patch.zip"
            archive.write_bytes(b"patch bytes")
            manifest = {
                "schema": 1,
                "from_version": "v0.3.0",
                "to_version": "v0.3.2",
                "archive_sha256": "0" * 64,
                "files": ["GDUTGradeMonitor.exe"],
            }

            with self.assertRaises(PatchManifestError):
                verify_patch_archive(archive, manifest, current_version="0.3.1", target_version="v0.3.2")

    def test_safe_patch_files_rejects_absolute_or_parent_paths(self):
        with self.assertRaises(PatchManifestError):
            safe_patch_files(["GDUTGradeMonitor.exe", "../config.json"])

        with self.assertRaises(PatchManifestError):
            safe_patch_files(["C:/Windows/System32/calc.exe"])

    def test_build_patch_apply_plan_writes_manifest_and_uses_helper_script(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "patch.zip"
            archive.write_bytes(b"patch")
            manifest = {"schema": 1, "files": ["GDUTGradeMonitor.exe"]}
            patch = PatchUpdate(
                from_version="v0.3.1",
                to_version="v0.3.2",
                manifest_name="patch.json",
                manifest_url="https://example.invalid/patch.json",
                archive_name="patch.zip",
                archive_url="https://example.invalid/patch.zip",
                archive_size=5,
            )

            plan = build_patch_apply_plan(
                patch=patch,
                archive_path=archive,
                manifest=manifest,
                data_dir=root / "data",
                install_dir=root / "app",
                current_pid=1234,
                executable_path=root / "app" / "GDUTGradeMonitor.exe",
            )

            self.assertIsInstance(plan, PatchApplyPlan)
            self.assertTrue(plan.manifest_path.exists())
            self.assertEqual(json.loads(plan.manifest_path.read_text(encoding="utf-8"))["files"], ["GDUTGradeMonitor.exe"])
            self.assertIn("apply_patch_update.ps1", str(plan.command))
            self.assertIn("-WaitPid", plan.command)
            self.assertIn("1234", plan.command)


if __name__ == "__main__":
    unittest.main()
