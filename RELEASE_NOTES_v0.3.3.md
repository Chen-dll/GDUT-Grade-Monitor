# GDUT 成绩提醒 v0.3.3

这是一个关闭窗口体验修复版，也会作为第一版真正提供小补丁资产的发布。

## 重要说明

- 已安装 `v0.3.2` 的打包版用户，可以在“设置 -> 检查更新”里看到 `v0.3.3`，并选择“安装小补丁”。
- 已安装 `v0.3.0` 或 `v0.3.1` 的用户仍需要先下载完整安装包或便携包，因为这些版本还没有内置补丁安装器。
- 小补丁只替换应用安装目录里的文件，不会覆盖本地配置、密码、Cookie、成绩快照或通知密钥。

## 修复

- 点击窗口右上角关闭按钮时，会询问“最小化到托盘”还是“退出程序”。
- 选择“最小化到托盘”后，窗口会隐藏到系统托盘，当前后台提醒进程继续运行。
- 选择“退出程序”才会真正结束当前进程。
- 托盘菜单里的“退出”和安装小补丁后的重启流程会直接退出，不再重复弹确认框。

## 验证

- `python -m unittest discover -s tests -v`
- `python -m compileall gdut_grade_monitor tests`
- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1`
- `powershell -ExecutionPolicy Bypass -File .\scripts\test_portable_release.ps1 -SkipLaunch`
- `powershell -ExecutionPolicy Bypass -File .\scripts\build_patch.ps1 -OldVersion 0.3.2 -NewVersion 0.3.3 ...`
- `powershell -ExecutionPolicy Bypass -File .\scripts\apply_patch_update.ps1 ...` 补丁应用冒烟
