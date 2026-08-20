; ============================================================
;  Mota's Downloader — Inno Setup Script
;  Requer Inno Setup 6+ com pacote de idioma pt-BR
; ============================================================

#define AppName      "Mota's Downloader"
#define AppVersion   "1.1.0"
#define AppPublisher "Tarcísio Mota"
#define AppURL       "https://github.com/tarcisiomota/MotasDownloader"
#define AppExeName   "MediaDownloader.exe"
#define SourceDir    "dist\MediaDownloader"

[Setup]
AppId={{E4A7B3C2-5D6E-7F8A-9B0C-1D2E3F4A5B6C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases

; Destino padrão: Arquivos de Programas do usuário (sem precisar de admin)
DefaultDirName={autopf}\MotasDownloader
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Licença exibida na segunda tela do wizard
LicenseFile=LICENSE.txt

; Saída
OutputDir=installer_output
OutputBaseFilename=MotasDownloader_Setup_v{#AppVersion}
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName}

; Compressão máxima (LZMA2 ultra)
Compression=lzma2/ultra64
SolidCompression=yes

; Visual moderno
WizardStyle=modern
WizardSizePercent=120

; Permite rodar sem privilégios de administrador (instala por usuário)
; Mas oferece opção de instalar para todos se rodar como admin
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Somente 64 bits
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Versão mínima do Windows: 10
MinVersion=10.0

; Imagens do wizard (geradas pelo build_installer.bat)
WizardImageFile=assets\wizard_banner.bmp
WizardSmallImageFile=assets\wizard_small.bmp

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[CustomMessages]
brazilianportuguese.WelcomeLabel1=Bem-vindo ao assistente de instalação do {#AppName}
brazilianportuguese.WelcomeLabel2=Este assistente irá guiá-lo pela instalação do {#AppName} {#AppVersion}.%n%nFecha outros aplicativos antes de continuar.%n%nClique em Avançar para continuar.
brazilianportuguese.FinishedLabel=A instalação do {#AppName} foi concluída com sucesso.%n%nClique em Concluir para fechar este assistente.

[Tasks]
; Atalho na área de trabalho (selecionado por padrão)
Name: "desktopicon"; \
  Description: "Criar atalho na Área de Trabalho"; \
  GroupDescription: "Atalhos adicionais:"; \
  Flags: checkedonce

; Executar ao iniciar o Windows (não selecionado por padrão)
Name: "startupicon"; \
  Description: "Iniciar automaticamente com o Windows"; \
  GroupDescription: "Atalhos adicionais:"; \
  Flags: unchecked

[Files]
; Todos os arquivos do build PyInstaller
Source: "{#SourceDir}\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Menu Iniciar
Name: "{group}\{#AppName}"; \
  Filename: "{app}\{#AppExeName}"; \
  IconFilename: "{app}\{#AppExeName}"

Name: "{group}\Desinstalar {#AppName}"; \
  Filename: "{uninstallexe}"

; Área de trabalho (só se a task foi marcada)
Name: "{autodesktop}\{#AppName}"; \
  Filename: "{app}\{#AppExeName}"; \
  IconFilename: "{app}\{#AppExeName}"; \
  Tasks: desktopicon

; Inicialização do Windows (só se a task foi marcada)
Name: "{autostartup}\{#AppName}"; \
  Filename: "{app}\{#AppExeName}"; \
  Tasks: startupicon

[Registry]
; Registra no "Adicionar ou Remover Programas"
Root: HKA; Subkey: "Software\{#AppPublisher}\{#AppName}"; \
  ValueType: string; ValueName: "InstallPath"; \
  ValueData: "{app}"; Flags: uninsdeletekey

Root: HKA; Subkey: "Software\{#AppPublisher}\{#AppName}"; \
  ValueType: string; ValueName: "Version"; \
  ValueData: "{#AppVersion}"; Flags: uninsdeletekey

[Run]
; Oferece abrir o app ao clicar em Concluir
Filename: "{app}\{#AppExeName}"; \
  Description: "Iniciar {#AppName} agora"; \
  Flags: nowait postinstall skipifsilent unchecked

[UninstallRun]
; Fecha o app antes de desinstalar
Filename: "{cmd}"; \
  Parameters: "/c taskkill /f /im {#AppExeName} 2>nul"; \
  Flags: runhidden; \
  RunOnceId: "KillBeforeUninstall"

[UninstallDelete]
; Remove pasta inteira ao desinstalar
Type: filesandordirs; Name: "{app}"

[Code]
// Verifica se o app já está rodando antes de instalar
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  // Tenta fechar instância anterior
  Exec(ExpandConstant('{cmd}'), '/c taskkill /f /im {#AppExeName} 2>nul',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;
