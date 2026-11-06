"""Pembaca berkas TIFF ilmiah HILALONE berbasis tifffile (mode baca saja).

Modul ini memisahkan secara tegas:
  1. ``scientific_data`` : array NumPy asli dengan dtype, dimensi, dan nilai
                           piksel yang dipertahankan 100% apa adanya (uint8,
                           uint16, uint32, int16, float32, float64, dll.).
                           Tidak ada normalisasi atau konversi permanen.
  2. ``preview``         : objek ``QImage`` 8-bit terpisah yang dibuat HANYA
                           untuk tampilan layar pada Image Viewer.

Untuk berkas TIFF multi-halaman (multi-page), modul ini TIDAK mengambil halaman
pertama secara diam-diam. Bila ``page_index`` tidak diberikan pada berkas
multi-halaman, ``MultiPageTiffError`` dilempar beserta daftar informasi halaman
agar pengguna atau pemanggil dapat memilih halaman secara eksplisit.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile
from PySide6.QtGui import QImage

from hilalone.input_manager.preview_builder import (
    PREVIEW_BIT_DEPTH,
    array_to_preview_qimage,
)


@dataclass(frozen=True)
class TiffPageSummary:
    """Ringkasan satu halaman (IFD) di dalam berkas TIFF."""

    index: int
    width: int
    height: int
    channels: int
    dtype_str: str
    compression_name: str

    def label(self) -> str:
        """Teks ringkas untuk ditampilkan pada dialog pemilihan halaman."""
        ch_text = {1: "Monokrom", 3: "RGB", 4: "RGBA"}.get(self.channels, f"{self.channels} kanal")
        return f"Halaman {self.index + 1}: {self.width} × {self.height} px, {self.dtype_str}, {ch_text}"


@dataclass(frozen=True)
class TiffReadResult:
    """Hasil pembacaan satu halaman TIFF ilmiah beserta preview layarnya."""

    scientific_data: np.ndarray
    preview: QImage
    width: int
    height: int
    stored_width: int
    stored_height: int
    channels: int
    has_alpha: bool
    original_bit_depth: int
    original_is_float: bool
    dtype_str: str
    page_index: int
    page_count: int
    compression_name: str


def _compression_name(page: tifffile.TiffPage) -> str:
    """Mengambil nama kompresi halaman TIFF secara aman."""
    try:
        comp = tifffile.COMPRESSION(page.compression)
        return comp.name
    except Exception:
        return str(getattr(page, "compression", "TIDAK_DIKETAHUI"))


def _extract_shape_and_channels(shape: tuple[int, ...], planarconfig: int | None) -> tuple[int, int, int, bool]:
    """Menentukan (height, width, channels, is_planar) dari shape halaman TIFF.

    Raises:
        ValueError: bila dimensi array tidak berupa citra 2D atau 3D yang didukung.
    """
    if len(shape) == 2:
        h, w = shape
        return h, w, 1, False
    if len(shape) == 3:
        if planarconfig == 2 and shape[0] in (1, 3, 4) and shape[2] not in (1, 3, 4):
            c, h, w = shape
            return h, w, c, True
        h, w, c = shape
        if c in (1, 3, 4):
            return h, w, c, False
        if shape[0] in (1, 3, 4):
            c, h, w = shape
            return h, w, c, True
    raise ValueError(
        f"Dimensi array TIFF {shape} tidak didukung sebagai citra 2D monokrom atau RGB/RGBA."
    )


def inspect_tiff_pages(path: str | Path) -> list[TiffPageSummary]:
    """Membaca daftar halaman pada berkas TIFF tanpa memuat seluruh piksel ke memori."""
    from hilalone.input_manager.image_reader import ImageReadError

    path = Path(path)
    if not path.exists():
        raise ImageReadError(f"File tidak ditemukan: {path}")
    if not path.is_file():
        raise ImageReadError(f"Jalur yang dipilih bukan sebuah file gambar: {path}")

    try:
        with tifffile.TiffFile(path) as tif:
            if len(tif.pages) == 0:
                raise ImageReadError(f"File TIFF '{path.name}' tidak memiliki halaman gambar.")
            summaries: list[TiffPageSummary] = []
            for idx, page in enumerate(tif.pages):
                planar = getattr(page, "planarconfig", None)
                try:
                    h, w, ch, _ = _extract_shape_and_channels(tuple(page.shape), planar)
                except ValueError as err:
                    raise ImageReadError(
                        f"Halaman {idx + 1} pada '{path.name}' tidak didukung: {err}"
                    ) from err
                summaries.append(
                    TiffPageSummary(
                        index=idx,
                        width=w,
                        height=h,
                        channels=ch,
                        dtype_str=str(page.dtype),
                        compression_name=_compression_name(page),
                    )
                )
            return summaries
    except ImageReadError:
        raise
    except tifffile.TiffFileError as err:
        raise ImageReadError(
            f"File '{path.name}' bukan berkas TIFF yang valid atau isinya rusak. Detail: {err}"
        ) from err
    except Exception as err:
        raise ImageReadError(f"Gagal memeriksa isi file TIFF '{path.name}': {err}") from err


def read_tiff(path: str | Path, page_index: int | None = None) -> TiffReadResult:
    """Membaca berkas TIFF menggunakan tifffile secara baca-saja (read-only)."""
    from hilalone.input_manager.image_reader import ImageReadError, MultiPageTiffError

    path = Path(path)
    summaries = inspect_tiff_pages(path)
    page_count = len(summaries)

    if page_count > 1 and page_index is None:
        raise MultiPageTiffError(
            path=path,
            pages=tuple(summaries),
            message=(
                f"File TIFF '{path.name}' memiliki {page_count} halaman. "
                "Silakan pilih halaman yang ingin dibuka (sistem tidak mengambil halaman "
                "pertama secara diam-diam)."
            ),
        )

    chosen_index = 0 if page_index is None else int(page_index)
    if chosen_index < 0 or chosen_index >= page_count:
        raise ImageReadError(
            f"Indeks halaman TIFF tidak valid: halaman {chosen_index + 1} diminta, "
            f"tetapi file '{path.name}' hanya memiliki {page_count} halaman."
        )

    summary = summaries[chosen_index]
    try:
        with tifffile.TiffFile(path) as tif:
            page = tif.pages[chosen_index]
            planar = getattr(page, "planarconfig", None)
            raw_array = page.asarray()
    except ValueError as err:
        msg = str(err)
        if "imagecodecs" in msg.lower():
            raise ImageReadError(
                f"Gagal mendekode halaman {chosen_index + 1} pada '{path.name}': "
                f"file ini menggunakan kompresi '{summary.compression_name}' yang memerlukan "
                "paket codec tambahan 'imagecodecs' (belum dipasang pada tahap ini). "
                "TIFF tanpa kompresi atau dengan kompresi bawaan tetap didukung."
            ) from err
        raise ImageReadError(
            f"Gagal membaca data piksel TIFF '{path.name}' (kompresi: {summary.compression_name}): {err}"
        ) from err
    except Exception as err:
        raise ImageReadError(
            f"Gagal membaca data piksel TIFF '{path.name}': {err}"
        ) from err

    h, w, ch, is_planar = _extract_shape_and_channels(tuple(raw_array.shape), planar)
    if is_planar:
        scientific = np.ascontiguousarray(np.moveaxis(raw_array, 0, -1))
    elif raw_array.ndim == 3 and raw_array.shape[2] == 1:
        scientific = raw_array[:, :, 0]
    else:
        scientific = raw_array

    if w <= 0 or h <= 0:
        raise ImageReadError(f"Gambar TIFF '{path.name}' memiliki ukuran nol.")

    scientific.flags.writeable = False

    dtype = scientific.dtype
    bit_depth = dtype.itemsize * 8
    is_float = bool(np.issubdtype(dtype, np.floating))
    has_alpha = ch == 4

    preview = array_to_preview_qimage(scientific)

    return TiffReadResult(
        scientific_data=scientific,
        preview=preview,
        width=w,
        height=h,
        stored_width=w,
        stored_height=h,
        channels=ch,
        has_alpha=has_alpha,
        original_bit_depth=bit_depth,
        original_is_float=is_float,
        dtype_str=str(dtype),
        page_index=chosen_index,
        page_count=page_count,
        compression_name=summary.compression_name,
    )
