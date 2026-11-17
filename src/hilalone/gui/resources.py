"""Modul utilitas resource dan aset branding HILALONE.

Menyediakan resolusi path aset yang andal untuk berbagai lingkungan eksekusi:
- Mode pengembangan reguler (sumber kode / virtual environment).
- Eksekusi dari direktori kerja mana pun atau via run_hilalone.bat.
- Mode bundle / executable biner di masa depan (PyInstaller sys._MEIPASS).
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap
import numpy as np

logger = logging.getLogger(__name__)

# Direktori dan nama berkas aset branding resmi HILALONE (satu sumber kebenaran)
BRANDING_SUBDIR = Path("assets") / "branding"
APP_ICON_STANDARD = "hilalone_app_icon.ico"
APP_ICON_NIGHT_RED = "hilalone_app_icon_night_red.ico"
APP_ICON_LEGACY = "hilalone_app.ico"

LOGO_STANDARD = "hilalone_logo_standard.png"
LOGO_NIGHT_RED_PREFERRED = "hilalone_logo_night_red_separate.png"
LOGO_NIGHT_RED_FALLBACK = "hilalone_logo_night_red.png"
LOGO_LEGACY = "hilalone_logo.png"

COMPACT_ICON_STANDARD = "hilalone_icon_standard.png"
COMPACT_ICON_NIGHT_RED = "hilalone_icon_night_red.png"

# Proporsi diameter isi lingkaran terhadap sisi kanvas persegi agar ukuran visual logo konsisten antar tema
STANDARD_LOGO_FILL_RATIO = 0.92

# Cache aset di memori agar tidak membaca disk atau menskalakan ulang secara berlebihan
_APP_ICON_CACHE: dict[bool, QIcon] = {}
_RAW_LOGO_PIXMAP_CACHE: dict[bool, QPixmap] = {}
_RAW_COMPACT_LOGO_CACHE: dict[bool, QPixmap] = {}
_SCALED_HEADER_LOGO_CACHE: dict[tuple[bool, int], QPixmap] = {}
_MISSING_WARNED_PATHS: set[str] = set()


def _warn_missing_asset_once(asset_label: str, candidate: Path) -> None:
    """Mencatat peringatan satu kali ke log jika berkas aset branding tidak ditemukan."""
    key = f"{asset_label}:{candidate}"
    if key not in _MISSING_WARNED_PATHS:
        _MISSING_WARNED_PATHS.add(key)
        logger.warning("Aset branding %s tidak ditemukan di: %s", asset_label, candidate)


def clear_resource_cache() -> None:
    """Membersihkan cache ikon dan logo di memori (berguna untuk pengujian unit)."""
    _APP_ICON_CACHE.clear()
    _RAW_LOGO_PIXMAP_CACHE.clear()
    _RAW_COMPACT_LOGO_CACHE.clear()
    _SCALED_HEADER_LOGO_CACHE.clear()
    _MISSING_WARNED_PATHS.clear()


def get_project_root() -> Path:
    """Mengembalikan direktori root proyek HILALONE."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    # File ini berada di src/hilalone/gui/resources.py
    # parents: [0]=gui, [1]=hilalone, [2]=src, [3]=root proyek
    return Path(__file__).resolve().parents[3]


def get_user_data_dir() -> Path:
    """Mengembalikan direktori data pengguna HILALONE yang dapat ditulis tanpa hak Admin.

    Di Windows memakai ``%LOCALAPPDATA%\\HILALONE`` (atau fallback ``~/AppData/Local/HILALONE``).
    Tidak pernah menulis ke ``_MEIPASS`` maupun folder instalasi ``Program Files``.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        root = Path(base) if base else (Path.home() / "AppData" / "Local")
        return root / "HILALONE"
    return Path.home() / ".local" / "share" / "HILALONE"


def get_user_config_path() -> Path:
    """Mengembalikan path berkas konfigurasi preferensi pengguna HILALONE."""
    return get_user_data_dir() / "config.ini"


def get_user_log_dir() -> Path:
    """Mengembalikan direktori penyimpanan log permanen & diagnostik HILALONE (`%LOCALAPPDATA%\\HILALONE\\Logs`)."""
    return get_user_data_dir() / "Logs"


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


def _resolve_branding_candidate(filenames: tuple[str, ...]) -> Path:
    """Memilih path kandidat aset branding pertama yang tersedia di disk."""
    first_path = get_resource_path(BRANDING_SUBDIR / filenames[0])
    if first_path.exists():
        return first_path
    for name in filenames[1:]:
        candidate = get_resource_path(BRANDING_SUBDIR / name)
        if candidate.exists():
            return candidate
    return first_path


def get_app_icon_path(night_vision: bool = False) -> Path:
    """Mengembalikan path ke berkas ikon resmi aplikasi Windows (.ico)."""
    if night_vision:
        candidates = (APP_ICON_NIGHT_RED, APP_ICON_STANDARD, APP_ICON_LEGACY)
    else:
        candidates = (APP_ICON_STANDARD, APP_ICON_LEGACY)
    resolved = _resolve_branding_candidate(candidates)
    if not resolved.exists():
        _warn_missing_asset_once("app_icon", resolved)
    return resolved


def get_app_icon(night_vision: bool = False) -> QIcon:
    """Membuat dan mengembalikan objek QIcon resmi aplikasi HILALONE (dengan caching)."""
    if night_vision in _APP_ICON_CACHE:
        return _APP_ICON_CACHE[night_vision]

    icon_path = get_app_icon_path(night_vision=night_vision)
    if not icon_path.exists():
        _warn_missing_asset_once("app_icon", icon_path)
        return QIcon()

    icon = QIcon(str(icon_path))
    if icon.isNull():
        logger.warning("Gagal memuat berkas ikon aplikasi dari: %s", icon_path)
        return QIcon()

    _APP_ICON_CACHE[night_vision] = icon
    return icon


def get_logo_path(night_vision: bool = False) -> Path:
    """Mengembalikan path ke berkas logo resmi aplikasi (.png) sesuai tema aktif."""
    if night_vision:
        candidates = (
            LOGO_NIGHT_RED_PREFERRED,
            LOGO_NIGHT_RED_FALLBACK,
            LOGO_STANDARD,
            LOGO_LEGACY,
        )
    else:
        candidates = (LOGO_STANDARD, LOGO_LEGACY)

    resolved = _resolve_branding_candidate(candidates)
    if not resolved.exists():
        _warn_missing_asset_once("logo_night_red" if night_vision else "logo_standard", resolved)
    return resolved


def get_compact_logo_path(night_vision: bool = False) -> Path:
    """Mengembalikan path ke berkas ikon ringkas tanpa teks (.png) untuk ukuran kecil (<=96 px)."""
    if night_vision:
        candidates = (
            COMPACT_ICON_NIGHT_RED,
            COMPACT_ICON_STANDARD,
            LOGO_NIGHT_RED_PREFERRED,
            LOGO_STANDARD,
        )
    else:
        candidates = (COMPACT_ICON_STANDARD, LOGO_STANDARD, LOGO_LEGACY)

    resolved = _resolve_branding_candidate(candidates)
    if not resolved.exists():
        _warn_missing_asset_once("compact_icon_night_red" if night_vision else "compact_icon_standard", resolved)
    return resolved


def get_header_logo_path(night_vision: bool = False) -> Path:
    """Mengembalikan path ke ikon ringkas untuk area header aplikasi."""
    return get_compact_logo_path(night_vision=night_vision)


def _normalize_logo_pixmap(pixmap: QPixmap) -> QPixmap:
    """Menyamakan margin transparan & posisi pusat lingkaran logo antar varian tema.

    Aset Night Vision Red terpisah dapat memiliki padding transparan yang lebih lebar
    atau tidak simetris dibanding aset Standard Dark. Normalisasi ini hanya memotong
    padding berlebih dan menempatkan logo tepat di tengah kanvas persegi dengan proporsi
    pengisian seragam (`STANDARD_LOGO_FILL_RATIO`) tanpa mengubah desain maupun rasio aspek.
    """
    if pixmap.isNull():
        return pixmap

    qimg = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width = qimg.width()
    height = qimg.height()
    if width <= 0 or height <= 0:
        return pixmap

    bpl = qimg.bytesPerLine()
    buf = qimg.constBits()
    arr = np.frombuffer(buf, dtype=np.uint8).reshape((height, bpl))
    alpha = arr[:, : width * 4].reshape((height, width, 4))[:, :, 3]

    ys, xs = np.where(alpha > 10)
    if ys.size == 0 or xs.size == 0:
        return pixmap

    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    content_w = x1 - x0 + 1
    content_h = y1 - y0 + 1
    content_max = max(content_w, content_h)
    if content_w <= 0 or content_h <= 0:
        return pixmap

    cropped = pixmap.copy(x0, y0, content_w, content_h)
    canvas_size = max(width, height, int(round(content_max / STANDARD_LOGO_FILL_RATIO)))
    target_content_size = max(1, int(round(canvas_size * STANDARD_LOGO_FILL_RATIO)))
    scaled_content = cropped.scaled(
        target_content_size,
        target_content_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    normalized_img = QImage(canvas_size, canvas_size, QImage.Format.Format_RGBA8888)
    normalized_img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(normalized_img)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    draw_x = (canvas_size - scaled_content.width()) // 2
    draw_y = (canvas_size - scaled_content.height()) // 2
    painter.drawPixmap(draw_x, draw_y, scaled_content)
    painter.end()

    return QPixmap.fromImage(normalized_img)


def _load_normalized_pixmap(
    cache: dict[bool, QPixmap],
    path_resolver: Callable[[bool], Path],
    asset_label: str,
    night_vision: bool = False,
) -> QPixmap:
    """Memuat, menormalisasi padding, dan meng-cache QPixmap branding sesuai tema aktif."""
    if night_vision in cache:
        cached = cache[night_vision]
        if not cached.isNull():
            return cached

    asset_path = path_resolver(night_vision)
    if not asset_path.exists():
        _warn_missing_asset_once(asset_label, asset_path)
        return QPixmap()

    pixmap = QPixmap(str(asset_path))
    if pixmap.isNull():
        logger.warning("Gagal memuat berkas branding %s dari: %s", asset_label, asset_path)
        return QPixmap()

    pixmap = _normalize_logo_pixmap(pixmap)
    cache[night_vision] = pixmap
    return pixmap


def get_logo_pixmap(night_vision: bool = False) -> QPixmap:
    """Memuat dan meng-cache QPixmap logo lengkap resmi HILALONE untuk tampilan besar."""
    label = "logo_night_red" if night_vision else "logo_standard"
    return _load_normalized_pixmap(
        _RAW_LOGO_PIXMAP_CACHE,
        lambda nv: get_logo_path(night_vision=nv),
        label,
        night_vision=night_vision,
    )


def get_compact_logo_pixmap(night_vision: bool = False) -> QPixmap:
    """Memuat dan meng-cache QPixmap ikon ringkas tanpa teks untuk ukuran kecil/dialog identitas."""
    label = "compact_icon_night_red" if night_vision else "compact_icon_standard"
    return _load_normalized_pixmap(
        _RAW_COMPACT_LOGO_CACHE,
        lambda nv: get_compact_logo_path(night_vision=nv),
        label,
        night_vision=night_vision,
    )


def get_header_logo_pixmap(target_height: int = 44, night_vision: bool = False) -> QPixmap:
    """Memuat dan menskalakan ikon header dengan rasio aspek tetap serta caching per tema/ukuran.

    Parameter:
    -----------
    target_height : int
        Tinggi target dalam piksel (default 44 px, memakai varian ikon tanpa teks agar tetap tajam).
    night_vision : bool
        Jika True, menggunakan ikon ringkas tema Night Vision Red.
    """
    cache_key = (bool(night_vision), int(target_height))
    if cache_key in _SCALED_HEADER_LOGO_CACHE:
        return _SCALED_HEADER_LOGO_CACHE[cache_key]

    raw_pixmap = get_compact_logo_pixmap(night_vision=night_vision)
    if raw_pixmap.isNull():
        return QPixmap()

    scaled = raw_pixmap.scaled(
        target_height,
        target_height,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    if not scaled.isNull():
        _SCALED_HEADER_LOGO_CACHE[cache_key] = scaled
    return scaled
