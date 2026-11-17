"""Pelapor ilmiah terstruktur (Scientific Reporters) untuk setiap modul pemrosesan HILALONE.

Memastikan seluruh tahapan dari Input, Validasi Sequence, Kalibrasi Flat, Pembuatan Master Flat,
Stacking, Background Extraction, Image Enhancement (CLAHE), Histogram Transformation, Kurva,
Tampilan/Preview, hingga Output Generation dicatat secara akurat, transparan, dan jujur tanpa
pernah mengarang nilai metadata yang tidak tersedia.

Mendukung tiga tingkat Detail Mode (Verbosity) secara nyata:
  - NORMAL  : Ringkasan eksekusi dan milestone utama.
  - VERBOSE : Seluruh informasi NORMAL ditambah metadata dan parameter ilmiah lengkap.
  - DEBUG   : Seluruh informasi VERBOSE ditambah diagnostik teknis internal (buffer, shape,
              dtype, thread, dan timing).
  - WARNING, ERROR, dan CRITICAL selalu dicatat pada ketiga mode.
"""

from __future__ import annotations

import math
from pathlib import Path
import threading
from typing import TYPE_CHECKING, Any

import numpy as np

from hilalone.core.logging.log_event import (
    LogModule,
    ProcessingRunSummary,
    format_duration,
)
from hilalone.core.logging.logger import HilaloneLogger

if TYPE_CHECKING:
    from hilalone.input_manager.image_reader import ImageInfo
    from hilalone.input_manager.models import (
        InputMode,
        SequenceCompatibilityReport,
        SequenceFrameEntry,
    )
    from hilalone.processing.processing_models import (
        PipelineResult,
    )
    from hilalone.processing.stacking.models import (
        FlatCompatibilityCheckResult,
        LoadedMasterFlat,
    )

_UNAVAILABLE_STRINGS = frozenset({"", "-", "tidak tersedia", "unavailable", "none", "null"})


def _is_available(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, float) and not math.isfinite(val):
        return False
    s = str(val).strip()
    return s.lower() not in _UNAVAILABLE_STRINGS


def _determine_reader_name(info: ImageInfo) -> str:
    fmt = (info.file_format or "").upper()
    if info.fits_header is not None or "FITS" in fmt:
        return "Astropy FITS Reader"
    if info.raw_metadata is not None or "RAW" in fmt:
        return "rawpy Camera RAW Reader"
    if info.video_metadata is not None or "VIDEO" in fmt:
        return "PyAV Video Stream Reader"
    if info.ser_metadata is not None or "SER" in fmt:
        return "HILALONE SER Binary Reader"
    if fmt in ("TIFF", "TIF") or info.path.suffix.lower() in (".tif", ".tiff"):
        return "tifffile Scientific TIFF Reader"
    return "Qt QImageReader"


def _format_channels_label(info: ImageInfo) -> str:
    if info.raw_metadata is not None and info.raw_metadata.is_cfa_mosaic:
        pat = info.raw_metadata.cfa_pattern_str or "CFA"
        return f"1 (CFA Mosaic: {pat})"
    if info.ser_metadata is not None and info.ser_metadata.is_cfa_mosaic:
        pat = info.ser_metadata.cfa_pattern_str or "CFA"
        return f"1 (CFA Mosaic: {pat})"
    if info.channels == 1:
        return "Monochrome (1 channel)"
    if info.channels == 3:
        return "RGB (3 channels)"
    if info.channels == 4:
        return "RGBA (4 channels)"
    return str(info.channels or "Unknown")


def log_image_input_loaded(
    logger: HilaloneLogger,
    info: ImageInfo,
    *,
    input_mode_label: str = "Single Image",
    frame_count: int = 1,
    duration_ms: float = 0.0,
) -> None:
    """Mencatat informasi pembukaan berkas/sequence gambar sesuai tingkat Detail (NORMAL/VERBOSE/DEBUG)."""
    reader_name = _determine_reader_name(info)
    ch_label = _format_channels_label(info)
    dtype_str = info.dtype_str or "float32"
    bit_depth_str = f"{info.original_bit_depth}-bit" if info.original_bit_depth else "Unknown"

    # NORMAL: Ringkasan pembukaan berkas, format, dan jumlah frame
    logger.info(
        LogModule.INPUT,
        f"Opening {input_mode_label}: {info.file_name}",
        details={
            "filename": info.file_name,
            "format": info.file_format,
            "frame_count": frame_count,
        },
    )

    # VERBOSE & DEBUG: Dimensi, resolusi, kanal, tipe data, bit depth, dan metadata spesifik format
    if logger.is_verbose_enabled:
        logger.verbose(
            LogModule.INPUT,
            f"Format: {info.file_format} | Reader: {reader_name}.",
        )
        logger.verbose(
            LogModule.INPUT,
            f"Resolution: {info.width} × {info.height} px | Channels: {ch_label}.",
            details={
                "width": info.width,
                "height": info.height,
                "channels": info.channels,
            },
        )
        logger.verbose(
            LogModule.INPUT,
            f"Data type: {dtype_str} | Bit depth: {bit_depth_str}.",
            details={
                "dtype": dtype_str,
                "bit_depth": info.original_bit_depth,
            },
        )

    # 1. Metadata FITS jika tersedia
    if info.fits_header is not None:
        fh = info.fits_header
        fits_kv: dict[str, Any] = {}
        for attr, label in (
            ("bitpix", "BITPIX"),
            ("naxis", "NAXIS"),
            ("naxis1", "NAXIS1"),
            ("naxis2", "NAXIS2"),
            ("bunit", "BUNIT"),
            ("object_name", "OBJECT"),
            ("telescop", "TELESCOP"),
            ("instrume", "INSTRUME"),
            ("exptime", "EXPTIME"),
            ("date_obs", "DATE-OBS"),
            ("filter_name", "FILTER"),
        ):
            val = getattr(fh, attr, None)
            if _is_available(val):
                fits_kv[label] = val
        if fits_kv and logger.is_verbose_enabled:
            summary_str = ", ".join(f"{k}={v}" for k, v in fits_kv.items())
            logger.verbose(
                LogModule.INPUT,
                f"FITS header metadata: {summary_str}",
                details=fits_kv,
            )
        # WARNING selalu dicatat pada semua mode (NORMAL, VERBOSE, DEBUG)
        if not _is_available(getattr(fh, "date_obs", None)):
            logger.warning(
                LogModule.INPUT,
                "Optional metadata keyword DATE-OBS is unavailable.",
                details={"filename": info.file_name, "keyword": "DATE-OBS"},
            )

    # 2. Metadata Camera RAW jika tersedia
    if info.raw_metadata is not None and logger.is_verbose_enabled:
        rm = info.raw_metadata
        raw_kv: dict[str, Any] = {}
        cam_model = (
            rm.format_camera_name()
            if hasattr(rm, "format_camera_name")
            else f"{rm.camera_make or ''} {rm.camera_model or ''}".strip()
        )
        if _is_available(cam_model):
            raw_kv["camera_model"] = cam_model
        raw_kv["sensor_dimensions"] = f"{info.width}×{info.height} px"
        if _is_available(rm.cfa_pattern_str):
            raw_kv["cfa_pattern"] = rm.cfa_pattern_str
        if _is_available(info.original_bit_depth):
            raw_kv["bit_depth"] = f"{info.original_bit_depth}-bit"
        if _is_available(rm.white_level):
            raw_kv["white_level"] = rm.white_level
        if _is_available(getattr(rm, "iso_speed", None)):
            raw_kv["iso"] = rm.iso_speed
        logger.verbose(
            LogModule.INPUT,
            "Camera RAW metadata extracted.",
            details=raw_kv,
        )

    # 3. Metadata TIFF jika format TIFF
    elif (
        (info.file_format or "").upper() in ("TIFF", "TIF")
        or info.path.suffix.lower() in (".tif", ".tiff")
    ) and logger.is_verbose_enabled:
        tiff_kv: dict[str, Any] = {
            "resolution": f"{info.width}×{info.height} px",
            "samples_per_pixel": info.channels or 1,
            "bits_per_sample": info.original_bit_depth,
            "dtype": dtype_str,
        }
        if _is_available(info.compression_name):
            tiff_kv["compression"] = info.compression_name
        logger.verbose(
            LogModule.INPUT,
            "TIFF structure metadata inspected.",
            details=tiff_kv,
        )

    # 4. Metadata Video jika tersedia
    if info.video_metadata is not None:
        vm = info.video_metadata
        if logger.is_verbose_enabled:
            vid_kv: dict[str, Any] = {
                "container": vm.container_format,
                "codec": vm.codec_name,
                "pix_fmt": info.decoded_pix_fmt or vm.pix_fmt,
                "width": vm.width,
                "height": vm.height,
                "frame_count": vm.frame_count,
            }
            if _is_available(vm.average_rate_fps):
                vid_kv["fps"] = f"{vm.average_rate_fps:.2f} fps"
            if _is_available(vm.time_base_str):
                vid_kv["time_base"] = vm.time_base_str
            if _is_available(vm.duration_sec):
                vid_kv["video_length_s"] = f"{vm.duration_sec:.2f} s"
            logger.verbose(
                LogModule.INPUT,
                f"Video stream metadata: {vm.container_format} / {vm.codec_name} ({vm.frame_count} frames).",
                details=vid_kv,
            )
        else:
            logger.info(
                LogModule.INPUT,
                f"Video stream loaded: {vm.container_format} / {vm.codec_name} ({vm.frame_count} frames).",
            )

    # 5. Metadata SER jika tersedia
    if info.ser_metadata is not None:
        sm = info.ser_metadata
        p_depth = getattr(sm, "pixel_depth_per_plane", getattr(sm, "pixel_depth", info.original_bit_depth or 8))
        c_name = getattr(sm, "color_format_name", getattr(sm, "color_id_name", str(sm.color_id)))
        if logger.is_verbose_enabled:
            ser_kv: dict[str, Any] = {
                "frame_count": sm.frame_count,
                "resolution": f"{sm.width}×{sm.height} px",
                "pixel_depth": f"{p_depth}-bit",
                "color_id": c_name,
            }
            if _is_available(sm.cfa_pattern_str):
                ser_kv["cfa_pattern"] = sm.cfa_pattern_str
            if _is_available(sm.observer):
                ser_kv["observer"] = sm.observer
            if _is_available(sm.instrument):
                ser_kv["instrument"] = sm.instrument
            if _is_available(sm.telescope):
                ser_kv["telescope"] = sm.telescope
            logger.verbose(
                LogModule.INPUT,
                f"SER astronomy stream metadata: {sm.frame_count} frames ({p_depth}-bit, {c_name}).",
                details=ser_kv,
            )
        else:
            logger.info(
                LogModule.INPUT,
                f"SER astronomy stream loaded: {sm.frame_count} frames ({p_depth}-bit).",
            )

    # DEBUG: Diagnostik internal pembacaan berkas
    if logger.is_debug_enabled:
        logger.debug(
            LogModule.INPUT,
            f"Reader diagnostics: reader={reader_name}, stored_shape=({info.stored_height}, {info.stored_width}), "
            f"active_shape=({info.height}, {info.width}), dtype={dtype_str}, hdu={info.hdu_index}, page={info.page_index}.",
            details={
                "source_path": str(info.path),
                "stored_width": info.stored_width,
                "stored_height": info.stored_height,
                "orientation_applied": info.orientation_applied,
                "duration_ms": round(duration_ms, 3),
            },
        )

    logger.success(
        LogModule.INPUT,
        f"{input_mode_label} loaded successfully.",
        format_duration(duration_ms=duration_ms),
        details={
            "filename": info.file_name,
            "frame_count": frame_count,
            "duration_ms": round(duration_ms, 3),
        },
    )


def log_sequence_validation_report(
    logger: HilaloneLogger,
    report: SequenceCompatibilityReport,
    entries: tuple[SequenceFrameEntry, ...],
    *,
    input_mode: InputMode,
    user_selected_count: int | None = None,
    duration_ms: float = 0.0,
) -> None:
    """Mencatat hasil validasi struktural sequence sesuai tingkat Detail (NORMAL/VERBOSE/DEBUG)."""
    from hilalone.input_manager.models import FrameStatus

    logger.section("SEQUENCE VALIDATION", module=LogModule.SEQUENCE)
    total = report.total_files
    compat = report.compatible_count
    incompat = report.incompatible_count
    err_cnt = report.error_count
    selected_cnt = user_selected_count if user_selected_count is not None else compat
    user_excluded = max(0, total - selected_cnt - incompat - err_cnt) if user_selected_count is not None else 0
    total_excluded = incompat + err_cnt + user_excluded

    # NORMAL: Ringkasan kompatibilitas utama
    logger.info(
        LogModule.SEQUENCE,
        f"Total frames detected: {total} | Compatible frames: {compat}.",
        details={"total_frames": total, "compatible_frames": compat, "mode": input_mode.value},
    )

    # VERBOSE: Rincian kompatibel, inkompatibel, decoding error, dan seleksi pengguna
    if logger.is_verbose_enabled:
        logger.verbose(
            LogModule.SEQUENCE,
            f"Sequence breakdown: total={total}, compatible={compat}, incompatible={incompat}, error={err_cnt}.",
            details={
                "total_frames": total,
                "compatible_frames": compat,
                "incompatible_frames": incompat,
                "error_frames": err_cnt,
            },
        )
        if user_selected_count is not None:
            logger.verbose(
                LogModule.SEQUENCE,
                f"Frames selected by user: {selected_cnt} | Excluded: {total_excluded}.",
                details={
                    "selected_by_user": selected_cnt,
                    "excluded_total": total_excluded,
                    "excluded_user_deselected": user_excluded,
                },
            )

    # WARNING & ERROR selalu dicatat pada semua mode (NORMAL, VERBOSE, DEBUG)
    if incompat > 0:
        logger.warning(
            LogModule.SEQUENCE,
            f"Incompatible frames: {incompat} (structural incompatibility).",
            details={"incompatible_frames": incompat},
        )
    if err_cnt > 0:
        logger.warning(
            LogModule.SEQUENCE,
            f"Decoding errors: {err_cnt}.",
            details={"decoding_errors": err_cnt},
        )

    for entry in entries:
        if entry.status == FrameStatus.INCOMPATIBLE:
            reason = "; ".join(entry.issues) if entry.issues else "Structural mismatch with reference frame"
            logger.warning(
                LogModule.SEQUENCE,
                f"Frame #{entry.frame_index + 1} '{entry.file_name}' excluded (structural incompatibility).",
                details={"frame_index": entry.frame_index + 1, "filename": entry.file_name, "reason": reason},
            )
        elif entry.status == FrameStatus.ERROR:
            reason = "; ".join(entry.issues) if entry.issues else "File decoding error"
            logger.error(
                LogModule.SEQUENCE,
                f"Frame #{entry.frame_index + 1} '{entry.file_name}' excluded (decoding error).",
                details={"frame_index": entry.frame_index + 1, "filename": entry.file_name, "reason": reason},
            )

    # DEBUG: Diagnostik internal validator sequence
    if logger.is_debug_enabled:
        logger.debug(
            LogModule.VALIDATION,
            f"Sequence validator state: ref_frame_index={report.reference_frame_index}, "
            f"mixed_bit_depth={report.mixed_bit_depth}, is_ready_for_stacking={report.is_ready_for_stacking}.",
            details={
                "reference_frame_index": report.reference_frame_index,
                "mixed_bit_depth": report.mixed_bit_depth,
                "duration_ms": round(duration_ms, 3),
            },
        )

    readiness = "READY" if report.is_ready_for_stacking else ("SINGLE_FRAME" if total == 1 else "REQUIRES_CONFIRMATION")
    logger.success(
        LogModule.VALIDATION,
        "Sequence validation completed.",
        format_duration(duration_ms=duration_ms),
        details={
            "readiness": readiness,
            "duration_ms": round(duration_ms, 3),
        },
    )


def log_master_flat_prepared(
    logger: HilaloneLogger,
    loaded_flat: LoadedMasterFlat,
    *,
    compat: FlatCompatibilityCheckResult | None = None,
    light_frame_count: int | None = None,
    duration_ms: float = 0.0,
) -> None:
    """Mencatat pembuatan/pemuatan Master Flat sesuai tingkat Detail (NORMAL/VERBOSE/DEBUG)."""
    from hilalone.processing.stacking.flat_calibration import (
        NORMALIZATION_FORMULA_TEXT,
        compute_flat_pixel_statistics,
    )

    if loaded_flat.flat_input_type == "SEQUENCE":
        agg_method = (
            "Sigma-Clipped Mean (3.0 sigma)"
            if loaded_flat.frame_count >= 3
            else "Arithmetic Mean"
        )
    else:
        agg_method = "Single Master Flat"

    # NORMAL: Status ringkas Master Flat dan metode normalisasi
    logger.info(
        LogModule.FLAT,
        f"Master Flat loaded: {loaded_flat.source_description} ({agg_method}).",
        details={
            "source": loaded_flat.source_description,
            "flat_frames": loaded_flat.frame_count,
            "normalization": NORMALIZATION_FORMULA_TEXT,
        },
    )

    # VERBOSE & DEBUG: Statistik piksel, dimensi, kanal, dan kompatibilitas detail
    if logger.is_verbose_enabled or logger.is_debug_enabled:
        (
            med_val,
            mean_val,
            inv_count,
            zero_neg_count,
            non_finite_count,
            sat_count,
            _inv_mask,
        ) = compute_flat_pixel_statistics(
            loaded_flat.scientific_data,
            saturation_ceiling=loaded_flat.saturation_ceiling,
            is_cfa_mosaic=loaded_flat.is_cfa_mosaic,
        )
        ch_layout = (
            f"1 channel (Bayer CFA: {loaded_flat.cfa_pattern_str or 'Mosaic'})"
            if loaded_flat.is_cfa_mosaic
            else ("1 channel (Monochrome)" if loaded_flat.channels == 1 else f"{loaded_flat.channels} channels (RGB)")
        )
        logger.verbose(
            LogModule.FLAT,
            f"Light frames: {light_frame_count or 0} | Flat frames: {loaded_flat.frame_count} | Master Flat method: {agg_method}.",
            details={
                "light_frames": light_frame_count or 0,
                "flat_frames": loaded_flat.frame_count,
                "aggregation_method": agg_method,
            },
        )
        logger.verbose(
            LogModule.FLAT,
            f"Flat dimensions: {loaded_flat.width} × {loaded_flat.height} px | Channel layout: {ch_layout} | Data type: float32.",
            details={
                "width": loaded_flat.width,
                "height": loaded_flat.height,
                "channels": loaded_flat.channels,
                "dtype": "float32",
                "storage_dtype": loaded_flat.dtype_str,
            },
        )
        logger.verbose(
            LogModule.FLAT,
            f"Normalization method: {NORMALIZATION_FORMULA_TEXT} (median={med_val:.4g}, mean={mean_val:.4g}).",
        )
        logger.verbose(
            LogModule.FLAT,
            f"Flat invalid pixel statistics: invalid={inv_count}, zero/neg={zero_neg_count}, NaN/Inf={non_finite_count}, saturated={sat_count}.",
            details={
                "invalid_pixels": inv_count,
                "zero_or_neg_pixels": zero_neg_count,
                "nan_or_inf_pixels": non_finite_count,
                "saturated_pixels": sat_count,
            },
        )
        if logger.is_debug_enabled:
            arr = loaded_flat.scientific_data
            logger.debug(
                LogModule.FLAT,
                f"Master Flat buffer allocated: shape={arr.shape}, dtype={arr.dtype}, nbytes={arr.nbytes}, "
                f"saturation_ceiling={loaded_flat.saturation_ceiling}, is_cfa_mosaic={loaded_flat.is_cfa_mosaic}.",
                details={
                    "shape": list(arr.shape),
                    "dtype": str(arr.dtype),
                    "nbytes": int(arr.nbytes),
                    "duration_ms": round(duration_ms, 3),
                },
            )

    if compat is not None:
        if compat.is_compatible:
            if logger.is_verbose_enabled:
                logger.verbose(
                    LogModule.CALIBRATION,
                    "Compatibility status: COMPATIBLE with Light frames.",
                )
        else:
            # Ketidakcocokan selalu dicatat sebagai WARNING di semua mode
            logger.warning(
                LogModule.CALIBRATION,
                f"Compatibility status: {compat.status_text}",
            )

    for w in loaded_flat.warnings:
        logger.warning(LogModule.FLAT, w)

    logger.success(
        LogModule.FLAT,
        "Master Flat generated and validated successfully.",
        format_duration(duration_ms=duration_ms),
        details={"duration_ms": round(duration_ms, 3)},
    )


def log_pipeline_execution_details(
    logger: HilaloneLogger,
    result: PipelineResult,
    *,
    run_id: str,
    total_input_frames: int,
    user_excluded_count: int = 0,
    curve_applied: bool = False,
    output_files: tuple[str, ...] = (),
    wall_elapsed_sec: float | None = None,
) -> ProcessingRunSummary:
    """Mencatat rincian setiap tahapan ilmiah pada PipelineResult sesuai tingkat Detail (NORMAL/VERBOSE/DEBUG)."""
    from hilalone.processing.processing_models import PipelineStage

    stage_map = {rec.stage: rec for rec in result.stage_records}
    thread_name = threading.current_thread().name

    # -------------------------------------------------------------------------
    # 1. FLAT FIELD CALIBRATION (Bagian XII)
    # -------------------------------------------------------------------------
    logger.section("FLAT FIELD CALIBRATION", module=LogModule.CALIBRATION, run_id=run_id)
    flat_rec = stage_map.get(PipelineStage.FLAT_CALIBRATION)
    flat_rep = result.flat_report
    if flat_rep is not None and flat_rep.applied:
        flat_dur = flat_rec.duration_ms if flat_rec else 0.0
        logger.info(
            LogModule.CALIBRATION,
            f"Flat Calibration: ENABLED ({flat_rep.source_description}).",
            run_id=run_id,
        )
        if logger.is_verbose_enabled:
            logger.verbose(
                LogModule.CALIBRATION,
                f"Light frames: {total_input_frames} | Flat frames: {flat_rep.flat_frame_count} (1 Master Flat).",
                details={
                    "light_frames": total_input_frames,
                    "flat_frames": flat_rep.flat_frame_count,
                    "flat_source": flat_rep.source_description,
                    "dimensions": f"{flat_rep.width}×{flat_rep.height} px",
                    "channels": flat_rep.channels,
                },
                run_id=run_id,
            )
            logger.verbose(
                LogModule.FLAT,
                f"Normalization method: {flat_rep.normalization_method} | Invalid pixels: {flat_rep.invalid_pixel_count}.",
                details={
                    "median_before_norm": round(flat_rep.flat_median_before_norm, 4),
                    "invalid_pixels": flat_rep.invalid_pixel_count,
                    "nan_inf_pixels": flat_rep.non_finite_pixel_count,
                    "saturated_pixels": flat_rep.saturated_pixel_count,
                },
                run_id=run_id,
            )
        if logger.is_debug_enabled:
            cal_shape = result.calibrated_data.shape if result.calibrated_data is not None else (flat_rep.height, flat_rep.width)
            logger.debug(
                LogModule.CALIBRATION,
                f"Flat division execution: calibrated_shape={cal_shape}, dtype=float32, "
                f"protected_zero_pixels={flat_rep.protected_zero_pixels_count}, thread={thread_name}.",
                details={
                    "protected_zero_pixels": flat_rep.protected_zero_pixels_count,
                    "duration_ms": round(flat_dur, 3),
                },
                run_id=run_id,
            )
        for w in flat_rep.warnings:
            logger.warning(LogModule.CALIBRATION, w, run_id=run_id)
        logger.success(
            LogModule.CALIBRATION,
            "Flat Calibration completed.",
            format_duration(duration_ms=flat_dur),
            details={"duration_ms": round(flat_dur, 3)},
            run_id=run_id,
        )
        flat_summary_status = "APPLIED"
    else:
        logger.skipped(
            LogModule.CALIBRATION,
            "Flat Calibration skipped.",
            reason="Disabled by user",
            run_id=run_id,
        )
        flat_summary_status = "SKIPPED"

    # -------------------------------------------------------------------------
    # 2. IMAGE STACKING (Bagian XIII)
    # -------------------------------------------------------------------------
    logger.section("IMAGE STACKING", module=LogModule.STACKING, run_id=run_id)
    stk_rec = stage_map.get(PipelineStage.STACKING)
    stk_res = result.stacking_result
    if stk_res is not None:
        stk_dur = stk_rec.duration_ms if stk_rec else 0.0
        prof_val = stk_res.profile_config.profile.value
        algo_val = stk_res.effective_algorithm.value
        excl_cnt = len(stk_res.excluded_frames)
        out_h, out_w = stk_res.stacked_scientific_data.shape[:2]
        out_ch = stk_res.stacked_scientific_data.shape[2] if stk_res.stacked_scientific_data.ndim == 3 else 1

        # NORMAL: Metode stacking & jumlah frame ringkas
        logger.info(
            LogModule.STACKING,
            f"Starting image integration | Profile: {prof_val} | Method: {algo_val} ({stk_res.stacked_frame_count} frames).",
            run_id=run_id,
        )

        # VERBOSE: Rincian metode penolakan outlier, pembobotan, dimensi, dan tipe data keluaran
        if logger.is_verbose_enabled:
            logger.verbose(
                LogModule.STACKING,
                f"Stacking configuration: profile={prof_val}, method={algo_val}, selected_frames={stk_res.stacked_frame_count}/{stk_res.total_input_frames} (excluded={excl_cnt}).",
                details={
                    "profile": prof_val,
                    "method": algo_val,
                    "input_frames": stk_res.total_input_frames,
                    "selected_frames": stk_res.stacked_frame_count,
                    "excluded_frames": excl_cnt,
                    "output_dtype": str(stk_res.stacked_scientific_data.dtype),
                    "output_dimensions": f"{out_w}×{out_h} px ({out_ch} ch)",
                },
                run_id=run_id,
            )
            if stk_res.profile_config.use_sigma_clipping:
                logger.verbose(
                    LogModule.STACKING,
                    f"Rejection method: Median + MAD Sigma Clipping (sigma_low={stk_res.profile_config.sigma_low}, sigma_high={stk_res.profile_config.sigma_high}, rejected_samples={stk_res.total_rejected_pixel_samples}).",
                    run_id=run_id,
                )
            if stk_res.profile_config.use_quality_weights:
                logger.verbose(
                    LogModule.STACKING,
                    f"Weighting method: Inverse Noise Variance Quality Weighting (clamp=[{stk_res.profile_config.weight_clamp_min}, {stk_res.profile_config.weight_clamp_max}]).",
                    run_id=run_id,
                )

        # DEBUG: Buffer internal, strip count, dan memory limit
        if logger.is_debug_enabled:
            arr_stk = stk_res.stacked_scientific_data
            logger.debug(
                LogModule.STACKING,
                f"Stacking engine diagnostics: output_shape={arr_stk.shape}, dtype={arr_stk.dtype}, "
                f"nbytes={arr_stk.nbytes}, strip_count={stk_res.strip_count_used}, "
                f"memory_limit_mb={stk_res.working_memory_limit_mb}, thread={thread_name}.",
                details={
                    "shape": list(arr_stk.shape),
                    "dtype": str(arr_stk.dtype),
                    "strip_count": stk_res.strip_count_used,
                    "working_memory_limit_mb": stk_res.working_memory_limit_mb,
                    "duration_ms": round(stk_dur, 3),
                },
                run_id=run_id,
            )

        for ex in stk_res.excluded_frames:
            logger.warning(
                LogModule.STACKING,
                f"Excluded Frame #{ex.frame_index + 1} ('{ex.file_name}'): {ex.reason}",
                run_id=run_id,
            )

        logger.success(
            LogModule.STACKING,
            "Image integration completed.",
            format_duration(duration_ms=stk_dur),
            details={
                "output_dtype": str(stk_res.stacked_scientific_data.dtype),
                "output_dimensions": f"{out_w}×{out_h} px ({out_ch} ch)",
                "duration_ms": round(stk_dur, 3),
            },
            run_id=run_id,
        )
        frames_processed = stk_res.stacked_frame_count
        frames_excluded = excl_cnt
        stacking_summary_status = "COMPLETED"
    else:
        logger.skipped(
            LogModule.STACKING,
            "Image stacking skipped.",
            reason="Single Image mode (1 frame)",
            run_id=run_id,
        )
        frames_processed = 1
        frames_excluded = user_excluded_count
        stacking_summary_status = "SKIPPED"

    # -------------------------------------------------------------------------
    # 3. BACKGROUND EXTRACTION (Bagian XIV)
    # -------------------------------------------------------------------------
    logger.section("BACKGROUND EXTRACTION", module=LogModule.BACKGROUND, run_id=run_id)
    bg_rec = stage_map.get(PipelineStage.BACKGROUND_EXTRACTION)
    bg_res = result.background_result
    bg_dur = bg_rec.duration_ms if bg_rec else 0.0
    bg_method = bg_res.effective_method.value
    bg_cfg = bg_res.config_used

    if "POLYNOMIAL" in bg_method:
        poly_deg = 1 if "DEG_1" in bg_method else 2
        interp_desc = f"2D Polynomial Surface (degree={poly_deg})"
    else:
        poly_deg = None
        interp_desc = f"Thin Plate Spline RBF (smoothing={bg_res.effective_rbf_smoothing:.4g})"

    # NORMAL: Status ringkas ekstraksi background
    logger.info(
        LogModule.BACKGROUND,
        f"Starting background modeling | Method: {bg_method}.",
        run_id=run_id,
    )

    # VERBOSE: Parameter aktual polinomial/RBF, mesh grid, sampel, dan reduksi gradien
    if logger.is_verbose_enabled:
        bg_params: dict[str, Any] = {
            "method": bg_method,
            "interpolation": interp_desc,
            "mesh_size": f"{bg_cfg.grid_rows}×{bg_cfg.grid_cols}",
            "accepted_samples": bg_res.accepted_sample_count,
            "rejected_samples": bg_res.rejected_sample_count,
            "gradient_reduction": f"{bg_res.residual_stats.gradient_reduction_ratio:.1%}",
            "overcorrection_score": round(bg_res.residual_stats.overcorrection_score, 4),
        }
        if poly_deg is not None:
            bg_params["polynomial_degree"] = poly_deg
        else:
            bg_params["rbf_smoothing"] = round(bg_res.effective_rbf_smoothing, 4)
        if bg_res.protected_pixel_count > 0:
            bg_params["protected_roi_pixels"] = bg_res.protected_pixel_count

        logger.verbose(
            LogModule.BACKGROUND,
            f"Background parameters: method={bg_method}, interpolation={interp_desc}, mesh={bg_cfg.grid_rows}×{bg_cfg.grid_cols}.",
            details=bg_params,
            run_id=run_id,
        )

    # DEBUG: Diagnostik internal solver & statistik residual
    if logger.is_debug_enabled:
        bm_arr = bg_res.background_model
        rs = bg_res.residual_stats
        logger.debug(
            LogModule.BACKGROUND,
            f"Background solver diagnostics: model_shape={bm_arr.shape}, dtype={bm_arr.dtype}, "
            f"mad_sigma_clip={bg_cfg.mad_sigma_clip}, max_iterations={bg_cfg.max_rejection_iterations}, "
            f"residual_rms={rs.residual_rms:.4g}, residual_mad_sigma={rs.residual_mad_sigma:.4g}.",
            details={
                "model_shape": list(bm_arr.shape),
                "dtype": str(bm_arr.dtype),
                "residual_rms": round(rs.residual_rms, 5),
                "residual_mad_sigma": round(rs.residual_mad_sigma, 5),
                "duration_ms": round(bg_dur, 3),
            },
            run_id=run_id,
        )

    for w in bg_res.warnings:
        logger.warning(LogModule.BACKGROUND, w, run_id=run_id)

    logger.success(
        LogModule.BACKGROUND,
        "Background extraction completed (subtractive correction on linear branch).",
        format_duration(duration_ms=bg_dur),
        details={"duration_ms": round(bg_dur, 3)},
        run_id=run_id,
    )
    bg_summary_status = "COMPLETED"

    # -------------------------------------------------------------------------
    # 4. IMAGE ENHANCEMENT (Bagian XV)
    # -------------------------------------------------------------------------
    logger.section("IMAGE ENHANCEMENT", module=LogModule.ENHANCEMENT, run_id=run_id)
    enh_rec = stage_map.get(PipelineStage.IMAGE_ENHANCEMENT)
    enh_res = result.enhancement_result
    enh_dur = enh_rec.duration_ms if enh_rec else 0.0
    if enh_res.config_used.enabled:
        tiles_y, tiles_x = enh_res.effective_kernel_tiles
        # NORMAL: Metode enhancement secara ringkas
        logger.info(
            LogModule.ENHANCEMENT,
            "Method: CLAHE | Status: ENABLED.",
            run_id=run_id,
        )
        # VERBOSE: Parameter Clip Limit, Tile Grid Size, Channel, dan cabang data
        if logger.is_verbose_enabled:
            logger.verbose(
                LogModule.ENHANCEMENT,
                f"CLAHE parameters: clip_limit={enh_res.effective_clip_limit:.4f}, tile_grid_size={tiles_y}×{tiles_x}, channel={enh_res.color_mode}.",
                details={
                    "clip_limit": round(enh_res.effective_clip_limit, 4),
                    "tile_grid_size": f"{tiles_y}×{tiles_x}",
                    "channel_mode": enh_res.color_mode,
                    "input_branch": "LINEAR (float32)",
                    "output_branch": "ENHANCED_DERIVED (float32)",
                    "noise_amplification_ratio": round(enh_res.noise_amplification_ratio, 3),
                },
                run_id=run_id,
            )
        # DEBUG: Diagnostik internal CLAHE (working range, noise sigma before/after, backend)
        if logger.is_debug_enabled:
            enh_arr = enh_res.enhanced_data
            logger.debug(
                LogModule.ENHANCEMENT,
                f"CLAHE internal diagnostics: backend={enh_res.backend_used}, shape={enh_arr.shape}, dtype={enh_arr.dtype}, "
                f"working_range=[{enh_res.working_min:.4g}, {enh_res.working_max:.4g}], "
                f"noise_sigma={enh_res.noise_sigma_before:.4g}->{enh_res.noise_sigma_after:.4g}.",
                details={
                    "backend": enh_res.backend_used,
                    "shape": list(enh_arr.shape),
                    "dtype": str(enh_arr.dtype),
                    "working_min": round(enh_res.working_min, 5),
                    "working_max": round(enh_res.working_max, 5),
                    "duration_ms": round(enh_dur, 3),
                },
                run_id=run_id,
            )
        for w in enh_res.warnings:
            logger.warning(LogModule.ENHANCEMENT, w, run_id=run_id)
        logger.success(
            LogModule.ENHANCEMENT,
            "Enhancement completed (scientific linear_result branch preserved unmodified).",
            format_duration(duration_ms=enh_dur),
            details={"duration_ms": round(enh_dur, 3)},
            run_id=run_id,
        )
        enh_summary_status = "COMPLETED"
    else:
        logger.skipped(
            LogModule.ENHANCEMENT,
            "Image Enhancement (CLAHE) skipped.",
            reason="Disabled by user",
            run_id=run_id,
        )
        enh_summary_status = "SKIPPED"

    # -------------------------------------------------------------------------
    # 5. HISTOGRAM TRANSFORMATION (Bagian XVI)
    # -------------------------------------------------------------------------
    logger.section("HISTOGRAM TRANSFORMATION", module=LogModule.HISTOGRAM, run_id=run_id)
    hist_rec = stage_map.get(PipelineStage.HISTOGRAM_TRANSFORMATION)
    hist_res = result.histogram_result
    hist_dur = hist_rec.duration_ms if hist_rec else 0.0
    stretch_name = hist_res.effective_method.value
    in_branch = "ENHANCED_DERIVED" if enh_res.config_used.enabled else "LINEAR"

    # NORMAL: Stretch method ringkas & pernyataan kejujuran cabang DISPLAY
    logger.info(
        LogModule.HISTOGRAM,
        f"Stretch method: {stretch_name} | Input branch: {in_branch} -> Output branch: DISPLAY.",
        run_id=run_id,
    )
    logger.info(
        LogModule.HISTOGRAM,
        "Display transformation applies only to DISPLAY branch; scientific linear data remains unchanged.",
        run_id=run_id,
    )

    # VERBOSE: Parameter aktual transformasi histogram
    if logger.is_verbose_enabled:
        hist_params: dict[str, Any] = {
            "stretch_method": stretch_name,
            "input_branch": in_branch,
            "output_branch": "DISPLAY",
            "vmin": round(hist_res.vmin, 6),
            "vmax": round(hist_res.vmax, 6),
            "mtf_midtone": round(hist_res.effective_midtone_balance, 4),
            "output_min": round(float(np.min(hist_res.display_data)), 4),
            "output_max": round(float(np.max(hist_res.display_data)), 4),
        }
        if "ASINH" in stretch_name:
            hist_params["asinh_a"] = round(hist_res.effective_asinh_a, 4)
        if "GHS" in stretch_name:
            hist_params["ghs_d"] = hist_res.config_used.ghs_stretch_factor_d
            hist_params["ghs_b"] = hist_res.config_used.ghs_local_intensity_b
            hist_params["ghs_sp"] = hist_res.config_used.ghs_symmetry_point_sp

        logger.verbose(
            LogModule.HISTOGRAM,
            f"Histogram stretch parameters: vmin={hist_res.vmin:.4g}, vmax={hist_res.vmax:.4g}, mtf_midtone={hist_res.effective_midtone_balance:.4f}.",
            details=hist_params,
            run_id=run_id,
        )

    # DEBUG: Diagnostik internal distribusi piksel & persentil
    if logger.is_debug_enabled:
        disp_arr = hist_res.display_data
        hd = hist_res.histogram_data
        logger.debug(
            LogModule.HISTOGRAM,
            f"Histogram internal diagnostics: display_shape={disp_arr.shape}, dtype={disp_arr.dtype}, "
            f"valid_pixels={hist_res.valid_pixel_count}, percentiles=[{hist_res.effective_low_percentile}%, {hist_res.effective_high_percentile}%], "
            f"median={hd.median_before:.4g}->{hd.median_after:.4g}.",
            details={
                "shape": list(disp_arr.shape),
                "dtype": str(disp_arr.dtype),
                "valid_pixel_count": hist_res.valid_pixel_count,
                "median_before": round(hd.median_before, 5),
                "median_after": round(hd.median_after, 5),
                "duration_ms": round(hist_dur, 3),
            },
            run_id=run_id,
        )

    for w in hist_res.warnings:
        logger.warning(LogModule.HISTOGRAM, w, run_id=run_id)

    logger.success(
        LogModule.HISTOGRAM,
        "Display transformation completed.",
        format_duration(duration_ms=hist_dur),
        details={"duration_ms": round(hist_dur, 3)},
        run_id=run_id,
    )
    hist_summary_status = "COMPLETED"

    # -------------------------------------------------------------------------
    # 6. PROCESSING SUMMARY (Bagian XX)
    # -------------------------------------------------------------------------
    total_sec = wall_elapsed_sec if wall_elapsed_sec is not None else result.total_elapsed_seconds
    summary = ProcessingRunSummary(
        run_id=run_id,
        status="SUCCESS",
        profile=result.profile.value,
        input_frames=total_input_frames,
        frames_processed=frames_processed,
        frames_excluded=frames_excluded,
        flat_calibration_status=flat_summary_status,
        stacking_status=stacking_summary_status,
        background_status=bg_summary_status,
        enhancement_status=enh_summary_status,
        histogram_status=hist_summary_status,
        curve_status="APPLIED" if curve_applied else "NOT USED",
        output_files=output_files,
        processing_time_sec=total_sec,
    )
    logger.log_processing_summary(summary)
    return summary


def log_output_saved(
    logger: HilaloneLogger,
    saved_path: Path,
    *,
    product_category: str,
    data_array: np.ndarray | None = None,
    duration_ms: float = 0.0,
    json_report_path: Path | None = None,
) -> None:
    """Mencatat penulisan berkas hasil pemrosesan sesuai tingkat Detail (NORMAL/VERBOSE/DEBUG)."""
    logger.section("OUTPUT GENERATION", module=LogModule.OUTPUT)

    ext = saved_path.suffix.lower().lstrip(".").upper() or "FILE"
    exists_ok = saved_path.exists() and saved_path.is_file()
    file_size = saved_path.stat().st_size if exists_ok else 0

    # NORMAL: Ringkasan penulisan berkas output
    logger.info(
        LogModule.OUTPUT,
        f"Writing {product_category} ({ext}): {saved_path.name}",
        details={
            "filename": saved_path.name,
            "format": ext,
        },
    )

    # VERBOSE: Tipe data, dimensi, rentang, path lengkap, dan ukuran berkas
    if logger.is_verbose_enabled:
        verb_details: dict[str, Any] = {
            "format": ext,
            "output_location": str(saved_path),
            "file_size_bytes": file_size,
        }
        if data_array is not None and data_array.size > 0:
            h, w = data_array.shape[:2]
            ch = data_array.shape[2] if data_array.ndim == 3 else 1
            verb_details["dimensions"] = f"{w}×{h} px ({ch} ch)"
            verb_details["dtype"] = str(data_array.dtype)
            finite = data_array[np.isfinite(data_array)]
            if finite.size > 0:
                verb_details["range"] = f"[{float(np.min(finite)):.4g}, {float(np.max(finite)):.4g}]"
        logger.verbose(
            LogModule.OUTPUT,
            f"Output details: format={ext}, path={saved_path}, size={file_size} B.",
            details=verb_details,
        )

    # DEBUG: Diagnostik internal verifikasi berkas & laporan JSON pendamping
    if logger.is_debug_enabled:
        dbg_details: dict[str, Any] = {
            "verified_exists": exists_ok,
            "file_size_bytes": file_size,
            "report_json": json_report_path.name if (json_report_path and json_report_path.exists()) else None,
            "duration_ms": round(duration_ms, 3),
        }
        if data_array is not None:
            dbg_details["array_shape"] = list(data_array.shape)
            dbg_details["array_dtype"] = str(data_array.dtype)
        logger.debug(
            LogModule.OUTPUT,
            f"Output verification diagnostics: path={saved_path.resolve()}, exists={exists_ok}, "
            f"size_bytes={file_size}, report_json={dbg_details['report_json']}.",
            details=dbg_details,
        )

    if exists_ok and file_size > 0:
        logger.success(
            LogModule.OUTPUT,
            "File saved and verified successfully.",
            format_duration(duration_ms=duration_ms),
            details={
                "location": str(saved_path),
                "size_bytes": file_size,
                "duration_ms": round(duration_ms, 3),
            },
        )
    else:
        logger.error(
            LogModule.OUTPUT,
            f"Output verification failed for '{saved_path.name}'.",
            details={"location": str(saved_path)},
        )
