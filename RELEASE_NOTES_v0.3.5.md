# GDUT 成绩提醒 v0.3.5

这是一个后台定时检查热修复版。

## 更新方式

- 已安装 `v0.3.4` 的打包版用户，可以在“设置 -> 检查更新”里安装 `v0.3.5` 小补丁。
- 小补丁只替换应用文件，不会覆盖本地配置、密码、Cookie、成绩快照、日志或通知密钥。
- 便携版用户也可以下载新的便携包覆盖程序目录，数据仍保存在用户目录。

## 修复

- 修复打开主界面后只自动检查一次，之后“下次检查”时间已过但没有继续检查的问题。
- 主界面现在会每 15 秒确认一次是否到达后台记录的 `next_check_at`，到点后自动执行一次静默只读检查。
- 定时器会避开未配置账号、暂停中、正在一键配置、正在执行其他后台任务等状态，避免重复请求教务系统。

## 验证

- `python -m unittest tests.test_qt_gui_packaging tests.test_v11_v12 tests.test_gui_model -v`
- `python -m compileall gdut_grade_monitor tests`
- `git diff --check`
