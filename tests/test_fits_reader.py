"""Pengujian unit untuk FITS Reader astronomi (hilalone.input_manager.adapters.fits_reader)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from PySide6.QtGui import QImage

from hilalone.input_manager.adapters.fits_reader import (
    UNAVAILABLE_TEXT,
    inspect_fits_hdus,
    read_fits,
)
from hilalone.input_manager.image_reader import (
    ImageReadError,
    MultiHduFitsError,
    read_image,
    supported_extensions,
)


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001
    return qapp


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# -------------------------------------------- 1. Ekstensi & Dimensi 20x12
def test_supported_extensions_include_fits() -> None:
    exts = supported_extensions()
    for ext in ("fit", "fits", "fts"):
        assert ext in exts


def test_fits_rectangular_dimensions_naxis1_20_naxis2_12(tmp_path: Path) -> None:
    """NAXIS1=20 (lebar) dan NAXIS2=12 (tinggi) wajib menghasilkan array shape (12, 20)."""
    source = np.arange(12 * 20, dtype=np.int16).reshape(12, 20)
    path = tmp_path / "rect_20x12.fits"
    fits.PrimaryHDU(data=source).writeto(path)

    loaded = read_image(path)
    assert loaded.scientific_data is not None
    assert loaded.scientific_data.shape == (12, 20)
    assert np.array_equal(loaded.scientific_data, source)

    hdr = loaded.info.fits_header
    assert hdr is not None
    assert hdr.naxis == 2
    assert hdr.naxis1 == 20
    assert hdr.naxis2 == 12
    assert (loaded.info.width, loaded.info.height) == (20, 12)
    assert (loaded.preview.width(), loaded.preview.height()) == (20, 12)


# -------------------------------------------- 2. Grayscale int16
def test_fits_int16_exact_preservation(tmp_path: Path) -> None:
    source = np.linspace(-1000, 15000, num=10 * 16, dtype=np.int16).reshape(10, 16)
    path = tmp_path / "int16.fits"
    fits.PrimaryHDU(data=source).writeto(path)

    loaded = read_image(path)
    assert loaded.scientific_data is not None
    assert loaded.scientific_data.dtype == np.int16
    assert loaded.scientific_data.shape == (10, 16)
    assert np.array_equal(loaded.scientific_data, source)

    hdr = loaded.info.fits_header
    assert hdr is not None
    assert hdr.bitpix == 16
    assert hdr.stored_dtype_str == "int16"
    assert hdr.interpreted_dtype_str == "int16"
    assert hdr.scaling_applied is False
    assert loaded.preview.format() == QImage.Format.Format_Grayscale8


# -------------------------------------------- 3. Grayscale uint16 (BZERO=32768, BSCALE=1)
def test_fits_uint16_with_bzero_bscale_convention(tmp_path: Path) -> None:
    """Astropy menulis uint16 sebagai BITPIX=16 dengan BZERO=32768 dan BSCALE=1."""
    source = np.array(
        [[0, 100, 32767, 32768], [40000, 50000, 65534, 65535]],
        dtype=np.uint16,
    )
    path = tmp_path / "uint16_bzero.fits"
    fits.PrimaryHDU(data=source).writeto(path)

    loaded = read_image(path)
    assert loaded.scientific_data is not None
    assert loaded.scientific_data.dtype == np.uint16
    assert loaded.scientific_data.shape == (2, 4)
    assert np.array_equal(loaded.scientific_data, source)

    hdr = loaded.info.fits_header
    assert hdr is not None
    assert hdr.bitpix == 16
    assert hdr.bzero == 32768
    assert hdr.bscale == 1
    assert hdr.stored_dtype_str == "int16"
    assert hdr.interpreted_dtype_str == "uint16"
    assert hdr.is_uint16_offset_convention is True
    assert hdr.scaling_applied is True
    assert loaded.info.original_bit_depth == 16


# -------------------------------------------- 4. Float32 & Float64
@pytest.mark.parametrize(
    ("dtype", "expected_bitpix"),
    [(np.float32, -32), (np.float64, -64)],
)
def test_fits_floating_point_exact_preservation(
    tmp_path: Path, dtype: type[np.floating], expected_bitpix: int
) -> None:
    source = np.linspace(-5.25, 120.875, num=8 * 12, dtype=dtype).reshape(8, 12)
    path = tmp_path / f"float_{expected_bitpix}.fits"
    fits.PrimaryHDU(data=source).writeto(path)

    loaded = read_image(path)
    assert loaded.scientific_data is not None
    assert loaded.scientific_data.dtype == dtype
    assert loaded.scientific_data.shape == (8, 12)
    assert np.array_equal(loaded.scientific_data, source)
    assert loaded.info.original_is_float is True
    assert loaded.info.fits_header is not None
    assert loaded.info.fits_header.bitpix == expected_bitpix


def test_fits_custom_bscale_bzero_physical_scaling(tmp_path: Path) -> None:
    """Jika BSCALE/BZERO kustom digunakan, memisahkan stored BITPIX dan physical float."""
    raw_stored = np.array([[10, 20], [30, 40]], dtype=np.int16)
    hdu = fits.PrimaryHDU(data=raw_stored)
    hdu.header["BSCALE"] = 2.5
    hdu.header["BZERO"] = 100.0
    path = tmp_path / "scaled_custom.fits"
    hdu.writeto(path)

    loaded = read_image(path)
    assert loaded.scientific_data is not None
    expected_physical = 100.0 + 2.5 * raw_stored.astype(np.float64)
    assert np.allclose(loaded.scientific_data, expected_physical)

    hdr = loaded.info.fits_header
    assert hdr is not None
    assert hdr.bitpix == 16
    assert hdr.stored_dtype_str == "int16"
    assert hdr.scaling_applied is True
    assert hdr.bscale == 2.5
    assert hdr.bzero == 100.0


# -------------------------------------------- 5. Multi-HDU
def test_fits_empty_primary_and_single_image_extension_auto_selected(tmp_path: Path) -> None:
    """Jika Primary HDU kosong dan hanya ada 1 ImageHDU, boleh dipilih otomatis."""
    primary = fits.PrimaryHDU()  # kosong (NAXIS=0)
    img_data = np.arange(24, dtype=np.uint16).reshape(4, 6)
    ext = fits.ImageHDU(data=img_data, name="SCI")
    path = tmp_path / "empty_primary_one_ext.fits"
    fits.HDUList([primary, ext]).writeto(path)

    hdus = inspect_fits_hdus(path)
    assert len(hdus) == 2
    assert hdus[0].is_image is False
    assert hdus[1].is_image is True

    loaded = read_image(path)
    assert loaded.scientific_data is not None
    assert np.array_equal(loaded.scientific_data, img_data)
    assert loaded.info.hdu_index == 1
    assert loaded.info.hdu_count == 2
    assert "HDU #1" in loaded.info.file_format


def test_fits_multiple_image_hdus_require_explicit_selection(tmp_path: Path) -> None:
    """Jika terdapat beberapa HDU gambar, sistem tidak boleh mengambil HDU pertama diam-diam."""
    img0 = np.full((6, 8), 100, dtype=np.uint16)
    img1 = np.full((6, 8), 50000, dtype=np.uint16)
    hdu0 = fits.PrimaryHDU(data=img0)
    hdu1 = fits.ImageHDU(data=img1, name="SECOND")
    path = tmp_path / "multi_image_hdu.fits"
    fits.HDUList([hdu0, hdu1]).writeto(path)

    with pytest.raises(MultiHduFitsError) as exc_info:
        read_image(path)
    assert len(exc_info.value.image_hdus) == 2
    assert exc_info.value.total_hdu_count == 2

    loaded0 = read_image(path, hdu_index=0)
    loaded1 = read_image(path, hdu_index=1)
    assert loaded0.scientific_data is not None
    assert loaded1.scientific_data is not None
    assert np.array_equal(loaded0.scientific_data, img0)
    assert np.array_equal(loaded1.scientific_data, img1)
    assert loaded0.info.hdu_index == 0
    assert loaded1.info.hdu_index == 1


# -------------------------------------------- 6. Header Lengkap & Tidak Lengkap
def test_fits_complete_and_incomplete_headers(tmp_path: Path) -> None:
    data = np.ones((4, 5), dtype=np.float32)

    # Header tidak lengkap (tanpa DATE-OBS, EXPTIME, INSTRUME, GAIN, TELESCOP)
    p_incomplete = tmp_path / "incomplete_hdr.fits"
    fits.PrimaryHDU(data=data).writeto(p_incomplete)
    loaded_inc = read_image(p_incomplete)
    assert loaded_inc.info.fits_header is not None
    disp_inc = loaded_inc.info.fits_header.to_display_dict()
    for key in ("DATE-OBS", "EXPTIME", "INSTRUME", "GAIN", "TELESCOP"):
        assert disp_inc[key] == UNAVAILABLE_TEXT

    # Header lengkap
    hdu_full = fits.PrimaryHDU(data=data)
    hdu_full.header["DATE-OBS"] = "2026-11-05T18:05:00"
    hdu_full.header["EXPTIME"] = 1.25
    hdu_full.header["INSTRUME"] = "ZWO ASI183MC"
    hdu_full.header["GAIN"] = 120
    hdu_full.header["TELESCOP"] = "Takahashi FSQ-85"
    p_full = tmp_path / "full_hdr.fits"
    hdu_full.writeto(p_full)

    loaded_full = read_image(p_full)
    assert loaded_full.info.fits_header is not None
    disp_full = loaded_full.info.fits_header.to_display_dict()
    assert disp_full["DATE-OBS"] == "2026-11-05T18:05:00"
    assert disp_full["EXPTIME"] == "1.25"
    assert disp_full["INSTRUME"] == "ZWO ASI183MC"
    assert disp_full["GAIN"] == "120"
    assert disp_full["TELESCOP"] == "Takahashi FSQ-85"


# -------------------------------------------- 7. Keamanan File Sumber & Handle
def test_fits_source_file_never_modified_and_handle_closed(tmp_path: Path) -> None:
    source = np.arange(60, dtype=np.uint16).reshape(6, 10)
    path = tmp_path / "readonly_check.fits"
    fits.PrimaryHDU(data=source).writeto(path)

    hash_before = _sha256(path)
    stat_before = path.stat()

    loaded = read_fits(path)
    assert loaded.scientific_data.flags.writeable is False

    # Pastikan hash dan metadata file di disk tidak berubah sama sekali
    assert _sha256(path) == hash_before
    assert path.stat().st_mtime_ns == stat_before.st_mtime_ns
    assert path.stat().st_size == stat_before.st_size

    # Pastikan file handle sudah ditutup oleh Windows (bisa diganti nama tanpa PermissionError)
    renamed = tmp_path / "renamed_check.fits"
    path.rename(renamed)
    assert renamed.exists()


# -------------------------------------------- 8. Tampilan GUI Informasi FITS & Header Lengkap
def test_gui_fits_structured_metadata_and_collapsible_full_header(
    qapp,  # noqa: ANN001
    tmp_path: Path,
) -> None:
    """Menguji 3 sub-kelompok Informasi FITS, DATE-OBS panjang, keyword kustom, dan collapsible Header Lengkap."""
    from hilalone.gui.main_window import MainWindow

    # 1. Buat berkas FITS dengan header lengkap + keyword kustom + DATE-OBS panjang
    data1 = np.arange(80, dtype=np.int16).reshape(8, 10)
    hdu1 = fits.PrimaryHDU(data=data1)
    long_date_obs = "2026-06-16T17:21:29.987654321Z"
    hdu1.header["BSCALE"] = 1.0
    hdu1.header["BZERO"] = 0.0
    hdu1.header["BLANK"] = -32768
    hdu1.header["DATE-OBS"] = (long_date_obs, "High precision UTC observation time")
    hdu1.header["DATE"] = "2026-06-16"
    hdu1.header["TIME-OBS"] = "17:21:29.987"
    hdu1.header["EXPTIME"] = (0.09178114256022202, "Exposure time in seconds")
    hdu1.header["GAIN"] = 120
    hdu1.header["FILTER"] = "IR-Pass 685nm"
    hdu1.header["OBJECT"] = "Hilal Dzulhijjah 1447H"
    hdu1.header["INSTRUME"] = "ZWO ASI290MM Mini Planetary Camera"
    hdu1.header["TELESCOP"] = "William Optics RedCat 51 APO"
    hdu1.header["OBSERVER"] = "Tim Rukyat HILALONE"
    hdu1.header["DETECTOR"] = "Sony IMX290"
    hdu1.header["CUSTOMKW"] = ("HILAL_2026_OK", "Custom observatory tag")
    p_full = tmp_path / "01_full_meta.fits"
    hdu1.writeto(p_full)

    # 2. Buat berkas FITS dengan header minimal (tanpa metadata observasi/instrumen)
    data2 = np.zeros((8, 10), dtype=np.int16)
    p_min = tmp_path / "02_min_meta.fits"
    fits.PrimaryHDU(data=data2).writeto(p_min)

    win = MainWindow()
    win.resize(1333, 768)
    win.show()
    qapp.processEvents()
    try:
        # Buka Single Image FITS lengkap
        assert win.load_path(p_full) is True
        qapp.processEvents()

        # Pastikan bagian 'Informasi FITS' tampil dan 'Metadata RAW' tersembunyi
        assert win.header_fits_info.text() == "Informasi FITS"
        assert win.section_fits_info.isHidden() is False
        assert win.section_camera_metadata.isHidden() is True

        # A. Struktur Data
        assert win._info_values["fits_bitpix"].text() == "16"
        assert win._info_values["fits_naxis"].text() == "2"
        assert win._info_values["fits_naxis1"].text() == "10"
        assert win._info_values["fits_naxis2"].text() == "8"
        assert win._info_values["fits_blank"].isHidden() is False
        assert win._info_values["fits_blank"].text() == "-32768"

        # B. Informasi Observasi (DATE-OBS utuh dan EXPTIME diformat ke ms pada ringkasan)
        assert win.fits_sub_struct_label.text() == "A. Struktur Data"
        assert win.fits_sub_obs_label.text() == "B. Informasi Observasi"
        assert win.fits_sub_inst_label.text() == "C. Informasi Instrumen"
        assert win._info_values["fits_date_obs"].text() == long_date_obs
        assert win._info_values["fits_date"].isHidden() is False
        assert win._info_values["fits_date"].text() == "2026-06-16"
        assert win._info_values["fits_time_obs"].isHidden() is False
        assert win._info_values["fits_exptime"].text() == "91.78 ms"
        assert win._info_values["fits_gain"].text() == "120"
        assert win._info_values["fits_filter"].text() == "IR-Pass 685nm"
        assert win._info_values["fits_object"].text() == "Hilal Dzulhijjah 1447H"

        # C. Informasi Instrumen
        assert win._info_values["fits_instrume"].text() == "ZWO ASI290MM Mini Planetary Camera"
        assert win._info_values["fits_telescop"].text() == "William Optics RedCat 51 APO"
        assert win._info_values["fits_observer"].text() == "Tim Rukyat HILALONE"
        assert win._info_values["fits_detector"].text() == "Sony IMX290"

        # Bagian Collapsible: Header FITS Lengkap (default tertutup, dibuka saat diklik)
        assert win.fits_full_header_toggle.isChecked() is False
        assert win.fits_full_header_container.isHidden() is True
        win.fits_full_header_toggle.setChecked(True)
        qapp.processEvents()
        assert win.fits_full_header_container.isHidden() is False
        full_hdr_text = win._info_values["fits_full_header"].text()
        assert "CUSTOMKW" in full_hdr_text
        assert "HILAL_2026_OK" in full_hdr_text
        assert "Custom observatory tag" in full_hdr_text
        assert long_date_obs in full_hdr_text
        # Nilai EXPTIME asli berpresisi penuh tetap utuh di Header FITS Lengkap!
        assert "0.09178114256022202" in full_hdr_text

        # 3. Uji Multiple Images FITS (perpindahan dari header lengkap ke header minimal)
        assert win.load_sequence_paths([p_full, p_min]) is True
        qapp.processEvents()
        win.show_next_frame()
        qapp.processEvents()

        assert win._info_values["file_name"].text() == "02_min_meta.fits"
        assert win._info_values["fits_date_obs"].text() == "Tidak tersedia"
        assert win._info_values["fits_exptime"].text() == "Tidak tersedia"
        assert win._info_values["fits_gain"].text() == "Tidak tersedia"
        assert win._info_values["fits_instrume"].text() == "Tidak tersedia"
        assert win._info_values["fits_telescop"].text() == "Tidak tersedia"
        # Field opsional yang tidak ada harus disembunyikan pada berkas minimal
        assert win._info_values["fits_blank"].isHidden() is True
        assert win._info_values["fits_date"].isHidden() is True
        assert win._info_values["fits_time_obs"].isHidden() is True
        assert win._info_values["fits_filter"].isHidden() is True
        assert win._info_values["fits_object"].isHidden() is True
        assert win._info_values["fits_observer"].isHidden() is True
        assert win._info_values["fits_detector"].isHidden() is True
    finally:
        win.close()


@pytest.mark.parametrize(
    ("raw_val", "expected_text"),
    [
        (20.0, "20 s"),
        (1.7021129, "1.7 s"),
        (0.09178114256, "91.78 ms"),
        (0.020, "20 ms"),
        (0.0005, "500 µs"),
        (None, "Tidak tersedia"),
        (float("nan"), "Tidak tersedia"),
        (float("inf"), "Tidak tersedia"),
        (float("-inf"), "Tidak tersedia"),
        (-0.05, "Tidak tersedia"),
        (-10, "Tidak tersedia"),
        (0.0, "Tidak tersedia"),
    ],
)
def test_exposure_time_formatter_cases(raw_val: object, expected_text: str) -> None:
    """Menguji helper format_exposure_time pada seluruh kasus s, ms, µs, dan nilai tidak valid."""
    from hilalone.gui.main_window import format_exposure_time

    assert format_exposure_time(raw_val) == expected_text


def test_exposure_time_formatting_preserves_source_fits_header_precision(
    qapp,  # noqa: ANN001
    tmp_path: Path,
) -> None:
    """Memastikan pemformatan EXPTIME di GUI tidak mengubah nilai asli pada FitsHeaderInfo maupun file FITS."""
    from hilalone.gui.main_window import MainWindow

    orig_exptime = 0.09178114256022202
    data = np.ones((6, 8), dtype=np.uint16)
    hdu = fits.PrimaryHDU(data=data)
    hdu.header["EXPTIME"] = orig_exptime
    fits_path = tmp_path / "precision_check.fits"
    hdu.writeto(fits_path)
    before_hash = _sha256(fits_path)

    win = MainWindow()
    try:
        assert win.load_path(fits_path) is True
        assert win._info_values["fits_exptime"].text() == "91.78 ms"

        # Nilai di dalam model data ilmiah tetap float berpresisi penuh
        entry = win.sequence_manager.entries[0]
        assert entry.info is not None
        assert entry.info.fits_header is not None
        assert entry.info.fits_header.exptime == orig_exptime

        # Berkas FITS asli tidak berubah
        assert _sha256(fits_path) == before_hash
    finally:
        win.close()
