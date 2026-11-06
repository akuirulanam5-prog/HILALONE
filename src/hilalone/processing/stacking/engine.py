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
    """Menghitung (background_median, robust_noise_sigma, gradient_energy) secara baca-saja.

    Estimasi derau menggunakan MAD dari operator Laplacian 2D diskrit:
      ``L_lap = L(y-1,x) + L(y+1,x) + L(y,x-1) + L(y,x+1) - 4*L(y,x)``
    sehingga gradien langit linear tereliminasi dan menyisakan derau frekuensi tinggi
    sensor dengan faktor normalisasi ``sqrt(20)``.
    """
    lum, _ = extract_luminance_proxy_readonly(scientific_data, is_cfa_mosaic=is_cfa_mosaic)
    lum64 = np.asarray(lum, dtype=np.float64)
    finite = lum64[np.isfinite(lum64)]
    if finite.size == 0:
        return 0.0, 1.0, 0.0

    bg_median = float(np.median(finite))

    if lum64.shape[0] >= 3 and lum64.shape[1] >= 3:
        lap = (
            lum64[:-2, 1:-1]
            + lum64[2:, 1:-1]
            + lum64[1:-1, :-2]
            + lum64[1:-1, 2:]
            - 4.0 * lum64[1:-1, 1:-1]
        )
        lap_med = float(np.median(lap))
        mad_lap = float(np.median(np.abs(lap - lap_med)))
        # Varian dari (1 + 1 + 1 + 1 + (-4)^2) * sigma^2 = 20 * sigma^2
        noise_sigma = (1.4826 * mad_lap) / math.sqrt(20.0)

        gy = 0.5 * (lum64[2:, 1:-1] - lum64[:-2, 1:-1])
        gx = 0.5 * (lum64[1:-1, 2:] - lum64[1:-1, :-2])
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

    # Hitung luminans 3D (N, strip_h, W) untuk keputusan outlier bersama (FR-ST-03a)
    if is_rgb:
        lum_cube = (
            0.2126 * strip_cube[..., 0].astype(np.float64)
            + 0.7152 * strip_cube[..., 1].astype(np.float64)
            + 0.0722 * strip_cube[..., 2].astype(np.float64)
        )
    else:
        lum_cube = strip_cube.astype(np.float64)

    keep_mask = np.ones((n_frames, strip_h, width), dtype=bool)
    min_kept = max(3, int(math.ceil(config.min_kept_fraction * n_frames)))
    min_kept = min(min_kept, n_frames)

    for _ in range(config.max_clip_iterations):
        masked_vals = np.where(keep_mask, lum_cube, np.nan)
        med = np.nanmedian(masked_vals, axis=0)
        diff = lum_cube - med[None, :, :]
        abs_dev = np.abs(diff)
        mad = np.nanmedian(np.where(keep_mask, abs_dev, np.nan), axis=0)
        robust_sigma = 1.4826 * mad

        # Apabila mayoritas frame terkuantisasi pada nilai identik (MAD == 0) namun ada
        # frame outlier dengan simpangan besar, gunakan ambang skala fallback minimal
        # agar frame identik (diff == 0) tetap lolos sementara outlier ekstrem tertolak.
        fallback_sigma = np.maximum(1e-5, 1e-4 * np.abs(med))
        effective_sigma = np.where(robust_sigma > 1e-9, robust_sigma, fallback_sigma)
        has_any_deviation = np.nanmax(np.where(keep_mask, abs_dev, 0.0), axis=0) > 1e-9

        low_bound = -config.sigma_low * effective_sigma[None, :, :]
        high_bound = config.sigma_high * effective_sigma[None, :, :]

        in_bounds = (diff >= low_bound) & (diff <= high_bound)
        candidate_mask = np.where(
            has_any_deviation[None, :, :],
            keep_mask & in_bounds,
            keep_mask,
        )

        # Safeguard minimum sampel: jika suatu piksel menyisakan < min_kept sampel,
        # pertahankan min_kept sampel dengan simpangan terkecil terhadap median
        cand_counts = np.sum(candidate_mask, axis=0)
        underflow = cand_counts < min_kept
        if np.any(underflow):
            # Urutkan simpangan dari terkecil ke terbesar sepanjang sumbu frame
            order = np.argsort(abs_dev, axis=0)
            rank = np.argsort(order, axis=0)
            fallback_mask = rank < min_kept
            candidate_mask = np.where(underflow[None, :, :], fallback_mask, candidate_mask)

        if np.array_equal(candidate_mask, keep_mask):
            break
        keep_mask = candidate_mask

    kept_counts = np.sum(keep_mask, axis=0).astype(np.uint16)
    rejected_counts = (n_frames - kept_counts).astype(np.uint16)

    # Hitung rata-rata berbobot pada sampel yang lolos (jumlah bobot per piksel dinormalisasi ke 1.0)
    w_3d = np.where(keep_mask, frame_weights[:, None, None], 0.0)
    w_sum = np.sum(w_3d, axis=0)
    w_sum_safe = np.where(w_sum > 0.0, w_sum, 1.0)

    if is_rgb:
        weighted_sum = np.sum(
            strip_cube.astype(np.float64) * w_3d[..., None],
            axis=0,
        )
        stacked_strip = weighted_sum / w_sum_safe[..., None]
    else:
        weighted_sum = np.sum(
            strip_cube.astype(np.float64) * w_3d,
            axis=0,
        )
        stacked_strip = weighted_sum / w_sum_safe

    return stacked_strip.astype(np.float32), rejected_counts, kept_counts


class AutomaticStackingEngine:
    """Mesin penumpukan citra otomatis HILALONE untuk Multiple Images, Video, dan SER."""

    def __init__(
        self,
        *,
        max_working_memory_mb: int = 128,
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
        check_position_stability: bool = True,
        confirm_proceed_with_shift_risk: bool = False,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheckCallback | None = None,
    ) -> StackingResult:
        """Menjalankan validasi pra-stacking, pemeriksaan posisi, flat opsional, dan stacking.

        Args:
            sequence_manager: Instance ``SequenceManager`` yang sedang aktif.
            profile: Profil stacking (``BASIC``, ``MEDIUM``, atau ``HIGH``).
            master_flat: Opsional array atau jalur berkas Master Flat.
            excluded_frame_indices: Himpunan indeks frame (0-based) yang dikecualikan pengguna.
            allow_exclude_incompatible_and_error: Bila ``True``, frame berstatus ``INCOMPATIBLE``
                atau ``ERROR`` dikecualikan dengan catatan eksplisit. Bila ``False`` (default),
                engine akan melempar ``StackingConfirmationRequiredError`` agar tidak ada frame
                yang dilewati diam-diam.
            check_position_stability: Bila ``True``, mengukur pergeseran translasi ``(dx, dy)``
                terhadap frame referensi.
            confirm_proceed_with_shift_risk: Bila ``True``, tetap melanjutkan stacking meskipun
                terdapat frame dengan pergeseran > ambang atau ``INDETERMINATE`` (dengan peringatan).
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
            )
            warnings.extend(flat_report.warnings)
            notes.append(
                f"Kalibrasi Master Flat opsional diterapkan dari '{flat_report.source_description}' "
                f"(rata-rata awal={flat_report.flat_mean_before_norm:.2f} dinormalisasi ke 1.0)."
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

        # 3. Pemeriksaan Stabilitas Posisi (baca-saja)
        stability_report = None
        if check_position_stability:
            _notify_progress(
                progress_callback,
                0,
                len(included_indices) * 2,
                "Memeriksa stabilitas posisi frame terhadap frame referensi...",
            )
            stability_report = measure_sequence_position_stability(
                tuple(included_indices),
                _load_frame_f32,
                reference_frame_index=validation.reference_frame_index,
                threshold_px=self._shift_threshold_px,
            )
            validation = replace(validation, stability_report=stability_report)
            warnings.extend(stability_report.warnings)

            if stability_report.has_warnings and not confirm_proceed_with_shift_risk:
                shift_msgs = "\n".join(f"• {w}" for w in stability_report.warnings[:6])
                raise StackingConfirmationRequiredError(
                    "Pemeriksaan stabilitas posisi mendeteksi pergeseran melebihi ambang "
                    f"({self._shift_threshold_px:.2f} px) atau status INDETERMINATE:\n"
                    f"{shift_msgs}\n\n"
                    "Karena image registration/alignment dilarang pada MVP 1.0, melanjutkan stacking "
                    "berisiko menimbulkan blur pada sabit hilal. Konfirmasi "
                    "confirm_proceed_with_shift_risk=True untuk tetap melanjutkan atau kecualikan "
                    "frame yang bergeser."
                )

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
        # Hitung ukuran memori per baris melintasi seluruh N frame (faktor 3x untuk ruang kerja median/MAD)
        bytes_per_row_all_frames = n_active * width * channels * 4 * 3
        budget_bytes = self._max_working_memory_mb * 1024 * 1024
        strip_height = max(1, min(height, int(budget_bytes // max(1, bytes_per_row_all_frames))))
        strip_count = int(math.ceil(height / float(strip_height)))

        raw_metrics_list = []
        included_names = []

        # Jika seluruh N frame muat di dalam anggaran memori kerja (strip_count == 1),
        # muat sekali agar tidak membaca disk berulang-ulang
        cached_full_frames: list[np.ndarray] | None = [] if strip_count == 1 else None

        total_steps = n_active + strip_count
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
            if cached_full_frames is not None:
                cached_full_frames.append(arr_f32)
            _notify_progress(
                progress_callback,
                step_idx,
                total_steps,
                f"Mengevaluasi metrik kualitas frame [{step_idx}/{n_active}]...",
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

            if cached_full_frames is not None:
                strip_cube = np.stack([f[y0:y1] for f in cached_full_frames], axis=0)
            else:
                strip_shape = (
                    (n_active, cur_h, width)
                    if channels == 1
                    else (n_active, cur_h, width, channels)
                )
                strip_cube = np.empty(strip_shape, dtype=np.float32)
                for f_pos, frame_idx in enumerate(included_indices):
                    _check_cancelled(cancel_check)
                    arr_f32, _, _ = _load_frame_f32(frame_idx)
                    strip_cube[f_pos] = arr_f32[y0:y1]

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


def run_stacking_on_sequence(
    sequence_manager: SequenceManager,
    profile: StackingProfile | str = StackingProfile.MEDIUM,
    *,
    master_flat: np.ndarray | str | Path | None = None,
    excluded_frame_indices: set[int] | None = None,
    allow_exclude_incompatible_and_error: bool = False,
    check_position_stability: bool = True,
    confirm_proceed_with_shift_risk: bool = False,
    max_working_memory_mb: int = 128,
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
