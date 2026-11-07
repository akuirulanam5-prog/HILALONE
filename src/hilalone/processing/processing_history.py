"""Pengelolaan riwayat pemrosesan dan metadata ilmiah untuk Full Automated Processing Pipeline.

Mencatat secara terperinci setiap keputusan algoritma, parameter, metrik residual,
amplifikasi derau, rentang persentil, dan status setiap tahap pemrosesan untuk:
  1. Header ilmiah FITS (HISTORY dan kartu HIERARCH terstruktur).
  2. Berkas laporan pendamping JSON (*_processing_report.json).
  3. Tampilan kartu ringkasan riwayat di antarmuka grafis (GUI).
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from astropy.io import fits
import numpy as np

from hilalone.processing.processing_models import (
    PipelineResult,
    PipelineStage,
    StageStatus,
)


def build_pipeline_history_dict(result: PipelineResult) -> dict[str, Any]:
    """Menyusun representasi kamus komprehensif riwayat pemrosesan pipeline HILALONE."""
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

    # Flat calibration summary
    flat_summary: dict[str, Any]
    if result.flat_report is not None and result.flat_report.applied:
        fr = result.flat_report
        flat_summary = {
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
        flat_summary = {
            "applied": False,
            "calibration_status": "TIDAK DITERAPKAN (Opsi Flat Calibration tidak diaktifkan)",
        }

    # Stacking summary (jika multi-frame)
    stack_summary: dict[str, Any] | None = None
    if result.stacking_result is not None:
        sr = result.stacking_result
        stack_summary = {
            "total_input_frames": sr.total_input_frames,
            "stacked_frame_count": sr.stacked_frame_count,
            "excluded_frame_count": len(sr.excluded_frames),
            "algorithm": sr.effective_algorithm.value,
            "profile": sr.profile_config.profile.value,
            "total_rejected_pixel_samples": sr.total_rejected_pixel_samples,
        }

    # Engine 1 summary
    bg = result.background_result
    rs = bg.residual_stats
    bg_summary: dict[str, Any] = {
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

    # Engine 2 summary
    enh = result.enhancement_result
    enh_summary: dict[str, Any] = {
        "enabled": enh.config_used.enabled,
        "backend": enh.backend_used,
        "color_mode": enh.color_mode,
        "clip_limit": enh.effective_clip_limit,
        "kernel_tiles": list(enh.effective_kernel_tiles),
        "noise_amplification_ratio": enh.noise_amplification_ratio,
        "local_contrast_before": enh.local_contrast_before,
        "local_contrast_after": enh.local_contrast_after,
    }

    # Engine 3 summary
    hist = result.histogram_result
    hist_summary: dict[str, Any] = {
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

    stages_list = [
        {
            "stage": rec.stage.value,
            "status": rec.status.value,
            "summary": rec.summary,
            "duration_ms": round(rec.duration_ms, 2),
            "input": rec.input_description,
            "output": rec.output_description,
            "warnings": list(rec.warnings),
        }
        for rec in result.stage_records
    ]

    return {
        "application": "HILALONE",
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "profile": result.profile.value,
        "input_mode": result.input_mode,
        "position_stability_precheck": "DISABLED",
        "registration_alignment": "NOT_PERFORMED",
        "flat_compatibility_preflight": "DISABLED",
        "source_file_names": list(result.source_file_names),
        "is_cfa_mosaic": result.is_cfa_mosaic,
        "cfa_pattern": result.cfa_pattern_str,
        "data_branches": {
            "linear_result": {
                "dtype": str(lin_arr.dtype),
                "shape": list(lin_arr.shape),
                "min": lin_min,
                "max": lin_max,
                "nature": "SCIENTIFIC_LINEAR_FLOAT32",
            },
            "enhanced_result": {
                "dtype": str(enh_arr.dtype),
                "shape": list(enh_arr.shape),
                "min": enh_min,
                "max": enh_max,
                "nature": "DERIVED_NONLINEAR_FLOAT32",
            },
            "display_result": {
                "dtype": str(disp_arr.dtype),
                "shape": list(disp_arr.shape),
                "min": disp_min,
                "max": disp_max,
                "nature": "DISPLAY_NORMALIZED_0_TO_1",
            },
        },
        "flat_calibration": flat_summary,
        "automatic_stacking": stack_summary,
        "background_extraction": bg_summary,
        "image_enhancement": enh_summary,
        "histogram_transformation": hist_summary,
        "stage_execution_history": stages_list,
        "warnings": list(result.warnings),
        "notes": list(result.notes),
    }


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
