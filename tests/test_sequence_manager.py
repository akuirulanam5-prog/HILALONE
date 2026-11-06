"""Pengujian unit Sub-Tahap 2A: Unified Input Data Model, Multiple Image Import, & Sequence Manager."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import tifffile
from astropy.io import fits
from PySide6.QtGui import QImage

from hilalone.gui.main_window import MainWindow
from hilalone.input_manager import image_reader, sequence_manager
from hilalone.input_manager.models import (
    FrameStatus,
    InputMode,
    to_controlled_float32,
)
from hilalone.input_manager.sequence_manager import (
    SORT_NATURAL_LABEL,
    SORT_TIMESTAMP_FALLBACK_LABEL,
    SORT_TIMESTAMP_LABEL,
    SequenceManager,
)


@pytest.fixture(autouse=True)
def _qt_app(qapp):  # noqa: ANN001
    return qapp


def _make_png(path: Path, width: int = 24, height: int = 16, fmt=QImage.Format.Format_RGB32) -> Path:
    img = QImage(width, height, fmt)
    img.fill(0)
    assert img.save(str(path))
    return path


def _make_fits(
    path: Path,
    width: int = 24,
    height: int = 16,
    dtype=np.uint16,
    date_obs: str | None = None,
) -> Path:
    arr = np.ones((height, width), dtype=dtype) * 100
    hdu = fits.PrimaryHDU(data=arr)
    if date_obs is not None:
        hdu.header["DATE-OBS"] = date_obs
    hdu.writeto(path)
    return path


# -------------------------------------------- 1. Unified Input Data Model
def test_unified_model_populates_scientific_data_for_png_tiff_fits(tmp_path: Path) -> None:
    p_png = _make_png(tmp_path / "u.png", 20, 10, QImage.Format.Format_Grayscale8)
    p_tif = tmp_path / "u.tif"
    tifffile.imwrite(p_tif, np.full((10, 20), 1234, dtype=np.uint16))
    p_fit = _make_fits(tmp_path / "u.fits", 20, 10, dtype=np.float32)

    for p, expected_dtype in [(p_png, np.uint8), (p_tif, np.uint16), (p_fit, np.float32)]:
        loaded = image_reader.read_image(p)
        assert loaded.scientific_data is not None
        assert loaded.scientific_data.dtype == expected_dtype
        assert loaded.scientific_data.shape == (10, 20)
        assert loaded.scientific_data.flags.writeable is False
        assert loaded.info.dtype_str == np.dtype(expected_dtype).name
        assert not loaded.preview.isNull()


# -------------------------------------------- 2. Single vs Multiple & stacking_required
def test_single_image_sets_stacking_required_false(tmp_path: Path) -> None:
    mgr = SequenceManager()
    assert mgr.input_mode == InputMode.EMPTY
    assert mgr.stacking_required is False

    p = _make_png(tmp_path / "single.png", 32, 24)
    mgr.open_single_file(p)

    assert mgr.input_mode == InputMode.SINGLE
    assert mgr.stacking_required is False
    assert mgr.frame_count == 1
    assert mgr.compatibility_report.is_ready_for_stacking is False


def test_multiple_images_sets_stacking_required_true(tmp_path: Path) -> None:
    p1 = _make_png(tmp_path / "f1.png", 32, 24)
    p2 = _make_png(tmp_path / "f2.png", 32, 24)
    p3 = _make_png(tmp_path / "f3.png", 32, 24)

    mgr = SequenceManager()
    report = mgr.open_files([p1, p2, p3])

    assert mgr.input_mode == InputMode.MULTI
    assert mgr.stacking_required is True
    assert mgr.frame_count == 3
    assert report.is_ready_for_stacking is True
    assert report.compatible_count == 3
    assert report.incompatible_count == 0
    assert report.error_count == 0


# -------------------------------------------- 3. Folder Sequence & Natural Sorting
def test_folder_sequence_and_natural_filename_sorting(tmp_path: Path) -> None:
    # Urutan leksikografis biasa akan menempatkan img_10 sebelum img_2;
    # natural sorting WAJIB menghasilkan img_1, img_2, img_10.
    for name in ("img_10.png", "img_2.png", "img_1.png"):
        _make_png(tmp_path / name, 20, 15)
    # File non-gambar di dalam folder harus diabaikan oleh pencarian folder
    (tmp_path / "catatan.txt").write_text("abaikan")

    mgr = SequenceManager()
    mgr.open_folder(tmp_path)

    assert mgr.sorting_method == SORT_NATURAL_LABEL
    names = [e.file_name for e in mgr.entries]
    assert names == ["img_1.png", "img_2.png", "img_10.png"]
    assert [e.frame_index for e in mgr.entries] == [0, 1, 2]


def test_timestamp_sorting_when_valid_and_fallback_when_incomplete(tmp_path: Path) -> None:
    f_late = _make_fits(tmp_path / "a_frame.fits", date_obs="2026-11-05T18:10:00")
    f_early = _make_fits(tmp_path / "b_frame.fits", date_obs="2026-11-05T18:01:00")

    mgr = SequenceManager()
    mgr.open_files([f_late, f_early], sort_by="timestamp")
    assert mgr.sorting_method == SORT_TIMESTAMP_LABEL
    assert [e.file_name for e in mgr.entries] == ["b_frame.fits", "a_frame.fits"]

    # Jika ada frame tanpa DATE-OBS, kembali ke natural sorting dan beri tahu pengguna
    f_no_ts = _make_fits(tmp_path / "c_frame.fits", date_obs=None)
    mgr.open_files([f_late, f_early, f_no_ts], sort_by="timestamp")
    assert mgr.sorting_method == SORT_TIMESTAMP_FALLBACK_LABEL
    assert [e.file_name for e in mgr.entries] == ["a_frame.fits", "b_frame.fits", "c_frame.fits"]


# -------------------------------------------- 4. Validasi Dimensi, Kanal, & Bit Depth
def test_different_dimensions_marked_incompatible_but_still_previewable(tmp_path: Path) -> None:
    p1 = _make_png(tmp_path / "01_ref.png", 40, 30)
    p2 = _make_png(tmp_path / "02_diff_dim.png", 60, 50)

    mgr = SequenceManager()
    report = mgr.open_files([p1, p2])

    assert mgr.frame_count == 2  # tidak ada yang dibuang diam-diam
    assert report.is_ready_for_stacking is False
    assert report.compatible_count == 1
    assert report.incompatible_count == 1
    assert mgr.entries[0].status == FrameStatus.COMPATIBLE
    assert mgr.entries[1].status == FrameStatus.INCOMPATIBLE
    assert any("Dimensi" in w for w in report.warnings)

    # Frame INCOMPATIBLE tetap harus dapat dibuka dan dipratinjau secara individual
    assert mgr.entries[1].can_preview() is True
    loaded_diff = mgr.load_frame(1)
    assert (loaded_diff.info.width, loaded_diff.info.height) == (60, 50)
    assert not loaded_diff.preview.isNull()


def test_different_channels_mono_vs_rgb_marked_incompatible_and_previewable(tmp_path: Path) -> None:
    p_mono = _make_png(tmp_path / "01_mono.png", 30, 20, QImage.Format.Format_Grayscale8)
    p_rgb = _make_png(tmp_path / "02_rgb.png", 30, 20, QImage.Format.Format_RGB32)

    mgr = SequenceManager()
    report = mgr.open_files([p_mono, p_rgb])

    assert report.is_ready_for_stacking is False
    assert mgr.entries[1].status == FrameStatus.INCOMPATIBLE
    assert any("kanal" in w.lower() for w in report.warnings)

    # Tetap bisa dipratinjau individual
    loaded_rgb = mgr.load_frame(1)
    assert loaded_rgb.info.channels == 3


def test_different_bit_depth_remains_compatible_with_controlled_float32_conversion(
    tmp_path: Path,
) -> None:
    """Perbedaan bit depth tidak otomatis menyebabkan INCOMPATIBLE."""
    p_u8 = tmp_path / "01_u8.tif"
    p_u16 = tmp_path / "02_u16.tif"
    arr_u8 = np.full((12, 16), 255, dtype=np.uint8)
    arr_u16 = np.full((12, 16), 65535, dtype=np.uint16)
    tifffile.imwrite(p_u8, arr_u8)
    tifffile.imwrite(p_u16, arr_u16)

    mgr = SequenceManager()
    report = mgr.open_files([p_u8, p_u16])

    assert report.is_ready_for_stacking is True
    assert report.mixed_bit_depth is True
    assert mgr.entries[0].status == FrameStatus.COMPATIBLE
    assert mgr.entries[1].status == FrameStatus.COMPATIBLE
    assert len(mgr.entries[1].notes) == 1

    # Konversi terkontrol ke float32 untuk kebutuhan stacking tanpa mengubah data ilmiah asli
    loaded0 = mgr.load_frame(0)
    loaded1 = mgr.load_frame(1)
    assert loaded0.scientific_data is not None and loaded0.scientific_data.dtype == np.uint8
    assert loaded1.scientific_data is not None and loaded1.scientific_data.dtype == np.uint16

    f0 = to_controlled_float32(loaded0.scientific_data)
    f1 = to_controlled_float32(loaded1.scientific_data)
    assert f0.dtype == np.float32 and f1.dtype == np.float32
    assert np.allclose(f0, 1.0) and np.allclose(f1, 1.0)
    # Pastikan scientific_data asli tetap utuh
    assert loaded0.scientific_data.dtype == np.uint8
    assert loaded1.scientific_data.dtype == np.uint16


# -------------------------------------------- 5. File Rusak (ERROR) Tidak Dibuang
def test_corrupt_file_recorded_as_error_without_dropping_or_reordering(tmp_path: Path) -> None:
    p1 = _make_png(tmp_path / "01_ok.png", 24, 16)
    p2_bad = tmp_path / "02_rusak.png"
    p2_bad.write_bytes(b"bukan png valid")
    p3 = _make_png(tmp_path / "03_ok.png", 24, 16)

    mgr = SequenceManager()
    report = mgr.open_files([p1, p2_bad, p3])

    assert mgr.frame_count == 3
    assert [e.file_name for e in mgr.entries] == ["01_ok.png", "02_rusak.png", "03_ok.png"]
    assert mgr.entries[0].status == FrameStatus.COMPATIBLE
    assert mgr.entries[1].status == FrameStatus.ERROR
    assert mgr.entries[2].status == FrameStatus.COMPATIBLE
    assert report.error_count == 1
    assert report.is_ready_for_stacking is False

    # Frame valid setelah frame rusak tetap dapat dibuka
    loaded3 = mgr.load_frame(2)
    assert loaded3.info.file_name == "03_ok.png"


# -------------------------------------------- 6. Lazy Loading
def test_lazy_loading_does_not_read_pixel_arrays_when_opening_sequence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = [_make_png(tmp_path / f"f_{i}.png", 20, 20) for i in range(5)]

    read_calls: list[Path] = []
    orig_read = sequence_manager.read_image

    def _tracked_read(path, *args, **kwargs):  # noqa: ANN001
        read_calls.append(Path(path))
        return orig_read(path, *args, **kwargs)

    monkeypatch.setattr(sequence_manager, "read_image", _tracked_read)

    mgr = SequenceManager()
    mgr.open_files(paths)

    # Saat open_files selesai, TIDAK BOLEH ada satu pun pembacaan piksel penuh yang dipanggil!
    assert len(read_calls) == 0
    assert all(e.is_pixel_loaded is False for e in mgr.entries)

    # Saat hanya frame ke-2 diminta, hanya 1 berkas yang dibaca pikselnya
    mgr.load_frame(2)
    assert len(read_calls) == 1
    assert read_calls[0].name == "f_2.png"
    assert mgr.entries[2].is_pixel_loaded is True
    assert mgr.entries[0].is_pixel_loaded is False


# -------------------------------------------- 7. Integrasi GUI Sequence
def test_gui_multiple_images_navigation_and_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win = MainWindow()
    warnings_shown: list[str] = []
    monkeypatch.setattr(win, "_show_warning", warnings_shown.append)

    p1 = _make_png(tmp_path / "img_1.png", 40, 30)
    p2 = _make_png(tmp_path / "img_2.png", 50, 30)  # beda lebar -> INCOMPATIBLE

    assert win.load_sequence_paths([p2, p1]) is True
    assert len(warnings_shown) == 1
    assert win.sequence_manager.stacking_required is True
    assert win.frame_combo.count() == 2

    # Navigasi ke frame berikutnya (yang INCOMPATIBLE) tetap menampilkan pratinjau
    win.show_next_frame()
    assert win.sequence_manager.current_index == 1
    assert win.viewer.has_image() is True
    assert win._info_values["file_name"].text() == "img_2.png"
    win.close()
