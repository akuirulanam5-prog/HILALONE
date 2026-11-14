"""Mesin utama Automatic Stacking Engine HILALONE (Sub-Tahap 3A).

Mendukung tiga profil berbasis konfigurasi (``STACKING_PROFILE_CONFIGS``):
  * ``BASIC``  : *Streaming Arithmetic Mean* (1 akumulator ``float64`` di RAM).
  * ``MEDIUM`` : *Iterative Sigma-Clipped Mean* berbasis Median & MAD per-piksel.
  * ``HIGH``   : *Quality-Weighted Robust Stacking* (bobot invers varians derau
                 terbatas + penolakan outlier Median & MAD).

Jaminan kejujuran ilmiah (AGENTS.md Bagian 4, 5, 6, 8):
  1. Selalu memproses ``scientific_data`` asli dalam ``float32``/``float64``
     (tidak pernah memakai ``preview`` 8-bit).
  2. Tidak pernah melakukan registrasi/alignment, dark/bias, noise reduction,
     atau sharpening otomatis.
  3. Tidak pernah memotong (*clip*) nilai piksel negatif pada data floating-point.
  4. Pada citra RGB, keputusan penolakan outlier dan bobot kualitas dihitung pada
     luminans bersama lalu diterapkan secara serempak ke kanal R, G, dan B agar
     tidak terjadi pergeseran warna (FR-ST-03a).
  5. Mendukung pemrosesan per-strip baris (*bounded-memory strip processing*),
     pelaporan progres (``progress_callback``), dan pembatalan aman
     (``cancel_check``).
"""

from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
import tempfile
from typing import Callable

import numpy as np

from hilalone.input_manager.image_reader import ImageReadError
from hilalone.input_manager.models import FrameStatus, to_controlled_float32
from hilalone.input_manager.preview_builder import array_to_preview_qimage
from hilalone.input_manager.sequence_manager import SequenceManager
from hilalone.processing.stacking.flat_calibration import (
    apply_flat_calibration,
    validate_and_prepare_master_flat,
)
from hilalone.processing.stacking.models import (
    ExcludedFrameRecord,
    FlatCalibrationReport,
    FrameQualityMetrics,
    PreStackValidationReport,
    StackingAlgorithm,
    StackingCancelledError,
    StackingConfirmationRequiredError,
    StackingError,
    StackingProfile,
    StackingProfileConfig,
    StackingResult,
    get_stacking_profile_config,
)
from hilalone.processing.stacking.validator import (
    DEFAULT_SHIFT_THRESHOLD_PX,
    extract_frame_cfa_info,
    extract_luminance_proxy_readonly,
    measure_sequence_position_stability,
    validate_sequence_for_stacking,
)

ProgressCallback = Callable[[int, int, str], None]
CancelCheckCallback = Callable[[], bool]


def _check_cancelled(cancel_check: CancelCheckCallback | None) -> None:
    if cancel_check is not None and cancel_check():
        raise StackingCancelledError("Proses stacking dibatalkan oleh pengguna.")


def _notify_progress(
    progress_callback: ProgressCallback | None,
    current_step: int,
    total_steps: int,
    message: str,
) -> None:
    if progress_callback is not None:
        progress_callback(current_step, max(1, total_steps), message)


def compute_single_frame_quality_metrics(
    scientific_data: np.ndarray,
    *,
    frame_index: int,
    file_name: str,
    is_cfa_mosaic: bool = False,
) -> tuple[float, float, float]:
    """Menghitung (background_median, robust_noise_sigma, gradient_energy) secara cepat & hemat memori.

    Estimasi derau menggunakan MAD dari operator Laplacian 2D diskrit:
      ``L_lap = L(y-1,x) + L(y+1,x) + L(y,x-1) + L(y,x+1) - 4*L(y,x)``
    sehingga gradien langit linear tereliminasi dan menyisakan derau frekuensi tinggi
    sensor dengan faktor normalisasi ``sqrt(20)``.
    """
    lum, _ = extract_luminance_proxy_readonly(scientific_data, is_cfa_mosaic=is_cfa_mosaic)
    h, w = lum.shape[:2]

    # Subsampling terkontrol jika frame berukuran besar (> 300x300) agar evaluasi metrik super cepat (< 12 ms)
    if h > 300 or w > 300:
        sy = max(1, h // 250)
        sx = max(1, w // 250)
        lum_work = np.ascontiguousarray(lum[::sy, ::sx], dtype=np.float32)
    else:
        lum_work = np.ascontiguousarray(lum, dtype=np.float32)

    finite = lum_work[np.isfinite(lum_work)]
    if finite.size == 0:
        return 0.0, 1.0, 0.0

    bg_median = float(np.median(finite))

    if lum_work.shape[0] >= 3 and lum_work.shape[1] >= 3:
        lap = (
            lum_work[:-2, 1:-1]
            + lum_work[2:, 1:-1]
            + lum_work[1:-1, :-2]
            + lum_work[1:-1, 2:]
            - 4.0 * lum_work[1:-1, 1:-1]
        )
        lap_med = float(np.median(lap))
        mad_lap = float(np.median(np.abs(lap - lap_med)))
        noise_sigma = (1.4826 * mad_lap) / math.sqrt(20.0)

        gy = 0.5 * (lum_work[2:, 1:-1] - lum_work[:-2, 1:-1])
        gx = 0.5 * (lum_work[1:-1, 2:] - lum_work[1:-1, :-2])
        grad_energy = float(np.mean(np.hypot(gx, gy)))
    else:
        mad_val = float(np.median(np.abs(finite - bg_median)))
        noise_sigma = 1.4826 * mad_val
        grad_energy = 0.0

    return bg_median, max(0.0, float(noise_sigma)), max(0.0, float(grad_energy))


def build_normalized_frame_weights(
    raw_metrics: list[tuple[int, str, float, float, float]],
    config: StackingProfileConfig,
) -> tuple[tuple[FrameQualityMetrics, ...], np.ndarray]:
    """Menyusun bobot kualitas ternormalisasi (jumlah bobot = 1.0) untuk seluruh frame aktif."""
    n = len(raw_metrics)
    if n == 0:
        raise StackingError("Tidak ada frame aktif untuk dihitung bobotnya.")

    if not config.use_quality_weights:
        uniform_w = 1.0 / float(n)
        records = tuple(
            FrameQualityMetrics(
                frame_index=idx,
                file_name=fname,
                background_median=bg,
                robust_noise_sigma=sig,
                gradient_energy=grad,
                raw_weight=1.0,
                normalized_weight=uniform_w,
            )
            for idx, fname, bg, sig, grad in raw_metrics
        )
        return records, np.full(n, uniform_w, dtype=np.float64)

    # Untuk profil HIGH: bobot invers varians derau (1 / sigma^2) dengan batas rasio aman
    sigmas = np.array([m[3] for m in raw_metrics], dtype=np.float64)
    positive_sigmas = sigmas[sigmas > 1e-9]
    if positive_sigmas.size == 0:
        # Semua frame memiliki derau ~0 (mis. frame sintetis bebas noise): bobot seragam
        raw_w = np.ones(n, dtype=np.float64)
    else:
        floor_sigma = max(1e-6, 0.1 * float(np.median(positive_sigmas)))
        clamped_sigmas = np.maximum(sigmas, floor_sigma)
        inv_var = 1.0 / (clamped_sigmas**2)
        med_w = float(np.median(inv_var))
        if med_w > 0.0:
            raw_w = np.clip(
                inv_var / med_w,
                config.weight_clamp_min,
                config.weight_clamp_max,
            )
        else:
            raw_w = np.ones(n, dtype=np.float64)

    w_sum = float(np.sum(raw_w))
    norm_w = raw_w / w_sum if w_sum > 0.0 else np.full(n, 1.0 / float(n), dtype=np.float64)

    records = tuple(
        FrameQualityMetrics(
            frame_index=raw_metrics[i][0],
            file_name=raw_metrics[i][1],
            background_median=raw_metrics[i][2],
            robust_noise_sigma=raw_metrics[i][3],
            gradient_energy=raw_metrics[i][4],
            raw_weight=float(raw_w[i]),
            normalized_weight=float(norm_w[i]),
        )
        for i in range(n)
    )
    return records, norm_w


def _stack_strip_robust(
    strip_cube: np.ndarray,
    frame_weights: np.ndarray,
    config: StackingProfileConfig,
    *,
    enable_clipping: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Menjalankan sigma-clipping (Median+MAD) dan rata-rata berbobot pada satu strip baris.

    Args:
        strip_cube: Array ``(N, strip_h, W)`` atau ``(N, strip_h, W, 3)`` bertipe ``float32``.
        frame_weights: Bobot per frame ``(N,)`` bertipe ``float64`` dengan jumlah ``1.0``.
        config: Konfigurasi profil stacking.
        enable_clipping: Apakah penolakan outlier dijalankan (True bila N >= min_frames_for_clipping).

    Returns:
        Tuple ``(stacked_strip_f32, rejected_count_u16, kept_count_u16)``.
    """
    n_frames = strip_cube.shape[0]
    strip_h = strip_cube.shape[1]
    width = strip_cube.shape[2]
    is_rgb = strip_cube.ndim == 4

    if not enable_clipping:
        w_norm = frame_weights / np.sum(frame_weights)
        if is_rgb:
            acc = np.tensordot(w_norm, strip_cube.astype(np.float64), axes=(0, 0))
        else:
            acc = np.tensordot(w_norm, strip_cube.astype(np.float64), axes=(0, 0))
        rej_map = np.zeros((strip_h, width), dtype=np.uint16)
        kept_map = np.full((strip_h, width), n_frames, dtype=np.uint16)
        return acc.astype(np.float32), rej_map, kept_map

    # Hitung luminans 3D (N, strip_h, W) dalam float32 untuk keputusan outlier bersama (FR-ST-03a)
    if is_rgb:
        lum_cube = (
            0.2126 * strip_cube[..., 0]
            + 0.7152 * strip_cube[..., 1]
            + 0.0722 * strip_cube[..., 2]
        ).astype(np.float32)
    else:
        lum_cube = strip_cube.astype(np.float32, copy=False)

    keep_mask = np.ones((n_frames, strip_h, width), dtype=bool)
    min_kept = max(3, int(math.ceil(config.min_kept_fraction * n_frames)))
    min_kept = min(min_kept, n_frames)

    for it in range(config.max_clip_iterations):
        if it == 0 or np.all(keep_mask):
            med = np.median(lum_cube, axis=0)
            diff = lum_cube - med[None, :, :]
            abs_dev = np.abs(diff)
            mad = np.median(abs_dev, axis=0)
            robust_sigma = 1.4826 * mad
            fallback_sigma = np.maximum(1e-5, 1e-4 * np.abs(med))
            effective_sigma = np.where(robust_sigma > 1e-9, robust_sigma, fallback_sigma)
        else:
            # Iterasi lanjutan (it > 0): perbarui estimasi pusat sinyal secara cepat dan akurat
            # menggunakan rata-rata terpotong (clipped mean) dari piksel yang lolos uji outlier.
            # Menghindari komputasi np.nanmedian yang berbiaya O(N log N) tinggi pada jutaan kolom.
            # Skala sebaran (effective_sigma) dipertahankan dari estimasi awal Median & MAD
            # yang kebal outlier hingga 50% (breakdown point 0.5) sesuai prinsip astronomi.
            kept_c = np.count_nonzero(keep_mask, axis=0)
            kept_safe = np.maximum(1, kept_c)
            med = np.sum(np.where(keep_mask, lum_cube, np.float32(0.0)), axis=0) / kept_safe
            diff = lum_cube - med[None, :, :]
            abs_dev = np.abs(diff)

        # Cek batas simpangan sigma: jika sigma_low == sigma_high (umumnya 3.0),
        # cek abs_dev <= high_bound secara instan tanpa alokasi ganda low/high &
        if config.sigma_low == config.sigma_high:
            in_bounds = abs_dev <= (config.sigma_high * effective_sigma[None, :, :])
        else:
            low_bound = -config.sigma_low * effective_sigma[None, :, :]
            high_bound = config.sigma_high * effective_sigma[None, :, :]
            in_bounds = (diff >= low_bound) & (diff <= high_bound)

        candidate_mask = keep_mask & in_bounds

        # Safeguard minimum sampel: jika suatu piksel menyisakan < min_kept sampel,
        # pertahankan min_kept sampel dengan simpangan terkecil terhadap median
        cand_counts = np.count_nonzero(candidate_mask, axis=0)
        underflow = cand_counts < min_kept
        if np.any(underflow):
            # Optimasi selektif: hanya urutkan kolom piksel yang benar-benar mengalami underflow
            uy, ux = np.where(underflow)
            sub_d = abs_dev[:, uy, ux]
            idx_part = np.argpartition(sub_d, min_kept, axis=0)[:min_kept]
            candidate_mask[:, uy, ux] = False
            np.put_along_axis(candidate_mask[:, uy, ux], idx_part, True, axis=0)

        if np.array_equal(candidate_mask, keep_mask):
            break
        keep_mask = candidate_mask

    kept_counts = np.count_nonzero(keep_mask, axis=0).astype(np.uint16)
    rejected_counts = (n_frames - kept_counts).astype(np.uint16)

    # Hitung rata-rata berbobot (HIGH) atau rata-rata aritmetika unweighted (MEDIUM)
    if config.use_quality_weights:
        w_3d = np.where(keep_mask, frame_weights[:, None, None], np.float32(0.0))
        w_sum = np.sum(w_3d, axis=0)
        w_sum_safe = np.where(w_sum > 0.0, w_sum, np.float32(1.0))

        if is_rgb:
            weighted_sum = np.sum(
                strip_cube * w_3d[..., None],
                axis=0,
            )
            stacked_strip = weighted_sum / w_sum_safe[..., None]
        else:
            weighted_sum = np.sum(
                strip_cube * w_3d,
                axis=0,
            )
            stacked_strip = weighted_sum / w_sum_safe
    else:
        # MEDIUM: Rata-rata terpotong langsung tanpa alokasi w_3d multi-ratus MB
        kept_safe = np.maximum(1, kept_counts)
        if is_rgb:
            unweighted_sum = np.sum(
                np.where(keep_mask[..., None], strip_cube, np.float32(0.0)),
                axis=0,
            )
            stacked_strip = unweighted_sum / kept_safe[..., None]
        else:
            unweighted_sum = np.sum(
                np.where(keep_mask, strip_cube, np.float32(0.0)),
                axis=0,
            )
            stacked_strip = unweighted_sum / kept_safe

    return stacked_strip.astype(np.float32), rejected_counts, kept_counts


class AutomaticStackingEngine:
    """Mesin penumpukan citra otomatis HILALONE untuk Multiple Images, Video, dan SER."""

    def __init__(
        self,
        *,
        max_working_memory_mb: int = 512,
        shift_threshold_px: float = DEFAULT_SHIFT_THRESHOLD_PX,
    ) -> None:
        self._max_working_memory_mb = max(1, int(max_working_memory_mb))
        self._shift_threshold_px = float(shift_threshold_px)

    @property
    def max_working_memory_mb(self) -> int:
        return self._max_working_memory_mb

    @property
    def shift_threshold_px(self) -> float:
        return self._shift_threshold_px

    def stack_sequence(
        self,
        sequence_manager: SequenceManager,
        profile: StackingProfile | str = StackingProfile.MEDIUM,
        *,
        master_flat: np.ndarray | str | Path | None = None,
        excluded_frame_indices: set[int] | None = None,
        allow_exclude_incompatible_and_error: bool = False,
        check_position_stability: bool = False,
        confirm_proceed_with_shift_risk: bool = True,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheckCallback | None = None,
    ) -> StackingResult:
        """Menjalankan validasi pra-stacking, flat opsional, dan stacking langsung tanpa gate stabilitas posisi.

        Args:
            sequence_manager: Instance ``SequenceManager`` yang sedang aktif.
            profile: Profil stacking (``BASIC``, ``MEDIUM``, atau ``HIGH``).
            master_flat: Opsional array atau jalur berkas Master Flat.
            excluded_frame_indices: Himpunan indeks frame (0-based) yang dikecualikan pengguna.
            allow_exclude_incompatible_and_error: Bila ``True``, frame berstatus ``INCOMPATIBLE``
                atau ``ERROR`` dikecualikan dengan catatan eksplisit. Bila ``False`` (default),
                engine akan melempar ``StackingConfirmationRequiredError`` agar tidak ada frame
                yang dilewati diam-diam.
            check_position_stability: Parameter legasi (selalu False; gate stabilitas posisi dihapus).
            confirm_proceed_with_shift_risk: Parameter legasi (selalu True; frame diproses langsung tanpa alignment).
            progress_callback: Callback progres ``(step, total, message)``.
            cancel_check: Callback pembatalan ``() -> bool``.
        """
        _check_cancelled(cancel_check)
        profile_config = get_stacking_profile_config(profile)

        # 1. Validasi struktural, CFA, bit depth, dan metadata
        validation = validate_sequence_for_stacking(
            sequence_manager.input_mode,
            sequence_manager.entries,
            excluded_frame_indices=excluded_frame_indices,
            allow_exclude_incompatible_and_error=allow_exclude_incompatible_and_error,
        )

        if validation.requires_user_confirmation:
            reasons = "\n".join(f"• {w}" for w in validation.structural_warnings[:8])
            raise StackingConfirmationRequiredError(
                "Terdapat frame yang gagal dibaca atau tidak kompatibel di dalam sequence:\n"
                f"{reasons}\n\n"
                "HILALONE tidak membuang frame secara diam-diam. Silakan konfirmasi pengecualian "
                "frame bermasalah (allow_exclude_incompatible_and_error=True) atau pilih daftar "
                "excluded_frame_indices terlebih dahulu."
            )

        included_indices = list(validation.included_frame_indices)
        if len(included_indices) < 2:
            raise StackingError(
                f"Stacking membutuhkan minimal 2 frame kompatibel yang aktif, tetapi saat ini hanya "
                f"tersedia {len(included_indices)} frame setelah pengecualian."
            )

        excluded_records = list(validation.excluded_frames)
        warnings: list[str] = list(validation.structural_warnings) + list(
            validation.metadata_warnings
        )
        notes: list[str] = []

        if validation.normalize_integers_to_unit:
            notes.append(
                "Sequence memiliki bit depth integer yang berbeda antar-frame; setiap frame "
                "dinormalisasi secara terkontrol ke skala linear float32 [0.0, 1.0]."
            )

        # 2. Validasi dan siapkan Master Flat opsional bila diberikan
        normalized_flat: np.ndarray | None = None
        flat_report: FlatCalibrationReport | None = None
        if master_flat is not None:
            ref_entry = sequence_manager.entries[validation.reference_frame_index or included_indices[0]]
            ref_info = ref_entry.info
            normalized_flat, flat_report = validate_and_prepare_master_flat(
                master_flat,
                expected_height=validation.height,
                expected_width=validation.width,
                expected_channels=validation.channels,
                expected_is_cfa=validation.is_cfa_mosaic,
                expected_cfa_pattern=validation.cfa_pattern_str,
                reference_bit_depth=ref_info.original_bit_depth if ref_info else None,
                reference_orientation=ref_info.exif_orientation if ref_info else None,
                reference_info=ref_info,
            )
            warnings.extend(flat_report.warnings)
            notes.append(
                f"Kalibrasi Master Flat opsional DITERAPKAN dari '{flat_report.source_description}' "
                f"(format={flat_report.flat_format}, dimensi={flat_report.width}×{flat_report.height}, "
                f"normalisasi={flat_report.normalization_method}, median awal={flat_report.flat_median_before_norm:.2f}, "
                f"invalid pixels={flat_report.invalid_pixel_count})."
            )
        else:
            notes.append(
                "Kalibrasi Master Flat: TIDAK DITERAPKAN (Opsi Kalibrasi Flat tidak diaktifkan / Master Flat tidak disediakan)."
            )

        # Helper untuk memuat satu frame ilmiah ke float32 (beserta flat bila aktif)
        def _load_frame_f32(idx: int) -> tuple[np.ndarray, str, bool]:
            _check_cancelled(cancel_check)
            try:
                loaded = sequence_manager.load_frame(idx)
            except ImageReadError as exc:
                raise StackingError(
                    f"Gagal membaca data piksel Frame #{idx + 1}: {exc}"
                ) from exc
            if loaded.scientific_data is None:
                raise StackingError(
                    f"Frame #{idx + 1} ('{loaded.info.file_name}') tidak memiliki data ilmiah."
                )
            arr_f32 = to_controlled_float32(
                loaded.scientific_data,
                normalize_integers=validation.normalize_integers_to_unit,
            )
            if normalized_flat is not None:
                arr_f32 = apply_flat_calibration(arr_f32, normalized_flat)
            is_cfa, _ = extract_frame_cfa_info(loaded.info)
            return arr_f32, loaded.info.file_name, is_cfa

        # 3. Kestabilan Posisi: Dinonaktifkan sesuai keputusan pengguna (MVP 1.0)
        # Seluruh frame diproses langsung tanpa pengukuran pergeseran dan tanpa alignment geometris.
        notes.append("Position stability precheck: DISABLED (seluruh frame diproses langsung tanpa gate stabilitas posisi).")
        notes.append("Registration/alignment: NOT PERFORMED (aturan ilmiah MVP 1.0 tanpa pergeseran geometris/translasi piksel).")
        notes.append("Flat compatibility preflight: DISABLED (evaluasi kompatibilitas dimensi terjadi saat operasi pembagian).")

        n_active = len(included_indices)
        height = validation.height
        width = validation.width
        channels = validation.channels

        # Tentukan algoritma efektif (fallback ke Arithmetic Mean bila N < min_frames_for_clipping)
        effective_algo = profile_config.algorithm
        enable_clipping = (
            profile_config.use_sigma_clipping
            and n_active >= profile_config.min_frames_for_clipping
        )
        if profile_config.use_sigma_clipping and not enable_clipping:
            effective_algo = (
                StackingAlgorithm.QUALITY_WEIGHTED_ROBUST
                if profile_config.use_quality_weights
                else StackingAlgorithm.ARITHMETIC_MEAN
            )
            notes.append(
                f"Jumlah frame aktif ({n_active}) kurang dari batas minimum sigma-clipping "
                f"({profile_config.min_frames_for_clipping} frame); penolakan outlier dilewati "
                "agar sinyal tidak terbuang secara keliru."
            )

        # 4. Jalur Eksekusi 1: BASIC (Single-Pass Streaming Arithmetic Mean)
        if (
            profile_config.profile == StackingProfile.BASIC
            and not profile_config.use_sigma_clipping
            and not profile_config.use_quality_weights
        ):
            acc_shape = (height, width) if channels == 1 else (height, width, channels)
            sum_acc = np.zeros(acc_shape, dtype=np.float64)
            raw_metrics_list: list[tuple[int, str, float, float, float]] = []
            included_names: list[str] = []

            for step_idx, frame_idx in enumerate(included_indices, start=1):
                _check_cancelled(cancel_check)
                arr_f32, fname, is_cfa = _load_frame_f32(frame_idx)
                included_names.append(fname)
                bg, sig, grad = compute_single_frame_quality_metrics(
                    arr_f32,
                    frame_index=frame_idx,
                    file_name=fname,
                    is_cfa_mosaic=is_cfa,
                )
                raw_metrics_list.append((frame_idx, fname, bg, sig, grad))
                sum_acc += arr_f32.astype(np.float64)
                _notify_progress(
                    progress_callback,
                    step_idx,
                    n_active,
                    f"Menumpuk frame [{step_idx}/{n_active}] (Arithmetic Mean)...",
                )

            stacked_f32 = (sum_acc / float(n_active)).astype(np.float32)
            stacked_f32.flags.writeable = False
            quality_records, _ = build_normalized_frame_weights(raw_metrics_list, profile_config)
            rej_map = np.zeros((height, width), dtype=np.uint16)
            kept_map = np.full((height, width), n_active, dtype=np.uint16)
            preview_qimg = array_to_preview_qimage(stacked_f32)

            return StackingResult(
                stacked_scientific_data=stacked_f32,
                preview=preview_qimg,
                rejection_map=rej_map,
                effective_frame_count_map=kept_map,
                profile_config=profile_config,
                effective_algorithm=effective_algo,
                total_input_frames=sequence_manager.frame_count,
                stacked_frame_count=n_active,
                included_frame_indices=tuple(included_indices),
                included_file_names=tuple(included_names),
                excluded_frames=tuple(excluded_records),
                frame_quality_metrics=quality_records,
                validation_report=validation,
                flat_report=flat_report,
                strip_count_used=1,
                working_memory_limit_mb=self._max_working_memory_mb,
                warnings=tuple(warnings),
                notes=tuple(notes),
            )

        # 5. Jalur Eksekusi 2: MEDIUM & HIGH (Quality Evaluation + Bounded-Memory Strip Processing)
        # Sesuai preferensi performa & permintaan pengguna: batasi strip menjadi paling banyak 2 bagian (atas & bawah)
        # untuk memaksimalkan vektorisasi C dan meminimalkan strip processing overhead.
        budget_bytes = max(1, self._max_working_memory_mb) * 1024 * 1024
        if self._max_working_memory_mb <= 0:
            strip_height = 1
            strip_count = height
        else:
            bytes_per_row_all_frames = n_active * width * channels * 4 * 3
            calc_h = max(1, min(height, int(budget_bytes // max(1, bytes_per_row_all_frames))))
            calc_count = int(math.ceil(height / float(calc_h)))
            if calc_count == 1 or height <= 1:
                strip_count = 1
                strip_height = height
            else:
                strip_count = min(2, height)
                strip_height = int(math.ceil(height / float(strip_count)))

        raw_metrics_list = []
        included_names = []

        # Jika seluruh N frame muat di dalam anggaran memori kerja atau cache (hingga 1.5 GB),
        # alokasikan array 3D kontigu di RAM agar decoding video/file dijalankan tepat sekali (O(1))
        # dan pemotongan per-strip baris bersifat zero-copy slice tanpa alokasi ulang berulang.
        # Bila melebihi anggaran atau RAM tidak mencukupi, gunakan memory-mapped file sementara.
        total_frames_bytes = n_active * height * width * channels * 4
        cache_budget_bytes = 0 if self._max_working_memory_mb <= 0 else max(budget_bytes, 1536 * 1024 * 1024)
        cached_cube: np.ndarray | None = None
        cube_shape = (n_active, height, width) if channels == 1 else (n_active, height, width, channels)
        if total_frames_bytes <= cache_budget_bytes:
            try:
                cached_cube = np.empty(cube_shape, dtype=np.float32)
            except (MemoryError, ValueError):
                cached_cube = None

        temp_mmap_path: Path | None = None
        cube_mmap: np.memmap | None = None
        if cached_cube is None:
            tf = tempfile.NamedTemporaryFile(prefix="hilalone_stack_", suffix=".dat", delete=False)
            tf.close()
            temp_mmap_path = Path(tf.name)
            cube_mmap = np.memmap(temp_mmap_path, dtype=np.float32, mode="w+", shape=cube_shape)

        try:
            total_steps = n_active + strip_count
            for step_idx, frame_idx in enumerate(included_indices, start=1):
                _check_cancelled(cancel_check)
                arr_f32, fname, is_cfa = _load_frame_f32(frame_idx)
                included_names.append(fname)
                if profile_config.use_quality_weights:
                    bg, sig, grad = compute_single_frame_quality_metrics(
                        arr_f32,
                        frame_index=frame_idx,
                        file_name=fname,
                        is_cfa_mosaic=is_cfa,
                    )
                else:
                    bg, sig, grad = 0.0, 1.0, 0.0
                raw_metrics_list.append((frame_idx, fname, bg, sig, grad))
                if cached_cube is not None:
                    cached_cube[step_idx - 1] = arr_f32
                else:
                    cube_mmap[step_idx - 1] = arr_f32
                if step_idx % 10 == 0 or step_idx == n_active:
                    _notify_progress(
                        progress_callback,
                        step_idx,
                        total_steps,
                        f"Mengevaluasi/memuat frame [{step_idx}/{n_active}]...",
                    )

            quality_records, frame_weights = build_normalized_frame_weights(
                raw_metrics_list, profile_config
            )

            out_shape = (height, width) if channels == 1 else (height, width, channels)
            stacked_out = np.zeros(out_shape, dtype=np.float32)
            rej_map = np.zeros((height, width), dtype=np.uint16)
            kept_map = np.zeros((height, width), dtype=np.uint16)

            for s_idx in range(strip_count):
                _check_cancelled(cancel_check)
                y0 = s_idx * strip_height
                y1 = min(height, y0 + strip_height)
                cur_h = y1 - y0

                if cached_cube is not None:
                    strip_cube = cached_cube[:, y0:y1]
                else:
                    strip_cube = np.ascontiguousarray(cube_mmap[:, y0:y1])

                s_data, s_rej, s_kept = _stack_strip_robust(
                    strip_cube,
                    frame_weights,
                    profile_config,
                    enable_clipping=enable_clipping,
                )
                stacked_out[y0:y1] = s_data
                rej_map[y0:y1] = s_rej
                kept_map[y0:y1] = s_kept

                _notify_progress(
                    progress_callback,
                    n_active + s_idx + 1,
                    total_steps,
                    f"Memproses strip baris [{s_idx + 1}/{strip_count}] ({profile_config.profile.value})...",
                )

            stacked_out.flags.writeable = False
            preview_qimg = array_to_preview_qimage(stacked_out)

            return StackingResult(
                stacked_scientific_data=stacked_out,
                preview=preview_qimg,
                rejection_map=rej_map,
                effective_frame_count_map=kept_map,
                profile_config=profile_config,
                effective_algorithm=effective_algo,
                total_input_frames=sequence_manager.frame_count,
                stacked_frame_count=n_active,
                included_frame_indices=tuple(included_indices),
                included_file_names=tuple(included_names),
                excluded_frames=tuple(excluded_records),
                frame_quality_metrics=quality_records,
                validation_report=validation,
                flat_report=flat_report,
                strip_count_used=strip_count,
                working_memory_limit_mb=self._max_working_memory_mb,
                warnings=tuple(warnings),
                notes=tuple(notes),
            )
        finally:
            if cached_cube is not None:
                del cached_cube
            if cube_mmap is not None:
                try:
                    cube_mmap._mmap.close()
                except Exception:
                    pass
                del cube_mmap
                if temp_mmap_path is not None:
                    try:
                        temp_mmap_path.unlink(missing_ok=True)
                    except Exception:
                        pass


def run_stacking_on_sequence(
    sequence_manager: SequenceManager,
    profile: StackingProfile | str = StackingProfile.MEDIUM,
    *,
    master_flat: np.ndarray | str | Path | None = None,
    excluded_frame_indices: set[int] | None = None,
    allow_exclude_incompatible_and_error: bool = False,
    check_position_stability: bool = False,
    confirm_proceed_with_shift_risk: bool = True,
    max_working_memory_mb: int = 512,
    shift_threshold_px: float = DEFAULT_SHIFT_THRESHOLD_PX,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheckCallback | None = None,
) -> StackingResult:
    """Fungsi pembantu tingkat atas untuk menjalankan Automatic Stacking Engine pada SequenceManager."""
    engine = AutomaticStackingEngine(
        max_working_memory_mb=max_working_memory_mb,
        shift_threshold_px=shift_threshold_px,
    )
    return engine.stack_sequence(
        sequence_manager,
        profile=profile,
        master_flat=master_flat,
        excluded_frame_indices=excluded_frame_indices,
        allow_exclude_incompatible_and_error=allow_exclude_incompatible_and_error,
        check_position_stability=check_position_stability,
        confirm_proceed_with_shift_risk=confirm_proceed_with_shift_risk,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )
