"""Penulis berkas log permanen (.log dan .jsonl) dengan rotasi aman dan fallback anti-crash.

Memenuhi Bagian XXVI:
  - Lokasi default Windows: ``%LOCALAPPDATA%\\HILALONE\\Logs\\``
  - Struktur direktori:
        Logs/
            application/
                application_latest.log
            sessions/
                HILALONE_YYYYMMDD_HHMMSS.log
                HILALONE_YYYYMMDD_HHMMSS.jsonl
            diagnostics/
                diagnostic_latest.log
  - Mendukung rotasi terukur (bounded file size) dengan pengarsipan bernama timestamp
    tanpa pernah menghapus berkas log secara diam-diam.
  - Aman untuk multithreading (thread-safe lock).
  - Bila penulisan ke disk gagal, aplikasi tidak pernah crash dan kegagalan dicatat
    di memori fallback.
"""

from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import sys
import threading
from typing import Iterable

from hilalone.core.logging.log_event import LogEvent, LogLevel
from hilalone.core.logging.log_formatter import (
    format_jsonl_line,
    format_persistent_line,
)

# Batas ukuran berkas log bergulir sebelum diarsipkan (5 MB)
DEFAULT_MAX_LOG_BYTES: int = 5 * 1024 * 1024


def get_default_logs_root() -> Path:
    """Mengembalikan direktori root penyimpanan log permanen: ``%LOCALAPPDATA%\\HILALONE\\Logs``."""
    override_dir = os.environ.get("HILALONE_LOG_DIR")
    if override_dir:
        return Path(override_dir)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(base) if base else (Path.home() / "AppData" / "Local")
        return root / "HILALONE" / "Logs"
    return Path.home() / ".local" / "share" / "HILALONE" / "Logs"


class PersistentLogFileHandler:
    """Pengelola penulisan berkas log permanen (.log dan .jsonl) yang aman dari multithreading."""

    def __init__(
        self,
        base_dir: Path | str | None = None,
        *,
        session_timestamp: datetime | None = None,
        max_bytes: int = DEFAULT_MAX_LOG_BYTES,
    ) -> None:
        self._lock = threading.RLock()
        self._base_dir = Path(base_dir) if base_dir is not None else get_default_logs_root()
        self._max_bytes = max(1024, int(max_bytes))
        self._has_write_error = False
        self._last_error_message: str | None = None
        self._fallback_records: list[str] = []

        now = session_timestamp if session_timestamp is not None else datetime.now().astimezone()
        tag = now.strftime("%Y%m%d_%H%M%S")

        self.application_dir = self._base_dir / "application"
        self.sessions_dir = self._base_dir / "sessions"
        self.diagnostics_dir = self._base_dir / "diagnostics"

        self.application_log_path = self.application_dir / "application_latest.log"
        self.diagnostic_log_path = self.diagnostics_dir / "diagnostic_latest.log"
        self.session_log_path = self.sessions_dir / f"HILALONE_{tag}.log"
        self.session_jsonl_path = self.sessions_dir / f"HILALONE_{tag}.jsonl"

        self._initialize_directories()

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    @property
    def has_write_error(self) -> bool:
        with self._lock:
            return self._has_write_error

    @property
    def last_error_message(self) -> str | None:
        with self._lock:
            return self._last_error_message

    @property
    def fallback_records(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._fallback_records)

    def _initialize_directories(self) -> None:
        """Membuat direktori log dan mengarsipkan berkas latest jika sudah melebihi batas ukuran."""
        with self._lock:
            try:
                self.application_dir.mkdir(parents=True, exist_ok=True)
                self.sessions_dir.mkdir(parents=True, exist_ok=True)
                self.diagnostics_dir.mkdir(parents=True, exist_ok=True)

                self._rotate_if_needed(self.application_log_path)
                self._rotate_if_needed(self.diagnostic_log_path)

                # Pastikan berkas sesi dibuat sejak awal
                if not self.session_log_path.exists():
                    self.session_log_path.write_text("", encoding="utf-8")
                if not self.session_jsonl_path.exists():
                    self.session_jsonl_path.write_text("", encoding="utf-8")
                if not self.application_log_path.exists():
                    self.application_log_path.write_text("", encoding="utf-8")
                if not self.diagnostic_log_path.exists():
                    self.diagnostic_log_path.write_text("", encoding="utf-8")
            except Exception as exc:
                self._record_write_failure(f"Gagal menyiapkan direktori log '{self._base_dir}': {exc}")

    def _rotate_if_needed(self, file_path: Path) -> Path | None:
        """Mengarsipkan berkas log yang melampaui ``max_bytes`` tanpa menghapus data lama."""
        with self._lock:
            try:
                if not file_path.exists():
                    return None
                size = file_path.stat().st_size
                if size < self._max_bytes:
                    return None

                stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
                stem = file_path.stem.replace("_latest", "")
                archive_name = f"{stem}_archive_{stamp}{file_path.suffix}"
                archive_path = file_path.with_name(archive_name)
                counter = 1
                while archive_path.exists():
                    archive_path = file_path.with_name(f"{stem}_archive_{stamp}_{counter}{file_path.suffix}")
                    counter += 1

                file_path.replace(archive_path)
                file_path.write_text(
                    f"# Log rotated at {stamp}. Previous log archived to: {archive_path.name}\n",
                    encoding="utf-8",
                )
                return archive_path
            except Exception as exc:
                self._record_write_failure(f"Gagal merotasi berkas log '{file_path}': {exc}")
                return None

    def _record_write_failure(self, error_msg: str) -> None:
        self._has_write_error = True
        self._last_error_message = error_msg
        self._fallback_records.append(error_msg)

    def write_event(self, event: LogEvent) -> bool:
        """Menulis satu ``LogEvent`` ke berkas sesi (.log & .jsonl), aplikasi, dan diagnostik."""
        with self._lock:
            text_line = format_persistent_line(event)
            jsonl_line = format_jsonl_line(event)

            try:
                # 1. Tulis ke berkas sesi .log dan .jsonl (kecuali DEBUG yang hanya ke diagnostic & jsonl)
                if event.level != LogLevel.DEBUG:
                    with open(self.session_log_path, "a", encoding="utf-8") as sf:
                        sf.write(text_line + "\n")

                with open(self.session_jsonl_path, "a", encoding="utf-8") as jf:
                    jf.write(jsonl_line + "\n")

                # 2. Tulis ke application_latest.log (rotasi otomatis bila melampaui batas)
                self._rotate_if_needed(self.application_log_path)
                if event.level != LogLevel.DEBUG:
                    with open(self.application_log_path, "a", encoding="utf-8") as af:
                        af.write(text_line + "\n")

                # 3. Tulis ke diagnostic_latest.log (mencakup semua level termasuk DEBUG dan traceback)
                self._rotate_if_needed(self.diagnostic_log_path)
                with open(self.diagnostic_log_path, "a", encoding="utf-8") as df:
                    df.write(text_line + "\n")
                    tb = event.details.get("traceback") if event.details else None
                    if tb:
                        df.write(f"--- TRACEBACK ({event.run_id}) ---\n{tb}\n--- END TRACEBACK ---\n")

                return True
            except Exception as exc:
                self._record_write_failure(f"Gagal menulis event log ke disk: {exc} | {text_line}")
                return False

    def export_events_to_log(self, events: Iterable[LogEvent], target_path: Path | str) -> Path:
        """Mengekspor kumpulan event ke berkas teks ``.log`` / ``.txt`` dengan urutan terjaga."""
        p = Path(target_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [format_console_line_for_export(ev) for ev in events]
        p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return p

    def export_events_to_jsonl(self, events: Iterable[LogEvent], target_path: Path | str) -> Path:
        """Mengekspor kumpulan event ke berkas terstruktur ``.jsonl``."""
        p = Path(target_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        lines = [format_jsonl_line(ev) for ev in events]
        p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return p


def format_console_line_for_export(event: LogEvent) -> str:
    """Memformat baris log untuk file ekspor teks (.log / .txt)."""
    return event.format_line(use_iso_timestamp=False)
