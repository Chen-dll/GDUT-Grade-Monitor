# Changelog

## 0.2.6 - 2026-07-08

### Fixed

- Shortened the first-run wizard sidebar step labels so the active step no longer wraps awkwardly.

## 0.2.5 - 2026-07-08

### Added

- Added a first-launch onboarding wizard that opens automatically on a new computer before setup.
- Added a step-by-step wizard rail covering purpose, privacy, read-only boundaries, main pages, baseline behavior, and one-click setup.
- Added manual "新手向导" entry points from the dashboard and Help page for users who want to review the setup flow again.

### Changed

- First-run guidance now feels more like a mature desktop app setup flow: users can click through pages and start one-click setup from the final step.
- The wizard is shown only before the app has an account, local grade baseline, or a saved "seen" flag.

## 0.2.4 - 2026-07-08

### Changed

- Improved the first-run guide with clearer wording for one-click setup, local-only password storage, baseline behavior, and the default 30-minute check interval.
- After one-click setup completes, the GUI now returns to the dashboard and confirms that background reminders are ready.

## 0.2.3 - 2026-07-08

### Added

- Added GUI update checking against the latest GitHub Release.
- Added release checksum generation for `SHA256SUMS.txt`.
- Added `PRIVACY.md` documenting local storage, diagnostics redaction, and cleanup steps.

### Changed

- GUI background errors now map common failures to friendlier recovery guidance.
- Installer packages `PRIVACY.md` with the application files.

## 0.2.2 - 2026-07-08

### Fixed

- The installer now validates the selected install path before installation and creates a missing target directory when the path is valid.
- Packaged exe builds now include `win32timezone`, fixing startup failures from pywin32 dynamic imports.

## 0.2.1 - 2026-07-08

### Added

- Login automation now tries to select the CAS "7 days / keep me signed in" checkbox before submitting credentials.
- The official transcript button now first opens the school service hall with this tool's managed login browser profile, then falls back to the system default browser if needed.

### Security

- The official transcript entry remains manual-only and does not submit forms or call write APIs.

## 0.2.0 - 2026-07-08

### Added

- Qt/PySide6 modern desktop interface as the default GUI.
- One-click local setup from the GUI: credential entry, login, baseline creation, and autostart setup.
- Dashboard guidance card and full in-app Help page for first-time users.
- Local grade analytics: GPA summary, semester trend, distribution, filtering, and search.
- Local transcript export to PDF/HTML from the local grade snapshot.
- Manual-only official transcript portal entry for the school service hall.
- Windows installer built with Inno Setup, plus portable zip distribution.
- Single-instance protection so repeated launches focus the existing window.
- Diagnostics export with sensitive information redaction.

### Changed

- Author metadata is `Chen-Dll`.
- Password validation blocks CJK/full-width input before saving credentials.
- PDF transcript export now paginates long transcripts instead of shrinking them onto one page.
- GUI window opens centered within the current screen's available area.

### Security

- Direct education-system data requests remain restricted to the read-only allowlist:
  - `GET /login!welcome.action`
  - `POST /xskccjxx!getDataList.action`
- Passwords are stored through Windows Credential Manager via `keyring`.
- Cookies, state, and logs stay under `%USERPROFILE%\.gdut-grade-monitor`.
