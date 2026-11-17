"""Manajemen Session ID, Processing Run ID, dan perekam riwayat sesi pemrosesan HILALONE.

Memenuhi Bagian IV dan XXVII:
  - Setiap aplikasi berjalan memiliki Application Session ID unik.
  - Setiap kali Automated Processing / Stacking dijalankan, dibuat Processing Run ID unik.
  - Menggunakan ``time.monotonic()`` untuk mengukur durasi proses agar kebal terhadap
    perubahan jam sistem.
  - Riwayat sesi lama tidak pernah dihapus ketika pengguna memulai proses baru atau
    membuka gambar baru.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import threading
import time
from typing import Any
import uuid


def format_timestamps(dt: datetime | None = None) -> tuple[str, str]:
    """Menghasilkan pasangan ``(ui_timestamp, iso_timestamp)`` dengan presisi milidetik.

    Returns:
        - ``ui_timestamp``  : ``HH:MM:SS.mmm`` (contoh: ``20:15:03.125``)
        - ``iso_timestamp`` : ISO 8601 dengan offset zona waktu lokal
                              (contoh: ``2026-11-17T20:15:03.125+07:00``)
    """
    now = dt if dt is not None else datetime.now().astimezone()
    if now.tzinfo is None:
        now = now.astimezone()
    ms = now.microsecond // 1000
    ui_ts = f"{now.strftime('%H:%M:%S')}.{ms:03d}"
    tz_raw = now.strftime("%z")
    if len(tz_raw) == 5:
        tz_iso = f"{tz_raw[:3]}:{tz_raw[3:]}"
    else:
        tz_iso = "+00:00"
    iso_ts = f"{now.strftime('%Y-%m-%dT%H:%M:%S')}.{ms:03d}{tz_iso}"
    return ui_ts, iso_ts


def generate_session_id(dt: datetime | None = None) -> str:
    """Membuat Application Session ID unik saat aplikasi dibuka."""
    now = dt if dt is not None else datetime.now().astimezone()
    short_hex = uuid.uuid4().hex[:6].upper()
    return f"SES-{now.strftime('%Y%m%d-%H%M%S')}-{short_hex}"


def generate_run_id(dt: datetime | None = None) -> str:
    """Membuat Processing Run ID unik untuk satu siklus pemrosesan ilmiah."""
    now = dt if dt is not None else datetime.now().astimezone()
    short_hex = uuid.uuid4().hex[:6].upper()
    return f"RUN-{now.strftime('%Y%m%d-%H%M%S')}-{short_hex}"


@dataclass
class ProcessingSessionRecord:
    """Catatan satu sesi eksekusi pemrosesan (Bagian XXVII)."""

    run_id: str
    session_id: str
    start_time_iso: str
    monotonic_start: float
    end_time_iso: str | None = None
    duration_ms: float = 0.0
    input_summary: dict[str, Any] = field(default_factory=dict)
    processing_config: dict[str, Any] = field(default_factory=dict)
    stages: dict[str, str] = field(default_factory=dict)
    final_status: str = "RUNNING"
    output_summary: list[str] = field(default_factory=list)

    def finish(self, status: str, output_files: list[str] | tuple[str, ...] = ()) -> float:
        """Menandai sesi pemrosesan selesai dan menghitung durasi menggunakan monotonic timer."""
        _, iso_end = format_timestamps()
        self.end_time_iso = iso_end
        self.duration_ms = max(0.0, (time.monotonic() - self.monotonic_start) * 1000.0)
        self.final_status = status
        if output_files:
            for f in output_files:
                if f not in self.output_summary:
                    self.output_summary.append(str(f))
        return self.duration_ms


class LogSessionManager:
    """Pengelola thread-safe untuk Application Session ID, Run ID aktif, dan nomor urut event."""

    def __init__(self, session_id: str | None = None) -> None:
        self._lock = threading.RLock()
        _, self._startup_iso = format_timestamps()
        self._session_id: str = session_id or generate_session_id()
        self._active_run_id: str | None = None
        self._sequence_counter: int = 0
        self._run_records: dict[str, ProcessingSessionRecord] = {}
        self._run_order: list[str] = []

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def startup_iso(self) -> str:
        return self._startup_iso

    @property
    def active_run_id(self) -> str | None:
        with self._lock:
            return self._active_run_id

    @property
    def current_run_or_session_id(self) -> str:
        with self._lock:
            return self._active_run_id or self._session_id

    def next_sequence(self) -> int:
        """Mengembalikan nomor urut sekuensial berikutnya secara atomik."""
        with self._lock:
            self._sequence_counter += 1
            return self._sequence_counter

    def start_processing_run(
        self,
        *,
        run_id: str | None = None,
        input_summary: dict[str, Any] | None = None,
        processing_config: dict[str, Any] | None = None,
    ) -> ProcessingSessionRecord:
        """Memulai satu sesi Processing Run baru tanpa menghapus histori sesi sebelumnya."""
        with self._lock:
            rid = run_id or generate_run_id()
            _, iso_now = format_timestamps()
            rec = ProcessingSessionRecord(
                run_id=rid,
                session_id=self._session_id,
                start_time_iso=iso_now,
                monotonic_start=time.monotonic(),
                input_summary=dict(input_summary or {}),
                processing_config=dict(processing_config or {}),
            )
            self._active_run_id = rid
            self._run_records[rid] = rec
            self._run_order.append(rid)
            return rec

    def update_stage_status(self, stage_name: str, status: str, *, run_id: str | None = None) -> None:
        """Memperbarui status tahapan pada sesi pemrosesan yang sedang berjalan."""
        with self._lock:
            target_id = run_id or self._active_run_id
            if target_id and target_id in self._run_records:
                self._run_records[target_id].stages[stage_name] = status

    def finish_processing_run(
        self,
        status: str = "SUCCESS",
        *,
        run_id: str | None = None,
        output_files: list[str] | tuple[str, ...] = (),
    ) -> ProcessingSessionRecord | None:
        """Menyelesaikan sesi pemrosesan dan mengembalikan catatannya."""
        with self._lock:
            target_id = run_id or self._active_run_id
            rec = self._run_records.get(target_id) if target_id else None
            if rec is not None:
                rec.finish(status, output_files=output_files)
            if target_id == self._active_run_id:
                self._active_run_id = None
            return rec

    def clear_active_run_context(self) -> None:
        """Melepas pengikatan Run ID aktif (mis. saat membuka gambar baru setelah proses selesai)
        tanpa menghapus catatan sesi sebelumnya.
        """
        with self._lock:
            self._active_run_id = None

    def get_run_record(self, run_id: str) -> ProcessingSessionRecord | None:
        with self._lock:
            return self._run_records.get(run_id)

    def all_run_records(self) -> tuple[ProcessingSessionRecord, ...]:
        with self._lock:
            return tuple(self._run_records[rid] for rid in self._run_order if rid in self._run_records)
