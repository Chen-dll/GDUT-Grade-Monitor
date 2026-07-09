from __future__ import annotations

from collections import defaultdict
from datetime import datetime
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
    excluded_zero, excluded_deferred = _zero_score_placeholder_indexes(grades)
    for index, grade in enumerate(grades):
        if index in excluded_zero:
            uncounted += 1
            continue
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
        "excluded_deferred_count": len(excluded_deferred),
        "excluded_zero_placeholder_count": len(excluded_zero),
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


def status_center_rows(config: dict, state: dict, startup_installed: bool, now_iso: str | None = None) -> list[dict[str, str]]:
    monitor = state.get("monitor", {})
    raw_status = state.get("last_check_status") or "idle"
    paused_until_raw = str(config.get("monitor_paused_until", "") or "").strip()
    paused_until = paused_until_raw.replace("T", " ") if _pause_is_active(paused_until_raw, now_iso) else ""
    last_check = str(monitor.get("last_check_at", "尚未检查")).replace("T", " ")
    heartbeat = str(monitor.get("heartbeat_at", "尚未启动")).replace("T", " ")
    interval = int(config.get("poll_interval_minutes", 30))

    status_labels = {
        "ok": ("后台正常", "最近一次检查完成。", "ok"),
        "paused": ("暂停中", "自动后台检查已暂停，手动立即检查仍可使用。", "warning"),
        "error": ("检查失败", "后台检查遇到问题。", "error"),
        "notification_failed": ("通知异常", "成绩检查已完成，但至少一个通知渠道发送失败。", "warning"),
        "idle": ("等待配置", "完成一键配置后会开始后台提醒。", "warning"),
    }
    status_value, status_detail, status_tone = status_labels.get(raw_status, (str(raw_status), "查看日志或诊断包了解详情。", "warning"))
    if raw_status == "error":
        kind_labels = {
            "login_expired": ("登录过期", "请重新登录/初始化，完成统一身份认证。", "error"),
            "network": ("网络异常", "请检查网络、校园网或代理设置，稍后会自动重试。", "warning"),
            "school_system": ("学校系统异常", "可能是教务系统临时异常，请稍后重试或导出诊断包。", "warning"),
            "browser_missing": ("浏览器组件缺失", "请在设置页重新进行一键配置，或安装 Chrome/Edge。", "error"),
            "autostart_broken": ("自启动路径失效", "请在设置页点击安装/修复自启动。", "warning"),
        }
        status_value, status_detail, status_tone = kind_labels.get(
            str(monitor.get("last_error_kind", "") or ""),
            (status_value, status_detail, status_tone),
        )
    if paused_until:
        status_value = "暂停中"
        status_detail = "自动后台检查已暂停，手动立即检查仍可使用。"
        status_tone = "warning"

    next_value = f"每 {interval} 分钟"
    next_detail = "后台启动后按此频率只读检查。"
    if paused_until:
        next_value = f"暂停到 {paused_until}"
        next_detail = "到点后自动恢复按频率检查。"

    rows = [
        {"label": "后台状态", "value": status_value, "detail": status_detail, "tone": status_tone},
        {"label": "最近检查", "value": last_check, "detail": f"最近心跳: {heartbeat}", "tone": "neutral"},
        {"label": "下次检查", "value": next_value, "detail": next_detail, "tone": "neutral"},
        {
            "label": "登录配置",
            "value": "已保存账号" if config.get("student_id") else "未配置",
            "detail": "密码保存在 Windows 凭据管理器。" if config.get("student_id") else "点击一键配置本机完成登录。",
            "tone": "ok" if config.get("student_id") else "warning",
        },
        {
            "label": "后台自启动",
            "value": "已开启" if startup_installed else "未开启",
            "detail": "Windows 登录后会自动后台检查。" if startup_installed else "建议在设置页安装/修复自启动。",
            "tone": "ok" if startup_installed else "warning",
        },
    ]
    failure_count = int(monitor.get("consecutive_failures", 0) or 0)
    summary = str(monitor.get("last_error_summary", "") or state.get("last_error", "") or "").strip()
    action = str(monitor.get("last_error_action", "") or "可重新登录、打开环境检查或导出诊断包。").strip()
    if summary:
        value = summary
        if failure_count >= 3:
            value = f"连续 {failure_count} 次失败: {summary}"
        rows.append({"label": "最近错误", "value": value, "detail": action, "tone": "error" if raw_status == "error" else "warning"})
    return rows


def _pause_is_active(paused_until: str, now_iso: str | None = None) -> bool:
    if not paused_until:
        return False
    try:
        until = datetime.fromisoformat(paused_until)
        now = datetime.fromisoformat(now_iso) if now_iso else datetime.now()
    except ValueError:
        return False
    return until > now


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


def _zero_score_placeholder_indexes(grades: list[dict]) -> tuple[set[int], set[int]]:
    grouped: dict[tuple[str, ...], list[tuple[int, float | None]]] = defaultdict(list)
    for index, grade in enumerate(grades):
        key = _analytics_course_key(index, grade)
        grouped[key].append((index, _number(grade.get("score"))))

    zero_score = set()
    deferred = set()
    for rows in grouped.values():
        zero_rows = {index for index, score in rows if score == 0}
        zero_score.update(zero_rows)
        has_positive_score = any(score is not None and score > 0 for _, score in rows)
        if has_positive_score:
            deferred.update(zero_rows)
    return zero_score, deferred


def _analytics_course_key(index: int, grade: dict) -> tuple[str, ...]:
    course_code = str(grade.get("course_code", "")).strip()
    course_name = str(grade.get("course_name", "")).strip()
    raw = grade.get("raw", {})
    if isinstance(raw, dict):
        if not course_code:
            course_code = str(_first(raw, ("kcbh", "kcdm", "课程代码", "课程编号"))).strip()
        if not course_name:
            course_name = str(_first(raw, ("kcmc", "课程名称", "name"))).strip()
    if course_code:
        return ("code", course_code, course_name)
    if course_name:
        credit = str(grade.get("credit", "")).strip()
        return ("name", course_name, credit)
    return ("row", str(index))


def _first(values: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = values.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


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


def history_table_rows(state: dict, include_delivery: bool = False) -> list[tuple]:
    labels = {"new": "新成绩", "changed": "成绩变化"}
    rows = []
    for item in state.get("history", []):
        at = str(item.get("at", "")).replace("T", " ")
        base = (
            at,
            labels.get(item.get("kind", ""), str(item.get("kind", ""))),
            str(item.get("semester", "")),
            str(item.get("course_name", "")),
            str(item.get("score", "")),
        )
        if include_delivery:
            channels, results = _delivery_summary(item.get("delivery", []))
            rows.append((*base, channels, results))
        else:
            rows.append(base)
    return rows


def _delivery_summary(delivery: object) -> tuple[str, str]:
    if not isinstance(delivery, list) or not delivery:
        return ("未记录", "旧记录")
    channels = []
    ok_count = 0
    fail_count = 0
    for item in delivery:
        if not isinstance(item, dict):
            continue
        channels.append(str(item.get("label") or item.get("channel_id") or "未知渠道"))
        if item.get("ok"):
            ok_count += 1
        else:
            fail_count += 1
    if not channels:
        return ("未记录", "旧记录")
    if fail_count:
        result = f"{ok_count} 成功 / {fail_count} 失败"
    else:
        result = f"{ok_count} 成功"
    return (
        "、".join(channels),
        result,
    )


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
            "body": "点击一键配置本机，程序会引导你输入学号和密码、登录教务系统、建立成绩基线，并安装/修复自启动。",
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
            "body": "成绩基线已建立，但还没有安装/修复自启动。安装后每次登录 Windows 会自动后台检查。",
            "primary_action": "安装/修复自启动",
        }

    interval = int(config.get("poll_interval_minutes", 30))
    last_check = str(state.get("monitor", {}).get("last_check_at", "尚未检查")).replace("T", " ")
    return {
        "tone": "ok",
        "title": "现在已经可以后台提醒了",
        "body": f"当前会在 Windows 登录后后台运行，每 {interval} 分钟只读检查一次。最近检查: {last_check}",
        "primary_action": "立即检查",
    }


def onboarding_steps() -> list[dict[str, str]]:
    return [
        {
            "title": "一键配置本机",
            "body": "先点击“一键配置本机”，填写学号、密码和查询频率；密码不会上传，只保存到 Windows 凭据管理器。",
        },
        {
            "title": "完成浏览器登录",
            "body": "如果学校登录页要求验证码或短信，就在弹出的浏览器里手动完成。",
        },
        {
            "title": "建立成绩基线",
            "body": "首次读取只保存本地快照，第一次不会提醒，之后才比较新增或变化成绩。",
        },
        {
            "title": "后台自动提醒",
            "body": "默认每 30 分钟严格只读检查一次，只有新增或变化成绩才通知。",
        },
    ]


def first_run_wizard_pages() -> list[dict[str, object]]:
    return [
        {
            "title": "欢迎使用 GDUT 成绩提醒",
            "nav_title": "欢迎使用",
            "body": "这个工具会在你的 Windows 电脑上后台运行，定时只读检查教务系统课程成绩。",
            "items": [
                "发现新增成绩或成绩变化时才弹 Windows 通知。",
                "默认每 30 分钟检查一次，之后可以在设置页调整。",
                "它不是官方项目，请只在自己的账号上使用。",
            ],
            "primary_action": "下一步",
        },
        {
            "title": "隐私与只读边界",
            "nav_title": "隐私边界",
            "body": "核心原则是本地保存、严格只读、不给教务系统写入任何数据。",
            "items": [
                "密码不会上传，只保存到 Windows 凭据管理器。",
                "Cookie、配置、成绩快照和日志保存在用户目录 .gdut-grade-monitor。",
                "首次读取只建立本地成绩基线，第一次不会提醒旧成绩。",
                "不实现评价、修改密码、保存、删除、更新等写入操作。",
            ],
            "primary_action": "下一步",
        },
        {
            "title": "认识主界面",
            "nav_title": "认识界面",
            "body": "配置完成后，大多数操作都可以在左侧导航里完成。",
            "items": [
                "总览：查看后台状态、下一次检查频率和最近变化。",
                "成绩：查看本地成绩快照、绩点统计和本地成绩单导出。",
                "提醒历史：查看已经提醒过的新成绩或成绩变化。",
                "设置：重新登录、调整频率、安装/修复自启动、检查更新。",
                "环境检查：排查浏览器、配置、数据目录和自启动问题。",
            ],
            "primary_action": "下一步",
        },
        {
            "title": "开始初始化",
            "nav_title": "开始配置",
            "body": "接下来会进入一键配置流程。你只需要填写学号、密码和检查频率，然后按弹出的学校登录页完成认证。",
            "items": [
                "建议保持默认每 30 分钟检查一次。",
                "如果遇到验证码、短信或风控提示，直接在浏览器里手动完成。",
                "配置完成后会回到总览页，并显示现在已经可以后台提醒了。",
            ],
            "primary_action": "开始一键配置",
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
                "提醒历史会记录提醒摘要和各通知渠道发送结果，不保存密码、Cookie 或通知密钥。",
                "立即检查适合调试；后台提醒依赖设置页里的自启动状态。",
            ],
        },
        {
            "title": "多设备通知",
            "body": "电脑仍然负责只读查询成绩，手机、微信和邮箱只接收通知事件。",
            "items": [
                "设置页可以开启 PushPlus、Server酱、ntfy 或邮件 SMTP。",
                "每个通道可选择隐私模式、摘要模式或详细模式。",
                "远程通道默认隐私模式，只提示有新成绩或成绩变化。",
                "第三方通知服务会接收你选择发送的通知内容，开启详细模式前请确认风险。",
            ],
        },
        {
            "title": "数据与隐私",
            "body": "所有敏感数据都留在本机，且尽量放在系统提供的位置。",
            "items": [
                "密码保存在 Windows 凭据管理器，不写入配置文件、日志或诊断包。",
                "通知 token、SendKey 和邮箱授权码同样保存在 Windows 凭据管理器。",
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
                "设置页的卸载辅助可以检测并清理便携版目录被直接删除后留下的启动项。",
                "卸载安装版程序只会移除程序文件，不会主动删除你的本地成绩快照。",
                "本地数据目录在 ~/.gdut-grade-monitor，可以从总览页打开数据目录后手动清理。",
                "如需删除保存的密码，请在 Windows 凭据管理器中删除对应凭据。",
            ],
        },
        {
            "title": "配置迁移与恢复默认",
            "body": "设置页可以迁移非敏感偏好，也可以把设置恢复到推荐状态。",
            "items": [
                "导出设置只包含查询频率、日志级别和通知渠道开关等非敏感配置。",
                "导出文件不会包含学号、密码、Cookie、成绩快照、通知 token、SendKey 或邮箱授权码。",
                "导入设置不会覆盖本机已保存账号；通知密钥仍需在多设备通知页重新保存。",
                "恢复默认会重置查询频率、暂停状态和通知开关，但保留账号与本地成绩快照。",
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
        return "点击安装/修复自启动，开启登录后后台提醒。"
    if "startup residue" in name:
        return "打开设置页的卸载辅助，点击一键清理残留。"
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
