# GDUT 成绩提醒 v0.3.2

这是一个发布前稳定性和更新体验版本。重点是修复缓考/未开放成绩对绩点统计的影响，并为后续版本加入安全的小补丁更新能力。

## 重要说明

- 已安装 `v0.3.0` 或 `v0.3.1` 的用户需要先下载完整安装包或便携包更新到 `v0.3.2`。
- 小补丁更新能力从 `v0.3.2` 开始提供；之后版本如果发布补丁包，用户可在“设置 -> 检查更新”里安装小补丁。
- 补丁更新只替换应用安装目录中的文件，不会覆盖本地配置、密码、Cookie、成绩快照或通知密钥。

## 改进

- 成绩统计会把 `0` 分占位记录排除在学分、平均绩点、绩点分布和本地成绩单平均分之外。
- 如果同一课程同时存在 `0` 分和正常分数，`0` 分会被视为疑似缓考前占位记录，不计入总学分。
- “检查更新”会识别匹配当前版本的小补丁资产，并优先提示安装小补丁。
- 检查更新、下载补丁和立即检查时都会显示处理中提示，连续点击不会启动多个后台任务。
- 补丁下载和清单校验失败时，会提示下载完整安装包或便携包，不再显示难懂的底层异常。

## 验证

- `python -m unittest discover -s tests -v`
- `python -m compileall gdut_grade_monitor tests packaging docs scripts`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1`
- `powershell -ExecutionPolicy Bypass -File .\scripts\test_portable_release.ps1 -SkipLaunch`
