"""Image Information Dialog & Metadata Editor terinspirasi dari FITS Header Editor Siril.

Menyajikan metadata citra ilmiah, video, SER, dan citra umum dalam bentuk tabel terstruktur:
    KEYWORD | VALUE | COMMENT

Fitur:
  1. Copy Selected & Copy All ke clipboard.
  2. Edit metadata non-struktural secara aman.
  3. Tambah keyword/komentar baru oleh pengguna (disimpan dalam sesi proyek).
  4. Hapus metadata kustom yang dibuat pengguna.
  5. Proteksi mutlak keyword struktural FITS (SIMPLE, BITPIX, NAXIS*, EXTEND, BZERO, BSCALE).
  6. Berkas sumber asli tidak pernah dimodifikasi (non-destructive).
"""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from hilalone.gui.icons import create_themed_vector_icon, create_vector_icon
from hilalone.input_manager.image_reader import ImageInfo

_FITS_PROTECTED_KEYWORDS = frozenset({
    "SIMPLE",
    "BITPIX",
    "NAXIS",
    "NAXIS1",
    "NAXIS2",
    "NAXIS3",
    "EXTEND",
    "BZERO",
    "BSCALE",
    "BLANK",
})

FITS_PROTECTED_KEYWORDS = _FITS_PROTECTED_KEYWORDS


class ImageInformationDialog(QDialog):
    """Jendela independen pembaca dan editor metadata terstruktur."""

    metadata_edited = Signal(str, str, str)

    def __init__(
        self,
        info: ImageInfo | None = None,
        custom_metadata: dict[str, tuple[str, str]] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Image Information & Metadata Editor")
        self.resize(750, 520)
        self.setMinimumSize(540, 360)

        self.info = info
        self._base_cards: list[tuple[str, str, str]] = []
        # custom_metadata: dict of key -> (value, comment)
        self.custom_metadata: dict[str, tuple[str, str]] = dict(custom_metadata or {})
        self._user_added_keys: set[str] = set(self.custom_metadata.keys())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        self._is_night_vision: bool = getattr(parent, "_is_night_vision", False)

        # Header keterangan sumber
        header_text = "Metadata Berkas Citra"
        if info is not None:
            header_text = f"Metadata: {info.file_name} ({info.file_format})"
        self.lbl_title = QLabel(header_text)
        title_color = "#ef4444" if self._is_night_vision else "#60a5fa"
        self.lbl_title.setStyleSheet(f"font-size: 11pt; font-weight: bold; color: {title_color};")
        layout.addWidget(self.lbl_title)

        # Tabel 3 kolom
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["KEYWORD", "VALUE", "COMMENT"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        
        # Set palet eksplisit agar gaya sistem Windows tidak menimpa warna gelap
        pal = self.table.palette()
        if self._is_night_vision:
            pal.setColor(QPalette.ColorRole.Base, QColor("#060101"))
            pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#0a0202"))
            pal.setColor(QPalette.ColorRole.Text, QColor("#fca5a5"))
            self.table.setStyleSheet(
                """
                QTableWidget {
                    background-color: #060101;
                    alternate-background-color: #0a0202;
                    gridline-color: #1a0505;
                    color: #fca5a5;
                    border: 1px solid #2b0b0b;
                    border-radius: 5px;
                }
                QTableWidget::item {
                    background-color: transparent;
                    color: #fca5a5;
                }
                QTableWidget::item:alternate {
                    background-color: #0a0202;
                }
                QTableWidget::item:selected {
                    background-color: #7f1d1d;
                    color: #ffffff;
                }
                QTableWidget::item:hover {
                    background-color: #1a0505;
                }
                QHeaderView {
                    background-color: #0a0202;
                }
                QHeaderView::section {
                    background-color: #0a0202;
                    color: #ef4444;
                    border: 1px solid #2b0b0b;
                    padding: 4px;
                    font-weight: 600;
                }
                QTableCornerButton::section {
                    background-color: #0a0202;
                    border: 1px solid #2b0b0b;
                }
                """
            )
        else:
            pal.setColor(QPalette.ColorRole.Base, QColor("#070d18"))
            pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#0d1527"))
            pal.setColor(QPalette.ColorRole.Text, QColor("#e2e8f0"))
            self.table.setStyleSheet(
                """
                QTableWidget {
                    background-color: #070d18;
                    alternate-background-color: #0d1527;
                    gridline-color: #17243c;
                    color: #e2e8f0;
                    border: 1px solid #1e2a45;
                    border-radius: 5px;
                }
                QTableWidget::item {
                    background-color: transparent;
                    color: #e2e8f0;
                }
                QTableWidget::item:alternate {
                    background-color: #0d1527;
                }
                QTableWidget::item:selected {
                    background-color: #1e3a8a;
                    color: #ffffff;
                }
                QTableWidget::item:hover {
                    background-color: #132038;
                }
                QHeaderView {
                    background-color: #0e1628;
                }
                QHeaderView::section {
                    background-color: #0e1628;
                    color: #93a6cc;
                    border: 1px solid #1e2a45;
                    padding: 4px;
                    font-weight: 600;
                }
                QTableCornerButton::section {
                    background-color: #0e1628;
                    border: 1px solid #1e2a45;
                }
                """
            )
        self.table.setPalette(pal)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        layout.addWidget(self.table, 1)

        # Action Buttons bar
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)

        self.btn_copy_sel = QPushButton("Copy Selected")
        self.btn_copy_sel.setObjectName("secondaryButton")
        self.btn_copy_sel.setIcon(
            create_themed_vector_icon("copy", night_vision=self._is_night_vision, size=14)
        )
        self.btn_copy_sel.setIconSize(QSize(14, 14))
        self.btn_copy_sel.clicked.connect(self._copy_selected)
        btn_bar.addWidget(self.btn_copy_sel)

        self.btn_copy_all = QPushButton("Copy All")
        self.btn_copy_all.setObjectName("secondaryButton")
        self.btn_copy_all.setIcon(
            create_themed_vector_icon("clipboard", night_vision=self._is_night_vision, size=14)
        )
        self.btn_copy_all.setIconSize(QSize(14, 14))
        self.btn_copy_all.clicked.connect(self._copy_all)
        btn_bar.addWidget(self.btn_copy_all)

        btn_bar.addSpacing(12)

        self.btn_edit = QPushButton("Edit...")
        self.btn_edit.setObjectName("secondaryButton")
        self.btn_edit.setIcon(
            create_themed_vector_icon("edit-3", night_vision=self._is_night_vision, size=14)
        )
        self.btn_edit.setIconSize(QSize(14, 14))
        self.btn_edit.clicked.connect(self._edit_selected_row)
        btn_bar.addWidget(self.btn_edit)

        self.btn_add = QPushButton("Add...")
        self.btn_add.setObjectName("secondaryButton")
        self.btn_add.setIcon(
            create_themed_vector_icon("plus", night_vision=self._is_night_vision, size=14)
        )
        self.btn_add.setIconSize(QSize(14, 14))
        self.btn_add.clicked.connect(self._add_custom_keyword)
        btn_bar.addWidget(self.btn_add)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("secondaryButton")
        self.btn_delete.setIcon(
            create_themed_vector_icon("trash-2", night_vision=self._is_night_vision, size=14)
        )
        self.btn_delete.setIconSize(QSize(14, 14))
        self.btn_delete.clicked.connect(self._delete_custom_keyword)
        btn_bar.addWidget(self.btn_delete)

        btn_bar.addStretch(1)

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("secondaryButton")
        self.btn_close.setIcon(
            create_themed_vector_icon("x", night_vision=self._is_night_vision, size=14)
        )
        self.btn_close.setIconSize(QSize(14, 14))
        self.btn_close.clicked.connect(self.accept)
        btn_bar.addWidget(self.btn_close)

        layout.addLayout(btn_bar)

        self._populate_table()
        self._on_table_selection_changed()

    def _on_table_selection_changed(self) -> None:
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        if not selected_rows:
            self.btn_edit.setEnabled(False)
            self.btn_delete.setEnabled(False)
            return
        row = selected_rows[0]
        item = self.table.item(row, 0)
        kw = item.text().strip().upper() if item else ""
        is_protected = kw in _FITS_PROTECTED_KEYWORDS
        self.btn_edit.setEnabled(not is_protected)
        self.btn_delete.setEnabled(not is_protected)

    def populate_metadata(self, cards: list[tuple[str, str, str]], file_name: str = "") -> None:
        """Memuat daftar kartu metadata langsung (keyword, value, comment) ke dalam tabel."""
        if file_name:
            self.lbl_title.setText(f"File: {file_name}")
        self._base_cards = [(str(k), str(v), str(c)) for k, v, c in cards]
        self._populate_table()

    def set_info(
        self,
        info: ImageInfo | None = None,
        custom_metadata: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        """Memperbarui ImageInfo aktif dan menyegarkan isi tabel metadata."""
        self.info = info
        self._base_cards = []
        if custom_metadata is not None:
            self.custom_metadata = dict(custom_metadata)
            self._user_added_keys = set(self.custom_metadata.keys())
        header_text = "Metadata Berkas Citra"
        if info is not None:
            header_text = f"File: {info.file_name} ({info.file_format})"
        self.lbl_title.setText(header_text)
        self._populate_table()

    def _add_metadata_row(self, key: str, value: str, comment: str) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(key))
        self.table.setItem(row, 1, QTableWidgetItem(value))
        self.table.setItem(row, 2, QTableWidgetItem(comment))
        self.custom_metadata[key] = (value, comment)
        self._user_added_keys.add(key)
        self.metadata_edited.emit(key, value, comment)
        self._on_table_selection_changed()

    def copy_selected_to_clipboard(self) -> str:
        return self._copy_selected()

    def copy_all_to_clipboard(self) -> str:
        return self._copy_all()

    def delete_selected(self) -> None:
        self._delete_custom_keyword()

    def _populate_table(self) -> None:
        """Mengisi tabel dengan metadata berkas dan metadata kustom pengguna."""
        self.table.setRowCount(0)
        items_to_add: list[tuple[str, str, str, bool]] = []
        # tuple: (keyword, value, comment, is_custom)

        if self._base_cards:
            for k, v, c in self._base_cards:
                k_clean = str(k).strip()
                v_clean = str(v).strip()
                c_clean = str(c).strip()
                if k_clean.upper() in ("EXPTIME", "EXPOSURE") and v_clean:
                    try:
                        sec_val = float(v_clean.rstrip("s").strip())
                        if math.isfinite(sec_val) and sec_val >= 0.0:
                            v_clean = f"{sec_val:.2f} s"
                    except (ValueError, TypeError):
                        pass
                items_to_add.append((k_clean, v_clean, c_clean, False))
        elif self.info is not None:
            # 1. Jika berkas FITS dan memiliki header cards
            if self.info.fits_header is not None and self.info.fits_header.raw_header_cards:
                for card in self.info.fits_header.raw_header_cards:
                    key = str(card.keyword).strip()
                    val = str(card.value).strip() if card.value is not None else ""
                    com = str(card.comment).strip() if card.comment is not None else ""
                    if key.upper() in ("EXPTIME", "EXPOSURE") and val:
                        try:
                            f_val = float(val)
                            if math.isfinite(f_val) and f_val >= 0.0:
                                val = f"{f_val:.2f} s"
                        except (ValueError, TypeError):
                            pass
                    items_to_add.append((key, val, com, False))
            else:
                # Metadata standar untuk non-FITS / FITS tanpa raw cards
                info = self.info
                items_to_add.append(("FILENAME", info.file_name, "Nama berkas sumber", False))
                items_to_add.append(("FORMAT", info.file_format, "Format kontainer atau file", False))
                items_to_add.append(("WIDTH", str(info.width), "Lebar citra (piksel)", False))
                items_to_add.append(("HEIGHT", str(info.height), "Tinggi citra (piksel)", False))
                items_to_add.append(("CHANNELS", str(info.channels), "Jumlah kanal sensor (1=Mono, 3=RGB)", False))
                items_to_add.append(("BITPIX", str(info.original_bit_depth), "Kedalaman bit asli sensor", False))
                items_to_add.append(("DATATYPE", info.dtype_str or "float32", "Tipe data penyimpanan internal", False))
                items_to_add.append(("ORIENT", info.exif_orientation or "Normal", "Orientasi EXIF/sensor", False))

                if info.raw_metadata is not None:
                    raw = info.raw_metadata
                    cam_name = (
                        raw.format_camera_name()
                        if hasattr(raw, "format_camera_name")
                        else f"{raw.camera_make or ''} {raw.camera_model or ''}".strip()
                    )
                    if cam_name:
                        items_to_add.append(("INSTRUME", cam_name, "Kamera / Instrumen", False))
                    if hasattr(raw, "iso_speed") and raw.iso_speed:
                        items_to_add.append(("ISOSPEED", str(raw.iso_speed), "Sensitivitas ISO sensor", False))
                    if hasattr(raw, "shutter_speed_sec") and raw.shutter_speed_sec is not None:
                        items_to_add.append(("EXPTIME", f"{raw.shutter_speed_sec} s", "Waktu eksposur (shutter)", False))
                    if hasattr(raw, "aperture_fnumber") and raw.aperture_fnumber is not None:
                        items_to_add.append(("APERTUR", f"f/{raw.aperture_fnumber:.1f}", "Bukaan lensa (aperture)", False))
                    if hasattr(raw, "focal_length_mm") and raw.focal_length_mm is not None:
                        items_to_add.append(("FOCALLEN", f"{raw.focal_length_mm:.1f} mm", "Panjang fokus lensa", False))
                    if getattr(raw, "timestamp_str", None):
                        items_to_add.append(("DATE-OBS", str(raw.timestamp_str), "Waktu observasi/perekaman", False))
                    if getattr(raw, "is_cfa_mosaic", False):
                        items_to_add.append(("BAYERPAT", getattr(raw, "cfa_pattern_str", "Mosaic"), "Pola mosaik Bayer CFA sensor", False))

                if info.video_metadata is not None:
                    v = info.video_metadata
                    items_to_add.append(("CONTAINER", v.container_format, "Format kontainer video", False))
                    items_to_add.append(("CODEC", v.codec_name, "Codec video", False))
                    items_to_add.append(("FRAMECNT", str(v.frame_count), "Total frame dalam berkas video", False))
                    items_to_add.append(("FPS", f"{v.average_rate_fps:.2f}" if v.average_rate_fps else "-", "Frame rate rata-rata", False))
                    items_to_add.append(("PIX_FMT", v.pix_fmt or "-", "Format piksel video asli", False))
                    items_to_add.append(("DURATION", f"{v.duration_sec:.2f} s" if v.duration_sec else "-", "Durasi total video", False))

                if info.ser_metadata is not None:
                    s = info.ser_metadata
                    items_to_add.append(("COLOR_ID", str(s.color_id), "ID Warna SER", False))
                    items_to_add.append(("FRAMECNT", str(s.frame_count), "Jumlah frame SER", False))
                    if s.observer:
                        items_to_add.append(("OBSERVER", s.observer, "Nama observer", False))
                    if s.instrument:
                        items_to_add.append(("TELESCOP", s.instrument, "Instrumen teleskop", False))
                    if s.telescope:
                        items_to_add.append(("TELESCOP", s.telescope, "Teleskop pengamat", False))

        # 2. Tambahkan metadata kustom pengguna
        for key, (val, com) in self.custom_metadata.items():
            # Cari jika sudah ada yang menimpa
            existing_idx = next((i for i, item in enumerate(items_to_add) if item[0] == key), None)
            if existing_idx is not None:
                items_to_add[existing_idx] = (key, val, com, True)
            else:
                items_to_add.append((key, val, com, True))

        # Masukkan ke tabel
        self.table.setRowCount(len(items_to_add))
        for row, (k, v, c, is_custom) in enumerate(items_to_add):
            k_item = QTableWidgetItem(k)
            k_item.setFlags(k_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            v_item = QTableWidgetItem(v)
            v_item.setFlags(v_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            c_item = QTableWidgetItem(c)
            c_item.setFlags(c_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            # Latar belakang eksplisit per baris bergantian untuk menjamin kontras tinggi
            if self._is_night_vision:
                bg_color = QColor("#0a0202") if (row % 2 == 1) else QColor("#060101")
            else:
                bg_color = QColor("#0d1527") if (row % 2 == 1) else QColor("#070d18")
            k_item.setBackground(bg_color)
            v_item.setBackground(bg_color)
            c_item.setBackground(bg_color)

            # Highlight jika kustom atau struktural
            if self._is_night_vision:
                if k in _FITS_PROTECTED_KEYWORDS:
                    k_item.setToolTip("Keyword struktural FITS: Dilindungi dari perubahan.")
                    k_item.setForeground(QColor("#f87171"))  # Merah terang terproteksi
                    v_item.setForeground(QColor("#fecaca"))
                    c_item.setForeground(QColor("#b91c1c"))
                elif is_custom:
                    k_item.setForeground(QColor("#ef4444"))  # Merah aksen custom
                    v_item.setForeground(QColor("#fca5a5"))
                    c_item.setForeground(QColor("#b91c1c"))
                else:
                    k_item.setForeground(QColor("#fca5a5"))
                    v_item.setForeground(QColor("#fecaca"))
                    c_item.setForeground(QColor("#b91c1c"))
            else:
                if k in _FITS_PROTECTED_KEYWORDS:
                    k_item.setToolTip("Keyword struktural FITS: Dilindungi dari perubahan.")
                    k_item.setForeground(QColor("#fbbf24"))  # Warm Amber / Gold
                    v_item.setForeground(QColor("#fef08a"))  # Light amber for value
                    c_item.setForeground(QColor("#94a3b8"))  # Muted slate
                elif is_custom:
                    k_item.setForeground(QColor("#38bdf8"))  # Sky Cyan
                    v_item.setForeground(QColor("#7dd3fc"))  # Light cyan
                    c_item.setForeground(QColor("#94a3b8"))
                else:
                    k_item.setForeground(QColor("#cbd5e1"))  # Off-white / light slate
                    v_item.setForeground(QColor("#f8fafc"))  # Crisp bright white
                    c_item.setForeground(QColor("#94a3b8"))  # Muted slate

            self.table.setItem(row, 0, k_item)
            self.table.setItem(row, 1, v_item)
            self.table.setItem(row, 2, c_item)

    def _copy_selected(self) -> str:
        """Menyalin baris terpilih ke clipboard."""
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        if not selected_rows:
            return ""

        lines: list[str] = []
        for r in selected_rows:
            k = self.table.item(r, 0).text()
            v = self.table.item(r, 1).text()
            c = self.table.item(r, 2).text()
            lines.append(f"{k:<10} = {v:<25} / {c}")

        text = "\n".join(lines)
        QGuiApplication.clipboard().setText(text)
        return text

    def _copy_all(self) -> str:
        """Menyalin seluruh isi tabel ke clipboard."""
        lines: list[str] = []
        for r in range(self.table.rowCount()):
            k = self.table.item(r, 0).text()
            v = self.table.item(r, 1).text()
            c = self.table.item(r, 2).text()
            lines.append(f"{k:<10} = {v:<25} / {c}")

        text = "\n".join(lines)
        QGuiApplication.clipboard().setText(text)
        return text

    def _edit_selected_row(self) -> None:
        """Mengedit baris yang dipilih jika bukan keyword struktural terlindungi."""
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        if not selected_rows:
            QMessageBox.warning(self, "Edit Metadata", "Pilih baris yang ingin diedit.")
            return

        row = selected_rows[0]
        keyword = self.table.item(row, 0).text()

        # Proteksi keyword struktural
        if keyword in _FITS_PROTECTED_KEYWORDS:
            QMessageBox.critical(
                self,
                "Keyword Terlindungi",
                f"Keyword '{keyword}' merupakan keyword struktural inti FITS dan dilindungi "
                "dari perubahan demi integritas ilmiah data citra.",
            )
            return

        current_val = self.table.item(row, 1).text()
        current_com = self.table.item(row, 2).text()

        new_val, ok1 = QInputDialog.getText(
            self,
            f"Edit Nilai untuk '{keyword}'",
            "Masukkan nilai baru (tidak mengubah berkas sumber fisik):",
            text=current_val,
        )
        if not ok1:
            return

        new_com, ok2 = QInputDialog.getText(
            self,
            f"Edit Komentar untuk '{keyword}'",
            "Masukkan komentar metadata (opsional):",
            text=current_com,
        )
        if not ok2:
            new_com = current_com

        self.custom_metadata[keyword] = (new_val.strip(), new_com.strip())
        self._user_added_keys.add(keyword)
        self._populate_table()

    def _add_custom_keyword(self) -> None:
        """Menambahkan keyword metadata kustom baru."""
        key, ok1 = QInputDialog.getText(
            self,
            "Tambah Keyword Metadata",
            "Nama Keyword (maksimal 8 karakter huruf besar, mis. OBJECT, TELESCOP):",
        )
        if not ok1 or not key.strip():
            return

        key_clean = key.strip().upper()[:8]
        if key_clean in _FITS_PROTECTED_KEYWORDS:
            QMessageBox.warning(
                self,
                "Keyword Terlindungi",
                f"Tidak dapat menggunakan keyword struktural '{key_clean}'.",
            )
            return

        val, ok2 = QInputDialog.getText(
            self,
            f"Nilai untuk '{key_clean}'",
            "Masukkan nilai:",
        )
        if not ok2:
            return

        com, ok3 = QInputDialog.getText(
            self,
            f"Komentar untuk '{key_clean}'",
            "Masukkan komentar:",
        )
        if not ok3:
            com = ""

        self.custom_metadata[key_clean] = (val.strip(), com.strip())
        self._user_added_keys.add(key_clean)
        self._populate_table()

    def delete_selected(self, prompt_confirm: bool = False) -> bool:
        """Menghapus metadata yang dipilih jika bukan keyword struktural terlindungi."""
        selected_rows = sorted(set(idx.row() for idx in self.table.selectedIndexes()))
        if not selected_rows:
            return False

        row = selected_rows[0]
        keyword = self.table.item(row, 0).text()

        if keyword in _FITS_PROTECTED_KEYWORDS:
            return False

        if prompt_confirm:
            confirm = QMessageBox.question(
                self,
                "Konfirmasi Hapus",
                f"Apakah Anda yakin ingin menghapus metadata '{keyword}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return False

        self.custom_metadata.pop(keyword, None)
        self._user_added_keys.discard(keyword)
        self.table.removeRow(row)
        self._on_table_selection_changed()
        return True

    def _delete_custom_keyword(self) -> None:
        """Menghapus metadata kustom yang dibuat pengguna."""
        self.delete_selected(prompt_confirm=True)
