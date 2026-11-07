"""Profile Manager HILALONE — Penghubung konfigurasi deklaratif ketiga engine pemrosesan.

Sesuai AGENTS.md Bagian 3 & 8 serta spesifikasi bagian 6:
  * Profil ``BASIC``, ``MEDIUM``, dan ``HIGH`` didefinisikan sebagai objek
    konfigurasi deklaratif ``UnifiedProfileConfig``, bukan percabangan ``if``
    yang tersebar.
  * Setiap profil menghubungkan:
      1. Automatic Stacking (jika multi-frame/video/SER)
      2. Engine 1 — Background Extraction
      3. Engine 2 — Image Enhancement (CLAHE)
      4. Engine 3 — Histogram Transformation
  * Setiap profil wajib menyertakan penjelasan karakteristik dan risiko ilmiah
    secara jujur (tidak mengklaim profil ``HIGH`` selalu terbaik).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from hilalone.processing.processing_models import (
    BackgroundExtractionConfig,
    BackgroundModelMethod,
    EnhancementMethod,
    HistogramTransformConfig,
    ImageEnhancementConfig,
    ProcessingError,
    ProcessingProfile,
    ProtectedRegionROI,
    StretchMethod,
)
from hilalone.processing.stacking.models import (
    StackingProfileConfig,
    get_stacking_profile_config,
)


@dataclass(frozen=True)
class UnifiedProfileConfig:
    """Konfigurasi lengkap satu profil pemrosesan otomatis HILALONE."""

    profile: ProcessingProfile
    display_name: str
    short_summary_id: str
    characteristics_id: str
    risk_note_id: str
    stacking_config: StackingProfileConfig
    background_config: BackgroundExtractionConfig
    enhancement_config: ImageEnhancementConfig
    histogram_config: HistogramTransformConfig


UNIFIED_PROFILE_CONFIGS: dict[ProcessingProfile, UnifiedProfileConfig] = {
    ProcessingProfile.BASIC: UnifiedProfileConfig(
        profile=ProcessingProfile.BASIC,
        display_name="Basic — Konservatif (Polinomial Derajat 1 + CLAHE Ringan + Linear/MTF)",
        short_summary_id="Polinomial derajat 1, Mean Stacking, CLAHE ringan, Linear + MTF",
        characteristics_id=(
            "Menggunakan model bidang miring linear (Polinomial derajat 1), CLAHE ringan "
            "(clip_limit=0.008, tiles 6×6), dan peregangan Linear + MTF. Sangat aman untuk "
            "menjaga keutuhan bentuk sabit hilal pada langit senja bergradien lurus."
        ),
        risk_note_id=(
            "Risiko overcorrection paling rendah, namun kurang mampu meratakan gradien "
            "langit senja yang melengkung kompleks atau vignetting sisa di tepi bidang."
        ),
        stacking_config=get_stacking_profile_config(ProcessingProfile.BASIC.to_stacking_profile()),
        background_config=BackgroundExtractionConfig(
            enabled=True,
            method=BackgroundModelMethod.POLYNOMIAL_DEG_1,
            grid_rows=6,
            grid_cols=6,
            mad_sigma_clip=3.0,
            max_rejection_iterations=2,
            rbf_smoothing=2.0,
            overcorrection_warn_ratio=0.18,
        ),
        enhancement_config=ImageEnhancementConfig(
            enabled=True,
            method=EnhancementMethod.CLAHE,
            clip_limit=0.008,
            kernel_tiles=(6, 6),
            nbins=256,
            adaptive_parameters=False,
            max_noise_amplification_ratio=1.8,
        ),
        histogram_config=HistogramTransformConfig(
            enabled=True,
            method=StretchMethod.LINEAR_MTF,
            low_percentile=0.50,
            high_percentile=99.80,
            asinh_a=0.25,
            midtone_balance=0.35,
            adaptive_parameters=False,
            target_background_median=0.18,
        ),
    ),
    ProcessingProfile.MEDIUM: UnifiedProfileConfig(
        profile=ProcessingProfile.MEDIUM,
        display_name="Medium — Seimbang (Polinomial Derajat 2 / RBF + CLAHE Moderat + Asinh/MTF)",
        short_summary_id="Polinomial derajat 2 / RBF, Sigma-Clipped Mean, CLAHE moderat, Asinh + MTF",
        characteristics_id=(
            "Menggunakan permukaan Polinomial derajat 2 (atau Thin Plate Spline RBF) dengan "
            "sampling 10×10 dan penolakan outlier MAD, CLAHE moderat (clip_limit=0.014, tiles 8×8), "
            "serta peregangan Asinh + MTF untuk menonjolkan sabit tipis tanpa membakar area terang."
        ),
        risk_note_id=(
            "Risiko moderat: jika sabit hilal berukuran besar di tengah frame, disarankan "
            "menandai Wilayah Proteksi (Protected ROI) agar kelengkungan model tidak menyerap sabit."
        ),
        stacking_config=get_stacking_profile_config(ProcessingProfile.MEDIUM.to_stacking_profile()),
        background_config=BackgroundExtractionConfig(
            enabled=True,
            method=BackgroundModelMethod.POLYNOMIAL_DEG_2,
            grid_rows=10,
            grid_cols=10,
            mad_sigma_clip=2.5,
            max_rejection_iterations=3,
            rbf_smoothing=1.5,
            overcorrection_warn_ratio=0.18,
        ),
        enhancement_config=ImageEnhancementConfig(
            enabled=True,
            method=EnhancementMethod.CLAHE,
            clip_limit=0.014,
            kernel_tiles=(8, 8),
            nbins=256,
            adaptive_parameters=False,
            max_noise_amplification_ratio=2.2,
        ),
        histogram_config=HistogramTransformConfig(
            enabled=True,
            method=StretchMethod.ASINH_MTF,
            low_percentile=0.25,
            high_percentile=99.85,
            asinh_a=0.15,
            midtone_balance=0.30,
            adaptive_parameters=False,
            target_background_median=0.18,
        ),
    ),
    ProcessingProfile.HIGH: UnifiedProfileConfig(
        profile=ProcessingProfile.HIGH,
        display_name="High — Adaptif (Auto Robust Mesh RBF + CLAHE Adaptif + Adaptive Asinh/MTF)",
        short_summary_id="Auto Robust Mesh + RBF, Quality-Weighted Robust Stacking, CLAHE adaptif, Adaptive Asinh + MTF",
        characteristics_id=(
            "Menggunakan estimasi mesh otomatis + Regularized Thin Plate Spline RBF adaptif, "
            "CLAHE dengan pemilihan parameter berbasis kontras/derau citra, dan Adaptive Asinh + MTF."
        ),
        risk_note_id=(
            "PERHATIAN: Profil High TIDAK selalu menghasilkan hasil terbaik untuk setiap citra. "
            "Model RBF yang fleksibel dan peregangan agresif berisiko menyebabkan overcorrection "
            "pada struktur ber-kontras rendah atau memperkuat derau (noise) langit bila SNR rendah. "
            "Gunakan Wilayah Proteksi (Protected ROI) di sekitar posisi sabit bila diperlukan."
        ),
        stacking_config=get_stacking_profile_config(ProcessingProfile.HIGH.to_stacking_profile()),
        background_config=BackgroundExtractionConfig(
            enabled=True,
            method=BackgroundModelMethod.AUTO_ROBUST_RBF,
            grid_rows=12,
            grid_cols=12,
            mad_sigma_clip=2.2,
            max_rejection_iterations=4,
            rbf_smoothing=2.0,
            overcorrection_warn_ratio=0.16,
        ),
        enhancement_config=ImageEnhancementConfig(
            enabled=True,
            method=EnhancementMethod.CLAHE,
            clip_limit=0.018,
            kernel_tiles=(10, 10),
            nbins=256,
            adaptive_parameters=True,
            max_noise_amplification_ratio=2.4,
        ),
        histogram_config=HistogramTransformConfig(
            enabled=True,
            method=StretchMethod.ADAPTIVE_ASINH_MTF,
            low_percentile=0.15,
            high_percentile=99.90,
            asinh_a=0.10,
            midtone_balance=0.26,
            adaptive_parameters=True,
            target_background_median=0.19,
        ),
    ),
}


def get_unified_profile_config(profile: ProcessingProfile | str) -> UnifiedProfileConfig:
    """Mengambil objek ``UnifiedProfileConfig`` berdasarkan enum atau string nama profil."""
    if isinstance(profile, ProcessingProfile):
        return UNIFIED_PROFILE_CONFIGS[profile]
    norm = str(profile).strip().upper()
    try:
        enum_val = ProcessingProfile(norm)
    except ValueError as exc:
        valid = ", ".join(p.value for p in ProcessingProfile)
        raise ProcessingError(
            f"Profil pemrosesan '{profile}' tidak dikenal. Pilihan yang valid: {valid}."
        ) from exc
    return UNIFIED_PROFILE_CONFIGS[enum_val]


def customize_profile_config(
    base_profile: ProcessingProfile | str,
    *,
    background_method: BackgroundModelMethod | str | None = None,
    grid_rows: int | None = None,
    grid_cols: int | None = None,
    mad_sigma_clip: float | None = None,
    rbf_smoothing: float | None = None,
    protected_regions: tuple[ProtectedRegionROI, ...] | None = None,
    protected_mask: object | None = None,
    manual_include_points: tuple[tuple[int, int], ...] | None = None,
    manual_exclude_points: tuple[tuple[int, int], ...] | None = None,
    clahe_enabled: bool | None = None,
    clahe_clip_limit: float | None = None,
    clahe_kernel_tiles: tuple[int, int] | None = None,
    clahe_adaptive: bool | None = None,
    stretch_method: StretchMethod | str | None = None,
    low_percentile: float | None = None,
    high_percentile: float | None = None,
    asinh_a: float | None = None,
    midtone_balance: float | None = None,
    ghs_stretch_factor_d: float | None = None,
    ghs_local_intensity_b: float | None = None,
    ghs_symmetry_point_sp: float | None = None,
    is_cfa_mosaic: bool = False,
    cfa_pattern_str: str | None = None,
) -> UnifiedProfileConfig:
    """Membuat salinan ``UnifiedProfileConfig`` dengan penyesuaian Advanced Settings pengguna."""
    base = get_unified_profile_config(base_profile)

    bg_cfg = base.background_config
    if background_method is not None:
        m_val = (
            background_method
            if isinstance(background_method, BackgroundModelMethod)
            else BackgroundModelMethod(str(background_method).strip().upper())
        )
        bg_cfg = replace(bg_cfg, method=m_val)
    if grid_rows is not None:
        bg_cfg = replace(bg_cfg, grid_rows=max(2, int(grid_rows)))
    if grid_cols is not None:
        bg_cfg = replace(bg_cfg, grid_cols=max(2, int(grid_cols)))
    if mad_sigma_clip is not None:
        bg_cfg = replace(bg_cfg, mad_sigma_clip=max(1.0, float(mad_sigma_clip)))
    if rbf_smoothing is not None:
        bg_cfg = replace(bg_cfg, rbf_smoothing=max(0.0, float(rbf_smoothing)))
    if protected_regions is not None:
        bg_cfg = replace(bg_cfg, protected_regions=tuple(protected_regions))
    if protected_mask is not None:
        bg_cfg = replace(bg_cfg, protected_mask=protected_mask)  # type: ignore[arg-type]
    if manual_include_points is not None:
        bg_cfg = replace(bg_cfg, manual_include_points=tuple(manual_include_points))
    if manual_exclude_points is not None:
        bg_cfg = replace(bg_cfg, manual_exclude_points=tuple(manual_exclude_points))
    bg_cfg = replace(
        bg_cfg,
        is_cfa_mosaic=bool(is_cfa_mosaic),
        cfa_pattern_str=cfa_pattern_str,
    )

    enh_cfg = base.enhancement_config
    if clahe_enabled is not None:
        enh_cfg = replace(enh_cfg, enabled=bool(clahe_enabled))
    if clahe_clip_limit is not None:
        enh_cfg = replace(enh_cfg, clip_limit=float(max(0.001, min(0.20, clahe_clip_limit))))
    if clahe_kernel_tiles is not None:
        enh_cfg = replace(
            enh_cfg,
            kernel_tiles=(max(2, int(clahe_kernel_tiles[0])), max(2, int(clahe_kernel_tiles[1]))),
        )
    if clahe_adaptive is not None:
        enh_cfg = replace(enh_cfg, adaptive_parameters=bool(clahe_adaptive))
    enh_cfg = replace(
        enh_cfg,
        is_cfa_mosaic=bool(is_cfa_mosaic),
        cfa_pattern_str=cfa_pattern_str,
    )

    hist_cfg = base.histogram_config
    if stretch_method is not None:
        s_val = (
            stretch_method
            if isinstance(stretch_method, StretchMethod)
            else StretchMethod(str(stretch_method).strip().upper())
        )
        hist_cfg = replace(hist_cfg, method=s_val)
    if low_percentile is not None:
        hist_cfg = replace(hist_cfg, low_percentile=float(max(0.0, min(49.0, low_percentile))))
    if high_percentile is not None:
        hist_cfg = replace(hist_cfg, high_percentile=float(max(51.0, min(100.0, high_percentile))))
    if asinh_a is not None:
        hist_cfg = replace(hist_cfg, asinh_a=float(max(1e-4, min(10.0, asinh_a))))
    if midtone_balance is not None:
        hist_cfg = replace(
            hist_cfg, midtone_balance=float(max(0.01, min(0.99, midtone_balance)))
        )
    if ghs_stretch_factor_d is not None:
        hist_cfg = replace(hist_cfg, ghs_stretch_factor_d=float(max(0.0, ghs_stretch_factor_d)))
    if ghs_local_intensity_b is not None:
        hist_cfg = replace(hist_cfg, ghs_local_intensity_b=float(max(-5.0, min(15.0, ghs_local_intensity_b))))
    if ghs_symmetry_point_sp is not None:
        hist_cfg = replace(hist_cfg, ghs_symmetry_point_sp=float(max(0.0, min(1.0, ghs_symmetry_point_sp))))

    return replace(
        base,
        background_config=bg_cfg,
        enhancement_config=enh_cfg,
        histogram_config=hist_cfg,
    )
