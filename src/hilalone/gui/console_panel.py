"""Panel Console / Scientific Processing Log profesional untuk HILALONE.

Menampilkan dan mengelola seluruh aktivitas pengolahan citra ilmiah secara transparan:
    [TIMESTAMP] [LEVEL] [MODULE] MESSAGE | DETAILS

Fitur utama:
  - Pewarnaan semantik per jenis pesan untuk tema Standard Dark dan Night Vision Red.
  - Filter kategori: All, Info, Success, Progress, Warning, Error, Critical, Debug.
  - Pilihan tingkat kedalaman (Detail Mode / Verbosity): Normal, Verbose, Debug.
  - Pencarian real-time berdasarkan kata kunci, nama berkas, modul, Run ID, atau error code
    beserta penghitung jumlah hasil.
  - Tombol aksi lengkap: Copy Selected, Copy All, Export Visible, Export Complete Log,
    Clear Console (hanya membersihkan tampilan tanpa menghapus log permanen), Open Log Folder,
    Auto-scroll / Pause Scrolling, dan Line Wrap.
  - Ukuran tombol dihitung dinamis berdasarkan metrik font tebal agar teks tidak pernah terpotong.
  - Lokasi ekspor otomatis diarahkan ke direktori sumber citra aktif (atau fallback ke folder log HILALONE).
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontMetrics,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from hilalone.core.logging import (
    ConsoleFilterCategory,
    HilaloneLogger,
    LogEntry,
    LogEvent,
    LogFilterCriteria,
    LogLevel,
    LogManager,
    LogModule,
    LogVerbosity,
    format_console_line,
    get_log_color,
    is_semibold_level,
)
from hilalone.gui.icons import create_themed_vector_icon, create_vector_icon

__all__ = [
    "ConsoleFilterCategory",
    "ConsoleLogPanel",
    "LogEntry",
    "LogEvent",
    "LogLevel",
    "LogManager",
    "LogVerbosity",
]


class ConsoleLogPanel(QFrame):
    """Widget panel Scientific Processing Log di bagian bawah aplikasi HILALONE."""

    def __init__(self, log_manager: HilaloneLogger, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("consoleCard")
        self.log_manager = log_manager
        self._is_night_vision: bool = False
        self._auto_scroll: bool = True
        self._line_wrap: bool = True
        self._displayed_events: list[LogEvent] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        # ------------------------------------------------------------------
        # Baris 1: Judul, Status Notifikasi, Filter, Detail, Search, Tutup
        # ------------------------------------------------------------------
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        title_lbl = QLabel("SCIENTIFIC PROCESSING LOG")
        title_lbl.setObjectName("sectionHeader")
        header_layout.addWidget(title_lbl)

        self.status_notice_label = QLabel("")
        self.status_notice_label.setObjectName("infoKey")
        self.status_notice_label.setVisible(False)
        header_layout.addWidget(self.status_notice_label)

        header_layout.addStretch(1)

        # Filter Level Dropdown
        lbl_filter = QLabel("Filter:")
        lbl_filter.setObjectName("infoKey")
        header_layout.addWidget(lbl_filter)

        self.filter_combo = QComboBox()
        self.filter_combo.setMinimumHeight(28)
        self.filter_combo.setMinimumWidth(105)
        self.filter_combo.setToolTip("Filter kategori pesan log yang ditampilkan")
        self.filter_combo.addItem("All", ConsoleFilterCategory.ALL.value)
        self.filter_combo.addItem("Info", ConsoleFilterCategory.INFO.value)
        self.filter_combo.addItem("Success", ConsoleFilterCategory.SUCCESS.value)
        self.filter_combo.addItem("Progress", ConsoleFilterCategory.PROGRESS.value)
        self.filter_combo.addItem("Warning", ConsoleFilterCategory.WARNING.value)
        self.filter_combo.addItem("Error", ConsoleFilterCategory.ERROR.value)
        self.filter_combo.addItem("Critical", ConsoleFilterCategory.CRITICAL.value)
        self.filter_combo.addItem("Debug", ConsoleFilterCategory.DEBUG.value)
        self.filter_combo.currentIndexChanged.connect(self._on_filter_or_search_changed)
        header_layout.addWidget(self.filter_combo)

        # Verbosity / Detail Mode Dropdown
        lbl_verb = QLabel("Detail:")
        lbl_verb.setObjectName("infoKey")
        header_layout.addWidget(lbl_verb)

        self.verbosity_combo = QComboBox()
        self.verbosity_combo.setMinimumHeight(28)
        self.verbosity_combo.setMinimumWidth(102)
        self.verbosity_combo.setToolTip("Tingkat kedalaman informasi yang dicatat (Normal / Verbose / Debug)")
        self.verbosity_combo.addItem("Normal", LogVerbosity.NORMAL.value)
        self.verbosity_combo.addItem("Verbose", LogVerbosity.VERBOSE.value)
        self.verbosity_combo.addItem("Debug", LogVerbosity.DEBUG.value)
        # Sinkronkan nilai awal dropdown dengan verbosity logger saat ini tanpa memicu log perubahan
        init_verb = self.log_manager.verbosity.value
        for i in range(self.verbosity_combo.count()):
            if self.verbosity_combo.itemData(i) == init_verb:
                self.verbosity_combo.setCurrentIndex(i)
                break
        self.verbosity_combo.currentIndexChanged.connect(self._on_verbosity_combo_changed)
        header_layout.addWidget(self.verbosity_combo)

        # Search Input + Result Counter
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Cari kata kunci, file, modul, Run ID...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setMinimumHeight(28)
        self.search_input.setMinimumWidth(180)
        self.search_input.setToolTip(
            "Cari pesan berdasarkan kata kunci, nama file, modul, Run ID, atau kode error"
        )
        self.search_input.textChanged.connect(self._on_filter_or_search_changed)
        header_layout.addWidget(self.search_input)

        self.search_count_label = QLabel("")
        self.search_count_label.setObjectName("panelCounter")
        self.search_count_label.setMinimumWidth(64)
        header_layout.addWidget(self.search_count_label)

        self.toggle_hide_btn = QPushButton("Tutup")
        self.toggle_hide_btn.setObjectName("secondaryButton")
        self.toggle_hide_btn.setIcon(create_vector_icon("chevron-down", size=14))
        self.toggle_hide_btn.setIconSize(QSize(14, 14))
        self.toggle_hide_btn.setMinimumHeight(28)
        self.toggle_hide_btn.clicked.connect(self.hide)
        header_layout.addWidget(self.toggle_hide_btn)

        layout.addLayout(header_layout)

        # ------------------------------------------------------------------
        # Baris 2: Action Toolbar (Copy, Export, Clear, Folder, Scroll, Wrap)
        # ------------------------------------------------------------------
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(6)

        self.copy_selected_btn = QPushButton("Copy Selected")
        self.copy_selected_btn.setObjectName("secondaryButton")
        self.copy_selected_btn.setIcon(create_vector_icon("copy", size=14))
        self.copy_selected_btn.setIconSize(QSize(14, 14))
        self.copy_selected_btn.setMinimumHeight(28)
        self.copy_selected_btn.setToolTip("Salin teks log yang sedang dipilih ke clipboard")
        self.copy_selected_btn.clicked.connect(self.copy_selected_to_clipboard)
        action_layout.addWidget(self.copy_selected_btn)

        self.copy_all_btn = QPushButton("Copy All")
        self.copy_all_btn.setObjectName("secondaryButton")
        self.copy_all_btn.setIcon(create_vector_icon("clipboard", size=14))
        self.copy_all_btn.setIconSize(QSize(14, 14))
        self.copy_all_btn.setMinimumHeight(28)
        self.copy_all_btn.setToolTip("Salin seluruh baris log yang sedang ditampilkan ke clipboard")
        self.copy_all_btn.clicked.connect(self.copy_all_to_clipboard)
        action_layout.addWidget(self.copy_all_btn)

        self.export_visible_btn = QPushButton("Export Visible")
        self.export_visible_btn.setObjectName("secondaryButton")
        self.export_visible_btn.setIcon(create_vector_icon("download", size=14))
        self.export_visible_btn.setIconSize(QSize(14, 14))
        self.export_visible_btn.setMinimumHeight(28)
        self.export_visible_btn.setToolTip("Ekspor baris log yang sedang tampil (sesuai filter/pencarian)")
        self.export_visible_btn.clicked.connect(self._on_export_visible_clicked)
        action_layout.addWidget(self.export_visible_btn)

        self.export_btn = QPushButton("Export Complete Log...")
        self.export_btn.setObjectName("secondaryButton")
        self.export_btn.setIcon(create_vector_icon("download", size=14))
        self.export_btn.setIconSize(QSize(14, 14))
        self.export_btn.setMinimumHeight(28)
        self.export_btn.setToolTip("Ekspor seluruh catatan sesi tanpa terpengaruh filter atau Clear Console")
        self.export_btn.clicked.connect(self._on_export_clicked)
        self.export_complete_btn = self.export_btn
        action_layout.addWidget(self.export_btn)

        self.open_folder_btn = QPushButton("Open Log Folder")
        self.open_folder_btn.setObjectName("secondaryButton")
        self.open_folder_btn.setIcon(create_vector_icon("folder-open", size=14))
        self.open_folder_btn.setIconSize(QSize(14, 14))
        self.open_folder_btn.setMinimumHeight(28)
        self.open_folder_btn.setToolTip("Buka folder penyimpanan file log permanen di Windows Explorer")
        self.open_folder_btn.clicked.connect(self.open_log_folder)
        action_layout.addWidget(self.open_folder_btn)

        action_layout.addStretch(1)

        self.auto_scroll_btn = QPushButton("Auto-scroll: ON")
        self.auto_scroll_btn.setObjectName("secondaryButton")
        self.auto_scroll_btn.setCheckable(True)
        self.auto_scroll_btn.setChecked(True)
        self.auto_scroll_btn.setMinimumHeight(28)
        self.auto_scroll_btn.setToolTip("Aktifkan untuk mengikuti pesan terbaru; matikan (Pause) untuk menahan posisi baca")
        self.auto_scroll_btn.toggled.connect(self._on_auto_scroll_toggled)
        action_layout.addWidget(self.auto_scroll_btn)

        self.pause_scroll_btn = QPushButton("Pause Scroll")
        self.pause_scroll_btn.setObjectName("secondaryButton")
        self.pause_scroll_btn.setCheckable(True)
        self.pause_scroll_btn.setChecked(False)
        self.pause_scroll_btn.setMinimumHeight(28)
        self.pause_scroll_btn.setToolTip("Tahan posisi gulir agar tidak berpindah saat pesan baru masuk")
        self.pause_scroll_btn.toggled.connect(self._on_pause_scroll_toggled)
        action_layout.addWidget(self.pause_scroll_btn)

        self.wrap_btn = QPushButton("Line Wrap")
        self.wrap_btn.setObjectName("secondaryButton")
        self.wrap_btn.setCheckable(True)
        self.wrap_btn.setChecked(True)
        self.wrap_btn.setMinimumHeight(28)
        self.wrap_btn.setToolTip("Aktifkan atau nonaktifkan pelipatan baris otomatis (Line Wrapping)")
        self.wrap_btn.toggled.connect(self._on_line_wrap_toggled)
        action_layout.addWidget(self.wrap_btn)

        self.clear_btn = QPushButton("Clear Console")
        self.clear_btn.setObjectName("secondaryButton")
        self.clear_btn.setIcon(create_vector_icon("trash-2", size=14))
        self.clear_btn.setIconSize(QSize(14, 14))
        self.clear_btn.setMinimumHeight(28)
        self.clear_btn.setToolTip(
            "Bersihkan tampilan layar Console (file log permanen dan riwayat sesi tetap tersimpan)"
        )
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        action_layout.addWidget(self.clear_btn)

        layout.addLayout(action_layout)

        # Pastikan seluruh tombol memiliki lebar minimum yang mencukupi teks tebal + padding
        self._ensure_all_button_widths()

        # ------------------------------------------------------------------
        # Baris 3: Area Teks Monospaced Berwarna Semantik
        # ------------------------------------------------------------------
        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(5000)
        self.text_edit.setMinimumHeight(135)
        self.text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.text_edit)

        # Sambungkan sinyal logger (AutoConnection otomatis thread-safe dari QThread)
        self.log_manager.entry_logged.connect(self._on_entry_logged)
        self.log_manager.log_cleared.connect(self._on_log_cleared)
        self.log_manager.view_cleared.connect(self._on_view_cleared)
        self.log_manager.verbosity_changed.connect(self._on_logger_verbosity_changed)

        # Muat entri awal jika sudah ada
        self._rebuild_view()

    # ------------------------------------------------------------------ Button Sizing & Anti-Clipping
    @staticmethod
    def _configure_button_width(
        btn: QPushButton,
        candidate_texts: tuple[str, ...],
        *,
        has_icon: bool = False,
        extra_padding: int = 28,
    ) -> int:
        """Menghitung dan menetapkan ``minimumWidth`` tombol berdasarkan metrik font tebal (Bold).

        Hal ini mencegah terpotongnya huruf pertama/terakhir (seperti 'A' pada 'Auto-scroll: ON')
        saat QSS mengubah ``font-weight`` menjadi ``600`` pada state ``:checked`` atau saat
        lebar jendela mengecil.
        """
        bold_font = QFont(btn.font())
        bold_font.setPointSize(max(10, bold_font.pointSize() if bold_font.pointSize() > 0 else 10))
        bold_font.setWeight(QFont.Weight.Bold)
        fm = QFontMetrics(bold_font)

        max_text_w = max(fm.horizontalAdvance(t) for t in candidate_texts)
        icon_w = 22 if has_icon else 0
        min_w = max_text_w + icon_w + extra_padding
        btn.setMinimumWidth(min_w)
        btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        return min_w

    def _ensure_all_button_widths(self) -> None:
        """Memastikan seluruh tombol pada toolbar Console tidak pernah mengalami pemotongan teks."""
        self._configure_button_width(
            self.auto_scroll_btn,
            ("Auto-scroll: ON", "Auto-scroll: OFF"),
            has_icon=False,
            extra_padding=34,
        )
        self._configure_button_width(
            self.pause_scroll_btn,
            ("Pause Scroll",),
            has_icon=False,
            extra_padding=28,
        )
        self._configure_button_width(
            self.wrap_btn,
            ("Line Wrap",),
            has_icon=False,
            extra_padding=28,
        )
        self._configure_button_width(
            self.copy_selected_btn,
            ("Copy Selected",),
            has_icon=True,
            extra_padding=26,
        )
        self._configure_button_width(
            self.copy_all_btn,
            ("Copy All",),
            has_icon=True,
            extra_padding=26,
        )
        self._configure_button_width(
            self.export_visible_btn,
            ("Export Visible",),
            has_icon=True,
            extra_padding=26,
        )
        self._configure_button_width(
            self.export_btn,
            ("Export Complete Log...",),
            has_icon=True,
            extra_padding=26,
        )
        self._configure_button_width(
            self.open_folder_btn,
            ("Open Log Folder",),
            has_icon=True,
            extra_padding=26,
        )
        self._configure_button_width(
            self.clear_btn,
            ("Clear Console",),
            has_icon=True,
            extra_padding=26,
        )
        self._configure_button_width(
            self.toggle_hide_btn,
            ("Tutup",),
            has_icon=True,
            extra_padding=24,
        )

    # ------------------------------------------------------------------ Tema & Warna Semantik
    def set_night_vision(self, active: bool) -> None:
        """Menyesuaikan warna ikon dan palet warna log secara real-time saat tema berubah."""
        self._is_night_vision = bool(active)
        self.clear_btn.setIcon(create_themed_vector_icon("trash-2", night_vision=active, size=14))
        self.export_btn.setIcon(create_themed_vector_icon("download", night_vision=active, size=14))
        self.export_visible_btn.setIcon(create_themed_vector_icon("download", night_vision=active, size=14))
        self.copy_selected_btn.setIcon(create_themed_vector_icon("copy", night_vision=active, size=14))
        self.copy_all_btn.setIcon(create_themed_vector_icon("clipboard", night_vision=active, size=14))
        self.open_folder_btn.setIcon(create_themed_vector_icon("folder-open", night_vision=active, size=14))
        self.toggle_hide_btn.setIcon(create_themed_vector_icon("chevron-down", night_vision=active, size=14))

        self._ensure_all_button_widths()
        # Render ulang tampilan log dengan palet warna tema baru tanpa mengubah isi pesan
        self._rebuild_view()

    def current_filter_criteria(self) -> LogFilterCriteria:
        """Menyusun objek ``LogFilterCriteria`` berdasarkan status kontrol UI saat ini."""
        cat_str = str(self.filter_combo.currentData() or ConsoleFilterCategory.ALL.value)
        try:
            cat = ConsoleFilterCategory(cat_str)
        except ValueError:
            cat = ConsoleFilterCategory.ALL

        verb_str = str(self.verbosity_combo.currentData() or LogVerbosity.NORMAL.value)
        try:
            verb = LogVerbosity(verb_str)
        except ValueError:
            verb = LogVerbosity.NORMAL

        query = self.search_input.text().strip()
        return LogFilterCriteria(
            category=cat,
            verbosity=verb,
            search_query=query,
            preserve_historical_verbosity=True,
        )

    def set_filter_category(self, category: ConsoleFilterCategory | str) -> None:
        """Mengatur kategori filter tampilan secara terprogram."""
        target = category.value if isinstance(category, ConsoleFilterCategory) else str(category).strip().upper()
        for idx in range(self.filter_combo.count()):
            if self.filter_combo.itemData(idx) == target:
                self.filter_combo.setCurrentIndex(idx)
                return

    def set_search_query(self, query: str) -> None:
        """Mengatur kata kunci pencarian secara terprogram."""
        self.search_input.setText(query)

    def set_verbosity(self, verbosity: LogVerbosity | str) -> None:
        """Mengatur tingkat verbosity pada dropdown dan logger."""
        target = verbosity.value if isinstance(verbosity, LogVerbosity) else str(verbosity).strip().upper()
        self.verbosity_combo.blockSignals(True)
        for idx in range(self.verbosity_combo.count()):
            if self.verbosity_combo.itemData(idx) == target:
                self.verbosity_combo.setCurrentIndex(idx)
                break
        self.verbosity_combo.blockSignals(False)
        self.log_manager.set_verbosity(target, log_change=True)
        self._rebuild_view()

    # ------------------------------------------------------------------ Rendering & Scrolling
    def _build_level_format(self, level: LogLevel, *, bold: bool | None = None) -> QTextCharFormat:
        """Membuat format karakter berwarna semantik untuk level tertentu dan tema aktif."""
        fmt = QTextCharFormat()
        hex_color = get_log_color(level, night_vision=self._is_night_vision)
        fmt.setForeground(QColor(hex_color))
        use_bold = is_semibold_level(level) if bold is None else bold
        fmt.setFontWeight(QFont.Weight.DemiBold if use_bold else QFont.Weight.Normal)
        return fmt

    def _build_char_format(self, entry: LogEvent) -> QTextCharFormat:
        """Membuat format karakter berwarna semantik sesuai level pesan dan tema aktif."""
        return self._build_level_format(entry.level)

    def _resolve_value_status_format(self, val_str: str) -> QTextCharFormat:
        """Menentukan warna semantik khusus untuk nilai status pada baris ringkasan."""
        upper = val_str.strip().upper()
        if upper.startswith(("SUCCESS", "COMPLETED", "APPLIED", "SAVED", "VERIFIED")):
            return self._build_level_format(LogLevel.SUCCESS, bold=True)
        if upper.startswith(("SKIPPED", "NOT USED", "READY_TO_SAVE", "IN-MEMORY")):
            return self._build_level_format(LogLevel.SKIPPED, bold=False)
        if upper.startswith(("FAILED", "ERROR", "UNVERIFIED")):
            return self._build_level_format(LogLevel.ERROR, bold=True)
        if upper.startswith(("CANCELLED", "WARNING", "PARTIAL")):
            return self._build_level_format(LogLevel.WARNING, bold=True)
        return self._build_level_format(LogLevel.INFO, bold=False)

    def _insert_entry_with_cursor(self, cursor: QTextCursor, entry: LogEvent) -> None:
        """Menyisipkan satu LogEvent ke QTextCursor; untuk blok SUMMARY mewarnai hanya nilai status."""
        line_text = format_console_line(entry)
        if entry.raw_block is None:
            cursor.insertText(line_text, self._build_char_format(entry))
            return

        fmt_section = self._build_level_format(LogLevel.SECTION, bold=True)
        fmt_subhead = self._build_level_format(LogLevel.PROGRESS, bold=True)
        fmt_info = self._build_level_format(LogLevel.INFO, bold=False)

        block_lines = line_text.splitlines()
        for idx, b_line in enumerate(block_lines):
            if idx > 0:
                cursor.insertBlock()
            stripped = b_line.strip()
            if not stripped:
                continue
            if stripped.startswith("=") or "SUMMARY" in stripped or "AUTOMATED PROCESSING" in stripped:
                cursor.insertText(b_line, fmt_section)
            elif stripped.startswith("-") or (stripped.isupper() and " : " not in b_line):
                cursor.insertText(b_line, fmt_subhead)
            elif " : " in b_line:
                sep_pos = b_line.find(" : ")
                prefix_part = b_line[: sep_pos + 3]
                value_part = b_line[sep_pos + 3 :]
                cursor.insertText(prefix_part, fmt_info)
                cursor.insertText(value_part, self._resolve_value_status_format(value_part))
            else:
                cursor.insertText(b_line, fmt_info)

    def _append_entry_formatted(self, entry: LogEvent) -> None:
        """Menambahkan satu ``LogEvent`` ke ``text_edit`` dengan warna semantik dan kontrol scroll."""
        scrollbar = self.text_edit.verticalScrollBar()
        prev_scroll_val = scrollbar.value() if scrollbar is not None else 0

        doc = self.text_edit.document()
        cursor = QTextCursor(doc)
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not doc.isEmpty():
            cursor.insertBlock()

        self._insert_entry_with_cursor(cursor, entry)

        if self._auto_scroll and scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())
        elif scrollbar is not None:
            scrollbar.setValue(prev_scroll_val)

    def _append_entry_text(self, entry: LogEvent) -> None:
        """Alias kompatibilitas untuk menambahkan entri ke tampilan."""
        self._append_entry_formatted(entry)

    def _rebuild_view(self) -> None:
        """Menyusun ulang isi ``text_edit`` berdasarkan filter, pencarian, dan palet warna aktif."""
        criteria = self.current_filter_criteria()
        matched = self.log_manager.filter_entries(criteria, respect_view_clear=True)
        self._displayed_events = matched

        scrollbar = self.text_edit.verticalScrollBar()
        prev_scroll_val = scrollbar.value() if scrollbar is not None else 0

        self.text_edit.clear()
        doc = self.text_edit.document()
        cursor = QTextCursor(doc)

        for idx, entry in enumerate(matched):
            if idx > 0:
                cursor.insertBlock()
            self._insert_entry_with_cursor(cursor, entry)

        self._update_counter_label(len(matched))

        if self._auto_scroll and scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())
        elif scrollbar is not None:
            scrollbar.setValue(min(prev_scroll_val, scrollbar.maximum()))

    def _update_counter_label(self, matched_count: int) -> None:
        total_visible = len(self.log_manager.visible_entries_after_clear)
        has_query = bool(self.search_input.text().strip())
        cat_val = self.filter_combo.currentData()
        if has_query or cat_val != ConsoleFilterCategory.ALL.value:
            self.search_count_label.setText(f"{matched_count} / {total_visible} baris")
        else:
            self.search_count_label.setText(f"{matched_count} baris")

    # ------------------------------------------------------------------ Signal Handlers
    def _on_entry_logged(self, entry: LogEvent) -> None:
        if self.status_notice_label.isVisible():
            self.status_notice_label.setVisible(False)

        criteria = self.current_filter_criteria()
        if criteria.matches(entry):
            self._displayed_events.append(entry)
            self._append_entry_formatted(entry)
        self._update_counter_label(len(self._displayed_events))

    def _on_log_cleared(self) -> None:
        self._displayed_events.clear()
        self.text_edit.clear()
        self._update_counter_label(0)

    def _on_view_cleared(self) -> None:
        self._displayed_events.clear()
        self.text_edit.clear()
        self.status_notice_label.setText("Console view cleared. Session log remains available.")
        self.status_notice_label.setVisible(True)
        self._update_counter_label(0)

    def _on_clear_clicked(self) -> None:
        """Membersihkan tampilan Console saja tanpa menghapus riwayat pemrosesan atau berkas log."""
        self.log_manager.clear_console_view()

    def _on_filter_or_search_changed(self, *_args: object) -> None:
        self._rebuild_view()

    def _on_verbosity_combo_changed(self, _index: int) -> None:
        verb_str = str(self.verbosity_combo.currentData() or LogVerbosity.NORMAL.value)
        self.log_manager.set_verbosity(verb_str, log_change=True)
        self._rebuild_view()

    def _on_logger_verbosity_changed(self, verb_str: str) -> None:
        self.verbosity_combo.blockSignals(True)
        for i in range(self.verbosity_combo.count()):
            if self.verbosity_combo.itemData(i) == verb_str:
                self.verbosity_combo.setCurrentIndex(i)
                break
        self.verbosity_combo.blockSignals(False)
        self._rebuild_view()

    def _on_auto_scroll_toggled(self, checked: bool) -> None:
        self._auto_scroll = bool(checked)
        self.auto_scroll_btn.setText("Auto-scroll: ON" if checked else "Auto-scroll: OFF")
        self._configure_button_width(
            self.auto_scroll_btn,
            ("Auto-scroll: ON", "Auto-scroll: OFF"),
            has_icon=False,
            extra_padding=34,
        )
        self.pause_scroll_btn.blockSignals(True)
        self.pause_scroll_btn.setChecked(not checked)
        self.pause_scroll_btn.blockSignals(False)
        if checked:
            sb = self.text_edit.verticalScrollBar()
            if sb is not None:
                sb.setValue(sb.maximum())

    def _on_pause_scroll_toggled(self, paused: bool) -> None:
        self.auto_scroll_btn.setChecked(not paused)

    def _on_line_wrap_toggled(self, wrapped: bool) -> None:
        self._line_wrap = bool(wrapped)
        mode = (
            QPlainTextEdit.LineWrapMode.WidgetWidth
            if wrapped
            else QPlainTextEdit.LineWrapMode.NoWrap
        )
        self.text_edit.setLineWrapMode(mode)

    # ------------------------------------------------------------------ Action Methods
    def copy_selected_to_clipboard(self) -> str:
        """Menyalin teks yang sedang diblok/dipilih pada Console ke clipboard sistem."""
        cursor = self.text_edit.textCursor()
        selected = cursor.selectedText()
        cleaned = selected.replace("\u2029", "\n").replace("\u2028", "\n")
        if cleaned:
            QApplication.clipboard().setText(cleaned)
        return cleaned

    def copy_all_to_clipboard(self) -> str:
        """Menyalin seluruh baris yang sedang ditampilkan pada Console ke clipboard sistem."""
        all_text = self.text_edit.toPlainText()
        QApplication.clipboard().setText(all_text)
        return all_text

    def open_log_folder(self) -> Path:
        """Membuka folder penyimpanan log permanen di file manager sistem operasi."""
        folder = self.log_manager.log_dir
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if "PYTEST_CURRENT_TEST" not in os.environ:
                url = QUrl.fromLocalFile(str(folder.resolve()))
                if not QDesktopServices.openUrl(url) and sys.platform == "win32":
                    os.startfile(str(folder.resolve()))  # type: ignore[attr-defined]
        except Exception:
            pass
        return folder

    def get_default_export_path(
        self,
        *,
        visible_only: bool = True,
        complete: bool | None = None,
        ext: str = "log",
        emit_fallback_log: bool = True,
    ) -> Path:
        """Menentukan path lengkap awal untuk dialog Save File saat Export Visible / Complete Log.

        Mengarahkan secara otomatis ke folder sumber citra aktif, atau ke folder log HILALONE
        jika belum ada citra/sequence yang dibuka.
        """
        if complete is not None:
            is_visible = not complete
        else:
            is_visible = visible_only
        target_dir = self.log_manager.resolve_export_directory(emit_fallback_log=emit_fallback_log)
        kind_label = "Visible" if is_visible else "Complete"
        default_name = self.log_manager.default_export_filename(ext, kind=kind_label)
        return target_dir / default_name

    def _confirm_overwrite(self, target_path: Path) -> bool:
        """Meminta konfirmasi pengguna apabila berkas tujuan sudah ada."""
        ans = QMessageBox.question(
            self,
            "Konfirmasi Timpa Berkas Log",
            f"Berkas '{target_path.name}' sudah ada di:\n{target_path.parent}\n\nApakah Anda ingin menimpanya?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return ans == QMessageBox.StandardButton.Yes

    def _on_export_visible_clicked(self) -> None:
        self._run_export_dialog(visible_only=True)

    def _on_export_clicked(self) -> None:
        self._run_export_dialog(visible_only=False)

    def _run_export_dialog(self, *, visible_only: bool) -> Path | None:
        dialog_title = (
            "Ekspor Log yang Terlihat (Export Visible Log)"
            if visible_only
            else "Ekspor Seluruh Log Sesi (Export Complete Session Log)"
        )
        initial_path = self.get_default_export_path(
            visible_only=visible_only,
            ext="log",
            emit_fallback_log=True,
        )
        file_filter = (
            "Log File (*.log);;"
            "Structured JSON Lines (*.jsonl);;"
            "Text File (*.txt);;"
            "CSV File (*.csv);;"
            "JSON File (*.json);;"
            "Semua Berkas (*.*)"
        )
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self,
            dialog_title,
            str(initial_path),
            file_filter,
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not file_path:
            return None

        p = Path(file_path)
        ext = p.suffix.lower().lstrip(".")
        sel_low = selected_filter.lower()
        if not ext:
            if "jsonl" in sel_low:
                p = p.with_suffix(".jsonl")
            elif "csv" in sel_low:
                p = p.with_suffix(".csv")
            elif "json" in sel_low:
                p = p.with_suffix(".json")
            elif "txt" in sel_low:
                p = p.with_suffix(".txt")
            else:
                p = p.with_suffix(".log")

        if p.exists() and not self._confirm_overwrite(p):
            return None

        try:
            if visible_only:
                out_p = self.log_manager.export_visible_log(p, self.current_filter_criteria())
            else:
                out_p = self.log_manager.export_complete_log(p)

            self.log_manager.info(
                LogModule.EXPORT,
                f"{'Visible' if visible_only else 'Complete'} log exported to: {out_p}",
                details={"output_location": str(out_p), "mode": "VISIBLE" if visible_only else "COMPLETE"},
            )
            QMessageBox.information(
                self,
                "Ekspor Log Berhasil",
                f"Console log berhasil disimpan ke:\n{out_p}",
            )
            return out_p
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Gagal Ekspor Log",
                f"Terjadi kesalahan saat menyimpan log:\n{exc}",
            )
            return None
