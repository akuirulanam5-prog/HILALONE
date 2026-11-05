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

PREVIEW_BIT_DEPTH = 8


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
        return str( getattr(page, "compression", "TIDAK_DIKETAHUI") )


def _extract_shape_and_channels(shape: tuple[int, ...], planarconfig: int | None) -> tuple[int, int, int, bool]:
    """Menentukan (height, width, channels, is_planar) dari shape halaman TIFF.

    Raises:
        ValueError: bila dimensi array tidak berupa citra 2D atau 3D yang didukung.
    """
    if len(shape) == 2:
        h, w = shape
        return h, w, 1, False
    if len(shape) == 3:
        # Konfigurasi planar (2 = terpisah per kanal, mis. (C, H, W))
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


def _scale_to_uint8_for_preview(data: np.ndarray) -> np.ndarray:
    """Membuat salinan uint8 HANYA untuk tampilan layar (preview).

    Data ilmiah asli TIDAK diubah sama sekali.
    - uint8  : dipakai langsung (salinan).
    - uint16 : digeser 8 bit (dibagi 256) agar memetakan 0..65535 -> 0..255 secara jujur.
    - uint32 : digeser 24 bit (dibagi 16777216) untuk memetakan rentang penuh uint32.
    - signed integer / float : dipetakan secara linear ke 0..255 hanya untuk layar
      agar citra tetap dapat dilihat di viewer tanpa mengubah array ilmiah.
    """
    dtype = data.dtype
    if dtype == np.uint8:
        return np.ascontiguousarray(data)
    if dtype == np.uint16:
        return np.ascontiguousarray((data >> 8).astype(np.uint8))
    if dtype == np.uint32:
        return np.ascontiguousarray((data >> 24).astype(np.uint8))
    if dtype == np.uint64:
        return np.ascontiguousarray((data >> 56).astype(np.uint8))

    # Untuk bilangan bertanda (int8/int16/int32) atau floating-point (float16/32/64):
    work = np.asarray(data, dtype=np.float64)
    finite_mask = np.isfinite(work)
    if not np.any(finite_mask):
        return np.zeros(data.shape, dtype=np.uint8)

    vmin = float(np.min(work[finite_mask]))
    vmax = float(np.max(work[finite_mask]))

    # Bila float sudah berada di dalam [0.0, 1.0], petakan langsung 0..1 -> 0..255.
    if np.issubdtype(dtype, np.floating) and vmin >= 0.0 and vmax <= 1.0:
        scaled = np.clip(work * 255.0, 0.0, 255.0)
    elif vmax > vmin:
        scaled = (work - vmin) / (vmax - vmin) * 255.0
        scaled = np.clip(scaled, 0.0, 255.0)
    else:
        scaled = np.zeros_like(work)

    scaled = np.where(finite_mask, scaled, 0.0)
    return np.ascontiguousarray(scaled.astype(np.uint8))


def _array_to_preview_qimage(data: np.ndarray) -> QImage:
    """Mengonversi array citra (H, W) atau (H, W, C) menjadi QImage 8-bit terpisah."""
    preview_u8 = _scale_to_uint8_for_preview(data)
    if preview_u8.ndim == 2:
        h, w = preview_u8.shape
        bytes_per_line = w
        qimg = QImage(preview_u8.data, w, h, bytes_per_line, QImage.Format.Format_Grayscale8)
        return qimg.copy()  # .copy() agar QImage memiliki salinan memori sendiri

    h, w, c = preview_u8.shape
    if c == 3:
        bytes_per_line = w * 3
        qimg = QImage(preview_u8.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        return qimg.copy()
    if c == 4:
        bytes_per_line = w * 4
        qimg = QImage(preview_u8.data, w, h, bytes_per_line, QImage.Format.Format_RGBA8888)
        return qimg.copy()

    raise ValueError(f"Jumlah kanal tidak didukung untuk preview: {c}")


def read_tiff(path: str | Path, page_index: int | None = None) -> TiffReadResult:
    """Membaca berkas TIFF menggunakan tifffile secara baca-saja (read-only).

    Args:
        path: Jalur berkas TIFF.
        page_index: Indeks halaman (mulai dari 0). Wajib diisi bila berkas
            memiliki lebih dari 1 halaman; bila ``None`` pada TIFF multi-halaman,
            ``MultiPageTiffError`` akan dilempar.

    Returns:
        ``TiffReadResult`` berisi ``scientific_data`` (NumPy array asli) dan
        ``preview`` (QImage 8-bit terpisah).
    """
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
        # Susun ulang sumbu (C, H, W) -> (H, W, C) tanpa mengubah dtype atau nilai piksel
        scientific = np.ascontiguousarray(np.moveaxis(raw_array, 0, -1))
    elif raw_array.ndim == 3 and raw_array.shape[2] == 1:
        scientific = raw_array[:, :, 0]
    else:
        scientific = raw_array

    if w <= 0 or h <= 0:
        raise ImageReadError(f"Gambar TIFF '{path.name}' memiliki ukuran nol.")

    # Kunci array ilmiah agar tidak dapat diubah secara tidak sengaja di memori.
    scientific.flags.writeable = False

    dtype = scientific.dtype
    bit_depth = dtype.itemsize * 8
    is_float = bool(np.issubdtype(dtype, np.floating))
    has_alpha = ch == 4

    preview = _array_to_preview_qimage(scientific)

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
