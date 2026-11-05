"""Pembaca gambar HILALONE v0.1 (hanya baca).

Modul ini menghasilkan TIGA komponen yang dipisahkan dengan jelas:
  * ``ImageInfo``       : fakta tentang berkas ASLI (ukuran tersimpan, bit depth
                          asli, dtype, jumlah kanal, orientasi EXIF asli, serta
                          informasi halaman bila multi-page TIFF).
  * ``scientific_data`` : array NumPy asli tanpa perubahan nilai piksel atau
                          normalisasi permanen (diisi oleh adapter ilmiah seperti
                          ``tiff_reader``).
  * ``preview``         : salinan ``QImage`` 8-bit di memori untuk TAMPILAN LAYAR
                          saja. Preview bukan data ilmiah.

Berkas sumber hanya dibuka untuk dibaca; tidak pernah diubah atau ditimpa.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtGui import QImage, QImageIOHandler, QImageReader

if TYPE_CHECKING:
    from hilalone.input_manager.adapters.tiff_reader import TiffPageSummary

# Ekstensi yang ditangani melalui QImageReader (Qt).
_QT_EXTENSIONS_BY_FORMAT: dict[str, tuple[str, ...]] = {
    "png": ("png",),
    "jpeg": ("jpg", "jpeg"),
    "jpg": ("jpg", "jpeg"),
    "bmp": ("bmp",),
}
# Ekstensi TIFF kini selalu didukung melalui adapter ilmiah tifffile.
_TIFF_EXTENSIONS = ("tif", "tiff")

# Bit depth preview layar (selalu 8-bit pada v0.1).
PREVIEW_BIT_DEPTH = 8

_F = QImage.Format

# Tabel format Qt -> (jumlah kanal, ada alpha, bit per kanal, bilangan riil/float).
# None berarti "tidak dapat dipastikan" (tidak ditebak agar tetap jujur).
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

# Nama orientasi untuk ditampilkan kepada pengguna.
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


class ImageReadError(Exception):
    """Galat pembacaan gambar; pesannya sudah berbahasa Indonesia dan siap ditampilkan."""


class MultiPageTiffError(ImageReadError):
    """Dilempar saat berkas TIFF memiliki >1 halaman tetapi page_index belum dipilih."""

    def __init__(self, path: Path, pages: tuple[TiffPageSummary, ...], message: str) -> None:
        super().__init__(message)
        self.path = path
        self.pages = pages


@dataclass(frozen=True)
class ImageInfo:
    """Informasi berkas ASLI (tidak berubah setelah dibuat).

    ``stored_width/height`` adalah ukuran yang tersimpan di berkas, sedangkan
    ``width/height`` adalah ukuran preview setelah orientasi EXIF diterapkan
    (keduanya sama bila tidak ada rotasi 90°/270°).
    """

    path: Path
    file_name: str
    file_format: str  # nama format hasil deteksi isi berkas, mis. "PNG", "JPEG", "TIFF"
    width: int
    height: int
    stored_width: int
    stored_height: int
    channels: int | None  # 1, 3, 4, atau None bila tidak diketahui
    has_alpha: bool
    original_bit_depth: int | None  # bit per kanal pada berkas asli
    original_is_float: bool
    preview_bit_depth: int
    exif_orientation: str  # orientasi ASLI yang tercatat pada berkas
    orientation_applied: bool  # True bila preview diputar/dicerminkan
    dtype_str: str | None = None
    page_index: int = 0
    page_count: int = 1
    compression_name: str | None = None


@dataclass(frozen=True)
class LoadedImage:
    """Hasil pembacaan: informasi berkas asli + preview layar + data ilmiah (bila ada)."""

    info: ImageInfo
    preview: QImage
    scientific_data: np.ndarray | None = None


def supported_extensions() -> tuple[str, ...]:
    """Daftar ekstensi (tanpa titik) yang didukung saat ini.

    Format PNG/JPG/BMP diperiksa lewat ``QImageReader.supportedImageFormats()``,
    sedangkan ``tif`` dan ``tiff`` didukung penuh lewat ``tifffile``.
    """
    qt_formats = {bytes(f).decode("ascii", "ignore").lower() for f in QImageReader.supportedImageFormats()}
    extensions: list[str] = []
    for qt_name, exts in _QT_EXTENSIONS_BY_FORMAT.items():
        if qt_name in qt_formats:
            for ext in exts:
                if ext not in extensions:
                    extensions.append(ext)
    for ext in _TIFF_EXTENSIONS:
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
        raise ImageReadError(
            "Format TIFF belum dapat dibuka pada konfigurasi saat ini."
        )
    shown = ", ".join(e.upper() for e in supported)
    ext_text = f".{ext}" if ext else "(tanpa ekstensi)"
    raise ImageReadError(f"Format file {ext_text} belum didukung. Format yang didukung saat ini: {shown}.")


def _describe_format(fmt: QImage.Format) -> tuple[int | None, bool, int | None, bool]:
    """Mengubah format piksel Qt menjadi (kanal, alpha, bit depth, float)."""
    return _FORMAT_TABLE.get(fmt, (None, False, None, False))


def _to_display_preview(image: QImage, channels: int | None, has_alpha: bool) -> QImage:
    """Membuat salinan 8-bit untuk layar TANPA mengubah jenis citra.

    Mono tetap mono (Grayscale8), warna tetap warna (RGB). Tidak ada
    konversi RGB -> grayscale. Hanya presisi bit yang diturunkan ke 8-bit,
    dan hanya pada salinan preview ini.
    """
    if channels == 1 and not has_alpha:
        target = QImage.Format.Format_Grayscale8
    elif has_alpha or image.hasAlphaChannel():
        target = QImage.Format.Format_RGBA8888
    else:
        target = QImage.Format.Format_RGB888
    if image.format() == target:
        return image
    return image.convertToFormat(target)


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
        page_index=result.page_index,
        page_count=result.page_count,
        compression_name=result.compression_name,
    )
    return LoadedImage(
        info=info,
        preview=result.preview,
        scientific_data=result.scientific_data,
    )


def read_image(path: str | Path, page_index: int | None = None) -> LoadedImage:
    """Membaca gambar (mode baca saja) dan mengembalikan info asli + preview (+ scientific_data).

    Args:
        path: Jalur berkas gambar.
        page_index: Indeks halaman (khusus TIFF multi-halaman, berbasis 0).
            Bila ``None`` pada TIFF multi-halaman, ``MultiPageTiffError`` dilempar
            agar pemanggil memilih halaman secara eksplisit.

    Raises:
        MultiPageTiffError: bila berkas TIFF memiliki >1 halaman dan ``page_index`` belum dipilih.
        ImageReadError: bila berkas tidak ada, formatnya tidak didukung,
            atau isinya rusak/tidak valid.
    """
    path = Path(path)
    _validate_path(path)

    ext = path.suffix.lower().lstrip(".")
    if ext in _TIFF_EXTENSIONS:
        return _read_tiff_via_adapter(path, page_index=page_index)

    # Pembaca #1 (metadata): TANPA rotasi otomatis, supaya fakta berkas asli
    # (ukuran tersimpan, format piksel, orientasi EXIF) tercatat apa adanya.
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

    # Pembaca #2 (preview): rotasi EXIF diterapkan HANYA pada salinan di memori.
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    image = reader.read()
    if image.isNull():
        raise ImageReadError(
            f"Gagal membaca data gambar '{path.name}': file kemungkinan rusak atau tidak lengkap, "
            f"atau ukurannya terlalu besar untuk dimuat. Detail Qt: {reader.errorString()}"
        )
    if image.width() <= 0 or image.height() <= 0:
        raise ImageReadError(f"Gambar '{path.name}' memiliki ukuran nol dan tidak dapat ditampilkan.")

    has_alpha = has_alpha or (channels is None and image.hasAlphaChannel())
    preview = _to_display_preview(image, channels, has_alpha)

    if stored_size.isValid():
        stored_w, stored_h = stored_size.width(), stored_size.height()
    else:
        stored_w, stored_h = image.width(), image.height()

    orientation_label = _ORIENTATION_LABELS.get(original_orientation, "Tidak diketahui")
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
    )
    return LoadedImage(info=info, preview=preview, scientific_data=None)
