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
from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
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
    QWheelEvent,
)
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

PLACEHOLDER_TEXT = 'Klik "Open Image" untuk membuka foto hilal'

MIN_ZOOM_FACTOR = 0.05   # 5%
MAX_ZOOM_FACTOR = 32.0   # 3200%
ZOOM_STEP_RATIO = 1.25   # Faktor pengali setiap langkah zoom


class ImageViewer(QLabel):
    """Widget penampil gambar dengan kemampuan zoom, pan, loupe, dan seleksi ROI."""

    # Signal yang dipancarkan saat rasio zoom berubah: (zoom_factor: float, is_fit_mode: bool)
    zoom_changed = Signal(float, bool)

    # Signal saat kursor bergerak di atas piksel citra: (img_x: int, img_y: int, pixel_value_str: str)
    pixel_hovered = Signal(int, int, str)

    # Signal saat pengguna menyelesaikan seleksi ROI: (x: int, y: int, w: int, h: int)
    roi_selected = Signal(int, int, int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("imageViewer")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(200, 200)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Sumber gambar visual dan data ilmiah asli
        self._source_qimage: QImage | None = None
        self._source_pixmap: QPixmap | None = None
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

        self.clear_image()

    # ----------------------------------------------------------------- DATA BINDING
    def set_image(self, image: QImage, scientific_data: np.ndarray | None = None) -> None:
        """Menampilkan gambar pratinjau baru dan mereferensikan scientific data jika ada."""
        self._source_qimage = image.copy()
        self._source_pixmap = QPixmap.fromImage(image)
        self._scientific_data = scientific_data
        self._raw_image_size = image.size()
        self._is_fit_mode = True
        self._pan_offset = QPoint(0, 0)
        self._refresh()

    def set_scientific_data(self, scientific_data: np.ndarray | None) -> None:
        """Memperbarui referensi data ilmiah tanpa mengubah tampilan gambar pratinjau."""
        self._scientific_data = scientific_data

    def clear_image(self) -> None:
        """Mengosongkan tampilan viewer dan mengembalikan state ke kondisi awal."""
        self._source_qimage = None
        self._source_pixmap = None
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
        self.setText(PLACEHOLDER_TEXT)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.zoom_changed.emit(1.0, True)

    def has_image(self) -> bool:
        """True bila ada citra yang sedang dimuat pada viewer."""
        return self._source_pixmap is not None and not self._source_pixmap.isNull()

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
        """Memperbesar tampilan gambar (Zoom In) dengan faktor bertahap."""
        if not self.has_image():
            return
        target_zoom = min(MAX_ZOOM_FACTOR, self._zoom_factor * ZOOM_STEP_RATIO)
        self._apply_zoom(target_zoom, focus_point=focus_point)

    def zoom_out(self, focus_point: QPoint | None = None) -> None:
        """Memperkecil tampilan gambar (Zoom Out) dengan faktor bertahap."""
        if not self.has_image():
            return
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

    def _apply_zoom(self, new_zoom: float, focus_point: QPoint | None = None) -> None:
        """Menerapkan faktor zoom baru dengan mempertahankan titik fokus kursor."""
        if not self.has_image():
            return
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

        # Gambar konten citra sesuai skala
        painter.drawPixmap(QRect(0, 0, rect.width(), rect.height()), self._source_pixmap)

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
        painter.drawPixmap(self._scaled_rect, self._source_pixmap)

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

        crop_img = self._source_qimage.copy(src_x0, src_y0, src_w, src_h)
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

        # Gambar bingkai lingkaran/kotak elegan (#38bdf8)
        border_pen = QPen(QColor(56, 189, 248, 255), 2.5)
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(loupe_rect, 10, 10)

        # Gambar crosshair halus di tengah loupe
        center_x = lx + loupe_radius
        center_y = ly + loupe_radius
        ch_pen = QPen(QColor(255, 255, 255, 200), 1.0)
        painter.setPen(ch_pen)
        painter.drawLine(center_x - 8, center_y, center_x + 8, center_y)
        painter.drawLine(center_x, center_y - 8, center_x, center_y + 8)

        # Gambar kartu teks informasi (Koordinat X/Y, Skala Loupe, & Nilai Piksel Asli)
        val_str = self._read_pixel_value_str(img_x, img_y)
        tag_text = f"X:{img_x} Y:{img_y} [{zoom_mult}×] | {val_str}"

        tag_rect = QRect(lx - 10, ly + loupe_dia + 4, loupe_dia + 20, 22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 23, 42, 230))
        painter.drawRoundedRect(tag_rect, 4, 4)

        painter.setPen(QColor(226, 232, 240))
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

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Zoom In / Zoom Out dengan mouse wheel yang berpusat pada posisi kursor."""
        if not self.has_image():
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        pos = event.position().toPoint()
        if delta > 0:
            self.zoom_in(focus_point=pos)
        else:
            self.zoom_out(focus_point=pos)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.has_image():
            super().mousePressEvent(event)
            return

        # 1. Mode Seleksi ROI
        if self.roi_selection_enabled and event.button() == Qt.MouseButton.LeftButton:
            coords = self._screen_to_image_coords(event.pos())
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
            self._pan_start_pos = event.pos()
            self._pan_start_offset = QPoint(self._pan_offset.x(), self._pan_offset.y())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if not self.has_image():
            super().mouseMoveEvent(event)
            return

        pos = event.pos()
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
