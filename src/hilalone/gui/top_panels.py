"""Tiga Panel Utama Sejajar HILALONE (Panel A: Open Image, Panel B: Frame List, Panel C: Image Information).

Ketiga panel ini berada dalam satu baris horizontal di bagian atas workspace:
  - Memiliki tinggi visual seragam yang proporsional.
  - Responsif terhadap perubahan ukuran jendela.
  - Tidak menutupi area utama Image Viewer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from hilalone.gui.icons import create_themed_vector_icon, create_vector_icon
from hilalone.input_manager.image_reader import ImageInfo
from hilalone.input_manager.models import FrameStatus, SequenceFrameEntry


class OpenImagePanel(QFrame):
    """Panel A — Open Image: Tombol aksi impor berkas dan sequence."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("topPanelCard")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(120)
        self.setMaximumHeight(155)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        title = QLabel("PANEL A: OPEN IMAGE")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        self.btn_open_single = QPushButton("Open Image")
        self.btn_open_single.setIcon(create_vector_icon("folder-open", size=14))
        self.btn_open_single.setIconSize(QSize(14, 14))
        self.btn_open_single.setToolTip("Buka satu gambar (Single Image – tanpa stacking)")

        self.btn_open_multi = QPushButton("Multiple Images")
        self.btn_open_multi.setObjectName("secondaryButton")
        self.btn_open_multi.setIcon(create_vector_icon("images", size=14))
        self.btn_open_multi.setIconSize(QSize(14, 14))
        self.btn_open_multi.setToolTip("Pilih beberapa gambar sekaligus untuk sequence")

        self.btn_open_folder = QPushButton("Folder Sequence")
        self.btn_open_folder.setObjectName("secondaryButton")
        self.btn_open_folder.setIcon(create_vector_icon("folder", size=14))
        self.btn_open_folder.setIconSize(QSize(14, 14))
        self.btn_open_folder.setToolTip("Buka seluruh gambar yang didukung dari satu folder")

        self.btn_open_video = QPushButton("Video")
        self.btn_open_video.setObjectName("secondaryButton")
        self.btn_open_video.setIcon(create_vector_icon("video", size=14))
        self.btn_open_video.setIconSize(QSize(14, 14))
        self.btn_open_video.setToolTip("Buka berkas video (.MP4, .MOV, .AVI)")

        self.btn_open_ser = QPushButton("SER")
        self.btn_open_ser.setObjectName("secondaryButton")
        self.btn_open_ser.setIcon(create_vector_icon("film", size=14))
        self.btn_open_ser.setIconSize(QSize(14, 14))
        self.btn_open_ser.setToolTip("Buka berkas video astronomi SER (.SER)")

        self.btn_close = QPushButton("Close Image")
        self.btn_close.setObjectName("secondaryButton")
        self.btn_close.setIcon(create_vector_icon("x", size=14))
        self.btn_close.setIconSize(QSize(14, 14))
        self.btn_close.setToolTip("Tutup citra atau sequence yang sedang dibuka")

        grid.addWidget(self.btn_open_single, 0, 0)
        grid.addWidget(self.btn_open_multi, 0, 1)
        grid.addWidget(self.btn_open_folder, 0, 2)
        grid.addWidget(self.btn_open_video, 1, 0)
        grid.addWidget(self.btn_open_ser, 1, 1)
        grid.addWidget(self.btn_close, 1, 2)

        layout.addLayout(grid)

    def set_night_vision(self, active: bool) -> None:
        """Menyesuaikan palet ikon Open Image Panel dengan status Night Vision."""
        self.btn_open_single.setIcon(create_themed_vector_icon("folder-open", night_vision=active, size=14))
        self.btn_open_multi.setIcon(create_themed_vector_icon("images", night_vision=active, size=14))
        self.btn_open_folder.setIcon(create_themed_vector_icon("folder", night_vision=active, size=14))
        self.btn_open_video.setIcon(create_themed_vector_icon("video", night_vision=active, size=14))
        self.btn_open_ser.setIcon(create_themed_vector_icon("film", night_vision=active, size=14))
        self.btn_close.setIcon(create_themed_vector_icon("x", night_vision=active, size=14))


class FrameListPanel(QFrame):
    """Panel B — Frame List: Daftar frame dengan seleksi checkbox dan pemisahan visual frame aktif."""

    frame_activated = Signal(int)       # Indeks frame diklik untuk ditampilkan di viewer
    selection_changed = Signal(list)    # Daftar indeks frame yang dicentang (checked)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("topPanelCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(120)
        self.setMaximumHeight(155)

        self._entries: list[SequenceFrameEntry] = []
        self._block_signals: bool = False
        self._active_index: int = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Header baris
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        title = QLabel("PANEL B: FRAME LIST")
        title.setObjectName("panelTitle")
        header_layout.addWidget(title)

        self.counter_label = QLabel("Selected: 0 / 0 Frames")
        self.counter_label.setObjectName("panelCounter")
        header_layout.addWidget(self.counter_label)

        header_layout.addStretch(1)

        self.btn_select_all = QPushButton("Select All")
        self.btn_select_all.setObjectName("secondaryButton")
        self.btn_select_all.setIcon(create_vector_icon("check-square", size=13))
        self.btn_select_all.setIconSize(QSize(13, 13))
        self.btn_select_all.setFixedHeight(22)
        self.btn_select_all.setStyleSheet("padding: 2px 8px; font-size: 8pt;")
        self.btn_select_all.clicked.connect(self.select_all_frames)
        header_layout.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("Deselect All")
        self.btn_deselect_all.setObjectName("secondaryButton")
        self.btn_deselect_all.setIcon(create_vector_icon("square", size=13))
        self.btn_deselect_all.setIconSize(QSize(13, 13))
        self.btn_deselect_all.setFixedHeight(22)
        self.btn_deselect_all.setStyleSheet("padding: 2px 8px; font-size: 8pt;")
        self.btn_deselect_all.clicked.connect(self.deselect_all_frames)
        header_layout.addWidget(self.btn_deselect_all)

        layout.addLayout(header_layout)

        # List Widget frame
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("frameListWidget")
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        self.list_widget.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.list_widget, 1)

    def set_night_vision(self, active: bool) -> None:
        """Menyesuaikan palet ikon Frame List Panel dengan status Night Vision."""
        self.btn_select_all.setIcon(create_themed_vector_icon("check-square", night_vision=active, size=13))
        self.btn_deselect_all.setIcon(create_themed_vector_icon("square", night_vision=active, size=13))

    def populate_sequence(self, entries: list[SequenceFrameEntry]) -> None:
        """Memuat entri frame sequence ke dalam list widget dengan status badge dan seleksi jujur."""
        self._block_signals = True
        self._entries = list(entries)
        self.list_widget.clear()

        total = len(entries)
        for idx, entry in enumerate(entries):
            item = QListWidgetItem()
            badge = entry.status_badge_indonesian()
            item.setText(f"[{idx + 1:04d}] {entry.file_name}  [{badge}]")
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
            )

            # Pewarnaan status & centang default
            if entry.status == FrameStatus.ERROR:
                item.setForeground(QColor("#f87171"))  # Merah muda untuk frame gagal dibaca
                item.setCheckState(Qt.CheckState.Unchecked)  # Jangan centang frame error
            elif entry.status == FrameStatus.INCOMPATIBLE:
                item.setForeground(QColor("#facc15"))  # Kuning perhatian untuk inkompatibel
                item.setCheckState(Qt.CheckState.Unchecked)  # Pengguna harus konfirmasi eksplisit
            else:
                item.setForeground(QColor("#e2e8f0"))  # Normal kompatibel
                item.setCheckState(Qt.CheckState.Checked)

            # Tooltip informatif
            tooltip_lines = [
                f"Frame #{idx + 1}: {entry.file_name}",
                f"Status: {badge}",
            ]
            if entry.issues:
                tooltip_lines.append("Masalah: " + "; ".join(entry.issues))
            if entry.notes:
                tooltip_lines.append("Catatan: " + "; ".join(entry.notes))
            item.setToolTip("\n".join(tooltip_lines))

            item.setData(Qt.ItemDataRole.UserRole, idx)
            self.list_widget.addItem(item)

        self._block_signals = False
        self._active_index = 0
        if total > 0:
            self.list_widget.setCurrentRow(0)
        self._update_counter()
        self.selection_changed.emit(self.get_selected_frame_indices())

    def clear(self) -> None:
        self._block_signals = True
        self._entries.clear()
        self.list_widget.clear()
        self.counter_label.setText("Selected: 0 / 0 Frames")
        self._block_signals = False

    def total_count(self) -> int:
        return self.list_widget.count()

    def set_active_index(self, index: int) -> None:
        self.set_active_frame(index)

    def set_active_frame(self, index: int) -> None:
        """Menandai frame yang sedang aktif ditampilkan di viewer secara visual."""
        if 0 <= index < self.list_widget.count():
            self._active_index = index
            self._block_signals = True
            self.list_widget.setCurrentRow(index)
            self._block_signals = False

    def select_all_frames(self) -> None:
        self._block_signals = True
        for row in range(self.list_widget.count()):
            it = self.list_widget.item(row)
            it.setCheckState(Qt.CheckState.Checked)
        self._block_signals = False
        self._update_counter()
        self.selection_changed.emit(self.get_selected_frame_indices())

    def deselect_all_frames(self) -> None:
        self._block_signals = True
        for row in range(self.list_widget.count()):
            it = self.list_widget.item(row)
            it.setCheckState(Qt.CheckState.Unchecked)
        self._block_signals = False
        self._update_counter()
        self.selection_changed.emit(self.get_selected_frame_indices())

    def get_selected_frame_indices(self) -> list[int]:
        """Mengembalikan list indeks frame yang dicentang oleh pengguna."""
        indices: list[int] = []
        for row in range(self.list_widget.count()):
            it = self.list_widget.item(row)
            if it.checkState() == Qt.CheckState.Checked:
                f_idx = it.data(Qt.ItemDataRole.UserRole)
                indices.append(f_idx if f_idx is not None else row)
        return indices

    def get_selected_count(self) -> int:
        return len(self.get_selected_frame_indices())

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        f_idx = item.data(Qt.ItemDataRole.UserRole)
        if f_idx is not None:
            self.frame_activated.emit(int(f_idx))

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        if self._block_signals:
            return
        self._update_counter()
        self.selection_changed.emit(self.get_selected_frame_indices())

    def _update_counter(self) -> None:
        total = self.list_widget.count()
        selected = self.get_selected_count()
        self.counter_label.setText(f"Selected: {selected} / {total} Frames")


class ImageInfoPanel(QFrame):
    """Panel C — Image Information: Ringkasan cepat & Tombol Ikon 'i' Pembuka Dialog Metadata."""

    open_dialog_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("topPanelCard")
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.setMinimumHeight(120)
        self.setMaximumHeight(155)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        title = QLabel("PANEL C: IMAGE INFORMATION")
        title.setObjectName("panelTitle")
        header_layout.addWidget(title)

        header_layout.addStretch(1)

        # Tombol Ikon "i"
        self.btn_info_dialog = QToolButton()
        self.btn_info_dialog.setIcon(create_vector_icon("info"))
        self.btn_info_dialog.setIconSize(QSize(18, 18))
        self.btn_info_dialog.setToolTip("Buka Image Information Dialog (FITS Header & Metadata Editor)")
        self.btn_info_dialog.setStyleSheet(
            "QToolButton { background-color: #243552; border: 1px solid #3b82f6; border-radius: 4px; padding: 2px; } "
            "QToolButton:hover { background-color: #3b82f6; }"
        )
        self.btn_info_dialog.clicked.connect(self.open_dialog_requested.emit)
        header_layout.addWidget(self.btn_info_dialog)

        layout.addLayout(header_layout)

        # Grid ringkasan metadata
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(2)

        self.lbl_file = QLabel("-")
        self.lbl_file.setObjectName("panelFileName")

        self.lbl_format = QLabel("-")
        self.lbl_format.setObjectName("infoValue")

        self.lbl_res = QLabel("-")
        self.lbl_res.setObjectName("infoValue")

        self.lbl_ch_bits = QLabel("-")
        self.lbl_ch_bits.setObjectName("infoValue")

        self.grid.addWidget(QLabel("File:"), 0, 0)
        self.grid.addWidget(self.lbl_file, 0, 1)

        self.grid.addWidget(QLabel("Format:"), 1, 0)
        self.grid.addWidget(self.lbl_format, 1, 1)

        self.grid.addWidget(QLabel("Resolusi:"), 2, 0)
        self.grid.addWidget(self.lbl_res, 2, 1)

        self.grid.addWidget(QLabel("Kanal / Bit:"), 3, 0)
        self.grid.addWidget(self.lbl_ch_bits, 3, 1)

        layout.addLayout(self.grid)

    def set_night_vision(self, active: bool) -> None:
        """Menyesuaikan palet ikon dan tombol Image Info Panel dengan status Night Vision."""
        self.btn_info_dialog.setIcon(create_themed_vector_icon("info", night_vision=active, is_info=True, size=18))
        if active:
            self.btn_info_dialog.setStyleSheet(
                "QToolButton { background-color: #2b0b0b; border: 1px solid #ef4444; border-radius: 4px; padding: 2px; } "
                "QToolButton:hover { background-color: #ef4444; }"
            )
        else:
            self.btn_info_dialog.setStyleSheet(
                "QToolButton { background-color: #243552; border: 1px solid #3b82f6; border-radius: 4px; padding: 2px; } "
                "QToolButton:hover { background-color: #3b82f6; }"
            )

    def update_info(self, info: ImageInfo | SequenceFrameEntry | None) -> None:
        actual_info: ImageInfo | None = None
        if info is not None:
            if hasattr(info, "info"):
                actual_info = info.info
            elif isinstance(info, ImageInfo):
                actual_info = info

        if actual_info is None:
            self.lbl_file.setText("-")
            self.lbl_format.setText("-")
            self.lbl_res.setText("-")
            self.lbl_ch_bits.setText("-")
            return

        name = actual_info.file_name
        if len(name) > 22:
            name = name[:10] + "..." + name[-9:]
        self.lbl_file.setText(name)
        self.lbl_file.setToolTip(actual_info.file_name)

        self.lbl_format.setText(actual_info.file_format or "-")
        self.lbl_res.setText(f"{actual_info.width} × {actual_info.height} px")

        ch_name = "1 (Mono)" if actual_info.channels == 1 else f"{actual_info.channels} (RGB)"
        bit_str = f"{actual_info.original_bit_depth}-bit" if actual_info.original_bit_depth else (actual_info.dtype_str or "")
        self.lbl_ch_bits.setText(f"{ch_name} | {bit_str}")

    def clear(self) -> None:
        """Mengosongkan tampilan informasi berkas."""
        self.update_info(None)
