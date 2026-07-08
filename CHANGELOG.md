# Changelog

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
