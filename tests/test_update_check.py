import unittest

from gdut_grade_monitor.update_check import (
    GitHubRelease,
    PatchUpdate,
    UpdateCheckError,
    check_latest_release,
    is_newer_version,
    parse_version,
)


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self.payload = payload or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class FakeRequests:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers, timeout))
        if self.exc:
            raise self.exc
        return self.response


class UpdateCheckTests(unittest.TestCase):
    def test_parse_version_ignores_v_prefix_and_prerelease_suffix(self):
        self.assertEqual(parse_version("v0.2.3"), (0, 2, 3))
        self.assertEqual(parse_version("0.10.0-beta.1"), (0, 10, 0))

    def test_version_compare_detects_newer_release(self):
        self.assertTrue(is_newer_version("0.2.3", "0.2.2"))
        self.assertFalse(is_newer_version("0.2.2", "0.2.2"))
        self.assertFalse(is_newer_version("0.2.1", "0.2.2"))

    def test_check_latest_release_parses_github_payload(self):
        fake = FakeRequests(
            FakeResponse(
                {
                    "tag_name": "v0.2.3",
                    "name": "GDUT 成绩提醒 v0.2.3",
                    "html_url": "https://github.com/Chen-Dll/GDUT-Grade-Monitor/releases/tag/v0.2.3",
                    "body": "release notes",
                }
            )
        )

        result = check_latest_release(current_version="0.2.2", requests_module=fake)

        self.assertEqual(
            result,
            GitHubRelease(
                tag_name="v0.2.3",
                name="GDUT 成绩提醒 v0.2.3",
                url="https://github.com/Chen-Dll/GDUT-Grade-Monitor/releases/tag/v0.2.3",
                body="release notes",
                is_newer=True,
            ),
        )
        self.assertIn("/repos/Chen-Dll/GDUT-Grade-Monitor/releases/latest", fake.calls[0][0])
        self.assertEqual(fake.calls[0][2], 8)

    def test_check_latest_release_detects_matching_patch_assets(self):
        fake = FakeRequests(
            FakeResponse(
                {
                    "tag_name": "v0.3.2",
                    "name": "GDUT 成绩提醒 v0.3.2",
                    "html_url": "https://github.com/Chen-Dll/GDUT-Grade-Monitor/releases/tag/v0.3.2",
                    "assets": [
                        {
                            "name": "GDUTGradeMonitor-patch-v0.3.1-to-v0.3.2.json",
                            "browser_download_url": "https://example.invalid/patch.json",
                            "size": 512,
                        },
                        {
                            "name": "GDUTGradeMonitor-patch-v0.3.1-to-v0.3.2.zip",
                            "browser_download_url": "https://example.invalid/patch.zip",
                            "size": 4096,
                        },
                    ],
                }
            )
        )

        result = check_latest_release(current_version="0.3.1", requests_module=fake)

        self.assertEqual(
            result.patch_update,
            PatchUpdate(
                from_version="v0.3.1",
                to_version="v0.3.2",
                manifest_name="GDUTGradeMonitor-patch-v0.3.1-to-v0.3.2.json",
                manifest_url="https://example.invalid/patch.json",
                archive_name="GDUTGradeMonitor-patch-v0.3.1-to-v0.3.2.zip",
                archive_url="https://example.invalid/patch.zip",
                archive_size=4096,
            ),
        )

    def test_check_latest_release_ignores_patch_for_other_source_version(self):
        fake = FakeRequests(
            FakeResponse(
                {
                    "tag_name": "v0.3.2",
                    "assets": [
                        {
                            "name": "GDUTGradeMonitor-patch-v0.3.0-to-v0.3.2.json",
                            "browser_download_url": "https://example.invalid/patch.json",
                        },
                        {
                            "name": "GDUTGradeMonitor-patch-v0.3.0-to-v0.3.2.zip",
                            "browser_download_url": "https://example.invalid/patch.zip",
                        },
                    ],
                }
            )
        )

        result = check_latest_release(current_version="0.3.1", requests_module=fake)

        self.assertIsNone(result.patch_update)

    def test_check_latest_release_wraps_network_errors_for_gui(self):
        fake = FakeRequests(exc=OSError("network down"))

        with self.assertRaises(UpdateCheckError) as ctx:
            check_latest_release(current_version="0.2.2", requests_module=fake)

        self.assertIn("无法检查更新", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
