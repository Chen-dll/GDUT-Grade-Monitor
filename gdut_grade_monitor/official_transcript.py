from __future__ import annotations

OFFICIAL_TRANSCRIPT_PORTAL_URL = "https://e.gdut.edu.cn/infoplus/form/BKSZWCJD/start"


def official_transcript_guidance() -> str:
    return (
        "已打开广东工业大学网上办事大厅的“全日制本科生中文成绩单申请”。\n\n"
        "程序会优先使用本工具登录时的浏览器登录资料打开，尽量复用统一认证的 7天保持登录状态。\n"
        "这是学校官方流程；如果学校仍要求验证，请你在浏览器里手动登录、查看或下载；是否生成申请记录以学校页面为准。\n\n"
        "本工具不会自动提交申请，不调用写入接口，也不会保存办事大厅的 Cookie。"
    )
