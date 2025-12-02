; Script generated for Finance Manager Pro
; SEE THE DOCUMENTATION FOR DETAILS ON CREATING INNO SETUP SCRIPT FILES!

#define MyAppName "Finance Manager Pro"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Santanu Ghosh"
#define MyAppURL "https://github.com/santanugh/FinanceManagerPro"
#define MyAppExeName "FinanceManagerPro.exe"

[Setup]
; NOTE: The value of AppId uniquely identifies this application.
; Do not use the same AppId value in installers for other applications.
; (To generate a new GUID, click Tools | Generate GUID inside Inno Setup)
AppId={{A3B4C5D6-E7F8-9012-3456-7890ABCDEF12}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; INSTALLATION DIRECTORY
; We use {userpf} (User Program Files) or {localappdata} to avoid Admin Permission issues during auto-updates.
DefaultDirName={localappdata}\{#MyAppName}
DisableDirPage=yes

; START MENU GROUP
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; OUTPUT SETTINGS
OutputDir=Output
OutputBaseFilename=FinanceManagerPro_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

; ICON SETTINGS (Make sure logo.ico is in assets folder)
SetupIconFile=assets\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; PERMISSIONS
; "lowest" allows installation without Admin password (preferred for auto-updaters)
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The Main Application File
Source: "dist\FinanceManagerPro.exe"; DestDir: "{app}"; Flags: ignoreversion

; NOTE: We do NOT need to include assets/updater.exe here because 
; PyInstaller already baked them inside FinanceManagerPro.exe!

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram, {#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent