"""Pengujian unit komprehensif untuk Optional Flat-Field Calibration (TAHAP 9).

Mencakup seluruh skenario pengujian yang disyaratkan:
  A. Format Master Flat:
     - FITS (single & multi-HDU)
     - TIFF (single & multi-page)
     - Camera RAW (Bayer CFA domain & sampel NEF bila tersedia)
     - PNG & peringatan format lossy JPEG
     - Flat Frame Sequence (Multiple Images & Folder Sequence)
     - Master Flat dari Video AVI (.avi)
     - Master Flat dari Astronomi SER (.ser)
  B. Akurasi Numerik & Penanganan Kasus Khusus:
     - Uniform flat (F_norm = 1.0, sinyal tidak berubah)
     - Gradien flat sintetis (verifikasi matematis F_norm = F / median(F_valid))
     - Flat dengan vignetting radial
     - Piksel flat bernilai nol dan negatif (proteksi division by zero)
     - Piksel flat bernilai NaN dan Infinity
     - Piksel flat jenuh (saturated pixels) & invalid_pixel_mask
     - Kompatibilitas lintas bit depth / dtype (mis. uint8/uint16 vs float32)
     - Penolakan dimensi berbeda
     - Penolakan ketidakcocokan domain/pola Bayer CFA (CFA mismatch)
     - Penolakan ketidakcocokan Monokrom vs RGB
     - Penolakan video objek langit gelap sebagai flat sequence
  C. Integrasi GUI, Stacking Engine, & Output:
     - Stacking tanpa flat tetap berjalan & mencatat alasan eksplisit
     - Stacking dengan flat benar-benar mengoreksi setiap light frame sebelum stacking
     - Flat aktif tanpa Master Flat menonaktifkan tombol 'Mulai Stacking'
     - Flat tidak kompatibel menghentikan stacking (tidak dilewati diam-diam)
     - Preview Master Flat, informasi normalisasi, & invalid pixels tampil di GUI
     - Berkas sumber light & flat tetap utuh 100% (SHA-256)
     - Ekspor FITS/TIFF menyimpan nilai ilmiah float32 hasil koreksi, sedangkan PNG hanya preview
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct

from astropy.io import fits
import av
import numpy as np
from PySide6.QtGui import QColor, QImage
import pytest
import tifffile

from hilalone.gui.main_window import MainWindow
from hilalone.input_manager.adapters.raw_reader import RawMetadataInfo
from hilalone.input_manager.image_reader import ImageInfo
from hilalone.input_manager.sequence_manager import SequenceManager
from hilalone.processing.stacking import (
    NORMALIZATION_FORMULA_TEXT,
    StackingError,
    StackingProfile,
    apply_flat_calibration,
    check_flat_compatibility,
    load_master_flat_auto,
    load_master_flat_from_sequence,
    load_single_master_flat,
    run_flat_calibration_on_sequence,
    run_stacking_on_sequence,
    validate_and_prepare_master_flat,
)

_SER_HEADER_STRUCT = struct.Struct("<14siiiiiii40s40s40sqq")


def _make_crescent_scene(height: int = 48, width: int = 64) -> np.ndarray:
    """Membuat sinyal hilal + bintang sintetis yang stabil untuk pengujian."""
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    sky = 800.0 + 2.5 * yy + 1.2 * xx
    cy, cx = height * 0.52, width * 0.48
    dy, dx = yy - cy, xx - cx
    radius = np.hypot(dx, dy)
    angle = np.arctan2(dy, dx)
    ring = np.exp(-0.5 * ((radius - 11.0) / 1.5) ** 2)
    crescent = 500.0 * ring * (np.clip(np.cos(angle - 0.3), 0.0, 1.0) ** 2)
    stars = (
        900.0 * np.exp(-0.5 * (((xx - width * 0.25) ** 2 + (yy - height * 0.30) ** 2) / 1.4**2))
        + 850.0 * np.exp(-0.5 * (((xx - width * 0.75) ** 2 + (yy - height * 0.28) ** 2) / 1.4**2))
        + 950.0 * np.exp(-0.5 * (((xx - width * 0.68) ** 2 + (yy - height * 0.74) ** 2) / 1.5**2))
    )
    return (sky + crescent + stars).astype(np.float32)


def _write_ser(
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


def _write_avi_rgb(path: Path, frames_rgb_u8: list[np.ndarray], fps: int = 10) -> Path:
    h, w, _ = frames_rgb_u8[0].shape
    container = av.open(str(path), mode="w")
    stream = container.add_stream("rawvideo", rate=fps)
    stream.width = w
    stream.height = h
    stream.pix_fmt = "rgb24"
    for arr in frames_rgb_u8:
        vf = av.VideoFrame.from_ndarray(np.ascontiguousarray(arr, dtype=np.uint8), format="rgb24")
        for pkt in stream.encode(vf):
            container.mux(pkt)
    for pkt in stream.encode():
        container.mux(pkt)
    container.close()
    return path


# =====================================================================
# A. PENGUJIAN FORMAT MASTER FLAT
# =====================================================================
def test_master_flat_formats_fits_multi_hdu_tiff_png_jpeg_and_sequences(tmp_path: Path) -> None:
    """Menguji pembacaan Master Flat dari FITS (single & multi-HDU), TIFF, PNG, JPEG, dan Sequence."""
    h, w = 36, 48
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    flat_pattern = 1000.0 * (1.0 - 0.15 * (((yy - 18.0) / 18.0) ** 2 + ((xx - 24.0) / 24.0) ** 2))

    # 1. Single FITS Master Flat
    fits_path = tmp_path / "master_flat.fits"
    fits.PrimaryHDU(data=flat_pattern).writeto(fits_path)
    lf_fits = load_single_master_flat(fits_path)
    assert lf_fits.flat_format.startswith("FITS")
    assert lf_fits.flat_input_type == "SINGLE"
    assert (lf_fits.height, lf_fits.width, lf_fits.channels) == (h, w, 1)
    np.testing.assert_allclose(lf_fits.scientific_data, flat_pattern, rtol=1e-6)

    # 2. Multi-HDU FITS Master Flat (memilih hdu_index=1)
    multi_fits_path = tmp_path / "multi_flat.fits"
    hdul = fits.HDUList(
        [
            fits.PrimaryHDU(data=np.ones((10, 10), dtype=np.float32) * 500.0),
            fits.ImageHDU(data=flat_pattern, name="FLAT_EXT"),
        ]
    )
    hdul.writeto(multi_fits_path)
    lf_multi_fits = load_single_master_flat(multi_fits_path, hdu_index=1)
    assert (lf_multi_fits.height, lf_multi_fits.width) == (h, w)
    np.testing.assert_allclose(lf_multi_fits.scientific_data, flat_pattern, rtol=1e-6)

    # 3. Single & Multi-page TIFF Master Flat
    tiff_path = tmp_path / "master_flat.tif"
    tifffile.imwrite(str(tiff_path), flat_pattern.astype(np.uint16))
    lf_tiff = load_single_master_flat(tiff_path)
    assert lf_tiff.flat_format == "TIFF"
    assert lf_tiff.dtype_str == "uint16"

    multi_tiff_path = tmp_path / "multi_flat.tif"
    with tifffile.TiffWriter(str(multi_tiff_path)) as tw:
        tw.write(np.full((12, 12), 500, dtype=np.uint16))
        tw.write(flat_pattern.astype(np.uint16))
    lf_multi_tiff = load_single_master_flat(multi_tiff_path, page_index=1)
    assert lf_multi_tiff.flat_format == "TIFF (Halaman 2/2)"
    assert (lf_multi_tiff.height, lf_multi_tiff.width) == (h, w)

    # 4. PNG Master Flat (RGB 8-bit) & JPEG Master Flat (memastikan peringatan lossy tercatat)
    png_path = tmp_path / "master_flat.png"
    jpg_path = tmp_path / "master_flat.jpg"
    qimg = QImage(w, h, QImage.Format.Format_RGB888)
    qimg.fill(QColor(180, 185, 190))
    assert qimg.save(str(png_path), "PNG")
    assert qimg.save(str(jpg_path), "JPEG")

    lf_png = load_single_master_flat(png_path)
    assert lf_png.flat_format == "PNG"
    assert lf_png.channels == 3
    assert lf_png.is_lossy_source is False

    lf_jpg = load_single_master_flat(jpg_path)
    assert lf_jpg.is_lossy_source is True
    assert any("lossy" in w_msg.lower() for w_msg in lf_jpg.warnings)

    # 5. Flat Frame Sequence (Folder Sequence berisi 4 berkas TIFF)
    seq_folder = tmp_path / "flat_seq_folder"
    seq_folder.mkdir()
    for i in range(4):
        tifffile.imwrite(
            str(seq_folder / f"flat_{i + 1:02d}.tif"),
            flat_pattern.astype(np.float32),
        )
    lf_seq = load_master_flat_from_sequence(seq_folder, source_kind="folder")
    assert lf_seq.flat_input_type == "SEQUENCE"
    assert lf_seq.frame_count == 4
    np.testing.assert_allclose(lf_seq.scientific_data, flat_pattern, rtol=1e-6)


def test_master_flat_from_avi_and_ser_and_raw_domain(tmp_path: Path) -> None:
    """Menguji pembuatan Master Flat dari AVI, SER, serta validasi domain RAW Bayer CFA."""
    h, w = 48, 64
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    vignette = 1.0 - 0.20 * (((yy - 24.0) / 24.0) ** 2 + ((xx - 32.0) / 32.0) ** 2)

    # 1. Master Flat dari Video AVI (RGB)
    flat_u8 = np.clip(vignette * 200.0, 50, 240).astype(np.uint8)
    flat_rgb_u8 = np.stack([flat_u8, flat_u8, flat_u8], axis=-1)
    avi_flat_path = _write_avi_rgb(tmp_path / "flat_video.avi", [flat_rgb_u8 for _ in range(5)])

    lf_avi = load_master_flat_auto(avi_flat_path)
    assert lf_avi.flat_input_type == "SEQUENCE"
    assert lf_avi.frame_count == 5
    assert lf_avi.channels == 3
    np.testing.assert_allclose(lf_avi.scientific_data, flat_rgb_u8.astype(np.float32), atol=1e-4)

    # 2. Master Flat dari SER (Bayer RGGB 16-bit)
    flat_u16 = (vignette * 16000.0).astype(np.uint16)
    ser_flat_path = _write_ser(
        tmp_path / "flat_astro.ser",
        [flat_u16 for _ in range(4)],
        color_id=8,  # BAYER_RGGB
        pixel_depth=16,
    )
    lf_ser = load_master_flat_auto(ser_flat_path)
    assert lf_ser.flat_input_type == "SEQUENCE"
    assert lf_ser.frame_count == 4
    assert lf_ser.is_cfa_mosaic is True
    assert lf_ser.cfa_pattern_str == "RGGB"
    np.testing.assert_allclose(lf_ser.scientific_data, flat_u16.astype(np.float32), atol=1e-4)

    # 3. Kamera RAW (sampel Nikon Z6 NEF nyata bila ada di workspace)
    real_nef = Path("DSC_0045.NEF")
    if real_nef.is_file():
        lf_raw = load_single_master_flat(real_nef, validate_flat_characteristics=False)
        assert lf_raw.is_cfa_mosaic is True
        assert lf_raw.cfa_pattern_str == "RGGB"
        assert lf_raw.channels == 1

    # 4. Pastikan video objek langit gelap ditolak sebagai Master Flat Sequence
    dark_sky = np.zeros((h, w, 3), dtype=np.uint8)
    dark_sky[20:23, 30:33, :] = 250  # Hanya titik bintang terang di tengah langit gelap (0)
    bad_video_path = _write_avi_rgb(tmp_path / "night_object.avi", [dark_sky for _ in range(3)])
    with pytest.raises(StackingError, match="tidak valid|pencahayaan"):
        load_master_flat_auto(bad_video_path)


# =====================================================================
# B. PENGUJIAN NUMERIK & VALIDASI KOMPATIBILITAS
# =====================================================================
def test_flat_numerical_accuracy_uniform_gradient_vignetting_and_special_pixels() -> None:
    """Verifikasi matematis F_norm(x,y) = F(x,y) / median(F_valid) dan I_corr = I_orig / F_norm."""
    h, w = 32, 40
    scene = _make_crescent_scene(h, w) - 900.0  # Termasuk nilai negatif linear!
    assert float(np.min(scene)) < 0.0

    # 1. Uniform Flat -> F_norm == 1.0 di setiap piksel -> I_corrected == I_original persis!
    uniform_flat = np.full((h, w), 4200.0, dtype=np.float32)
    norm_u, rep_u = validate_and_prepare_master_flat(
        uniform_flat,
        expected_height=h,
        expected_width=w,
        expected_channels=1,
    )
    assert rep_u.applied is True
    assert rep_u.normalization_method == NORMALIZATION_FORMULA_TEXT
    assert rep_u.flat_median_before_norm == pytest.approx(4200.0)
    assert rep_u.invalid_pixel_count == 0
    np.testing.assert_allclose(norm_u, 1.0, rtol=1e-6)
    corr_u = apply_flat_calibration(scene, norm_u)
    np.testing.assert_allclose(corr_u, scene, rtol=1e-6)

    # 2. Gradien Flat Sintetis -> memulihkan sinyal asli secara matematis
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    true_gain = 0.75 + 0.50 * (xx / float(w - 1))  # Rentang [0.75, 1.25], median eksak = 1.0
    grad_flat = (true_gain * 10000.0).astype(np.float32)
    expected_med = float(np.median(grad_flat))
    expected_f_norm = grad_flat / expected_med

    norm_g, rep_g = validate_and_prepare_master_flat(
        grad_flat,
        expected_height=h,
        expected_width=w,
        expected_channels=1,
    )
    assert rep_g.flat_median_before_norm == pytest.approx(expected_med, rel=1e-6)
    np.testing.assert_allclose(norm_g, expected_f_norm, rtol=1e-6)

    # Jika pengamatan terdistorsi oleh expected_f_norm, pembagian memulihkan scene secara eksak!
    observed = (scene * expected_f_norm).astype(np.float32)
    restored = apply_flat_calibration(observed, norm_g)
    np.testing.assert_allclose(restored, scene, rtol=1e-5, atol=1e-4)

    # 3. Penanganan piksel Nol, Negatif, NaN, Infinity, dan Saturated
    special_flat = np.full((h, w), 20000, dtype=np.uint16).astype(np.float32)
    special_flat[0, 0] = 0.0          # Nol
    special_flat[0, 1] = -50.0        # Negatif
    special_flat[1, 0] = np.nan       # NaN
    special_flat[1, 1] = np.inf       # Infinity
    special_flat[2, 0] = 65535.0      # Saturated (uint16 max)
    special_flat[2, 1] = 65535.0      # Saturated (uint16 max)

    fake_info = ImageInfo(
        path=Path("special_flat.tif"),
        file_name="special_flat.tif",
        file_format="TIFF",
        width=w,
        height=h,
        stored_width=w,
        stored_height=h,
        channels=1,
        has_alpha=False,
        original_bit_depth=16,
        original_is_float=False,
        preview_bit_depth=8,
        exif_orientation="Normal (tanpa rotasi)",
        orientation_applied=False,
        dtype_str="uint16",
    )
    norm_s, rep_s = validate_and_prepare_master_flat(
        special_flat,
        expected_height=h,
        expected_width=w,
        expected_channels=1,
        flat_info=fake_info,
    )
    assert rep_s.zero_or_negative_pixel_count == 2
    assert rep_s.non_finite_pixel_count == 2
    assert rep_s.saturated_pixel_count == 2
    assert rep_s.invalid_pixel_count == 6
    assert rep_s.invalid_pixel_mask is not None
    assert int(np.count_nonzero(rep_s.invalid_pixel_mask)) == 6
    # Piksel Saturated dikeluarkan dari median(F_valid), sehingga median tetap 20000.0!
    assert rep_s.flat_median_before_norm == pytest.approx(20000.0)
    # Tidak ada NaN atau Inf pada hasil normalisasi maupun hasil kalibrasi
    assert np.all(np.isfinite(norm_s))
    corr_s = apply_flat_calibration(scene, norm_s)
    assert np.all(np.isfinite(corr_s))


def test_flat_compatibility_rejections_and_cross_bit_depth_support() -> None:
    """Menguji kompatibilitas lintas bit depth serta penolakan dimensi, kanal, dan CFA yang salah."""
    h, w = 32, 40
    flat_2d = np.full((h, w), 1000.0, dtype=np.float32)
    flat_3d = np.full((h, w, 3), 1000.0, dtype=np.float32)

    # 1. Perbedaan bit depth (mis. flat 16-bit vs light 8-bit) DIIZINKAN dengan peringatan informatif
    flat_info_16 = ImageInfo(
        path=Path("flat16.tif"),
        file_name="flat16.tif",
        file_format="TIFF",
        width=w,
        height=h,
        stored_width=w,
        stored_height=h,
        channels=1,
        has_alpha=False,
        original_bit_depth=16,
        original_is_float=False,
        preview_bit_depth=8,
        exif_orientation="Normal (tanpa rotasi)",
        orientation_applied=False,
        dtype_str="uint16",
    )
    _, rep_bd = validate_and_prepare_master_flat(
        flat_2d,
        expected_height=h,
        expected_width=w,
        expected_channels=1,
        reference_bit_depth=8,
        flat_info=flat_info_16,
    )
    assert rep_bd.applied is True
    assert any("Bit depth Master Flat" in w_msg for w_msg in rep_bd.warnings)

    # 2. Perbedaan dimensi dengan check_compatibility=True -> DITOLAK
    with pytest.raises(StackingError, match="Ukuran Master Flat"):
        validate_and_prepare_master_flat(
            flat_2d,
            expected_height=20,
            expected_width=20,
            expected_channels=1,
            check_compatibility=True,
        )

    # 3. Perbedaan Monokrom vs RGB dengan check_compatibility=True -> DITOLAK
    with pytest.raises(StackingError, match="Jumlah kanal Master Flat"):
        validate_and_prepare_master_flat(
            flat_2d,
            expected_height=h,
            expected_width=w,
            expected_channels=3,
            check_compatibility=True,
        )
    with pytest.raises(StackingError, match="Jumlah kanal Master Flat"):
        validate_and_prepare_master_flat(
            flat_3d,
            expected_height=h,
            expected_width=w,
            expected_channels=1,
            check_compatibility=True,
        )

    # 4. Ketidakcocokan domain CFA (Mono Non-CFA flat vs Bayer CFA light) -> DITOLAK
    with pytest.raises(StackingError, match="Domain sensor Master Flat"):
        validate_and_prepare_master_flat(
            flat_2d,
            expected_height=h,
            expected_width=w,
            expected_channels=1,
            expected_is_cfa=True,
            expected_cfa_pattern="RGGB",
            flat_info=flat_info_16,
            check_compatibility=True,
        )

    # 5. Ketidakcocokan pola Bayer CFA (BGGR flat vs RGGB light) -> DITOLAK
    raw_bggr = RawMetadataInfo(
        camera_make="Test",
        camera_model="Cam",
        lens_make=None,
        lens_model=None,
        iso_speed=100,
        shutter_speed_sec=0.01,
        aperture_fnumber=2.8,
        focal_length_mm=50.0,
        timestamp_str=None,
        raw_width=w,
        raw_height=h,
        visible_width=w,
        visible_height=h,
        top_margin=0,
        left_margin=0,
        raw_type_str="Bayer",
        is_cfa_mosaic=True,
        num_colors=3,
        color_desc="RGBG",
        raw_pattern_matrix=((2, 1), (1, 0)),
        cfa_pattern_str="BGGR",
        black_level_per_channel=(0, 0, 0, 0),
        white_level=16383,
        camera_white_level_per_channel=(16383, 16383, 16383, 16383),
        camera_whitebalance=(1.0, 1.0, 1.0, 1.0),
        daylight_whitebalance=(1.0, 1.0, 1.0, 1.0),
    )
    flat_info_bggr = ImageInfo(
        path=Path("flat_bggr.dng"),
        file_name="flat_bggr.dng",
        file_format="DNG",
        width=w,
        height=h,
        stored_width=w,
        stored_height=h,
        channels=1,
        has_alpha=False,
        original_bit_depth=14,
        original_is_float=False,
        preview_bit_depth=8,
        exif_orientation="Normal (tanpa rotasi)",
        orientation_applied=False,
        dtype_str="uint16",
        raw_metadata=raw_bggr,
    )
    with pytest.raises(StackingError, match="Pola CFA Master Flat"):
        validate_and_prepare_master_flat(
            flat_2d,
            expected_height=h,
            expected_width=w,
            expected_channels=1,
            expected_is_cfa=True,
            expected_cfa_pattern="RGGB",
            flat_info=flat_info_bggr,
            check_compatibility=True,
        )


# =====================================================================
# C. PENGUJIAN INTEGRASI GUI, AVI/SER/FITS/TIFF STACKING, & OUTPUT
# =====================================================================
def test_gui_flat_calibration_integration_avi_fits_ser_and_safety_rules(
    qapp: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Menguji alur lengkap Flat Calibration melalui GUI untuk AVI, FITS, dan SER."""
    errors: list[str] = []
    monkeypatch.setattr(MainWindow, "_show_error", lambda self, msg: errors.append(msg))
    monkeypatch.setattr(MainWindow, "_show_warning", lambda self, msg: None)
    monkeypatch.setattr(MainWindow, "_confirm_shift_risk", lambda self, msg: True)

    h, w = 48, 64
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    vignette = 0.80 + 0.40 * (xx / float(w - 1))  # Median = 1.0
    true_scene = _make_crescent_scene(h, w)

    # Buat 4 berkas FITS light yang terdistorsi oleh vignette + 1 berkas FITS Master Flat
    light_dir = tmp_path / "fits_lights"
    light_dir.mkdir()
    light_paths: list[Path] = []
    for i in range(4):
        lp = light_dir / f"light_{i + 1:02d}.fits"
        fits.PrimaryHDU(data=(true_scene * vignette).astype(np.float32)).writeto(lp)
        light_paths.append(lp)

    flat_fits_path = tmp_path / "master_flat.fits"
    flat_data = (vignette * 5000.0).astype(np.float32)
    flat_data[0, 0] = 0.0  # 1 invalid pixel (nol) untuk memverifikasi pelaporan invalid pixels di GUI
    fits.PrimaryHDU(data=flat_data).writeto(flat_fits_path)

    hashes_before = {
        p: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (*light_paths, flat_fits_path)
    }

    win = MainWindow()
    win.show()
    assert win.load_sequence_paths(light_paths) is True
    assert win.start_stacking_button.isEnabled() is True

    # 1. Jika checkbox Flat diaktifkan tetapi Master Flat belum dipilih -> Mulai Stacking WAJIB nonaktif!
    win.flat_checkbox.setChecked(True)
    assert win.start_stacking_button.isEnabled() is False
    assert "belum dipilih" in win._proc_values["proc_flat_status"].text()
    assert win.start_stacking(wait_for_completion=True) is False
    assert any("belum dipilih" in e for e in errors)

    # 2. Pilih Master Flat yang ukurannya salah -> Mulai Stacking menghentikan proses saat runtime division mismatch!
    bad_flat_path = tmp_path / "wrong_size_flat.tif"
    tifffile.imwrite(str(bad_flat_path), np.full((20, 20), 1000, dtype=np.uint16))
    assert win.set_master_flat_path(bad_flat_path) is True
    errors.clear()
    assert win.start_stacking(wait_for_completion=True) is False
    assert win._last_stacking_result is None
    assert any("tidak sesuai" in e.lower() or "dimensi" in e.lower() for e in errors)

    # 3. Pilih Master Flat FITS yang KOMPATIBEL -> Informasi tampil lengkap di GUI & Preview Flat bekerja
    assert win.set_master_flat_path(flat_fits_path) is True
    assert NORMALIZATION_FORMULA_TEXT in win._proc_values["flat_norm_status"].text()
    assert "1 piksel" in win._proc_values["flat_invalid_pixels"].text()
    assert win.preview_master_flat() is True
    assert win.viewer.has_image()
    assert win.start_stacking_button.isEnabled() is True

    # 3b. Uji tombol langsung Start Calibration pada GUI
    assert win.start_flat_calibration() is True
    assert win._last_calibrated_frames is not None
    assert len(win._last_calibrated_frames) == 4
    assert win._last_calibrated_frames[0].shape == (h, w)

    # Jalankan stacking dengan Flat Calibration aktif
    win.set_stacking_profile(StackingProfile.BASIC)
    assert win.start_stacking(wait_for_completion=True) is True
    res = win._last_stacking_result
    assert res is not None
    assert res.flat_report is not None
    assert res.flat_report.applied is True
    assert res.flat_report.invalid_pixel_count == 1
    assert "Flat-field: DITERAPKAN (master_flat.fits)" in win._proc_values["res_history"].text()
    assert NORMALIZATION_FORMULA_TEXT in win._proc_values["res_history"].text()

    # Verifikasi matematis: di luar piksel [0, 0], vignetting telah dikoreksi kembali ke true_scene!
    valid_mask = np.ones((h, w), dtype=bool)
    valid_mask[0, 0] = False
    f_norm_expected = np.where(
        valid_mask,
        flat_data / float(np.median(flat_data[valid_mask])),
        1.0,
    )
    expected_corrected = (true_scene * vignette) / f_norm_expected
    np.testing.assert_allclose(
        res.stacked_scientific_data[valid_mask],
        expected_corrected[valid_mask],
        rtol=1e-5,
        atol=1e-3,
    )

    # 4. Uji ekspor FITS, TIFF, dan PNG beserta laporan JSON
    out_fits = tmp_path / "out" / "calibrated_stack.fits"
    out_tif = tmp_path / "out" / "calibrated_stack.tif"
    out_png = tmp_path / "out" / "calibrated_stack.png"
    assert win.save_stacking_result_to_path(out_fits) == out_fits
    assert win.save_stacking_result_to_path(out_tif) == out_tif
    assert win.save_stacking_result_to_path(out_png) == out_png

    with fits.open(out_fits, mode="readonly") as hdul:
        assert hdul[0].header["FLATCORR"] is True
        assert hdul[0].header["FLATSRC"] == "master_flat.fits"
        assert hdul[0].header["FLATINV"] == 1
        np.testing.assert_allclose(hdul[0].data, res.stacked_scientific_data, rtol=1e-6)

    tif_loaded = tifffile.imread(str(out_tif))
    assert tif_loaded.dtype == np.float32
    np.testing.assert_allclose(tif_loaded, res.stacked_scientific_data, rtol=1e-6)

    rep_json = json.loads(
        out_fits.with_name("calibrated_stack_stacking_report.json").read_text(encoding="utf-8")
    )
    assert rep_json["flat_calibration"]["applied"] is True
    assert rep_json["flat_calibration"]["normalization_method"] == NORMALIZATION_FORMULA_TEXT
    assert rep_json["flat_calibration"]["invalid_pixel_count"] == 1

    # Pastikan berkas Master Flat juga dilindungi dari penimpaan (overwrite protection)
    errors.clear()
    assert win.save_stacking_result_to_path(flat_fits_path) is None
    assert any("Dilarang menimpa berkas sumber" in e for e in errors)

    # 5. Uji Video AVI Light Sequence + Video AVI Flat Sequence melalui GUI!
    u8_light = np.clip((true_scene - 750.0) * 0.4 * vignette, 15, 235).astype(np.uint8)
    rgb_light = np.stack([u8_light, u8_light, u8_light], axis=-1)
    avi_light_path = _write_avi_rgb(tmp_path / "hilal_obs.avi", [rgb_light for _ in range(4)])

    u8_flat = np.clip(vignette * 180.0, 60, 240).astype(np.uint8)
    rgb_flat = np.stack([u8_flat, u8_flat, u8_flat], axis=-1)
    avi_flat_path = _write_avi_rgb(tmp_path / "hilal_flat.avi", [rgb_flat for _ in range(4)])

    assert win.load_video_path(avi_light_path) is True
    assert win.set_master_flat_sequence(avi_flat_path, source_kind="video") is True
    assert "KOMPATIBEL" in win._proc_values["flat_compat_status"].text()
    assert win.start_stacking(wait_for_completion=True) is True
    assert win._last_stacking_result is not None
    assert win._last_stacking_result.flat_report is not None
    assert win._last_stacking_result.flat_report.applied is True
    assert "DITERAPKAN" in win._proc_values["res_history"].text()

    # 6. Verifikasi seluruh berkas sumber tetap utuh 100% (SHA-256)
    for p, sha_orig in hashes_before.items():
        assert hashlib.sha256(p.read_bytes()).hexdigest() == sha_orig

    win.close()


def test_flat_calibration_light_106_frames_and_flat_26_frames(tmp_path: Path) -> None:
    """Verifikasi kasus aktual pengguna: Light sequence 106 frame dan Flat sequence 26 frame.

    Membuktikan secara ketat:
      1. Jumlah frame Light dan Flat tidak wajib sama (106 light vs 26 flat).
      2. Seluruh 26 flat frames diagregasikan menjadi SATU Master Flat (frame_count == 26).
      3. Master Flat bukan salinan frame pertama, melainkan hasil agregasi seluruh 26 frame.
      4. Master Flat yang sama diterapkan kepada seluruh 106 light frames tanpa one-to-one matching.
      5. Hasil kalibrasi menghasilkan persis 106 frame terkalibrasi yang diteruskan ke Stacking.
      6. Stacking berhasil mengagregasi 106 frame terkalibrasi dengan laporan flat diterapkan.
    """
    h, w = 32, 32
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # Vignetting radial sintetis (pusat terang, tepi redup ~80%)
    vignette = 1.0 - 0.20 * (((yy - 16.0) / 16.0) ** 2 + ((xx - 16.0) / 16.0) ** 2)

    rng = np.random.default_rng(2026)

    # 1. Buat 26 flat frames (vignette + variasi noise kecil di setiap frame)
    flat_frames_u8: list[np.ndarray] = []
    for _ in range(26):
        noise = rng.normal(0.0, 1.5, (h, w)).astype(np.float32)
        f_u8 = np.clip((vignette * 180.0) + noise, 30.0, 240.0).astype(np.uint8)
        f_rgb = np.stack([f_u8, f_u8, f_u8], axis=-1)
        flat_frames_u8.append(f_rgb)

    flat_avi_path = _write_avi_rgb(tmp_path / "flat_26.avi", flat_frames_u8, fps=15)

    # 2. Buat 106 light frames (objek hilal/langit + vignette + noise)
    light_scene = 100.0 + 15.0 * np.sin(xx * 0.2) + 20.0 * np.cos(yy * 0.2)
    light_frames_u8: list[np.ndarray] = []
    for _ in range(106):
        noise = rng.normal(0.0, 2.0, (h, w)).astype(np.float32)
        l_u8 = np.clip((light_scene * vignette) + noise, 20.0, 240.0).astype(np.uint8)
        l_rgb = np.stack([l_u8, l_u8, l_u8], axis=-1)
        light_frames_u8.append(l_rgb)

    light_avi_path = _write_avi_rgb(tmp_path / "light_106.avi", light_frames_u8, fps=15)

    # 3. Muat Master Flat dari Flat Sequence (26 frame)
    master_flat = load_master_flat_auto(flat_avi_path)

    # Assert 1: Master Flat mencatat 26 frame
    assert master_flat.frame_count == 26
    assert master_flat.channels == 3
    assert master_flat.height == h
    assert master_flat.width == w

    # Assert 2: Master Flat merupakan hasil agregasi ke-26 frame, bukan sekadar frame ke-0
    frame_0_f32 = flat_frames_u8[0].astype(np.float32)
    diff_from_first = np.abs(master_flat.scientific_data - frame_0_f32)
    assert np.any(diff_from_first > 0.0)

    # 4. Buka Light Sequence (106 frame)
    sm_light = SequenceManager()
    try:
        sm_light.open_video_file(light_avi_path)
        assert sm_light.frame_count == 106

        # Assert 3: Validasi kompatibilitas berhasil tanpa mempedulikan perbedaan jumlah frame (106 vs 26)
        first_light = sm_light.load_frame(0)
        from hilalone.processing.stacking.flat_calibration import check_flat_compatibility
        compat = check_flat_compatibility(
            master_flat,
            expected_height=h,
            expected_width=w,
            expected_channels=3,
            reference_info=first_light.info,
        )
        assert compat.is_compatible is True
        assert not any("frame" in r.lower() for r in compat.reasons)

        # 5. Jalankan run_flat_calibration_on_sequence
        calibrated_frames, cal_report = run_flat_calibration_on_sequence(sm_light, master_flat)

        # Assert 4: Jumlah calibrated frames persis sama dengan light frames (106)
        assert len(calibrated_frames) == 106
        assert cal_report.applied is True
        for cal_f in calibrated_frames:
            assert cal_f.shape == (h, w, 3)
            assert cal_f.dtype == np.float32

        # 6. Jalankan Stacking Engine dengan Master Flat aktif
        stack_result = run_stacking_on_sequence(
            sm_light,
            profile=StackingProfile.BASIC,
            master_flat=master_flat,
        )

        # Assert 5: Stacking memproses 106 frame dan flat terkalibrasi sukses
        assert stack_result.total_input_frames == 106
        assert stack_result.stacked_frame_count == 106
        assert stack_result.stacked_scientific_data.shape == (h, w, 3)
        assert stack_result.flat_report is not None
        assert stack_result.flat_report.applied is True
        assert "flat_26.avi" in stack_result.flat_report.source_description
    finally:
        sm_light.clear()


def test_flat_calibration_real_pal8_avi_files() -> None:
    """Menguji data observasi nyata pak Ahmad Junaidi (AVI pal8 / rawvideo).

    Memastikan regresi context seek(0) FFmpeg/PyAV tidak pernah terulang lagi:
      - moon.avi (103 frame pal8) terbaca dengan sinyal terang (>0).
      - flat.avi (26 frame pal8) terbaca homogen (>0) dan sukses menghasilkan Master Flat.
    """
    real_flat = Path(r"C:\Astrofotografer\Stacking beta\bahan pak ahmad junaidi\flat.avi")
    real_moon = Path(r"C:\Astrofotografer\Stacking beta\bahan pak ahmad junaidi\moon.avi")

    if not real_flat.is_file() or not real_moon.is_file():
        pytest.skip("Berkas sampel nyata tidak ditemukan di sistem lokal.")

    # 1. Pastikan flat.avi sukses dimuat sebagai Master Flat 26 frame tanpa error
    master_flat = load_master_flat_auto(real_flat)
    assert master_flat.frame_count == 26
    assert master_flat.channels == 3
    assert master_flat.scientific_data.min() > 50.0
    assert master_flat.scientific_data.mean() > 100.0

    # 2. Pastikan moon.avi terbaca dengan sinyal terang dan kompatibel dengan flat.avi
    sm = SequenceManager()
    try:
        sm.open_video_file(real_moon)
        assert sm.frame_count == 103
        f0 = sm.load_frame(0)
        assert f0.scientific_data is not None
        assert f0.scientific_data.mean() > 100.0

        compat = check_flat_compatibility(
            master_flat,
            expected_height=f0.info.height,
            expected_width=f0.info.width,
            expected_channels=f0.info.channels,
            reference_info=f0.info,
        )
        assert compat.is_compatible is True
    finally:
        sm.clear()


