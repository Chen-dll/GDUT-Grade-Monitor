# Privacy

GDUT Grade Monitor 是本地运行工具。它不会上传你的学号、密码、Cookie、成绩快照或诊断包。

## 本机会保存什么

- 密码：保存到 Windows 凭据管理器，服务名为 `gdut-grade-monitor`。
- 配置：保存到 `%USERPROFILE%\.gdut-grade-monitor\config.json`，包含检查频率、学号等非密码配置。
- Cookie：保存到 `%USERPROFILE%\.gdut-grade-monitor\cookies.json`，用于减少重复登录。
- 成绩快照和提醒历史：保存到 `%USERPROFILE%\.gdut-grade-monitor\state.json`。
- 日志：保存到 `%USERPROFILE%\.gdut-grade-monitor\logs\monitor.log`，用于排查运行问题。

## 不会保存什么

- 密码不会写入配置文件、日志、诊断包或 Release 文件。
- 诊断包不会包含完整 Cookie、token、secret、完整学号、完整课程成绩明细。
- 本工具不会收集遥测，不会把数据上传到作者、GitHub 或第三方服务。

## 网络访问

- 教务系统数据访问只允许只读成绩查询和登录状态验证。
- “检查更新”只访问 GitHub Releases，用于比较当前版本和最新版本。
- “官方成绩单”入口会打开学校网上办事大厅，由用户在网页中手动操作。

## 删除本地数据

卸载程序只会删除程序文件和快捷方式，不会自动删除你的本地数据。

如需删除本地数据：

1. 在应用的“设置”页取消自启动。
2. 删除 `%USERPROFILE%\.gdut-grade-monitor`。
3. 打开 Windows 凭据管理器，删除服务名为 `gdut-grade-monitor` 的凭据。

## 诊断包

环境检查页可以导出诊断包。诊断包只用于帮你或维护者排查问题，导出前会自动隐藏敏感信息。发送诊断包前，仍建议自行确认其中内容。
