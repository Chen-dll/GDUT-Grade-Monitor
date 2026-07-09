# Release Checklist

这份清单用于每次发给别人之前做最后验收。不要上传含真实账号、真实 Cookie、真实成绩截图或个人诊断包的文件。

## 自动检查

- [ ] `python -m unittest discover -s tests -v`
- [ ] `python -m compileall gdut_grade_monitor tests packaging docs scripts`
- [ ] `git diff --check`
- [ ] `powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1`
- [ ] `powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1 -SkipExeBuild`
- [ ] `powershell -ExecutionPolicy Bypass -File scripts\test_portable_release.ps1`

## 安装版验收

- [ ] 在干净 Windows 电脑或虚拟机运行 `GDUTGradeMonitor-Setup.exe`。
- [ ] 默认路径可以安装，桌面快捷方式可选创建。
- [ ] 选择一个不存在的新安装路径时，安装程序能自动创建目录。
- [ ] 安装完成后启动程序，窗口位于屏幕可见区域。
- [ ] “一键配置本机”能打开登录流程，第一次只建立本地基线，不弹新成绩提醒。
- [ ] 卸载时分别测试“保留本地数据”和“删除本地数据”。

## 便携版验收

- [ ] 解压 `GDUTGradeMonitor-portable.zip` 到普通路径后能启动。
- [ ] 解压到中文路径后能启动。
- [ ] 解压到空格路径后能启动。
- [ ] 解压到不存在的新文件夹后能正常运行。
- [ ] `GDUTGradeMonitor-Cleanup.cmd` 和 `GDUTGradeMonitor-Cleanup.ps1` 随便携版一起存在。

## 小补丁更新验收

- [ ] 如本次发布提供小补丁，运行 `scripts\build_patch.ps1` 生成 `GDUTGradeMonitor-patch-v旧版本-to-v新版本.zip` 和同名 `.json`。
- [ ] 把补丁 zip/json 随新版 Release 一起上传。
- [ ] 旧版打包应用点击“设置 -> 检查更新”后显示“安装小补丁”。
- [ ] 检查更新、下载补丁和立即检查时都有处理中提示，连续点击不会启动多个后台任务。
- [ ] 补丁应用前会校验 SHA256，应用后程序能自动重新启动。
- [ ] 补丁不包含 `%USERPROFILE%\.gdut-grade-monitor`、密码、Cookie、通知密钥或真实成绩数据。

## 启动项残留清理

- [ ] 安装自启动后，“环境检查”显示自启动状态。
- [ ] 取消自启动后，不再保留本工具的用户启动文件。
- [ ] 模拟便携版目录被删除后，环境检查能提示残留启动项。
- [ ] “设置 -> 卸载辅助 -> 一键清理残留”能删除本工具创建的启动文件。
- [ ] 清理工具不会删除 Windows 凭据管理器里的密码或通知密钥。

## 发布包

- [ ] `dist\GDUTGradeMonitor-Setup.exe`
- [ ] `dist\GDUTGradeMonitor-portable.zip`
- [ ] `dist\GDUTGradeMonitor-Cleanup.cmd`
- [ ] `dist\GDUTGradeMonitor-Cleanup.ps1`
- [ ] `dist\SHA256SUMS.txt`
- [ ] 可选：`dist\GDUTGradeMonitor-patch-v旧版本-to-v新版本.zip`
- [ ] 可选：`dist\GDUTGradeMonitor-patch-v旧版本-to-v新版本.json`
- [ ] `README.md`
- [ ] `PRIVACY.md`
- [ ] `CHANGELOG.md`
- [ ] `RELEASE_NOTES_v0.3.3.md`
