@echo off
REM ============================================================
REM  Shared environment for WhisperX Portable launchers.
REM  Included from sibling .bat files via `call "%~dp0tools\env.bat"`.
REM ============================================================

REM Repo root = parent folder of this script.
for %%I in ("%~dp0..") do set "WHISPERX_HOME=%%~fI"

set "PYTHON_DIR=%WHISPERX_HOME%\runtime\python"
set "VENV_DIR=%WHISPERX_HOME%\runtime\venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "FFMPEG_BIN=%WHISPERX_HOME%\runtime\ffmpeg\bin"
set "TORCH_LIB=%VENV_DIR%\Lib\site-packages\torch\lib"

REM Make ffmpeg, venv Scripts and PyTorch cuDNN DLLs discoverable.
set "PATH=%FFMPEG_BIN%;%TORCH_LIB%;%VENV_DIR%\Scripts;%PATH%"

REM Force UTF-8 for filenames and stdout. WhisperX prints JSON/SRT in
REM multiple languages - this prevents garbled output in consoles with
REM legacy code pages.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM Pin Hugging Face / model caches inside the portable folder so that
REM nothing leaks into %USERPROFILE%.
set "WHISPERX_CACHE=%WHISPERX_HOME%\models"
set "HF_HOME=%WHISPERX_CACHE%\huggingface"
set "TRANSFORMERS_CACHE=%HF_HOME%\transformers"
set "TORCH_HOME=%WHISPERX_CACHE%\torch"
set "XDG_CACHE_HOME=%WHISPERX_CACHE%"

if not exist "%WHISPERX_CACHE%" mkdir "%WHISPERX_CACHE%" >nul 2>&1
if not exist "%HF_HOME%" mkdir "%HF_HOME%" >nul 2>&1
