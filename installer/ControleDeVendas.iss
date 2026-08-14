#define MyAppName "Vendas PRO - Controle de Vendas"
#define MyAppVersion "1.6.0"
#define MyAppPublisher "Vendas L de S"
#define MyAppExeName "ControleDeVendas.exe"

[Setup]
AppId={{7A0557B0-EC70-47D9-A2E4-6ACF5F2D87E1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Vendas PRO
DefaultGroupName=Vendas PRO
DisableProgramGroupPage=yes
OutputDir=..\outputs
OutputBaseFilename=ControleDeVendas-Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=force
RestartApplications=yes
SetupLogging=yes
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductName={#MyAppName}
VersionInfoCompany={#MyAppPublisher}
SetupIconFile=..\assets\app_icon.ico

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "..\outputs\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion restartreplace

[Icons]
Name: "{autoprograms}\Vendas PRO"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Vendas PRO"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o Vendas PRO"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

; O banco fica fora da pasta do programa, em
; %LOCALAPPDATA%\ControleDeVendas. Ele nunca é removido pelo instalador.
