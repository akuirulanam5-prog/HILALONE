"""Kalibrasi Master Flat-Field Opsional untuk HILALONE (Sub-Tahap 3A).

Aturan ilmiah (AGENTS.md Bagian 4 & FR-FL-01..03):
  1. Kalibrasi flat-field bersifat **murni opsional** dan hanya dijalankan bila
     pengguna secara eksplisit menyediakan Master Flat.
  2. **Tidak ada** kalibrasi dark maupun bias.
  3. Dimensi dan jumlah kanal Master Flat wajib identik dengan frame sequence.
     Apabila sequence berupa mosaik CFA (RAW/SER Bayer), pola CFA Master Flat
     juga harus cocok.
  4. Master Flat dinormalisasi sehingga nilai rata-ratanya menjadi ``1.0``
     (dihitung per-kanal pada RGB atau per-subkanal 2×2 pada Bayer CFA agar
     tidak mengubah keseimbangan warna asli).
  5. Piksel Master Flat yang bernilai ``<= 0`` atau sangat mendekati nol
     (``<= 1e-4``) dilindungi dengan nilai netral ``1.0`` agar tidak memicu
     pembagian nol (``NaN``/``Inf``), dan jumlah piksel yang dilindungi dicatat
     pada ``FlatCalibrationReport``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from hilalone.input_manager.image_reader import ImageInfo, ImageReadError, read_image
from hilalone.processing.stacking.models import FlatCalibrationReport, StackingError

FLAT_ZERO_THRESHOLD = 1e-4


def _extract_cfa_info(info: ImageInfo | None) -> tuple[bool, str | None]:
    if info is None:
        return False, None
    if info.raw_metadata is not None and info.raw_metadata.is_cfa_mosaic:
        return True, info.raw_metadata.cfa_pattern_str
    if info.ser_metadata is not None and info.ser_metadata.is_cfa_mosaic:
        return True, info.ser_metadata.cfa_pattern_str
    return False, None


def validate_and_prepare_master_flat(
    master_flat: np.ndarray | str | Path,
    *,
    expected_height: int,
    expected_width: int,
    expected_channels: int,
    expected_is_cfa: bool = False,
    expected_cfa_pattern: str | None = None,
    reference_bit_depth: int | None = None,
    reference_orientation: str | None = None,
    flat_info: ImageInfo | None = None,
) -> tuple[np.ndarray, FlatCalibrationReport]:
    """Memvalidasi Master Flat dan menghasilkan array flat ternormalisasi (float32, mean=1.0).

    Args:
        master_flat: Array NumPy ``(H, W)`` / ``(H, W, 3)`` atau jalur berkas gambar flat.
        expected_height: Tinggi frame sequence.
        expected_width: Lebar frame sequence.
        expected_channels: Jumlah kanal sequence (1 atau 3).
        expected_is_cfa: Apakah sequence merupakan mosaik sensor CFA.
        expected_cfa_pattern: Nama pola CFA sequence (mis. ``"RGGB"``).
        reference_bit_depth: Bit depth frame referensi (untuk peringatan bila berbeda).
        reference_orientation: Orientasi EXIF frame referensi (untuk peringatan bila berbeda).
        flat_info: Objek ``ImageInfo`` dari berkas flat bila ``master_flat`` berupa array.

    Returns:
        Tuple ``(normalized_flat_float32, FlatCalibrationReport)``.
    """
    source_desc = "Array Master Flat di memori"
    if isinstance(master_flat, (str, Path)):
        flat_path = Path(master_flat)
        source_desc = flat_path.name
        try:
            loaded_flat = read_image(flat_path)
        except ImageReadError as exc:
            raise StackingError(
                f"Gagal membaca berkas Master Flat '{flat_path.name}': {exc}"
            ) from exc
        if loaded_flat.scientific_data is None:
            raise StackingError(
                f"Berkas Master Flat '{flat_path.name}' tidak memiliki data ilmiah."
            )
        flat_arr = loaded_flat.scientific_data
        flat_info = loaded_flat.info
    elif isinstance(master_flat, np.ndarray):
        flat_arr = master_flat
    else:
        raise StackingError("Master Flat harus berupa array NumPy atau jalur berkas gambar yang valid.")

    if flat_arr.ndim == 2:
        f_h, f_w = flat_arr.shape
        f_ch = 1
    elif flat_arr.ndim == 3:
        f_h, f_w, f_ch = flat_arr.shape
    else:
        raise StackingError(
            f"Dimensi array Master Flat tidak didukung (ndim={flat_arr.ndim}); "
            "harus 2D (Monokrom/CFA) atau 3D (RGB)."
        )

    # 1. Validasi ukuran (height x width)
    if (f_h, f_w) != (expected_height, expected_width):
        raise StackingError(
            f"Ukuran Master Flat ({f_w}×{f_h} px) tidak cocok dengan ukuran frame sequence "
            f"({expected_width}×{expected_height} px). Kalibrasi flat dibatalkan."
        )

    # 2. Validasi jumlah kanal
    if f_ch != expected_channels:
        raise StackingError(
            f"Jumlah kanal Master Flat ({f_ch}) tidak cocok dengan jumlah kanal frame sequence "
            f"({expected_channels}). Monokrom dan RGB tidak dapat dicampur."
        )

    warnings: list[str] = []
    flat_is_cfa, flat_cfa_pattern = _extract_cfa_info(flat_info)

    # 3. Validasi pola CFA bila informasi metadata flat tersedia
    if flat_info is not None:
        if expected_is_cfa != flat_is_cfa:
            raise StackingError(
                "Jenis sensor Master Flat (CFA vs Non-CFA) tidak cocok dengan frame sequence."
            )
        if (
            expected_is_cfa
            and expected_cfa_pattern
            and flat_cfa_pattern
            and expected_cfa_pattern != flat_cfa_pattern
        ):
            raise StackingError(
                f"Pola CFA Master Flat ({flat_cfa_pattern}) berbeda dari pola CFA frame sequence "
                f"({expected_cfa_pattern})."
            )
        if (
            reference_orientation is not None
            and flat_info.exif_orientation != reference_orientation
        ):
            warnings.append(
                f"Orientasi EXIF Master Flat ('{flat_info.exif_orientation}') berbeda dari "
                f"frame referensi ('{reference_orientation}')."
            )
        if (
            reference_bit_depth is not None
            and flat_info.original_bit_depth is not None
            and flat_info.original_bit_depth != reference_bit_depth
        ):
            warnings.append(
                f"Bit depth Master Flat ({flat_info.original_bit_depth}-bit) berbeda dari "
                f"frame referensi ({reference_bit_depth}-bit); flat tetap dinormalisasi ke float32."
            )
    else:
        flat_is_cfa = expected_is_cfa
        flat_cfa_pattern = expected_cfa_pattern

    work = np.asarray(flat_arr, dtype=np.float64)
    valid_positive = np.isfinite(work) & (work > 0.0)
    if not np.any(valid_positive):
        raise StackingError(
            f"Master Flat '{source_desc}' tidak valid karena seluruh nilai piksel bernilai <= 0 atau NaN."
        )

    global_mean = float(np.mean(work[valid_positive]))
    norm_flat = np.ones_like(work, dtype=np.float64)

    if f_ch == 3:
        # Normalisasi per-kanal R, G, B agar keseimbangan warna tetap terjaga
        for c in range(3):
            plane = work[..., c]
            mask_c = np.isfinite(plane) & (plane > 0.0)
            if not np.any(mask_c):
                raise StackingError(
                    f"Kanal warna ke-{c + 1} pada Master Flat '{source_desc}' bernilai <= 0 seluruhnya."
                )
            mean_c = float(np.mean(plane[mask_c]))
            norm_flat[..., c] = plane / mean_c
    elif expected_is_cfa:
        # Normalisasi per-subkanal 2x2 pada mosaik CFA agar respons warna Bayer tidak berubah
        for py in (0, 1):
            for px in (0, 1):
                sub = work[py::2, px::2]
                mask_sub = np.isfinite(sub) & (sub > 0.0)
                if np.any(mask_sub):
                    mean_sub = float(np.mean(sub[mask_sub]))
                    norm_flat[py::2, px::2] = sub / mean_sub
                else:
                    norm_flat[py::2, px::2] = sub / global_mean
    else:
        norm_flat = work / global_mean

    # Proteksi pembagian nol atau nilai sangat kecil / negatif / non-finite
    bad_mask = (~np.isfinite(norm_flat)) | (norm_flat <= FLAT_ZERO_THRESHOLD)
    protected_count = int(np.count_nonzero(bad_mask))
    if protected_count > 0:
        norm_flat = np.where(bad_mask, 1.0, norm_flat)
        warnings.append(
            f"Master Flat memiliki {protected_count} piksel bernilai <= {FLAT_ZERO_THRESHOLD} "
            "atau non-finite; piksel tersebut dilindungi dengan nilai pembagi netral 1.0."
        )

    out_flat = norm_flat.astype(np.float32)
    out_flat.flags.writeable = False

    report = FlatCalibrationReport(
        applied=True,
        source_description=source_desc,
        width=f_w,
        height=f_h,
        channels=f_ch,
        is_cfa_mosaic=flat_is_cfa,
        cfa_pattern_str=flat_cfa_pattern,
        flat_mean_before_norm=global_mean,
        protected_zero_pixels_count=protected_count,
        warnings=tuple(warnings),
    )
    return out_flat, report


def apply_flat_calibration(
    scientific_frame_float32: np.ndarray,
    normalized_flat: np.ndarray,
) -> np.ndarray:
    """Membagi satu frame float32 dengan Master Flat ternormalisasi tanpa mengubah input asli."""
    if scientific_frame_float32.shape != normalized_flat.shape:
        raise StackingError(
            f"Dimensi frame ({scientific_frame_float32.shape}) tidak sesuai dengan "
            f"Master Flat ({normalized_flat.shape})."
        )
    calibrated = np.asarray(scientific_frame_float32, dtype=np.float32) / np.asarray(
        normalized_flat, dtype=np.float32
    )
    return calibrated.astype(np.float32, copy=False)
