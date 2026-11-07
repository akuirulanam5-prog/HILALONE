"""Paket pemrosesan citra ilmiah HILALONE.

Berisi modul-modul pemrosesan modular yang terpisah sepenuhnya dari antarmuka GUI:
  * ``stacking`` : Automatic Stacking Engine (Basic, Medium, High).
  * ``background_engine`` : Engine 1 — Background Extraction (Polinomial, RBF, Protected ROI).
  * ``enhancement_engine`` : Engine 2 — Image Enhancement (CLAHE).
  * ``histogram_engine`` : Engine 3 — Histogram Transformation (Linear, Asinh, GHS, MTF).
  * ``profile_manager`` : Profile Manager (UnifiedProfileConfig Basic/Medium/High).
  * ``processing_pipeline`` : Processing Orchestrator (Single & Multi-frame pipeline).
"""

from __future__ import annotations

from hilalone.processing.background_engine import (
    build_combined_protected_mask,
    render_background_overlay_preview,
    run_background_extraction,
)
from hilalone.processing.enhancement_engine import run_image_enhancement
from hilalone.processing.histogram_engine import (
    apply_asinh_stretch,
    apply_ghs_stretch,
    apply_mtf,
    compute_robust_percentile_limits,
    render_histogram_chart_qimage,
    run_histogram_transformation,
    solve_mtf_parameter_for_target_median,
)
from hilalone.processing.processing_history import (
    build_pipeline_history_dict,
    populate_fits_header_for_pipeline,
)
from hilalone.processing.processing_models import (
    BackgroundExtractionConfig,
    BackgroundExtractionResult,
    BackgroundModelMethod,
    BackgroundResidualStats,
    BackgroundSamplePoint,
    EnhancementMethod,
    HistogramData,
    HistogramTransformConfig,
    HistogramTransformResult,
    ImageEnhancementConfig,
    ImageEnhancementResult,
    PipelineResult,
    PipelineStage,
    PreviewMode,
    ProcessingCancelledError,
    ProcessingError,
    ProcessingProfile,
    ProtectedRegionROI,
    StageExecutionRecord,
    StageStatus,
    StretchMethod,
)
from hilalone.processing.processing_pipeline import (
    ProcessingPipelineOrchestrator,
)
from hilalone.processing.profile_manager import (
    UNIFIED_PROFILE_CONFIGS,
    UnifiedProfileConfig,
    customize_profile_config,
    get_unified_profile_config,
)

__all__ = [
    "UNIFIED_PROFILE_CONFIGS",
    "BackgroundExtractionConfig",
    "BackgroundExtractionResult",
    "BackgroundModelMethod",
    "BackgroundResidualStats",
    "BackgroundSamplePoint",
    "EnhancementMethod",
    "HistogramData",
    "HistogramTransformConfig",
    "HistogramTransformResult",
    "ImageEnhancementConfig",
    "ImageEnhancementResult",
    "PipelineResult",
    "PipelineStage",
    "PreviewMode",
    "ProcessingCancelledError",
    "ProcessingError",
    "ProcessingPipelineOrchestrator",
    "ProcessingProfile",
    "ProtectedRegionROI",
    "StageExecutionRecord",
    "StageStatus",
    "StretchMethod",
    "UnifiedProfileConfig",
    "apply_asinh_stretch",
    "apply_ghs_stretch",
    "apply_mtf",
    "build_combined_protected_mask",
    "build_pipeline_history_dict",
    "compute_robust_percentile_limits",
    "customize_profile_config",
    "get_unified_profile_config",
    "populate_fits_header_for_pipeline",
    "render_background_overlay_preview",
    "render_histogram_chart_qimage",
    "run_background_extraction",
    "run_histogram_transformation",
    "run_image_enhancement",
    "solve_mtf_parameter_for_target_median",
]
