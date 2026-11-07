"""Jendela utama HILALONE v0.1: Single Image, Multiple Images, Sequence Navigator, & Image Viewer.

Berkas ini hanya mengurus TAMPILAN. Pembacaan, pengurutan, dan validasi berkas
dilakukan oleh ``hilalone.input_manager`` (sesuai aturan: GUI tanpa logika
pemrosesan).
"""

from __future__ import annotations

from pathlib import Path
import math
from typing import Any, Iterable

from PySide6.QtCore import QEventLoop, QSize, Qt
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import numpy as np

from hilalone import APP_NAME, APP_SUBTITLE
from hilalone.gui.icons import create_vector_icon
from hilalone.gui.image_viewer import ImageViewer
from hilalone.gui.pipeline_worker import PipelineWorker
from hilalone.gui.resources import get_app_icon, get_header_logo_pixmap
from hilalone.gui.stacking_worker import StackingWorker
from hilalone.gui.state_manager import ProcessingState, ProcessingStateManager
from hilalone.input_manager.adapters.fits_reader import (
    UNAVAILABLE_TEXT as FITS_UNAVAILABLE,
    FitsHduSummary,
)
from hilalone.input_manager.adapters.raw_reader import UNAVAILABLE_TEXT as RAW_UNAVAILABLE
from hilalone.input_manager.adapters.ser_reader import (
    SER_EXTENSIONS,
    UNAVAILABLE_TEXT as SER_UNAVAILABLE,
)
from hilalone.input_manager.adapters.tiff_reader import TiffPageSummary
from hilalone.input_manager.adapters.video_reader import (
    UNAVAILABLE_TEXT as VIDEO_UNAVAILABLE,
    VIDEO_EXTENSIONS,
)
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
from hilalone.output_manager.pipeline_writer import save_pipeline_result
from hilalone.output_manager.stacking_writer import (
    OutputWriteError,
    save_stacking_result,
)
from hilalone.processing import (
    UNIFIED_PROFILE_CONFIGS,
    BackgroundExtractionConfig,
    BackgroundExtractionResult,
    BackgroundModelMethod,
    ImageEnhancementConfig,
    ImageEnhancementResult,
    HistogramTransformConfig,
    HistogramTransformResult,
    PipelineResult,
    PipelineStage,
    PreviewMode,
    ProcessingError,
    ProcessingProfile,
    ProtectedRegionROI,
    StretchMethod,
    UnifiedProfileConfig,
    customize_profile_config,
    get_unified_profile_config,
)
from hilalone.processing.stacking import (
    FlatCompatibilityCheckResult,
    LoadedMasterFlat,
    NORMALIZATION_FORMULA_TEXT,
    PreStackValidationReport,
    StackingError,
    StackingProfile,
    StackingResult,
    check_flat_compatibility,
    compute_flat_pixel_statistics,
    get_stacking_profile_config,
    load_master_flat_auto,
    load_master_flat_from_sequence,
    validate_sequence_for_stacking,
)
from hilalone.processing.stacking.validator import extract_frame_cfa_info

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

# Kelompok D (VIDEO): Informasi Video
_SECTION_VIDEO_ROWS: tuple[tuple[str, str], ...] = (
    ("video_container", "Container & Ukuran"),
    ("video_stream", "Video stream"),
    ("video_codec", "Video codec"),
    ("video_pix_fmt", "Pixel format"),
    ("video_fps", "Frame rate"),
    ("video_time_base", "time_base"),
    ("video_frame_pts", "Timestamp frame"),
    ("video_duration", "Durasi"),
    ("video_bit_rate", "Bit rate"),
    ("video_color_meta", "Color metadata"),
    ("video_honesty_note", "Catatan video"),
)

# Kelompok D (SER): Informasi SER
_SECTION_SER_ROWS: tuple[tuple[str, str], ...] = (
    ("ser_file_id", "FileID & LuID"),
    ("ser_file_size", "Ukuran file"),
    ("ser_color_id", "ColorID"),
    ("ser_cfa_pattern", "Pola CFA"),
    ("ser_resolution", "Resolusi"),
    ("ser_pixel_depth", "Pixel depth"),
    ("ser_endianness", "Byte order"),
    ("ser_frame_count", "Jumlah frame"),
    ("ser_observer", "Observer"),
    ("ser_instrument", "Instrument"),
    ("ser_telescope", "Telescope"),
    ("ser_datetime_local", "DateTime (Lokal)"),
    ("ser_datetime_utc", "DateTime (UTC)"),
    ("ser_trailer_status", "Trailer timestamp"),
    ("ser_frame_timestamp", "Timestamp frame"),
    ("ser_honesty_note", "Catatan SER"),
)

# Kelompok E: IMAGE PROCESSING (Informasi Pra-Stacking)
_PROC_INFO_ROWS: tuple[tuple[str, str], ...] = (
    ("proc_total_frames", "Total frame"),
    ("proc_compatible_frames", "Frame kompatibel"),
    ("proc_incompatible_frames", "Frame inkompatibel"),
    ("proc_error_frames", "Frame error"),
    ("proc_method", "Metode stacking"),
    ("proc_flat_status", "Status flat"),
)

# Kelompok E: IMAGE PROCESSING (Rincian Kalibrasi Master Flat)
_PROC_FLAT_ROWS: tuple[tuple[str, str], ...] = (
    ("flat_source_info", "File / Sequence"),
    ("flat_format_meta", "Format & Dimensi"),
    ("flat_compat_status", "Kompatibilitas"),
    ("flat_norm_status", "Normalisasi"),
    ("flat_invalid_pixels", "Invalid pixels"),
)

# Kelompok E: IMAGE PROCESSING (Hasil Stacking)
_PROC_RESULT_ROWS: tuple[tuple[str, str], ...] = (
    ("res_status", "Status hasil"),
    ("res_frames_used", "Frame digunakan"),
    ("res_algorithm", "Algoritma"),
    ("res_dtype_range", "Data & rentang"),
    ("res_rejected_samples", "Sampel ditolak"),
    ("res_history", "Riwayat proses"),
)

# Kelompok E: AUTOMATED IMAGE PROCESSING (Hasil Pipeline)
_PROC_PIPELINE_ROWS: tuple[tuple[str, str], ...] = (
    ("pipe_stage", "Tahap akhir"),
    ("pipe_profile", "Profil"),
    ("pipe_bg_summary", "Background"),
    ("pipe_enh_summary", "Enhancement"),
    ("pipe_hist_summary", "Stretch visual"),
    ("pipe_gradient_reduc", "Reduksi gradien"),
    ("pipe_overcorrection", "Overcorrection"),
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
    """Label bagian metadata yang menyesuaikan format berkas (Informasi FITS, Metadata RAW, Informasi Video, Informasi SER, atau generik)."""
    if info is not None:
        if info.raw_metadata is not None:
            return "Metadata RAW"
        if info.fits_header is not None:
            return "Informasi FITS"
        if info.video_metadata is not None:
            return "Informasi Video"
        if info.ser_metadata is not None:
            return "Informasi SER"
    return "Metadata sumber"


def format_channels(info: ImageInfo) -> str:
    """Teks jumlah kanal sensor; jujur 'Tidak diketahui' bila tidak dapat dipastikan."""
    if info.raw_metadata is not None and info.raw_metadata.is_cfa_mosaic:
        return (
            f"1 (Sensor CFA Mosaic: {info.raw_metadata.cfa_pattern_str}) | "
            "Preview: 3 (RGB Demosaiced)"
        )
    if info.ser_metadata is not None and info.ser_metadata.is_cfa_mosaic:
        return (
            f"1 (Sensor CFA Mosaic: {info.ser_metadata.cfa_pattern_str}) | "
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
    if info.ser_metadata is not None and info.ser_metadata.is_cfa_mosaic:
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
    """Teks ringkasan metadata ilmiah (FITS, Camera RAW, atau SER), atau '-' bila bukan ketiganya."""
    if info.fits_header is not None:
        return info.fits_header.summary_text()
    if info.raw_metadata is not None:
        return info.raw_metadata.summary_text()
    if info.ser_metadata is not None:
        return info.ser_metadata.summary_text()
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
        app_icon = get_app_icon()
        if not app_icon.isNull():
            self.setWindowIcon(app_icon)
        self.resize(1200, 800)
        self.setMinimumSize(800, 560)
        self._last_dir: str = str(Path.home())
        self._info_keys: dict[str, QLabel] = {}
        self._info_values: dict[str, QLabel] = {}
        self._proc_keys: dict[str, QLabel] = {}
        self._proc_values: dict[str, QLabel] = {}
        self._full_fits_card_widgets: list[QWidget] = []
        self._full_fits_card_count: int = 0
        self.sequence_manager = SequenceManager()
        self._updating_combo: bool = False
        self._stacking_worker: StackingWorker | None = None
        self._last_stacking_result: StackingResult | None = None
        self._pipeline_worker: PipelineWorker | None = None
        self._last_pipeline_result: PipelineResult | None = None
        self._current_protected_roi: ProtectedRegionROI | None = None
        self._preview_mode: PreviewMode = PreviewMode.FINAL_DISPLAY
        self._is_showing_before: bool = False
        self._master_flat_path: Path | None = None
        self._loaded_master_flat: LoadedMasterFlat | None = None
        self._last_calibrated_frames: list[np.ndarray] | None = None
        self._last_allow_exclude_invalid: bool = False
        self._cancel_requested_by_ui: bool = False
        self._current_file_name: str = ""
        self.state_manager = ProcessingStateManager(parent=self)
        self.state_manager.state_changed.connect(self._on_processing_state_changed)

        self._build_ui()
        self.viewer.roi_selected.connect(self._on_roi_selected_from_viewer)
        self.viewer.zoom_changed.connect(self._on_viewer_zoom_changed)
        self.viewer.pixel_hovered.connect(self._on_viewer_pixel_hovered)
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

        viewer_column = QVBoxLayout()
        viewer_column.setSpacing(6)
        self.viewer = ImageViewer()
        self.image_action_toolbar = self._build_image_action_toolbar()
        viewer_column.addWidget(self.viewer, 1)
        viewer_column.addWidget(self.image_action_toolbar, 0)

        body.addLayout(viewer_column, 1)
        body.addWidget(self._build_info_panel(), 0)
        root.addLayout(body, 1)

        self._setup_status_bar()

    def _build_header(self) -> QHBoxLayout:
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(14)

        # Logo resmi HILALONE di sisi kiri judul
        self.logo_label = QLabel()
        self.logo_label.setObjectName("headerLogo")
        logo_pixmap = get_header_logo_pixmap(target_height=44)
        if not logo_pixmap.isNull():
            self.logo_label.setPixmap(logo_pixmap)
            self.logo_label.setFixedSize(logo_pixmap.size())
            self.logo_label.setScaledContents(False)
            header_layout.addWidget(self.logo_label, 0, Qt.AlignmentFlag.AlignVCenter)

        # Kontainer teks judul dan subtitle
        text_layout = QVBoxLayout()
        text_layout.setSpacing(0)
        text_layout.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel(APP_NAME)
        self.title_label.setObjectName("headerTitle")
        self.subtitle_label = QLabel(APP_SUBTITLE)
        self.subtitle_label.setObjectName("headerSubtitle")
        text_layout.addWidget(self.title_label)
        text_layout.addWidget(self.subtitle_label)

        header_layout.addLayout(text_layout)
        header_layout.addStretch(1)
        return header_layout

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
        self.open_video_button.setToolTip("Buka berkas video (.MP4, .MOV, .AVI)")
        self.open_video_button.clicked.connect(self.open_video_dialog)

        self.open_ser_button = QPushButton("SER")
        self.open_ser_button.setObjectName("secondaryButton")
        self.open_ser_button.setToolTip("Buka berkas video astronomi SER (.SER)")
        self.open_ser_button.clicked.connect(self.open_ser_dialog)

        self.close_button = QPushButton("Close Image")
        self.close_button.setObjectName("secondaryButton")
        self.close_button.clicked.connect(self.close_image)

        layout.addWidget(self.open_button)
        layout.addWidget(self.open_multi_button)
        layout.addWidget(self.open_folder_button)
        layout.addWidget(self.open_video_button)
        layout.addWidget(self.open_ser_button)
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

    def _build_image_action_toolbar(self) -> QWidget:
        """Membuat toolbar interaksi gambar (Icon-Only) tepat di bawah area gambar utama."""
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("imageActionToolbar")
        layout = QHBoxLayout(toolbar_frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        # 1. scan-eye — Hover Magnifier
        self.magnifier_button = QToolButton()
        self.magnifier_button.setProperty("class", "imageActionButton")
        self.magnifier_button.setIcon(create_vector_icon("scan-eye"))
        self.magnifier_button.setIconSize(QSize(20, 20))
        self.magnifier_button.setCheckable(True)
        self.magnifier_button.setToolTip(
            "Hover Magnifier / Kaca Pembesar (Aktifkan loupe interaktif di atas gambar. Klik kanan untuk memilih perbesaran 2×, 4×, 8×)"
        )
        self.magnifier_button.clicked.connect(self._on_magnifier_toggled)

        # Menu konteks / dropdown pilihan perbesaran loupe
        self.magnifier_menu = QMenu(self)
        self.mag_2x_action = self.magnifier_menu.addAction("Perbesaran 2×")
        self.mag_2x_action.setCheckable(True)
        self.mag_2x_action.setChecked(True)
        self.mag_2x_action.triggered.connect(lambda: self._set_magnifier_zoom(2))

        self.mag_4x_action = self.magnifier_menu.addAction("Perbesaran 4×")
        self.mag_4x_action.setCheckable(True)
        self.mag_4x_action.setChecked(False)
        self.mag_4x_action.triggered.connect(lambda: self._set_magnifier_zoom(4))

        self.mag_8x_action = self.magnifier_menu.addAction("Perbesaran 8×")
        self.mag_8x_action.setCheckable(True)
        self.mag_8x_action.setChecked(False)
        self.mag_8x_action.triggered.connect(lambda: self._set_magnifier_zoom(8))

        self.magnifier_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.magnifier_button.customContextMenuRequested.connect(
            lambda pos: self.magnifier_menu.exec(self.magnifier_button.mapToGlobal(pos))
        )

        # 2. zoom-out — Zoom Out
        self.zoom_out_button = QToolButton()
        self.zoom_out_button.setProperty("class", "imageActionButton")
        self.zoom_out_button.setIcon(create_vector_icon("zoom-out"))
        self.zoom_out_button.setIconSize(QSize(20, 20))
        self.zoom_out_button.setToolTip("Zoom Out / Perkecil (Klik atau putar mouse wheel ke bawah)")
        self.zoom_out_button.clicked.connect(self.viewer.zoom_out)

        # 3. zoom-in — Zoom In
        self.zoom_in_button = QToolButton()
        self.zoom_in_button.setProperty("class", "imageActionButton")
        self.zoom_in_button.setIcon(create_vector_icon("zoom-in"))
        self.zoom_in_button.setIconSize(QSize(20, 20))
        self.zoom_in_button.setToolTip("Zoom In / Perbesar (Klik atau putar mouse wheel ke atas)")
        self.zoom_in_button.clicked.connect(self.viewer.zoom_in)

        # 4. scan — Fit the Image
        self.fit_image_button = QToolButton()
        self.fit_image_button.setProperty("class", "imageActionButton")
        self.fit_image_button.setIcon(create_vector_icon("scan"))
        self.fit_image_button.setIconSize(QSize(20, 20))
        self.fit_image_button.setToolTip(
            "Fit the Image / Sesuaikan ke Jendela (Tampilkan seluruh citra proporsional)"
        )
        self.fit_image_button.clicked.connect(self.viewer.fit_to_viewport)

        # 5. maximize — Original Size / 1:1
        self.original_size_button = QToolButton()
        self.original_size_button.setProperty("class", "imageActionButton")
        self.original_size_button.setIcon(create_vector_icon("maximize"))
        self.original_size_button.setIconSize(QSize(20, 20))
        self.original_size_button.setToolTip(
            "Original Size / Ukuran Asli 1:1 (Pemetaan 1 piksel data ke 1 piksel layar)"
        )
        self.original_size_button.clicked.connect(self.viewer.set_original_size)

        layout.addWidget(self.magnifier_button)
        layout.addWidget(self.zoom_out_button)
        layout.addWidget(self.zoom_in_button)
        layout.addWidget(self.fit_image_button)
        layout.addWidget(self.original_size_button)

        layout.addStretch(1)

        # 6. save — Save Result
        self.save_result_action_button = QToolButton()
        self.save_result_action_button.setProperty("class", "imageActionButton")
        self.save_result_action_button.setIcon(create_vector_icon("save"))
        self.save_result_action_button.setIconSize(QSize(20, 20))
        self.save_result_action_button.setToolTip(
            "Save Result / Simpan Hasil (Pilih format Master Linear FITS/TIFF atau Display PNG)"
        )
        self.save_result_action_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        self.save_action_menu = QMenu(self)
        self.act_save_linear_fits = self.save_action_menu.addAction("Simpan Master Linear (FITS Float32)...")
        self.act_save_linear_fits.triggered.connect(lambda: self.save_pipeline_result_dialog("LINEAR_FITS"))

        self.act_save_linear_tiff = self.save_action_menu.addAction("Simpan Master Linear (TIFF Float32)...")
        self.act_save_linear_tiff.triggered.connect(lambda: self.save_pipeline_result_dialog("LINEAR_TIFF"))

        self.act_save_enhanced_fits = self.save_action_menu.addAction("Simpan Derived Enhanced (FITS Float32)...")
        self.act_save_enhanced_fits.triggered.connect(lambda: self.save_pipeline_result_dialog("ENHANCED_FITS"))

        self.save_action_menu.addSeparator()
        self.act_save_display_png = self.save_action_menu.addAction("Ekspor Pratinjau Tampilan (PNG)...")
        self.act_save_display_png.triggered.connect(lambda: self.save_pipeline_result_dialog("DISPLAY_PNG"))

        self.save_result_action_button.setMenu(self.save_action_menu)

        # 7. camera — Quick Snapshot
        self.snapshot_button = QToolButton()
        self.snapshot_button.setProperty("class", "imageActionButton")
        self.snapshot_button.setIcon(create_vector_icon("camera"))
        self.snapshot_button.setIconSize(QSize(20, 20))
        self.snapshot_button.setToolTip(
            "Quick Snapshot / Tangkapan Cepat (Simpan tampilan gambar saat ini ke format PNG)"
        )
        self.snapshot_button.clicked.connect(self.take_quick_snapshot)

        layout.addWidget(self.save_result_action_button)
        layout.addWidget(self.snapshot_button)

        return toolbar_frame

    def _setup_status_bar(self) -> None:
        """Menyiapkan indikator terstruktur di status bar bawah."""
        sb = self.statusBar()
        sb.setObjectName("statusBar")

        self.status_file_info = QLabel("Tidak ada berkas terbuka")
        self.status_file_info.setObjectName("infoKey")
        self.status_file_info.setStyleSheet("color: #94a3b8; padding-right: 12px;")

        self.status_res_info = QLabel("-")
        self.status_res_info.setObjectName("infoKey")
        self.status_res_info.setStyleSheet("color: #94a3b8; padding-right: 12px;")

        self.status_view_info = QLabel("Mode: Normal")
        self.status_view_info.setObjectName("infoKey")
        self.status_view_info.setStyleSheet("color: #94a3b8; padding-right: 12px;")

        self.status_zoom_info = QLabel("Zoom: -")
        self.status_zoom_info.setObjectName("infoKey")
        self.status_zoom_info.setStyleSheet("color: #38bdf8; font-weight: bold; padding-right: 12px;")

        self.status_pixel_info = QLabel("")
        self.status_pixel_info.setObjectName("infoKey")
        self.status_pixel_info.setStyleSheet("color: #e2e8f0; font-family: monospace; padding-right: 6px;")

        sb.addPermanentWidget(self.status_file_info)
        sb.addPermanentWidget(self.status_res_info)
        sb.addPermanentWidget(self.status_view_info)
        sb.addPermanentWidget(self.status_zoom_info)
        sb.addPermanentWidget(self.status_pixel_info)

    def _on_viewer_zoom_changed(self, zoom_factor: float, is_fit_mode: bool) -> None:
        """Memperbarui persentase zoom pada status bar saat zoom gambar berubah."""
        pct = int(round(zoom_factor * 100))
        if is_fit_mode:
            self.status_zoom_info.setText(f"Zoom: Fit ({pct}%)")
        elif math.isclose(zoom_factor, 1.0, rel_tol=1e-3):
            self.status_zoom_info.setText("Zoom: 100% (1:1)")
        else:
            self.status_zoom_info.setText(f"Zoom: {pct}%")

    def _on_viewer_pixel_hovered(self, img_x: int, img_y: int, val_str: str) -> None:
        """Memperbarui pembacaan koordinat piksel dan nilai intensitas di status bar."""
        if img_x >= 0 and img_y >= 0:
            self.status_pixel_info.setText(f"X:{img_x} Y:{img_y} | {val_str}")
        else:
            self.status_pixel_info.setText("")

    def _on_magnifier_toggled(self, checked: bool) -> None:
        """Menghidupkan atau mematikan Hover Magnifier."""
        self.viewer.set_magnifier_active(checked)
        if checked:
            self.statusBar().showMessage(
                f"Hover Magnifier aktif ({self.viewer.magnifier_zoom()}×). Arahkan mouse di atas gambar."
            )
        else:
            self.statusBar().showMessage("Hover Magnifier dinonaktifkan.")

    def _set_magnifier_zoom(self, zoom: int) -> None:
        """Mengatur faktor perbesaran Hover Magnifier (2x, 4x, atau 8x)."""
        self.viewer.set_magnifier_zoom(zoom)
        self.mag_2x_action.setChecked(zoom == 2)
        self.mag_4x_action.setChecked(zoom == 4)
        self.mag_8x_action.setChecked(zoom == 8)
        self.statusBar().showMessage(f"Perbesaran Hover Magnifier diatur ke {zoom}×.")

    def _refresh_image_toolbar_state(self) -> None:
        """Memperbarui status ketersediaan tombol toolbar aksi gambar."""
        has_img = self.viewer.has_image()
        self.magnifier_button.setEnabled(has_img)
        self.zoom_out_button.setEnabled(has_img)
        self.zoom_in_button.setEnabled(has_img)
        self.fit_image_button.setEnabled(has_img)
        self.original_size_button.setEnabled(has_img)
        self.snapshot_button.setEnabled(has_img)

        has_save_data = (
            has_img
            or (self._last_stacking_result is not None)
            or (self._last_pipeline_result is not None)
        )
        self.save_result_action_button.setEnabled(has_save_data)

        # Pengaturan ketersediaan item menu simpan
        has_pipeline = self._last_pipeline_result is not None
        has_stacking = self._last_stacking_result is not None
        self.act_save_linear_fits.setEnabled(has_pipeline or has_stacking or has_img)
        self.act_save_linear_tiff.setEnabled(has_pipeline or has_stacking or has_img)
        self.act_save_enhanced_fits.setEnabled(has_pipeline)
        self.act_save_display_png.setEnabled(has_img or has_pipeline or has_stacking)

        if not has_img:
            self.magnifier_button.setChecked(False)
            self.viewer.set_magnifier_active(False)

    def take_quick_snapshot(self) -> Path | None:
        """Mengambil tangkapan layar bersih area gambar aktif (Quick Snapshot) format PNG."""
        if not self.viewer.has_image():
            self._show_error("Tidak ada gambar yang sedang ditampilkan untuk diambil snapshot.")
            return None

        # Tentukan folder tujuan (folder terakhir atau folder kerja)
        save_dir = Path(self._last_dir) if self._last_dir else Path.home()
        if not save_dir.is_dir():
            save_dir = Path.home()

        from datetime import datetime
        now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"HILALONE_snapshot_{now_str}"
        candidate_path = save_dir / f"{base_name}.png"

        # Proteksi anti-overwrite: berikan counter _1, _2 jika ada benturan nama
        counter = 1
        while candidate_path.exists():
            candidate_path = save_dir / f"{base_name}_{counter}.png"
            counter += 1

        pixmap = self.viewer.render_view_pixmap()
        if pixmap.isNull():
            self._show_error("Gagal merender tangkapan layar gambar.")
            return None

        success = pixmap.save(str(candidate_path), "PNG")
        if not success:
            self._show_error(f"Gagal menyimpan snapshot ke: {candidate_path}")
            return None

        self._last_dir = str(candidate_path.parent)
        self.statusBar().showMessage(f"Snapshot tersimpan: {candidate_path.name}")
        self.stacking_status_label.setText(f"Snapshot cepat tersimpan: {candidate_path.name}")
        return candidate_path

    def _populate_key_value_grid(
        self,
        grid: QGridLayout,
        rows: tuple[tuple[str, str], ...],
        key_min_width: int = 112,
        target_keys: dict[str, QLabel] | None = None,
        target_values: dict[str, QLabel] | None = None,
    ) -> None:
        """Mengisi QGridLayout 2 kolom (label di kiri, nilai word-wrapped di kanan)."""
        keys_dict = self._info_keys if target_keys is None else target_keys
        vals_dict = self._info_values if target_values is None else target_values
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
            keys_dict[key] = key_label
            vals_dict[key] = value_label

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

    def _build_processing_card(self) -> QFrame:
        """Membangun kartu 'AUTOMATED IMAGE PROCESSING' untuk menjalankan Full Automated Pipeline."""
        card = QFrame()
        card.setObjectName("processingCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        self.header_processing = QLabel("AUTOMATED IMAGE PROCESSING")
        self.header_processing.setObjectName("sectionHeader")
        self.header_processing.setWordWrap(True)
        layout.addWidget(self.header_processing)

        # A. Profile selector
        prof_row = QHBoxLayout()
        prof_row.setSpacing(8)
        prof_lbl = QLabel("Profil:")
        prof_lbl.setObjectName("infoKey")
        prof_lbl.setMinimumWidth(68)
        self.profile_combo = QComboBox()
        self.profile_combo.addItem(
            "Basic — Konservatif", ProcessingProfile.BASIC.value
        )
        self.profile_combo.addItem(
            "Medium — Seimbang (Default)", ProcessingProfile.MEDIUM.value
        )
        self.profile_combo.addItem(
            "High — Adaptif", ProcessingProfile.HIGH.value
        )
        self.profile_combo.setCurrentIndex(1)  # Default: Medium
        self.profile_combo.currentIndexChanged.connect(self._on_profile_combo_changed)
        prof_row.addWidget(prof_lbl)
        prof_row.addWidget(self.profile_combo, 1)
        layout.addLayout(prof_row)

        self.profile_summary_label = QLabel("")
        self.profile_summary_label.setObjectName("infoKey")
        self.profile_summary_label.setWordWrap(True)
        layout.addWidget(self.profile_summary_label)

        # Bagian Collapsible: Pengaturan Lanjutan (Advanced Settings)
        self.adv_settings_toggle = QPushButton("▶ Pengaturan Lanjutan (Advanced Settings)")
        self.adv_settings_toggle.setObjectName("collapsibleButton")
        self.adv_settings_toggle.setCheckable(True)
        self.adv_settings_toggle.setChecked(False)
        self.adv_settings_toggle.toggled.connect(self._on_adv_settings_toggled)
        layout.addWidget(self.adv_settings_toggle)

        self.adv_settings_container = QFrame()
        self.adv_settings_container.setObjectName("fullHeaderBox")
        adv_layout = QVBoxLayout(self.adv_settings_container)
        adv_layout.setContentsMargins(8, 8, 8, 8)
        adv_layout.setSpacing(6)

        # 1. Background Settings
        bg_set_lbl = QLabel("1. Background Extraction")
        bg_set_lbl.setObjectName("subSectionHeader")
        adv_layout.addWidget(bg_set_lbl)

        bg_meth_row = QHBoxLayout()
        bg_meth_lbl = QLabel("Metode:")
        bg_meth_lbl.setObjectName("infoKey")
        bg_meth_lbl.setMinimumWidth(64)
        self.adv_bg_method_combo = QComboBox()
        self.adv_bg_method_combo.addItem("Polinomial Derajat 1", BackgroundModelMethod.POLYNOMIAL_DEG_1.value)
        self.adv_bg_method_combo.addItem("Polinomial Derajat 2", BackgroundModelMethod.POLYNOMIAL_DEG_2.value)
        self.adv_bg_method_combo.addItem("Thin Plate Spline RBF", BackgroundModelMethod.TPS_RBF.value)
        self.adv_bg_method_combo.addItem("Automatic Robust Mesh RBF", BackgroundModelMethod.AUTO_ROBUST_RBF.value)
        self.adv_bg_method_combo.setCurrentIndex(1)
        bg_meth_row.addWidget(bg_meth_lbl)
        bg_meth_row.addWidget(self.adv_bg_method_combo, 1)
        adv_layout.addLayout(bg_meth_row)

        # Protected ROI tools
        roi_btn_row = QHBoxLayout()
        roi_btn_row.setSpacing(6)
        self.roi_select_button = QPushButton("Tandai Wilayah Proteksi (ROI)")
        self.roi_select_button.setObjectName("secondaryButton")
        self.roi_select_button.setCheckable(True)
        self.roi_select_button.clicked.connect(self._on_roi_select_button_clicked)

        self.roi_clear_button = QPushButton("Hapus ROI")
        self.roi_clear_button.setObjectName("secondaryButton")
        self.roi_clear_button.setEnabled(False)
        self.roi_clear_button.clicked.connect(self.clear_protected_roi)

        roi_btn_row.addWidget(self.roi_select_button, 1)
        roi_btn_row.addWidget(self.roi_clear_button, 0)
        adv_layout.addLayout(roi_btn_row)

        self.roi_status_label = QLabel("ROI: Tidak ada (seluruh citra disampel)")
        self.roi_status_label.setObjectName("infoKey")
        self.roi_status_label.setWordWrap(True)
        adv_layout.addWidget(self.roi_status_label)

        # 2. Image Enhancement Settings
        enh_set_lbl = QLabel("2. Image Enhancement (CLAHE)")
        enh_set_lbl.setObjectName("subSectionHeader")
        adv_layout.addWidget(enh_set_lbl)

        self.adv_clahe_enable_checkbox = QCheckBox("Aktifkan CLAHE")
        self.adv_clahe_enable_checkbox.setChecked(True)
        adv_layout.addWidget(self.adv_clahe_enable_checkbox)

        enh_clip_row = QHBoxLayout()
        enh_clip_lbl = QLabel("Clip Limit:")
        enh_clip_lbl.setObjectName("infoKey")
        enh_clip_lbl.setMinimumWidth(64)
        self.adv_clahe_clip_combo = QComboBox()
        self.adv_clahe_clip_combo.addItem("0.008 (Sangat Ringan)", 0.008)
        self.adv_clahe_clip_combo.addItem("0.012 (Ringan)", 0.012)
        self.adv_clahe_clip_combo.addItem("0.016 (Moderat)", 0.016)
        self.adv_clahe_clip_combo.addItem("0.022 (Kuat)", 0.022)
        self.adv_clahe_clip_combo.setCurrentIndex(1)
        enh_clip_row.addWidget(enh_clip_lbl)
        enh_clip_row.addWidget(self.adv_clahe_clip_combo, 1)
        adv_layout.addLayout(enh_clip_row)

        # 3. Histogram Transformation Settings
        hist_set_lbl = QLabel("3. Histogram Transformation")
        hist_set_lbl.setObjectName("subSectionHeader")
        adv_layout.addWidget(hist_set_lbl)

        hist_meth_row = QHBoxLayout()
        hist_meth_lbl = QLabel("Stretch:")
        hist_meth_lbl.setObjectName("infoKey")
        hist_meth_lbl.setMinimumWidth(64)
        self.adv_stretch_combo = QComboBox()
        self.adv_stretch_combo.addItem("Linear + MTF", StretchMethod.LINEAR_MTF.value)
        self.adv_stretch_combo.addItem("Asinh + MTF", StretchMethod.ASINH_MTF.value)
        self.adv_stretch_combo.addItem("Adaptive Asinh + MTF", StretchMethod.ADAPTIVE_ASINH_MTF.value)
        self.adv_stretch_combo.addItem("GHS + MTF (Generalized Hyperbolic)", StretchMethod.GHS_MTF.value)
        self.adv_stretch_combo.setCurrentIndex(1)
        hist_meth_row.addWidget(hist_meth_lbl)
        hist_meth_row.addWidget(self.adv_stretch_combo, 1)
        adv_layout.addLayout(hist_meth_row)

        self.adv_settings_container.setVisible(False)
        layout.addWidget(self.adv_settings_container)

        # Informasi sebelum proses (frame counts, flat status)
        pre_grid = QGridLayout()
        self._populate_key_value_grid(
            pre_grid,
            _PROC_INFO_ROWS,
            key_min_width=112,
            target_keys=self._proc_keys,
            target_values=self._proc_values,
        )
        layout.addLayout(pre_grid)

        # Flat Calibration (Opsional)
        self.flat_checkbox = QCheckBox("Apply Flat Calibration (Opsional)")
        self.flat_checkbox.setChecked(False)
        self.flat_checkbox.toggled.connect(self._on_flat_checkbox_toggled)
        layout.addWidget(self.flat_checkbox)

        flat_type_row = QHBoxLayout()
        flat_type_row.setSpacing(6)
        flat_type_lbl = QLabel("Jenis Flat:")
        flat_type_lbl.setObjectName("infoKey")
        flat_type_lbl.setMinimumWidth(68)
        self.flat_input_type_combo = QComboBox()
        self.flat_input_type_combo.addItem(
            "Single Master Flat (FITS / TIFF / RAW / PNG / JPEG)", "single"
        )
        self.flat_input_type_combo.addItem(
            "Flat Frame Sequence — Multiple Images", "multi_files"
        )
        self.flat_input_type_combo.addItem(
            "Flat Frame Sequence — Folder", "folder"
        )
        self.flat_input_type_combo.addItem(
            "Flat Frame Sequence — Video (AVI / MP4 / MOV)", "video"
        )
        self.flat_input_type_combo.addItem(
            "Flat Frame Sequence — SER (.SER)", "ser"
        )
        self.flat_input_type_combo.setEnabled(False)
        flat_type_row.addWidget(flat_type_lbl)
        flat_type_row.addWidget(self.flat_input_type_combo, 1)
        layout.addLayout(flat_type_row)

        flat_btn_row = QHBoxLayout()
        flat_btn_row.setSpacing(6)
        self.select_flat_button = QPushButton("Select Master Flat...")
        self.select_flat_button.setObjectName("secondaryButton")
        self.select_flat_button.setEnabled(False)
        self.select_flat_button.clicked.connect(self.select_master_flat_dialog)

        self.start_calibration_button = QPushButton("Start Calibration")
        self.start_calibration_button.setObjectName("secondaryButton")
        self.start_calibration_button.setEnabled(False)
        self.start_calibration_button.clicked.connect(self.start_flat_calibration)

        self.preview_flat_button = QPushButton("Preview Flat")
        self.preview_flat_button.setObjectName("secondaryButton")
        self.preview_flat_button.setEnabled(False)
        self.preview_flat_button.clicked.connect(self.preview_master_flat)

        self.clear_flat_button = QPushButton("Remove Flat")
        self.clear_flat_button.setObjectName("secondaryButton")
        self.clear_flat_button.setEnabled(False)
        self.clear_flat_button.clicked.connect(self.clear_master_flat)

        flat_btn_row.addWidget(self.select_flat_button, 1)
        flat_btn_row.addWidget(self.start_calibration_button, 1)
        flat_btn_row.addWidget(self.preview_flat_button, 0)
        flat_btn_row.addWidget(self.clear_flat_button, 0)
        layout.addLayout(flat_btn_row)

        self.flat_file_label = QLabel("Master Flat: Tidak digunakan")
        self.flat_file_label.setObjectName("infoKey")
        self.flat_file_label.setWordWrap(True)
        layout.addWidget(self.flat_file_label)

        self.flat_details_container = QFrame()
        self.flat_details_container.setObjectName("fullHeaderBox")
        flat_det_layout = QVBoxLayout(self.flat_details_container)
        flat_det_layout.setContentsMargins(8, 8, 8, 8)
        flat_det_layout.setSpacing(4)

        flat_det_title = QLabel("INFORMASI MASTER FLAT")
        flat_det_title.setObjectName("subSectionHeader")
        flat_det_layout.addWidget(flat_det_title)

        flat_det_grid = QGridLayout()
        self._populate_key_value_grid(
            flat_det_grid,
            _PROC_FLAT_ROWS,
            key_min_width=106,
            target_keys=self._proc_keys,
            target_values=self._proc_values,
        )
        flat_det_layout.addLayout(flat_det_grid)
        self.flat_details_container.setVisible(False)
        layout.addWidget(self.flat_details_container)

        # B. TOMBOL UTAMA: Mulai Pemrosesan Otomatis & Cancel
        auto_action_row = QHBoxLayout()
        auto_action_row.setSpacing(8)
        self.start_auto_process_button = QPushButton("Mulai Pemrosesan Otomatis")
        self.start_auto_process_button.setObjectName("startAutoProcessButton")
        self.start_auto_process_button.setEnabled(False)
        self.start_auto_process_button.clicked.connect(self._on_start_auto_process_clicked)

        self.cancel_pipeline_button = QPushButton("Cancel")
        self.cancel_pipeline_button.setObjectName("secondaryButton")
        self.cancel_pipeline_button.setEnabled(False)
        self.cancel_pipeline_button.clicked.connect(self.cancel_automated_pipeline)

        auto_action_row.addWidget(self.start_auto_process_button, 1)
        auto_action_row.addWidget(self.cancel_pipeline_button, 0)
        layout.addLayout(auto_action_row)

        # Tombol Khusus Stacking Saja (Kompatibilitas Penuh)
        stacking_only_row = QHBoxLayout()
        stacking_only_row.setSpacing(8)
        self.start_stacking_button = QPushButton("Mulai Stacking (Hanya Stacking)")
        self.start_stacking_button.setObjectName("startStackingButton")
        self.start_stacking_button.setEnabled(False)
        self.start_stacking_button.clicked.connect(self._on_start_stacking_clicked)

        self.cancel_stacking_button = QPushButton("Cancel Stacking")
        self.cancel_stacking_button.setObjectName("secondaryButton")
        self.cancel_stacking_button.setEnabled(False)
        self.cancel_stacking_button.clicked.connect(self.cancel_stacking)

        stacking_only_row.addWidget(self.start_stacking_button, 1)
        stacking_only_row.addWidget(self.cancel_stacking_button, 0)
        layout.addLayout(stacking_only_row)

        # Progress bar & status proses pipeline
        self.stacking_progress_bar = QProgressBar()
        self.stacking_progress_bar.setRange(0, 100)
        self.stacking_progress_bar.setValue(0)
        self.stacking_progress_bar.setVisible(False)
        layout.addWidget(self.stacking_progress_bar)

        self.stacking_status_label = QLabel("Belum ada proses pemrosesan.")
        self.stacking_status_label.setObjectName("infoKey")
        self.stacking_status_label.setWordWrap(True)
        layout.addWidget(self.stacking_status_label)

        # Pratinjau Interaktif (Preview Mode Selector & Before/After Toggle)
        self.preview_controls_box = QFrame()
        self.preview_controls_box.setObjectName("fullHeaderBox")
        prev_ctrl_layout = QVBoxLayout(self.preview_controls_box)
        prev_ctrl_layout.setContentsMargins(8, 8, 8, 8)
        prev_ctrl_layout.setSpacing(6)

        prev_ctrl_title = QLabel("TAMPILAN PRATINJAU")
        prev_ctrl_title.setObjectName("subSectionHeader")
        prev_ctrl_layout.addWidget(prev_ctrl_title)

        prev_row = QHBoxLayout()
        prev_row.setSpacing(6)
        prev_mode_lbl = QLabel("Mode:")
        prev_mode_lbl.setObjectName("infoKey")
        prev_mode_lbl.setMinimumWidth(44)
        self.preview_mode_combo = QComboBox()
        self.preview_mode_combo.addItem("Final Display (Stretch)", PreviewMode.FINAL_DISPLAY.value)
        self.preview_mode_combo.addItem("Enhanced (CLAHE)", PreviewMode.ENHANCED.value)
        self.preview_mode_combo.addItem("Background Corrected (Linear)", PreviewMode.BACKGROUND_CORRECTED.value)
        self.preview_mode_combo.addItem("Background Model", PreviewMode.BACKGROUND_MODEL.value)
        self.preview_mode_combo.addItem("Original (Sebelum Proses)", PreviewMode.ORIGINAL.value)
        self.preview_mode_combo.currentIndexChanged.connect(self._on_preview_mode_changed)

        self.toggle_before_after_button = QPushButton("Before / After")
        self.toggle_before_after_button.setObjectName("toggleBeforeAfterButton")
        self.toggle_before_after_button.setCheckable(True)
        self.toggle_before_after_button.clicked.connect(self._on_toggle_before_after_clicked)

        prev_row.addWidget(prev_mode_lbl)
        prev_row.addWidget(self.preview_mode_combo, 1)
        prev_row.addWidget(self.toggle_before_after_button, 0)
        prev_ctrl_layout.addLayout(prev_row)

        self.preview_controls_box.setVisible(False)
        layout.addWidget(self.preview_controls_box)

        # Grafik Histogram Sebelum / Sesudah
        self.histogram_container = QFrame()
        self.histogram_container.setObjectName("fullHeaderBox")
        hist_layout = QVBoxLayout(self.histogram_container)
        hist_layout.setContentsMargins(8, 8, 8, 8)
        hist_layout.setSpacing(4)

        hist_title = QLabel("HISTOGRAM SEBELUM & SESUDAH")
        hist_title.setObjectName("subSectionHeader")
        hist_layout.addWidget(hist_title)

        self.histogram_chart_label = QLabel()
        self.histogram_chart_label.setObjectName("histogramBox")
        self.histogram_chart_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.histogram_chart_label.setMinimumHeight(120)
        hist_layout.addWidget(self.histogram_chart_label)

        self.histogram_container.setVisible(False)
        layout.addWidget(self.histogram_container)

        # Hasil Stacking & Pipeline
        self.stacking_result_container = QFrame()
        self.stacking_result_container.setObjectName("fullHeaderBox")
        res_layout = QVBoxLayout(self.stacking_result_container)
        res_layout.setContentsMargins(8, 8, 8, 8)
        res_layout.setSpacing(6)

        res_title = QLabel("HASIL PEMROSESAN")
        res_title.setObjectName("subSectionHeader")
        res_layout.addWidget(res_title)

        res_grid = QGridLayout()
        self._populate_key_value_grid(
            res_grid,
            _PROC_RESULT_ROWS,
            key_min_width=106,
            target_keys=self._proc_keys,
            target_values=self._proc_values,
        )
        res_layout.addLayout(res_grid)

        # Opsi Penyimpanan Hasil Komprehensif
        save_btn_layout = QVBoxLayout()
        save_btn_layout.setSpacing(4)

        self.save_linear_fits_button = QPushButton("Simpan Master Linear (FITS)")
        self.save_linear_fits_button.clicked.connect(lambda: self.save_pipeline_result_dialog("LINEAR_FITS"))
        self.save_linear_tiff_button = QPushButton("Simpan Master Linear (TIFF)")
        self.save_linear_tiff_button.setObjectName("secondaryButton")
        self.save_linear_tiff_button.clicked.connect(lambda: self.save_pipeline_result_dialog("LINEAR_TIFF"))
        self.save_enhanced_fits_button = QPushButton("Simpan Derived Enhanced (FITS)")
        self.save_enhanced_fits_button.setObjectName("secondaryButton")
        self.save_enhanced_fits_button.clicked.connect(lambda: self.save_pipeline_result_dialog("ENHANCED_FITS"))
        self.export_display_png_button = QPushButton("Ekspor Preview Visual (PNG)")
        self.export_display_png_button.setObjectName("secondaryButton")
        self.export_display_png_button.clicked.connect(lambda: self.save_pipeline_result_dialog("DISPLAY_PNG"))

        self.save_result_button = QPushButton("Save Result")
        self.save_result_button.setEnabled(False)
        self.save_result_button.clicked.connect(self.save_stacking_result_dialog)

        save_btn_layout.addWidget(self.save_linear_fits_button)
        save_btn_layout.addWidget(self.save_linear_tiff_button)
        save_btn_layout.addWidget(self.save_enhanced_fits_button)
        save_btn_layout.addWidget(self.export_display_png_button)
        save_btn_layout.addWidget(self.save_result_button)
        res_layout.addLayout(save_btn_layout)

        self.stacking_result_container.setVisible(False)
        layout.addWidget(self.stacking_result_container)
        return card

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
        self.section_processing = self._build_processing_card()
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
        self.section_video_info, self.header_video_info = self._create_section_card(
            "Informasi Video", _SECTION_VIDEO_ROWS
        )
        self.section_ser_info, self.header_ser_info = self._create_section_card(
            "Informasi SER", _SECTION_SER_ROWS
        )

        content_layout.addWidget(self.section_input_sequence)
        content_layout.addWidget(self.section_processing)
        content_layout.addWidget(self.section_image_info)
        content_layout.addWidget(self.section_sensor_info)
        content_layout.addWidget(self.section_camera_metadata)
        content_layout.addWidget(self.section_fits_info)
        content_layout.addWidget(self.section_video_info)
        content_layout.addWidget(self.section_ser_info)
        content_layout.addStretch(1)

        self.info_scroll_area.setWidget(self.info_scroll_content)
        outer_layout.addWidget(self.info_scroll_area, 1)
        return self.info_panel

    def _set_row_visible(self, key: str, visible: bool) -> None:
        if key in self._info_keys:
            self._info_keys[key].setVisible(visible)
        if key in self._info_values:
            self._info_values[key].setVisible(visible)
        if key in self._proc_keys:
            self._proc_keys[key].setVisible(visible)
        if key in self._proc_values:
            self._proc_values[key].setVisible(visible)

    def _set_row(self, key: str, value: str, visible: bool = True) -> None:
        if key in self._info_values:
            self._info_values[key].setText(value)
        if key in self._proc_values:
            self._proc_values[key].setText(value)
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

    def _video_file_dialog_filter(self) -> str:
        """Filter dialog untuk berkas video yang didukung."""
        patterns = " ".join(f"*.{ext}" for ext in VIDEO_EXTENSIONS)
        return f"Video yang didukung ({patterns});;Semua file (*)"

    def open_video_dialog(self) -> None:
        """Menampilkan dialog pemilih berkas video (.MP4, .MOV, .AVI) lalu memuatnya."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Buka Berkas Video (.MP4, .MOV, .AVI)",
            self._last_dir,
            self._video_file_dialog_filter(),
        )
        if not file_path:
            return
        self._last_dir = str(Path(file_path).parent)
        self.load_video_path(file_path)

    def open_video_placeholder(self) -> None:
        """Alias kompatibilitas yang membuka dialog pemilih berkas video."""
        self.open_video_dialog()

    def load_video_path(self, path: str | Path) -> bool:
        """Memuat berkas video ke dalam SequenceManager secara *lazy*."""
        try:
            report = self.sequence_manager.open_video_file(path)
        except ImageReadError as err:
            self._show_error(str(err))
            return False
        return self._finalize_sequence_open(report.warnings)

    def _ser_file_dialog_filter(self) -> str:
        """Filter dialog untuk berkas SER yang didukung."""
        patterns = " ".join(f"*.{ext}" for ext in SER_EXTENSIONS)
        return f"Berkas SER ({patterns});;Semua file (*)"

    def open_ser_dialog(self) -> None:
        """Menampilkan dialog pemilih berkas SER (.SER) lalu memuatnya."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Buka Berkas Astronomi SER (.SER)",
            self._last_dir,
            self._ser_file_dialog_filter(),
        )
        if not file_path:
            return
        self._last_dir = str(Path(file_path).parent)
        self.load_ser_path(file_path)

    def load_ser_path(
        self,
        path: str | Path,
        endianness_policy: str = "siril_default",
    ) -> bool:
        """Memuat berkas SER ke dalam SequenceManager secara *lazy*."""
        try:
            report = self.sequence_manager.open_ser_file(
                path, endianness_policy=endianness_policy
            )
        except ImageReadError as err:
            self._show_error(str(err))
            return False
        return self._finalize_sequence_open(report.warnings)

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

        self._last_stacking_result = None
        self._current_file_name = loaded.info.file_name
        self._refresh_sequence_controls()
        self._refresh_processing_controls()
        entry = self.sequence_manager.entries[0]
        self.viewer.set_image(loaded.preview, loaded.scientific_data)
        self._show_info(loaded.info, entry)
        self.close_button.setEnabled(True)
        if hasattr(self, "status_file_info"):
            self.status_file_info.setText(loaded.info.file_name)
            self.status_res_info.setText(f"{loaded.info.width} × {loaded.info.height} px")
            self.status_view_info.setText("Mode: Single Image")
        if hasattr(self, "image_action_toolbar"):
            self._refresh_image_toolbar_state()
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
        self._last_stacking_result = None
        self._refresh_sequence_controls()
        self._refresh_processing_controls()
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
        self._current_file_name = loaded.info.file_name
        self.viewer.set_image(loaded.preview, loaded.scientific_data)
        self._show_info(loaded.info, updated_entry)
        if hasattr(self, "status_file_info"):
            self.status_file_info.setText(loaded.info.file_name)
            self.status_res_info.setText(f"{loaded.info.width} × {loaded.info.height} px")
            self.status_view_info.setText(f"Mode: Frame [{index + 1}/{len(entries)}]")
        if hasattr(self, "image_action_toolbar"):
            self._refresh_image_toolbar_state()
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
        self.section_video_info.setVisible(False)
        self.section_ser_info.setVisible(False)
        self._last_pipeline_result = None
        self._last_stacking_result = None
        self._current_protected_roi = None
        self.viewer.set_roi_rect(None)
        self.viewer.roi_selection_enabled = False
        self.roi_select_button.setChecked(False)
        self.roi_clear_button.setEnabled(False)
        self.roi_status_label.setText("ROI: Tidak ada (seluruh citra disampel)")
        self.preview_controls_box.setVisible(False)
        self.histogram_container.setVisible(False)
        self.histogram_chart_label.clear()
        self.toggle_before_after_button.setChecked(False)
        self._is_showing_before = False
        self._refresh_processing_controls()
        self._refresh_sequence_controls()
        self._refresh_processing_controls()
        self.close_button.setEnabled(False)
        self._current_file_name = ""
        if hasattr(self, "state_manager"):
            self.state_manager.transition_to(ProcessingState.IDLE)
        self._set_input_controls_enabled(True)
        if hasattr(self, "status_file_info"):
            self.status_file_info.setText("Tidak ada berkas terbuka")
            self.status_res_info.setText("-")
            self.status_view_info.setText("Mode: Normal")
            self.status_zoom_info.setText("Zoom: -")
            self.status_pixel_info.setText("")
        if hasattr(self, "image_action_toolbar"):
            self._refresh_image_toolbar_state()
        self.statusBar().showMessage(STATUS_EMPTY)

    def _format_mode_text(self) -> str:
        mode = self.sequence_manager.input_mode
        if mode == InputMode.SINGLE:
            return "Single Image"
        if mode == InputMode.MULTI:
            return "Multiple Images"
        if mode == InputMode.VIDEO:
            return "Video Sequence"
        if mode == InputMode.SER:
            return "SER Sequence"
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
        is_multi = self.sequence_manager.input_mode in (
            InputMode.MULTI,
            InputMode.VIDEO,
            InputMode.SER,
        )
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
            ser_cfa = (
                info.ser_metadata.cfa_pattern_str
                if (info.ser_metadata is not None and info.ser_metadata.cfa_pattern_str)
                else None
            )
            self._set_row("cfa_pattern", ser_cfa or EMPTY_VALUE, visible=bool(ser_cfa))
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
            self.section_video_info.setVisible(False)
            self.section_ser_info.setVisible(False)
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

        vmeta = info.video_metadata
        if vmeta is not None:
            self._clear_full_fits_header_grid()
            self.section_fits_info.setVisible(False)
            self.section_ser_info.setVisible(False)
            self.header_video_info.setText("Informasi Video")
            dv = vmeta.to_display_dict()
            self._set_row("video_container", f"{dv['CONTAINER']} ({dv['FILE_SIZE']})", visible=True)
            self._set_row("video_stream", dv["VIDEO_STREAM"], visible=True)
            self._set_row("video_codec", dv["CODEC"], visible=True)
            pix_txt = info.decoded_pix_fmt or vmeta.pix_fmt
            self._set_row("video_pix_fmt", f"{pix_txt} ({vmeta.bits_per_component}-bit)", visible=True)
            self._set_row("video_fps", dv["FRAME_RATE"], visible=True)
            self._set_row("video_time_base", dv["TIME_BASE"], visible=True)

            if info.frame_timestamp_sec is not None and info.frame_pts is not None:
                pts_txt = f"{info.frame_timestamp_sec:.6f} s (PTS={info.frame_pts})"
            elif info.frame_pts is not None:
                pts_txt = f"PTS={info.frame_pts}"
            else:
                pts_txt = VIDEO_UNAVAILABLE
            self._set_row("video_frame_pts", pts_txt, visible=True)

            self._set_row("video_duration", dv["DURATION"], visible=True)
            self._set_row(
                "video_bit_rate",
                dv["BIT_RATE"],
                visible=(dv["BIT_RATE"] != VIDEO_UNAVAILABLE),
            )
            self._set_row(
                "video_color_meta",
                dv["COLOR_META"],
                visible=(dv["COLOR_META"] != VIDEO_UNAVAILABLE),
            )
            self._set_row("video_honesty_note", vmeta.honesty_note, visible=True)
            self._set_row("fits_metadata", vmeta.summary_text(), visible=False)
            self.section_video_info.setVisible(True)
            return

        self.section_video_info.setVisible(False)
        for vk, _ in _SECTION_VIDEO_ROWS:
            self._set_row(vk, EMPTY_VALUE, visible=False)

        smeta = info.ser_metadata
        if smeta is not None:
            self._clear_full_fits_header_grid()
            self.section_fits_info.setVisible(False)
            self.header_ser_info.setText("Informasi SER")
            ds = smeta.to_display_dict()
            self._set_row("ser_file_id", ds["FILE_ID"], visible=True)
            self._set_row("ser_file_size", ds["FILE_SIZE"], visible=True)
            self._set_row("ser_color_id", ds["COLOR_ID"], visible=True)
            self._set_row(
                "ser_cfa_pattern",
                ds["CFA_PATTERN"],
                visible=bool(smeta.cfa_pattern_str),
            )
            self._set_row("ser_resolution", ds["RESOLUTION"], visible=True)
            self._set_row("ser_pixel_depth", ds["PIXEL_DEPTH"], visible=True)
            self._set_row("ser_endianness", ds["ENDIANNESS"], visible=True)
            self._set_row("ser_frame_count", ds["FRAME_COUNT"], visible=True)
            self._set_row(
                "ser_observer",
                ds["OBSERVER"],
                visible=(ds["OBSERVER"] != SER_UNAVAILABLE),
            )
            self._set_row(
                "ser_instrument",
                ds["INSTRUMENT"],
                visible=(ds["INSTRUMENT"] != SER_UNAVAILABLE),
            )
            self._set_row(
                "ser_telescope",
                ds["TELESCOPE"],
                visible=(ds["TELESCOPE"] != SER_UNAVAILABLE),
            )
            self._set_row(
                "ser_datetime_local",
                ds["DATETIME_LOCAL"],
                visible=(ds["DATETIME_LOCAL"] != SER_UNAVAILABLE),
            )
            self._set_row(
                "ser_datetime_utc",
                ds["DATETIME_UTC"],
                visible=(ds["DATETIME_UTC"] != SER_UNAVAILABLE),
            )
            self._set_row("ser_trailer_status", ds["TRAILER_STATUS"], visible=True)

            if info.frame_timestamp_utc_str is not None and info.frame_timestamp_sec is not None:
                fts_txt = (
                    f"{info.frame_timestamp_utc_str} (+{info.frame_timestamp_sec:.4f} s, "
                    f"ticks={info.frame_timestamp_ticks})"
                )
            elif info.frame_timestamp_utc_str is not None:
                fts_txt = info.frame_timestamp_utc_str
            else:
                fts_txt = SER_UNAVAILABLE
            self._set_row("ser_frame_timestamp", fts_txt, visible=True)
            self._set_row("ser_honesty_note", smeta.honesty_note, visible=True)
            self._set_row("fits_metadata", smeta.summary_text(), visible=False)
            self.section_ser_info.setVisible(True)
            return

        self.section_ser_info.setVisible(False)
        for sk, _ in _SECTION_SER_ROWS:
            self._set_row(sk, EMPTY_VALUE, visible=False)

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
        self.section_video_info.setVisible(False)
        self.section_ser_info.setVisible(False)
        self._refresh_processing_controls()

    def _show_error(self, message: str) -> None:
        """Menampilkan pesan galat kepada pengguna (dipisah agar mudah diuji)."""
        QMessageBox.warning(self, "Gagal membuka gambar", message)

    def _show_warning(self, message: str) -> None:
        """Menampilkan peringatan sequence kepada pengguna (dipisah agar mudah diuji)."""
        QMessageBox.warning(self, "Peringatan Sequence", message)

    # ------------------------------------------------- IMAGE PROCESSING (STACKING)
    def selected_stacking_profile(self) -> StackingProfile:
        """Mengembalikan profil stacking yang sedang dipilih pada dropdown."""
        raw_val = self.profile_combo.currentData()
        if isinstance(raw_val, StackingProfile):
            return raw_val
        if isinstance(raw_val, str):
            for p in StackingProfile:
                if p.value == raw_val:
                    return p
        return StackingProfile.MEDIUM

    def set_stacking_profile(self, profile: StackingProfile | str) -> None:
        """Mengatur pilihan profil stacking pada dropdown."""
        target = profile.value if isinstance(profile, StackingProfile) else str(profile).strip().upper()
        for idx in range(self.profile_combo.count()):
            if self.profile_combo.itemData(idx) == target:
                self.profile_combo.setCurrentIndex(idx)
                return

    def _on_profile_combo_changed(self, _index: int) -> None:
        self._refresh_processing_controls()

    def _on_flat_checkbox_toggled(self, checked: bool) -> None:
        is_running = self._is_stacking_running() or self._is_pipeline_running()
        self.flat_input_type_combo.setEnabled(checked and not is_running)
        self.select_flat_button.setEnabled(checked and not is_running)
        has_flat = self._loaded_master_flat is not None
        has_frames = self.sequence_manager.frame_count > 0
        self.start_calibration_button.setEnabled(checked and has_flat and has_frames and not is_running)
        self.preview_flat_button.setEnabled(checked and has_flat and not is_running)
        self.clear_flat_button.setEnabled(checked and has_flat and not is_running)
        self._refresh_processing_controls()

    def _all_flat_file_dialog_filter(self) -> str:
        """Filter dialog lengkap yang mencakup seluruh format Master Flat (Gambar, Video, & SER)."""
        img_exts = " ".join(f"*.{ext}" for ext in supported_extensions())
        vid_exts = " ".join(f"*.{ext}" for ext in VIDEO_EXTENSIONS)
        ser_exts = " ".join(f"*.{ext}" for ext in SER_EXTENSIONS)
        all_exts = f"{img_exts} {vid_exts} {ser_exts}".strip()
        return (
            f"Semua Format Master Flat ({all_exts});;"
            f"Single Master Flat Gambar ({img_exts});;"
            f"Video Flat ({vid_exts});;"
            f"SER Flat ({ser_exts});;"
            "Semua file (*)"
        )

    def select_master_flat_dialog(self) -> None:
        """Membuka dialog pemilih Single Master Flat atau Flat Frame Sequence sesuai pilihan pengguna."""
        flat_mode = str(self.flat_input_type_combo.currentData() or "single")
        if flat_mode == "multi_files":
            file_paths, _ = QFileDialog.getOpenFileNames(
                self,
                "Pilih Berkas-Berkas Flat Frame Sequence",
                self._last_dir,
                self._file_dialog_filter(),
            )
            if not file_paths:
                return
            self._last_dir = str(Path(file_paths[0]).parent)
            self.set_master_flat_sequence(file_paths, source_kind="files")
            return

        if flat_mode == "folder":
            folder = QFileDialog.getExistingDirectory(
                self,
                "Pilih Folder Flat Frame Sequence",
                self._last_dir,
            )
            if not folder:
                return
            self._last_dir = folder
            self.set_master_flat_sequence(folder, source_kind="folder")
            return

        if flat_mode == "video":
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Pilih Video Flat Frame Sequence (.AVI, .MP4, .MOV)",
                self._last_dir,
                self._video_file_dialog_filter(),
            )
            if not file_path:
                return
            self._last_dir = str(Path(file_path).parent)
            self.set_master_flat_sequence(file_path, source_kind="video")
            return

        if flat_mode == "ser":
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Pilih Berkas SER Flat Frame Sequence (.SER)",
                self._last_dir,
                self._ser_file_dialog_filter(),
            )
            if not file_path:
                return
            self._last_dir = str(Path(file_path).parent)
            self.set_master_flat_sequence(file_path, source_kind="ser")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Pilih Master Flat (FITS, TIFF, RAW, PNG, JPEG, AVI, MP4, MOV, SER)",
            self._last_dir,
            self._all_flat_file_dialog_filter(),
        )
        if not file_path:
            return
        self._last_dir = str(Path(file_path).parent)
        self.set_master_flat_path(file_path)

    def set_master_flat_path(
        self,
        path: str | Path | None,
        *,
        page_index: int | None = None,
        hdu_index: int | None = None,
    ) -> bool:
        """Memuat Single Master Flat (atau file Video/SER flat) secara terprogram atau dari dialog."""
        if path is None:
            self.clear_master_flat()
            return False

        p = Path(path)
        try:
            loaded_flat = load_master_flat_auto(
                p,
                page_index=page_index,
                hdu_index=hdu_index,
            )
        except MultiPageTiffError as multi_err:
            chosen = self._ask_tiff_page(multi_err.path, multi_err.pages)
            if chosen is None:
                return False
            return self.set_master_flat_path(p, page_index=chosen)
        except MultiHduFitsError as fits_err:
            chosen_hdu = self._ask_fits_hdu(
                fits_err.path, fits_err.image_hdus, fits_err.total_hdu_count
            )
            if chosen_hdu is None:
                return False
            return self.set_master_flat_path(p, hdu_index=chosen_hdu)
        except (StackingError, ImageReadError) as err:
            self._show_error(str(err))
            return False

        self._apply_loaded_master_flat(loaded_flat, primary_path=p)
        return True

    def set_master_flat_sequence(
        self,
        source: str | Path | Iterable[str | Path] | SequenceManager,
        *,
        source_kind: str = "auto",
        endianness_policy: str = "siril_default",
    ) -> bool:
        """Membuat dan menetapkan Master Flat dari sequence frame flat (Multiple Images, Folder, Video, SER)."""
        try:
            loaded_flat = load_master_flat_from_sequence(
                source,
                source_kind=source_kind,
                endianness_policy=endianness_policy,
            )
        except (StackingError, ImageReadError) as err:
            self._show_error(str(err))
            return False

        primary = loaded_flat.source_paths[0] if loaded_flat.source_paths else None
        self._apply_loaded_master_flat(loaded_flat, primary_path=primary)
        return True

    def _apply_loaded_master_flat(
        self,
        loaded_flat: LoadedMasterFlat,
        *,
        primary_path: Path | None = None,
    ) -> None:
        self._loaded_master_flat = loaded_flat
        self._master_flat_path = primary_path
        if primary_path is not None:
            self._last_dir = str(primary_path.parent if primary_path.is_file() else primary_path)
        self.flat_checkbox.setChecked(True)
        self.flat_file_label.setText(f"Master Flat: {loaded_flat.source_description}")
        is_running = self._is_stacking_running()
        self.preview_flat_button.setEnabled(not is_running)
        self.clear_flat_button.setEnabled(not is_running)
        self._refresh_processing_controls()

        if loaded_flat.warnings:
            self._show_warning(
                "Peringatan Master Flat:\n\n" + "\n".join(f"• {w}" for w in loaded_flat.warnings)
            )

    def preview_master_flat(self) -> bool:
        """Menampilkan pratinjau Master Flat yang sedang dipilih pada ImageViewer."""
        if self._loaded_master_flat is None:
            self._show_error("Belum ada Master Flat yang dipilih untuk dipratinjau.")
            return False
        self.viewer.set_image(self._loaded_master_flat.preview)
        self.statusBar().showMessage(
            f"Preview Master Flat: {self._loaded_master_flat.source_description}  |  "
            f"{self._loaded_master_flat.width} × {self._loaded_master_flat.height} px  |  "
            f"{self._loaded_master_flat.flat_format}"
        )
        return True

    def start_flat_calibration(self) -> bool:
        """Menjalankan kalibrasi Master Flat secara langsung pada sequence aktif tanpa preflight checks."""
        if self._loaded_master_flat is None:
            self._show_error("Pilih berkas atau sequence Master Flat terlebih dahulu.")
            return False

        if self.sequence_manager.frame_count == 0:
            self._show_error("Buka citra atau sequence light frame terlebih dahulu.")
            return False

        self._set_input_controls_enabled(False)
        self.stacking_progress_bar.setVisible(True)
        self.stacking_progress_bar.setValue(0)
        self.stacking_status_label.setText("Menjalankan Flat Calibration secara langsung...")
        self.statusBar().showMessage("Menerapkan koreksi Master Flat...")

        try:
            from PySide6.QtCore import QCoreApplication
            from hilalone.input_manager.preview_builder import array_to_preview_qimage
            from hilalone.processing.stacking.flat_calibration import run_flat_calibration_on_sequence

            def _prog(cur: int, tot: int, msg: str) -> None:
                pct = int(round(100.0 * cur / max(1, tot)))
                self.stacking_progress_bar.setValue(pct)
                self.stacking_status_label.setText(msg)
                QCoreApplication.processEvents()

            calibrated_frames, report = run_flat_calibration_on_sequence(
                self.sequence_manager,
                self._loaded_master_flat,
                progress_callback=_prog,
            )
            self._last_calibrated_frames = calibrated_frames

            self.stacking_progress_bar.setValue(100)
            self.stacking_status_label.setText(
                f"Kalibrasi Flat selesai: {len(calibrated_frames)} frame berhasil dikalibrasi "
                f"({report.normalization_method})."
            )
            if calibrated_frames:
                prev = array_to_preview_qimage(calibrated_frames[0])
                self.viewer.set_image(prev)
            self.statusBar().showMessage(
                f"Flat Calibration selesai: {len(calibrated_frames)} frame dikalibrasi."
            )
            return True
        except Exception as exc:
            self.stacking_status_label.setText(f"Kalibrasi Flat gagal: {exc}")
            self._show_error(f"Gagal menjalankan Kalibrasi Flat: {exc}")
            return False
        finally:
            self._set_input_controls_enabled(True)
            self._refresh_processing_controls(preserve_status_label=True)

    def clear_master_flat(self) -> None:
        """Menghapus pilihan berkas/sequence Master Flat."""
        self._loaded_master_flat = None
        self._master_flat_path = None
        self.flat_file_label.setText("Master Flat: Tidak digunakan")
        self.preview_flat_button.setEnabled(False)
        self.clear_flat_button.setEnabled(False)
        self._refresh_processing_controls()

    def _evaluate_current_flat_compatibility(self) -> FlatCompatibilityCheckResult | None:
        """Memeriksa kompatibilitas Master Flat yang sedang dimuat terhadap sequence light frame aktif."""
        if self._loaded_master_flat is None:
            return None
        if (
            self.sequence_manager.frame_count == 0
            or not self.sequence_manager.stacking_required
            or self.sequence_manager.compatibility_report.compatible_count == 0
        ):
            return None

        ref_idx = self.sequence_manager.compatibility_report.reference_frame_index
        if ref_idx is None:
            ref_idx = 0
        entries = self.sequence_manager.entries
        if not (0 <= ref_idx < len(entries)):
            return None
        ref_info = entries[ref_idx].info
        if ref_info is None:
            return None

        ref_is_cfa, ref_cfa_pat = extract_frame_cfa_info(ref_info)
        return check_flat_compatibility(
            self._loaded_master_flat,
            expected_height=ref_info.height,
            expected_width=ref_info.width,
            expected_channels=ref_info.channels or 1,
            expected_is_cfa=ref_is_cfa,
            expected_cfa_pattern=ref_cfa_pat,
            reference_bit_depth=ref_info.original_bit_depth,
            reference_orientation=ref_info.exif_orientation,
            reference_info=ref_info,
        )

    def _update_flat_details_section(
        self,
        compat: FlatCompatibilityCheckResult | None,
    ) -> None:
        """Memperbarui kotak 'INFORMASI MASTER FLAT' pada panel Image Processing."""
        lf = self._loaded_master_flat
        if lf is None:
            self.flat_details_container.setVisible(False)
            for k, _ in _PROC_FLAT_ROWS:
                self._set_row(k, EMPTY_VALUE, visible=False)
            return

        if lf.is_cfa_mosaic:
            ch_txt = f"1 kanal (Bayer CFA: {lf.cfa_pattern_str or 'Mosaic'})"
        elif lf.channels == 1:
            ch_txt = "1 kanal (Monokrom)"
        else:
            ch_txt = f"{lf.channels} kanal (RGB)"

        bd_txt = f"{lf.bit_depth}-bit" if lf.bit_depth is not None else lf.dtype_str
        meta_txt = (
            f"{lf.flat_format} | {lf.width}×{lf.height} px | {ch_txt} | "
            f"dtype: {lf.dtype_str} ({bd_txt})"
        )

        (
            med_val,
            _mean_val,
            inv_count,
            zero_neg_count,
            non_finite_count,
            sat_count,
            _inv_mask,
        ) = compute_flat_pixel_statistics(
            lf.scientific_data,
            saturation_ceiling=lf.saturation_ceiling,
            is_cfa_mosaic=lf.is_cfa_mosaic,
        )

        if compat is None:
            compat_txt = "Menunggu sequence light frame dibuka untuk verifikasi kompatibilitas"
        elif compat.is_compatible:
            compat_txt = "KOMPATIBEL (Dimensi, kanal, dan domain sensor cocok)"
        else:
            compat_txt = compat.status_text

        norm_txt = f"Siap ({NORMALIZATION_FORMULA_TEXT} | Median awal: {med_val:.4g})"
        inv_txt = (
            f"{inv_count} piksel (Nol/Negatif: {zero_neg_count}, "
            f"NaN/Inf: {non_finite_count}, Saturated: {sat_count})"
        )

        self._set_row("flat_source_info", lf.source_description, visible=True)
        self._set_row("flat_format_meta", meta_txt, visible=True)
        self._set_row("flat_compat_status", compat_txt, visible=True)
        self._set_row("flat_norm_status", norm_txt, visible=True)
        self._set_row("flat_invalid_pixels", inv_txt, visible=True)
        self.flat_details_container.setVisible(True)

    def _is_stacking_running(self) -> bool:
        return self._stacking_worker is not None and self._stacking_worker.isRunning()

    def _is_pipeline_running(self) -> bool:
        return self._pipeline_worker is not None and self._pipeline_worker.isRunning()

    def _on_adv_settings_toggled(self, checked: bool) -> None:
        arrow = "▼" if checked else "▶"
        self.adv_settings_toggle.setText(f"{arrow} Pengaturan Lanjutan (Advanced Settings)")
        self.adv_settings_container.setVisible(checked)

    def _on_roi_select_button_clicked(self, checked: bool) -> None:
        self.viewer.roi_selection_enabled = checked
        if checked:
            self.statusBar().showMessage(
                "Mode Wilayah Proteksi (ROI) aktif: Seret mouse pada gambar untuk menandai area sabit."
            )
        else:
            self.statusBar().showMessage("Mode Wilayah Proteksi dinonaktifkan.")

    def _on_roi_selected_from_viewer(self, x: int, y: int, w: int, h: int) -> None:
        self._current_protected_roi = ProtectedRegionROI(
            shape_type="RECTANGLE",
            rect=(x, y, w, h),
            label=f"ROI ({w}×{h} px)",
        )
        self.roi_status_label.setText(f"ROI: x={x}, y={y}, {w}×{h} px (Terlindungi)")
        self.roi_clear_button.setEnabled(True)
        self.roi_select_button.setChecked(False)
        self.viewer.roi_selection_enabled = False
        self.statusBar().showMessage(f"Wilayah proteksi ditetapkan: x={x}, y={y}, {w}×{h} px.")

    def clear_protected_roi(self) -> None:
        self._current_protected_roi = None
        self.viewer.set_roi_rect(None)
        self.viewer.roi_selection_enabled = False
        self.roi_select_button.setChecked(False)
        self.roi_clear_button.setEnabled(False)
        self.roi_status_label.setText("ROI: Tidak ada (seluruh citra disampel)")
        self.statusBar().showMessage("Wilayah proteksi dihapus.")

    def selected_processing_profile(self) -> ProcessingProfile:
        raw_val = self.profile_combo.currentData()
        if isinstance(raw_val, ProcessingProfile):
            return raw_val
        if isinstance(raw_val, str):
            for p in ProcessingProfile:
                if p.value == raw_val:
                    return p
        return ProcessingProfile.MEDIUM

    def set_processing_profile(self, profile: ProcessingProfile | str) -> None:
        target = profile.value if isinstance(profile, ProcessingProfile) else str(profile).strip().upper()
        for idx in range(self.profile_combo.count()):
            if self.profile_combo.itemData(idx) == target:
                self.profile_combo.setCurrentIndex(idx)
                return

    def _on_preview_mode_changed(self, _index: int) -> None:
        if self._last_pipeline_result is None:
            return
        mode_val = self.preview_mode_combo.currentData()
        for m in PreviewMode:
            if m.value == mode_val:
                self._preview_mode = m
                break
        self._update_displayed_preview()

    def _on_toggle_before_after_clicked(self, checked: bool) -> None:
        self._is_showing_before = checked
        self._update_displayed_preview()

    def _update_displayed_preview(self) -> None:
        if self._last_pipeline_result is None:
            return
        if self._is_showing_before:
            img = self._last_pipeline_result.previews.get(PreviewMode.ORIGINAL)
            self.statusBar().showMessage("Menampilkan Pratinjau: Original (Sebelum Pemrosesan)")
        else:
            img = self._last_pipeline_result.previews.get(self._preview_mode)
            self.statusBar().showMessage(f"Menampilkan Pratinjau: {self._preview_mode.value}")
        if img is not None and not img.isNull():
            sci_target = (
                self._last_pipeline_result.linear_result
                if self._last_pipeline_result.linear_result is not None
                else self._last_pipeline_result.stacked_data
            )
            if sci_target is None:
                sci_target = self._last_pipeline_result.original_data
            self.viewer.set_image(img, sci_target)
            if hasattr(self, "image_action_toolbar"):
                self._refresh_image_toolbar_state()
            if hasattr(self, "status_view_info"):
                mode_str = "Sebelum Pemrosesan" if self._is_showing_before else self._preview_mode.value
                self.status_view_info.setText(f"Pratinjau: {mode_str}")

    def _on_processing_state_changed(self, state: ProcessingState) -> None:
        """Menangani sinkronisasi status UI berdasarkan status pemrosesan aktif."""
        is_busy = self.state_manager.is_busy
        self._set_input_controls_enabled(not is_busy)

    def _set_input_controls_enabled(self, enabled: bool) -> None:
        """Mengaktifkan/menonaktifkan tombol navigasi & pembuka berkas selama pemrosesan berjalan."""
        self.open_button.setEnabled(enabled)
        self.open_multi_button.setEnabled(enabled)
        self.open_folder_button.setEnabled(enabled)
        self.open_video_button.setEnabled(enabled)
        self.open_ser_button.setEnabled(enabled)
        has_any_image = self.sequence_manager.frame_count > 0 or self.viewer.has_image()
        self.close_button.setEnabled(enabled and has_any_image)
        self.profile_combo.setEnabled(enabled)
        self.adv_settings_toggle.setEnabled(enabled)
        self.adv_bg_method_combo.setEnabled(enabled)
        self.adv_clahe_enable_checkbox.setEnabled(enabled)
        self.adv_clahe_clip_combo.setEnabled(enabled)
        self.adv_stretch_combo.setEnabled(enabled)
        self.flat_checkbox.setEnabled(enabled)
        flat_checked = self.flat_checkbox.isChecked()
        has_flat = self._loaded_master_flat is not None
        self.flat_input_type_combo.setEnabled(enabled and flat_checked)
        self.select_flat_button.setEnabled(enabled and flat_checked)
        self.preview_flat_button.setEnabled(enabled and flat_checked and has_flat)
        self.clear_flat_button.setEnabled(enabled and flat_checked and has_flat)
        self.roi_select_button.setEnabled(enabled and has_any_image)
        self.roi_clear_button.setEnabled(enabled and self._current_protected_roi is not None)
        if enabled:
            self._refresh_sequence_controls()
        else:
            self.frame_combo.setEnabled(False)
            self.prev_frame_button.setEnabled(False)
            self.next_frame_button.setEnabled(False)
        if hasattr(self, "image_action_toolbar"):
            self._refresh_image_toolbar_state()

    def _refresh_processing_controls(self, *, preserve_status_label: bool = False) -> None:
        """Memperbarui informasi pra-pemrosesan dan status tombol 'Mulai Pemrosesan Otomatis'."""
        prof_enum = self.selected_processing_profile()
        u_cfg = get_unified_profile_config(prof_enum)
        self.profile_summary_label.setText(
            f"{u_cfg.short_summary_id}\n"
            f"Karakteristik: {u_cfg.characteristics_id}\n"
            f"Risiko: {u_cfg.risk_note_id}"
        )

        stk_cfg = u_cfg.stacking_config
        method_txt = f"{stk_cfg.profile.value} — {stk_cfg.description_id}"
        self._set_row("proc_method", method_txt, visible=True)

        flat_compat = self._evaluate_current_flat_compatibility()
        self._update_flat_details_section(flat_compat)

        flat_checked = self.flat_checkbox.isChecked()
        has_flat = self._loaded_master_flat is not None
        if flat_checked:
            if not has_flat:
                flat_txt = "Aktif — Master Flat belum dipilih (belum diterapkan)"
            else:
                flat_txt = f"Siap diterapkan ({self._loaded_master_flat.source_description})"
        else:
            flat_txt = "Nonaktif (Opsional)"
        self._set_row("proc_flat_status", flat_txt, visible=True)

        mode = self.sequence_manager.input_mode
        total = self.sequence_manager.frame_count
        rep = self.sequence_manager.compatibility_report

        is_running = self._is_stacking_running() or self._is_pipeline_running()
        self.cancel_stacking_button.setEnabled(self._is_stacking_running())
        self.cancel_pipeline_button.setEnabled(self._is_pipeline_running())
        self.start_calibration_button.setEnabled(
            not is_running and flat_checked and has_flat and total > 0
        )

        has_any_image = total > 0 or self.viewer.has_image()
        self.roi_select_button.setEnabled(has_any_image and not is_running)
        self.roi_clear_button.setEnabled(self._current_protected_roi is not None and not is_running)

        flat_ready_to_click = (not flat_checked) or has_flat

        if total == 0:
            self._set_row("proc_total_frames", "0 frame", visible=True)
            self._set_row("proc_compatible_frames", "0", visible=True)
            self._set_row("proc_incompatible_frames", "0", visible=True)
            self._set_row("proc_error_frames", "0", visible=True)
            self.start_stacking_button.setEnabled(False)
            self.start_auto_process_button.setEnabled(False)
            if not is_running and not preserve_status_label:
                self.stacking_progress_bar.setVisible(False)
                self.stacking_progress_bar.setValue(0)
                self.stacking_status_label.setText(
                    "Belum ada gambar dibuka. Buka Single Image, Multiple Images, Video, atau SER."
                )
            self._update_result_section()
            if hasattr(self, "image_action_toolbar"):
                self._refresh_image_toolbar_state()
            return

        if mode == InputMode.SINGLE:
            self._set_row("proc_total_frames", "1 frame (Single Image)", visible=True)
            self._set_row("proc_compatible_frames", "1", visible=True)
            self._set_row("proc_incompatible_frames", "0", visible=True)
            self._set_row("proc_error_frames", "0", visible=True)
            self.start_stacking_button.setEnabled(False)

            can_auto = not is_running and flat_ready_to_click
            self.start_auto_process_button.setEnabled(can_auto)

            if not is_running and self._last_pipeline_result is None and not preserve_status_label:
                if flat_checked and not has_flat:
                    self.stacking_status_label.setText(
                        "Kalibrasi Flat aktif: Silakan pilih Master Flat terlebih dahulu (tombol Mulai dinonaktifkan)."
                    )
                else:
                    self.stacking_status_label.setText("Mode Single Image siap untuk pemrosesan otomatis (Stacking dilewati).")
            self._update_result_section()
            if hasattr(self, "image_action_toolbar"):
                self._refresh_image_toolbar_state()
            return

        # Mode MULTI, VIDEO, atau SER (stacking wajib)
        self._set_row("proc_total_frames", f"{rep.total_files} frame", visible=True)
        self._set_row("proc_compatible_frames", str(rep.compatible_count), visible=True)
        self._set_row("proc_incompatible_frames", str(rep.incompatible_count), visible=True)
        self._set_row("proc_error_frames", str(rep.error_count), visible=True)

        can_stack = (
            not is_running
            and self.sequence_manager.stacking_required
            and rep.compatible_count >= 2
            and flat_ready_to_click
        )
        self.start_stacking_button.setEnabled(can_stack)

        can_auto = (
            not is_running
            and rep.compatible_count >= 2
            and flat_ready_to_click
        )
        self.start_auto_process_button.setEnabled(can_auto)

        if not is_running and self._last_pipeline_result is None and self._last_stacking_result is None and not preserve_status_label:
            if rep.compatible_count < 2:
                self.stacking_status_label.setText(
                    f"Tidak dapat memproses: hanya {rep.compatible_count} frame kompatibel (minimal 2 frame diperlukan)."
                )
            elif flat_checked and not has_flat:
                self.stacking_status_label.setText(
                    "Kalibrasi Flat aktif: Silakan pilih berkas/sequence Master Flat terlebih dahulu."
                )
            elif rep.incompatible_count > 0 or rep.error_count > 0:
                self.stacking_status_label.setText(
                    f"Perhatian: Terdapat {rep.incompatible_count} frame inkompatibel dan "
                    f"{rep.error_count} frame error. Konfirmasi diperlukan sebelum pemrosesan."
                )
            else:
                self.stacking_status_label.setText(
                    f"Siap menjalankan pemrosesan otomatis ({rep.compatible_count} frame kompatibel)."
                )

        self._update_result_section()
        if hasattr(self, "image_action_toolbar"):
            self._refresh_image_toolbar_state()

    def _update_result_section(self) -> None:
        """Menampilkan atau menyembunyikan rincian hasil stacking dan pipeline terakhir."""
        pipe_res = self._last_pipeline_result
        stk_res = self._last_stacking_result

        if pipe_res is None and stk_res is None:
            self.stacking_result_container.setVisible(False)
            self.preview_controls_box.setVisible(False)
            self.histogram_container.setVisible(False)
            self.save_result_button.setEnabled(False)
            self.save_linear_fits_button.setEnabled(False)
            self.save_linear_tiff_button.setEnabled(False)
            self.save_enhanced_fits_button.setEnabled(False)
            self.export_display_png_button.setEnabled(False)
            for k, _ in _PROC_RESULT_ROWS:
                self._set_row(k, EMPTY_VALUE, visible=False)
            for k, _ in _PROC_PIPELINE_ROWS:
                self._set_row(k, EMPTY_VALUE, visible=False)
            return

        if pipe_res is not None:
            # Tampilkan hasil pipeline lengkap
            arr = pipe_res.linear_result
            finite_mask = np.isfinite(arr)
            min_v = float(np.min(arr[finite_mask])) if np.any(finite_mask) else 0.0
            max_v = float(np.max(arr[finite_mask])) if np.any(finite_mask) else 0.0
            range_str = f"[{min_v:.4g}, {max_v:.4g}]"

            frames_used_txt = (
                f"{pipe_res.stacking_result.stacked_frame_count} frame digabungkan"
                if pipe_res.stacking_result
                else "1 frame (Single Image — stacking dilewati)"
            )

            bg_info = (
                f"{pipe_res.background_result.effective_method.value} "
                f"({pipe_res.background_result.accepted_sample_count} sampel diterima, "
                f"{pipe_res.background_result.protected_pixel_count} px dilindungi)"
            )
            enh_info = (
                f"CLAHE aktif (clip={pipe_res.enhancement_result.effective_clip_limit:.4f}, "
                f"noise_amp={pipe_res.enhancement_result.noise_amplification_ratio:.2f}×)"
                if pipe_res.enhancement_result.config_used.enabled
                else "CLAHE nonaktif"
            )
            hist_info = (
                f"{pipe_res.histogram_result.effective_method.value} "
                f"(vmin={pipe_res.histogram_result.vmin:.3g}, vmax={pipe_res.histogram_result.vmax:.3g})"
            )

            self._set_row("res_status", f"Selesai (Pipeline Otomatis Profil {pipe_res.profile.value})", visible=True)
            self._set_row("res_frames_used", frames_used_txt, visible=True)
            self._set_row("res_algorithm", f"Pipeline Terpadu ({pipe_res.profile.value})", visible=True)
            self._set_row("res_dtype_range", f"float32 linear | shape {arr.shape} | rentang {range_str}", visible=True)
            self._set_row("res_rejected_samples", f"{pipe_res.background_result.rejected_sample_count} sampel background ditolak", visible=True)

            self._set_row("pipe_stage", "Tahap 6/6 (Histogram Transformation)", visible=True)
            self._set_row("pipe_profile", pipe_res.profile.value, visible=True)
            self._set_row("pipe_bg_summary", bg_info, visible=True)
            self._set_row("pipe_enh_summary", enh_info, visible=True)
            self._set_row("pipe_hist_summary", hist_info, visible=True)
            self._set_row("pipe_gradient_reduc", f"{pipe_res.background_result.residual_stats.gradient_reduction_ratio:.1%}", visible=True)
            over_txt = (
                f"Peringatan ({pipe_res.background_result.residual_stats.overcorrection_score:.2f})"
                if pipe_res.background_result.residual_stats.overcorrection_warning
                else f"Aman ({pipe_res.background_result.residual_stats.overcorrection_score:.2f})"
            )
            self._set_row("pipe_overcorrection", over_txt, visible=True)

            hist_lines = [
                f"Mode: {pipe_res.input_mode}",
                f"Profil: {pipe_res.profile.value}",
                f"Background: {pipe_res.background_result.effective_method.value}",
                f"Enhancement: {enh_info}",
                f"Display: {hist_info}",
            ]
            if pipe_res.flat_report and pipe_res.flat_report.applied:
                hist_lines.append(f"Flat-field: DITERAPKAN ({pipe_res.flat_report.source_description})")
            else:
                hist_lines.append("Flat-field: Tidak diterapkan")
            self._set_row("res_history", "\n".join(hist_lines), visible=True)

            # Tampilkan grafik histogram
            chart_qimg = pipe_res.histogram_result.histogram_chart_preview
            if chart_qimg is not None and not chart_qimg.isNull():
                self.histogram_chart_label.setPixmap(QPixmap.fromImage(chart_qimg))
                self.histogram_container.setVisible(True)

            self.preview_controls_box.setVisible(True)
            self.stacking_result_container.setVisible(True)
            is_running = self._is_stacking_running() or self._is_pipeline_running()
            self.save_linear_fits_button.setEnabled(not is_running)
            self.save_linear_tiff_button.setEnabled(not is_running)
            self.save_enhanced_fits_button.setEnabled(not is_running)
            self.export_display_png_button.setEnabled(not is_running)
            self.save_result_button.setEnabled(not is_running)
            return

        # Hanya Stacking Result (jika dijalankan lewat Mulai Stacking)
        res = stk_res
        assert res is not None
        arr = res.stacked_scientific_data
        finite_mask = np.isfinite(arr)
        min_v = float(np.min(arr[finite_mask])) if np.any(finite_mask) else 0.0
        max_v = float(np.max(arr[finite_mask])) if np.any(finite_mask) else 0.0
        range_str = f"[{min_v:.4g}, {max_v:.4g}]"

        excl_count = len(res.excluded_frames)
        prof_str = res.profile_config.profile.value
        algo_str = res.effective_algorithm.value
        dtype_str = str(arr.dtype)
        flat_applied = bool(res.flat_report and res.flat_report.applied)

        self._set_row("res_status", "Selesai (Data ilmiah linear float32 dipertahankan)", visible=True)
        self._set_row("res_frames_used", f"{res.stacked_frame_count} digunakan / {res.total_input_frames} total ({excl_count} dikecualikan)", visible=True)
        self._set_row("res_algorithm", f"{prof_str} ({algo_str})", visible=True)
        self._set_row("res_dtype_range", f"{dtype_str} | shape {arr.shape} | rentang {range_str}", visible=True)
        self._set_row("res_rejected_samples", f"{res.total_rejected_pixel_samples} sampel piksel outlier ditolak", visible=True)

        for k, _ in _PROC_PIPELINE_ROWS:
            self._set_row(k, EMPTY_VALUE, visible=False)

        hist_lines = [
            f"Mode input: {self.sequence_manager.input_mode.value}",
            f"Profil: {prof_str} ({algo_str})",
        ]
        if flat_applied and res.flat_report is not None:
            fr = res.flat_report
            hist_lines.extend(
                [
                    f"Flat-field: DITERAPKAN ({fr.source_description})",
                    f"Format & Dimensi Flat: {fr.flat_format} | {fr.width}×{fr.height} px ({fr.channels} kanal)",
                    f"Normalisasi Flat: {fr.normalization_method} (median awal={fr.flat_median_before_norm:.4g})",
                    f"Invalid Pixels Flat: {fr.invalid_pixel_count} piksel",
                ]
            )
        else:
            reason_not_applied = (
                res.flat_report.not_applied_reason
                if (res.flat_report is not None and res.flat_report.not_applied_reason)
                else "Opsi Apply Flat Calibration tidak diaktifkan oleh pengguna"
            )
            hist_lines.append(f"Flat-field: TIDAK DITERAPKAN ({reason_not_applied})")

        hist_lines.append("Registrasi/Alignment: TIDAK ADA (dilarang pada MVP 1.0)")
        if res.excluded_frames:
            excl_preview = ", ".join(f"#{ef.frame_index + 1} ({ef.file_name})" for ef in res.excluded_frames[:4])
            if len(res.excluded_frames) > 4:
                excl_preview += f", +{len(res.excluded_frames) - 4} lainnya"
            hist_lines.append(f"Frame dikecualikan: {excl_preview}")
        if res.warnings:
            hist_lines.append(f"Peringatan tercatat: {len(res.warnings)} item")

        self._set_row("res_history", "\n".join(hist_lines), visible=True)
        self.stacking_result_container.setVisible(True)
        self.preview_controls_box.setVisible(False)
        self.histogram_container.setVisible(False)
        is_running = self._is_stacking_running() or self._is_pipeline_running()
        self.save_result_button.setEnabled(not is_running)
        self.save_linear_fits_button.setEnabled(not is_running)
        self.save_linear_tiff_button.setEnabled(not is_running)
        self.save_enhanced_fits_button.setEnabled(False)
        self.export_display_png_button.setEnabled(not is_running)

    def _confirm_exclude_invalid_frames(self, validation: PreStackValidationReport) -> bool:
        """Meminta konfirmasi pengguna bila sequence memiliki frame inkompatibel/error.

        Menampilkan daftar jelas frame mana yang akan diproses dan frame mana yang
        dikecualikan beserta alasannya, sehingga tidak ada frame yang dibuang diam-diam.
        """
        used_list = ", ".join(f"#{idx + 1}" for idx in validation.included_frame_indices[:12])
        if len(validation.included_frame_indices) > 12:
            used_list += f", ... (total {len(validation.included_frame_indices)} frame)"

        excl_lines = [
            f"• Frame #{ef.frame_index + 1} '{ef.file_name}': {ef.reason}"
            for ef in validation.excluded_frames[:8]
        ]
        if len(validation.excluded_frames) > 8:
            excl_lines.append(
                f"... dan {len(validation.excluded_frames) - 8} frame bermasalah lainnya."
            )
        excl_text = "\n".join(excl_lines)

        msg = (
            "Ditemukan frame yang TIDAK KOMPATIBEL atau ERROR di dalam sequence.\n"
            "HILALONE tidak pernah membuang frame secara diam-diam.\n\n"
            f"Frame yang AKAN DIPROSES ({len(validation.included_frame_indices)} frame):\n"
            f"{used_list}\n\n"
            f"Frame yang AKAN DIKECUALIKAN ({len(validation.excluded_frames)} frame):\n"
            f"{excl_text}\n\n"
            "Apakah Anda ingin melanjutkan stacking hanya dengan frame yang kompatibel "
            "(seluruh frame yang dikecualikan akan dicatat dalam laporan hasil)?"
        )
        ans = QMessageBox.question(
            self,
            "Konfirmasi Pengecualian Frame Bermasalah",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return ans == QMessageBox.StandardButton.Yes

    def _confirm_shift_risk(self, _message: str) -> bool:
        """Pemeriksaan stabilitas posisi dinonaktifkan (MVP 1.0); selalu lanjutkan tanpa popup dialog."""
        return True

    def _on_start_stacking_clicked(self) -> None:
        self.start_stacking(wait_for_completion=False)

    def start_stacking(self, *, wait_for_completion: bool = False) -> bool:
        """Menjalankan alur validasi pra-stacking lalu memulai StackingWorker secara langsung."""
        if self._is_stacking_running():
            return False

        if self.sequence_manager.frame_count == 0 or not self.sequence_manager.stacking_required:
            self._show_error(
                "Stacking hanya dapat dijalankan pada mode Multiple Images, Video, atau SER."
            )
            return False

        if self.flat_checkbox.isChecked():
            if self._loaded_master_flat is None:
                self._show_error(
                    "Kalibrasi Flat diaktifkan, tetapi berkas/sequence Master Flat belum dipilih.\n"
                    "Silakan pilih Master Flat terlebih dahulu atau nonaktifkan opsi Apply Flat Calibration."
                )
                return False

        try:
            validation = validate_sequence_for_stacking(
                self.sequence_manager.input_mode,
                self.sequence_manager.entries,
                allow_exclude_incompatible_and_error=True,
            )
        except StackingError as err:
            self._show_error(str(err))
            return False

        if len(validation.included_frame_indices) < 2:
            self._show_error(
                f"Jumlah frame yang kompatibel hanya {len(validation.included_frame_indices)} frame "
                "(minimal 2 frame diperlukan untuk menjalankan stacking)."
            )
            return False

        allow_exclude_invalid = False
        if len(validation.excluded_frames) > 0:
            if not self._confirm_exclude_invalid_frames(validation):
                self.stacking_status_label.setText(
                    "Stacking dibatalkan oleh pengguna pada tahap konfirmasi kompatibilitas frame."
                )
                return False
            allow_exclude_invalid = True

        self._last_allow_exclude_invalid = allow_exclude_invalid
        return self._launch_stacking_worker(
            allow_exclude_incompatible_and_error=allow_exclude_invalid,
            confirm_proceed_with_shift_risk=True,
            wait_for_completion=wait_for_completion,
        )

    def _launch_stacking_worker(
        self,
        *,
        allow_exclude_incompatible_and_error: bool,
        confirm_proceed_with_shift_risk: bool = True,
        wait_for_completion: bool = False,
    ) -> bool:
        profile = self.selected_stacking_profile()
        master_flat = self._loaded_master_flat if self.flat_checkbox.isChecked() else None

        worker = StackingWorker(
            self.sequence_manager,
            profile,
            master_flat=master_flat,
            allow_exclude_incompatible_and_error=allow_exclude_incompatible_and_error,
            check_position_stability=False,
            confirm_proceed_with_shift_risk=True,
            parent=self,
        )
        self._cancel_requested_by_ui = False
        self._stacking_worker = worker
        worker.progress_updated.connect(self._on_stacking_progress)
        worker.stacking_finished.connect(self._on_stacking_finished)
        worker.stacking_cancelled.connect(self._on_stacking_cancelled)
        worker.confirmation_required.connect(self._on_stacking_confirmation_required)
        worker.stacking_failed.connect(self._on_stacking_failed)
        worker.finished.connect(lambda w=worker: self._on_worker_thread_finished(w))

        self._set_input_controls_enabled(False)
        self.state_manager.transition_to(ProcessingState.PROCESSING)
        self.start_stacking_button.setEnabled(False)
        self.cancel_stacking_button.setEnabled(True)
        self.save_result_button.setEnabled(False)
        self.stacking_progress_bar.setValue(0)
        self.stacking_progress_bar.setVisible(True)
        self.stacking_status_label.setText("Memulai proses stacking...")
        self.statusBar().showMessage(f"Menjalankan stacking ({profile.value})...")

        worker.start()

        if wait_for_completion:
            from PySide6.QtCore import QCoreApplication

            while self._stacking_worker is not None:
                self._stacking_worker.wait(10)
                QCoreApplication.processEvents()
            QCoreApplication.processEvents()
            return self._last_stacking_result is not None

        return True

    def cancel_stacking(self) -> None:
        """Meminta pembatalan proses stacking yang sedang berjalan di worker thread."""
        self._cancel_requested_by_ui = True
        self.state_manager.transition_to(ProcessingState.CANCELLING)
        self.cancel_stacking_button.setEnabled(False)
        self.stacking_status_label.setText("Membatalkan proses stacking secara aman...")
        if self._stacking_worker is not None:
            self._stacking_worker.request_cancel()

    def _on_stacking_progress(self, current_step: int, total_steps: int, message: str) -> None:
        if self._cancel_requested_by_ui:
            return
        total = max(1, int(total_steps))
        pct = int(round(100.0 * max(0, min(current_step, total)) / total))
        self.stacking_progress_bar.setVisible(True)
        self.stacking_progress_bar.setValue(pct)
        self.stacking_status_label.setText(message)
        self.statusBar().showMessage(f"Stacking [{pct}%]: {message}")

    def _on_stacking_finished(self, result_obj: object) -> None:
        try:
            if self._cancel_requested_by_ui:
                self._on_stacking_cancelled("Proses stacking dibatalkan oleh pengguna.")
                return
            if not isinstance(result_obj, StackingResult):
                self.state_manager.transition_to(ProcessingState.FAILED)
                return
            self._last_stacking_result = result_obj
            prof_str = result_obj.profile_config.profile.value
            algo_str = result_obj.effective_algorithm.value
            dtype_str = str(result_obj.stacked_scientific_data.dtype)
            self.stacking_progress_bar.setVisible(True)
            self.stacking_progress_bar.setValue(100)
            self.stacking_status_label.setText(
                f"Stacking selesai: {result_obj.stacked_frame_count} frame digabungkan dengan "
                f"{prof_str} ({algo_str})."
            )
            self.viewer.set_image(result_obj.preview, result_obj.stacked_scientific_data)
            if hasattr(self, "image_action_toolbar"):
                self._refresh_image_toolbar_state()
            if hasattr(self, "status_view_info"):
                self.status_view_info.setText(f"Mode: Stacking ({prof_str})")
            self.state_manager.transition_to(ProcessingState.COMPLETED)
            self.statusBar().showMessage(
                f"Hasil Stacking ({prof_str}): {result_obj.stacked_frame_count} frame  |  "
                f"dtype: {dtype_str}"
            )
        except Exception as exc:
            self.state_manager.transition_to(ProcessingState.FAILED)
            self.stacking_status_label.setText(f"Gagal menampilkan hasil: {exc}")
            self._show_error(f"Gagal menampilkan hasil stacking: {exc}")
        finally:
            self._set_input_controls_enabled(True)
            self._refresh_processing_controls()

    def _on_stacking_cancelled(self, message: str) -> None:
        try:
            self._last_stacking_result = None
            self.state_manager.transition_to(ProcessingState.CANCELLED)
            self.stacking_progress_bar.setValue(0)
            self.stacking_progress_bar.setVisible(False)
            self.stacking_status_label.setText(f"Dibatalkan: {message}")
            self.statusBar().showMessage("Proses stacking dibatalkan oleh pengguna.")
        finally:
            self._set_input_controls_enabled(True)
            self._refresh_processing_controls(preserve_status_label=True)

    def _on_stacking_confirmation_required(self, message: str) -> None:
        self._set_input_controls_enabled(True)
        self.stacking_progress_bar.setValue(0)
        self.stacking_progress_bar.setVisible(False)
        if self._confirm_shift_risk(message):
            self._launch_stacking_worker(
                allow_exclude_incompatible_and_error=self._last_allow_exclude_invalid,
                confirm_proceed_with_shift_risk=True,
                wait_for_completion=False,
            )
        else:
            self.stacking_status_label.setText(
                "Stacking dibatalkan karena peringatan pergeseran posisi frame."
            )
            self._refresh_processing_controls(preserve_status_label=True)
            self.statusBar().showMessage("Stacking dibatalkan (pergeseran posisi > ambang).")

    def _on_stacking_failed(self, message: str) -> None:
        try:
            self._last_stacking_result = None
            self.state_manager.transition_to(ProcessingState.FAILED)
            self.stacking_progress_bar.setValue(0)
            self.stacking_progress_bar.setVisible(False)
            self.stacking_status_label.setText(f"Gagal: {message}")
            self.statusBar().showMessage("Proses stacking gagal.")
            self._show_error(message)
        finally:
            self._set_input_controls_enabled(True)
            self._refresh_processing_controls(preserve_status_label=True)

    def _on_worker_thread_finished(self, worker: StackingWorker) -> None:
        try:
            if self._stacking_worker is worker:
                self._stacking_worker = None
            worker.deleteLater()
            self.cancel_stacking_button.setEnabled(False)
            if self.state_manager.is_busy:
                self.state_manager.transition_to(
                    ProcessingState.COMPLETED if self._last_stacking_result is not None else ProcessingState.IDLE
                )
        finally:
            self._set_input_controls_enabled(True)
            self._refresh_processing_controls(preserve_status_label=True)

    # ------------------------------------------------- SAVE STACKING RESULT
    def save_stacking_result_dialog(self) -> Path | None:
        """Membuka dialog penyimpanan hasil stacking (.fits, .tif, atau .png)."""
        if self._last_stacking_result is None:
            self._show_error("Belum ada hasil stacking untuk disimpan.")
            return None

        prof_lower = self._last_stacking_result.profile_config.profile.value.lower()
        default_name = f"stacked_{prof_lower}.fits"
        default_path = str(Path(self._last_dir) / default_name)
        file_filter = (
            "FITS Linear Float32 (*.fits *.fit);;"
            "TIFF Linear Float32 (*.tif *.tiff);;"
            "PNG Display Preview (*.png)"
        )
        out_path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Simpan Hasil Stacking",
            default_path,
            file_filter,
        )
        if not out_path_str:
            return None
        return self.save_stacking_result_to_path(out_path_str)

    def save_stacking_result_to_path(self, output_path: str | Path) -> Path | None:
        """Menyimpan hasil stacking ke ``output_path`` tanpa menimpa berkas sumber."""
        if self._last_stacking_result is None:
            self._show_error("Belum ada hasil stacking untuk disimpan.")
            return None

        source_paths = [e.source_path for e in self.sequence_manager.entries]
        if self._master_flat_path is not None:
            source_paths.append(self._master_flat_path)
        if self._loaded_master_flat is not None:
            source_paths.extend(self._loaded_master_flat.source_paths)

        try:
            saved_path, _json_path = save_stacking_result(
                self._last_stacking_result,
                output_path,
                source_paths=source_paths,
                write_json_report=True,
            )
        except OutputWriteError as err:
            self._show_error(str(err))
            return None

        self._last_dir = str(saved_path.parent)
        self.stacking_status_label.setText(f"Hasil stacking disimpan ke: {saved_path.name}")
        self.statusBar().showMessage(f"Hasil stacking tersimpan: {saved_path}")
        return saved_path

    # ------------------------------------------------- AUTOMATED PROCESSING PIPELINE
    def _on_start_auto_process_clicked(self) -> None:
        self.start_automated_pipeline(wait_for_completion=False)

    def start_automated_pipeline(self, *, wait_for_completion: bool = False) -> bool:
        """Menjalankan full automated pipeline untuk Single Image atau Sequence."""
        if self._is_stacking_running() or self._is_pipeline_running():
            return False

        mode = self.sequence_manager.input_mode
        total = self.sequence_manager.frame_count

        if total == 0:
            self._show_error("Tidak ada gambar atau sequence yang dibuka untuk diproses.")
            return False

        if self.flat_checkbox.isChecked():
            if self._loaded_master_flat is None:
                self._show_error(
                    "Kalibrasi Flat diaktifkan, tetapi Master Flat belum dipilih.\n"
                    "Silakan pilih berkas Master Flat terlebih dahulu atau nonaktifkan opsi Apply Flat Calibration."
                )
                return False

        allow_exclude_invalid = False
        if mode in (InputMode.MULTI, InputMode.VIDEO, InputMode.SER):
            rep = self.sequence_manager.compatibility_report
            if rep.compatible_count < 2:
                self._show_error(
                    f"Jumlah frame kompatibel hanya {rep.compatible_count} frame (minimal 2 frame diperlukan)."
                )
                return False
            if rep.incompatible_count > 0 or rep.error_count > 0:
                val = validate_sequence_for_stacking(
                    mode,
                    self.sequence_manager.entries,
                    allow_exclude_incompatible_and_error=True,
                )
                if not self._confirm_exclude_invalid_frames(val):
                    self.stacking_status_label.setText("Pemrosesan dibatalkan pada konfirmasi frame bermasalah.")
                    return False
                allow_exclude_invalid = True

        base_prof = self.selected_processing_profile()
        bg_m = self.adv_bg_method_combo.currentData()
        clahe_on = self.adv_clahe_enable_checkbox.isChecked()
        clahe_c = float(self.adv_clahe_clip_combo.currentData() or 0.012)
        str_m = self.adv_stretch_combo.currentData()
        prot_rois = (self._current_protected_roi,) if self._current_protected_roi is not None else ()

        conf = customize_profile_config(
            base_prof,
            background_method=bg_m,
            protected_regions=prot_rois,
            clahe_enabled=clahe_on,
            clahe_clip_limit=clahe_c,
            stretch_method=str_m,
        )

        master_flat = self._loaded_master_flat if self.flat_checkbox.isChecked() else None

        worker = PipelineWorker(
            self.sequence_manager,
            config=conf,
            master_flat=master_flat,
            allow_exclude_incompatible_and_error=allow_exclude_invalid,
            confirm_proceed_with_shift_risk=True,
            parent=self,
        )
        self._cancel_requested_by_ui = False
        self._pipeline_worker = worker

        worker.stage_changed.connect(self._on_pipeline_stage_changed)
        worker.progress_updated.connect(self._on_pipeline_progress)
        worker.pipeline_finished.connect(self._on_pipeline_finished)
        worker.pipeline_cancelled.connect(self._on_pipeline_cancelled)
        worker.pipeline_failed.connect(self._on_pipeline_failed)
        worker.confirmation_required.connect(self._on_pipeline_confirmation_required)
        worker.finished.connect(lambda w=worker: self._on_pipeline_worker_finished(w))

        self.state_manager.transition_to(ProcessingState.PROCESSING)
        self._set_input_controls_enabled(False)
        self.start_auto_process_button.setEnabled(False)
        self.start_stacking_button.setEnabled(False)
        self.cancel_pipeline_button.setEnabled(True)
        self.stacking_progress_bar.setValue(0)
        self.stacking_progress_bar.setVisible(True)
        self.stacking_status_label.setText("Memulai pemrosesan otomatis...")
        self.statusBar().showMessage(f"Menjalankan pemrosesan otomatis ({base_prof.value})...")

        worker.start()

        if wait_for_completion:
            from PySide6.QtCore import QCoreApplication
            while self._pipeline_worker is not None:
                self._pipeline_worker.wait(10)
                QCoreApplication.processEvents()
            QCoreApplication.processEvents()
            return self._last_pipeline_result is not None

        return True

    def cancel_automated_pipeline(self) -> None:
        self._cancel_requested_by_ui = True
        self.state_manager.transition_to(ProcessingState.CANCELLING)
        self.cancel_pipeline_button.setEnabled(False)
        self.stacking_status_label.setText("Membatalkan pemrosesan otomatis secara aman...")
        if self._pipeline_worker is not None:
            self._pipeline_worker.request_cancel()

    def _on_pipeline_stage_changed(self, stage_name: str, step: int, total_steps: int, msg: str) -> None:
        if self._cancel_requested_by_ui:
            return
        self.stacking_status_label.setText(f"[{stage_name}]: {msg}")
        self.statusBar().showMessage(f"Pipeline [{stage_name}]: {msg}")

    def _on_pipeline_progress(self, pct: int, msg: str) -> None:
        if self._cancel_requested_by_ui:
            return
        self.stacking_progress_bar.setVisible(True)
        self.stacking_progress_bar.setValue(pct)
        self.stacking_status_label.setText(msg)

    def _on_pipeline_finished(self, result_obj: object) -> None:
        try:
            if self._cancel_requested_by_ui:
                self._on_pipeline_cancelled("Pemrosesan otomatis dibatalkan oleh pengguna.")
                return
            if not isinstance(result_obj, PipelineResult):
                self.state_manager.transition_to(ProcessingState.FAILED)
                self._show_error("Hasil pemrosesan pipeline tidak valid.")
                return

            self._last_pipeline_result = result_obj
            if result_obj.stacking_result is not None:
                self._last_stacking_result = result_obj.stacking_result

            self.stacking_progress_bar.setVisible(True)
            self.stacking_progress_bar.setValue(100)
            self.stacking_status_label.setText(
                f"Pemrosesan otomatis selesai (Profil: {result_obj.profile.value})."
            )
            self._is_showing_before = False
            self.toggle_before_after_button.setChecked(False)
            self.preview_mode_combo.setCurrentIndex(0)
            self._preview_mode = PreviewMode.FINAL_DISPLAY
            self._update_displayed_preview()

            self.state_manager.transition_to(ProcessingState.COMPLETED)
            self.statusBar().showMessage(f"Pemrosesan otomatis selesai ({result_obj.profile.value}).")
        except Exception as exc:
            self._last_pipeline_result = None
            self.state_manager.transition_to(ProcessingState.FAILED)
            self.stacking_status_label.setText(f"Gagal menampilkan hasil: {exc}")
            self._show_error(f"Gagal menampilkan hasil pemrosesan: {exc}")
        finally:
            self._set_input_controls_enabled(True)
            try:
                self._refresh_processing_controls()
            except Exception:
                pass

    def _on_pipeline_cancelled(self, message: str) -> None:
        try:
            self.state_manager.transition_to(ProcessingState.CANCELLED)
            self.stacking_progress_bar.setValue(0)
            self.stacking_progress_bar.setVisible(False)
            self.stacking_status_label.setText(f"Dibatalkan: {message}")
            self.statusBar().showMessage("Pemrosesan otomatis dibatalkan.")
        finally:
            self._set_input_controls_enabled(True)
            self._refresh_processing_controls(preserve_status_label=True)

    def _on_pipeline_failed(self, message: str) -> None:
        try:
            self.state_manager.transition_to(ProcessingState.FAILED)
            self.stacking_progress_bar.setValue(0)
            self.stacking_progress_bar.setVisible(False)
            self.stacking_status_label.setText(f"Gagal: {message}")
            self.statusBar().showMessage("Pemrosesan otomatis gagal.")
            self._show_error(message)
        finally:
            self._set_input_controls_enabled(True)
            self._refresh_processing_controls(preserve_status_label=True)

    def _on_pipeline_confirmation_required(self, message: str) -> None:
        self._set_input_controls_enabled(True)
        self.stacking_progress_bar.setValue(0)
        self.stacking_progress_bar.setVisible(False)
        if self._confirm_shift_risk(message):
            self.start_automated_pipeline(wait_for_completion=False)
        else:
            self.stacking_status_label.setText("Pemrosesan dibatalkan karena peringatan pergeseran posisi frame.")
            self._refresh_processing_controls(preserve_status_label=True)

    def _on_pipeline_worker_finished(self, worker: PipelineWorker) -> None:
        try:
            if self._pipeline_worker is worker:
                self._pipeline_worker = None
            worker.deleteLater()
            self.cancel_pipeline_button.setEnabled(False)
            if self.state_manager.is_busy:
                self.state_manager.transition_to(
                    ProcessingState.COMPLETED if self._last_pipeline_result is not None else ProcessingState.IDLE
                )
        finally:
            self._set_input_controls_enabled(True)
            self._refresh_processing_controls(preserve_status_label=True)

    # ------------------------------------------------- SAVE PIPELINE RESULT
    def save_pipeline_result_dialog(self, target_type: str = "LINEAR_FITS") -> Path | None:
        """Membuka dialog penyimpanan produk hasil pemrosesan otomatis."""
        if self._last_pipeline_result is None and self._last_stacking_result is None:
            if not self.viewer.has_image():
                self._show_error("Belum ada hasil pemrosesan untuk disimpan.")
                return None
            if target_type == "DISPLAY_PNG":
                stem = Path(self._current_file_name or "image").stem
                def_name = f"display_{stem}.png"
                out_path_str, _ = QFileDialog.getSaveFileName(
                    self,
                    "Ekspor Pratinjau Tampilan (PNG)",
                    str(Path(self._last_dir) / def_name),
                    "PNG Display Preview (*.png)",
                )
                if not out_path_str:
                    return None
                pix = self.viewer.render_view_pixmap()
                pix.save(out_path_str, "PNG")
                self._last_dir = str(Path(out_path_str).parent)
                self.statusBar().showMessage(f"Pratinjau tampilan tersimpan: {Path(out_path_str).name}")
                return Path(out_path_str)
            else:
                self._show_error(
                    "Hasil pemrosesan otomatis atau stacking belum dijalankan.\n"
                    "Jalankan Mulai Stacking atau Mulai Pemrosesan Otomatis terlebih dahulu "
                    "untuk menghasilkan berkas Master Ilmiah (FITS/TIFF)."
                )
                return None

        prof = self.selected_processing_profile().value.lower()
        if target_type == "LINEAR_FITS":
            def_name = f"hilal_linear_{prof}.fits"
            filt = "FITS Linear Float32 (*.fits *.fit)"
            save_kind = "LINEAR"
        elif target_type == "LINEAR_TIFF":
            def_name = f"hilal_linear_{prof}.tif"
            filt = "TIFF Linear Float32 (*.tif *.tiff)"
            save_kind = "LINEAR"
        elif target_type == "ENHANCED_FITS":
            def_name = f"hilal_enhanced_{prof}.fits"
            filt = "FITS Derived Enhanced Float32 (*.fits *.fit)"
            save_kind = "ENHANCED"
        elif target_type == "DISPLAY_PNG":
            def_name = f"hilal_display_{prof}.png"
            filt = "PNG Display Preview (*.png)"
            save_kind = "DISPLAY"
        else:
            def_name = f"hilal_linear_{prof}.fits"
            filt = "FITS (*.fits);;TIFF (*.tif);;PNG (*.png)"
            save_kind = "LINEAR"

        out_path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Simpan Hasil Pemrosesan Otomatis",
            str(Path(self._last_dir) / def_name),
            filt,
        )
        if not out_path_str:
            return None
        return self.save_pipeline_result_to_path(out_path_str, save_target=save_kind)

    def save_pipeline_result_to_path(
        self,
        output_path: str | Path,
        save_target: str = "LINEAR",
    ) -> Path | None:
        """Menyimpan hasil pemrosesan otomatis ke disk dengan jaminan anti-overwrite."""
        if self._last_pipeline_result is None:
            if self._last_stacking_result is not None:
                return self.save_stacking_result_to_path(output_path)
            self._show_error("Belum ada hasil pemrosesan untuk disimpan.")
            return None

        source_paths: list[Path] = [e.source_path for e in self.sequence_manager.entries]
        if self._master_flat_path is not None:
            source_paths.append(self._master_flat_path)
        if self._loaded_master_flat is not None:
            source_paths.extend(self._loaded_master_flat.source_paths)

        try:
            saved_path, _json_path = save_pipeline_result(
                self._last_pipeline_result,
                output_path,
                save_target=save_target,
                source_paths=source_paths,
                write_json_report=True,
            )
        except OutputWriteError as err:
            self._show_error(str(err))
            return None

        self._last_dir = str(saved_path.parent)
        self.stacking_status_label.setText(f"Hasil disimpan ke: {saved_path.name}")
        self.statusBar().showMessage(f"Hasil tersimpan: {saved_path}")
        return saved_path
