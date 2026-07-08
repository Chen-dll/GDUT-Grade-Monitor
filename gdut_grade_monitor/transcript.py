from __future__ import annotations

from datetime import date
from html import escape
from math import isfinite
from pathlib import Path
from typing import Any

from .constants import APP_NAME
from .gui_model import grade_analytics


TRANSCRIPT_NOTICE = "本成绩单由本地成绩快照生成，仅供个人核对，不具备学校官方证明效力。"


def build_transcript_html(grades: list[dict[str, Any]], config: dict[str, Any], generated_at: date | None = None) -> str:
    generated_at = generated_at or date.today()
    analytics = grade_analytics(grades)
    sorted_grades = sorted(
        grades,
        key=lambda grade: (
            str(grade.get("semester", "")),
            str(grade.get("course_code", "")),
            str(grade.get("course_name", "")),
        ),
    )
    average_score = _average_score(sorted_grades)
    rows = "\n".join(_course_row(grade) for grade in sorted_grades)
    if not rows:
        rows = '<tr><td colspan="8" class="empty">暂无成绩快照</td></tr>'

    profile = _profile(config)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{_e(profile["title"])}</title>
  <style>
    @page {{ size: A4; margin: 12mm; }}
    body {{ font-family: "Microsoft YaHei UI", "Microsoft YaHei", Arial, sans-serif; color: #111827; background: #ffffff; margin: 0; }}
    .sheet {{ background: #ffffff; margin: 0 auto; padding: 10px 8px 12px; }}
    h1 {{ text-align: center; font-size: 26px; margin: 8px 0 18px; letter-spacing: 0; }}
    .meta {{ display: grid; grid-template-columns: 1fr auto; gap: 16px; align-items: end; margin-bottom: 8px; }}
    .section-title {{ font-weight: 700; margin: 12px 0 6px; }}
    table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
    tr {{ page-break-inside: avoid; }}
    th, td {{ border: 1px solid #9ca3af; padding: 5px 7px; font-size: 12px; line-height: 1.35; word-break: break-word; }}
    th {{ background: #f3f4f6; font-weight: 700; }}
    .profile th {{ width: 16%; text-align: center; }}
    .profile td {{ width: 34%; text-align: center; }}
    .courses th, .courses td {{ text-align: center; }}
    .courses td.name {{ text-align: left; }}
    .summary th {{ text-align: center; }}
    .summary td {{ text-align: left; }}
    .notice {{ margin-top: 10px; color: #dc2626; font-size: 12px; font-weight: 700; }}
    .source {{ margin-top: 4px; color: #64748b; font-size: 11px; }}
    .empty {{ color: #64748b; padding: 22px; }}
  </style>
</head>
<body>
  <main class="sheet">
    <h1>{_e(profile["title"])}</h1>
    <div class="meta">
      <div class="section-title">申请信息：</div>
      <div>生成日期：{_e(generated_at.isoformat())}</div>
    </div>
    <table class="profile">
      <tbody>
        <tr><th>学号</th><td>{_e(profile["student_id"])}</td><th>姓名</th><td>{_e(profile["name"])}</td></tr>
        <tr><th>学院</th><td>{_e(profile["college"])}</td><th>专业</th><td>{_e(profile["major"])}</td></tr>
        <tr><th>班级</th><td colspan="3">{_e(profile["class_name"])}</td></tr>
      </tbody>
    </table>

    <div class="section-title">课程信息：</div>
    <table class="courses">
      <thead>
        <tr>
          <th style="width: 12%;">学年学期</th>
          <th style="width: 12%;">课程编号</th>
          <th style="width: 24%;">课程名称</th>
          <th style="width: 14%;">课程性质</th>
          <th style="width: 9%;">成绩</th>
          <th style="width: 8%;">学分</th>
          <th style="width: 10%;">成绩绩点</th>
          <th style="width: 11%;">考试性质</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>

    <table class="summary">
      <tbody>
        <tr><th>本地记录课程</th><td>{analytics["course_count"]}</td><th>参与绩点统计课程</th><td>{analytics["numeric_gpa_count"]}</td></tr>
        <tr><th>本地记录学分</th><td>{_format_number(_credit_total(sorted_grades))}</td><th>参与绩点统计学分</th><td>{_format_number(analytics["counted_credit_total"])}</td></tr>
        <tr><th>平均绩点</th><td>{_format_optional(analytics["average_gpa"])}</td><th>平均成绩</th><td>{_format_optional(average_score)}</td></tr>
      </tbody>
    </table>
    <div class="notice">说明：{_e(TRANSCRIPT_NOTICE)}</div>
    <div class="source">数据来源：{_e(APP_NAME)} 本地成绩快照；不会提交成绩单申请或调用任何写入接口。</div>
  </main>
</body>
</html>
"""


def write_transcript_html(path: Path, grades: list[dict[str, Any]], config: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_transcript_html(grades, config), encoding="utf-8")
    return path


def _course_row(grade: dict[str, Any]) -> str:
    raw = grade.get("raw", {})
    if not isinstance(raw, dict):
        raw = {}
    return (
        "<tr>"
        f"<td>{_e(grade.get('semester', ''))}</td>"
        f"<td>{_e(grade.get('course_code', ''))}</td>"
        f'<td class="name">{_e(grade.get("course_name", ""))}</td>'
        f"<td>{_e(_first(raw, ('课程性质', 'kcxzmc', 'kcxz', 'courseNature')))}</td>"
        f"<td>{_e(grade.get('score', ''))}</td>"
        f"<td>{_e(grade.get('credit', ''))}</td>"
        f"<td>{_e(_display_grade_point(grade))}</td>"
        f"<td>{_e(_first(raw, ('考试性质', 'ksxz', 'ksxzmc', 'examNature')))}</td>"
        "</tr>"
    )


def _profile(config: dict[str, Any]) -> dict[str, str]:
    return {
        "title": str(config.get("transcript_title") or "本地成绩单"),
        "student_id": str(config.get("student_id") or ""),
        "name": str(config.get("transcript_name") or ""),
        "college": str(config.get("transcript_college") or ""),
        "major": str(config.get("transcript_major") or ""),
        "class_name": str(config.get("transcript_class") or ""),
    }


def _first(raw: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = raw.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _display_grade_point(grade: dict[str, Any]) -> str:
    explicit = str(grade.get("grade_point", "")).strip()
    if explicit:
        return explicit
    raw = grade.get("raw", {})
    if isinstance(raw, dict):
        raw_point = _first(raw, ("cjjd", "jd", "绩点", "gradePoint", "grade_point"))
        if raw_point:
            return raw_point
    point = _grade_point_from_score(grade.get("score"))
    return "" if point is None else f"{point:.1f}".rstrip("0").rstrip(".")


def _grade_point_from_score(score: Any) -> float | None:
    number = _number(score)
    if number is None:
        return None
    return max(0.0, min(5.0, (number - 50.0) / 10.0))


def _average_score(grades: list[dict[str, Any]]) -> float | None:
    scored = []
    for grade in grades:
        score = _number(grade.get("score"))
        if score is None:
            continue
        credit = _number(grade.get("credit")) or 0
        scored.append((score, credit))
    credit_total = sum(credit for _, credit in scored if credit > 0)
    if credit_total > 0:
        return sum(score * credit for score, credit in scored if credit > 0) / credit_total
    if scored:
        return sum(score for score, _ in scored) / len(scored)
    return None


def _credit_total(grades: list[dict[str, Any]]) -> float:
    return sum(_number(grade.get("credit")) or 0 for grade in grades)


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if isfinite(number) else None


def _format_optional(value: Any) -> str:
    number = _number(value)
    return "--" if number is None else _format_number(number)


def _format_number(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "--"
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _e(value: Any) -> str:
    return escape(str(value), quote=True)
