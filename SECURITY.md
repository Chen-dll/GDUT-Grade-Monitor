# Security Notes

This tool is designed as a read-only grade monitor.

## Sensitive Data

- Passwords are stored through `keyring`, which uses Windows Credential Manager on Windows.
- Passwords are not written to `config.json`, logs, tests, or README examples.
- Cookies and runtime state are stored under `%USERPROFILE%\.gdut-grade-monitor`.

## Read-only Boundary

All direct教务数据 requests pass through an allowlist. The application should not add write endpoints unless the project scope changes explicitly.

Allowed data endpoints:

- `GET /login!welcome.action`
- `POST /xskccjxx!getDataList.action`

## Reporting Issues

If you find a path that can modify教务系统 data, treat it as a security issue and remove or block it before release.
