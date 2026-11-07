"""Penulis berkas hasil pemrosesan otomatis HILALONE (FITS, TIFF, PNG, dan Laporan JSON).

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
  5. Setiap penyimpanan disertai berkas laporan JSON (*_processing_report.json).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from astropy.io import fits
import numpy as np
import tifffile

from hilalone.output_manager.stacking_writer import OutputWriteError
from hilalone.processing.processing_history import (
    build_pipeline_history_dict,
    populate_fits_header_for_pipeline,
)
from hilalone.processing.processing_models import PipelineResult


def save_pipeline_result(
    result: PipelineResult,
    output_path: str | Path,
    *,
    save_target: str = "LINEAR",  # "LINEAR", "ENHANCED", atau "DISPLAY"
    source_paths: Iterable[str | Path] = (),
    write_json_report: bool = True,
) -> tuple[Path, Path | None]:
    """Menyimpan produk pemrosesan pipeline HILALONE ke disk tanpa pernah menimpa berkas sumber.

    Args:
        result: Objek ``PipelineResult`` lengkap.
        output_path: Jalur berkas tujuan.
        save_target: Cabang data yang ingin disimpan:
                     * ``"LINEAR"``   : Scientific Linear Master (FITS/TIFF float32).
                     * ``"ENHANCED"`` : Derived Nonlinear Image (FITS/TIFF float32, ditandai nonlinear).
                     * ``"DISPLAY"``  : Display Preview (PNG 8-bit).
        source_paths: Daftar seluruh berkas masukan asli untuk proteksi anti-overwrite.
        write_json_report: Apakah menulis berkas pendamping ``*_processing_report.json``.

    Returns:
        Tuple ``(saved_image_path, saved_json_report_path)``.
    """
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
    history_dict = build_pipeline_history_dict(result)

    # Tentukan array yang akan disimpan
    is_enhanced = (save_target == "ENHANCED")
    if save_target == "ENHANCED":
        work_arr = np.asarray(result.enhanced_result, dtype=np.float32)
    elif save_target == "DISPLAY":
        work_arr = np.asarray(result.display_result, dtype=np.float32)
    else:
        work_arr = np.asarray(result.linear_result, dtype=np.float32)

    try:
        if ext in ("fits", "fit", "fts"):
            hdu = fits.PrimaryHDU(data=work_arr)
            populate_fits_header_for_pipeline(hdu.header, result, is_enhanced_derived=is_enhanced)
            hdu.writeto(target, overwrite=True)

        elif ext in ("tif", "tiff"):
            desc_meta = {
                "HILALONE_TYPE": "DERIVED_NONLINEAR_FLOAT32" if is_enhanced else "SCIENTIFIC_LINEAR_FLOAT32",
                "HISTORY": history_dict,
            }
            tifffile.imwrite(
                str(target),
                work_arr,
                description=json.dumps(desc_meta, ensure_ascii=True),
            )

        elif ext == "png":
            # Simpan QImage tampilan
            qimg = result.previews.get(result.previews.__class__.FINAL_DISPLAY if hasattr(result.previews, "FINAL_DISPLAY") else list(result.previews.keys())[-1])
            if qimg is None or qimg.isNull():
                disp_u8 = np.clip(np.rint(result.display_result * 255.0), 0, 255).astype(np.uint8)
                if disp_u8.ndim == 2:
                    from PySide6.QtGui import QImage
                    qimg = QImage(disp_u8.data, disp_u8.shape[1], disp_u8.shape[0], disp_u8.shape[1], QImage.Format.Format_Grayscale8).copy()
                else:
                    from PySide6.QtGui import QImage
                    qimg = QImage(disp_u8.data, disp_u8.shape[1], disp_u8.shape[0], 3 * disp_u8.shape[1], QImage.Format.Format_RGB888).copy()

            ok = qimg.save(str(target), "PNG")
            if not ok:
                raise OutputWriteError(f"Gagal mengekspor pratinjau PNG ke '{target}'.")

    except OutputWriteError:
        raise
    except Exception as exc:
        raise OutputWriteError(f"Gagal menyimpan hasil pemrosesan ke '{target.name}': {exc}") from exc

    json_path: Path | None = None
    if write_json_report:
        candidate_json = target.with_name(f"{target.stem}_processing_report.json")
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
