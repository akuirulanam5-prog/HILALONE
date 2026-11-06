"""Unified Input Data Model HILALONE (Sub-Tahap 2A).

Modul ini menyatukan representasi data masukan dari seluruh format gambar yang
didukung (PNG, JPG/JPEG, BMP, TIFF, dan FITS) baik untuk mode Single Image
maupun Multiple Images / Folder Sequence.

Prinsip utama:
  1. Setiap frame dalam sequence memiliki kartu identitas ``SequenceFrameEntry``
     yang menyimpan sumber berkas, indeks urut, metadata, dimensi, jumlah kanal,
     tipe data asli, dan status kompatibilitas/pemuatan.
  2. Frame dengan dimensi, jumlah kanal, atau orientasi yang berbeda dari frame
     referensi ditandai ``INCOMPATIBLE`` untuk stacking, namun TETAP dapat
     dibuka dan dipratinjau secara individual.
  3. Perbedaan bit depth / tipe numerik (mis. ``uint8`` vs ``uint16``) TIDAK
     otomatis membuat frame ``INCOMPATIBLE``; hal itu dicatat sebagai catatan
     konversi numerik terkontrol (``notes``) dan disediakan fungsi
     ``to_controlled_float32()`` untuk kebutuhan preprocessing/stacking
     berikutnya tanpa mengubah ``scientific_data`` asli.
  4. ``is_structural_ready_for_stacking`` (dan alias ``is_ready_for_stacking``)
     hanya menyatakan kesiapan STRUKTURAL (dimensi, kanal, orientasi, keterbacaan),
     bukan hasil stacking ataupun jaminan kualitas/stabilitas posisi piksel.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from hilalone.input_manager.image_reader import ImageInfo


class FrameStatus(str, Enum):
    """Status struktural satu frame di dalam sequence."""

    COMPATIBLE = "COMPATIBLE"
    INCOMPATIBLE = "INCOMPATIBLE"
    ERROR = "ERROR"


class InputMode(str, Enum):
    """Mode masukan yang sedang aktif di HILALONE."""

    EMPTY = "EMPTY"
    SINGLE = "SINGLE"
    MULTI = "MULTI"
    VIDEO = "VIDEO"
    SER = "SER"


@dataclass(frozen=True)
class SequenceFrameEntry:
    """Kartu identitas satu frame di dalam Sequence Manager (tanpa memuat piksel ke RAM)."""

    frame_index: int
    source_path: Path
    info: ImageInfo | None
    status: FrameStatus
    is_pixel_loaded: bool = False
    timestamp_str: str | None = None
    issues: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def file_name(self) -> str:
        return self.source_path.name

    @property
    def width(self) -> int | None:
        return self.info.width if self.info is not None else None

    @property
    def height(self) -> int | None:
        return self.info.height if self.info is not None else None

    @property
    def channels(self) -> int | None:
        return self.info.channels if self.info is not None else None

    @property
    def dtype_str(self) -> str | None:
        return self.info.dtype_str if self.info is not None else None

    @property
    def file_format(self) -> str | None:
        return self.info.file_format if self.info is not None else None

    def can_preview(self) -> bool:
        """Frame COMPATIBLE maupun INCOMPATIBLE tetap dapat dibuka untuk pratinjau individual."""
        return self.status in (FrameStatus.COMPATIBLE, FrameStatus.INCOMPATIBLE)

    def status_badge_indonesian(self) -> str:
        """Label status singkat dalam Bahasa Indonesia untuk daftar GUI."""
        if self.status == FrameStatus.COMPATIBLE:
            return "KOMPATIBEL" if not self.notes else "KOMPATIBEL (Beda Bit Depth)"
        if self.status == FrameStatus.INCOMPATIBLE:
            return "TIDAK KOMPATIBEL"
        return "GAGAL DIBACA"

    def dropdown_label(self, total: int) -> str:
        """Teks untuk ditampilkan pada daftar navigasi frame di GUI."""
        prefix = f"[{self.frame_index + 1}/{total}] {self.file_name}"
        if self.info is not None:
            dim = f"{self.info.width}×{self.info.height}"
            ch = {1: "Mono", 3: "RGB", 4: "RGBA"}.get(self.info.channels or 0, "?")
            dt = self.info.dtype_str or f"{self.info.original_bit_depth}-bit"
            ts_part = f" | t={self.timestamp_str}" if self.timestamp_str else ""
            return f"{prefix}{ts_part} — {dim}, {ch}, {dt} [{self.status_badge_indonesian()}]"
        return f"{prefix} — [{self.status_badge_indonesian()}]"


@dataclass(frozen=True)
class SequenceCompatibilityReport:
    """Laporan pemeriksaan kompatibilitas struktural sequence.

    Catatan penting: ``is_ready_for_stacking`` hanya menunjukkan kompatibilitas
    STRUKTURAL (seluruh frame terbaca dan memiliki dimensi, jumlah kanal, serta
    orientasi yang seragam). Pemeriksaan kestabilan posisi piksel (ambang 1 px)
    dan kualitas frame dilakukan pada tahap pemeriksaan pra-stacking berikutnya.
    """

    is_ready_for_stacking: bool
    reference_frame_index: int | None
    total_files: int
    compatible_count: int
    incompatible_count: int
    error_count: int
    mixed_bit_depth: bool
    warnings: tuple[str, ...]
    notes: tuple[str, ...]


def to_controlled_float32(scientific_data: np.ndarray, normalize_integers: bool = True) -> np.ndarray:
    """Konversi numerik terkontrol ke ``float32`` untuk kebutuhan stacking berikutnya.

    Fungsi ini TIDAK mengubah ``scientific_data`` asli (selalu mengembalikan
    salinan baru bertipe ``np.float32``).
      * Bila ``normalize_integers=True`` dan tipe sumber adalah unsigned integer
        (``uint8``, ``uint16``, ``uint32``), nilai dibagi dengan nilai maksimum
        tipenya (255.0, 65535.0, 4294967295.0) agar frame dengan bit depth
        berbeda berada pada skala linear [0.0, 1.0] yang setara.
      * Bila sumber sudah bertipe floating-point (``float32``/``float64``) atau
        ``normalize_integers=False``, nilai dikonversi langsung ke ``np.float32``
        tanpa mengubah skala.
    """
    dtype = scientific_data.dtype
    if normalize_integers and np.issubdtype(dtype, np.unsignedinteger):
        max_val = float(np.iinfo(dtype).max)
        out = scientific_data.astype(np.float32) / np.float32(max_val)
    else:
        out = scientific_data.astype(np.float32, copy=True)
    out.flags.writeable = False
    return out
