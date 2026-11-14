"""Processing Orchestrator HILALONE — Pipeline Pemrosesan Otomatis Terintegrasi.

Menghubungkan seluruh tahapan pemrosesan citra hilal dalam urutan ilmiah yang ketat:
  * Single Image:
      1. Input Validation
      2. Optional Flat Calibration
      3. Stacking Dilewati
      4. Engine 1 — Background Extraction
      5. Engine 2 — Image Enhancement (CLAHE)
      6. Engine 3 — Histogram Transformation
      7. Pratinjau Terpadu & Output Ilmiah
  * Multi-Frame / Video / SER:
      1. Input Sequence Validation
      2. Optional Flat Calibration pada setiap light frame
      3. Automatic Stacking Engine
      4. Engine 1 — Background Extraction pada hasil stacking
      5. Engine 2 — Image Enhancement (CLAHE)
      6. Engine 3 — Histogram Transformation
      7. Pratinjau Terpadu & Output Ilmiah

Prinsip Data Ilmiah:
  * Pemisahan ketat antara original_data, calibrated_data, stacked_data,
    linear_result, enhanced_result, dan display_result.
  * Array sumber tidak pernah dimodifikasi secara in-place.
"""

from __future__ import annotations

import time
from typing import Callable

import numpy as np
from PySide6.QtGui import QImage

from hilalone.input_manager.image_reader import ImageInfo, read_image
from hilalone.input_manager.models import InputMode
from hilalone.input_manager.preview_builder import array_to_preview_qimage
from hilalone.input_manager.sequence_manager import SequenceManager
from hilalone.processing.background_engine import run_background_extraction
from hilalone.processing.enhancement_engine import run_image_enhancement
from hilalone.processing.histogram_engine import run_histogram_transformation
from hilalone.processing.processing_models import (
    PipelineResult,
    PipelineStage,
    PreviewMode,
    ProcessingCancelledError,
    ProcessingError,
    ProcessingProfile,
    StageExecutionRecord,
    StageStatus,
)
from hilalone.processing.profile_manager import (
    UnifiedProfileConfig,
    get_unified_profile_config,
)
from hilalone.processing.stacking.engine import run_stacking_on_sequence
from hilalone.processing.stacking.flat_calibration import (
    apply_flat_calibration,
    build_unapplied_flat_report,
    check_flat_compatibility,
    validate_and_prepare_master_flat,
)
from hilalone.processing.stacking.models import (
    FlatCalibrationReport,
    LoadedMasterFlat,
    StackingResult,
)
from hilalone.processing.stacking.validator import (
    extract_frame_cfa_info,
    validate_sequence_for_stacking,
)


def _check_cancel(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check is not None and cancel_check():
        raise ProcessingCancelledError("Pemrosesan otomatis dibatalkan oleh pengguna.")


class ProcessingPipelineOrchestrator:
    """Mesin pengelola eksekusi seluruh tahapan pemrosesan citra HILALONE."""

    def __init__(
        self,
        config: UnifiedProfileConfig | ProcessingProfile | str = ProcessingProfile.MEDIUM,
        *,
        master_flat: LoadedMasterFlat | None = None,
        excluded_frame_indices: set[int] | None = None,
        allow_exclude_incompatible_and_error: bool = False,
        confirm_proceed_with_shift_risk: bool = False,
    ) -> None:
        if isinstance(config, (ProcessingProfile, str)):
            self.config = get_unified_profile_config(config)
        else:
            self.config = config

        self.master_flat = master_flat
        self.excluded_frame_indices = set(excluded_frame_indices) if excluded_frame_indices else None
        self.allow_exclude_incompatible_and_error = allow_exclude_incompatible_and_error
        self.confirm_proceed_with_shift_risk = confirm_proceed_with_shift_risk
        self.stage_records: list[StageExecutionRecord] = []

    def _record_stage(
        self,
        stage: PipelineStage,
        status: StageStatus,
        summary: str,
        *,
        parameters: dict[str, object] | None = None,
        input_desc: str = "",
        output_desc: str = "",
        duration_ms: float = 0.0,
        warnings: tuple[str, ...] = (),
    ) -> StageExecutionRecord:
        rec = StageExecutionRecord(
            stage=stage,
            status=status,
            summary=summary,
            parameters=parameters or {},
            input_description=input_desc,
            output_description=output_desc,
            duration_ms=duration_ms,
            warnings=warnings,
        )
        self.stage_records.append(rec)
        return rec

    def run_on_single_image(
        self,
        image_source: str | np.ndarray,
        image_info: ImageInfo | None = None,
        *,
        progress_callback: Callable[[PipelineStage, int, int, str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> PipelineResult:
        """Menjalankan alur pemrosesan lengkap untuk mode Single Image."""
        self.stage_records.clear()
        _check_cancel(cancel_check)

        def _notify(stage: PipelineStage, step: int, total: int, msg: str) -> None:
            if progress_callback is not None:
                progress_callback(stage, step, total, msg)

        # -------------------------------------------------------------
        # TAHAP 1: INPUT VALIDATION
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        _notify(PipelineStage.INPUT_VALIDATION, 1, 6, "Memvalidasi citra masukan tunggal...")

        source_names: list[str] = []
        if isinstance(image_source, (str, bytes)):
            loaded = read_image(image_source)
            orig_data = np.asarray(loaded.scientific_data, dtype=np.float32)
            ref_info = loaded.info
            source_names.append(ref_info.file_name)
        elif isinstance(image_source, np.ndarray):
            orig_data = np.asarray(image_source, dtype=np.float32)
            ref_info = image_info
            if ref_info is not None:
                source_names.append(ref_info.file_name)
            else:
                source_names.append("array_input.npy")
        else:
            raise ProcessingError("Format masukan image_source tidak valid.")

        if orig_data.ndim not in (2, 3):
            raise ProcessingError(f"Dimensi citra {orig_data.shape} tidak didukung.")

        h, w = int(orig_data.shape[0]), int(orig_data.shape[1])
        ch = int(orig_data.shape[2]) if orig_data.ndim == 3 else 1
        is_cfa, cfa_pat = extract_frame_cfa_info(ref_info)

        dur_input = (time.perf_counter() - t0) * 1000.0
        self._record_stage(
            PipelineStage.INPUT_VALIDATION,
            StageStatus.COMPLETED,
            f"Citra tunggal tervalidasi ({w}×{h} px, {ch} kanal, CFA={cfa_pat or 'Tidak'})",
            parameters={"width": w, "height": h, "channels": ch, "is_cfa": is_cfa},
            input_desc=source_names[0],
            output_desc=f"{w}×{h} float32",
            duration_ms=dur_input,
        )

        _check_cancel(cancel_check)

        # -------------------------------------------------------------
        # TAHAP 2: OPTIONAL FLAT CALIBRATION
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        flat_report: FlatCalibrationReport | None = None
        calibrated_data: np.ndarray

        if self.master_flat is not None:
            _notify(PipelineStage.FLAT_CALIBRATION, 2, 6, "Menerapkan kalibrasi Master Flat...")
            norm_flat, rep_flat = validate_and_prepare_master_flat(
                self.master_flat.scientific_data,
                expected_height=h,
                expected_width=w,
                expected_channels=ch,
                expected_is_cfa=is_cfa,
                expected_cfa_pattern=cfa_pat,
                reference_bit_depth=ref_info.original_bit_depth if ref_info else None,
                flat_info=self.master_flat.info if isinstance(self.master_flat.info, ImageInfo) else None,
                reference_info=ref_info,
                check_compatibility=False,
            )
            flat_report = rep_flat
            calibrated_data = apply_flat_calibration(orig_data, norm_flat)
            dur_flat = (time.perf_counter() - t0) * 1000.0
            self._record_stage(
                PipelineStage.FLAT_CALIBRATION,
                StageStatus.COMPLETED,
                f"Master Flat diterapkan ({self.master_flat.source_description})",
                parameters={"normalization": rep_flat.normalization_method, "invalid_px": rep_flat.invalid_pixel_count},
                input_desc=self.master_flat.source_description,
                output_desc="Calibrated float32",
                duration_ms=dur_flat,
                warnings=rep_flat.warnings,
            )
        else:
            flat_report = build_unapplied_flat_report("Opsi Flat Calibration tidak diaktifkan.")
            calibrated_data = orig_data.copy()
            self._record_stage(
                PipelineStage.FLAT_CALIBRATION,
                StageStatus.SKIPPED,
                "Flat Calibration dilewati (tidak diaktifkan).",
                duration_ms=0.0,
            )

        _check_cancel(cancel_check)

        # -------------------------------------------------------------
        # TAHAP 3: STACKING (Dilewati pada Single Image)
        # -------------------------------------------------------------
        self._record_stage(
            PipelineStage.STACKING,
            StageStatus.SKIPPED,
            "Stacking dilewati untuk mode Single Image.",
            duration_ms=0.0,
        )

        # -------------------------------------------------------------
        # TAHAP 4: ENGINE 1 — BACKGROUND EXTRACTION
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        _notify(PipelineStage.BACKGROUND_EXTRACTION, 4, 6, "Menjalankan Engine 1 — Background Extraction...")
        bg_cfg = self.config.background_config
        bg_cfg = replace_cfg = bg_cfg.__class__(
            enabled=bg_cfg.enabled,
            method=bg_cfg.method,
            grid_rows=bg_cfg.grid_rows,
            grid_cols=bg_cfg.grid_cols,
            mad_sigma_clip=bg_cfg.mad_sigma_clip,
            max_rejection_iterations=bg_cfg.max_rejection_iterations,
            rbf_smoothing=bg_cfg.rbf_smoothing,
            overcorrection_warn_ratio=bg_cfg.overcorrection_warn_ratio,
            preserve_mean_sky_pedestal=bg_cfg.preserve_mean_sky_pedestal,
            protected_regions=bg_cfg.protected_regions,
            protected_mask=bg_cfg.protected_mask,
            manual_include_points=bg_cfg.manual_include_points,
            manual_exclude_points=bg_cfg.manual_exclude_points,
            is_cfa_mosaic=is_cfa,
            cfa_pattern_str=cfa_pat,
        )

        bg_res = run_background_extraction(
            calibrated_data,
            replace_cfg,
            cancel_check=cancel_check,
        )
        linear_result = bg_res.linear_corrected_data
        dur_bg = (time.perf_counter() - t0) * 1000.0
        self._record_stage(
            PipelineStage.BACKGROUND_EXTRACTION,
            StageStatus.COMPLETED,
            f"Background diekstraksi ({bg_res.effective_method.value}, {bg_res.accepted_sample_count} sampel)",
            parameters={
                "method": bg_res.effective_method.value,
                "gradient_reduction": round(bg_res.residual_stats.gradient_reduction_ratio, 3),
                "overcorrection_score": round(bg_res.residual_stats.overcorrection_score, 3),
            },
            input_desc="Calibrated linear data",
            output_desc="Background model + Linear corrected float32",
            duration_ms=dur_bg,
            warnings=bg_res.warnings,
        )

        _check_cancel(cancel_check)

        # -------------------------------------------------------------
        # TAHAP 5: ENGINE 2 — IMAGE ENHANCEMENT (CLAHE)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        _notify(PipelineStage.IMAGE_ENHANCEMENT, 5, 6, "Menjalankan Engine 2 — Image Enhancement (CLAHE)...")
        enh_cfg = self.config.enhancement_config
        enh_cfg = enh_cfg.__class__(
            enabled=enh_cfg.enabled,
            method=enh_cfg.method,
            clip_limit=enh_cfg.clip_limit,
            kernel_tiles=enh_cfg.kernel_tiles,
            nbins=enh_cfg.nbins,
            adaptive_parameters=enh_cfg.adaptive_parameters,
            max_noise_amplification_ratio=enh_cfg.max_noise_amplification_ratio,
            is_cfa_mosaic=is_cfa,
            cfa_pattern_str=cfa_pat,
        )
        enh_res = run_image_enhancement(
            linear_result,
            enh_cfg,
            cancel_check=cancel_check,
        )
        enhanced_result = enh_res.enhanced_data
        dur_enh = (time.perf_counter() - t0) * 1000.0
        self._record_stage(
            PipelineStage.IMAGE_ENHANCEMENT,
            StageStatus.COMPLETED if enh_res.config_used.enabled else StageStatus.SKIPPED,
            f"Image Enhancement ({enh_res.color_mode}, clip={enh_res.effective_clip_limit:.4f})",
            parameters={
                "enabled": enh_res.config_used.enabled,
                "clip_limit": enh_res.effective_clip_limit,
                "noise_amp_ratio": round(enh_res.noise_amplification_ratio, 2),
            },
            input_desc="Linear corrected float32",
            output_desc="Derived nonlinear enhanced float32",
            duration_ms=dur_enh,
            warnings=enh_res.warnings,
        )

        _check_cancel(cancel_check)

        # -------------------------------------------------------------
        # TAHAP 6: ENGINE 3 — HISTOGRAM TRANSFORMATION
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        _notify(PipelineStage.HISTOGRAM_TRANSFORMATION, 6, 6, "Menjalankan Engine 3 — Histogram Transformation...")
        hist_input = enhanced_result if enh_res.config_used.enabled else linear_result
        hist_res = run_histogram_transformation(
            hist_input,
            self.config.histogram_config,
            cancel_check=cancel_check,
        )
        display_result = hist_res.display_data
        dur_hist = (time.perf_counter() - t0) * 1000.0
        self._record_stage(
            PipelineStage.HISTOGRAM_TRANSFORMATION,
            StageStatus.COMPLETED,
            f"Display stretch ({hist_res.effective_method.value}, vmin={hist_res.vmin:.3g}, vmax={hist_res.vmax:.3g})",
            parameters={
                "method": hist_res.effective_method.value,
                "vmin": hist_res.vmin,
                "vmax": hist_res.vmax,
                "asinh_a": hist_res.effective_asinh_a,
                "mtf_m": hist_res.effective_midtone_balance,
            },
            input_desc="Enhanced/Linear array",
            output_desc="Display float32 [0.0, 1.0]",
            duration_ms=dur_hist,
            warnings=hist_res.warnings,
        )

        # Himpun seluruh peringatan dan catatan
        all_warnings: list[str] = []
        all_notes: list[str] = []
        for r in self.stage_records:
            all_warnings.extend(r.warnings)
        all_notes.extend(bg_res.notes)
        all_notes.extend(enh_res.notes)
        all_notes.extend(hist_res.notes)

        previews: dict[PreviewMode, QImage] = {
            PreviewMode.ORIGINAL: array_to_preview_qimage(orig_data),
            PreviewMode.BACKGROUND_MODEL: bg_res.model_preview,
            PreviewMode.BACKGROUND_CORRECTED: bg_res.corrected_preview,
            PreviewMode.ENHANCED: enh_res.enhanced_preview,
            PreviewMode.FINAL_DISPLAY: hist_res.display_preview,
        }

        return PipelineResult(
            profile=self.config.profile,
            input_mode="SINGLE",
            original_data=orig_data,
            calibrated_data=calibrated_data if self.master_flat is not None else None,
            stacked_data=None,
            background_model=bg_res.background_model,
            linear_result=linear_result,
            enhanced_result=enhanced_result,
            display_result=display_result,
            flat_report=flat_report,
            stacking_result=None,
            background_result=bg_res,
            enhancement_result=enh_res,
            histogram_result=hist_res,
            stage_records=tuple(self.stage_records),
            previews=previews,
            is_cfa_mosaic=is_cfa,
            cfa_pattern_str=cfa_pat,
            source_file_names=tuple(source_names),
            warnings=tuple(all_warnings),
            notes=tuple(all_notes),
        )

    def run_on_sequence(
        self,
        sequence_manager: SequenceManager,
        *,
        progress_callback: Callable[[PipelineStage, int, int, str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> PipelineResult:
        """Menjalankan alur pemrosesan lengkap untuk sequence (Multiple Images, Video, atau SER)."""
        self.stage_records.clear()
        _check_cancel(cancel_check)

        def _notify(stage: PipelineStage, step: int, total: int, msg: str) -> None:
            if progress_callback is not None:
                progress_callback(stage, step, total, msg)

        # -------------------------------------------------------------
        # TAHAP 1: INPUT SEQUENCE VALIDATION
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        _notify(PipelineStage.INPUT_VALIDATION, 1, 6, "Memvalidasi sequence masukan...")
        if sequence_manager.frame_count == 0:
            raise ProcessingError("Sequence kosong; tidak ada frame untuk diproses.")

        if sequence_manager.input_mode == InputMode.SINGLE:
            return self.run_on_single_image(
                sequence_manager.entries[0].source_path,
                sequence_manager.entries[0].info,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )

        val = validate_sequence_for_stacking(
            sequence_manager.input_mode,
            sequence_manager.entries,
            allow_exclude_incompatible_and_error=self.allow_exclude_incompatible_and_error,
        )
        if len(val.included_frame_indices) < 2:
            raise ProcessingError(
                f"Jumlah frame kompatibel hanya {len(val.included_frame_indices)} frame "
                "(minimal 2 frame diperlukan untuk stacking)."
            )

        dur_val = (time.perf_counter() - t0) * 1000.0
        source_names = [e.file_name for e in sequence_manager.entries]
        self._record_stage(
            PipelineStage.INPUT_VALIDATION,
            StageStatus.COMPLETED,
            f"Sequence tervalidasi ({len(val.included_frame_indices)} frame kompatibel, "
            f"{len(val.excluded_frames)} dikecualikan)",
            parameters={"total_frames": len(sequence_manager.entries), "compatible": len(val.included_frame_indices)},
            input_desc=f"{sequence_manager.input_mode.value} ({len(sequence_manager.entries)} frame)",
            output_desc=f"{val.width}×{val.height} px, {val.channels} kanal",
            duration_ms=dur_val,
        )

        _check_cancel(cancel_check)

        # -------------------------------------------------------------
        # TAHAP 2 & 3: OPTIONAL FLAT CALIBRATION & AUTOMATIC STACKING
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        _notify(PipelineStage.STACKING, 3, 6, "Menjalankan Automatic Stacking Engine...")

        def _stack_prog(cur: int, tot: int, msg: str) -> None:
            _notify(PipelineStage.STACKING, 3, 6, f"Stacking: {msg}")

        stack_res = run_stacking_on_sequence(
            sequence_manager,
            self.config.stacking_config.profile,
            master_flat=self.master_flat,
            excluded_frame_indices=self.excluded_frame_indices,
            allow_exclude_incompatible_and_error=self.allow_exclude_incompatible_and_error,
            check_position_stability=False,
            confirm_proceed_with_shift_risk=True,
            progress_callback=_stack_prog,
            cancel_check=cancel_check,
        )

        dur_stack = (time.perf_counter() - t0) * 1000.0
        flat_status = (
            f"Diterapkan ({self.master_flat.source_description})"
            if (self.master_flat is not None and stack_res.flat_report and stack_res.flat_report.applied)
            else "Tidak diterapkan"
        )
        self._record_stage(
            PipelineStage.FLAT_CALIBRATION,
            StageStatus.COMPLETED if (self.master_flat and stack_res.flat_report and stack_res.flat_report.applied) else StageStatus.SKIPPED,
            f"Flat Calibration per frame: {flat_status}",
            input_desc=self.master_flat.source_description if self.master_flat else "None",
            output_desc="Calibrated light frames",
            duration_ms=0.0,
        )
        self._record_stage(
            PipelineStage.STACKING,
            StageStatus.COMPLETED,
            f"Stacking selesai: {stack_res.stacked_frame_count} frame digabungkan "
            f"({stack_res.effective_algorithm.value})",
            parameters={
                "algorithm": stack_res.effective_algorithm.value,
                "stacked_frames": stack_res.stacked_frame_count,
                "rejected_samples": stack_res.total_rejected_pixel_samples,
            },
            input_desc=f"{sequence_manager.input_mode.value}",
            output_desc="Stacked scientific float32",
            duration_ms=dur_stack,
            warnings=stack_res.warnings,
        )

        stacked_data = stack_res.stacked_scientific_data
        is_cfa = val.is_cfa_mosaic
        cfa_pat = val.cfa_pattern_str

        _check_cancel(cancel_check)

        # -------------------------------------------------------------
        # TAHAP 4: ENGINE 1 — BACKGROUND EXTRACTION PADA HASIL STACKING
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        _notify(PipelineStage.BACKGROUND_EXTRACTION, 4, 6, "Menjalankan Engine 1 — Background Extraction pada hasil stacking...")
        bg_cfg = self.config.background_config
        bg_cfg = bg_cfg.__class__(
            enabled=bg_cfg.enabled,
            method=bg_cfg.method,
            grid_rows=bg_cfg.grid_rows,
            grid_cols=bg_cfg.grid_cols,
            mad_sigma_clip=bg_cfg.mad_sigma_clip,
            max_rejection_iterations=bg_cfg.max_rejection_iterations,
            rbf_smoothing=bg_cfg.rbf_smoothing,
            overcorrection_warn_ratio=bg_cfg.overcorrection_warn_ratio,
            preserve_mean_sky_pedestal=bg_cfg.preserve_mean_sky_pedestal,
            protected_regions=bg_cfg.protected_regions,
            protected_mask=bg_cfg.protected_mask,
            manual_include_points=bg_cfg.manual_include_points,
            manual_exclude_points=bg_cfg.manual_exclude_points,
            is_cfa_mosaic=is_cfa,
            cfa_pattern_str=cfa_pat,
        )
        bg_res = run_background_extraction(
            stacked_data,
            bg_cfg,
            cancel_check=cancel_check,
        )
        linear_result = bg_res.linear_corrected_data
        dur_bg = (time.perf_counter() - t0) * 1000.0
        self._record_stage(
            PipelineStage.BACKGROUND_EXTRACTION,
            StageStatus.COMPLETED,
            f"Background diekstraksi ({bg_res.effective_method.value}, {bg_res.accepted_sample_count} sampel)",
            parameters={
                "method": bg_res.effective_method.value,
                "gradient_reduction": round(bg_res.residual_stats.gradient_reduction_ratio, 3),
            },
            input_desc="Stacked scientific data",
            output_desc="Background model + Linear corrected float32",
            duration_ms=dur_bg,
            warnings=bg_res.warnings,
        )

        _check_cancel(cancel_check)

        # -------------------------------------------------------------
        # TAHAP 5: ENGINE 2 — IMAGE ENHANCEMENT (CLAHE)
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        _notify(PipelineStage.IMAGE_ENHANCEMENT, 5, 6, "Menjalankan Engine 2 — Image Enhancement (CLAHE)...")
        enh_cfg = self.config.enhancement_config
        enh_cfg = enh_cfg.__class__(
            enabled=enh_cfg.enabled,
            method=enh_cfg.method,
            clip_limit=enh_cfg.clip_limit,
            kernel_tiles=enh_cfg.kernel_tiles,
            nbins=enh_cfg.nbins,
            adaptive_parameters=enh_cfg.adaptive_parameters,
            max_noise_amplification_ratio=enh_cfg.max_noise_amplification_ratio,
            is_cfa_mosaic=is_cfa,
            cfa_pattern_str=cfa_pat,
        )
        enh_res = run_image_enhancement(
            linear_result,
            enh_cfg,
            cancel_check=cancel_check,
        )
        enhanced_result = enh_res.enhanced_data
        dur_enh = (time.perf_counter() - t0) * 1000.0
        self._record_stage(
            PipelineStage.IMAGE_ENHANCEMENT,
            StageStatus.COMPLETED if enh_res.config_used.enabled else StageStatus.SKIPPED,
            f"Image Enhancement ({enh_res.color_mode}, clip={enh_res.effective_clip_limit:.4f})",
            parameters={
                "enabled": enh_res.config_used.enabled,
                "clip_limit": enh_res.effective_clip_limit,
                "noise_amp_ratio": round(enh_res.noise_amplification_ratio, 2),
            },
            input_desc="Linear corrected float32",
            output_desc="Derived nonlinear enhanced float32",
            duration_ms=dur_enh,
            warnings=enh_res.warnings,
        )

        _check_cancel(cancel_check)

        # -------------------------------------------------------------
        # TAHAP 6: ENGINE 3 — HISTOGRAM TRANSFORMATION
        # -------------------------------------------------------------
        t0 = time.perf_counter()
        _notify(PipelineStage.HISTOGRAM_TRANSFORMATION, 6, 6, "Menjalankan Engine 3 — Histogram Transformation...")
        hist_input = enhanced_result if enh_res.config_used.enabled else linear_result
        hist_res = run_histogram_transformation(
            hist_input,
            self.config.histogram_config,
            cancel_check=cancel_check,
        )
        display_result = hist_res.display_data
        dur_hist = (time.perf_counter() - t0) * 1000.0
        self._record_stage(
            PipelineStage.HISTOGRAM_TRANSFORMATION,
            StageStatus.COMPLETED,
            f"Display stretch ({hist_res.effective_method.value}, vmin={hist_res.vmin:.3g}, vmax={hist_res.vmax:.3g})",
            parameters={
                "method": hist_res.effective_method.value,
                "vmin": hist_res.vmin,
                "vmax": hist_res.vmax,
            },
            input_desc="Enhanced/Linear array",
            output_desc="Display float32 [0.0, 1.0]",
            duration_ms=dur_hist,
            warnings=hist_res.warnings,
        )

        all_warnings: list[str] = []
        all_notes: list[str] = []
        for r in self.stage_records:
            all_warnings.extend(r.warnings)
        all_notes.extend(bg_res.notes)
        all_notes.extend(enh_res.notes)
        all_notes.extend(hist_res.notes)

        ref_entry = sequence_manager.entries[0]
        orig_prev = (
            sequence_manager.load_frame(0).preview
            if sequence_manager.frame_count > 0
            else array_to_preview_qimage(stacked_data)
        )

        previews: dict[PreviewMode, QImage] = {
            PreviewMode.ORIGINAL: orig_prev,
            PreviewMode.BACKGROUND_MODEL: bg_res.model_preview,
            PreviewMode.BACKGROUND_CORRECTED: bg_res.corrected_preview,
            PreviewMode.ENHANCED: enh_res.enhanced_preview,
            PreviewMode.FINAL_DISPLAY: hist_res.display_preview,
        }

        return PipelineResult(
            profile=self.config.profile,
            input_mode=sequence_manager.input_mode.value,
            original_data=stacked_data,  # Pada mode multi-frame, data referensi linear awal adalah stacked_data
            calibrated_data=stacked_data if self.master_flat is not None else None,
            stacked_data=stacked_data,
            background_model=bg_res.background_model,
            linear_result=linear_result,
            enhanced_result=enhanced_result,
            display_result=display_result,
            flat_report=stack_res.flat_report,
            stacking_result=stack_res,
            background_result=bg_res,
            enhancement_result=enh_res,
            histogram_result=hist_res,
            stage_records=tuple(self.stage_records),
            previews=previews,
            is_cfa_mosaic=is_cfa,
            cfa_pattern_str=cfa_pat,
            source_file_names=tuple(source_names),
            warnings=tuple(all_warnings),
            notes=tuple(all_notes),
        )
