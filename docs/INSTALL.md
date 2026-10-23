# Руководство по установке

## Кратко

```bat
setup.bat
```

Запускает установку по умолчанию: Python 3.12 + PyTorch с CUDA 12.8 + WhisperX + ffmpeg.

## Бекенды

Установщик принимает параметр `/Backend`:

| Команда | Результат |
| --- | --- |
| `setup.bat` (без аргументов) | Сборки CUDA 12.8 — нужен драйвер NVIDIA R555+ |
| `powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Backend cpu` | Сборки PyTorch только под CPU |
| `powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Backend auto` | `cuda`, если `nvidia-smi` работает, иначе `cpu` |
| `powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Backend cuda -PythonVersion 3.11` | использовать Python 3.11 вместо 3.12 |
| `powershell -ExecutionPolicy Bypass -File tools\setup.ps1 -Force` | стереть `runtime/` и переустановить |

## Что делает `setup.bat`

1. Читает метаданные последнего релиза `python-build-standalone`.
2. Скачивает `cpython-3.X.Y+TAG-x86_64-pc-windows-msvc-install_only.tar.gz` и распаковывает в `runtime/python/`.
3. Создаёт virtualenv в `runtime/venv/`.
4. Обновляет pip / setuptools / wheel.
5. Ставит PyTorch с выбранного индекса бекенда (`https://download.pytorch.org/whl/cu128` или `/cpu`).
6. `pip install whisperx` с PyPI — это подтягивает `faster-whisper`, `ctranslate2`, `pyannote-audio`, `transformers` и пр.
7. Скачивает `ffmpeg-release-essentials.zip` с gyan.dev и распаковывает в `runtime/ffmpeg/`.
8. Запускает смоук-тест: импортирует torch и whisperx, печатает флаг доступности CUDA.

Установщик идемпотентен — повторный запуск пропускает уже установленные компоненты. Используйте `-Force`, чтобы начать с нуля.

## Сетевые особенности

`setup.bat` обращается по HTTPS к:

- `raw.githubusercontent.com`
- `api.github.com`
- `github.com` и `objects.githubusercontent.com` (загрузки релизов)
- `download.pytorch.org`
- `pypi.org` и `files.pythonhosted.org`
- `huggingface.co` и `cdn-lfs.huggingface.co` (когда GUI качает модель)
- `www.gyan.dev` и `github.com` (редирект ffmpeg)

За корпоративным прокси перед запуском `setup.bat` задайте `HTTP_PROXY` / `HTTPS_PROXY`.

## Использование диска

Примерные размеры после установки:

| Путь | Размер |
| --- | --- |
| `runtime/python/` | ~150 МБ |
| `runtime/venv/` (CUDA) | ~3.5 ГБ |
| `runtime/venv/` (CPU)  | ~700 МБ |
| `runtime/ffmpeg/` | ~150 МБ |
| `models/` после первой транскрипции с `large-v3` | ~3 ГБ |

## Обновление WhisperX

Чтобы подтянуть новую версию `whisperx` без переустановки:

```bat
call tools\env.bat
"%PYTHON_EXE%" -m pip install --upgrade whisperx
```

Либо полная переустановка: `setup.bat /Force` (PowerShell ожидает `-Force`).

## Перенос на другую машину

После успешного `setup.bat` вся папка (включая `runtime/`, `models/` и `config.json`) портативна. Скопируйте её на USB-флешку или другой ПК. Лаунчеры .bat собирают PATH относительно собственного расположения, поэтому ничего не зависит от исходного пути установки.

Единственное требование на целевой машине — драйвер NVIDIA достаточно свежий для установленных CUDA-сборок (R555+ для CUDA 12.8). Для CPU-сборок дополнительных требований нет.
