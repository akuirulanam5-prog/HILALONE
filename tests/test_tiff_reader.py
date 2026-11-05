"""Pengujian unit untuk TIFF Reader ilmiah (hilalone.input_manager.adapters.tiff_reader)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PySide6.QtGui import QImage

from hilalone.input_manager.adapters.tiff_reader import inspect_tiff_pages, read_tiff
from hilalone.input_manager.image_reader import (
    ImageReadError,
    MultiPageTiffError,
    read_image,
)


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001
    return qapp


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------- 1. Grayscale uint8
def test_tiff_grayscale_uint8_exact_preservation(tmp_path: Path) -> None:
    source = np.arange(0, 240, dtype=np.uint8).reshape(12, 20)
    path = tmp_path / "gray_u8.tif"
    tifffile.imwrite(path, source)

    loaded = read_image(path)
    assert loaded.scientific_data is not None
    assert loaded.scientific_data.dtype == np.uint8
    assert loaded.scientific_data.shape == (12, 20)
    assert np.array_equal(loaded.scientific_data, source)

    assert loaded.info.channels == 1
    assert loaded.info.original_bit_depth == 8
    assert loaded.info.original_is_float is False
    assert loaded.info.preview_bit_depth == 8
    assert loaded.preview.format() == QImage.Format.Format_Grayscale8
    assert (loaded.preview.width(), loaded.preview.height()) == (20, 12)


# --------------------------------------------------- 2. Grayscale uint16
def test_tiff_grayscale_uint16_exact_preservation(tmp_path: Path) -> None:
    source = np.linspace(0, 65535, num=16 * 24, dtype=np.uint16).reshape(16, 24)
    source[0, 0] = 12345
    source[-1, -1] = 65535
    path = tmp_path / "gray_u16.tif"
    tifffile.imwrite(path, source)

    loaded = read_image(path)
    assert loaded.scientific_data is not None
    assert loaded.scientific_data.dtype == np.uint16
    assert loaded.scientific_data.shape == (16, 24)
    assert np.array_equal(loaded.scientific_data, source)
    assert int(loaded.scientific_data[0, 0]) == 12345
    assert int(loaded.scientific_data[-1, -1]) == 65535

    # Preview terpisah 8-bit, data ilmiah tetap 16-bit
    assert loaded.info.original_bit_depth == 16
    assert loaded.info.preview_bit_depth == 8
    assert loaded.info.dtype_str == "uint16"
    assert loaded.preview.format() == QImage.Format.Format_Grayscale8
    assert loaded.scientific_data.dtype == np.uint16


# --------------------------------------------------- 3. RGB uint16
def test_tiff_rgb_uint16_exact_preservation(tmp_path: Path) -> None:
    r = np.full((10, 14), 1000, dtype=np.uint16)
    g = np.full((10, 14), 30000, dtype=np.uint16)
    b = np.full((10, 14), 65000, dtype=np.uint16)
    source = np.stack([r, g, b], axis=-1)
    path = tmp_path / "rgb_u16.tif"
    tifffile.imwrite(path, source, photometric="rgb")

    loaded = read_image(path)
    assert loaded.scientific_data is not None
    assert loaded.scientific_data.dtype == np.uint16
    assert loaded.scientific_data.shape == (10, 14, 3)
    assert np.array_equal(loaded.scientific_data, source)

    assert loaded.info.channels == 3
    assert loaded.info.original_bit_depth == 16
    assert loaded.info.preview_bit_depth == 8
    assert loaded.preview.format() == QImage.Format.Format_RGB888


# --------------------------------------------------- 4. Float32, Float64, Uint32
def test_tiff_float32_exact_preservation(tmp_path: Path) -> None:
    source = np.linspace(-2.5, 42.75, num=10 * 15, dtype=np.float32).reshape(10, 15)
    path = tmp_path / "float32.tif"
    tifffile.imwrite(path, source)

    loaded = read_image(path)
    assert loaded.scientific_data is not None
    assert loaded.scientific_data.dtype == np.float32
    assert loaded.scientific_data.shape == (10, 15)
    assert np.array_equal(loaded.scientific_data, source)
    assert loaded.info.original_bit_depth == 32
    assert loaded.info.original_is_float is True
    assert loaded.info.dtype_str == "float32"
    assert loaded.preview.format() == QImage.Format.Format_Grayscale8


@pytest.mark.parametrize("dtype", [np.uint32, np.float64])
def test_tiff_uint32_and_float64_preserved(tmp_path: Path, dtype: np.dtype) -> None:
    source = np.arange(0, 48, dtype=dtype).reshape(6, 8)
    path = tmp_path / f"test_{np.dtype(dtype).name}.tif"
    tifffile.imwrite(path, source)

    loaded = read_image(path)
    assert loaded.scientific_data is not None
    assert loaded.scientific_data.dtype == dtype
    assert loaded.scientific_data.shape == (6, 8)
    assert np.array_equal(loaded.scientific_data, source)


# --------------------------------------------------- 5. Multi-page TIFF
def test_multipage_tiff_does_not_silently_take_first_page(tmp_path: Path) -> None:
    page0 = np.full((8, 10), 1111, dtype=np.uint16)
    page1 = np.full((8, 10), 55555, dtype=np.uint16)
    path = tmp_path / "multipage.tif"
    with tifffile.TiffWriter(path) as writer:
        writer.write(page0)
        writer.write(page1)

    pages = inspect_tiff_pages(path)
    assert len(pages) == 2
    assert pages[0].index == 0 and pages[1].index == 1

    # Memanggil read_image tanpa page_index WAJIB menolak diam-diam mengambil halaman pertama
    with pytest.raises(MultiPageTiffError) as exc_info:
        read_image(path)
    assert len(exc_info.value.pages) == 2
    assert "2 halaman" in str(exc_info.value)

    # Membaca halaman 0 dan halaman 1 secara eksplisit
    loaded0 = read_image(path, page_index=0)
    loaded1 = read_image(path, page_index=1)

    assert loaded0.scientific_data is not None
    assert loaded1.scientific_data is not None
    assert np.array_equal(loaded0.scientific_data, page0)
    assert np.array_equal(loaded1.scientific_data, page1)
    assert loaded0.info.page_index == 0 and loaded0.info.page_count == 2
    assert loaded1.info.page_index == 1 and loaded1.info.page_count == 2
    assert "Halaman 1/2" in loaded0.info.file_format
    assert "Halaman 2/2" in loaded1.info.file_format


def test_multipage_invalid_page_index_raises_clear_error(tmp_path: Path) -> None:
    path = tmp_path / "single.tif"
    tifffile.imwrite(path, np.zeros((4, 4), dtype=np.uint8))
    with pytest.raises(ImageReadError, match="Indeks halaman TIFF tidak valid"):
        read_image(path, page_index=3)


# --------------------------------------------------- 6. Kompresi & imagecodecs
def test_missing_imagecodecs_gives_specific_indonesian_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "comp.tif"
    tifffile.imwrite(path, np.zeros((6, 6), dtype=np.uint16))

    def _raise_codec_error(self):  # noqa: ANN001
        raise ValueError("reading LZW compressed data requires the 'imagecodecs' package")

    monkeypatch.setattr(tifffile.TiffPage, "asarray", _raise_codec_error)
    with pytest.raises(ImageReadError) as exc_info:
        read_tiff(path)

    msg = str(exc_info.value)
    assert "imagecodecs" in msg
    assert "kompresi" in msg.lower()


# --------------------------------------------------- 7. Keamanan Berkas Asli
def test_tiff_source_file_never_modified(tmp_path: Path) -> None:
    source = np.arange(100, dtype=np.uint16).reshape(10, 10)
    path = tmp_path / "readonly.tif"
    tifffile.imwrite(path, source)

    hash_before = _sha256(path)
    stat_before = path.stat()

    loaded = read_image(path)
    assert loaded.scientific_data is not None
    # Array ilmiah dikunci (read-only di memori)
    assert loaded.scientific_data.flags.writeable is False

    assert _sha256(path) == hash_before
    assert path.stat().st_mtime_ns == stat_before.st_mtime_ns
    assert path.stat().st_size == stat_before.st_size


def test_real_tes_tif_if_present() -> None:
    """Bila C:\\Astrofotografer\\tes.tif ada, uji baca read-only dan verifikasi SHA-256."""
    real_path = Path(r"C:\Astrofotografer\tes.tif")
    if not real_path.exists():
        pytest.skip("Berkas tes.tif tidak tersedia di mesin ini.")

    hash_before = _sha256(real_path)
    loaded = read_image(real_path)

    assert loaded.scientific_data is not None
    assert loaded.scientific_data.dtype == np.float32
    assert loaded.scientific_data.shape == (3672, 5496)
    assert loaded.info.channels == 1
    assert loaded.info.original_bit_depth == 32
    assert loaded.info.original_is_float is True
    assert not loaded.preview.isNull()
    assert (loaded.preview.width(), loaded.preview.height()) == (5496, 3672)

    hash_after = _sha256(real_path)
    assert hash_after == hash_before
