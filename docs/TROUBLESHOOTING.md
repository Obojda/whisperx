# Решение проблем

## `setup.bat` падает

### `tar.exe was not found`

В Windows 10 1803+ `tar.exe` лежит в `C:\Windows\System32\`. Если система старее — поставьте GNU tar (например, из Git for Windows), убедитесь, что он есть в `PATH`, и снова запустите `setup.bat`.

### `Could not list python-build-standalone assets`

Установщик берёт свежую сборку портативного Python с GitHub. За прокси задайте `HTTPS_PROXY` перед запуском `setup.bat`. Если GitHub недоступен — можно заранее положить скачанный архив в `downloads/` и запустить с `-Force`.

### Антивирус блокирует загрузку

Некоторые антивирусы кладут в карантин CUDA-сборку PyTorch из-за DLL cuDNN. Добавьте папку проекта в исключения и запустите `setup.bat /Force`.

## Ошибки выполнения (GUI / CLI)

### `Could not load library cudnn_cnn_infer64_8.dll` (или похожая)

Драйвер NVIDIA старее, чем ожидают CUDA 12.8-сборки. Варианты:

1. Обновите драйвер до R555 или новее с [nvidia.com/Download](https://www.nvidia.com/Download/index.aspx), либо
2. Переустановите с CPU-бекендом:
   ```bat
   powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Backend cpu -Force
   ```

### `RuntimeError: CUDA out of memory`

Выберите в GUI конфигурацию поменьше:

- `compute_type` → `int8`
- `batch_size` → `4` или `2`
- `model` → `medium` или `small`

Модель `large-v3` при настройках по умолчанию требует ~10 ГБ VRAM.

### `Could not load model … from …huggingface…`

- Для диаризации: убедитесь, что вы приняли пользовательское соглашение на <https://huggingface.co/pyannote/speaker-diarization-community-1> и вставили токен в GUI.
- Для моделей выравнивания: некоторые wav2vec2 на Hugging Face — gated. Откройте карточку модели и примите соглашение.
- Недокачанная модель может «отравить» кеш: удалите `models/huggingface/hub/<repo>/blobs/*.partial` и повторите.

### Тишина в результате или транскрипция «гудения»

WhisperX требует, чтобы файл декодировался через ffmpeg. Проверьте `ffprobe input.ext` из встроенного ffmpeg:

```bat
call tools\env.bat
ffprobe path\to\file.ext
```

Если ffprobe тоже падает — кодек нестандартный, сначала перекодируйте файл.

### Окно GUI не появляется

Проверьте наличие `runtime/install.json`; если его нет, запустите `setup.bat`. Если он есть — запустите GUI из консоли, чтобы увидеть traceback:

```bat
call tools\env.bat
"%PYTHON_EXE%" -X utf8 gui\app.py
```

### Ошибка импорта `tcl/tk`

Портативная сборка Python включает Tk по умолчанию. Если вы вручную заменили `runtime/python/` на сборку без Tk — запустите `setup.bat /Force`.

## Диагностика

### Показать, что установлено

```bat
call tools\env.bat
"%PYTHON_EXE%" -m pip list
"%PYTHON_EXE%" -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

### Полный сброс

```bat
powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Force
```

Это сотрёт `runtime/` (Python, venv, ffmpeg), но сохранит `models/` и `config.json`.

### Очистить кеш моделей

```bat
rmdir /s /q models
```

Модели будут заново скачаны при следующем использовании.

## Куда обращаться за помощью

Проблемы из апстрима WhisperX (качество транскрипции, поддержка языков и т.п.) — заводите issue в [m-bain/whisperX](https://github.com/m-bain/whisperX).

Проблемы, специфичные для этой портативной сборки (setup.bat, лаунчеры, GUI), — открывайте issue здесь.
