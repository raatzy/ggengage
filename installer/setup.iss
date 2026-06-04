; Photo GeoTager — Inno Setup 6 Script
; Requirements: Inno Setup 6.3+  https://jrsoftware.org/isdl.php
; Run:  ISCC.exe setup.iss  (from installer\ directory)

#define AppName      "Photo GeoTager"
#define AppVersion   "1.0.0"
#define AppPublisher "MJS App Origins"
#define AppURL       "https://mjsapporigins.com.au"
#define AppExe       "PhotoGeoTager.exe"
#define SourceDir    "..\dist\PhotoGeoTager"
#define DeepLink     "geotager"

; ── Setup metadata ────────────────────────────────────────────────────────────
[Setup]
AppId={{C6A3D5E9-8F4B-4C2D-7E1A-2B9D6F3E8C4A}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL=mailto:support@mjsapporigins.com.au
AppUpdatesURL={#AppURL}
DefaultDirName={localappdata}\PhotoGeoTager
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=tos.txt
OutputDir=Output
OutputBaseFilename=PhotoGeoTager_Setup_v{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
MinVersion=10.0.17763
PrivilegesRequired=lowest
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}

; ── Localisation ──────────────────────────────────────────────────────────────
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── Optional tasks ────────────────────────────────────────────────────────────
[Tasks]
Name: "desktopicon"; \
  Description: "Create a &desktop shortcut for {#AppName}"; \
  GroupDescription: "Additional shortcuts:"; \
  Flags: unchecked

; ── Files ─────────────────────────────────────────────────────────────────────
[Files]
Source: "{#SourceDir}\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; ── Shortcuts ─────────────────────────────────────────────────────────────────
[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}";   Filename: "{app}\{#AppExe}"; \
  Tasks: desktopicon

; ── Deep-link URL scheme: geotager://activate/<key> ──────────────────────────
; Clicking "Activate Now" in the licence email opens the app directly.
[Registry]
Root: HKCU; Subkey: "Software\Classes\{#DeepLink}"; \
  ValueType: string; ValueName: ""; \
  ValueData: "Photo GeoTager"; \
  Flags: uninsdeletekey

Root: HKCU; Subkey: "Software\Classes\{#DeepLink}"; \
  ValueType: string; ValueName: "URL Protocol"; ValueData: ""

Root: HKCU; Subkey: "Software\Classes\{#DeepLink}\DefaultIcon"; \
  ValueType: string; ValueName: ""; \
  ValueData: "{app}\{#AppExe},0"

Root: HKCU; Subkey: "Software\Classes\{#DeepLink}\shell\open\command"; \
  ValueType: string; ValueName: ""; \
  ValueData: """{app}\{#AppExe}"" ""%1"""

; ── Launch after install ──────────────────────────────────────────────────────
[Run]
Filename: "{app}\{#AppExe}"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

; ── Uninstall note ────────────────────────────────────────────────────────────
; The three hidden licence/trial storage locations (registry key, jump-list
; file, Explorer cache file) are intentionally NOT removed on uninstall so
; that reinstalling cannot reset the free-trial counter.
; The geotager:// URL scheme IS removed (Flags: uninsdeletekey above).
