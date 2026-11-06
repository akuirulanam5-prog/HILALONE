"""Pembaca berkas Camera RAW HILALONE berbasis rawpy / LibRaw (mode baca saja).

Prinsip utama modul ini:
  1. **Keamanan Berkas Sumber & Memori**:
     Berkas RAW dibuka hanya dalam mode baca menggunakan context manager
     ``with rawpy.imread(str(path)) as raw:`` (atau ``try ... finally: raw.close()``)
     sehingga buffer C++ LibRaw dan file handle selalu ditutup begitu array yang
     diperlukan selesai disalin (``.copy()``) ke memori Python.
  2. **Pemisahan Ketat Data Sensor vs RGB Demosaiced Preview**:
     - ``scientific_data`` (dan ``raw_image_visible``) menyimpan nilai piksel
       sensor RAW aktif asli (umumnya mosaic 2D ``uint16``) tanpa pengurangan
       black level permanen, tanpa normalisasi, dan tanpa demosaicing.
     - ``raw_image_full`` menyimpan array sensor penuh (termasuk tepi *optical
       black* / margin sensor) secara terpisah bila tersedia.
     - ``demosaiced_rgb`` adalah representasi RGB 16-bit turunan hasil
       ``raw.postprocess(...)`` dengan parameter eksplisit yang jujur:
         * ``no_auto_bright=True``
         * ``gamma=(1, 1)``
         * ``output_bps=16``
         * ``fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off``
         * ``median_filter_passes=0``
         * ``use_camera_wb=True``
       tanpa sharpening dan tanpa denoising otomatis.
     - ``preview`` adalah ``QImage`` 8-bit untuk tampilan layar GUI semata.
  3. **Fleksibilitas Pola CFA**:
     Tidak mengasumsikan seluruh kamera menggunakan Bayer 2×2. Mendukung Bayer
     2×2 (RGGB, BGGR, GRBG, GBRG, RGBE, CYGM), X-Trans 6×6, maupun sensor
     non-CFA / Linear RAW sesuai matriks ``raw_pattern`` dan ``color_desc``
     aktual dari LibRaw.
  4. **Kejujuran Kompatibilitas Kamera**:
     Tidak mengklaim semua berkas dengan ekstensi ``.CR2``, ``.CR3``, ``.NEF``,
     ``.ARW``, ``.DNG``, ``.ORF``, ``.RAF``, ``.RW2``, ``.PEF``, atau ``.SRW``
     pasti didukung. Dukungan bergantung pada kemampuan aktual LibRaw di dalam
     ``rawpy``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import struct
from typing import Any

import numpy as np
import rawpy
from PySide6.QtGui import QImage

from hilalone.input_manager.preview_builder import array_to_preview_qimage

UNAVAILABLE_TEXT = "Tidak tersedia"

# Ekstensi kandidat berkas kamera RAW yang diteruskan ke adapter LibRaw/rawpy.
RAW_EXTENSIONS: tuple[str, ...] = (
    "cr2",
    "cr3",
    "nef",
    "arw",
    "dng",
    "orf",
    "raf",
    "rw2",
    "pef",
    "srw",
)

DEMOSAIC_PARAMS_DESCRIPTION = (
    "no_auto_bright=True, gamma=(1, 1), output_bps=16, "
    "fbdd_noise_reduction=Off, median_filter_passes=0, use_camera_wb=True"
)
DEMOSAIC_HONESTY_NOTE = (
    "RGB hasil demosaicing adalah representasi turunan untuk pratinjau tampilan, "
    "BUKAN data sensor RAW asli."
)


@dataclass(frozen=True)
class RawMetadataInfo:
    """Metadata sensor, CFA, kalibrasi, dan eksposur dari berkas Camera RAW."""

    camera_make: str | None
    camera_model: str | None
    lens_make: str | None
    lens_model: str | None
    iso_speed: float | int | None
    shutter_speed_sec: float | None
    aperture_fnumber: float | None
    focal_length_mm: float | None
    timestamp_str: str | None
    raw_width: int
    raw_height: int
    visible_width: int
    visible_height: int
    top_margin: int
    left_margin: int
    raw_type_str: str
    is_cfa_mosaic: bool
    num_colors: int | None
    color_desc: str | None
    raw_pattern_matrix: tuple[tuple[int, ...], ...] | None
    cfa_pattern_str: str
    black_level_per_channel: tuple[int, ...] | None
    white_level: int | None
    camera_white_level_per_channel: tuple[int, ...] | None
    camera_whitebalance: tuple[float, ...] | None
    daylight_whitebalance: tuple[float, ...] | None
    demosaic_parameters: str = DEMOSAIC_PARAMS_DESCRIPTION
    demosaic_note: str = DEMOSAIC_HONESTY_NOTE

    def format_camera_name(self) -> str:
        parts = [p.strip() for p in (self.camera_make, self.camera_model) if p and p.strip()]
        if not parts:
            return UNAVAILABLE_TEXT
        if len(parts) == 2 and parts[1].lower().startswith(parts[0].lower()):
            return parts[1]
        return " ".join(parts)

    def format_shutter_speed(self) -> str:
        val = self.shutter_speed_sec
        if val is None or val <= 0.0 or not np.isfinite(val):
            return UNAVAILABLE_TEXT
        if val < 1.0:
            inv = round(1.0 / val)
            if inv > 0 and abs(val - (1.0 / inv)) / val < 0.03:
                return f"1/{inv} s ({val:.5f} s)"
            return f"{val:.5f} s"
        return f"{val:.3f} s"

    def format_aperture(self) -> str:
        val = self.aperture_fnumber
        if val is None or val <= 0.0 or not np.isfinite(val):
            return UNAVAILABLE_TEXT
        return f"f/{val:.1f}"

    def format_focal_length(self) -> str:
        val = self.focal_length_mm
        if val is None or val <= 0.0 or not np.isfinite(val):
            return UNAVAILABLE_TEXT
        return f"{val:.1f} mm"

    def format_iso(self) -> str:
        val = self.iso_speed
        if val is None or val <= 0 or not np.isfinite(float(val)):
            return UNAVAILABLE_TEXT
        if float(val).is_integer():
            return str(int(round(float(val))))
        return f"{float(val):.1f}"

    def to_display_dict(self) -> dict[str, str]:
        """Mengembalikan pasangan field -> teks tampilan ('Tidak tersedia' bila None)."""
        blk = (
            ", ".join(str(v) for v in self.black_level_per_channel)
            if self.black_level_per_channel
            else UNAVAILABLE_TEXT
        )
        wht = str(self.white_level) if self.white_level is not None else UNAVAILABLE_TEXT
        cam_wb = (
            ", ".join(f"{v:.3f}" for v in self.camera_whitebalance)
            if self.camera_whitebalance
            else UNAVAILABLE_TEXT
        )
        return {
            "CAMERA": self.format_camera_name(),
            "ISO": self.format_iso(),
            "SHUTTER": self.format_shutter_speed(),
            "APERTURE": self.format_aperture(),
            "FOCAL_LENGTH": self.format_focal_length(),
            "TIMESTAMP": self.timestamp_str or UNAVAILABLE_TEXT,
            "RAW_DIM": f"{self.raw_width}×{self.raw_height} px",
            "VISIBLE_DIM": f"{self.visible_width}×{self.visible_height} px",
            "CFA_PATTERN": self.cfa_pattern_str or UNAVAILABLE_TEXT,
            "COLOR_DESC": self.color_desc or UNAVAILABLE_TEXT,
            "BLACK_LEVEL": blk,
            "WHITE_LEVEL": wht,
            "CAMERA_WB": cam_wb,
            "DEMOSAIC_NOTE": self.demosaic_note,
        }

    def summary_text(self) -> str:
        """Ringkasan multibaris untuk ditampilkan pada panel informasi GUI."""
        d = self.to_display_dict()
        lines = [
            f"Kamera: {d['CAMERA']}",
            f"Sensor: Aktif {d['VISIBLE_DIM']} | Penuh {d['RAW_DIM']}",
            f"CFA: {d['CFA_PATTERN']} ( Kanal: {d['COLOR_DESC']} )",
            f"Black Level: [{d['BLACK_LEVEL']}] | White Level: {d['WHITE_LEVEL']}",
            f"ISO: {d['ISO']} | Shutter: {d['SHUTTER']} | {d['APERTURE']} | {d['FOCAL_LENGTH']}",
            f"White Balance (Camera): [{d['CAMERA_WB']}]",
            f"Timestamp: {d['TIMESTAMP']}",
            f"Catatan: {self.demosaic_note}",
        ]
        return "\n".join(lines)


@dataclass(frozen=True)
class RawReadResult:
    """Hasil lengkap pembacaan berkas Camera RAW."""

    width: int
    height: int
    stored_width: int
    stored_height: int
    channels: int
    has_alpha: bool
    original_bit_depth: int
    original_is_float: bool
    dtype_str: str
    stored_dtype_str: str
    metadata: RawMetadataInfo
    scientific_data: np.ndarray
    raw_image_visible: np.ndarray
    raw_image_full: np.ndarray | None
    demosaiced_rgb: np.ndarray
    preview: QImage


def _decode_color_desc(raw_color_desc: Any) -> str | None:
    """Menerjemahkan ``raw.color_desc`` (bytes/str) menjadi teks ASCII bersih."""
    if raw_color_desc is None:
        return None
    if isinstance(raw_color_desc, bytes):
        text = raw_color_desc.decode("ascii", errors="ignore").strip("\x00").strip()
    else:
        text = str(raw_color_desc).strip("\x00").strip()
    return text if text else None


def _describe_cfa_pattern(
    raw_pattern: Any,
    color_desc: str | None,
    raw_type: Any,
) -> tuple[tuple[tuple[int, ...], ...] | None, str, bool]:
    """Menyusun matriks pola CFA dan label pola CFA tanpa mengasumsikan selalu Bayer 2×2.

    Returns:
        (raw_pattern_matrix, cfa_pattern_str, is_cfa_mosaic)
    """
    is_stack = False
    if raw_type is not None:
        type_name = getattr(raw_type, "name", str(raw_type)).lower()
        if "stack" in type_name:
            is_stack = True

    if raw_pattern is None:
        if is_stack:
            return None, "Non-CFA (Stacked / Linear RAW)", False
        return None, UNAVAILABLE_TEXT, False

    try:
        arr = np.asarray(raw_pattern)
    except Exception:
        return None, UNAVAILABLE_TEXT, not is_stack

    if arr.ndim != 2 or arr.size == 0:
        if is_stack:
            return None, "Non-CFA (Stacked / Linear RAW)", False
        return None, UNAVAILABLE_TEXT, False

    matrix: tuple[tuple[int, ...], ...] = tuple(
        tuple(int(v) for v in row) for row in arr.tolist()
    )
    rows, cols = arr.shape
    palette = color_desc or "RGBG"

    def _idx_to_char(idx: int) -> str:
        if 0 <= idx < len(palette):
            return palette[idx]
        return str(idx)

    row_strings = ["".join(_idx_to_char(int(v)) for v in row) for row in arr]

    if is_stack:
        return matrix, "Non-CFA (Stacked / Linear RAW)", False

    if (rows, cols) == (2, 2):
        flat_code = "".join(row_strings)
        return matrix, f"{flat_code} (Bayer 2×2)", True

    if (rows, cols) == (6, 6):
        top_sample = "/".join(row_strings[:2])
        return matrix, f"X-Trans / CFA 6×6 ({top_sample}/...)", True

    if (rows, cols) == (1, 1):
        return matrix, f"Monokrom / 1×1 ({row_strings[0]})", False

    joined = "/".join(row_strings[:4])
    if rows > 4:
        joined += "/..."
    return matrix, f"CFA {rows}×{cols} ({joined})", True


def _clean_positive_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f) or f <= 0.0:
        return None
    return f


def _format_unix_timestamp(ts_val: Any) -> str | None:
    """Mengubah nilai timestamp (Unix epoch detik atau string ISO) ke string terbaca."""
    if ts_val is None:
        return None
    if isinstance(ts_val, str):
        cleaned = ts_val.strip()
        return cleaned if cleaned else None
    try:
        f = float(ts_val)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f) or f <= 0.0:
        return None
    try:
        dt = datetime.fromtimestamp(f, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def _parse_tiff_ifd0_ascii_tags(buf: bytes, tiff_start: int = 0) -> dict[int, str]:
    """Membaca tag ASCII pada IFD0 header TIFF (mis. 271=Make, 272=Model, 306=DateTime).

    Fungsi ini murni membaca buffer byte di memori (tanpa mengubah berkas).
    """
    result: dict[int, str] = {}
    data = buf[tiff_start:]
    if len(data) < 8:
        return result

    byte_order = data[:2]
    if byte_order == b"II":
        endian = "<"
    elif byte_order == b"MM":
        endian = ">"
    else:
        return result

    try:
        magic, ifd_offset = struct.unpack(f"{endian}HI", data[2:8])
        if magic not in (42, 0x4F52, 0x5352, 0x0055):
            return result
        if ifd_offset + 2 > len(data):
            return result
        (num_entries,) = struct.unpack(f"{endian}H", data[ifd_offset : ifd_offset + 2])
        pos = ifd_offset + 2
        for _ in range(min(num_entries, 128)):
            if pos + 12 > len(data):
                break
            tag, field_type, count, val_offset = struct.unpack(
                f"{endian}HHII", data[pos : pos + 12]
            )
            pos += 12
            # Tipe 2 = ASCII string
            if field_type == 2 and tag in (271, 272, 306) and 0 < count <= 256:
                if count <= 4:
                    raw_bytes = data[pos - 4 : pos - 4 + count]
                elif val_offset + count <= len(data):
                    raw_bytes = data[val_offset : val_offset + count]
                else:
                    continue
                text = raw_bytes.decode("ascii", errors="ignore").strip("\x00").strip()
                if text:
                    result[tag] = text
    except Exception:
        return result
    return result


def _extract_camera_make_model_from_file(path: Path) -> tuple[str | None, str | None, str | None]:
    """Mengekstrak (Make, Model, DateTime) dari header berkas secara aman (hanya-baca)."""
    try:
        with path.open("rb") as f:
            header = f.read(65536)
    except OSError:
        return None, None, None

    if len(header) < 8:
        return None, None, None

    # 1. Berkas RAW berbasis TIFF langsung (CR2, NEF, ARW, DNG, ORF, PEF, RW2, SRW)
    if header[:2] in (b"II", b"MM"):
        tags = _parse_tiff_ifd0_ascii_tags(header, 0)
        return tags.get(271), tags.get(272), tags.get(306)

    # 2. Berkas Canon CR3 (ISO Base Media File dengan kotak 'CMT1' berisi TIFF IFD0)
    cmt1_idx = header.find(b"CMT1")
    if cmt1_idx != -1 and cmt1_idx + 4 < len(header):
        tags = _parse_tiff_ifd0_ascii_tags(header, cmt1_idx + 4)
        return tags.get(271), tags.get(272), tags.get(306)

    # 3. Berkas Fujifilm RAF (memiliki header "FUJIFILMCCD-RAW " diikuti nama model kamera)
    if header.startswith(b"FUJIFILMCCD-RAW"):
        model_bytes = header[0x1C:0x3C].split(b"\x00", 1)[0]
        model_str = model_bytes.decode("ascii", errors="ignore").strip()
        return "Fujifilm", (model_str or None), None

    return None, None, None


def _extract_raw_metadata(raw: Any, path: Path) -> RawMetadataInfo:
    """Mengekstrak seluruh metadata sensor, CFA, kalibrasi, dan eksposur dari objek RawPy."""
    sizes = getattr(raw, "sizes", None)
    raw_width = int(getattr(sizes, "raw_width", 0) or 0)
    raw_height = int(getattr(sizes, "raw_height", 0) or 0)
    vis_width = int(getattr(sizes, "width", 0) or 0)
    vis_height = int(getattr(sizes, "height", 0) or 0)
    top_margin = int(getattr(sizes, "top_margin", 0) or 0)
    left_margin = int(getattr(sizes, "left_margin", 0) or 0)

    raw_type = getattr(raw, "raw_type", None)
    raw_type_str = getattr(raw_type, "name", str(raw_type)) if raw_type is not None else "Unknown"

    num_colors_raw = getattr(raw, "num_colors", None)
    num_colors = int(num_colors_raw) if num_colors_raw is not None else None

    color_desc = _decode_color_desc(getattr(raw, "color_desc", None))
    raw_pattern = getattr(raw, "raw_pattern", None)
    pattern_matrix, cfa_str, is_cfa_mosaic = _describe_cfa_pattern(
        raw_pattern, color_desc, raw_type
    )

    # Black level & White level
    blk_raw = getattr(raw, "black_level_per_channel", None)
    blk_tuple: tuple[int, ...] | None = None
    if blk_raw is not None:
        try:
            blk_tuple = tuple(int(v) for v in blk_raw)
        except Exception:
            blk_tuple = None

    white_raw = getattr(raw, "white_level", None)
    white_level = int(white_raw) if white_raw is not None and int(white_raw) > 0 else None

    cam_wl_raw = getattr(raw, "camera_white_level_per_channel", None)
    cam_wl_tuple: tuple[int, ...] | None = None
    if cam_wl_raw is not None:
        try:
            cam_wl_tuple = tuple(int(v) for v in cam_wl_raw)
        except Exception:
            cam_wl_tuple = None

    # White balance multipliers
    cam_wb_raw = getattr(raw, "camera_whitebalance", None)
    cam_wb: tuple[float, ...] | None = None
    if cam_wb_raw is not None:
        try:
            vals = tuple(float(v) for v in cam_wb_raw)
            if any(v > 0.0 for v in vals):
                cam_wb = vals
        except Exception:
            cam_wb = None

    day_wb_raw = getattr(raw, "daylight_whitebalance", None)
    day_wb: tuple[float, ...] | None = None
    if day_wb_raw is not None:
        try:
            vals = tuple(float(v) for v in day_wb_raw)
            if any(v > 0.0 for v in vals):
                day_wb = vals
        except Exception:
            day_wb = None

    # Eksposur dari raw.other & lens dari raw.lens
    other = getattr(raw, "other", None)
    iso_speed = _clean_positive_float(getattr(other, "iso_speed", None)) if other else None
    shutter_sec = _clean_positive_float(getattr(other, "shutter_speed", None)) if other else None
    aperture = _clean_positive_float(getattr(other, "aperture", None)) if other else None
    focal_len = _clean_positive_float(getattr(other, "focal_length", None)) if other else None
    ts_str = _format_unix_timestamp(getattr(other, "timestamp", None)) if other else None

    lens = getattr(raw, "lens", None)
    lens_make = (str(getattr(lens, "make", "") or "").strip() or None) if lens else None
    lens_model = (str(getattr(lens, "model", "") or "").strip() or None) if lens else None

    # Camera make/model: periksa atribut langsung pada objek raw (mis. mock/ekstensi),
    # lalu fallback ke pembaca header TIFF/CR3/RAF.
    cam_make = str(getattr(raw, "camera_make", "") or "").strip() or None
    cam_model = str(getattr(raw, "camera_model", "") or "").strip() or None
    hdr_make, hdr_model, hdr_dt = _extract_camera_make_model_from_file(path)
    if cam_make is None:
        cam_make = hdr_make
    if cam_model is None:
        cam_model = hdr_model
    if ts_str is None and hdr_dt:
        ts_str = hdr_dt

    return RawMetadataInfo(
        camera_make=cam_make,
        camera_model=cam_model,
        lens_make=lens_make,
        lens_model=lens_model,
        iso_speed=iso_speed,
        shutter_speed_sec=shutter_sec,
        aperture_fnumber=aperture,
        focal_length_mm=focal_len,
        timestamp_str=ts_str,
        raw_width=raw_width,
        raw_height=raw_height,
        visible_width=vis_width,
        visible_height=vis_height,
        top_margin=top_margin,
        left_margin=left_margin,
        raw_type_str=raw_type_str,
        is_cfa_mosaic=is_cfa_mosaic,
        num_colors=num_colors,
        color_desc=color_desc,
        raw_pattern_matrix=pattern_matrix,
        cfa_pattern_str=cfa_str,
        black_level_per_channel=blk_tuple,
        white_level=white_level,
        camera_white_level_per_channel=cam_wl_tuple,
        camera_whitebalance=cam_wb,
        daylight_whitebalance=day_wb,
    )


def _translate_rawpy_exception(path: Path, exc: Exception) -> Exception:
    """Menerjemahkan eksepsi LibRaw/rawpy ke ImageReadError berbahasa Indonesia yang spesifik."""
    from hilalone.input_manager.image_reader import ImageReadError

    if isinstance(exc, ImageReadError):
        return exc

    if isinstance(exc, (rawpy.LibRawFileUnsupportedError, rawpy.NotSupportedError)):
        return ImageReadError(
            f"Format atau model kamera pada file RAW '{path.name}' belum didukung oleh LibRaw "
            f"(detail: {exc}). Tidak semua kamera pada ekstensi {path.suffix.upper()} didukung."
        )

    if isinstance(
        exc,
        (
            rawpy.LibRawDataError,
            rawpy.LibRawIOError,
            rawpy.LibRawBadCropError,
            rawpy.LibRawRequestForNonexistentImageError,
        ),
    ):
        return ImageReadError(
            f"Gagal membaca data sensor dari file RAW '{path.name}': file kemungkinan rusak, "
            f"terpotong, atau bukan berkas RAW yang valid (detail: {exc})."
        )

    if isinstance(exc, (rawpy.LibRawUnsufficientMemoryError, rawpy.LibRawMemPoolOverflowError, MemoryError)):
        return ImageReadError(
            f"Memori tidak mencukupi saat membuka file RAW '{path.name}'."
        )

    if isinstance(exc, rawpy.LibRawError):
        return ImageReadError(
            f"Gagal membuka file RAW '{path.name}' melalui LibRaw: {exc}"
        )

    return ImageReadError(
        f"File RAW '{path.name}' tidak dapat dibaca atau rusak: {exc}"
    )


def _open_raw_safely(path: Path) -> Any:
    """Membuka berkas RAW menggunakan rawpy.imread dengan penanganan galat Bahasa Indonesia."""
    try:
        return rawpy.imread(str(path))
    except Exception as exc:
        raise _translate_rawpy_exception(path, exc) from exc


def inspect_raw_header(path: str | Path) -> tuple[RawMetadataInfo, str, int]:
    """Memeriksa metadata dan dimensi berkas RAW TANPA menjalankan demosaicing (*Lazy Loading*).

    Returns:
        (metadata, dtype_str, channels)
    """
    from hilalone.input_manager.image_reader import ImageReadError

    path = Path(path)
    raw = _open_raw_safely(path)
    try:
        meta = _extract_raw_metadata(raw, path)
        if meta.visible_width <= 0 or meta.visible_height <= 0:
            raise ImageReadError(
                f"Header file RAW '{path.name}' memiliki dimensi aktif tidak valid "
                f"({meta.visible_width}×{meta.visible_height})."
            )
        channels = 1 if meta.is_cfa_mosaic else (meta.num_colors or 3)
        dtype_str = "uint16"
        return meta, dtype_str, channels
    except Exception as exc:
        raise _translate_rawpy_exception(path, exc) from exc
    finally:
        try:
            raw.close()
        except Exception:
            pass


def read_raw(path: str | Path) -> RawReadResult:
    """Membaca berkas Camera RAW: memisahkan data sensor asli dan RGB demosaiced preview.

    - ``scientific_data`` & ``raw_image_visible``: salinan ``raw.raw_image_visible``
      asli sebelum objek ``RawPy`` ditutup, dikunci ``writeable = False``.
    - ``raw_image_full``: salinan ``raw.raw_image`` penuh (termasuk margin sensor)
      bila tersedia, dikunci ``writeable = False``.
    - ``demosaiced_rgb``: hasil ``raw.postprocess(...)`` dengan parameter eksplisit:
      ``no_auto_bright=True, gamma=(1, 1), output_bps=16,
      fbdd_noise_reduction=FBDDNoiseReductionMode.Off, median_filter_passes=0``.
    - ``preview``: ``QImage`` 8-bit terpisah untuk tampilan layar GUI.
    """
    from hilalone.input_manager.image_reader import ImageReadError

    path = Path(path)
    raw = _open_raw_safely(path)
    try:
        meta = _extract_raw_metadata(raw, path)

        # 1. Salin raw_image_visible (data sensor aktif) sebelum raw.close()
        vis_arr = getattr(raw, "raw_image_visible", None)
        full_arr = getattr(raw, "raw_image", None)

        if vis_arr is None and full_arr is None:
            raise ImageReadError(
                f"File RAW '{path.name}' tidak menyediakan data sensor (raw_image_visible kosong)."
            )

        if vis_arr is not None:
            raw_visible = np.array(vis_arr, copy=True)
        else:
            raw_visible = np.array(full_arr, copy=True)

        if full_arr is not None:
            raw_full: np.ndarray | None = np.array(full_arr, copy=True)
            raw_full.flags.writeable = False
        else:
            raw_full = None

        raw_visible.flags.writeable = False
        scientific_data = raw_visible

        if scientific_data.size == 0 or scientific_data.shape[0] <= 0 or scientific_data.shape[1] <= 0:
            raise ImageReadError(
                f"Data sensor RAW '{path.name}' memiliki ukuran nol dan tidak dapat digunakan."
            )

        # 2. Buat representasi RGB demosaiced terpisah dengan parameter eksplisit & jujur
        demosaiced = raw.postprocess(
            use_camera_wb=True,
            no_auto_bright=True,
            gamma=(1, 1),
            output_bps=16,
            fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
            median_filter_passes=0,
        )
        demosaiced_rgb = np.array(demosaiced, copy=True)
        demosaiced_rgb.flags.writeable = False
    except Exception as exc:
        raise _translate_rawpy_exception(path, exc) from exc
    finally:
        try:
            raw.close()
        except Exception:
            pass

    # 3. Buat QImage 8-bit preview dari demosaiced_rgb tanpa menyentuh scientific_data
    preview = array_to_preview_qimage(demosaiced_rgb)

    vis_h, vis_w = int(scientific_data.shape[0]), int(scientific_data.shape[1])
    if scientific_data.ndim == 2:
        channels = 1
    else:
        channels = int(scientific_data.shape[2])

    stored_w = meta.raw_width if meta.raw_width > 0 else (
        int(raw_full.shape[1]) if raw_full is not None else vis_w
    )
    stored_h = meta.raw_height if meta.raw_height > 0 else (
        int(raw_full.shape[0]) if raw_full is not None else vis_h
    )

    dt = scientific_data.dtype
    dtype_str = str(dt)

    return RawReadResult(
        width=vis_w,
        height=vis_h,
        stored_width=stored_w,
        stored_height=stored_h,
        channels=channels,
        has_alpha=(channels == 4),
        original_bit_depth=dt.itemsize * 8,
        original_is_float=bool(np.issubdtype(dt, np.floating)),
        dtype_str=dtype_str,
        stored_dtype_str=dtype_str,
        metadata=meta,
        scientific_data=scientific_data,
        raw_image_visible=raw_visible,
        raw_image_full=raw_full,
        demosaiced_rgb=demosaiced_rgb,
        preview=preview,
    )
