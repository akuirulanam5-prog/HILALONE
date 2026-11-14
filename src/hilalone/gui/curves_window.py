"""Jendela Transformasi Kurva (Curves Adjustment) Khusus HILALONE.

Menyediakan pengaturan kontras dan tonal non-linear manual berbasis kurva spline:
  - Kanvas kurva interaktif (tambah, geser, dan hapus titik kontrol kurva).
  - Interpolasi halus monotonic cubic spline (PCHIP) bebas osilasi liar.
  - Histogram citra aktif sebagai panduan visual latar belakang.
  - Pilihan preset astronomi (Linear, S-Curve Sabit Hilal, Shadow Lift, Highlight Compress).
  - Mode RGB dan Luminance-aware (mempertahankan integritas warna hilal sesuai RULE 5).
  - Live Preview instan ke Image Viewer.
  - Tombol Terapkan (Apply) untuk menyimpan perubahan ke data ilmiah/tampilan.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from scipy.interpolate import PchipInterpolator

from hilalone.gui.icons import create_themed_vector_icon, create_vector_icon


@dataclass
class CurvePoint:
    x: float  # Masukan [0.0, 1.0]
    y: float  # Keluaran [0.0, 1.0]


def compute_pchip_lut(points: list[tuple[float, float]], num_samples: int = 256) -> np.ndarray:
    """Menghitung Look-Up Table (LUT) menggunakan interpolasi PCHIP yang monoton dan halus."""
    pts = sorted(points, key=lambda p: p[0])
    # Pastikan batas x=0 dan x=1 ada
    if not pts:
        return np.linspace(0.0, 1.0, num_samples, dtype=np.float32)

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]

    # Atasi titik dengan x identik jika ada
    clean_xs = [xs[0]]
    clean_ys = [ys[0]]
    for i in range(1, len(xs)):
        if xs[i] > clean_xs[-1] + 1e-5:
            clean_xs.append(xs[i])
            clean_ys.append(ys[i])

    if len(clean_xs) == 1:
        return np.full(num_samples, clean_ys[0], dtype=np.float32)

    # Tambahkan titik ujung jika belum mencapai 0.0 atau 1.0
    if clean_xs[0] > 0.0:
        clean_xs.insert(0, 0.0)
        clean_ys.insert(0, clean_ys[0])
    if clean_xs[-1] < 1.0:
        clean_xs.append(1.0)
        clean_ys.append(clean_ys[-1])

    interpolator = PchipInterpolator(clean_xs, clean_ys)
    sample_x = np.linspace(0.0, 1.0, num_samples, dtype=np.float32)
    lut = np.clip(interpolator(sample_x), 0.0, 1.0).astype(np.float32)
    return lut


def apply_curve_lut_to_array(
    arr: np.ndarray,
    lut_256: np.ndarray,
    mode: str = "RGB",
) -> np.ndarray:
    """Menerapkan kurva LUT ke array data ilmiah float32 [vmin, vmax]."""
    finite_mask = np.isfinite(arr)
    if not np.any(finite_mask):
        return arr.copy()

    vmin = float(np.min(arr[finite_mask]))
    vmax = float(np.max(arr[finite_mask]))
    diff = vmax - vmin if vmax > vmin else 1.0

    # Normalisasi ke [0.0, 1.0]
    norm = np.clip((arr - vmin) / diff, 0.0, 1.0)
    lut_x = np.linspace(0.0, 1.0, 256, dtype=np.float32)
    lut_y = np.clip(np.asarray(lut_256, dtype=np.float32), 0.0, 1.0)

    if norm.ndim == 2 or mode == "RGB" or norm.shape[-1] != 3:
        # Terapkan langsung per elemen
        curved = np.interp(norm.ravel(), lut_x, lut_y).reshape(norm.shape)
    else:
        # Luminance-aware (mempertahankan kromatisitas RGB)
        r, g, b = norm[..., 0], norm[..., 1], norm[..., 2]
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        lum_curved = np.interp(lum.ravel(), lut_x, lut_y).reshape(lum.shape)
        scale = np.where(lum > 1e-6, lum_curved / np.maximum(lum, 1e-6), 1.0)
        curved = np.clip(norm * scale[..., np.newaxis], 0.0, 1.0)

    # Kembalikan ke rentang semula
    return (curved * diff + vmin).astype(np.float32)


def apply_curve_lut_to_pixmap(
    source_pixmap: QPixmap,
    lut_256: np.ndarray,
    mode: str = "RGB",
) -> QPixmap:
    """Menerapkan LUT ke QPixmap secara cepat untuk pratinjau instan di layar."""
    from PySide6.QtGui import QImage
    qimg = source_pixmap.toImage()
    w, h = qimg.width(), qimg.height()
    if w <= 0 or h <= 0:
        return source_pixmap

    # Gunakan Format_RGBA8888 yang selalu 4-byte aligned (bytesPerLine == 4 * w) tanpa padding
    img_rgba = qimg.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = img_rgba.constBits()
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, w, 4)).copy()

    lut_u8 = np.clip(np.asarray(lut_256, dtype=np.float32) * 255.0, 0, 255).astype(np.uint8)

    if mode == "LUMINANCE":
        # Luminance aware di ruang uint8 (mempertahankan rasio warna hilal)
        r = arr[..., 0].astype(np.float32)
        g = arr[..., 1].astype(np.float32)
        b = arr[..., 2].astype(np.float32)
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        lum_idx = np.clip(lum.round(), 0, 255).astype(np.uint8)
        lum_out = lut_u8[lum_idx].astype(np.float32)
        scale = np.where(lum > 1e-3, lum_out / np.maximum(lum, 1e-3), 1.0)
        arr[..., 0] = np.clip(r * scale, 0, 255).astype(np.uint8)
        arr[..., 1] = np.clip(g * scale, 0, 255).astype(np.uint8)
        arr[..., 2] = np.clip(b * scale, 0, 255).astype(np.uint8)
    else:
        # Direct LUT lookup pada kanal RGB (kanal Alpha pada indeks 3 tetap utuh)
        arr[..., :3] = lut_u8[arr[..., :3]]

    out_qimg = QImage(arr.data, w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(out_qimg)


class CurveCanvas(QWidget):
    """Kanvas kurva interaktif dengan background histogram dan titik kontrol."""

    curve_changed = Signal(object)  # np.ndarray LUT 256
    point_hovered = Signal(str)     # Info koordinat hover teks

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(280, 280)

        # Titik kontrol awal: (0.0, 0.0) dan (1.0, 1.0)
        self._points: list[CurvePoint] = [
            CurvePoint(0.0, 0.0),
            CurvePoint(1.0, 1.0),
        ]
        self._lut: np.ndarray = np.linspace(0.0, 1.0, 256, dtype=np.float32)

        # Background histogram
        self._hist_counts: np.ndarray | None = None

        # State interaksi
        self._dragged_idx: int | None = None
        self._hovered_idx: int | None = None

        # Padding / margin dalam pixel
        self._margin_left = 30
        self._margin_bottom = 26
        self._margin_top = 16
        self._margin_right = 16

    @property
    def points(self) -> list[tuple[float, float]]:
        return [(p.x, p.y) for p in self._points]

    def set_points(self, pts: list[tuple[float, float]]) -> None:
        """Mengatur titik kontrol kurva baru."""
        if len(pts) < 2:
            pts = [(0.0, 0.0), (1.0, 1.0)]
        sorted_pts = sorted(pts, key=lambda p: p[0])
        self._points = [CurvePoint(float(x), float(y)) for x, y in sorted_pts]
        self._recompute_lut()
        self.update()

    def set_histogram_data(self, arr: np.ndarray | None) -> None:
        """Menghitung data histogram latar belakang dari array citra."""
        if arr is None or arr.size == 0:
            self._hist_counts = None
            self.update()
            return

        finite_mask = np.isfinite(arr)
        if not np.any(finite_mask):
            self._hist_counts = None
            self.update()
            return

        valid_vals = arr[finite_mask]
        # Batasi sampel maksimal 200,000 piksel untuk performa seketika
        if valid_vals.size > 200000:
            step = valid_vals.size // 200000
            valid_vals = valid_vals[::step]

        vmin = float(np.min(valid_vals))
        vmax = float(np.max(valid_vals))
        diff = vmax - vmin if vmax > vmin else 1.0
        norm_vals = np.clip((valid_vals - vmin) / diff, 0.0, 1.0)

        counts, _ = np.histogram(norm_vals, bins=128, range=(0.0, 1.0))
        max_c = np.max(counts) if len(counts) > 0 and np.max(counts) > 0 else 1.0
        # Gunakan log scale lembut agar sinyal redup terlihat
        self._hist_counts = np.log1p(counts) / np.log1p(max_c)
        self.update()

    def get_lut(self) -> np.ndarray:
        return self._lut.copy()

    def _plot_rect(self) -> QRectF:
        w = self.width() - self._margin_left - self._margin_right
        h = self.height() - self._margin_top - self._margin_bottom
        return QRectF(self._margin_left, self._margin_top, max(10, w), max(10, h))

    def _val_to_canvas(self, x: float, y: float) -> QPointF:
        r = self._plot_rect()
        cx = r.left() + x * r.width()
        cy = r.bottom() - y * r.height()
        return QPointF(cx, cy)

    def _canvas_to_val(self, pt: QPointF) -> tuple[float, float]:
        r = self._plot_rect()
        vx = (pt.x() - r.left()) / r.width()
        vy = (r.bottom() - pt.y()) / r.height()
        return float(np.clip(vx, 0.0, 1.0)), float(np.clip(vy, 0.0, 1.0))

    def _recompute_lut(self) -> None:
        self._lut = compute_pchip_lut([(p.x, p.y) for p in self._points], 256)
        self.curve_changed.emit(self._lut)

    def paintEvent(self, _event: Any) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = self._plot_rect()

        # 1. Area Latar Belakang Plot
        painter.fillRect(r, QColor("#080d1a"))
        painter.setPen(QPen(QColor("#1e2a45"), 1))
        painter.drawRect(r)

        # 2. Grid Koordinat (4 grid lines = 25%, 50%, 75%)
        grid_pen = QPen(QColor("#142038"), 1, Qt.PenStyle.DashLine)
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        painter.setPen(grid_pen)

        for frac in (0.25, 0.5, 0.75):
            # Garis vertikal
            gx = r.left() + frac * r.width()
            painter.drawLine(QPointF(gx, r.top()), QPointF(gx, r.bottom()))
            # Garis horizontal
            gy = r.bottom() - frac * r.height()
            painter.drawLine(QPointF(r.left(), gy), QPointF(r.right(), gy))

        # Teks Sumbu
        painter.setPen(QColor("#64748b"))
        painter.drawText(int(r.left() - 24), int(r.bottom() + 4), "0.0")
        painter.drawText(int(r.left() - 24), int(r.top() + 8), "1.0")
        painter.drawText(int(r.left() - 4), int(r.bottom() + 18), "0")
        painter.drawText(int(r.right() - 10), int(r.bottom() + 18), "1")
        painter.drawText(int(r.center().x() - 16), int(r.bottom() + 18), "In")
        painter.drawText(int(r.left() - 26), int(r.center().y() + 4), "Out")

        # 3. Histogram Latar Belakang (jika ada)
        if self._hist_counts is not None and len(self._hist_counts) > 0:
            hist_brush = QBrush(QColor(56, 189, 248, 40))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hist_brush)
            num_bins = len(self._hist_counts)
            bin_w = r.width() / num_bins
            for i, val in enumerate(self._hist_counts):
                bh = float(val) * r.height()
                bx = r.left() + i * bin_w
                by = r.bottom() - bh
                painter.drawRect(QRectF(bx, by, bin_w, bh))

        # 4. Garis Identitas (Diagonal netral y = x)
        ident_pen = QPen(QColor("#334155"), 1, Qt.PenStyle.DashLine)
        painter.setPen(ident_pen)
        painter.drawLine(QPointF(r.left(), r.bottom()), QPointF(r.right(), r.top()))

        # 5. Kurva Spline Halus (PCHIP)
        curve_path = QPainterPath()
        first_pt = self._val_to_canvas(0.0, float(self._lut[0]))
        curve_path.moveTo(first_pt)
        for i in range(1, 256):
            x = i / 255.0
            y = float(self._lut[i])
            pt = self._val_to_canvas(x, y)
            curve_path.lineTo(pt)

        is_nv = getattr(self.parent(), "_is_night_vision", False) if self.parent() is not None else False
        curve_color = QColor("#ef4444") if is_nv else QColor("#38bdf8")
        curve_pen = QPen(curve_color, 2.2)
        painter.strokePath(curve_path, curve_pen)

        # 6. Titik-Titik Kontrol Kurva
        for i, pt in enumerate(self._points):
            c_pt = self._val_to_canvas(pt.x, pt.y)
            is_hover = (i == self._hovered_idx)
            is_drag = (i == self._dragged_idx)

            if is_hover or is_drag:
                halo_pen = QPen(QColor(56, 189, 248, 120), 2)
                painter.setPen(halo_pen)
                painter.setBrush(QColor(56, 189, 248, 50))
                painter.drawEllipse(c_pt, 8, 8)

            pt_pen = QPen(QColor("#0284c7"), 1.8)
            painter.setPen(pt_pen)
            painter.setBrush(QColor("#ffffff"))
            painter.drawEllipse(c_pt, 4.5, 4.5)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        r = self._plot_rect()
        if not r.contains(pos):
            return

        # Cek apakah klik dekat titik kontrol yang sudah ada
        clicked_idx: int | None = None
        for i, pt in enumerate(self._points):
            c_pt = self._val_to_canvas(pt.x, pt.y)
            dx = pos.x() - c_pt.x()
            dy = pos.y() - c_pt.y()
            if (dx * dx + dy * dy) <= 12 * 12:
                clicked_idx = i
                break

        if event.button() == Qt.MouseButton.LeftButton:
            if clicked_idx is not None:
                self._dragged_idx = clicked_idx
            else:
                # Tambahkan titik kontrol baru di posisi klik
                vx, vy = self._canvas_to_val(pos)
                new_pt = CurvePoint(vx, vy)
                self._points.append(new_pt)
                self._points.sort(key=lambda p: p.x)
                self._dragged_idx = self._points.index(new_pt)
                self._recompute_lut()
            self.update()

        elif event.button() == Qt.MouseButton.RightButton:
            # Klik kanan menghapus titik (kecuali titik ujung)
            if clicked_idx is not None and 0 < clicked_idx < len(self._points) - 1:
                self._points.pop(clicked_idx)
                self._hovered_idx = None
                self._recompute_lut()
                self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position()
        r = self._plot_rect()

        if self._dragged_idx is not None and 0 <= self._dragged_idx < len(self._points):
            vx, vy = self._canvas_to_val(pos)
            pt = self._points[self._dragged_idx]

            # Titik ujung x=0 terkunci di x=0
            if self._dragged_idx == 0:
                pt.x = 0.0
                pt.y = vy
            # Titik ujung x=1 terkunci di x=1
            elif self._dragged_idx == len(self._points) - 1:
                pt.x = 1.0
                pt.y = vy
            else:
                # Titik tengah dibatasi antar tetangga
                left_bound = self._points[self._dragged_idx - 1].x + 0.01
                right_bound = self._points[self._dragged_idx + 1].x - 0.01
                pt.x = float(np.clip(vx, left_bound, right_bound))
                pt.y = vy

            self.point_hovered.emit(f"Titik Kontrol: In = {pt.x:.2f}, Out = {pt.y:.2f}")
            self._recompute_lut()
            self.update()
        else:
            # Hover check
            hover_idx = None
            for i, pt in enumerate(self._points):
                c_pt = self._val_to_canvas(pt.x, pt.y)
                dx = pos.x() - c_pt.x()
                dy = pos.y() - c_pt.y()
                if (dx * dx + dy * dy) <= 12 * 12:
                    hover_idx = i
                    break

            if hover_idx != self._hovered_idx:
                self._hovered_idx = hover_idx
                self.update()

            if hover_idx is not None:
                p = self._points[hover_idx]
                self.point_hovered.emit(f"Titik Kontrol: In = {p.x:.2f}, Out = {p.y:.2f} (Klik kanan hapus)")
            elif r.contains(pos):
                vx, vy = self._canvas_to_val(pos)
                self.point_hovered.emit(f"Posisi: In = {vx:.2f}, Out = {vy:.2f} (Klik tambah titik)")
            else:
                self.point_hovered.emit("Klik & seret titik kontrol untuk mengatur kurva.")

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragged_idx = None
            self.update()


class CurvesWindow(QDialog):
    """Jendela Transformasi Kurva lengkap dengan kanvas interaktif, preset, dan live preview."""

    preview_requested = Signal(object, str)  # (lut_256: np.ndarray, channel_mode: str)
    apply_requested = Signal(object, str)    # (lut_256: np.ndarray, channel_mode: str)
    reset_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowTitle("Transformasi Kurva (Curves Adjustment) — HILALONE")
        self.setObjectName("curvesWindow")
        self.resize(580, 440)
        self.setMinimumSize(540, 400)

        self._source_data: np.ndarray | None = None
        self._source_qimage: Any = None
        self._title_text: str = ""

        self._build_ui()

    def set_source_data(
        self,
        arr: np.ndarray | None,
        qimg: Any,
        title: str = "Citra Aktif",
    ) -> None:
        """Mengatur data citra sumber untuk panduan histogram dan preview."""
        self._source_data = arr
        self._source_qimage = qimg
        self._title_text = title
        self.lbl_target_info.setText(f"Target Citra: {title}")
        self.canvas.set_histogram_data(arr)
        # Reset kurva ke default linear saat citra baru diatur
        self.canvas.set_points([(0.0, 0.0), (1.0, 1.0)])

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Header Info
        header_box = QHBoxLayout()
        header_box.setSpacing(10)

        is_nv = getattr(self.parent(), "_is_night_vision", False) if self.parent() is not None else False

        icon_lbl = QLabel()
        icon_lbl.setPixmap(create_themed_vector_icon("trending-up", night_vision=is_nv, size=24).pixmap(24, 24))
        header_box.addWidget(icon_lbl)

        v_text = QVBoxLayout()
        v_text.setSpacing(2)
        title_lbl = QLabel("TRANSFORMASI KURVA (CURVES ADJUSTMENT)")
        title_lbl.setObjectName("sectionHeader")
        title_col = "#ef4444" if is_nv else "#38bdf8"
        title_lbl.setStyleSheet(f"font-size: 11pt; font-weight: 700; color: {title_col};")

        self.lbl_target_info = QLabel("Target Citra: Tidak ada citra")
        self.lbl_target_info.setObjectName("infoKey")
        v_text.addWidget(title_lbl)
        v_text.addWidget(self.lbl_target_info)
        header_box.addLayout(v_text)
        header_box.addStretch(1)
        layout.addLayout(header_box)

        # Main Body: Canvas Kiri, Panel Kontrol Kanan
        body_layout = QHBoxLayout()
        body_layout.setSpacing(14)

        # Canvas Kurva
        self.canvas = CurveCanvas(self)
        self.canvas.curve_changed.connect(self._on_curve_changed)
        self.canvas.point_hovered.connect(self._on_point_hovered)
        body_layout.addWidget(self.canvas, 1)

        # Panel Sisi Kanan
        right_panel = QVBoxLayout()
        right_panel.setSpacing(10)

        # 1. Preset Kurva
        grp_preset = QGroupBox("Preset Astronomi")
        grp_preset.setObjectName("infoSectionCard")
        v_preset = QVBoxLayout(grp_preset)
        v_preset.setSpacing(6)

        self.btn_preset_linear = QPushButton("Identitas / Linear")
        self.btn_preset_linear.setObjectName("secondaryButton")
        self.btn_preset_linear.clicked.connect(self._preset_linear)
        v_preset.addWidget(self.btn_preset_linear)

        self.btn_preset_scurve = QPushButton("Kontras Sabit Hilal (S-Curve)")
        self.btn_preset_scurve.setObjectName("secondaryButton")
        self.btn_preset_scurve.setToolTip("Meningkatkan kontras midtone sabit hilal terhadap latar langit senja")
        self.btn_preset_scurve.clicked.connect(self._preset_scurve)
        v_preset.addWidget(self.btn_preset_scurve)

        self.btn_preset_shadow = QPushButton("Angkat Sinyal Redup (Shadow Lift)")
        self.btn_preset_shadow.setObjectName("secondaryButton")
        self.btn_preset_shadow.setToolTip("Mengangkat struktur sabit tipis yang sangat redup mendekati noise background")
        self.btn_preset_shadow.clicked.connect(self._preset_shadow_lift)
        v_preset.addWidget(self.btn_preset_shadow)

        self.btn_preset_highlight = QPushButton("Kompresi Terang (Highlight)")
        self.btn_preset_highlight.setObjectName("secondaryButton")
        self.btn_preset_highlight.clicked.connect(self._preset_highlight_compress)
        v_preset.addWidget(self.btn_preset_highlight)

        right_panel.addWidget(grp_preset)

        # 2. Mode Kanal
        grp_mode = QGroupBox("Mode Pemrosesan")
        grp_mode.setObjectName("infoSectionCard")
        v_mode = QVBoxLayout(grp_mode)
        v_mode.setSpacing(6)

        self.combo_channel_mode = QComboBox()
        self.combo_channel_mode.addItem("RGB (Semua Kanal)", "RGB")
        self.combo_channel_mode.addItem("Luminance (Pertahankan Warna)", "LUMINANCE")
        self.combo_channel_mode.currentIndexChanged.connect(self._on_mode_changed)
        v_mode.addWidget(self.combo_channel_mode)

        self.chk_live_preview = QCheckBox("Pratinjau Langsung (Live Preview)")
        self.chk_live_preview.setChecked(True)
        self.chk_live_preview.toggled.connect(self._on_live_preview_toggled)
        v_mode.addWidget(self.chk_live_preview)

        right_panel.addWidget(grp_mode)

        # 3. Status Koordinat Titik
        self.lbl_coord_status = QLabel("Klik & seret titik kontrol untuk mengatur kurva.")
        self.lbl_coord_status.setObjectName("infoKey")
        self.lbl_coord_status.setWordWrap(True)
        right_panel.addWidget(self.lbl_coord_status)

        right_panel.addStretch(1)
        body_layout.addLayout(right_panel, 0)
        layout.addLayout(body_layout, 1)

        # Footer Action Buttons
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(8)

        self.btn_apply = QPushButton("Terapkan (Apply)")
        self.btn_apply.setObjectName("startAutoProcessButton")
        self.btn_apply.setIcon(create_themed_vector_icon("check", night_vision=is_nv, size=16))
        self.btn_apply.setIconSize(QSize(16, 16))
        self.btn_apply.setMinimumHeight(32)
        self.btn_apply.setToolTip("Terapkan kurva secara permanen ke tampilan citra aktif")
        self.btn_apply.clicked.connect(self._on_apply_clicked)
        footer_layout.addWidget(self.btn_apply, 1)

        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setObjectName("secondaryButton")
        self.btn_reset.setIcon(create_themed_vector_icon("refresh-cw", night_vision=is_nv, size=14))
        self.btn_reset.setIconSize(QSize(14, 14))
        self.btn_reset.setMinimumHeight(32)
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        footer_layout.addWidget(self.btn_reset, 0)

        self.btn_close = QPushButton("Tutup")
        self.btn_close.setObjectName("secondaryButton")
        self.btn_close.setIcon(create_themed_vector_icon("x", night_vision=is_nv, size=14))
        self.btn_close.setIconSize(QSize(14, 14))
        self.btn_close.setMinimumHeight(32)
        self.btn_close.clicked.connect(self.close)
        footer_layout.addWidget(self.btn_close, 0)

        layout.addLayout(footer_layout)

    def mark_applied(self) -> None:
        """Memberi indikasi visual bahwa kurva berhasil diterapkan ke citra."""
        self.btn_apply.setText("Berhasil Diterapkan!")
        self.lbl_coord_status.setText("Transformasi kurva berhasil diterapkan ke citra.")
        QTimer.singleShot(1800, lambda: self.btn_apply.setText("Terapkan (Apply)"))

    def _on_point_hovered(self, msg: str) -> None:
        self.lbl_coord_status.setText(msg)

    def _on_curve_changed(self, lut: np.ndarray) -> None:
        if self.chk_live_preview.isChecked():
            mode = self.combo_channel_mode.currentData()
            self.preview_requested.emit(lut, mode)

    def _on_live_preview_toggled(self, checked: bool) -> None:
        if checked:
            lut = self.canvas.get_lut()
            mode = self.combo_channel_mode.currentData()
            self.preview_requested.emit(lut, mode)
        else:
            self.reset_requested.emit()

    def _on_mode_changed(self, _idx: int) -> None:
        if self.chk_live_preview.isChecked():
            lut = self.canvas.get_lut()
            mode = self.combo_channel_mode.currentData()
            self.preview_requested.emit(lut, mode)

    def _on_apply_clicked(self) -> None:
        lut = self.canvas.get_lut()
        mode = self.combo_channel_mode.currentData()
        self.apply_requested.emit(lut, mode)

    def _on_reset_clicked(self) -> None:
        self._preset_linear()
        self.reset_requested.emit()

    def _preset_linear(self) -> None:
        self.canvas.set_points([(0.0, 0.0), (1.0, 1.0)])

    def _preset_scurve(self) -> None:
        self.canvas.set_points([(0.0, 0.0), (0.28, 0.16), (0.72, 0.84), (1.0, 1.0)])

    def _preset_shadow_lift(self) -> None:
        self.canvas.set_points([(0.0, 0.0), (0.22, 0.44), (0.65, 0.85), (1.0, 1.0)])

    def _preset_highlight_compress(self) -> None:
        self.canvas.set_points([(0.0, 0.0), (0.40, 0.60), (0.75, 0.88), (1.0, 1.0)])
