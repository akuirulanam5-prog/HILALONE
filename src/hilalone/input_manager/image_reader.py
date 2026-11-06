"""Pembaca gambar HILALONE v0.1 (hanya baca).

Modul ini menghasilkan TIGA komponen yang dipisahkan dengan jelas:
  * ``ImageInfo``       : fakta tentang berkas ASLI (ukuran tersimpan, bit depth
                          asli, dtype, jumlah kanal, orientasi EXIF asli, serta
                          informasi halaman TIFF atau HDU & header FITS).
  * ``scientific_data`` : array NumPy asli tanpa perubahan nilai piksel atau
                          normalisasi permanen (diisi untuk seluruh format:
                          PNG, JPG/JPEG, BMP, TIFF, dan FITS).
  * ``preview``         : salinan ``QImage`` 8-bit di memori untuk TAMPILAN LAYAR
                          saja. Preview bukan data ilmiah.

Modul ini juga menyediakan ``inspect_image_header(path)`` untuk kebutuhan
*Lazy Loading* pada Sequence Manager: membaca dimensi, jumlah kanal, tipe data,
dan metadata berkas TANPA memuat seluruh array piksel ke RAM.

Berkas sumber hanya dibuka untuk dibaca; tidak pernah diubah atau ditimpa.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtGui import QImage, QImageIOHandler, QImageReader

if TYPE_CHECKING:
    from hilalone.input_manager.adapters.fits_reader import FitsHeaderInfo, FitsHduSummary
    from hilalone.input_manager.adapters.raw_reader import RawMetadataInfo
    from hilalone.input_manager.adapters.tiff_reader import TiffPageSummary

# Ekstensi yang ditangani melalui QImageReader (Qt).
_QT_EXTENSIONS_BY_FORMAT: dict[str, tuple[str, ...]] = {
    "png": ("png",),
    "jpeg": ("jpg", "jpeg"),
    "jpg": ("jpg", "jpeg"),
    "bmp": ("bmp",),
}
# Ekstensi ilmiah & kamera yang ditangani melalui adapter khusus.
_TIFF_EXTENSIONS = ("tif", "tiff")
_FITS_EXTENSIONS = ("fit", "fits", "fts")
_RAW_EXTENSIONS = ("cr2", "cr3", "nef", "arw", "dng", "orf", "raf", "rw2", "pef", "srw")

# Bit depth preview layar (selalu 8-bit pada v0.1).
PREVIEW_BIT_DEPTH = 8

_F = QImage.Format

# Tabel format Qt -> (jumlah kanal, ada alpha, bit per kanal, bilangan riil/float).
_FORMAT_TABLE: dict[QImage.Format, tuple[int | None, bool, int | None, bool]] = {
    _F.Format_Mono: (1, False, 1, False),
    _F.Format_MonoLSB: (1, False, 1, False),
    _F.Format_Indexed8: (None, False, 8, False),  # berpalet: kanal tidak pasti
    _F.Format_Grayscale8: (1, False, 8, False),
    _F.Format_Grayscale16: (1, False, 16, False),
    _F.Format_RGB32: (3, False, 8, False),
    _F.Format_RGB888: (3, False, 8, False),
    _F.Format_BGR888: (3, False, 8, False),
    _F.Format_RGBX8888: (3, False, 8, False),
    _F.Format_RGB16: (3, False, None, False),
    _F.Format_RGB555: (3, False, None, False),
    _F.Format_RGB666: (3, False, None, False),
    _F.Format_RGB444: (3, False, None, False),
    _F.Format_ARGB32: (4, True, 8, False),
    _F.Format_ARGB32_Premultiplied: (4, True, 8, False),
    _F.Format_RGBA8888: (4, True, 8, False),
    _F.Format_RGBA8888_Premultiplied: (4, True, 8, False),
    _F.Format_RGB30: (3, False, 10, False),
    _F.Format_BGR30: (3, False, 10, False),
    _F.Format_RGBX64: (3, False, 16, False),
    _F.Format_RGBA64: (4, True, 16, False),
    _F.Format_RGBA64_Premultiplied: (4, True, 16, False),
    _F.Format_RGBX16FPx4: (3, False, 16, True),
    _F.Format_RGBA16FPx4: (4, True, 16, True),
    _F.Format_RGBA16FPx4_Premultiplied: (4, True, 16, True),
    _F.Format_RGBX32FPx4: (3, False, 32, True),
    _F.Format_RGBA32FPx4: (4, True, 32, True),
    _F.Format_RGBA32FPx4_Premultiplied: (4, True, 32, True),
}

_T = QImageIOHandler.Transformation

_ORIENTATION_LABELS: dict[QImageIOHandler.Transformation, str] = {
    _T.TransformationNone: "Normal (tanpa rotasi)",
    _T.TransformationMirror: "Dicerminkan horizontal",
    _T.TransformationFlip: "Dibalik vertikal",
    _T.TransformationRotate180: "Diputar 180°",
    _T.TransformationRotate90: "Diputar 90°",
    _T.TransformationRotate270: "Diputar 270°",
    _T.TransformationMirrorAndRotate90: "Dicerminkan + diputar 90°",
    _T.TransformationFlipAndRotate90: "Dibalik + diputar 90°",
}

_ROTATE_90_OR_270 = {
    _T.TransformationRotate90,
    _T.TransformationRotate270,
    _T.TransformationMirrorAndRotate90,
    _T.TransformationFlipAndRotate90,
}


class ImageReadError(Exception):
    """Galat pembacaan gambar; pesannya sudah berbahasa Indonesia dan siap ditampilkan."""


class MultiPageTiffError(ImageReadError):
    """Dilempar saat berkas TIFF memiliki >1 halaman tetapi page_index belum dipilih."""

    def __init__(self, path: Path, pages: tuple[TiffPageSummary, ...], message: str) -> None:
        super().__init__(message)
        self.path = path
        self.pages = pages


class MultiHduFitsError(ImageReadError):
    """Dilempar saat berkas FITS memiliki >1 HDU gambar tetapi hdu_index belum dipilih."""

    def __init__(
        self,
        path: Path,
        image_hdus: tuple[FitsHduSummary, ...],
        total_hdu_count: int,
        message: str,
    ) -> None:
        super().__init__(message)
        self.path = path
        self.image_hdus = image_hdus
        self.total_hdu_count = total_hdu_count


@dataclass(frozen=True)
class ImageInfo:
    """Informasi berkas ASLI (tidak berubah setelah dibuat)."""

    path: Path
    file_name: str
    file_format: str  # mis. "PNG", "JPEG", "TIFF", "FITS"
    width: int
    height: int
    stored_width: int
    stored_height: int
    channels: int | None  # 1, 3, 4, atau None bila tidak diketahui
    has_alpha: bool
    original_bit_depth: int | None
    original_is_float: bool
    preview_bit_depth: int
    exif_orientation: str
    orientation_applied: bool
    dtype_str: str | None = None
    stored_dtype_str: str | None = None
    page_index: int = 0
    page_count: int = 1
    compression_name: str | None = None
    hdu_index: int = 0
    hdu_count: int = 1
    image_hdu_count: int = 1
    fits_header: FitsHeaderInfo | None = None
    raw_metadata: RawMetadataInfo | None = None


@dataclass(frozen=True)
class LoadedImage:
    """Hasil pembacaan: informasi berkas asli + preview layar + data ilmiah."""

    info: ImageInfo
    preview: QImage
    scientific_data: np.ndarray | None = None
    raw_image_visible: np.ndarray | None = None
    raw_image_full: np.ndarray | None = None
    demosaiced_rgb: np.ndarray | None = None


def supported_extensions() -> tuple[str, ...]:
    """Daftar ekstensi (tanpa titik) yang didukung saat ini."""
    qt_formats = {bytes(f).decode("ascii", "ignore").lower() for f in QImageReader.supportedImageFormats()}
    extensions: list[str] = []
    for qt_name, exts in _QT_EXTENSIONS_BY_FORMAT.items():
        if qt_name in qt_formats:
            for ext in exts:
                if ext not in extensions:
                    extensions.append(ext)
    for ext in (*_TIFF_EXTENSIONS, *_FITS_EXTENSIONS, *_RAW_EXTENSIONS):
        if ext not in extensions:
            extensions.append(ext)
    return tuple(extensions)


def _validate_path(path: Path) -> None:
    """Memeriksa berkas ada, berupa berkas, dan berekstensi yang didukung."""
    if not path.exists():
        raise ImageReadError(f"File tidak ditemukan: {path}")
    if not path.is_file():
        raise ImageReadError(f"Jalur yang dipilih bukan sebuah file gambar: {path}")

    ext = path.suffix.lower().lstrip(".")
    supported = supported_extensions()
    if ext in supported:
        return
    if ext in _TIFF_EXTENSIONS:
        raise ImageReadError("Format TIFF belum dapat dibuka pada konfigurasi saat ini.")
    shown = ", ".join(e.upper() for e in supported)
    ext_text = f".{ext}" if ext else "(tanpa ekstensi)"
    raise ImageReadError(f"Format file {ext_text} belum didukung. Format yang didukung saat ini: {shown}.")


def _describe_format(fmt: QImage.Format) -> tuple[int | None, bool, int | None, bool]:
    """Mengubah format piksel Qt menjadi (kanal, alpha, bit depth, float)."""
    return _FORMAT_TABLE.get(fmt, (None, False, None, False))


def _dtype_str_from_bits(bit_depth: int | None, is_float: bool) -> str | None:
    if bit_depth is None:
        return None
    if is_float:
        return f"float{bit_depth}"
    if bit_depth in (1, 8):
        return "uint8"
    if bit_depth == 16:
        return "uint16"
    if bit_depth == 32:
        return "uint32"
    return f"uint{bit_depth}"


def _qimage_to_scientific_array(
    image: QImage,
    channels: int | None,
    has_alpha: bool,
    bit_depth: int | None,
) -> np.ndarray:
    """Mengekstrak array NumPy ilmiah dari QImage tanpa mengubah jenis citra (mono vs RGB).

    Dipakai untuk format berbasis Qt (PNG/JPEG/BMP) agar menghasilkan
    ``scientific_data`` yang seragam dengan TIFF dan FITS.
    """
    w, h = image.width(), image.height()
    use_16 = bit_depth == 16

    if channels == 1 and not has_alpha:
        if use_16:
            conv = image.convertToFormat(_F.Format_Grayscale16)
            bpl = conv.bytesPerLine() // 2
            arr = np.frombuffer(bytes(conv.constBits()), dtype=np.uint16).reshape(h, bpl)[:, :w].copy()
        else:
            conv = image.convertToFormat(_F.Format_Grayscale8)
            bpl = conv.bytesPerLine()
            arr = np.frombuffer(bytes(conv.constBits()), dtype=np.uint8).reshape(h, bpl)[:, :w].copy()
    elif has_alpha or channels == 4:
        if use_16:
            conv = image.convertToFormat(_F.Format_RGBA64)
            bpl = conv.bytesPerLine() // 2
            arr = np.frombuffer(bytes(conv.constBits()), dtype=np.uint16).reshape(h, bpl // 4, 4)[:, :w, :].copy()
        else:
            conv = image.convertToFormat(_F.Format_RGBA8888)
            bpl = conv.bytesPerLine()
            arr = np.frombuffer(bytes(conv.constBits()), dtype=np.uint8).reshape(h, bpl // 4, 4)[:, :w, :].copy()
    else:
        if use_16:
            conv = image.convertToFormat(_F.Format_RGBA64)
            bpl = conv.bytesPerLine() // 2
            arr = np.frombuffer(bytes(conv.constBits()), dtype=np.uint16).reshape(h, bpl // 4, 4)[:, :w, :3].copy()
        else:
            conv = image.convertToFormat(_F.Format_RGB888)
            bpl = conv.bytesPerLine()
            raw = np.frombuffer(bytes(conv.constBits()), dtype=np.uint8).reshape(h, bpl)[:, : w * 3]
            arr = raw.reshape(h, w, 3).copy()

    arr.flags.writeable = False
    return arr


def _to_display_preview(image: QImage, channels: int | None, has_alpha: bool) -> QImage:
    """Membuat salinan 8-bit untuk layar TANPA mengubah jenis citra."""
    if channels == 1 and not has_alpha:
        target = QImage.Format.Format_Grayscale8
    elif has_alpha or image.hasAlphaChannel():
        target = QImage.Format.Format_RGBA8888
    else:
        target = QImage.Format.Format_RGB888
    if image.format() == target:
        return image
    return image.convertToFormat(target)


def inspect_image_header(path: str | Path) -> ImageInfo:
    """Membaca metadata dan struktur berkas TANPA memuat seluruh piksel ke RAM (*Lazy Loading*).

    Raises:
        MultiPageTiffError: bila berkas TIFF memiliki >1 halaman.
        MultiHduFitsError: bila berkas FITS memiliki >1 HDU gambar.
        ImageReadError: bila berkas tidak ada, format tidak didukung, atau header rusak.
    """
    path = Path(path)
    _validate_path(path)
    ext = path.suffix.lower().lstrip(".")

    if ext in _TIFF_EXTENSIONS:
        from hilalone.input_manager.adapters.tiff_reader import inspect_tiff_pages

        pages = inspect_tiff_pages(path)
        if len(pages) > 1:
            raise MultiPageTiffError(
                path=path,
                pages=tuple(pages),
                message=(
                    f"File TIFF '{path.name}' memiliki {len(pages)} halaman. "
                    "Pilih halaman spesifik atau gunakan TIFF satu halaman untuk sequence."
                ),
            )
        p0 = pages[0]
        dt = np.dtype(p0.dtype_str)
        return ImageInfo(
            path=path,
            file_name=path.name,
            file_format="TIFF",
            width=p0.width,
            height=p0.height,
            stored_width=p0.width,
            stored_height=p0.height,
            channels=p0.channels,
            has_alpha=p0.channels == 4,
            original_bit_depth=dt.itemsize * 8,
            original_is_float=bool(np.issubdtype(dt, np.floating)),
            preview_bit_depth=PREVIEW_BIT_DEPTH,
            exif_orientation="Normal (tanpa rotasi)",
            orientation_applied=False,
            dtype_str=p0.dtype_str,
            stored_dtype_str=p0.dtype_str,
            page_index=0,
            page_count=1,
            compression_name=p0.compression_name,
        )

    if ext in _FITS_EXTENSIONS:
        from astropy.io import fits

        from hilalone.input_manager.adapters.fits_reader import (
            _extract_header_info,
            inspect_fits_hdus,
        )

        all_hdus = inspect_fits_hdus(path)
        image_hdus = [h for h in all_hdus if h.is_image]
        if not image_hdus:
            raise ImageReadError(
                f"File FITS '{path.name}' tidak memiliki HDU yang berisi citra 2D/3D yang didukung."
            )
        if len(image_hdus) > 1:
            raise MultiHduFitsError(
                path=path,
                image_hdus=tuple(image_hdus),
                total_hdu_count=len(all_hdus),
                message=(
                    f"File FITS '{path.name}' memiliki {len(image_hdus)} HDU gambar "
                    f"(dari total {len(all_hdus)} HDU)."
                ),
            )
        h0 = image_hdus[0]
        with fits.open(path, mode="readonly", memmap=False, do_not_scale_image_data=True) as hdul:
            raw_hdr = hdul[h0.index].header.copy()

        # Tentukan dtype hasil interpretasi tanpa memuat array piksel penuh
        bitpix = raw_hdr.get("BITPIX", 16)
        bzero = raw_hdr.get("BZERO", None)
        bscale = raw_hdr.get("BSCALE", None)
        eff_bscale = 1.0 if bscale is None else float(bscale)
        eff_bzero = 0.0 if bzero is None else float(bzero)
        if bitpix == 16 and eff_bscale == 1.0 and eff_bzero == 32768.0:
            interp_dt = np.dtype(np.uint16)
        elif eff_bscale != 1.0 or eff_bzero != 0.0:
            interp_dt = np.dtype(np.float32 if abs(int(bitpix)) <= 16 else np.float64)
        else:
            bp_map = {8: np.uint8, 16: np.int16, 32: np.int32, 64: np.int64, -32: np.float32, -64: np.float64}
            interp_dt = np.dtype(bp_map.get(int(bitpix), np.float32))

        hdr_info = _extract_header_info(raw_hdr, interp_dt)
        name_tag = f" [{h0.name}]" if h0.name else ""
        fmt_label = (
            f"FITS (HDU #{h0.index}{name_tag} dari {len(all_hdus)} HDU)"
            if len(all_hdus) > 1
            else f"FITS (HDU #{h0.index}{name_tag})"
        )
        return ImageInfo(
            path=path,
            file_name=path.name,
            file_format=fmt_label,
            width=h0.width,
            height=h0.height,
            stored_width=h0.width,
            stored_height=h0.height,
            channels=h0.channels,
            has_alpha=h0.channels == 4,
            original_bit_depth=interp_dt.itemsize * 8,
            original_is_float=bool(np.issubdtype(interp_dt, np.floating)),
            preview_bit_depth=PREVIEW_BIT_DEPTH,
            exif_orientation="Normal (tanpa rotasi)",
            orientation_applied=False,
            dtype_str=str(interp_dt),
            stored_dtype_str=hdr_info.stored_dtype_str,
            hdu_index=h0.index,
            hdu_count=len(all_hdus),
            image_hdu_count=1,
            fits_header=hdr_info,
        )

    if ext in _RAW_EXTENSIONS:
        from hilalone.input_manager.adapters.raw_reader import inspect_raw_header

        raw_meta, dtype_str, channels = inspect_raw_header(path)
        dt = np.dtype(dtype_str)
        ext_upper = ext.upper()
        fmt_label = f"RAW ({ext_upper})"
        return ImageInfo(
            path=path,
            file_name=path.name,
            file_format=fmt_label,
            width=raw_meta.visible_width,
            height=raw_meta.visible_height,
            stored_width=raw_meta.raw_width or raw_meta.visible_width,
            stored_height=raw_meta.raw_height or raw_meta.visible_height,
            channels=channels,
            has_alpha=False,
            original_bit_depth=dt.itemsize * 8,
            original_is_float=bool(np.issubdtype(dt, np.floating)),
            preview_bit_depth=PREVIEW_BIT_DEPTH,
            exif_orientation="Normal (tanpa rotasi)",
            orientation_applied=False,
            dtype_str=dtype_str,
            stored_dtype_str=dtype_str,
            raw_metadata=raw_meta,
        )

    # Format berbasis Qt (PNG/JPEG/BMP): hanya baca header melalui QImageReader tanpa .read()
    meta = QImageReader(str(path))
    meta.setAutoTransform(False)
    if not meta.canRead():
        raise ImageReadError(
            f"File tidak dapat dibaca: isi file bukan gambar yang valid atau file rusak ({path.name})."
        )
    stored_size = meta.size()
    if not stored_size.isValid() or stored_size.width() <= 0 or stored_size.height() <= 0:
        raise ImageReadError(f"Header gambar '{path.name}' tidak memiliki ukuran yang valid.")

    original_orientation = meta.transformation()
    qt_format_name = bytes(meta.format()).decode("ascii", "ignore").upper()
    channels, has_alpha, bit_depth, is_float = _describe_format(meta.imageFormat())

    stored_w, stored_h = stored_size.width(), stored_size.height()
    if original_orientation in _ROTATE_90_OR_270:
        disp_w, disp_h = stored_h, stored_w
    else:
        disp_w, disp_h = stored_w, stored_h

    orientation_label = _ORIENTATION_LABELS.get(original_orientation, "Tidak diketahui")
    dtype_str = _dtype_str_from_bits(bit_depth, is_float)
    return ImageInfo(
        path=path,
        file_name=path.name,
        file_format=qt_format_name or path.suffix.lstrip(".").upper(),
        width=disp_w,
        height=disp_h,
        stored_width=stored_w,
        stored_height=stored_h,
        channels=channels,
        has_alpha=has_alpha,
        original_bit_depth=bit_depth,
        original_is_float=is_float,
        preview_bit_depth=PREVIEW_BIT_DEPTH,
        exif_orientation=orientation_label,
        orientation_applied=original_orientation != _T.TransformationNone,
        dtype_str=dtype_str,
        stored_dtype_str=dtype_str,
    )


def _read_tiff_via_adapter(path: Path, page_index: int | None) -> LoadedImage:
    """Membaca berkas TIFF melalui adapter tifffile dan membungkusnya ke LoadedImage."""
    from hilalone.input_manager.adapters.tiff_reader import read_tiff

    result = read_tiff(path, page_index=page_index)
    if result.page_count > 1:
        fmt_label = f"TIFF (Halaman {result.page_index + 1}/{result.page_count})"
    else:
        fmt_label = "TIFF"

    info = ImageInfo(
        path=path,
        file_name=path.name,
        file_format=fmt_label,
        width=result.width,
        height=result.height,
        stored_width=result.stored_width,
        stored_height=result.stored_height,
        channels=result.channels,
        has_alpha=result.has_alpha,
        original_bit_depth=result.original_bit_depth,
        original_is_float=result.original_is_float,
        preview_bit_depth=PREVIEW_BIT_DEPTH,
        exif_orientation="Normal (tanpa rotasi)",
        orientation_applied=False,
        dtype_str=result.dtype_str,
        stored_dtype_str=result.dtype_str,
        page_index=result.page_index,
        page_count=result.page_count,
        compression_name=result.compression_name,
    )
    return LoadedImage(
        info=info,
        preview=result.preview,
        scientific_data=result.scientific_data,
    )


def _read_fits_via_adapter(path: Path, hdu_index: int | None) -> LoadedImage:
    """Membaca berkas FITS melalui adapter astropy.io.fits dan membungkusnya ke LoadedImage."""
    from hilalone.input_manager.adapters.fits_reader import read_fits

    result = read_fits(path, hdu_index=hdu_index)
    name_tag = f" [{result.hdu_name}]" if result.hdu_name else ""
    if result.total_hdu_count > 1:
        fmt_label = f"FITS (HDU #{result.hdu_index}{name_tag} dari {result.total_hdu_count} HDU)"
    else:
        fmt_label = f"FITS (HDU #{result.hdu_index}{name_tag})"

    info = ImageInfo(
        path=path,
        file_name=path.name,
        file_format=fmt_label,
        width=result.width,
        height=result.height,
        stored_width=result.stored_width,
        stored_height=result.stored_height,
        channels=result.channels,
        has_alpha=result.has_alpha,
        original_bit_depth=result.original_bit_depth,
        original_is_float=result.original_is_float,
        preview_bit_depth=PREVIEW_BIT_DEPTH,
        exif_orientation="Normal (tanpa rotasi)",
        orientation_applied=False,
        dtype_str=result.dtype_str,
        stored_dtype_str=result.stored_dtype_str,
        hdu_index=result.hdu_index,
        hdu_count=result.total_hdu_count,
        image_hdu_count=result.image_hdu_count,
        fits_header=result.header_info,
    )
    return LoadedImage(
        info=info,
        preview=result.preview,
        scientific_data=result.scientific_data,
    )


def _read_raw_via_adapter(path: Path) -> LoadedImage:
    """Membaca berkas Camera RAW melalui adapter rawpy dan membungkusnya ke LoadedImage."""
    from hilalone.input_manager.adapters.raw_reader import read_raw

    result = read_raw(path)
    ext_upper = path.suffix.lower().lstrip(".").upper()
    fmt_label = f"RAW ({ext_upper})"

    info = ImageInfo(
        path=path,
        file_name=path.name,
        file_format=fmt_label,
        width=result.width,
        height=result.height,
        stored_width=result.stored_width,
        stored_height=result.stored_height,
        channels=result.channels,
        has_alpha=result.has_alpha,
        original_bit_depth=result.original_bit_depth,
        original_is_float=result.original_is_float,
        preview_bit_depth=PREVIEW_BIT_DEPTH,
        exif_orientation="Normal (tanpa rotasi)",
        orientation_applied=False,
        dtype_str=result.dtype_str,
        stored_dtype_str=result.stored_dtype_str,
        raw_metadata=result.metadata,
    )
    return LoadedImage(
        info=info,
        preview=result.preview,
        scientific_data=result.scientific_data,
        raw_image_visible=result.raw_image_visible,
        raw_image_full=result.raw_image_full,
        demosaiced_rgb=result.demosaiced_rgb,
    )


def read_image(
    path: str | Path,
    page_index: int | None = None,
    hdu_index: int | None = None,
) -> LoadedImage:
    """Membaca gambar (mode baca saja) dan mengembalikan info asli + preview + scientific_data."""
    path = Path(path)
    _validate_path(path)

    ext = path.suffix.lower().lstrip(".")
    if ext in _TIFF_EXTENSIONS:
        return _read_tiff_via_adapter(path, page_index=page_index)
    if ext in _FITS_EXTENSIONS:
        return _read_fits_via_adapter(path, hdu_index=hdu_index)
    if ext in _RAW_EXTENSIONS:
        return _read_raw_via_adapter(path)

    # Pembaca #1: tanpa rotasi otomatis untuk mengambil metadata dan scientific_data asli
    meta = QImageReader(str(path))
    meta.setAutoTransform(False)
    if not meta.canRead():
        raise ImageReadError(
            f"File tidak dapat dibaca: isi file bukan gambar yang valid atau file rusak ({path.name})."
        )
    stored_size = meta.size()
    original_orientation = meta.transformation()
    qt_format_name = bytes(meta.format()).decode("ascii", "ignore").upper()
    channels, has_alpha, bit_depth, is_float = _describe_format(meta.imageFormat())
    raw_qimg = meta.read()
    if raw_qimg.isNull():
        raise ImageReadError(
            f"Gagal membaca data gambar '{path.name}': file kemungkinan rusak atau tidak lengkap, "
            f"atau ukurannya terlalu besar untuk dimuat. Detail Qt: {meta.errorString()}"
        )
    if raw_qimg.width() <= 0 or raw_qimg.height() <= 0:
        raise ImageReadError(f"Gambar '{path.name}' memiliki ukuran nol dan tidak dapat ditampilkan.")

    has_alpha = has_alpha or (channels is None and raw_qimg.hasAlphaChannel())
    scientific = _qimage_to_scientific_array(raw_qimg, channels, has_alpha, bit_depth)

    # Pembaca #2 (preview): rotasi EXIF diterapkan HANYA pada salinan preview di memori
    if original_orientation != _T.TransformationNone:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        oriented_qimg = reader.read()
        if oriented_qimg.isNull():
            oriented_qimg = raw_qimg
    else:
        oriented_qimg = raw_qimg

    preview = _to_display_preview(oriented_qimg, channels, has_alpha)

    if stored_size.isValid():
        stored_w, stored_h = stored_size.width(), stored_size.height()
    else:
        stored_w, stored_h = raw_qimg.width(), raw_qimg.height()

    orientation_label = _ORIENTATION_LABELS.get(original_orientation, "Tidak diketahui")
    dtype_str = str(scientific.dtype)
    info = ImageInfo(
        path=path,
        file_name=path.name,
        file_format=qt_format_name or path.suffix.lstrip(".").upper(),
        width=preview.width(),
        height=preview.height(),
        stored_width=stored_w,
        stored_height=stored_h,
        channels=channels,
        has_alpha=has_alpha,
        original_bit_depth=bit_depth,
        original_is_float=is_float,
        preview_bit_depth=PREVIEW_BIT_DEPTH,
        exif_orientation=orientation_label,
        orientation_applied=original_orientation != _T.TransformationNone,
        dtype_str=dtype_str,
        stored_dtype_str=dtype_str,
    )
    return LoadedImage(info=info, preview=preview, scientific_data=scientific)
