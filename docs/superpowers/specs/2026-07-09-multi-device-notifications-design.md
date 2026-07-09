# Multi-Device Notifications Design

## Goal

Add optional multi-device notifications for 0.3.0 while keeping the existing Windows desktop app as the only component that logs in to GDUT and queries grades.

## Scope

- The Windows app still performs all read-only grade checks.
- Remote devices only receive notification events.
- First supported remote channels: PushPlus, Server Chan, ntfy, and SMTP email.
- Notification content privacy is configurable per channel:
  - Private: only says a new/changed grade exists.
  - Summary: includes semester and course name.
  - Detailed: includes semester, course name, and score.
- Windows local notification remains enabled by default and can use detailed mode.
- Remote channels default to private mode.

## Non-Goals

- No mobile app in 0.3.0.
- No cloud account system or hosted relay.
- No phone-side GDUT login or grade querying.
- No automatic official transcript requests.

## Architecture

The monitor emits grade changes as before. `notify.py` formats a change according to a privacy mode. A new notification channel module builds channel objects from local config and secrets stored in Windows Credential Manager via keyring.

`GradeMonitor` remains unaware of PushPlus, Server Chan, ntfy, SMTP, or any third-party service. If a notifier supports `send_change(change)`, the monitor passes the raw change to it so each channel can choose its own privacy level. Existing notifiers that only implement `send(title, body)` continue to work.

Remote notification failures are isolated. A failed remote channel logs a warning but does not stop Windows notification, grade state updates, or background checking.

## Configuration

Non-secret channel options live in `config.json` under `notifications`. Secrets are not written to config:

- PushPlus token: keyring.
- Server Chan SendKey: keyring.
- ntfy bearer token: keyring, optional.
- SMTP password: keyring.

The config sanitizer recursively removes keys such as `token`, `secret`, `password`, and `cookie` if they are accidentally passed to `save_config`.

## GUI

The Settings page gets a "多设备通知" action. It opens a modal dialog with one card per channel. Each card has:

- Enable checkbox.
- Privacy mode selector.
- Channel-specific non-secret fields.
- Secret field for token/password, saved to keyring.

The dialog includes a "发送测试通知" button. The test uses the current channel configuration and privacy mode, but sends a synthetic message rather than any real grade data.

## Testing

- Message formatting for private, summary, and detailed modes.
- Config sanitizer removes nested secrets.
- PushPlus and Server Chan request payloads are correct.
- ntfy builds the expected URL, headers, and body.
- SMTP sends a text email with the configured sender and recipient.
- Multi-device notifier catches remote failures and keeps sending other channels.
- GUI contains the multi-device settings entry and supported channel labels.
