<#
.SYNOPSIS
    Однократный установщик WhisperX Portable для Windows.

.DESCRIPTION
    Скачивает портативный Python (python-build-standalone), ffmpeg,
    затем устанавливает WhisperX с выбранным вычислительным
    бекендом в самодостаточную папку runtime/ рядом с этим скриптом.

    После завершения вся папка репозитория портативна:
    скопируйте её на другой Windows-компьютер с драйвером NVIDIA и
    запустите WhisperX.bat - никакая системная установка не требуется.

.PARAMETER Backend
    cuda  : установить PyTorch со сборками CUDA 12.8 (по умолчанию, требует драйвер NVIDIA R555+)
    cpu   : установить PyTorch только под CPU
    auto  : выбрать cuda, если `nvidia-smi` доступен, иначе cpu

.PARAMETER PythonVersion
    Мажорная.минорная версия Python для скачивания. По умолчанию 3.12.
    WhisperX поддерживает 3.10..3.13.

.PARAMETER Force
    Стереть существующую папку runtime/ перед установкой.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File tools\setup.ps1
    powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Backend cpu
    powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Backend auto -Force
#>
[CmdletBinding()]
param(
    [ValidateSet('cuda', 'cpu', 'auto')]
    [string]$Backend = 'cuda',

    [ValidatePattern('^3\.(1[0-3])$')]
    [string]$PythonVersion = '3.12',

    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'  # сильно ускоряет Invoke-WebRequest

# Принудительный UTF-8 в консоли, чтобы кириллица не превращалась в мусор.
try {
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch {}

# ---------------------------------------------------------------
# Paths
# ---------------------------------------------------------------
$RepoRoot   = Split-Path -Parent $PSScriptRoot
$RuntimeDir = Join-Path $RepoRoot 'runtime'
$DownloadDir = Join-Path $RepoRoot 'downloads'
$PythonDir  = Join-Path $RuntimeDir 'python'
$VenvDir    = Join-Path $RuntimeDir 'venv'
$FfmpegDir  = Join-Path $RuntimeDir 'ffmpeg'
$ModelsDir  = Join-Path $RepoRoot   'models'
$OutputDir  = Join-Path $RepoRoot   'output'

function Write-Step($msg) { Write-Host ""; Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Info($msg) { Write-Host "    $msg" -ForegroundColor DarkGray }
function Write-Ok  ($msg) { Write-Host "    $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "    $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

# ---------------------------------------------------------------
# Architecture & backend resolution
# ---------------------------------------------------------------
if ([Environment]::Is64BitOperatingSystem -eq $false) {
    Fail "WhisperX Portable требует 64-битную Windows."
}

if ($Backend -eq 'auto') {
    $nvsmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
    if ($nvsmi) {
        Write-Info "nvidia-smi обнаружен -> устанавливаю бекенд CUDA."
        $Backend = 'cuda'
    } else {
        Write-Info "Драйвер NVIDIA не найден -> устанавливаю бекенд CPU."
        $Backend = 'cpu'
    }
}

Write-Step "Установщик WhisperX Portable"
Write-Info "Корень репо   : $RepoRoot"
Write-Info "Бекенд        : $Backend"
Write-Info "Версия Python : $PythonVersion"
Write-Info "Папка runtime : $RuntimeDir"

# ---------------------------------------------------------------
# Pre-flight: ffmpeg + tar checks
# ---------------------------------------------------------------
$tar = Get-Command tar.exe -ErrorAction SilentlyContinue
if (-not $tar) {
    Fail "tar.exe не найден. Windows 10 1803+ поставляется с bsdtar; обновите Windows или установите GNU tar."
}

# ---------------------------------------------------------------
# Optional clean
# ---------------------------------------------------------------
if ($Force -and (Test-Path $RuntimeDir)) {
    Write-Step "Удаляю существующую папку runtime (--Force)"
    Remove-Item -LiteralPath $RuntimeDir -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $RuntimeDir, $DownloadDir, $ModelsDir, $OutputDir | Out-Null

# ---------------------------------------------------------------
# 1. Resolve latest python-build-standalone release
# ---------------------------------------------------------------
function Get-PbsAssetUrl {
    param([string]$PyMinor)

    $latestUrl = 'https://raw.githubusercontent.com/astral-sh/python-build-standalone/latest-release/latest-release.json'
    Write-Info "Получаю метаданные python-build-standalone..."
    $latest = Invoke-RestMethod -UseBasicParsing -Uri $latestUrl

    # Pull the GitHub release JSON to enumerate assets.
    $releaseApi = "https://api.github.com/repos/astral-sh/python-build-standalone/releases/tags/$($latest.tag)"
    try {
        $release = Invoke-RestMethod -UseBasicParsing -Uri $releaseApi -Headers @{
            'User-Agent' = 'whisperx-portable-setup'
            'Accept'     = 'application/vnd.github+json'
        }
    } catch {
        Write-Warn "GitHub API недоступен."
        # Best-effort fallback. The exact patch version is not in the metadata file
        # so we cannot construct the URL without listing assets. Surface the error.
        Fail "Не удалось получить список артефактов python-build-standalone: $($_.Exception.Message)"
    }

    # Match: cpython-<full>+<tag>-x86_64-pc-windows-msvc-install_only.tar.gz
    # We want non-stripped install_only build.
    $pattern = "^cpython-$([regex]::Escape($PyMinor))\.\d+\+$([regex]::Escape($latest.tag))-x86_64-pc-windows-msvc-install_only\.tar\.gz$"
    $asset = $release.assets | Where-Object { $_.name -match $pattern } | Select-Object -First 1
    if (-not $asset) {
        Fail "Не найден Windows x86_64 install_only артефакт для Python $PyMinor в релизе $($latest.tag)."
    }
    Write-Info "Выбран: $($asset.name)"
    return [pscustomobject]@{
        Url      = $asset.browser_download_url
        FileName = $asset.name
        Tag      = $latest.tag
    }
}

function Invoke-Download {
    param(
        [string]$Url,
        [string]$OutFile,
        [string]$Description
    )

    if (Test-Path $OutFile) {
        Write-Info "$Description уже в кеше: $OutFile"
        return
    }
    Write-Info "Скачиваю $Description"
    Write-Info "  $Url"
    $tmp = "$OutFile.partial"
    if (Test-Path $tmp) { Remove-Item -LiteralPath $tmp -Force }
    Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $tmp
    Move-Item -LiteralPath $tmp -Destination $OutFile -Force
}

# ---------------------------------------------------------------
# 2. Download & extract Python
# ---------------------------------------------------------------
if (-not (Test-Path (Join-Path $PythonDir 'python.exe'))) {
    Write-Step "Устанавливаю портативный Python $PythonVersion"
    $pyAsset = Get-PbsAssetUrl -PyMinor $PythonVersion
    $pyArchive = Join-Path $DownloadDir $pyAsset.FileName
    Invoke-Download -Url $pyAsset.Url -OutFile $pyArchive -Description "Python $PythonVersion"

    $pyExtract = Join-Path $RuntimeDir '_python_extract'
    if (Test-Path $pyExtract) { Remove-Item -LiteralPath $pyExtract -Recurse -Force }
    New-Item -ItemType Directory -Path $pyExtract | Out-Null

    Write-Info "Распаковываю Python..."
    & tar.exe -xzf $pyArchive -C $pyExtract
    if ($LASTEXITCODE -ne 0) { Fail "tar не смог распаковать $pyArchive" }

    # Archive layout is: python/ (the actual install_only root)
    $extractedRoot = Join-Path $pyExtract 'python'
    if (-not (Test-Path $extractedRoot)) {
        Fail "Неожиданная структура архива $pyArchive"
    }
    Move-Item -LiteralPath $extractedRoot -Destination $PythonDir -Force
    Remove-Item -LiteralPath $pyExtract -Recurse -Force
    Write-Ok "Python установлен в $PythonDir"
} else {
    Write-Step "Python уже установлен в $PythonDir (пропускаю)"
}

$pyExe = Join-Path $PythonDir 'python.exe'
if (-not (Test-Path $pyExe)) { Fail "python.exe не найден в $pyExe" }

& $pyExe --version

# ---------------------------------------------------------------
# 3. Create venv
# ---------------------------------------------------------------
if (-not (Test-Path (Join-Path $VenvDir 'Scripts\python.exe'))) {
    Write-Step "Создаю venv в $VenvDir"
    & $pyExe -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { Fail "Не удалось создать venv" }
} else {
    Write-Step "venv уже существует в $VenvDir (пропускаю)"
}

$venvPy  = Join-Path $VenvDir 'Scripts\python.exe'
$venvPip = @($venvPy, '-m', 'pip')

Write-Step "Обновляю pip / setuptools / wheel"
& $venvPy -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { Fail "Не удалось обновить pip." }

# ---------------------------------------------------------------
# 4. Install PyTorch (backend-specific) then WhisperX
# ---------------------------------------------------------------
Write-Step "Устанавливаю PyTorch ($Backend)"
$torchSpec = 'torch~=2.8.0', 'torchaudio~=2.8.0', 'torchvision~=0.23.0'
switch ($Backend) {
    'cuda' { $torchIndex = 'https://download.pytorch.org/whl/cu128' }
    'cpu'  { $torchIndex = 'https://download.pytorch.org/whl/cpu' }
}

& $venvPy -m pip install --index-url $torchIndex --extra-index-url https://pypi.org/simple @torchSpec
if ($LASTEXITCODE -ne 0) { Fail "Установка torch не удалась (index=$torchIndex)." }

Write-Step "Устанавливаю WhisperX и зависимости"
& $venvPy -m pip install whisperx
if ($LASTEXITCODE -ne 0) { Fail "Установка whisperx не удалась." }

# ---------------------------------------------------------------
# 5. Download & extract ffmpeg
# ---------------------------------------------------------------
$ffmpegBin = Join-Path $FfmpegDir 'bin\ffmpeg.exe'
if (-not (Test-Path $ffmpegBin)) {
    Write-Step "Устанавливаю ffmpeg"
    $ffmpegUrl  = 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
    $ffmpegZip  = Join-Path $DownloadDir 'ffmpeg-release-essentials.zip'
    Invoke-Download -Url $ffmpegUrl -OutFile $ffmpegZip -Description 'сборка ffmpeg essentials'

    $ffmpegExtract = Join-Path $RuntimeDir '_ffmpeg_extract'
    if (Test-Path $ffmpegExtract) { Remove-Item -LiteralPath $ffmpegExtract -Recurse -Force }
    Expand-Archive -LiteralPath $ffmpegZip -DestinationPath $ffmpegExtract -Force

    $extractedFf = Get-ChildItem -LiteralPath $ffmpegExtract -Directory | Select-Object -First 1
    if (-not $extractedFf) { Fail "Неожиданная структура архива ffmpeg." }

    if (Test-Path $FfmpegDir) { Remove-Item -LiteralPath $FfmpegDir -Recurse -Force }
    Move-Item -LiteralPath $extractedFf.FullName -Destination $FfmpegDir -Force
    Remove-Item -LiteralPath $ffmpegExtract -Recurse -Force
    Write-Ok "ffmpeg установлен в $FfmpegDir"
} else {
    Write-Step "ffmpeg уже установлен (пропускаю)"
}

# ---------------------------------------------------------------
# 6. Persist install metadata
# ---------------------------------------------------------------
$metaPath = Join-Path $RuntimeDir 'install.json'
$meta = [pscustomobject]@{
    backend       = $Backend
    pythonVersion = $PythonVersion
    installedAt   = (Get-Date).ToString('o')
}
$meta | ConvertTo-Json | Set-Content -Path $metaPath -Encoding UTF8

# ---------------------------------------------------------------
# 7. Smoke tests
# ---------------------------------------------------------------
Write-Step "Проверяю установку"
$smokeScript = @'
import os, sys
print(f"python   : {sys.version.split()[0]}")
import torch
print(f"torch    : {torch.__version__}")
print(f"cuda     : available={torch.cuda.is_available()} count={torch.cuda.device_count()}")
import whisperx  # noqa: F401
import importlib.metadata as md
print(f"whisperx : {md.version('whisperx')}")
import faster_whisper, ctranslate2
print(f"f-whisper: {faster_whisper.__version__}")
print(f"ctrans2  : {ctranslate2.__version__}")
'@
$smokePath = Join-Path $env:TEMP 'whisperx_smoke.py'
$smokeScript | Set-Content -Path $smokePath -Encoding UTF8
& $venvPy -X utf8 $smokePath
$smokeRc = $LASTEXITCODE
Remove-Item -LiteralPath $smokePath -Force -ErrorAction SilentlyContinue
if ($smokeRc -ne 0) { Fail "Смоук-тест не прошёл (rc=$smokeRc)." }

Write-Step "Готово!"
Write-Host @"

Дальнейшие шаги:
  - Дважды кликните по WhisperX.bat, чтобы открыть GUI.
  - Или перетащите медиа-файл на WhisperX-CLI.bat для быстрой транскрипции из CLI.
  - Для диаризации говорящих создайте токен Hugging Face на
    https://huggingface.co/settings/tokens и примите соглашение на
    https://huggingface.co/pyannote/speaker-diarization-community-1
    Вставьте токен в поле "Токен Hugging Face" в GUI -
    он сохранится в config.json рядом с исполняемым файлом.
"@
