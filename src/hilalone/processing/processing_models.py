"""Model data terpadu untuk Full Automated Image Processing Pipeline HILALONE.

Modul ini mendefinisikan struktur data, konfigurasi, status tahap, dan produk
ilmiah terpisah untuk:
  1. Engine 1 — Background Extraction (Polinomial, Thin Plate Spline RBF, &
     Automatic Robust Mesh + Protected Region ROI).
  2. Engine 2 — Image Enhancement (CLAHE konservatif, moderat, & adaptif).
  3. Engine 3 — Histogram Transformation (Linear + MTF, Asinh + MTF, Adaptive
     Asinh + MTF, & Generalized Hyperbolic Stretch / GHS).
  4. Processing Orchestrator & Scientific Data Management (pemisahan ketat
     antara ``original_data``, ``calibrated_data``, ``stacked_data``,
     ``linear_result``, ``enhanced_result``, dan ``display_result``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
from PySide6.QtGui import QImage

from hilalone.processing.stacking.models import (
    FlatCalibrationReport,
    StackingProfile,
    StackingResult,
)


class ProcessingError(Exception):
    """Galat selama eksekusi pipeline pemrosesan citra; pesan berbahasa Indonesia."""


class ProcessingCancelledError(ProcessingError):
    """Dilempar ketika pengguna membatalkan pipeline pemrosesan yang sedang berjalan."""


class ProcessingProfile(str, Enum):
    """Tiga profil pemrosesan otomatis HILALONE (Basic, Medium, High)."""

    BASIC = "BASIC"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    def to_stacking_profile(self) -> StackingProfile:
        return StackingProfile(self.value)


class PipelineStage(str, Enum):
    """Tahap-tahap berurutan di dalam Processing Orchestrator."""

    INPUT_VALIDATION = "INPUT_VALIDATION"
    FLAT_CALIBRATION = "FLAT_CALIBRATION"
    STACKING = "STACKING"
    BACKGROUND_EXTRACTION = "BACKGROUND_EXTRACTION"
    IMAGE_ENHANCEMENT = "IMAGE_ENHANCEMENT"
    HISTOGRAM_TRANSFORMATION = "HISTOGRAM_TRANSFORMATION"
    COMPLETED = "COMPLETED"


class StageStatus(str, Enum):
    """Status eksekusi setiap tahap di dalam pipeline."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PreviewMode(str, Enum):
    """Mode tampilan pratinjau hasil pemrosesan pada kanvas GUI."""

    ORIGINAL = "ORIGINAL"
    BACKGROUND_MODEL = "BACKGROUND_MODEL"
    BACKGROUND_CORRECTED = "BACKGROUND_CORRECTED"
    ENHANCED = "ENHANCED"
    FINAL_DISPLAY = "FINAL_DISPLAY"


# =====================================================================
# ENGINE 1: BACKGROUND EXTRACTION MODELS
# =====================================================================
class BackgroundModelMethod(str, Enum):
    """Metode pemodelan permukaan gradien background langit senja."""

    POLYNOMIAL_DEG_1 = "POLYNOMIAL_DEG_1"
    POLYNOMIAL_DEG_2 = "POLYNOMIAL_DEG_2"
    TPS_RBF = "TPS_RBF"
    AUTO_ROBUST_RBF = "AUTO_ROBUST_RBF"


@dataclass(frozen=True)
class ProtectedRegionROI:
    """Wilayah proteksi manual (Rectangle atau Polygon) agar area sabit tidak ikut disampel.

    Catatan penting:
      * Ini adalah alat proteksi wilayah pilihan pengguna, BUKAN deteksi hilal otomatis.
      * Mask disimpan terpisah dan TIDAK mengubah data piksel sumber.
    """

    shape_type: str = "RECTANGLE"  # "RECTANGLE" atau "POLYGON"
    rect: tuple[int, int, int, int] | None = None  # (x, y, width, height)
    polygon: tuple[tuple[float, float], ...] | None = None  # ((x1, y1), (x2, y2), ...)
    label: str = "Wilayah Proteksi Manual"

    def build_mask(self, height: int, width: int) -> np.ndarray:
        """Membangun mask boolean 2D ``(height, width)`` di mana ``True`` berarti terlindungi."""
        mask = np.zeros((height, width), dtype=bool)
        if height <= 0 or width <= 0:
            return mask

        kind = self.shape_type.strip().upper()
        if kind == "RECTANGLE" and self.rect is not None:
            rx, ry, rw, rh = self.rect
            x0 = max(0, min(width, int(round(min(rx, rx + rw)))))
            x1 = max(0, min(width, int(round(max(rx, rx + rw)))))
            y0 = max(0, min(height, int(round(min(ry, ry + rh)))))
            y1 = max(0, min(height, int(round(max(ry, ry + rh)))))
            if x1 > x0 and y1 > y0:
                mask[y0:y1, x0:x1] = True
            return mask

        if kind == "POLYGON" and self.polygon is not None and len(self.polygon) >= 3:
            pts = np.asarray(self.polygon, dtype=np.float64)
            min_x = max(0, int(np.floor(np.min(pts[:, 0]))))
            max_x = min(width - 1, int(np.ceil(np.max(pts[:, 0]))))
            min_y = max(0, int(np.floor(np.min(pts[:, 1]))))
            max_y = min(height - 1, int(np.ceil(np.max(pts[:, 1]))))
            if max_x < min_x or max_y < min_y:
                return mask

            yy, xx = np.mgrid[min_y : max_y + 1, min_x : max_x + 1].astype(np.float64)
            inside = np.zeros(xx.shape, dtype=bool)
            n_vert = len(pts)
            x_prev, y_prev = pts[-1, 0], pts[-1, 1]
            for i in range(n_vert):
                x_curr, y_curr = pts[i, 0], pts[i, 1]
                cond = (y_curr > yy) != (y_prev > yy)
                denom = y_prev - y_curr
                safe_denom = np.where(np.abs(denom) > 1e-12, denom, 1.0)
                x_intersect = (x_prev - x_curr) * (yy - y_curr) / safe_denom + x_curr
                inside ^= cond & (xx < x_intersect)
                x_prev, y_prev = x_curr, y_curr

            mask[min_y : max_y + 1, min_x : max_x + 1] = inside
        return mask


@dataclass(frozen=True)
class BackgroundSamplePoint:
    """Satu titik sampel grid/manual untuk pemodelan permukaan background langit."""

    x: float
    y: float
    value: float
    local_mad: float
    accepted: bool
    is_manual: bool = False
    rejection_reason: str | None = None


@dataclass(frozen=True)
class BackgroundExtractionConfig:
    """Konfigurasi deklaratif untuk Engine 1 — Background Extraction."""

    enabled: bool = True
    method: BackgroundModelMethod = BackgroundModelMethod.POLYNOMIAL_DEG_2
    grid_rows: int = 8
    grid_cols: int = 8
    mad_sigma_clip: float = 2.5
    max_rejection_iterations: int = 3
    rbf_smoothing: float = 1.0
    overcorrection_warn_ratio: float = 0.18
    preserve_mean_sky_pedestal: bool = False
    protected_regions: tuple[ProtectedRegionROI, ...] = ()
    protected_mask: np.ndarray | None = None
    manual_include_points: tuple[tuple[int, int], ...] = ()
    manual_exclude_points: tuple[tuple[int, int], ...] = ()
    is_cfa_mosaic: bool = False
    cfa_pattern_str: str | None = None


@dataclass(frozen=True)
class BackgroundResidualStats:
    """Statistik kuantitatif model background dan residual setelah koreksi subtractive."""

    initial_gradient_ptp: float
    residual_gradient_ptp: float
    gradient_reduction_ratio: float
    background_median_before: float
    background_median_after: float
    residual_rms: float
    residual_mad_sigma: float
    overcorrection_score: float
    overcorrection_warning: bool


@dataclass(frozen=True)
class BackgroundExtractionResult:
    """Hasil lengkap Engine 1 — Background Extraction."""

    linear_corrected_data: np.ndarray  # float32: I_corrected(x,y) = I_linear(x,y) - B_model(x,y)
    background_model: np.ndarray       # float32: B_model(x,y)
    sample_points: tuple[BackgroundSamplePoint, ...]
    accepted_sample_count: int
    rejected_sample_count: int
    protected_pixel_count: int
    protected_mask: np.ndarray         # (H, W) bool
    residual_stats: BackgroundResidualStats
    config_used: BackgroundExtractionConfig
    effective_method: BackgroundModelMethod
    effective_rbf_smoothing: float
    cfa_subchannel_modeled: bool
    model_preview: QImage
    overlay_preview: QImage
    corrected_preview: QImage
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


# =====================================================================
# ENGINE 2: IMAGE ENHANCEMENT MODELS (CLAHE)
# =====================================================================
class EnhancementMethod(str, Enum):
    """Metode penguatan kontras lokal (Local Contrast Enhancement)."""

    CLAHE = "CLAHE"


@dataclass(frozen=True)
class ImageEnhancementConfig:
    """Konfigurasi deklaratif untuk Engine 2 — Image Enhancement (CLAHE)."""

    enabled: bool = True
    method: EnhancementMethod = EnhancementMethod.CLAHE
    clip_limit: float = 0.012
    kernel_tiles: tuple[int, int] = (8, 8)
    nbins: int = 256
    adaptive_parameters: bool = False
    max_noise_amplification_ratio: float = 2.5
    is_cfa_mosaic: bool = False
    cfa_pattern_str: str | None = None


@dataclass(frozen=True)
class ImageEnhancementResult:
    """Hasil lengkap Engine 2 — Image Enhancement (CLAHE)."""

    enhanced_data: np.ndarray  # float32 derived nonlinear image (terpisah dari linear_result)
    config_used: ImageEnhancementConfig
    effective_clip_limit: float
    effective_kernel_tiles: tuple[int, int]
    backend_used: str
    color_mode: str
    working_min: float
    working_max: float
    noise_sigma_before: float
    noise_sigma_after: float
    noise_amplification_ratio: float
    local_contrast_before: float
    local_contrast_after: float
    enhanced_preview: QImage
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


# =====================================================================
# ENGINE 3: HISTOGRAM TRANSFORMATION MODELS
# =====================================================================
class StretchMethod(str, Enum):
    """Metode peregangan tampilan (Display Histogram Transformation)."""

    LINEAR_MTF = "LINEAR_MTF"
    ASINH_MTF = "ASINH_MTF"
    ADAPTIVE_ASINH_MTF = "ADAPTIVE_ASINH_MTF"
    GHS_MTF = "GHS_MTF"


@dataclass(frozen=True)
class HistogramData:
    """Data distribusi histogram sebelum dan sesudah transformasi tampilan."""

    bin_edges: np.ndarray
    counts_before: np.ndarray
    counts_after: np.ndarray
    median_before: float
    median_after: float
    mad_before: float
    mad_after: float


@dataclass(frozen=True)
class HistogramTransformConfig:
    """Konfigurasi deklaratif untuk Engine 3 — Histogram Transformation."""

    enabled: bool = True
    method: StretchMethod = StretchMethod.ASINH_MTF
    low_percentile: float = 0.25
    high_percentile: float = 99.85
    asinh_a: float = 0.15
    midtone_balance: float = 0.30
    ghs_stretch_factor_d: float = 2.0
    ghs_local_intensity_b: float = 1.5
    ghs_symmetry_point_sp: float = 0.15
    adaptive_parameters: bool = False
    target_background_median: float = 0.18


@dataclass(frozen=True)
class HistogramTransformResult:
    """Hasil lengkap Engine 3 — Histogram Transformation."""

    display_data: np.ndarray  # float32 dalam [0.0, 1.0] khusus untuk cabang display
    display_preview: QImage
    histogram_chart_preview: QImage
    histogram_data: HistogramData
    config_used: HistogramTransformConfig
    effective_method: StretchMethod
    vmin: float
    vmax: float
    effective_low_percentile: float
    effective_high_percentile: float
    effective_asinh_a: float
    effective_midtone_balance: float
    valid_pixel_count: int
    is_uniform_or_degenerate: bool
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


# =====================================================================
# PIPELINE ORCHESTRATOR & SCIENTIFIC DATA MANAGEMENT MODELS
# =====================================================================
@dataclass(frozen=True)
class StageExecutionRecord:
    """Catatan eksekusi per tahap di dalam pipeline terintegrasi."""

    stage: PipelineStage
    status: StageStatus
    summary: str
    parameters: dict[str, Any] = field(default_factory=dict)
    input_description: str = ""
    output_description: str = ""
    duration_ms: float = 0.0
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelineResult:
    """Hasil terpadu dari seluruh tahapan Automated Image Processing Pipeline HILALONE.

    Memisahkan secara eksplisit keenam cabang data:
      A. ``original_data``   : Data sumber asli (immutable float32 copy).
      B. ``calibrated_data`` : Data setelah kalibrasi Master Flat opsional.
      C. ``stacked_data``    : Hasil stacking (jika multi-frame/video/SER; ``None`` jika Single Image).
      D. ``linear_result``   : Hasil ilmiah linear setelah Background Extraction (``float32``).
      E. ``enhanced_result`` : Citra turunan nonlinear setelah CLAHE (``float32`` terpisah).
      F. ``display_result``  : Citra cabang tampilan ``[0.0, 1.0]`` setelah Histogram Transformation.
    """

    profile: ProcessingProfile
    input_mode: str
    original_data: np.ndarray
    calibrated_data: np.ndarray | None
    stacked_data: np.ndarray | None
    background_model: np.ndarray
    linear_result: np.ndarray
    enhanced_result: np.ndarray
    display_result: np.ndarray
    flat_report: FlatCalibrationReport | None
    stacking_result: StackingResult | None
    background_result: BackgroundExtractionResult
    enhancement_result: ImageEnhancementResult
    histogram_result: HistogramTransformResult
    stage_records: tuple[StageExecutionRecord, ...]
    previews: dict[PreviewMode, QImage]
    is_cfa_mosaic: bool = False
    cfa_pattern_str: str | None = None
    source_file_names: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
