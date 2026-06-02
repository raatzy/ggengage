; GG Engage Photo Processor — Inno Setup 6 Script
; Requirements: Inno Setup 6.3+  https://jrsoftware.org/isdl.php
; Run:  ISCC.exe setup.iss  (from the installer\ directory)
; Output: installer\Output\GGEngagePhotoProcessor_Setup_v1.0.0.exe

#define AppName      "GG Engage Photo Processor"
#define AppVersion   "1.0.0"
#define AppPublisher "GG Engage"
#define AppURL       "https://ggengage.com.au"
#define AppExe       "PhotoProcessor.exe"
#define SourceDir    "..\dist\PhotoProcessor"

; ── Setup metadata ────────────────────────────────────────────────────────────
[Setup]
; Do NOT change AppId after first release — used for upgrades and uninstall
AppId={{A3F7C2D1-4B8E-4F9A-9C0D-2E5B7A3F8C1D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL=mailto:support@ggengage.com.au
AppUpdatesURL={#AppURL}

; Install into user's local app data — no UAC prompt needed
DefaultDirName={localappdata}\GGEngagePhotoProcessor
DefaultGroupName={#AppName}
AllowNoIcons=yes

; ToS + Privacy Statement shown before the user can proceed
LicenseFile=tos.txt

; Output
OutputDir=Output
OutputBaseFilename=GGEngagePhotoProcessor_Setup_v{#AppVersion}

; Compression
Compression=lzma2/ultra64
SolidCompression=yes

; Appearance
WizardStyle=modern
WizardSizePercent=110

; Windows 10 (1809 / build 17763) or later
MinVersion=10.0.17763

; No UAC elevation required
PrivilegesRequired=lowest

; Uninstall display
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}

; ── Localisation ──────────────────────────────────────────────────────────────
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── Optional install tasks ────────────────────────────────────────────────────
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

; ── Launch after install ──────────────────────────────────────────────────────
[Run]
Filename: "{app}\{#AppExe}"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

; ── Uninstall ─────────────────────────────────────────────────────────────────
; NOTE: The three hidden license/trial storage locations (registry key, jump-list
; file, Explorer cache file) are intentionally NOT listed here. They must survive
; uninstall so that reinstalling cannot reset the free trial. The only thing
; removed is the application files themselves.
[UninstallDelete]
; Nothing extra to remove — app files in {app} are removed automatically
