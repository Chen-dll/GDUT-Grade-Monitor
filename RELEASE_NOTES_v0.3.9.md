# GDUT 成绩提醒 v0.3.9

这是一个更新稳定性增强版，主要给 GitHub 访问不稳定的用户增加 Gitee 国内镜像更新源。

## 更新方式

- 已安装 `v0.3.8` 的打包版用户，可以在“设置 -> 检查更新”里安装 `v0.3.9` 小补丁。
- 如果因为网络原因无法访问 GitHub，可以到 Gitee 镜像页面手动下载新版安装包、便携包或补丁包。
- 从 `v0.3.9` 开始，之后检查更新会先尝试 GitHub，失败后自动尝试 Gitee 镜像。

## 新增

- 新增 Gitee 国内镜像更新源。
- 小补丁识别兼容 Gitee Release 附件字段。

## 改进

- 检查更新时先访问 GitHub，失败、超时或返回异常后自动尝试 Gitee。
- 更新弹窗会显示当前使用的更新源，例如 `GitHub` 或 `Gitee`。
- README 下载说明补充 Gitee 镜像地址。

## 说明

- 这个版本只调整应用更新通道，不改变教务系统查询逻辑。
- 严格只读边界保持不变，不会新增任何会修改教务系统数据的请求。
- `v0.3.8` 本身还没有自动 Gitee fallback，所以 GitHub 访问困难的用户可能需要手动从 Gitee 下载一次 `v0.3.9`。

## 验证

- `python -m unittest discover -s tests -v`：204 项通过。
- `python -m unittest tests.test_update_check tests.test_qt_gui_packaging tests.test_privacy_and_release_docs -v`：29 项通过。
- `python -m compileall gdut_grade_monitor tests`：通过。
- `git diff --check`：通过。
- `scripts\test_portable_release.ps1 -SkipLaunch`：普通路径、中文路径、带空格路径均通过。
