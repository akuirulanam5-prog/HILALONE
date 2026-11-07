"""Modul utilitas resource dan aset branding HILALONE.

Menyediakan resolusi path aset yang andal untuk berbagai lingkungan eksekusi:
- Mode pengembangan reguler (sumber kode / virtual environment).
- Eksekusi dari direktori kerja mana pun atau via run_hilalone.bat.
- Mode bundle / executable biner di masa depan (PyInstaller sys._MEIPASS).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPixmap


def get_project_root() -> Path:
    """Mengembalikan direktori root proyek HILALONE."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # File ini berada di src/hilalone/gui/resources.py
    # parents: [0]=gui, [1]=hilalone, [2]=src, [3]=root proyek
    return Path(__file__).resolve().parents[3]


def get_resource_path(relative_path: str | Path) -> Path:
    """Mencari path mutlak dari berkas aset/resource.

    Memeriksa root bundle PyInstaller (jika aktif), root proyek relatif terhadap
    modul, dan direktori kerja aktif sebagai fallback.
    """
    rel = Path(relative_path)
    if rel.is_absolute():
        return rel

    # 1. Periksa basis root proyek / MEIPASS
    root_candidate = get_project_root() / rel
    if root_candidate.exists():
        return root_candidate

    # 2. Periksa basis Current Working Directory (CWD)
    cwd_candidate = Path.cwd() / rel
    if cwd_candidate.exists():
        return cwd_candidate

    # Default kembalikan path kandidat root proyek meskipun belum ada di disk
    return root_candidate


def get_app_icon_path() -> Path:
    """Mengembalikan path ke berkas ikon resmi aplikasi (.ico)."""
    return get_resource_path(Path("assets") / "branding" / "hilalone_app.ico")


def get_app_icon() -> QIcon:
    """Membuat dan mengembalikan objek QIcon resmi aplikasi HILALONE."""
    icon_path = get_app_icon_path()
    if icon_path.exists():
        return QIcon(str(icon_path))
    return QIcon()


def get_header_logo_path() -> Path:
    """Mengembalikan path ke berkas logo resmi aplikasi (.png)."""
    return get_resource_path(Path("assets") / "branding" / "hilalone_logo.png")


def get_header_logo_pixmap(target_height: int = 44) -> QPixmap:
    """Memuat dan menskalakan logo header dengan proporsi asli dan interpolasi halus.

    Parameter:
    -----------
    target_height : int
        Tinggi target dalam piksel (default 44 px, proporsional dengan judul 20pt + subtitle 10pt).
    """
    logo_path = get_header_logo_path()
    if not logo_path.exists():
        return QPixmap()

    pixmap = QPixmap(str(logo_path))
    if pixmap.isNull():
        return QPixmap()

    return pixmap.scaledToHeight(
        target_height,
        Qt.TransformationMode.SmoothTransformation,
    )
