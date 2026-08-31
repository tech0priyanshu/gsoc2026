; PyASL Pipeline GUI Desktop Application Installer Setup
; Inno Setup Compiler Script
; 
; 1. Why it exists:
;    Defines Windows installer setup for packaging PyASL standalone executable
;    bundle into a standard Windows installer (.exe).
; 
; 2. Why its location was chosen:
;    Organized under installer/ as repository packaging infrastructure.
; 
; 3. Why this is preferable to previous implementation:
;    Separated completely from Python source code, with enhanced shortcut options,
;    registry registration metadata, uninstall entries, and icon resolution.
; 
; 4. Any trade-offs:
;    Requires Inno Setup compiler (ISCC.exe) on the host Windows system.

#define MyAppName "PyASL Pipeline GUI"
#define MyAppVersion "0.3.0"
#define MyAppPublisher "OSIPI TF2.2 Taskforce"
#define MyAppURL "https://github.com/elooff/PyASL"
#define MyAppExeName "PyASL-GUI.exe"

[Setup]
AppId={{D8C9B9A1-3F2E-4E1D-8A7B-9C0D1E2F3A4B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\PyASL
DisableProgramGroupPage=yes
LicenseFile=..\..\LICENSE
OutputBaseFilename=PyASL-GUI-v{#MyAppVersion}-Setup
OutputDir=..\release
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\assets\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\PyASL-GUI\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\dist\PyASL-GUI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\assets\icon.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\assets\icon.ico"

[Registry]
Root: HKCU; Subkey: "Software\PyASL"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\PyASL"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"
Root: HKCU; Subkey: "Software\PyASL"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
