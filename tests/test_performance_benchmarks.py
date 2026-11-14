"""Suite Performance Benchmarking HILALONE MVP 1.0.

Mengukur waktu eksekusi (detik) dan memori puncak (MB) secara ilmiah pada:
  1. Stacking Engine: Basic, Medium, High
  2. Background Extraction: Polynomial Deg 1, Polynomial Deg 2, TPS RBF, Auto Robust RBF
  3. Image Enhancement: CLAHE Mono & RGB Luminance-Aware
  4. Histogram Transformation: Linear MTF, Asinh MTF, Adaptive Asinh MTF, GHS MTF
  5. Flat-Field Calibration: Normalisasi Master Flat & Aplikasi Pembagian Terlindungi

Setiap pengukuran diulang sebanyak 3 kali (menggunakan median) untuk memastikan
hasil objektif, stabil, dan dapat diulang (reproducible).
"""

from __future__ import annotations

from pathlib import Path
import statistics
import time
import tracemalloc
from typing import Any, Callable

import numpy as np
import pytest
import tifffile

from hilalone.input_manager.sequence_manager import SequenceManager

from hilalone.processing.background_engine import (
    run_background_extraction,
)
from hilalone.processing.enhancement_engine import (
    run_image_enhancement,
)
from hilalone.processing.histogram_engine import (
    run_histogram_transformation,
)
from hilalone.processing.processing_models import (
    BackgroundExtractionConfig,
    BackgroundModelMethod,
    ImageEnhancementConfig,
    HistogramTransformConfig,
    ProcessingProfile,
    StretchMethod,
)
from hilalone.processing.stacking.engine import run_stacking_on_sequence
from hilalone.processing.stacking.flat_calibration import (
    apply_flat_calibration,
    validate_and_prepare_master_flat,
)
from hilalone.processing.stacking.models import StackingProfile


def _measure_execution(fn: Callable[[], Any], repeat: int = 3) -> tuple[float, float]:
    """Mengukur median runtime (detik) dan peak memory (MB) dari sebuah fungsi."""
    times: list[float] = []
    mems: list[float] = []

    for _ in range(repeat):
        tracemalloc.start()
        t0 = time.perf_counter()
        _res = fn()
        t1 = time.perf_counter()
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        times.append(t1 - t0)
        mems.append(peak / (1024 * 1024))

    median_time = statistics.median(times)
    median_mem = statistics.median(mems)
    return median_time, median_mem


def test_benchmark_stacking_profiles(tmp_path: Path) -> None:
    """Benchmark performa algoritma Stacking: Basic vs Medium vs High."""
    h, w = 128, 128
    num_frames = 6
    rng = np.random.default_rng(42)

    seq_dir = tmp_path / "bench_stack"
    seq_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i in range(num_frames):
        p = seq_dir / f"f_{i:03d}.tif"
        arr = rng.normal(loc=1000.0, scale=35.0, size=(h, w)).astype(np.float32)
        tifffile.imwrite(str(p), arr)
        paths.append(p)

    sm = SequenceManager()
    sm.open_files(paths)

    # 1. Basic (Arithmetic Mean)
    t_basic, m_basic = _measure_execution(
        lambda: run_stacking_on_sequence(sm, profile=StackingProfile.BASIC)
    )

    # 2. Medium (Iterative Sigma-Clipped Mean)
    t_med, m_med = _measure_execution(
        lambda: run_stacking_on_sequence(sm, profile=StackingProfile.MEDIUM)
    )

    # 3. High (Quality-Weighted Robust Stacking)
    t_high, m_high = _measure_execution(
        lambda: run_stacking_on_sequence(sm, profile=StackingProfile.HIGH)
    )

    print(f"\n[BENCHMARK STACKING] ({num_frames} frames, {w}x{h} px, float32):")
    print(f"  - BASIC  : {t_basic*1000:.2f} ms | RAM Peak: {m_basic:.2f} MB")
    print(f"  - MEDIUM : {t_med*1000:.2f} ms | RAM Peak: {m_med:.2f} MB")
    print(f"  - HIGH   : {t_high*1000:.2f} ms | RAM Peak: {m_high:.2f} MB")

    assert t_basic > 0.0
    assert t_med > 0.0
    assert t_high > 0.0


def test_benchmark_background_extraction_methods() -> None:
    """Benchmark pemodelan background: Poly 1, Poly 2, TPS RBF, dan Auto Robust RBF."""
    h, w = 256, 256
    rng = np.random.default_rng(123)
    # Gradien langit miring + derau
    y, x = np.ogrid[:h, :w]
    grad = (0.5 * x + 0.8 * y).astype(np.float32)
    noise = rng.normal(0, 10, (h, w)).astype(np.float32)
    raw_img = (1000.0 + grad + noise).astype(np.float32)

    # 1. Polynomial Deg 1
    cfg_p1 = BackgroundExtractionConfig(method=BackgroundModelMethod.POLYNOMIAL_DEG_1)
    t_p1, m_p1 = _measure_execution(lambda: run_background_extraction(raw_img, config=cfg_p1))

    # 2. Polynomial Deg 2
    cfg_p2 = BackgroundExtractionConfig(method=BackgroundModelMethod.POLYNOMIAL_DEG_2)
    t_p2, m_p2 = _measure_execution(lambda: run_background_extraction(raw_img, config=cfg_p2))

    # 3. Thin Plate Spline RBF
    cfg_tps = BackgroundExtractionConfig(method=BackgroundModelMethod.TPS_RBF)
    t_tps, m_tps = _measure_execution(lambda: run_background_extraction(raw_img, config=cfg_tps))

    # 4. Auto Robust Mesh RBF
    cfg_auto = BackgroundExtractionConfig(method=BackgroundModelMethod.AUTO_ROBUST_RBF)
    t_auto, m_auto = _measure_execution(lambda: run_background_extraction(raw_img, config=cfg_auto))

    print(f"\n[BENCHMARK BACKGROUND] ({w}x{h} px, float32):")
    print(f"  - Poly 1     : {t_p1*1000:.2f} ms | RAM Peak: {m_p1:.2f} MB")
    print(f"  - Poly 2     : {t_p2*1000:.2f} ms | RAM Peak: {m_p2:.2f} MB")
    print(f"  - TPS RBF    : {t_tps*1000:.2f} ms | RAM Peak: {m_tps:.2f} MB")
    print(f"  - Auto RBF   : {t_auto*1000:.2f} ms | RAM Peak: {m_auto:.2f} MB")

    assert t_p1 > 0.0
    assert t_p2 > 0.0
    assert t_tps > 0.0
    assert t_auto > 0.0


def test_benchmark_image_enhancement_clahe() -> None:
    """Benchmark peningkatan kontras lokal CLAHE pada citra Mono & RGB."""
    h, w = 256, 256
    rng = np.random.default_rng(456)
    mono_img = rng.uniform(0.1, 0.9, (h, w)).astype(np.float32)
    rgb_img = rng.uniform(0.1, 0.9, (h, w, 3)).astype(np.float32)

    cfg = ImageEnhancementConfig(enabled=True, clip_limit=0.012)

    t_mono, m_mono = _measure_execution(lambda: run_image_enhancement(mono_img, config=cfg))
    t_rgb, m_rgb = _measure_execution(lambda: run_image_enhancement(rgb_img, config=cfg))

    print(f"\n[BENCHMARK CLAHE] ({w}x{h} px, float32):")
    print(f"  - Mono CLAHE : {t_mono*1000:.2f} ms | RAM Peak: {m_mono:.2f} MB")
    print(f"  - RGB CLAHE  : {t_rgb*1000:.2f} ms | RAM Peak: {m_rgb:.2f} MB")

    assert t_mono > 0.0
    assert t_rgb > 0.0


def test_benchmark_histogram_transform_stretches(qapp: object) -> None:
    """Benchmark peregangan histogram display: Linear MTF, Asinh MTF, Adaptive Asinh MTF, GHS MTF."""
    h, w = 256, 256
    rng = np.random.default_rng(789)
    img = rng.exponential(scale=0.05, size=(h, w)).astype(np.float32)
    img = np.clip(img, 0.0, 1.0)

    # 1. Linear MTF
    cfg_lin = HistogramTransformConfig(method=StretchMethod.LINEAR_MTF)
    t_lin, m_lin = _measure_execution(lambda: run_histogram_transformation(img, config=cfg_lin))

    # 2. Asinh MTF
    cfg_asinh = HistogramTransformConfig(method=StretchMethod.ASINH_MTF)
    t_asinh, m_asinh = _measure_execution(lambda: run_histogram_transformation(img, config=cfg_asinh))

    # 3. Adaptive Asinh MTF
    cfg_adapt = HistogramTransformConfig(method=StretchMethod.ADAPTIVE_ASINH_MTF)
    t_adapt, m_adapt = _measure_execution(lambda: run_histogram_transformation(img, config=cfg_adapt))

    # 4. GHS MTF
    cfg_ghs = HistogramTransformConfig(method=StretchMethod.GHS_MTF)
    t_ghs, m_ghs = _measure_execution(lambda: run_histogram_transformation(img, config=cfg_ghs))

    print(f"\n[BENCHMARK HISTOGRAM] ({w}x{h} px, float32):")
    print(f"  - Linear MTF         : {t_lin*1000:.2f} ms | RAM Peak: {m_lin:.2f} MB")
    print(f"  - Asinh MTF          : {t_asinh*1000:.2f} ms | RAM Peak: {m_asinh:.2f} MB")
    print(f"  - Adaptive Asinh MTF : {t_adapt*1000:.2f} ms | RAM Peak: {m_adapt:.2f} MB")
    print(f"  - GHS MTF            : {t_ghs*1000:.2f} ms | RAM Peak: {m_ghs:.2f} MB")

    assert t_lin > 0.0
    assert t_asinh > 0.0
    assert t_adapt > 0.0
    assert t_ghs > 0.0


def test_benchmark_flat_field_calibration() -> None:
    """Benchmark kalibrasi flat: validasi master flat dan koreksi pembagian piksel."""
    h, w = 256, 256
    rng = np.random.default_rng(999)

    light_frame = rng.normal(1200.0, 50.0, (h, w)).astype(np.float32)
    # Master flat dengan vignetting radial
    y, x = np.ogrid[:h, :w]
    r = np.sqrt((x - w / 2) ** 2 + (y - h / 2) ** 2)
    raw_flat = (20000.0 * (1.0 - 0.3 * (r / (w / 2)))).astype(np.float32)

    # 1. Normalisasi master flat
    t_norm, m_norm = _measure_execution(
        lambda: validate_and_prepare_master_flat(raw_flat, expected_height=h, expected_width=w, expected_channels=1)
    )

    norm_flat, meta = validate_and_prepare_master_flat(raw_flat, expected_height=h, expected_width=w, expected_channels=1)

    # 2. Aplikasi kalibrasi pembagian
    t_apply, m_apply = _measure_execution(
        lambda: apply_flat_calibration(light_frame, norm_flat)
    )

    print(f"\n[BENCHMARK FLAT FIELD] ({w}x{h} px, float32):")
    print(f"  - Normalisasi Flat   : {t_norm*1000:.2f} ms | RAM Peak: {m_norm:.2f} MB")
    print(f"  - Aplikasi Flat      : {t_apply*1000:.2f} ms | RAM Peak: {m_apply:.2f} MB")

    assert t_norm > 0.0
    assert t_apply > 0.0
