@echo off
setlocal EnableDelayedExpansion
title GG Engage Photo Processor — Build Script

echo ============================================================
echo  GG Engage Photo Processor  ^|  Windows Installer Builder
echo ============================================================
echo.

REM ── Check Python ─────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.11+ from https://python.org
    pause & exit /b 1
)

REM ── Install / upgrade Python dependencies ────────────────────
echo [1/3] Installing Python dependencies...
pip install --quiet --upgrade pyinstaller Pillow piexif geopy
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause & exit /b 1
)
echo       Done.
echo.

REM ── Build standalone exe with PyInstaller ────────────────────
echo [2/3] Building executable with PyInstaller...
cd /d "%~dp0.."

pyinstaller ^
    --onedir ^
    --windowed ^
    --name PhotoProcessor ^
    --hidden-import geopy.geocoders.nominatim ^
    --hidden-import PIL._tkinter_finder ^
    --hidden-import piexif ^
    --clean ^
    process_photos.py

if errorlevel 1 (
    echo ERROR: PyInstaller failed. See output above.
    pause & exit /b 1
)
echo       Done.  Output: dist\PhotoProcessor\
echo.

REM ── Build installer with Inno Setup ──────────────────────────
echo [3/3] Building installer with Inno Setup 6...

REM Try common Inno Setup install locations
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
echo        Download it from https://jrsoftware.org/isdl.php then re-run.
pause & exit /b 1

:found_iscc
echo       Using: !ISCC!
!ISCC! "%~dp0setup.iss"
if errorlevel 1 (
    echo ERROR: Inno Setup compilation failed. See output above.
    pause & exit /b 1
)

echo.
echo ============================================================
echo  BUILD COMPLETE
echo  Installer: installer\Output\GGEngagePhotoProcessor_Setup_v1.0.0.exe
echo ============================================================
echo.
pause
