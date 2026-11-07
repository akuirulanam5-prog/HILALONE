"""Pengelola Ikon Vektor SVG untuk Antarmuka HILALONE.

Menghasilkan QIcon berbasis SVG secara konsisten tanpa dependensi pustaka luar.
Semua ikon digambar dengan gaya minimalis beresolusi tinggi yang tajam di berbagai DPI.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Definisi template SVG (Lucide-inspired) berdimensi 24x24
_SVG_TEMPLATES: dict[str, str] = {
    # 1. Hover Magnifier / Loupe (scan-eye)
    "scan-eye": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 7V5a2 2 0 0 1 2-2h2"/>
  <path d="M17 3h2a2 2 0 0 1 2 2v2"/>
  <path d="M21 17v2a2 2 0 0 1-2 2h-2"/>
  <path d="M7 21H5a2 2 0 0 1-2-2v-2"/>
  <circle cx="12" cy="12" r="3.5"/>
  <path d="m14.5 14.5 2.5 2.5"/>
</svg>""",

    # 2. Zoom Out (zoom-out)
    "zoom-out": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="11" cy="11" r="7"/>
  <line x1="21" y1="21" x2="16.65" y2="16.65"/>
  <line x1="8" y1="11" x2="14" y2="11"/>
</svg>""",

    # 3. Zoom In (zoom-in)
    "zoom-in": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="11" cy="11" r="7"/>
  <line x1="21" y1="21" x2="16.65" y2="16.65"/>
  <line x1="11" y1="8" x2="11" y2="14"/>
  <line x1="8" y1="11" x2="14" y2="11"/>
</svg>""",

    # 4. Fit the Image (scan)
    "scan": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 7V5a2 2 0 0 1 2-2h2"/>
  <path d="M17 3h2a2 2 0 0 1 2 2v2"/>
  <path d="M21 17v2a2 2 0 0 1-2 2h-2"/>
  <path d="M7 21H5a2 2 0 0 1-2-2v-2"/>
  <rect x="8" y="8" width="8" height="8" rx="1.5"/>
</svg>""",

    # 5. Original Size / 1:1 (maximize)
    "maximize": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M8 3H5a2 2 0 0 0-2 2v3"/>
  <path d="M21 8V5a2 2 0 0 0-2-2h-3"/>
  <path d="M3 16v3a2 2 0 0 0 2 2h3"/>
  <path d="M16 21h3a2 2 0 0 0 2-2v-3"/>
  <text x="12" y="14" font-family="sans-serif" font-size="7" font-weight="bold" fill="{color}" stroke="none" text-anchor="middle" dominant-baseline="middle">1:1</text>
</svg>""",

    # 6. Save Result (save)
    "save": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
  <polyline points="17 21 17 13 7 13 7 21"/>
  <polyline points="7 3 7 8 15 8"/>
</svg>""",

    # 7. Quick Snapshot (camera)
    "camera": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z"/>
  <circle cx="12" cy="13" r="4"/>
</svg>""",
}


def _render_svg_pixmap(svg_text: str, size: int = 24) -> QPixmap:
    """Merender teks XML SVG ke QPixmap transparan berukuran tertentu."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    byte_array = QByteArray(svg_text.encode("utf-8"))
    renderer = QSvgRenderer(byte_array)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter, QRectF(0.0, 0.0, float(size), float(size)))
    painter.end()
    return pixmap


def create_vector_icon(
    name: str,
    *,
    normal_color: str = "#e2e8f0",
    hover_color: str = "#38bdf8",
    active_color: str = "#0ea5e9",
    disabled_color: str = "#64748b",
    size: int = 24,
) -> QIcon:
    """Membuat objek QIcon multi-state dari nama vektor yang terdaftar."""
    template = _SVG_TEMPLATES.get(name)
    if template is None:
        raise ValueError(f"Ikon vektor '{name}' tidak terdaftar dalam HILALONE.")

    icon = QIcon()
    # Mode Normal / Off
    normal_svg = template.format(color=normal_color)
    icon.addPixmap(_render_svg_pixmap(normal_svg, size), QIcon.Mode.Normal, QIcon.State.Off)

    # Mode Active / On (ketika tombol ditekan/checked seperti Magnifier)
    active_svg = template.format(color=active_color)
    icon.addPixmap(_render_svg_pixmap(active_svg, size), QIcon.Mode.Normal, QIcon.State.On)
    icon.addPixmap(_render_svg_pixmap(active_svg, size), QIcon.Mode.Active, QIcon.State.On)

    # Mode Hover / Active
    hover_svg = template.format(color=hover_color)
    icon.addPixmap(_render_svg_pixmap(hover_svg, size), QIcon.Mode.Active, QIcon.State.Off)

    # Mode Disabled
    disabled_svg = template.format(color=disabled_color)
    icon.addPixmap(_render_svg_pixmap(disabled_svg, size), QIcon.Mode.Disabled, QIcon.State.Off)
    icon.addPixmap(_render_svg_pixmap(disabled_svg, size), QIcon.Mode.Disabled, QIcon.State.On)

    return icon
