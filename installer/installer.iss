; Codex Account Manager 当前用户 Inno Setup 安装器
#define AppName "Codex Account Manager"
#define AppPublisher "Codex Account Manager"
#define AppExeName "CodexAccountManager.exe"
#ifndef AppVersion
#define AppVersion "1.0.0"
#endif

[Setup]
AppId={{C2B27F93-4E23-4EA6-9B88-0E8E2A5F2D0B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={localappdata}\Programs\CodexAccountManager
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\release
OutputBaseFilename=CodexAccountManager-{#AppVersion}-Setup-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\resources\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Files]
Source: "..\dist\CodexAccountManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "启动 {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 不删除 %LOCALAPPDATA%\CodexAccountManager，账号数据默认保留。
Type: filesandordirs; Name: "{app}"
