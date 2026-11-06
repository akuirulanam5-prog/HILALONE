"""Jendela utama HILALONE v0.1: Single Image, Multiple Images, Sequence Navigator, & Image Viewer.

Berkas ini hanya mengurus TAMPILAN. Pembacaan, pengurutan, dan validasi berkas
dilakukan oleh ``hilalone.input_manager`` (sesuai aturan: GUI tanpa logika
pemrosesan).
"""

from __future__ import annotations

from pathlib import Path
import math
from typing import Any, Iterable

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
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from hilalone import APP_NAME, APP_SUBTITLE
from hilalone.gui.image_viewer import ImageViewer
from hilalone.input_manager.adapters.fits_reader import (
    UNAVAILABLE_TEXT as FITS_UNAVAILABLE,
    FitsHduSummary,
)
from hilalone.input_manager.adapters.raw_reader import UNAVAILABLE_TEXT as RAW_UNAVAILABLE
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
STACKING_HONESTY_NOTE = "Kesiapan struktural bukan berarti stacking sudah dijalankan."

# Kelompok A: INPUT & SEQUENCE
_SECTION_A_ROWS: tuple[tuple[str, str], ...] = (
    ("input_mode", "Mode input"),
    ("frame_count", "Jumlah frame"),
    ("active_frame", "Frame aktif"),
    ("sort_method", "Metode pengurutan"),
    ("compatible_count", "Jumlah kompatibel"),
    ("incompatible_count", "Jumlah inkompatibel"),
    ("error_count", "Jumlah error"),
    ("stacking_requirement", "Stacking"),
    ("structural_readiness", "Kesiapan struktural"),
    ("stacking_note", "Keterangan"),
    ("sequence_info", "Ringkasan"),
)

# Kelompok B: IMAGE INFORMATION
_SECTION_B_ROWS: tuple[tuple[str, str], ...] = (
    ("file_name", "Nama file"),
    ("file_format", "Format"),
    ("active_resolution", "Resolusi aktif"),
    ("full_resolution", "Resolusi penuh"),
    ("width", "Lebar"),
    ("height", "Tinggi"),
    ("orientation", "Orientasi"),
)

# Kelompok C: SENSOR INFORMATION
_SECTION_C_ROWS: tuple[tuple[str, str], ...] = (
    ("channels", "Sensor channels"),
    ("cfa_pattern", "CFA pattern"),
    ("storage_dtype", "Storage dtype"),
    ("white_level", "White level"),
    ("black_level", "Black level"),
    ("preview_info", "RGB preview"),
    ("bit_depth", "Bit depth"),
)

# Kelompok D (RAW): Metadata RAW
_SECTION_RAW_ROWS: tuple[tuple[str, str], ...] = (
    ("camera_model", "Camera make/model"),
    ("iso", "ISO"),
    ("shutter_speed", "Shutter speed"),
    ("aperture", "Aperture"),
    ("focal_length", "Focal length"),
    ("white_balance", "White balance"),
    ("timestamp", "Timestamp"),
    ("demosaic_note", "Catatan RAW"),
    ("fits_metadata", "Metadata sumber"),
)

# Kelompok D (FITS) — Sub-kelompok A: STRUKTUR DATA
_FITS_STRUCT_ROWS: tuple[tuple[str, str], ...] = (
    ("fits_bitpix", "BITPIX"),
    ("fits_naxis", "NAXIS"),
    ("fits_naxis1", "NAXIS1 (Width)"),
    ("fits_naxis2", "NAXIS2 (Height)"),
    ("fits_bscale", "BSCALE"),
    ("fits_bzero", "BZERO"),
    ("fits_blank", "BLANK"),
)

# Kelompok D (FITS) — Sub-kelompok B: INFORMASI OBSERVASI
_FITS_OBS_ROWS: tuple[tuple[str, str], ...] = (
    ("fits_date_obs", "DATE-OBS"),
    ("fits_date", "DATE"),
    ("fits_time_obs", "TIME-OBS"),
    ("fits_exptime", "EXPTIME"),
    ("fits_gain", "GAIN"),
    ("fits_filter", "FILTER"),
    ("fits_object", "OBJECT"),
)

# Kelompok D (FITS) — Sub-kelompok C: INFORMASI INSTRUMEN
_FITS_INST_ROWS: tuple[tuple[str, str], ...] = (
    ("fits_instrume", "INSTRUME"),
    ("fits_telescop", "TELESCOP"),
    ("fits_observer", "OBSERVER"),
    ("fits_detector", "DETECTOR"),
)

# Baris sequence yang hanya relevan pada mode Multiple Images
_MULTI_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "frame_count",
        "active_frame",
        "sort_method",
        "compatible_count",
        "incompatible_count",
        "error_count",
        "structural_readiness",
        "stacking_note",
        "sequence_info",
    }
)


def format_metadata_label(info: ImageInfo | None) -> str:
    """Label bagian metadata yang menyesuaikan format berkas (Informasi FITS, Metadata RAW, atau generik)."""
    if info is not None:
        if info.raw_metadata is not None:
            return "Metadata RAW"
        if info.fits_header is not None:
            return "Informasi FITS"
    return "Metadata sumber"


def format_channels(info: ImageInfo) -> str:
    """Teks jumlah kanal sensor; jujur 'Tidak diketahui' bila tidak dapat dipastikan."""
    if info.raw_metadata is not None and info.raw_metadata.is_cfa_mosaic:
        return (
            f"1 (Sensor CFA Mosaic: {info.raw_metadata.cfa_pattern_str}) | "
            "Preview: 3 (RGB Demosaiced)"
        )
    if info.channels is None:
        return "Tidak diketahui"
    names = {1: "monokrom", 3: "RGB", 4: "RGBA"}
    return f"{info.channels} ({names.get(info.channels, 'kanal')})"


def format_preview_channels_and_depth(info: ImageInfo) -> str:
    """Teks informasi kanal dan bit depth khusus untuk representasi pratinjau layar."""
    if info.raw_metadata is not None and info.raw_metadata.is_cfa_mosaic:
        return f"3 kanal (RGB Demosaiced), {info.preview_bit_depth}-bit"
    if info.channels == 1 and not info.has_alpha:
        return f"1 kanal (Monokrom), {info.preview_bit_depth}-bit"
    if info.channels == 4 or info.has_alpha:
        return f"4 kanal (RGBA), {info.preview_bit_depth}-bit"
    return f"3 kanal (RGB), {info.preview_bit_depth}-bit"


def format_bit_depth(info: ImageInfo) -> str:
    """Teks bit depth yang membedakan data asli dan preview layar.

    Khusus untuk berkas Camera RAW, container penyimpanan ``uint16`` TIDAK diklaim
    sebagai presisi efektif 16-bit sensor; yang ditampilkan adalah Storage dtype,
    White level aktual dari sensor/kamera, dan Display preview.
    """
    if info.raw_metadata is not None:
        storage_dtype = info.dtype_str or "uint16"
        wl = info.raw_metadata.white_level
        wl_text = str(wl) if wl is not None else "Tidak tersedia"
        return (
            f"Storage dtype: {storage_dtype} | White level: {wl_text} | "
            f"Display preview: {info.preview_bit_depth}-bit"
        )
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


def format_exposure_time(value: Any) -> str:
    """Memformat nilai exposure time (detik) ke satuan s, ms, atau µs untuk tampilan GUI.

    Aturan:
      * ``>= 1`` detik        -> ditampilkan dalam ``s``
      * ``>= 0.001`` & ``< 1`` -> ditampilkan dalam ``ms``
      * ``< 0.001`` detik     -> ditampilkan dalam ``µs``
      * Maksimal 2 angka desimal, tanpa angka nol buntut (*trailing zeros*) yang
        tidak perlu, dan tanpa notasi ilmiah untuk nilai normal.
      * Nilai ``None``, ``NaN``, ``Infinity``, nol, atau negatif dikembalikan
        sebagai ``"Tidak tersedia"``.
      * Fungsi ini murni untuk lapisan presentasi GUI dan tidak mengubah nilai
        header FITS asli.
    """
    if value is None or isinstance(value, bool):
        return FITS_UNAVAILABLE
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped == FITS_UNAVAILABLE:
            return FITS_UNAVAILABLE
        try:
            sec = float(stripped)
        except ValueError:
            return FITS_UNAVAILABLE
    else:
        try:
            sec = float(value)
        except (TypeError, ValueError):
            return FITS_UNAVAILABLE

    if not math.isfinite(sec) or sec <= 0.0:
        return FITS_UNAVAILABLE

    if sec >= 1.0:
        scaled = sec
        unit = "s"
    elif sec >= 0.001:
        scaled = sec * 1000.0
        unit = "ms"
        if round(scaled, 2) >= 1000.0:
            scaled = sec
            unit = "s"
    else:
        scaled = sec * 1_000_000.0
        unit = "µs"
        if round(scaled, 2) >= 1000.0:
            scaled = sec * 1000.0
            unit = "ms"

    formatted_num = f"{scaled:.2f}".rstrip("0").rstrip(".")
    if formatted_num in ("", "-0"):
        formatted_num = "0"
    return f"{formatted_num} {unit}"


def format_fits_metadata(info: ImageInfo) -> str:
    """Teks ringkasan metadata ilmiah (FITS atau Camera RAW), atau '-' bila bukan keduanya."""
    if info.fits_header is not None:
        return info.fits_header.summary_text()
    if info.raw_metadata is not None:
        return info.raw_metadata.summary_text()
    return EMPTY_VALUE


def _read_fits_header_cards_readonly(
    path: Path,
    hdu_index: int,
) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """Membaca kartu header FITS secara *read-only* untuk tampilan GUI terstruktur & Header Lengkap.

    Tidak mengubah ``fits_reader.py`` maupun berkas FITS sumber, dan tidak memuat
    array piksel gambar.

    Returns:
        (keyword_dict, cards_list)
        - ``keyword_dict``: peta keyword -> nilai string asli (tanpa hilangnya presisi).
        - ``cards_list``: daftar ``(keyword, value_str, comment_str)`` sesuai urutan asli.
    """
    from astropy.io import fits

    kw_map: dict[str, str] = {}
    cards_out: list[tuple[str, str, str]] = []
    try:
        with fits.open(
            path,
            mode="readonly",
            memmap=False,
            do_not_scale_image_data=True,
        ) as hdul:
            if 0 <= hdu_index < len(hdul):
                hdr = hdul[hdu_index].header
            else:
                hdr = hdul[0].header

            for card in hdr.cards:
                key = str(card.keyword or "").strip()
                try:
                    val = card.value
                except Exception:
                    val = ""
                comment = str(card.comment or "").strip()

                if val is None or isinstance(val, fits.Undefined):
                    val_str = ""
                elif isinstance(val, bool):
                    val_str = "T" if val else "F"
                else:
                    val_str = str(val)

                if key and key not in ("COMMENT", "HISTORY", "END") and val_str != "":
                    if key not in kw_map:
                        kw_map[key] = val_str

                if key or val_str or comment:
                    cards_out.append((key or "(BLANK)", val_str, comment))
    except Exception:
        return kw_map, cards_out

    return kw_map, cards_out


class MainWindow(QMainWindow):
    """Jendela utama aplikasi HILALONE."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} – {APP_SUBTITLE}")
        self.resize(1200, 800)
        self.setMinimumSize(800, 560)
        self._last_dir: str = str(Path.home())
        self._info_keys: dict[str, QLabel] = {}
        self._info_values: dict[str, QLabel] = {}
        self._full_fits_card_widgets: list[QWidget] = []
        self._full_fits_card_count: int = 0
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
        body.addWidget(self._build_info_panel(), 0)
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

    def _populate_key_value_grid(
        self,
        grid: QGridLayout,
        rows: tuple[tuple[str, str], ...],
        key_min_width: int = 112,
    ) -> None:
        """Mengisi QGridLayout 2 kolom (label di kiri, nilai word-wrapped di kanan)."""
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

        for row_idx, (key, label_text) in enumerate(rows):
            key_label = QLabel(label_text)
            key_label.setObjectName("infoKey")
            key_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            key_label.setMinimumWidth(key_min_width)

            value_label = QLabel(EMPTY_VALUE)
            value_label.setObjectName("infoValue")
            value_label.setWordWrap(True)
            value_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            value_label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            grid.addWidget(key_label, row_idx, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(value_label, row_idx, 1, Qt.AlignmentFlag.AlignTop)
            self._info_keys[key] = key_label
            self._info_values[key] = value_label

    def _create_section_card(
        self,
        title_text: str,
        rows: tuple[tuple[str, str], ...],
    ) -> tuple[QFrame, QLabel]:
        """Membuat satu kartu kelompok informasi dengan header dan grid 2 kolom."""
        card = QFrame()
        card.setObjectName("infoSectionCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(6)

        header = QLabel(title_text)
        header.setObjectName("sectionHeader")
        header.setWordWrap(True)
        card_layout.addWidget(header)

        grid = QGridLayout()
        self._populate_key_value_grid(grid, rows)
        card_layout.addLayout(grid)
        return card, header

    def _build_fits_info_card(self) -> QFrame:
        """Membangun kartu 'Informasi FITS' dengan 3 sub-kelompok + bagian collapsible 'Header FITS Lengkap'."""
        card = QFrame()
        card.setObjectName("infoSectionCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        self.header_fits_info = QLabel("Informasi FITS")
        self.header_fits_info.setObjectName("sectionHeader")
        self.header_fits_info.setWordWrap(True)
        layout.addWidget(self.header_fits_info)

        # Sub-kelompok A: Struktur Data
        self.fits_sub_struct_label = QLabel("A. Struktur Data")
        self.fits_sub_struct_label.setObjectName("subSectionHeader")
        layout.addWidget(self.fits_sub_struct_label)
        struct_grid = QGridLayout()
        self._populate_key_value_grid(struct_grid, _FITS_STRUCT_ROWS, key_min_width=106)
        layout.addLayout(struct_grid)

        # Sub-kelompok B: Informasi Observasi
        self.fits_sub_obs_label = QLabel("B. Informasi Observasi")
        self.fits_sub_obs_label.setObjectName("subSectionHeader")
        layout.addWidget(self.fits_sub_obs_label)
        obs_grid = QGridLayout()
        self._populate_key_value_grid(obs_grid, _FITS_OBS_ROWS, key_min_width=106)
        layout.addLayout(obs_grid)

        # Sub-kelompok C: Informasi Instrumen
        self.fits_sub_inst_label = QLabel("C. Informasi Instrumen")
        self.fits_sub_inst_label.setObjectName("subSectionHeader")
        layout.addWidget(self.fits_sub_inst_label)
        inst_grid = QGridLayout()
        self._populate_key_value_grid(inst_grid, _FITS_INST_ROWS, key_min_width=106)
        layout.addLayout(inst_grid)

        # Bagian Collapsible: Header FITS Lengkap
        self.fits_full_header_toggle = QPushButton("▶ Header FITS Lengkap")
        self.fits_full_header_toggle.setObjectName("collapsibleButton")
        self.fits_full_header_toggle.setCheckable(True)
        self.fits_full_header_toggle.setChecked(False)
        self.fits_full_header_toggle.toggled.connect(self._on_fits_full_header_toggled)
        layout.addWidget(self.fits_full_header_toggle)

        self.fits_full_header_container = QFrame()
        self.fits_full_header_container.setObjectName("fullHeaderBox")
        full_box_layout = QVBoxLayout(self.fits_full_header_container)
        full_box_layout.setContentsMargins(8, 8, 8, 8)
        full_box_layout.setSpacing(4)

        self.fits_full_header_grid = QGridLayout()
        self.fits_full_header_grid.setHorizontalSpacing(10)
        self.fits_full_header_grid.setVerticalSpacing(4)
        self.fits_full_header_grid.setColumnStretch(0, 0)
        self.fits_full_header_grid.setColumnStretch(1, 1)
        full_box_layout.addLayout(self.fits_full_header_grid)

        # Label tersembunyi yang menyimpan seluruh kartu header asli secara utuh untuk inspeksi/tes
        self.fits_full_header_raw_label = QLabel(EMPTY_VALUE)
        self.fits_full_header_raw_label.setObjectName("infoValue")
        self.fits_full_header_raw_label.setWordWrap(True)
        self.fits_full_header_raw_label.setVisible(False)
        full_box_layout.addWidget(self.fits_full_header_raw_label)
        self._info_values["fits_full_header"] = self.fits_full_header_raw_label

        self.fits_full_header_container.setVisible(False)
        layout.addWidget(self.fits_full_header_container)
        return card

    def _on_fits_full_header_toggled(self, checked: bool) -> None:
        arrow = "▼" if checked else "▶"
        count_suffix = f" ({self._full_fits_card_count})" if self._full_fits_card_count > 0 else ""
        self.fits_full_header_toggle.setText(f"{arrow} Header FITS Lengkap{count_suffix}")
        self.fits_full_header_container.setVisible(checked)

    def _build_info_panel(self) -> QFrame:
        self.info_panel = QFrame()
        self.info_panel.setObjectName("infoPanel")
        self.info_panel.setMinimumWidth(340)
        self.info_panel.setMaximumWidth(420)
        self.info_panel.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Expanding,
        )

        outer_layout = QVBoxLayout(self.info_panel)
        outer_layout.setContentsMargins(12, 12, 12, 12)
        outer_layout.setSpacing(8)

        title = QLabel("INFORMASI GAMBAR")
        title.setObjectName("infoTitle")
        outer_layout.addWidget(title)

        self.info_scroll_area = QScrollArea()
        self.info_scroll_area.setObjectName("infoScrollArea")
        self.info_scroll_area.setWidgetResizable(True)
        self.info_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.info_scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.info_scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.info_scroll_content = QWidget()
        self.info_scroll_content.setObjectName("infoScrollContent")
        content_layout = QVBoxLayout(self.info_scroll_content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(10)

        self.section_input_sequence, self.header_input_sequence = self._create_section_card(
            "A. INPUT & SEQUENCE", _SECTION_A_ROWS
        )
        self.section_image_info, self.header_image_info = self._create_section_card(
            "B. IMAGE INFORMATION", _SECTION_B_ROWS
        )
        self.section_sensor_info, self.header_sensor_info = self._create_section_card(
            "C. SENSOR INFORMATION", _SECTION_C_ROWS
        )
        self.section_camera_metadata, self.header_camera_metadata = self._create_section_card(
            "Metadata RAW", _SECTION_RAW_ROWS
        )
        self.section_fits_info = self._build_fits_info_card()

        content_layout.addWidget(self.section_input_sequence)
        content_layout.addWidget(self.section_image_info)
        content_layout.addWidget(self.section_sensor_info)
        content_layout.addWidget(self.section_camera_metadata)
        content_layout.addWidget(self.section_fits_info)
        content_layout.addStretch(1)

        self.info_scroll_area.setWidget(self.info_scroll_content)
        outer_layout.addWidget(self.info_scroll_area, 1)
        return self.info_panel

    def _set_row_visible(self, key: str, visible: bool) -> None:
        if key in self._info_keys:
            self._info_keys[key].setVisible(visible)
        if key in self._info_values:
            self._info_values[key].setVisible(visible)

    def _set_row(self, key: str, value: str, visible: bool = True) -> None:
        if key in self._info_values:
            self._info_values[key].setText(value)
        self._set_row_visible(key, visible)

    def _clear_full_fits_header_grid(self) -> None:
        for w in self._full_fits_card_widgets:
            self.fits_full_header_grid.removeWidget(w)
            w.deleteLater()
        self._full_fits_card_widgets.clear()
        self._full_fits_card_count = 0

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
        """Menampilkan dialog pemilih satu folder berisi urutan berkas gambar."""
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
        """Placeholder tombol Video sampai Sub-Tahap Video & SER Reader diimplementasikan."""
        QMessageBox.information(
            self,
            "Video Reader (Tahap Berikutnya)",
            "Dukungan pembacaan berkas video astronomi (.SER) dan video umum "
            "(.MP4, .MOV, .AVI) akan diaktifkan pada sub-tahap Input Manager berikutnya.",
        )

    def _ask_tiff_page(self, path: Path, pages: tuple[TiffPageSummary, ...]) -> int | None:
        items = [p.label() for p in pages]
        choice, ok = QInputDialog.getItem(
            self,
            "Pilih Halaman TIFF",
            f"Berkas '{path.name}' berisi {len(pages)} halaman.\nPilih halaman yang ingin dibuka:",
            items,
            0,
            False,
        )
        if not ok or not choice:
            return None
        idx = items.index(choice)
        return pages[idx].index

    def _ask_fits_hdu(
        self,
        path: Path,
        image_hdus: tuple[FitsHduSummary, ...],
        total_hdu_count: int,
    ) -> int | None:
        items = [h.label() for h in image_hdus]
        choice, ok = QInputDialog.getItem(
            self,
            "Pilih HDU Gambar FITS",
            (
                f"Berkas FITS '{path.name}' memiliki {len(image_hdus)} HDU gambar "
                f"(dari total {total_hdu_count} HDU).\n"
                "Pilih HDU gambar yang ingin dibuka:"
            ),
            items,
            0,
            False,
        )
        if not ok or not choice:
            return None
        idx = items.index(choice)
        return image_hdus[idx].index

    def load_path(
        self,
        path: str | Path,
        page_index: int | None = None,
        hdu_index: int | None = None,
    ) -> bool:
        """Memuat satu berkas gambar (Single Image; stacking_required = False)."""
        path = Path(path)
        try:
            loaded = self.sequence_manager.open_single_file(
                path, page_index=page_index, hdu_index=hdu_index
            )
        except MultiPageTiffError as multi_err:
            chosen = self._ask_tiff_page(multi_err.path, multi_err.pages)
            if chosen is None:
                return False
            return self.load_path(path, page_index=chosen)
        except MultiHduFitsError as fits_err:
            chosen_hdu = self._ask_fits_hdu(
                fits_err.path, fits_err.image_hdus, fits_err.total_hdu_count
            )
            if chosen_hdu is None:
                return False
            return self.load_path(path, hdu_index=chosen_hdu)
        except ImageReadError as err:
            self._show_error(str(err))
            return False

        self._refresh_sequence_controls()
        entry = self.sequence_manager.entries[0]
        self.viewer.set_image(loaded.preview)
        self._show_info(loaded.info, entry)
        self.close_button.setEnabled(True)
        self.statusBar().showMessage(
            f"Single Image: {loaded.info.file_name}  |  {loaded.info.width} × {loaded.info.height} px"
        )
        return True

    def load_folder_sequence(self, folder_path: str | Path, sort_by: str = "natural") -> bool:
        """Memuat seluruh gambar yang didukung dari sebuah folder."""
        try:
            report = self.sequence_manager.open_folder(folder_path, sort_by=sort_by)
        except ImageReadError as err:
            self._show_error(str(err))
            return False
        return self._finalize_sequence_open(report.warnings)

    def load_sequence_paths(
        self,
        paths: Iterable[str | Path],
        sort_by: str = "natural",
    ) -> bool:
        """Memuat banyak berkas gambar sekaligus ke dalam SequenceManager."""
        try:
            report = self.sequence_manager.open_files(paths, sort_by=sort_by)
        except ImageReadError as err:
            self._show_error(str(err))
            return False
        return self._finalize_sequence_open(report.warnings)

    def _finalize_sequence_open(self, warnings: tuple[str, ...]) -> bool:
        self._refresh_sequence_controls()
        self.close_button.setEnabled(self.sequence_manager.frame_count > 0)

        target_idx = self.sequence_manager.compatibility_report.reference_frame_index
        if target_idx is None:
            target_idx = 0
        self.select_sequence_frame(target_idx, show_error_dialog=False)

        if warnings:
            shown = "\n".join(f"• {w}" for w in warnings[:8])
            if len(warnings) > 8:
                shown += f"\n... dan {len(warnings) - 8} peringatan lainnya."
            self._show_warning(
                "Sebagian berkas di dalam sequence memiliki masalah kompatibilitas atau gagal dibaca:\n\n"
                f"{shown}\n\n"
                "Catatan: Frame berstatus TIDAK KOMPATIBEL tetap dapat dipilih pada daftar untuk dipratinjau secara individual."
            )
        return True

    def select_sequence_frame(self, index: int, show_error_dialog: bool = True) -> bool:
        """Memilih dan menampilkan pratinjau untuk frame ke-`index` secara *on-demand*."""
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
        self._clear_full_fits_header_grid()
        if "fits_metadata" in self._info_keys:
            self._info_keys["fits_metadata"].setText(format_metadata_label(None))
        self.header_camera_metadata.setText("Metadata RAW")
        self.header_fits_info.setText("Informasi FITS")
        self.fits_full_header_toggle.setChecked(False)
        self.fits_full_header_toggle.setText("▶ Header FITS Lengkap")
        self.fits_full_header_container.setVisible(False)
        for key, label in self._info_values.items():
            label.setText(EMPTY_VALUE)
            self._set_row_visible(key, key not in _MULTI_ONLY_KEYS)
        self.section_camera_metadata.setVisible(False)
        self.section_fits_info.setVisible(False)
        self._refresh_sequence_controls()
        self.close_button.setEnabled(False)
        self.statusBar().showMessage(STATUS_EMPTY)

    def _format_mode_text(self) -> str:
        mode = self.sequence_manager.input_mode
        if mode == InputMode.SINGLE:
            return "Single Image"
        if mode == InputMode.MULTI:
            return "Multiple Images"
        return EMPTY_VALUE

    def _format_sequence_summary(self, entry: SequenceFrameEntry) -> str:
        if self.sequence_manager.input_mode == InputMode.SINGLE:
            return "1 frame (berkas tunggal)"
        rep = self.sequence_manager.compatibility_report
        ready_txt = "Siap" if rep.is_ready_for_stacking else "Tidak siap"
        lines = [
            f"Frame #{entry.frame_index + 1}/{rep.total_files} [{entry.status_badge_indonesian()}]",
            f"Urutan: {self.sequence_manager.sorting_method}",
            f"Kompatibel: {rep.compatible_count} | Inkompatibel: {rep.incompatible_count} | Error: {rep.error_count}",
            f"Kesiapan struktural: {ready_txt}",
            STACKING_HONESTY_NOTE,
        ]
        if entry.issues:
            lines.append("Masalah frame ini: " + "; ".join(entry.issues))
        if entry.notes:
            lines.append("Catatan: " + "; ".join(entry.notes))
        return "\n".join(lines)

    def _populate_section_a_input_sequence(self, entry: SequenceFrameEntry) -> None:
        is_multi = self.sequence_manager.input_mode == InputMode.MULTI
        rep = self.sequence_manager.compatibility_report

        self._set_row("input_mode", self._format_mode_text(), visible=True)

        if not is_multi:
            self._set_row("stacking_requirement", "Tidak diperlukan", visible=True)
            for k in _MULTI_ONLY_KEYS:
                self._set_row(k, EMPTY_VALUE, visible=False)
            self._info_values["sequence_info"].setText("1 frame (berkas tunggal)")
            return

        ready_txt = "Siap" if rep.is_ready_for_stacking else "Tidak siap"
        note_lines = [STACKING_HONESTY_NOTE]
        if entry.issues:
            note_lines.append("Masalah frame aktif: " + "; ".join(entry.issues))
        if entry.notes:
            note_lines.append("Catatan frame aktif: " + "; ".join(entry.notes))

        self._set_row("frame_count", f"{rep.total_files} frame", visible=True)
        self._set_row(
            "active_frame",
            f"{entry.frame_index + 1}/{rep.total_files} ({entry.status_badge_indonesian()})",
            visible=True,
        )
        self._set_row("sort_method", self.sequence_manager.sorting_method, visible=True)
        self._set_row("compatible_count", str(rep.compatible_count), visible=True)
        self._set_row("incompatible_count", str(rep.incompatible_count), visible=True)
        self._set_row("error_count", str(rep.error_count), visible=True)
        self._set_row("stacking_requirement", "Stacking: Wajib", visible=True)
        self._set_row("structural_readiness", ready_txt, visible=True)
        self._set_row("stacking_note", "\n".join(note_lines), visible=True)
        self._set_row("sequence_info", self._format_sequence_summary(entry), visible=False)

    def _populate_section_b_image_info(self, info: ImageInfo) -> None:
        self._set_row("file_name", info.file_name, visible=True)
        self._set_row("file_format", info.file_format, visible=True)
        self._set_row("active_resolution", f"{info.width} × {info.height} px", visible=True)

        has_diff_full_res = (info.stored_width, info.stored_height) != (info.width, info.height)
        if has_diff_full_res:
            self._set_row(
                "full_resolution",
                f"{info.stored_width} × {info.stored_height} px",
                visible=True,
            )
        else:
            self._set_row("full_resolution", EMPTY_VALUE, visible=False)

        self._set_row("width", f"{info.width} px", visible=True)
        self._set_row("height", f"{info.height} px", visible=True)
        self._set_row("orientation", format_orientation(info), visible=True)

    def _populate_section_c_sensor_info(self, info: ImageInfo) -> None:
        raw_meta = info.raw_metadata
        self._set_row("channels", format_channels(info), visible=True)

        if raw_meta is not None:
            cfa_txt = raw_meta.cfa_pattern_str or RAW_UNAVAILABLE
            self._set_row("cfa_pattern", cfa_txt, visible=(cfa_txt != RAW_UNAVAILABLE))
            self._set_row("storage_dtype", info.dtype_str or "uint16", visible=True)

            wl_txt = str(raw_meta.white_level) if raw_meta.white_level is not None else RAW_UNAVAILABLE
            self._set_row("white_level", wl_txt, visible=(wl_txt != RAW_UNAVAILABLE))

            if raw_meta.black_level_per_channel:
                blk_txt = ", ".join(str(v) for v in raw_meta.black_level_per_channel)
                self._set_row("black_level", blk_txt, visible=True)
            else:
                self._set_row("black_level", EMPTY_VALUE, visible=False)
        else:
            self._set_row("cfa_pattern", EMPTY_VALUE, visible=False)
            self._set_row("storage_dtype", info.dtype_str or EMPTY_VALUE, visible=bool(info.dtype_str))
            self._set_row("white_level", EMPTY_VALUE, visible=False)
            self._set_row("black_level", EMPTY_VALUE, visible=False)

        self._set_row("preview_info", format_preview_channels_and_depth(info), visible=True)
        self._set_row("bit_depth", format_bit_depth(info), visible=True)

    def _populate_fits_full_header_cards(
        self,
        cards: list[tuple[str, str, str]],
    ) -> None:
        self._clear_full_fits_header_grid()
        self._full_fits_card_count = len(cards)
        raw_lines: list[str] = []

        for row_idx, (kw, val_str, comment_str) in enumerate(cards):
            key_lbl = QLabel(kw)
            key_lbl.setObjectName("infoKey")
            key_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            key_lbl.setMinimumWidth(84)
            key_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            if val_str and comment_str:
                rhs = f"{val_str}  / {comment_str}"
            elif val_str:
                rhs = val_str
            else:
                rhs = f"/ {comment_str}" if comment_str else ""

            val_lbl = QLabel(rhs)
            val_lbl.setObjectName("infoValue")
            val_lbl.setWordWrap(True)
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
            val_lbl.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )
            val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            self.fits_full_header_grid.addWidget(key_lbl, row_idx, 0, Qt.AlignmentFlag.AlignTop)
            self.fits_full_header_grid.addWidget(val_lbl, row_idx, 1, Qt.AlignmentFlag.AlignTop)
            self._full_fits_card_widgets.extend((key_lbl, val_lbl))
            raw_lines.append(f"{kw} = {rhs}")

        self.fits_full_header_raw_label.setText("\n".join(raw_lines) if raw_lines else EMPTY_VALUE)
        self._on_fits_full_header_toggled(self.fits_full_header_toggle.isChecked())

    def _populate_section_d_camera_or_fits(self, info: ImageInfo) -> None:
        if "fits_metadata" in self._info_keys:
            self._info_keys["fits_metadata"].setText(format_metadata_label(info))

        raw_meta = info.raw_metadata
        if raw_meta is not None:
            self.section_fits_info.setVisible(False)
            self.header_camera_metadata.setText("Metadata RAW")
            d = raw_meta.to_display_dict()
            pairs = (
                ("camera_model", d["CAMERA"]),
                ("iso", d["ISO"]),
                ("shutter_speed", d["SHUTTER"]),
                ("aperture", d["APERTURE"]),
                ("focal_length", d["FOCAL_LENGTH"]),
                ("white_balance", d["CAMERA_WB"]),
                ("timestamp", d["TIMESTAMP"]),
            )
            for key, val in pairs:
                avail = bool(val and val != RAW_UNAVAILABLE)
                self._set_row(key, val if avail else EMPTY_VALUE, visible=avail)

            self._set_row("demosaic_note", raw_meta.demosaic_note, visible=True)
            self._set_row("fits_metadata", raw_meta.summary_text(), visible=False)
            self.section_camera_metadata.setVisible(True)
            return

        # Sembunyikan kartu Metadata RAW bila berkas bukan Camera RAW
        self.section_camera_metadata.setVisible(False)
        for k in (
            "camera_model",
            "iso",
            "shutter_speed",
            "aperture",
            "focal_length",
            "white_balance",
            "timestamp",
            "demosaic_note",
        ):
            self._set_row(k, EMPTY_VALUE, visible=False)

        fh = info.fits_header
        if fh is not None:
            self.header_fits_info.setText("Informasi FITS")
            d_fits = fh.to_display_dict()
            extra_kw, all_cards = _read_fits_header_cards_readonly(info.path, info.hdu_index)

            def _req(val: str) -> str:
                return val if (val and val != FITS_UNAVAILABLE) else FITS_UNAVAILABLE

            # Sub-kelompok A: STRUKTUR DATA
            self._set_row("fits_bitpix", _req(d_fits["BITPIX"]), visible=True)
            self._set_row("fits_naxis", _req(d_fits["NAXIS"]), visible=True)
            self._set_row("fits_naxis1", _req(d_fits["NAXIS1"]), visible=True)
            self._set_row("fits_naxis2", _req(d_fits["NAXIS2"]), visible=True)
            self._set_row("fits_bscale", _req(d_fits["BSCALE"]), visible=True)
            self._set_row("fits_bzero", _req(d_fits["BZERO"]), visible=True)
            blank_val = extra_kw.get("BLANK")
            self._set_row("fits_blank", blank_val or EMPTY_VALUE, visible=bool(blank_val))

            # Sub-kelompok B: Informasi Observasi
            self._set_row("fits_date_obs", _req(d_fits["DATE-OBS"]), visible=True)
            date_val = extra_kw.get("DATE")
            self._set_row("fits_date", date_val or EMPTY_VALUE, visible=bool(date_val))
            time_obs_val = extra_kw.get("TIME-OBS")
            self._set_row("fits_time_obs", time_obs_val or EMPTY_VALUE, visible=bool(time_obs_val))
            self._set_row("fits_exptime", format_exposure_time(fh.exptime), visible=True)
            self._set_row("fits_gain", _req(d_fits["GAIN"]), visible=True)
            filter_val = extra_kw.get("FILTER")
            self._set_row("fits_filter", filter_val or EMPTY_VALUE, visible=bool(filter_val))
            object_val = extra_kw.get("OBJECT")
            self._set_row("fits_object", object_val or EMPTY_VALUE, visible=bool(object_val))

            # Sub-kelompok C: INFORMASI INSTRUMEN
            self._set_row("fits_instrume", _req(d_fits["INSTRUME"]), visible=True)
            self._set_row("fits_telescop", _req(d_fits["TELESCOP"]), visible=True)
            observer_val = extra_kw.get("OBSERVER")
            self._set_row("fits_observer", observer_val or EMPTY_VALUE, visible=bool(observer_val))
            detector_val = extra_kw.get("DETECTOR")
            self._set_row("fits_detector", detector_val or EMPTY_VALUE, visible=bool(detector_val))

            # Header FITS Lengkap (Collapsible)
            self._populate_fits_full_header_cards(all_cards)

            self._set_row("fits_metadata", fh.summary_text(), visible=False)
            self.section_fits_info.setVisible(True)
        else:
            self._clear_full_fits_header_grid()
            self._set_row("fits_metadata", EMPTY_VALUE, visible=False)
            self.section_fits_info.setVisible(False)

    def _show_info(self, info: ImageInfo, entry: SequenceFrameEntry) -> None:
        self._populate_section_a_input_sequence(entry)
        self._populate_section_b_image_info(info)
        self._populate_section_c_sensor_info(info)
        self._populate_section_d_camera_or_fits(info)

    def _show_error_entry_info(self, entry: SequenceFrameEntry) -> None:
        self._clear_full_fits_header_grid()
        if "fits_metadata" in self._info_keys:
            self._info_keys["fits_metadata"].setText(format_metadata_label(None))
        for key, label in self._info_values.items():
            label.setText(EMPTY_VALUE)
        self._populate_section_a_input_sequence(entry)
        self._set_row("file_name", entry.file_name, visible=True)
        self._set_row("file_format", "GAGAL DIBACA", visible=True)
        self.section_camera_metadata.setVisible(False)
        self.section_fits_info.setVisible(False)

    def _show_error(self, message: str) -> None:
        """Menampilkan pesan galat kepada pengguna (dipisah agar mudah diuji)."""
        QMessageBox.warning(self, "Gagal membuka gambar", message)

    def _show_warning(self, message: str) -> None:
        """Menampilkan peringatan sequence kepada pengguna (dipisah agar mudah diuji)."""
        QMessageBox.warning(self, "Peringatan Sequence", message)
