"""Tes unit untuk resource branding, ikon aplikasi, dan logo header HILALONE."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication

from hilalone.gui.main_window import MainWindow
from hilalone.gui.resources import (
    get_app_icon,
    get_app_icon_path,
    get_header_logo_path,
    get_header_logo_pixmap,
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
    assert icon_path.name == "hilalone_app.ico"
    assert icon_path.stat().st_size > 0

    logo_path = get_header_logo_path()
    assert logo_path.exists(), f"Berkas logo tidak ditemukan di: {logo_path}"
    assert logo_path.name == "hilalone_logo.png"
    assert logo_path.stat().st_size > 0


def test_resource_path_helper_resolutions() -> None:
    """Memastikan fungsi get_resource_path menangani path absolut dan relatif."""
    root = get_project_root()
    assert root.exists()

    # Path relatif
    resolved_rel = get_resource_path("assets/branding/hilalone_app.ico")
    assert resolved_rel.exists()

    # Path absolut
    abs_path = resolved_rel.resolve()
    assert get_resource_path(abs_path) == abs_path


def test_get_app_icon(qapp: QApplication) -> None:
    """Memastikan get_app_icon memuat QIcon yang valid dari berkas .ico resmi."""
    icon = get_app_icon()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()
    # Memeriksa bahwa icon memiliki ukuran representasi yang tersedia
    available_sizes = icon.availableSizes()
    assert len(available_sizes) > 0


def test_get_header_logo_pixmap(qapp: QApplication) -> None:
    """Memastikan get_header_logo_pixmap memuat logo dengan proporsi dan scaling yang benar."""
    target_h = 44
    pixmap = get_header_logo_pixmap(target_height=target_h)
    assert isinstance(pixmap, QPixmap)
    assert not pixmap.isNull()
    assert pixmap.height() == target_h
    # Logo resmi hilalone_logo.png berdimensi 1254x1254 (rasio 1:1)
    # Setelah scaledToHeight(44), lebarnya juga harus 44
    assert pixmap.width() == target_h


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
