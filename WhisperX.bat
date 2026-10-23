@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions
cd /d "%~dp0"

call "%~dp0tools\env.bat"

if not exist "%PYTHON_EXE%" (
    echo [WhisperX] Not installed yet.
    echo Run setup.bat first, then retry.
    pause
    exit /b 1
)

start "" "%PYTHON_EXE%" -X utf8 "%~dp0gui\app.py" %*
exit /b 0
