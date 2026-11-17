"""Jendela utama HILALONE v0.1: Single Image, Multiple Images, Sequence Navigator, & Image Viewer.

Berkas ini hanya mengurus TAMPILAN. Pembacaan, pengurutan, dan validasi berkas
dilakukan oleh ``hilalone.input_manager`` (sesuai aturan: GUI tanpa logika
pemrosesan).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import logging
from pathlib import Path
import math
import os
import time
from typing import Any, Callable, Iterable

from PySide6.QtCore import QEventLoop, QSettings, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QPixmap, QTransform
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

import numpy as np

from hilalone import APP_NAME, APP_SUBTITLE, __version__
from hilalone.gui.about_dialog import AboutDialog
from hilalone.gui.accordion import AccordionGroup, AccordionHeader, AccordionSection
from hilalone.gui.console_panel import ConsoleLogPanel, LogEntry, LogLevel, LogManager
from hilalone.gui.curves_window import CurvesWindow, apply_curve_lut_to_array, apply_curve_lut_to_pixmap
from hilalone.gui.histogram_window import HistogramWindow
from hilalone.gui.icons import create_themed_vector_icon, create_vector_icon
from hilalone.gui.image_viewer import ImageViewer
from hilalone.gui.info_dialog import ImageInformationDialog
from hilalone.gui.pipeline_worker import PipelineWorker
from hilalone.gui.resources import get_app_icon, get_header_logo_pixmap, get_user_config_path
from hilalone.gui.stacking_worker import StackingWorker
from hilalone.gui.state_manager import ProcessingState, ProcessingStateManager
from hilalone.gui.styles import ThemeMode, get_theme_stylesheet
from hilalone.gui.top_panels import FrameListPanel, ImageInfoPanel, OpenImagePanel
from hilalone.gui.update_dialog import UpdateDialog
from hilalone.gui.update_notification_dialog import UpdateNotificationDialog
from hilalone.updates.github_updater import is_frozen_app
from hilalone.updates.models import GITHUB_NEW_ISSUE_URL, UpdateCheckResult
from hilalone.updates.update_preferences import (
    AUTO_UPDATE_STARTUP_DELAY_MS,
    REMINDER_DELAY_INTERVAL,
    UpdatePreferences,
    load_update_preferences,
    record_check_timestamp,
    record_notification_shown,
    save_update_preferences,
    should_run_automatic_check,
    should_show_update_notification,
    snooze_update_reminder,
    utc_now,
)
from hilalone.updates.update_worker import UpdateWorker, UpdateWorkerMode
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
        self.resize(1366, 768)
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
        self._current_info: ImageInfo | None = None
        self.state_manager = ProcessingStateManager(parent=self)
        self.state_manager.state_changed.connect(self._on_processing_state_changed)

        # Logging, Theme, Metadata, & Windows baru
        self.log_manager = LogManager(self)
        self._is_night_vision: bool = False
        self._custom_metadata: dict[str, tuple[str, str]] = {}
        self._selected_frame_indices: list[int] = []
        self.histogram_window: HistogramWindow | None = None
        self.curves_window: CurvesWindow | None = None
        self.info_dialog: ImageInformationDialog | None = None
        self.about_dialog: AboutDialog | None = None
        self.update_dialog: UpdateDialog | None = None
        self.update_notification_dialog: UpdateNotificationDialog | None = None
        self._update_worker: UpdateWorker | None = None
        self._update_prefs: UpdatePreferences = UpdatePreferences()
        self._update_config_path: Path | None = None
        self._is_frozen_checker: Callable[[], bool] = is_frozen_app
        self._now_provider: Callable[[], datetime] = utc_now
        self._auto_check_func: Any = None
        self._update_check_is_automatic: bool = False
        self._startup_timer_scheduled: bool = False
        self._startup_update_delay_ms: int = AUTO_UPDATE_STARTUP_DELAY_MS
        self._is_closing: bool = False
        self._was_closed: bool = False
        self._startup_update_timer = QTimer(self)
        self._startup_update_timer.setSingleShot(True)
        self._startup_update_timer.setInterval(self._startup_update_delay_ms)
        self._startup_update_timer.timeout.connect(self._on_startup_update_timer_timeout)
        self._reminder_update_timer = QTimer(self)
        self._reminder_update_timer.setSingleShot(True)
        self._reminder_update_timer.timeout.connect(self._on_reminder_update_timer_timeout)
        self._curves_backup_qimage: Any = None
        self._curves_backup_scientific_data: np.ndarray | None = None
        self._active_original_qimage: Any = None
        self._original_unprocessed_qimage: Any = None
        self._on_the_fly_previews: dict[PreviewMode, Any] = {}

        self._build_ui()
        self.viewer.roi_selected.connect(self._on_roi_selected_from_viewer)
        self.viewer.zoom_changed.connect(self._on_viewer_zoom_changed)
        self.viewer.pixel_hovered.connect(self._on_viewer_pixel_hovered)
        self.viewer.image_changed.connect(self._refresh_image_toolbar_state)
        self._apply_theme_to_widgets(self._is_night_vision)
        self._load_user_preferences()
        self.close_image()

    def _preferences_enabled(self) -> bool:
        """Menghindari pembacaan/penulisan config desktop global saat pengujian pytest berjalan."""
        return "PYTEST_CURRENT_TEST" not in os.environ

    def _load_user_preferences(self, config_path: Path | None = None) -> None:
        """Memuat preferensi pengguna (tema, direktori, & update) dari folder lokal Windows."""
        effective_cfg = config_path if config_path is not None else self._update_config_path
        if effective_cfg is None and not self._preferences_enabled():
            return
        try:
            self._update_prefs = load_update_preferences(effective_cfg)
            if hasattr(self, "act_auto_update_check"):
                self.act_auto_update_check.blockSignals(True)
                self.act_auto_update_check.setChecked(self._update_prefs.auto_update_check_enabled)
                self.act_auto_update_check.blockSignals(False)
            cfg = effective_cfg if effective_cfg is not None else get_user_config_path()
            if not cfg.exists():
                return
            settings = QSettings(str(cfg), QSettings.Format.IniFormat)
            saved_dir = str(settings.value("ui/last_dir", "") or "").strip()
            if saved_dir and Path(saved_dir).is_dir():
                self._last_dir = saved_dir
            night_raw = settings.value("ui/night_vision", False)
            night_active = (
                night_raw
                if isinstance(night_raw, bool)
                else str(night_raw).strip().lower() in {"1", "true", "yes", "on"}
            )
            if night_active != self._is_night_vision:
                self.toggle_night_vision_theme(night_active, persist=False)
        except Exception:
            pass

    def _save_user_preferences(self, config_path: Path | None = None) -> None:
        """Menyimpan preferensi tema, direktori kerja, & update ke folder konfigurasi."""
        effective_cfg = config_path if config_path is not None else self._update_config_path
        if effective_cfg is None and not self._preferences_enabled():
            return
        try:
            cfg = effective_cfg if effective_cfg is not None else get_user_config_path()
            cfg.parent.mkdir(parents=True, exist_ok=True)
            settings = QSettings(str(cfg), QSettings.Format.IniFormat)
            settings.setValue("ui/night_vision", bool(self._is_night_vision))
            settings.setValue("ui/last_dir", str(self._last_dir))
            settings.sync()
            save_update_preferences(self._update_prefs, cfg)
        except Exception:
            pass

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(16, 10, 16, 8)
        root.setSpacing(8)

        # 1. Header (Logo, Judul, Tombol Cepat)
        root.addLayout(self._build_header())
        line = QFrame()
        line.setObjectName("headerLine")
        line.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(line)

        # 2. Tiga Panel Utama Sejajar (Panel A: Open Image, Panel B: Frame List, Panel C: Image Information)
        self.top_panels_widget = QWidget()
        self.top_panels_widget.setObjectName("topPanelsContainer")
        top_panels_row = QHBoxLayout(self.top_panels_widget)
        top_panels_row.setContentsMargins(0, 0, 0, 0)
        top_panels_row.setSpacing(10)

        self.panel_a = OpenImagePanel(self)
        self.panel_b = FrameListPanel(self)
        self.panel_c = ImageInfoPanel(self)

        top_panels_row.addWidget(self.panel_a, 2)
        top_panels_row.addWidget(self.panel_b, 5)
        top_panels_row.addWidget(self.panel_c, 3)
        root.addWidget(self.top_panels_widget)

        # Sembunyikan Panel A, B, C secara default agar area kerja utama bersih dan lapang
        self.top_panels_widget.setVisible(False)
        self.panel_a.setVisible(False)
        self.panel_b.setVisible(False)
        self.panel_c.setVisible(False)

        # Sambungkan sinyal Panel A (impor) & referensi tombol kompatibilitas
        self.open_button = self.panel_a.btn_open_single
        self.open_multi_button = self.panel_a.btn_open_multi
        self.open_folder_button = self.panel_a.btn_open_folder
        self.open_video_button = self.panel_a.btn_open_video
        self.open_ser_button = self.panel_a.btn_open_ser
        self.close_button = self.panel_a.btn_close

        self.open_button.clicked.connect(self.open_image_dialog)
        self.open_multi_button.clicked.connect(self.open_multiple_images_dialog)
        self.open_folder_button.clicked.connect(self.open_folder_sequence_dialog)
        self.open_video_button.clicked.connect(self.open_video_dialog)
        self.open_ser_button.clicked.connect(self.open_ser_dialog)
        self.close_button.clicked.connect(self.close_image)

        # Sambungkan sinyal Panel B & C
        self.panel_b.frame_activated.connect(self._on_frame_list_activated)
        self.panel_b.selection_changed.connect(self._on_frame_selection_changed)
        self.panel_c.open_dialog_requested.connect(self.open_image_information_dialog)

        # Komponen navigasi bar kompatibilitas (hidden / background sync)
        self.nav_bar = self._build_sequence_nav_bar()
        self.nav_bar.setVisible(False)

        # 3. Main Workspace Body (Viewer + Minimal Processing Sidebar)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)

        viewer_column = QWidget()
        v_col_layout = QVBoxLayout(viewer_column)
        v_col_layout.setContentsMargins(0, 0, 0, 0)
        v_col_layout.setSpacing(6)

        self.viewer = ImageViewer()
        self.image_action_toolbar = self._build_image_action_toolbar()
        v_col_layout.addWidget(self.viewer, 1)
        v_col_layout.addWidget(self.image_action_toolbar, 0)

        main_splitter.addWidget(viewer_column)
        self.info_panel_widget = self._build_info_panel()
        main_splitter.addWidget(self.info_panel_widget)
        main_splitter.setStretchFactor(0, 68)
        main_splitter.setStretchFactor(1, 32)
        main_splitter.setSizes([910, 430])

        root.addWidget(main_splitter, 1)

        # 4. Console / Processing Log Panel di bagian bawah (tertutup secara default agar ruang viewer lega)
        self.console_panel = ConsoleLogPanel(self.log_manager, parent=self)
        self.console_panel.setVisible(False)
        self.console_panel.toggle_hide_btn.clicked.connect(lambda: self.toggle_console_panel(False))
        root.addWidget(self.console_panel, 0)

        self._setup_status_bar()
        self._build_menu_bar()

    def _build_menu_bar(self) -> None:
        """Membangun Top Navigation Bar dengan menu dropdown ala Siril."""
        menu_bar = self.menuBar()
        menu_bar.clear()

        # 1. Menu OPEN IMAGE / FILE
        menu_open = menu_bar.addMenu("Open Image")

        act_single = menu_open.addAction("Open Single Image...")
        act_single.setShortcut("Ctrl+O")
        act_single.triggered.connect(self.open_image_dialog)

        act_multi = menu_open.addAction("Multiple Images...")
        act_multi.setShortcut("Ctrl+M")
        act_multi.triggered.connect(self.open_multiple_images_dialog)

        act_folder = menu_open.addAction("Open Folder Sequence...")
        act_folder.triggered.connect(self.open_folder_sequence_dialog)

        act_video = menu_open.addAction("Open Video (.AVI, .MP4, .MOV)...")
        act_video.triggered.connect(self.open_video_dialog)

        act_ser = menu_open.addAction("Open SER Astronomy Video...")
        act_ser.triggered.connect(self.open_ser_dialog)

        menu_open.addSeparator()
        act_close = menu_open.addAction("Close Image")
        act_close.setShortcut("Ctrl+W")
        act_close.triggered.connect(self.close_image)

        menu_open.addSeparator()
        act_exit = menu_open.addAction("Keluar")
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)

        # 2. Menu IMAGE PROCESSING
        menu_proc = menu_bar.addMenu("Image Processing")

        act_auto = menu_proc.addAction("Mulai Pemrosesan Otomatis")
        act_auto.triggered.connect(self._on_start_auto_process_clicked)

        menu_proc.addSeparator()

        act_flat_info = menu_proc.addAction("Informasi Kalibrasi Flat-Field...")
        act_flat_info.triggered.connect(self.show_flat_info_dialog)

        act_proc_curves = menu_proc.addAction("Transformasi Kurva (Curves Adjustment)...")
        act_proc_curves.triggered.connect(self.open_curves_window)

        # 3. Menu TOOLS
        menu_tools = menu_bar.addMenu("Tools")

        act_info_dlg = menu_tools.addAction("Image Information && Metadata Editor (FITS Header)...")
        act_info_dlg.setShortcut("F2")
        act_info_dlg.triggered.connect(self.open_image_information_dialog)

        act_hist = menu_tools.addAction("Histogram && Image Statistics...")
        act_hist.setShortcut("F3")
        act_hist.triggered.connect(self.open_histogram_window)

        act_curves = menu_tools.addAction("Kurva / Curves Transformation...")
        act_curves.setShortcut("F4")
        act_curves.triggered.connect(self.open_curves_window)

        self.act_console_log = menu_tools.addAction("Console / Processing Log")
        self.act_console_log.setShortcut("F5")
        self.act_console_log.setCheckable(True)
        self.act_console_log.setChecked(False)
        self.act_console_log.triggered.connect(self.toggle_console_panel)

        menu_tools.addSeparator()

        self.act_night_vision = menu_tools.addAction("Night Vision Red Theme")
        self.act_night_vision.setCheckable(True)
        self.act_night_vision.setChecked(False)
        self.act_night_vision.triggered.connect(self.toggle_night_vision_theme)

        # 4. Menu VIEW
        menu_view = menu_bar.addMenu("View")

        act_fit = menu_view.addAction("Fit the Image")
        act_fit.triggered.connect(self.viewer.fit_to_viewport)

        act_1to1 = menu_view.addAction("Original Size (1:1)")
        act_1to1.triggered.connect(self.viewer.set_original_size)

        act_zin = menu_view.addAction("Zoom In")
        act_zin.setShortcut("Ctrl++")
        act_zin.triggered.connect(lambda: self.viewer.zoom_in())

        act_zout = menu_view.addAction("Zoom Out")
        act_zout.setShortcut("Ctrl+-")
        act_zout.triggered.connect(lambda: self.viewer.zoom_out())

        menu_view.addSeparator()

        act_rot_ccw = menu_view.addAction("Rotate 90° CCW (Berlawanan Jarum Jam)")
        act_rot_ccw.triggered.connect(self.rotate_image_ccw)

        act_rot_cw = menu_view.addAction("Rotate 90° CW (Searah Jarum Jam)")
        act_rot_cw.triggered.connect(self.rotate_image_cw)

        act_flip_h = menu_view.addAction("Flip Horizontal (Balik Kiri-Kanan)")
        act_flip_h.triggered.connect(self.flip_image_horizontal)

        act_flip_v = menu_view.addAction("Flip Vertical (Balik Atas-Bawah)")
        act_flip_v.triggered.connect(self.flip_image_vertical)

        menu_view.addSeparator()
        self.act_toggle_top_panels = menu_view.addAction("Tampilkan Panel Input (Panel A, B, C)")
        self.act_toggle_top_panels.setCheckable(True)
        self.act_toggle_top_panels.setChecked(False)
        self.act_toggle_top_panels.toggled.connect(self._set_top_panels_visible)

        self.act_toggle_console = menu_view.addAction("Tampilkan Console / Log")
        self.act_toggle_console.setCheckable(True)
        self.act_toggle_console.setChecked(False)
        self.act_toggle_console.triggered.connect(self.toggle_console_panel)

        menu_view.addSeparator()
        act_reset_layout = menu_view.addAction("Reset Layout Jendela")
        act_reset_layout.triggered.connect(lambda: self.resize(1366, 768))

        # 5. Menu HELP
        menu_help = menu_bar.addMenu("Help")

        self.act_check_updates = menu_help.addAction("Check for Updates...")
        self.act_check_updates.triggered.connect(self.check_for_updates_interactive)

        self.act_auto_update_check = menu_help.addAction("Automatic Update Check")
        self.act_auto_update_check.setCheckable(True)
        self.act_auto_update_check.setChecked(self._update_prefs.auto_update_check_enabled)
        self.act_auto_update_check.triggered.connect(self.toggle_automatic_update_check)

        menu_help.addSeparator()

        self.act_report_issue = menu_help.addAction("Report an Issue...")
        self.act_report_issue.triggered.connect(self.open_report_issue_page)

        menu_help.addSeparator()

        self.act_about_hilalone = menu_help.addAction("About HILALONE...")
        self.act_about_hilalone.triggered.connect(self.show_about_dialog)

    def _set_top_panels_visible(self, visible: bool) -> None:
        """Menampilkan atau menyembunyikan kontainer Panel A, B, C."""
        if hasattr(self, "top_panels_widget"):
            self.top_panels_widget.setVisible(visible)
        if hasattr(self, "panel_a"):
            self.panel_a.setVisible(visible)
        if hasattr(self, "panel_b"):
            self.panel_b.setVisible(visible)
        if hasattr(self, "panel_c"):
            self.panel_c.setVisible(visible)
        if hasattr(self, "act_toggle_top_panels"):
            self.act_toggle_top_panels.blockSignals(True)
            self.act_toggle_top_panels.setChecked(visible)
            self.act_toggle_top_panels.blockSignals(False)

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

        # Tombol Aksi Cepat di Header Kanan (Night Vision, Histogram, Console Log)
        self.btn_quick_night_vision = QPushButton("Night Vision")
        self.btn_quick_night_vision.setObjectName("secondaryButton")
        self.btn_quick_night_vision.setIcon(create_vector_icon("moon", size=16))
        self.btn_quick_night_vision.setIconSize(QSize(16, 16))
        self.btn_quick_night_vision.setCheckable(True)
        self.btn_quick_night_vision.setChecked(False)
        self.btn_quick_night_vision.setMinimumHeight(32)
        self.btn_quick_night_vision.setToolTip("Toggle Night Vision Red Theme untuk lingkungan malam")
        self.btn_quick_night_vision.clicked.connect(self.toggle_night_vision_theme)
        header_layout.addWidget(self.btn_quick_night_vision)

        self.btn_quick_histogram = QPushButton("Histogram")
        self.btn_quick_histogram.setObjectName("secondaryButton")
        self.btn_quick_histogram.setIcon(create_vector_icon("bar-chart-2", size=16))
        self.btn_quick_histogram.setIconSize(QSize(16, 16))
        self.btn_quick_histogram.setMinimumHeight(32)
        self.btn_quick_histogram.setToolTip("Buka jendela analisis Histogram & Statistik Citra [F3]")
        self.btn_quick_histogram.clicked.connect(self.open_histogram_window)
        header_layout.addWidget(self.btn_quick_histogram)

        self.btn_quick_curves = QPushButton("Kurva")
        self.btn_quick_curves.setObjectName("secondaryButton")
        self.btn_quick_curves.setIcon(create_vector_icon("trending-up", size=16))
        self.btn_quick_curves.setIconSize(QSize(16, 16))
        self.btn_quick_curves.setMinimumHeight(32)
        self.btn_quick_curves.setToolTip("Buka jendela Transformasi Kurva untuk mengatur kontras secara manual [F4]")
        self.btn_quick_curves.clicked.connect(self.open_curves_window)
        header_layout.addWidget(self.btn_quick_curves)

        self.btn_quick_info = QPushButton("Info")
        self.btn_quick_info.setObjectName("secondaryButton")
        self.btn_quick_info.setIcon(create_vector_icon("info", size=16))
        self.btn_quick_info.setIconSize(QSize(16, 16))
        self.btn_quick_info.setMinimumHeight(32)
        self.btn_quick_info.setToolTip("Buka Image Information & Metadata Editor (FITS Header) [F2]")
        self.btn_quick_info.clicked.connect(self.open_image_information_dialog)
        header_layout.addWidget(self.btn_quick_info)

        self.btn_quick_console = QPushButton("Console Log")
        self.btn_quick_console.setObjectName("secondaryButton")
        self.btn_quick_console.setIcon(create_vector_icon("terminal", size=16))
        self.btn_quick_console.setIconSize(QSize(16, 16))
        self.btn_quick_console.setCheckable(True)
        self.btn_quick_console.setChecked(False)
        self.btn_quick_console.setMinimumHeight(32)
        self.btn_quick_console.setToolTip("Tampilkan atau sembunyikan Console / Processing Log")
        self.btn_quick_console.clicked.connect(self.toggle_console_panel)
        header_layout.addWidget(self.btn_quick_console)

        return header_layout

    def _build_toolbar(self) -> QHBoxLayout:
        """Toolbar kompatibilitas internal (menggunakan tombol pada Panel A)."""
        layout = QHBoxLayout()
        layout.setSpacing(10)
        if hasattr(self, "panel_a"):
            layout.addWidget(self.panel_a.btn_open_single)
            layout.addWidget(self.panel_a.btn_open_multi)
            layout.addWidget(self.panel_a.btn_open_folder)
            layout.addWidget(self.panel_a.btn_open_video)
            layout.addWidget(self.panel_a.btn_open_ser)
            layout.addWidget(self.panel_a.btn_close)
        layout.addStretch(1)
        return layout

    def _build_sequence_nav_bar(self) -> QWidget:
        self.nav_bar = QWidget()
        layout = QHBoxLayout(self.nav_bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        lbl = QLabel("Daftar Frame:")
        lbl.setObjectName("infoKey")

        self.prev_frame_button = QPushButton("Sebelumnya")
        self.prev_frame_button.setObjectName("secondaryButton")
        self.prev_frame_button.setIcon(create_vector_icon("chevron-left", size=14))
        self.prev_frame_button.setIconSize(QSize(14, 14))
        self.prev_frame_button.clicked.connect(self.show_previous_frame)

        self.frame_combo = QComboBox()
        self.frame_combo.currentIndexChanged.connect(self._on_frame_combo_changed)

        self.next_frame_button = QPushButton("Berikutnya")
        self.next_frame_button.setObjectName("secondaryButton")
        self.next_frame_button.setIcon(create_vector_icon("chevron-right", size=14))
        self.next_frame_button.setIconSize(QSize(14, 14))
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
        self.zoom_out_button.clicked.connect(lambda: self.viewer.zoom_out())

        # 3. zoom-in — Zoom In
        self.zoom_in_button = QToolButton()
        self.zoom_in_button.setProperty("class", "imageActionButton")
        self.zoom_in_button.setIcon(create_vector_icon("zoom-in"))
        self.zoom_in_button.setIconSize(QSize(20, 20))
        self.zoom_in_button.setToolTip("Zoom In / Perbesar (Klik atau putar mouse wheel ke atas)")
        self.zoom_in_button.clicked.connect(lambda: self.viewer.zoom_in())

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

        # 6. rotate-ccw — Putar 90° Berlawanan Jarum Jam
        self.rotate_ccw_button = QToolButton()
        self.rotate_ccw_button.setProperty("class", "imageActionButton")
        self.rotate_ccw_button.setIcon(create_vector_icon("rotate-ccw"))
        self.rotate_ccw_button.setIconSize(QSize(20, 20))
        self.rotate_ccw_button.setToolTip("Putar 90° Berlawanan Jarum Jam (Rotate 90° CCW)")
        self.rotate_ccw_button.clicked.connect(self.rotate_image_ccw)

        # 7. rotate-cw — Putar 90° Searah Jarum Jam
        self.rotate_cw_button = QToolButton()
        self.rotate_cw_button.setProperty("class", "imageActionButton")
        self.rotate_cw_button.setIcon(create_vector_icon("rotate-cw"))
        self.rotate_cw_button.setIconSize(QSize(20, 20))
        self.rotate_cw_button.setToolTip("Putar 90° Searah Jarum Jam (Rotate 90° CW)")
        self.rotate_cw_button.clicked.connect(self.rotate_image_cw)

        # 8. flip-horizontal — Balik Horizontal
        self.flip_horizontal_button = QToolButton()
        self.flip_horizontal_button.setProperty("class", "imageActionButton")
        self.flip_horizontal_button.setIcon(create_vector_icon("flip-horizontal"))
        self.flip_horizontal_button.setIconSize(QSize(20, 20))
        self.flip_horizontal_button.setToolTip("Balik Citra Horizontal (Flip Horizontal / Mirror Kiri-Kanan)")
        self.flip_horizontal_button.clicked.connect(self.flip_image_horizontal)

        # 9. flip-vertical — Balik Vertikal
        self.flip_vertical_button = QToolButton()
        self.flip_vertical_button.setProperty("class", "imageActionButton")
        self.flip_vertical_button.setIcon(create_vector_icon("flip-vertical"))
        self.flip_vertical_button.setIconSize(QSize(20, 20))
        self.flip_vertical_button.setToolTip("Balik Citra Vertikal (Flip Vertical / Mirror Atas-Bawah)")
        self.flip_vertical_button.clicked.connect(self.flip_image_vertical)

        # 10. negative-view — Switch Normal & Negative View
        self.negative_view_button = QToolButton()
        self.negative_view_button.setProperty("class", "imageActionButton")
        self.negative_view_button.setIcon(create_vector_icon("negative-view"))
        self.negative_view_button.setIconSize(QSize(20, 20))
        self.negative_view_button.setCheckable(True)
        self.negative_view_button.setChecked(False)
        self.negative_view_button.setToolTip(
            "Switch Normal / Negative View (Balik Tampilan Intensitas Citra)"
        )
        self.negative_view_button.toggled.connect(self._on_negative_view_toggled)

        layout.addWidget(self.magnifier_button)
        layout.addWidget(self.zoom_out_button)
        layout.addWidget(self.zoom_in_button)
        layout.addWidget(self.fit_image_button)
        layout.addWidget(self.original_size_button)
        layout.addWidget(self.rotate_ccw_button)
        layout.addWidget(self.rotate_cw_button)
        layout.addWidget(self.flip_horizontal_button)
        layout.addWidget(self.flip_vertical_button)
        layout.addWidget(self.negative_view_button)

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

    # ------------------------------------------------------------------ REDESIGN HANDLERS & WINDOWS
    def _on_frame_list_activated(self, index: int) -> None:
        """Dipanggil saat pengguna mengklik atau menekan enter pada item di Frame List Panel (Panel B)."""
        if 0 <= index < self.sequence_manager.frame_count:
            self.select_sequence_frame(index)

    def _on_frame_selection_changed(self, selected_indices: list[int]) -> None:
        """Dipanggil saat status checkbox frame di Panel B berubah."""
        t0 = time.perf_counter()
        self._selected_frame_indices = list(selected_indices)
        total = self.sequence_manager.frame_count
        dt = time.perf_counter() - t0
        if total > 0:
            self.log_manager.info(
                "FRAME_SELECTION",
                "Seleksi Frame Diperbarui",
                f"{len(selected_indices)} dari {total} frame dipilih untuk pemrosesan | Total waktu: {dt:.2f}s",
            )

    def _get_current_active_scientific_data(self) -> np.ndarray | None:
        """Mendapatkan array float32/ilmiah dari frame aktif saat ini atau dari viewer."""
        if hasattr(self, "viewer") and self.viewer.has_image():
            sci = self.viewer.scientific_data()
            if sci is not None:
                return sci
        if self.sequence_manager.frame_count > 0:
            idx = self.sequence_manager.current_index
            if 0 <= idx < self.sequence_manager.frame_count:
                try:
                    loaded = self.sequence_manager.load_frame(idx)
                    return loaded.scientific_data
                except Exception as exc:
                    if hasattr(self, "log_manager"):
                        self.log_manager.warning("DATA", "Ambil Data Frame", f"Gagal membaca data ilmiah frame #{idx + 1}: {exc}")
        return None

    def open_histogram_window(self) -> None:
        """Membuka jendela analisis Histogram & Statistik Citra non-modal interaktif."""
        t0 = time.perf_counter()
        if self.histogram_window is None:
            self.histogram_window = HistogramWindow(parent=self)
        data = self._get_current_active_scientific_data()
        title = self._current_file_name or "Citra Aktif"
        self.histogram_window.set_image_data(data, title)
        self.histogram_window.show()
        self.histogram_window.raise_()
        self.histogram_window.activateWindow()
        dt = time.perf_counter() - t0
        self.log_manager.info("TOOLS", "Histogram Dibuka", f"Menampilkan analisis histogram untuk '{title}' | Total waktu: {dt:.2f}s")

    def open_curves_window(self) -> None:
        """Membuka jendela Transformasi Kurva non-modal interaktif."""
        if not self.viewer.has_image():
            self._show_error("Buka citra terlebih dahulu untuk menggunakan Transformasi Kurva.")
            return
        t0 = time.perf_counter()
        if self.curves_window is None:
            self.curves_window = CurvesWindow(parent=self)
            self.curves_window.preview_requested.connect(self._on_curves_live_preview)
            self.curves_window.apply_requested.connect(self._on_curves_apply)
            self.curves_window.reset_requested.connect(self._on_curves_reset)

        qimg = self.viewer.source_qimage()
        data = self._get_current_active_scientific_data()
        self._curves_backup_qimage = qimg.copy() if qimg is not None else None
        self._curves_backup_scientific_data = data.copy() if data is not None else None

        title = self._current_file_name or "Citra Aktif"
        self.curves_window.set_source_data(data, qimg, title)
        self.curves_window.show()
        self.curves_window.raise_()
        self.curves_window.activateWindow()
        dt = time.perf_counter() - t0
        self.log_manager.info("TOOLS", "Kurva Dibuka", f"Menampilkan Transformasi Kurva untuk '{title}' | Total waktu: {dt:.2f}s")

    def _on_curves_live_preview(self, lut: np.ndarray, mode: str) -> None:
        """Menerapkan kurva secara instan ke layar untuk pratinjau."""
        base_qimg = self._curves_backup_qimage if self._curves_backup_qimage is not None else self.viewer.source_qimage()
        if base_qimg is None:
            return
        pix = QPixmap.fromImage(base_qimg)
        curved_pix = apply_curve_lut_to_pixmap(pix, lut, mode)
        self.viewer.set_image(curved_pix.toImage(), self.viewer.scientific_data())

    def _on_curves_apply(self, lut: np.ndarray, mode: str) -> None:
        """Menerapkan kurva secara permanen ke tampilan dan data ilmiah."""
        t0 = time.perf_counter()
        if not self.viewer.has_image():
            return

        base_qimg = self._curves_backup_qimage if self._curves_backup_qimage is not None else self.viewer.source_qimage()
        if base_qimg is not None:
            pix = QPixmap.fromImage(base_qimg)
            curved_pix = apply_curve_lut_to_pixmap(pix, lut, mode)
            curved_qimg = curved_pix.toImage()
        else:
            curved_qimg = None

        if self._curves_backup_scientific_data is not None:
            base_data = self._curves_backup_scientific_data
        else:
            base_data = self._get_current_active_scientific_data()

        curved_data = None
        if base_data is not None:
            curved_data = apply_curve_lut_to_array(base_data, lut, mode)

        if curved_qimg is not None:
            self.viewer.set_image(curved_qimg, curved_data)
            self._curves_backup_qimage = curved_qimg.copy()
            self._curves_backup_scientific_data = curved_data.copy() if curved_data is not None else None
            self._active_original_qimage = curved_qimg.copy()
            if hasattr(self, "_on_the_fly_previews"):
                self._on_the_fly_previews.clear()

        if self.curves_window is not None and self.curves_window.isVisible():
            self.curves_window.mark_applied()
            self.curves_window._source_data = curved_data
            self.curves_window._source_qimage = curved_qimg
            self.curves_window.canvas.set_histogram_data(curved_data)
            self.curves_window.canvas.set_points([(0.0, 0.0), (1.0, 1.0)])

        if self.histogram_window is not None and self.histogram_window.isVisible():
            self.histogram_window.set_image_data(curved_data, self._current_file_name or "Citra (Kurva)")

        self.statusBar().showMessage("Transformasi Kurva berhasil diterapkan pada citra.", 3000)
        dt_curv = time.perf_counter() - t0
        self.log_manager.success("CURVES", "Transformasi Kurva Diterapkan", f"Mode: {mode} | Total waktu: {dt_curv:.2f}s")

    def _on_curves_reset(self) -> None:
        """Mengembalikan tampilan citra ke kondisi sebelum kurva diubah."""
        if self._curves_backup_qimage is not None:
            self.viewer.set_image(self._curves_backup_qimage, self._curves_backup_scientific_data)
            self.statusBar().showMessage("Kurva direset ke tampilan awal.", 2500)

    def open_image_information_dialog(self) -> None:
        """Membuka jendela Image Information & Metadata Editor ala Siril FITS Header Editor."""
        t0 = time.perf_counter()
        if self.info_dialog is None:
            self.info_dialog = ImageInformationDialog(parent=self)
            self.info_dialog.metadata_edited.connect(self._on_metadata_edited)

        cards: list[tuple[str, str, str]] = []
        info: ImageInfo | None = self._current_info
        entry: SequenceFrameEntry | None = None

        if self.sequence_manager.frame_count > 0:
            idx = self.sequence_manager.current_index
            if 0 <= idx < self.sequence_manager.frame_count:
                entry = self.sequence_manager.entries[idx]
                if info is None and entry.info is not None:
                    info = entry.info

        file_name = (
            info.file_name
            if info is not None
            else (entry.file_name if entry is not None else (self._current_file_name or "Tidak ada berkas aktif"))
        )

        try:
            if entry is not None or info is not None:
                src_path = str(entry.source_path) if entry is not None else (str(info.path) if info is not None else "-")
                cards.append(("FILENAME", file_name, "Nama berkas citra"))
                cards.append(("FILE_PATH", src_path, "Jalur berkas di penyimpanan"))

                fmt_str = (
                    info.file_format
                    if info is not None
                    else (entry.file_format if entry is not None else "UNKNOWN")
                )
                cards.append(("FILE_FORMAT", str(fmt_str), "Format container citra"))

                if info is not None:
                    cards.append(("NAXIS1", str(info.width), "Lebar citra (piksel)"))
                    cards.append(("NAXIS2", str(info.height), "Tinggi citra (piksel)"))
                    cards.append(("CHANNELS", str(info.channels or 1), "Jumlah kanal sensor"))
                    cards.append(("BITPIX", str(info.original_bit_depth or 16), "Kedalaman bit data asli"))
                    if info.dtype_str:
                        cards.append(("DATATYPE", str(info.dtype_str), "Tipe data penyimpanan internal"))
                    if info.exif_orientation:
                        cards.append(("ORIENT", str(info.exif_orientation), "Orientasi EXIF/sensor"))

                    if info.fits_header is not None:
                        try:
                            _kw_map, raw_cards = _read_fits_header_cards_readonly(info.path, getattr(info, "hdu_index", 0) or 0)
                            existing_keys = {c[0].upper() for c in cards}
                            for k, v, cmt in raw_cards:
                                k_up = str(k).strip().upper()
                                if k_up and k_up not in existing_keys:
                                    v_clean = str(v).strip()
                                    if k_up in ("EXPTIME", "EXPOSURE") and v_clean:
                                        try:
                                            sec_val = float(v_clean)
                                            if math.isfinite(sec_val) and sec_val >= 0.0:
                                                v_clean = f"{sec_val:.2f} s"
                                        except (ValueError, TypeError):
                                            pass
                                    cards.append((str(k).strip(), v_clean, str(cmt).strip()))
                                    existing_keys.add(k_up)
                        except Exception as fits_err:
                            self.log_manager.warning("FITS", "Gagal membaca header FITS lengkap", str(fits_err))

                    if info.raw_metadata is not None:
                        meta = info.raw_metadata
                        cam_name = (
                            meta.format_camera_name()
                            if hasattr(meta, "format_camera_name")
                            else f"{meta.camera_make or ''} {meta.camera_model or ''}".strip()
                        )
                        raw_exptime_str = ""
                        if hasattr(meta, "shutter_speed_sec") and meta.shutter_speed_sec is not None:
                            try:
                                s_val = float(meta.shutter_speed_sec)
                                raw_exptime_str = f"{s_val:.2f} s" if (math.isfinite(s_val) and s_val >= 0.0) else f"{meta.shutter_speed_sec} s"
                            except (ValueError, TypeError):
                                raw_exptime_str = f"{meta.shutter_speed_sec} s"

                        raw_items = [
                            ("INSTRUME", cam_name, "Kamera / Instrumen"),
                            ("ISOSPEED", str(meta.iso_speed or "") if hasattr(meta, "iso_speed") else "", "Sensitivitas ISO sensor"),
                            ("EXPTIME", raw_exptime_str, "Waktu eksposur (shutter)"),
                            ("APERTUR", f"f/{meta.aperture_fnumber:.1f}" if (hasattr(meta, "aperture_fnumber") and meta.aperture_fnumber is not None) else "", "Bukaan lensa (aperture)"),
                            ("FOCALLEN", f"{meta.focal_length_mm:.1f} mm" if (hasattr(meta, "focal_length_mm") and meta.focal_length_mm is not None) else "", "Panjang fokus lensa"),
                            ("DATE-OBS", str(meta.timestamp_str or ""), "Waktu perekaman citra"),
                            ("BAYERPAT", str(getattr(meta, "cfa_pattern_str", "") or ""), "Pola Bayer CFA sensor"),
                        ]
                        existing_keys = {c[0].upper() for c in cards}
                        for k, v, cmt in raw_items:
                            if v and k.upper() not in existing_keys:
                                cards.append((k, v, cmt))
                                existing_keys.add(k.upper())

                    if info.video_metadata is not None:
                        v = info.video_metadata
                        v_items = [
                            ("CONTAINER", str(v.container_format), "Format kontainer video"),
                            ("CODEC", str(v.codec_name), "Codec kompresi video"),
                            ("FRAMECNT", str(v.frame_count), "Total frame dalam berkas video"),
                            ("FPS", f"{v.average_rate_fps:.2f}" if v.average_rate_fps else "-", "Frame rate rata-rata"),
                            ("PIX_FMT", str(v.pix_fmt or "-"), "Format piksel video asli"),
                            ("DURATION", f"{v.duration_sec:.2f} s" if v.duration_sec else "-", "Durasi total video"),
                        ]
                        existing_keys = {c[0].upper() for c in cards}
                        for k, v, cmt in v_items:
                            if v and k.upper() not in existing_keys:
                                cards.append((k, v, cmt))
                                existing_keys.add(k.upper())

                    if info.ser_metadata is not None:
                        s = info.ser_metadata
                        s_items = [
                            ("COLOR_ID", str(s.color_id), "ID Tata Warna SER"),
                            ("FRAMECNT", str(s.frame_count), "Jumlah frame SER"),
                            ("OBSERVER", str(s.observer or "-"), "Pengamat / Observer"),
                            ("TELESCOP", str(s.telescope or s.instrument or "-"), "Instrumen / Teleskop"),
                            ("DATE-OBS", str(getattr(s, "date_time_utc_str", None) or getattr(s, "date_time_local_str", None) or "-"), "Waktu perekaman"),
                        ]
                        existing_keys = {c[0].upper() for c in cards}
                        for k, v, cmt in s_items:
                            if v and k.upper() not in existing_keys:
                                cards.append((k, v, cmt))
                                existing_keys.add(k.upper())
            else:
                cards.append(("STATUS", "Tidak ada berkas aktif", "Buka citra untuk memeriksa metadata"))
        except Exception as exc:
            self.log_manager.warning("METADATA", "Galat ekstraksi metadata", str(exc))
            if not cards:
                cards.append(("FILENAME", file_name, "Nama berkas citra"))
                cards.append(("ERROR", str(exc), "Catatan pembacaan metadata"))

        # Sertakan metadata custom yang telah diedit/ditambahkan oleh pengguna
        for kw, (val, cmt) in self._custom_metadata.items():
            cards.append((kw, val, cmt))

        self.info_dialog.populate_metadata(cards, file_name)
        self.info_dialog.show()
        self.info_dialog.raise_()
        self.info_dialog.activateWindow()
        dt = time.perf_counter() - t0
        self.log_manager.info("TOOLS", "Image Information Dibuka", f"Memeriksa metadata '{file_name}' | Total waktu: {dt:.2f}s")

    def _on_metadata_edited(self, key: str, value: str, comment: str) -> None:
        """Handler saat pengguna memodifikasi atau menambah kartu metadata di info dialog."""
        t0 = time.perf_counter()
        self._custom_metadata[key] = (value, comment)
        dt = time.perf_counter() - t0
        self.log_manager.info("METADATA", "Metadata Diperbarui", f"Kartu '{key}' = '{value}' ({comment}) | Total waktu: {dt:.2f}s")

    def show_flat_info_dialog(self) -> None:
        """Menampilkan dialog informasi dan pedoman ilmiah kalibrasi Flat-Field HILALONE."""
        msg_text = (
            "PEDOMAN KALIBRASI FLAT-FIELD (MVP 1.0)\n\n"
            "1. Tujuan Ilmiah:\n"
            "   Mengoreksi efek vignetting optik (penurunan cahaya ke tepi sensor/lensa) dan\n"
            "   variasi respons sensitivitas piksel secara non-destruktif sebelum ekstraksi\n"
            "   background dan stacking.\n\n"
            "2. Rumus Normalisasi Master Flat:\n"
            f"   {NORMALIZATION_FORMULA_TEXT}\n"
            "   (Normalisasi dilakukan dengan membagi master flat terhadap median dari seluruh\n"
            "    piksel yang valid: F > 0 dan berhingga)\n\n"
            "3. Persyaratan Berkas Flat:\n"
            "   • Pencahayaan Homogen : Flat frame harus berupa citra pencahayaan merata\n"
            "                          (twilight sky flat atau lightbox panel).\n"
            "   • Validitas Piksel    : Dilarang menggunakan flat gelap total\n"
            "                          (nilai piksel <= 0 atau bernilai NaN/Infinite).\n"
            "   • Format Fleksibel    : Mendukung Single Image, Multiple Files, Folder,\n"
            "                          Video (AVI/MP4/MOV), atau berkas astronomi SER.\n\n"
            "4. Multi-frame Light vs Flat:\n"
            "   Jumlah frame Light dan Flat tidak wajib sama. Seluruh frame Flat diagregasikan\n"
            "   menjadi SATU Master Flat berkualitas tinggi yang otomatis diaplikasikan ke seluruh\n"
            "   frame Light saat pemrosesan otomatis dijalankan."
        )
        QMessageBox.information(
            self,
            "Informasi Kalibrasi Flat-Field HILALONE",
            msg_text,
        )

    def toggle_night_vision_theme(self, active: bool | None = None, *, persist: bool = True) -> None:
        """Mengganti tema antarmuka antara Standard Dark dan Night Vision Red Theme."""
        t0 = time.perf_counter()
        if active is None:
            self._is_night_vision = not self._is_night_vision
        else:
            self._is_night_vision = bool(active)

        self.act_night_vision.blockSignals(True)
        self.act_night_vision.setChecked(self._is_night_vision)
        self.act_night_vision.blockSignals(False)

        self.btn_quick_night_vision.blockSignals(True)
        self.btn_quick_night_vision.setChecked(self._is_night_vision)
        self.btn_quick_night_vision.blockSignals(False)

        theme_mode = ThemeMode.NIGHT_VISION_RED if self._is_night_vision else ThemeMode.STANDARD_DARK
        stylesheet = get_theme_stylesheet(theme_mode)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(stylesheet)

        # Terapkan penyelarasan warna ikon & elemen ke seluruh widget antarmuka
        self._apply_theme_to_widgets(self._is_night_vision)
        if persist:
            self._save_user_preferences()

        theme_name = "Night Vision Red" if self._is_night_vision else "Standard Dark"
        dt_theme = time.perf_counter() - t0
        self.log_manager.info("THEME", "Pergantian Tema", f"Tema antarmuka beralih ke {theme_name} | Total waktu: {dt_theme:.2f}s")
        self.statusBar().showMessage(f"Tema antarmuka: {theme_name}", 3000)

    def _apply_theme_to_widgets(self, is_night_vision: bool) -> None:
        """Menyelaraskan seluruh elemen visual, ikon, status bar, accordion, dan logo dengan tema aktif."""
        # 0. Ikon Jendela
        window_icon = get_app_icon(night_vision=is_night_vision)
        if not window_icon.isNull():
            self.setWindowIcon(window_icon)

        # 1. Logo Header
        if hasattr(self, "logo_label"):
            logo_pixmap = get_header_logo_pixmap(target_height=44, night_vision=is_night_vision)
            if not logo_pixmap.isNull():
                self.logo_label.setPixmap(logo_pixmap)

        # 2. Tombol Aksi Cepat di Header
        if hasattr(self, "btn_quick_night_vision"):
            self.btn_quick_night_vision.setIcon(
                create_themed_vector_icon("moon", night_vision=is_night_vision, size=16)
            )
        if hasattr(self, "btn_quick_histogram"):
            self.btn_quick_histogram.setIcon(
                create_themed_vector_icon("bar-chart-2", night_vision=is_night_vision, size=16)
            )
        if hasattr(self, "btn_quick_curves"):
            self.btn_quick_curves.setIcon(
                create_themed_vector_icon("trending-up", night_vision=is_night_vision, size=16)
            )
        if hasattr(self, "btn_quick_info"):
            self.btn_quick_info.setIcon(
                create_themed_vector_icon("info", night_vision=is_night_vision, size=16)
            )
        if hasattr(self, "btn_quick_console"):
            self.btn_quick_console.setIcon(
                create_themed_vector_icon("terminal", night_vision=is_night_vision, size=16)
            )

        # 3. Toolbar Aksi Gambar (bawah viewer)
        action_buttons = [
            ("magnifier_button", "scan-eye", 20, False),
            ("zoom_out_button", "zoom-out", 20, False),
            ("zoom_in_button", "zoom-in", 20, False),
            ("fit_image_button", "scan", 20, False),
            ("original_size_button", "maximize", 20, False),
            ("rotate_ccw_button", "rotate-ccw", 20, False),
            ("rotate_cw_button", "rotate-cw", 20, False),
            ("flip_horizontal_button", "flip-horizontal", 20, False),
            ("flip_vertical_button", "flip-vertical", 20, False),
            ("negative_view_button", "negative-view", 20, False),
            ("save_result_action_button", "save", 20, False),
            ("snapshot_button", "camera", 20, False),
        ]
        for attr, icon_name, icon_size, is_info in action_buttons:
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.setIcon(
                    create_themed_vector_icon(
                        icon_name,
                        night_vision=is_night_vision,
                        is_info=is_info,
                        size=icon_size,
                    )
                )

        # 4. Kontrol Pemrosesan & Navigasi
        if hasattr(self, "btn_flat_info"):
            self.btn_flat_info.setIcon(
                create_themed_vector_icon("info", night_vision=is_night_vision, is_info=True, size=14)
            )
        if hasattr(self, "start_auto_process_button"):
            self.start_auto_process_button.setIcon(
                create_themed_vector_icon("play", night_vision=is_night_vision, size=16)
            )
        if hasattr(self, "toggle_before_after_button"):
            self.toggle_before_after_button.setIcon(
                create_themed_vector_icon("eye", night_vision=is_night_vision, size=15)
            )
        if hasattr(self, "prev_frame_button"):
            self.prev_frame_button.setIcon(
                create_themed_vector_icon("chevron-left", night_vision=is_night_vision, size=14)
            )
        if hasattr(self, "next_frame_button"):
            self.next_frame_button.setIcon(
                create_themed_vector_icon("chevron-right", night_vision=is_night_vision, size=14)
            )
        if hasattr(self, "fits_full_header_toggle"):
            icon_name = "chevron-down" if self.fits_full_header_toggle.isChecked() else "chevron-right"
            self.fits_full_header_toggle.setIcon(
                create_themed_vector_icon(icon_name, night_vision=is_night_vision, size=14)
            )

        # 5. Status Bar
        if hasattr(self, "status_file_info"):
            file_col = "#b91c1c" if is_night_vision else "#94a3b8"
            self.status_file_info.setStyleSheet(f"color: {file_col}; padding-right: 12px;")
        if hasattr(self, "status_res_info"):
            res_col = "#b91c1c" if is_night_vision else "#94a3b8"
            self.status_res_info.setStyleSheet(f"color: {res_col}; padding-right: 12px;")
        if hasattr(self, "status_view_info"):
            view_col = "#b91c1c" if is_night_vision else "#94a3b8"
            self.status_view_info.setStyleSheet(f"color: {view_col}; padding-right: 12px;")
        if hasattr(self, "status_zoom_info"):
            zoom_col = "#ef4444" if is_night_vision else "#38bdf8"
            self.status_zoom_info.setStyleSheet(f"color: {zoom_col}; font-weight: bold; padding-right: 12px;")
        if hasattr(self, "status_pixel_info"):
            pix_col = "#fca5a5" if is_night_vision else "#e2e8f0"
            self.status_pixel_info.setStyleSheet(f"color: {pix_col}; font-family: monospace; padding-right: 6px;")

        # 6. Accordion Groups & Sections
        if hasattr(self, "main_accordion_group"):
            self.main_accordion_group.set_night_vision(is_night_vision)
        if hasattr(self, "nested_accordion_group"):
            self.nested_accordion_group.set_night_vision(is_night_vision)

        accordion_sections = [
            "section_input_sequence",
            "section_processing",
            "section_image_info",
            "section_sensor_info",
            "section_camera_metadata",
            "section_fits_info",
            "section_video_info",
            "section_ser_info",
            "acc_nested_adv_settings",
            "acc_nested_flat",
            "acc_nested_master_flat",
            "acc_nested_preview",
            "acc_nested_results",
            "acc_nested_histogram",
        ]
        for sec_name in accordion_sections:
            sec = getattr(self, sec_name, None)
            if sec is not None and hasattr(sec, "set_night_vision"):
                sec.set_night_vision(is_night_vision)

        # 7. Viewer
        if hasattr(self, "viewer") and hasattr(self.viewer, "set_night_vision"):
            self.viewer.set_night_vision(is_night_vision)

        # 8. Top Panels (Panel A, B, C)
        for panel_attr in ("panel_a", "panel_b", "panel_c"):
            p = getattr(self, panel_attr, None)
            if p is not None and hasattr(p, "set_night_vision"):
                p.set_night_vision(is_night_vision)

        # 9. Console Panel
        if hasattr(self, "console_panel") and hasattr(self.console_panel, "set_night_vision"):
            self.console_panel.set_night_vision(is_night_vision)

        # 10. Dialog Help & Pembaruan
        if getattr(self, "about_dialog", None) is not None:
            self.about_dialog.apply_theme(is_night_vision)
        if getattr(self, "update_dialog", None) is not None:
            self.update_dialog.apply_theme(is_night_vision)
        if getattr(self, "update_notification_dialog", None) is not None:
            self.update_notification_dialog.apply_theme(is_night_vision)

    def toggle_console_panel(self, visible: bool | None = None) -> None:
        """Menampilkan atau menyembunyikan panel Console / Processing Log di bagian bawah."""
        if visible is None:
            visible = not self.console_panel.isVisible()
        else:
            visible = bool(visible)

        self.console_panel.setVisible(visible)
        self.act_console_log.blockSignals(True)
        self.act_console_log.setChecked(visible)
        self.act_console_log.blockSignals(False)

        if hasattr(self, "act_toggle_console"):
            self.act_toggle_console.blockSignals(True)
            self.act_toggle_console.setChecked(visible)
            self.act_toggle_console.blockSignals(False)

        self.btn_quick_console.blockSignals(True)
        self.btn_quick_console.setChecked(visible)
        self.btn_quick_console.blockSignals(False)

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

    def _on_negative_view_toggled(self, checked: bool) -> None:
        """Mengalihkan mode tampilan viewer antara Normal View dan Negative View."""
        if not self.viewer.has_image():
            if self.negative_view_button.isChecked():
                self.negative_view_button.blockSignals(True)
                self.negative_view_button.setChecked(False)
                self.negative_view_button.blockSignals(False)
            self.viewer.set_negative_view(False)
            return

        self.viewer.set_negative_view(checked)
        if checked:
            self.log_manager.info("VIEW", "Mode Tampilan", "Tampilan dialihkan ke Negative View (non-destruktif).")
            self.statusBar().showMessage("Tampilan Negative View aktif (data ilmiah tidak berubah).", 2500)
        else:
            self.log_manager.info("VIEW", "Mode Tampilan", "Tampilan dikembalikan ke Normal View.")
            self.statusBar().showMessage("Tampilan Normal View aktif.", 2500)

    def _refresh_image_toolbar_state(self) -> None:
        """Memperbarui status ketersediaan tombol toolbar aksi gambar."""
        has_img = self.viewer.has_image()
        self.magnifier_button.setEnabled(has_img)
        self.zoom_out_button.setEnabled(has_img)
        self.zoom_in_button.setEnabled(has_img)
        self.fit_image_button.setEnabled(has_img)
        self.original_size_button.setEnabled(has_img)
        self.rotate_ccw_button.setEnabled(has_img)
        self.rotate_cw_button.setEnabled(has_img)
        self.flip_horizontal_button.setEnabled(has_img)
        self.flip_vertical_button.setEnabled(has_img)
        self.negative_view_button.setEnabled(has_img)
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
            self.negative_view_button.blockSignals(True)
            self.negative_view_button.setChecked(False)
            self.negative_view_button.blockSignals(False)
            self.viewer.set_negative_view(False)

    # ------------------------------------------------- TRANSFORMASI CITRA (ROTASI & FLIP)
    def _apply_geometric_transform_to_all_layers(
        self,
        qimage_transform_fn: Any,
        array_transform_fn: Any,
    ) -> None:
        """Menerapkan transformasi geometris (rotasi/flip) secara sinkron ke seluruh layer pratinjau dan data ilmiah."""
        # 1. Update active original & original unprocessed
        if self._active_original_qimage is not None:
            self._active_original_qimage = qimage_transform_fn(self._active_original_qimage)
        if hasattr(self, "_original_unprocessed_qimage") and self._original_unprocessed_qimage is not None:
            self._original_unprocessed_qimage = qimage_transform_fn(self._original_unprocessed_qimage)

        # 2. Update curves backup jika ada
        if self._curves_backup_qimage is not None:
            self._curves_backup_qimage = qimage_transform_fn(self._curves_backup_qimage)
        if self._curves_backup_scientific_data is not None:
            self._curves_backup_scientific_data = array_transform_fn(self._curves_backup_scientific_data)

        # 3. Update pipeline previews & scientific result jika ada
        if self._last_pipeline_result is not None:
            if hasattr(self._last_pipeline_result, "previews") and self._last_pipeline_result.previews:
                for k, prev_img in list(self._last_pipeline_result.previews.items()):
                    if prev_img is not None and not prev_img.isNull():
                        self._last_pipeline_result.previews[k] = qimage_transform_fn(prev_img)
            if self._last_pipeline_result.linear_result is not None:
                self._last_pipeline_result.linear_result = array_transform_fn(self._last_pipeline_result.linear_result)

        # 4. Kosongkan cache on-the-fly previews agar dihitung ulang dari data terputar
        if hasattr(self, "_on_the_fly_previews"):
            self._on_the_fly_previews.clear()

        # 5. Sinkronisasi info resolusi dan dialog/window eksternal
        sz = self.viewer.raw_image_size()
        if hasattr(self, "status_res_info"):
            self.status_res_info.setText(f"{sz.width()} × {sz.height()} px")
        if self.histogram_window is not None and self.histogram_window.isVisible():
            self.histogram_window.set_image_data(self.viewer.scientific_data(), self._current_file_name)
        if self.curves_window is not None and self.curves_window.isVisible():
            self.curves_window.set_source_data(
                self.viewer.scientific_data(), self.viewer.source_qimage(), self._current_file_name
            )

    def rotate_image_cw(self) -> None:
        """Memutar citra aktif 90° searah jarum jam (Clockwise)."""
        if not self.viewer.has_image():
            return
        t0 = time.perf_counter()
        self.viewer.rotate_cw()
        self._apply_geometric_transform_to_all_layers(
            lambda img: img.transformed(QTransform().rotate(90), Qt.TransformationMode.FastTransformation),
            lambda arr: np.ascontiguousarray(np.rot90(arr, k=-1, axes=(0, 1))),
        )
        dt = time.perf_counter() - t0
        self.log_manager.info("VIEW", "Rotasi Citra", f"Citra diputar 90° searah jarum jam (CW) | Total waktu: {dt:.2f}s")
        self.statusBar().showMessage("Citra diputar 90° searah jarum jam (CW).", 2500)

    def rotate_image_ccw(self) -> None:
        """Memutar citra aktif 90° berlawanan arah jarum jam (Counter-Clockwise)."""
        if not self.viewer.has_image():
            return
        t0 = time.perf_counter()
        self.viewer.rotate_ccw()
        self._apply_geometric_transform_to_all_layers(
            lambda img: img.transformed(QTransform().rotate(-90), Qt.TransformationMode.FastTransformation),
            lambda arr: np.ascontiguousarray(np.rot90(arr, k=1, axes=(0, 1))),
        )
        dt = time.perf_counter() - t0
        self.log_manager.info("VIEW", "Rotasi Citra", f"Citra diputar 90° berlawanan arah jarum jam (CCW) | Total waktu: {dt:.2f}s")
        self.statusBar().showMessage("Citra diputar 90° berlawanan arah jarum jam (CCW).", 2500)

    def flip_image_horizontal(self) -> None:
        """Membalik citra aktif secara horizontal (Mirror Kiri-Kanan)."""
        if not self.viewer.has_image():
            return
        t0 = time.perf_counter()
        self.viewer.flip_horizontal()
        self._apply_geometric_transform_to_all_layers(
            lambda img: img.transformed(QTransform().scale(-1, 1)),
            lambda arr: np.ascontiguousarray(np.flip(arr, axis=1)),
        )
        dt = time.perf_counter() - t0
        self.log_manager.info("VIEW", "Flip Citra", f"Citra dibalik secara horizontal (Flip Horizontal) | Total waktu: {dt:.2f}s")
        self.statusBar().showMessage("Citra dibalik secara horizontal (Flip Horizontal).", 2500)

    def flip_image_vertical(self) -> None:
        """Membalik citra aktif secara vertikal (Mirror Atas-Bawah)."""
        if not self.viewer.has_image():
            return
        t0 = time.perf_counter()
        self.viewer.flip_vertical()
        self._apply_geometric_transform_to_all_layers(
            lambda img: img.transformed(QTransform().scale(1, -1)),
            lambda arr: np.ascontiguousarray(np.flip(arr, axis=0)),
        )
        dt = time.perf_counter() - t0
        self.log_manager.info("VIEW", "Flip Citra", f"Citra dibalik secara vertikal (Flip Vertical) | Total waktu: {dt:.2f}s")
        self.statusBar().showMessage("Citra dibalik secara vertikal (Flip Vertical).", 2500)

    def take_quick_snapshot(self) -> Path | None:
        """Mengambil tangkapan layar bersih area gambar aktif (Quick Snapshot) format PNG."""
        t0 = time.perf_counter()
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
        dt_snap = time.perf_counter() - t0
        self.log_manager.info(
            "SNAPSHOT",
            "Cuplikan Cepat Disimpan",
            f"{candidate_path.name} | Lokasi: {candidate_path.parent} | Total waktu: {dt_snap:.2f}s",
        )
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
    ) -> tuple[AccordionSection, QLabel]:
        """Membuat satu kartu kelompok informasi sebagai AccordionSection dengan header dan grid 2 kolom."""
        card = AccordionSection(title_text)
        grid = QGridLayout()
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(6)
        self._populate_key_value_grid(grid, rows)
        card.add_layout(grid)
        return card, card.title_label

    def _build_fits_info_card(self) -> AccordionSection:
        """Membangun kartu 'Informasi FITS' sebagai AccordionSection dengan 3 sub-kelompok + bagian collapsible 'Header FITS Lengkap'."""
        card = AccordionSection("Informasi FITS")
        self.header_fits_info = card.title_label
        layout = card.content_layout

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
        self.fits_full_header_toggle = QPushButton("Header FITS Lengkap")
        self.fits_full_header_toggle.setObjectName("collapsibleButton")
        self.fits_full_header_toggle.setIcon(
            create_themed_vector_icon("chevron-right", night_vision=self._is_night_vision, size=14)
        )
        self.fits_full_header_toggle.setIconSize(QSize(14, 14))
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

        # Label di memori yang menyimpan seluruh kartu header asli secara utuh untuk pengujian/inspeksi,
        # tidak dimasukkan ke dalam visual layout agar tidak menduplikasi tampilan tabel grid.
        self.fits_full_header_raw_label = QLabel(EMPTY_VALUE)
        self.fits_full_header_raw_label.setObjectName("infoValue")
        self.fits_full_header_raw_label.setVisible(False)
        self._info_values["fits_full_header"] = self.fits_full_header_raw_label

        self.fits_full_header_container.setVisible(False)
        layout.addWidget(self.fits_full_header_container)
        return card

    def _on_fits_full_header_toggled(self, checked: bool) -> None:
        icon_name = "chevron-down" if checked else "chevron-right"
        self.fits_full_header_toggle.setIcon(
            create_themed_vector_icon(icon_name, night_vision=self._is_night_vision, size=14)
        )
        count_suffix = f" ({self._full_fits_card_count})" if self._full_fits_card_count > 0 else ""
        self.fits_full_header_toggle.setText(f"Header FITS Lengkap{count_suffix}")
        self.fits_full_header_container.setVisible(checked)

    def _build_processing_card(self) -> AccordionSection:
        """Membangun kartu 'B. AUTOMATED IMAGE PROCESSING' sebagai AccordionSection dengan kontrol utama dan nested accordions."""
        card = AccordionSection("B. AUTOMATED IMAGE PROCESSING")
        card.setObjectName("accordionSection")
        self.header_processing = card.title_label
        layout = card.content_layout
        layout.setSpacing(8)

        # A. Profile selector (disembunyikan dari UI; aplikasi berjalan di mode Standar Basic tunggal)
        self.profile_combo = QComboBox()
        self.profile_combo.addItem(
            "Basic — Standar HILALONE (Cepat & Ilmiah)", ProcessingProfile.BASIC.value
        )
        self.profile_combo.setCurrentIndex(0)
        self.profile_combo.setEnabled(False)
        self.profile_combo.setVisible(False)
        self.profile_combo.currentIndexChanged.connect(self._on_profile_combo_changed)

        self.profile_summary_label = QLabel("")
        self.profile_summary_label.setObjectName("infoKey")
        self.profile_summary_label.setWordWrap(True)
        self.profile_summary_label.setVisible(False)

        # Flat Calibration (Opsional)
        flat_check_row = QHBoxLayout()
        flat_check_row.setSpacing(6)
        self.flat_checkbox = QCheckBox("Apply Flat Calibration (Opsional)")
        self.flat_checkbox.setChecked(False)
        self.flat_checkbox.toggled.connect(self._on_flat_checkbox_toggled)
        self.btn_flat_info = QToolButton()
        self.btn_flat_info.setObjectName("flatInfoButton")
        self.btn_flat_info.setIcon(
            create_themed_vector_icon("info", night_vision=self._is_night_vision, is_info=True, size=14)
        )
        self.btn_flat_info.setIconSize(QSize(14, 14))
        self.btn_flat_info.setToolTip("Informasi & Pedoman Ilmiah Kalibrasi Flat-Field HILALONE")
        self.btn_flat_info.setFixedSize(22, 22)
        self.btn_flat_info.clicked.connect(self.show_flat_info_dialog)
        flat_check_row.addWidget(self.flat_checkbox)
        flat_check_row.addWidget(self.btn_flat_info)
        flat_check_row.addStretch(1)
        layout.addLayout(flat_check_row)

        # Tombol Utama: Mulai Pemrosesan Otomatis & Cancel
        auto_action_row = QHBoxLayout()
        auto_action_row.setSpacing(8)
        self.start_auto_process_button = QPushButton("Mulai Pemrosesan Otomatis")
        self.start_auto_process_button.setObjectName("startAutoProcessButton")
        self.start_auto_process_button.setIcon(
            create_themed_vector_icon("play", night_vision=self._is_night_vision, size=16)
        )
        self.start_auto_process_button.setIconSize(QSize(16, 16))
        self.start_auto_process_button.setEnabled(False)
        self.start_auto_process_button.clicked.connect(self._on_start_auto_process_clicked)

        self.cancel_pipeline_button = QPushButton("Cancel")
        self.cancel_pipeline_button.setObjectName("secondaryButton")
        self.cancel_pipeline_button.setEnabled(False)
        self.cancel_pipeline_button.clicked.connect(self.cancel_automated_pipeline)

        auto_action_row.addWidget(self.start_auto_process_button, 1)
        auto_action_row.addWidget(self.cancel_pipeline_button, 0)
        layout.addLayout(auto_action_row)

        # Tombol Khusus Stacking Saja (disembunyikan dari UI visual; alur terintegrasi lewat Mulai Pemrosesan Otomatis)
        self.start_stacking_button = QPushButton("Mulai Stacking (Hanya Stacking)")
        self.start_stacking_button.setObjectName("startStackingButton")
        self.start_stacking_button.setEnabled(False)
        self.start_stacking_button.setVisible(False)
        self.start_stacking_button.clicked.connect(self._on_start_stacking_clicked)

        self.cancel_stacking_button = QPushButton("Cancel Stacking")
        self.cancel_stacking_button.setObjectName("secondaryButton")
        self.cancel_stacking_button.setEnabled(False)
        self.cancel_stacking_button.setVisible(False)
        self.cancel_stacking_button.clicked.connect(self.cancel_stacking)

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

        # =====================================================================
        # NESTED ACCORDION GROUP (Automated Image Processing Sub-sections)
        # =====================================================================
        self.nested_accordion_group = AccordionGroup(exclusive=True)

        # 1. Nested: Pengaturan Lanjutan (Advanced Settings)
        self.acc_nested_adv_settings = AccordionSection("Pengaturan Lanjutan (Advanced Settings)", is_nested=True)
        self.adv_settings_toggle = self.acc_nested_adv_settings.header_button

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
        self.adv_bg_method_combo.setCurrentIndex(0)
        self.adv_bg_method_combo.currentIndexChanged.connect(lambda: self._update_processing_accordion_summary())
        bg_meth_row.addWidget(bg_meth_lbl)
        bg_meth_row.addWidget(self.adv_bg_method_combo, 1)
        adv_layout.addLayout(bg_meth_row)

        # 2. Image Enhancement Settings
        enh_set_lbl = QLabel("2. Image Enhancement (CLAHE)")
        enh_set_lbl.setObjectName("subSectionHeader")
        adv_layout.addWidget(enh_set_lbl)

        self.adv_clahe_enable_checkbox = QCheckBox("Aktifkan CLAHE")
        self.adv_clahe_enable_checkbox.setChecked(True)
        self.adv_clahe_enable_checkbox.toggled.connect(lambda: self._update_processing_accordion_summary())
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
        self.adv_clahe_clip_combo.setCurrentIndex(0)
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
        self.adv_stretch_combo.setCurrentIndex(0)
        self.adv_stretch_combo.currentIndexChanged.connect(lambda: self._update_processing_accordion_summary())
        hist_meth_row.addWidget(hist_meth_lbl)
        hist_meth_row.addWidget(self.adv_stretch_combo, 1)
        adv_layout.addLayout(hist_meth_row)

        self.adv_settings_container.setVisible(True)
        self.acc_nested_adv_settings.content_layout.addWidget(self.adv_settings_container)
        self.nested_accordion_group.add_section(self.acc_nested_adv_settings)
        layout.addWidget(self.acc_nested_adv_settings)

        # 2. Nested: Kalibrasi Flat-Field
        self.acc_nested_flat_calib = AccordionSection("Kalibrasi Flat-Field", is_nested=True)
        flat_calib_box = QFrame()
        flat_calib_box.setObjectName("fullHeaderBox")
        flat_calib_layout = QVBoxLayout(flat_calib_box)
        flat_calib_layout.setContentsMargins(8, 8, 8, 8)
        flat_calib_layout.setSpacing(6)

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
        self.flat_input_type_combo.currentIndexChanged.connect(lambda: self._update_processing_accordion_summary())
        flat_type_row.addWidget(flat_type_lbl)
        flat_type_row.addWidget(self.flat_input_type_combo, 1)
        flat_calib_layout.addLayout(flat_type_row)

        flat_btn_row = QHBoxLayout()
        flat_btn_row.setSpacing(6)
        self.select_flat_button = QPushButton("Select Master Flat...")
        self.select_flat_button.setObjectName("secondaryButton")
        self.select_flat_button.setEnabled(False)
        self.select_flat_button.clicked.connect(self.select_master_flat_dialog)

        # Fitur kalibrasi flat mandiri disembunyikan; kalibrasi terintegrasi di 'Mulai Pemrosesan Otomatis'
        self.start_calibration_button = QPushButton("Start Calibration")
        self.start_calibration_button.setObjectName("secondaryButton")
        self.start_calibration_button.setEnabled(False)
        self.start_calibration_button.setVisible(False)
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
        flat_btn_row.addWidget(self.preview_flat_button, 0)
        flat_btn_row.addWidget(self.clear_flat_button, 0)
        flat_calib_layout.addLayout(flat_btn_row)

        self.flat_file_label = QLabel("Master Flat: Tidak digunakan")
        self.flat_file_label.setObjectName("infoKey")
        self.flat_file_label.setWordWrap(True)
        flat_calib_layout.addWidget(self.flat_file_label)

        self.acc_nested_flat_calib.content_layout.addWidget(flat_calib_box)
        self.nested_accordion_group.add_section(self.acc_nested_flat_calib)
        layout.addWidget(self.acc_nested_flat_calib)

        # 3. Nested: Informasi Master Flat
        self.acc_nested_flat_info = AccordionSection("Informasi Master Flat", is_nested=True)
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
        self.flat_details_container.setVisible(True)
        self.acc_nested_flat_info.content_layout.addWidget(self.flat_details_container)
        self.nested_accordion_group.add_section(self.acc_nested_flat_info)
        layout.addWidget(self.acc_nested_flat_info)

        # 4. Nested: Tampilan Pratinjau (Preview Controls)
        self.acc_nested_preview = AccordionSection("Tampilan Pratinjau", is_nested=True)
        self.preview_controls_box = QFrame()
        self.preview_controls_box.setObjectName("fullHeaderBox")
        prev_ctrl_layout = QVBoxLayout(self.preview_controls_box)
        prev_ctrl_layout.setContentsMargins(8, 8, 8, 8)
        prev_ctrl_layout.setSpacing(6)

        prev_ctrl_title = QLabel("TAMPILAN PRATINJAU")
        prev_ctrl_title.setObjectName("subSectionHeader")
        prev_ctrl_layout.addWidget(prev_ctrl_title)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        prev_mode_lbl = QLabel("Mode:")
        prev_mode_lbl.setObjectName("infoKey")
        prev_mode_lbl.setFixedWidth(44)
        self.preview_mode_combo = QComboBox()
        self.preview_mode_combo.addItem("Final Display (Stretch)", PreviewMode.FINAL_DISPLAY.value)
        self.preview_mode_combo.addItem("Enhanced (CLAHE)", PreviewMode.ENHANCED.value)
        self.preview_mode_combo.addItem("Background Corrected (Linear)", PreviewMode.BACKGROUND_CORRECTED.value)
        self.preview_mode_combo.addItem("Background Model", PreviewMode.BACKGROUND_MODEL.value)
        self.preview_mode_combo.addItem("Original (Sebelum Proses)", PreviewMode.ORIGINAL.value)
        self.preview_mode_combo.currentIndexChanged.connect(self._on_preview_mode_changed)

        mode_row.addWidget(prev_mode_lbl)
        mode_row.addWidget(self.preview_mode_combo, 1)
        prev_ctrl_layout.addLayout(mode_row)

        self.toggle_before_after_button = QPushButton("Before / After")
        self.toggle_before_after_button.setObjectName("toggleBeforeAfterButton")
        self.toggle_before_after_button.setIcon(
            create_themed_vector_icon("eye", night_vision=self._is_night_vision, size=15)
        )
        self.toggle_before_after_button.setIconSize(QSize(15, 15))
        self.toggle_before_after_button.setCheckable(True)
        self.toggle_before_after_button.setMinimumHeight(28)
        self.toggle_before_after_button.setToolTip("Bandingkan tampilan hasil pemrosesan dengan citra asli sebelum proses")
        self.toggle_before_after_button.clicked.connect(self._on_toggle_before_after_clicked)
        prev_ctrl_layout.addWidget(self.toggle_before_after_button)

        self.preview_controls_box.setVisible(True)
        self.acc_nested_preview.content_layout.addWidget(self.preview_controls_box)
        self.nested_accordion_group.add_section(self.acc_nested_preview)
        layout.addWidget(self.acc_nested_preview)

        # 5. Nested: Histogram Sebelum & Sesudah (disembunyikan dari UI; analisis histogram lengkap tersedia di jendela Histogram)
        self.acc_nested_histogram = AccordionSection("Histogram Sebelum & Sesudah", is_nested=True)
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
        self.acc_nested_histogram.content_layout.addWidget(self.histogram_container)
        self.acc_nested_histogram.setVisible(False)

        # 6. Nested: Hasil Pemrosesan
        self.acc_nested_results = AccordionSection("Hasil Pemrosesan", is_nested=True)
        self.stacking_result_container = QFrame()
        self.stacking_result_container.setObjectName("fullHeaderBox")
        res_layout = QVBoxLayout(self.stacking_result_container)
        res_layout.setContentsMargins(8, 8, 8, 8)
        res_layout.setSpacing(6)

        # Informasi status data sebelum proses
        pre_title = QLabel("STATUS DATA & METODE")
        pre_title.setObjectName("subSectionHeader")
        res_layout.addWidget(pre_title)

        pre_grid = QGridLayout()
        self._populate_key_value_grid(
            pre_grid,
            _PROC_INFO_ROWS,
            key_min_width=112,
            target_keys=self._proc_keys,
            target_values=self._proc_values,
        )
        res_layout.addLayout(pre_grid)

        res_title = QLabel("HASIL AKHIR PEMROSESAN")
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

        self.stacking_result_container.setVisible(True)
        self.acc_nested_results.content_layout.addWidget(self.stacking_result_container)
        self.nested_accordion_group.add_section(self.acc_nested_results)
        layout.addWidget(self.acc_nested_results)

        # Default state: semua nested accordion tertutup (Persyaratan No. 10)
        self.nested_accordion_group.collapse_all()

        # Inisialisasi ringkasan awal
        self._update_processing_accordion_summary()
        return card

    def _build_info_panel(self) -> QFrame:
        self.info_panel = QFrame()
        self.info_panel.setObjectName("infoPanel")
        self.info_panel.setMinimumWidth(340)
        self.info_panel.setMaximumWidth(440)
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
        content_layout.setSpacing(6)

        # 5 Bagian Utama Accordion
        self.section_input_sequence, self.header_input_sequence = self._create_section_card(
            "A. INPUT & SEQUENCE", _SECTION_A_ROWS
        )
        self.section_processing = self._build_processing_card()
        self.section_image_info, self.header_image_info = self._create_section_card(
            "C. IMAGE INFORMATION", _SECTION_B_ROWS
        )
        self.section_sensor_info, self.header_sensor_info = self._create_section_card(
            "D. SENSOR INFORMATION", _SECTION_C_ROWS
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

        # Accordion Utama Eksklusif: membuka satu bagian utama otomatis menutup yang lain
        self.main_accordion_group = AccordionGroup(exclusive=True)
        self.main_accordion_group.add_section(self.section_input_sequence)
        self.main_accordion_group.add_section(self.section_processing)
        self.main_accordion_group.add_section(self.section_image_info)
        self.main_accordion_group.add_section(self.section_sensor_info)
        self.main_accordion_group.add_section(self.section_camera_metadata)
        self.main_accordion_group.add_section(self.section_fits_info)
        self.main_accordion_group.add_section(self.section_video_info)
        self.main_accordion_group.add_section(self.section_ser_info)

        # Default State (Persyaratan No. 10):
        # - INPUT & SEQUENCE: Collapsed
        # - AUTOMATED IMAGE PROCESSING: Expanded
        # - IMAGE INFORMATION: Collapsed
        # - SENSOR INFORMATION: Collapsed
        # - Format metadata khusus: Collapsed & tersembunyi sampai jenis berkas dimuat
        self.section_input_sequence.set_expanded(False)
        self.section_processing.set_expanded(True)
        self.section_image_info.set_expanded(False)
        self.section_sensor_info.set_expanded(False)
        self.section_camera_metadata.set_expanded(False)
        self.section_camera_metadata.setVisible(False)
        self.section_fits_info.set_expanded(False)
        self.section_fits_info.setVisible(False)
        self.section_video_info.set_expanded(False)
        self.section_video_info.setVisible(False)
        self.section_ser_info.set_expanded(False)
        self.section_ser_info.setVisible(False)

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

    def _update_processing_accordion_summary(self) -> None:
        """Memperbarui teks ringkasan dinamis pada header Accordion Processing dan sub-kelompok nested-nya."""
        if not hasattr(self, "section_processing"):
            return
        prof_name = self.profile_combo.currentText().split("—")[0].strip()
        flat_str = "Flat On" if self.flat_checkbox.isChecked() else "No Flat"
        if self._last_pipeline_result is not None:
            status_str = "Selesai"
        elif self._is_pipeline_running() or self._is_stacking_running():
            status_str = "Memproses..."
        else:
            status_str = "Ready"
        self.section_processing.set_summary(f"{prof_name} | {flat_str} | {status_str}")

        if hasattr(self, "acc_nested_adv_settings"):
            bg_txt = self.adv_bg_method_combo.currentText()
            if "Polinomial Derajat 1" in bg_txt:
                bg_short = "Poly 1"
            elif "Polinomial Derajat 2" in bg_txt:
                bg_short = "Poly 2"
            elif "Thin Plate" in bg_txt:
                bg_short = "TPS RBF"
            else:
                bg_short = "Auto RBF"
            clahe_short = "CLAHE On" if self.adv_clahe_enable_checkbox.isChecked() else "CLAHE Off"
            self.acc_nested_adv_settings.set_summary(f"{bg_short} | {clahe_short}")

        if hasattr(self, "acc_nested_flat_calib"):
            if self.flat_checkbox.isChecked():
                flat_type_txt = self.flat_input_type_combo.currentText().split("(")[0].strip()
                if len(flat_type_txt) > 16:
                    flat_type_txt = flat_type_txt[:14] + ".."
                self.acc_nested_flat_calib.set_summary(flat_type_txt)
            else:
                self.acc_nested_flat_calib.set_summary("Nonaktif")

        if hasattr(self, "acc_nested_preview"):
            mode_txt = self.preview_mode_combo.currentText().split("(")[0].strip()
            self.acc_nested_preview.set_summary(mode_txt)

        if hasattr(self, "acc_nested_histogram"):
            if self._last_pipeline_result is not None and self._last_pipeline_result.histogram_result.histogram_chart_preview is not None:
                self.acc_nested_histogram.set_summary("Grafik Terkini")
            else:
                self.acc_nested_histogram.set_summary("Belum ada grafik")

        if hasattr(self, "acc_nested_results"):
            if self._last_pipeline_result is not None:
                self.acc_nested_results.set_summary(f"Selesai ({self._last_pipeline_result.profile.value})")
            elif self._last_stacking_result is not None:
                self.acc_nested_results.set_summary(f"Selesai ({self._last_stacking_result.stacked_frame_count} Frame)")
            else:
                self.acc_nested_results.set_summary("Belum diproses")

    def _set_row_visible(self, key: str, visible: bool) -> None:
        if key == "fits_full_header":
            return
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
        t0 = time.perf_counter()
        try:
            report = self.sequence_manager.open_video_file(path)
        except ImageReadError as err:
            self._show_error(str(err))
            return False
        return self._finalize_sequence_open(report.warnings, elapsed_sec=time.perf_counter() - t0)

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
        t0 = time.perf_counter()
        try:
            report = self.sequence_manager.open_ser_file(
                path, endianness_policy=endianness_policy
            )
        except ImageReadError as err:
            self._show_error(str(err))
            return False
        return self._finalize_sequence_open(report.warnings, elapsed_sec=time.perf_counter() - t0)

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
        t0 = time.perf_counter()
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
        self._current_info = loaded.info
        self._refresh_sequence_controls()
        self._refresh_processing_controls()
        entry = self.sequence_manager.entries[0]
        self._active_original_qimage = loaded.preview.copy()
        self._original_unprocessed_qimage = loaded.preview.copy()
        self._on_the_fly_previews = {}
        self.viewer.set_image(loaded.preview, loaded.scientific_data)
        if self.curves_window is not None and self.curves_window.isVisible():
            self.curves_window.set_source_data(loaded.scientific_data, loaded.preview, loaded.info.file_name)
        if self.info_dialog is not None and self.info_dialog.isVisible():
            self.open_image_information_dialog()
        self._show_info(loaded.info, entry)
        self.close_button.setEnabled(True)

        # Sinkronisasi Panel B (Frame List) & Panel C (Image Info)
        if hasattr(self, "panel_b"):
            self.panel_b.populate_sequence(self.sequence_manager.entries)
            self.panel_b.set_active_index(0)
        if hasattr(self, "panel_c"):
            self.panel_c.update_info(entry)

        # Logging terstruktur & update histogram jika aktif
        dt = time.perf_counter() - t0
        self.log_manager.info(
            "INPUT",
            "Single Image Dibuka",
            f"{loaded.info.file_name} ({loaded.info.width} × {loaded.info.height} px, {loaded.info.channels or 1} kanal) | Total waktu: {dt:.2f}s",
        )
        if self.histogram_window is not None and self.histogram_window.isVisible():
            self.histogram_window.set_image_data(loaded.scientific_data, loaded.info.file_name)

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
        t0 = time.perf_counter()
        try:
            report = self.sequence_manager.open_folder(folder_path, sort_by=sort_by)
        except ImageReadError as err:
            self._show_error(str(err))
            return False
        return self._finalize_sequence_open(report.warnings, elapsed_sec=time.perf_counter() - t0)

    def load_sequence_paths(
        self,
        paths: Iterable[str | Path],
        sort_by: str = "natural",
    ) -> bool:
        """Memuat banyak berkas gambar sekaligus ke dalam SequenceManager."""
        t0 = time.perf_counter()
        try:
            report = self.sequence_manager.open_files(paths, sort_by=sort_by)
        except ImageReadError as err:
            self._show_error(str(err))
            return False
        return self._finalize_sequence_open(report.warnings, elapsed_sec=time.perf_counter() - t0)

    def _finalize_sequence_open(self, warnings: tuple[str, ...], elapsed_sec: float = 0.0) -> bool:
        self._last_stacking_result = None
        self._refresh_sequence_controls()
        self._refresh_processing_controls()
        self.close_button.setEnabled(self.sequence_manager.frame_count > 0)

        target_idx = self.sequence_manager.compatibility_report.reference_frame_index
        if target_idx is None:
            target_idx = 0

        # Sinkronisasi Panel B (Frame List)
        if hasattr(self, "panel_b"):
            self.panel_b.populate_sequence(self.sequence_manager.entries)
            self.panel_b.set_active_index(target_idx)

        # Logging terstruktur
        mode_str = self._format_mode_text()
        self.log_manager.info(
            "INPUT",
            "Sequence Berhasil Dimuat",
            f"Mode: {mode_str} | Total: {self.sequence_manager.frame_count} frame | "
            f"Kompatibel: {self.sequence_manager.compatibility_report.compatible_count} | Total waktu: {elapsed_sec:.2f}s",
        )

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
        self._current_info = loaded.info
        self._active_original_qimage = loaded.preview.copy()
        self._original_unprocessed_qimage = loaded.preview.copy()
        self._on_the_fly_previews = {}
        self.viewer.set_image(loaded.preview, loaded.scientific_data)
        if self.curves_window is not None and self.curves_window.isVisible():
            self.curves_window.set_source_data(loaded.scientific_data, loaded.preview, loaded.info.file_name)
        if self.info_dialog is not None and self.info_dialog.isVisible():
            self.open_image_information_dialog()
        self._show_info(loaded.info, updated_entry)

        # Sinkronisasi Panel B & C
        if hasattr(self, "panel_b"):
            self.panel_b.set_active_index(index)
        if hasattr(self, "panel_c"):
            self.panel_c.update_info(updated_entry)

        # Update histogram jika jendela histogram sedang terbuka
        if self.histogram_window is not None and self.histogram_window.isVisible():
            self.histogram_window.set_image_data(loaded.scientific_data, loaded.info.file_name)

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
        t0 = time.perf_counter()
        self.sequence_manager.clear()
        self.viewer.clear_image()
        self._clear_full_fits_header_grid()
        if "fits_metadata" in self._info_keys:
            self._info_keys["fits_metadata"].setText(format_metadata_label(None))
        self.header_camera_metadata.setText("Metadata RAW")
        self.header_fits_info.setText("Informasi FITS")
        self.fits_full_header_toggle.setChecked(False)
        self.fits_full_header_toggle.setIcon(
            create_themed_vector_icon("chevron-right", night_vision=self._is_night_vision, size=14)
        )
        self.fits_full_header_toggle.setText("Header FITS Lengkap")
        self.fits_full_header_container.setVisible(False)
        for key, label in self._info_values.items():
            label.setText(EMPTY_VALUE)
            self._set_row_visible(key, key not in _MULTI_ONLY_KEYS)
        self.section_camera_metadata.setVisible(False)
        self.section_fits_info.setVisible(False)
        self.section_video_info.setVisible(False)
        self.section_ser_info.setVisible(False)
        if hasattr(self, "section_input_sequence"):
            self.section_input_sequence.set_summary("")
            self.section_input_sequence.set_expanded(False)
        if hasattr(self, "section_image_info"):
            self.section_image_info.set_summary("")
            self.section_image_info.set_expanded(False)
        if hasattr(self, "section_sensor_info"):
            self.section_sensor_info.set_summary("")
            self.section_sensor_info.set_expanded(False)
        if hasattr(self, "section_video_info"):
            self.section_video_info.set_summary("")
            self.section_video_info.set_expanded(False)
        if hasattr(self, "section_ser_info"):
            self.section_ser_info.set_summary("")
            self.section_ser_info.set_expanded(False)
        if hasattr(self, "section_fits_info"):
            self.section_fits_info.set_summary("")
            self.section_fits_info.set_expanded(False)
        if hasattr(self, "section_camera_metadata"):
            self.section_camera_metadata.set_summary("")
            self.section_camera_metadata.set_expanded(False)
        if hasattr(self, "section_processing"):
            self.section_processing.set_expanded(True)
            self._update_processing_accordion_summary()
        if hasattr(self, "nested_accordion_group"):
            self.nested_accordion_group.collapse_all()
        self._last_pipeline_result = None
        self._last_stacking_result = None
        self._current_protected_roi = None
        self.viewer.set_roi_rect(None)
        self.viewer.roi_selection_enabled = False
        if hasattr(self, "roi_select_button"):
            self.roi_select_button.setChecked(False)
        if hasattr(self, "roi_clear_button"):
            self.roi_clear_button.setEnabled(False)
        if hasattr(self, "roi_status_label"):
            self.roi_status_label.setText("ROI: Tidak ada (seluruh citra disampel)")
        self.preview_controls_box.setVisible(True)
        self.histogram_container.setVisible(False)
        self.histogram_chart_label.clear()
        self.toggle_before_after_button.setChecked(False)
        self.toggle_before_after_button.setText("Before / After")
        self._is_showing_before = False
        self._active_original_qimage = None
        self._original_unprocessed_qimage = None
        self._on_the_fly_previews = {}
        if self.curves_window is not None and self.curves_window.isVisible():
            self.curves_window.set_source_data(None, None, "Tidak ada gambar")
        self._refresh_processing_controls()
        self._refresh_sequence_controls()
        self._refresh_processing_controls()
        self.close_button.setEnabled(False)
        self._current_file_name = ""
        self._current_info = None

        # Bersihkan Panel B & Panel C
        if hasattr(self, "panel_b"):
            self.panel_b.clear()
        if hasattr(self, "panel_c"):
            self.panel_c.update_info(None)

        if self.info_dialog is not None and self.info_dialog.isVisible():
            self.info_dialog.populate_metadata([], "Tidak ada berkas aktif")

        # Reset Histogram jika aktif
        if self.histogram_window is not None and self.histogram_window.isVisible():
            self.histogram_window.set_image_data(None, "Tidak ada gambar")

        dt = time.perf_counter() - t0
        self.log_manager.info("INPUT", "Citra Ditutup", f"Ruang kerja telah dibersihkan | Total waktu: {dt:.2f}s")

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
            if hasattr(self, "section_input_sequence"):
                self.section_input_sequence.set_summary("1 Frame | Single Image")
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
        if hasattr(self, "section_input_sequence"):
            status_summary = "Ready" if rep.is_ready_for_stacking else "Not Ready"
            self.section_input_sequence.set_summary(
                f"{rep.total_files} Frames | {rep.compatible_count} Kompatibel | {status_summary}"
            )

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
        if hasattr(self, "section_image_info"):
            fname = info.file_name
            if len(fname) > 18:
                fname = fname[:15] + "..."
            self.section_image_info.set_summary(f"{fname} | {info.width} × {info.height} px")

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
        if hasattr(self, "section_sensor_info"):
            ch_str = "Mono" if info.channels == 1 else "RGB"
            dtype_str = info.dtype_str or "uint8"
            depth_str = f"{info.original_bit_depth}-bit" if info.original_bit_depth else ""
            summary_parts = [ch_str, dtype_str]
            if depth_str:
                summary_parts.append(depth_str)
            self.section_sensor_info.set_summary(" | ".join(summary_parts))

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

            # Format EXPTIME / EXPOSURE ke tampilan '0.00 s' agar bersih dan nyaman dibaca pengguna
            disp_val = val_str
            if kw.upper() in ("EXPTIME", "EXPOSURE") and val_str:
                try:
                    sec_val = float(val_str)
                    if math.isfinite(sec_val) and sec_val >= 0.0:
                        disp_val = f"{sec_val:.2f} s"
                except (ValueError, TypeError):
                    disp_val = val_str

            if disp_val and comment_str:
                rhs = f"{disp_val}  / {comment_str}"
            elif disp_val:
                rhs = disp_val
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

            # Raw line asli tetap mempertahankan nilai presisi penuh berkas FITS asli untuk kebutuhan data/inspeksi
            if val_str and comment_str:
                raw_rhs = f"{val_str}  / {comment_str}"
            elif val_str:
                raw_rhs = val_str
            else:
                raw_rhs = f"/ {comment_str}" if comment_str else ""
            raw_lines.append(f"{kw} = {raw_rhs}")

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
            if hasattr(self, "section_camera_metadata"):
                cam = d.get("CAMERA") or "RAW"
                if len(cam) > 18:
                    cam = cam[:15] + "..."
                iso = d.get("ISO") or ""
                summary_str = f"{cam} | ISO {iso}" if iso and iso != RAW_UNAVAILABLE else cam
                self.section_camera_metadata.set_summary(summary_str)
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
            if hasattr(self, "section_video_info"):
                cnt = dv.get("CONTAINER", "VIDEO")
                fps = dv.get("FRAME_RATE", "")
                dur = dv.get("DURATION", "")
                parts = [cnt]
                if fps and fps != VIDEO_UNAVAILABLE:
                    parts.append(fps)
                if dur and dur != VIDEO_UNAVAILABLE:
                    parts.append(dur)
                self.section_video_info.set_summary(" | ".join(parts[:3]))
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
            if hasattr(self, "section_ser_info"):
                fc = ds.get("FRAME_COUNT", "")
                depth = ds.get("PIXEL_DEPTH", "")
                parts = ["SER"]
                if fc:
                    parts.append(f"{fc} Frames")
                if depth:
                    parts.append(depth)
                self.section_ser_info.set_summary(" | ".join(parts))
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
            if hasattr(self, "section_fits_info"):
                bitpix_val = _req(d_fits["BITPIX"])
                dim_str = f"{d_fits.get('NAXIS1', '')} × {d_fits.get('NAXIS2', '')}"
                parts = ["FITS"]
                if bitpix_val and bitpix_val != FITS_UNAVAILABLE:
                    parts.append(f"{bitpix_val}-bit")
                if dim_str and dim_str != " × ":
                    parts.append(dim_str)
                self.section_fits_info.set_summary(" | ".join(parts))
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
        if hasattr(self, "section_image_info"):
            self.section_image_info.set_summary(f"{entry.file_name} | Gagal Dibaca")
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
        """Mengembalikan profil stacking yang dipilih pada dropdown (default: Basic)."""
        raw_val = self.profile_combo.currentData()
        if isinstance(raw_val, StackingProfile):
            return raw_val
        if isinstance(raw_val, str):
            for p in StackingProfile:
                if p.value == raw_val:
                    return p
        return StackingProfile.BASIC

    def set_stacking_profile(self, profile: StackingProfile | str) -> None:
        """Mengatur pilihan profil stacking pada dropdown."""
        target = profile.value if isinstance(profile, StackingProfile) else str(profile).strip().upper()
        for idx in range(self.profile_combo.count()):
            if self.profile_combo.itemData(idx) == target:
                self.profile_combo.setCurrentIndex(idx)
                return
        self.profile_combo.addItem(target, target)
        self.profile_combo.setCurrentIndex(self.profile_combo.count() - 1)

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

        t0 = time.perf_counter()
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
            dt_flat = time.perf_counter() - t0

            self.stacking_progress_bar.setValue(100)
            self.stacking_status_label.setText(
                f"Kalibrasi Flat selesai: {len(calibrated_frames)} frame berhasil dikalibrasi "
                f"({report.normalization_method})."
            )
            self.log_manager.success(
                "FLAT",
                "Kalibrasi Flat Selesai",
                f"{len(calibrated_frames)} frame dikalibrasi ({report.normalization_method}) | Total waktu: {dt_flat:.2f}s",
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
            if hasattr(self, "acc_nested_flat_info"):
                self.acc_nested_flat_info.set_summary("Tidak digunakan")
                self.acc_nested_flat_info.set_expanded(False)
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
        if hasattr(self, "acc_nested_flat_info"):
            badge = "KOMPATIBEL" if (compat and compat.is_compatible) else "INKOMPATIBEL"
            self.acc_nested_flat_info.set_summary(f"{lf.flat_format} | {badge}")

    def _is_stacking_running(self) -> bool:
        return self._stacking_worker is not None and self._stacking_worker.isRunning()

    def _is_pipeline_running(self) -> bool:
        return self._pipeline_worker is not None and self._pipeline_worker.isRunning()

    def _on_adv_settings_toggled(self, checked: bool) -> None:
        if hasattr(self, "acc_nested_adv_settings"):
            self.acc_nested_adv_settings.set_expanded(checked)

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
        if hasattr(self, "roi_status_label"):
            self.roi_status_label.setText(f"ROI: x={x}, y={y}, {w}×{h} px (Terlindungi)")
        if hasattr(self, "roi_clear_button"):
            self.roi_clear_button.setEnabled(True)
        if hasattr(self, "roi_select_button"):
            self.roi_select_button.setChecked(False)
        self.viewer.roi_selection_enabled = False
        self.statusBar().showMessage(f"Wilayah proteksi ditetapkan: x={x}, y={y}, {w}×{h} px.")

    def clear_protected_roi(self) -> None:
        self._current_protected_roi = None
        self.viewer.set_roi_rect(None)
        self.viewer.roi_selection_enabled = False
        if hasattr(self, "roi_select_button"):
            self.roi_select_button.setChecked(False)
        if hasattr(self, "roi_clear_button"):
            self.roi_clear_button.setEnabled(False)
        if hasattr(self, "roi_status_label"):
            self.roi_status_label.setText("ROI: Tidak ada (seluruh citra disampel)")
        self.statusBar().showMessage("Wilayah proteksi dihapus.")

    def selected_processing_profile(self) -> ProcessingProfile:
        """Mengembalikan profil pemrosesan otomatis yang dipilih pada dropdown (default: Basic)."""
        raw_val = self.profile_combo.currentData()
        if isinstance(raw_val, ProcessingProfile):
            return raw_val
        if isinstance(raw_val, str):
            for p in ProcessingProfile:
                if p.value == raw_val:
                    return p
        return ProcessingProfile.BASIC

    def set_processing_profile(self, profile: ProcessingProfile | str) -> None:
        """Mengatur pilihan profil pemrosesan pada dropdown."""
        target = profile.value if isinstance(profile, ProcessingProfile) else str(profile).strip().upper()
        for idx in range(self.profile_combo.count()):
            if self.profile_combo.itemData(idx) == target:
                self.profile_combo.setCurrentIndex(idx)
                return
        self.profile_combo.addItem(target, target)
        self.profile_combo.setCurrentIndex(self.profile_combo.count() - 1)

    def _get_or_compute_preview_for_mode(self, mode: PreviewMode) -> Any:
        """Mengambil preview dari pipeline result jika ada, atau menghitung preview on-the-fly."""
        # 1. Jika ada hasil pipeline resmi, gunakan preview yang sudah ada
        if self._last_pipeline_result is not None:
            prev = self._last_pipeline_result.previews.get(mode)
            if prev is not None and not prev.isNull():
                return prev

        # 2. Jika belum ada pipeline result, ambil dari data aktif saat ini
        raw_data = self._get_current_active_scientific_data()
        if raw_data is None:
            return self.viewer.source_qimage()

        if mode == PreviewMode.ORIGINAL:
            if hasattr(self, "_original_unprocessed_qimage") and self._original_unprocessed_qimage is not None:
                return self._original_unprocessed_qimage
            if hasattr(self, "_active_original_qimage") and self._active_original_qimage is not None:
                return self._active_original_qimage
            from hilalone.input_manager.preview_builder import array_to_preview_qimage
            return array_to_preview_qimage(raw_data)

        if not hasattr(self, "_on_the_fly_previews"):
            self._on_the_fly_previews = {}

        if mode in self._on_the_fly_previews:
            return self._on_the_fly_previews[mode]

        prof = self.selected_processing_profile()
        try:
            if mode == PreviewMode.FINAL_DISPLAY:
                from hilalone.processing.histogram_engine import run_histogram_transformation
                res = run_histogram_transformation(raw_data, config=prof)
                self._on_the_fly_previews[mode] = res.display_preview
                return res.display_preview
            elif mode == PreviewMode.ENHANCED:
                from hilalone.processing.enhancement_engine import run_image_enhancement
                res = run_image_enhancement(raw_data, config=prof)
                self._on_the_fly_previews[mode] = res.enhanced_preview
                return res.enhanced_preview
            elif mode == PreviewMode.BACKGROUND_MODEL:
                from hilalone.processing.background_engine import run_background_extraction
                res = run_background_extraction(raw_data, config=prof)
                self._on_the_fly_previews[mode] = res.model_preview
                return res.model_preview
            elif mode == PreviewMode.BACKGROUND_CORRECTED:
                from hilalone.processing.background_engine import run_background_extraction
                res = run_background_extraction(raw_data, config=prof)
                self._on_the_fly_previews[mode] = res.corrected_preview
                return res.corrected_preview
        except Exception as exc:
            if hasattr(self, "log_manager"):
                self.log_manager.warning("PREVIEW", "Kalkulasi Pratinjau", f"Gagal menghitung pratinjau mode {mode.value}: {exc}")

        return self.viewer.source_qimage()

    def _on_preview_mode_changed(self, _index: int) -> None:
        mode_val = self.preview_mode_combo.currentData()
        for m in PreviewMode:
            if m.value == mode_val:
                self._preview_mode = m
                break
        self._update_displayed_preview()
        self._update_processing_accordion_summary()

    def _on_toggle_before_after_clicked(self, checked: bool) -> None:
        self._is_showing_before = checked
        btn_txt = "Sedang Menampilkan: SEBELUM Proses" if checked else "Before / After"
        self.toggle_before_after_button.setText(btn_txt)
        self._update_displayed_preview()

    def _update_displayed_preview(self) -> None:
        if not self.viewer.has_image():
            return

        target_mode = PreviewMode.ORIGINAL if self._is_showing_before else self._preview_mode
        img = self._get_or_compute_preview_for_mode(target_mode)

        if img is not None and not img.isNull():
            sci_target = (
                self._last_pipeline_result.linear_result
                if self._last_pipeline_result is not None and self._last_pipeline_result.linear_result is not None
                else self._get_current_active_scientific_data()
            )
            self.viewer.set_image(img, sci_target, preserve_view=True)
            if hasattr(self, "image_action_toolbar"):
                self._refresh_image_toolbar_state()
            if hasattr(self, "status_view_info"):
                mode_str = "Sebelum Pemrosesan (Original)" if self._is_showing_before else self._preview_mode.value
                self.status_view_info.setText(f"Pratinjau: {mode_str}")
            if self._is_showing_before:
                self.statusBar().showMessage("Menampilkan Pratinjau: Original (Sebelum Pemrosesan)")
            else:
                self.statusBar().showMessage(f"Menampilkan Pratinjau: {self._preview_mode.value}")

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
        self.profile_combo.setEnabled(False)  # Selalu terkunci pada Basic sebagai satu-satunya profil
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
        if hasattr(self, "roi_select_button"):
            self.roi_select_button.setEnabled(enabled and has_any_image)
        if hasattr(self, "roi_clear_button"):
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
        if hasattr(self, "roi_select_button"):
            self.roi_select_button.setEnabled(has_any_image and not is_running)
        if hasattr(self, "roi_clear_button"):
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
            self._update_processing_accordion_summary()
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
            self._update_processing_accordion_summary()
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
        self._update_processing_accordion_summary()

    def _update_result_section(self) -> None:
        """Menampilkan atau menyembunyikan rincian hasil stacking dan pipeline terakhir."""
        pipe_res = self._last_pipeline_result
        stk_res = self._last_stacking_result

        if pipe_res is None and stk_res is None:
            self.stacking_result_container.setVisible(False)
            self.preview_controls_box.setVisible(True)
            self.histogram_container.setVisible(False)
            if hasattr(self, "acc_nested_results"):
                self.acc_nested_results.set_summary("Belum diproses")
            if hasattr(self, "acc_nested_histogram"):
                self.acc_nested_histogram.set_summary("Belum ada grafik")
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
            if hasattr(self, "acc_nested_results"):
                self.acc_nested_results.set_summary(f"Selesai ({pipe_res.profile.value})")
                self.acc_nested_results.set_expanded(True)
            if hasattr(self, "acc_nested_histogram"):
                self.acc_nested_histogram.set_summary("Grafik Terkini")
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
        if hasattr(self, "acc_nested_results"):
            self.acc_nested_results.set_summary(f"Selesai ({res.stacked_frame_count} Frame)")
            self.acc_nested_results.set_expanded(True)
        self.preview_controls_box.setVisible(True)
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

        total_frames = self.sequence_manager.frame_count
        excluded_unselected: set[int] = set()
        if hasattr(self, "panel_b") and total_frames > 0:
            selected_set = set(self.panel_b.get_selected_frame_indices())
            excluded_unselected = set(range(total_frames)) - selected_set
            remaining_selected = total_frames - len(excluded_unselected)
            if remaining_selected < 2:
                self._show_error(
                    f"Hanya {remaining_selected} frame yang dicentang pada daftar frame. "
                    "Minimal 2 frame diperlukan untuk menjalankan stacking."
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
            excluded_frame_indices=excluded_unselected if excluded_unselected else None,
            allow_exclude_incompatible_and_error=allow_exclude_invalid,
            confirm_proceed_with_shift_risk=True,
            wait_for_completion=wait_for_completion,
        )

    def _launch_stacking_worker(
        self,
        *,
        excluded_frame_indices: set[int] | None = None,
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
            excluded_frame_indices=excluded_frame_indices,
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

        self._stacking_start_time = time.perf_counter()
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
            dt_stack = time.perf_counter() - getattr(self, "_stacking_start_time", time.perf_counter())
            self.log_manager.success(
                "STACKING",
                "Stacking Selesai",
                f"{result_obj.stacked_frame_count} frame digabungkan ({prof_str}, {algo_str}) | Total waktu: {dt_stack:.2f}s. Hasil siap disimpan melalui Save Result.",
            )
            if result_obj.preview is not None and not result_obj.preview.isNull():
                self.viewer.set_image(
                    result_obj.preview,
                    result_obj.stacked_scientific_data,
                    preserve_view=True,
                )
            if hasattr(self, "status_view_info"):
                self.status_view_info.setText(f"Mode: Hasil Stacking ({prof_str})")
            if self.histogram_window is not None and self.histogram_window.isVisible():
                self.histogram_window.set_image_data(
                    result_obj.stacked_scientific_data,
                    f"{self._current_file_name or 'Citra'} (Hasil Stacking {prof_str})",
                )
            if hasattr(self, "image_action_toolbar"):
                self._refresh_image_toolbar_state()
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
            self._refresh_processing_controls(preserve_status_label=self._cancel_requested_by_ui)

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
        t0 = time.perf_counter()
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
        dt_save = time.perf_counter() - t0
        self.log_manager.success(
            "OUTPUT",
            "Hasil Stacking Tersimpan",
            f"{saved_path.name} | Jalur: {saved_path} | Total waktu: {dt_save:.2f}s",
        )
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
        excluded_unselected: set[int] = set()
        if mode in (InputMode.MULTI, InputMode.VIDEO, InputMode.SER):
            if hasattr(self, "panel_b") and total > 0:
                selected_set = set(self.panel_b.get_selected_frame_indices())
                excluded_unselected = set(range(total)) - selected_set
                remaining_selected = total - len(excluded_unselected)
                if remaining_selected < 2:
                    self._show_error(
                        f"Hanya {remaining_selected} frame yang dicentang pada daftar frame. "
                        "Minimal 2 frame diperlukan untuk pemrosesan sequence."
                    )
                    return False

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
            excluded_frame_indices=excluded_unselected if excluded_unselected else None,
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

        self._pipeline_start_time = time.perf_counter()
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
            self.toggle_before_after_button.setText("Before / After")
            self._preview_mode = PreviewMode.FINAL_DISPLAY
            self.preview_mode_combo.blockSignals(True)
            self.preview_mode_combo.setCurrentIndex(0)
            self.preview_mode_combo.blockSignals(False)

            # Langsung perbarui tampilan citra di layar dengan hasil akhir (FINAL_DISPLAY)
            final_prev = result_obj.previews.get(PreviewMode.FINAL_DISPLAY)
            sci_target = (
                result_obj.linear_result
                if result_obj.linear_result is not None
                else result_obj.stacked_data
            )
            if final_prev is not None and not final_prev.isNull():
                self.viewer.set_image(final_prev, sci_target, preserve_view=True)
            self._update_displayed_preview()

            # Simpan backup citra sebelum proses untuk fitur Before / After
            orig_prev = result_obj.previews.get(PreviewMode.ORIGINAL)
            if orig_prev is not None and not orig_prev.isNull():
                self._original_unprocessed_qimage = orig_prev.copy()

            if hasattr(self, "status_view_info"):
                self.status_view_info.setText(f"Mode: Hasil Pemrosesan ({result_obj.profile.value})")

            if self.histogram_window is not None and self.histogram_window.isVisible():
                self.histogram_window.set_image_data(
                    sci_target,
                    f"{self._current_file_name or 'Citra'} (Hasil {result_obj.profile.value})",
                )

            elapsed_sec = getattr(result_obj, "total_elapsed_seconds", 0.0)
            if hasattr(result_obj, "stage_records"):
                for stage_rec in result_obj.stage_records:
                    if stage_rec.status.value != "SKIPPED":
                        s_sec = (stage_rec.duration_ms or 0.0) / 1000.0
                        self.log_manager.info(
                            "STAGE",
                            f"{stage_rec.stage.value}",
                            f"{stage_rec.summary} | Waktu: {s_sec:.2f}s",
                        )
            self.log_manager.success(
                "PIPELINE",
                "Pemrosesan Otomatis Selesai",
                f"Profil: {result_obj.profile.value} | Total waktu: {elapsed_sec:.2f}s. Gunakan menu Save Result untuk menyimpan.",
            )
            export_rep = getattr(result_obj, "export_report", None)
            if export_rep is not None and hasattr(export_rep, "generated_files"):
                for out_f in export_rep.generated_files:
                    self.log_manager.info("OUTPUT", f"File Tersimpan ({out_f.stage})", f"{out_f.path} | Waktu: 0.01s")

            if hasattr(self, "image_action_toolbar"):
                self._refresh_image_toolbar_state()

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
                self._refresh_processing_controls(preserve_status_label=self._cancel_requested_by_ui)
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

    # ------------------------------------------------------------------ Help & Update Slots
    def _has_active_processing_worker(self) -> bool:
        """Memeriksa apakah ada pipeline atau stacking worker yang sedang berjalan."""
        return self._is_pipeline_running() or self._is_stacking_running()

    def _log_update_dialog_message(self, level: str, source: str, detail: str) -> None:
        """Meneruskan pesan status dari dialog updater ke LogManager."""
        lvl = (level or "INFO").upper()
        if lvl == "SUCCESS":
            self.log_manager.success("UPDATE", source, detail)
        elif lvl == "WARNING":
            self.log_manager.warning("UPDATE", source, detail)
        elif lvl == "ERROR":
            self.log_manager.error("UPDATE", source, detail)
        else:
            self.log_manager.info("UPDATE", source, detail)

    def open_report_issue_page(self, _checked: bool = False) -> None:
        """Membuka halaman GitHub Issues di browser default tanpa mengirim log otomatis."""
        opened = QDesktopServices.openUrl(QUrl(GITHUB_NEW_ISSUE_URL))
        self.log_manager.info(
            "HELP",
            "Report an Issue",
            f"Membuka formulir laporan masalah GitHub: {GITHUB_NEW_ISSUE_URL}",
        )
        if not opened:
            QMessageBox.information(
                self,
                "Report an Issue",
                f"Silakan buka halaman GitHub Issues melalui browser:\n\n{GITHUB_NEW_ISSUE_URL}",
            )

    def show_about_dialog(self, _checked: bool = False) -> None:
        """Menampilkan dialog khusus About HILALONE sesuai tema aktif."""
        if self.about_dialog is None:
            self.about_dialog = AboutDialog(night_vision=self._is_night_vision, parent=self)
        else:
            self.about_dialog.apply_theme(self._is_night_vision)
        self.about_dialog.show()
        self.about_dialog.raise_()
        self.about_dialog.activateWindow()
        self.log_manager.info("HELP", "About HILALONE Dibuka", f"Versi aplikasi: v{__version__}")

    def _persist_update_preferences(self, config_path: Path | None = None) -> None:
        """Menyimpan preferensi & jadwal automatic update ke berkas konfigurasi bila aktif."""
        effective_cfg = config_path if config_path is not None else self._update_config_path
        if effective_cfg is None and not self._preferences_enabled():
            return
        try:
            save_update_preferences(self._update_prefs, effective_cfg)
        except Exception:
            pass

    def toggle_automatic_update_check(
        self,
        enabled: bool | None = None,
        *,
        config_path: Path | None = None,
    ) -> None:
        """Mengaktifkan atau menonaktifkan pemeriksaan pembaruan otomatis."""
        new_val = (
            not self._update_prefs.auto_update_check_enabled
            if enabled is None
            else bool(enabled)
        )
        self._update_prefs = replace(self._update_prefs, auto_update_check_enabled=new_val)
        if hasattr(self, "act_auto_update_check"):
            self.act_auto_update_check.blockSignals(True)
            self.act_auto_update_check.setChecked(new_val)
            self.act_auto_update_check.blockSignals(False)

        if not new_val:
            self._startup_update_timer.stop()
            self._reminder_update_timer.stop()

        self._persist_update_preferences(config_path)
        state_text = "diaktifkan" if new_val else "dinonaktifkan"
        self.log_manager.info(
            "UPDATE",
            "Automatic Update Check",
            f"Pemeriksaan pembaruan otomatis {state_text}.",
        )

    def _schedule_startup_update_check_if_eligible(self) -> None:
        """Menjadwalkan QTimer 10 detik setelah jendela utama ditampilkan bila memenuhi syarat."""
        if self._startup_timer_scheduled or self._is_closing or self._was_closed:
            return
        self._startup_timer_scheduled = True
        if not bool(self._is_frozen_checker()):
            return
        if not self._update_prefs.auto_update_check_enabled:
            return
        self._startup_update_timer.start(max(0, int(self._startup_update_delay_ms)))

    def showEvent(self, event: Any) -> None:  # noqa: N802
        """Menjadwalkan cek update otomatis sekitar 10 detik setelah tampilan siap."""
        super().showEvent(event)
        self._schedule_startup_update_check_if_eligible()

    def _on_startup_update_timer_timeout(self) -> None:
        """Slot saat timer startup 10 detik berbunyi."""
        self.run_automatic_update_check()

    def _on_reminder_update_timer_timeout(self) -> None:
        """Slot saat pengingat 24 jam ('Later') berakhir."""
        self.run_automatic_update_check()

    def run_automatic_update_check(
        self,
        *,
        check_func: Any = None,
        now: datetime | None = None,
    ) -> bool:
        """Menjalankan pemeriksaan pembaruan otomatis di background bila syarat terpenuhi."""
        if self._is_closing or self._was_closed:
            return False
        if self._update_worker is not None and self._update_worker.isRunning():
            return False

        now_dt = now if now is not None else self._now_provider()
        is_frozen = bool(self._is_frozen_checker())
        if not should_run_automatic_check(self._update_prefs, now=now_dt, is_frozen=is_frozen):
            return False

        self._update_check_is_automatic = True
        chosen_check = check_func if check_func is not None else self._auto_check_func
        self.log_manager.info(
            "UPDATE",
            "Cek Pembaruan Otomatis",
            f"Memeriksa pembaruan rilis stabil di latar belakang (versi lokal: v{__version__})...",
        )
        worker = UpdateWorker(
            mode=UpdateWorkerMode.CHECK_ONLY,
            local_version=__version__,
            check_func=chosen_check,
            parent=self,
        )
        self._update_worker = worker
        worker.update_available.connect(self._on_update_available)
        worker.up_to_date.connect(self._on_update_up_to_date)
        worker.check_failed.connect(self._on_update_check_failed)
        worker.cancelled.connect(self._on_update_check_cancelled)
        worker.finished.connect(self._on_update_worker_finished)
        worker.start()
        return True

    def check_for_updates_interactive(
        self,
        _checked: bool = False,
        *,
        check_func: Any = None,
    ) -> None:
        """Memeriksa pembaruan GitHub Releases secara manual tanpa dibatasi jadwal 24 jam."""
        if self._update_worker is not None and self._update_worker.isRunning():
            if self._update_check_is_automatic:
                self._update_check_is_automatic = False
                if hasattr(self, "act_check_updates"):
                    self.act_check_updates.setEnabled(False)
                    self.act_check_updates.setText("Checking for Updates...")
                self.statusBar().showMessage("Memeriksa pembaruan HILALONE dari GitHub Releases...")
                return
            self.statusBar().showMessage("Pemeriksaan pembaruan sedang berjalan...", 3000)
            return

        self._update_check_is_automatic = False
        if hasattr(self, "act_check_updates"):
            self.act_check_updates.setEnabled(False)
            self.act_check_updates.setText("Checking for Updates...")
        self.statusBar().showMessage("Memeriksa pembaruan HILALONE dari GitHub Releases...")
        self.log_manager.info(
            "UPDATE",
            "Periksa Pembaruan",
            f"Memeriksa rilis stabil terbaru di GitHub Releases (versi saat ini: v{__version__})...",
        )

        worker = UpdateWorker(
            mode=UpdateWorkerMode.CHECK_ONLY,
            local_version=__version__,
            check_func=check_func,
            parent=self,
        )
        self._update_worker = worker
        worker.update_available.connect(self._on_update_available)
        worker.up_to_date.connect(self._on_update_up_to_date)
        worker.check_failed.connect(self._on_update_check_failed)
        worker.cancelled.connect(self._on_update_check_cancelled)
        worker.finished.connect(self._on_update_worker_finished)
        worker.start()

    def _restore_update_check_action(self) -> None:
        if hasattr(self, "act_check_updates"):
            self.act_check_updates.setEnabled(True)
            self.act_check_updates.setText("Check for Updates...")

    def _open_update_dialog(self, result: UpdateCheckResult) -> None:
        """Membuka UpdateDialog standar untuk mengunduh & memasang pembaruan."""
        if self._is_closing or self._was_closed:
            return
        if self.update_dialog is not None:
            self.update_dialog.cancel_active_download()
            self.update_dialog.close()
            self.update_dialog.deleteLater()
            self.update_dialog = None

        self.update_dialog = UpdateDialog(
            result,
            night_vision=self._is_night_vision,
            is_frozen=bool(self._is_frozen_checker()),
            active_processing_checker=self._has_active_processing_worker,
            parent=self,
        )
        self.update_dialog.log_message_requested.connect(self._log_update_dialog_message)
        self.update_dialog.install_close_requested.connect(self._close_for_installer_update)
        self.update_dialog.show()
        self.update_dialog.raise_()
        self.update_dialog.activateWindow()

    def _on_notification_update_now(self, result: UpdateCheckResult) -> None:
        """Handler saat pengguna memilih Update Now pada dialog notifikasi."""
        self.log_manager.info(
            "UPDATE",
            "Update Now Dipilih",
            f"Membuka dialog instalasi untuk {result.release.tag_name if result.release else 'rilis baru'}.",
        )
        self._open_update_dialog(result)

    def _on_notification_later(self, result: UpdateCheckResult) -> None:
        """Handler saat pengguna memilih Later: tunda 24 jam & jadwalkan pengingat ulang."""
        version_tag = (
            result.release.version.normalized
            if result.release is not None
            else result.local_version
        )
        now_dt = self._now_provider()
        self._update_prefs = snooze_update_reminder(
            self._update_prefs,
            version_tag,
            now=now_dt,
            reminder_interval=REMINDER_DELAY_INTERVAL,
        )
        self._persist_update_preferences()

        if (
            not self._is_closing
            and not self._was_closed
            and self._update_prefs.auto_update_check_enabled
            and bool(self._is_frozen_checker())
        ):
            delay_ms = max(1000, int(REMINDER_DELAY_INTERVAL.total_seconds() * 1000))
            self._reminder_update_timer.start(delay_ms)

        self.log_manager.info(
            "UPDATE",
            "Pembaruan Ditunda",
            f"Pengingat pembaruan v{version_tag} ditunda selama 24 jam.",
        )

    def _show_update_notification(self, result: UpdateCheckResult) -> None:
        """Menampilkan dialog notifikasi update tanpa menduplikasi versi yang sedang tampil."""
        if self._is_closing or self._was_closed or result.release is None:
            return
        candidate_ver = result.release.version.normalized

        existing_notif = getattr(self, "update_notification_dialog", None)
        if existing_notif is not None and existing_notif.isVisible():
            existing_rel = existing_notif.check_result.release
            if existing_rel is not None and existing_rel.version.normalized == candidate_ver:
                existing_notif.raise_()
                existing_notif.activateWindow()
                return
            existing_notif.blockSignals(True)
            existing_notif.close()
            existing_notif.deleteLater()
            self.update_notification_dialog = None

        existing_upd = getattr(self, "update_dialog", None)
        if existing_upd is not None and existing_upd.isVisible():
            return

        self._update_prefs = record_notification_shown(self._update_prefs, candidate_ver)
        self._persist_update_preferences()

        notif = UpdateNotificationDialog(
            result,
            night_vision=self._is_night_vision,
            parent=self,
        )
        notif.update_now_requested.connect(self._on_notification_update_now)
        notif.later_requested.connect(self._on_notification_later)
        self.update_notification_dialog = notif
        notif.show()
        notif.raise_()
        notif.activateWindow()

    def _on_update_available(self, result: UpdateCheckResult) -> None:
        if self._is_closing or self._was_closed:
            return

        was_automatic = self._update_check_is_automatic
        if was_automatic:
            now_dt = self._now_provider()
            self._update_prefs = record_check_timestamp(self._update_prefs, now=now_dt)
            self._persist_update_preferences()
            if result.release is None:
                return
            if not should_show_update_notification(
                self._update_prefs,
                result.release.tag_name,
                local_version=__version__,
                draft=result.release.draft,
                prerelease=result.release.prerelease,
                now=now_dt,
            ):
                self.log_manager.info(
                    "UPDATE",
                    "Notifikasi Ditunda",
                    f"Notifikasi pembaruan v{result.release.version.normalized} masih dalam periode tunda 24 jam.",
                )
                return
            self.statusBar().showMessage(result.message, 6000)
            self.log_manager.info("UPDATE", "Pembaruan Tersedia", result.message)
            self._show_update_notification(result)
            return

        self._restore_update_check_action()
        self.statusBar().showMessage(result.message, 6000)
        self.log_manager.info("UPDATE", "Pembaruan Tersedia", result.message)
        self._open_update_dialog(result)

    def _on_update_up_to_date(self, result: UpdateCheckResult) -> None:
        if self._is_closing or self._was_closed:
            return
        if self._update_check_is_automatic:
            self._update_prefs = record_check_timestamp(
                self._update_prefs, now=self._now_provider()
            )
            self._persist_update_preferences()
            self.log_manager.info("UPDATE", "Status Versi (Otomatis)", result.message)
            return

        self._restore_update_check_action()
        self.statusBar().showMessage(result.message, 5000)
        self.log_manager.info("UPDATE", "Status Versi", result.message)
        QMessageBox.information(
            self,
            "Pembaruan HILALONE",
            result.message,
        )

    def _on_update_check_failed(self, err_msg: str) -> None:
        if self._is_closing or self._was_closed:
            return
        if self._update_check_is_automatic:
            self._update_prefs = record_check_timestamp(
                self._update_prefs, now=self._now_provider()
            )
            self._persist_update_preferences()
            logging.warning("Pemeriksaan pembaruan otomatis gagal: %s", err_msg)
            self.log_manager.warning("UPDATE", "Cek Pembaruan Otomatis Gagal", err_msg)
            return

        self._restore_update_check_action()
        self.statusBar().showMessage(f"Pemeriksaan pembaruan gagal: {err_msg}", 6000)
        self.log_manager.warning("UPDATE", "Gagal Memeriksa Pembaruan", err_msg)
        QMessageBox.warning(
            self,
            "Gagal Memeriksa Pembaruan",
            err_msg,
        )

    def _on_update_check_cancelled(self, msg: str) -> None:
        if self._is_closing or self._was_closed:
            return
        if self._update_check_is_automatic:
            return
        self._restore_update_check_action()
        self.statusBar().showMessage(msg, 4000)

    def _on_update_worker_finished(self) -> None:
        worker = self.sender()
        if isinstance(worker, UpdateWorker):
            worker.wait(500)
            if self._update_worker is worker:
                self._update_worker = None
            worker.deleteLater()

    def _close_for_installer_update(self) -> None:
        """Menutup jendela utama secara normal agar installer Inno Setup dapat berjalan."""
        self.close()

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        """Menyimpan preferensi tema dan menghentikan timer/worker pembaruan dengan aman."""
        self._is_closing = True
        self._was_closed = True
        if getattr(self, "_startup_update_timer", None) is not None:
            self._startup_update_timer.stop()
        if getattr(self, "_reminder_update_timer", None) is not None:
            self._reminder_update_timer.stop()

        notif = getattr(self, "update_notification_dialog", None)
        if notif is not None:
            notif.blockSignals(True)
            notif.close()
            self.update_notification_dialog = None

        worker = getattr(self, "_update_worker", None)
        if worker is not None:
            if worker.isRunning():
                worker.request_cancel()
            worker.wait(2000)
        if getattr(self, "update_dialog", None) is not None:
            self.update_dialog.cancel_active_download()
            self.update_dialog.close()
        self._save_user_preferences()
        super().closeEvent(event)
