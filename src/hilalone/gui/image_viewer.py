"""Widget penampil gambar HILALONE (Interaktif, Presisi Ilmiah, & Ramah Pengguna).

Mendukung:
- Penskalaan Fit-to-Window otomatis dengan mempertahankan rasio aspek citra.
- Zoom In / Zoom Out bebas (ikon toolbar dan mouse wheel berpusat di kursor).
- Pan (geser) interaktif dengan mouse drag ketika diperbesar.
- Tampilan Skala Asli 1:1 (Original Size).
- Hover Magnifier / Loupe dengan pembesaran 2x, 4x, 8x yang mulus tanpa mengarang detail baru.
- Ekspor Snapshot cepat kanvas gambar tanpa elemen kontrol UI.
- Seleksi Wilayah Proteksi (Protected ROI) untuk Background Extraction.

Prinsip Ilmiah:
"ENHANCE THE SIGNAL, NEVER INVENT THE SIGNAL."
Seluruh transformasi tampilan hanya berlaku pada tingkat rendering visual (QPixmap/QImage);
array data ilmiah asli tidak pernah dimodifikasi atau diubah ukurannya.
"""

from __future__ import annotations

import math
from typing import Tuple

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QCursor,
    QImage,
    QMouseEvent,
    QPaintEvent,
    QPainter,
    QPen,
    QPixmap,
    QResizeEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGestureEvent,
    QLabel,
    QPinchGesture,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from hilalone.gui.resources import get_logo_pixmap

PLACEHOLDER_TEXT = 'Klik "Open Image" untuk membuka foto hilal'
SECONDARY_PLACEHOLDER_TEXT = (
    "Gunakan Multiple Images, Video, atau SER\n"
    "untuk membuka kumpulan frame."
)

MIN_ZOOM_FACTOR = 0.05   # 5%
MAX_ZOOM_FACTOR = 32.0   # 3200%
ZOOM_STEP_RATIO = 1.15   # Faktor pengali setiap langkah zoom (15% per step, mulus & presisi)


class ImageViewer(QLabel):
    """Widget penampil gambar dengan kemampuan zoom, pan, loupe, dan seleksi ROI."""

    # Signal saat citra dimuat atau dibersihkan
    image_changed = Signal()

    # Signal yang dipancarkan saat rasio zoom berubah: (zoom_factor: float, is_fit_mode: bool)
    zoom_changed = Signal(float, bool)

    # Signal saat kursor bergerak di atas piksel citra: (img_x: int, img_y: int, pixel_value_str: str)
    pixel_hovered = Signal(int, int, str)

    # Signal saat pengguna menyelesaikan seleksi ROI: (x: int, y: int, w: int, h: int)
    roi_selected = Signal(int, int, int, int)

    # Signal saat mode tampilan Normal/Negative View berubah: (active: bool)
    negative_view_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("imageViewer")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(200, 200)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Registrasi native pinch gesture untuk layar sentuh (touchscreen)
        self.grabGesture(Qt.GestureType.PinchGesture)

        # Sumber gambar visual dan data ilmiah asli (serta buffer tampilan visual Normal/Negative)
        self._source_qimage: QImage | None = None
        self._source_pixmap: QPixmap | None = None
        self._display_qimage: QImage | None = None
        self._display_pixmap: QPixmap | None = None
        self._negative_mode: bool = False
        self._scientific_data: np.ndarray | None = None
        self._raw_image_size: QSize = QSize(0, 0)

        # Status geometri rendering
        self._is_fit_mode: bool = True
        self._zoom_factor: float = 1.0
        self._pan_offset: QPoint = QPoint(0, 0)
        self._scaled_rect: QRect = QRect()

        # Status interaksi Pan (geser)
        self._is_panning: bool = False
        self._pan_start_pos: QPoint = QPoint(0, 0)
        self._pan_start_offset: QPoint = QPoint(0, 0)

        # Status Wilayah Proteksi (ROI)
        self.roi_selection_enabled: bool = False
        self._is_roi_selecting: bool = False
        self._roi_rect_img: QRect | None = None
        self._roi_drag_start: QPoint | None = None
        self._roi_drag_current: QPoint | None = None

        # Status Hover Magnifier / Loupe
        self._magnifier_active: bool = False
        self._magnifier_zoom: int = 2  # Pilihan: 2x, 4x, 8x
        self._cursor_widget_pos: QPoint | None = None
        self._cursor_image_pos: tuple[int, int] | None = None

        # Status Night Vision (menyesuaikan overlay & aksen visual viewer)
        self._is_night_vision: bool = False
        self._cached_empty_logo_size: int = 0
        self._cached_empty_logo_theme: bool | None = None

        # Overlay Empty State bergaya Siril di tengah Image Viewer saat belum ada gambar
        self._empty_layout = QVBoxLayout(self)
        self._empty_layout.setContentsMargins(24, 24, 24, 24)
        self._empty_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._empty_state_widget = QWidget(self)
        self._empty_state_widget.setObjectName("viewerEmptyState")
        self._empty_state_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._empty_state_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._empty_state_widget.setStyleSheet("background: transparent; border: none;")

        empty_inner_layout = QVBoxLayout(self._empty_state_widget)
        empty_inner_layout.setContentsMargins(0, 0, 0, 0)
        empty_inner_layout.setSpacing(12)
        empty_inner_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._empty_logo_label = QLabel(self._empty_state_widget)
        self._empty_logo_label.setObjectName("viewerEmptyLogo")
        self._empty_logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_logo_label.setStyleSheet("background: transparent; border: none;")

        self._empty_primary_label = QLabel(PLACEHOLDER_TEXT, self._empty_state_widget)
        self._empty_primary_label.setObjectName("viewerEmptyPrimaryText")
        self._empty_primary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_primary_label.setWordWrap(True)

        self._empty_secondary_label = QLabel(SECONDARY_PLACEHOLDER_TEXT, self._empty_state_widget)
        self._empty_secondary_label.setObjectName("viewerEmptySecondaryText")
        self._empty_secondary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_secondary_label.setWordWrap(True)

        empty_inner_layout.addWidget(self._empty_logo_label, 0, Qt.AlignmentFlag.AlignCenter)
        empty_inner_layout.addSpacing(6)
        empty_inner_layout.addWidget(self._empty_primary_label, 0, Qt.AlignmentFlag.AlignCenter)
        empty_inner_layout.addWidget(self._empty_secondary_label, 0, Qt.AlignmentFlag.AlignCenter)

        self._empty_layout.addWidget(self._empty_state_widget, 0, Qt.AlignmentFlag.AlignCenter)

        self.clear_image()

    def set_night_vision(self, active: bool) -> None:
        """Mengatur status mode Night Vision untuk menyesuaikan aksen visual overlay viewer."""
        if self._is_night_vision == active:
            return
        self._is_night_vision = active
        self._update_empty_state_visuals(force=True)
        self.update()

    def _compute_empty_logo_size(self) -> int:
        """Menghitung ukuran sisi logo Empty State secara proporsional terhadap ukuran viewport."""
        w = max(self.width(), 1)
        h = max(self.height(), 1)
        # Target sekitar 220-260 px pada viewport lapang, lalu turun proporsional di layar 1366x768
        preferred = int(min(w * 0.32, h * 0.50))
        if w >= 520 and h >= 440:
            preferred = max(220, min(260, preferred))
        else:
            preferred = min(220, preferred)
        max_safe = max(64, min(w - 80, h - 140))
        return max(64, min(preferred, max_safe))

    def _update_empty_state_visuals(self, force: bool = False) -> None:
        """Memperbarui logo, skala responsif, dan warna teks Empty State sesuai tema aktif."""
        night_vision = self._is_night_vision
        target_size = self._compute_empty_logo_size()

        theme_changed = self._cached_empty_logo_theme != night_vision
        size_changed = abs(target_size - self._cached_empty_logo_size) >= 2

        if force or theme_changed or size_changed:
            raw_pixmap = get_logo_pixmap(night_vision=night_vision)
            if raw_pixmap.isNull():
                self._empty_logo_label.setPixmap(QPixmap())
                self._empty_logo_label.setText("HILALONE")
                fallback_color = "#c84b4b" if night_vision else "#7dd3fc"
                self._empty_logo_label.setStyleSheet(
                    f"background: transparent; border: none; color: {fallback_color}; "
                    "font-size: 22px; font-weight: 700; letter-spacing: 2px;"
                )
            else:
                scaled_pixmap = raw_pixmap.scaled(
                    target_size,
                    target_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._empty_logo_label.setText("")
                self._empty_logo_label.setStyleSheet("background: transparent; border: none;")
                self._empty_logo_label.setPixmap(scaled_pixmap)
            self._cached_empty_logo_size = target_size
            self._cached_empty_logo_theme = night_vision

        if night_vision:
            primary_color = "#c84b4b"
            secondary_color = "#8c3232"
        else:
            primary_color = "#7dd3fc"
            secondary_color = "#7c93b0"

        self._empty_primary_label.setStyleSheet(
            f"background: transparent; border: none; color: {primary_color}; "
            "font-size: 13px; font-weight: 600;"
        )
        self._empty_secondary_label.setStyleSheet(
            f"background: transparent; border: none; color: {secondary_color}; "
            "font-size: 12px; font-weight: 400;"
        )

        # Pastikan teks instruksi tidak terpotong oleh wordWrap yang menyempit
        narrow_viewport = self.width() < 420
        self._empty_primary_label.setWordWrap(narrow_viewport)
        self._empty_secondary_label.setWordWrap(narrow_viewport)
        if narrow_viewport:
            wrap_width = max(220, self.width() - 64)
            self._empty_primary_label.setMaximumWidth(wrap_width)
            self._empty_secondary_label.setMaximumWidth(wrap_width)
        else:
            self._empty_primary_label.setMaximumWidth(16777215)
            self._empty_secondary_label.setMaximumWidth(16777215)
        self._empty_primary_label.adjustSize()
        self._empty_secondary_label.adjustSize()
        self._empty_state_widget.adjustSize()

    # ----------------------------------------------------------------- DATA BINDING
    def set_image(
        self,
        image: QImage,
        scientific_data: np.ndarray | None = None,
        *,
        preserve_view: bool = False,
    ) -> None:
        """Menampilkan gambar pratinjau baru dan mereferensikan scientific data jika ada."""
        old_zoom = self._zoom_factor
        old_pan = QPoint(self._pan_offset)
        old_fit = self._is_fit_mode

        self._source_qimage = image.copy()
        self._source_pixmap = QPixmap.fromImage(image)
        self._rebuild_display_buffer()
        self._scientific_data = scientific_data
        self._raw_image_size = image.size()

        if preserve_view:
            self._zoom_factor = old_zoom
            self._pan_offset = old_pan
            self._is_fit_mode = old_fit
        else:
            self._is_fit_mode = True
            self._pan_offset = QPoint(0, 0)

        self._empty_state_widget.hide()
        self._refresh()
        self.image_changed.emit()

    def _rebuild_display_buffer(self) -> None:
        """Menyusun buffer citra tampilan (Normal atau Negative) tanpa mengubah sumber ilmiah."""
        if self._source_qimage is None or self._source_qimage.isNull():
            self._display_qimage = None
            self._display_pixmap = None
            return

        if not self._negative_mode:
            self._display_qimage = self._source_qimage
            if self._source_pixmap is None or self._source_pixmap.isNull():
                self._source_pixmap = QPixmap.fromImage(self._source_qimage)
            self._display_pixmap = self._source_pixmap
            return

        inv = self._source_qimage.copy()
        if inv.format() == QImage.Format.Format_Indexed8:
            inv = inv.convertToFormat(QImage.Format.Format_RGB888)
        inv.invertPixels(QImage.InvertMode.InvertRgb)
        self._display_qimage = inv
        self._display_pixmap = QPixmap.fromImage(inv)

    def is_negative_view(self) -> bool:
        """True bila mode tampilan Negative View sedang aktif."""
        return self._negative_mode

    def set_negative_view(self, active: bool) -> None:
        """Mengaktifkan atau menonaktifkan Negative View (hanya tampilan visual, non-destruktif)."""
        target = bool(active)
        if self._negative_mode == target:
            return
        self._negative_mode = target
        self._rebuild_display_buffer()
        self.negative_view_changed.emit(target)
        if self.has_image():
            self._refresh()
        else:
            self.update()

    def toggle_negative_view(self) -> bool:
        """Membalik mode tampilan antara Normal dan Negative View lalu mengembalikan status baru."""
        new_state = not self._negative_mode
        self.set_negative_view(new_state)
        return new_state

    def set_scientific_data(self, scientific_data: np.ndarray | None) -> None:
        """Memperbarui referensi data ilmiah tanpa mengubah tampilan gambar pratinjau."""
        self._scientific_data = scientific_data

    def clear_image(self) -> None:
        """Mengosongkan tampilan viewer dan mengembalikan state ke kondisi awal."""
        was_negative = self._negative_mode
        self._source_qimage = None
        self._source_pixmap = None
        self._display_qimage = None
        self._display_pixmap = None
        self._negative_mode = False
        self._scientific_data = None
        self._raw_image_size = QSize(0, 0)
        self._is_fit_mode = True
        self._zoom_factor = 1.0
        self._pan_offset = QPoint(0, 0)
        self._scaled_rect = QRect()
        self._is_panning = False
        self._is_roi_selecting = False
        self._roi_rect_img = None
        self._cursor_widget_pos = None
        self._cursor_image_pos = None
        self.setPixmap(QPixmap())
        self.setText("")
        self._update_empty_state_visuals()
        self._empty_state_widget.show()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        if was_negative:
            self.negative_view_changed.emit(False)
        self.zoom_changed.emit(1.0, True)
        self.image_changed.emit()

    def has_image(self) -> bool:
        """True bila ada citra yang sedang dimuat pada viewer."""
        return self._source_pixmap is not None and not self._source_pixmap.isNull()

    def source_qimage(self) -> QImage | None:
        """Mengembalikan salinan QImage asli yang sedang ditampilkan."""
        return self._source_qimage.copy() if self._source_qimage is not None else None

    def scientific_data(self) -> np.ndarray | None:
        """Mengembalikan array data ilmiah float32 yang sedang aktif."""
        return self._scientific_data

    def raw_image_size(self) -> QSize:
        """Mengembalikan ukuran asli citra dalam piksel."""
        return self._raw_image_size

    def displayed_size(self) -> QSize:
        """Ukuran tampilan gambar yang sedang dirender di layar."""
        return self._scaled_rect.size() if self.has_image() else QSize(0, 0)

    def zoom_factor(self) -> float:
        """Faktor perbesaran saat ini (1.0 = 100%)."""
        return self._zoom_factor

    def is_fit_mode(self) -> bool:
        """True jika gambar saat ini dalam mode Fit to Viewport."""
        return self._is_fit_mode

    # ----------------------------------------------------------------- ZOOM & PAN
    def zoom_in(self, focus_point: QPoint | None = None) -> None:
        """Memperbesar tampilan gambar (Zoom In) dengan faktor bertahap yang mulus."""
        if not self.has_image():
            return
        if not isinstance(focus_point, QPoint):
            focus_point = None
        target_zoom = min(MAX_ZOOM_FACTOR, self._zoom_factor * ZOOM_STEP_RATIO)
        self._apply_zoom(target_zoom, focus_point=focus_point)

    def zoom_out(self, focus_point: QPoint | None = None) -> None:
        """Memperkecil tampilan gambar (Zoom Out) dengan faktor bertahap yang mulus."""
        if not self.has_image():
            return
        if not isinstance(focus_point, QPoint):
            focus_point = None
        target_zoom = max(MIN_ZOOM_FACTOR, self._zoom_factor / ZOOM_STEP_RATIO)
        self._apply_zoom(target_zoom, focus_point=focus_point)

    def fit_to_viewport(self) -> None:
        """Menyesuaikan citra agar muat sempurna di dalam area viewport (Fit the Image)."""
        if not self.has_image():
            return
        self._is_fit_mode = True
        self._pan_offset = QPoint(0, 0)
        self._refresh()

    def set_original_size(self) -> None:
        """Menampilkan citra pada skala 1:1 piksel asli (Original Size)."""
        if not self.has_image():
            return
        self._is_fit_mode = False
        self._zoom_factor = 1.0
        self._pan_offset = QPoint(0, 0)
        self._refresh()

    def rotate_cw(self) -> None:
        """Memutar citra 90° searah jarum jam (Clockwise)."""
        if not self.has_image() or self._source_qimage is None:
            return
        transform = QTransform().rotate(90)
        self._source_qimage = self._source_qimage.transformed(transform, Qt.TransformationMode.FastTransformation)
        self._source_pixmap = QPixmap.fromImage(self._source_qimage)
        self._rebuild_display_buffer()
        if self._scientific_data is not None:
            self._scientific_data = np.ascontiguousarray(np.rot90(self._scientific_data, k=-1, axes=(0, 1)))
        self._raw_image_size = self._source_qimage.size()
        self._roi_rect_img = None
        self._refresh()

    def rotate_ccw(self) -> None:
        """Memutar citra 90° berlawanan arah jarum jam (Counter-Clockwise)."""
        if not self.has_image() or self._source_qimage is None:
            return
        transform = QTransform().rotate(-90)
        self._source_qimage = self._source_qimage.transformed(transform, Qt.TransformationMode.FastTransformation)
        self._source_pixmap = QPixmap.fromImage(self._source_qimage)
        self._rebuild_display_buffer()
        if self._scientific_data is not None:
            self._scientific_data = np.ascontiguousarray(np.rot90(self._scientific_data, k=1, axes=(0, 1)))
        self._raw_image_size = self._source_qimage.size()
        self._roi_rect_img = None
        self._refresh()

    def flip_horizontal(self) -> None:
        """Membalik citra secara horizontal (Mirror Kiri-Kanan)."""
        if not self.has_image() or self._source_qimage is None:
            return
        self._source_qimage = self._source_qimage.transformed(QTransform().scale(-1, 1))
        self._source_pixmap = QPixmap.fromImage(self._source_qimage)
        self._rebuild_display_buffer()
        if self._scientific_data is not None:
            self._scientific_data = np.ascontiguousarray(np.flip(self._scientific_data, axis=1))
        self._roi_rect_img = None
        self._refresh()

    def flip_vertical(self) -> None:
        """Membalik citra secara vertikal (Mirror Atas-Bawah)."""
        if not self.has_image() or self._source_qimage is None:
            return
        self._source_qimage = self._source_qimage.transformed(QTransform().scale(1, -1))
        self._source_pixmap = QPixmap.fromImage(self._source_qimage)
        self._rebuild_display_buffer()
        if self._scientific_data is not None:
            self._scientific_data = np.ascontiguousarray(np.flip(self._scientific_data, axis=0))
        self._roi_rect_img = None
        self._refresh()

    def _apply_zoom(self, new_zoom: float, focus_point: QPoint | None = None) -> None:
        """Menerapkan faktor zoom baru dengan mempertahankan titik fokus kursor."""
        if not self.has_image():
            return
        if not isinstance(focus_point, QPoint):
            focus_point = None
        old_zoom = self._zoom_factor
        if math.isclose(old_zoom, new_zoom, rel_tol=1e-4):
            return

        avail = self.contentsRect().size()
        if focus_point is None:
            focus_point = QPoint(avail.width() // 2, avail.height() // 2)

        # Hitung koordinat relatif terhadap gambar sebelum zoom
        anchor_x = focus_point.x() - self._scaled_rect.x()
        anchor_y = focus_point.y() - self._scaled_rect.y()
        ratio = new_zoom / max(1e-5, old_zoom)

        # Perbarui offset pan agar titik anchor tetap berada di bawah fokus kursor
        new_anchor_x = anchor_x * ratio
        new_anchor_y = anchor_y * ratio
        delta_x = int(round(anchor_x - new_anchor_x))
        delta_y = int(round(anchor_y - new_anchor_y))

        self._is_fit_mode = False
        self._zoom_factor = new_zoom
        self._pan_offset += QPoint(delta_x, delta_y)
        self._clamp_pan_offset()
        self._refresh()

    def _clamp_pan_offset(self) -> None:
        """Membatasi nilai pan agar gambar tidak terlempar keluar dari batas pandang."""
        if not self.has_image() or self._is_fit_mode:
            self._pan_offset = QPoint(0, 0)
            return

        avail = self.contentsRect().size()
        w = int(round(self._raw_image_size.width() * self._zoom_factor))
        h = int(round(self._raw_image_size.height() * self._zoom_factor))

        base_ox = (avail.width() - w) // 2
        base_oy = (avail.height() - h) // 2

        # Berikan margin toleransi agar gambar tetap nyaman dipan
        margin_x = max(60, avail.width() // 3)
        margin_y = max(60, avail.height() // 3)

        min_ox = margin_x - w
        max_ox = avail.width() - margin_x
        min_oy = margin_y - h
        max_oy = avail.height() - margin_y

        cur_ox = base_ox + self._pan_offset.x()
        cur_oy = base_oy + self._pan_offset.y()

        clamped_ox = max(min_ox, min(max_ox, cur_ox))
        clamped_oy = max(min_oy, min(max_oy, cur_oy))

        self._pan_offset = QPoint(clamped_ox - base_ox, clamped_oy - base_oy)

    # ----------------------------------------------------------------- MAGNIFIER / LOUPE
    def set_magnifier_active(self, active: bool) -> None:
        """Mengaktifkan atau menonaktifkan fitur Hover Magnifier / Loupe."""
        if self._magnifier_active == active:
            return
        self._magnifier_active = active
        self._update_cursor_shape()
        self.update()

    def is_magnifier_active(self) -> bool:
        """True jika Hover Magnifier sedang aktif."""
        return self._magnifier_active

    def set_magnifier_zoom(self, zoom: int) -> None:
        """Menentukan perbesaran loupe (2x, 4x, atau 8x)."""
        if zoom in (2, 4, 8):
            self._magnifier_zoom = zoom
            if self._magnifier_active:
                self.update()

    def magnifier_zoom(self) -> int:
        """Mengembalikan faktor perbesaran loupe aktif."""
        return self._magnifier_zoom

    # ----------------------------------------------------------------- ROI INTERACTION
    def set_roi_rect(self, rect: tuple[int, int, int, int] | None) -> None:
        """Menetapkan kotak Wilayah Proteksi (x, y, w, h) dalam koordinat piksel citra."""
        if rect is None:
            self._roi_rect_img = None
        else:
            x, y, w, h = rect
            self._roi_rect_img = QRect(x, y, w, h)
        self._refresh()

    def get_roi_rect(self) -> tuple[int, int, int, int] | None:
        """Mengembalikan kotak wilayah proteksi aktif (x, y, w, h) atau None."""
        if self._roi_rect_img is None or self._roi_rect_img.isEmpty():
            return None
        return (
            self._roi_rect_img.x(),
            self._roi_rect_img.y(),
            self._roi_rect_img.width(),
            self._roi_rect_img.height(),
        )

    # ----------------------------------------------------------------- SNAPSHOT
    def render_view_pixmap(self) -> QPixmap:
        """Menghasilkan tangkapan layar bersih area gambar yang dirender (tanpa overlay loupe/UI)."""
        if not self.has_image() or self._source_pixmap is None:
            empty = QPixmap(self.size())
            empty.fill(QColor(15, 23, 42))
            return empty

        # Buat pixmap dengan ukuran persis kotak gambar yang sedang tampil
        rect = self._scaled_rect
        if rect.isEmpty():
            return QPixmap()

        canvas = QPixmap(rect.size())
        canvas.fill(Qt.GlobalColor.transparent)

        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self._zoom_factor <= 1.0)

        # Gambar konten citra sesuai skala & mode tampilan aktif (Normal / Negative)
        active_pixmap = self._display_pixmap if self._display_pixmap is not None else self._source_pixmap
        painter.drawPixmap(QRect(0, 0, rect.width(), rect.height()), active_pixmap)

        # Gambar ROI jika ada
        if self._roi_rect_img is not None and self._raw_image_size.width() > 0:
            scale_x = float(rect.width()) / float(self._raw_image_size.width())
            scale_y = float(rect.height()) / float(self._raw_image_size.height())
            rx = int(round(self._roi_rect_img.x() * scale_x))
            ry = int(round(self._roi_rect_img.y() * scale_y))
            rw = int(round(self._roi_rect_img.width() * scale_x))
            rh = int(round(self._roi_rect_img.height() * scale_y))
            painter.setPen(QPen(QColor(255, 204, 0, 240), 2))
            painter.setBrush(QColor(255, 204, 0, 48))
            painter.drawRect(rx, ry, rw, rh)

        painter.end()
        return canvas

    # ----------------------------------------------------------------- RENDERING
    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._source_pixmap is None:
            self._update_empty_state_visuals()
            return
        if self._is_fit_mode:
            self._refresh()
        else:
            self._clamp_pan_offset()
            self._refresh()

    def _refresh(self) -> None:
        """Menghitung ulang geometri kotak gambar dan memicu pembaruan tampilan."""
        if not self.has_image() or self._source_pixmap is None:
            return

        avail = self.contentsRect().size()
        if avail.width() < 1 or avail.height() < 1:
            return

        img_w = self._source_pixmap.width()
        img_h = self._source_pixmap.height()

        if self._is_fit_mode:
            fit_factor = min(
                float(avail.width()) / float(img_w),
                float(avail.height()) / float(img_h),
            )
            self._zoom_factor = fit_factor
            scaled_w = max(1, int(round(img_w * fit_factor)))
            scaled_h = max(1, int(round(img_h * fit_factor)))
            ox = (avail.width() - scaled_w) // 2
            oy = (avail.height() - scaled_h) // 2
            self._scaled_rect = QRect(ox, oy, scaled_w, scaled_h)
            self._pan_offset = QPoint(0, 0)
        else:
            scaled_w = max(1, int(round(img_w * self._zoom_factor)))
            scaled_h = max(1, int(round(img_h * self._zoom_factor)))
            base_ox = (avail.width() - scaled_w) // 2
            base_oy = (avail.height() - scaled_h) // 2
            ox = base_ox + self._pan_offset.x()
            oy = base_oy + self._pan_offset.y()
            self._scaled_rect = QRect(ox, oy, scaled_w, scaled_h)

        self.setText("")
        self._update_cursor_shape()
        self.zoom_changed.emit(self._zoom_factor, self._is_fit_mode)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Menggambar kanvas gambar, ROI overlay, dan Hover Loupe dengan rapi."""
        if not self.has_image() or self._source_pixmap is None:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. Gambar citra pada area yang telah dihitung (smooth scaling jika perkecil, fast jika pixel-level zoom)
        smooth = self._zoom_factor <= 1.0
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, smooth)
        active_pixmap = self._display_pixmap if self._display_pixmap is not None else self._source_pixmap
        painter.drawPixmap(self._scaled_rect, active_pixmap)

        # 2. Gambar overlay Wilayah Proteksi (Protected ROI) jika aktif
        if self._roi_rect_img is not None and self._raw_image_size.width() > 0:
            scale_x = float(self._scaled_rect.width()) / float(self._raw_image_size.width())
            scale_y = float(self._scaled_rect.height()) / float(self._raw_image_size.height())
            rx = self._scaled_rect.x() + int(round(self._roi_rect_img.x() * scale_x))
            ry = self._scaled_rect.y() + int(round(self._roi_rect_img.y() * scale_y))
            rw = int(round(self._roi_rect_img.width() * scale_x))
            rh = int(round(self._roi_rect_img.height() * scale_y))

            painter.setPen(QPen(QColor(255, 204, 0, 240), 2))
            painter.setBrush(QColor(255, 204, 0, 48))
            painter.drawRect(rx, ry, rw, rh)

        # 3. Gambar Hover Magnifier / Loupe jika fitur diaktifkan dan kursor di atas citra
        if (
            self._magnifier_active
            and self._cursor_widget_pos is not None
            and self._cursor_image_pos is not None
            and self._source_qimage is not None
        ):
            self._paint_magnifier_loupe(painter)

        painter.end()

    def _paint_magnifier_loupe(self, painter: QPainter) -> None:
        """Menggambar kaca pembesar (loupe) melayang yang mengikuti posisi kursor."""
        if self._cursor_widget_pos is None or self._cursor_image_pos is None or self._source_qimage is None:
            return

        cx, cy = self._cursor_widget_pos.x(), self._cursor_widget_pos.y()
        img_x, img_y = self._cursor_image_pos

        loupe_radius = 80  # Diameter loupe = 160 px
        loupe_dia = loupe_radius * 2
        zoom_mult = self._magnifier_zoom

        # Hitung area potong sumber pada citra asli (tidak menciptakan sinyal palsu)
        src_w = max(4, int(round(loupe_dia / float(zoom_mult))))
        src_h = max(4, int(round(loupe_dia / float(zoom_mult))))
        src_x0 = max(0, min(self._raw_image_size.width() - src_w, img_x - src_w // 2))
        src_y0 = max(0, min(self._raw_image_size.height() - src_h, img_y - src_h // 2))

        active_qimage = self._display_qimage if self._display_qimage is not None else self._source_qimage
        crop_img = active_qimage.copy(src_x0, src_y0, src_w, src_h)
        scaled_crop = crop_img.scaled(
            loupe_dia,
            loupe_dia,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,  # Menjaga keaslian diskrit piksel
        )

        # Tentukan letak pusat loupe agar tidak menutupi persis kursor dan tidak keluar layar
        avail_w = self.width()
        avail_h = self.height()

        # Posisi preferensi: sedikit di atas atau di kanan kursor
        lx = cx + 24
        ly = cy - loupe_dia - 24
        if lx + loupe_dia > avail_w - 12:
            lx = cx - loupe_dia - 24
        if ly < 12:
            ly = cy + 24
        if lx < 12:
            lx = 12
        if ly + loupe_dia + 28 > avail_h:
            ly = avail_h - loupe_dia - 32

        # Gambar background bayangan loupe
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        loupe_rect = QRect(lx, ly, loupe_dia, loupe_dia)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 160))
        painter.drawRoundedRect(loupe_rect.adjusted(-3, -3, 3, 3), 16, 16)

        # Gambar isi crop yang diperbesar
        painter.drawPixmap(loupe_rect.topLeft(), QPixmap.fromImage(scaled_crop))

        # Gambar bingkai lingkaran/kotak elegan (merah pada Night Vision, cyan pada Standard Dark)
        border_color = QColor(239, 68, 68, 255) if self._is_night_vision else QColor(56, 189, 248, 255)
        border_pen = QPen(border_color, 2.5)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(loupe_rect, 10, 10)

        # Gambar crosshair halus di tengah loupe
        center_x = lx + loupe_radius
        center_y = ly + loupe_radius
        ch_color = QColor(254, 202, 202, 220) if self._is_night_vision else QColor(255, 255, 255, 200)
        ch_pen = QPen(ch_color, 1.0)
        painter.setPen(ch_pen)
        painter.drawLine(center_x - 8, center_y, center_x + 8, center_y)
        painter.drawLine(center_x, center_y - 8, center_x, center_y + 8)

        # Gambar kartu teks informasi (Koordinat X/Y, Skala Loupe, & Nilai Piksel Asli)
        val_str = self._read_pixel_value_str(img_x, img_y)
        tag_text = f"X:{img_x} Y:{img_y} [{zoom_mult}×] | {val_str}"

        tag_rect = QRect(lx - 10, ly + loupe_dia + 4, loupe_dia + 20, 22)
        painter.setPen(Qt.PenStyle.NoPen)
        tag_bg = QColor(26, 8, 8, 230) if self._is_night_vision else QColor(15, 23, 42, 230)
        painter.setBrush(tag_bg)
        painter.drawRoundedRect(tag_rect, 4, 4)

        tag_text_color = QColor(254, 202, 202) if self._is_night_vision else QColor(226, 232, 240)
        painter.setPen(tag_text_color)
        font = painter.font()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, tag_text)

        painter.restore()

    def _read_pixel_value_str(self, img_x: int, img_y: int) -> str:
        """Membaca nilai piksel ilmiah asli atau nilai warna RGB layar secara presisi."""
        if self._scientific_data is not None:
            arr = self._scientific_data
            if 0 <= img_y < arr.shape[0] and 0 <= img_x < arr.shape[1]:
                val = arr[img_y, img_x]
                if np.ndim(val) == 0:
                    return f"ADU: {float(val):.4g}"
                if len(val) >= 3:
                    return f"RGB: ({float(val[0]):.4g}, {float(val[1]):.4g}, {float(val[2]):.4g})"

        if self._source_qimage is not None:
            if 0 <= img_x < self._source_qimage.width() and 0 <= img_y < self._source_qimage.height():
                col = self._source_qimage.pixelColor(img_x, img_y)
                if self._source_qimage.isGrayscale():
                    return f"Gray: {col.red()}"
                return f"RGB: ({col.red()}, {col.green()}, {col.blue()})"

        return "-"

    # ----------------------------------------------------------------- KOORDINAT & EVENT
    def _screen_to_image_coords(self, pos: QPoint) -> tuple[int, int] | None:
        """Mengonversi koordinat layar (widget) ke koordinat piksel citra asli."""
        if not self.has_image() or self._scaled_rect.isEmpty() or self._raw_image_size.isEmpty():
            return None

        rel_x = pos.x() - self._scaled_rect.x()
        rel_y = pos.y() - self._scaled_rect.y()

        if rel_x < 0 or rel_x >= self._scaled_rect.width() or rel_y < 0 or rel_y >= self._scaled_rect.height():
            return None

        img_x = int(math.floor(float(rel_x) * self._raw_image_size.width() / float(self._scaled_rect.width())))
        img_y = int(math.floor(float(rel_y) * self._raw_image_size.height() / float(self._scaled_rect.height())))

        clamped_x = max(0, min(self._raw_image_size.width() - 1, img_x))
        clamped_y = max(0, min(self._raw_image_size.height() - 1, img_y))
        return (clamped_x, clamped_y)

    def _update_cursor_shape(self) -> None:
        """Menyesuaikan bentuk kursor mouse sesuai mode aktif."""
        if not self.has_image():
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self.roi_selection_enabled:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif self._magnifier_active:
            self.setCursor(Qt.CursorShape.CrossCursor)
        elif not self._is_fit_mode and (self._scaled_rect.width() > self.width() or self._scaled_rect.height() > self.height()):
            self.setCursor(Qt.CursorShape.ClosedHandCursor if self._is_panning else Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def event(self, event: QEvent) -> bool:
        """Menangani gesture native layar sentuh (touchscreen pinch-to-zoom)."""
        if event.type() == QEvent.Type.Gesture:
            gesture_ev = event
            if isinstance(gesture_ev, QGestureEvent):
                pinch = gesture_ev.gesture(Qt.GestureType.PinchGesture)
                if pinch is not None and self.has_image():
                    scale = pinch.scaleFactor()
                    if scale > 0.0 and not math.isclose(scale, 1.0, rel_tol=1e-3):
                        # Redam laju perbesaran touch screen (damped scale) agar pergerakan halus & tidak terlalu cepat
                        damped_scale = 1.0 + (scale - 1.0) * 0.4
                        center = pinch.centerPoint().toPoint()
                        target_zoom = max(MIN_ZOOM_FACTOR, min(MAX_ZOOM_FACTOR, self._zoom_factor * damped_scale))
                        self._apply_zoom(target_zoom, focus_point=center)
                    gesture_ev.accept()
                    return True
        return super().event(event)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Zoom In / Zoom Out dengan mouse wheel atau gesture touchpad/touchscreen yang berpusat pada posisi kursor."""
        if not self.has_image():
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        if delta == 0:
            delta = event.pixelDelta().y()
            if delta == 0:
                return

        pos = event.position().toPoint()
        # Normalisasi delta: 120 units adalah satu notch roda mouse standar.
        # Trackpad dan touchscreen mengirimkan delta kecil dan beruntun (misal 10-30 units).
        num_steps = delta / 120.0
        # Batasi rentang step agar tidak melonjak tiba-tiba pada flick/swipe cepat
        num_steps = max(-2.0, min(2.0, num_steps))
        # Skala perbesaran halus bertahap proporsional terhadap jarak fisik gesture:
        zoom_mult = math.pow(ZOOM_STEP_RATIO, num_steps)
        target_zoom = max(MIN_ZOOM_FACTOR, min(MAX_ZOOM_FACTOR, self._zoom_factor * zoom_mult))
        self._apply_zoom(target_zoom, focus_point=pos)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.has_image():
            super().mousePressEvent(event)
            return

        # 1. Mode Seleksi ROI
        if self.roi_selection_enabled and event.button() == Qt.MouseButton.LeftButton:
            coords = self._screen_to_image_coords(event.position().toPoint())
            if coords is not None:
                self._is_roi_selecting = True
                self._roi_drag_start = QPoint(coords[0], coords[1])
                self._roi_drag_current = self._roi_drag_start
                return

        # 2. Mode Pan (Geser Gambar)
        is_middle_click = event.button() == Qt.MouseButton.MiddleButton
        is_left_pan = event.button() == Qt.MouseButton.LeftButton and not self.roi_selection_enabled and not self._magnifier_active

        if is_middle_click or is_left_pan:
            self._is_panning = True
            self._pan_start_pos = event.position().toPoint()
            self._pan_start_offset = QPoint(self._pan_offset.x(), self._pan_offset.y())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.has_image():
            super().mouseMoveEvent(event)
            return

        pos = event.position().toPoint()
        coords = self._screen_to_image_coords(pos)

        # 1. Update Pan jika sedang mendrag
        if self._is_panning:
            delta = pos - self._pan_start_pos
            self._is_fit_mode = False
            self._pan_offset = self._pan_start_offset + delta
            self._clamp_pan_offset()
            self._refresh()
            event.accept()
            return

        # 2. Update Seleksi ROI
        if self._is_roi_selecting and self._roi_drag_start is not None and coords is not None:
            self._roi_drag_current = QPoint(coords[0], coords[1])
            x0 = min(self._roi_drag_start.x(), self._roi_drag_current.x())
            x1 = max(self._roi_drag_start.x(), self._roi_drag_current.x())
            y0 = min(self._roi_drag_start.y(), self._roi_drag_current.y())
            y1 = max(self._roi_drag_start.y(), self._roi_drag_current.y())
            self._roi_rect_img = QRect(x0, y0, max(2, x1 - x0), max(2, y1 - y0))
            self.update()
            event.accept()
            return

        # 3. Update Hover Magnifier dan pancarkan pixel_hovered
        self._cursor_widget_pos = pos
        self._cursor_image_pos = coords
        if coords is not None:
            val_str = self._read_pixel_value_str(coords[0], coords[1])
            self.pixel_hovered.emit(coords[0], coords[1], val_str)
        else:
            self.pixel_hovered.emit(-1, -1, "-")

        if self._magnifier_active:
            self.update()

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._is_panning and (event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton)):
            self._is_panning = False
            self._update_cursor_shape()
            event.accept()
            return

        if self._is_roi_selecting and event.button() == Qt.MouseButton.LeftButton:
            self._is_roi_selecting = False
            if self._roi_rect_img is not None and self._roi_rect_img.width() >= 3 and self._roi_rect_img.height() >= 3:
                self.roi_selected.emit(
                    self._roi_rect_img.x(),
                    self._roi_rect_img.y(),
                    self._roi_rect_img.width(),
                    self._roi_rect_img.height(),
                )
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        """Menghilangkan loupe saat kursor mouse keluar dari area widget viewer."""
        self._cursor_widget_pos = None
        self._cursor_image_pos = None
        self.pixel_hovered.emit(-1, -1, "-")
        if self._magnifier_active:
            self.update()
        super().leaveEvent(event)
