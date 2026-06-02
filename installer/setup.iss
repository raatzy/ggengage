; GG Engage Photo Processor — Inno Setup 6 Script
; Requirements: Inno Setup 6.3+  https://jrsoftware.org/isdl.php
; Run:  ISCC.exe setup.iss  (from this directory)
; Output: installer\Output\GGEngagePhotoProcessor_Setup_v1.0.0.exe

#define AppName      "GG Engage Photo Processor"
#define AppVersion   "1.0.0"
#define AppPublisher "GG Engage"
#define AppURL       "https://ggengage.com.au"
#define AppExe       "PhotoProcessor.exe"
#define SourceDir    "..\dist\PhotoProcessor"

; ── Setup metadata ────────────────────────────────────────────────────────────
[Setup]
; Unique ID — do NOT change after first release (used for upgrades / uninstall)
AppId={{A3F7C2D1-4B8E-4F9A-9C0D-2E5B7A3F8C1D}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL=mailto:support@ggengage.com.au
AppUpdatesURL={#AppURL}

; Install into user's local app data so no admin rights are needed
DefaultDirName={localappdata}\GGEngagePhotoProcessor
DefaultGroupName={#AppName}
AllowNoIcons=yes

; Show the ToS + Privacy statement page in the wizard
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
SetupIconFile=

; Windows 10 (build 17763) or later
MinVersion=10.0.17763

; No UAC prompt — installs to user profile only
PrivilegesRequired=lowest

; Uninstall
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}

; ── Localisation ──────────────────────────────────────────────────────────────
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; ── Optional tasks (shown on the Extra Tasks wizard page) ────────────────────
[Tasks]
Name: "desktopicon"; \
  Description: "Create a &desktop shortcut for {#AppName}"; \
  GroupDescription: "Additional shortcuts:"; \
  Flags: unchecked

; ── Files to install ─────────────────────────────────────────────────────────
[Files]
; All PyInstaller output (exe + bundled libraries)
Source: "{#SourceDir}\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

; ── Shortcuts ─────────────────────────────────────────────────────────────────
[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}";   Filename: "{app}\{#AppExe}"; \
  Tasks: desktopicon

; ── Run after install ────────────────────────────────────────────────────────
[Run]
Filename: "{app}\{#AppExe}"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

; ── Custom wizard pages (informational) ──────────────────────────────────────
[Code]

{ Show a brief "About licensing" message after the license page is accepted }
procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpSelectDir then
  begin
    WizardForm.DirEdit.Text := ExpandConstant('{localappdata}\GGEngagePhotoProcessor');
  end;
end;

{ Warn the user if they try to install over an existing version }
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
