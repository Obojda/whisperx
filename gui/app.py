"""WhisperX Portable - Tkinter GUI launcher.

This is the user-facing front end for the portable WhisperX bundle.
It runs the regular `python -m whisperx` CLI in a subprocess and
streams its output into a log pane, so we never re-implement the
underlying transcription pipeline -- we just wrap it.
"""

from __future__ import annotations

import json
import os
import queue
import shlex
import subprocess
import sys
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tkinter import (
    BOTH,
    DISABLED,
    END,
    NORMAL,
    StringVar,
    BooleanVar,
    IntVar,
    Tk,
    filedialog,
    messagebox,
    ttk,
    scrolledtext,
)


# ---------------------------------------------------------------------------
# Path bootstrap: load CUDA / cuDNN DLLs that ship inside torch's wheel.
# Without this, faster-whisper / ctranslate2 may fail to find cudnn_*.dll on
# Windows because Python 3.8+ no longer searches PATH for DLL dependencies of
# extension modules. We mirror what env.bat already sets, but defensively.
# ---------------------------------------------------------------------------
def _add_dll_directories() -> None:
    if sys.platform != "win32":
        return
    home = Path(__file__).resolve().parent.parent
    candidates = [
        home / "runtime" / "ffmpeg" / "bin",
        home / "runtime" / "venv" / "Lib" / "site-packages" / "torch" / "lib",
        home / "runtime" / "venv" / "Lib" / "site-packages" / "nvidia" / "cudnn" / "bin",
        home / "runtime" / "venv" / "Lib" / "site-packages" / "nvidia" / "cublas" / "bin",
        home / "runtime" / "venv" / "Lib" / "site-packages" / "ctranslate2",
    ]
    for path in candidates:
        if path.is_dir():
            try:
                os.add_dll_directory(str(path))
            except (OSError, AttributeError):
                pass


_add_dll_directories()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.json"
DEFAULT_OUTPUT = REPO_ROOT / "output"

MODELS = [
    "tiny",
    "base",
    "small",
    "medium",
    "large-v2",
    "large-v3",
    "large-v3-turbo",
]
COMPUTE_TYPES = ["default", "float16", "float32", "int8"]
DEVICES = ["cuda", "cpu"]
OUTPUT_FORMATS = ["all", "srt", "vtt", "txt", "tsv", "json"]
LANGUAGES = [
    "auto",
    "en",
    "ru",
    "de",
    "es",
    "fr",
    "it",
    "ja",
    "ko",
    "pt",
    "tr",
    "uk",
    "zh",
    "nl",
    "pl",
    "ar",
]

AUDIO_PATTERNS = [
    ("Аудио / видео", "*.mp3 *.wav *.flac *.ogg *.opus *.m4a *.aac *.mp4 *.mkv *.mov *.webm *.avi"),
    ("Все файлы", "*.*"),
]


# ---------------------------------------------------------------------------
# Persistent config
# ---------------------------------------------------------------------------


@dataclass
class AppConfig:
    last_input: str = ""
    output_dir: str = str(DEFAULT_OUTPUT)
    model: str = "small"
    language: str = "auto"
    device: str = "cuda"
    compute_type: str = "default"
    output_format: str = "srt"
    batch_size: int = 8
    diarize: bool = False
    min_speakers: int = 0
    max_speakers: int = 0
    hf_token: str = ""
    align: bool = True
    highlight_words: bool = False
    extra_args: str = ""

    @classmethod
    def load(cls) -> "AppConfig":
        if not CONFIG_PATH.exists():
            return cls()
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        cfg = cls()
        for key in asdict(cfg):
            if key in data:
                setattr(cfg, key, data[key])
        return cfg

    def save(self) -> None:
        try:
            CONFIG_PATH.write_text(
                json.dumps(asdict(self), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:  # pragma: no cover - best-effort save
            print(f"[config] failed to save: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI argument builder
# ---------------------------------------------------------------------------


@dataclass
class TranscribeJob:
    inputs: list[str] = field(default_factory=list)
    config: AppConfig = field(default_factory=AppConfig)

    def build_command(self, python_exe: str) -> list[str]:
        cfg = self.config
        cmd: list[str] = [python_exe, "-X", "utf8", "-m", "whisperx"]
        cmd += self.inputs
        cmd += ["--model", cfg.model]
        cmd += ["--device", cfg.device]
        cmd += ["--compute_type", cfg.compute_type]
        cmd += ["--batch_size", str(cfg.batch_size)]
        cmd += ["--output_dir", cfg.output_dir]
        cmd += ["--output_format", cfg.output_format]
        if cfg.language and cfg.language != "auto":
            cmd += ["--language", cfg.language]
        if not cfg.align:
            cmd += ["--no_align"]
        if cfg.highlight_words:
            cmd += ["--highlight_words", "True"]
        if cfg.diarize:
            cmd += ["--diarize"]
            if cfg.min_speakers > 0:
                cmd += ["--min_speakers", str(cfg.min_speakers)]
            if cfg.max_speakers > 0:
                cmd += ["--max_speakers", str(cfg.max_speakers)]
            if cfg.hf_token:
                cmd += ["--hf_token", cfg.hf_token]
        if cfg.extra_args.strip():
            cmd += shlex.split(cfg.extra_args, posix=False)
        cmd += ["--print_progress", "True"]
        return cmd


# ---------------------------------------------------------------------------
# Background runner
# ---------------------------------------------------------------------------


class Runner:
    """Run the whisperx CLI in a subprocess, stream output into a queue."""

    def __init__(self, on_line, on_done) -> None:
        self._on_line = on_line
        self._on_done = on_done
        self._proc: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._cancel_requested = False

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, cmd: list[str], cwd: str) -> None:
        if self.is_running:
            raise RuntimeError("задача уже выполняется")
        self._cancel_requested = False
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW
        self._proc = subprocess.Popen(  # noqa: S603 - we control argv
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        assert self._proc is not None
        assert self._proc.stdout is not None
        try:
            for line in self._proc.stdout:
                self._on_line(line.rstrip("\r\n"))
            rc = self._proc.wait()
        except Exception as exc:  # pragma: no cover - defensive
            self._on_line(f"[runner] error: {exc}")
            rc = -1
        finally:
            self._on_done(rc, self._cancel_requested)

    def cancel(self) -> None:
        if not self.is_running:
            return
        self._cancel_requested = True
        try:
            self._proc.terminate()  # type: ignore[union-attr]
        except OSError:
            pass


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


class WhisperXGui:
    PADX = 6
    PADY = 4

    def __init__(self, root: Tk, config: AppConfig) -> None:
        self.root = root
        self.config = config
        self.root.title("WhisperX Portable")
        self.root.geometry("960x720")
        self.root.minsize(820, 600)

        self._line_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.runner = Runner(
            on_line=lambda line: self._line_queue.put(("line", line)),
            on_done=lambda rc, cancelled: self._line_queue.put(
                ("done", (rc, cancelled))
            ),
        )

        self._build_ui()
        self._apply_config_to_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._drain_queue)

    # -- UI construction --------------------------------------------------
    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=BOTH, expand=True)

        # Input file row ------------------------------------------------
        input_frame = ttk.LabelFrame(outer, text="Исходный файл")
        input_frame.pack(fill="x", pady=(0, 6))

        self.var_input = StringVar()
        ttk.Entry(input_frame, textvariable=self.var_input).pack(
            side="left", fill="x", expand=True, padx=self.PADX, pady=self.PADY
        )
        ttk.Button(input_frame, text="Обзор…", command=self._pick_input).pack(
            side="left", padx=(0, self.PADX), pady=self.PADY
        )

        # Output row ----------------------------------------------------
        output_frame = ttk.LabelFrame(outer, text="Папка результата")
        output_frame.pack(fill="x", pady=(0, 6))
        self.var_output = StringVar()
        ttk.Entry(output_frame, textvariable=self.var_output).pack(
            side="left", fill="x", expand=True, padx=self.PADX, pady=self.PADY
        )
        ttk.Button(output_frame, text="Обзор…", command=self._pick_output).pack(
            side="left", padx=(0, self.PADX), pady=self.PADY
        )
        ttk.Button(output_frame, text="Открыть", command=self._open_output).pack(
            side="left", padx=(0, self.PADX), pady=self.PADY
        )

        # Options grid --------------------------------------------------
        opts = ttk.LabelFrame(outer, text="Параметры")
        opts.pack(fill="x", pady=(0, 6))
        for i in range(4):
            opts.columnconfigure(i, weight=1)

        self.var_model = StringVar()
        self.var_language = StringVar()
        self.var_device = StringVar()
        self.var_compute_type = StringVar()
        self.var_output_format = StringVar()
        self.var_batch_size = IntVar(value=8)
        self.var_align = BooleanVar(value=True)
        self.var_highlight_words = BooleanVar(value=False)
        self.var_diarize = BooleanVar(value=False)
        self.var_min_speakers = IntVar(value=0)
        self.var_max_speakers = IntVar(value=0)
        self.var_hf_token = StringVar()
        self.var_extra_args = StringVar()

        self._add_combobox(opts, 0, 0, "Модель", self.var_model, MODELS)
        self._add_combobox(opts, 0, 1, "Язык", self.var_language, LANGUAGES)
        self._add_combobox(opts, 0, 2, "Устройство", self.var_device, DEVICES)
        self._add_combobox(opts, 0, 3, "Тип вычислений", self.var_compute_type, COMPUTE_TYPES)

        self._add_combobox(opts, 1, 0, "Формат вывода", self.var_output_format, OUTPUT_FORMATS)
        self._add_spinbox(opts, 1, 1, "Размер батча", self.var_batch_size, 1, 64)
        ttk.Checkbutton(opts, text="Выравнивание (временные метки слов)", variable=self.var_align).grid(
            row=1, column=2, sticky="w", padx=self.PADX, pady=self.PADY
        )
        ttk.Checkbutton(opts, text="Подсвечивать слова", variable=self.var_highlight_words).grid(
            row=1, column=3, sticky="w", padx=self.PADX, pady=self.PADY
        )

        # Diarization sub-frame ----------------------------------------
        diar = ttk.LabelFrame(outer, text="Диаризация говорящих (опционально)")
        diar.pack(fill="x", pady=(0, 6))
        for i in range(4):
            diar.columnconfigure(i, weight=1)

        ttk.Checkbutton(diar, text="Включить диаризацию", variable=self.var_diarize).grid(
            row=0, column=0, sticky="w", padx=self.PADX, pady=self.PADY
        )
        self._add_spinbox(diar, 0, 1, "Мин. говорящих", self.var_min_speakers, 0, 64)
        self._add_spinbox(diar, 0, 2, "Макс. говорящих", self.var_max_speakers, 0, 64)
        ttk.Label(diar, text="Токен HF").grid(row=1, column=0, sticky="w", padx=self.PADX)
        ttk.Entry(diar, textvariable=self.var_hf_token, show="•").grid(
            row=1, column=1, columnspan=3, sticky="ew", padx=self.PADX, pady=self.PADY
        )
        ttk.Label(
            diar,
            text=(
                "Для диаризации примите соглашение модели на "
                "huggingface.co/pyannote/speaker-diarization-community-1 "
                "и вставьте ваш токен в поле выше."
            ),
            wraplength=900,
            foreground="gray",
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=self.PADX, pady=(0, self.PADY))

        # Extra args ----------------------------------------------------
        extra = ttk.LabelFrame(outer, text="Дополнительные флаги CLI (расширенные)")
        extra.pack(fill="x", pady=(0, 6))
        ttk.Entry(extra, textvariable=self.var_extra_args).pack(
            fill="x", padx=self.PADX, pady=self.PADY
        )

        # Buttons -------------------------------------------------------
        btns = ttk.Frame(outer)
        btns.pack(fill="x", pady=(0, 6))
        self.btn_start = ttk.Button(btns, text="Транскрибировать", command=self._on_start)
        self.btn_start.pack(side="left")
        self.btn_cancel = ttk.Button(
            btns, text="Отмена", command=self._on_cancel, state=DISABLED
        )
        self.btn_cancel.pack(side="left", padx=(self.PADX, 0))
        self.btn_clear_log = ttk.Button(btns, text="Очистить лог", command=self._clear_log)
        self.btn_clear_log.pack(side="left", padx=(self.PADX, 0))
        self.var_status = StringVar(value="Готово")
        ttk.Label(btns, textvariable=self.var_status, foreground="gray").pack(
            side="right"
        )

        # Log -----------------------------------------------------------
        self.log = scrolledtext.ScrolledText(outer, height=18, font=("Consolas", 9))
        self.log.pack(fill=BOTH, expand=True)
        self.log.configure(state=DISABLED)

    def _add_combobox(self, parent, row, col, label, var, values):
        ttk.Label(parent, text=label).grid(row=row * 2, column=col, sticky="w", padx=self.PADX)
        cb = ttk.Combobox(parent, textvariable=var, values=values, state="readonly")
        cb.grid(row=row * 2 + 1, column=col, sticky="ew", padx=self.PADX, pady=self.PADY)
        return cb

    def _add_spinbox(self, parent, row, col, label, var, low, high):
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=self.PADX)
        sb = ttk.Spinbox(parent, textvariable=var, from_=low, to=high, width=8)
        sb.grid(row=row, column=col, sticky="e", padx=self.PADX, pady=self.PADY)
        return sb

    # -- Config bridge ----------------------------------------------------
    def _apply_config_to_widgets(self) -> None:
        c = self.config
        self.var_input.set(c.last_input)
        self.var_output.set(c.output_dir or str(DEFAULT_OUTPUT))
        self.var_model.set(c.model)
        self.var_language.set(c.language)
        self.var_device.set(c.device)
        self.var_compute_type.set(c.compute_type)
        self.var_output_format.set(c.output_format)
        self.var_batch_size.set(c.batch_size)
        self.var_align.set(c.align)
        self.var_highlight_words.set(c.highlight_words)
        self.var_diarize.set(c.diarize)
        self.var_min_speakers.set(c.min_speakers)
        self.var_max_speakers.set(c.max_speakers)
        self.var_hf_token.set(c.hf_token)
        self.var_extra_args.set(c.extra_args)

    def _gather_config(self) -> AppConfig:
        return AppConfig(
            last_input=self.var_input.get().strip(),
            output_dir=self.var_output.get().strip() or str(DEFAULT_OUTPUT),
            model=self.var_model.get() or "small",
            language=self.var_language.get() or "auto",
            device=self.var_device.get() or "cuda",
            compute_type=self.var_compute_type.get() or "default",
            output_format=self.var_output_format.get() or "srt",
            batch_size=int(self.var_batch_size.get() or 8),
            diarize=bool(self.var_diarize.get()),
            min_speakers=int(self.var_min_speakers.get() or 0),
            max_speakers=int(self.var_max_speakers.get() or 0),
            hf_token=self.var_hf_token.get().strip(),
            align=bool(self.var_align.get()),
            highlight_words=bool(self.var_highlight_words.get()),
            extra_args=self.var_extra_args.get().strip(),
        )

    # -- Actions ---------------------------------------------------------
    def _pick_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите аудио или видео", filetypes=AUDIO_PATTERNS
        )
        if path:
            self.var_input.set(path)

    def _pick_output(self) -> None:
        path = filedialog.askdirectory(title="Выберите папку для результатов")
        if path:
            self.var_output.set(path)

    def _open_output(self) -> None:
        path = Path(self.var_output.get().strip() or str(DEFAULT_OUTPUT))
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(path)])  # noqa: S603, S607

    def _on_start(self) -> None:
        if self.runner.is_running:
            return
        cfg = self._gather_config()
        if not cfg.last_input:
            messagebox.showerror("WhisperX", "Сначала выберите исходный файл.")
            return
        if not Path(cfg.last_input).exists():
            messagebox.showerror("WhisperX", f"Исходный файл не найден:\n{cfg.last_input}")
            return
        if cfg.diarize and not cfg.hf_token:
            if not messagebox.askyesno(
                "WhisperX",
                "Диаризация включена, но токен Hugging Face не указан.\n"
                "Скачивание модели диаризации без него не удастся.\n\n"
                "Продолжить всё равно?",
            ):
                return
        Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)
        self.config = cfg
        self.config.save()

        job = TranscribeJob(inputs=[cfg.last_input], config=cfg)
        cmd = job.build_command(sys.executable)
        self._append_log("=" * 70)
        self._append_log(f"Запуск: {subprocess.list2cmdline(cmd)}")
        self._append_log("=" * 70)
        try:
            self.runner.start(cmd, cwd=str(REPO_ROOT))
        except Exception as exc:
            messagebox.showerror("WhisperX", f"Не удалось запустить: {exc}")
            return
        self.btn_start.configure(state=DISABLED)
        self.btn_cancel.configure(state=NORMAL)
        self.var_status.set("Выполняется…")

    def _on_cancel(self) -> None:
        if not self.runner.is_running:
            return
        if messagebox.askyesno("WhisperX", "Прервать текущую транскрипцию?"):
            self.runner.cancel()
            self.var_status.set("Прерывается…")

    def _on_close(self) -> None:
        if self.runner.is_running:
            if not messagebox.askyesno(
                "WhisperX", "Транскрипция ещё выполняется. Прервать и выйти?"
            ):
                return
            self.runner.cancel()
        try:
            self._gather_config().save()
        except Exception:  # noqa: BLE001
            pass
        self.root.destroy()

    # -- Log handling ----------------------------------------------------
    def _drain_queue(self) -> None:
        try:
            while True:
                kind, payload = self._line_queue.get_nowait()
                if kind == "line":
                    self._append_log(str(payload))
                elif kind == "done":
                    rc, cancelled = payload  # type: ignore[misc]
                    self._on_finished(int(rc), bool(cancelled))
        except queue.Empty:
            pass
        self.root.after(80, self._drain_queue)

    def _append_log(self, line: str) -> None:
        self.log.configure(state=NORMAL)
        self.log.insert(END, line + "\n")
        self.log.see(END)
        self.log.configure(state=DISABLED)

    def _clear_log(self) -> None:
        self.log.configure(state=NORMAL)
        self.log.delete("1.0", END)
        self.log.configure(state=DISABLED)

    def _on_finished(self, rc: int, cancelled: bool) -> None:
        self.btn_start.configure(state=NORMAL)
        self.btn_cancel.configure(state=DISABLED)
        if cancelled:
            self.var_status.set("Прервано")
            self._append_log("[whisperx] прервано пользователем")
            return
        if rc == 0:
            self.var_status.set("Готово")
            self._append_log("[whisperx] успешно завершено")
            messagebox.showinfo(
                "WhisperX",
                f"Транскрипция завершена.\nПапка результатов:\n{self.var_output.get()}",
            )
        else:
            self.var_status.set(f"Ошибка (rc={rc})")
            self._append_log(f"[whisperx] завершился с кодом {rc}")
            messagebox.showerror(
                "WhisperX",
                f"WhisperX завершился с кодом {rc}. Подробности в логе.",
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    cfg = AppConfig.load()
    # Honour first positional arg as a convenience when launched from
    # the CLI launcher (drag-drop or `WhisperX.bat path\to\file.mp3`).
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        cfg.last_input = str(Path(sys.argv[1]).resolve())
    root = Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:  # noqa: BLE001
        pass
    WhisperXGui(root, cfg)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
