; GG Engage Photo Processor — Inno Setup 6 Script
; Requirements: Inno Setup 6.3+  https://jrsoftware.org/isdl.php
; Run:  ISCC.exe setup.iss  (from installer\ directory)

#define AppName      "GG Engage Photo Processor"
#define AppVersion   "1.0.0"
#define AppPublisher "GG Engage"
#define AppURL       "https://ggengage.com.au"
#define AppExe       "PhotoProcessor.exe"
#define SourceDir    "..\dist\PhotoProcessor"
#define DeepLink     "ggphoto"

; ── Setup metadata ────────────────────────────────────────────────────────────
[Setup]
AppId={{A3F7C2D1-4B8E-4F9A-9C0D-2E5B7A3F8C1D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL=mailto:support@ggengage.com.au
AppUpdatesURL={#AppURL}
DefaultDirName={localappdata}\GGEngagePhotoProcessor
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=tos.txt
OutputDir=Output
OutputBaseFilename=GGEngagePhotoProcessor_Setup_v{#AppVersion}
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

; ── Deep-link URL scheme: ggphoto://activate/<key> ───────────────────────────
; Clicking "Activate Now" in the license email opens the app directly
; with the key pre-filled, so the customer never has to type it.
[Registry]
Root: HKCU; Subkey: "Software\Classes\{#DeepLink}"; \
  ValueType: string; ValueName: ""; \
  ValueData: "GG Engage Photo Processor"; \
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
; The three hidden license/trial storage locations (registry COM key, jump-list
; file, Explorer cache file) are intentionally NOT removed on uninstall so that
; reinstalling the app cannot reset the free trial counter.
; The ggphoto:// URL scheme IS removed (Flags: uninsdeletekey above).
