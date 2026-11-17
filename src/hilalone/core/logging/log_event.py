"""Model data event, level, modul, palet warna, dan ringkasan sesi untuk HILALONE Scientific Processing Log.

Prinsip:
    "Enhance the Signal, Never Invent the Signal."

Seluruh event pencatatan tidak pernah mengarang parameter atau metadata yang tidak tersedia,
membedakan dengan tegas timestamp kejadian, waktu observasi metadata citra, dan durasi
pemrosesan (diukur menggunakan monotonic timer).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class LogLevel(str, Enum):
    """Kategori tingkat/jenis pesan pada HILALONE Scientific Processing Log."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    PROGRESS = "PROGRESS"
    SECTION = "SECTION"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"


class LogEventType(str, Enum):
    """Jenis semantik event pencatatan untuk pemfilteran, pewarnaan, dan serialisasi JSONL."""

    DEBUG = "DEBUG"
    MESSAGE = "MESSAGE"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    PROGRESS = "PROGRESS"
    SECTION = "SECTION"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"
    SUMMARY = "SUMMARY"


class LogVerbosity(str, Enum):
    """Tingkat kedalaman informasi yang ditampilkan pada Console GUI."""

    NORMAL = "NORMAL"
    VERBOSE = "VERBOSE"
    DEBUG = "DEBUG"


class LogModule(str, Enum):
    """Nama modul standar yang konsisten di seluruh komponen HILALONE."""

    SYSTEM = "SYSTEM"
    LOGGING = "LOGGING"
    SESSION = "SESSION"
    INPUT = "INPUT"
    SEQUENCE = "SEQUENCE"
    VALIDATION = "VALIDATION"
    CALIBRATION = "CALIBRATION"
    FLAT = "FLAT"
    STACKING = "STACKING"
    BACKGROUND = "BACKGROUND"
    ENHANCEMENT = "ENHANCEMENT"
    HISTOGRAM = "HISTOGRAM"
    CURVE = "CURVE"
    DISPLAY = "DISPLAY"
    OUTPUT = "OUTPUT"
    EXPORT = "EXPORT"
    VIEWER = "VIEWER"
    UPDATE = "UPDATE"
    HELP = "HELP"
    ERROR = "ERROR"


# Pemetaan nama modul alias/lama ke nama modul standar HILALONE
_MODULE_ALIAS_MAP: dict[str, str] = {
    "SYSTEM": LogModule.SYSTEM.value,
    "MAIN": LogModule.SYSTEM.value,
    "APP": LogModule.SYSTEM.value,
    "LOGGING": LogModule.LOGGING.value,
    "LOG": LogModule.LOGGING.value,
    "SESSION": LogModule.SESSION.value,
    "PIPELINE": LogModule.SESSION.value,
    "STAGE": LogModule.SESSION.value,
    "INPUT": LogModule.INPUT.value,
    "FITS": LogModule.INPUT.value,
    "TIFF": LogModule.INPUT.value,
    "RAW": LogModule.INPUT.value,
    "VIDEO": LogModule.INPUT.value,
    "SER": LogModule.INPUT.value,
    "DATA": LogModule.INPUT.value,
    "METADATA": LogModule.INPUT.value,
    "IO": LogModule.INPUT.value,
    "SEQUENCE": LogModule.SEQUENCE.value,
    "FRAME_SELECTION": LogModule.SEQUENCE.value,
    "VALIDATION": LogModule.VALIDATION.value,
    "CHECK": LogModule.VALIDATION.value,
    "CALIBRATION": LogModule.CALIBRATION.value,
    "FLAT": LogModule.FLAT.value,
    "MASTER_FLAT": LogModule.FLAT.value,
    "STACKING": LogModule.STACKING.value,
    "BACKGROUND": LogModule.BACKGROUND.value,
    "ENHANCEMENT": LogModule.ENHANCEMENT.value,
    "CLAHE": LogModule.ENHANCEMENT.value,
    "HISTOGRAM": LogModule.HISTOGRAM.value,
    "CURVE": LogModule.CURVE.value,
    "CURVES": LogModule.CURVE.value,
    "DISPLAY": LogModule.DISPLAY.value,
    "PREVIEW": LogModule.DISPLAY.value,
    "THEME": LogModule.DISPLAY.value,
    "TOOLS": LogModule.DISPLAY.value,
    "OUTPUT": LogModule.OUTPUT.value,
    "SNAPSHOT": LogModule.OUTPUT.value,
    "EXPORT": LogModule.EXPORT.value,
    "VIEWER": LogModule.VIEWER.value,
    "VIEW": LogModule.VIEWER.value,
    "ERROR": LogModule.ERROR.value,
}


def normalize_module_name(module: str | LogModule) -> str:
    """Menormalisasi nama modul agar konsisten dengan standar penamaan HILALONE."""
    if isinstance(module, LogModule):
        return module.value
    cleaned = str(module or "SYSTEM").strip().upper()
    if not cleaned:
        return LogModule.SYSTEM.value
    return _MODULE_ALIAS_MAP.get(cleaned, cleaned)


# ============================================================================
# PALET WARNA SEMANTIK — STANDARD DARK & NIGHT VISION RED
# ============================================================================

STANDARD_DARK_LOG_PALETTE: dict[str, str] = {
    LogLevel.INFO.value: "#C7D5E8",
    LogLevel.SUCCESS.value: "#65DDA5",
    LogLevel.WARNING.value: "#F0B65C",
    LogLevel.ERROR.value: "#FF7777",
    LogLevel.CRITICAL.value: "#FF4242",
    LogLevel.PROGRESS.value: "#57CFFF",
    LogLevel.DEBUG.value: "#8292AA",
    LogLevel.SECTION.value: "#EAF3FF",
    LogLevel.CANCELLED.value: "#F0B65C",
    LogLevel.SKIPPED.value: "#94A3B8",
}

NIGHT_VISION_RED_LOG_PALETTE: dict[str, str] = {
    LogLevel.INFO.value: "#D9AAAA",
    LogLevel.SUCCESS.value: "#FFA8A8",
    LogLevel.WARNING.value: "#F3A18D",
    LogLevel.ERROR.value: "#FF6666",
    LogLevel.CRITICAL.value: "#FF3333",
    LogLevel.PROGRESS.value: "#F28F8F",
    LogLevel.DEBUG.value: "#A87878",
    LogLevel.SECTION.value: "#FFD0D0",
    LogLevel.CANCELLED.value: "#F3A18D",
    LogLevel.SKIPPED.value: "#B88686",
}


def get_log_color(level: LogLevel | str, *, night_vision: bool = False) -> str:
    """Mengembalikan kode warna hex untuk level/event tertentu berdasarkan tema aktif."""
    lvl_key = level.value if isinstance(level, LogLevel) else str(level).strip().upper()
    palette = NIGHT_VISION_RED_LOG_PALETTE if night_vision else STANDARD_DARK_LOG_PALETTE
    default_color = "#D9AAAA" if night_vision else "#C7D5E8"
    return palette.get(lvl_key, default_color)


def is_semibold_level(level: LogLevel | str) -> bool:
    """Menentukan apakah pesan dengan level ini ditampilkan dengan ketebalan semibold."""
    lvl_key = level.value if isinstance(level, LogLevel) else str(level).strip().upper()
    return lvl_key in {
        LogLevel.SUCCESS.value,
        LogLevel.CRITICAL.value,
        LogLevel.SECTION.value,
    }


def format_duration(
    duration_ms: float | int | None = None,
    *,
    duration_s: float | int | None = None,
    include_label: bool = True,
) -> str:
    """Memformat durasi secara terpusat ke format standar ``Duration: 0.00 s``.

    Aturan:
      1. Menerima ``duration_ms`` (milidetik) ATAU ``duration_s`` (detik).
      2. Mengonversi milidetik menjadi detik tepat satu kali (``sec = ms / 1000.0``).
      3. Membulatkan tampilan menjadi dua angka desimal (``0.00 s``).
      4. Mencegah kesalahan konversi ganda dan menjaga presisi nilai internal.
    """
    if duration_s is not None:
        sec = max(0.0, float(duration_s))
    elif duration_ms is not None:
        sec = max(0.0, float(duration_ms) / 1000.0)
    else:
        sec = 0.0

    if include_label:
        return f"Duration: {sec:.2f} s"
    return f"{sec:.2f} s"


def format_details_kv(details: dict[str, Any] | None) -> str:
    """Memformat dictionary detail tambahan menjadi teks ``key=value`` yang ringkas dan jujur.

    Khusus untuk field durasi (``duration_ms``, ``duration_s``, ``processing_time_sec``),
    selalu diformat menggunakan ``format_duration()`` menjadi ``Duration: 0.00 s``.
    """
    if not details:
        return ""
    parts: list[str] = []
    duration_formatted: str | None = None

    for k, v in details.items():
        if v is None or v == "":
            continue
        if k == "traceback":
            # Traceback lengkap disimpan untuk mode DEBUG / diagnostic file
            continue
        if k == "duration_ms" and isinstance(v, (int, float)):
            if duration_formatted is None:
                duration_formatted = format_duration(duration_ms=float(v))
            continue
        if k in ("duration_s", "processing_time_sec") and isinstance(v, (int, float)):
            if duration_formatted is None:
                duration_formatted = format_duration(duration_s=float(v))
            continue
        if isinstance(v, float):
            parts.append(f"{k}={v:.4g}")
        elif isinstance(v, (dict, list, tuple)):
            if len(v) == 0:
                continue
            if isinstance(v, dict):
                inner = ", ".join(
                    f"{ik}={iv:.4g}" if isinstance(iv, float) else f"{ik}={iv}"
                    for ik, iv in v.items()
                    if iv is not None
                )
                if inner:
                    parts.append(f"{k}={{{inner}}}")
            else:
                if len(v) <= 6:
                    inner_seq = ", ".join(str(x) for x in v)
                    parts.append(f"{k}=[{inner_seq}]")
                else:
                    parts.append(f"{k}=[{len(v)} items]")
        else:
            parts.append(f"{k}={v}")

    if duration_formatted is not None:
        parts.append(duration_formatted)
    return ", ".join(parts)


@dataclass(frozen=True)
class LogEvent:
    """Satu peristiwa pencatatan ilmiah pada HILALONE.

    Menyimpan informasi waktu presisi milidetik (UI) dan ISO 8601 ber-timezone (file),
    Run ID / Session ID, nomor urut sekuensial, level, jenis event, modul, pesan utama,
    serta detail terstruktur.
    """

    timestamp: str
    iso_timestamp: str
    session_id: str
    run_id: str
    sequence: int
    level: LogLevel
    event_type: LogEventType
    module: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    action: str = ""
    detail_text: str = ""
    min_verbosity: LogVerbosity = LogVerbosity.NORMAL
    emitted_under_verbosity: LogVerbosity = LogVerbosity.NORMAL
    raw_block: str | None = None

    @property
    def detail(self) -> str:
        """Properti kompatibilitas untuk kode/tes yang membaca ``entry.detail``."""
        if self.detail_text:
            return self.detail_text
        return format_details_kv(self.details)

    def format_line(self, *, use_iso_timestamp: bool = False) -> str:
        """Memformat event menjadi satu baris teks standar HILALONE:
        ``[TIMESTAMP] [LEVEL] [MODULE] MESSAGE | DETAILS``
        atau format khusus untuk ``SECTION`` dan ``SUMMARY``.
        """
        if self.raw_block is not None:
            return self.raw_block

        if self.level == LogLevel.SECTION or self.event_type == LogEventType.SECTION:
            title = self.message.strip().strip("=").strip()
            return f"=== {title.upper()} ==="

        ts_str = self.iso_timestamp if use_iso_timestamp else self.timestamp
        lvl_str = self.level.value
        mod_str = self.module

        # Gabungkan detail_text dan details key=value tanpa duplikasi
        det_str = self.detail_text.strip()
        kv_str = format_details_kv(self.details)
        if det_str and kv_str:
            # Hindari duplikasi "Duration: X.XX s" jika sudah ada di det_str
            if "Duration:" in det_str and "Duration:" in kv_str:
                kv_items = [item.strip() for item in kv_str.split(",") if not item.strip().startswith("Duration:")]
                kv_str = ", ".join(kv_items)
            combined_detail = f"{det_str} | {kv_str}" if (kv_str and kv_str not in det_str) else det_str
        elif det_str:
            combined_detail = det_str
        else:
            combined_detail = kv_str

        base = f"[{ts_str}] [{lvl_str}] [{mod_str}] {self.message}"
        if combined_detail:
            return f"{base} | {combined_detail}"
        return base

    def to_jsonl_dict(self) -> dict[str, Any]:
        """Menghasilkan representasi dictionary terstruktur yang siap diserialisasi ke JSONL."""
        clean_details: dict[str, Any] = {}
        if self.detail_text and "detail" not in self.details:
            clean_details["info"] = self.detail_text
        for k, v in self.details.items():
            if v is not None:
                clean_details[k] = v
        return {
            "timestamp": self.iso_timestamp,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "level": self.level.value,
            "event_type": self.event_type.value,
            "module": self.module,
            "message": self.message,
            "details": clean_details,
        }


# Alias untuk menjaga kompatibilitas mundur dengan kode yang mengimpor LogEntry
LogEntry = LogEvent


@dataclass(frozen=True)
class ProcessingRunSummary:
    """Data terstruktur untuk mencetak blok PROCESSING SUMMARY di akhir pemrosesan otomatis."""

    run_id: str
    status: str  # "SUCCESS", "PARTIAL", "FAILED", "CANCELLED"
    profile: str
    input_frames: int
    frames_processed: int
    frames_excluded: int
    flat_calibration_status: str  # "APPLIED", "SKIPPED", "FAILED"
    stacking_status: str          # "COMPLETED", "SKIPPED", "FAILED", "CANCELLED"
    background_status: str        # "COMPLETED", "SKIPPED", "FAILED", "CANCELLED"
    enhancement_status: str       # "COMPLETED", "SKIPPED", "FAILED", "CANCELLED"
    histogram_status: str         # "COMPLETED", "SKIPPED", "FAILED", "CANCELLED"
    curve_status: str = "NOT USED"  # "APPLIED", "NOT USED"
    output_files: tuple[str, ...] = ()
    processing_time_sec: float = 0.0

    def format_summary_block(self) -> str:
        """Memformat blok ringkasan eksekusi sesuai standar Bagian XX dengan format durasi seragam."""
        out_str = ", ".join(self.output_files) if self.output_files else "In-memory (Ready to Save)"
        time_str = format_duration(duration_s=self.processing_time_sec)

        if self.status == "CANCELLED":
            footer_title = "AUTOMATED PROCESSING CANCELLED"
        elif self.status == "FAILED":
            footer_title = "AUTOMATED PROCESSING FAILED"
        else:
            footer_title = "AUTOMATED PROCESSING COMPLETED"

        lines = [
            "====================================================",
            "              PROCESSING SUMMARY",
            "====================================================",
            f"Run ID              : {self.run_id}",
            f"Status              : {self.status}",
            f"Profile             : {self.profile}",
            f"Input frames        : {self.input_frames}",
            f"Frames processed    : {self.frames_processed}",
            f"Frames excluded     : {self.frames_excluded}",
            f"Flat Calibration    : {self.flat_calibration_status}",
            f"Image Stacking      : {self.stacking_status}",
            f"Background          : {self.background_status}",
            f"Enhancement         : {self.enhancement_status}",
            f"Histogram           : {self.histogram_status}",
            f"Curve               : {self.curve_status}",
            f"Output              : {out_str}",
            f"Processing time     : {time_str}",
            "====================================================",
            f"       {footer_title}",
            "====================================================",
        ]
        return "\n".join(lines)
