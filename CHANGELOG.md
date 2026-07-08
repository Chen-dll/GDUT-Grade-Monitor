# Changelog

## 0.2.8 - 2026-07-08

### Added

- Added a course detail dialog from the grade table so users can inspect normalized fields and original grade payload fields without leaving the GUI.
- Added setup/re-login progress hints during one-click setup so long browser/login steps no longer feel frozen.

### Changed

- Removed the dashboard first-run guide card from the main overview because it duplicated the first-launch wizard and made the page feel crowded after setup.
- Expanded the runtime status center tiles so status values remain readable instead of collapsing into thin placeholder lines.
- Reduced duplicate dashboard information by showing only the three key runtime cards, simplifying local configuration metrics, and keeping only the most common quick actions on the overview.
- Made scroll-heavy areas, including the first-run wizard, About page, and recent changes card, easier to read when content grows.

### Fixed

- Login now falls back across the managed profile, a temporary login profile, bundled Playwright Chromium, and detected Chrome/Edge installations before reporting browser startup failure.
- Browser startup failures now show a concise Chinese recovery message instead of raw Playwright logs.

## 0.2.7 - 2026-07-08

### Added

- Added a dashboard runtime status center showing background state, last check, next check, login setup, autostart, and recent errors.
- Added tray and dashboard actions to pause background reminders for one hour, resume background checks, and open monitor logs.

### Changed

- The background monitor now records heartbeat/error status while paused or after failed checks, making runtime state easier to diagnose.
- Successful grade checks now clear stale previous errors so the UI does not keep showing fixed problems.
- Expired pause timestamps are ignored in the status center instead of incorrectly showing "paused".

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
