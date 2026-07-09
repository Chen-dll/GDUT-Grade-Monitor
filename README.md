# GDUT Grade Monitor

广东工业大学教务系统成绩提醒工具。它会在本机定时、只读查询课程成绩，发现新增成绩或成绩变化时弹出 Windows 通知。

![Version](https://img.shields.io/badge/version-0.3.5-blue)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-2563eb)
![License](https://img.shields.io/badge/license-MIT-green)

> 非官方项目。请只在自己的账号上使用，并遵守学校相关规定。本工具的教务数据访问路径有只读 allowlist 限制，不提供评价、保存、删除、更新等会修改教务系统数据的功能。

## 下载

请到 [GitHub Releases](https://github.com/Chen-Dll/GDUT-Grade-Monitor/releases/latest) 下载最新版：

- `GDUTGradeMonitor-Setup.exe`：安装版，推荐大多数用户使用。
- `GDUTGradeMonitor-portable.zip`：便携版，解压后双击 `GDUTGradeMonitor.exe` 即可运行。
- `SHA256SUMS.txt`：安装包、便携包和可选小补丁的 SHA256 校验值，用于确认下载文件完整。

Windows 可能提示“未知发布者”，这是因为当前版本还没有代码签名证书。确认来源是本仓库 Release 后再运行。

## 3 分钟快速使用

1. 下载 `GDUTGradeMonitor-Setup.exe`，按安装向导完成安装并启动程序。
2. 第一次打开后点击“一键配置本机”，填写学号、密码和检查频率。
3. 如果弹出统一认证浏览器页面，按学校页面完成验证码或二次验证。
4. 回到主界面看到“现在已经可以后台提醒了”或“后台提醒已准备好”即可。

默认每 30 分钟检查一次。第一次只建立本地基线，不会提醒；之后发现新成绩或成绩变化才会通知。

密码和通知密钥不会上传，也不会写入配置文件；它们只保存到 Windows 凭据管理器。Cookie、成绩快照和日志保存在本机用户目录。

## 功能

- 只读查询课程成绩，不调用评价、修改、保存、删除类接口。
- 首次登录后保存 Cookie；密码保存到 Windows Credential Manager，不写入配置文件。
- 每 30 分钟默认检查一次，可自定义 1 到 1440 分钟。
- Windows 通知提醒、提醒历史、成绩表格 GUI。
- 可选多设备通知：支持 PushPlus、Server酱、ntfy 和邮件 SMTP。
- 多设备通知支持隐私模式、摘要模式、详细模式；远程通道默认隐私模式。
- 提醒历史会显示每次成绩变化的通知渠道和发送结果，方便排查某个手机/邮箱渠道是否失败。
- 支持 Windows 登录后自动后台运行；没有任务计划权限时自动使用用户启动项。
- 提供 `doctor` 环境检查，方便在别人的电脑上排查安装问题。
- 新电脑第一次打开会自动显示“新手向导”，按步骤介绍隐私、只读边界、页面功能和一键配置。
- 总览页提供“运行状态中心”，可查看后台状态、最近检查、下次检查、登录配置、自启动和最近错误。
- GUI 提供“一键配置本机”：填写学号、密码和检查频率后，自动完成登录、建立基线、安装后台自启动。
- 支持从总览页或系统托盘临时暂停后台提醒 1 小时、恢复后台检查、查看运行日志。
- 可从本地成绩快照导出 PDF/HTML 成绩单，便于个人核对；不会提交学校成绩单申请。
- 可打开学校网上办事大厅官方成绩单入口，由用户手动查看或下载官方成绩单；工具不会自动提交申请。
- 登录时会尽量勾选统一认证的“7天/保持登录/免登录”，官方成绩单入口也会优先复用本工具登录时的浏览器登录资料。
- GUI 提供“检查更新”，可打开 GitHub 最新 Release 下载页；如果 Release 提供匹配当前版本的小补丁，会优先提示“安装小补丁”。
- GUI 支持导出/导入非敏感设置，换电脑时可迁移查询频率和通知渠道开关；不会导出学号、密码、Cookie 或通知密钥。
- GUI 支持恢复推荐默认设置，会保留已保存账号和本地成绩快照。
- 环境检查会提示便携版残留启动项；设置页提供“卸载辅助”，也可单独运行 `GDUTGradeMonitor-Cleanup.cmd` 清理遗留启动项。
- 提供“关于”和“导出诊断包”，方便反馈问题；诊断包会隐藏学号、密码、Cookie 和完整成绩明细。
- 0.2.0 起默认使用 PySide6/Qt 现代桌面界面，保留旧 Tkinter 界面作为备用入口。

## 多设备通知

0.3.0 起可以在 GUI 的“设置 -> 多设备通知”里开启手机或邮箱提醒。电脑仍然是唯一登录教务系统并只读查询成绩的设备，手机、微信和邮箱只接收通知事件。

首批支持：

- `PushPlus`：微信类通知，填写 PushPlus token。
- `Server酱`：微信类通知，填写 SendKey。
- `ntfy`：支持手机 App 或网页订阅 topic；公共 topic 不建议发送详细成绩。
- `邮件 SMTP`：填写 SMTP 服务器、账号、收件人和授权码。

每个通道都可以单独选择通知内容：

- `隐私模式`：只提示有新成绩或成绩变化，不显示课程名和分数。
- `摘要模式`：显示学期和课程名，不显示分数。
- `详细模式`：显示学期、课程名和成绩。

远程通道会经过对应第三方服务。为了避免锁屏通知或第三方服务暴露成绩，远程通道默认使用隐私模式；如果你手动改为详细模式，请确认自己接受这个风险。通知 token、SendKey 和邮箱授权码只保存到 Windows Credential Manager，不写入 `config.json`。

发送测试通知和真实成绩提醒都会在本机提醒历史里记录每个渠道的成功/失败摘要。失败原因只保存可读提示，不保存 token、SendKey 或邮箱授权码。

## 环境要求

- Windows 10/11
- Python 3.10 或更高版本
- Chrome 或 Edge 浏览器。没有系统浏览器时，可运行 `python -m playwright install chromium`
- 能访问广东工业大学统一身份认证和教务系统

## 普通用户下载使用（推荐）

发布时会提供两种文件：

- 安装版：`GDUTGradeMonitor-Setup.exe`，推荐普通用户下载。
- 便携版：`GDUTGradeMonitor-portable.zip`，适合临时测试或不想安装时解压运行。
- 残留清理工具：`GDUTGradeMonitor-Cleanup.cmd` / `GDUTGradeMonitor-Cleanup.ps1`，适合已经手动删除便携版目录、但启动项还残留的情况。

如果使用安装版，普通用户只需要：

1. 下载并运行 `GDUTGradeMonitor-Setup.exe`
2. 按安装向导选择安装路径，可选创建桌面快捷方式
3. 安装完成后勾选“启动 GDUT 成绩提醒”
4. 点击主界面的“一键配置本机”
5. 输入学号、密码，确认检查频率和“开启登录自启动”
6. 按弹出的浏览器完成统一身份认证（如果需要验证码或二次验证）
7. 回到主界面确认顶部状态显示“后台提醒已准备好”

如果使用便携版 `GDUTGradeMonitor-portable.zip`，则只需要：

1. 下载并解压 `GDUTGradeMonitor-portable.zip`
2. 双击解压目录里的 `GDUTGradeMonitor.exe`
3. 点击主界面的“一键配置本机”
4. 输入学号、密码，确认检查频率和“开启登录自启动”
5. 按弹出的浏览器完成统一身份认证（如果需要验证码或二次验证）
6. 回到主界面确认顶部状态显示“后台提醒已准备好”

所有常用操作都可以在 GUI 中完成，不需要打开终端。

下载后如需校验文件完整性，可在 Release 中同时下载 `SHA256SUMS.txt`，用 PowerShell 的 `Get-FileHash` 对比安装包、便携包或小补丁的 SHA256 值。

如果只是小修复，Release 可能同时提供 `GDUTGradeMonitor-patch-v旧版本-to-v新版本.zip` 和同名 `.json` 补丁清单。已安装的打包版用户在“设置 -> 检查更新”里可以直接选择“安装小补丁”，程序会先校验补丁 SHA256，再短暂关闭、替换变化文件并重新启动。源码运行版不会自动应用补丁，需要拉取源码或下载完整包。

注意：小补丁能力从 `0.3.2` 开始提供。已经安装 `0.3.0` 或 `0.3.1` 的用户，需要先下载完整安装包或便携包更新到 `0.3.2`；之后的版本才可以通过“安装小补丁”减少下载量。

如果自启动安装时 Windows 拒绝创建计划任务，程序会自动改用当前用户启动项。

安装路径可以选择一个还不存在的新文件夹；只要路径格式正确并且你有权限写入，安装程序会自动创建它。

首次配置只会建立成绩基线，不会对已有成绩弹通知。之后发现新成绩或成绩变化才会提醒。

## 从源码安装

从 GitHub 下载 ZIP 或 clone 项目后，在项目目录运行：

```powershell
python -m pip install .
python -m gdut_grade_monitor doctor
```

如果是开发/修改源码，使用 editable 安装：

```powershell
python -m pip install -e .
```

也可以用一键安装脚本：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

脚本会安装依赖、运行环境检查，然后打开 GUI。后续配置仍在 GUI 里点击“一键配置本机”完成。

## 首次配置

运行：

```powershell
python -m gdut_grade_monitor setup
```

按提示输入学号和密码。注意：

- 密码输入时不会显示，这是正常的。
- 请切换到英文输入法；程序会阻止中文/全角字符密码被保存。
- 如果浏览器弹出登录页，请完成登录。

完成后先手动检查一次：

```powershell
python -m gdut_grade_monitor check --json
python -m gdut_grade_monitor monitor --once
```

## 开启后台提醒

```powershell
python -m gdut_grade_monitor task install
python -m gdut_grade_monitor task status
```

如果 Windows 拒绝创建计划任务，程序会自动安装到当前用户启动文件夹。登录 Windows 后会在后台运行。

取消自启动：

```powershell
python -m gdut_grade_monitor task uninstall
```

## GUI 界面

```powershell
python -m gdut_grade_monitor gui
```

默认打开 Qt 版现代界面。旧版 Tkinter 界面仍可作为备用入口：

```powershell
python -m gdut_grade_monitor legacy-gui
```

双击 exe 或运行 GUI 后支持：

- 一键配置本机
- 查看成绩列表
- 导出本地成绩单
- 打开官方成绩单入口
- 立即检查
- 登录/初始化
- 安装/取消自启动
- 修改查询频率
- 导出/导入非敏感设置
- 恢复推荐默认设置
- 查看提醒历史
- 环境检查
- 导出诊断包
- 检查更新
- 查看版本和只读安全说明
- 打开本地数据目录

## 隐私说明

隐私和本地数据保存位置见 [PRIVACY.md](PRIVACY.md)。简要来说：密码和通知密钥只保存到 Windows 凭据管理器，Cookie、配置、成绩快照和日志保存在 `%USERPROFILE%\.gdut-grade-monitor`；默认不会上传这些数据。若主动开启多设备通知，程序会按你选择的隐私级别把通知内容发送到对应第三方服务。

## 配置参数

查看配置：

```powershell
python -m gdut_grade_monitor config show
```

修改查询频率，例如 10 分钟：

```powershell
python -m gdut_grade_monitor config interval 10
```

导出非敏感设置：

```powershell
python -m gdut_grade_monitor config export --output gdut-grade-settings.json
```

导入非敏感设置：

```powershell
python -m gdut_grade_monitor config import --input gdut-grade-settings.json
```

恢复推荐默认设置：

```powershell
python -m gdut_grade_monitor config reset
```

配置文件位置：

```text
%USERPROFILE%\.gdut-grade-monitor\config.json
```

敏感信息不会写入配置文件。密码保存在 Windows Credential Manager，Cookie 保存在用户目录。

## 环境检查

```powershell
python -m gdut_grade_monitor doctor
```

它会检查：

- Python 版本
- Windows 平台
- 依赖包是否安装
- Chrome/Edge 或 Playwright 浏览器是否可用
- 数据目录是否可写
- 是否已配置学号
- 自启动是否已安装

## 反馈问题

如果发给别人后运行失败，可以让对方在 GUI 的“环境检查”页点击“导出诊断包”，或通过菜单“文件 → 导出诊断包...”导出 zip。

诊断包用于排查环境和运行状态，会自动隐藏：

- 完整学号
- 密码
- Cookie / token / secret
- 完整成绩明细和课程名称

也可以用命令行导出：

```powershell
python -m gdut_grade_monitor diagnostics export --output support.zip
```

## 常用命令

```powershell
python -m gdut_grade_monitor doctor
python -m gdut_grade_monitor setup
python -m gdut_grade_monitor check --json
python -m gdut_grade_monitor monitor --once
python -m gdut_grade_monitor monitor
python -m gdut_grade_monitor gui
python -m gdut_grade_monitor config show
python -m gdut_grade_monitor config interval 30
python -m gdut_grade_monitor cleanup
python -m gdut_grade_monitor task install
python -m gdut_grade_monitor task status
python -m gdut_grade_monitor task uninstall
```

安装后如果 `gdut-grade` 在 PATH 中，也可以把 `python -m gdut_grade_monitor` 替换为：

```powershell
gdut-grade
```

## 安全边界

教务系统数据请求经过 allowlist 限制，目前只允许：

- `GET /login!welcome.action`
- `POST /xskccjxx!getDataList.action`

登录过程只用于获取会话。成绩查询失败时，如果教务系统返回 HTML 错误页，程序会报友好错误，而不是继续解析。

## 卸载

```powershell
python -m gdut_grade_monitor task uninstall
python -m pip uninstall gdut-grade-monitor
```

安装版卸载时会询问是否同时删除本地配置、Cookie、成绩快照和日志。选择保留数据后，之后重装可以继续使用原来的本地状态。

如果使用便携版时直接删除了解压目录，可能会留下 Windows 启动项。此时可单独下载或运行 Release 里的：

```text
GDUTGradeMonitor-Cleanup.cmd
```

它会删除本工具创建的启动文件和计划任务，并询问是否同时删除本地配置、Cookie、成绩快照和日志。它不会删除 Windows 凭据管理器中的密码和通知密钥。

如果程序还能打开，也可以进入“设置 -> 卸载辅助”，点击“一键清理残留”。环境检查页会在发现启动项指向已删除程序时给出提示。

如需手动删除本地状态文件，可删除：

```text
%USERPROFILE%\.gdut-grade-monitor
```

## 给维护者

发布前运行：

```powershell
python -m unittest discover -s tests -v
python -m compileall gdut_grade_monitor tests
python -m gdut_grade_monitor doctor
powershell -ExecutionPolicy Bypass -File .\scripts\test_portable_release.ps1 -SkipLaunch
```

构建 Windows GUI 应用目录和便携 zip：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
```

构建传统安装包需要先安装 Inno Setup，然后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

如果要给已安装用户提供小补丁，保留上一版 `dist\GDUTGradeMonitor`，新版构建完成后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_patch.ps1 `
  -OldVersion 0.3.4 `
  -NewVersion 0.3.5 `
  -PreviousDist .\dist-prev\GDUTGradeMonitor `
  -CurrentDist .\dist\GDUTGradeMonitor
```

脚本会生成补丁 zip 和补丁清单 json。把这两个文件随新版 Release 一起上传，旧版应用检查更新时就能识别并安装小补丁。补丁只会复制清单里的相对路径文件，不包含用户目录里的配置、Cookie、成绩快照、日志或凭据。

构建产物：

```text
dist\GDUTGradeMonitor\GDUTGradeMonitor.exe
dist\GDUTGradeMonitor-portable.zip
dist\GDUTGradeMonitor-Setup.exe
dist\SHA256SUMS.txt
```

## 版本记录

见 [CHANGELOG.md](CHANGELOG.md)。
