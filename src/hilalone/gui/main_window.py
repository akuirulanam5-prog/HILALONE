"""Jendela utama HILALONE v0.1: Open Image, Image Viewer, Image Information, Close Image.

Berkas ini hanya mengurus TAMPILAN. Pembacaan dan validasi berkas dilakukan
oleh ``hilalone.input_manager.image_reader`` (sesuai aturan: GUI tanpa logika
pemrosesan).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
from hilalone.input_manager.adapters.tiff_reader import TiffPageSummary
from hilalone.input_manager.image_reader import (
    ImageInfo,
    ImageReadError,
    MultiPageTiffError,
    read_image,
    supported_extensions,
)

EMPTY_VALUE = "-"
STATUS_EMPTY = "Belum ada gambar dibuka."

# Baris panel informasi: (kunci internal, label yang ditampilkan).
_INFO_ROWS: tuple[tuple[str, str], ...] = (
    ("file_name", "Nama file"),
    ("file_format", "Format"),
    ("width", "Lebar"),
    ("height", "Tinggi"),
    ("channels", "Kanal"),
    ("bit_depth", "Bit depth"),
    ("orientation", "Orientasi"),
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
        dtype_note = f" ({info.dtype_str})" if info.dtype_str else ""
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


class MainWindow(QMainWindow):
    """Jendela utama aplikasi HILALONE."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} – {APP_SUBTITLE}")
        self.resize(1200, 800)
        self.setMinimumSize(800, 560)
        self._last_dir: str = str(Path.home())
        self._info_values: dict[str, QLabel] = {}

        self._build_ui()
        self.close_image()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 8)
        root.setSpacing(12)

        root.addLayout(self._build_header())
        line = QFrame()
        line.setObjectName("headerLine")
        line.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(line)
        root.addLayout(self._build_toolbar())

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
        self.open_button.clicked.connect(self.open_image_dialog)
        self.close_button = QPushButton("Close Image")
        self.close_button.setObjectName("secondaryButton")
        self.close_button.clicked.connect(self.close_image)
        layout.addWidget(self.open_button)
        layout.addWidget(self.close_button)
        layout.addStretch(1)
        return layout

    def _build_info_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("infoPanel")
        panel.setFixedWidth(300)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QLabel("INFORMASI GAMBAR")
        title.setObjectName("infoTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(10)
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
        """Menampilkan dialog pemilih berkas lalu memuat gambar yang dipilih."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Buka Gambar", self._last_dir, self._file_dialog_filter()
        )
        if not file_path:  # pengguna menekan Batal
            return
        self._last_dir = str(Path(file_path).parent)
        self.load_path(file_path)

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

    def load_path(self, file_path: str | Path, page_index: int | None = None) -> bool:
        """Memuat gambar dari jalur tertentu. True bila berhasil.

        Bila berkas berupa TIFF multi-halaman dan ``page_index`` belum diberikan,
        pengguna diminta memilih halaman terlebih dahulu (tidak diam-diam
        mengambil halaman pertama).
        """
        try:
            loaded = read_image(file_path, page_index=page_index)
        except MultiPageTiffError as multi_err:
            selected_page = self._ask_tiff_page(multi_err.path.name, multi_err.pages)
            if selected_page is None:
                return False
            return self.load_path(file_path, page_index=selected_page)
        except ImageReadError as error:
            self._show_error(str(error))
            return False
        except Exception as error:  # jaring pengaman: aplikasi tidak boleh crash
            self._show_error(f"Terjadi kesalahan tak terduga saat membuka gambar: {error}")
            return False

        self.viewer.set_image(loaded.preview)
        self._show_info(loaded.info)
        self.close_button.setEnabled(True)
        self.statusBar().showMessage(
            f"Dibuka: {loaded.info.file_name}  |  {loaded.info.width} × {loaded.info.height} px"
        )
        return True

    def close_image(self) -> None:
        """Mengosongkan viewer dan panel informasi (berkas di disk tidak disentuh)."""
        self.viewer.clear_image()
        for label in self._info_values.values():
            label.setText(EMPTY_VALUE)
        self.close_button.setEnabled(False)
        self.statusBar().showMessage(STATUS_EMPTY)

    def _show_info(self, info: ImageInfo) -> None:
        values = {
            "file_name": info.file_name,
            "file_format": info.file_format,
            "width": f"{info.width} px",
            "height": f"{info.height} px",
            "channels": format_channels(info),
            "bit_depth": format_bit_depth(info),
            "orientation": format_orientation(info),
        }
        for key, text in values.items():
            self._info_values[key].setText(text)

    def _show_error(self, message: str) -> None:
        """Menampilkan pesan galat kepada pengguna (dipisah agar mudah diuji)."""
        QMessageBox.warning(self, "Gagal membuka gambar", message)
