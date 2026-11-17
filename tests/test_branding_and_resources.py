"""Tes unit untuk resource branding, ikon aplikasi, dan logo header HILALONE."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from hilalone.gui.image_viewer import PLACEHOLDER_TEXT, SECONDARY_PLACEHOLDER_TEXT
from hilalone.gui.main_window import MainWindow
from hilalone.gui.resources import (
    clear_resource_cache,
    get_app_icon,
    get_app_icon_path,
    get_compact_logo_path,
    get_compact_logo_pixmap,
    get_header_logo_path,
    get_header_logo_pixmap,
    get_logo_path,
    get_logo_pixmap,
    get_project_root,
    get_resource_path,
)
from hilalone.main import _setup_windows_app_id


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Fixture sesi untuk QApplication instance."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_resource_paths_exist() -> None:
    """Memastikan berkas aset resmi branding tersedia di path yang ditentukan."""
    icon_path = get_app_icon_path()
    assert icon_path.exists(), f"Berkas ikon tidak ditemukan di: {icon_path}"
    assert icon_path.name == "hilalone_app_icon.ico"
    assert icon_path.stat().st_size > 0

    night_icon_path = get_app_icon_path(night_vision=True)
    assert night_icon_path.exists(), f"Berkas ikon Night Vision tidak ditemukan di: {night_icon_path}"
    assert night_icon_path.name == "hilalone_app_icon_night_red.ico"
    assert night_icon_path.stat().st_size > 0

    header_logo_path = get_header_logo_path()
    assert header_logo_path.exists(), f"Berkas ikon header tidak ditemukan di: {header_logo_path}"
    assert header_logo_path.name == "hilalone_icon_standard.png"
    assert header_logo_path.stat().st_size > 0

    compact_nv_path = get_compact_logo_path(night_vision=True)
    assert compact_nv_path.exists(), f"Berkas ikon Night Vision tidak ditemukan di: {compact_nv_path}"
    assert compact_nv_path.name == "hilalone_icon_night_red.png"
    assert compact_nv_path.stat().st_size > 0

    full_logo_path = get_logo_path()
    assert full_logo_path.exists(), f"Berkas logo lengkap tidak ditemukan di: {full_logo_path}"
    assert full_logo_path.name == "hilalone_logo_standard.png"
    assert full_logo_path.stat().st_size > 0

    night_logo_path = get_logo_path(night_vision=True)
    assert night_logo_path.exists(), f"Berkas logo Night Vision tidak ditemukan di: {night_logo_path}"
    assert night_logo_path.name in {"hilalone_logo_night_red_separate.png", "hilalone_logo_night_red.png"}
    assert night_logo_path.stat().st_size > 0


def test_branding_png_transparency() -> None:
    """Memastikan seluruh aset PNG branding memiliki kanal alfa dan sudut luar transparan."""
    for path_getter in (get_logo_path, get_compact_logo_path):
        for nv in (False, True):
            path = path_getter(night_vision=nv)
            img = Image.open(path)
            assert img.mode == "RGBA"
            w, h = img.size
            assert w == h
            assert img.getpixel((0, 0))[3] == 0
            assert img.getpixel((w - 1, 0))[3] == 0


def test_resource_path_helper_resolutions() -> None:
    """Memastikan fungsi get_resource_path menangani path absolut dan relatif."""
    root = get_project_root()
    assert root.exists()

    # Path relatif
    resolved_rel = get_resource_path("assets/branding/hilalone_app_icon.ico")
    assert resolved_rel.exists()

    # Path absolut
    abs_path = resolved_rel.resolve()
    assert get_resource_path(abs_path) == abs_path


def test_get_app_icon(qapp: QApplication) -> None:
    """Memastikan get_app_icon memuat QIcon yang valid dan menggunakan cache."""
    clear_resource_cache()
    icon = get_app_icon()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()
    available_sizes = icon.availableSizes()
    assert len(available_sizes) > 0
    assert get_app_icon() is icon


def test_get_header_and_raw_logo_pixmap(qapp: QApplication) -> None:
    """Memastikan get_logo_pixmap dan get_header_logo_pixmap menjaga rasio serta caching."""
    clear_resource_cache()
    raw_std = get_logo_pixmap(night_vision=False)
    raw_nv = get_logo_pixmap(night_vision=True)
    compact_std = get_compact_logo_pixmap(night_vision=False)
    compact_nv = get_compact_logo_pixmap(night_vision=True)
    assert not raw_std.isNull()
    assert not raw_nv.isNull()
    assert not compact_std.isNull()
    assert not compact_nv.isNull()
    assert raw_std.width() == raw_std.height()
    assert raw_nv.width() == raw_nv.height()
    assert compact_std.width() == compact_std.height()
    assert compact_nv.width() == compact_nv.height()
    assert get_logo_pixmap(night_vision=False) is raw_std
    assert get_compact_logo_pixmap(night_vision=False) is compact_std

    target_h = 44
    pixmap = get_header_logo_pixmap(target_height=target_h)
    assert isinstance(pixmap, QPixmap)
    assert not pixmap.isNull()
    assert pixmap.height() == target_h
    assert pixmap.width() == target_h

    # Pastikan diameter isi visual antara Standard Dark dan Night Vision Red identik setelah normalisasi
    def _visual_content_width(pix: QPixmap) -> int:
        img = pix.toImage().convertToFormat(pix.toImage().Format.Format_RGBA8888)
        bpl = img.bytesPerLine()
        arr = np.frombuffer(img.constBits(), dtype=np.uint8).reshape((img.height(), bpl))
        alpha = arr[:, : img.width() * 4].reshape((img.height(), img.width(), 4))[:, :, 3]
        _, xs = np.where(alpha > 10)
        return int(xs.max() - xs.min() + 1)

    std_scaled = raw_std.scaled(240, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    nv_scaled = raw_nv.scaled(240, 240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    assert abs(_visual_content_width(std_scaled) - _visual_content_width(nv_scaled)) <= 2

    compact_std_scaled = compact_std.scaled(84, 84, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    compact_nv_scaled = compact_nv.scaled(84, 84, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
    assert abs(_visual_content_width(compact_std_scaled) - _visual_content_width(compact_nv_scaled)) <= 2


def test_missing_asset_fallback_logs_warning(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """Memastikan aplikasi tidak crash bila file aset hilang dan mencatat warning ke log."""
    clear_resource_cache()
    missing = tmp_path / "tidak_ada.png"
    monkeypatch.setattr("hilalone.gui.resources.get_logo_path", lambda night_vision=False: missing)
    with caplog.at_level(logging.WARNING):
        pix = get_logo_pixmap(night_vision=False)
    assert pix.isNull()
    assert any("tidak ditemukan" in rec.message.lower() for rec in caplog.records)
    clear_resource_cache()


def test_empty_state_lifecycle_and_theme_switching(
    qapp: QApplication,
    tmp_path: Path,
) -> None:
    """Memastikan Empty State bergaya Siril mengikuti state viewer dan tema Night Vision Red."""
    win = MainWindow()
    try:
        win.resize(1366, 768)
        win.show()
        qapp.processEvents()

        viewer = win.viewer
        assert not viewer.has_image()
        assert viewer._empty_state_widget.isVisible()
        assert viewer._empty_primary_label.text() == PLACEHOLDER_TEXT
        assert viewer._empty_secondary_label.text() == SECONDARY_PLACEHOLDER_TEXT
        assert not viewer._empty_logo_label.pixmap().isNull()

        # Pastikan warna Standard Dark memakai biru muda/cyan redup & Night Vision Red memakai merah redup
        assert "#7dd3fc" in viewer._empty_primary_label.styleSheet().lower()
        win.toggle_night_vision_theme(True)
        qapp.processEvents()
        assert viewer._empty_state_widget.isVisible()
        assert "#c84b4b" in viewer._empty_primary_label.styleSheet().lower()
        assert not viewer._empty_logo_label.pixmap().isNull()

        # Kembalikan ke Standard Dark lalu buka gambar sintetis
        win.toggle_night_vision_theme(False)
        qapp.processEvents()
        sample_path = tmp_path / "hilal_test.png"
        arr = np.full((64, 96, 3), 80, dtype=np.uint8)
        Image.fromarray(arr).save(sample_path)

        win.load_path(sample_path)
        qapp.processEvents()
        assert viewer.has_image()
        assert not viewer._empty_state_widget.isVisible()

        # Mengganti tema saat gambar terbuka tidak memunculkan empty state & tidak menghapus gambar
        win.toggle_night_vision_theme(True)
        qapp.processEvents()
        assert viewer.has_image()
        assert not viewer._empty_state_widget.isVisible()

        # Membuka berkas gagal tidak merusak atau menutup state Empty setelah close
        win.close_image()
        qapp.processEvents()
        assert not viewer.has_image()
        assert viewer._empty_state_widget.isVisible()

        bad_path = tmp_path / "rusak.png"
        bad_path.write_bytes(b"bukan-png")
        errors: list[str] = []
        win._show_error = lambda msg: errors.append(msg)  # hindari dialog modal offscreen
        win.load_path(bad_path)
        qapp.processEvents()
        assert len(errors) == 1
        assert not viewer.has_image()
        assert viewer._empty_state_widget.isVisible()
    finally:
        win.close()


@pytest.mark.parametrize("resolution", [(1366, 768), (1600, 900), (1920, 1080)])
def test_empty_state_responsive_centering(
    qapp: QApplication,
    resolution: tuple[int, int],
) -> None:
    """Memastikan Empty State selalu proporsional dan tepat berada di tengah viewport."""
    win = MainWindow()
    try:
        win.resize(*resolution)
        win.show()
        qapp.processEvents()

        viewer = win.viewer
        empty = viewer._empty_state_widget
        logo = viewer._empty_logo_label
        assert empty.isVisible()
        min_expected = 140 if viewer.height() < 420 else 220
        assert min_expected <= logo.pixmap().width() <= 260
        assert empty.width() <= viewer.width()
        assert empty.height() <= viewer.height()

        # Pastikan ukuran logo di mode Night Vision Red persis sama dengan Standard Dark pada viewport sama
        std_size = logo.pixmap().size()
        win.toggle_night_vision_theme(True)
        qapp.processEvents()
        assert logo.pixmap().size() == std_size

        viewer_center_x = viewer.width() / 2.0
        viewer_center_y = viewer.height() / 2.0
        empty_center = empty.geometry().center()
        assert abs(empty_center.x() - viewer_center_x) <= 2.0
        assert abs(empty_center.y() - viewer_center_y) <= 2.0
    finally:
        win.close()


def test_main_window_branding_elements(qapp: QApplication) -> None:
    """Memastikan MainWindow memiliki window icon dan header logo yang terpasang."""
    window = MainWindow()
    try:
        # Cek window icon
        window_icon = window.windowIcon()
        assert not window_icon.isNull()

        # Cek header logo label
        assert hasattr(window, "logo_label")
        assert window.logo_label.pixmap() is not None
        assert not window.logo_label.pixmap().isNull()
        assert window.logo_label.pixmap().height() == 44

        # Cek teks judul dan subtitle tetap utuh
        assert hasattr(window, "title_label")
        assert window.title_label.text() == "HILALONE"
        assert hasattr(window, "subtitle_label")
        assert "Hilal Image Processing" in window.subtitle_label.text()
    finally:
        window.close()


def test_setup_windows_app_id() -> None:
    """Memastikan fungsi setup Windows AppUserModelID berjalan aman."""
    # Fungsi ini tidak boleh melempar exception di environment apa pun
    _setup_windows_app_id()
