@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions
cd /d "%~dp0"

REM ============================================================
REM  WhisperX Portable - one-time installer

REM  All user-facing text lives in the PowerShell script so we
REM  do not have to fight cmd.exe codepage issues with Cyrillic.
REM  Downloads portable Python, ffmpeg and installs WhisperX into
REM  ./runtime/. After it finishes you can copy the whole folder
REM  to any Windows box with an NVIDIA driver and run WhisperX.bat.
REM ============================================================

where powershell.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] powershell.exe not found, but it is required.
    echo PowerShell ships with every supported Windows release.
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if %RC% NEQ 0 (
    echo [setup.bat] Installation failed with exit code %RC%.
) else (
    echo [setup.bat] Installation finished. Run WhisperX.bat to open the GUI.
)
echo.
pause
exit /b %RC%
