"""Pembaca berkas FITS astronomi HILALONE berbasis astropy.io.fits (mode baca saja).

Prinsip utama modul ini:
  1. **Keamanan Berkas Sumber**:
     Berkas FITS dibuka hanya dalam mode ``readonly`` dengan ``memmap=False``.
     Begitu array piksel dan metadata HDU yang dibutuhkan disalin ke memori,
     blok ``with fits.open(...)`` selesai dan file handle langsung ditutup.
  2. **Deteksi Seluruh HDU & Pemilihan Image HDU**:
     Tidak mengasumsikan Primary HDU (indeks 0) selalu berisi gambar.
     - Jika hanya ada 1 HDU yang berisi gambar di seluruh berkas, HDU tersebut
       dipilih otomatis (dan indeks HDU-nya dicatat secara jujur).
     - Jika terdapat beberapa HDU gambar dan ``hdu_index`` belum diberikan,
       modul melempar ``MultiHduFitsError`` berisi daftar seluruh HDU gambar
       agar pengguna memilihnya secara eksplisit.
  3. **Integritas Data Ilmiah (Stored vs Physical/Scaled)**:
     - Mencatat ``BITPIX``, ``BSCALE``, dan ``BZERO`` asli dari header sebelum
       scaling diterapkan (``stored_dtype_str`` vs ``dtype_str``).
     - Mendukung ``int16``, ``uint16`` (konvensi ``BITPIX=16, BZERO=32768, BSCALE=1``),
       ``int32``, ``uint8``, ``float32``, dan ``float64``.
     - Tidak melakukan normalisasi permanen; array ilmiah dikunci
       (``writeable = False``).
  4. **Pemisahan Display Preview**:
     ``preview`` adalah ``QImage`` 8-bit terpisah yang dibuat melalui
     ``preview_builder.array_to_preview_qimage`` tanpa menyentuh ``scientific_data``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits
from PySide6.QtGui import QImage

from hilalone.input_manager.preview_builder import PREVIEW_BIT_DEPTH, array_to_preview_qimage

UNAVAILABLE_TEXT = "Tidak tersedia"

# Pemetaan BITPIX standar FITS ke nama tipe data tersimpan (stored dtype).
_BITPIX_TO_STORED_DTYPE: dict[int, str] = {
    8: "uint8",
    16: "int16",
    32: "int32",
    64: "int64",
    -32: "float32",
    -64: "float64",
}


@dataclass(frozen=True)
class FitsHeaderInfo:
    """Metadata terpilih dari Header FITS (keyword yang absen bernilai None)."""

    naxis: int | None
    naxis1: int | None
    naxis2: int | None
    naxis3: int | None
    bitpix: int | None
    bzero: float | int | None
    bscale: float | int | None
    date_obs: str | None
    exptime: float | str | None
    instrume: str | None
    gain: float | int | str | None
    telescop: str | None
    stored_dtype_str: str
    interpreted_dtype_str: str
    scaling_applied: bool
    is_uint16_offset_convention: bool

    def to_display_dict(self) -> dict[str, str]:
        """Mengembalikan pasangan keyword -> teks tampilan ('Tidak tersedia' bila None)."""

        def _fmt(val: Any) -> str:
            if val is None or val == "":
                return UNAVAILABLE_TEXT
            return str(val)

        return {
            "NAXIS": _fmt(self.naxis),
            "NAXIS1": _fmt(self.naxis1),
            "NAXIS2": _fmt(self.naxis2),
            "BITPIX": _fmt(self.bitpix),
            "BZERO": _fmt(self.bzero),
            "BSCALE": _fmt(self.bscale),
            "DATE-OBS": _fmt(self.date_obs),
            "EXPTIME": _fmt(self.exptime),
            "INSTRUME": _fmt(self.instrume),
            "GAIN": _fmt(self.gain),
            "TELESCOP": _fmt(self.telescop),
        }

    def summary_text(self) -> str:
        """Ringkasan multibaris untuk ditampilkan pada panel informasi GUI."""
        d = self.to_display_dict()
        if self.is_uint16_offset_convention:
            scale_note = f"Ya (uint16 standar FITS: stored {self.stored_dtype_str} -> {self.interpreted_dtype_str})"
        elif self.scaling_applied:
            scale_note = f"Ya (stored {self.stored_dtype_str} -> physical {self.interpreted_dtype_str})"
        else:
            scale_note = f"Tidak (stored = interpreted: {self.interpreted_dtype_str})"

        lines = [
            f"BITPIX: {d['BITPIX']} | NAXIS: {d['NAXIS']} ({d['NAXIS1']}×{d['NAXIS2']})",
            f"BZERO: {d['BZERO']} | BSCALE: {d['BSCALE']}",
            f"Scaling: {scale_note}",
            f"DATE-OBS: {d['DATE-OBS']}",
            f"EXPTIME: {d['EXPTIME']} | GAIN: {d['GAIN']}",
            f"INSTRUME: {d['INSTRUME']}",
            f"TELESCOP: {d['TELESCOP']}",
        ]
        return "\n".join(lines)


@dataclass(frozen=True)
class FitsHduSummary:
    """Ringkasan satu HDU di dalam berkas FITS."""

    index: int
    name: str
    hdu_type: str
    is_image: bool
    shape: tuple[int, ...]
    width: int
    height: int
    channels: int
    bitpix: int | None
    bzero: float | int | None
    bscale: float | int | None

    def label(self) -> str:
        """Teks ringkas untuk dialog pemilihan HDU."""
        name_part = f" [{self.name}]" if self.name else ""
        ch_text = {1: "Monokrom", 3: "RGB"}.get(self.channels, f"{self.channels} kanal")
        return (
            f"HDU #{self.index}{name_part} ({self.hdu_type}): "
            f"{self.width} × {self.height} px, BITPIX={self.bitpix}, {ch_text}"
        )


@dataclass(frozen=True)
class FitsReadResult:
    """Hasil pembacaan satu Image HDU FITS beserta metadata dan preview layarnya."""

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
    stored_dtype_str: str
    hdu_index: int
    total_hdu_count: int
    image_hdu_count: int
    hdu_name: str
    header_info: FitsHeaderInfo


def _classify_image_shape(shape: tuple[int, ...]) -> tuple[int, int, int, bool] | None:
    """Memeriksa apakah shape array FITS merupakan citra 2D atau 3D RGB.

    Di FITS/NumPy, array 2D berurutan ``(NAXIS2, NAXIS1)`` = ``(height, width)``.
    Array 3D FITS umumnya ``(3, NAXIS2, NAXIS1)`` (planar) atau ``(NAXIS2, NAXIS1, 3)``.

    Returns:
        Tuple ``(height, width, channels, is_planar)`` bila valid, atau ``None`` bila bukan citra.
    """
    if len(shape) == 2:
        h, w = shape
        if h > 0 and w > 0:
            return h, w, 1, False
        return None
    if len(shape) == 3:
        if shape[0] in (1, 3, 4) and shape[2] not in (1, 3, 4):
            c, h, w = shape
            if h > 0 and w > 0:
                return h, w, c, True
        if shape[2] in (1, 3, 4):
            h, w, c = shape
            if h > 0 and w > 0:
                return h, w, c, False
        if shape[0] in (1, 3, 4):
            c, h, w = shape
            if h > 0 and w > 0:
                return h, w, c, True
    return None


def _is_image_like_hdu(hdu: Any) -> bool:
    """True bila HDU bertipe HDU citra (PrimaryHDU, ImageHDU, CompImageHDU)."""
    return isinstance(hdu, (fits.PrimaryHDU, fits.ImageHDU, fits.CompImageHDU))


def _header_shape(header: fits.Header) -> tuple[int, ...]:
    """Membaca tuple shape menurut urutan NumPy (NAXISn, ..., NAXIS2, NAXIS1) langsung dari header."""
    naxis = int(header.get("NAXIS", 0) or 0)
    if naxis <= 0:
        return ()
    dims: list[int] = []
    for axis in range(naxis, 0, -1):
        dims.append(int(header.get(f"NAXIS{axis}", 0) or 0))
    return tuple(dims)


def _extract_header_info(
    raw_header: fits.Header,
    interpreted_dtype: np.dtype[Any],
) -> FitsHeaderInfo:
    """Mengekstrak keyword penting dari header FITS asli secara aman."""
    naxis = raw_header.get("NAXIS", None)
    naxis1 = raw_header.get("NAXIS1", None)
    naxis2 = raw_header.get("NAXIS2", None)
    naxis3 = raw_header.get("NAXIS3", None)
    bitpix = raw_header.get("BITPIX", None)
    bzero = raw_header.get("BZERO", None)
    bscale = raw_header.get("BSCALE", None)

    stored_dtype_str = _BITPIX_TO_STORED_DTYPE.get(int(bitpix), f"bitpix_{bitpix}") if bitpix is not None else "tidak_diketahui"
    interp_str = str(interpreted_dtype)

    eff_bscale = 1.0 if bscale is None else float(bscale)
    eff_bzero = 0.0 if bzero is None else float(bzero)
    is_uint16_conv = (
        bitpix == 16
        and eff_bscale == 1.0
        and eff_bzero == 32768.0
        and interpreted_dtype == np.uint16
    )
    scaling_applied = (eff_bscale != 1.0) or (eff_bzero != 0.0)

    return FitsHeaderInfo(
        naxis=int(naxis) if naxis is not None else None,
        naxis1=int(naxis1) if naxis1 is not None else None,
        naxis2=int(naxis2) if naxis2 is not None else None,
        naxis3=int(naxis3) if naxis3 is not None else None,
        bitpix=int(bitpix) if bitpix is not None else None,
        bzero=bzero,
        bscale=bscale,
        date_obs=raw_header.get("DATE-OBS", None),
        exptime=raw_header.get("EXPTIME", None),
        instrume=raw_header.get("INSTRUME", None),
        gain=raw_header.get("GAIN", None),
        telescop=raw_header.get("TELESCOP", None),
        stored_dtype_str=stored_dtype_str,
        interpreted_dtype_str=interp_str,
        scaling_applied=scaling_applied,
        is_uint16_offset_convention=is_uint16_conv,
    )


def inspect_fits_hdus(path: str | Path) -> list[FitsHduSummary]:
    """Memeriksa seluruh HDU di dalam berkas FITS (mode readonly, memmap=False)."""
    from hilalone.input_manager.image_reader import ImageReadError

    path = Path(path)
    if not path.exists():
        raise ImageReadError(f"File tidak ditemukan: {path}")
    if not path.is_file():
        raise ImageReadError(f"Jalur yang dipilih bukan sebuah file gambar: {path}")

    try:
        with fits.open(path, mode="readonly", memmap=False) as hdul:
            if len(hdul) == 0:
                raise ImageReadError(f"File FITS '{path.name}' tidak memiliki HDU.")
            summaries: list[FitsHduSummary] = []
            for idx, hdu in enumerate(hdul):
                hdr = hdu.header
                shape = _header_shape(hdr)
                classified = _classify_image_shape(shape) if _is_image_like_hdu(hdu) else None
                if classified is not None:
                    h, w, ch, _ = classified
                    is_img = True
                else:
                    h, w, ch = 0, 0, 0
                    is_img = False
                summaries.append(
                    FitsHduSummary(
                        index=idx,
                        name=str(getattr(hdu, "name", "") or ""),
                        hdu_type=type(hdu).__name__,
                        is_image=is_img,
                        shape=shape,
                        width=w,
                        height=h,
                        channels=ch,
                        bitpix=hdr.get("BITPIX", None),
                        bzero=hdr.get("BZERO", None),
                        bscale=hdr.get("BSCALE", None),
                    )
                )
            return summaries
    except ImageReadError:
        raise
    except Exception as err:
        raise ImageReadError(
            f"File '{path.name}' bukan berkas FITS yang valid atau isinya rusak. Detail: {err}"
        ) from err


def read_fits(path: str | Path, hdu_index: int | None = None) -> FitsReadResult:
    """Membaca satu HDU citra dari berkas FITS secara aman (readonly, memmap=False).

    Aturan pemilihan HDU:
      * Bila ``hdu_index`` tidak diberikan (``None``):
        - Jika hanya ada 1 HDU citra di dalam berkas, HDU tersebut dipilih otomatis.
        - Jika ada >1 HDU citra, ``MultiHduFitsError`` dilempar agar pengguna memilih.
        - Jika tidak ada HDU citra sama sekali, ``ImageReadError`` dilempar.
      * Bila ``hdu_index`` diberikan, HDU pada indeks tersebut divalidasi dan dibaca.
    """
    from hilalone.input_manager.image_reader import ImageReadError, MultiHduFitsError

    path = Path(path)
    all_hdus = inspect_fits_hdus(path)
    total_count = len(all_hdus)
    image_hdus = [h for h in all_hdus if h.is_image]

    if not image_hdus:
        raise ImageReadError(
            f"File FITS '{path.name}' ({total_count} HDU) tidak memiliki HDU yang berisi citra 2D/3D yang didukung."
        )

    if hdu_index is None:
        if len(image_hdus) == 1:
            chosen_index = image_hdus[0].index
        else:
            raise MultiHduFitsError(
                path=path,
                image_hdus=tuple(image_hdus),
                total_hdu_count=total_count,
                message=(
                    f"File FITS '{path.name}' memiliki {len(image_hdus)} HDU gambar "
                    f"(dari total {total_count} HDU). Silakan pilih HDU yang ingin dibuka."
                ),
            )
    else:
        chosen_index = int(hdu_index)
        if chosen_index < 0 or chosen_index >= total_count:
            raise ImageReadError(
                f"Indeks HDU FITS tidak valid: HDU #{chosen_index} diminta, "
                f"tetapi file '{path.name}' hanya memiliki {total_count} HDU (indeks 0..{total_count - 1})."
            )
        if not all_hdus[chosen_index].is_image:
            raise ImageReadError(
                f"HDU #{chosen_index} pada '{path.name}' tidak berisi citra gambar yang valid."
            )

    try:
        # Pertama: salin header mentah sebelum Astropy menghapus BZERO/BSCALE saat scaling
        with fits.open(path, mode="readonly", memmap=False, do_not_scale_image_data=True) as hdul_raw:
            raw_header = hdul_raw[chosen_index].header.copy()

        # Kedua: baca data ilmiah dengan interpretasi standar FITS (termasuk uint16 BZERO=32768)
        with fits.open(
            path,
            mode="readonly",
            memmap=False,
            do_not_scale_image_data=False,
            uint=True,
        ) as hdul:
            hdu = hdul[chosen_index]
            if hdu.data is None:
                raise ImageReadError(f"HDU #{chosen_index} pada '{path.name}' tidak memiliki data piksel.")
            # Salin ke array NumPy dengan native byte order (=) dan lepaskan dari file handle
            raw_data = np.array(hdu.data, copy=True)
            native_dtype = raw_data.dtype.newbyteorder("=")
            data_native = np.ascontiguousarray(raw_data.astype(native_dtype, copy=False))
            hdu_name = str(getattr(hdu, "name", "") or "")
    except ImageReadError:
        raise
    except Exception as err:
        raise ImageReadError(f"Gagal membaca data FITS '{path.name}' pada HDU #{chosen_index}: {err}") from err

    classified = _classify_image_shape(tuple(data_native.shape))
    if classified is None:
        raise ImageReadError(
            f"Dimensi array FITS {data_native.shape} pada HDU #{chosen_index} tidak didukung."
        )
    h, w, ch, is_planar = classified

    # Verifikasi konsistensi terhadap NAXIS1 (lebar) dan NAXIS2 (tinggi) di header bila 2D
    naxis1 = raw_header.get("NAXIS1", None)
    naxis2 = raw_header.get("NAXIS2", None)
    if data_native.ndim == 2 and naxis1 is not None and naxis2 is not None:
        if (h, w) != (int(naxis2), int(naxis1)):
            raise ImageReadError(
                f"Ketidaksesuaian dimensi FITS pada '{path.name}': header menyatakan "
                f"NAXIS1={naxis1}, NAXIS2={naxis2}, tetapi array berukuran {data_native.shape}."
            )

    if is_planar:
        scientific = np.ascontiguousarray(np.moveaxis(data_native, 0, -1))
    elif data_native.ndim == 3 and data_native.shape[2] == 1:
        scientific = np.ascontiguousarray(data_native[:, :, 0])
    else:
        scientific = data_native

    # Kunci array ilmiah agar tidak pernah termodifikasi di memori
    scientific.flags.writeable = False

    header_info = _extract_header_info(raw_header, scientific.dtype)
    preview = array_to_preview_qimage(scientific)

    dtype = scientific.dtype
    bit_depth = dtype.itemsize * 8
    is_float = bool(np.issubdtype(dtype, np.floating))
    has_alpha = ch == 4

    return FitsReadResult(
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
        stored_dtype_str=header_info.stored_dtype_str,
        hdu_index=chosen_index,
        total_hdu_count=total_count,
        image_hdu_count=len(image_hdus),
        hdu_name=hdu_name,
        header_info=header_info,
    )
