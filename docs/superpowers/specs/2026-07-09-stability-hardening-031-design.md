# Stability Hardening 0.3.1 Design

## Goal

Make GDUT Grade Monitor more dependable on other people's Windows computers before adding larger new product features. Version 0.3.1 should make background failures visible, separate grade-query success from notification-channel failure, and provide safer recovery paths when startup entries or login sessions break.

The app must keep the existing read-only boundary: only local Windows runs the monitor, only allowed GDUT grade endpoints are queried, and no school data is modified.

## Scope

- Classify monitor failures into user-readable categories.
- Persist enough runtime health in `state.json` for the GUI, diagnostics, and support.
- Keep grade snapshot updates working even if one notification channel fails.
- Detect broken autostart targets for Startup `.vbs` and HKCU Run key entries.
- Offer one clear repair path for broken autostart from the GUI and CLI.
- Improve diagnostics without exposing passwords, cookies, notification secrets, or full grade rows.

## Non-Goals

- No new notification providers.
- No mobile app or cloud relay.
- No automatic official transcript application.
- No broad UI redesign.
- No change to the grade-query allowlist.
- No automatic deletion of local data or Windows credentials.

## Failure Classification

Add a small error classification layer, for example `runtime_health.py` or a focused section in `errors.py`, with stable error kinds:

- `login_expired`: CAS/login page, session timeout, or HTML login response from the grade endpoint.
- `network`: request timeout, DNS failure, connection error, proxy/TLS failure.
- `school_system`: school server returns non-JSON, malformed JSON, 5xx, or unexpected payload that is not clearly a login page.
- `browser_missing`: Playwright/Chromium/system browser missing during login.
- `notification_failed`: at least one notification channel failed after grades were fetched.
- `autostart_broken`: configured startup target points to a missing executable.
- `unknown`: anything not confidently mapped.

Each classification returns:

- `kind`: stable machine-readable string.
- `summary`: short Chinese status text.
- `action`: short Chinese next step.
- `severity`: `info`, `warning`, or `error`.

This keeps the GUI from showing raw tracebacks while diagnostics can still include sanitized technical details.

## Monitor Runtime State

Extend `state.json` under `monitor`:

- `heartbeat_at`: updated whenever the background loop wakes.
- `last_check_at`: updated only after a grade check attempt starts.
- `last_success_at`: updated after grades are fetched and state is saved.
- `last_failure_at`: updated after a monitor-level failure.
- `consecutive_failures`: increments on monitor-level failures, resets to `0` after a successful grade fetch.
- `last_error_kind`: stable kind from failure classification.
- `last_error_summary`: user-readable summary.
- `last_error_action`: suggested next step.
- `last_notification_failure_at`: updated when one or more notification channels fail but grade fetch succeeds.

Existing keys such as `last_error` remain for backward compatibility but should be treated as legacy display text. New UI surfaces prefer the structured fields.

## Notification Failure Isolation

The monitor should treat grade fetching and notification delivery as separate stages:

1. Fetch grades.
2. Diff and save the new snapshot.
3. Attempt notifications.
4. Record per-channel delivery results in history.
5. If notifications fail, record `notification_failed` state but do not roll back the grade snapshot.

This prevents one broken remote channel from making the user repeatedly receive or reprocess the same grade change. If all grade logic succeeded and only notification delivery failed, the main check status should remain "grades updated, notification issue" rather than a full monitor failure.

## Autostart Health

Add helper functions in `task.py` for current-user startup health:

- Read Startup `.vbs` target if present.
- Read HKCU Run key target if present.
- Detect whether each target exists.
- Return a small structured report with mode, target path, exists flag, and issue message.

`doctor` should include an optional warning if:

- Startup `.vbs` points to a missing exe.
- HKCU Run key points to a missing exe.
- Config says startup is enabled but no startup entry is detected.

The GUI settings/status area should show "启动项路径失效，可一键修复" and expose the existing install action as the repair. Repair should use the same fallback order already implemented:

1. Task Scheduler.
2. Startup folder.
3. HKCU Run key.

## GUI Changes

Keep visual changes small:

- Status center shows structured runtime health:
  - normal
  - paused
  - notification issue
  - login expired
  - network issue
  - school system issue
  - autostart broken
- Recent error row uses `last_error_summary` and `last_error_action`.
- Environment page includes startup target details and one clear "修复自启动" action through the existing settings action.
- When consecutive failures reach 3, show a stronger warning: "连续 3 次检查失败，建议重新登录或导出诊断包。"

No new page is required for 0.3.1.

## Diagnostics

Diagnostics should include a sanitized `runtime-health.json` or extend the existing support summary with:

- app version
- last success/failure timestamps
- consecutive failure count
- last error kind/summary/action
- startup health summary
- notification channel enabled/disabled and last delivery status

It must not include:

- password
- cookies
- notification tokens
- SendKey
- SMTP authorization code
- full grade rows
- unmasked student ID

## Data Compatibility

Existing users may already have `state.json` without the new fields. All reads must tolerate missing keys. On the next check or background loop heartbeat, the new monitor fields are added gradually.

The feature does not require migration scripts.

## Testing

Add or extend tests for:

- Error classification for login expired, network, school system, browser missing, notification failure, and unknown errors.
- Monitor increments `consecutive_failures` on failures and resets it after success.
- Successful grade fetch with notification failure updates the grade snapshot and records notification failure without treating the whole check as failed.
- Startup health detects missing Startup `.vbs` targets.
- Startup health detects missing HKCU Run key targets using mocks.
- Doctor reports broken startup target as a non-required warning.
- Diagnostics include runtime health but redact secrets and full grade data.
- GUI model renders clear status rows for consecutive failures, notification issues, and broken startup.

## Release Criteria

- `python -m unittest discover -s tests -v` passes locally.
- `python -m compileall gdut_grade_monitor tests packaging docs scripts` passes.
- `git diff --check` passes.
- GitHub Actions tests pass for Python 3.10, 3.11, and 3.12.
- Manual smoke: `python -m gdut_grade_monitor doctor`, `python -m gdut_grade_monitor monitor --once`, and packaged GUI launch still work on the development Windows machine.
