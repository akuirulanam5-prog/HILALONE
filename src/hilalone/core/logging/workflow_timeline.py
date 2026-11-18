"""Pelacak Kronologi Interaksi Pengguna, Interval Idle, dan Transaksi Penyimpanan (Report Schema v2.0).

Merekam seluruh perjalanan pengolahan citra HILALONE secara kronologis dan akurat:
  - Sejak pengguna pertama kali menekan Open Image (Session Start)
  - Hingga berkas foto hasil pemrosesan selesai ditulis ke disk (Session End).

Prinsip Pengukuran Waktu (Bagian VII, VIII, X, XI, XII):
  1. Seluruh timestamp kejadian menggunakan ISO-8601 lengkap dengan milidetik dan
     offset zona waktu sistem lokal (``YYYY-MM-DDTHH:MM:SS.mmm+HH:MM``).
  2. Seluruh selang durasi (``duration_ms``, ``interval_since_previous_action_ms``,
     ``action_to_operation_latency_ms``, ``workflow_idle_duration_ms``) dihitung
     menggunakan *monotonic performance counter* (``time.perf_counter()``) agar
     kebal terhadap loncatan jam sistem operasi.
  3. Memisahkan dengan tegas antara ``USER_ACTION``, ``OPERATION_STARTED``,
     ``OPERATION_COMPLETED``, ``OPERATION_FAILED``, ``OPERATION_SKIPPED``, dan
     ``WORKFLOW_IDLE_INTERVAL``.
  4. Tidak pernah merekam gerakan mouse, seluruh ketikan keyboard, isi clipboard,
     maupun kredensial pribadi pengguna.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import secrets
import threading
import time
from typing import Any

from hilalone.core.logging.aligned_summary import format_duration_seconds
from hilalone.core.logging.log_event import format_duration
from hilalone.core.logging.log_session import format_timestamps


def generate_report_id() -> str:
    """Menghasilkan ID unik untuk setiap berkas laporan ilmiah (``RPT-YYYYMMDD-HHMMSS-XXXXXX``)."""
    now = datetime.now().astimezone()
    suffix = secrets.token_hex(3).upper()
    return f"RPT-{now.strftime('%Y%m%d-%H%M%S')}-{suffix}"


def generate_transaction_id() -> str:
    """Menghasilkan ID unik untuk setiap transaksi penyimpanan output (``TX-YYYYMMDD-HHMMSS-XXXXXX``)."""
    now = datetime.now().astimezone()
    suffix = secrets.token_hex(3).upper()
    return f"TX-{now.strftime('%Y%m%d-%H%M%S')}-{suffix}"


def format_utc_timestamp(dt: datetime | None = None) -> str:
    """Memformat waktu UTC dalam ISO-8601 milidetik (``YYYY-MM-DDTHH:MM:SS.mmmZ``)."""
    now_utc = (dt or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ms = now_utc.microsecond // 1000
    return f"{now_utc.strftime('%Y-%m-%dT%H:%M:%S')}.{ms:03d}Z"


class TimelineEventType(str, Enum):
    """Kategori peristiwa pada User Interaction & Processing Timeline."""

    USER_ACTION = "USER_ACTION"
    OPERATION_STARTED = "OPERATION_STARTED"
    OPERATION_COMPLETED = "OPERATION_COMPLETED"
    OPERATION_FAILED = "OPERATION_FAILED"
    OPERATION_SKIPPED = "OPERATION_SKIPPED"
    WORKFLOW_IDLE_INTERVAL = "WORKFLOW_IDLE_INTERVAL"


# Pemetaan kode aksi ke deskripsi manusia untuk Human-Readable Timeline (Bagian XV)
_HUMAN_ACTION_LABELS: dict[str, str] = {
    "OPEN_IMAGE_CLICKED": "Open Image clicked",
    "MULTIPLE_IMAGES_CLICKED": "Multiple Images clicked",
    "OPEN_FOLDER_SEQUENCE_CLICKED": "Open Folder Sequence clicked",
    "VIDEO_CLICKED": "Video clicked",
    "SER_CLICKED": "SER clicked",
    "FILE_SELECTION_COMPLETED": "File selection completed",
    "FILE_DIALOG_CANCELLED": "File dialog cancelled",
    "INPUT_LOADING_STARTED": "Image loading started",
    "INPUT_LOADING_COMPLETED": "Image loaded successfully",
    "INPUT_VALIDATION_STARTED": "Sequence validation started",
    "INPUT_VALIDATION_COMPLETED": "Sequence validation completed",
    "APPLY_FLAT_ENABLED": "Apply Flat Calibration enabled",
    "APPLY_FLAT_DISABLED": "Apply Flat Calibration disabled",
    "SELECT_MASTER_FLAT_CLICKED": "Select Master Flat clicked",
    "FLAT_FILE_SELECTED": "Master Flat selected",
    "MASTER_FLAT_GENERATION_STARTED": "Master Flat generation started",
    "MASTER_FLAT_GENERATION_COMPLETED": "Master Flat generated and validated",
    "START_CALIBRATION_CLICKED": "Start Calibration clicked",
    "PREVIEW_FLAT_CLICKED": "Preview Flat clicked",
    "PROFILE_SELECTED": "Processing profile selected",
    "ADVANCED_SETTINGS_OPENED": "Advanced Settings opened",
    "ADVANCED_PARAMETER_CHANGED": "Advanced parameter changed",
    "START_AUTOMATIC_PROCESSING_CLICKED": "Start Automated Processing clicked",
    "START_STACKING_CLICKED": "Start Stacking clicked",
    "CANCEL_CLICKED": "Cancel clicked",
    "AUTOMATED_PROCESSING_STARTED": "Processing backend started",
    "AUTOMATED_PROCESSING_COMPLETED": "Automated processing completed",
    "AUTOMATED_PROCESSING_FAILED": "Automated processing failed",
    "AUTOMATED_PROCESSING_CANCELLED": "Automated processing cancelled",
    "FLAT_CALIBRATION_STARTED": "Flat Calibration started",
    "FLAT_CALIBRATION_COMPLETED": "Flat Calibration completed",
    "FLAT_CALIBRATION_SKIPPED": "Flat Calibration skipped",
    "STACKING_STARTED": "Image Stacking started",
    "STACKING_COMPLETED": "Stacking completed",
    "STACKING_SKIPPED": "Image Stacking skipped",
    "BACKGROUND_EXTRACTION_STARTED": "Background Extraction started",
    "BACKGROUND_EXTRACTION_COMPLETED": "Background Extraction completed",
    "IMAGE_ENHANCEMENT_STARTED": "Image Enhancement started",
    "IMAGE_ENHANCEMENT_COMPLETED": "Image Enhancement completed",
    "IMAGE_ENHANCEMENT_SKIPPED": "Image Enhancement skipped",
    "HISTOGRAM_TRANSFORMATION_STARTED": "Histogram Transformation started",
    "HISTOGRAM_TRANSFORMATION_COMPLETED": "Histogram Transformation completed",
    "PREVIEW_MODE_CHANGED": "Preview mode changed",
    "BEFORE_AFTER_ENABLED": "Before/After comparison toggled",
    "HISTOGRAM_WINDOW_OPENED": "Histogram window opened",
    "CURVE_WINDOW_OPENED": "Curve window opened",
    "CURVE_APPLIED": "Curve transformation applied",
    "INFORMATION_WINDOW_OPENED": "Information window opened",
    "SAVE_CLICKED": "Save Image clicked",
    "SAVE_DIALOG_OPENED": "Save dialog opened",
    "OUTPUT_FILENAME_CONFIRMED": "Output filename confirmed",
    "OUTPUT_WRITE_STARTED": "Image writing started",
    "OUTPUT_WRITE_COMPLETED": "Image saved successfully",
    "OUTPUT_WRITE_FAILED": "Image writing failed",
}


@dataclass(frozen=True)
class TimelineEvent:
    """Satu peristiwa kronologis pada User Interaction & Operation Timeline."""

    sequence: int
    event_id: str
    event_type: str
    action: str
    timestamp: str
    timestamp_utc: str
    ui_time: str
    monotonic_s: float
    module: str
    action_result: str
    interval_since_previous_action_ms: float | None = None
    interval_since_previous_action_display: str | None = None
    action_to_operation_latency_ms: float | None = None
    action_to_operation_latency_display: str | None = None
    duration_ms: float | None = None
    duration_display: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Menghasilkan representasi dictionary JSON Schema v2.0."""
        payload: dict[str, Any] = {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "action": self.action,
            "timestamp": self.timestamp,
            "timestamp_utc": self.timestamp_utc,
            "module": self.module,
            "action_result": self.action_result,
            "interval_since_previous_action_ms": (
                round(self.interval_since_previous_action_ms, 3)
                if self.interval_since_previous_action_ms is not None
                else None
            ),
            "interval_since_previous_action_display": self.interval_since_previous_action_display,
        }
        if self.action_to_operation_latency_ms is not None:
            payload["action_to_operation_latency_ms"] = round(self.action_to_operation_latency_ms, 3)
            payload["action_to_operation_latency_display"] = self.action_to_operation_latency_display
        if self.duration_ms is not None:
            payload["duration_ms"] = round(self.duration_ms, 3)
            payload["duration_display"] = self.duration_display
        if self.details:
            payload["details"] = dict(self.details)
        return payload


@dataclass(frozen=True)
class WorkflowIdleInterval:
    """Catatan eksplisit ketika aplikasi tidak sedang menjalankan proses backend dan menunggu aksi berikutnya."""

    interval_id: str
    started_at: str
    ended_at: str
    duration_ms: float
    duration_display: str
    preceding_event: str
    following_action: str
    app_window_state: str = "FOREGROUND"
    interval_type: str = "WORKFLOW_IDLE_INTERVAL"
    description: str = "Application was not processing and was waiting for the next workflow action."

    def to_dict(self) -> dict[str, Any]:
        return {
            "interval_id": self.interval_id,
            "interval_type": self.interval_type,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": round(self.duration_ms, 3),
            "duration_display": self.duration_display,
            "preceding_event": self.preceding_event,
            "following_action": self.following_action,
            "app_window_state": self.app_window_state,
            "description": self.description,
        }


@dataclass
class OutputArtifactRecord:
    """Metadata untuk satu berkas hasil pemrosesan yang disimpan ke disk."""

    artifact_id: str
    filename: str
    format: str
    save_target: str
    data_type: str
    bit_depth: int
    dimensions: str
    width: int
    height: int
    channels: int
    path: str
    file_size_bytes: int
    started_at: str
    completed_at: str
    duration_ms: float
    duration_display: str
    save_status: str
    verified_on_disk: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "filename": self.filename,
            "format": self.format,
            "save_target": self.save_target,
            "data_type": self.data_type,
            "bit_depth": self.bit_depth,
            "dimensions": self.dimensions,
            "width": self.width,
            "height": self.height,
            "channels": self.channels,
            "path": self.path,
            "file_size_bytes": self.file_size_bytes,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": round(self.duration_ms, 3),
            "duration_display": self.duration_display,
            "save_status": self.save_status,
            "verified_on_disk": self.verified_on_disk,
        }


@dataclass
class SaveTransactionContext:
    """Konteks pengukuran waktu untuk satu transaksi Save (memisahkan dialog dari penulisan disk)."""

    transaction_id: str
    run_id: str
    save_clicked_at: str
    save_clicked_mono: float
    save_dialog_opened_at: str | None = None
    save_dialog_opened_mono: float | None = None
    save_dialog_confirmed_at: str | None = None
    save_dialog_confirmed_mono: float | None = None
    output_write_started_at: str | None = None
    output_write_started_mono: float | None = None
    output_write_completed_at: str | None = None
    output_write_completed_mono: float | None = None
    save_dialog_duration_ms: float | None = None
    image_write_duration_ms: float = 0.0
    save_transaction_duration_ms: float = 0.0
    artifacts: list[OutputArtifactRecord] = field(default_factory=list)


class WorkflowTimelineTracker:
    """Manajer pencatatan kronologis interaksi pengguna, operasi backend, dan durasi workflow.

    Menggunakan satu sumber waktu monotonic (``time.perf_counter()``) untuk seluruh
    perhitungan durasi dan timestamp ISO-8601 zona waktu lokal untuk waktu kejadian.
    """

    # Ambang batas minimum (ms) agar jeda penjadwalan OS/GUI kecil tidak dicatat sebagai idle pengguna
    DEFAULT_IDLE_THRESHOLD_MS: float = 25.0

    def __init__(self, *, idle_threshold_ms: float = DEFAULT_IDLE_THRESHOLD_MS) -> None:
        self._lock = threading.RLock()
        self._idle_threshold_ms = max(1.0, float(idle_threshold_ms))
        self.reset_for_new_source_session()

    def reset_for_new_source_session(self) -> None:
        """Mereset dan memulai pelacakan sesi baru saat pengguna mulai membuka sumber citra."""
        now_dt = datetime.now().astimezone()
        ui_ts, iso_ts = format_timestamps(now_dt)
        mono_now = time.perf_counter()
        with self._lock:
            self._sequence_counter: int = 0
            self._idle_counter: int = 0
            self._artifact_counter: int = 0
            self._events: list[TimelineEvent] = []
            self._idle_intervals: list[WorkflowIdleInterval] = []
            self._save_transactions: list[dict[str, Any]] = []
            self._active_save_tx: SaveTransactionContext | None = None

            self._session_start_timestamp: str = iso_ts
            self._session_start_utc: str = format_utc_timestamp(now_dt)
            self._session_start_mono: float = mono_now
            self._session_end_timestamp: str | None = None
            self._session_end_utc: str | None = None
            self._session_end_mono: float | None = None

            self._last_user_action_mono: float | None = None
            self._last_user_action_name: str | None = None
            self._pending_trigger_action_mono: float | None = None

            self._active_backend_ops: int = 0
            self._idle_started_mono: float | None = None
            self._idle_started_iso: str | None = None
            self._idle_preceding_event: str = "SESSION_INITIALIZED"

            # Statistik durasi per tahap di luar PipelineOrchestrator (mis. input loading, curve, master flat)
            self._input_loading_started_at: str | None = None
            self._input_loading_completed_at: str | None = None
            self._input_loading_duration_ms: float | None = None

            self._input_validation_started_at: str | None = None
            self._input_validation_completed_at: str | None = None
            self._input_validation_duration_ms: float | None = None

            self._master_flat_record: dict[str, Any] | None = None
            self._curve_record: dict[str, Any] | None = None
            self._display_record: dict[str, Any] | None = None
            self._pipeline_started_at: str | None = None
            self._pipeline_completed_at: str | None = None
            self._pipeline_elapsed_ms: float | None = None
            self._source_entries_snapshot: list[Any] = []
            self._single_image_info_snapshot: Any = None
            self._user_config_snapshot: dict[str, Any] = {}

    # ------------------------------------------------------------------ Properties
    @property
    def session_start_timestamp(self) -> str:
        with self._lock:
            return self._session_start_timestamp

    @property
    def session_end_timestamp(self) -> str | None:
        with self._lock:
            return self._session_end_timestamp

    @property
    def events(self) -> tuple[TimelineEvent, ...]:
        with self._lock:
            return tuple(self._events)

    @property
    def idle_intervals(self) -> tuple[WorkflowIdleInterval, ...]:
        with self._lock:
            return tuple(self._idle_intervals)

    # ------------------------------------------------------------------ Context Snapshots
    def mark_session_open_triggered(self) -> None:
        """Menandai waktu awal sesi (SESSION START) ketika pengguna menekan tombol Open Image."""
        now_dt = datetime.now().astimezone()
        _, iso_ts = format_timestamps(now_dt)
        mono_now = time.perf_counter()
        with self._lock:
            if not self._events:
                self._session_start_timestamp = iso_ts
                self._session_start_utc = format_utc_timestamp(now_dt)
                self._session_start_mono = mono_now

    def update_source_snapshot(
        self,
        *,
        single_info: Any = None,
        sequence_entries: tuple[Any, ...] | list[Any] = (),
    ) -> None:
        """Menyimpan referensi metadata sumber citra untuk deduplikasi bagian source_data."""
        with self._lock:
            self._single_image_info_snapshot = single_info
            self._source_entries_snapshot = list(sequence_entries)

    def update_user_configuration(self, config_dict: dict[str, Any]) -> None:
        """Memperbarui snapshot konfigurasi pemrosesan yang dipilih pengguna."""
        with self._lock:
            self._user_config_snapshot.update(config_dict)

    # ------------------------------------------------------------------ Core Event Recording
    def record_user_action(
        self,
        action: str,
        *,
        module: str = "INPUT",
        action_result: str = "RECORDED",
        details: dict[str, Any] | None = None,
        app_window_state: str = "FOREGROUND",
        is_operation_trigger: bool = False,
    ) -> TimelineEvent:
        """Mencatat satu tindakan bermakna dari pengguna (USER_ACTION) beserta intervalnya."""
        now_dt = datetime.now().astimezone()
        ui_ts, iso_ts = format_timestamps(now_dt)
        utc_ts = format_utc_timestamp(now_dt)
        mono_now = time.perf_counter()

        with self._lock:
            if not self._events:
                self._session_start_timestamp = iso_ts
                self._session_start_utc = utc_ts
                self._session_start_mono = mono_now

            # 1. Jika tidak ada backend processing aktif dan ada periode tunggu sebelumnya,
            #    evaluasi apakah terbentuk WORKFLOW_IDLE_INTERVAL yang bermakna.
            if self._active_backend_ops == 0 and self._idle_started_mono is not None and self._idle_started_iso is not None:
                idle_ms = max(0.0, (mono_now - self._idle_started_mono) * 1000.0)
                if idle_ms >= self._idle_threshold_ms:
                    self._idle_counter += 1
                    idle_rec = WorkflowIdleInterval(
                        interval_id=f"IDLE-{self._idle_counter:04d}",
                        started_at=self._idle_started_iso,
                        ended_at=iso_ts,
                        duration_ms=idle_ms,
                        duration_display=format_duration_seconds(idle_ms),
                        preceding_event=self._idle_preceding_event,
                        following_action=action,
                        app_window_state=app_window_state,
                    )
                    self._idle_intervals.append(idle_rec)
                # Reset titik mulai idle ke setelah aksi pengguna ini selesai
                self._idle_started_mono = mono_now
                self._idle_started_iso = iso_ts
                self._idle_preceding_event = action

            # 2. Hitung interval sejak tindakan pengguna (USER_ACTION) sebelumnya
            interval_ms: float | None = None
            interval_disp: str | None = None
            if self._last_user_action_mono is not None:
                interval_ms = max(0.0, (mono_now - self._last_user_action_mono) * 1000.0)
                interval_disp = format_duration_seconds(interval_ms)

            self._last_user_action_mono = mono_now
            self._last_user_action_name = action
            if is_operation_trigger:
                self._pending_trigger_action_mono = mono_now

            self._sequence_counter += 1
            ev = TimelineEvent(
                sequence=self._sequence_counter,
                event_id=f"EVT-{self._sequence_counter:04d}",
                event_type=TimelineEventType.USER_ACTION.value,
                action=action,
                timestamp=iso_ts,
                timestamp_utc=utc_ts,
                ui_time=ui_ts,
                monotonic_s=mono_now,
                module=module,
                action_result=action_result,
                interval_since_previous_action_ms=interval_ms,
                interval_since_previous_action_display=interval_disp,
                details=dict(details or {}),
            )
            self._events.append(ev)
            return ev

    def record_operation_started(
        self,
        action: str,
        *,
        module: str = "SESSION",
        details: dict[str, Any] | None = None,
    ) -> TimelineEvent:
        """Mencatat saat backend benar-benar memulai suatu operasi (OPERATION_STARTED)."""
        now_dt = datetime.now().astimezone()
        ui_ts, iso_ts = format_timestamps(now_dt)
        utc_ts = format_utc_timestamp(now_dt)
        mono_now = time.perf_counter()

        with self._lock:
            latency_ms: float | None = None
            latency_disp: str | None = None
            ref_mono = self._pending_trigger_action_mono or self._last_user_action_mono
            if ref_mono is not None:
                latency_ms = max(0.0, (mono_now - ref_mono) * 1000.0)
                latency_disp = format_duration_seconds(latency_ms)
            self._pending_trigger_action_mono = None

            # Selama operasi backend berjalan, aplikasi TIDAK dalam kondisi idle
            self._active_backend_ops += 1
            self._idle_started_mono = None
            self._idle_started_iso = None

            if action == "INPUT_LOADING_STARTED":
                self._input_loading_started_at = iso_ts
            elif action == "INPUT_VALIDATION_STARTED":
                self._input_validation_started_at = iso_ts
            elif action == "AUTOMATED_PROCESSING_STARTED":
                self._pipeline_started_at = iso_ts

            self._sequence_counter += 1
            ev = TimelineEvent(
                sequence=self._sequence_counter,
                event_id=f"EVT-{self._sequence_counter:04d}",
                event_type=TimelineEventType.OPERATION_STARTED.value,
                action=action,
                timestamp=iso_ts,
                timestamp_utc=utc_ts,
                ui_time=ui_ts,
                monotonic_s=mono_now,
                module=module,
                action_result="STARTED",
                action_to_operation_latency_ms=latency_ms,
                action_to_operation_latency_display=latency_disp,
                details=dict(details or {}),
            )
            self._events.append(ev)
            return ev

    def record_operation_completed(
        self,
        action: str,
        *,
        module: str = "SESSION",
        duration_ms: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> TimelineEvent:
        """Mencatat saat backend berhasil menyelesaikan suatu operasi (OPERATION_COMPLETED)."""
        now_dt = datetime.now().astimezone()
        ui_ts, iso_ts = format_timestamps(now_dt)
        utc_ts = format_utc_timestamp(now_dt)
        mono_now = time.perf_counter()

        with self._lock:
            self._active_backend_ops = max(0, self._active_backend_ops - 1)
            if self._active_backend_ops == 0:
                self._idle_started_mono = mono_now
                self._idle_started_iso = iso_ts
                self._idle_preceding_event = action

            dur_disp = format_duration_seconds(duration_ms) if duration_ms is not None else None

            if action == "INPUT_LOADING_COMPLETED":
                self._input_loading_completed_at = iso_ts
                if duration_ms is not None:
                    self._input_loading_duration_ms = float(duration_ms)
            elif action == "INPUT_VALIDATION_COMPLETED":
                self._input_validation_completed_at = iso_ts
                if duration_ms is not None:
                    self._input_validation_duration_ms = float(duration_ms)
            elif action == "AUTOMATED_PROCESSING_COMPLETED":
                self._pipeline_completed_at = iso_ts
                if duration_ms is not None:
                    self._pipeline_elapsed_ms = float(duration_ms)

            self._sequence_counter += 1
            ev = TimelineEvent(
                sequence=self._sequence_counter,
                event_id=f"EVT-{self._sequence_counter:04d}",
                event_type=TimelineEventType.OPERATION_COMPLETED.value,
                action=action,
                timestamp=iso_ts,
                timestamp_utc=utc_ts,
                ui_time=ui_ts,
                monotonic_s=mono_now,
                module=module,
                action_result="COMPLETED",
                duration_ms=duration_ms,
                duration_display=dur_disp,
                details=dict(details or {}),
            )
            self._events.append(ev)
            return ev

    def record_operation_failed(
        self,
        action: str,
        *,
        module: str = "SESSION",
        reason: str = "",
        duration_ms: float | None = None,
        details: dict[str, Any] | None = None,
    ) -> TimelineEvent:
        """Mencatat saat suatu operasi gagal (OPERATION_FAILED)."""
        now_dt = datetime.now().astimezone()
        ui_ts, iso_ts = format_timestamps(now_dt)
        utc_ts = format_utc_timestamp(now_dt)
        mono_now = time.perf_counter()

        with self._lock:
            self._active_backend_ops = max(0, self._active_backend_ops - 1)
            if self._active_backend_ops == 0:
                self._idle_started_mono = mono_now
                self._idle_started_iso = iso_ts
                self._idle_preceding_event = action

            merged = dict(details or {})
            if reason:
                merged["reason"] = reason
            dur_disp = format_duration_seconds(duration_ms) if duration_ms is not None else None

            self._sequence_counter += 1
            ev = TimelineEvent(
                sequence=self._sequence_counter,
                event_id=f"EVT-{self._sequence_counter:04d}",
                event_type=TimelineEventType.OPERATION_FAILED.value,
                action=action,
                timestamp=iso_ts,
                timestamp_utc=utc_ts,
                ui_time=ui_ts,
                monotonic_s=mono_now,
                module=module,
                action_result="FAILED",
                duration_ms=duration_ms,
                duration_display=dur_disp,
                details=merged,
            )
            self._events.append(ev)
            return ev

    def record_operation_skipped(
        self,
        action: str,
        *,
        module: str = "SESSION",
        reason: str = "",
        details: dict[str, Any] | None = None,
    ) -> TimelineEvent:
        """Mencatat saat tahapan opsional sengaja dilewati (OPERATION_SKIPPED)."""
        now_dt = datetime.now().astimezone()
        ui_ts, iso_ts = format_timestamps(now_dt)
        utc_ts = format_utc_timestamp(now_dt)
        mono_now = time.perf_counter()

        with self._lock:
            merged = dict(details or {})
            if reason:
                merged["reason"] = reason
            self._sequence_counter += 1
            ev = TimelineEvent(
                sequence=self._sequence_counter,
                event_id=f"EVT-{self._sequence_counter:04d}",
                event_type=TimelineEventType.OPERATION_SKIPPED.value,
                action=action,
                timestamp=iso_ts,
                timestamp_utc=utc_ts,
                ui_time=ui_ts,
                monotonic_s=mono_now,
                module=module,
                action_result="SKIPPED",
                duration_ms=None,
                duration_display=None,
                details=merged,
            )
            self._events.append(ev)
            return ev

    # ------------------------------------------------------------------ Stage Metadata Recording
    def record_master_flat_details(
        self,
        *,
        aggregation_method: str,
        normalization_method: str,
        input_flat_count: int,
        output_dimensions: str,
        data_type: str,
        invalid_pixels: int,
        duration_ms: float,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> None:
        """Menyimpan metadata aktual pembuatan/persiapan Master Flat."""
        now_iso = format_timestamps()[1]
        with self._lock:
            self._master_flat_record = {
                "stage_id": "STAGE_04_MASTER_FLAT",
                "stage_name": "Master Flat Generation",
                "status": "COMPLETED",
                "started_at": started_at or now_iso,
                "completed_at": completed_at or now_iso,
                "duration_ms": round(float(duration_ms), 3),
                "duration_display": format_duration_seconds(duration_ms),
                "input": {"flat_frame_count": int(input_flat_count)},
                "parameters": {
                    "aggregation_method": aggregation_method,
                    "normalization_method": normalization_method,
                },
                "output": {
                    "dimensions": output_dimensions,
                    "data_type": data_type,
                },
                "metrics": {
                    "invalid_pixel_count": int(invalid_pixels),
                },
                "warnings": [],
            }

    def record_curve_processing_details(
        self,
        *,
        channel: str,
        control_points: list[tuple[float, float]] | list[list[float]],
        duration_ms: float,
        input_branch: str = "DISPLAY",
        output_branch: str = "DISPLAY_CURVE_ADJUSTED",
    ) -> None:
        """Menyimpan metadata aktual ketika pengguna menerapkan Curve Transformation."""
        now_iso = format_timestamps()[1]
        pts = [[round(float(x), 4), round(float(y), 4)] for x, y in control_points]
        with self._lock:
            self._curve_record = {
                "stage_id": "STAGE_09_CURVE_PROCESSING",
                "stage_name": "Curve Processing",
                "status": "COMPLETED",
                "started_at": now_iso,
                "completed_at": now_iso,
                "duration_ms": round(float(duration_ms), 3),
                "duration_display": format_duration_seconds(duration_ms),
                "input": {"branch": input_branch},
                "parameters": {
                    "curve_method": "PCHIP_MONOTONIC_CUBIC_INTERPOLATION",
                    "channel": channel,
                    "control_point_count": len(pts),
                    "control_points": pts,
                },
                "output": {"branch": output_branch},
                "metrics": {},
                "warnings": [],
            }
        self.record_user_action(
            "CURVE_APPLIED",
            module="CURVE",
            action_result="COMPLETED",
            details={
                "channel": channel,
                "control_point_count": len(pts),
                "duration_ms": round(float(duration_ms), 3),
            },
        )

    def record_display_generation_details(
        self,
        *,
        display_mode: str,
        display_branch: str = "DISPLAY",
        normalization: str = "[0.0, 1.0] -> uint8 [0, 255]",
        output_dtype: str = "float32",
        output_range: tuple[float, float] = (0.0, 1.0),
        duration_ms: float = 0.0,
    ) -> None:
        """Menyimpan metadata pembuatan cabang tampilan (Display Generation)."""
        now_iso = format_timestamps()[1]
        with self._lock:
            self._display_record = {
                "stage_id": "STAGE_10_DISPLAY_GENERATION",
                "stage_name": "Display Generation",
                "status": "COMPLETED",
                "started_at": now_iso,
                "completed_at": now_iso,
                "duration_ms": round(float(duration_ms), 3),
                "duration_display": format_duration_seconds(duration_ms),
                "input": {"branch": display_branch},
                "parameters": {
                    "display_mode": display_mode,
                    "normalization": normalization,
                },
                "output": {
                    "data_type": output_dtype,
                    "output_range": [round(float(output_range[0]), 6), round(float(output_range[1]), 6)],
                },
                "metrics": {},
                "warnings": [],
            }

    # ------------------------------------------------------------------ Save Transaction Lifecycle
    def begin_save_transaction(self, *, run_id: str, save_target: str = "LINEAR") -> str:
        """Memulai satu Save Transaction ketika pengguna menekan tombol Save."""
        tx_id = generate_transaction_id()
        ev = self.record_user_action(
            "SAVE_CLICKED",
            module="OUTPUT",
            details={"transaction_id": tx_id, "save_target": save_target},
            is_operation_trigger=True,
        )
        with self._lock:
            self._active_save_tx = SaveTransactionContext(
                transaction_id=tx_id,
                run_id=run_id,
                save_clicked_at=ev.timestamp,
                save_clicked_mono=ev.monotonic_s,
            )
        return tx_id

    def mark_save_dialog_opened(self) -> None:
        """Mencatat saat dialog Save File dibuka."""
        ev = self.record_user_action("SAVE_DIALOG_OPENED", module="OUTPUT")
        with self._lock:
            if self._active_save_tx is not None:
                self._active_save_tx.save_dialog_opened_at = ev.timestamp
                self._active_save_tx.save_dialog_opened_mono = ev.monotonic_s

    def mark_save_dialog_confirmed(self, target_path: str) -> None:
        """Mencatat saat pengguna mengonfirmasi nama dan lokasi berkas pada dialog Save File."""
        now_dt = datetime.now().astimezone()
        _, iso_ts = format_timestamps(now_dt)
        mono_now = time.perf_counter()
        with self._lock:
            dlg_ms: float | None = None
            if self._active_save_tx is not None:
                self._active_save_tx.save_dialog_confirmed_at = iso_ts
                self._active_save_tx.save_dialog_confirmed_mono = mono_now
                if self._active_save_tx.save_dialog_opened_mono is not None:
                    dlg_ms = max(0.0, (mono_now - self._active_save_tx.save_dialog_opened_mono) * 1000.0)
                    self._active_save_tx.save_dialog_duration_ms = dlg_ms

        self.record_user_action(
            "OUTPUT_FILENAME_CONFIRMED",
            module="OUTPUT",
            details={
                "filename": target_path,
                "save_dialog_duration_ms": round(dlg_ms, 3) if dlg_ms is not None else None,
            },
            is_operation_trigger=True,
        )

    def mark_output_write_started(self, target_path: str, *, run_id: str = "") -> SaveTransactionContext:
        """Mencatat saat backend mulai menulis berkas gambar ke penyimpanan."""
        with self._lock:
            if self._active_save_tx is None:
                now_iso = format_timestamps()[1]
                mono_now = time.perf_counter()
                self._active_save_tx = SaveTransactionContext(
                    transaction_id=generate_transaction_id(),
                    run_id=run_id,
                    save_clicked_at=now_iso,
                    save_clicked_mono=mono_now,
                )
            tx = self._active_save_tx

        ev = self.record_operation_started(
            "OUTPUT_WRITE_STARTED",
            module="OUTPUT",
            details={"transaction_id": tx.transaction_id, "path": target_path},
        )
        with self._lock:
            tx.output_write_started_at = ev.timestamp
            tx.output_write_started_mono = ev.monotonic_s
            return tx

    def mark_output_write_completed(
        self,
        *,
        filename: str,
        fmt: str,
        save_target: str,
        data_type: str,
        bit_depth: int,
        width: int,
        height: int,
        channels: int,
        path: str,
        file_size_bytes: int,
        verified_on_disk: bool,
    ) -> tuple[SaveTransactionContext, OutputArtifactRecord]:
        """Mencatat saat penulisan berkas gambar selesai dan memperbarui SESSION END."""
        now_dt = datetime.now().astimezone()
        _, iso_ts = format_timestamps(now_dt)
        utc_ts = format_utc_timestamp(now_dt)
        mono_now = time.perf_counter()

        with self._lock:
            if self._active_save_tx is None:
                self._active_save_tx = SaveTransactionContext(
                    transaction_id=generate_transaction_id(),
                    run_id="",
                    save_clicked_at=iso_ts,
                    save_clicked_mono=mono_now,
                    output_write_started_at=iso_ts,
                    output_write_started_mono=mono_now,
                )
            tx = self._active_save_tx
            start_mono = tx.output_write_started_mono if tx.output_write_started_mono is not None else mono_now
            write_ms = max(0.0, (mono_now - start_mono) * 1000.0)
            tx_ms = max(0.0, (mono_now - tx.save_clicked_mono) * 1000.0)

            tx.output_write_completed_at = iso_ts
            tx.output_write_completed_mono = mono_now
            tx.image_write_duration_ms = write_ms
            tx.save_transaction_duration_ms = tx_ms

            self._artifact_counter += 1
            art_id = f"ART-{self._artifact_counter:03d}"
            art = OutputArtifactRecord(
                artifact_id=art_id,
                filename=filename,
                format=fmt,
                save_target=save_target,
                data_type=data_type,
                bit_depth=bit_depth,
                dimensions=f"{width}x{height}" if channels == 1 else f"{width}x{height}x{channels}",
                width=width,
                height=height,
                channels=channels,
                path=path,
                file_size_bytes=file_size_bytes,
                started_at=tx.output_write_started_at or iso_ts,
                completed_at=iso_ts,
                duration_ms=write_ms,
                duration_display=format_duration_seconds(write_ms),
                save_status="SAVED" if verified_on_disk else "UNVERIFIED",
                verified_on_disk=verified_on_disk,
            )
            tx.artifacts.append(art)

            # SESSION END didefinisikan saat foto hasil selesai ditulis dengan sukses
            self._session_end_timestamp = iso_ts
            self._session_end_utc = utc_ts
            self._session_end_mono = mono_now

        self.record_operation_completed(
            "OUTPUT_WRITE_COMPLETED",
            module="OUTPUT",
            duration_ms=write_ms,
            details={
                "transaction_id": tx.transaction_id,
                "artifact_id": art.artifact_id,
                "filename": filename,
                "format": fmt,
                "file_size_bytes": file_size_bytes,
                "verified_on_disk": verified_on_disk,
            },
        )
        return tx, art

    def finalize_save_transaction(self) -> None:
        """Menutup transaksi save aktif setelah laporan pendamping selesai diproses."""
        with self._lock:
            self._active_save_tx = None

    # ------------------------------------------------------------------ Human-Readable Timeline
    def build_human_readable_timeline_lines(self) -> list[str]:
        """Menyusun daftar baris timeline kronologis yang mudah dibaca manusia (Bagian XV)."""
        with self._lock:
            events_copy = list(self._events)
            idles_copy = list(self._idle_intervals)

        # Gabungkan events dan idle intervals secara kronologis
        lines: list[str] = []
        idle_by_following: dict[tuple[str, str], WorkflowIdleInterval] = {
            (idl.ended_at, idl.following_action): idl for idl in idles_copy
        }

        for ev in events_copy:
            idl = idle_by_following.get((ev.timestamp, ev.action))
            if idl is not None:
                idle_start_time = idl.started_at.split("T")[-1][:12] if "T" in idl.started_at else idl.started_at
                lines.append(f"{idle_start_time}  Workflow idle started")
                label = _HUMAN_ACTION_LABELS.get(ev.action, ev.action.replace("_", " ").capitalize())
                lines.append(f"{ev.ui_time}  {label}")
                lines.append(f"              Workflow idle duration: {idl.duration_display}")
                continue

            label = _HUMAN_ACTION_LABELS.get(ev.action, ev.action.replace("_", " ").capitalize())
            suffix_parts: list[str] = []
            if ev.duration_display is not None:
                suffix_parts.append(f"Duration: {ev.duration_display}")
            elif ev.action_to_operation_latency_display is not None and ev.event_type == TimelineEventType.OPERATION_STARTED.value:
                suffix_parts.append(f"Startup latency: {ev.action_to_operation_latency_display}")

            if suffix_parts:
                lines.append(f"{ev.ui_time}  {label} ({', '.join(suffix_parts)})")
            else:
                lines.append(f"{ev.ui_time}  {label}")

        return lines
