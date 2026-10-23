# WhisperX Portable

Портативная Windows-сборка WhisperX — быстрого автоматического распознавания речи с пословной разметкой времени и диаризацией говорящих.

Этот репозиторий **не является форком** WhisperX. Это лёгкая обёртка-упаковщик:

- `setup.bat` скачивает портативный Python, ffmpeg, PyTorch со сборками CUDA 12.8 и пакет `whisperx` с PyPI.
- `WhisperX.bat` запускает небольшой Tkinter GUI поверх CLI `whisperx`.
- После завершения `setup.bat` папка становится самодостаточной: её можно скопировать на любую 64-битную Windows-машину с драйвером NVIDIA и запускать без системной установки.

> Протестировано с `whisperx==3.8.x`, `torch~=2.8.0` (cu128). Интерфейс на русском, есть CPU-режим.

---

## Быстрый старт

1. Скачайте или клонируйте этот репозиторий (например, как ZIP-архив).
2. Распакуйте в любую папку (путь может содержать пробелы, но **не должен** содержать символы вне ASCII).
3. Дважды кликните `setup.bat`. Первый запуск скачивает ~3–5 ГБ в `runtime/` и `models/`, это может занять 10–30 минут в зависимости от скорости сети.
4. После завершения дважды кликните `WhisperX.bat` для запуска GUI. Выберите медиа-файл и нажмите **Транскрибировать**.

Лаунчер `WhisperX-CLI.bat` принимает файлы через drag-and-drop и сохраняет результаты в `output/`.

## Требования

| Компонент | Рекомендация |
| --- | --- |
| Windows | 10 1809 / 11, 64-бит |
| ОЗУ | 8 ГБ (для `small`), 16 ГБ и больше (для `large-v3`) |
| GPU (опционально) | NVIDIA с драйвером R555+ для сборок CUDA 12.8 (любая RTX или ≥GTX 10-й серии) |
| Диск | ~6 ГБ после `setup.bat` + кеш моделей |

CPU-режим доступен через `setup.bat /Backend cpu` (см. [INSTALL.md](docs/INSTALL.md)).

## Что устанавливается

После запуска `setup.bat` структура папки такая:

```
whisperx-portable/
├── setup.bat
├── WhisperX.bat
├── WhisperX-CLI.bat
├── tools/                 # установщик + хелперы для лаунчеров
├── gui/                   # исходники Tkinter GUI
├── runtime/
│   ├── python/            # python-build-standalone (портативный Python)
│   ├── venv/              # virtualenv с whisperx и зависимостями
│   ├── ffmpeg/            # встроенный ffmpeg
│   └── install.json       # метаданные бекенда
├── models/                # кеш моделей HF / faster-whisper
├── output/                # папка для результатов по умолчанию
└── config.json            # последние настройки GUI
```

Файлы моделей кешируются в `models/`, чтобы ничего не утекало в `%USERPROFILE%`. Папку можно переносить куда угодно — пути вычисляются относительно лаунчера.

## Диаризация говорящих (опционально)

Диаризация использует [pyannote](https://huggingface.co/pyannote/speaker-diarization-community-1) — модель Hugging Face с ограниченным доступом:

1. Создайте [аккаунт Hugging Face](https://huggingface.co/join).
2. Откройте [страницу модели](https://huggingface.co/pyannote/speaker-diarization-community-1) и примите пользовательское соглашение.
3. Сгенерируйте [токен с правом чтения](https://huggingface.co/settings/tokens).
4. Вставьте токен в поле **Токен HF** в GUI. Он сохранится в `config.json`.

## Использование из командной строки

WhisperX можно использовать и из консоли. Обёртка `WhisperX-CLI.bat` сама настроит окружение:

```bat
REM Перетащите файл на WhisperX-CLI.bat, либо:
WhisperX-CLI.bat input.mp3 --model large-v3 --language ru --output_format srt
```

Полный список флагов:

```bat
WhisperX-CLI.bat
```

## Решение проблем

См. [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md). Самые частые случаи:

- **`Could not load library cudnn_*.dll`** — драйвер NVIDIA старее R555. Обновите драйвер с nvidia.com или пересоберите сборку через `setup.bat /Backend cpu`.
- **`Out of memory`** — возьмите модель поменьше или поставьте в GUI `compute_type=int8` и `batch_size=4`.
- **`Could not download model`** — проверьте `models/huggingface/` на недокачанные файлы; удалите их и повторите. Некоторые модели (диаризация) требуют токен HF.

## Благодарности

- WhisperX от [Max Bain](https://github.com/m-bain/whisperX) — собственно движок, делающий всю работу.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) и [CTranslate2](https://github.com/OpenNMT/CTranslate2) — быстрый бекенд инференса.
- [pyannote-audio](https://github.com/pyannote/pyannote-audio) — VAD и диаризация.
- [python-build-standalone](https://github.com/astral-sh/python-build-standalone) — портативный CPython.
- [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) — Windows-сборки ffmpeg.

## Лицензия

Эта сборка распространяется под BSD-2-Clause (см. `LICENSE`). Все сторонние компоненты сохраняют свои оригинальные лицензии; ffmpeg по умолчанию — сборка «essentials» под LGPL.
