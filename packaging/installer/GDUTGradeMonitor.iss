#define SourceRoot "..\.."
#define AppExeName "GDUTGradeMonitor.exe"
#define AppVersion "0.2.1"

[Setup]
AppId={{9D32DEAF-2BA9-4F75-8B4F-6FB6998B8D20}
AppName=GDUT 成绩提醒
AppVersion={#AppVersion}
AppVerName=GDUT 成绩提醒 {#AppVersion}
AppPublisher=Chen-Dll
AppPublisherURL=https://github.com/Chen-Dll
AppSupportURL=https://github.com/Chen-Dll/GDUT-Grade-Monitor/issues
DefaultDirName={localappdata}\Programs\GDUTGradeMonitor
DefaultGroupName=GDUT 成绩提醒
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupIconFile={#SourceRoot}\gdut_grade_monitor\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
LicenseFile={#SourceRoot}\LICENSE
InfoBeforeFile={#SourceRoot}\packaging\installer\InfoBefore.txt
InfoAfterFile={#SourceRoot}\packaging\installer\InfoAfter.txt
OutputDir={#SourceRoot}\dist
OutputBaseFilename=GDUTGradeMonitor-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
VersionInfoCompany=Chen-Dll
VersionInfoDescription=GDUT read-only grade reminder
VersionInfoVersion={#AppVersion}

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl,{#SourceRoot}\packaging\installer\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: unchecked

[Files]
Source: "{#SourceRoot}\dist\GDUTGradeMonitor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\GDUT 成绩提醒"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\GDUT 成绩提醒"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "启动 GDUT 成绩提醒"; Flags: nowait postinstall skipifsilent
