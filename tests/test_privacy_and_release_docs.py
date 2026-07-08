import unittest
from pathlib import Path


class PrivacyAndReleaseDocsTests(unittest.TestCase):
    def test_privacy_doc_explains_local_storage_and_deletion(self):
        text = Path("PRIVACY.md").read_text(encoding="utf-8")

        self.assertIn("Windows 凭据管理器", text)
        self.assertIn("%USERPROFILE%\\.gdut-grade-monitor", text)
        self.assertIn("cookies.json", text)
        self.assertIn("state.json", text)
        self.assertIn("诊断包", text)
        self.assertIn("不会上传", text)
        self.assertIn("删除本地数据", text)

    def test_readme_mentions_privacy_doc_update_check_and_checksums(self):
        text = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("PRIVACY.md", text)
        self.assertIn("检查更新", text)
        self.assertIn("SHA256SUMS.txt", text)

    def test_packaging_includes_privacy_doc_and_checksum_generation(self):
        installer = Path("packaging/installer/GDUTGradeMonitor.iss").read_text(encoding="utf-8")
        build_installer = Path("scripts/build_installer.ps1").read_text(encoding="utf-8")
        checksum_script = Path("scripts/write_checksums.ps1").read_text(encoding="utf-8")

        self.assertIn('Source: "{#SourceRoot}\\dist\\GDUTGradeMonitor\\*"', installer)
        self.assertIn("scripts\\write_checksums.ps1", build_installer)
        self.assertIn("SHA256SUMS.txt", build_installer)
        self.assertIn("Get-FileHash", checksum_script)
        self.assertIn("GDUTGradeMonitor-Setup.exe", checksum_script)
        self.assertIn("GDUTGradeMonitor-portable.zip", checksum_script)

    def test_portable_build_includes_user_docs(self):
        text = Path("scripts/build_exe.ps1").read_text(encoding="utf-8")

        self.assertIn('Copy-Item -LiteralPath "README.md"', text)
        self.assertIn('Copy-Item -LiteralPath "PRIVACY.md"', text)
        self.assertIn('Copy-Item -LiteralPath "LICENSE"', text)


if __name__ == "__main__":
    unittest.main()
