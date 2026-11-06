"""Jendela utama HILALONE v0.1: Single Image, Multiple Images, Sequence Navigator, & Image Viewer.

Berkas ini hanya mengurus TAMPILAN. Pembacaan, pengurutan, dan validasi berkas
dilakukan oleh ``hilalone.input_manager`` (sesuai aturan: GUI tanpa logika
pemrosesan).
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hilalone import APP_NAME, APP_SUBTITLE
from hilalone.gui.image_viewer import ImageViewer
from hilalone.input_manager.adapters.fits_reader import FitsHduSummary
from hilalone.input_manager.adapters.tiff_reader import TiffPageSummary
from hilalone.input_manager.image_reader import (
    ImageInfo,
    ImageReadError,
    MultiHduFitsError,
    MultiPageTiffError,
    supported_extensions,
)
from hilalone.input_manager.models import (
    FrameStatus,
    InputMode,
    SequenceFrameEntry,
)
from hilalone.input_manager.sequence_manager import SequenceManager

EMPTY_VALUE = "-"
STATUS_EMPTY = "Belum ada gambar dibuka."

# Baris panel informasi: (kunci internal, label yang ditampilkan).
_INFO_ROWS: tuple[tuple[str, str], ...] = (
    ("input_mode", "Mode input"),
    ("sequence_info", "Sequence"),
    ("file_name", "Nama file"),
    ("file_format", "Format"),
    ("width", "Lebar"),
    ("height", "Tinggi"),
    ("channels", "Kanal"),
    ("bit_depth", "Bit depth"),
    ("orientation", "Orientasi"),
    ("fits_metadata", "Header FITS"),
)


def format_channels(info: ImageInfo) -> str:
    """Teks jumlah kanal; jujur 'Tidak diketahui' bila tidak dapat dipastikan."""
    if info.channels is None:
        return "Tidak diketahui"
    names = {1: "monokrom", 3: "RGB", 4: "RGBA"}
    return f"{info.channels} ({names.get(info.channels, 'kanal')})"


def format_bit_depth(info: ImageInfo) -> str:
    """Teks bit depth yang membedakan data asli dan preview layar."""
    if info.original_bit_depth is None:
        original = "tidak diketahui"
    else:
        suffix = " float" if info.original_is_float else ""
        if info.stored_dtype_str and info.dtype_str and info.stored_dtype_str != info.dtype_str:
            dtype_note = f" ({info.dtype_str}; stored {info.stored_dtype_str})"
        else:
            dtype_note = ""
        original = f"{info.original_bit_depth}-bit{suffix}{dtype_note}"
    return f"Original: {original} | Display Preview: {info.preview_bit_depth}-bit"


def format_orientation(info: ImageInfo) -> str:
    """Teks orientasi EXIF asli, dan catatan bahwa rotasi hanya untuk preview."""
    if not info.orientation_applied:
        return info.exif_orientation
    return (
        f"{info.exif_orientation} (hanya pada preview)\n"
        f"Ukuran tersimpan: {info.stored_width} × {info.stored_height} px"
    )


def format_fits_metadata(info: ImageInfo) -> str:
    """Teks ringkasan metadata FITS bila berkas adalah FITS, atau '-' bila bukan."""
    if info.fits_header is None:
        return EMPTY_VALUE
    return info.fits_header.summary_text()


class MainWindow(QMainWindow):
    """Jendela utama aplikasi HILALONE."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} – {APP_SUBTITLE}")
        self.resize(1200, 800)
        self.setMinimumSize(800, 560)
        self._last_dir: str = str(Path.home())
        self._info_values: dict[str, QLabel] = {}
        self.sequence_manager = SequenceManager()
        self._updating_combo: bool = False

        self._build_ui()
        self.close_image()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 8)
        root.setSpacing(10)

        root.addLayout(self._build_header())
        line = QFrame()
        line.setObjectName("headerLine")
        line.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(line)
        root.addLayout(self._build_toolbar())
        root.addWidget(self._build_sequence_nav_bar())

        body = QHBoxLayout()
        body.setSpacing(16)
        self.viewer = ImageViewer()
        body.addWidget(self.viewer, 1)
        body.addWidget(self._build_info_panel())
        root.addLayout(body, 1)

        self.statusBar().setObjectName("statusBar")

    def _build_header(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(0)
        self.title_label = QLabel(APP_NAME)
        self.title_label.setObjectName("headerTitle")
        self.subtitle_label = QLabel(APP_SUBTITLE)
        self.subtitle_label.setObjectName("headerSubtitle")
        layout.addWidget(self.title_label)
        layout.addWidget(self.subtitle_label)
        return layout

    def _build_toolbar(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(10)

        self.open_button = QPushButton("Open Image")
        self.open_button.setToolTip("Buka satu gambar (Single Image – tanpa stacking)")
        self.open_button.clicked.connect(self.open_image_dialog)

        self.open_multi_button = QPushButton("Multiple Images")
        self.open_multi_button.setObjectName("secondaryButton")
        self.open_multi_button.setToolTip("Pilih beberapa file gambar sekaligus (Stacking wajib)")
        self.open_multi_button.clicked.connect(self.open_multiple_images_dialog)

        self.open_folder_button = QPushButton("Open Folder Sequence")
        self.open_folder_button.setObjectName("secondaryButton")
        self.open_folder_button.setToolTip("Buka seluruh gambar yang didukung dari satu folder")
        self.open_folder_button.clicked.connect(self.open_folder_sequence_dialog)

        self.open_video_button = QPushButton("Video")
        self.open_video_button.setObjectName("secondaryButton")
        self.open_video_button.setToolTip("Buka berkas video (akan tersedia pada sub-tahap Video Reader)")
        self.open_video_button.clicked.connect(self.open_video_placeholder)

        self.close_button = QPushButton("Close Image")
        self.close_button.setObjectName("secondaryButton")
        self.close_button.clicked.connect(self.close_image)

        layout.addWidget(self.open_button)
        layout.addWidget(self.open_multi_button)
        layout.addWidget(self.open_folder_button)
        layout.addWidget(self.open_video_button)
        layout.addWidget(self.close_button)
        layout.addStretch(1)
        return layout

    def _build_sequence_nav_bar(self) -> QWidget:
        self.nav_bar = QWidget()
        layout = QHBoxLayout(self.nav_bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        lbl = QLabel("Daftar Frame:")
        lbl.setObjectName("infoKey")

        self.prev_frame_button = QPushButton("◀ Sebelumnya")
        self.prev_frame_button.setObjectName("secondaryButton")
        self.prev_frame_button.clicked.connect(self.show_previous_frame)

        self.frame_combo = QComboBox()
        self.frame_combo.currentIndexChanged.connect(self._on_frame_combo_changed)

        self.next_frame_button = QPushButton("Berikutnya ▶")
        self.next_frame_button.setObjectName("secondaryButton")
        self.next_frame_button.clicked.connect(self.show_next_frame)

        layout.addWidget(lbl)
        layout.addWidget(self.prev_frame_button)
        layout.addWidget(self.frame_combo, 1)
        layout.addWidget(self.next_frame_button)
        return self.nav_bar

    def _build_info_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("infoPanel")
        panel.setFixedWidth(320)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        title = QLabel("INFORMASI GAMBAR")
        title.setObjectName("infoTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        for row, (key, label_text) in enumerate(_INFO_ROWS):
            key_label = QLabel(label_text)
            key_label.setObjectName("infoKey")
            key_label.setAlignment(Qt.AlignmentFlag.AlignTop)
            value_label = QLabel(EMPTY_VALUE)
            value_label.setObjectName("infoValue")
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(key_label, row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value_label, row, 1)
            self._info_values[key] = value_label
        layout.addLayout(grid)
        layout.addStretch(1)
        return panel

    # ------------------------------------------------------------- aksi
    def _file_dialog_filter(self) -> str:
        """Filter dialog dibuat dinamis dari format yang didukung."""
        patterns = " ".join(f"*.{ext}" for ext in supported_extensions())
        return f"Gambar yang didukung ({patterns});;Semua file (*)"

    def open_image_dialog(self) -> None:
        """Menampilkan dialog pemilih satu berkas lalu memuat gambar yang dipilih."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Buka Satu Gambar (Single Image)", self._last_dir, self._file_dialog_filter()
        )
        if not file_path:
            return
        self._last_dir = str(Path(file_path).parent)
        self.load_path(file_path)

    def open_multiple_images_dialog(self) -> None:
        """Menampilkan dialog pemilih banyak berkas sekaligus."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Pilih Beberapa Gambar (Multiple Images)",
            self._last_dir,
            self._file_dialog_filter(),
        )
        if not file_paths:
            return
        self._last_dir = str(Path(file_paths[0]).parent)
        self.load_sequence_paths(file_paths)

    def open_folder_sequence_dialog(self) -> None:
        """Menampilkan dialog pemilih satu folder sequence."""
        folder = QFileDialog.getExistingDirectory(
            self,
            "Pilih Folder Sequence Gambar",
            self._last_dir,
        )
        if not folder:
            return
        self._last_dir = folder
        self.load_folder_sequence(folder)

    def open_video_placeholder(self) -> None:
        """Menampilkan informasi bahwa fitur Video Reader akan diaktifkan pada sub-tahap berikutnya."""
        QMessageBox.information(
            self,
            "Fitur Video Belum Tersedia",
            (
                "Pembaca berkas Video (MP4, MOV, AVI, dan SER) belum diaktifkan pada Sub-Tahap 2A ini.\n\n"
                "Fitur Video Reader akan dikembangkan pada sub-tahap Input Manager berikutnya."
            ),
        )

    def _ask_tiff_page(self, file_name: str, pages: tuple[TiffPageSummary, ...]) -> int | None:
        """Meminta pengguna memilih halaman untuk TIFF multi-halaman."""
        items = [p.label() for p in pages]
        chosen, ok = QInputDialog.getItem(
            self,
            "Pilih Halaman TIFF",
            (
                f"File '{file_name}' memiliki {len(pages)} halaman.\n"
                "Pilih halaman yang ingin ditampilkan:"
            ),
            items,
            0,
            False,
        )
        if not ok or not chosen:
            return None
        for p in pages:
            if p.label() == chosen:
                return p.index
        return 0

    def _ask_fits_hdu(
        self,
        file_name: str,
        image_hdus: tuple[FitsHduSummary, ...],
        total_hdu_count: int,
    ) -> int | None:
        """Meminta pengguna memilih HDU gambar bila FITS memiliki beberapa HDU gambar."""
        items = [h.label() for h in image_hdus]
        chosen, ok = QInputDialog.getItem(
            self,
            "Pilih HDU FITS",
            (
                f"File FITS '{file_name}' memiliki {len(image_hdus)} HDU berisi gambar "
                f"(dari total {total_hdu_count} HDU).\n"
                "Pilih HDU yang ingin ditampilkan:"
            ),
            items,
            0,
            False,
        )
        if not ok or not chosen:
            return None
        for h in image_hdus:
            if h.label() == chosen:
                return h.index
        return image_hdus[0].index

    def load_path(
        self,
        file_path: str | Path,
        page_index: int | None = None,
        hdu_index: int | None = None,
    ) -> bool:
        """Memuat satu gambar sebagai mode Single Image (stacking_required = False)."""
        try:
            loaded = self.sequence_manager.open_single_file(
                file_path, page_index=page_index, hdu_index=hdu_index
            )
        except MultiPageTiffError as multi_err:
            selected_page = self._ask_tiff_page(multi_err.path.name, multi_err.pages)
            if selected_page is None:
                return False
            return self.load_path(file_path, page_index=selected_page)
        except MultiHduFitsError as fits_err:
            selected_hdu = self._ask_fits_hdu(
                fits_err.path.name,
                fits_err.image_hdus,
                fits_err.total_hdu_count,
            )
            if selected_hdu is None:
                return False
            return self.load_path(file_path, hdu_index=selected_hdu)
        except ImageReadError as error:
            self._show_error(str(error))
            return False
        except Exception as error:
            self._show_error(f"Terjadi kesalahan tak terduga saat membuka gambar: {error}")
            return False

        self.viewer.set_image(loaded.preview)
        self._refresh_sequence_controls()
        self._show_info(loaded.info, self.sequence_manager.entries[0])
        self.close_button.setEnabled(True)
        self.statusBar().showMessage(
            f"Dibuka (Single Image): {loaded.info.file_name}  |  {loaded.info.width} × {loaded.info.height} px"
        )
        return True

    def load_sequence_paths(self, paths: Iterable[str | Path], sort_by: str = "natural") -> bool:
        """Memuat daftar beberapa berkas gambar ke dalam Sequence Manager secara lazy."""
        path_list = [Path(p) for p in paths]
        if len(path_list) == 1:
            return self.load_path(path_list[0])

        try:
            report = self.sequence_manager.open_files(path_list, sort_by=sort_by)
        except ImageReadError as error:
            self._show_error(str(error))
            return False
        except Exception as error:
            self._show_error(f"Terjadi kesalahan saat memeriksa sequence gambar: {error}")
            return False

        return self._finalize_sequence_open(report.warnings)

    def load_folder_sequence(self, folder_path: str | Path, sort_by: str = "natural") -> bool:
        """Memuat seluruh berkas gambar yang didukung dari sebuah folder."""
        try:
            report = self.sequence_manager.open_folder(folder_path, sort_by=sort_by)
        except ImageReadError as error:
            self._show_error(str(error))
            return False
        except Exception as error:
            self._show_error(f"Terjadi kesalahan saat membuka folder sequence: {error}")
            return False

        return self._finalize_sequence_open(report.warnings)

    def _finalize_sequence_open(self, warnings: tuple[str, ...]) -> bool:
        self._refresh_sequence_controls()
        self.close_button.setEnabled(True)

        # Pilih frame pertama yang dapat dipratinjau (atau indeks 0 bila semuanya error)
        first_previewable = 0
        for entry in self.sequence_manager.entries:
            if entry.can_preview():
                first_previewable = entry.frame_index
                break

        self.select_sequence_frame(first_previewable, show_error_dialog=False)

        if warnings:
            joined = "\n• ".join(warnings[:10])
            more = f"\n... dan {len(warnings) - 10} peringatan lainnya." if len(warnings) > 10 else ""
            self._show_warning(
                "Peringatan Kompatibilitas Sequence:\n"
                f"Metode pengurutan: {self.sequence_manager.sorting_method}\n\n"
                f"• {joined}{more}\n\n"
                "Catatan: Tidak ada frame yang dihapus diam-diam. Frame yang berbeda ukuran/kanal "
                "ditandai TIDAK KOMPATIBEL untuk stacking tetapi tetap dapat dipratinjau satu per satu."
            )
        return True

    def select_sequence_frame(self, index: int, show_error_dialog: bool = True) -> bool:
        """Menampilkan pratinjau frame pada indeks tertentu (lazy load on demand)."""
        entries = self.sequence_manager.entries
        if index < 0 or index >= len(entries):
            return False

        self._updating_combo = True
        self.frame_combo.setCurrentIndex(index)
        self._updating_combo = False
        self._update_nav_buttons(index, len(entries))

        entry = entries[index]
        if entry.status == FrameStatus.ERROR:
            self.viewer.clear_image()
            self._show_error_entry_info(entry)
            msg = "; ".join(entry.issues) if entry.issues else "Berkas rusak atau tidak dapat dibaca."
            self.statusBar().showMessage(f"Frame [{index + 1}/{len(entries)}] GAGAL DIBACA: {entry.file_name}")
            if show_error_dialog:
                self._show_error(f"Frame [{index + 1}/{len(entries)}] '{entry.file_name}':\n{msg}")
            return False

        try:
            loaded = self.sequence_manager.load_frame(index)
        except ImageReadError as err:
            self.viewer.clear_image()
            self._show_error_entry_info(entry)
            if show_error_dialog:
                self._show_error(str(err))
            return False

        updated_entry = self.sequence_manager.entries[index]
        self.viewer.set_image(loaded.preview)
        self._show_info(loaded.info, updated_entry)
        self.statusBar().showMessage(
            f"Frame [{index + 1}/{len(entries)}]: {loaded.info.file_name}  |  "
            f"{loaded.info.width} × {loaded.info.height} px  |  {updated_entry.status_badge_indonesian()}"
        )
        return True

    def show_previous_frame(self) -> None:
        idx = self.sequence_manager.current_index
        if idx > 0:
            self.select_sequence_frame(idx - 1)

    def show_next_frame(self) -> None:
        idx = self.sequence_manager.current_index
        if 0 <= idx < self.sequence_manager.frame_count - 1:
            self.select_sequence_frame(idx + 1)

    def _on_frame_combo_changed(self, index: int) -> None:
        if self._updating_combo or index < 0:
            return
        self.select_sequence_frame(index)

    def _refresh_sequence_controls(self) -> None:
        entries = self.sequence_manager.entries
        total = len(entries)
        self._updating_combo = True
        self.frame_combo.clear()
        for entry in entries:
            self.frame_combo.addItem(entry.dropdown_label(total))
        self._updating_combo = False

        has_items = total > 0
        self.frame_combo.setEnabled(has_items)
        self._update_nav_buttons(self.sequence_manager.current_index, total)

    def _update_nav_buttons(self, current_idx: int, total: int) -> None:
        self.prev_frame_button.setEnabled(total > 1 and current_idx > 0)
        self.next_frame_button.setEnabled(total > 1 and 0 <= current_idx < total - 1)

    def close_image(self) -> None:
        """Mengosongkan viewer, sequence manager, dan panel informasi (berkas di disk tidak disentuh)."""
        self.sequence_manager.clear()
        self.viewer.clear_image()
        for label in self._info_values.values():
            label.setText(EMPTY_VALUE)
        self._refresh_sequence_controls()
        self.close_button.setEnabled(False)
        self.statusBar().showMessage(STATUS_EMPTY)

    def _format_mode_text(self) -> str:
        mode = self.sequence_manager.input_mode
        if mode == InputMode.SINGLE:
            return "Single Image (Stacking: Tidak)"
        if mode == InputMode.MULTI:
            return f"Multiple Images – {self.sequence_manager.frame_count} frame (Stacking: Wajib)"
        return EMPTY_VALUE

    def _format_sequence_summary(self, entry: SequenceFrameEntry) -> str:
        if self.sequence_manager.input_mode == InputMode.SINGLE:
            return "1 frame (berkas tunggal)"
        rep = self.sequence_manager.compatibility_report
        ready_txt = "Siap secara struktural" if rep.is_ready_for_stacking else "Perlu perhatian (lihat peringatan)"
        lines = [
            f"Frame #{entry.frame_index + 1}/{rep.total_files} [{entry.status_badge_indonesian()}]",
            f"Urutan: {self.sequence_manager.sorting_method}",
            f"Kompatibel: {rep.compatible_count} | Inkompatibel: {rep.incompatible_count} | Error: {rep.error_count}",
            f"Kesiapan struktural: {ready_txt}",
        ]
        if entry.issues:
            lines.append("Masalah frame ini: " + "; ".join(entry.issues))
        if entry.notes:
            lines.append("Catatan: " + "; ".join(entry.notes))
        return "\n".join(lines)

    def _show_info(self, info: ImageInfo, entry: SequenceFrameEntry) -> None:
        values = {
            "input_mode": self._format_mode_text(),
            "sequence_info": self._format_sequence_summary(entry),
            "file_name": info.file_name,
            "file_format": info.file_format,
            "width": f"{info.width} px",
            "height": f"{info.height} px",
            "channels": format_channels(info),
            "bit_depth": format_bit_depth(info),
            "orientation": format_orientation(info),
            "fits_metadata": format_fits_metadata(info),
        }
        for key, text in values.items():
            self._info_values[key].setText(text)

    def _show_error_entry_info(self, entry: SequenceFrameEntry) -> None:
        for key, label in self._info_values.items():
            label.setText(EMPTY_VALUE)
        self._info_values["input_mode"].setText(self._format_mode_text())
        self._info_values["sequence_info"].setText(self._format_sequence_summary(entry))
        self._info_values["file_name"].setText(entry.file_name)
        self._info_values["file_format"].setText("GAGAL DIBACA")

    def _show_error(self, message: str) -> None:
        """Menampilkan pesan galat kepada pengguna (dipisah agar mudah diuji)."""
        QMessageBox.warning(self, "Gagal membuka gambar", message)

    def _show_warning(self, message: str) -> None:
        """Menampilkan peringatan sequence kepada pengguna (dipisah agar mudah diuji)."""
        QMessageBox.warning(self, "Peringatan Sequence", message)
