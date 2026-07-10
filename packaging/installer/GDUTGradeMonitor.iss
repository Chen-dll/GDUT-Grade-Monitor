#define SourceRoot "..\.."
#define AppExeName "GDUTGradeMonitor.exe"
#define AppVersion "0.3.9"

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

[Icons]
Name: "{autoprograms}\GDUT 成绩提醒"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\GDUT 成绩提醒"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "启动 GDUT 成绩提醒"; Flags: nowait postinstall skipifsilent

[Code]
var
  RemoveLocalDataOnUninstall: Boolean;

function ContainsInvalidPathChars(Value: String): Boolean;
var
  I: Integer;
  Ch: String;
begin
  Result := False;
  for I := 1 to Length(Value) do
  begin
    Ch := Copy(Value, I, 1);
    if Pos(Ch, '<>"|?*') > 0 then
    begin
      Result := True;
      Exit;
    end;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  RemoveLocalDataOnUninstall :=
    MsgBox(
      '是否同时删除本地配置、Cookie、成绩快照和日志？' + #13#10 + #13#10 +
      '选择“是”会删除：' + ExpandConstant('{userprofile}\.gdut-grade-monitor') + #13#10 +
      '选择“否”只卸载程序，保留本地数据，之后重装可以继续使用。' + #13#10 + #13#10 +
      '注意：Windows 凭据管理器中的教务密码和通知密钥不会由卸载器删除。',
      mbConfirmation,
      MB_YESNO
    ) = IDYES;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and RemoveLocalDataOnUninstall then
  begin
    DeleteFile(ExpandConstant('{userstartup}\GDUT Grade Monitor.vbs'));
    DelTree(ExpandConstant('{userprofile}\.gdut-grade-monitor'), True, True, True);
  end;
end;

function HasInvalidColon(Value: String): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to Length(Value) do
  begin
    if Copy(Value, I, 1) = ':' then
    begin
      if I <> 2 then
      begin
        Result := True;
        Exit;
      end;
    end;
  end;
end;

function LooksLikeAbsoluteInstallDir(Value: String): Boolean;
begin
  Result := ((Length(Value) >= 3) and (Copy(Value, 2, 2) = ':\')) or
            ((Length(Value) >= 5) and (Copy(Value, 1, 2) = '\\'));
end;

function ValidateInstallDir(Value: String; var ErrorMessage: String): Boolean;
var
  Drive: String;
begin
  Result := False;
  Value := Trim(Value);

  if Value = '' then
  begin
    ErrorMessage := '安装路径不能为空。请选择一个有效文件夹。';
    Exit;
  end;

  if ContainsInvalidPathChars(Value) or HasInvalidColon(Value) then
  begin
    ErrorMessage := '安装路径格式不正确。路径不能包含 < > " | ? * 等字符，冒号只能用于盘符，例如 C:\Apps\GDUTGradeMonitor。';
    Exit;
  end;

  if not LooksLikeAbsoluteInstallDir(Value) then
  begin
    ErrorMessage := '安装路径格式不正确。请使用完整路径，例如 C:\Apps\GDUTGradeMonitor。';
    Exit;
  end;

  Drive := ExtractFileDrive(Value);
  if (Length(Drive) = 2) and (Copy(Drive, 2, 1) = ':') and (not DirExists(Drive + '\')) then
  begin
    ErrorMessage := '安装路径所在的磁盘不存在：' + Drive;
    Exit;
  end;

  Result := True;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Dir: String;
  ErrorMessage: String;
begin
  Result := True;

  if CurPageID = wpSelectDir then
  begin
    Dir := WizardDirValue;
    if not ValidateInstallDir(Dir, ErrorMessage) then
    begin
      MsgBox(ErrorMessage, mbError, MB_OK);
      Result := False;
      Exit;
    end;

    if not DirExists(Dir) then
    begin
      MsgBox('目录不存在，安装程序将自动创建：' + #13#10 + Dir, mbInformation, MB_OK);
      if not ForceDirectories(Dir) then
      begin
        MsgBox('无法创建安装目录。请检查路径是否正确，或选择一个你有权限写入的位置。', mbError, MB_OK);
        Result := False;
        Exit;
      end;
    end;
  end;
end;
