"""Validator kompatibilitas pra-stacking dan pengukur stabilitas posisi (Sub-Tahap 3A).

Modul ini menjalankan dua tugas utama sebelum stacking dieksekusi:
  1. **Validasi Struktural, CFA, & Metadata**:
     Memeriksa ukuran (width × height), jumlah kanal (mono vs RGB), pola CFA
     (mencegah pencampuran CFA dengan monokrom biasa atau pola CFA berbeda),
     orientasi EXIF, tipe data/bit depth, serta konsistensi metadata observasi
     (EXPTIME/shutter, GAIN/ISO, dan INSTRUME/kamera).
  2. **Pemeriksaan Stabilitas Posisi Baca-Saja (FR-CP-03..07)**:
     Mengukur estimasi pergeseran translasi ``(dx, dy)`` setiap frame terhadap
     frame referensi menggunakan *Phase Correlation* 2D FFT dengan interpolasi
     puncak parabolik sub-piksel.
     - **Murni Baca-Saja**: Tidak pernah menggeser, memutar, atau menyelaraskan
       piksel frame.
     - Ambang default: ``1.0`` piksel.
     - Status per frame: ``OK`` (<= ambang), ``MELEBIHI_AMBANG`` (> ambang),
       atau ``INDETERMINATE`` (kontras terlalu rendah / frame rata / puncak
       korelasi lemah).
"""

from __future__ import annotations

import math
from typing import Callable

import numpy as np

from hilalone.input_manager.image_reader import ImageInfo
from hilalone.input_manager.models import FrameStatus, InputMode, SequenceFrameEntry
from hilalone.processing.stacking.models import (
    ExcludedFrameRecord,
    FrameShiftMeasurement,
    PositionStabilityReport,
    PositionStabilityStatus,
    PreStackValidationReport,
    StackingError,
)

DEFAULT_SHIFT_THRESHOLD_PX = 1.0
MIN_CONFIDENCE_PSR = 4.5
MIN_CONTRAST_STD = 1e-4


def extract_frame_cfa_info(info: ImageInfo | None) -> tuple[bool, str | None]:
    """Mengambil status mosaik CFA dan nama pola CFA dari ImageInfo bila tersedia."""
    if info is None:
        return False, None
    if info.raw_metadata is not None and info.raw_metadata.is_cfa_mosaic:
        return True, info.raw_metadata.cfa_pattern_str
    if info.ser_metadata is not None and info.ser_metadata.is_cfa_mosaic:
        return True, info.ser_metadata.cfa_pattern_str
    return False, None


def _extract_exposure_sec(info: ImageInfo) -> float | None:
    if info.fits_header is not None and info.fits_header.exptime is not None:
        try:
            val = float(info.fits_header.exptime)
            if math.isfinite(val) and val > 0:
                return val
        except (TypeError, ValueError):
            pass
    if info.raw_metadata is not None and info.raw_metadata.shutter_sec is not None:
        try:
            val = float(info.raw_metadata.shutter_sec)
            if math.isfinite(val) and val > 0:
                return val
        except (TypeError, ValueError):
            pass
    return None


def _extract_gain_or_iso(info: ImageInfo) -> str | None:
    if info.fits_header is not None and info.fits_header.gain is not None:
        return f"GAIN={info.fits_header.gain}"
    if info.raw_metadata is not None and info.raw_metadata.iso_speed is not None:
        return f"ISO={info.raw_metadata.iso_speed}"
    return None


def _extract_instrument_name(info: ImageInfo) -> str | None:
    if info.fits_header is not None and info.fits_header.instrume:
        return str(info.fits_header.instrume).strip()
    if info.raw_metadata is not None:
        parts = [
            p.strip()
            for p in (info.raw_metadata.camera_make or "", info.raw_metadata.camera_model or "")
            if p and p.strip()
        ]
        if parts:
            return " ".join(parts)
    if info.ser_metadata is not None and info.ser_metadata.instrument:
        return info.ser_metadata.instrument.strip()
    return None


def extract_luminance_proxy_readonly(
    scientific_data: np.ndarray,
    is_cfa_mosaic: bool = False,
) -> tuple[np.ndarray, float]:
    """Membuat array 2D luminans sementara (read-only) untuk pengukuran posisi/kualitas.

    Fungsi ini TIDAK pernah mengubah ``scientific_data`` asli.
      * Citra RGB 3-kanal: ``L = 0.2126*R + 0.7152*G + 0.0722*B``, skala = 1.0.
      * Citra CFA 2D: rata-rata superpiksel 2×2 agar kisi Bayer tidak mengunci
        fase genap, skala = 2.0 (karena 1 piksel superpiksel = 2 piksel asli).
      * Citra Monokrom 2D: salinan float32 langsung, skala = 1.0.
    """
    if scientific_data.ndim == 3 and scientific_data.shape[2] >= 3:
        r = scientific_data[..., 0].astype(np.float32, copy=False)
        g = scientific_data[..., 1].astype(np.float32, copy=False)
        b = scientific_data[..., 2].astype(np.float32, copy=False)
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return lum.astype(np.float32, copy=False), 1.0

    arr2d = scientific_data.astype(np.float32, copy=False)
    if is_cfa_mosaic and arr2d.shape[0] >= 8 and arr2d.shape[1] >= 8:
        h2 = (arr2d.shape[0] // 2) * 2
        w2 = (arr2d.shape[1] // 2) * 2
        binned = 0.25 * (
            arr2d[0:h2:2, 0:w2:2]
            + arr2d[0:h2:2, 1:w2:2]
            + arr2d[1:h2:2, 0:w2:2]
            + arr2d[1:h2:2, 1:w2:2]
        )
        return binned.astype(np.float32, copy=False), 2.0

    return arr2d, 1.0


def _parabolic_subpixel_offset(v_minus: float, v_center: float, v_plus: float) -> float:
    """Interpolasi puncak parabolik 3-titik pada sekitar puncak korelasi."""
    denom = 2.0 * (v_minus - 2.0 * v_center + v_plus)
    if abs(denom) < 1e-12:
        return 0.0
    offset = (v_minus - v_plus) / denom
    if not math.isfinite(offset):
        return 0.0
    return float(max(-0.5, min(0.5, offset)))


def measure_frame_translation_readonly(
    reference_lum: np.ndarray,
    target_lum: np.ndarray,
    *,
    frame_index: int,
    file_name: str,
    scale_factor: float = 1.0,
    threshold_px: float = DEFAULT_SHIFT_THRESHOLD_PX,
    is_reference_self: bool = False,
) -> FrameShiftMeasurement:
    """Mengukur pergeseran translasi ``(dx, dy)`` secara *read-only* terhadap frame referensi.

    Menggunakan Phase Correlation 2D FFT. Apabila kontras citra terlalu datar/jenuh
    atau rasio puncak korelasi (PSR) terlalu lemah, status ditetapkan sebagai
    ``INDETERMINATE`` (FR-CP-06).
    """
    ref_finite = np.isfinite(reference_lum)
    tgt_finite = np.isfinite(target_lum)
    if not np.all(ref_finite) or not np.all(tgt_finite):
        return FrameShiftMeasurement(
            frame_index=frame_index,
            file_name=file_name,
            dx_px=None,
            dy_px=None,
            shift_magnitude_px=None,
            confidence_psr=0.0,
            status=PositionStabilityStatus.INDETERMINATE,
            note="Citra mengandung nilai non-finite (NaN/Inf); pergeseran tidak dapat ditentukan.",
        )

    ref_std = float(np.std(reference_lum))
    tgt_std = float(np.std(target_lum))
    if ref_std < MIN_CONTRAST_STD or tgt_std < MIN_CONTRAST_STD:
        return FrameShiftMeasurement(
            frame_index=frame_index,
            file_name=file_name,
            dx_px=None,
            dy_px=None,
            shift_magnitude_px=None,
            confidence_psr=0.0,
            status=PositionStabilityStatus.INDETERMINATE,
            note=(
                "Kontras citra terlalu rendah/rata (hampir kosong atau jenuh seluruhnya) "
                "sehingga pergeseran posisi tidak dapat diukur secara andal (INDETERMINATE)."
            ),
        )

    if is_reference_self:
        return FrameShiftMeasurement(
            frame_index=frame_index,
            file_name=file_name,
            dx_px=0.0,
            dy_px=0.0,
            shift_magnitude_px=0.0,
            confidence_psr=100.0,
            status=PositionStabilityStatus.OK,
            note="Frame referensi (dx=0.00 px, dy=0.00 px).",
        )

    h, w = reference_lum.shape
    if h < 4 or w < 4:
        return FrameShiftMeasurement(
            frame_index=frame_index,
            file_name=file_name,
            dx_px=None,
            dy_px=None,
            shift_magnitude_px=None,
            confidence_psr=0.0,
            status=PositionStabilityStatus.INDETERMINATE,
            note="Resolusi citra terlalu kecil untuk korelasi fase 2D.",
        )

    # Winsorize outlier ekstrem (mis. hot pixel, cosmic ray, atau kilatan lokal)
    # pada salinan sementara agar 1 blok outlier tidak mendominasi spektrum FFT
    def _winsorize_for_fft(arr: np.ndarray) -> np.ndarray:
        arr64 = arr.astype(np.float64, copy=True)
        med = float(np.median(arr64))
        mad = float(np.median(np.abs(arr64 - med)))
        sigma_rob = 1.4826 * mad
        if sigma_rob > 1e-9:
            arr64 = np.clip(arr64, med - 3.5 * sigma_rob, med + 3.5 * sigma_rob)
        return arr64 - float(np.mean(arr64))

    # Kurangi rata-rata dan terapkan jendela Hanning 2D untuk menekan kebocoran tepi spektral
    win_y = np.hanning(h).astype(np.float64)
    win_x = np.hanning(w).astype(np.float64)
    window2d = np.outer(win_y, win_x)

    ref_zero = _winsorize_for_fft(reference_lum) * window2d
    tgt_zero = _winsorize_for_fft(target_lum) * window2d

    f_ref = np.fft.rfft2(ref_zero)
    f_tgt = np.fft.rfft2(tgt_zero)

    # Cross-power spectrum: menggunakan sedikit regularisasi agar noise frekuensi tinggi
    # pada latar polos tidak mendominasi
    cross = f_tgt * np.conj(f_ref)
    mag = np.abs(cross)
    max_mag = float(np.max(mag))
    if max_mag <= 1e-12:
        return FrameShiftMeasurement(
            frame_index=frame_index,
            file_name=file_name,
            dx_px=None,
            dy_px=None,
            shift_magnitude_px=None,
            confidence_psr=0.0,
            status=PositionStabilityStatus.INDETERMINATE,
            note="Spektrum silang bernilai nol; posisi tidak dapat diukur.",
        )

    reg_eps = max(1e-12, 1e-3 * max_mag)
    normalized_cross = cross / (mag + reg_eps)
    corr = np.fft.fftshift(np.fft.irfft2(normalized_cross, s=(h, w)))

    peak_flat_idx = int(np.argmax(corr))
    py, px = divmod(peak_flat_idx, w)
    peak_val = float(corr[py, px])

    # Hitung Peak-to-Sidelobe Ratio (PSR) dengan mengecualikan area 3x3 di sekitar puncak
    mask_sidelobe = np.ones((h, w), dtype=bool)
    y0, y1 = max(0, py - 1), min(h, py + 2)
    x0, x1 = max(0, px - 1), min(w, px + 2)
    mask_sidelobe[y0:y1, x0:x1] = False
    sidelobes = corr[mask_sidelobe]
    side_mean = float(np.mean(sidelobes)) if sidelobes.size > 0 else 0.0
    side_std = float(np.std(sidelobes)) if sidelobes.size > 0 else 1.0
    psr = (peak_val - side_mean) / max(side_std, 1e-9)

    if psr < MIN_CONFIDENCE_PSR:
        return FrameShiftMeasurement(
            frame_index=frame_index,
            file_name=file_name,
            dx_px=None,
            dy_px=None,
            shift_magnitude_px=None,
            confidence_psr=float(psr),
            status=PositionStabilityStatus.INDETERMINATE,
            note=(
                f"Puncak korelasi fase lemah/ambigu (PSR={psr:.2f} < {MIN_CONFIDENCE_PSR}); "
                "estimasi pergeseran tidak dapat dipercaya (INDETERMINATE)."
            ),
        )

    # Interpolasi sub-piksel bila puncak tidak menempel di batas terluar array
    sub_y = 0.0
    sub_x = 0.0
    if 0 < py < h - 1:
        sub_y = _parabolic_subpixel_offset(
            float(corr[py - 1, px]),
            peak_val,
            float(corr[py + 1, px]),
        )
    if 0 < px < w - 1:
        sub_x = _parabolic_subpixel_offset(
            float(corr[py, px - 1]),
            peak_val,
            float(corr[py, px + 1]),
        )

    cy = h // 2
    cx = w // 2
    dy_px = float((py + sub_y - cy) * scale_factor)
    dx_px = float((px + sub_x - cx) * scale_factor)
    shift_mag = float(math.hypot(dx_px, dy_px))

    if shift_mag <= threshold_px:
        status = PositionStabilityStatus.OK
        note = (
            f"Stabil (dx={dx_px:+.2f} px, dy={dy_px:+.2f} px, |dr|={shift_mag:.2f} px <= {threshold_px:.2f} px)."
        )
    else:
        status = PositionStabilityStatus.MELEBIHI_AMBANG
        note = (
            f"Pergeseran melebihi ambang (dx={dx_px:+.2f} px, dy={dy_px:+.2f} px, "
            f"|dr|={shift_mag:.2f} px > {threshold_px:.2f} px). Menumpuk frame ini tanpa "
            f"alignment berisiko menimbulkan blur sebesar ~{shift_mag:.2f} px."
        )

    return FrameShiftMeasurement(
        frame_index=frame_index,
        file_name=file_name,
        dx_px=dx_px,
        dy_px=dy_px,
        shift_magnitude_px=shift_mag,
        confidence_psr=float(psr),
        status=status,
        note=note,
    )


def measure_sequence_position_stability(
    frame_indices: tuple[int, ...],
    load_scientific_frame_fn: Callable[[int], tuple[np.ndarray, str, bool]],
    *,
    reference_frame_index: int | None = None,
    threshold_px: float = DEFAULT_SHIFT_THRESHOLD_PX,
) -> PositionStabilityReport:
    """Mengukur stabilitas posisi seluruh frame kandidat secara *read-only*.

    Args:
        frame_indices: Indeks frame yang akan diperiksa.
        load_scientific_frame_fn: Fungsi pembaca ``(index) -> (scientific_data, file_name, is_cfa)``.
        reference_frame_index: Indeks frame referensi (default: indeks pertama pada ``frame_indices``).
        threshold_px: Ambang maksimum pergeseran dalam piksel (default ``1.0`` px).
    """
    if not frame_indices:
        raise StackingError("Tidak ada frame untuk diperiksa stabilitas posisinya.")

    ref_idx = reference_frame_index if reference_frame_index in frame_indices else frame_indices[0]
    ref_arr, ref_name, ref_is_cfa = load_scientific_frame_fn(ref_idx)
    ref_lum, ref_scale = extract_luminance_proxy_readonly(ref_arr, is_cfa_mosaic=ref_is_cfa)

    measurements: list[FrameShiftMeasurement] = []
    warnings: list[str] = []
    valid_shifts: list[float] = []
    ok_count = 0
    exceeded_count = 0
    indeterminate_count = 0

    for idx in frame_indices:
        if idx == ref_idx:
            m = measure_frame_translation_readonly(
                ref_lum,
                ref_lum,
                frame_index=idx,
                file_name=ref_name,
                scale_factor=ref_scale,
                threshold_px=threshold_px,
                is_reference_self=True,
            )
        else:
            tgt_arr, tgt_name, tgt_is_cfa = load_scientific_frame_fn(idx)
            tgt_lum, tgt_scale = extract_luminance_proxy_readonly(
                tgt_arr, is_cfa_mosaic=tgt_is_cfa
            )
            m = measure_frame_translation_readonly(
                ref_lum,
                tgt_lum,
                frame_index=idx,
                file_name=tgt_name,
                scale_factor=tgt_scale,
                threshold_px=threshold_px,
                is_reference_self=False,
            )

        measurements.append(m)
        if m.shift_magnitude_px is not None:
            valid_shifts.append(m.shift_magnitude_px)

        if m.status == PositionStabilityStatus.OK:
            ok_count += 1
        elif m.status == PositionStabilityStatus.MELEBIHI_AMBANG:
            exceeded_count += 1
            warnings.append(
                f"Frame #{idx + 1} ({m.file_name}) [MELEBIHI_AMBANG]: {m.note}"
            )
        else:
            indeterminate_count += 1
            warnings.append(
                f"Frame #{idx + 1} ({m.file_name}) [INDETERMINATE]: {m.note}"
            )

    max_shift = max(valid_shifts) if valid_shifts else None
    mean_shift = (sum(valid_shifts) / len(valid_shifts)) if valid_shifts else None

    return PositionStabilityReport(
        reference_frame_index=ref_idx,
        threshold_px=threshold_px,
        measurements=tuple(measurements),
        max_shift_px=max_shift,
        mean_shift_px=mean_shift,
        ok_count=ok_count,
        exceeded_count=exceeded_count,
        indeterminate_count=indeterminate_count,
        has_warnings=(exceeded_count > 0 or indeterminate_count > 0),
        warnings=tuple(warnings),
    )


def validate_sequence_for_stacking(
    input_mode: InputMode,
    entries: tuple[SequenceFrameEntry, ...],
    *,
    excluded_frame_indices: set[int] | None = None,
    allow_exclude_incompatible_and_error: bool = False,
) -> PreStackValidationReport:
    """Memeriksa kelayakan seluruh frame di dalam SequenceManager sebelum stacking.

    Aturan:
      * Mode ``SINGLE`` atau kosong ditolak dengan ``StackingError``.
      * Memeriksa dimensi, kanal, pola CFA, orientasi, bit depth/dtype, serta
        konsistensi metadata observasi (EXPTIME, GAIN/ISO, INSTRUME).
      * Tidak pernah membuang frame secara diam-diam: setiap frame yang
        dikecualikan dicatat di dalam ``ExcludedFrameRecord``.
    """
    if input_mode == InputMode.SINGLE:
        raise StackingError(
            "Mode Single Image tidak memerlukan dan tidak mengizinkan stacking "
            "(stacking hanya berlaku untuk Multiple Images, Video, dan SER)."
        )
    if input_mode == InputMode.EMPTY or len(entries) == 0:
        raise StackingError("Belum ada sequence multi-frame atau video yang dibuka untuk di-stack.")
    if len(entries) < 2:
        raise StackingError(
            f"Stacking memerlukan minimal 2 frame, tetapi sequence saat ini hanya berisi {len(entries)} frame."
        )

    user_excluded = set(excluded_frame_indices or ())
    excluded_records: list[ExcludedFrameRecord] = []
    structural_warnings: list[str] = []
    metadata_warnings: list[str] = []

    # 1. Cari frame referensi pertama yang memiliki info valid dan tidak dikecualikan pengguna
    ref_entry: SequenceFrameEntry | None = None
    for entry in entries:
        if entry.frame_index in user_excluded:
            continue
        if entry.status != FrameStatus.ERROR and entry.info is not None:
            ref_entry = entry
            break

    if ref_entry is None or ref_entry.info is None:
        raise StackingError(
            "Tidak ditemukan frame referensi yang valid di dalam sequence untuk memulai stacking."
        )

    ref_info = ref_entry.info
    ref_is_cfa, ref_cfa_pattern = extract_frame_cfa_info(ref_info)
    ref_exp = _extract_exposure_sec(ref_info)
    ref_gain_iso = _extract_gain_or_iso(ref_info)
    ref_inst = _extract_instrument_name(ref_info)

    included_indices: list[int] = []
    dtypes_seen: set[str] = set()
    bit_depths_seen: set[int] = set()
    has_unconfirmed_invalid = False

    for entry in entries:
        idx = entry.frame_index
        if idx in user_excluded:
            excluded_records.append(
                ExcludedFrameRecord(
                    frame_index=idx,
                    file_name=entry.file_name,
                    reason="Dikecualikan secara eksplisit oleh pengguna.",
                )
            )
            continue

        if entry.status == FrameStatus.ERROR or entry.info is None:
            reason = "; ".join(entry.issues) if entry.issues else "Berkas gagal dibaca (ERROR)."
            structural_warnings.append(f"Frame #{idx + 1} ({entry.file_name}): {reason}")
            if allow_exclude_incompatible_and_error:
                excluded_records.append(
                    ExcludedFrameRecord(
                        frame_index=idx,
                        file_name=entry.file_name,
                        reason=f"GAGAL DIBACA: {reason}",
                    )
                )
            else:
                has_unconfirmed_invalid = True
            continue

        info = entry.info
        frame_issues: list[str] = list(entry.issues)

        # Validasi dimensi
        if (info.width, info.height) != (ref_info.width, ref_info.height) and not any(
            "Dimensi" in iss for iss in frame_issues
        ):
            frame_issues.append(
                f"Dimensi ({info.width}×{info.height} px) berbeda dari frame referensi "
                f"({ref_info.width}×{ref_info.height} px)."
            )

        # Validasi kanal
        if info.channels != ref_info.channels and not any(
            "kanal" in iss.lower() for iss in frame_issues
        ):
            frame_issues.append(
                f"Jumlah kanal ({info.channels}) berbeda dari frame referensi ({ref_info.channels})."
            )

        # Validasi status & pola CFA (RAW/SER Bayer tidak boleh dicampur dengan Mono biasa atau pola lain)
        cur_is_cfa, cur_cfa_pattern = extract_frame_cfa_info(info)
        if cur_is_cfa != ref_is_cfa:
            frame_issues.append(
                "Ketidakcocokan struktur sensor: tidak dapat mencampur data mosaik CFA "
                "(RAW/SER Bayer) dengan citra non-CFA."
            )
        elif cur_is_cfa and (cur_cfa_pattern or "") != (ref_cfa_pattern or ""):
            frame_issues.append(
                f"Pola CFA ({cur_cfa_pattern}) berbeda dari frame referensi ({ref_cfa_pattern})."
            )

        # Validasi orientasi
        if info.exif_orientation != ref_info.exif_orientation and not any(
            "Orientasi" in iss for iss in frame_issues
        ):
            frame_issues.append(
                f"Orientasi ('{info.exif_orientation}') berbeda dari frame referensi "
                f"('{ref_info.exif_orientation}')."
            )

        if frame_issues or entry.status == FrameStatus.INCOMPATIBLE:
            reason_str = "; ".join(frame_issues) if frame_issues else "Frame berstatus INCOMPATIBLE."
            structural_warnings.append(f"Frame #{idx + 1} ({entry.file_name}): {reason_str}")
            if allow_exclude_incompatible_and_error:
                excluded_records.append(
                    ExcludedFrameRecord(
                        frame_index=idx,
                        file_name=entry.file_name,
                        reason=f"TIDAK KOMPATIBEL: {reason_str}",
                    )
                )
            else:
                has_unconfirmed_invalid = True
            continue

        # Frame kompatibel secara struktural
        included_indices.append(idx)
        if info.dtype_str:
            dtypes_seen.add(info.dtype_str)
        if info.original_bit_depth is not None:
            bit_depths_seen.add(info.original_bit_depth)

        # Periksa konsistensi metadata observasi (peringatan ilmiah)
        cur_exp = _extract_exposure_sec(info)
        if ref_exp is not None and cur_exp is not None:
            rel_diff = abs(cur_exp - ref_exp) / max(ref_exp, 1e-12)
            if rel_diff > 0.01:
                metadata_warnings.append(
                    f"Frame #{idx + 1} ({entry.file_name}): Exposure time ({cur_exp:g} s) berbeda "
                    f"dari frame referensi ({ref_exp:g} s)."
                )

        cur_gain_iso = _extract_gain_or_iso(info)
        if ref_gain_iso is not None and cur_gain_iso is not None and cur_gain_iso != ref_gain_iso:
            metadata_warnings.append(
                f"Frame #{idx + 1} ({entry.file_name}): Sensitivitas ({cur_gain_iso}) berbeda "
                f"dari frame referensi ({ref_gain_iso})."
            )

        cur_inst = _extract_instrument_name(info)
        if ref_inst is not None and cur_inst is not None and cur_inst != ref_inst:
            metadata_warnings.append(
                f"Frame #{idx + 1} ({entry.file_name}): Instrumen/kamera ('{cur_inst}') berbeda "
                f"dari frame referensi ('{ref_inst}')."
            )

    mixed_bit_depth = len(dtypes_seen) > 1 or len(bit_depths_seen) > 1
    all_uint = all(dt.startswith("uint") for dt in dtypes_seen) if dtypes_seen else False
    normalize_integers = mixed_bit_depth and all_uint

    is_valid = (not has_unconfirmed_invalid) and (len(included_indices) >= 2)

    return PreStackValidationReport(
        is_valid_to_proceed=is_valid,
        requires_user_confirmation=has_unconfirmed_invalid,
        reference_frame_index=ref_entry.frame_index,
        included_frame_indices=tuple(included_indices),
        excluded_frames=tuple(excluded_records),
        width=ref_info.width,
        height=ref_info.height,
        channels=ref_info.channels or 1,
        is_cfa_mosaic=ref_is_cfa,
        cfa_pattern_str=ref_cfa_pattern,
        mixed_bit_depth=mixed_bit_depth,
        normalize_integers_to_unit=normalize_integers,
        metadata_warnings=tuple(metadata_warnings),
        structural_warnings=tuple(structural_warnings),
        stability_report=None,
    )
