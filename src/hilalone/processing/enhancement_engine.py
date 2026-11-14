"""Engine 2 — Image Enhancement HILALONE berbasis CLAHE.

Meningkatkan keterlihatan detail dan kontras lokal menggunakan Contrast Limited
Adaptive Histogram Equalization (``skimage.exposure.equalize_adapthist``) tanpa
mengubah data ilmiah linear (``linear_result``).

Prinsip Ilmiah & Keselamatan Data (AGENTS.md Bagian 4, 5, & 8):
  1. ``linear_result`` tetap terpisah dan tidak pernah dimodifikasi secara in-place.
     CLAHE menghasilkan citra turunan nonlinear (``enhanced_result``) pada cabang
     tersendiri.
  2. TIDAK ada noise reduction, sharpening, ataupun smoothing otomatis.
  3. Untuk citra RGB 3-kanal, CLAHE diterapkan pada kanal luminansi (Y) dengan
     mempertahankan rasio warna asli (luminance-aware ratio-preserving), bukan
     diterapkan secara independen pada R, G, dan B.
  4. Untuk citra Bayer CFA 2×2, CLAHE diterapkan per sub-kanal 2×2 tanpa demosaicing.
  5. Nilai negatif akibat pengurangan background dinormalisasi hanya pada salinan
     kerja sementara (working array) untuk perhitungan CLAHE.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
from skimage.exposure import equalize_adapthist

from hilalone.input_manager.preview_builder import array_to_preview_qimage
from hilalone.processing.processing_models import (
    ImageEnhancementConfig,
    ImageEnhancementResult,
    ProcessingCancelledError,
    ProcessingError,
    ProcessingProfile,
)
from hilalone.processing.profile_manager import get_unified_profile_config


def _check_cancel(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check is not None and cancel_check():
        raise ProcessingCancelledError("Image Enhancement (CLAHE) dibatalkan oleh pengguna.")


def _estimate_high_freq_noise_sigma(arr_2d: np.ndarray) -> float:
    """Mengestimasi simpangan baku derau frekuensi tinggi secara robust menggunakan operator Laplacian MAD."""
    finite = np.where(np.isfinite(arr_2d), arr_2d, np.nanmedian(arr_2d) if np.any(np.isfinite(arr_2d)) else 0.0)
    if finite.shape[0] < 3 or finite.shape[1] < 3:
        med = float(np.median(finite))
        return float(np.median(np.abs(finite - med))) * 1.4826

    # Subsampling jika citra berukuran besar (> 500x500) agar evaluasi metrik berlangsung real-time (< 25 ms)
    h, w = finite.shape
    if h > 500 or w > 500:
        sy = max(1, h // 400)
        sx = max(1, w // 400)
        finite = finite[::sy, ::sx]

    # Selisih orde dua horizontal & vertikal untuk mengisolasi derau piksel-ke-piksel dari gradien
    diff_h = finite[:, 2:] - 2.0 * finite[:, 1:-1] + finite[:, :-2]
    diff_v = finite[2:, :] - 2.0 * finite[1:-1, :] + finite[:-2, :]
    med_h = float(np.median(diff_h))
    mad_h = float(np.median(np.abs(diff_h - med_h))) * 1.4826 / np.sqrt(6.0)
    med_v = float(np.median(diff_v))
    mad_v = float(np.median(np.abs(diff_v - med_v))) * 1.4826 / np.sqrt(6.0)
    return 0.5 * (mad_h + mad_v)


def _estimate_local_contrast_metric(arr_2d: np.ndarray) -> float:
    """Mengukur kontras lokal (simpangan baku antarpersentil menengah P90 - P10) pada skala normalisasi."""
    finite = arr_2d[np.isfinite(arr_2d)]
    if finite.size < 4:
        return 0.0
    if finite.size > 100000:
        stride = max(1, finite.size // 50000)
        finite = finite[::stride]
    return float(np.percentile(finite, 90.0) - np.percentile(finite, 10.0))


def _compute_tile_kernel_size(
    height: int,
    width: int,
    kernel_tiles: tuple[int, int],
) -> tuple[int, int]:
    """Mengonversi jumlah tile ``(tiles_y, tiles_x)`` menjadi ukuran kernel piksel ``(kh, kw)`` untuk skimage."""
    ty = max(2, int(kernel_tiles[0]))
    tx = max(2, int(kernel_tiles[1]))
    kh = max(4, min(height, int(round(height / float(ty)))))
    kw = max(4, min(width, int(round(width / float(tx)))))
    return (kh, kw)


def _apply_clahe_2d_unit(
    unit_2d: np.ndarray,
    *,
    clip_limit: float,
    kernel_tiles: tuple[int, int],
    nbins: int,
) -> np.ndarray:
    """Menerapkan ``skimage.exposure.equalize_adapthist`` pada array 2D di rentang ``[0.0, 1.0]``."""
    height, width = unit_2d.shape
    ptp_val = float(np.max(unit_2d) - np.min(unit_2d))
    if ptp_val <= 1e-12 or height < 4 or width < 4:
        return unit_2d.astype(np.float32, copy=True)

    kernel_size = _compute_tile_kernel_size(height, width, kernel_tiles)
    eff_clip = float(np.clip(clip_limit, 0.001, 0.25))
    eff_bins = int(np.clip(nbins, 32, 128))

    out = equalize_adapthist(
        np.clip(unit_2d, 0.0, 1.0),
        kernel_size=kernel_size,
        clip_limit=eff_clip,
        nbins=eff_bins,
    )
    return np.asarray(out, dtype=np.float32)


def _select_adaptive_clahe_parameters(
    unit_lum_2d: np.ndarray,
    base_config: ImageEnhancementConfig,
) -> tuple[float, tuple[int, int], list[str]]:
    """Memilih ``clip_limit`` dan ``kernel_tiles`` secara adaptif berdasarkan statistik SNR & kontras citra."""
    notes: list[str] = []
    height, width = unit_lum_2d.shape
    noise_sigma = _estimate_high_freq_noise_sigma(unit_lum_2d)
    contrast_span = max(1e-6, _estimate_local_contrast_metric(unit_lum_2d))
    snr_proxy = contrast_span / max(noise_sigma, 1e-6)

    base_clip = float(base_config.clip_limit)
    if snr_proxy < 4.0:
        # Citra didominasi derau: turunkan clip_limit secara konservatif agar derau tidak meledak
        eff_clip = float(np.clip(base_clip * 0.45, 0.004, 0.010))
        eff_tiles = (max(4, base_config.kernel_tiles[0] - 2), max(4, base_config.kernel_tiles[1] - 2))
        notes.append(
            f"CLAHE Adaptif mendeteksi SNR rendah (rasio kontras/derau={snr_proxy:.2f}): "
            f"clip_limit diturunkan ke {eff_clip:.4f} dengan tiles {eff_tiles[0]}×{eff_tiles[1]} "
            "untuk mencegah amplifikasi derau berlebihan."
        )
    elif snr_proxy < 10.0:
        eff_clip = float(np.clip(base_clip * 0.80, 0.006, 0.016))
        eff_tiles = base_config.kernel_tiles
        notes.append(
            f"CLAHE Adaptif menyesuaikan parameter moderat (SNR={snr_proxy:.2f}): "
            f"clip_limit={eff_clip:.4f}, tiles={eff_tiles[0]}×{eff_tiles[1]}."
        )
    else:
        # Citra memiliki sinyal bersih tetapi kontras lokal sabit mungkin rendah
        eff_clip = float(np.clip(base_clip, 0.008, 0.022))
        min_dim = min(height, width)
        t_auto = int(np.clip(min_dim // 48, 6, 12))
        eff_tiles = (max(base_config.kernel_tiles[0], t_auto), max(base_config.kernel_tiles[1], t_auto))
        notes.append(
            f"CLAHE Adaptif mengoptimalkan kontras lokal pada SNR baik (SNR={snr_proxy:.2f}): "
            f"clip_limit={eff_clip:.4f}, tiles={eff_tiles[0]}×{eff_tiles[1]}."
        )

    return eff_clip, eff_tiles, notes


def run_image_enhancement(
    linear_image: np.ndarray,
    config: ImageEnhancementConfig | ProcessingProfile | str = ProcessingProfile.MEDIUM,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> ImageEnhancementResult:
    """Menjalankan Engine 2 — Image Enhancement (CLAHE) pada salinan citra tanpa mengubah data ilmiah asli.

    Args:
        linear_image: Array input (umumnya ``linear_result`` dari Background Extraction).
                      Array ini TIDAK diubah secara in-place.
        config: Objek ``ImageEnhancementConfig`` atau profil ``BASIC``/``MEDIUM``/``HIGH``.
        cancel_check: Fungsi opsional untuk membatalkan proses secara aman.

    Returns:
        ``ImageEnhancementResult`` dengan ``enhanced_data`` (``float32``), metrik kontras
        dan amplifikasi derau sebelum/sesudah, serta pratinjau ``QImage``.
    """
    _check_cancel(cancel_check)

    if isinstance(config, (ProcessingProfile, str)):
        cfg = get_unified_profile_config(config).enhancement_config
    else:
        cfg = config

    src = np.asarray(linear_image)
    if src.ndim not in (2, 3):
        raise ProcessingError(
            f"Image Enhancement membutuhkan citra 2D atau 3D, tetapi menerima dimensi {src.shape}."
        )

    work = np.array(src, dtype=np.float32, copy=True)
    finite_mask = np.isfinite(work)
    warnings: list[str] = []
    notes: list[str] = []

    if not np.any(finite_mask):
        preview = array_to_preview_qimage(work)
        return ImageEnhancementResult(
            enhanced_data=work,
            config_used=cfg,
            effective_clip_limit=cfg.clip_limit,
            effective_kernel_tiles=cfg.kernel_tiles,
            backend_used="skimage.exposure.equalize_adapthist",
            color_mode="DEGENERATE_NON_FINITE",
            working_min=0.0,
            working_max=0.0,
            noise_sigma_before=0.0,
            noise_sigma_after=0.0,
            noise_amplification_ratio=1.0,
            local_contrast_before=0.0,
            local_contrast_after=0.0,
            enhanced_preview=preview,
            warnings=("Seluruh piksel bernilai NaN/Inf; CLAHE dilewati.",),
            notes=(),
        )

    valid_vals = work[finite_mask]
    w_min = float(np.min(valid_vals))
    w_max = float(np.max(valid_vals))
    span = w_max - w_min

    if not cfg.enabled or span <= 1e-12:
        if span <= 1e-12:
            notes.append("Citra bernilai seragam/konstan (dynamic range = 0); CLAHE tidak mengubah nilai piksel.")
        else:
            notes.append("Image Enhancement (CLAHE) dinonaktifkan oleh konfigurasi pengguna.")
        preview = array_to_preview_qimage(work)
        return ImageEnhancementResult(
            enhanced_data=work,
            config_used=cfg,
            effective_clip_limit=0.0 if not cfg.enabled else cfg.clip_limit,
            effective_kernel_tiles=cfg.kernel_tiles,
            backend_used="skimage.exposure.equalize_adapthist",
            color_mode="BYPASSED_CONSTANT_OR_DISABLED",
            working_min=w_min,
            working_max=w_max,
            noise_sigma_before=0.0,
            noise_sigma_after=0.0,
            noise_amplification_ratio=1.0,
            local_contrast_before=0.0,
            local_contrast_after=0.0,
            enhanced_preview=preview,
            warnings=tuple(warnings),
            notes=tuple(notes),
        )

    if w_min < 0.0:
        notes.append(
            f"Terdapat nilai negatif pada data linear (min={w_min:.4g}); normalisasi ke [0, 1] "
            "dilakukan hanya pada salinan kerja sementara untuk CLAHE."
        )

    # Salinan kerja ternormalisasi [0.0, 1.0]; piksel NaN diisi median sementara selama CLAHE
    if np.all(finite_mask):
        unit_work = np.clip((work - w_min) / span, 0.0, 1.0).astype(np.float32)
    else:
        if valid_vals.size > 100000:
            med_valid = float(np.median(valid_vals[::valid_vals.size // 50000]))
        else:
            med_valid = float(np.median(valid_vals))
        safe_work = np.where(finite_mask, work, med_valid)
        unit_work = np.clip((safe_work - w_min) / span, 0.0, 1.0).astype(np.float32)

    if unit_work.ndim == 2:
        lum_before = unit_work
    else:
        lum_before = (
            0.2126 * unit_work[:, :, 0]
            + 0.7152 * unit_work[:, :, 1]
            + 0.0722 * unit_work[:, :, 2]
        ).astype(np.float32)

    noise_before = _estimate_high_freq_noise_sigma(lum_before)
    contrast_before = _estimate_local_contrast_metric(lum_before)

    if cfg.adaptive_parameters:
        eff_clip, eff_tiles, adapt_notes = _select_adaptive_clahe_parameters(lum_before, cfg)
        notes.extend(adapt_notes)
    else:
        eff_clip = float(cfg.clip_limit)
        eff_tiles = cfg.kernel_tiles

    _check_cancel(cancel_check)

    # Terapkan CLAHE sesuai jenis citra (2D Bayer CFA, 2D Grayscale, atau 3D RGB Luminance-Aware)
    if cfg.is_cfa_mosaic and unit_work.ndim == 2 and (unit_work.shape[0] % 2 == 0) and (unit_work.shape[1] % 2 == 0):
        color_mode = "CFA_BAYER_SUBCHANNEL"
        unit_enhanced = np.zeros_like(unit_work, dtype=np.float32)
        sub_tiles = (max(2, eff_tiles[0] // 2), max(2, eff_tiles[1] // 2))
        for dy in (0, 1):
            for dx in (0, 1):
                _check_cancel(cancel_check)
                sub = unit_work[dy::2, dx::2]
                s_min = float(np.min(sub))
                s_max = float(np.max(sub))
                s_span = s_max - s_min
                if s_span > 1e-12:
                    sub_norm = (sub - s_min) / s_span
                    sub_clahe = _apply_clahe_2d_unit(
                        sub_norm,
                        clip_limit=eff_clip,
                        kernel_tiles=sub_tiles,
                        nbins=cfg.nbins,
                    )
                    unit_enhanced[dy::2, dx::2] = s_min + sub_clahe * s_span
                else:
                    unit_enhanced[dy::2, dx::2] = sub
        lum_after = unit_enhanced
        notes.append(
            "Mode Bayer CFA: CLAHE diterapkan pada masing-masing sub-kanal Bayer 2×2 tanpa demosaicing."
        )
    elif unit_work.ndim == 2:
        color_mode = "GRAYSCALE_DIRECT"
        unit_enhanced = _apply_clahe_2d_unit(
            unit_work,
            clip_limit=eff_clip,
            kernel_tiles=eff_tiles,
            nbins=cfg.nbins,
        )
        lum_after = unit_enhanced
    else:
        color_mode = "RGB_LUMINANCE_RATIO_PRESERVING"
        lum_clahe = _apply_clahe_2d_unit(
            lum_before,
            clip_limit=eff_clip,
            kernel_tiles=eff_tiles,
            nbins=cfg.nbins,
        )
        # Pertahankan rasio warna RGB (R:G:B) melalui pengali luminansi terproteksi
        gain = lum_clahe / np.maximum(lum_before, 1e-5)
        scaled_rgb = unit_work[:, :, :3] * gain[:, :, None]
        # Jika ada piksel yang melebihi 1.0, kompres secara proporsional per piksel agar rona warna tidak bergeser
        max_ch = np.max(scaled_rgb, axis=2, keepdims=True)
        overflow_scale = np.where(max_ch > 1.0, 1.0 / np.maximum(max_ch, 1.0), 1.0)
        unit_enhanced = np.zeros_like(unit_work, dtype=np.float32)
        unit_enhanced[:, :, :3] = np.clip(scaled_rgb * overflow_scale, 0.0, 1.0)
        if unit_work.shape[2] > 3:
            unit_enhanced[:, :, 3:] = unit_work[:, :, 3:]
        lum_after = (
            0.2126 * unit_enhanced[:, :, 0]
            + 0.7152 * unit_enhanced[:, :, 1]
            + 0.0722 * unit_enhanced[:, :, 2]
        ).astype(np.float32)
        notes.append(
            "Mode RGB Luminance-Aware: CLAHE diterapkan pada kanal luminansi (Y) dengan menjaga rasio warna R:G:B."
        )

    _check_cancel(cancel_check)

    # Safeguard pembatas amplifikasi derau (Noise Amplification Limiter tanpa smoothing/denoising!)
    noise_after = _estimate_high_freq_noise_sigma(lum_after)
    if noise_before > 1e-7:
        amp_ratio = float(noise_after / noise_before)
    else:
        amp_ratio = 1.0

    if amp_ratio > cfg.max_noise_amplification_ratio and noise_before > 1e-7:
        # Kurangi bobot penguatan CLAHE secara linier terhadap citra sebelum CLAHE
        # (murni pencampuran intensitas piksel-ke-piksel, BUKAN spatial smoothing/denoising!)
        target_ratio = float(cfg.max_noise_amplification_ratio)
        alpha = float(np.clip((target_ratio - 1.0) / max(amp_ratio - 1.0, 1e-6), 0.15, 1.0))
        unit_enhanced = (unit_work + alpha * (unit_enhanced - unit_work)).astype(np.float32)
        if unit_enhanced.ndim == 2:
            lum_after = unit_enhanced
        else:
            lum_after = (
                0.2126 * unit_enhanced[:, :, 0]
                + 0.7152 * unit_enhanced[:, :, 1]
                + 0.0722 * unit_enhanced[:, :, 2]
            ).astype(np.float32)
        noise_after = _estimate_high_freq_noise_sigma(lum_after)
        amp_ratio = float(noise_after / noise_before)
        warnings.append(
            f"Pembatas amplifikasi derau aktif: kekuatan CLAHE disesuaikan (faktor={alpha:.2f}) "
            f"agar rasio derau tetap <= {cfg.max_noise_amplification_ratio:.2f}x."
        )

    contrast_after = _estimate_local_contrast_metric(lum_after)

    # Kembalikan ke skala rentang kerja fisik [w_min, w_max] dalam float32 dan pulihkan posisi NaN/Inf
    enhanced_f32 = (w_min + unit_enhanced * span).astype(np.float32)
    enhanced_f32 = np.where(finite_mask, enhanced_f32, work).astype(np.float32)

    preview = array_to_preview_qimage(enhanced_f32)

    return ImageEnhancementResult(
        enhanced_data=enhanced_f32,
        config_used=cfg,
        effective_clip_limit=eff_clip,
        effective_kernel_tiles=eff_tiles,
        backend_used="skimage.exposure.equalize_adapthist",
        color_mode=color_mode,
        working_min=w_min,
        working_max=w_max,
        noise_sigma_before=float(noise_before * span),
        noise_sigma_after=float(noise_after * span),
        noise_amplification_ratio=amp_ratio,
        local_contrast_before=float(contrast_before * span),
        local_contrast_after=float(contrast_after * span),
        enhanced_preview=preview,
        warnings=tuple(warnings),
        notes=tuple(notes),
    )
