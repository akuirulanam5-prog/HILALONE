"""Kalibrasi Master Flat-Field Opsional untuk HILALONE (Sub-Tahap 3A).

Aturan ilmiah (AGENTS.md Bagian 4 & TAHAP 2–8):
  1. Kalibrasi flat-field bersifat **murni opsional** dan hanya dijalankan bila
     pengguna secara eksplisit mengaktifkannya dan menyediakan Master Flat.
  2. **Tidak ada** kalibrasi dark maupun bias.
  3. Mendukung dua jenis input flat melalui Unified Input Data Model & Reader
     yang telah tersedia di ``hilalone.input_manager``:
       * **Single Master Flat**: FITS (termasuk multi-HDU), TIFF (termasuk
         multi-page), Camera RAW, PNG, JPEG, BMP.
       * **Flat Frame Sequence**: Multiple Images, Folder Sequence, FITS/TIFF/RAW
         sequence, Video (``.avi``, ``.mp4``, ``.mov``), dan SER (``.ser``)
         secara *lazy* / bertahap tanpa memuat seluruh video ke RAM.
  4. Rumus normalisasi & koreksi:
       * ``F_norm(x,y) = F(x,y) / median(F_valid)``
       * ``I_corrected(x,y) = I_original(x,y) / F_norm(x,y)``
     Dihitung pada salinan kerja floating-point (``float64`` -> ``float32``),
     per-kanal untuk RGB atau per-subkanal 2×2 untuk Bayer CFA tanpa pernah
     melakukan demosaicing pada data ilmiah.
  5. Piksel tidak valid (``<= 0``, ``NaN``, ``Infinity``, dan *saturated*)
     dideteksi ke dalam ``invalid_pixel_mask`` dan dilaporkan jumlahnya. Piksel
     dengan pembagi ``<= 1e-4`` atau non-finite dilindungi dengan nilai netral
     ``1.0`` agar tidak pernah terjadi *division by zero*.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, Iterable, Sequence

import numpy as np

from hilalone.input_manager.adapters.ser_reader import SER_EXTENSIONS
from hilalone.input_manager.adapters.video_reader import VIDEO_EXTENSIONS
from hilalone.input_manager.image_reader import (
    ImageInfo,
    ImageReadError,
    MultiHduFitsError,
    MultiPageTiffError,
    read_image,
)
from hilalone.input_manager.models import FrameStatus
from hilalone.input_manager.preview_builder import array_to_preview_qimage
from hilalone.input_manager.sequence_manager import SequenceManager
from hilalone.processing.stacking.models import (
    FlatCalibrationReport,
    FlatCompatibilityCheckResult,
    LoadedMasterFlat,
    StackingCancelledError,
    StackingError,
)

FLAT_ZERO_THRESHOLD = 1e-4
NORMALIZATION_FORMULA_TEXT = "F_norm(x,y) = F(x,y) / median(F_valid)"

_LOSSY_IMAGE_FORMATS = frozenset({"JPEG", "JPG"})
_LOSSY_VIDEO_CODECS = frozenset(
    {"h264", "hevc", "h265", "mpeg4", "msmpeg4v3", "vp8", "vp9", "av1", "wmv3", " cinepak"}
)


def _extract_cfa_info(info: ImageInfo | None) -> tuple[bool, str | None]:
    if info is None:
        return False, None
    if info.raw_metadata is not None and info.raw_metadata.is_cfa_mosaic:
        return True, info.raw_metadata.cfa_pattern_str
    if info.ser_metadata is not None and info.ser_metadata.is_cfa_mosaic:
        return True, info.ser_metadata.cfa_pattern_str
    return False, None


def _extract_instrument_or_camera(info: ImageInfo | None) -> str | None:
    if info is None:
        return None
    if info.fits_header is not None and info.fits_header.instrume:
        val = str(info.fits_header.instrume).strip()
        if val and val != "Tidak tersedia":
            return val
    if info.raw_metadata is not None:
        parts = [
            p.strip()
            for p in (info.raw_metadata.camera_make or "", info.raw_metadata.camera_model or "")
            if p and p.strip() and p.strip() != "Tidak tersedia"
        ]
        if parts:
            return " ".join(parts)
    if info.ser_metadata is not None and info.ser_metadata.instrument:
        val = info.ser_metadata.instrument.strip()
        if val and val != "Tidak tersedia":
            return val
    return None


def _determine_saturation_ceiling(
    arr: np.ndarray,
    info: ImageInfo | None,
) -> float | None:
    """Menentukan batas nilai saturasi piksel berdasarkan metadata sensor atau tipe data asli."""
    if info is not None and info.raw_metadata is not None and info.raw_metadata.white_level:
        wl = float(info.raw_metadata.white_level)
        if wl > 0:
            return wl

    if info is not None and not info.original_is_float and info.original_bit_depth is not None:
        bd = int(info.original_bit_depth)
        if 8 <= bd <= 32:
            return float((1 << bd) - 1)

    if np.issubdtype(arr.dtype, np.integer):
        return float(np.iinfo(arr.dtype).max)

    return None


def _check_lossy_warning(info: ImageInfo | None) -> list[str]:
    """Menghasilkan peringatan akurasi ilmiah apabila flat berasal dari format lossy."""
    warnings: list[str] = []
    if info is None:
        return warnings

    fmt_upper = (info.file_format or "").upper()
    if fmt_upper in _LOSSY_IMAGE_FORMATS or info.path.suffix.lower() in (".jpg", ".jpeg"):
        warnings.append(
            f"Master Flat '{info.file_name}' menggunakan format kompresi lossy (JPEG) dan "
            "kurva gamma non-linear; akurasi fotometrik kalibrasi flat ilmiah terbatas."
        )

    if info.video_metadata is not None:
        codec_low = (info.video_metadata.codec_name or "").lower()
        ext_low = info.path.suffix.lower()
        if codec_low in _LOSSY_VIDEO_CODECS or ext_low in (".mp4", ".mov"):
            warnings.append(
                f"Master Flat berasal dari video terkompresi ('{info.file_name}', codec={info.video_metadata.codec_name}); "
                "kompresi lossy dan kurva transfer video dapat menurunkan akurasi kalibrasi flat ilmiah."
            )
    return warnings


def _validate_flat_optical_characteristics(
    arr: np.ndarray,
    source_desc: str,
    *,
    is_sequence_source: bool = False,
) -> list[str]:
    """Memeriksa apakah array memenuhi karakteristik optik citra flat-field.

    Menolak citra yang gelap gulita (>50% piksel <= 0/NaN) atau video objek langit
    gelap yang bukan merupakan flat-field bercahaya homogen.
    """
    warnings: list[str] = []
    work = np.asarray(arr, dtype=np.float64)
    finite_pos = np.isfinite(work) & (work > FLAT_ZERO_THRESHOLD)
    total_elems = max(1, work.size)
    valid_ratio = float(np.count_nonzero(finite_pos)) / float(total_elems)

    if valid_ratio == 0.0:
        raise StackingError(
            f"Master Flat '{source_desc}' tidak valid karena seluruh nilai piksel bernilai <= 0 atau NaN."
        )
    if valid_ratio < 0.50:
        raise StackingError(
            f"Citra flat '{source_desc}' tidak valid sebagai Master Flat: hanya {valid_ratio * 100:.1f}% "
            "piksel yang memiliki pencahayaan positif (lebih dari 50% piksel bernilai <= 0 atau NaN)."
        )

    valid_vals = work[finite_pos]
    med_val = float(np.median(valid_vals))
    p05, p25, p75, p95, p99 = (
        float(v) for v in np.percentile(valid_vals, [5.0, 25.0, 75.0, 95.0, 99.0])
    )

    if med_val <= FLAT_ZERO_THRESHOLD:
        raise StackingError(
            f"Master Flat '{source_desc}' memiliki nilai median terlalu rendah ({med_val:.4g}); "
            "pastikan frame flat memiliki pencahayaan yang memadai."
        )

    # Deteksi bila pengguna salah memilih video objek langit gelap (bukan flat-field):
    # Pada video langit malam + objek terang, mayoritas latar belakang sangat gelap dibanding puncak P99
    if is_sequence_source and p99 > 0.0:
        if (p99 / max(med_val, 1e-9)) > 10.0 or (p05 / max(p95, 1e-9)) < 0.02:
            raise StackingError(
                f"Sequence/video '{source_desc}' tidak memiliki karakteristik pencahayaan homogen "
                f"sebagai flat-field (rasio puncak/median={p99 / max(med_val, 1e-9):.1f}x, "
                f"P05/P95={p05 / max(p95, 1e-9):.3f}). Jangan menggunakan video objek pengamatan "
                "sebagai Master Flat."
            )

    rel_iqr = (p75 - p25) / max(med_val, 1e-9)
    if rel_iqr > 1.2:
        warnings.append(
            f"Master Flat '{source_desc}' memiliki variasi iluminasi yang sangat lebar "
            f"(IQR/median={rel_iqr:.2f}); periksa apakah pencahayaan flat sudah merata."
        )

    return warnings


def compute_flat_pixel_statistics(
    flat_arr: np.ndarray,
    *,
    saturation_ceiling: float | None = None,
    is_cfa_mosaic: bool = False,
) -> tuple[float, float, int, int, int, int, np.ndarray]:
    """Menghitung statistik piksel Master Flat sebelum normalisasi.

    Returns:
        Tuple ``(global_median, global_mean, invalid_pixel_count, zero_or_neg_count,
        non_finite_count, saturated_count, invalid_pixel_mask_2d)``.
    """
    work = np.asarray(flat_arr, dtype=np.float64)
    finite_mask = np.isfinite(work)
    non_finite_elem_mask = ~finite_mask
    zero_or_neg_elem_mask = finite_mask & (work <= FLAT_ZERO_THRESHOLD)

    if saturation_ceiling is not None and saturation_ceiling > 0.0:
        sat_elem_mask = finite_mask & (work >= saturation_ceiling)
    else:
        sat_elem_mask = np.zeros_like(finite_mask, dtype=bool)

    if work.ndim == 3:
        non_finite_2d = np.any(non_finite_elem_mask, axis=2)
        zero_or_neg_2d = np.any(zero_or_neg_elem_mask, axis=2) & (~non_finite_2d)
        sat_2d = np.any(sat_elem_mask, axis=2) & (~non_finite_2d) & (~zero_or_neg_2d)
    else:
        non_finite_2d = non_finite_elem_mask
        zero_or_neg_2d = zero_or_neg_elem_mask
        sat_2d = sat_elem_mask

    invalid_mask_2d = non_finite_2d | zero_or_neg_2d | sat_2d
    non_finite_count = int(np.count_nonzero(non_finite_2d))
    zero_or_neg_count = int(np.count_nonzero(zero_or_neg_2d))
    saturated_count = int(np.count_nonzero(sat_2d))
    invalid_pixel_count = int(np.count_nonzero(invalid_mask_2d))

    # F_valid adalah piksel yang finite, > FLAT_ZERO_THRESHOLD, dan tidak saturated
    valid_elem_mask = finite_mask & (work > FLAT_ZERO_THRESHOLD) & (~sat_elem_mask)
    if not np.any(valid_elem_mask):
        # Fallback bila seluruh piksel positif berada pada plafon saturasi
        valid_elem_mask = finite_mask & (work > FLAT_ZERO_THRESHOLD)

    if np.any(valid_elem_mask):
        global_median = float(np.median(work[valid_elem_mask]))
        global_mean = float(np.mean(work[valid_elem_mask]))
    else:
        global_median = 0.0
        global_mean = 0.0

    return (
        global_median,
        global_mean,
        invalid_pixel_count,
        zero_or_neg_count,
        non_finite_count,
        saturated_count,
        invalid_mask_2d,
    )


def load_single_master_flat(
    path: str | Path,
    *,
    page_index: int | None = None,
    hdu_index: int | None = None,
    validate_flat_characteristics: bool = True,
) -> LoadedMasterFlat:
    """Membaca satu berkas Master Flat (FITS, TIFF, RAW, PNG, JPEG, BMP) melalui reader standar.

    Catatan:
        ``MultiPageTiffError`` dan ``MultiHduFitsError`` sengaja diteruskan bila
        ``page_index`` / ``hdu_index`` belum dipilih agar GUI dapat menampilkan
        dialog pemilihan halaman/HDU kepada pengguna.
    """
    flat_path = Path(path)
    try:
        loaded = read_image(flat_path, page_index=page_index, hdu_index=hdu_index)
    except (MultiPageTiffError, MultiHduFitsError):
        raise
    except ImageReadError as exc:
        raise StackingError(
            f"Gagal membaca berkas Master Flat '{flat_path.name}': {exc}"
        ) from exc

    if loaded.scientific_data is None:
        raise StackingError(
            f"Berkas Master Flat '{flat_path.name}' tidak memiliki data ilmiah."
        )

    raw_arr = loaded.scientific_data
    info = loaded.info

    # Apabila PNG/TIFF memiliki kanal ke-4 (Alpha) yang konstan penuh, ambil 3 kanal RGB
    # dan catat peringatannya; tetap tolak bila jumlah kanal tidak valid.
    warnings: list[str] = _check_lossy_warning(info)
    if raw_arr.ndim == 3 and raw_arr.shape[2] == 4:
        raw_arr = raw_arr[..., :3]
        warnings.append(
            f"Master Flat '{flat_path.name}' memiliki kanal alpha (RGBA); hanya 3 kanal warna RGB yang digunakan."
        )

    if raw_arr.ndim == 2:
        h, w = raw_arr.shape
        ch = 1
    elif raw_arr.ndim == 3 and raw_arr.shape[2] == 3:
        h, w, ch = raw_arr.shape
    else:
        raise StackingError(
            f"Dimensi array Master Flat '{flat_path.name}' tidak didukung (shape={raw_arr.shape}); "
            "harus 2D (Monokrom/CFA) atau 3D (RGB 3-kanal)."
        )

    if validate_flat_characteristics:
        warnings.extend(
            _validate_flat_optical_characteristics(
                raw_arr, flat_path.name, is_sequence_source=False
            )
        )

    sat_ceiling = _determine_saturation_ceiling(raw_arr, info)
    sci_f32 = np.array(raw_arr, dtype=np.float32, copy=True)
    sci_f32.flags.writeable = False

    is_cfa, cfa_pat = _extract_cfa_info(info)
    fmt_str = info.file_format or flat_path.suffix.lstrip(".").upper()
    if info.raw_metadata is not None:
        fmt_str = f"RAW ({info.file_format})"

    is_lossy = (info.file_format or "").upper() in _LOSSY_IMAGE_FORMATS or flat_path.suffix.lower() in (
        ".jpg",
        ".jpeg",
    )

    return LoadedMasterFlat(
        scientific_data=sci_f32,
        preview=loaded.preview,
        info=info,
        source_description=flat_path.name,
        source_paths=(flat_path,),
        flat_format=fmt_str,
        flat_input_type="SINGLE",
        frame_count=1,
        width=w,
        height=h,
        channels=ch,
        dtype_str=info.dtype_str or str(raw_arr.dtype),
        bit_depth=info.original_bit_depth,
        is_cfa_mosaic=is_cfa,
        cfa_pattern_str=cfa_pat,
        exif_orientation=info.exif_orientation,
        saturation_ceiling=sat_ceiling,
        is_lossy_source=is_lossy,
        warnings=tuple(warnings),
    )


def load_master_flat_from_sequence(
    source: str | Path | Iterable[str | Path] | SequenceManager,
    *,
    source_kind: str = "auto",
    sort_by: str = "natural",
    endianness_policy: str = "siril_default",
    validate_flat_characteristics: bool = True,
    max_working_memory_mb: int = 512,
) -> LoadedMasterFlat:
    """Membuat satu Master Flat (float32) dari sequence frame flat secara *lazy* & hemat RAM.

    Mendukung:
      * ``source_kind="files"``  : Daftar berkas gambar flat (FITS, TIFF, RAW, PNG, JPEG).
      * ``source_kind="folder"`` : Satu folder berisi berkas-berkas frame flat.
      * ``source_kind="video"``  : Berkas video flat (``.avi``, ``.mp4``, ``.mov``).
      * ``source_kind="ser"``    : Berkas astronomi flat (``.ser``).
      * ``source_kind="auto"``   : Deteksi otomatis berdasarkan tipe/ekstensi ``source``.
    """
    owns_sm = False
    if isinstance(source, SequenceManager):
        sm = source
    else:
        sm = SequenceManager()
        owns_sm = True
        try:
            if isinstance(source, (str, Path)):
                p = Path(source)
                kind = source_kind.lower()
                ext = p.suffix.lower().lstrip(".")
                if kind == "folder" or (kind == "auto" and p.is_dir()):
                    sm.open_folder(p, sort_by=sort_by)
                elif kind == "video" or (kind == "auto" and ext in VIDEO_EXTENSIONS):
                    sm.open_video_file(p)
                elif kind == "ser" or (kind == "auto" and ext in SER_EXTENSIONS):
                    sm.open_ser_file(p, endianness_policy=endianness_policy)
                else:
                    sm.open_files([p], sort_by=sort_by)
            elif isinstance(source, Iterable):
                paths_list = [Path(item) for item in source]
                if not paths_list:
                    raise StackingError("Daftar berkas Flat Frame Sequence kosong.")
                sm.open_files(paths_list, sort_by=sort_by)
            else:
                raise StackingError("Sumber Flat Frame Sequence tidak dikenali.")
        except ImageReadError as exc:
            if owns_sm:
                sm.clear()
            raise StackingError(f"Gagal membuka Flat Frame Sequence: {exc}") from exc

    try:
        entries = sm.entries
        if not entries:
            raise StackingError("Flat Frame Sequence tidak berisi frame.")

        compat_entries = [e for e in entries if e.status == FrameStatus.COMPATIBLE]
        incompat_entries = [e for e in entries if e.status == FrameStatus.INCOMPATIBLE]
        error_entries = [e for e in entries if e.status == FrameStatus.ERROR]

        if incompat_entries or error_entries:
            bad_names = ", ".join(
                f"'{e.file_name}' ({e.status.value})"
                for e in (*incompat_entries, *error_entries)[:4]
            )
            raise StackingError(
                f"Flat Frame Sequence mengandung {len(incompat_entries)} frame tidak kompatibel "
                f"dan {len(error_entries)} frame rusak ({bad_names}). "
                "Pastikan seluruh frame di dalam sequence flat berukuran dan berformat seragam."
            )

        if len(compat_entries) == 0:
            raise StackingError("Tidak ada frame flat yang valid di dalam sequence.")

        ref_entry = compat_entries[0]
        ref_loaded = sm.load_frame(ref_entry.frame_index)
        if ref_loaded.scientific_data is None:
            raise StackingError(
                f"Frame flat '{ref_entry.file_name}' tidak memiliki data ilmiah."
            )

        ref_info = ref_loaded.info
        ref_arr = ref_loaded.scientific_data
        warnings: list[str] = _check_lossy_warning(ref_info)

        if ref_arr.ndim == 3 and ref_arr.shape[2] == 4:
            ref_arr = ref_arr[..., :3]
            warnings.append(
                "Flat Frame Sequence memiliki kanal alpha (RGBA); hanya 3 kanal RGB yang digunakan."
            )

        if ref_arr.ndim == 2:
            height, width = ref_arr.shape
            channels = 1
        elif ref_arr.ndim == 3 and ref_arr.shape[2] == 3:
            height, width, channels = ref_arr.shape
        else:
            raise StackingError(
                f"Dimensi frame flat tidak didukung (shape={ref_arr.shape})."
            )

        n_frames = len(compat_entries)
        frame_indices = [e.frame_index for e in compat_entries]
        sat_ceiling = _determine_saturation_ceiling(ref_arr, ref_info)

        unique_paths = tuple(dict.fromkeys(e.source_path for e in compat_entries))
        if len(unique_paths) == 1:
            src_desc = f"{unique_paths[0].name} (Sequence {n_frames} frame)"
        else:
            src_desc = f"Flat Sequence ({n_frames} berkas: {unique_paths[0].name} .. {unique_paths[-1].name})"

        # Gabungkan seluruh frame flat sequence secara hemat memori dan tahan outlier (NaN-safe)
        acc_shape = (height, width) if channels == 1 else (height, width, channels)
        bytes_per_frame = height * width * channels * 4
        budget_bytes = max(32, max_working_memory_mb) * 1024 * 1024

        frame_stats: list[dict[str, Any]] = []
        valid_frames_data: list[np.ndarray] = []
        valid_frame_indices: list[int] = []

        # Akumulator streaming NaN-safe
        sum_acc = np.zeros(acc_shape, dtype=np.float64)
        valid_pixel_counts = np.zeros(acc_shape, dtype=np.int32)

        can_store_all_in_memory = (n_frames * bytes_per_frame) <= budget_bytes

        for pos, f_idx in enumerate(frame_indices):
            loaded_f = ref_loaded if pos == 0 else sm.load_frame(f_idx)
            f_arr = loaded_f.scientific_data
            if f_arr is None:
                frame_stats.append({
                    "frame_index": f_idx,
                    "is_valid": False,
                    "reason": "Data ilmiah tidak terbaca (None)",
                    "median": 0.0,
                    "mean": 0.0,
                    "min": 0.0,
                    "max": 0.0,
                })
                continue

            if f_arr.ndim == 3 and f_arr.shape[2] == 4:
                f_arr = f_arr[..., :3]

            f_f32 = np.asarray(f_arr, dtype=np.float32)
            finite_mask = np.isfinite(f_f32)
            pos_mask = finite_mask & (f_f32 > FLAT_ZERO_THRESHOLD)

            # Subsampling cepat jika frame berukuran besar untuk memeriksa validitas frame
            f_h, f_w = f_f32.shape[:2]
            if f_h * f_w > 10000:
                sy = max(1, f_h // 100)
                sx = max(1, f_w // 100)
                sub_f = f_f32[::sy, ::sx]
                sub_pos = np.isfinite(sub_f) & (sub_f > FLAT_ZERO_THRESHOLD)
                total_px = max(1, sub_f.size)
                valid_px_count = int(np.count_nonzero(sub_pos))
                valid_ratio = float(valid_px_count) / float(total_px)
                if valid_px_count > 0:
                    f_valid_vals = sub_f[sub_pos]
                    f_med = float(np.median(f_valid_vals))
                    f_mean = float(np.mean(f_valid_vals))
                    f_min = float(np.min(f_valid_vals))
                    f_max = float(np.max(f_valid_vals))
                else:
                    f_med, f_mean, f_min, f_max = 0.0, 0.0, 0.0, 0.0
            else:
                total_px = max(1, f_f32.size)
                valid_px_count = int(np.count_nonzero(pos_mask))
                valid_ratio = float(valid_px_count) / float(total_px)
                if valid_px_count > 0:
                    f_valid_vals = f_f32[pos_mask]
                    f_med = float(np.median(f_valid_vals))
                    f_mean = float(np.mean(f_valid_vals))
                    f_min = float(np.min(f_valid_vals))
                    f_max = float(np.max(f_valid_vals))
                else:
                    f_med, f_mean, f_min, f_max = 0.0, 0.0, 0.0, 0.0

            # Sebuah frame flat dianggap valid bila memiliki pencahayaan positif (>10% piksel) dan median > 0
            is_frame_valid = (valid_ratio >= 0.10) and (f_med > FLAT_ZERO_THRESHOLD)
            frame_stats.append({
                "frame_index": f_idx,
                "is_valid": is_frame_valid,
                "valid_ratio": valid_ratio,
                "median": f_med,
                "mean": f_mean,
                "min": f_min,
                "max": f_max,
            })

            if not is_frame_valid:
                continue

            valid_frame_indices.append(f_idx)

            if can_store_all_in_memory:
                valid_frames_data.append(f_f32)

            # Akumulasi NaN-safe (hanya piksel finite & positif yang ditambahkan ke pembagi)
            safe_frame_vals = np.where(pos_mask, f_f32, 0.0)
            sum_acc += safe_frame_vals
            valid_pixel_counts += pos_mask.astype(np.int32)

        n_valid = len(valid_frame_indices)
        if n_valid == 0:
            raise StackingError(
                f"Master Flat '{src_desc}' tidak valid karena seluruh {n_frames} frame flat bernilai <= 0 atau NaN "
                "(seluruh frame gelap total, median=0.0). Pastikan berkas sequence flat direkam dengan pencahayaan homogen yang memadai."
            )

        if n_valid < n_frames:
            dropped = n_frames - n_valid
            warnings.append(
                f"Flat Frame Sequence: {dropped} frame dilewati karena gelap total / tidak valid. "
                f"Master Flat berhasil dibentuk dari {n_valid} frame flat yang valid."
            )

        # Bentuk SATU Master Flat dari seluruh frame valid
        if can_store_all_in_memory and n_valid >= 3:
            # Gunakan Sigma-Clipped Mean pada seluruh frame valid
            cube = np.stack(valid_frames_data, axis=0)
            med = np.median(cube, axis=0)
            mad = np.median(np.abs(cube - med[np.newaxis, ...]), axis=0)
            sigma = 1.4826 * mad
            fallback_sigma = np.maximum(1e-5, 1e-4 * np.abs(med))
            eff_sigma = np.where(sigma > 1e-6, sigma, fallback_sigma)
            keep = np.abs(cube - med[np.newaxis, ...]) <= (3.0 * eff_sigma[np.newaxis, ...])
            kept_count = np.sum(keep, axis=0)
            valid_combine = kept_count >= max(1, int(math.ceil(0.5 * n_valid)))
            sum_kept = np.sum(np.where(keep, cube, 0.0), axis=0, dtype=np.float64)
            safe_denom = np.maximum(kept_count, 1).astype(np.float64)
            combined_f32 = np.where(valid_combine, sum_kept / safe_denom, med).astype(np.float32)
        elif can_store_all_in_memory and n_valid < 3:
            cube = np.stack(valid_frames_data, axis=0)
            combined_f32 = np.mean(cube, axis=0).astype(np.float32)
        else:
            # Streaming mean nan-safe dari frame-frame valid
            has_valid_pixels = valid_pixel_counts > 0
            safe_denom = np.maximum(valid_pixel_counts, 1).astype(np.float64)
            combined_f32 = np.where(has_valid_pixels, sum_acc / safe_denom, 0.0).astype(np.float32)

        if validate_flat_characteristics:
            warnings.extend(
                _validate_flat_optical_characteristics(
                    combined_f32, src_desc, is_sequence_source=True
                )
            )

        combined_f32.flags.writeable = False
        is_cfa, cfa_pat = _extract_cfa_info(ref_info)
        preview_qimg = array_to_preview_qimage(combined_f32)

        fmt_base = ref_info.file_format or unique_paths[0].suffix.lstrip(".").upper()
        if ref_info.raw_metadata is not None:
            fmt_base = f"RAW ({ref_info.file_format})"
        flat_fmt = f"{fmt_base} Sequence ({n_frames} frame)"

        is_lossy = bool(_check_lossy_warning(ref_info))

        return LoadedMasterFlat(
            scientific_data=combined_f32,
            preview=preview_qimg,
            info=ref_info,
            source_description=src_desc,
            source_paths=unique_paths,
            flat_format=flat_fmt,
            flat_input_type="SEQUENCE",
            frame_count=n_frames,
            width=width,
            height=height,
            channels=channels,
            dtype_str=ref_info.dtype_str or "float32",
            bit_depth=ref_info.original_bit_depth,
            is_cfa_mosaic=is_cfa,
            cfa_pattern_str=cfa_pat,
            exif_orientation=ref_info.exif_orientation,
            saturation_ceiling=sat_ceiling,
            is_lossy_source=is_lossy,
            warnings=tuple(warnings),
        )
    finally:
        if owns_sm:
            sm.clear()


def load_master_flat_auto(
    master_flat: (
        LoadedMasterFlat
        | np.ndarray
        | str
        | Path
        | Sequence[str | Path]
        | SequenceManager
    ),
    *,
    page_index: int | None = None,
    hdu_index: int | None = None,
    endianness_policy: str = "siril_default",
    validate_flat_characteristics: bool = True,
    flat_info: ImageInfo | None = None,
) -> LoadedMasterFlat:
    """Memuat berbagai bentuk input Master Flat ke objek ``LoadedMasterFlat`` yang seragam."""
    if isinstance(master_flat, LoadedMasterFlat):
        return master_flat

    if isinstance(master_flat, SequenceManager):
        return load_master_flat_from_sequence(
            master_flat,
            source_kind="auto",
            endianness_policy=endianness_policy,
            validate_flat_characteristics=validate_flat_characteristics,
        )

    if isinstance(master_flat, np.ndarray):
        arr = master_flat
        if arr.ndim == 2:
            h, w = arr.shape
            ch = 1
        elif arr.ndim == 3 and arr.shape[2] == 3:
            h, w, ch = arr.shape
        else:
            raise StackingError(
                f"Dimensi array Master Flat tidak didukung (ndim={arr.ndim}, shape={arr.shape}); "
                "harus 2D (Monokrom/CFA) atau 3D (RGB)."
            )
        warnings: list[str] = []
        if validate_flat_characteristics:
            warnings.extend(
                _validate_flat_optical_characteristics(
                    arr, "Array Master Flat di memori", is_sequence_source=False
                )
            )
        sat_ceiling = _determine_saturation_ceiling(arr, flat_info)
        is_cfa, cfa_pat = _extract_cfa_info(flat_info)
        sci_f32 = np.array(arr, dtype=np.float32, copy=True)
        sci_f32.flags.writeable = False
        preview_qimg = array_to_preview_qimage(sci_f32)
        return LoadedMasterFlat(
            scientific_data=sci_f32,
            preview=preview_qimg,
            info=flat_info,
            source_description=flat_info.file_name if flat_info is not None else "Array Master Flat di memori",
            source_paths=(flat_info.path,) if flat_info is not None else (),
            flat_format=flat_info.file_format if flat_info is not None else f"ARRAY ({arr.dtype})",
            flat_input_type="ARRAY",
            frame_count=1,
            width=w,
            height=h,
            channels=ch,
            dtype_str=flat_info.dtype_str if (flat_info and flat_info.dtype_str) else str(arr.dtype),
            bit_depth=flat_info.original_bit_depth if flat_info is not None else (arr.dtype.itemsize * 8),
            is_cfa_mosaic=is_cfa,
            cfa_pattern_str=cfa_pat,
            exif_orientation=flat_info.exif_orientation if flat_info is not None else "Normal (tanpa rotasi)",
            saturation_ceiling=sat_ceiling,
            is_lossy_source=False,
            warnings=tuple(warnings),
        )

    if isinstance(master_flat, (str, Path)):
        p = Path(master_flat)
        if not p.exists():
            raise StackingError(f"Berkas atau folder Master Flat tidak ditemukan: {p}")
        if p.is_dir():
            return load_master_flat_from_sequence(
                p,
                source_kind="folder",
                endianness_policy=endianness_policy,
                validate_flat_characteristics=validate_flat_characteristics,
            )
        ext = p.suffix.lower().lstrip(".")
        if ext in VIDEO_EXTENSIONS:
            return load_master_flat_from_sequence(
                p,
                source_kind="video",
                endianness_policy=endianness_policy,
                validate_flat_characteristics=validate_flat_characteristics,
            )
        if ext in SER_EXTENSIONS:
            return load_master_flat_from_sequence(
                p,
                source_kind="ser",
                endianness_policy=endianness_policy,
                validate_flat_characteristics=validate_flat_characteristics,
            )
        return load_single_master_flat(
            p,
            page_index=page_index,
            hdu_index=hdu_index,
            validate_flat_characteristics=validate_flat_characteristics,
        )

    if isinstance(master_flat, Iterable):
        paths = [Path(item) for item in master_flat]
        if len(paths) == 1 and paths[0].is_file():
            ext = paths[0].suffix.lower().lstrip(".")
            if ext not in VIDEO_EXTENSIONS and ext not in SER_EXTENSIONS:
                return load_single_master_flat(
                    paths[0],
                    page_index=page_index,
                    hdu_index=hdu_index,
                    validate_flat_characteristics=validate_flat_characteristics,
                )
        return load_master_flat_from_sequence(
            paths,
            source_kind="files",
            endianness_policy=endianness_policy,
            validate_flat_characteristics=validate_flat_characteristics,
        )

    raise StackingError(
        "Master Flat harus berupa jalur berkas, daftar berkas sequence, SequenceManager, "
        "LoadedMasterFlat, atau array NumPy yang valid."
    )


def check_flat_compatibility(
    loaded_flat: LoadedMasterFlat,
    *,
    expected_height: int,
    expected_width: int,
    expected_channels: int,
    expected_is_cfa: bool = False,
    expected_cfa_pattern: str | None = None,
    reference_bit_depth: int | None = None,
    reference_orientation: str | None = None,
    reference_info: ImageInfo | None = None,
) -> FlatCompatibilityCheckResult:
    """Memeriksa kompatibilitas struktural, optik, kanal, dan CFA antara Master Flat dan Light Frame."""
    reasons: list[str] = []
    warnings: list[str] = list(loaded_flat.warnings)

    flat_info = loaded_flat.info if isinstance(loaded_flat.info, ImageInfo) else None

    # 1. Validasi dimensi aktif (width x height)
    if (loaded_flat.height, loaded_flat.width) != (expected_height, expected_width):
        reasons.append(
            f"Ukuran Master Flat ({loaded_flat.width}×{loaded_flat.height} px) tidak cocok "
            f"dengan ukuran frame sequence ({expected_width}×{expected_height} px)."
        )

    # 2. Validasi dimensi sensor tersimpan / crop apabila kedua ImageInfo tersedia
    if flat_info is not None and reference_info is not None:
        if (flat_info.stored_width, flat_info.stored_height) != (
            reference_info.stored_width,
            reference_info.stored_height,
        ):
            reasons.append(
                f"Dimensi sensor penuh/crop Master Flat ({flat_info.stored_width}×{flat_info.stored_height} px) "
                f"berbeda dari frame sequence ({reference_info.stored_width}×{reference_info.stored_height} px)."
            )

    # 3. Validasi orientasi
    ref_orient = (
        reference_orientation
        if reference_orientation is not None
        else (reference_info.exif_orientation if reference_info is not None else None)
    )
    if (
        ref_orient is not None
        and flat_info is not None
        and loaded_flat.exif_orientation != ref_orient
    ):
        reasons.append(
            f"Orientasi Master Flat ('{loaded_flat.exif_orientation}') berbeda dari "
            f"orientasi frame sequence ('{ref_orient}')."
        )

    # 4. Validasi jumlah kanal & jenis warna (Monokrom vs RGB)
    if loaded_flat.channels != expected_channels:
        flat_kind = "Monokrom (1 kanal)" if loaded_flat.channels == 1 else f"RGB ({loaded_flat.channels} kanal)"
        seq_kind = "Monokrom (1 kanal)" if expected_channels == 1 else f"RGB ({expected_channels} kanal)"
        reasons.append(
            f"Jumlah kanal Master Flat ({flat_kind}) tidak cocok dengan frame sequence ({seq_kind}). "
            "Monokrom dan RGB tidak dapat dicampur."
        )

    # 5. Validasi domain sensor CFA & pola Bayer (TAHAP 6)
    # Catatan: Bila loaded_flat dibuat dari array mentah tanpa ImageInfo dan bukan sequence,
    # izinkan mewarisi status CFA dari sequence kecuali flat_info tersedia secara eksplisit.
    has_explicit_sensor_domain = (flat_info is not None) or (loaded_flat.flat_input_type != "ARRAY")
    if has_explicit_sensor_domain:
        if expected_is_cfa != loaded_flat.is_cfa_mosaic:
            flat_dom = (
                f"Bayer CFA ({loaded_flat.cfa_pattern_str or 'Mosaic'})"
                if loaded_flat.is_cfa_mosaic
                else ("Monokrom Non-CFA" if loaded_flat.channels == 1 else "RGB Terdemosaik")
            )
            seq_dom = (
                f"Bayer CFA ({expected_cfa_pattern or 'Mosaic'})"
                if expected_is_cfa
                else ("Monokrom Non-CFA" if expected_channels == 1 else "RGB")
            )
            reasons.append(
                f"Domain sensor Master Flat ({flat_dom}) tidak cocok dengan frame sequence ({seq_dom}). "
                "Data Bayer CFA harus dikalibrasi dengan Master Flat Bayer CFA berpola sama."
            )
        elif (
            expected_is_cfa
            and expected_cfa_pattern
            and loaded_flat.cfa_pattern_str
            and expected_cfa_pattern.upper() != loaded_flat.cfa_pattern_str.upper()
        ):
            reasons.append(
                f"Pola CFA Master Flat ({loaded_flat.cfa_pattern_str}) berbeda dari pola CFA "
                f"frame sequence ({expected_cfa_pattern})."
            )

    # 6. Bandingkan metadata kamera/instrumen bila tersedia (peringatan ilmiah)
    flat_inst = _extract_instrument_or_camera(flat_info)
    ref_inst = _extract_instrument_or_camera(reference_info)
    if flat_inst and ref_inst and flat_inst.lower() != ref_inst.lower():
        warnings.append(
            f"Instrumen/kamera pada Master Flat ('{flat_inst}') berbeda dari frame sequence ('{ref_inst}')."
        )

    # 7. Perbedaan bit depth / dtype diperbolehkan lewat konversi float32 terkontrol, dicatat sebagai info
    ref_bd = (
        reference_bit_depth
        if reference_bit_depth is not None
        else (reference_info.original_bit_depth if reference_info is not None else None)
    )
    if (
        ref_bd is not None
        and loaded_flat.bit_depth is not None
        and loaded_flat.bit_depth != ref_bd
    ):
        warnings.append(
            f"Bit depth Master Flat ({loaded_flat.bit_depth}-bit) berbeda dari frame referensi "
            f"({ref_bd}-bit); kalibrasi tetap valid melalui normalisasi floating-point (float32)."
        )

    is_compat = len(reasons) == 0
    if is_compat:
        status_txt = "KOMPATIBEL"
    else:
        status_txt = "TIDAK KOMPATIBEL: " + " ".join(reasons)

    return FlatCompatibilityCheckResult(
        is_compatible=is_compat,
        status_text=status_txt,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def validate_and_prepare_master_flat(
    master_flat: (
        LoadedMasterFlat
        | np.ndarray
        | str
        | Path
        | Sequence[str | Path]
        | SequenceManager
    ),
    *,
    expected_height: int,
    expected_width: int,
    expected_channels: int,
    expected_is_cfa: bool = False,
    expected_cfa_pattern: str | None = None,
    reference_bit_depth: int | None = None,
    reference_orientation: str | None = None,
    reference_info: ImageInfo | None = None,
    flat_info: ImageInfo | None = None,
    validate_flat_characteristics: bool = True,
    check_compatibility: bool = False,
) -> tuple[np.ndarray, FlatCalibrationReport]:
    """Menyiapkan dan menormalisasi Master Flat (float32, median=1.0) tanpa preflight gates yang menghalangi.

    Rumus normalisasi:
        ``F_norm(x,y) = F(x,y) / median(F_valid)``
    Untuk citra RGB 3-kanal, normalisasi dihitung per-kanal warna.
    Untuk citra Bayer CFA 2D, normalisasi dihitung per-subkanal 2×2 agar keseimbangan
    gain kanal Bayer tidak terdistorsi.
    """
    loaded_flat = load_master_flat_auto(
        master_flat,
        validate_flat_characteristics=validate_flat_characteristics,
        flat_info=flat_info,
    )

    compat = check_flat_compatibility(
        loaded_flat,
        expected_height=expected_height,
        expected_width=expected_width,
        expected_channels=expected_channels,
        expected_is_cfa=expected_is_cfa,
        expected_cfa_pattern=expected_cfa_pattern,
        reference_bit_depth=reference_bit_depth,
        reference_orientation=reference_orientation,
        reference_info=reference_info,
    )
    if check_compatibility and not compat.is_compatible:
        raise StackingError(
            "Master Flat tidak kompatibel dengan sequence light frame:\n"
            + "\n".join(f"• {r}" for r in compat.reasons)
        )

    warnings: list[str] = list(compat.warnings)
    work = np.asarray(loaded_flat.scientific_data, dtype=np.float64)

    (
        global_median,
        global_mean,
        invalid_pixel_count,
        zero_or_neg_count,
        non_finite_count,
        saturated_count,
        invalid_mask_2d,
    ) = compute_flat_pixel_statistics(
        work,
        saturation_ceiling=loaded_flat.saturation_ceiling,
        is_cfa_mosaic=expected_is_cfa,
    )

    if global_median <= 0.0 or not math.isfinite(global_median):
        raise StackingError(
            f"Master Flat '{loaded_flat.source_description}' tidak valid karena seluruh nilai piksel "
            "bernilai <= 0, NaN, atau tidak memiliki piksel valid."
        )

    # Mask elemen yang layak menjadi anggota F_valid untuk perhitungan median(F_valid)
    finite_elem = np.isfinite(work)
    pos_elem = finite_elem & (work > FLAT_ZERO_THRESHOLD)
    if loaded_flat.saturation_ceiling is not None and loaded_flat.saturation_ceiling > 0.0:
        not_sat_elem = work < loaded_flat.saturation_ceiling
    else:
        not_sat_elem = np.ones_like(finite_elem, dtype=bool)

    valid_for_median = pos_elem & not_sat_elem
    if not np.any(valid_for_median):
        valid_for_median = pos_elem

    norm_flat = np.ones_like(work, dtype=np.float64)
    f_ch = loaded_flat.channels

    if f_ch == 3:
        # Normalisasi per-kanal R, G, B menggunakan median(F_valid, c)
        for c in range(3):
            plane = work[..., c]
            mask_c = valid_for_median[..., c]
            if not np.any(mask_c):
                mask_c = pos_elem[..., c]
            if not np.any(mask_c):
                raise StackingError(
                    f"Kanal warna ke-{c + 1} pada Master Flat '{loaded_flat.source_description}' "
                    "bernilai <= 0 atau NaN seluruhnya."
                )
            med_c = float(np.median(plane[mask_c]))
            norm_flat[..., c] = plane / med_c
    elif expected_is_cfa:
        # Normalisasi per-subkanal 2x2 pada mosaik CFA menggunakan median(F_valid_sub)
        for py in (0, 1):
            for px in (0, 1):
                sub = work[py::2, px::2]
                mask_sub = valid_for_median[py::2, px::2]
                if not np.any(mask_sub):
                    mask_sub = pos_elem[py::2, px::2]
                if np.any(mask_sub):
                    med_sub = float(np.median(sub[mask_sub]))
                    norm_flat[py::2, px::2] = sub / med_sub
                else:
                    norm_flat[py::2, px::2] = sub / global_median
    else:
        norm_flat = work / global_median

    # Proteksi pembagian nol, nilai negatif, NaN, atau Infinity
    bad_divisor_mask = (~np.isfinite(norm_flat)) | (norm_flat <= FLAT_ZERO_THRESHOLD)
    protected_count = int(np.count_nonzero(bad_divisor_mask))
    if protected_count > 0:
        norm_flat = np.where(bad_divisor_mask, 1.0, norm_flat)
        warnings.append(
            f"Master Flat memiliki {protected_count} sampel piksel bernilai <= {FLAT_ZERO_THRESHOLD} "
            "atau non-finite; piksel tersebut dilindungi dengan pembagi netral 1.0 agar bebas division by zero."
        )

    if saturated_count > 0:
        warnings.append(
            f"Master Flat memiliki {saturated_count} piksel jenuh (saturated >= {loaded_flat.saturation_ceiling:g}); "
            "piksel tersebut ditandai pada invalid-pixel mask."
        )

    out_flat = norm_flat.astype(np.float32)
    out_flat.flags.writeable = False

    mask_copy = np.array(invalid_mask_2d, dtype=bool, copy=True)
    mask_copy.flags.writeable = False

    flat_is_cfa = loaded_flat.is_cfa_mosaic if flat_info is not None else expected_is_cfa
    flat_cfa_pat = loaded_flat.cfa_pattern_str if flat_info is not None else expected_cfa_pattern

    report = FlatCalibrationReport(
        applied=True,
        source_description=loaded_flat.source_description,
        width=loaded_flat.width,
        height=loaded_flat.height,
        channels=f_ch,
        is_cfa_mosaic=flat_is_cfa,
        cfa_pattern_str=flat_cfa_pat,
        flat_mean_before_norm=global_mean,
        protected_zero_pixels_count=protected_count,
        warnings=tuple(warnings),
        flat_format=loaded_flat.flat_format,
        flat_input_type=loaded_flat.flat_input_type,
        flat_frame_count=loaded_flat.frame_count,
        normalization_method=NORMALIZATION_FORMULA_TEXT,
        flat_median_before_norm=global_median,
        invalid_pixel_count=invalid_pixel_count,
        zero_or_negative_pixel_count=zero_or_neg_count,
        non_finite_pixel_count=non_finite_count,
        saturated_pixel_count=saturated_count,
        calibration_status="DITERAPKAN",
        not_applied_reason=None,
        invalid_pixel_mask=mask_copy,
    )
    return out_flat, report


def build_unapplied_flat_report(reason: str) -> FlatCalibrationReport:
    """Membuat laporan eksplisit ketika kalibrasi flat tidak diterapkan beserta alasannya."""
    return FlatCalibrationReport(
        applied=False,
        source_description="Tidak digunakan",
        width=0,
        height=0,
        channels=0,
        is_cfa_mosaic=False,
        cfa_pattern_str=None,
        flat_mean_before_norm=0.0,
        protected_zero_pixels_count=0,
        warnings=(),
        flat_format="-",
        flat_input_type="NONE",
        flat_frame_count=0,
        normalization_method=NORMALIZATION_FORMULA_TEXT,
        flat_median_before_norm=0.0,
        invalid_pixel_count=0,
        zero_or_negative_pixel_count=0,
        non_finite_pixel_count=0,
        saturated_pixel_count=0,
        calibration_status=f"TIDAK DITERAPKAN ({reason})",
        not_applied_reason=reason,
        invalid_pixel_mask=None,
    )


def apply_flat_calibration(
    scientific_frame_float32: np.ndarray,
    normalized_flat: np.ndarray,
) -> np.ndarray:
    """Membagi satu light frame float32 dengan Master Flat ternormalisasi tanpa mengubah input asli.

    Rumus (TAHAP 5):
        ``I_corrected(x,y) = I_original(x,y) / F_norm(x,y)``
    Nilai negatif pada ``scientific_frame_float32`` tetap dipertahankan secara linear.
    """
    if scientific_frame_float32.shape != normalized_flat.shape:
        raise StackingError(
            f"Dimensi light frame ({scientific_frame_float32.shape}) tidak sesuai dengan "
            f"Master Flat ({normalized_flat.shape})."
        )
    # Pembagian langsung float32 terakselerasi vektor AVX2 tanpa overhead alokasi float64
    f_in = np.asarray(scientific_frame_float32, dtype=np.float32)
    f_flat = np.asarray(normalized_flat, dtype=np.float32)
    return (f_in / f_flat).astype(np.float32)


def run_flat_calibration_on_sequence(
    sequence_manager: SequenceManager,
    master_flat: (
        LoadedMasterFlat
        | np.ndarray
        | str
        | Path
        | Sequence[str | Path]
        | SequenceManager
    ),
    *,
    progress_callback: Callable[[int, int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[list[np.ndarray], FlatCalibrationReport]:
    """Menerapkan kalibrasi Master Flat secara langsung pada seluruh light frame di SequenceManager.

    Rumus tervalidasi:
        ``F_norm(x, y) = F(x, y) / median(F_valid)``
        ``I_cal(x, y) = I_light(x, y) / F_norm(x, y)``

    Tanpa preflight checks yang menghalangi proses. Bila dimensi array tidak sesuai
    saat pembagian, dilempar StackingError runtime yang ringkas.
    """
    if cancel_check is not None and cancel_check():
        raise StackingCancelledError("Kalibrasi Flat dibatalkan oleh pengguna.")

    total_frames = sequence_manager.frame_count
    if total_frames == 0:
        raise StackingError("Sequence kosong; tidak ada frame untuk dikalibrasi.")

    first_loaded = sequence_manager.load_frame(0)
    ref_info = first_loaded.info
    first_data = np.asarray(first_loaded.scientific_data, dtype=np.float32)
    h, w = int(first_data.shape[0]), int(first_data.shape[1])
    ch = int(first_data.shape[2]) if first_data.ndim == 3 else 1
    is_cfa, cfa_pat = _extract_cfa_info(ref_info)

    norm_flat, report = validate_and_prepare_master_flat(
        master_flat,
        expected_height=h,
        expected_width=w,
        expected_channels=ch,
        expected_is_cfa=is_cfa,
        expected_cfa_pattern=cfa_pat,
        reference_info=ref_info,
        check_compatibility=False,
    )

    calibrated_frames: list[np.ndarray] = []
    for idx in range(total_frames):
        if cancel_check is not None and cancel_check():
            raise StackingCancelledError("Kalibrasi Flat dibatalkan oleh pengguna.")
        if progress_callback is not None:
            progress_callback(idx + 1, total_frames, f"Mengalibrasi light frame #{idx + 1}/{total_frames}...")

        loaded = sequence_manager.load_frame(idx)
        raw_f32 = np.asarray(loaded.scientific_data, dtype=np.float32)
        cal = apply_flat_calibration(raw_f32, norm_flat)
        calibrated_frames.append(cal)

    return calibrated_frames, report
