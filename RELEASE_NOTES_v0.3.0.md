# GDUT 成绩提醒 v0.3.0

这是一个多设备通知版本。电脑仍然负责登录和只读查询教务系统，手机、微信和邮箱只接收通知事件。

## 新增

- 支持 PushPlus 微信通知。
- 支持 Server酱 微信通知。
- 支持 ntfy 手机/网页通知。
- 支持邮件 SMTP 通知。
- 每个通道可单独设置隐私模式、摘要模式或详细模式。
- 设置页新增“多设备通知”窗口，可保存配置并发送测试通知。
- 多设备通知窗口新增“配置自检”，会提示 token、SendKey、Topic、SMTP 授权码等缺失项；发送测试后会按渠道显示成功/失败结果，并给出更明确的中文处理建议。

## 隐私与安全

- 远程通知通道默认使用隐私模式，只提示有新成绩或成绩变化。
- PushPlus token、Server酱 SendKey、ntfy token 和 SMTP 授权码只保存到 Windows Credential Manager。
- 配置文件会递归剔除 token、password、secret、cookie 等敏感字段。
- 第三方通知服务会接收你选择发送的通知内容，开启详细模式前请确认自己接受这个风险。

## 验证

- `python -m unittest discover -s tests -v`
- `python -m compileall gdut_grade_monitor tests packaging docs`
