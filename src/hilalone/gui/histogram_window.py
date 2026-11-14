"""Jendela Histogram Khusus & Analisis Statistik Citra Ilmiah HILALONE.

Menyediakan visualisasi distribusi intensitas piksel ilmiah secara interaktif:
  - Sumbu X: Intensitas / Nilai Piksel Ilmiah
  - Sumbu Y: Frekuensi / Jumlah Piksel
  - Skala: Linear & Logarithmic (penanganan aman log10(1 + count))
  - Mode: Grayscale, Red, Green, Blue, RGB Overlay, Filled vs Line
  - Bins: 256, 512, 1024, Custom
  - Range: Full, Automatic, Custom Min/Max
  - Interaksi: Hover crosshair & values, Zoom, Pan, Reset
  - Statistik Lengkap: Min, Max, Mean, Median, StdDev, Total, Zero, Saturated, Percentile
  - Ekspor: Grafik ke PNG & Tabel Data ke CSV
"""

from __future__ import annotations

import csv
import math
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from hilalone.gui.icons import create_themed_vector_icon, create_vector_icon


class HistogramCanvas(QWidget):
    """Widget kanvas grafik histogram interaktif berkinerja tinggi berbasis QPainter."""

    hover_info_changed = Signal(str)  # Informasi teks saat mouse hover di atas kurva

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(420, 260)

        # Data model
        self._data: np.ndarray | None = None
        self._bins: int = 256
        self._is_log_scale: bool = False
        self._is_filled: bool = True
        self._channel_mode: str = "AUTO"  # "AUTO", "RGB_OVERLAY", "RED", "GREEN", "BLUE", "GRAY"
        self._custom_range: tuple[float, float] | None = None

        # Histogram cache per kanal: tuple of (counts, bin_edges, bin_centers, max_count)
        self._hist_cache: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray, float]] = {}

        # Navigasi & interaksi (Zoom & Pan pada X)
        self._zoom_factor: float = 1.0
        self._pan_offset_x: float = 0.0
        self._last_mouse_pos: QPointF | None = None
        self._hover_x: float | None = None
        self._hover_y: float | None = None

    def set_data(
        self,
        arr: np.ndarray | None,
        bins: int = 256,
        is_log: bool = False,
        is_filled: bool = True,
        channel_mode: str = "AUTO",
        custom_range: tuple[float, float] | None = None,
    ) -> None:
        """Memperbarui data dan menghitung ulang bin histogram."""
        self._data = arr
        self._bins = max(16, int(bins))
        self._is_log_scale = is_log
        self._is_filled = is_filled
        self._channel_mode = channel_mode
        self._custom_range = custom_range
        self._recompute_histogram()
        self.update()

    def reset_view(self) -> None:
        self._zoom_factor = 1.0
        self._pan_offset_x = 0.0
        self.update()

    def _recompute_histogram(self) -> None:
        self._hist_cache.clear()
        if self._data is None or self._data.size == 0:
            return

        work = np.asarray(self._data, dtype=np.float64)
        finite_mask = np.isfinite(work)
        if not np.any(finite_mask):
            return

        is_rgb = (work.ndim == 3 and work.shape[2] == 3)

        # Rentang hitung
        if self._custom_range is not None:
            r_min, r_max = self._custom_range
        else:
            r_min = float(np.min(work[finite_mask]))
            r_max = float(np.max(work[finite_mask]))

        if math.isclose(r_min, r_max, abs_tol=1e-7):
            r_max = r_min + 1.0

        hist_range = (r_min, r_max)

        channels_to_calc = [0, 1, 2] if is_rgb else [0]
        for c in channels_to_calc:
            plane = work[..., c] if is_rgb else work
            plane_finite = plane[np.isfinite(plane)]
            if plane_finite.size == 0:
                continue

            counts, edges = np.histogram(plane_finite, bins=self._bins, range=hist_range)
            centers = 0.5 * (edges[:-1] + edges[1:])
            max_c = float(np.max(counts)) if counts.size > 0 else 1.0
            self._hist_cache[c] = (counts, edges, centers, max_c)

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        w, h = self.width(), self.height()
        # Latar belakang kanvas grafik
        bg_rect = QRectF(0, 0, w, h)
        painter.fillRect(bg_rect, QColor(10, 15, 26))

        # Margin area plot
        margin_left = 65
        margin_bottom = 35
        margin_top = 20
        margin_right = 20

        plot_w = max(10, w - margin_left - margin_right)
        plot_h = max(10, h - margin_top - margin_bottom)
        plot_rect = QRectF(margin_left, margin_top, plot_w, plot_h)

        # Gambar bingkai dan garis grid
        painter.setPen(QPen(QColor(30, 42, 69), 1))
        painter.drawRect(plot_rect)

        grid_pen = QPen(QColor(22, 33, 56), 1, Qt.PenStyle.DashLine)
        painter.setPen(grid_pen)
        for gy in range(1, 5):
            yy = margin_top + (plot_h * gy / 5)
            painter.drawLine(QPointF(margin_left, yy), QPointF(margin_left + plot_w, yy))
        for gx in range(1, 5):
            xx = margin_left + (plot_w * gx / 5)
            painter.drawLine(QPointF(xx, margin_top), QPointF(xx, margin_top + plot_h))

        if not self._hist_cache:
            painter.setPen(QColor(100, 116, 139))
            painter.drawText(plot_rect, Qt.AlignmentFlag.AlignCenter, "Tidak ada data citra")
            return

        # Cari nilai maksimum Y
        max_y_global = 1.0
        for c_idx, (counts, edges, centers, max_c) in self._hist_cache.items():
            if self._is_log_scale:
                val = math.log10(1.0 + max_c)
            else:
                val = max_c
            if val > max_y_global:
                max_y_global = val

        if max_y_global <= 0.0:
            max_y_global = 1.0

        # Label Sumbu Y
        painter.setPen(QColor(148, 163, 184))
        font = QFont("Segoe UI", 8)
        painter.setFont(font)
        y_label_top = f"{int(10**max_y_global - 1):,}" if self._is_log_scale else f"{int(max_y_global):,}"
        painter.drawText(QRectF(4, margin_top - 6, margin_left - 10, 16), Qt.AlignmentFlag.AlignRight, y_label_top)
        painter.drawText(QRectF(4, margin_top + plot_h - 10, margin_left - 10, 16), Qt.AlignmentFlag.AlignRight, "0")

        # Label Sumbu X (Min dan Max rentang)
        sample_edges = next(iter(self._hist_cache.values()))[1]
        x_min_val, x_max_val = float(sample_edges[0]), float(sample_edges[-1])
        painter.drawText(
            QRectF(margin_left, margin_top + plot_h + 6, 90, 18),
            Qt.AlignmentFlag.AlignLeft,
            f"{x_min_val:.2f}",
        )
        painter.drawText(
            QRectF(margin_left + plot_w - 90, margin_top + plot_h + 6, 90, 18),
            Qt.AlignmentFlag.AlignRight,
            f"{x_max_val:.2f}",
        )
        # Judul Sumbu
        scale_tag = "Log(Piksel + 1)" if self._is_log_scale else "Jumlah Piksel"
        painter.drawText(
            QRectF(margin_left + (plot_w / 2) - 100, margin_top + plot_h + 6, 200, 18),
            Qt.AlignmentFlag.AlignCenter,
            f"Nilai Intensitas (Sumbu X) — [{scale_tag}]",
        )

        # Warna kanal
        colors = {
            0: (QColor(239, 68, 68, 180), QColor(239, 68, 68, 60)),     # Red
            1: (QColor(34, 197, 94, 180), QColor(34, 197, 94, 60)),     # Green
            2: (QColor(59, 130, 246, 180), QColor(59, 130, 246, 60)),   # Blue
        }
        is_nv = getattr(self.parent(), "_is_night_vision", False) if self.parent() is not None else False
        if is_nv:
            mono_color = (QColor(239, 68, 68, 220), QColor(239, 68, 68, 70))
        else:
            mono_color = (QColor(56, 189, 248, 220), QColor(56, 189, 248, 70))

        # Tentukan kanal mana yang dirender
        is_rgb = len(self._hist_cache) > 1
        channels_to_draw = []
        if is_rgb:
            if self._channel_mode in ("AUTO", "RGB_OVERLAY"):
                channels_to_draw = [0, 1, 2]
            elif self._channel_mode == "RED":
                channels_to_draw = [0]
            elif self._channel_mode == "GREEN":
                channels_to_draw = [1]
            elif self._channel_mode == "BLUE":
                channels_to_draw = [2]
            else:
                channels_to_draw = [0, 1, 2]
        else:
            channels_to_draw = [0]

        # Gambar kurva setiap kanal
        for c_idx in channels_to_draw:
            if c_idx not in self._hist_cache:
                continue
            counts, edges, centers, _ = self._hist_cache[c_idx]
            nb = len(counts)
            if nb == 0:
                continue

            pen_col, brush_col = colors.get(c_idx, mono_color) if is_rgb else mono_color

            path = QPainterPath()
            path.moveTo(margin_left, margin_top + plot_h)

            for b_idx in range(nb):
                cnt = float(counts[b_idx])
                val_y = math.log10(1.0 + cnt) if self._is_log_scale else cnt
                y_norm = np.clip(val_y / max_y_global, 0.0, 1.0)

                px = margin_left + (b_idx / (nb - 1 if nb > 1 else 1)) * plot_w
                py = margin_top + plot_h - (y_norm * plot_h)

                if b_idx == 0:
                    path.lineTo(px, py)
                else:
                    path.lineTo(px, py)

            if self._is_filled:
                path.lineTo(margin_left + plot_w, margin_top + plot_h)
                path.closeSubpath()
                painter.setBrush(QBrush(brush_col))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)

            painter.setPen(QPen(pen_col, 1.5))
            painter.drawPath(path)

        # Crosshair & hover reading
        if self._hover_x is not None and plot_rect.contains(self._hover_x, self._hover_y or 0):
            painter.setPen(QPen(QColor(255, 255, 255, 120), 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(self._hover_x, margin_top), QPointF(self._hover_x, margin_top + plot_h))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        self._hover_x = pos.x()
        self._hover_y = pos.y()
        self.update()

        # Hitung estimasi nilai piksel & count di bawah kursor
        w, h = self.width(), self.height()
        margin_left, margin_top = 65, 20
        plot_w = max(10, w - margin_left - 20)

        if self._hist_cache and (margin_left <= pos.x() <= margin_left + plot_w):
            frac = (pos.x() - margin_left) / plot_w
            sample_edges = next(iter(self._hist_cache.values()))[1]
            x_min_val, x_max_val = float(sample_edges[0]), float(sample_edges[-1])
            curr_val = x_min_val + frac * (x_max_val - x_min_val)

            counts_info = []
            for c_idx, (counts, edges, centers, _) in self._hist_cache.items():
                bin_idx = int(np.clip(frac * len(counts), 0, len(counts) - 1))
                c_cnt = int(counts[bin_idx])
                c_name = ["R", "G", "B"][c_idx] if len(self._hist_cache) > 1 else "Pixel"
                counts_info.append(f"{c_name}:{c_cnt:,}")

            readout = f"Intensitas: {curr_val:.4f} | Jumlah: {', '.join(counts_info)}"
            self.hover_info_changed.emit(readout)
        else:
            self.hover_info_changed.emit("")

    def leaveEvent(self, event: Any) -> None:
        self._hover_x = None
        self._hover_y = None
        self.hover_info_changed.emit("")
        self.update()


class HistogramWindow(QDialog):
    """Jendela analisis histogram terpisah dan mandiri untuk HILALONE."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("HILALONE — Histogram & Image Statistics")
        self.resize(850, 560)
        self.setMinimumSize(600, 400)

        self._raw_data: np.ndarray | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        # Toolbar atas kontrol histogram
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        # Skala
        top_bar.addWidget(QLabel("Skala:"))
        self.scale_combo = QComboBox()
        self.scale_combo.addItem("Linear", False)
        self.scale_combo.addItem("Logarithmic", True)
        self.scale_combo.currentIndexChanged.connect(self._refresh_canvas)
        top_bar.addWidget(self.scale_combo)

        # Bins
        top_bar.addWidget(QLabel("Bins:"))
        self.bins_combo = QComboBox()
        self.bins_combo.addItem("256", 256)
        self.bins_combo.addItem("512", 512)
        self.bins_combo.addItem("1024", 1024)
        self.bins_combo.addItem("Custom...", -1)
        self.bins_combo.currentIndexChanged.connect(self._on_bins_changed)
        top_bar.addWidget(self.bins_combo)

        # Mode Tampilan Kanal
        top_bar.addWidget(QLabel("Kanal:"))
        self.channel_combo = QComboBox()
        self.channel_combo.addItem("RGB Overlay", "RGB_OVERLAY")
        self.channel_combo.addItem("Red", "RED")
        self.channel_combo.addItem("Green", "GREEN")
        self.channel_combo.addItem("Blue", "BLUE")
        self.channel_combo.addItem("Grayscale / Luminance", "GRAY")
        self.channel_combo.currentIndexChanged.connect(self._refresh_canvas)
        top_bar.addWidget(self.channel_combo)

        # Filled vs Line
        top_bar.addWidget(QLabel("Gaya:"))
        self.style_combo = QComboBox()
        self.style_combo.addItem("Filled Area", True)
        self.style_combo.addItem("Line Curve", False)
        self.style_combo.currentIndexChanged.connect(self._refresh_canvas)
        top_bar.addWidget(self.style_combo)

        top_bar.addStretch(1)

        # Tombol Reset View
        self.reset_btn = QPushButton("Reset View")
        self.reset_btn.setObjectName("secondaryButton")
        self.reset_btn.clicked.connect(self._on_reset_view)
        top_bar.addWidget(self.reset_btn)

        layout.addLayout(top_bar)

        # Splitter antara Kanvas Grafik dan Panel Statistik
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Kanvas Grafik
        canvas_container = QWidget()
        canv_layout = QVBoxLayout(canvas_container)
        canv_layout.setContentsMargins(0, 0, 0, 0)
        canv_layout.setSpacing(4)

        self.canvas = HistogramCanvas(self)
        self.canvas.hover_info_changed.connect(self._on_hover_info_changed)
        canv_layout.addWidget(self.canvas, 1)

        self.hover_readout_lbl = QLabel("Arahkan mouse di atas grafik untuk melihat nilai piksel...")
        self.hover_readout_lbl.setObjectName("infoKey")
        is_nv = getattr(parent, "_is_night_vision", False)
        readout_col = "#ef4444" if is_nv else "#38bdf8"
        self.hover_readout_lbl.setStyleSheet(f"font-family: monospace; font-size: 8.5pt; color: {readout_col};")
        canv_layout.addWidget(self.hover_readout_lbl)

        splitter.addWidget(canvas_container)

        # Panel Statistik di Kanan
        stats_widget = QWidget()
        stats_layout = QVBoxLayout(stats_widget)
        stats_layout.setContentsMargins(10, 0, 0, 0)
        stats_layout.setSpacing(6)

        stats_title = QLabel("STATISTIK CITRA")
        stats_title.setObjectName("sectionHeader")
        stats_layout.addWidget(stats_title)

        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(10)
        self.stats_grid.setVerticalSpacing(4)
        self._stats_labels: dict[str, QLabel] = {}

        stats_rows = [
            ("min", "Minimum:"),
            ("max", "Maximum:"),
            ("mean", "Mean:"),
            ("median", "Median:"),
            ("std", "Std Deviation:"),
            ("total", "Total Pixels:"),
            ("zero", "Zero Pixels:"),
            ("sat", "Saturated Pixels:"),
            ("p1", "Percentile 1%:"),
            ("p99", "Percentile 99%:"),
        ]
        for row, (k, title) in enumerate(stats_rows):
            k_lbl = QLabel(title)
            k_lbl.setObjectName("infoKey")
            v_lbl = QLabel("-")
            v_lbl.setObjectName("infoValue")
            v_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.stats_grid.addWidget(k_lbl, row, 0)
            self.stats_grid.addWidget(v_lbl, row, 1)
            self._stats_labels[k] = v_lbl

        stats_layout.addLayout(self.stats_grid)
        stats_layout.addStretch(1)

        # Tombol Ekspor
        self.export_graph_btn = QPushButton("Ekspor Grafik (PNG)...")
        self.export_graph_btn.setObjectName("secondaryButton")
        self.export_graph_btn.setIcon(create_themed_vector_icon("camera", night_vision=is_nv, size=14))
        self.export_graph_btn.setIconSize(QSize(14, 14))
        self.export_graph_btn.clicked.connect(self._export_graph_png)
        stats_layout.addWidget(self.export_graph_btn)

        self.export_data_btn = QPushButton("Ekspor Data (CSV)...")
        self.export_data_btn.setObjectName("secondaryButton")
        self.export_data_btn.setIcon(create_themed_vector_icon("download", night_vision=is_nv, size=14))
        self.export_data_btn.setIconSize(QSize(14, 14))
        self.export_data_btn.clicked.connect(self._export_data_csv)
        stats_layout.addWidget(self.export_data_btn)

        splitter.addWidget(stats_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

    def set_image_data(self, scientific_data: np.ndarray | None, title: str = "") -> None:
        """Memuat data array ilmiah citra asli dan memperbarui grafik & statistik."""
        self._raw_data = scientific_data
        if title:
            self.setWindowTitle(f"Histogram & Analisis Statistik Citra — {title}")
        else:
            self.setWindowTitle("Histogram & Analisis Statistik Citra")
        self._refresh_canvas()
        self._compute_statistics()

    def _on_bins_changed(self) -> None:
        val = self.bins_combo.currentData()
        if val == -1:
            custom_b, ok = QInputDialog.getInt(
                self, "Custom Bins", "Masukkan jumlah bins (16 - 4096):", value=256, minValue=16, maxValue=4096
            )
            if ok:
                self.bins_combo.setItemText(3, f"Custom ({custom_b})")
                self.bins_combo.setItemData(3, custom_b)
            else:
                self.bins_combo.setCurrentIndex(0)
        self._refresh_canvas()

    def _refresh_canvas(self) -> None:
        if self._raw_data is None:
            self.canvas.set_data(None)
            return

        bins = int(self.bins_combo.currentData())
        is_log = bool(self.scale_combo.currentData())
        is_filled = bool(self.style_combo.currentData())
        mode = str(self.channel_combo.currentData())

        self.canvas.set_data(
            self._raw_data,
            bins=bins,
            is_log=is_log,
            is_filled=is_filled,
            channel_mode=mode,
        )

    def _compute_statistics(self) -> None:
        if self._raw_data is None or self._raw_data.size == 0:
            for lbl in self._stats_labels.values():
                lbl.setText("-")
            return

        work = np.asarray(self._raw_data, dtype=np.float64)
        finite_mask = np.isfinite(work)
        finite_vals = work[finite_mask]

        if finite_vals.size == 0:
            for lbl in self._stats_labels.values():
                lbl.setText("NaN / Non-finite")
            return

        total_px = int(work.size)
        min_v = float(np.min(finite_vals))
        max_v = float(np.max(finite_vals))
        mean_v = float(np.mean(finite_vals))
        med_v = float(np.median(finite_vals))
        std_v = float(np.std(finite_vals))
        zero_px = int(np.count_nonzero(finite_vals <= 1e-6))

        # Saturasi
        if np.issubdtype(self._raw_data.dtype, np.integer):
            sat_ceiling = float(np.iinfo(self._raw_data.dtype).max)
        else:
            sat_ceiling = 1.0 if max_v <= 1.0 else max_v
        sat_px = int(np.count_nonzero(finite_vals >= sat_ceiling))

        p1_v = float(np.percentile(finite_vals, 1))
        p99_v = float(np.percentile(finite_vals, 99))

        self._stats_labels["min"].setText(f"{min_v:.4f}")
        self._stats_labels["max"].setText(f"{max_v:.4f}")
        self._stats_labels["mean"].setText(f"{mean_v:.4f}")
        self._stats_labels["median"].setText(f"{med_v:.4f}")
        self._stats_labels["std"].setText(f"{std_v:.4f}")
        self._stats_labels["total"].setText(f"{total_px:,}")
        self._stats_labels["zero"].setText(f"{zero_px:,} ({(zero_px/total_px)*100:.1f}%)")
        self._stats_labels["sat"].setText(f"{sat_px:,} ({(sat_px/total_px)*100:.1f}%)")
        self._stats_labels["p1"].setText(f"{p1_v:.4f}")
        self._stats_labels["p99"].setText(f"{p99_v:.4f}")

    def _on_hover_info_changed(self, text: str) -> None:
        if text:
            self.hover_readout_lbl.setText(text)
        else:
            self.hover_readout_lbl.setText("Arahkan mouse di atas grafik untuk melihat nilai piksel...")

    def _on_reset_view(self) -> None:
        self.canvas.reset_view()

    def export_chart_png(self, target_path: Path | str) -> bool:
        """Mengekspor kanvas grafik histogram ke berkas gambar PNG."""
        path = Path(target_path)
        pixmap = self.canvas.grab()
        return bool(pixmap.save(str(path), "PNG"))

    def export_table_csv(self, target_path: Path | str) -> bool:
        """Mengekspor tabel data frekuensi bin histogram ke berkas CSV."""
        if not self.canvas._hist_cache:
            return False
        path = Path(target_path)
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                headers = ["Bin_Index", "Bin_Left_Edge", "Bin_Center", "Bin_Right_Edge"]
                channels = sorted(self.canvas._hist_cache.keys())
                for c in channels:
                    c_name = ["Red", "Green", "Blue"][c] if len(channels) > 1 else "Pixel_Count"
                    headers.append(f"Count_{c_name}")
                writer.writerow(headers)

                nb = len(next(iter(self.canvas._hist_cache.values()))[0])
                sample_edges = next(iter(self.canvas._hist_cache.values()))[1]
                sample_centers = next(iter(self.canvas._hist_cache.values()))[2]

                for i in range(nb):
                    row = [i, f"{sample_edges[i]:.6f}", f"{sample_centers[i]:.6f}", f"{sample_edges[i+1]:.6f}"]
                    for c in channels:
                        row.append(int(self.canvas._hist_cache[c][0][i]))
                    writer.writerow(row)
            return True
        except Exception:
            return False

    def _export_graph_png(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Ekspor Grafik Histogram", "HILALONE_histogram.png", "PNG Image (*.png)"
        )
        if not path:
            return
        if self.export_chart_png(path):
            QMessageBox.information(self, "Ekspor Sukses", f"Grafik disimpan ke:\n{path}")
        else:
            QMessageBox.critical(self, "Gagal", "Gagal menyimpan gambar grafik.")

    def _export_data_csv(self) -> None:
        if not self.canvas._hist_cache:
            QMessageBox.warning(self, "Data Kosong", "Tidak ada data histogram untuk diekspor.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Ekspor Data Histogram", "HILALONE_histogram_data.csv", "CSV File (*.csv)"
        )
        if not path:
            return

        if self.export_table_csv(path):
            QMessageBox.information(self, "Ekspor Sukses", f"Data histogram berhasil diekspor ke:\n{path}")
        else:
            QMessageBox.critical(self, "Gagal Ekspor", "Terjadi kesalahan saat mengekspor data ke CSV.")
