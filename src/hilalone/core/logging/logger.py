"""Sistem Logger Terpusat HILALONE (``HilaloneLogger`` / ``LogManager``).

Menyatukan seluruh aktivitas pencatatan dari:
  - Main Application (Startup & System Info)
  - Image Input Manager (FITS, TIFF, Camera RAW, Video, SER)
  - Sequence Manager & Frame Validation
  - Flat Calibration & Master Flat Generation
  - Image Stacking
  - Background Extraction
  - Image Enhancement (CLAHE)
  - Histogram Transformation
  - Curve Processing
  - Display & Image Viewer
  - Output Manager
  - Automated Processing Pipeline & Processing Summary
  - Error & Cancellation Handler

Mempertahankan kompatibilitas penuh dengan antarmuka ``LogManager`` sebelumnya
(``info(module, action, detail)``, ``export_to_txt``, ``export_to_csv``, ``export_to_json``)
sekaligus menyediakan API ilmiah terstruktur untuk v1.0.0.
"""

from __future__ import annotations

import csv
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import sys
import threading
import time
import traceback
from typing import Any, Iterable

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QObject, Signal, qVersion

from hilalone import APP_NAME, __version__
from hilalone.core.logging.aligned_summary import format_aligned_summary
from hilalone.core.logging.file_handler import (
    PersistentLogFileHandler,
    get_default_logs_root,
)
from hilalone.core.logging.log_event import (
    LogEvent,
    LogEventType,
    LogLevel,
    LogModule,
    LogVerbosity,
    ProcessingRunSummary,
    normalize_module_name,
)
from hilalone.core.logging.log_filter import (
    ConsoleFilterCategory,
    LogFilterCriteria,
    filter_log_events,
)
from hilalone.core.logging.log_formatter import (
    format_console_line,
    format_jsonl_line,
    sanitize_details,
)
from hilalone.core.logging.log_handler import ProgressRateLimiter
from hilalone.core.logging.log_session import (
    LogSessionManager,
    ProcessingSessionRecord,
    format_timestamps,
)
from hilalone.core.logging.workflow_timeline import WorkflowTimelineTracker


class HilaloneLogger(QObject):
    """Manajer log ilmiah terpusat HILALONE yang thread-safe dan mendukung persistensi berkas."""

    entry_logged = Signal(object)        # LogEvent
    log_cleared = Signal()               # Sinyal saat daftar direset
    view_cleared = Signal()              # Sinyal saat hanya tampilan Console yang dibersihkan
    verbosity_changed = Signal(str)      # Sinyal saat verbosity berubah (NORMAL/VERBOSE/DEBUG)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        log_dir: Path | str | None = None,
        enable_file_logging: bool | None = None,
        session_id: str | None = None,
        verbosity: LogVerbosity = LogVerbosity.NORMAL,
    ) -> None:
        super().__init__(parent)
        self._lock = threading.RLock()
        self._entries: list[LogEvent] = []
        self._session_history: list[LogEvent] = []
        self._view_start_index: int = 0
        self._verbosity: LogVerbosity = verbosity
        self._source_directory: Path | None = None
        self._session_manager = LogSessionManager(session_id=session_id)
        self._timeline_tracker = WorkflowTimelineTracker()
        self._progress_limiter = ProgressRateLimiter(min_step_percent=10)
        self._startup_logged: bool = False

        # Secara default aktifkan file logging. Jika di dalam pytest tanpa log_dir eksplisit,
        # arahkan ke subdirektori khusus pytest di temp agar tidak mencemari folder pengguna.
        if enable_file_logging is None:
            enable_file_logging = True

        self._file_handler: PersistentLogFileHandler | None = None
        if enable_file_logging:
            if log_dir is not None:
                target_dir = Path(log_dir)
            elif "PYTEST_CURRENT_TEST" in os.environ and "HILALONE_LOG_DIR" not in os.environ:
                import tempfile

                target_dir = Path(tempfile.gettempdir()) / "HILALONE_pytest_logs"
            else:
                target_dir = get_default_logs_root()
            self._file_handler = PersistentLogFileHandler(base_dir=target_dir)

    # ------------------------------------------------------------------ Properti
    @property
    def entries(self) -> tuple[LogEvent, ...]:
        """Daftar event pada sesi aktif."""
        with self._lock:
            return tuple(self._entries)

    @property
    def session_entries(self) -> tuple[LogEvent, ...]:
        """Seluruh catatan event sesi sejak aplikasi dibuka (tidak terpengaruh Clear Console)."""
        with self._lock:
            return tuple(self._session_history)

    @property
    def visible_entries_after_clear(self) -> tuple[LogEvent, ...]:
        """Daftar event setelah penekanan tombol Clear Console terakhir."""
        with self._lock:
            return tuple(self._entries[self._view_start_index :])

    @property
    def session_id(self) -> str:
        return self._session_manager.session_id

    @property
    def active_run_id(self) -> str | None:
        return self._session_manager.active_run_id

    @property
    def current_run_id(self) -> str:
        return self._session_manager.current_run_or_session_id

    @property
    def session_manager(self) -> LogSessionManager:
        return self._session_manager

    @property
    def timeline_tracker(self) -> WorkflowTimelineTracker:
        return self._timeline_tracker

    @property
    def file_handler(self) -> PersistentLogFileHandler | None:
        return self._file_handler

    @property
    def log_dir(self) -> Path:
        if self._file_handler is not None:
            return self._file_handler.base_dir
        return get_default_logs_root()

    @property
    def verbosity(self) -> LogVerbosity:
        with self._lock:
            return self._verbosity

    @property
    def is_verbose_enabled(self) -> bool:
        """True jika mode Detail saat ini adalah VERBOSE atau DEBUG."""
        with self._lock:
            return self._verbosity in (LogVerbosity.VERBOSE, LogVerbosity.DEBUG)

    @property
    def is_debug_enabled(self) -> bool:
        """True jika mode Detail saat ini adalah DEBUG."""
        with self._lock:
            return self._verbosity == LogVerbosity.DEBUG

    @property
    def source_directory(self) -> Path | None:
        """Direktori sumber citra/sequence aktif pada sesi pemrosesan saat ini."""
        with self._lock:
            return self._source_directory

    def set_source_directory(self, path: Path | str | None) -> Path | None:
        """Menetapkan direktori sumber aktif dari berkas atau folder input yang dibuka pengguna."""
        with self._lock:
            if path is None:
                self._source_directory = None
                return None
            p = Path(path)
            if p.exists():
                self._source_directory = p if p.is_dir() else p.parent
            else:
                # Jika path belum ada di disk atau berupa file path dengan ekstensi
                self._source_directory = p.parent if p.suffix else p
            return self._source_directory

    def resolve_export_directory(self, *, emit_fallback_log: bool = True) -> Path:
        """Menentukan folder awal untuk dialog Export Visible / Export Complete Log.

        - Jika ada direktori sumber citra aktif, gunakan direktori tersebut.
        - Jika belum ada berkas atau sequence yang dibuka, gunakan fallback
          ``%LOCALAPPDATA%\\HILALONE\\Logs\\`` dan catat pesan informasi ke modul ``EXPORT``.
        """
        with self._lock:
            src_dir = self._source_directory

        if src_dir is not None:
            return src_dir

        if emit_fallback_log:
            self.info(
                LogModule.EXPORT,
                "No active source directory. Using default HILALONE log folder.",
            )
        return self.log_dir

    def set_verbosity(
        self,
        verbosity: LogVerbosity | str,
        *,
        log_change: bool = True,
    ) -> None:
        """Mengubah tingkat verbosity logging secara real-time tanpa menutup aplikasi."""
        if isinstance(verbosity, str):
            try:
                verb = LogVerbosity(verbosity.strip().upper())
            except ValueError:
                verb = LogVerbosity.NORMAL
        else:
            verb = verbosity

        with self._lock:
            old_verb = self._verbosity
            if old_verb == verb:
                return
            self._verbosity = verb

        if log_change:
            self.info(
                LogModule.LOGGING,
                f"Detail mode changed: {old_verb.value} -> {verb.value}.",
            )
        self.verbosity_changed.emit(verb.value)

    # ------------------------------------------------------------------ Run & Session Management
    def start_processing_run(
        self,
        *,
        run_id: str | None = None,
        input_summary: dict[str, Any] | None = None,
        processing_config: dict[str, Any] | None = None,
    ) -> ProcessingSessionRecord:
        """Memulai satu sesi Processing Run baru dengan Run ID unik."""
        self._progress_limiter.reset()
        return self._session_manager.start_processing_run(
            run_id=run_id,
            input_summary=input_summary,
            processing_config=processing_config,
        )

    def finish_processing_run(
        self,
        status: str = "SUCCESS",
        *,
        run_id: str | None = None,
        output_files: list[str] | tuple[str, ...] = (),
    ) -> ProcessingSessionRecord | None:
        """Menutup sesi Processing Run aktif."""
        return self._session_manager.finish_processing_run(
            status=status,
            run_id=run_id,
            output_files=output_files,
        )

    def clear_active_run_context(self) -> None:
        """Melepas Run ID aktif ketika pengguna membuka citra baru setelah proses selesai."""
        self._session_manager.clear_active_run_context()

    # ------------------------------------------------------------------ Core Logging Methods
    def log(
        self,
        level: LogLevel | str,
        module: str | LogModule,
        message_or_action: str,
        detail: str = "",
        *,
        details: dict[str, Any] | None = None,
        event_type: LogEventType | None = None,
        run_id: str | None = None,
        min_verbosity: LogVerbosity = LogVerbosity.NORMAL,
        raw_block: str | None = None,
        write_to_python_logging: bool = False,
    ) -> LogEvent:
        """Mencatat satu peristiwa aktivitas secara thread-safe ke memori, berkas log, dan GUI."""
        if isinstance(level, str):
            try:
                lvl = LogLevel(level.strip().upper())
            except ValueError:
                lvl = LogLevel.INFO
        else:
            lvl = level

        if event_type is None:
            if lvl == LogLevel.SUCCESS:
                ev_type = LogEventType.SUCCESS
            elif lvl == LogLevel.PROGRESS:
                ev_type = LogEventType.PROGRESS
            elif lvl == LogLevel.SECTION:
                ev_type = LogEventType.SECTION
            elif lvl == LogLevel.CANCELLED:
                ev_type = LogEventType.CANCELLED
            elif lvl == LogLevel.SKIPPED:
                ev_type = LogEventType.SKIPPED
            elif lvl == LogLevel.WARNING:
                ev_type = LogEventType.WARNING
            elif lvl == LogLevel.ERROR:
                ev_type = LogEventType.ERROR
            elif lvl == LogLevel.CRITICAL:
                ev_type = LogEventType.CRITICAL
            elif lvl == LogLevel.DEBUG:
                ev_type = LogEventType.DEBUG
            else:
                ev_type = LogEventType.MESSAGE
        else:
            ev_type = event_type

        if lvl == LogLevel.DEBUG and min_verbosity == LogVerbosity.NORMAL:
            min_verbosity = LogVerbosity.DEBUG

        ui_ts, iso_ts = format_timestamps()
        norm_mod = normalize_module_name(module)
        clean_msg = str(message_or_action).strip()
        clean_det_text = str(detail).strip() if detail else ""
        sanitized_dict = sanitize_details(details)

        with self._lock:
            seq = self._session_manager.next_sequence()
            eff_run_id = run_id or self._session_manager.current_run_or_session_id
            cur_verb = self._verbosity
            event = LogEvent(
                timestamp=ui_ts,
                iso_timestamp=iso_ts,
                session_id=self._session_manager.session_id,
                run_id=eff_run_id,
                sequence=seq,
                level=lvl,
                event_type=ev_type,
                module=norm_mod,
                message=clean_msg,
                details=sanitized_dict,
                action=clean_msg,
                detail_text=clean_det_text,
                min_verbosity=min_verbosity,
                emitted_under_verbosity=cur_verb,
                raw_block=raw_block,
            )
            self._entries.append(event)
            self._session_history.append(event)

            if self._file_handler is not None:
                self._file_handler.write_event(event)

        self.entry_logged.emit(event)
        return event

    def debug(
        self,
        module: str | LogModule,
        message: str,
        detail: str = "",
        *,
        details: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> LogEvent:
        """Mencatat pesan diagnostik teknis (DEBUG; tersembunyi pada mode NORMAL)."""
        return self.log(
            LogLevel.DEBUG,
            module,
            message,
            detail,
            details=details,
            run_id=run_id,
            min_verbosity=LogVerbosity.DEBUG,
        )

    def verbose(
        self,
        module: str | LogModule,
        message: str,
        detail: str = "",
        *,
        details: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> LogEvent:
        """Mencatat pesan parameter/metadata tambahan untuk mode VERBOSE dan DEBUG."""
        return self.log(
            LogLevel.INFO,
            module,
            message,
            detail,
            details=details,
            run_id=run_id,
            min_verbosity=LogVerbosity.VERBOSE,
        )

    def info(
        self,
        module: str | LogModule,
        action_or_message: str,
        detail: str = "",
        *,
        details: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> LogEvent:
        """Mencatat informasi aktivitas normal, status input, metadata, dan parameter."""
        return self.log(
            LogLevel.INFO,
            module,
            action_or_message,
            detail,
            details=details,
            run_id=run_id,
        )

    def success(
        self,
        module: str | LogModule,
        action_or_message: str,
        detail: str = "",
        *,
        details: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> LogEvent:
        """Mencatat konfirmasi keberhasilan penyelesaian suatu tahapan."""
        return self.log(
            LogLevel.SUCCESS,
            module,
            action_or_message,
            detail,
            details=details,
            event_type=LogEventType.SUCCESS,
            run_id=run_id,
        )

    def warning(
        self,
        module: str | LogModule,
        action_or_message: str,
        detail: str = "",
        *,
        details: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> LogEvent:
        """Mencatat anomali nonfatal yang perlu diketahui pengguna."""
        return self.log(
            LogLevel.WARNING,
            module,
            action_or_message,
            detail,
            details=details,
            event_type=LogEventType.WARNING,
            run_id=run_id,
        )

    def error(
        self,
        module: str | LogModule,
        action_or_message: str,
        detail: str = "",
        *,
        details: dict[str, Any] | None = None,
        exc: BaseException | None = None,
        operation: str | None = None,
        error_code: str | None = None,
        suggested_action: str | None = None,
        run_id: str | None = None,
    ) -> LogEvent:
        """Mencatat kegagalan operasi beserta informasi penyebab dan saran penanganan aman."""
        merged_details = dict(details or {})
        if operation:
            merged_details.setdefault("operation", operation)
        if error_code:
            merged_details.setdefault("error_code", error_code)
        if exc is not None:
            merged_details.setdefault("exception_type", type(exc).__name__)
            tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            merged_details["traceback"] = tb_str
        if suggested_action:
            merged_details.setdefault("suggested_action", suggested_action)

        return self.log(
            LogLevel.ERROR,
            module,
            action_or_message,
            detail,
            details=merged_details,
            event_type=LogEventType.ERROR,
            run_id=run_id,
        )

    def critical(
        self,
        module: str | LogModule,
        action_or_message: str,
        detail: str = "",
        *,
        details: dict[str, Any] | None = None,
        exc: BaseException | None = None,
        run_id: str | None = None,
    ) -> LogEvent:
        """Mencatat masalah serius/kritis yang menghentikan sesi kerja."""
        merged_details = dict(details or {})
        if exc is not None:
            merged_details.setdefault("exception_type", type(exc).__name__)
            merged_details["traceback"] = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            )
        return self.log(
            LogLevel.CRITICAL,
            module,
            action_or_message,
            detail,
            details=merged_details,
            event_type=LogEventType.CRITICAL,
            run_id=run_id,
        )

    def section(
        self,
        title: str,
        *,
        module: str | LogModule = LogModule.SESSION,
        run_id: str | None = None,
    ) -> LogEvent:
        """Mencatat pembatas judul bagian proses: ``=== SECTION TITLE ===``."""
        clean_title = title.strip().strip("=").strip().upper()
        return self.log(
            LogLevel.SECTION,
            module,
            clean_title,
            event_type=LogEventType.SECTION,
            run_id=run_id,
        )

    def progress(
        self,
        module: str | LogModule,
        current: int,
        total: int,
        message: str = "",
        *,
        operation: str = "default",
        force: bool = False,
        run_id: str | None = None,
    ) -> LogEvent | None:
        """Mencatat perkembangan pekerjaan panjang dengan rate-limiting otomatis."""
        norm_mod = normalize_module_name(module)
        key = f"{norm_mod}:{operation}"
        tot = max(1, int(total))
        cur = max(0, min(int(current), tot))

        if force:
            pct = int(round(100.0 * cur / float(tot)))
            allow = True
        else:
            allow, pct = self._progress_limiter.should_emit(key, cur, tot)

        if not allow:
            return None

        msg = message.strip() if message else f"{pct}% completed ({cur}/{tot})."
        return self.log(
            LogLevel.PROGRESS,
            norm_mod,
            msg,
            details={
                "progress_current": cur,
                "progress_total": tot,
                "percent": f"{pct}%",
            },
            event_type=LogEventType.PROGRESS,
            run_id=run_id,
        )

    def cancelled(
        self,
        module: str | LogModule,
        message: str = "Processing cancelled by user.",
        detail: str = "",
        *,
        details: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> LogEvent:
        """Mencatat penghentian proses yang diminta secara sengaja oleh pengguna (bukan ERROR)."""
        return self.log(
            LogLevel.CANCELLED,
            module,
            message,
            detail,
            details=details,
            event_type=LogEventType.CANCELLED,
            run_id=run_id,
        )

    def skipped(
        self,
        module: str | LogModule,
        message: str,
        reason: str = "",
        *,
        details: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> LogEvent:
        """Mencatat tahapan opsional yang dilewati secara sengaja (bukan WARNING/ERROR)."""
        merged = dict(details or {})
        if reason:
            merged.setdefault("reason", reason)
        det_str = f"Reason: {reason}" if reason else ""
        return self.log(
            LogLevel.SKIPPED,
            module,
            message,
            det_str,
            details=merged,
            event_type=LogEventType.SKIPPED,
            run_id=run_id,
        )

    def log_processing_summary(self, summary: ProcessingRunSummary) -> LogEvent:
        """Mencatat blok PROCESSING SUMMARY di akhir pemrosesan otomatis (Bagian XX)."""
        block_text = summary.format_summary_block()
        return self.log(
            LogLevel.SECTION,
            LogModule.SESSION,
            f"PROCESSING SUMMARY ({summary.status})",
            details={
                "run_id": summary.run_id,
                "status": summary.status,
                "profile": summary.profile,
                "input_frames": summary.input_frames,
                "frames_processed": summary.frames_processed,
                "frames_excluded": summary.frames_excluded,
                "flat_calibration": summary.flat_calibration_status,
                "stacking": summary.stacking_status,
                "background": summary.background_status,
                "enhancement": summary.enhancement_status,
                "histogram": summary.histogram_status,
                "curve": summary.curve_status,
                "output_files": list(summary.output_files),
                "processing_time_sec": round(summary.processing_time_sec, 4),
            },
            event_type=LogEventType.SUMMARY,
            run_id=summary.run_id,
            raw_block=block_text,
        )

    def log_aligned_summary_block(
        self,
        sections_or_items: list[tuple[str, Any]],
        *,
        title: str = "OUTPUT SAVE SUMMARY",
        footer: str | None = None,
        module: str | LogModule = LogModule.OUTPUT,
        details: dict[str, Any] | None = None,
        run_id: str | None = None,
        min_verbosity: LogVerbosity = LogVerbosity.NORMAL,
    ) -> LogEvent:
        """Mencatat blok ringkasan tiga kolom sejajar (mis. Output Save Summary / Session Summary)."""
        block_text = format_aligned_summary(
            sections_or_items,
            title=title,
            footer=footer,
        )
        return self.log(
            LogLevel.SECTION,
            module,
            title,
            details=details,
            event_type=LogEventType.SUMMARY,
            run_id=run_id,
            min_verbosity=min_verbosity,
            raw_block=block_text,
        )

    # ------------------------------------------------------------------ Application Startup Log
    def log_application_startup(self) -> None:
        """Mencatat informasi inisialisasi aplikasi sesuai Bagian IX (tanpa mencatat data pribadi)."""
        with self._lock:
            if self._startup_logged:
                return
            self._startup_logged = True

        os_name = platform.system() or sys.platform
        os_ver = platform.version() or platform.release()
        arch = platform.machine() or "x64"
        py_ver = platform.python_version()
        qt_ver = qVersion() or PYSIDE_VERSION

        self.section("HILALONE APPLICATION STARTUP", module=LogModule.SYSTEM)
        self.info(
            LogModule.SYSTEM,
            f"{APP_NAME} v{__version__} initialized.",
            details={"version": __version__, "session_id": self.session_id},
        )
        self.info(
            LogModule.SYSTEM,
            f"Operating system: {os_name}.",
            details={"os_release": platform.release(), "os_build": os_ver},
        )
        self.info(
            LogModule.SYSTEM,
            f"Architecture: {arch}.",
        )
        self.info(
            LogModule.SYSTEM,
            f"Python runtime: {py_ver}.",
        )
        self.info(
            LogModule.SYSTEM,
            f"Qt framework initialized (Qt {qt_ver}, PySide6 {PYSIDE_VERSION}).",
        )
        self.success(
            LogModule.SYSTEM,
            "Logging initialized.",
            details={"log_dir": str(self.log_dir)},
        )
        self.success(
            LogModule.SYSTEM,
            "Application startup completed.",
        )

    # ------------------------------------------------------------------ Clear & Export
    def clear_console_view(self) -> None:
        """Membersihkan tampilan Console GUI saja tanpa menghapus riwayat sesi atau berkas log."""
        with self._lock:
            self._view_start_index = len(self._entries)
        self.view_cleared.emit()

    def clear(self) -> None:
        """Metode kompatibilitas untuk mengosongkan daftar aktif di memori tanpa menyentuh berkas log."""
        with self._lock:
            self._entries.clear()
            self._view_start_index = 0
        self.log_cleared.emit()

    def filter_entries(
        self,
        criteria: LogFilterCriteria,
        *,
        respect_view_clear: bool = True,
    ) -> list[LogEvent]:
        """Menyaring event sesuai kriteria filter dan status Clear Console."""
        with self._lock:
            source = (
                self._entries[self._view_start_index :]
                if respect_view_clear
                else list(self._session_history)
            )
        return filter_log_events(source, criteria)

    def default_export_filename(
        self,
        ext: str = "log",
        *,
        kind: str = "Complete",
        run_id: str | None = None,
    ) -> str:
        """Menghasilkan nama berkas ekspor standar: ``HILALONE_Log_Visible/Complete_YYYYMMDD_HHMMSS.log``."""
        stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
        clean_ext = ext.lstrip(".")
        clean_kind = kind.strip() if kind else "Complete"
        return f"HILALONE_Log_{clean_kind}_{stamp}.{clean_ext}"

    def export_events(
        self,
        path: Path | str,
        events: Iterable[LogEvent],
        *,
        format_override: str | None = None,
    ) -> Path:
        """Mengekspor kumpulan ``LogEvent`` ke format ``.log``/``.txt``, ``.jsonl``, ``.csv``, atau ``.json``."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        ext = (format_override or p.suffix).lower().lstrip(".")
        event_list = list(events)

        if ext == "jsonl":
            lines = [format_jsonl_line(e) for e in event_list]
            p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            return p

        if ext == "csv":
            with open(p, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Level", "Module", "Action", "Detail", "RunID"])
                for e in event_list:
                    writer.writerow([
                        e.timestamp,
                        e.level.value,
                        e.module,
                        e.action or e.message,
                        e.detail,
                        e.run_id,
                    ])
            return p

        if ext == "json":
            data = [
                {
                    "timestamp": e.timestamp,
                    "iso_timestamp": e.iso_timestamp,
                    "run_id": e.run_id,
                    "sequence": e.sequence,
                    "level": e.level.value,
                    "event_type": e.event_type.value,
                    "module": e.module,
                    "action": e.action or e.message,
                    "message": e.message,
                    "detail": e.detail,
                    "details": e.details,
                }
                for e in event_list
            ]
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            return p

        # Default: .log atau .txt
        lines = [format_console_line(e) for e in event_list]
        p.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return p

    def export_visible_log(
        self,
        path: Path | str,
        criteria: LogFilterCriteria,
        *,
        format_override: str | None = None,
    ) -> Path:
        """Mengekspor hanya baris log yang sedang terlihat (sesuai filter dan pencarian aktif)."""
        visible = self.filter_entries(criteria, respect_view_clear=True)
        return self.export_events(path, visible, format_override=format_override)

    def export_complete_log(
        self,
        path: Path | str,
        *,
        run_id: str | None = None,
        format_override: str | None = None,
    ) -> Path:
        """Mengekspor seluruh catatan sesi secara utuh tanpa terpengaruh filter tampilan ataupun Clear Console."""
        with self._lock:
            all_events = list(self._session_history)
        if run_id:
            q = run_id.strip().lower()
            all_events = [e for e in all_events if q in e.run_id.lower() or q in e.session_id.lower()]
        return self.export_events(path, all_events, format_override=format_override)

    # ------------------------------------------------------------------ Metode Kompatibilitas Lama
    def export_to_txt(self, path: Path | str) -> Path:
        with self._lock:
            evs = list(self._entries) if self._entries else list(self._session_history)
        return self.export_events(path, evs, format_override="txt")

    def export_to_csv(self, path: Path | str) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            evs = list(self._entries) if self._entries else list(self._session_history)
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "Level", "Module", "Action", "Detail"])
            for e in evs:
                writer.writerow([e.timestamp, e.level.value, e.module, e.action or e.message, e.detail])
        return p

    def export_to_json(self, path: Path | str) -> Path:
        with self._lock:
            evs = list(self._entries) if self._entries else list(self._session_history)
        return self.export_events(path, evs, format_override="json")


# ============================================================================
# SINGLETON / INSTANCE REGISTRY GLOBAL
# ============================================================================
_GLOBAL_LOGGER_LOCK = threading.RLock()
_GLOBAL_LOGGER: HilaloneLogger | None = None


def get_logger() -> HilaloneLogger:
    """Mengambil instance ``HilaloneLogger`` aktif aplikasi."""
    global _GLOBAL_LOGGER
    with _GLOBAL_LOGGER_LOCK:
        if _GLOBAL_LOGGER is None:
            _GLOBAL_LOGGER = HilaloneLogger()
        return _GLOBAL_LOGGER


def set_active_logger(logger_instance: HilaloneLogger | None) -> None:
    """Menetapkan instance ``HilaloneLogger`` aktif (mis. milik ``MainWindow``)."""
    global _GLOBAL_LOGGER
    with _GLOBAL_LOGGER_LOCK:
        _GLOBAL_LOGGER = logger_instance


# Alias untuk kompatibilitas mundur
LogManager = HilaloneLogger
