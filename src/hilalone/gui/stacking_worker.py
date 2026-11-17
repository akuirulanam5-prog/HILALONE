"""Worker thread PySide6 (QThread) untuk menjalankan Automatic Stacking Engine di latar belakang.

Sesuai aturan AGENTS.md Bagian 3:
  * GUI tidak berisi logika pemrosesan.
  * Pemrosesan berat berjalan di worker thread agar antarmuka pengguna (GUI)
    tetap responsif, progress bar dapat diperbarui secara real-time, dan
    pengguna dapat menekan tombol Cancel kapan saja.
"""

from __future__ import annotations

from pathlib import Path
import threading
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

from hilalone.core.logging import LogModule
from hilalone.input_manager.sequence_manager import SequenceManager
from hilalone.processing.stacking import (
    AutomaticStackingEngine,
    LoadedMasterFlat,
    StackingCancelledError,
    StackingConfirmationRequiredError,
    StackingError,
    StackingProfile,
)

if TYPE_CHECKING:
    from hilalone.core.logging import HilaloneLogger


class StackingWorker(QThread):
    """Thread pekerja yang mengeksekusi AutomaticStackingEngine tanpa membekukan GUI."""

    progress_updated = Signal(int, int, str)
    stacking_finished = Signal(object)
    stacking_cancelled = Signal(str)
    confirmation_required = Signal(str)
    stacking_failed = Signal(str)

    def __init__(
        self,
        sequence_manager: SequenceManager,
        profile: StackingProfile,
        *,
        master_flat: LoadedMasterFlat | Path | str | np.ndarray | None = None,
        excluded_frame_indices: set[int] | None = None,
        allow_exclude_incompatible_and_error: bool = False,
        check_position_stability: bool = False,
        confirm_proceed_with_shift_risk: bool = True,
        max_working_memory_mb: int = 128,
        run_id: str | None = None,
        log_manager: HilaloneLogger | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._sequence_manager = sequence_manager
        self._profile = profile
        self._master_flat = master_flat
        self._excluded_frame_indices = (
            set(excluded_frame_indices) if excluded_frame_indices else None
        )
        self._allow_exclude_invalid = allow_exclude_incompatible_and_error
        self._check_position_stability = check_position_stability
        self._confirm_shift_risk = confirm_proceed_with_shift_risk
        self._max_working_memory_mb = max_working_memory_mb
        self._run_id = run_id
        self._log_manager = log_manager
        self._cancel_lock = threading.Lock()
        self._cancel_requested = False

    def request_cancel(self) -> None:
        """Meminta pembatalan proses stacking secara aman (thread-safe)."""
        with self._cancel_lock:
            self._cancel_requested = True

    def is_cancel_requested(self) -> bool:
        with self._cancel_lock:
            return self._cancel_requested

    def _on_engine_progress(self, step: int, total: int, message: str) -> None:
        self.progress_updated.emit(int(step), int(total), str(message))
        if self._log_manager is not None:
            pct = int(round(100.0 * max(0, min(step, max(1, total))) / max(1, total)))
            self._log_manager.progress(
                LogModule.STACKING,
                int(step),
                int(total),
                f"{pct}% completed ({step}/{total} steps).",
                operation="stacking",
                run_id=self._run_id,
            )

    def run(self) -> None:  # pragma: no cover - dijalankan di thread pekerja atau langsung
        engine = AutomaticStackingEngine(max_working_memory_mb=self._max_working_memory_mb)
        try:
            result = engine.stack_sequence(
                self._sequence_manager,
                profile=self._profile,
                master_flat=self._master_flat,
                excluded_frame_indices=self._excluded_frame_indices,
                allow_exclude_incompatible_and_error=self._allow_exclude_invalid,
                check_position_stability=self._check_position_stability,
                confirm_proceed_with_shift_risk=self._confirm_shift_risk,
                progress_callback=self._on_engine_progress,
                cancel_check=self.is_cancel_requested,
            )
        except StackingCancelledError as cancel_err:
            self.stacking_cancelled.emit(str(cancel_err))
            return
        except StackingConfirmationRequiredError as confirm_err:
            self.confirmation_required.emit(str(confirm_err))
            return
        except StackingError as stack_err:
            self.stacking_failed.emit(str(stack_err))
            return
        except Exception as exc:
            self.stacking_failed.emit(f"Terjadi galat tak terduga saat stacking: {exc}")
            return

        if self.is_cancel_requested():
            self.stacking_cancelled.emit("Proses stacking dibatalkan oleh pengguna.")
            return

        self.stacking_finished.emit(result)
