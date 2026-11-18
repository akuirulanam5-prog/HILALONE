"""Penulis berkas hasil pemrosesan otomatis HILALONE (FITS, TIFF, PNG, dan Laporan JSON Schema v2.0).

Aturan Data & Kejujuran Ilmiah (AGENTS.md Bagian 5 & FR-OUT-01..05):
  1. Berkas sumber TIDAK PERNAH diubah atau ditimpa. Menulis ke jalur berkas
     yang sama dengan berkas sumber ditolak dengan ``OutputWriteError``.
  2. Hasil ilmiah linear (``linear_result``, ``float32``) disimpan utuh tanpa
     clipping nilai negatif ke FITS atau TIFF float32.
  3. Hasil turunan nonlinear (``enhanced_result``, ``float32``) diberi penanda
     eksplisit pada kartu header (``HL_ISDER=True``) dan deskripsi berkas bahwa
     citra telah mengalami transformasi nonlinear CLAHE.
  4. Ekspor pratinjau visual PNG (uint8) setelah peregangan histogram tidak
     boleh diklaim sebagai master ilmiah.
  5. Setiap penyimpanan membuat Save Transaction yang mengukur waktu penulisan
     citra aktual, memverifikasi berkas di disk, lalu menulis berkas laporan
     pendamping JSON Schema v2.0 (``*_processing_report.json``). Jika penulisan
     JSON gagal setelah foto tersimpan, foto hasil TIDAK dihapus dan sistem
     mencatat peringatan eksplisit.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from astropy.io import fits
import numpy as np
import tifffile

from hilalone.core.logging.log_event import LogModule
from hilalone.core.logging.logger import get_logger
from hilalone.core.logging.workflow_timeline import WorkflowTimelineTracker
from hilalone.output_manager.stacking_writer import OutputWriteError
from hilalone.processing.processing_history import (
    build_pipeline_history_dict,
    populate_fits_header_for_pipeline,
)
from hilalone.processing.processing_models import PipelineResult


def _resolve_non_conflicting_report_path(
    target_image_path: Path,
    resolved_sources: set[Path],
) -> Path:
    """Menentukan path berkas laporan JSON pendamping yang terkait dengan nama foto."""
    base_candidate = target_image_path.with_name(f"{target_image_path.stem}_processing_report.json")
    try:
        if base_candidate.resolve() not in resolved_sources:
            return base_candidate
    except OSError:
        pass
    return target_image_path.with_name(f"{target_image_path.stem}_hilalone_report_v2.json")


def save_pipeline_result(
    result: PipelineResult,
    output_path: str | Path,
    *,
    save_target: str = "LINEAR",  # "LINEAR", "ENHANCED", atau "DISPLAY"
    source_paths: Iterable[str | Path] = (),
    write_json_report: bool = True,
    timeline_tracker: WorkflowTimelineTracker | None = None,
) -> tuple[Path, Path | None]:
    """Menyimpan produk pemrosesan pipeline HILALONE ke disk beserta JSON Report Schema v2.0.

    Args:
        result: Objek ``PipelineResult`` lengkap.
        output_path: Jalur berkas tujuan.
        save_target: Cabang data yang ingin disimpan:
                     * ``"LINEAR"``   : Scientific Linear Master (FITS/TIFF float32).
                     * ``"ENHANCED"`` : Derived Nonlinear Image (FITS/TIFF float32, ditandai nonlinear).
                     * ``"DISPLAY"``  : Display Preview (PNG 8-bit).
        source_paths: Daftar seluruh berkas masukan asli untuk proteksi anti-overwrite.
        write_json_report: Apakah menulis berkas pendamping ``*_processing_report.json``.
        timeline_tracker: Pelacak timeline opsional (default: ``get_logger().timeline_tracker``).

    Returns:
        Tuple ``(saved_image_path, saved_json_report_path)``.
    """
    logger = get_logger()
    tracker = timeline_tracker or logger.timeline_tracker

    target = Path(output_path)
    if not target.suffix:
        if save_target == "DISPLAY":
            target = target.with_suffix(".png")
        else:
            target = target.with_suffix(".fits")

    ext = target.suffix.lower().lstrip(".")
    if ext not in ("fits", "fit", "fts", "tif", "tiff", "png"):
        raise OutputWriteError(
            f"Format penyimpanan '.{ext}' tidak didukung. Gunakan .FITS, .TIFF (float32), atau .PNG (visual)."
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
            "Silakan pilih nama berkas atau folder penyimpanan yang berbeda."
        )

    target.parent.mkdir(parents=True, exist_ok=True)

    # Tentukan array dan karakteristik format yang akan disimpan
    is_enhanced = save_target == "ENHANCED"
    if save_target == "ENHANCED":
        work_arr = np.asarray(result.enhanced_result, dtype=np.float32)
    elif save_target == "DISPLAY":
        work_arr = np.asarray(result.display_result, dtype=np.float32)
    else:
        work_arr = np.asarray(result.linear_result, dtype=np.float32)

    h, w = int(work_arr.shape[0]), int(work_arr.shape[1])
    ch = int(work_arr.shape[2]) if work_arr.ndim == 3 else 1

    if ext in ("fits", "fit", "fts"):
        fmt_label = "FITS"
        dtype_label = "float32"
        bit_depth = 32
    elif ext in ("tif", "tiff"):
        fmt_label = "TIFF"
        dtype_label = "float32"
        bit_depth = 32
    else:
        fmt_label = "PNG"
        dtype_label = "uint8"
        bit_depth = 8

    # 1. Catat mulainya penulisan berkas gambar ke disk pada Save Transaction
    run_id = logger.active_run_id or logger.current_run_id
    tracker.mark_output_write_started(str(resolved_target), run_id=run_id)

    try:
        if ext in ("fits", "fit", "fts"):
            hdu = fits.PrimaryHDU(data=work_arr)
            populate_fits_header_for_pipeline(hdu.header, result, is_enhanced_derived=is_enhanced)
            hdu.writeto(target, overwrite=True)

        elif ext in ("tif", "tiff"):
            tiff_meta = {
                "HILALONE_TYPE": "DERIVED_NONLINEAR_FLOAT32" if is_enhanced else "SCIENTIFIC_LINEAR_FLOAT32",
                "PROFILE": result.profile.value,
                "INPUT_MODE": result.input_mode,
                "RUN_ID": run_id,
            }
            tifffile.imwrite(
                str(target),
                work_arr,
                description=json.dumps(tiff_meta, ensure_ascii=True),
            )

        elif ext == "png":
            qimg = result.previews.get(
                result.previews.__class__.FINAL_DISPLAY
                if hasattr(result.previews, "FINAL_DISPLAY")
                else list(result.previews.keys())[-1]
            )
            if qimg is None or qimg.isNull():
                disp_u8 = np.clip(np.rint(result.display_result * 255.0), 0, 255).astype(np.uint8)
                from PySide6.QtGui import QImage

                if disp_u8.ndim == 2:
                    qimg = QImage(
                        disp_u8.data,
                        disp_u8.shape[1],
                        disp_u8.shape[0],
                        disp_u8.shape[1],
                        QImage.Format.Format_Grayscale8,
                    ).copy()
                else:
                    qimg = QImage(
                        disp_u8.data,
                        disp_u8.shape[1],
                        disp_u8.shape[0],
                        3 * disp_u8.shape[1],
                        QImage.Format.Format_RGB888,
                    ).copy()

            ok = qimg.save(str(target), "PNG")
            if not ok:
                raise OutputWriteError(f"Gagal mengekspor pratinjau PNG ke '{target}'.")

    except OutputWriteError as err:
        tracker.record_operation_failed("OUTPUT_WRITE_FAILED", module="OUTPUT", reason=str(err))
        tracker.finalize_save_transaction()
        raise
    except Exception as exc:
        tracker.record_operation_failed("OUTPUT_WRITE_FAILED", module="OUTPUT", reason=str(exc))
        tracker.finalize_save_transaction()
        raise OutputWriteError(f"Gagal menyimpan hasil pemrosesan ke '{target.name}': {exc}") from exc

    # 2. Verifikasi berkas gambar di disk dan catat selesainya penulisan gambar
    verified_exists = target.exists() and target.is_file()
    file_size_bytes = target.stat().st_size if verified_exists else 0
    verified_ok = verified_exists and file_size_bytes > 0

    save_tx, out_artifact = tracker.mark_output_write_completed(
        filename=target.name,
        fmt=fmt_label,
        save_target=save_target,
        data_type=dtype_label,
        bit_depth=bit_depth,
        width=w,
        height=h,
        channels=ch,
        path=str(resolved_target),
        file_size_bytes=file_size_bytes,
        verified_on_disk=verified_ok,
    )

    # 3. Buat berkas JSON Report Schema v2.0 setelah foto hasil selesai ditulis dengan sukses
    json_path: Path | None = None
    if write_json_report:
        candidate_json = _resolve_non_conflicting_report_path(target, resolved_sources)
        try:
            report_dict = build_pipeline_history_dict(
                result,
                save_target=save_target,
                output_artifact=out_artifact,
                save_transaction=save_tx,
                companion_report_path=candidate_json,
                timeline_tracker=tracker,
                source_paths=source_paths,
            )
            candidate_json.write_text(
                json.dumps(report_dict, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            json_path = candidate_json
        except Exception as exc:
            # Aturan Bagian X.B: Jangan menghapus foto yang sudah berhasil disimpan!
            json_path = None
            logger.warning(
                LogModule.OUTPUT,
                f"Output image '{target.name}' saved successfully, but companion JSON report could not be written: {exc}",
                details={
                    "image_path": str(resolved_target),
                    "report_candidate": str(candidate_json),
                    "reason": str(exc),
                },
            )

    tracker.finalize_save_transaction()
    return target, json_path
