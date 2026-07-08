import unittest
from pathlib import Path


class InstallerPackagingTests(unittest.TestCase):
    def test_inno_setup_installs_per_user_with_icon_and_shortcuts(self):
        text = Path("packaging/installer/GDUTGradeMonitor.iss").read_text(encoding="utf-8")

        self.assertIn("AppName=GDUT 成绩提醒", text)
        self.assertIn("AppPublisher=Chen-Dll", text)
        self.assertIn("AppVerName=GDUT 成绩提醒 {#AppVersion}", text)
        self.assertIn("PrivilegesRequired=lowest", text)
        self.assertIn("SetupLogging=yes", text)
        self.assertIn("VersionInfoCompany=Chen-Dll", text)
        self.assertIn("ChineseSimplified.isl", text)
        self.assertNotIn("compiler:Languages\\ChineseSimplified.isl", text)
        self.assertIn(r"DefaultDirName={localappdata}\Programs\GDUTGradeMonitor", text)
        self.assertIn(r"SetupIconFile={#SourceRoot}\gdut_grade_monitor\assets\icon.ico", text)
        self.assertIn("OutputBaseFilename=GDUTGradeMonitor-Setup", text)
        self.assertIn(r"UninstallDisplayIcon={app}\{#AppExeName}", text)
        self.assertIn('Source: "{#SourceRoot}\\dist\\GDUTGradeMonitor\\*"', text)
        self.assertIn("recursesubdirs", text)
        self.assertIn('Name: "desktopicon"', text)
        self.assertIn('Name: "{autoprograms}\\GDUT 成绩提醒"', text)
        self.assertIn('Name: "{autodesktop}\\GDUT 成绩提醒"', text)
        self.assertIn("Flags: nowait postinstall skipifsilent", text)

    def test_inno_setup_validates_and_creates_custom_install_directory(self):
        text = Path("packaging/installer/GDUTGradeMonitor.iss").read_text(encoding="utf-8")

        self.assertIn("[Code]", text)
        self.assertIn("function NextButtonClick(CurPageID: Integer): Boolean;", text)
        self.assertIn("wpSelectDir", text)
        self.assertIn("ValidateInstallDir", text)
        self.assertIn("ForceDirectories", text)
        self.assertIn("目录不存在，安装程序将自动创建", text)
        self.assertIn("安装路径格式不正确", text)
        self.assertIn("ContainsInvalidPathChars", text)

    def test_installer_uses_local_chinese_language_file(self):
        script = Path("packaging/installer/GDUTGradeMonitor.iss").read_text(encoding="utf-8")
        language = Path("packaging/installer/ChineseSimplified.isl").read_text(encoding="utf-8")

        self.assertIn(
            r'MessagesFile: "compiler:Default.isl,{#SourceRoot}\packaging\installer\ChineseSimplified.isl"',
            script,
        )
        self.assertIn("[LangOptions]", language)
        self.assertIn("LanguageName=简体中文", language)
        self.assertIn("ButtonNext=下一步(&N) >", language)
        self.assertIn("ButtonInstall=安装(&I)", language)
        self.assertIn("安装阶段不会要求教务账号密码", language)
        self.assertIn("SelectDirDesc=您想将 [name] 安装到哪里？", language)
        self.assertIn("后台提醒和账号配置会在主程序里完成", language)
        self.assertIn("FinishedHeadingLabel=[name] 安装完成", language)

    def test_inno_setup_has_intro_and_readonly_notice(self):
        script = Path("packaging/installer/GDUTGradeMonitor.iss").read_text(encoding="utf-8")
        intro = Path("packaging/installer/InfoBefore.txt").read_text(encoding="utf-8")
        after = Path("packaging/installer/InfoAfter.txt").read_text(encoding="utf-8")

        self.assertIn(r"InfoBeforeFile={#SourceRoot}\packaging\installer\InfoBefore.txt", script)
        self.assertIn(r"InfoAfterFile={#SourceRoot}\packaging\installer\InfoAfter.txt", script)
        self.assertIn("作者: Chen-Dll", intro)
        self.assertIn("安装前请先确认", intro)
        self.assertIn("严格只读", intro)
        self.assertIn("安装程序不会收集或保存学号、密码", intro)
        self.assertIn("放心点击“下一步”", intro)
        self.assertIn("未知发布者", intro)
        self.assertIn("一键配置本机", intro)
        self.assertIn("安装已完成", after)
        self.assertIn("下一步建议", after)
        self.assertIn("不需要安装 Python", after)
        self.assertIn("环境检查", after)
        self.assertIn("卸载程序只会删除安装目录和快捷方式", after)
        self.assertIn("不会执行评价、保存、删除、更新", after)

    def test_installer_build_script_uses_inno_compiler_and_friendly_error(self):
        text = Path("scripts/build_installer.ps1").read_text(encoding="utf-8")

        self.assertIn("GDUTGradeMonitor.iss", text)
        self.assertIn("ISCC.exe", text)
        self.assertIn("Inno Setup", text)
        self.assertIn("CurrentVersion\\Uninstall", text)
        self.assertIn("scripts\\build_exe.ps1", text)
        self.assertIn("dist\\GDUTGradeMonitor\\GDUTGradeMonitor.exe", text)
        self.assertIn("dist\\GDUTGradeMonitor-Setup.exe", text)

    def test_readme_documents_portable_and_installer_releases(self):
        text = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("GDUTGradeMonitor-Setup.exe", text)
        self.assertIn("安装版", text)
        self.assertIn("便携版", text)
        self.assertIn("GDUTGradeMonitor-portable.zip", text)


if __name__ == "__main__":
    unittest.main()
