"""Engine 3 — Histogram Transformation HILALONE.

Menghasilkan transformasi tampilan otomatis (Automatic Display Stretch) pada
cabang tampilan (``display_result`` di ``[0.0, 1.0]``) agar detail sabit hilal
mudah diamati tanpa pernah mengubah data ilmiah linear (``linear_result``).

Metode yang didukung:
  1. BASIC  (``LINEAR_MTF``)         : Interval persentil robust + Linear Stretch + MTF.
  2. MEDIUM (``ASINH_MTF``)          : Normalisasi persentil + Asinh Stretch + MTF.
  3. HIGH   (``ADAPTIVE_ASINH_MTF``) : Persentil adaptif + Adaptive Asinh + Adaptive MTF
                                       berdasarkan distribusi intensitas & background.
  4. ADVANCED (``GHS_MTF``)          : Generalized Hyperbolic Stretch simetris tervalidasi + MTF.

Rumus Tervalidasi:
  * Normalisasi Linear:
        x = clip((I - vmin) / (vmax - vmin), 0, 1)
  * Asinh Stretch:
        S(x) = asinh(x / a) / asinh(1 / a),   a > 0
  * Midtones Transfer Function (MTF):
        MTF(x, m) = ((m - 1) * x) / ((2 * m - 1) * x - m),   0 < m < 1
"""

from __future__ import annotations

from typing import Callable

from astropy.visualization import AsymmetricPercentileInterval
import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF

from hilalone.input_manager.preview_builder import array_to_preview_qimage
from hilalone.processing.processing_models import (
    HistogramData,
    HistogramTransformConfig,
    HistogramTransformResult,
    ProcessingCancelledError,
    ProcessingError,
    ProcessingProfile,
    StretchMethod,
)
from hilalone.processing.profile_manager import get_unified_profile_config


def _check_cancel(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check is not None and cancel_check():
        raise ProcessingCancelledError("Histogram Transformation dibatalkan oleh pengguna.")


def apply_mtf(x: np.ndarray, midtone_balance: float) -> np.ndarray:
    """Menerapkan fungsi Midtones Transfer Function (MTF) PixInsight/Siril standar pada ``x`` di ``[0, 1]``.

    Rumus:
        MTF(x, m) = ((m - 1) * x) / ((2 * m - 1) * x - m)

    Sifat matematis:
      * MTF(0, m) = 0
      * MTF(m, m) = 0.5
      * MTF(1, m) = 1
      * MTF(x, 0.5) = x
      * Monoton naik murni untuk setiap m di (0, 1).
    """
    m = float(np.clip(midtone_balance, 1e-4, 1.0 - 1e-4))
    arr = np.clip(np.asarray(x, dtype=np.float32), 0.0, 1.0)
    if abs(m - 0.5) <= 1e-6:
        return arr

    m_f = np.float32(m)
    num = (m_f - np.float32(1.0)) * arr
    den = (np.float32(2.0) * m_f - np.float32(1.0)) * arr - m_f
    safe_den = np.where(np.abs(den) > 1e-7, den, np.float32(-1e-7))
    out = np.clip(num / safe_den, 0.0, 1.0)
    out = np.where(arr <= 0.0, 0.0, np.where(arr >= 1.0, 1.0, out))
    return out.astype(np.float32)


def solve_mtf_parameter_for_target_median(
    current_median: float,
    target_median: float = 0.18,
) -> float:
    """Menghitung parameter midtone balance ``m`` agar ``MTF(current_median, m) == target_median``.

    Dari persamaan:
        t = ((m - 1) * x) / ((2 * m - 1) * x - m)
    Diperoleh solusi analitik tunggal:
        m = (x * (t - 1)) / (2 * t * x - t - x)
    """
    x = float(np.clip(current_median, 1e-4, 0.95))
    t = float(np.clip(target_median, 0.05, 0.50))
    denom = 2.0 * t * x - t - x
    if abs(denom) <= 1e-9:
        return 0.5
    m = (x * (t - 1.0)) / denom
    return float(np.clip(m, 0.08, 0.65))


def apply_asinh_stretch(x: np.ndarray, a: float) -> np.ndarray:
    """Menerapkan peregangan Asinh tervalidasi pada ``x`` di ``[0, 1]`` dalam float32 cepat."""
    a_safe = float(max(1e-5, a))
    arr = np.clip(np.asarray(x, dtype=np.float32), 0.0, 1.0)
    denom = float(np.arcsinh(1.0 / a_safe))
    if denom <= 1e-12:
        return arr
    inv_denom = np.float32(1.0 / denom)
    inv_a = np.float32(1.0 / a_safe)
    out = np.arcsinh(arr * inv_a) * inv_denom
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def apply_ghs_stretch(
    x: np.ndarray,
    *,
    stretch_factor_d: float = 2.0,
    local_intensity_b: float = 1.5,
    symmetry_point_sp: float = 0.15,
) -> np.ndarray:
    """Menerapkan Generalized Hyperbolic Stretch (GHS) simetris yang monoton pada ``x`` di ``[0, 1]``.

    Rumus tervalidasi berbasis transformasi hiperbolik berpusat di titik simetri SP:
        T(x) = (asinh(k * (x - SP)) + asinh(k * SP)) / (asinh(k * (1 - SP)) + asinh(k * SP))
    di mana k = D * exp(b * 0.5) > 0.
    Transformasi ini dijamin:
      * T(0) = 0 dan T(1) = 1
      * Monoton naik murni (T'(x) > 0 untuk seluruh x di [0, 1])
      * Memiliki kemiringan lokal maksimum tepat pada x = SP (mengangkat kontras di sekitar sabit/langit).
    """
    arr = np.clip(np.asarray(x, dtype=np.float64), 0.0, 1.0)
    d_val = float(max(0.0, stretch_factor_d))
    if d_val <= 1e-6:
        return arr.astype(np.float32)

    b_val = float(np.clip(local_intensity_b, -4.0, 10.0))
    sp = float(np.clip(symmetry_point_sp, 0.0, 1.0))
    k = max(1e-4, d_val * float(np.exp(0.35 * b_val)))

    offset = float(np.arcsinh(k * sp))
    norm = float(np.arcsinh(k * (1.0 - sp)) + offset)
    if norm <= 1e-12:
        return arr.astype(np.float32)

    out = (np.arcsinh(k * (arr - sp)) + offset) / norm
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def _sample_valid_pixels_for_percentiles(
    image: np.ndarray,
    max_samples: int = 250_000,
) -> tuple[np.ndarray, int]:
    """Mengambil sampel piksel finite secara deterministik (strided 2D) untuk perhitungan persentil cepat."""
    h, w = image.shape[:2]
    total_px = h * w
    if total_px > max_samples:
        stride_step = max(1, int(np.ceil(np.sqrt(float(total_px) / float(max_samples)))))
        sub = image[::stride_step, ::stride_step]
    else:
        sub = image

    finite_mask = np.isfinite(sub)
    if not np.any(finite_mask):
        return np.empty(0, dtype=np.float64), 0

    valid_1d = sub[finite_mask]
    total_valid = int(np.count_nonzero(np.isfinite(image)))
    return valid_1d.astype(np.float64, copy=False), total_valid


def compute_robust_percentile_limits(
    valid_samples: np.ndarray,
    low_percentile: float,
    high_percentile: float,
) -> tuple[float, float]:
    """Menghitung ``(vmin, vmax)`` menggunakan ``astropy.visualization.AsymmetricPercentileInterval``."""
    if valid_samples.size == 0:
        return 0.0, 0.0
    p_low = float(np.clip(low_percentile, 0.0, 49.5))
    p_high = float(np.clip(high_percentile, max(p_low + 0.5, 50.5), 100.0))
    interval = AsymmetricPercentileInterval(p_low, p_high)
    vmin_raw, vmax_raw = interval.get_limits(valid_samples)
    return float(vmin_raw), float(vmax_raw)


def render_histogram_chart_qimage(
    hist_data: HistogramData,
    *,
    vmin: float,
    vmax: float,
    method_label: str,
    width: int = 360,
    height: int = 136,
) -> QImage:
    """Menggambar grafik perbandingan histogram Sebelum vs Sesudah transformasi sebagai QImage."""
    img = QImage(width, height, QImage.Format.Format_RGB888)
    img.fill(QColor(9, 15, 29))

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    pad_l, pad_r, pad_t, pad_b = 12, 12, 22, 22
    plot_w = max(10, width - pad_l - pad_r)
    plot_h = max(10, height - pad_t - pad_b)

    # Bingkai area plot
    painter.setPen(QPen(QColor(36, 54, 89), 1))
    painter.setBrush(QColor(13, 21, 38))
    painter.drawRect(pad_l, pad_t, plot_w, plot_h)

    def _draw_curve(counts: np.ndarray, line_color: QColor, fill_color: QColor) -> None:
        if counts.size < 2 or int(np.max(counts)) <= 0:
            return
        # Skala logaritmik halus agar puncak langit maupun ekor sinyal sabit terlihat jelas
        log_c = np.log1p(counts.astype(np.float64))
        max_log = float(np.max(log_c))
        if max_log <= 1e-9:
            return
        norm_c = log_c / max_log
        n_bins = norm_c.size

        pts: list[QPointF] = [QPointF(float(pad_l), float(pad_t + plot_h))]
        for i in range(n_bins):
            px = pad_l + (float(i) / float(n_bins - 1)) * plot_w
            py = pad_t + plot_h - float(norm_c[i]) * (plot_h - 4)
            pts.append(QPointF(px, py))
        pts.append(QPointF(float(pad_l + plot_w), float(pad_t + plot_h)))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill_color)
        painter.drawPolygon(QPolygonF(pts))

        painter.setPen(QPen(line_color, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF(pts[1:-1]))

    _draw_curve(
        hist_data.counts_before,
        QColor(96, 165, 250, 220),
        QColor(59, 130, 246, 55),
    )
    _draw_curve(
        hist_data.counts_after,
        QColor(52, 211, 153, 235),
        QColor(16, 185, 129, 55),
    )

    # Teks legenda & info vmin/vmax
    font = QFont("Segoe UI", 7)
    painter.setFont(font)
    painter.setPen(QColor(190, 206, 235))
    painter.drawText(
        pad_l,
        14,
        f"Biru: Sebelum | Hijau: Sesudah ({method_label})",
    )
    painter.setPen(QColor(138, 155, 189))
    painter.drawText(
        pad_l,
        height - 6,
        f"vmin={vmin:.4g}   vmax={vmax:.4g}   med: {hist_data.median_before:.2f} → {hist_data.median_after:.2f}",
    )

    painter.end()
    return img


def run_histogram_transformation(
    input_image: np.ndarray,
    config: HistogramTransformConfig | ProcessingProfile | str = ProcessingProfile.MEDIUM,
    *,
    nbins: int = 128,
    cancel_check: Callable[[], bool] | None = None,
) -> HistogramTransformResult:
    """Menjalankan Engine 3 — Histogram Transformation untuk menghasilkan citra tampilan ``[0.0, 1.0]``.

    Args:
        input_image: Array input (``enhanced_result`` atau ``linear_result``).
                     Array sumber TIDAK diubah secara in-place.
        config: Objek ``HistogramTransformConfig`` atau profil ``BASIC``/``MEDIUM``/``HIGH``.
        nbins: Jumlah bin untuk histogram sebelum/sesudah.
        cancel_check: Fungsi opsional untuk membatalkan proses secara aman.

    Returns:
        ``HistogramTransformResult`` berisi ``display_data`` (``float32`` di ``[0, 1]``),
        ``display_preview`` (``QImage``), ``histogram_chart_preview`` (``QImage``),
        ``vmin``, ``vmax``, dan parameter efektif yang digunakan.
    """
    _check_cancel(cancel_check)

    if isinstance(config, (ProcessingProfile, str)):
        cfg = get_unified_profile_config(config).histogram_config
    else:
        cfg = config

    src = np.asarray(input_image)
    if src.ndim not in (2, 3):
        raise ProcessingError(
            f"Histogram Transformation membutuhkan citra 2D atau 3D, tetapi menerima dimensi {src.shape}."
        )

    work = np.array(src, dtype=np.float32, copy=True)
    samples, valid_count = _sample_valid_pixels_for_percentiles(work)
    warnings: list[str] = []
    notes: list[str] = []

    edges = np.linspace(0.0, 1.0, max(16, int(nbins)) + 1, dtype=np.float32)

    # Kasus 1: Tidak ada piksel valid (semua NaN / Inf)
    if valid_count == 0 or samples.size == 0:
        zeros_disp = np.zeros_like(work, dtype=np.float32)
        empty_counts = np.zeros(edges.size - 1, dtype=np.int64)
        hist_data = HistogramData(
            bin_edges=edges,
            counts_before=empty_counts,
            counts_after=empty_counts,
            median_before=0.0,
            median_after=0.0,
            mad_before=0.0,
            mad_after=0.0,
        )
        chart_img = render_histogram_chart_qimage(
            hist_data, vmin=0.0, vmax=0.0, method_label=cfg.method.value
        )
        return HistogramTransformResult(
            display_data=zeros_disp,
            display_preview=array_to_preview_qimage(zeros_disp),
            histogram_chart_preview=chart_img,
            histogram_data=hist_data,
            config_used=cfg,
            effective_method=cfg.method,
            vmin=0.0,
            vmax=0.0,
            effective_low_percentile=cfg.low_percentile,
            effective_high_percentile=cfg.high_percentile,
            effective_asinh_a=cfg.asinh_a,
            effective_midtone_balance=cfg.midtone_balance,
            valid_pixel_count=0,
            is_uniform_or_degenerate=True,
            warnings=("Seluruh piksel bernilai NaN/Inf; tampilan diatur ke 0.0.",),
            notes=(),
        )

    full_min = float(np.min(samples))
    full_max = float(np.max(samples))

    # Kasus 2: Citra konstan / uniform (dynamic range sangat kecil / nol)
    if (full_max - full_min) <= 1e-12:
        const_level = 0.0 if full_max <= 0.0 else 0.5
        disp = np.where(np.isfinite(work), const_level, 0.0).astype(np.float32)
        c_before, _ = np.histogram(np.full(samples.size, const_level), bins=edges)
        hist_data = HistogramData(
            bin_edges=edges,
            counts_before=c_before,
            counts_after=c_before.copy(),
            median_before=const_level,
            median_after=const_level,
            mad_before=0.0,
            mad_after=0.0,
        )
        chart_img = render_histogram_chart_qimage(
            hist_data, vmin=full_min, vmax=full_max, method_label="UNIFORM"
        )
        notes.append(
            f"Citra bernilai seragam/konstan (nilai={full_min:.4g}); dipetakan ke tingkat tampilan {const_level:.2f}."
        )
        return HistogramTransformResult(
            display_data=disp,
            display_preview=array_to_preview_qimage(disp),
            histogram_chart_preview=chart_img,
            histogram_data=hist_data,
            config_used=cfg,
            effective_method=cfg.method,
            vmin=full_min,
            vmax=full_max,
            effective_low_percentile=cfg.low_percentile,
            effective_high_percentile=cfg.high_percentile,
            effective_asinh_a=cfg.asinh_a,
            effective_midtone_balance=cfg.midtone_balance,
            valid_pixel_count=valid_count,
            is_uniform_or_degenerate=True,
            warnings=tuple(warnings),
            notes=tuple(notes),
        )

    # Pilih batas persentil (adaptif bila profil HIGH / adaptive_parameters=True)
    eff_low_p = float(cfg.low_percentile)
    eff_high_p = float(cfg.high_percentile)
    med_raw = float(np.median(samples))
    mad_raw = float(np.median(np.abs(samples - med_raw))) * 1.4826

    if cfg.adaptive_parameters or cfg.method == StretchMethod.ADAPTIVE_ASINH_MTF:
        # Gunakan batas bawah berbasis median - 2.2 * sigma_MAD agar ekor derau negatif tidak memotong sinyal sabit
        target_vmin = max(full_min, med_raw - 2.2 * mad_raw)
        vmin_p, vmax_p = compute_robust_percentile_limits(samples, eff_low_p, eff_high_p)
        vmin = min(vmin_p, target_vmin)
        vmax = max(vmax_p, med_raw + 6.0 * mad_raw)
        if vmax <= vmin:
            vmin, vmax = full_min, full_max
    else:
        vmin, vmax = compute_robust_percentile_limits(samples, eff_low_p, eff_high_p)
        if (vmax - vmin) <= 1e-12:
            vmin, vmax = full_min, full_max

    span = max(1e-12, vmax - vmin)

    # Normalisasi linear ke [0, 1] pada cabang tampilan
    finite_mask = np.isfinite(work)
    norm_unit = np.where(
        finite_mask,
        np.clip((work - vmin) / span, 0.0, 1.0),
        0.0,
    ).astype(np.float32)

    norm_samples = np.clip((samples - vmin) / span, 0.0, 1.0)
    med_before = float(np.median(norm_samples))
    mad_before = float(np.median(np.abs(norm_samples - med_before))) * 1.4826

    _check_cancel(cancel_check)

    # Tentukan parameter stretch (asinh_a dan midtone_balance)
    eff_asinh_a = float(cfg.asinh_a)
    eff_mtf_m = float(cfg.midtone_balance)

    if not cfg.enabled:
        stretched = norm_unit
        notes.append("Histogram Transformation dinonaktifkan; hanya menggunakan pemetaan linear [vmin, vmax].")
    elif cfg.method == StretchMethod.LINEAR_MTF:
        if cfg.adaptive_parameters:
            eff_mtf_m = solve_mtf_parameter_for_target_median(
                med_before, cfg.target_background_median
            )
        stretched = apply_mtf(norm_unit, eff_mtf_m)
    elif cfg.method in (StretchMethod.ASINH_MTF, StretchMethod.ADAPTIVE_ASINH_MTF):
        if cfg.adaptive_parameters or cfg.method == StretchMethod.ADAPTIVE_ASINH_MTF:
            # Pilih pelunakan asinh_a berdasarkan kompresi rentang dinamis latar
            eff_asinh_a = float(np.clip(max(0.04, 1.8 * mad_before + 0.05), 0.04, 0.35))
            mid_after_asinh = float(
                np.arcsinh(med_before / eff_asinh_a) / np.arcsinh(1.0 / eff_asinh_a)
            )
            eff_mtf_m = solve_mtf_parameter_for_target_median(
                max(0.01, mid_after_asinh),
                cfg.target_background_median,
            )
            notes.append(
                f"Adaptive Asinh + MTF memilih parameter otomatis: a={eff_asinh_a:.4f}, "
                f"midtone_balance={eff_mtf_m:.4f} (target median={cfg.target_background_median:.2f})."
            )
        asinh_stage = apply_asinh_stretch(norm_unit, eff_asinh_a)
        stretched = apply_mtf(asinh_stage, eff_mtf_m)
    elif cfg.method == StretchMethod.GHS_MTF:
        sp_eff = med_before if cfg.adaptive_parameters else cfg.ghs_symmetry_point_sp
        ghs_stage = apply_ghs_stretch(
            norm_unit,
            stretch_factor_d=cfg.ghs_stretch_factor_d,
            local_intensity_b=cfg.ghs_local_intensity_b,
            symmetry_point_sp=sp_eff,
        )
        stretched = apply_mtf(ghs_stage, eff_mtf_m)
        notes.append(
            f"Generalized Hyperbolic Stretch (GHS) diterapkan: D={cfg.ghs_stretch_factor_d:.2f}, "
            f"b={cfg.ghs_local_intensity_b:.2f}, SP={sp_eff:.3f}."
        )
    else:
        stretched = apply_mtf(norm_unit, eff_mtf_m)

    display_data = np.where(finite_mask, np.clip(stretched, 0.0, 1.0), 0.0).astype(np.float32)

    _check_cancel(cancel_check)

    # Hitung histogram sebelum (norm_samples) dan sesudah (stretched_samples)
    after_samples, _ = _sample_valid_pixels_for_percentiles(display_data)
    if after_samples.size == 0:
        after_samples = np.zeros_like(norm_samples)

    counts_before, _ = np.histogram(norm_samples, bins=edges)
    counts_after, _ = np.histogram(after_samples, bins=edges)
    med_after = float(np.median(after_samples))
    mad_after = float(np.median(np.abs(after_samples - med_after))) * 1.4826

    hist_data = HistogramData(
        bin_edges=edges,
        counts_before=counts_before,
        counts_after=counts_after,
        median_before=med_before,
        median_after=med_after,
        mad_before=mad_before,
        mad_after=mad_after,
    )

    chart_img = render_histogram_chart_qimage(
        hist_data,
        vmin=vmin,
        vmax=vmax,
        method_label=cfg.method.value,
    )

    # Konversi display_data [0.0, 1.0] langsung menjadi QImage 8-bit untuk tampilan kanvas
    disp_u8 = np.clip(np.rint(display_data * 255.0), 0, 255).astype(np.uint8)
    if disp_u8.ndim == 2:
        h, w = disp_u8.shape
        contig = np.ascontiguousarray(disp_u8)
        display_preview = QImage(
            contig.data, w, h, w, QImage.Format.Format_Grayscale8
        ).copy()
    else:
        h, w, ch = disp_u8.shape
        rgb = np.ascontiguousarray(disp_u8[:, :, :3])
        display_preview = QImage(
            rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888
        ).copy()

    return HistogramTransformResult(
        display_data=display_data,
        display_preview=display_preview,
        histogram_chart_preview=chart_img,
        histogram_data=hist_data,
        config_used=cfg,
        effective_method=cfg.method,
        vmin=vmin,
        vmax=vmax,
        effective_low_percentile=eff_low_percentile if (eff_low_percentile := eff_low_p) is not None else cfg.low_percentile,
        effective_high_percentile=eff_high_p,
        effective_asinh_a=eff_asinh_a,
        effective_midtone_balance=eff_mtf_m,
        valid_pixel_count=valid_count,
        is_uniform_or_degenerate=False,
        warnings=tuple(warnings),
        notes=tuple(notes),
    )
