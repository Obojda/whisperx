@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

call "%~dp0tools\env.bat"

if not exist "%PYTHON_EXE%" (
    echo [WhisperX-CLI] Not installed yet.
    echo Run setup.bat first, then use this launcher.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo Drag and drop one or more audio/video files onto this script,
    echo or pass them as arguments:
    echo.
    echo   WhisperX-CLI.bat path\to\audio.mp3
    echo.
    echo Forwarding to whisperx --help:
    "%PYTHON_EXE%" -m whisperx --help
    pause
    exit /b 0
)

REM If the user did not pass --output_dir we route results into ./output.
set "HAS_OUTPUT_DIR="
for %%A in (%*) do (
    if /I "%%~A"=="--output_dir" set "HAS_OUTPUT_DIR=1"
    if /I "%%~A"=="-o"           set "HAS_OUTPUT_DIR=1"
)

set "EXTRA_ARGS="
if not defined HAS_OUTPUT_DIR (
    set "EXTRA_ARGS=--output_dir "%WHISPERX_HOME%\output""
)

"%PYTHON_EXE%" -m whisperx %* %EXTRA_ARGS%
set "RC=%ERRORLEVEL%"

echo.
echo Results saved to: %WHISPERX_HOME%\output
pause
exit /b %RC%
