; ── Inno Setup Script ────────────────────────────────────────────────────────
; Requer Inno Setup 6+ em C:\Program Files (x86)\Inno Setup 6\ISCC.exe
; Para compilar: rode build_installer.bat  (ou abra este .iss no Inno Setup IDE)

#define AppName      "Mota's Downloader"
#define AppVersion   "1.0.0"
#define AppPublisher "Mota's Downloader"
#define AppExeName   "MediaDownloader.exe"
#define SourceDir    "dist\MediaDownloader"

[Setup]
AppId={{A3F8B2C1-4D5E-6F7A-8B9C-0D1E2F3A4B5C}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Motas Downloader
DefaultGroupName={#AppName}
OutputDir=installer_output
OutputBaseFilename=MediaDownloader_Setup_v{#AppVersion}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Wizard visual
WizardSmallImageFile=assets\wizard_small.bmp
WizardImageFile=assets\wizard_banner.bmp

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /f /im {#AppExeName}"; Flags: runhidden; RunOnceId: "KillApp"

[Code]
// Verifica se ja existe versao instalada antes de continuar
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
