"""Unit and Integration Tests for HILALONE Full Automated Image Processing Pipeline.

Mencakup seluruh skenario pengujian:
1. Background Extraction Engine (polynomial, RBF, Bayer CFA 2x2, ROI masking, overcorrection safeguard).
2. Image Enhancement Engine (CLAHE grayscale, RGB luminance-aware ratio preservation, noise limiter).
3. Histogram Transformation Engine (Linear+MTF, Asinh+MTF, Adaptive Asinh+MTF, GHS+MTF, monotonicity, histogram chart).
4. Profile Manager (Basic, Medium, High unified presets and customization).
5. Orchestrator & End-to-End Pipeline (Single image, Sequence, Cancellation, Scientific Data Separation).
6. Pipeline Output Writer (FITS cards, TIFF export, PNG preview, JSON report, anti-overwrite protection).
7. Scientific Validation (Synthetic crescent with twilight sky gradient and noise).
"""

from __future__ import annotations

import json
from pathlib import Path

from astropy.io import fits
import numpy as np
from PySide6.QtGui import QImage
import pytest
import tifffile

from hilalone.input_manager.image_reader import ImageInfo
from hilalone.input_manager.sequence_manager import SequenceManager
from hilalone.output_manager.pipeline_writer import save_pipeline_result
from hilalone.output_manager.stacking_writer import OutputWriteError
from hilalone.processing.background_engine import (
    run_background_extraction,
)
from hilalone.processing.enhancement_engine import (
    run_image_enhancement,
)
from hilalone.processing.histogram_engine import (
    apply_asinh_stretch,
    apply_ghs_stretch,
    apply_mtf,
    render_histogram_chart_qimage,
    run_histogram_transformation,
)
from hilalone.processing.processing_models import (
    BackgroundExtractionConfig,
    BackgroundModelMethod,
    EnhancementMethod,
    HistogramTransformConfig,
    ImageEnhancementConfig,
    PipelineResult,
    PipelineStage,
    PreviewMode,
    ProcessingCancelledError,
    ProcessingError,
    ProcessingProfile,
    ProtectedRegionROI,
    StageStatus,
    StretchMethod,
)
from hilalone.processing.processing_pipeline import (
    ProcessingPipelineOrchestrator,
)
from hilalone.processing.profile_manager import (
    customize_profile_config,
    get_unified_profile_config,
)


@pytest.fixture(autouse=True)
def _qt_app(qapp):
    """Memastikan Qt siap sebelum operasi QImage dan QPainter."""
    return qapp


# ============================================================================
# 1. BACKGROUND EXTRACTION ENGINE TESTS
# ============================================================================

class TestBackgroundExtractionEngine:
    """Pengujian ekstraksi dan pemodelan gradien latar belakang langit."""

    def test_polynomial_deg1_exact_plane(self):
        """Polinomial derajat 1 harus memodelkan gradien bidang miring secara presisi."""
        height, width = 120, 160
        y, x = np.mgrid[0:height, 0:width]
        true_bg = (0.2 + 0.001 * x + 0.002 * y).astype(np.float32)

        config = BackgroundExtractionConfig(
            method=BackgroundModelMethod.POLYNOMIAL_DEG_1,
            grid_rows=8,
            grid_cols=8,
            preserve_mean_sky_pedestal=False,
        )
        result = run_background_extraction(true_bg, config)

        assert result.background_model.shape == (height, width)
        residual = result.linear_corrected_data
        np.testing.assert_allclose(residual, 0.0, atol=1e-3)
        assert result.residual_stats.gradient_reduction_ratio > 0.99

    def test_polynomial_deg2_curved_gradient(self):
        """Polinomial derajat 2 harus memodelkan gradien lengkung parabolik."""
        height, width = 100, 100
        y, x = np.mgrid[0:height, 0:width]
        true_bg = (0.1 + 0.0005 * x + 0.00001 * (x ** 2) + 0.00002 * (y ** 2)).astype(np.float32)

        config = BackgroundExtractionConfig(
            method=BackgroundModelMethod.POLYNOMIAL_DEG_2,
            grid_rows=8,
            grid_cols=8,
            preserve_mean_sky_pedestal=False,
        )
        result = run_background_extraction(true_bg, config)

        residual = result.linear_corrected_data
        assert float(np.std(residual)) < 0.002
        np.testing.assert_allclose(residual, 0.0, atol=0.005)

    def test_rbf_smooth_gradient(self):
        """Thin Plate Spline RBF harus memodelkan gradien halus non-linear."""
        height, width = 80, 80
        y, x = np.mgrid[0:height, 0:width]
        true_bg = (0.3 + 0.1 * np.sin(x / 40.0) + 0.1 * np.cos(y / 40.0)).astype(np.float32)

        config = BackgroundExtractionConfig(
            method=BackgroundModelMethod.TPS_RBF,
            grid_rows=6,
            grid_cols=6,
            preserve_mean_sky_pedestal=False,
        )
        result = run_background_extraction(true_bg, config)

        residual = result.linear_corrected_data
        assert np.std(residual) < np.std(true_bg) * 0.15

    def test_protected_roi_masking(self):
        """Wilayah proteksi ROI harus mengecualikan objek terang hilal dari model latar."""
        height, width = 100, 100
        data = np.full((height, width), 0.2, dtype=np.float32)
        # Tambahkan objek terang di tengah (x=40..60, y=40..60)
        data[40:60, 40:60] += 5.0

        roi = ProtectedRegionROI(
            shape_type="RECTANGLE",
            rect=(40, 40, 20, 20),  # x, y, w, h
            label="Zona Hilal",
        )
        config = BackgroundExtractionConfig(
            method=BackgroundModelMethod.POLYNOMIAL_DEG_1,
            grid_rows=8,
            grid_cols=8,
            protected_regions=(roi,),
            preserve_mean_sky_pedestal=False,
        )
        result = run_background_extraction(data, config)

        # Model latar tidak boleh terangkat oleh objek 5.0
        assert np.all(result.background_model < 0.35)
        # Sinyal hilal pada data terkoreksi tetap utuh (~5.0)
        crescent_patch = result.linear_corrected_data[45:55, 45:55]
        assert np.mean(crescent_patch) > 4.8

    def test_bayer_cfa_subchannel_handling(self):
        """Bayer CFA 2D mosaic harus memodelkan latar per subkanal 2x2 tanpa demosaicing."""
        height, width = 64, 64
        raw_mosaic = np.zeros((height, width), dtype=np.float32)
        raw_mosaic[0::2, 0::2] = 0.10  # R
        raw_mosaic[0::2, 1::2] = 0.20  # Gr
        raw_mosaic[1::2, 0::2] = 0.20  # Gb
        raw_mosaic[1::2, 1::2] = 0.15  # B

        config = BackgroundExtractionConfig(
            method=BackgroundModelMethod.POLYNOMIAL_DEG_1,
            grid_rows=6,
            grid_cols=6,
            is_cfa_mosaic=True,
            cfa_pattern_str="RGGB",
            preserve_mean_sky_pedestal=False,
        )
        result = run_background_extraction(raw_mosaic, config)

        assert result.cfa_subchannel_modeled is True
        assert result.background_model.shape == (height, width)
        assert np.isclose(np.mean(result.background_model[0::2, 0::2]), 0.10, atol=0.01)
        assert np.isclose(np.mean(result.background_model[0::2, 1::2]), 0.20, atol=0.01)
        assert np.isclose(np.mean(result.background_model[1::2, 1::2]), 0.15, atol=0.01)

    def test_overcorrection_safeguard(self):
        """Safeguard overcorrection harus menghitung skor risiko dan membunyikan peringatan bila melampaui ambang."""
        height, width = 60, 60
        data = np.full((height, width), 0.5, dtype=np.float32)
        # Turunkan area tengah tajam di bawah latar
        data[20:40, 20:40] -= 0.35

        config = BackgroundExtractionConfig(
            method=BackgroundModelMethod.POLYNOMIAL_DEG_2,
            grid_rows=6,
            grid_cols=6,
            overcorrection_warn_ratio=0.05,
            preserve_mean_sky_pedestal=False,
        )
        result = run_background_extraction(data, config)
        assert result.residual_stats.overcorrection_score >= 0.0
        assert isinstance(result.residual_stats.overcorrection_warning, bool)

    def test_constant_image_fallback(self):
        """Citra konstan harus ditangani dengan aman tanpa galat atau pembagian nol."""
        flat_data = np.full((50, 50), 10.0, dtype=np.float32)
        result = run_background_extraction(
            flat_data,
            BackgroundExtractionConfig(
                method=BackgroundModelMethod.POLYNOMIAL_DEG_1,
                preserve_mean_sky_pedestal=False,
            ),
        )
        assert np.allclose(result.background_model, 10.0, atol=1e-3)


# ============================================================================
# 2. IMAGE ENHANCEMENT ENGINE TESTS
# ============================================================================

class TestImageEnhancementEngine:
    """Pengujian Image Enhancement (CLAHE) pada citra saintifik."""

    def test_clahe_mono_contrast_boost(self):
        """CLAHE pada grayscale harus meningkatkan kontras target lokal dan menghasilkan float32."""
        height, width = 80, 80
        # Citra bertingkat dengan target samar di tengah
        data = np.full((height, width), 0.3, dtype=np.float32)
        data[35:45, 35:45] += 0.05

        config = ImageEnhancementConfig(
            method=EnhancementMethod.CLAHE,
            clip_limit=0.03,
            kernel_tiles=(8, 8),
            max_noise_amplification_ratio=3.0,
            adaptive_parameters=False,
        )
        result = run_image_enhancement(data, config)

        assert result.enhanced_data.dtype == np.float32
        assert result.enhanced_data.shape == (height, width)
        # Kontras target lokal terhadap latar sekitar harus dipertahankan atau diperkuat
        contrast_before = float(np.mean(data[38:42, 38:42]) - np.mean(data[10:15, 10:15]))
        contrast_after = float(np.mean(result.enhanced_data[38:42, 38:42]) - np.mean(result.enhanced_data[10:15, 10:15]))
        assert contrast_after >= contrast_before - 1e-4

    def test_clahe_rgb_ratio_preservation(self):
        """CLAHE berbasis luminansi pada RGB harus menjaga rasio warna tanpa pergeseran corak."""
        height, width = 64, 64
        rgb_data = np.zeros((height, width, 3), dtype=np.float32)
        base_ramp = np.linspace(0.0, 1.0, width, dtype=np.float32).reshape(1, width)
        rgb_data[:, :, 0] = base_ramp * 1.0  # R
        rgb_data[:, :, 1] = base_ramp * 0.5  # G
        rgb_data[:, :, 2] = base_ramp * 0.2  # B

        config = ImageEnhancementConfig(
            method=EnhancementMethod.CLAHE,
            clip_limit=0.02,
            kernel_tiles=(8, 8),
            adaptive_parameters=False,
        )
        result = run_image_enhancement(rgb_data, config)

        enhanced = result.enhanced_data
        assert enhanced.shape == (height, width, 3)

        # Periksa rasio kanal R/G pada piksel yang memiliki sinyal cukup
        valid_px = base_ramp[0] > 0.08
        r_chan = enhanced[:, valid_px, 0]
        g_chan = enhanced[:, valid_px, 1]
        ratio_rg = r_chan / np.maximum(g_chan, 1e-6)
        np.testing.assert_allclose(ratio_rg, 2.0, atol=0.08)

    def test_noise_amplification_limiter(self):
        """Noise amplification limiter harus membatasi amplifikasi derau sesuai ambang."""
        height, width = 64, 64
        np.random.seed(42)
        noisy = 0.5 + 0.05 * np.random.randn(height, width).astype(np.float32)

        config = ImageEnhancementConfig(
            method=EnhancementMethod.CLAHE,
            clip_limit=0.05,
            max_noise_amplification_ratio=1.5,
            adaptive_parameters=False,
        )
        result = run_image_enhancement(noisy, config)
        assert result.noise_amplification_ratio <= 1.55


# ============================================================================
# 3. HISTOGRAM TRANSFORMATION ENGINE TESTS
# ============================================================================

class TestHistogramTransformationEngine:
    """Pengujian peregangan kurva histogram visual."""

    def test_mtf_monotonicity(self):
        """Fungsi Midtone Transfer Function (MTF) harus monoton naik secara ketat."""
        x = np.linspace(0.0, 1.0, 101, dtype=np.float32)
        m = 0.15
        y = apply_mtf(x, m)

        assert y[0] == 0.0
        assert np.isclose(y[-1], 1.0)
        diffs = np.diff(y)
        assert np.all(diffs >= -1e-7)

    def test_asinh_stretch_properties(self):
        """Asinh stretch harus mengompresi rentang dinamis dan tetap berada di [0, 1]."""
        x = np.linspace(0.0, 1.0, 100, dtype=np.float32)
        y = apply_asinh_stretch(x, a=10.0)
        assert np.all(y >= 0.0)
        assert np.all(y <= 1.0)
        assert np.all(np.diff(y) >= 0.0)

    def test_ghs_stretch_monotonicity(self):
        """Generalized Hyperbolic Stretch (GHS) harus monoton naik."""
        x = np.linspace(0.0, 1.0, 100, dtype=np.float32)
        y = apply_ghs_stretch(x, stretch_factor_d=3.0, local_intensity_b=1.5, symmetry_point_sp=0.15)
        assert np.all(y >= 0.0)
        assert np.all(y <= 1.0)
        assert np.all(np.diff(y) >= -1e-6)

    def test_histogram_transform_preserves_linear_source(self):
        """Transformasi histogram harus menghasilkan salinan tampilan tanpa merusak data linear."""
        height, width = 50, 50
        raw_vals = np.linspace(-0.05, 1.5, height * width, dtype=np.float32).reshape(height, width)
        orig_copy = raw_vals.copy()

        config = HistogramTransformConfig(
            method=StretchMethod.ADAPTIVE_ASINH_MTF,
            target_background_median=0.25,
        )
        result = run_histogram_transformation(raw_vals, config)

        assert np.min(result.display_data) >= 0.0
        assert np.max(result.display_data) <= 1.0
        np.testing.assert_array_equal(raw_vals, orig_copy)

    def test_render_histogram_chart(self):
        """Pembuat grafik histogram harus menghasilkan QImage yang valid."""
        data = np.random.uniform(0.0, 1.0, (100, 100)).astype(np.float32)
        res = run_histogram_transformation(data, HistogramTransformConfig())

        qimg = render_histogram_chart_qimage(
            res.histogram_data,
            vmin=res.vmin,
            vmax=res.vmax,
            method_label="TEST_STRETCH",
            width=280,
            height=140,
        )
        assert isinstance(qimg, QImage)
        assert not qimg.isNull()
        assert qimg.width() == 280
        assert qimg.height() == 140


# ============================================================================
# 4. PROFILE MANAGER TESTS
# ============================================================================

class TestProfileManager:
    """Pengujian manajemen profil pemrosesan Basic, Medium, dan High."""

    def test_default_profiles_exist(self):
        """Ketiga profil terpadu harus terdefinisi dengan lengkap."""
        for profile in (ProcessingProfile.BASIC, ProcessingProfile.MEDIUM, ProcessingProfile.HIGH):
            cfg = get_unified_profile_config(profile)
            assert cfg.profile == profile
            assert len(cfg.display_name) > 0
            assert len(cfg.characteristics_id) > 0
            assert len(cfg.risk_note_id) > 0
            assert cfg.background_config is not None
            assert cfg.enhancement_config is not None
            assert cfg.histogram_config is not None

    def test_profile_algorithms_match_specification(self):
        """Algoritma setiap profil harus sesuai dengan spesifikasi fase."""
        basic = get_unified_profile_config(ProcessingProfile.BASIC)
        assert basic.background_config.method == BackgroundModelMethod.POLYNOMIAL_DEG_1
        assert basic.histogram_config.method == StretchMethod.LINEAR_MTF

        med = get_unified_profile_config(ProcessingProfile.MEDIUM)
        assert med.background_config.method in (
            BackgroundModelMethod.POLYNOMIAL_DEG_2,
            BackgroundModelMethod.TPS_RBF,
        )
        assert med.histogram_config.method == StretchMethod.ASINH_MTF

        high = get_unified_profile_config(ProcessingProfile.HIGH)
        assert high.background_config.method == BackgroundModelMethod.AUTO_ROBUST_RBF
        assert high.histogram_config.method == StretchMethod.ADAPTIVE_ASINH_MTF

    def test_profile_customization(self):
        """Penyesuaian profil lanjutan harus memperbarui konfigurasi secara benar."""
        base = get_unified_profile_config(ProcessingProfile.BASIC)
        custom = customize_profile_config(
            base.profile,
            background_method=BackgroundModelMethod.TPS_RBF,
            clahe_clip_limit=0.04,
            stretch_method=StretchMethod.GHS_MTF,
        )
        assert custom.background_config.method == BackgroundModelMethod.TPS_RBF
        assert custom.enhancement_config.clip_limit == 0.04
        assert custom.histogram_config.method == StretchMethod.GHS_MTF


# ============================================================================
# 5. ORCHESTRATOR & PIPELINE INTEGRATION TESTS
# ============================================================================

class TestProcessingPipelineOrchestrator:
    """Pengujian orchestrator pipeline untuk Single Image dan Sequence."""

    def test_single_image_pipeline_bypasses_stacking(self):
        """Pipeline Single Image harus melewati stacking dan menjalankan tahapan berikutnya."""
        height, width = 80, 80
        y, x = np.mgrid[0:height, 0:width]
        raw_data = (0.2 + 0.001 * x + 0.001 * y).astype(np.float32)

        profile_cfg = get_unified_profile_config(ProcessingProfile.BASIC)
        orchestrator = ProcessingPipelineOrchestrator(profile_cfg)

        stages_recorded = []
        result = orchestrator.run_on_single_image(
            raw_data,
            progress_callback=lambda stage, step, total, msg: stages_recorded.append((stage, msg)),
        )

        assert isinstance(result, PipelineResult)
        assert result.stacked_data is None  # Stacking dilewati
        assert result.linear_result is not None
        assert result.enhanced_result is not None
        assert result.display_result is not None
        assert result.background_model is not None

        # Pratinjau terpadu harus tersedia
        assert PreviewMode.FINAL_DISPLAY in result.previews
        assert PreviewMode.ENHANCED in result.previews
        assert PreviewMode.BACKGROUND_CORRECTED in result.previews
        assert PreviewMode.BACKGROUND_MODEL in result.previews
        assert PreviewMode.ORIGINAL in result.previews

        # Catatan tahap eksekusi
        stage_names = [r.stage for r in result.stage_records]
        assert PipelineStage.STACKING not in [r.stage for r in result.stage_records if r.status == StageStatus.COMPLETED]
        assert PipelineStage.BACKGROUND_EXTRACTION in stage_names
        assert PipelineStage.IMAGE_ENHANCEMENT in stage_names
        assert PipelineStage.HISTOGRAM_TRANSFORMATION in stage_names

    def test_pipeline_cancellation(self):
        """Pipeline harus berhenti seketika ketika dibatalkan pengguna."""
        raw_data = np.full((50, 50), 0.5, dtype=np.float32)
        profile_cfg = get_unified_profile_config(ProcessingProfile.BASIC)
        orchestrator = ProcessingPipelineOrchestrator(profile_cfg)

        with pytest.raises(ProcessingCancelledError):
            orchestrator.run_on_single_image(
                raw_data,
                cancel_check=lambda: True,
            )

    def test_sequence_pipeline_with_real_sequence(self, tmp_path):
        """Pipeline Sequence harus menjalankan stacking dan tahapan lanjutan."""
        height, width = 40, 50
        seq_paths = []
        for i in range(3):
            p = tmp_path / f"seq_frame_{i}.tif"
            frame_data = np.full((height, width), 0.3 + 0.02 * i, dtype=np.float32)
            tifffile.imwrite(str(p), frame_data)
            seq_paths.append(p)

        sm = SequenceManager()
        sm.open_files(seq_paths)

        profile_cfg = get_unified_profile_config(ProcessingProfile.BASIC)
        orchestrator = ProcessingPipelineOrchestrator(
            profile_cfg,
            confirm_proceed_with_shift_risk=True,
        )

        result = orchestrator.run_on_sequence(sm)
        assert isinstance(result, PipelineResult)
        assert result.stacked_data is not None
        assert result.linear_result is not None
        assert result.display_result is not None
        assert result.stacking_result is not None
        assert result.stacking_result.stacked_frame_count == 3


# ============================================================================
# 6. PIPELINE OUTPUT WRITER TESTS
# ============================================================================

class TestPipelineWriter:
    """Pengujian penyimpanan produk pemrosesan (FITS, TIFF, PNG, JSON)."""

    def test_save_pipeline_result_files(self, tmp_path):
        """Writer harus menyimpan berkas FITS/TIFF/PNG dan menyertakan laporan JSON."""
        height, width = 40, 40
        linear_data = (0.2 + 0.001 * np.arange(height * width, dtype=np.float32)).reshape(height, width)

        cfg = get_unified_profile_config(ProcessingProfile.BASIC)
        orch = ProcessingPipelineOrchestrator(cfg)
        result = orch.run_on_single_image(linear_data)

        # 1. Simpan Linear Scientific FITS
        linear_fits = tmp_path / "obs_linear.fits"
        saved_img, saved_json = save_pipeline_result(
            result, linear_fits, save_target="LINEAR", write_json_report=True
        )
        assert saved_img.exists()
        assert saved_json is not None and saved_json.exists()

        with fits.open(saved_img) as hdul:
            hdr = hdul[0].header
            assert hdr["HL_ISDER"] is False
            assert hdr["HL_PROF"] == "BASIC"
            assert "BG_METH" in hdr

        # 2. Simpan Enhanced Derived TIFF
        enh_tiff = tmp_path / "obs_enhanced.tif"
        saved_enh, _ = save_pipeline_result(
            result, enh_tiff, save_target="ENHANCED", write_json_report=False
        )
        assert saved_enh.exists()

        # 3. Simpan Visual Display PNG
        disp_png = tmp_path / "obs_display.png"
        saved_png, _ = save_pipeline_result(
            result, disp_png, save_target="DISPLAY", write_json_report=False
        )
        assert saved_png.exists()

        # 4. Verifikasi Laporan JSON
        with open(saved_json, "r", encoding="utf-8") as f:
            report_data = json.load(f)
            assert report_data["profile"] == "BASIC"
            assert "stage_execution_history" in report_data
            assert "background_extraction" in report_data

    def test_source_protection_anti_overwrite(self, tmp_path):
        """Writer dilarang menimpa berkas sumber asli (OutputWriteError)."""
        source_file = tmp_path / "light_001.fits"
        source_file.write_bytes(b"dummy_original_data")

        cfg = get_unified_profile_config(ProcessingProfile.BASIC)
        res = ProcessingPipelineOrchestrator(cfg).run_on_single_image(np.ones((20, 20), dtype=np.float32))

        with pytest.raises(OutputWriteError, match="Dilarang menimpa berkas sumber asli"):
            save_pipeline_result(
                res,
                source_file,
                source_paths=[source_file],
            )


# ============================================================================
# 7. SCIENTIFIC VALIDATION TEST: SYNTHETIC HILAL ON TWILIGHT GRADIENT
# ============================================================================

class TestScientificValidation:
    """Validasi Ilmiah: Sabit hilal sintetis pada gradien langit senja dengan derau."""

    def test_hilal_contrast_improvement_on_twilight_gradient(self):
        """Memvalidasi eliminasi gradien langit senja dan peningkatan kontras sabit hilal."""
        height, width = 120, 160
        y, x = np.mgrid[0:height, 0:width]

        # 1. Gradien langit senja diagonal realistis
        sky_gradient = (0.35 + 0.0015 * x + 0.003 * (height - y)).astype(np.float32)

        # 2. Derau Gaussian
        np.random.seed(12345)
        noise = np.random.normal(0.0, 0.005, (height, width)).astype(np.float32)

        # 3. Fitur sabit hilal tipis (lengkungan tipis dengan intensitas ~0.035)
        r = np.sqrt((x - 80.0) ** 2 + (y - 50.0) ** 2)
        crescent_mask = (r >= 28.0) & (r <= 31.0) & (y >= 50.0) & (x >= 70.0) & (x <= 95.0)
        crescent_signal = np.zeros((height, width), dtype=np.float32)
        crescent_signal[crescent_mask] = 0.035

        synthetic_observation = sky_gradient + noise + crescent_signal

        roi = ProtectedRegionROI(
            shape_type="RECTANGLE",
            rect=(65, 45, 35, 30),
            label="Zona Hilal",
        )

        profile_config = get_unified_profile_config(ProcessingProfile.HIGH)
        profile_config = customize_profile_config(
            profile_config.profile,
            background_method=BackgroundModelMethod.AUTO_ROBUST_RBF,
            grid_rows=8,
            grid_cols=8,
            protected_regions=(roi,),
        )

        orchestrator = ProcessingPipelineOrchestrator(profile_config)
        result = orchestrator.run_on_single_image(synthetic_observation)

        # A. Reduksi gradien background > 75%
        raw_std = float(np.std(synthetic_observation))
        bg_corrected_std = float(np.std(result.linear_result))
        reduction = (raw_std - bg_corrected_std) / raw_std
        assert reduction > 0.75

        # B. Sinyal sabit hilal tetap positif dan dipertahankan
        crescent_linear = result.linear_result[crescent_mask]
        local_sky_linear = result.linear_result[40:45, 70:95]
        contrast_linear = float(np.mean(crescent_linear) - np.mean(local_sky_linear))
        assert contrast_linear > 0.025

        # C. Skor overcorrection aman (< 0.10)
        assert result.background_result.residual_stats.overcorrection_score < 0.10

        # D. Peregangan tampilan visual mempertahankan keterlihatan sabit
        crescent_display = result.display_result[crescent_mask]
        local_sky_display = result.display_result[40:45, 70:95]
        assert float(np.mean(crescent_display)) > float(np.mean(local_sky_display))
