from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any

from .storage import AppPaths, load_state, save_state


def apply_manual_scores(grades: list[dict[str, Any]], manual_scores: dict[str, Any] | None) -> list[dict[str, Any]]:
    manual_scores = manual_scores if isinstance(manual_scores, dict) else {}
    positive_course_keys = _positive_course_keys(grades)
    applied = []
    for grade in grades:
        row = dict(grade)
        identity = str(row.get("identity") or _grade_identity(row))
        official_score = str(row.get("score", "") or "").strip()
        manual = manual_scores.get(identity)
        manual_score = _manual_score_value(manual)
        if manual_score and manual_score_allowed(row, grades, positive_course_keys=positive_course_keys):
            row["official_score"] = official_score
            row["official_grade_point"] = str(row.get("grade_point", "") or "").strip()
            row["manual_score"] = manual_score
            row["score"] = manual_score
            point = _score_to_grade_point(manual_score)
            if point is not None:
                row["grade_point"] = _format_number(point, places=1)
            row["score_source"] = "manual"
        else:
            row["score_source"] = "official"
            if manual_score:
                row["manual_score"] = manual_score
        applied.append(row)
    return applied


def set_manual_score(paths: AppPaths, identity: str, score: str) -> None:
    normalized = _validate_manual_score(score)
    state = load_state(paths)
    manual_scores = state.get("manual_scores")
    if not isinstance(manual_scores, dict):
        manual_scores = {}
    manual_scores[str(identity)] = {
        "score": normalized,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    state["manual_scores"] = manual_scores
    save_state(paths, state)


def delete_manual_score(paths: AppPaths, identity: str) -> None:
    state = load_state(paths)
    manual_scores = state.get("manual_scores")
    if isinstance(manual_scores, dict):
        manual_scores.pop(str(identity), None)
        state["manual_scores"] = manual_scores
        save_state(paths, state)


def manual_score_allowed(
    grade: dict[str, Any],
    all_grades: list[dict[str, Any]] | None = None,
    *,
    positive_course_keys: set[tuple[str, str, str]] | None = None,
) -> bool:
    official_score = str(grade.get("official_score", grade.get("score", "")) or "").strip()
    if official_score and not _is_zero_score(official_score):
        return False
    keys = positive_course_keys
    if keys is None and all_grades is not None:
        keys = _positive_course_keys(all_grades)
    return _course_key(grade) not in (keys or set())


def _manual_score_value(value: Any) -> str:
    if isinstance(value, dict):
        try:
            return _validate_manual_score(str(value.get("score", "") or ""))
        except ValueError:
            return ""
    return ""


def _validate_manual_score(score: str) -> str:
    text = str(score or "").strip()
    try:
        number = float(text)
    except ValueError as exc:
        raise ValueError("手动成绩必须是 0 到 100 之间的数字。") from exc
    if not isfinite(number) or number < 0 or number > 100:
        raise ValueError("手动成绩必须是 0 到 100 之间的数字。")
    return str(int(number)) if number.is_integer() else f"{number:g}"


def _is_positive_score(score: str) -> bool:
    try:
        return float(str(score).strip()) > 0
    except ValueError:
        return False


def _is_zero_score(score: str) -> bool:
    try:
        return float(str(score).strip()) == 0
    except ValueError:
        return False


def _positive_course_keys(grades: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    return {_course_key(grade) for grade in grades if _is_positive_score(str(grade.get("score", "") or ""))}


def _course_key(grade: dict[str, Any]) -> tuple[str, str, str]:
    semester = str(grade.get("semester", "") or "").strip()
    name = str(grade.get("course_name", "") or "").strip()
    credit = str(grade.get("credit", "") or "").strip()
    if name:
        return (semester, name, credit)
    return (semester, str(grade.get("course_code", "") or "").strip(), credit)


def _score_to_grade_point(score: str) -> float | None:
    try:
        number = float(str(score).strip())
    except ValueError:
        return None
    if not isfinite(number):
        return None
    return max(0.0, min(5.0, (number - 50.0) / 10.0))


def _format_number(number: float, *, places: int) -> str:
    return f"{number:.{places}f}".rstrip("0").rstrip(".")


def _grade_identity(grade: dict[str, Any]) -> str:
    return "|".join(
        [
            str(grade.get("semester", "")),
            str(grade.get("course_code", "")),
            str(grade.get("course_name", "")),
        ]
    )
