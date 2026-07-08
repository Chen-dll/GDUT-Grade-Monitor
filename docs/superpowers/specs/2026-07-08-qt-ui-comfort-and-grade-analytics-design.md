# Qt UI Comfort And Grade Analytics Design

## Goal

Polish the Windows desktop GUI for GDUT Grade Monitor 0.2.0 so it feels like a complete, friendly application rather than a terminal wrapper. The app keeps its strict read-only boundary: charts and summaries are computed only from the local grade snapshot already fetched through the allowed grade endpoint.

## Visual Direction

Use the selected "assistant home" direction:

- A wider left sidebar, around 240-252 px, with product identity, version, navigation, and a short read-only safety note.
- A dashboard that answers three questions immediately: whether monitoring is healthy, when grades were last checked, and what the user can do next.
- Clear primary and secondary button hierarchy. "立即检查" remains the primary action; diagnostics, startup, and data-directory actions use calmer secondary styling.
- Calm light content surface, dark sidebar, restrained blue accent, rounded but not playful panels.

## Dashboard

The dashboard contains:

- Header: "后台正在守着成绩" plus current read-only monitoring summary.
- Dark status panel: current state, last check time, latest change count, and next-check/frequency context.
- Recent changes panel: latest notification history items if available; otherwise a friendly empty state.
- Local configuration panel: grade count, autostart state, polling interval, and read-only boundary.
- Quick actions: one-click setup, immediate check, install autostart, export diagnostics.

## Grade Analytics

The grade page becomes a compact analysis workspace:

- Summary metrics: average GPA, counted course count, highest score.
- Trend chart: weighted GPA by semester, shown as a simple line chart.
- Distribution chart: GPA buckets 4-5, 3-4, 2-3, 0-2.
- Filters: semester selector, include/exclude elective-like courses, course search.
- Course table: semester, course, score, credit, GPA.

Charts are built with Qt widgets/painting or simple labels without adding a new dependency.

## Data Model

Add a small analytics model in `gui_model.py`:

- Parse numeric score, credit, and grade point safely.
- Compute weighted GPA using credit where available; fall back to unweighted averages when credit is missing.
- Group GPA by semester.
- Bucket GPA distribution.
- Filter grade rows by semester, search text, and elective inclusion.

Missing or non-numeric grades are ignored in numeric statistics but still appear in the course table.

## Verification

- Unit tests cover GPA parsing, average GPA, semester trend, bucket distribution, and filtering.
- Existing tests for read-only client and password safety must remain passing.
- GUI smoke test opens the Qt window and confirms it presents the 0.2.0 title.
