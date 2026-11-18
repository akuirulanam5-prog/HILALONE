"""Sistem HILALONE Scientific Processing Timeline & Report (Schema v2.0).

Menyusun laporan ilmiah terstruktur yang merekam perjalanan lengkap pengolahan citra:
  - DARI: Pengguna pertama kali menekan Open Image (Session Start)
  - HINGGA: Berkas hasil pemrosesan berhasil disimpan dan laporan JSON pendamping dibuat (Session End).

Mencakup:
  1. ``report_metadata``          : Identitas unik laporan, schema v2.0, Run ID, dan waktu pembuatan.
  2. ``session_information``      : Identitas sesi, OS, arsitektur, profil, konfigurasi, start & end time.
  3. ``source_data``              : Informasi sumber citra terdeduplikasi (1 entri video untuk N frame).
  4. ``user_interaction_timeline``: Kronologi tindakan pengguna, operasi backend, dan latensi.
  5. ``workflow_idle_intervals``  : Interval waktu tunggu saat tidak ada komputasi backend aktif.
  6. ``processing_pipeline``      : Rincian 11 tahapan pemrosesan dengan parameter aktual yang digunakan.
  7. ``scientific_data_branches`` : Pemisahan ketat cabang Linear, Enhanced Derived, dan Display.
  8. ``output_information``       : Transaksi penyimpanan (durasi dialog vs durasi tulis disk & verifikasi).
  9. ``timing_summary``           : Ringkasan metrik waktu end-to-end, komputasi, idle, dan penulisan.
  10. ``warnings`` & ``scientific_notes`` : Peringatan aktual dan catatan kejujuran ilmiah.
  11. Kompatibilitas mundur penuh untuk pembacaan arsip laporan Schema v1.0.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
import time
from typing import Any, Iterable

from astropy.io import fits
import numpy as np

from hilalone import APP_NAME, __version__
from hilalone.core.logging.aligned_summary import (
    format_aligned_summary,
    format_duration_seconds,
)
from hilalone.core.logging.log_session import format_timestamps, generate_run_id
from hilalone.core.logging.logger import get_logger
from hilalone.core.logging.workflow_timeline import (
    OutputArtifactRecord,
    SaveTransactionContext,
    WorkflowTimelineTracker,
    format_utc_timestamp,
    generate_report_id,
)
from hilalone.processing.processing_models import (
    BackgroundModelMethod,
    PipelineResult,
    PipelineStage,
    StageStatus,
    StretchMethod,
)

REPORT_SCHEMA_VERSION = "2.0"
REPORT_NAME = "HILALONE Scientific Processing Report"


def _is_available(val: Any) -> bool:
    if val is None:
        return False
    s = str(val).strip()
    if not s:
        return False
    return s.lower() not in ("tidak tersedia", "unavailable", "none", "null", "-")


def _extract_source_metadata_from_info(info: Any) -> dict[str, Any]:
    """Mengekstrak metadata ilmiah yang benar-benar tersedia dari objek ImageInfo tanpa mengarang nilai."""
    meta: dict[str, Any] = {}
    if info is None:
        return meta

    # 1. Video metadata
    vm = getattr(info, "video_metadata", None)
    if vm is not None:
        v_dict: dict[str, Any] = {}
        if _is_available(getattr(vm, "container_format", None)):
            v_dict["container_format"] = vm.container_format
        if _is_available(getattr(vm, "codec_name", None)):
            v_dict["video_codec"] = vm.codec_name
        pix_fmt = getattr(info, "decoded_pix_fmt", None) or getattr(vm, "pix_fmt", None)
        if _is_available(pix_fmt):
            v_dict["pixel_format"] = pix_fmt
        fps = getattr(vm, "average_rate_fps", None)
        if fps is not None and fps > 0:
            v_dict["frame_rate_fps"] = round(float(fps), 4)
        if _is_available(getattr(vm, "time_base_str", None)):
            v_dict["time_base"] = vm.time_base_str
        dur_s = getattr(vm, "duration_sec", None)
        if dur_s is not None and dur_s >= 0:
            v_dict["video_duration_s"] = round(float(dur_s), 4)
            v_dict["video_duration_display"] = format_duration_seconds(duration_s=dur_s)
        if v_dict:
            meta["video_metadata"] = v_dict

    # 2. FITS metadata
    fh = getattr(info, "fits_header", None)
    if fh is not None:
        f_dict: dict[str, Any] = {}
        for attr, key in (
            ("bitpix", "BITPIX"),
            ("naxis", "NAXIS"),
            ("naxis1", "NAXIS1"),
            ("naxis2", "NAXIS2"),
            ("bunit", "BUNIT"),
            ("object_name", "OBJECT"),
            ("telescop", "TELESCOP"),
            ("instrume", "INSTRUME"),
            ("observer", "OBSERVER"),
            ("exptime", "EXPTIME"),
            ("date_obs", "DATE-OBS"),
            ("filter_name", "FILTER"),
        ):
            val = getattr(fh, attr, None)
            if _is_available(val):
                f_dict[key] = val
        if f_dict:
            meta["fits_metadata"] = f_dict

    # 3. Camera RAW metadata
    rm = getattr(info, "raw_metadata", None)
    if rm is not None:
        r_dict: dict[str, Any] = {}
        cam_name = (
            rm.format_camera_name()
            if hasattr(rm, "format_camera_name")
            else f"{getattr(rm, 'camera_make', '') or ''} {getattr(rm, 'camera_model', '') or ''}".strip()
        )
        if _is_available(cam_name):
            r_dict["camera_model"] = cam_name
        if _is_available(getattr(rm, "cfa_pattern_str", None)):
            r_dict["cfa_pattern"] = rm.cfa_pattern_str
        if _is_available(getattr(rm, "white_level", None)):
            r_dict["white_level"] = rm.white_level
        if _is_available(getattr(rm, "black_level_summary", None)):
            r_dict["black_level"] = rm.black_level_summary
        if _is_available(getattr(rm, "iso_speed", None)):
            r_dict["iso_speed"] = rm.iso_speed
        if r_dict:
            meta["raw_metadata"] = r_dict

    # 4. SER metadata
    sm = getattr(info, "ser_metadata", None)
    if sm is not None:
        s_dict: dict[str, Any] = {
            "frame_count": getattr(sm, "frame_count", None),
            "pixel_depth_per_plane": getattr(
                sm,
                "pixel_depth_per_plane",
                getattr(sm, "pixel_depth", getattr(info, "original_bit_depth", None)),
            ),
            "color_format": getattr(sm, "color_format_name", getattr(sm, "color_id", None)),
        }
        for attr in ("cfa_pattern_str", "observer", "instrument", "telescope"):
            val = getattr(sm, attr, None)
            if _is_available(val):
                s_dict[attr] = val
        meta["ser_metadata"] = {k: v for k, v in s_dict.items() if v is not None}

    return meta


def build_source_data_section(
    result: PipelineResult,
    *,
    timeline_tracker: WorkflowTimelineTracker | None = None,
    source_paths: Iterable[str | Path] = (),
) -> tuple[dict[str, Any], list[str]]:
    """Menyusun bagian ``source_data`` terdeduplikasi (Bagian VI & XIV).

    Jika input berupa 1 berkas video atau SER dengan N frame, hanya mencatat 1 entri berkas
    dengan ``decoded_frame_count = N`` (tidak mengulang nama video N kali).
    """
    arr = result.original_data
    h, w = int(arr.shape[0]), int(arr.shape[1])
    ch = int(arr.shape[2]) if arr.ndim == 3 else 1
    dtype_str = str(arr.dtype)

    raw_names = list(result.source_file_names)
    if not raw_names and source_paths:
        raw_names = [Path(p).name for p in source_paths]
    if not raw_names:
        raw_names = ["in_memory_source"]

    # Ambil snapshot ImageInfo dari timeline_tracker jika tersedia
    ref_info = None
    entries_snapshot: list[Any] = []
    if timeline_tracker is not None:
        with timeline_tracker._lock:
            ref_info = timeline_tracker._single_image_info_snapshot
            entries_snapshot = list(timeline_tracker._source_entries_snapshot)
            if ref_info is None and entries_snapshot:
                ref_info = getattr(entries_snapshot[0], "info", None)

    info_by_filename: dict[str, Any] = {}
    for ent in entries_snapshot:
        ent_info = getattr(ent, "info", None)
        fname = getattr(ent, "file_name", None) or (getattr(ent_info, "file_name", None) if ent_info else None)
        if fname and ent_info is not None and fname not in info_by_filename:
            info_by_filename[fname] = ent_info
    if ref_info is not None and getattr(ref_info, "file_name", None):
        info_by_filename.setdefault(ref_info.file_name, ref_info)

    # Deduplikasi nama berkas dengan mempertahankan urutan kemunculan pertama
    counts_by_name = Counter(raw_names)
    unique_names: list[str] = []
    seen: set[str] = set()
    for name in raw_names:
        if name not in seen:
            seen.add(name)
            unique_names.append(name)

    files_list: list[dict[str, Any]] = []
    for idx, fname in enumerate(unique_names, start=1):
        f_info = info_by_filename.get(fname, ref_info)
        ext_fmt = Path(fname).suffix.lstrip(".").upper() or result.input_mode
        fmt_str = getattr(f_info, "file_format", None) or ext_fmt
        bit_depth = getattr(f_info, "original_bit_depth", None)
        fw = int(getattr(f_info, "width", w) or w)
        fh_px = int(getattr(f_info, "height", h) or h)
        fch = int(getattr(f_info, "channels", ch) or ch)
        fdtype = str(getattr(f_info, "dtype_str", None) or dtype_str)

        file_entry: dict[str, Any] = {
            "source_id": f"SOURCE_{idx:03d}",
            "filename": fname,
            "format": fmt_str,
            "decoded_frame_count": int(counts_by_name[fname]),
            "resolution": f"{fw}x{fh_px}",
            "width": fw,
            "height": fh_px,
            "channels": fch,
            "dtype": fdtype,
        }
        if bit_depth is not None:
            file_entry["bit_depth"] = int(bit_depth)

        extra_meta = _extract_source_metadata_from_info(f_info)
        file_entry.update(extra_meta)
        files_list.append(file_entry)

    total_frames = sum(counts_by_name.values())
    if result.stacking_result is not None:
        total_frames = max(total_frames, int(result.stacking_result.total_input_frames))

    source_data: dict[str, Any] = {
        "input_mode": result.input_mode,
        "file_count": len(files_list),
        "total_decoded_frames": total_frames,
        "resolution": f"{w}x{h}",
        "width": w,
        "height": h,
        "channels": ch,
        "dtype": dtype_str,
        "is_cfa_mosaic": bool(result.is_cfa_mosaic),
        "cfa_pattern": result.cfa_pattern_str,
        "files": files_list,
    }
    if ref_info is not None and getattr(ref_info, "original_bit_depth", None) is not None:
        source_data["bit_depth"] = int(ref_info.original_bit_depth)

    top_extra = _extract_source_metadata_from_info(ref_info)
    for k, v in top_extra.items():
        source_data.setdefault(k, v)

    return source_data, unique_names


def build_processing_pipeline_section(
    result: PipelineResult,
    *,
    timeline_tracker: WorkflowTimelineTracker | None = None,
    save_target: str = "LINEAR",
    output_format: str = "FITS",
) -> tuple[dict[str, Any], float]:
    """Menyusun bagian ``processing_pipeline`` (11 sub-tahap terpisah sesuai Bagian IX)."""
    stage_map = {rec.stage: rec for rec in result.stage_records}
    now_iso = format_timestamps()[1]

    # Ambil rekaman tahap dari timeline_tracker bila tersedia
    in_load_start = None
    in_load_end = None
    in_load_ms = None
    mf_rec = None
    curve_rec = None
    disp_rec = None
    if timeline_tracker is not None:
        with timeline_tracker._lock:
            in_load_start = timeline_tracker._input_loading_started_at
            in_load_end = timeline_tracker._input_loading_completed_at
            in_load_ms = timeline_tracker._input_loading_duration_ms
            mf_rec = dict(timeline_tracker._master_flat_record) if timeline_tracker._master_flat_record else None
            curve_rec = dict(timeline_tracker._curve_record) if timeline_tracker._curve_record else None
            disp_rec = dict(timeline_tracker._display_record) if timeline_tracker._display_record else None

    val_rec = stage_map.get(PipelineStage.INPUT_VALIDATION)
    val_ms = float(val_rec.duration_ms) if val_rec is not None else 0.0
    if in_load_ms is None:
        # Jika dijalankan langsung dari orchestrator tanpa GUI load_path terpisah
        in_load_ms = val_ms
        in_load_start = val_rec.started_at if val_rec else now_iso
        in_load_end = val_rec.completed_at if val_rec else now_iso

    h, w = int(result.linear_result.shape[0]), int(result.linear_result.shape[1])
    ch = int(result.linear_result.shape[2]) if result.linear_result.ndim == 3 else 1
    dims_str = f"{w}x{h}" if ch == 1 else f"{w}x{h}x{ch}"

    # 1. INPUT LOADING
    total_in_frames = (
        result.stacking_result.total_input_frames
        if result.stacking_result is not None
        else max(1, len(result.source_file_names))
    )
    input_loading_stage: dict[str, Any] = {
        "stage_id": "STAGE_01_INPUT_LOADING",
        "stage_name": "Input Loading",
        "status": "COMPLETED",
        "started_at": in_load_start or now_iso,
        "completed_at": in_load_end or now_iso,
        "duration_ms": round(float(in_load_ms), 3),
        "duration_display": format_duration_seconds(in_load_ms),
        "input": {
            "input_mode": result.input_mode,
            "total_frames_detected": total_in_frames,
        },
        "parameters": {"read_mode": "READ_ONLY_FLOAT32_CONVERSION"},
        "output": {
            "dimensions": dims_str,
            "data_type": "float32",
        },
        "metrics": {"frames_loaded": total_in_frames},
        "warnings": [],
    }

    # 2. INPUT VALIDATION
    compat_frames = (
        result.stacking_result.stacked_frame_count
        if result.stacking_result is not None
        else 1
    )
    excl_list = (
        [
            {"frame_index": ex.frame_index, "file_name": ex.file_name, "reason": ex.reason}
            for ex in result.stacking_result.excluded_frames
        ]
        if result.stacking_result is not None
        else []
    )
    input_validation_stage: dict[str, Any] = {
        "stage_id": "STAGE_02_INPUT_VALIDATION",
        "stage_name": "Input Validation",
        "status": val_rec.status.value if val_rec else "COMPLETED",
        "started_at": val_rec.started_at if val_rec else now_iso,
        "completed_at": val_rec.completed_at if val_rec else now_iso,
        "duration_ms": round(val_ms, 3),
        "duration_display": format_duration_seconds(val_ms),
        "input": {"total_frames": total_in_frames},
        "parameters": {
            "position_stability_precheck": "DISABLED",
            "registration_alignment": "NOT_PERFORMED",
        },
        "output": {
            "compatible_frames": compat_frames,
            "excluded_frames_count": len(excl_list),
            "excluded_frames": excl_list,
        },
        "metrics": {
            "total_frames": total_in_frames,
            "valid_frames": compat_frames,
            "incompatible_or_excluded_frames": len(excl_list),
        },
        "warnings": list(val_rec.warnings) if val_rec else [],
    }

    # 3. FLAT CALIBRATION & 4. MASTER FLAT GENERATION
    flat_rec = stage_map.get(PipelineStage.FLAT_CALIBRATION)
    fr = result.flat_report
    if fr is not None and fr.applied:
        flat_dur = float(flat_rec.duration_ms) if flat_rec else 0.0
        flat_calibration_stage: dict[str, Any] = {
            "stage_id": "STAGE_03_FLAT_CALIBRATION",
            "stage_name": "Flat Calibration",
            "status": "COMPLETED",
            "started_at": flat_rec.started_at if flat_rec else now_iso,
            "completed_at": flat_rec.completed_at if flat_rec else now_iso,
            "duration_ms": round(flat_dur, 3),
            "duration_display": format_duration_seconds(flat_dur),
            "input": {
                "light_frame_count": compat_frames,
                "flat_frame_count": fr.flat_frame_count,
                "source_description": fr.source_description,
            },
            "parameters": {
                "master_flat_method": fr.flat_input_type,
                "normalization_method": fr.normalization_method,
            },
            "output": {
                "dimensions": f"{fr.width}x{fr.height}x{fr.channels}" if fr.channels > 1 else f"{fr.width}x{fr.height}",
                "data_type": "float32",
            },
            "metrics": {
                "flat_median_before_norm": fr.flat_median_before_norm,
                "flat_mean_before_norm": fr.flat_mean_before_norm,
                "invalid_pixel_count": fr.invalid_pixel_count,
                "zero_or_negative_pixel_count": fr.zero_or_negative_pixel_count,
                "non_finite_pixel_count": fr.non_finite_pixel_count,
                "saturated_pixel_count": fr.saturated_pixel_count,
                "protected_zero_pixels_count": fr.protected_zero_pixels_count,
            },
            "warnings": list(fr.warnings),
        }
        if mf_rec is not None:
            master_flat_stage = mf_rec
        else:
            agg_method = (
                "Single Master Flat"
                if fr.flat_frame_count <= 1
                else ("Sigma-Clipped Mean (3.0 sigma)" if fr.flat_frame_count >= 5 else "Arithmetic Mean")
            )
            master_flat_stage = {
                "stage_id": "STAGE_04_MASTER_FLAT",
                "stage_name": "Master Flat Generation",
                "status": "COMPLETED",
                "started_at": flat_rec.started_at if flat_rec else now_iso,
                "completed_at": flat_rec.completed_at if flat_rec else now_iso,
                "duration_ms": round(flat_dur, 3),
                "duration_display": format_duration_seconds(flat_dur),
                "input": {"input_flat_count": fr.flat_frame_count},
                "parameters": {
                    "aggregation_method": agg_method,
                    "normalization": fr.normalization_method,
                },
                "output": {
                    "output_dimensions": f"{fr.width}x{fr.height}",
                    "data_type": "float32",
                },
                "metrics": {"invalid_pixels": fr.invalid_pixel_count},
                "warnings": list(fr.warnings),
            }
    else:
        skip_reason = (
            fr.not_applied_reason
            if (fr is not None and fr.not_applied_reason)
            else "Disabled by user (Apply Flat Calibration unchecked)"
        )
        flat_calibration_stage = {
            "stage_id": "STAGE_03_FLAT_CALIBRATION",
            "stage_name": "Flat Calibration",
            "status": "SKIPPED",
            "reason": skip_reason,
            "started_at": None,
            "completed_at": None,
            "duration_ms": None,
            "duration_display": None,
            "input": {"light_frame_count": compat_frames, "flat_frame_count": 0},
            "parameters": {},
            "output": None,
            "metrics": {},
            "warnings": [],
        }
        master_flat_stage = (
            mf_rec
            if mf_rec is not None
            else {
                "stage_id": "STAGE_04_MASTER_FLAT",
                "stage_name": "Master Flat Generation",
                "status": "SKIPPED",
                "reason": skip_reason,
                "started_at": None,
                "completed_at": None,
                "duration_ms": None,
                "duration_display": None,
                "input": {"input_flat_count": 0},
                "parameters": {},
                "output": None,
                "metrics": {},
                "warnings": [],
            }
        )

    # 5. STACKING
    stk_rec = stage_map.get(PipelineStage.STACKING)
    sr = result.stacking_result
    if sr is not None:
        stk_dur = float(stk_rec.duration_ms) if stk_rec else 0.0
        rej_method = (
            f"Iterative Median + MAD Sigma Clipping (low={sr.profile_config.sigma_low}, high={sr.profile_config.sigma_high})"
            if sr.profile_config.use_sigma_clipping
            else "NONE"
        )
        weight_method = (
            f"Inverse Noise Variance Quality Weighting (clamp=[{sr.profile_config.weight_clamp_min}, {sr.profile_config.weight_clamp_max}])"
            if sr.profile_config.use_quality_weights
            else "UNIFORM_EQUAL_WEIGHTS"
        )
        stacking_stage: dict[str, Any] = {
            "stage_id": "STAGE_05_STACKING",
            "stage_name": "Image Stacking",
            "status": "COMPLETED",
            "started_at": stk_rec.started_at if stk_rec else now_iso,
            "completed_at": stk_rec.completed_at if stk_rec else now_iso,
            "duration_ms": round(stk_dur, 3),
            "duration_display": format_duration_seconds(stk_dur),
            "input": {
                "total_input_frames": sr.total_input_frames,
                "frames_selected": sr.stacked_frame_count,
            },
            "parameters": {
                "profile": sr.profile_config.profile.value,
                "method": sr.effective_algorithm.value,
                "rejection_method": rej_method,
                "weighting_method": weight_method,
                "registration_alignment": "NOT_PERFORMED",
            },
            "output": {
                "frames_integrated": sr.stacked_frame_count,
                "frames_excluded": len(sr.excluded_frames),
                "output_data_type": str(sr.stacked_scientific_data.dtype),
                "output_dimensions": dims_str,
            },
            "metrics": {
                "total_rejected_pixel_samples": sr.total_rejected_pixel_samples,
                "strip_count_used": sr.strip_count_used,
            },
            "warnings": list(sr.warnings),
        }
    else:
        stacking_stage = {
            "stage_id": "STAGE_05_STACKING",
            "stage_name": "Image Stacking",
            "status": "SKIPPED",
            "reason": "Single Image mode (1 frame); stacking is only applicable to multi-frame sequences.",
            "started_at": None,
            "completed_at": None,
            "duration_ms": None,
            "duration_display": None,
            "input": {"total_input_frames": 1, "frames_selected": 1},
            "parameters": {},
            "output": None,
            "metrics": {},
            "warnings": [],
        }

    # 6. BACKGROUND EXTRACTION
    bg_rec = stage_map.get(PipelineStage.BACKGROUND_EXTRACTION)
    bg = result.background_result
    rs = bg.residual_stats
    bg_dur = float(bg_rec.duration_ms) if bg_rec else 0.0
    bg_method = bg.effective_method
    bg_params: dict[str, Any] = {
        "method": bg_method.value,
        "grid_size": [bg.config_used.grid_rows, bg.config_used.grid_cols],
        "mad_sigma_clip": bg.config_used.mad_sigma_clip,
        "preserve_mean_sky_pedestal": bg.config_used.preserve_mean_sky_pedestal,
    }
    if bg_method in (BackgroundModelMethod.POLYNOMIAL_DEG_1, BackgroundModelMethod.POLYNOMIAL_DEG_2):
        bg_params["polynomial_degree"] = 1 if bg_method == BackgroundModelMethod.POLYNOMIAL_DEG_1 else 2
        bg_params["interpolation"] = f"2D Least-Squares Polynomial Surface (degree={bg_params['polynomial_degree']})"
    else:
        bg_params["interpolation"] = "Thin-Plate Spline Radial Basis Function (RBF)"
        bg_params["rbf_smoothing"] = bg.effective_rbf_smoothing

    background_stage: dict[str, Any] = {
        "stage_id": "STAGE_06_BACKGROUND_EXTRACTION",
        "stage_name": "Background Extraction",
        "status": bg_rec.status.value if bg_rec else "COMPLETED",
        "started_at": bg_rec.started_at if bg_rec else now_iso,
        "completed_at": bg_rec.completed_at if bg_rec else now_iso,
        "duration_ms": round(bg_dur, 3),
        "duration_display": format_duration_seconds(bg_dur),
        "input": {
            "branch": "STACKED_LINEAR" if sr is not None else "CALIBRATED_LINEAR",
            "dimensions": dims_str,
            "data_type": "float32",
        },
        "parameters": bg_params,
        "output": {
            "branch": "SCIENTIFIC_LINEAR_RESULT",
            "dimensions": dims_str,
            "data_type": "float32",
        },
        "metrics": {
            "sample_count": bg.accepted_sample_count + bg.rejected_sample_count,
            "accepted_sample_count": bg.accepted_sample_count,
            "rejected_sample_count": bg.rejected_sample_count,
            "protected_pixel_count": bg.protected_pixel_count,
            "gradient_before_ptp": round(rs.initial_gradient_ptp, 6),
            "gradient_after_ptp": round(rs.residual_gradient_ptp, 6),
            "gradient_reduction_ratio": round(rs.gradient_reduction_ratio, 6),
            "background_median_before": round(rs.background_median_before, 6),
            "background_median_after": round(rs.background_median_after, 6),
            "residual_rms": round(rs.residual_rms, 6),
            "overcorrection_score": round(rs.overcorrection_score, 6),
            "overcorrection_warning": bool(rs.overcorrection_warning),
        },
        "warnings": list(bg.warnings),
    }

    # 7. IMAGE ENHANCEMENT
    enh_rec = stage_map.get(PipelineStage.IMAGE_ENHANCEMENT)
    enh = result.enhancement_result
    enh_dur = float(enh_rec.duration_ms) if enh_rec else 0.0
    if enh.config_used.enabled:
        enhancement_stage: dict[str, Any] = {
            "stage_id": "STAGE_07_IMAGE_ENHANCEMENT",
            "stage_name": "Image Enhancement",
            "status": "COMPLETED",
            "started_at": enh_rec.started_at if enh_rec else now_iso,
            "completed_at": enh_rec.completed_at if enh_rec else now_iso,
            "duration_ms": round(enh_dur, 3),
            "duration_display": format_duration_seconds(enh_dur),
            "input": {"branch": "SCIENTIFIC_LINEAR_RESULT", "data_type": "float32"},
            "parameters": {
                "method": enh.config_used.method.value,
                "backend": enh.backend_used,
                "clip_limit": enh.effective_clip_limit,
                "tile_grid": list(enh.effective_kernel_tiles),
                "channel_processing": enh.color_mode,
            },
            "output": {"branch": "ENHANCED_DERIVED_FLOAT32", "data_type": "float32"},
            "metrics": {
                "noise_sigma_before": round(enh.noise_sigma_before, 6),
                "noise_sigma_after": round(enh.noise_sigma_after, 6),
                "noise_amplification_ratio": round(enh.noise_amplification_ratio, 6),
                "local_contrast_before": round(enh.local_contrast_before, 6),
                "local_contrast_after": round(enh.local_contrast_after, 6),
            },
            "warnings": list(enh.warnings),
        }
    else:
        enhancement_stage = {
            "stage_id": "STAGE_07_IMAGE_ENHANCEMENT",
            "stage_name": "Image Enhancement",
            "status": "SKIPPED",
            "reason": "Disabled in profile configuration",
            "started_at": None,
            "completed_at": None,
            "duration_ms": None,
            "duration_display": None,
            "input": {"branch": "SCIENTIFIC_LINEAR_RESULT"},
            "parameters": {},
            "output": None,
            "metrics": {},
            "warnings": [],
        }

    # 8. HISTOGRAM TRANSFORMATION (Hanya tampilkan parameter yang benar-benar digunakan!)
    hist_rec = stage_map.get(PipelineStage.HISTOGRAM_TRANSFORMATION)
    hist = result.histogram_result
    hist_dur = float(hist_rec.duration_ms) if hist_rec else 0.0
    h_method = hist.effective_method
    hist_params: dict[str, Any] = {
        "stretch_method": h_method.value,
        "vmin": round(hist.vmin, 6),
        "vmax": round(hist.vmax, 6),
        "percentile_limits": [
            round(hist.effective_low_percentile, 4),
            round(hist.effective_high_percentile, 4),
        ],
        "mtf_parameters": {
            "midtone_balance": round(hist.effective_midtone_balance, 6),
        },
    }
    if h_method in (StretchMethod.ASINH_MTF, StretchMethod.ADAPTIVE_ASINH_MTF):
        hist_params["asinh_parameters"] = {
            "asinh_a": round(hist.effective_asinh_a, 6),
        }
    elif h_method == StretchMethod.GHS_MTF:
        hist_params["ghs_parameters"] = {
            "stretch_factor_d": round(hist.config_used.ghs_stretch_factor_d, 6),
            "local_intensity_b": round(hist.config_used.ghs_local_intensity_b, 6),
            "symmetry_point_sp": round(hist.config_used.ghs_symmetry_point_sp, 6),
        }

    histogram_stage: dict[str, Any] = {
        "stage_id": "STAGE_08_HISTOGRAM_TRANSFORMATION",
        "stage_name": "Histogram Transformation",
        "status": hist_rec.status.value if hist_rec else "COMPLETED",
        "started_at": hist_rec.started_at if hist_rec else now_iso,
        "completed_at": hist_rec.completed_at if hist_rec else now_iso,
        "duration_ms": round(hist_dur, 3),
        "duration_display": format_duration_seconds(hist_dur),
        "input": {
            "branch": "ENHANCED_DERIVED_FLOAT32" if enh.config_used.enabled else "SCIENTIFIC_LINEAR_RESULT",
            "data_type": "float32",
        },
        "parameters": hist_params,
        "output": {
            "branch": "DISPLAY_NORMALIZED_0_TO_1",
            "data_type": "float32",
            "range": [round(float(np.min(result.display_result)), 6), round(float(np.max(result.display_result)), 6)],
        },
        "metrics": {
            "median_before": round(hist.histogram_data.median_before, 6),
            "median_after": round(hist.histogram_data.median_after, 6),
            "valid_pixel_count": hist.valid_pixel_count,
        },
        "warnings": list(hist.warnings),
    }

    # 9. CURVE PROCESSING
    if curve_rec is not None:
        curve_stage = curve_rec
    else:
        curve_stage = {
            "stage_id": "STAGE_09_CURVE_PROCESSING",
            "stage_name": "Curve Processing",
            "status": "SKIPPED",
            "reason": "Curve adjustment was not used in this session.",
            "started_at": None,
            "completed_at": None,
            "duration_ms": None,
            "duration_display": None,
            "input": {"branch": "DISPLAY_NORMALIZED_0_TO_1"},
            "parameters": {},
            "output": None,
            "metrics": {},
            "warnings": [],
        }

    # 10. DISPLAY GENERATION
    disp_min = float(np.min(result.display_result)) if result.display_result.size > 0 else 0.0
    disp_max = float(np.max(result.display_result)) if result.display_result.size > 0 else 1.0
    if disp_rec is not None:
        display_stage = disp_rec
    else:
        display_stage = {
            "stage_id": "STAGE_10_DISPLAY_GENERATION",
            "stage_name": "Display Generation",
            "status": "COMPLETED",
            "started_at": hist_rec.completed_at if hist_rec else now_iso,
            "completed_at": hist_rec.completed_at if hist_rec else now_iso,
            "duration_ms": 0.0,
            "duration_display": "0.00 s",
            "input": {"branch": "DISPLAY_NORMALIZED_0_TO_1"},
            "parameters": {
                "display_mode": "FINAL_DISPLAY",
                "normalization": "[0.0, 1.0] float32 -> [0, 255] uint8 QImage",
            },
            "output": {
                "display_branch": "DISPLAY",
                "output_data_type": "float32",
                "output_range": [round(disp_min, 6), round(disp_max, 6)],
            },
            "metrics": {},
            "warnings": [],
        }

    # 11. OUTPUT PREPARATION
    output_prep_stage: dict[str, Any] = {
        "stage_id": "STAGE_11_OUTPUT_PREPARATION",
        "stage_name": "Output Preparation",
        "status": "COMPLETED",
        "started_at": now_iso,
        "completed_at": now_iso,
        "duration_ms": 0.0,
        "duration_display": "0.00 s",
        "input": {"selected_save_target": save_target},
        "parameters": {
            "target_format": output_format,
            "scientific_linear_preserved": True,
            "anti_overwrite_source_protection": True,
        },
        "output": {"target_branch": save_target, "dimensions": dims_str},
        "metrics": {},
        "warnings": [],
    }

    pipeline_dict: dict[str, Any] = {
        "input_loading": input_loading_stage,
        "input_validation": input_validation_stage,
        "flat_calibration": flat_calibration_stage,
        "master_flat_generation": master_flat_stage,
        "stacking": stacking_stage,
        "background_extraction": background_stage,
        "image_enhancement": enhancement_stage,
        "histogram_transformation": histogram_stage,
        "curve_processing": curve_stage,
        "display_generation": display_stage,
        "output_preparation": output_prep_stage,
    }

    # Hitung total waktu komputasi murni dari tahap-tahap yang dijalankan
    compute_sum_ms = 0.0
    for stg in (
        input_validation_stage,
        flat_calibration_stage,
        stacking_stage,
        background_stage,
        enhancement_stage,
        histogram_stage,
        curve_stage,
    ):
        d_val = stg.get("duration_ms")
        if isinstance(d_val, (int, float)) and d_val > 0:
            compute_sum_ms += float(d_val)

    return pipeline_dict, compute_sum_ms


def build_pipeline_history_dict(
    result: PipelineResult,
    *,
    save_target: str = "LINEAR",
    output_artifact: OutputArtifactRecord | None = None,
    save_transaction: SaveTransactionContext | None = None,
    companion_report_path: str | Path | None = None,
    timeline_tracker: WorkflowTimelineTracker | None = None,
    source_paths: Iterable[str | Path] = (),
) -> dict[str, Any]:
    """Menyusun laporan lengkap HILALONE Scientific Processing Report Schema v2.0
    sekaligus mempertahankan key kompatibilitas mundur v1.0."""
    logger = get_logger()
    tracker = timeline_tracker or logger.timeline_tracker

    now_dt = datetime.now().astimezone()
    _, generated_at_iso = format_timestamps(now_dt)
    generated_at_utc = format_utc_timestamp(now_dt)
    report_id = generate_report_id()
    all_runs = logger.session_manager.all_run_records()
    last_run_id = all_runs[-1].run_id if all_runs else None
    tx_run_id = (
        save_transaction.run_id
        if (save_transaction is not None and save_transaction.run_id and save_transaction.run_id.startswith("RUN-"))
        else None
    )
    run_id = tx_run_id or logger.active_run_id or last_run_id or generate_run_id()
    session_id = logger.session_id

    # Statistik 3 cabang data ilmiah (Bagian XIII)
    lin_arr = result.linear_result
    finite_lin = lin_arr[np.isfinite(lin_arr)]
    lin_min = float(np.min(finite_lin)) if finite_lin.size > 0 else 0.0
    lin_max = float(np.max(finite_lin)) if finite_lin.size > 0 else 0.0

    enh_arr = result.enhanced_result
    finite_enh = enh_arr[np.isfinite(enh_arr)]
    enh_min = float(np.min(finite_enh)) if finite_enh.size > 0 else 0.0
    enh_max = float(np.max(finite_enh)) if finite_enh.size > 0 else 0.0

    disp_arr = result.display_result
    disp_min = float(np.min(disp_arr)) if disp_arr.size > 0 else 0.0
    disp_max = float(np.max(disp_arr)) if disp_arr.size > 0 else 1.0

    data_branches: dict[str, Any] = {
        "linear_result": {
            "dtype": str(lin_arr.dtype),
            "shape": list(lin_arr.shape),
            "min": lin_min,
            "max": lin_max,
            "nature": "SCIENTIFIC_LINEAR_FLOAT32",
            "stage_origin": "BACKGROUND_EXTRACTION",
        },
        "enhanced_result": {
            "dtype": str(enh_arr.dtype),
            "shape": list(enh_arr.shape),
            "min": enh_min,
            "max": enh_max,
            "nature": "DERIVED_NONLINEAR_FLOAT32",
            "stage_origin": "IMAGE_ENHANCEMENT_CLAHE",
        },
        "display_result": {
            "dtype": str(disp_arr.dtype),
            "shape": list(disp_arr.shape),
            "min": disp_min,
            "max": disp_max,
            "nature": "DISPLAY_NORMALIZED_0_TO_1",
            "stage_origin": "HISTOGRAM_TRANSFORMATION",
        },
    }

    # 1. REPORT METADATA (Bagian IV)
    report_metadata: dict[str, Any] = {
        "report_name": REPORT_NAME,
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_id": report_id,
        "run_id": run_id,
        "generated_at": generated_at_iso,
        "generated_at_utc": generated_at_utc,
        "application": APP_NAME,
        "application_version": __version__,
    }

    # 2. SOURCE DATA TERDEDUPLIKASI (Bagian VI & XIV)
    source_data, deduplicated_source_names = build_source_data_section(
        result,
        timeline_tracker=tracker,
        source_paths=source_paths,
    )

    # 3. DETAILED PROCESSING PIPELINE (Bagian IX)
    out_fmt_str = output_artifact.format if output_artifact is not None else "FITS"
    processing_pipeline, compute_sum_ms = build_processing_pipeline_section(
        result,
        timeline_tracker=tracker,
        save_target=save_target,
        output_format=out_fmt_str,
    )

    # 4. TIMELINE & IDLE INTERVALS (Bagian VII, VIII, XI, XV)
    with tracker._lock:
        session_start_iso = tracker._session_start_timestamp
        session_end_iso = tracker._session_end_timestamp or generated_at_iso
        session_start_mono = tracker._session_start_mono
        session_end_mono = tracker._session_end_mono or time.perf_counter()
        events_list = [ev.to_dict() for ev in tracker._events]
        idle_list = [idl.to_dict() for idl in tracker._idle_intervals]
        in_load_ms = tracker._input_loading_duration_ms
        pipe_elapsed_ms = tracker._pipeline_elapsed_ms
        user_cfg = dict(tracker._user_config_snapshot)

    end_to_end_ms = max(0.0, (session_end_mono - session_start_mono) * 1000.0)
    if in_load_ms is None:
        in_load_ms = float(processing_pipeline["input_loading"]["duration_ms"] or 0.0)
    if pipe_elapsed_ms is None:
        pipe_elapsed_ms = compute_sum_ms

    workflow_idle_total_ms = sum(float(idl["duration_ms"]) for idl in idle_list)
    user_action_interval_total_ms = sum(
        float(ev["interval_since_previous_action_ms"])
        for ev in events_list
        if ev.get("interval_since_previous_action_ms") is not None
    )

    save_dialog_ms: float | None = None
    image_write_ms: float = 0.0
    save_tx_ms: float = 0.0
    if save_transaction is not None:
        save_dialog_ms = save_transaction.save_dialog_duration_ms
        image_write_ms = save_transaction.image_write_duration_ms
        save_tx_ms = save_transaction.save_transaction_duration_ms
    elif output_artifact is not None:
        image_write_ms = output_artifact.duration_ms
        save_tx_ms = output_artifact.duration_ms

    # 5. SESSION INFORMATION (Bagian V)
    os_str = f"{platform.system()} {platform.release()} ({platform.version()})"
    arch_str = platform.machine() or "x64"
    if not user_cfg:
        user_cfg = {
            "profile": result.profile.value,
            "flat_calibration_enabled": bool(result.flat_report and result.flat_report.applied),
            "background_method": result.background_result.effective_method.value,
            "enhancement_enabled": result.enhancement_result.config_used.enabled,
            "histogram_stretch_method": result.histogram_result.effective_method.value,
        }

    session_information: dict[str, Any] = {
        "session_id": session_id,
        "run_id": run_id,
        "application_version": __version__,
        "operating_system": os_str,
        "system_architecture": arch_str,
        "python_version": platform.python_version(),
        "processing_profile": result.profile.value,
        "input_mode": result.input_mode,
        "session_start_timestamp": session_start_iso,
        "session_end_timestamp": session_end_iso,
        "final_status": "SUCCESS",
        "report_generation_note": "This report was automatically generated after the output image was written and verified on disk.",
        "user_selected_configuration": user_cfg,
    }

    # 6. OUTPUT INFORMATION & SAVE TRANSACTION (Bagian X)
    artifacts_dicts = (
        [art.to_dict() for art in save_transaction.artifacts]
        if (save_transaction is not None and save_transaction.artifacts)
        else ([output_artifact.to_dict()] if output_artifact is not None else [])
    )
    comp_report_info: dict[str, Any] = {
        "report_id": report_id,
        "run_id": run_id,
        "report_filename": Path(companion_report_path).name if companion_report_path else None,
        "report_path": str(Path(companion_report_path).resolve()) if companion_report_path else None,
        "referenced_artifact_id": output_artifact.artifact_id if output_artifact is not None else None,
        "referenced_image_filename": output_artifact.filename if output_artifact is not None else None,
        "referenced_image_format": output_artifact.format if output_artifact is not None else None,
        "image_completed_at": output_artifact.completed_at if output_artifact is not None else None,
    }
    output_information: dict[str, Any] = {
        "transaction_id": save_transaction.transaction_id if save_transaction is not None else None,
        "run_id": run_id,
        "save_clicked_at": save_transaction.save_clicked_at if save_transaction is not None else None,
        "save_dialog_opened_at": save_transaction.save_dialog_opened_at if save_transaction is not None else None,
        "save_dialog_confirmed_at": save_transaction.save_dialog_confirmed_at if save_transaction is not None else None,
        "output_write_started_at": (
            save_transaction.output_write_started_at
            if save_transaction is not None
            else (output_artifact.started_at if output_artifact is not None else None)
        ),
        "output_write_completed_at": (
            save_transaction.output_write_completed_at
            if save_transaction is not None
            else (output_artifact.completed_at if output_artifact is not None else None)
        ),
        "save_dialog_duration_ms": round(save_dialog_ms, 3) if save_dialog_ms is not None else None,
        "save_dialog_duration_display": format_duration_seconds(save_dialog_ms) if save_dialog_ms is not None else None,
        "image_write_duration_ms": round(image_write_ms, 3),
        "image_write_duration_display": format_duration_seconds(image_write_ms),
        "save_transaction_duration_ms": round(save_tx_ms, 3),
        "save_transaction_duration_display": format_duration_seconds(save_tx_ms),
        "output_artifacts": artifacts_dicts,
        "companion_json_report": comp_report_info,
    }

    # 7. TIMING SUMMARY (Bagian XI & XII)
    timing_summary: dict[str, Any] = {
        "end_to_end_elapsed_ms": round(end_to_end_ms, 3),
        "end_to_end_elapsed_display": format_duration_seconds(end_to_end_ms),
        "input_loading_ms": round(float(in_load_ms), 3),
        "input_loading_display": format_duration_seconds(in_load_ms),
        "processing_compute_sum_ms": round(compute_sum_ms, 3),
        "processing_compute_sum_display": format_duration_seconds(compute_sum_ms),
        "automated_pipeline_elapsed_ms": round(float(pipe_elapsed_ms), 3),
        "automated_pipeline_elapsed_display": format_duration_seconds(pipe_elapsed_ms),
        "workflow_idle_total_ms": round(workflow_idle_total_ms, 3),
        "workflow_idle_total_display": format_duration_seconds(workflow_idle_total_ms),
        "user_action_interval_total_ms": round(user_action_interval_total_ms, 3),
        "user_action_interval_total_display": format_duration_seconds(user_action_interval_total_ms),
        "save_dialog_duration_ms": round(save_dialog_ms, 3) if save_dialog_ms is not None else None,
        "save_dialog_duration_display": format_duration_seconds(save_dialog_ms) if save_dialog_ms is not None else None,
        "image_write_duration_ms": round(image_write_ms, 3),
        "image_write_duration_display": format_duration_seconds(image_write_ms),
        "metric_definitions": {
            "end_to_end_elapsed_ms": "Total monotonic time from initial Open Image action until output image write completed.",
            "input_loading_ms": "Actual time spent reading and decoding source image/sequence files.",
            "processing_compute_sum_ms": "Sum of active backend computation durations across executed processing stages.",
            "automated_pipeline_elapsed_ms": "Wall/monotonic elapsed time from automated pipeline start to completion.",
            "workflow_idle_total_ms": "Accumulated intervals when no backend processing was active and application waited for next action.",
            "user_action_interval_total_ms": "Elapsed time between consecutive user actions (may overlap with loading/processing; not thinking time).",
            "save_dialog_duration_ms": "Time the file save dialog remained open waiting for filename confirmation.",
            "image_write_duration_ms": "Actual backend disk write and verification time for the output image.",
        },
    }

    # 8. HUMAN-READABLE TIMELINE & ALIGNED SUMMARY (Bagian XV & Addendum)
    human_timeline_lines = tracker.build_human_readable_timeline_lines()

    # Susun pula field-field kompatibilitas mundur v1.0 agar kode/tes lama tetap berjalan mulus
    if result.flat_report is not None and result.flat_report.applied:
        fr = result.flat_report
        flat_v1: dict[str, Any] = {
            "applied": True,
            "calibration_status": fr.calibration_status,
            "source_description": fr.source_description,
            "flat_format": fr.flat_format,
            "flat_dimensions": f"{fr.width}×{fr.height} px ({fr.channels} kanal)",
            "normalization_method": fr.normalization_method,
            "invalid_pixel_count": fr.invalid_pixel_count,
            "warnings": list(fr.warnings),
        }
    else:
        flat_v1 = {
            "applied": False,
            "calibration_status": "TIDAK DITERAPKAN (Opsi Flat Calibration tidak diaktifkan)",
        }

    stack_v1: dict[str, Any] | None = None
    if result.stacking_result is not None:
        sr = result.stacking_result
        stack_v1 = {
            "total_input_frames": sr.total_input_frames,
            "stacked_frame_count": sr.stacked_frame_count,
            "excluded_frame_count": len(sr.excluded_frames),
            "algorithm": sr.effective_algorithm.value,
            "profile": sr.profile_config.profile.value,
            "total_rejected_pixel_samples": sr.total_rejected_pixel_samples,
        }

    bg = result.background_result
    rs = bg.residual_stats
    bg_v1: dict[str, Any] = {
        "method": bg.effective_method.value,
        "grid_rows": bg.config_used.grid_rows,
        "grid_cols": bg.config_used.grid_cols,
        "rbf_smoothing": bg.effective_rbf_smoothing,
        "accepted_sample_count": bg.accepted_sample_count,
        "rejected_sample_count": bg.rejected_sample_count,
        "protected_pixel_count": bg.protected_pixel_count,
        "cfa_subchannel_modeled": bg.cfa_subchannel_modeled,
        "initial_gradient_ptp": rs.initial_gradient_ptp,
        "residual_gradient_ptp": rs.residual_gradient_ptp,
        "gradient_reduction_ratio": rs.gradient_reduction_ratio,
        "background_median_before": rs.background_median_before,
        "background_median_after": rs.background_median_after,
        "residual_rms": rs.residual_rms,
        "overcorrection_score": rs.overcorrection_score,
        "overcorrection_warning": rs.overcorrection_warning,
    }

    enh = result.enhancement_result
    enh_v1: dict[str, Any] = {
        "enabled": enh.config_used.enabled,
        "backend": enh.backend_used,
        "color_mode": enh.color_mode,
        "clip_limit": enh.effective_clip_limit,
        "kernel_tiles": list(enh.effective_kernel_tiles),
        "noise_amplification_ratio": enh.noise_amplification_ratio,
        "local_contrast_before": enh.local_contrast_before,
        "local_contrast_after": enh.local_contrast_after,
    }

    hist = result.histogram_result
    hist_v1: dict[str, Any] = {
        "method": hist.effective_method.value,
        "vmin": hist.vmin,
        "vmax": hist.vmax,
        "effective_low_percentile": hist.effective_low_percentile,
        "effective_high_percentile": hist.effective_high_percentile,
        "asinh_a": hist.effective_asinh_a,
        "midtone_balance": hist.effective_midtone_balance,
        "median_before": hist.histogram_data.median_before,
        "median_after": hist.histogram_data.median_after,
    }

    stages_v1 = [
        {
            "stage": rec.stage.value,
            "status": rec.status.value,
            "summary": rec.summary,
            "started_at": rec.started_at,
            "completed_at": rec.completed_at,
            "duration_ms": round(rec.duration_ms, 2),
            "duration_display": format_duration_seconds(rec.duration_ms),
            "input": rec.input_description,
            "output": rec.output_description,
            "warnings": list(rec.warnings),
        }
        for rec in result.stage_records
    ]

    scientific_notes = list(result.notes)
    if "Principle: Enhance the Signal, Never Invent the Signal." not in scientific_notes:
        scientific_notes.insert(0, "Principle: Enhance the Signal, Never Invent the Signal.")

    report_payload: dict[str, Any] = {
        "report_metadata": report_metadata,
        "session_information": session_information,
        "source_data": source_data,
        "user_interaction_timeline": events_list,
        "timeline_interpretation_note": (
            "Intervals between user actions (interval_since_previous_action_ms) represent elapsed time "
            "between actions and may include file loading, processing, or user inactivity; they do not "
            "measure psychological thinking time."
        ),
        "workflow_idle_intervals": idle_list,
        "processing_pipeline": processing_pipeline,
        "scientific_data_branches": data_branches,
        "output_information": output_information,
        "timing_summary": timing_summary,
        "human_readable_timeline": human_timeline_lines,
        "warnings": list(result.warnings),
        "scientific_notes": scientific_notes,
        # Field kompatibilitas mundur Schema v1.0
        "application": APP_NAME,
        "timestamp_utc": generated_at_utc,
        "profile": result.profile.value,
        "input_mode": result.input_mode,
        "position_stability_precheck": "DISABLED",
        "registration_alignment": "NOT_PERFORMED",
        "flat_compatibility_preflight": "DISABLED",
        "source_file_names": deduplicated_source_names,
        "is_cfa_mosaic": result.is_cfa_mosaic,
        "cfa_pattern": result.cfa_pattern_str,
        "data_branches": data_branches,
        "flat_calibration": flat_v1,
        "automatic_stacking": stack_v1,
        "background_extraction": bg_v1,
        "image_enhancement": enh_v1,
        "histogram_transformation": hist_v1,
        "stage_execution_history": stages_v1,
        "notes": scientific_notes,
    }

    report_payload["human_readable_summary"] = format_report_text_summary(report_payload).splitlines()
    return report_payload


def format_report_text_summary(report_data: dict[str, Any]) -> str:
    """Menghasilkan blok teks ringkasan tiga kolom sejajar dari dictionary JSON Report (v2.0 maupun v1.0)."""
    meta = report_data.get("report_metadata", {})
    sess = report_data.get("session_information", {})
    src = report_data.get("source_data", {})
    pipe = report_data.get("processing_pipeline", {})
    out_info = report_data.get("output_information", {})
    timing = report_data.get("timing_summary", {})

    run_id = sess.get("run_id") or meta.get("run_id") or "N/A"
    session_id = sess.get("session_id") or "N/A"
    status = sess.get("final_status") or "SUCCESS"
    profile = sess.get("processing_profile") or report_data.get("profile") or "BASIC"
    in_mode = sess.get("input_mode") or report_data.get("input_mode") or "SINGLE"

    session_items: list[tuple[str, Any]] = [
        ("Run ID", run_id),
        ("Session ID", session_id),
        ("Status", status),
        ("Profile", profile),
        ("Input mode", in_mode),
    ]
    if sess.get("session_start_timestamp"):
        session_items.append(("Session started", sess["session_start_timestamp"]))
    if sess.get("session_end_timestamp"):
        session_items.append(("Session completed", sess["session_end_timestamp"]))

    files_list = src.get("files", [])
    if files_list:
        first_fname = files_list[0].get("filename", "unknown")
        file_summary = first_fname if len(files_list) == 1 else f"{len(files_list)} files ({first_fname}, ...)"
    else:
        s_names = report_data.get("source_file_names", [])
        file_summary = ", ".join(s_names[:3]) if s_names else "In-memory array"

    total_frames = src.get("total_decoded_frames", 1)
    val_stg = pipe.get("input_validation", {})
    val_metrics = val_stg.get("metrics", {})
    compat_frames = val_metrics.get("valid_frames", total_frames)
    incompat_frames = val_metrics.get("incompatible_or_excluded_frames", 0)
    stk_stg = pipe.get("stacking", {})
    frames_proc = (
        stk_stg.get("output", {}).get("frames_integrated", compat_frames)
        if stk_stg.get("status") == "COMPLETED" and isinstance(stk_stg.get("output"), dict)
        else compat_frames
    )

    input_items: list[tuple[str, Any]] = [
        ("Input files", file_summary),
        ("Input frames", total_frames),
        ("Compatible frames", compat_frames),
        ("Incompatible frames", incompat_frames),
        ("Frames processed", frames_proc),
        ("Frames excluded", incompat_frames),
    ]

    def _stage_badge(stg_key: str, default_label: str = "SKIPPED") -> str:
        st = pipe.get(stg_key, {})
        st_status = st.get("status", default_label)
        params = st.get("parameters", {})
        if st_status == "COMPLETED":
            detail = (
                params.get("method")
                or params.get("stretch_method")
                or params.get("aggregation_method")
                or params.get("curve_method")
            )
            return f"COMPLETED ({detail})" if detail else "COMPLETED"
        return st_status

    curve_st = pipe.get("curve_processing", {}).get("status", "SKIPPED")
    curve_disp = "APPLIED" if curve_st == "COMPLETED" else "NOT USED"

    proc_items: list[tuple[str, Any]] = [
        ("Flat Calibration", "APPLIED" if pipe.get("flat_calibration", {}).get("status") == "COMPLETED" else "SKIPPED"),
        ("Master Flat", _stage_badge("master_flat_generation", "SKIPPED")),
        ("Image Stacking", _stage_badge("stacking", "SKIPPED")),
        ("Background Extraction", _stage_badge("background_extraction", "COMPLETED")),
        ("Image Enhancement", _stage_badge("image_enhancement", "COMPLETED")),
        ("Histogram Transformation", _stage_badge("histogram_transformation", "COMPLETED")),
        ("Curve Processing", curve_disp),
    ]

    artifacts = out_info.get("output_artifacts", [])
    if artifacts:
        art0 = artifacts[-1]
        output_items: list[tuple[str, Any]] = [
            ("Output filename", art0.get("filename", "N/A")),
            ("Output format", art0.get("format", "N/A")),
            ("Output location", art0.get("path", "N/A")),
            ("Data type", art0.get("data_type", "float32")),
            ("Save status", art0.get("save_status", "SAVED")),
        ]
    else:
        output_items = [
            ("Output", "In-memory (Ready to Save)"),
            ("Save status", "READY_TO_SAVE"),
        ]

    time_items: list[tuple[str, Any]] = [
        ("Input loading duration", timing.get("input_loading_display") or "0.00 s"),
        ("Processing duration", timing.get("processing_compute_sum_display") or "0.00 s"),
        ("Workflow idle duration", timing.get("workflow_idle_total_display") or "0.00 s"),
    ]
    if timing.get("save_dialog_duration_display") is not None:
        time_items.append(("Save dialog duration", timing["save_dialog_duration_display"]))
    time_items.extend([
        ("Image write duration", timing.get("image_write_duration_display") or "0.00 s"),
        ("Total end-to-end duration", timing.get("end_to_end_elapsed_display") or "0.00 s"),
    ])

    sections = [
        ("SESSION INFORMATION", session_items),
        ("INPUT INFORMATION", input_items),
        ("PROCESSING RESULTS", proc_items),
        ("OUTPUT INFORMATION", output_items),
        ("TIME SUMMARY", time_items),
    ]
    return format_aligned_summary(
        sections,
        title="PROCESSING SUMMARY",
        footer="AUTOMATED PROCESSING COMPLETED",
    )


def load_processing_report(source: str | Path | dict[str, Any]) -> dict[str, Any]:
    """Membaca berkas atau kamus JSON Processing Report (mendukung Schema v2.0 dan arsip Schema v1.0).

    Jika laporan berformat v1.0 (belum memiliki ``report_metadata``), fungsi ini
    menyediakan struktur ``report_metadata`` dengan ``schema_version = "1.0"``
    serta memetakan field lama ke struktur kompatibel tanpa merusak berkas asli.
    """
    if isinstance(source, (str, Path)):
        raw_text = Path(source).read_text(encoding="utf-8")
        data = json.loads(raw_text)
    elif isinstance(source, dict):
        data = dict(source)
    else:
        raise ValueError("Sumber laporan harus berupa Path berkas JSON atau dictionary.")

    if "report_metadata" in data and isinstance(data["report_metadata"], dict):
        return data

    # Adaptasi arsip Schema v1.0
    ts_utc = data.get("timestamp_utc", "1970-01-01T00:00:00Z")
    raw_sources = list(data.get("source_file_names", []))
    unique_sources = list(dict.fromkeys(raw_sources))
    data["report_metadata"] = {
        "report_name": REPORT_NAME,
        "schema_version": "1.0",
        "report_id": "LEGACY-V1-ARCHIVE",
        "run_id": "LEGACY-V1-RUN",
        "generated_at": ts_utc,
        "application": data.get("application", APP_NAME),
        "application_version": "1.0.0",
    }
    data.setdefault(
        "session_information",
        {
            "processing_profile": data.get("profile", "BASIC"),
            "input_mode": data.get("input_mode", "SINGLE"),
            "session_start_timestamp": ts_utc,
            "session_end_timestamp": ts_utc,
            "final_status": "SUCCESS",
        },
    )
    data.setdefault(
        "source_data",
        {
            "input_mode": data.get("input_mode", "SINGLE"),
            "file_count": len(unique_sources),
            "total_decoded_frames": max(1, len(raw_sources)),
            "files": [
                {
                    "source_id": f"SOURCE_{i:03d}",
                    "filename": fn,
                    "decoded_frame_count": raw_sources.count(fn),
                }
                for i, fn in enumerate(unique_sources, start=1)
            ],
        },
    )
    data.setdefault("scientific_data_branches", data.get("data_branches", {}))
    data.setdefault("scientific_notes", data.get("notes", []))
    return data


def populate_fits_header_for_pipeline(
    header: fits.Header,
    result: PipelineResult,
    *,
    is_enhanced_derived: bool = False,
) -> None:
    """Mengisi kartu header FITS dengan metadata terstruktur dan riwayat proses lengkap."""
    prof_val = result.profile.value
    header["HL_PROF"] = (prof_val, "HILALONE Processing Profile")
    header["HL_MODE"] = (result.input_mode, "HILALONE Input Mode")
    header["HL_ISDER"] = (
        bool(is_enhanced_derived),
        "True bila array adalah turunan nonlinear CLAHE",
    )
    header["HL_DTYPE"] = (
        "DERIVED_NONLINEAR_FLOAT32" if is_enhanced_derived else "SCIENTIFIC_LINEAR_FLOAT32",
        "Karakteristik data ilmiah",
    )
    header["HL_STAB"] = ("DISABLED", "Position stability precheck status")
    header["HL_ALIGN"] = ("NOT_PERFORMED", "Registration or alignment status")
    header["HL_FLPRE"] = ("DISABLED", "Flat compatibility preflight status")

    # Flat calibration
    flat_app = bool(result.flat_report and result.flat_report.applied)
    header["FLATCORR"] = (flat_app, "Apakah kalibrasi Flat diterapkan")
    if flat_app and result.flat_report is not None:
        header["FLATSRC"] = (result.flat_report.source_description[:68], "Sumber Master Flat")

    # Stacking
    if result.stacking_result is not None:
        sr = result.stacking_result
        header["NCOMBINE"] = (sr.stacked_frame_count, "Jumlah frame digabungkan")
        header["STACKALG"] = (sr.effective_algorithm.value, "Algoritma Stacking")

    # Background Extraction
    bg = result.background_result
    header["BG_METH"] = (bg.effective_method.value, "Metode Background Extraction")
    header["BG_SAMP"] = (bg.accepted_sample_count, "Jumlah sampel background diterima")
    header["BG_PROT"] = (bg.protected_pixel_count, "Jumlah piksel wilayah proteksi")
    header["BG_REDUC"] = (
        round(bg.residual_stats.gradient_reduction_ratio, 4),
        "Rasio reduksi gradien makro",
    )
    header["BG_OVERC"] = (
        bool(bg.residual_stats.overcorrection_warning),
        "Peringatan risiko overcorrection",
    )

    # Image Enhancement (CLAHE)
    enh = result.enhancement_result
    header["ENH_ENAB"] = (enh.config_used.enabled, "Apakah Image Enhancement aktif")
    header["ENH_CLIP"] = (round(enh.effective_clip_limit, 4), "CLAHE clip limit")
    header["ENH_TY"] = (enh.effective_kernel_tiles[0], "CLAHE kernel tiles Y")
    header["ENH_TX"] = (enh.effective_kernel_tiles[1], "CLAHE kernel tiles X")
    header["ENH_NAMP"] = (
        round(enh.noise_amplification_ratio, 2),
        "Rasio amplifikasi derau CLAHE",
    )

    # Histogram Transformation
    hist = result.histogram_result
    header["STR_METH"] = (hist.effective_method.value, "Metode Display Stretch")
    header["STR_VMIN"] = (float(f"{hist.vmin:.5g}"), "Batas bawah rentang tampilan (vmin)")
    header["STR_VMAX"] = (float(f"{hist.vmax:.5g}"), "Batas atas rentang tampilan (vmax)")
    header["STR_ASIN"] = (round(hist.effective_asinh_a, 4), "Parameter Asinh a")
    header["STR_MTFM"] = (round(hist.effective_midtone_balance, 4), "MTF midtone balance")

    # Catatan riwayat HISTORY
    header.add_history(f"HILALONE Automated Processing: Profile={prof_val}, Mode={result.input_mode}")
    header.add_history("Position stability precheck: DISABLED")
    header.add_history("Registration/alignment: NOT PERFORMED (MVP 1.0 rules)")
    header.add_history("Flat compatibility preflight: DISABLED")
    if flat_app and result.flat_report is not None:
        header.add_history(f"Flat Calibration DITERAPKAN: {result.flat_report.source_description}")
    else:
        header.add_history("Flat Calibration TIDAK DITERAPKAN")

    if result.stacking_result is not None:
        header.add_history(
            f"Stacking: {result.stacking_result.stacked_frame_count} frame digabungkan "
            f"({result.stacking_result.effective_algorithm.value})"
        )
    else:
        header.add_history("Stacking: DILEWATI (Mode Single Image)")

    header.add_history(
        f"Background Extraction: {bg.effective_method.value}, {bg.accepted_sample_count} sampel diterima, "
        f"{bg.protected_pixel_count} px dilindungi, grad_reduction={bg.residual_stats.gradient_reduction_ratio:.1%}"
    )

    if enh.config_used.enabled:
        header.add_history(
            f"CLAHE Enhancement: clip_limit={enh.effective_clip_limit}, "
            f"tiles={enh.effective_kernel_tiles[0]}x{enh.effective_kernel_tiles[1]}, "
            f"noise_amp={enh.noise_amplification_ratio:.2f}x"
        )
    else:
        header.add_history("CLAHE Enhancement: NONAKTIF")

    header.add_history(
        f"Display Stretch: {hist.effective_method.value}, vmin={hist.vmin:.4g}, vmax={hist.vmax:.4g}, "
        f"asinh_a={hist.effective_asinh_a:.4g}, mtf_m={hist.effective_midtone_balance:.4g}"
    )

    for w in result.warnings[:10]:
        w_safe = str(w).encode("ascii", "replace").decode("ascii")
        header.add_history(f"Warning: {w_safe}")
