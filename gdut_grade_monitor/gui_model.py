from __future__ import annotations

from collections import defaultdict
from math import isfinite

from .constants import APP_AUTHOR, APP_VERSION, GRADE_PATH, WELCOME_PATH
from .doctor import CheckResult


def status_summary(startup_installed: bool, state: dict) -> str:
    startup = "已安装" if startup_installed else "未安装"
    status_labels = {"ok": "正常"}
    raw_status = state.get("last_check_status") or "尚未检查"
    last_status = status_labels.get(raw_status, raw_status)
    change_count = state.get("last_change_count", 0)
    return f"自启动: {startup}    检查状态: {last_status}    变化: {change_count}"


def grade_table_rows(grades: list[dict]) -> list[tuple[str, str, str, str, str]]:
    rows = [
        (
            str(grade.get("semester", "")),
            str(grade.get("course_name", "")),
            str(grade.get("score", "")),
            str(grade.get("credit", "")),
            _display_grade_point(grade),
        )
        for grade in grades
    ]
    return sorted(rows, key=lambda row: (row[0], row[1]), reverse=True)


def grade_analytics(grades: list[dict]) -> dict:
    numeric = []
    uncounted = 0
    for grade in grades:
        grade_point = _grade_point(grade)
        if grade_point is None:
            uncounted += 1
            continue
        credit = _number(grade.get("credit")) or 0
        numeric.append((grade, grade_point, credit))

    weighted_total = sum(point * credit for _, point, credit in numeric if credit > 0)
    credit_total = sum(credit for _, _, credit in numeric if credit > 0)
    if credit_total > 0:
        average_gpa = weighted_total / credit_total
    elif numeric:
        average_gpa = sum(point for _, point, _ in numeric) / len(numeric)
    else:
        average_gpa = None

    semester_points: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for grade, point, credit in numeric:
        semester_points[str(grade.get("semester", "未知学期") or "未知学期")].append((point, credit))
    semester_trend = []
    for semester in sorted(semester_points):
        points = semester_points[semester]
        weighted = sum(point * credit for point, credit in points if credit > 0)
        credits = sum(credit for _, credit in points if credit > 0)
        value = weighted / credits if credits > 0 else sum(point for point, _ in points) / len(points)
        semester_trend.append((semester, round(value, 3)))

    distribution = {"4-5": 0, "3-4": 0, "2-3": 0, "0-2": 0}
    for _, point, _ in numeric:
        if point >= 4:
            distribution["4-5"] += 1
        elif point >= 3:
            distribution["3-4"] += 1
        elif point >= 2:
            distribution["2-3"] += 1
        else:
            distribution["0-2"] += 1

    scored = [(grade, _number(grade.get("score"))) for grade in grades]
    scored = [(grade, score) for grade, score in scored if score is not None]
    highest = max(scored, key=lambda item: item[1], default=(None, None))
    return {
        "average_gpa": round(average_gpa, 3) if average_gpa is not None else None,
        "numeric_gpa_count": len(numeric),
        "course_count": len(grades),
        "credit_course_count": sum(1 for _, _, credit in numeric if credit > 0),
        "counted_credit_total": round(credit_total, 3),
        "uncounted_course_count": uncounted,
        "highest_score": highest[1],
        "highest_course": highest[0].get("course_name", "") if highest[0] else "",
        "semester_trend": semester_trend,
        "distribution": distribution,
    }


def filter_grades(
    grades: list[dict],
    semester: str = "全部学期",
    search_text: str = "",
    include_electives: bool = True,
) -> list[dict]:
    needle = search_text.strip().lower()
    filtered = []
    for grade in grades:
        if semester and semester != "全部学期" and str(grade.get("semester", "")) != semester:
            continue
        if needle:
            haystack = " ".join(
                [
                    str(grade.get("course_name", "")),
                    str(grade.get("course_code", "")),
                    str(grade.get("semester", "")),
                ]
            ).lower()
            if needle not in haystack:
                continue
        if not include_electives and _looks_elective(grade):
            continue
        filtered.append(grade)
    return filtered


def semester_options(grades: list[dict]) -> list[str]:
    semesters = sorted({str(grade.get("semester", "")) for grade in grades if str(grade.get("semester", "")).strip()}, reverse=True)
    return ["全部学期", *semesters]


def recent_change_rows(state: dict, limit: int = 3) -> list[tuple[str, str, str]]:
    rows = []
    for item in list(state.get("history", []))[-limit:][::-1]:
        rows.append(
            (
                str(item.get("course_name", "")),
                str(item.get("score", "")),
                str(item.get("semester", "")),
            )
        )
    return rows


def next_check_summary(state: dict) -> str:
    monitor = state.get("monitor", {})
    interval = monitor.get("poll_interval_minutes", 30)
    last_check = str(monitor.get("last_check_at", "尚未检查")).replace("T", " ")
    return f"最近检查: {last_check}    查询频率: 每 {interval} 分钟"


def _number(value) -> float | None:
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


def _grade_point(grade: dict) -> float | None:
    explicit = _number(grade.get("grade_point"))
    if explicit is not None:
        return explicit
    raw = grade.get("raw", {})
    if isinstance(raw, dict):
        for key in ("cjjd", "jd", "绩点", "gradePoint", "grade_point"):
            explicit = _number(raw.get(key))
            if explicit is not None:
                return explicit
    score = _number(grade.get("score"))
    if score is None:
        return None
    return max(0.0, min(5.0, (score - 50.0) / 10.0))


def _display_grade_point(grade: dict) -> str:
    explicit = str(grade.get("grade_point", "")).strip()
    if explicit:
        return explicit
    point = _grade_point(grade)
    if point is None:
        return ""
    return f"{point:.1f}".rstrip("0").rstrip(".")


def _looks_elective(grade: dict) -> bool:
    raw = grade.get("raw", {})
    values = [
        grade.get("course_name", ""),
        raw.get("课程性质", ""),
        raw.get("课程类别", ""),
        raw.get("kcxz", ""),
        raw.get("kclb", ""),
        raw.get("xkfs", ""),
    ]
    return any("选修" in str(value) for value in values)


def history_table_rows(state: dict) -> list[tuple[str, str, str, str, str]]:
    labels = {"new": "新成绩", "changed": "成绩变化"}
    rows = []
    for item in state.get("history", []):
        at = str(item.get("at", "")).replace("T", " ")
        rows.append(
            (
                at,
                labels.get(item.get("kind", ""), str(item.get("kind", ""))),
                str(item.get("semester", "")),
                str(item.get("course_name", "")),
                str(item.get("score", "")),
            )
        )
    return rows


def setup_guidance(startup_installed: bool, config: dict, state: dict, required_checks_ok: bool) -> dict[str, str]:
    if not required_checks_ok:
        return {
            "tone": "error",
            "title": "环境需要处理",
            "body": "有必需环境检查未通过。请先查看环境检查页，按提示处理后再配置。",
            "primary_action": "查看环境检查",
        }
    if not config.get("student_id"):
        return {
            "tone": "warning",
            "title": "需要首次配置",
            "body": "点击一键配置本机，程序会引导你输入学号和密码、登录教务系统、建立成绩基线，并安装自启动。",
            "primary_action": "一键配置本机",
        }
    if not state.get("grades"):
        return {
            "tone": "warning",
            "title": "还没有成绩基线",
            "body": "账号已保存，但还没有本地成绩快照。请点击立即检查或一键配置本机建立基线。",
            "primary_action": "立即检查",
        }
    if not startup_installed:
        return {
            "tone": "warning",
            "title": "建议开启后台提醒",
            "body": "成绩基线已建立，但还没有安装自启动。安装后每次登录 Windows 会自动后台检查。",
            "primary_action": "安装自启动",
        }

    interval = int(config.get("poll_interval_minutes", 30))
    last_check = str(state.get("monitor", {}).get("last_check_at", "尚未检查")).replace("T", " ")
    return {
        "tone": "ok",
        "title": "后台提醒已准备好",
        "body": f"当前会在 Windows 登录后后台运行，每 {interval} 分钟只读检查一次。最近检查: {last_check}",
        "primary_action": "立即检查",
    }


def onboarding_steps() -> list[dict[str, str]]:
    return [
        {
            "title": "一键配置本机",
            "body": "填写学号、密码和查询频率，程序会把密码保存到 Windows 凭据管理器。",
        },
        {
            "title": "完成浏览器登录",
            "body": "如果学校登录页要求验证码或短信，就在弹出的浏览器里手动完成。",
        },
        {
            "title": "建立成绩基线",
            "body": "首次读取只保存本地快照，不会弹出成绩变化提醒。",
        },
        {
            "title": "后台自动提醒",
            "body": "默认每 30 分钟严格只读检查一次，只有新增或变化成绩才通知。",
        },
    ]


def help_sections() -> list[dict[str, object]]:
    return [
        {
            "title": "快速开始",
            "body": "第一次在一台电脑使用时，按这几个步骤完成配置。",
            "items": [
                "点击总览页的一键配置本机，填写学号、密码和查询频率。",
                "浏览器弹出后完成学校统一身份认证；如遇验证码、短信或风控，请手动处理。",
                "配置完成后会建立成绩基线；首次运行只记录快照，不提醒。",
                "默认每 30 分钟检查一次，可以在设置页调整。",
            ],
        },
        {
            "title": "成绩提醒怎么工作",
            "body": "本工具只比较本地快照和教务系统返回的课程成绩。",
            "items": [
                "发现新课程成绩，或同一课程成绩值发生变化时，才会弹 Windows 通知。",
                "重复检查到相同成绩不会重复提醒。",
                "提醒历史只记录提醒摘要，不保存密码、Cookie 或完整个人信息。",
                "立即检查适合调试；后台提醒依赖设置页里的自启动状态。",
            ],
        },
        {
            "title": "数据与隐私",
            "body": "所有敏感数据都留在本机，且尽量放在系统提供的位置。",
            "items": [
                "密码保存在 Windows 凭据管理器，不写入配置文件、日志或诊断包。",
                "Cookie、配置、成绩快照和日志保存在用户目录 ~/.gdut-grade-monitor。",
                "导出诊断包会隐藏敏感信息，方便排查环境问题。",
                "本工具严格只读，不实现评价、修改密码、保存、删除、更新等操作。",
            ],
        },
        {
            "title": "成绩单说明",
            "body": "应用里有本地成绩单和官方成绩单两个入口，适用场景不同。",
            "items": [
                "本地成绩单由本地成绩快照生成，适合自己核对和留档。",
                "官方成绩单会打开学校网上办事大厅，由你在网页中手动查看或下载。",
                "打开官方成绩单入口时，本工具不会自动提交申请，也不会代替你点击办理流程。",
                "如果学校页面调整，请以学校页面显示为准。",
            ],
        },
        {
            "title": "出错怎么办",
            "body": "大多数问题可以先从环境检查页定位。",
            "items": [
                "先打开环境检查，确认浏览器、配置、数据目录和自启动状态。",
                "如果登录失效或学校要求重新验证，可以在设置页点击重新登录/初始化。",
                "需要别人帮忙排查时，点击导出诊断包；诊断包不会包含密码和 Cookie。",
                "如果成绩页为空，先立即检查一次，确认已经建立成绩基线。",
            ],
        },
        {
            "title": "卸载与清理",
            "body": "卸载程序和本地数据是两件事，可以按需要分别处理。",
            "items": [
                "不想后台运行时，在设置页取消自启动。",
                "卸载安装版程序只会移除程序文件，不会主动删除你的本地成绩快照。",
                "本地数据目录在 ~/.gdut-grade-monitor，可以从总览页打开数据目录后手动清理。",
                "如需删除保存的密码，请在 Windows 凭据管理器中删除对应凭据。",
            ],
        },
    ]


def doctor_table_rows(results: list[CheckResult]) -> list[tuple[str, str, str, str]]:
    rows = []
    for result in results:
        if result.ok:
            status = "正常"
            action = "无需操作"
        elif result.required:
            status = "需要处理"
            action = _doctor_action(result)
        else:
            status = "提示"
            action = _doctor_action(result)
        rows.append((status, result.name, result.message, action))
    return rows


def _doctor_action(result: CheckResult) -> str:
    name = result.name.lower()
    if "browser" in name:
        return "安装 Edge 或 Chrome；也可以安装 Playwright Chromium。"
    if "configuration" in name:
        return "点击一键配置本机，保存账号并建立基线。"
    if "autostart" in name:
        return "点击安装自启动，开启登录后后台提醒。"
    if "data directory" in name:
        return "检查用户目录权限，确保本工具可以写入 .gdut-grade-monitor。"
    if "python" in name:
        return "安装 Python 3.10 或更高版本，或改用打包好的 exe。"
    return "按错误信息处理后重新检查。"


def about_text() -> str:
    return (
        "GDUT 成绩提醒\n\n"
        f"版本: {APP_VERSION}\n"
        f"作者: {APP_AUTHOR}\n\n"
        "这是一个本地运行的广东工业大学教务系统成绩提醒工具。\n"
        "本工具严格只读，只用于检查课程成绩是否新增或变化。\n\n"
        "安全边界:\n"
        f"- 只允许读取欢迎页: {WELCOME_PATH}\n"
        f"- 只允许查询成绩接口: {GRADE_PATH}\n"
        "- 不实现评价、修改密码、保存、删除、更新等操作。\n"
        "- 密码保存到 Windows 凭据管理器，不会保存密码到配置文件。\n"
    )
