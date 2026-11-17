"""Worker thread (QThread) untuk menjalankan Full Automated Image Processing Pipeline HILALONE.

Menjaga GUI tetap responsif saat pemrosesan berat (Stacking, Background Extraction,
CLAHE, dan Histogram Transformation) berlangsung di latar belakang.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import numpy as np
from PySide6.QtCore import QObject, QThread, Signal

from hilalone.core.logging import LogModule
from hilalone.input_manager.image_reader import ImageInfo
from hilalone.input_manager.sequence_manager import SequenceManager
from hilalone.processing.processing_models import (
    PipelineResult,
    PipelineStage,
    ProcessingCancelledError,
    ProcessingError,
    ProcessingProfile,
)
from hilalone.processing.processing_pipeline import (
    ProcessingPipelineOrchestrator,
)
from hilalone.processing.profile_manager import UnifiedProfileConfig
from hilalone.processing.stacking.models import (
    LoadedMasterFlat,
    StackingCancelledError,
    StackingConfirmationRequiredError,
    StackingError,
)

if TYPE_CHECKING:
    from hilalone.core.logging import HilaloneLogger


class PipelineWorker(QThread):
    """Worker thread untuk eksekusi pipeline pemrosesan otomatis HILALONE."""

    stage_changed = Signal(str, int, int, str)
    progress_updated = Signal(int, str)
    pipeline_finished = Signal(object)  # Mengirimkan PipelineResult
    pipeline_cancelled = Signal(str)
    pipeline_failed = Signal(str)
    confirmation_required = Signal(str)

    def __init__(
        self,
        sequence_manager: SequenceManager | None,
        single_image_array: np.ndarray | None = None,
        single_image_info: ImageInfo | None = None,
        *,
        config: UnifiedProfileConfig | ProcessingProfile | str = ProcessingProfile.MEDIUM,
        master_flat: LoadedMasterFlat | None = None,
        excluded_frame_indices: set[int] | None = None,
        allow_exclude_incompatible_and_error: bool = False,
        confirm_proceed_with_shift_risk: bool = True,
        run_id: str | None = None,
        log_manager: HilaloneLogger | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.sequence_manager = sequence_manager
        self.single_image_array = single_image_array
        self.single_image_info = single_image_info
        self.config = config
        self.master_flat = master_flat
        self.excluded_frame_indices = set(excluded_frame_indices) if excluded_frame_indices else None
        self.allow_exclude_incompatible_and_error = allow_exclude_incompatible_and_error
        self.confirm_proceed_with_shift_risk = confirm_proceed_with_shift_risk
        self.run_id = run_id
        self.log_manager = log_manager
        self._is_cancelled = False

    def request_cancel(self) -> None:
        """Meminta pembatalan proses secara aman."""
        self._is_cancelled = True

    def _cancel_check(self) -> bool:
        return self._is_cancelled

    def run(self) -> None:
        orchestrator = ProcessingPipelineOrchestrator(
            self.config,
            master_flat=self.master_flat,
            excluded_frame_indices=self.excluded_frame_indices,
            allow_exclude_incompatible_and_error=self.allow_exclude_incompatible_and_error,
            confirm_proceed_with_shift_risk=self.confirm_proceed_with_shift_risk,
        )

        stage_weights = {
            PipelineStage.INPUT_VALIDATION: 5,
            PipelineStage.FLAT_CALIBRATION: 10,
            PipelineStage.STACKING: 40,
            PipelineStage.BACKGROUND_EXTRACTION: 25,
            PipelineStage.IMAGE_ENHANCEMENT: 10,
            PipelineStage.HISTOGRAM_TRANSFORMATION: 10,
        }

        stage_order = [
            PipelineStage.INPUT_VALIDATION,
            PipelineStage.FLAT_CALIBRATION,
            PipelineStage.STACKING,
            PipelineStage.BACKGROUND_EXTRACTION,
            PipelineStage.IMAGE_ENHANCEMENT,
            PipelineStage.HISTOGRAM_TRANSFORMATION,
        ]

        def _on_progress(stage: PipelineStage, step: int, total_steps: int, msg: str) -> None:
            if self._is_cancelled:
                raise ProcessingCancelledError("Proses dibatalkan oleh pengguna.")

            self.stage_changed.emit(stage.value, step, total_steps, msg)
            try:
                cur_idx = stage_order.index(stage)
            except ValueError:
                cur_idx = 0

            prior_pct = sum(stage_weights[stage_order[i]] for i in range(cur_idx))
            cur_weight = stage_weights.get(stage, 15)
            step_frac = float(step) / float(max(1, total_steps))
            overall_pct = int(min(99, prior_pct + cur_weight * step_frac))
            self.progress_updated.emit(overall_pct, msg)

            if self.log_manager is not None:
                self.log_manager.progress(
                    LogModule.STACKING if stage == PipelineStage.STACKING else LogModule.SESSION,
                    overall_pct,
                    100,
                    f"{overall_pct}% completed — {msg}",
                    operation="pipeline",
                    run_id=self.run_id,
                )

        try:
            if self.sequence_manager is not None and self.sequence_manager.frame_count > 1:
                result = orchestrator.run_on_sequence(
                    self.sequence_manager,
                    progress_callback=_on_progress,
                    cancel_check=self._cancel_check,
                )
            elif self.single_image_array is not None:
                result = orchestrator.run_on_single_image(
                    self.single_image_array,
                    self.single_image_info,
                    progress_callback=_on_progress,
                    cancel_check=self._cancel_check,
                )
            elif self.sequence_manager is not None and self.sequence_manager.frame_count == 1:
                entry = self.sequence_manager.entries[0]
                loaded = self.sequence_manager.load_frame(0)
                result = orchestrator.run_on_single_image(
                    loaded.scientific_data if loaded.scientific_data is not None else np.asarray(loaded.preview),
                    entry.info,
                    progress_callback=_on_progress,
                    cancel_check=self._cancel_check,
                )
            else:
                raise ProcessingError("Tidak ada data gambar atau sequence yang dapat diproses.")

            if self._is_cancelled:
                self.pipeline_cancelled.emit("Proses dibatalkan oleh pengguna.")
            else:
                self.progress_updated.emit(100, "Pemrosesan otomatis selesai.")
                self.pipeline_finished.emit(result)

        except (ProcessingCancelledError, StackingCancelledError):
            self.pipeline_cancelled.emit("Pemrosesan otomatis berhasil dibatalkan secara aman.")
        except StackingConfirmationRequiredError as c_err:
            self.confirmation_required.emit(str(c_err))
        except (ProcessingError, StackingError, Exception) as exc:
            self.pipeline_failed.emit(str(exc))
