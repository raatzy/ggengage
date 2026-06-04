@echo off
setlocal EnableDelayedExpansion
title GG Engage Photo Processor — Build Script

echo ============================================================
echo  GG Engage Photo Processor  ^|  Windows Installer Builder
echo ============================================================
echo.

REM ── Verify Python ────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo        Install Python 3.11+ from https://python.org
    echo        Tick "Add Python to PATH" during setup.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('python --version') do echo Using %%v
echo.

REM ── Install / upgrade Python dependencies ────────────────────
echo [1/3] Installing Python dependencies...
pip install --quiet --upgrade ^
    pyinstaller ^
    Pillow ^
    piexif ^
    geopy ^
    cryptography ^
    requests
if errorlevel 1 (
    echo ERROR: pip install failed. Check your internet connection.
    pause & exit /b 1
)
echo       Done.
echo.

REM ── Build standalone exe with PyInstaller ────────────────────
echo [2/3] Building standalone exe with PyInstaller...
cd /d "%~dp0.."

REM Use an icon if one exists at installer\icon.ico
set ICON_ARG=
if exist "%~dp0icon.ico" set ICON_ARG=--icon="%~dp0icon.ico"

pyinstaller ^
    --onedir ^
    --windowed ^
    --name PhotoProcessor ^
    %ICON_ARG% ^
    --hidden-import geopy.geocoders.nominatim ^
    --hidden-import geopy.geocoders ^
    --hidden-import PIL._tkinter_finder ^
    --hidden-import piexif ^
    --hidden-import winreg ^
    --hidden-import cryptography ^
    --hidden-import cryptography.fernet ^
    --hidden-import cryptography.hazmat.primitives.kdf.hkdf ^
    --hidden-import cryptography.hazmat.primitives.hashes ^
    --hidden-import cryptography.hazmat.backends ^
    --hidden-import requests ^
    --hidden-import urllib3 ^
    --clean ^
    --noconfirm ^
    process_photos.py

if errorlevel 1 (
    echo ERROR: PyInstaller failed. See output above.
    pause & exit /b 1
)
echo       Done.  Output: dist\PhotoProcessor\
echo.

REM ── Build installer with Inno Setup 6 ────────────────────────
echo [3/3] Building installer with Inno Setup 6...

set ISCC=
for %%P in (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
    "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
) do (
    if exist %%P (
        set ISCC=%%P
        goto :found_iscc
    )
)
echo ERROR: Inno Setup 6 not found.
echo        Download free from: https://jrsoftware.org/isdl.php
pause & exit /b 1

:found_iscc
echo       Using: !ISCC!
!ISCC! "%~dp0setup.iss"
if errorlevel 1 (
    echo ERROR: Inno Setup compilation failed.
    pause & exit /b 1
)

echo.
echo ============================================================
echo  BUILD COMPLETE
echo.
echo  Installer: installer\Output\GGEngagePhotoProcessor_Setup_v1.0.0.exe
echo.
echo  To build a new license key:
echo    cd installer
echo    python keygen.py 1
echo.
echo  REMINDER: Never distribute server\ or installer\keygen.py
echo ============================================================
echo.
pause
