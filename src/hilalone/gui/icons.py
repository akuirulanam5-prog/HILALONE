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

    # 8. Information (info)
    "info": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <line x1="12" y1="16" x2="12" y2="12"/>
  <line x1="12" y1="8" x2="12.01" y2="8"/>
</svg>""",

    # 9. Rotate Counter-Clockwise (rotate-ccw)
    "rotate-ccw": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
  <polyline points="3 3 3 8 8 8"/>
</svg>""",

    # 10. Rotate Clockwise (rotate-cw)
    "rotate-cw": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"/>
  <polyline points="21 3 21 8 16 8"/>
</svg>""",

    # 11. Flip Horizontal (flip-horizontal)
    "flip-horizontal": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="12" y1="3" x2="12" y2="21" stroke-dasharray="2 2"/>
  <path d="M16 6l5 6-5 6V6z"/>
  <path d="M8 6L3 12l5 6V6z"/>
</svg>""",

    # 12. Flip Vertical (flip-vertical)
    "flip-vertical": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="3" y1="12" x2="21" y2="12" stroke-dasharray="2 2"/>
  <path d="M6 16l6 5 6-5H6z"/>
  <path d="M6 8l6-5 6 5H6z"/>
</svg>""",

    # 13. Moon / Night Vision (moon)
    "moon": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
</svg>""",

    # 14. Sun (sun)
    "sun": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="4"/>
  <path d="M12 2v2"/>
  <path d="M12 20v2"/>
  <path d="m4.93 4.93 1.41 1.41"/>
  <path d="m17.66 17.66 1.41 1.41"/>
  <path d="M2 12h2"/>
  <path d="M20 12h2"/>
  <path d="m6.34 17.66-1.41 1.41"/>
  <path d="m19.07 4.93-1.41 1.41"/>
</svg>""",

    # 15. Bar Chart / Histogram (bar-chart-2)
    "bar-chart-2": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="18" y1="20" x2="18" y2="10"/>
  <line x1="12" y1="20" x2="12" y2="4"/>
  <line x1="6" y1="20" x2="6" y2="14"/>
</svg>""",

    # 16. Trending Up / Kurva (trending-up)
    "trending-up": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>
  <polyline points="16 7 22 7 22 13"/>
</svg>""",

    # 17. Terminal / Console Log (terminal)
    "terminal": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="4 17 10 11 4 5"/>
  <line x1="12" y1="19" x2="20" y2="19"/>
</svg>""",

    # 18. Chevron Left (chevron-left)
    "chevron-left": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m15 18-6-6 6-6"/>
</svg>""",

    # 19. Chevron Right (chevron-right)
    "chevron-right": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m9 18 6-6-6-6"/>
</svg>""",

    # 20. Chevron Down (chevron-down)
    "chevron-down": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m6 9 6 6 6-6"/>
</svg>""",

    # 21. Chevron Up (chevron-up)
    "chevron-up": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m18 15-6-6-6 6"/>
</svg>""",

    # 22. Check / Apply (check)
    "check": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="20 6 9 17 4 12"/>
</svg>""",

    # 23. Eye / Preview (eye)
    "eye": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
  <circle cx="12" cy="12" r="3"/>
</svg>""",

    # 24. Folder Open (folder-open)
    "folder-open": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m6 14 1.45-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 0 1-1.94 1.5H4a2 2 0 0 1-2-2V5c0-1.1.9-2 2-2h3.93a2 2 0 0 1 1.66.9l.82 1.2a2 2 0 0 0 1.66.9H18a2 2 0 0 1 2 2v2"/>
</svg>""",

    # 25. Images / Multi Image (images)
    "images": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M18 22H4a2 2 0 0 1-2-2V6"/>
  <rect x="6" y="2" width="16" height="16" rx="2"/>
  <circle cx="11.5" cy="7.5" r="1.5"/>
  <path d="m21 15-5-5L8 18"/>
</svg>""",

    # 26. Folder / Sequence (folder)
    "folder": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>
</svg>""",

    # 27. Video (video)
    "video": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m22 8-6 4 6 4V8Z"/>
  <rect x="2" y="6" width="14" height="12" rx="2"/>
</svg>""",

    # 28. Film / SER (film)
    "film": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="2" y="2" width="20" height="20" rx="2"/>
  <line x1="7" y1="2" x2="7" y2="22"/>
  <line x1="17" y1="2" x2="17" y2="22"/>
  <line x1="2" y1="12" x2="22" y2="12"/>
  <line x1="2" y1="7" x2="7" y2="7"/>
  <line x1="2" y1="17" x2="7" y2="17"/>
  <line x1="17" y1="17" x2="22" y2="17"/>
  <line x1="17" y1="7" x2="22" y2="7"/>
</svg>""",

    # 29. Close / X (x)
    "x": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M18 6 6 18"/>
  <path d="m6 6 12 12"/>
</svg>""",

    # 30. Check Square (check-square)
    "check-square": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="9 11 12 14 22 4"/>
  <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
</svg>""",

    # 31. Square / Deselect (square)
    "square": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect width="18" height="18" x="3" y="3" rx="2"/>
</svg>""",

    # 32. Copy (copy)
    "copy": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
  <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
</svg>""",

    # 33. Clipboard (clipboard)
    "clipboard": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect width="8" height="4" x="8" y="2" rx="1" ry="1"/>
  <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
</svg>""",

    # 34. Plus / Add (plus)
    "plus": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M5 12h14"/>
  <path d="M12 5v14"/>
</svg>""",

    # 35. Trash / Delete (trash-2)
    "trash-2": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 6h18"/>
  <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/>
  <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>
  <line x1="10" y1="11" x2="10" y2="17"/>
  <line x1="14" y1="11" x2="14" y2="17"/>
</svg>""",

    # 36. Edit / Edit-3 (edit-3)
    "edit-3": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 20h9"/>
  <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
</svg>""",

    # 37. Download / Export (download)
    "download": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
  <polyline points="7 10 12 15 17 10"/>
  <line x1="12" y1="15" x2="12" y2="3"/>
</svg>""",

    # 38. Play / Auto Process (play)
    "play": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="6 3 20 12 6 21 6 3"/>
</svg>""",

    # 39. Layers / Stacking (layers)
    "layers": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="12 2 2 7 12 12 22 7 12 2"/>
  <polyline points="2 17 12 22 22 17"/>
  <polyline points="2 12 12 17 22 12"/>
</svg>""",

    # 40. Sliders / Advanced Settings (sliders)
    "sliders": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="4" y1="21" x2="4" y2="14"/>
  <line x1="4" y1="10" x2="4" y2="3"/>
  <line x1="12" y1="21" x2="12" y2="12"/>
  <line x1="12" y1="8" x2="12" y2="3"/>
  <line x1="20" y1="21" x2="20" y2="16"/>
  <line x1="20" y1="12" x2="20" y2="3"/>
  <line x1="1" y1="14" x2="7" y2="14"/>
  <line x1="9" y1="8" x2="15" y2="8"/>
  <line x1="17" y1="16" x2="23" y2="16"/>
</svg>""",

    # 41. Refresh / Reset (refresh-cw)
    "refresh-cw": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/>
  <path d="M21 3v5h-5"/>
  <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/>
  <path d="M8 16H3v5"/>
</svg>""",

    # 42. Switch Normal / Negative View (negative-view)
    "negative-view": """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="9"/>
  <path d="M12 3a9 9 0 0 0 0 18Z" fill="{color}" stroke="none"/>
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


def create_themed_vector_icon(
    name: str,
    *,
    night_vision: bool = False,
    is_info: bool = False,
    size: int = 24,
) -> QIcon:
    """Membuat ikon vektor dengan palet warna yang selaras dengan tema (Standard Dark atau Night Vision).

    Pada mode Night Vision Red, seluruh warna ikon disesuaikan dengan spektrum merah monokromatik
    untuk menjaga dark adaptation pupil mata saat pengamatan rukyatul hilal malam hari.
    """
    if night_vision:
        if is_info:
            return create_vector_icon(
                name,
                normal_color="#ef4444",
                hover_color="#f87171",
                active_color="#b91c1c",
                disabled_color="#4c1414",
                size=size,
            )
        return create_vector_icon(
            name,
            normal_color="#fca5a5",
            hover_color="#f87171",
            active_color="#ef4444",
            disabled_color="#4c1414",
            size=size,
        )
    else:
        if is_info:
            return create_vector_icon(
                name,
                normal_color="#38bdf8",
                hover_color="#7dd3fc",
                active_color="#0284c7",
                disabled_color="#64748b",
                size=size,
            )
        return create_vector_icon(
            name,
            normal_color="#e2e8f0",
            hover_color="#38bdf8",
            active_color="#0ea5e9",
            disabled_color="#64748b",
            size=size,
        )

