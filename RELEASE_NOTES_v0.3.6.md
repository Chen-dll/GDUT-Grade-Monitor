# GDUT 成绩提醒 v0.3.6

这是一个开机自启动热修复版，主要修复安装路径包含中文时 Windows Script Host 找不到启动目标的问题。

## 更新方式

- 已安装 `v0.3.5` 的打包版用户，可以在“设置 -> 检查更新”里安装 `v0.3.6` 小补丁。
- 小补丁只替换应用文件，不会覆盖本地配置、密码、Cookie、成绩快照、日志或通知密钥。
- 如果已经遇到开机弹出 `Windows Script Host` 报错，更新后在“设置 -> 安装/修复自启动”点一次即可重写正确启动项。

## 修复

- 修复 Startup 文件夹中的 `GDUT Grade Monitor.vbs` 在中文路径下可能被 Windows Script Host 误读编码，导致错误 `80070002：系统找不到指定的文件`。
- 新写入的 Startup VBS 改为 UTF-16 带 BOM，兼容 Windows Script Host 对非 ASCII 路径的读取。
- 自启动健康检查兼容读取新版 UTF-16 脚本和旧版 UTF-8 脚本。

## 验证

- `python -m unittest discover -s tests -v`：195 项通过。
- `python -m unittest tests.test_storage_and_task tests.test_installer_packaging tests.test_version_and_about -v`：34 项通过。
- `python -m compileall gdut_grade_monitor tests packaging docs scripts`：通过。
- `git diff --check`：通过。
- `scripts\test_portable_release.ps1 -SkipLaunch`：普通路径、中文路径、带空格路径均通过。
- `GDUTGradeMonitor-patch-v0.3.5-to-v0.3.6.json/.zip` 已通过补丁清单、版本和 SHA256 校验。
- 本机 Startup VBS 重新写入 UTF-16 后，用 `cscript.exe` 实测可启动 `GDUTGradeMonitor.exe --monitor`。
