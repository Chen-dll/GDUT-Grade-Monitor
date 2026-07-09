# Privacy

GDUT Grade Monitor 是本地运行工具。默认情况下，它不会上传你的学号、密码、Cookie、成绩快照或诊断包。若你主动开启多设备通知，程序会把你选择的通知内容发送到对应的第三方通知服务。

## 本机会保存什么

- 密码：保存到 Windows 凭据管理器，服务名为 `gdut-grade-monitor`。
- 多设备通知密钥：PushPlus token、Server酱 SendKey、ntfy token 和 SMTP 授权码保存到 Windows 凭据管理器。
- 配置：保存到 `%USERPROFILE%\.gdut-grade-monitor\config.json`，包含检查频率、学号等非密码配置。
- Cookie：保存到 `%USERPROFILE%\.gdut-grade-monitor\cookies.json`，用于减少重复登录。
- 成绩快照和提醒历史：保存到 `%USERPROFILE%\.gdut-grade-monitor\state.json`。
- 通知发送结果摘要：保存到提醒历史中，用于显示每个通知渠道成功或失败；不会保存通知密钥。
- 日志：保存到 `%USERPROFILE%\.gdut-grade-monitor\logs\monitor.log`，用于排查运行问题。

## 不会保存什么

- 密码不会写入配置文件、日志、诊断包或 Release 文件。
- 多设备通知 token、SendKey 和邮箱授权码不会写入配置文件、日志、诊断包或 Release 文件。
- 诊断包不会包含完整 Cookie、token、secret、完整学号、完整课程成绩明细。
- 本工具不会收集遥测，不会把数据上传到作者或 GitHub。
- “导出设置”只导出可迁移的非敏感配置，例如查询频率和通知渠道开关；不会导出学号、密码、Cookie、成绩快照、通知 token、SendKey 或邮箱授权码。

## 网络访问

- 教务系统数据访问只允许只读成绩查询和登录状态验证。
- “检查更新”只访问 GitHub Releases，用于比较当前版本和最新版本。
- “官方成绩单”入口会打开学校网上办事大厅，由用户在网页中手动操作。
- “多设备通知”是可选功能。开启 PushPlus、Server酱、ntfy 或 SMTP 后，第三方服务会接收通知标题和正文。远程通道默认隐私模式，只发送“有新成绩/成绩有变化”这类摘要；如果你改为详细模式，课程名和成绩也会发送到对应服务。

## 删除本地数据

安装版卸载程序会询问是否同时删除本地配置、Cookie、成绩快照和日志。选择“否”时只删除程序文件和快捷方式，保留本地数据以便之后重装继续使用。

如需删除本地数据：

1. 在应用的“设置”页取消自启动。
2. 如果便携版目录已被直接删除，可在应用“设置 -> 卸载辅助”点击“一键清理残留”，或运行 Release 中的 `GDUTGradeMonitor-Cleanup.cmd`。
3. 卸载时选择同时删除本地数据，或手动删除 `%USERPROFILE%\.gdut-grade-monitor`。
4. 打开 Windows 凭据管理器，删除服务名为 `gdut-grade-monitor` 的凭据。

## 诊断包

环境检查页可以导出诊断包。诊断包只用于帮你或维护者排查问题，导出前会自动隐藏敏感信息。发送诊断包前，仍建议自行确认其中内容。
