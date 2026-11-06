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
