"""Tes pembaca gambar (input_manager.image_reader) dengan gambar sintetis."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PySide6.QtGui import QImage

from hilalone.input_manager import image_reader
from hilalone.input_manager.image_reader import ImageReadError, read_image, supported_extensions

F = QImage.Format


def _make_image(path: Path, fmt: QImage.Format, width: int = 8, height: int = 4) -> Path:
    """Membuat gambar sintetis di folder sementara pytest (bukan di proyek)."""
    image = QImage(width, height, fmt)
    image.fill(0)
    assert image.save(str(path)), f"Gagal membuat gambar uji {path.name}"
    return path


def _make_exif_rotated_jpeg(path: Path) -> Path:
    """Membuat JPEG 8x4 dengan tag EXIF orientation = 6 (putar 90°)."""
    _make_image(path, F.Format_RGB32)
    raw = path.read_bytes()
    exif = (
        b"Exif\x00\x00" + b"MM\x00\x2a\x00\x00\x00\x08" + b"\x00\x01"
        + b"\x01\x12\x00\x03\x00\x00\x00\x01\x00\x06\x00\x00" + b"\x00\x00\x00\x00"
    )
    segment = b"\xff\xe1" + (len(exif) + 2).to_bytes(2, "big") + exif
    path.write_bytes(raw[:2] + segment + raw[2:])
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001 - memastikan Qt siap sebelum membuat QImage
    return qapp


# ----------------------------------------------------------- format dasar
def test_supported_extensions_contains_target_formats() -> None:
    exts = supported_extensions()
    for expected in ("png", "jpg", "jpeg", "bmp"):
        assert expected in exts


@pytest.mark.parametrize("name", ["a.png", "a.bmp", "a.jpg"])
def test_read_rgb_formats_keep_rgb(tmp_path: Path, name: str) -> None:
    loaded = read_image(_make_image(tmp_path / name, F.Format_RGB32))
    info = loaded.info
    assert (info.width, info.height) == (8, 4)
    assert info.channels == 3
    assert info.original_bit_depth == 8
    assert info.file_name == name
    assert loaded.preview.format() == F.Format_RGB888  # tetap warna


def test_mono_stays_mono(tmp_path: Path) -> None:
    loaded = read_image(_make_image(tmp_path / "gray.png", F.Format_Grayscale8))
    assert loaded.info.channels == 1
    assert loaded.preview.format() == F.Format_Grayscale8  # tidak jadi RGB


def test_16bit_original_reported_honestly_and_preview_is_8bit(tmp_path: Path) -> None:
    loaded = read_image(_make_image(tmp_path / "g16.png", F.Format_Grayscale16))
    assert loaded.info.original_bit_depth == 16
    assert loaded.info.preview_bit_depth == 8
    assert loaded.info.channels == 1
    assert loaded.preview.format() == F.Format_Grayscale8


def test_rgba_16bit_reports_four_channels(tmp_path: Path) -> None:
    loaded = read_image(_make_image(tmp_path / "rgba.png", F.Format_RGBA64))
    assert loaded.info.channels == 4
    assert loaded.info.has_alpha is True
    assert loaded.info.original_bit_depth == 16


# --------------------------------------------------------- orientasi EXIF
def test_exif_rotation_only_on_preview_and_original_recorded(tmp_path: Path) -> None:
    path = _make_exif_rotated_jpeg(tmp_path / "exif.jpg")
    loaded = read_image(path)
    info = loaded.info
    # Preview diputar 90°: 8x4 menjadi 4x8.
    assert (loaded.preview.width(), loaded.preview.height()) == (4, 8)
    assert (info.width, info.height) == (4, 8)
    # Ukuran tersimpan dan orientasi ASLI dicatat.
    assert (info.stored_width, info.stored_height) == (8, 4)
    assert info.orientation_applied is True
    assert "90" in info.exif_orientation


def test_no_exif_means_no_rotation(tmp_path: Path) -> None:
    info = read_image(_make_image(tmp_path / "plain.png", F.Format_RGB32)).info
    assert info.orientation_applied is False
    assert (info.stored_width, info.stored_height) == (info.width, info.height)


# ------------------------------------------------------------------ TIFF
def test_tiff_read_when_plugin_available(tmp_path: Path) -> None:
    if "tif" not in supported_extensions():
        pytest.skip("Plugin TIFF Qt tidak tersedia di mesin ini.")
    loaded = read_image(_make_image(tmp_path / "t.tif", F.Format_Grayscale16))
    assert loaded.info.original_bit_depth == 16
    assert loaded.info.channels == 1


def test_tiff_gives_clear_error_when_plugin_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "t.tif"
    path.write_bytes(b"II*\x00")
    monkeypatch.setattr(image_reader, "supported_extensions", lambda: ("png", "jpg", "jpeg", "bmp"))
    with pytest.raises(ImageReadError, match="TIFF"):
        read_image(path)


# ------------------------------------------------------------------ galat
def test_missing_file_raises_indonesian_error(tmp_path: Path) -> None:
    with pytest.raises(ImageReadError, match="File tidak ditemukan"):
        read_image(tmp_path / "tidak_ada.png")


def test_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ImageReadError, match="bukan sebuah file"):
        read_image(tmp_path)


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "catatan.txt"
    path.write_text("bukan gambar")
    with pytest.raises(ImageReadError, match="belum didukung"):
        read_image(path)


def test_corrupt_png_is_rejected_without_crash(tmp_path: Path) -> None:
    path = tmp_path / "rusak.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\nxxxxxxxx")
    with pytest.raises(ImageReadError):
        read_image(path)


def test_fake_image_with_image_extension_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "palsu.jpg"
    path.write_text("ini teks biasa, bukan JPEG")
    with pytest.raises(ImageReadError, match="tidak dapat dibaca"):
        read_image(path)


# ----------------------------------------------- berkas sumber tidak berubah
@pytest.mark.parametrize("name", ["s.png", "s.jpg", "s.bmp"])
def test_source_file_is_never_modified(tmp_path: Path, name: str) -> None:
    path = _make_image(tmp_path / name, F.Format_RGB32)
    hash_before = _sha256(path)
    stat_before = path.stat()

    read_image(path)

    assert _sha256(path) == hash_before
    assert path.stat().st_mtime_ns == stat_before.st_mtime_ns
    assert path.stat().st_size == stat_before.st_size
    assert path.exists()
