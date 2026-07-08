from __future__ import annotations

from typing import Any


FIELD_ALIASES = {
    "semester": ("xnxqdm", "xnxqmc", "学期", "学年学期"),
    "course_code": ("kcbh", "kcdm", "课程代码", "课程编号"),
    "course_name": ("kcmc", "课程名称", "name"),
    "score": ("zcj", "cj", "成绩", "score"),
    "credit": ("xf", "学分", "credit"),
    "grade_point": ("cjjd", "jd", "绩点", "gradePoint", "grade_point"),
}


def normalize_grade(raw: dict[str, Any]) -> dict[str, Any]:
    grade = {
        "semester": _first(raw, FIELD_ALIASES["semester"]),
        "course_code": _first(raw, FIELD_ALIASES["course_code"]),
        "course_name": _first(raw, FIELD_ALIASES["course_name"]),
        "score": _first(raw, FIELD_ALIASES["score"]),
        "credit": _first(raw, FIELD_ALIASES["credit"]),
        "grade_point": _first(raw, FIELD_ALIASES["grade_point"]),
        "raw": raw,
    }
    grade["identity"] = "|".join([grade["semester"], grade["course_code"], grade["course_name"]])
    return grade


def normalize_grades(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_grade(row) for row in rows]


def diff_grades(
    previous_snapshot: dict[str, dict[str, Any]] | None,
    current_grades: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    snapshot = {grade["identity"]: grade for grade in current_grades}
    if previous_snapshot is None:
        return [], snapshot

    changes: list[dict[str, Any]] = []
    for identity, grade in snapshot.items():
        previous = previous_snapshot.get(identity)
        if previous is None:
            changes.append({"kind": "new", "grade": grade})
            continue
        old_score = str(previous.get("score", ""))
        new_score = str(grade.get("score", ""))
        if old_score != new_score:
            changes.append({"kind": "changed", "grade": grade, "old_score": old_score})
    return changes, snapshot


def _first(raw: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = raw.get(key)
        if value is not None:
            return str(value).strip()
    return ""
