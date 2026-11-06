"""Pengujian unit komprehensif untuk Automatic Stacking Engine (Sub-Tahap 3A).

Mencakup seluruh skenario pengujian sintetis yang disyaratkan:
  1. Frame identik (akurasi aritmetika piksel pada BASIC, MEDIUM, HIGH).
  2. Frame dengan derau acak Gaussian (penurunan noise ~1/sqrt(N) & pelestarian sinyal hilal).
  3. Frame dengan outlier ekstrem (hot pixel / jejak satelit) dan verifikasi rejection_map.
  4. Frame dengan variasi tingkat derau pada profil HIGH (pembobotan kualitas invers varians
     tanpa mengubah tingkat intensitas sinyal).
  5. Citra RGB 3-kanal (keputusan penolakan berbasis luminans bersama tanpa pergeseran warna).
  6. Pemeriksaan stabilitas posisi baca-saja (OK, MELEBIHI_AMBANG > 1 px, dan INDETERMINATE)
     tanpa melakukan registrasi/alignment.
  7. Kalibrasi Master Flat opsional (normalisasi rata-rata=1.0, proteksi piksel nol, dan
     penolakan ukuran/kanal tidak cocok).
  8. Integrasi lintas format: FITS float32 (termasuk nilai negatif tanpa clipping), TIFF uint16,
     SER Bayer CFA (RGGB), dan Video AVI.
  9. Manajemen memori strip (bounded memory), pelaporan progress, dan pembatalan aman.
  10. Penolakan mode Single Image, larangan membuang frame error/inkompatibel secara diam-diam,
      serta verifikasi integritas berkas sumber (SHA-256).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct

from astropy.io import fits
import av
import numpy as np
import pytest
import tifffile

from hilalone.input_manager.sequence_manager import SequenceManager
from hilalone.processing.stacking import (
    AutomaticStackingEngine,
    PositionStabilityStatus,
    StackingAlgorithm,
    StackingCancelledError,
    StackingConfirmationRequiredError,
    StackingError,
    StackingProfile,
    run_stacking_on_sequence,
)

_SER_HEADER_STRUCT = struct.Struct("<14siiiiiii40s40s40sqq")


def _make_synthetic_crescent_base(height: int = 48, width: int = 64) -> np.ndarray:
    """Membuat citra sintetis float32 berisi gradien langit + busur sabit hilal + beberapa bintang."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    # Gradien langit lembut
    sky = 1000.0 + 4.0 * yy + 1.5 * xx

    # Busur sabit hilal sintetis (cincin elips dengan modulasi sudut)
    cy, cx = height * 0.52, width * 0.48
    dy = yy - cy
    dx = xx - cx
    radius = np.hypot(dx, dy)
    angle = np.arctan2(dy, dx)
    ring = np.exp(-0.5 * ((radius - 12.0) / 1.6) ** 2)
    angular_taper = np.clip(np.cos(angle - 0.4), 0.0, 1.0) ** 2
    crescent = 450.0 * ring * angular_taper

    # Tambahkan 3 titik bintang kompak secara proporsional di dalam kanvas
    s1x, s1y = width * 0.25, height * 0.28
    s2x, s2y = width * 0.78, height * 0.30
    s3x, s3y = width * 0.70, height * 0.75
    stars = (
        800.0 * np.exp(-0.5 * (((xx - s1x) ** 2 + (yy - s1y) ** 2) / 1.5**2))
        + 750.0 * np.exp(-0.5 * (((xx - s2x) ** 2 + (yy - s2y) ** 2) / 1.4**2))
        + 900.0 * np.exp(-0.5 * (((xx - s3x) ** 2 + (yy - s3y) ** 2) / 1.6**2))
    )
    return (sky + crescent + stars).astype(np.float32)


def _write_tiff_sequence(folder: Path, frames: list[np.ndarray], prefix: str = "frame") -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, arr in enumerate(frames, start=1):
        p = folder / f"{prefix}_{i:03d}.tif"
        tifffile.imwrite(str(p), arr)
        paths.append(p)
    return paths


def _write_ser_file(
    path: Path,
    frames: list[np.ndarray],
    *,
    color_id: int = 0,
    pixel_depth: int = 16,
) -> Path:
    h, w = frames[0].shape[:2]
    header = _SER_HEADER_STRUCT.pack(
        b"LUCAM-RECORDER",
        0,
        color_id,
        1,
        w,
        h,
        pixel_depth,
        len(frames),
        b"Observer".ljust(40, b"\x00"),
        b"Camera".ljust(40, b"\x00"),
        b"Telescope".ljust(40, b"\x00"),
        0,
        0,
    )
    with open(path, "wb") as f:
        f.write(header)
        for frame in frames:
            dt = np.uint8 if pixel_depth <= 8 else np.dtype("<u2")
            f.write(np.ascontiguousarray(frame, dtype=dt).tobytes())
    return path


def test_identical_frames_stacking_exact_preservation(tmp_path: Path) -> None:
    """Frame identik menghasilkan nilai piksel yang persis sama pada BASIC, MEDIUM, dan HIGH."""
    base = _make_synthetic_crescent_base(32, 40).astype(np.uint16)
    frames = [base.copy() for _ in range(6)]
    paths = _write_tiff_sequence(tmp_path / "identical", frames)

    sm = SequenceManager()
    sm.open_files(paths)

    for profile in (StackingProfile.BASIC, StackingProfile.MEDIUM, StackingProfile.HIGH):
        res = run_stacking_on_sequence(sm, profile=profile)
        assert res.stacked_scientific_data.dtype == np.float32
        assert res.stacked_scientific_data.shape == (32, 40)
        assert res.stacked_frame_count == 6
        assert res.total_rejected_pixel_samples == 0
        np.testing.assert_allclose(
            res.stacked_scientific_data,
            base.astype(np.float32),
            rtol=1e-6,
            atol=1e-4,
        )


def test_random_gaussian_noise_reduction_and_signal_preservation(tmp_path: Path) -> None:
    """Stacking 9 frame berderau Gaussian menurunkan simpangan baku derau ~1/3 tanpa merusak sinyal."""
    rng = np.random.default_rng(202603)
    clean_signal = _make_synthetic_crescent_base(48, 64)
    noise_sigma = 18.0
    n_frames = 9

    noisy_frames = [
        (clean_signal + rng.normal(0.0, noise_sigma, size=clean_signal.shape)).astype(np.float32)
        for _ in range(n_frames)
    ]
    paths = _write_tiff_sequence(tmp_path / "gaussian", noisy_frames)

    sm = SequenceManager()
    sm.open_files(paths)

    single_err_std = float(np.std(noisy_frames[0] - clean_signal))
    for profile in (StackingProfile.BASIC, StackingProfile.MEDIUM, StackingProfile.HIGH):
        res = run_stacking_on_sequence(sm, profile=profile)
        stacked_err = res.stacked_scientific_data - clean_signal
        stacked_err_std = float(np.std(stacked_err))
        # Teoretis untuk N=9 adalah single_err_std / 3.0 (~6.0 ADU)
        assert stacked_err_std < single_err_std * 0.45
        # Rata-rata intensitas global tetap terjaga (< 1.5 ADU)
        assert abs(float(np.mean(stacked_err))) < 1.5


def test_outlier_pixel_rejection_medium_and_high_vs_basic(tmp_path: Path) -> None:
    """Outlier ekstrem (hot pixel & jejak pesawat) ditolak oleh MEDIUM & HIGH, tercatat di rejection_map."""
    rng = np.random.default_rng(42)
    clean = _make_synthetic_crescent_base(36, 48)
    frames = [
        (clean + rng.normal(0.0, 2.0, size=clean.shape)).astype(np.float32)
        for _ in range(7)
    ]

    # Suntikkan jejak pesawat terang (+25000 ADU) pada baris 15 di frame ke-2
    frames[2][15, 10:35] += 25000.0
    # Suntikkan dead/cold outlier (-9000 ADU) pada titik (22, 28) di frame ke-5
    frames[5][22, 28] -= 9000.0

    paths = _write_tiff_sequence(tmp_path / "outliers", frames)
    sm = SequenceManager()
    sm.open_files(paths)

    res_basic = run_stacking_on_sequence(sm, profile=StackingProfile.BASIC)
    res_medium = run_stacking_on_sequence(sm, profile=StackingProfile.MEDIUM)
    res_high = run_stacking_on_sequence(sm, profile=StackingProfile.HIGH)

    # Pada BASIC, jejak pesawat tetap mencemari baris 15 (> +3000 ADU di atas sinyal asli)
    basic_err_streak = float(np.max(np.abs(res_basic.stacked_scientific_data[15, 10:35] - clean[15, 10:35])))
    assert basic_err_streak > 3000.0

    # Pada MEDIUM dan HIGH, seluruh piksel jejak pesawat dan titik cold outlier berhasil ditolak!
    for res in (res_medium, res_high):
        streak_err = float(np.max(np.abs(res.stacked_scientific_data[15, 10:35] - clean[15, 10:35])))
        cold_err = abs(float(res.stacked_scientific_data[22, 28] - clean[22, 28]))
        assert streak_err < 6.0
        assert cold_err < 6.0
        # Pastikan peta rejection mencatat penolakan pada seluruh piksel jejak pesawat
        assert np.all(res.rejection_map[15, 10:35] >= 1)
        assert res.rejection_map[22, 28] >= 1
        assert np.all(res.effective_frame_count_map[15, 10:35] <= 6)


def test_high_profile_quality_weighting_without_intensity_distortion(tmp_path: Path) -> None:
    """Profil HIGH memberi bobot lebih besar pada frame berderau rendah tanpa mengubah skala intensitas."""
    rng = np.random.default_rng(99)
    clean = _make_synthetic_crescent_base(40, 50)

    # 4 frame sangat bersih (sigma = 2.0) dan 2 frame sangat berderau (sigma = 45.0)
    frames: list[np.ndarray] = []
    for _ in range(4):
        frames.append((clean + rng.normal(0.0, 2.0, size=clean.shape)).astype(np.float32))
    for _ in range(2):
        frames.append((clean + rng.normal(0.0, 45.0, size=clean.shape)).astype(np.float32))

    paths = _write_tiff_sequence(tmp_path / "weighted", frames)
    sm = SequenceManager()
    sm.open_files(paths)

    res_basic = run_stacking_on_sequence(sm, profile=StackingProfile.BASIC)
    res_high = run_stacking_on_sequence(sm, profile=StackingProfile.HIGH)

    weights = [m.normalized_weight for m in res_high.frame_quality_metrics]
    # Jumlah bobot wajib tepat 1.0
    assert sum(weights) == pytest.approx(1.0, abs=1e-6)
    # Bobot frame bersih (indeks 0..3) harus jauh lebih besar daripada frame berderau (indeks 4..5)
    assert min(weights[:4]) > max(weights[4:]) * 3.0

    # Galat RMS profil HIGH harus lebih kecil daripada BASIC yang merata-ratakan frame buruk secara setara
    rms_basic = float(np.sqrt(np.mean((res_basic.stacked_scientific_data - clean) ** 2)))
    rms_high = float(np.sqrt(np.mean((res_high.stacked_scientific_data - clean) ** 2)))
    assert rms_high < rms_basic * 0.65

    # Intensitas rata-rata citra wajib tetap akurat (tidak ada perubahan kecerahan global)
    assert float(np.mean(res_high.stacked_scientific_data)) == pytest.approx(
        float(np.mean(clean)), rel=1e-3
    )


def test_rgb_luminance_consistent_rejection_preserves_color_ratios(tmp_path: Path) -> None:
    """Stacking RGB mempertahankan 3 kanal dan menolak outlier secara konsisten antar kanal (FR-ST-03a)."""
    base_lum = _make_synthetic_crescent_base(32, 40)
    # Rasio warna sabit & langit: R=1.4, G=1.0, B=0.7
    rgb_clean = np.stack([base_lum * 1.4, base_lum * 1.0, base_lum * 0.7], axis=-1).astype(
        np.uint16
    )

    frames = [rgb_clean.copy() for _ in range(6)]
    # Tambahkan gangguan kilatan lokal pada frame ke-1 di blok (3:6, 3:7)
    frames[1][3:6, 3:7, 0] = 60000
    frames[1][3:6, 3:7, 1] = 55000
    frames[1][3:6, 3:7, 2] = 50000

    paths = _write_tiff_sequence(tmp_path / "rgb_seq", frames)
    sm = SequenceManager()
    sm.open_files(paths)

    res = run_stacking_on_sequence(sm, profile=StackingProfile.MEDIUM)
    assert res.stacked_scientific_data.shape == (32, 40, 3)
    assert res.stacked_scientific_data.dtype == np.float32
    assert np.all(res.rejection_map[3:6, 3:7] == 1)
    np.testing.assert_allclose(
        res.stacked_scientific_data,
        rgb_clean.astype(np.float32),
        rtol=1e-5,
        atol=1e-3,
    )


def test_position_stability_ok_exceeded_and_indeterminate_without_alignment(
    tmp_path: Path,
) -> None:
    """Memeriksa deteksi pergeseran <= 1 px (OK), > 1 px (MELEBIHI_AMBANG), dan INDETERMINATE."""
    base = _make_synthetic_crescent_base(64, 64)
    # Geser frame ke-2 sejauh dx=+3 px, dy=+2 px (|dr| = ~3.61 px > 1.0 px)
    shifted = np.roll(np.roll(base, shift=2, axis=0), shift=3, axis=1)

    paths = _write_tiff_sequence(tmp_path / "shifted_seq", [base, base.copy(), shifted])
    sm = SequenceManager()
    sm.open_files(paths)

    # 1. Tanpa konfirmasi pengguna, pergeseran > 1 px wajib melempar StackingConfirmationRequiredError
    with pytest.raises(StackingConfirmationRequiredError, match="MELEBIHI_AMBANG"):
        run_stacking_on_sequence(sm, profile=StackingProfile.BASIC)

    # 2. Dengan confirm_proceed_with_shift_risk=True, stacking berjalan TANPA meng-align frame
    res = run_stacking_on_sequence(
        sm,
        profile=StackingProfile.BASIC,
        confirm_proceed_with_shift_risk=True,
    )
    stab = res.validation_report.stability_report
    assert stab is not None
    assert stab.measurements[0].status == PositionStabilityStatus.OK
    assert stab.measurements[1].status == PositionStabilityStatus.OK
    assert stab.measurements[2].status == PositionStabilityStatus.MELEBIHI_AMBANG
    assert stab.measurements[2].dx_px == pytest.approx(3.0, abs=0.35)
    assert stab.measurements[2].dy_px == pytest.approx(2.0, abs=0.35)

    # Buktikan TIDAK ada alignment: hasil rata-rata harus persis (base + base + shifted) / 3
    expected_unaligned = (base + base + shifted) / 3.0
    np.testing.assert_allclose(res.stacked_scientific_data, expected_unaligned, rtol=1e-5, atol=1e-4)

    # 3. Uji citra rata/kosong -> wajib berstatus INDETERMINATE dan meminta konfirmasi
    flat_frames = [np.full((32, 32), 500.0, dtype=np.float32) for _ in range(3)]
    flat_paths = _write_tiff_sequence(tmp_path / "flat_empty", flat_frames)
    sm_flat = SequenceManager()
    sm_flat.open_files(flat_paths)

    with pytest.raises(StackingConfirmationRequiredError, match="INDETERMINATE"):
        run_stacking_on_sequence(sm_flat, profile=StackingProfile.BASIC)


def test_optional_master_flat_calibration_and_zero_protection(tmp_path: Path) -> None:
    """Master Flat opsional mengoreksi vignetting, melindungi piksel 0, dan menolak dimensi salah."""
    true_scene = _make_synthetic_crescent_base(36, 48)
    yy, xx = np.mgrid[0:36, 0:48].astype(np.float32)
    vignette = 1.0 - 0.25 * (((yy - 18.0) / 18.0) ** 2 + ((xx - 24.0) / 24.0) ** 2)

    # Master flat dengan skala ADU 20000 dan 2 piksel mati bernilai 0.0
    raw_flat = (vignette * 20000.0).astype(np.float32)
    raw_flat[0, 0] = 0.0
    raw_flat[5, 5] = -10.0

    # Frame pengamatan yang terkena vignetting
    vignetted_frame = (true_scene * vignette).astype(np.float32)
    paths = _write_tiff_sequence(
        tmp_path / "vignetted",
        [vignetted_frame.copy() for _ in range(4)],
    )

    sm = SequenceManager()
    sm.open_files(paths)

    res = run_stacking_on_sequence(
        sm,
        profile=StackingProfile.BASIC,
        master_flat=raw_flat,
    )
    assert res.flat_report is not None
    assert res.flat_report.applied is True
    assert res.flat_report.protected_zero_pixels_count == 2
    assert np.all(np.isfinite(res.stacked_scientific_data))

    # Di luar 2 piksel mati, vignetting berhasil dipulihkan kembali ke proporsi true_scene
    valid_mask = np.ones((36, 48), dtype=bool)
    valid_mask[0, 0] = False
    valid_mask[5, 5] = False
    ratio = res.stacked_scientific_data[valid_mask] / true_scene[valid_mask]
    # Seluruh piksel memiliki rasio konstan (bebas vignetting!)
    assert float(np.std(ratio)) < 1e-5

    # Master Flat dengan ukuran berbeda harus ditolak dengan StackingError
    wrong_flat = np.ones((20, 20), dtype=np.float32)
    with pytest.raises(StackingError, match="Ukuran Master Flat"):
        run_stacking_on_sequence(sm, profile=StackingProfile.BASIC, master_flat=wrong_flat)


def test_scientific_formats_fits_negative_float32_tiff_uint16_raw_cfa_video_and_ser(
    tmp_path: Path,
) -> None:
    """Menguji FITS float32 bernilai negatif, SER Bayer CFA, dan Video AVI."""
    base = _make_synthetic_crescent_base(32, 40)

    # 1. FITS float32 dengan nilai negatif (memastikan nilai negatif TIDAK di-clip!)
    fits_dir = tmp_path / "fits_neg"
    fits_dir.mkdir()
    neg_base = base - float(np.mean(base)) - 50.0  # Memiliki banyak piksel negatif
    assert float(np.min(neg_base)) < -100.0
    fits_paths: list[Path] = []
    for i in range(4):
        fp = fits_dir / f"neg_{i + 1}.fits"
        hdu = fits.PrimaryHDU(data=neg_base.astype(np.float32))
        hdu.header["EXPTIME"] = 0.05
        hdu.header["INSTRUME"] = "HilalCam-1"
        hdu.writeto(fp)
        fits_paths.append(fp)

    sm_fits = SequenceManager()
    sm_fits.open_files(fits_paths)
    res_fits = run_stacking_on_sequence(sm_fits, profile=StackingProfile.BASIC)
    assert float(np.min(res_fits.stacked_scientific_data)) < -100.0
    np.testing.assert_allclose(res_fits.stacked_scientific_data, neg_base, rtol=1e-5, atol=1e-4)

    # 2. SER Bayer CFA (ColorID = 8 / RGGB) — memastikan mosaik 2D tetap terjaga
    cfa_base = base.astype(np.uint16)
    ser_path = _write_ser_file(
        tmp_path / "bayer_rggb.ser",
        [cfa_base.copy() for _ in range(5)],
        color_id=8,
        pixel_depth=16,
    )
    sm_ser = SequenceManager()
    sm_ser.open_ser_file(ser_path)
    res_ser = run_stacking_on_sequence(sm_ser, profile=StackingProfile.MEDIUM)
    assert res_ser.validation_report.is_cfa_mosaic is True
    assert res_ser.validation_report.cfa_pattern_str == "RGGB"
    assert res_ser.stacked_scientific_data.ndim == 2
    np.testing.assert_allclose(
        res_ser.stacked_scientific_data,
        cfa_base.astype(np.float32),
        rtol=1e-5,
        atol=1e-3,
    )
    sm_ser.clear()

    # 3. Video AVI Grayscale
    avi_path = tmp_path / "mono_seq.avi"
    u8_frame = np.clip((base - float(np.min(base))) / 8.0, 10, 240).astype(np.uint8)
    container = av.open(str(avi_path), mode="w")
    stream = container.add_stream("rawvideo", rate=10)
    stream.width = 40
    stream.height = 32
    stream.pix_fmt = "gray"
    for _ in range(4):
        vf = av.VideoFrame.from_ndarray(u8_frame, format="gray")
        for pkt in stream.encode(vf):
            container.mux(pkt)
    for pkt in stream.encode():
        container.mux(pkt)
    container.close()

    sm_vid = SequenceManager()
    sm_vid.open_video_file(avi_path)
    res_vid = run_stacking_on_sequence(sm_vid, profile=StackingProfile.BASIC)
    assert res_vid.stacked_scientific_data.shape == (32, 40)
    np.testing.assert_allclose(
        res_vid.stacked_scientific_data,
        u8_frame.astype(np.float32),
        rtol=1e-5,
        atol=1e-3,
    )
    sm_vid.clear()


def test_bounded_memory_strip_processing_progress_and_cancellation(tmp_path: Path) -> None:
    """Memastikan pemrosesan multi-strip menghasilkan output identik, melaporkan progres, & bisa dibatalkan."""
    rng = np.random.default_rng(777)
    base = _make_synthetic_crescent_base(48, 64)
    frames = [
        (base + rng.normal(0.0, 5.0, size=base.shape)).astype(np.float32)
        for _ in range(6)
    ]
    paths = _write_tiff_sequence(tmp_path / "strips", frames)

    sm = SequenceManager()
    sm.open_files(paths)

    # Bandingkan memori besar (1 strip penuh) vs memori sangat dibatasi (memaksa banyak strip)
    engine_full = AutomaticStackingEngine(max_working_memory_mb=128)
    res_full = engine_full.stack_sequence(sm, profile=StackingProfile.HIGH)
    assert res_full.strip_count_used == 1

    # Paksa strip_height kecil dengan menyetel _max_working_memory_mb secara langsung ke 0 (fallback 1 baris/strip)
    engine_tiny = AutomaticStackingEngine(max_working_memory_mb=1)
    engine_tiny._max_working_memory_mb = 0  # Memaksa strip_height = 1 (48 strip!)
    progress_events: list[tuple[int, int, str]] = []
    res_tiny = engine_tiny.stack_sequence(
        sm,
        profile=StackingProfile.HIGH,
        progress_callback=lambda step, total, msg: progress_events.append((step, total, msg)),
    )
    assert res_tiny.strip_count_used == 48
    assert len(progress_events) > 10
    np.testing.assert_allclose(
        res_tiny.stacked_scientific_data,
        res_full.stacked_scientific_data,
        rtol=1e-6,
        atol=1e-6,
    )
    assert np.array_equal(res_tiny.rejection_map, res_full.rejection_map)

    # Uji pembatalan aman di tengah jalan
    call_counter = {"count": 0}

    def _cancel_after_3_checks() -> bool:
        call_counter["count"] += 1
        return call_counter["count"] >= 3

    with pytest.raises(StackingCancelledError, match="dibatalkan"):
        engine_full.stack_sequence(
            sm,
            profile=StackingProfile.MEDIUM,
            cancel_check=_cancel_after_3_checks,
        )


def test_single_image_rejected_and_invalid_frames_never_silently_dropped_and_sha256_preserved(
    tmp_path: Path,
) -> None:
    """Single Image ditolak, frame inkompatibel dicatat eksplisit, dan SHA-256 berkas sumber utuh."""
    base = _make_synthetic_crescent_base(32, 40).astype(np.uint16)
    paths = _write_tiff_sequence(tmp_path / "integrity_seq", [base, base.copy(), base.copy()])
    hashes_before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

    # 1. Mode Single Image wajib ditolak untuk stacking
    sm = SequenceManager()
    sm.open_single_file(paths[0])
    with pytest.raises(StackingError, match="Single Image"):
        run_stacking_on_sequence(sm, profile=StackingProfile.BASIC)

    # 2. Tambahkan 1 berkas dengan dimensi berbeda (INCOMPATIBLE)
    bad_dim_path = tmp_path / "integrity_seq" / "frame_004.tif"
    tifffile.imwrite(str(bad_dim_path), np.zeros((20, 20), dtype=np.uint16))
    all_paths = [*paths, bad_dim_path]

    sm.open_files(all_paths)
    # Tanpa persetujuan allow_exclude_incompatible_and_error=True, wajib meminta konfirmasi
    with pytest.raises(StackingConfirmationRequiredError, match="tidak kompatibel"):
        run_stacking_on_sequence(sm, profile=StackingProfile.BASIC)

    # Dengan persetujuan eksplisit, frame inkompatibel dikecualikan dan DICATAT di excluded_frames
    res = run_stacking_on_sequence(
        sm,
        profile=StackingProfile.BASIC,
        allow_exclude_incompatible_and_error=True,
    )
    assert res.total_input_frames == 4
    assert res.stacked_frame_count == 3
    assert len(res.excluded_frames) == 1
    assert res.excluded_frames[0].file_name == "frame_004.tif"
    assert "Dimensi" in res.excluded_frames[0].reason

    # 3. Pastikan berkas sumber tidak berubah sedikit pun (SHA-256 identik)
    for p, h_before in hashes_before.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == h_before
