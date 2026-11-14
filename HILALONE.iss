; ============================================================================
; HILALONE v1.0.0 — Skrip Windows Installer (Inno Setup 7)
; Target output: release\HILALONE_Setup.exe
;
; Catatan:
; - Jalankan build ONE-DIR (`build_windows.bat`) dan uji `dist\HILALONE\HILALONE.exe`
;   terlebih dahulu sebelum mengompilasi skrip ini dengan Inno Setup 7 (ISCC.exe).
; - Mendukung instalasi per-user (`PrivilegesRequired=lowest`) tanpa hak Administrator.
; - Data pengguna (%LOCALAPPDATA%\HILALONE) TIDAK dihapus otomatis saat uninstall.
; ============================================================================

#define MyAppName "HILALONE"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "HILALONE Project"
#define MyAppDescription "Automated Hilal Image Processing"
#define MyAppExeName "HILALONE.exe"
#define MyAppDiagName "HILALONE_Diagnostic.bat"

[Setup]
AppId={{8D6B59C2-4F4B-4D17-9E2E-7A4D53D1B001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion=1.0.0.0
VersionInfoDescription={#MyAppDescription}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=release
OutputBaseFilename=HILALONE_Setup
SetupIconFile=assets\branding\hilalone_app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Buat ikon pintasan di Desktop (Create a &desktop icon)"; GroupDescription: "Pintasan Tambahan:"; Flags: unchecked

[Files]
Source: "dist\HILALONE\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\assets\branding\hilalone_app_icon.ico"; Comment: "{#MyAppDescription}"
Name: "{autoprograms}\{#MyAppName}\{#MyAppName} (Diagnostic Mode)"; Filename: "{app}\{#MyAppDiagName}"; Comment: "Jalankan HILALONE dengan log diagnostik"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\_internal\assets\branding\hilalone_app_icon.ico"; Tasks: desktopicon; Comment: "{#MyAppDescription}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Jalankan {#MyAppName} sekarang"; Flags: nowait postinstall skipifsilent
