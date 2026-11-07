"""Penulis hasil Automatic Stacking Engine HILALONE (Sub-Tahap 3A GUI Integration).

Aturan Data (AGENTS.md Bagian 5 & FR-OUT-01..05):
  1. Berkas sumber TIDAK PERNAH diubah atau ditimpa. Menulis ke jalur berkas
     yang sama dengan salah satu berkas sumber akan ditolak dengan
     ``OutputWriteError`` berbahasa Indonesia.
  2. Hasil ilmiah linear (``stacked_scientific_data`` bertipe ``float32``)
     disimpan utuh tanpa clipping nilai negatif ke dalam format ilmiah
     FITS (``.fits``/``.fit``) atau TIFF 32-bit float (``.tif``/``.tiff``).
  3. Apabila pengguna memilih ekstensi visual ``.png``, yang disimpan adalah
     pratinjau visual 8-bit terpisah, disertai laporan JSON riwayat proses.
  4. Seluruh parameter proses, daftar frame yang digabungkan, daftar frame yang
     dikecualikan, metrik kualitas, dan status Master Flat dicatat pada header
     FITS (``HISTORY``) serta berkas laporan JSON pendamping.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable

from astropy.io import fits
import numpy as np
import tifffile

from hilalone.processing.stacking.models import StackingResult


class OutputWriteError(Exception):
    """Galat saat menyimpan hasil pemrosesan; pesan berbahasa Indonesia."""


def build_stacking_history_dict(result: StackingResult) -> dict[str, object]:
    """Menyusun kamus metadata riwayat proses stacking secara lengkap dan jujur."""
    stab = result.validation_report.stability_report
    stability_summary: dict[str, object] | None = None
    if stab is not None:
        stability_summary = {
            "reference_frame_index": stab.reference_frame_index,
            "threshold_px": stab.threshold_px,
            "max_shift_px": stab.max_shift_px,
            "mean_shift_px": stab.mean_shift_px,
            "ok_count": stab.ok_count,
            "exceeded_count": stab.exceeded_count,
            "indeterminate_count": stab.indeterminate_count,
            "measurements": [
                {
                    "frame_index": m.frame_index,
                    "file_name": m.file_name,
                    "dx_px": m.dx_px,
                    "dy_px": m.dy_px,
                    "shift_magnitude_px": m.shift_magnitude_px,
                    "confidence_psr": round(m.confidence_psr, 3),
                    "status": m.status.value,
                    "note": m.note,
                }
                for m in stab.measurements
            ],
        }

    if result.flat_report is not None and result.flat_report.applied:
        fr = result.flat_report
        flat_summary: dict[str, object] = {
            "applied": True,
            "calibration_status": fr.calibration_status,
            "source_description": fr.source_description,
            "flat_format": fr.flat_format,
            "flat_input_type": fr.flat_input_type,
            "flat_frame_count": fr.flat_frame_count,
            "flat_dimensions": f"{fr.width}×{fr.height} px ({fr.channels} kanal)",
            "normalization_method": fr.normalization_method,
            "flat_median_before_norm": fr.flat_median_before_norm,
            "flat_mean_before_norm": fr.flat_mean_before_norm,
            "invalid_pixel_count": fr.invalid_pixel_count,
            "zero_or_negative_pixel_count": fr.zero_or_negative_pixel_count,
            "non_finite_pixel_count": fr.non_finite_pixel_count,
            "saturated_pixel_count": fr.saturated_pixel_count,
            "protected_zero_pixels_count": fr.protected_zero_pixels_count,
            "warnings": list(fr.warnings),
        }
    else:
        reason = (
            result.flat_report.not_applied_reason
            if (result.flat_report is not None and result.flat_report.not_applied_reason)
            else "Opsi Apply Flat Calibration tidak diaktifkan oleh pengguna."
        )
        flat_summary = {
            "applied": False,
            "calibration_status": f"TIDAK DITERAPKAN ({reason})",
            "not_applied_reason": reason,
        }

    arr = result.stacked_scientific_data
    return {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "profile": result.profile_config.profile.value,
        "effective_algorithm": result.effective_algorithm.value,
        "algorithm_description": result.profile_config.description_id,
        "output_dtype": str(arr.dtype),
        "output_shape": list(arr.shape),
        "min_value": float(np.min(arr)),
        "max_value": float(np.max(arr)),
        "total_input_frames": result.total_input_frames,
        "stacked_frame_count": result.stacked_frame_count,
        "included_frame_indices": list(result.included_frame_indices),
        "included_file_names": list(result.included_file_names),
        "excluded_frames": [
            {
                "frame_index": ex.frame_index,
                "file_name": ex.file_name,
                "reason": ex.reason,
            }
            for ex in result.excluded_frames
        ],
        "total_rejected_pixel_samples": result.total_rejected_pixel_samples,
        "flat_calibration": flat_summary,
        "position_stability": stability_summary,
        "warnings": list(result.warnings),
        "notes": list(result.notes),
    }


def save_stacking_result(
    result: StackingResult,
    output_path: str | Path,
    *,
    source_paths: Iterable[str | Path] = (),
    write_json_report: bool = True,
) -> tuple[Path, Path | None]:
    """Menyimpan hasil stacking ke berkas tujuan tanpa pernah menimpa berkas sumber.

    Format yang didukung:
      * ``.fits`` / ``.fit`` : Menyimpan ``stacked_scientific_data`` (``float32`` linear)
                               beserta kartu header ``HISTORY`` lengkap.
      * ``.tif`` / ``.tiff`` : Menyimpan ``stacked_scientific_data`` (``float32`` linear).
      * ``.png``             : Menyimpan pratinjau visual 8-bit terpisah.

    Returns:
        Tuple ``(saved_image_path, saved_json_report_path)``.
    """
    target = Path(output_path)
    if not target.suffix:
        target = target.with_suffix(".fits")

    ext = target.suffix.lower().lstrip(".")
    if ext not in ("fits", "fit", "fts", "tif", "tiff", "png"):
        raise OutputWriteError(
            f"Format penyimpanan '.{ext}' tidak didukung. Gunakan .FITS, .TIFF (linear float32), atau .PNG (visual)."
        )

    try:
        resolved_target = target.resolve()
    except OSError as exc:
        raise OutputWriteError(f"Jalur penyimpanan tidak valid: {exc}") from exc

    resolved_sources: set[Path] = set()
    for sp in source_paths:
        try:
            resolved_sources.add(Path(sp).resolve())
        except OSError:
            pass

    if resolved_target in resolved_sources:
        raise OutputWriteError(
            f"Dilarang menimpa berkas sumber asli ('{target.name}'). "
            "Silakan pilih nama berkas atau folder output yang berbeda."
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    history_dict = build_stacking_history_dict(result)
    sci_f32 = np.asarray(result.stacked_scientific_data, dtype=np.float32)

    try:
        if ext in ("fits", "fit", "fts"):
            # Untuk citra RGB 3D (H, W, 3), konvensi FITS menyimpan (3, H, W) atau (H, W, 3);
            # kita simpan array float32 beserta header riwayat lengkap
            hdu = fits.PrimaryHDU(data=sci_f32)
            hdr = hdu.header
            hdr["STACKPRF"] = (result.profile_config.profile.value, "HILALONE Stacking Profile")
            hdr["STACKALG"] = (result.effective_algorithm.value, "HILALONE Stacking Algorithm")
            hdr["NCOMBINE"] = (result.stacked_frame_count, "Jumlah frame yang digabungkan")
            hdr["NTOTAL"] = (result.total_input_frames, "Jumlah total frame di dalam sequence")
            hdr["NEXCLUDE"] = (len(result.excluded_frames), "Jumlah frame yang dikecualikan")
            hdr["FLATCORR"] = (
                bool(result.flat_report and result.flat_report.applied),
                "Apakah kalibrasi Master Flat diterapkan",
            )
            if result.flat_report is not None and result.flat_report.applied:
                fr = result.flat_report
                hdr["FLATSRC"] = (fr.source_description[:68], "Master Flat source")
                hdr["FLATFMT"] = (fr.flat_format[:68], "Master Flat format")
                hdr["FLATINV"] = (fr.invalid_pixel_count, "Jumlah invalid pixels pada Master Flat")
                hdr.add_history(
                    f"Flat Calibration DITERAPKAN: src={fr.source_description}, "
                    f"fmt={fr.flat_format}, dim={fr.width}x{fr.height}, "
                    f"norm={fr.normalization_method}, invalid_px={fr.invalid_pixel_count}"
                )
            elif result.flat_report is not None:
                hdr.add_history(
                    f"Flat Calibration TIDAK DITERAPKAN: {result.flat_report.not_applied_reason or 'Tidak diaktifkan.'}"
                )
            else:
                hdr.add_history(
                    "Flat Calibration TIDAK DITERAPKAN: Opsi Apply Flat Calibration tidak diaktifkan."
                )
            hdr.add_history(
                f"HILALONE Automatic Stacking: profile={result.profile_config.profile.value}, "
                f"algo={result.effective_algorithm.value}, frames={result.stacked_frame_count}/{result.total_input_frames}"
            )
            for fname in result.included_file_names[:20]:
                hdr.add_history(f"Included frame: {fname}")
            for ex in result.excluded_frames[:20]:
                hdr.add_history(f"Excluded frame #{ex.frame_index + 1} ({ex.file_name}): {ex.reason}")
            hdu.writeto(target, overwrite=True)

        elif ext in ("tif", "tiff"):
            tifffile.imwrite(
                str(target),
                sci_f32,
                description=json.dumps(history_dict, ensure_ascii=True),
            )

        elif ext == "png":
            ok = result.preview.save(str(target), "PNG")
            if not ok:
                raise OutputWriteError(f"Gagal menyimpan pratinjau PNG ke '{target}'.")

    except OutputWriteError:
        raise
    except Exception as exc:
        raise OutputWriteError(f"Gagal menyimpan hasil stacking ke '{target.name}': {exc}") from exc

    json_path: Path | None = None
    if write_json_report:
        candidate_json = target.with_name(f"{target.stem}_stacking_report.json")
        if candidate_json.resolve() not in resolved_sources:
            try:
                candidate_json.write_text(
                    json.dumps(history_dict, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                json_path = candidate_json
            except OSError:
                json_path = None

    return target, json_path
