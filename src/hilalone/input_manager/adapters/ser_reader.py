"""Pembaca berkas video astronomi SER (.ser) untuk HILALONE (Sub-Tahap 2D).

Modul ini mengimplementasikan pembaca spesifikasi **Lucam-Recorder SER Format v3**
murni menggunakan modul bawaan Python (``struct``, ``datetime``) dan ``numpy``
tanpa dependency eksternal baru.

Prinsip kejujuran ilmiah (Scientific Data Integrity):
  1. Berkas sumber ``.ser`` hanya dibuka dalam mode baca biner (``"rb"``), tidak
     pernah dimodifikasi, dan handle berkas selalu ditutup kembali seusai baca
     header maupun pembacaan satu frame.
  2. Header 178 byte divalidasi secara ketat: ``FileID`` wajib ``"LUCAM-RECORDER"``,
     dimensi gambar wajib ``> 0``, ``PixelDepthPerPlane`` wajib ``1..16``,
     ``FrameCount`` wajib ``> 0``, dan ``ColorID`` wajib termasuk kode resmi SER
     (tidak pernah menebak format warna untuk ``ColorID`` yang tidak dikenal).
  3. Data piksel ilmiah (``scientific_data``) dipertahankan sesuai struktur asli:
     - ``MONO`` (``ColorID = 0``) tetap berupa array 2D ``(H, W)`` (``uint8``/``uint16``).
     - ``BAYER_*`` (``ColorID = 8, 9, 16, 17, 18..21``) tetap berupa array 2D
       mosaik sensor ``(H, W)`` tanpa demosaicing permanen pada ``scientific_data``.
       Demosaicing bilinear hanya dijalankan secara terpisah untuk membentuk
       ``preview`` layar 8-bit.
     - ``RGB`` (``ColorID = 100``) dan ``BGR`` (``ColorID = 101``) menghasilkan
       array 3D ``(H, W, 3)`` dengan urutan kanal R-G-B yang jujur (dan salinan
       urutan asli tersimpan pada ``raw_stored_data``).
  4. Penanganan eksplisit terhadap anomali sejarah flag ``LittleEndian`` pada
     berkas SER 16-bit (dokumentasi Siril / Lucam-Recorder) melalui parameter
     ``endianness_policy`` (``"siril_default"``, ``"strict_spec"``, ``"force_le"``,
     ``"force_be"``).
  5. Pembacaan frame bekerja secara *lazy* berbasis byte offset
     (``178 + frame_index * frame_size_bytes``) dengan *bounded LRU cache*
     sehingga berkas SER berukuran gigabyte tidak dimuat sekaligus ke RAM.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import struct

import numpy as np
from PySide6.QtGui import QImage

from hilalone.input_manager.image_reader import ImageReadError
from hilalone.input_manager.preview_builder import (
    array_to_preview_qimage as build_display_preview,
)

SER_EXTENSIONS: tuple[str, ...] = ("ser",)
SER_HEADER_SIZE = 178
SER_FILE_ID = "LUCAM-RECORDER"
UNAVAILABLE_TEXT = "Tidak tersedia"

# Struktur biner header 178 byte SER (seluruh field header menggunakan Little-Endian '<'):
# 14s : FileID (14 byte)
# i   : LuID (4 byte)
# i   : ColorID (4 byte)
# i   : LittleEndian (4 byte)
# i   : ImageWidth (4 byte)
# i   : ImageHeight (4 byte)
# i   : PixelDepthPerPlane (4 byte)
# i   : FrameCount (4 byte)
# 40s : Observer (40 byte)
# 40s : Instrument (40 byte)
# 40s : Telescope (40 byte)
# q   : DateTime (8 byte signed int64)
# q   : DateTime_UTC (8 byte signed int64)
_HEADER_STRUCT = struct.Struct("<14siiiiiii40s40s40sqq")

# Tabel ColorID resmi spesifikasi SER v3:
# color_id -> (nama_resmi, num_planes, is_cfa_mosaic, cfa_pattern_str)
SER_COLOR_ID_TABLE: dict[int, tuple[str, int, bool, str | None]] = {
    0: ("MONO", 1, False, None),
    8: ("BAYER_RGGB", 1, True, "RGGB"),
    9: ("BAYER_GRBG", 1, True, "GRBG"),
    16: ("BAYER_GBRG", 1, True, "GBRG"),
    17: ("BAYER_BGGR", 1, True, "BGGR"),
    18: ("BAYER_CYYM", 1, True, "CYYM"),
    19: ("BAYER_YCMY", 1, True, "YCMY"),
    20: ("BAYER_YMCY", 1, True, "YMCY"),
    21: ("BAYER_MYYC", 1, True, "MYYC"),
    100: ("RGB", 3, False, None),
    101: ("BGR", 3, False, None),
}

VALID_ENDIANNESS_POLICIES: tuple[str, ...] = (
    "siril_default",
    "strict_spec",
    "force_le",
    "force_be",
)

# Batas wajar nilai ticks untuk tahun 0001..9999 (10_000_000 ticks/detik)
_MAX_VALID_TICKS = 3_155_378_975_999_999_999


def ser_ticks_to_iso8601(ticks: int, is_utc: bool = True) -> str | None:
    """Mengonversi nilai ticks SER (100-nanodetik sejak 0001-01-01 00:00:00) ke ISO-8601.

    Menggunakan aritmetika integer murni agar tidak kehilangan presisi mikrodetik.
    Nilai ``<= 0`` atau di luar rentang tahun 1..9999 dianggap tidak tersedia (``None``).
    """
    if ticks <= 0 or ticks > _MAX_VALID_TICKS:
        return None
    seconds, rem_ticks = divmod(int(ticks), 10_000_000)
    microseconds = rem_ticks // 10
    sub_micro_hundred_ns = rem_ticks % 10
    try:
        dt = datetime(1, 1, 1) + timedelta(seconds=seconds, microseconds=microseconds)
    except (OverflowError, ValueError):
        return None
    suffix = "Z" if is_utc else ""
    if sub_micro_hundred_ns:
        return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{microseconds:06d}{sub_micro_hundred_ns}{suffix}"
    return f"{dt.strftime('%Y-%m-%dT%H:%M:%S')}.{microseconds:06d}{suffix}"


def ser_ticks_to_seconds(ticks: int) -> float | None:
    """Mengonversi nilai ticks SER ke detik relatif terhadap epoch 0001-01-01."""
    if ticks <= 0 or ticks > _MAX_VALID_TICKS:
        return None
    seconds, rem_ticks = divmod(int(ticks), 10_000_000)
    return float(seconds) + (float(rem_ticks) / 10_000_000.0)


def _clean_ascii_field(raw_bytes: bytes) -> str:
    """Membersihkan field string 40-byte pada header SER dari NULL byte dan spasi buntut."""
    # Potong mulai dari NULL byte pertama bila ada
    null_pos = raw_bytes.find(b"\x00")
    if null_pos != -1:
        raw_bytes = raw_bytes[:null_pos]
    text = raw_bytes.decode("latin-1", errors="replace").strip()
    return text


def _format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024.0:.1f} KB"
    return f"{size_bytes / (1024.0 * 1024.0):.2f} MB"


def _demosaic_bayer_2x2_bilinear(mosaic: np.ndarray, pattern: str) -> np.ndarray:
    """Demosaicing bilinear ringan pada mosaik Bayer 2x2 khusus untuk pratinjau visual RGB.

    Fungsi ini TIDAK pernah dipakai untuk mengubah ``scientific_data``; data ilmiah
    tetap berupa mosaik sensor 2D asli.
    """
    arr = mosaic.astype(np.float32, copy=False)
    h, w = arr.shape
    padded = np.pad(arr, ((1, 1), (1, 1)), mode="reflect")

    # Rata-rata tetangga untuk interpolasi bilinear sederhana
    horiz = 0.5 * (padded[1:-1, :-2] + padded[1:-1, 2:])
    vert = 0.5 * (padded[:-2, 1:-1] + padded[2:, 1:-1])
    cross = 0.25 * (
        padded[:-2, 1:-1] + padded[2:, 1:-1] + padded[1:-1, :-2] + padded[1:-1, 2:]
    )
    diag = 0.25 * (
        padded[:-2, :-2] + padded[:-2, 2:] + padded[2:, :-2] + padded[2:, 2:]
    )

    r = np.zeros((h, w), dtype=np.float32)
    g = np.zeros((h, w), dtype=np.float32)
    b = np.zeros((h, w), dtype=np.float32)

    # Pemetaan posisi (baris_genap/ganjil, kolom_genap/ganjil) untuk tiap huruf pola 2x2
    # Urutan indeks karakter pada string pattern:
    # idx 0: (y genap, x genap)
    # idx 1: (y genap, x ganjil)
    # idx 2: (y ganjil, x genap)
    # idx 3: (y ganjil, x ganjil)
    pos_map = {
        (0, 0): pattern[0],
        (0, 1): pattern[1],
        (1, 0): pattern[2],
        (1, 1): pattern[3],
    }

    r_pos = next(pos for pos, ch in pos_map.items() if ch == "R")
    b_pos = next(pos for pos, ch in pos_map.items() if ch == "B")

    for py in (0, 1):
        for px in (0, 1):
            ys = slice(py, None, 2)
            xs = slice(px, None, 2)
            ch = pos_map[(py, px)]

            # Kanal Hijau (G)
            if ch == "G":
                g[ys, xs] = arr[ys, xs]
            else:
                g[ys, xs] = cross[ys, xs]

            # Kanal Merah (R)
            if (py, px) == r_pos:
                r[ys, xs] = arr[ys, xs]
            elif py == r_pos[0]:
                r[ys, xs] = horiz[ys, xs]
            elif px == r_pos[1]:
                r[ys, xs] = vert[ys, xs]
            else:
                r[ys, xs] = diag[ys, xs]

            # Kanal Biru (B)
            if (py, px) == b_pos:
                b[ys, xs] = arr[ys, xs]
            elif py == b_pos[0]:
                b[ys, xs] = horiz[ys, xs]
            elif px == b_pos[1]:
                b[ys, xs] = vert[ys, xs]
            else:
                b[ys, xs] = diag[ys, xs]

    rgb = np.stack([r, g, b], axis=-1)
    if mosaic.dtype == np.uint8:
        return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)
    return np.clip(np.rint(rgb), 0, 65535).astype(np.uint16)


@dataclass(frozen=True)
class SerFrameTimestamp:
    """Informasi waktu satu frame dari trailer opsional berkas SER."""

    frame_index: int
    ticks: int
    timestamp_utc_str: str | None
    relative_sec: float | None


@dataclass(frozen=True)
class SerMetadataInfo:
    """Metadata lengkap hasil pembacaan header 178-byte dan trailer berkas SER."""

    file_name: str
    file_size_bytes: int
    file_id: str
    lu_id: int
    color_id: int
    color_format_name: str
    num_planes: int
    is_cfa_mosaic: bool
    cfa_pattern_str: str | None
    little_endian_header_flag: int
    endianness_policy: str
    effective_byte_order: str  # "Little-Endian (<u2)", "Big-Endian (>u2)", atau "8-bit (1 byte/plane)"
    width: int
    height: int
    pixel_depth_per_plane: int
    bytes_per_pixel_plane: int
    storage_dtype_str: str
    frame_count: int
    frame_size_bytes: int
    observer: str
    instrument: str
    telescope: str
    date_time_ticks: int
    date_time_local_str: str | None
    date_time_utc_ticks: int
    date_time_utc_str: str | None
    has_timestamp_trailer: bool
    trailer_valid_count: int
    warnings: tuple[str, ...]
    honesty_note: str

    def to_display_dict(self) -> dict[str, str]:
        """Kamus terformat untuk ditampilkan pada kartu 'Informasi SER' di GUI."""
        cfa_txt = self.cfa_pattern_str if self.cfa_pattern_str else "Tidak ada (Non-CFA)"
        color_txt = f"{self.color_id} ({self.color_format_name})"
        if self.cfa_pattern_str:
            color_txt += f" — Pola CFA: {self.cfa_pattern_str}"

        le_txt = (
            f"Header LittleEndian={self.little_endian_header_flag} → "
            f"{self.effective_byte_order}"
        )
        depth_txt = (
            f"{self.pixel_depth_per_plane}-bit per plane "
            f"(disimpan sebagai {self.storage_dtype_str})"
        )
        trailer_txt = (
            f"Tersedia ({self.trailer_valid_count}/{self.frame_count} frame valid)"
            if self.has_timestamp_trailer
            else "Tidak tersedia (berkas tanpa trailer timestamp)"
        )

        return {
            "FILE_ID": f"{self.file_id} (LuID: {self.lu_id})",
            "FILE_SIZE": _format_file_size(self.file_size_bytes),
            "COLOR_ID": color_txt,
            "CFA_PATTERN": cfa_txt,
            "RESOLUTION": f"{self.width} × {self.height} px",
            "PIXEL_DEPTH": depth_txt,
            "ENDIANNESS": le_txt,
            "FRAME_COUNT": f"{self.frame_count} frame ({_format_file_size(self.frame_size_bytes)}/frame)",
            "OBSERVER": self.observer if self.observer else UNAVAILABLE_TEXT,
            "INSTRUMENT": self.instrument if self.instrument else UNAVAILABLE_TEXT,
            "TELESCOPE": self.telescope if self.telescope else UNAVAILABLE_TEXT,
            "DATETIME_LOCAL": self.date_time_local_str or UNAVAILABLE_TEXT,
            "DATETIME_UTC": self.date_time_utc_str or UNAVAILABLE_TEXT,
            "TRAILER_STATUS": trailer_txt,
        }

    def summary_text(self) -> str:
        """Ringkasan teks multi-baris untuk kebutuhan laporan dan kompatibilitas."""
        d = self.to_display_dict()
        lines = [
            f"Format: SER ({d['FILE_ID']})",
            f"ColorID: {d['COLOR_ID']}",
            f"Resolusi: {d['RESOLUTION']}",
            f"Pixel Depth: {d['PIXEL_DEPTH']}",
            f"Byte Order: {d['ENDIANNESS']}",
            f"Jumlah Frame: {d['FRAME_COUNT']}",
            f"Observer: {d['OBSERVER']}",
            f"Instrument: {d['INSTRUMENT']}",
            f"Telescope: {d['TELESCOPE']}",
            f"DateTime (Lokal): {d['DATETIME_LOCAL']}",
            f"DateTime (UTC): {d['DATETIME_UTC']}",
            f"Timestamp Trailer: {d['TRAILER_STATUS']}",
            f"Catatan: {self.honesty_note}",
        ]
        return "\n".join(lines)


@dataclass(frozen=True)
class SerDecodedFrame:
    """Hasil pembacaan satu frame dari berkas SER."""

    frame_index: int
    width: int
    height: int
    channels: int
    bit_depth: int
    dtype_str: str
    stored_dtype_str: str
    color_format_name: str
    is_cfa_mosaic: bool
    cfa_pattern_str: str | None
    timestamp_ticks: int | None
    timestamp_utc_str: str | None
    timestamp_relative_sec: float | None
    scientific_data: np.ndarray
    preview: QImage
    raw_stored_data: np.ndarray
    demosaiced_rgb: np.ndarray | None = None


def _resolve_16bit_byte_order(
    little_endian_flag: int,
    endianness_policy: str,
) -> tuple[str, str, list[str]]:
    """Menentukan dtype pembacaan 16-bit ('<u2' atau '>u2') beserta catatan peringatan."""
    if endianness_policy not in VALID_ENDIANNESS_POLICIES:
        raise ImageReadError(
            f"Kebijakan endianness SER tidak dikenal: '{endianness_policy}'. "
            f"Pilihan yang didukung: {', '.join(VALID_ENDIANNESS_POLICIES)}."
        )

    warnings: list[str] = []
    if endianness_policy == "force_le":
        return "<u2", "Little-Endian (<u2, dipaksa eksplisit)", warnings
    if endianness_policy == "force_be":
        return ">u2", "Big-Endian (>u2, dipaksa eksplisit)", warnings

    if endianness_policy == "strict_spec":
        if little_endian_flag == 0:
            return ">u2", "Big-Endian (>u2, mengikuti spesifikasi teks SER v3)", warnings
        return "<u2", "Little-Endian (<u2, mengikuti spesifikasi teks SER v3)", warnings

    # Default: "siril_default" (konvensi astronomi de-facto Siril / Lucam-Recorder)
    if little_endian_flag == 0:
        warnings.append(
            "Header SER mencantumkan LittleEndian=0 pada data 16-bit. Mengikuti konvensi "
            "standar astronomi (Siril / Lucam-Recorder), data diinterpretasikan sebagai "
            "Little-Endian (<u2). Gunakan endianness_policy='strict_spec' atau 'force_be' "
            "bila berkas berasal dari perangkat Big-Endian murni."
        )
        return "<u2", "Little-Endian (<u2, konvensi Siril/Lucam-Recorder)", warnings

    if little_endian_flag not in (0, 1):
        warnings.append(
            f"Header SER memiliki nilai LittleEndian non-standar ({little_endian_flag}); "
            "diinterpretasikan sebagai Little-Endian (<u2)."
        )
    return "<u2", "Little-Endian (<u2)", warnings


class SerSession:
    """Sesi pembacaan berkas SER berbasis *lazy byte-offset seeking* dan *bounded LRU cache*.

    Saat ``SerSession`` diinisialisasi:
      1. Hanya header 178 byte dan trailer timestamp opsional yang dibaca.
      2. Handle berkas langsung ditutup kembali.
      3. Pembacaan piksel frame individual hanya terjadi ketika ``read_frame(index)``
         (atau alias ``decode_frame(index)``) dipanggil.
    """

    def __init__(
        self,
        path: str | Path,
        max_cache_size: int = 8,
        endianness_policy: str = "siril_default",
    ) -> None:
        self._path = Path(path)
        self._max_cache_size = max(1, int(max_cache_size))
        self._endianness_policy = endianness_policy
        self._cache: OrderedDict[int, SerDecodedFrame] = OrderedDict()

        if not self._path.exists():
            raise ImageReadError(f"File SER tidak ditemukan: {self._path}")
        if not self._path.is_file():
            raise ImageReadError(f"Jalur yang dipilih bukan sebuah file SER: {self._path}")

        self._metadata, self._timestamps, self._disk_dtype = self._inspect_header_and_trailer()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def metadata(self) -> SerMetadataInfo:
        return self._metadata

    @property
    def frame_timestamps(self) -> tuple[SerFrameTimestamp, ...]:
        return self._timestamps

    @property
    def cached_frame_indices(self) -> tuple[int, ...]:
        """Daftar indeks frame yang saat ini berada di dalam LRU cache."""
        return tuple(self._cache.keys())

    def close(self) -> None:
        """Membersihkan cache frame di RAM."""
        self._cache.clear()

    def _inspect_header_and_trailer(
        self,
    ) -> tuple[SerMetadataInfo, tuple[SerFrameTimestamp, ...], np.dtype]:
        try:
            file_size = self._path.stat().st_size
        except OSError as exc:
            raise ImageReadError(
                f"Gagal memeriksa ukuran berkas SER '{self._path.name}': {exc}"
            ) from exc

        if file_size < SER_HEADER_SIZE:
            raise ImageReadError(
                f"Berkas SER '{self._path.name}' rusak atau tidak lengkap: ukuran berkas hanya "
                f"{file_size} byte (minimal header SER adalah {SER_HEADER_SIZE} byte)."
            )

        try:
            with open(self._path, "rb") as f:
                header_bytes = f.read(SER_HEADER_SIZE)
                if len(header_bytes) < SER_HEADER_SIZE:
                    raise ImageReadError(
                        f"Gagal membaca header 178 byte dari berkas SER '{self._path.name}'."
                    )

                (
                    raw_file_id,
                    lu_id,
                    color_id,
                    little_endian_flag,
                    width,
                    height,
                    pixel_depth,
                    frame_count,
                    raw_observer,
                    raw_instrument,
                    raw_telescope,
                    dt_ticks,
                    dt_utc_ticks,
                ) = _HEADER_STRUCT.unpack(header_bytes)

                file_id_str = raw_file_id.decode("latin-1", errors="replace").rstrip("\x00 ")
                if file_id_str != SER_FILE_ID:
                    raise ImageReadError(
                        f"Berkas '{self._path.name}' bukan berkas SER yang valid: FileID terbaca "
                        f"'{file_id_str}' (seharusnya '{SER_FILE_ID}')."
                    )

                if color_id not in SER_COLOR_ID_TABLE:
                    valid_ids = ", ".join(
                        f"{cid} ({info[0]})" for cid, info in sorted(SER_COLOR_ID_TABLE.items())
                    )
                    raise ImageReadError(
                        f"Berkas SER '{self._path.name}' memiliki ColorID tidak dikenal ({color_id}). "
                        f"HILALONE tidak menebak format warna. ColorID resmi yang didukung: {valid_ids}."
                    )

                if width <= 0 or height <= 0:
                    raise ImageReadError(
                        f"Berkas SER '{self._path.name}' memiliki dimensi gambar tidak valid: "
                        f"{width} × {height} px (lebar dan tinggi wajib > 0)."
                    )

                if pixel_depth < 1 or pixel_depth > 16:
                    raise ImageReadError(
                        f"Berkas SER '{self._path.name}' memiliki PixelDepthPerPlane tidak valid: "
                        f"{pixel_depth} (wajib berada pada rentang 1..16 bit)."
                    )

                if frame_count <= 0:
                    raise ImageReadError(
                        f"Berkas SER '{self._path.name}' tidak memiliki frame yang valid "
                        f"(FrameCount = {frame_count})."
                    )

                color_name, num_planes, is_cfa, cfa_pattern = SER_COLOR_ID_TABLE[color_id]
                bytes_per_plane = 1 if pixel_depth <= 8 else 2
                frame_size_bytes = int(width) * int(height) * int(num_planes) * int(bytes_per_plane)
                expected_pixel_end = SER_HEADER_SIZE + int(frame_count) * frame_size_bytes

                if file_size < expected_pixel_end:
                    missing_bytes = expected_pixel_end - file_size
                    raise ImageReadError(
                        f"Berkas SER '{self._path.name}' terpotong atau korup: untuk {frame_count} frame "
                        f"berukuran {width}×{height} ({pixel_depth}-bit {color_name}) dibutuhkan minimal "
                        f"{expected_pixel_end} byte, tetapi ukuran berkas hanya {file_size} byte "
                        f"(kurang {missing_bytes} byte)."
                    )

                warnings: list[str] = []
                if bytes_per_plane == 1:
                    disk_dtype = np.dtype(np.uint8)
                    storage_dtype_str = "uint8"
                    effective_byte_order = "8-bit (1 byte/plane, endianness tidak berpengaruh)"
                else:
                    dtype_code, effective_byte_order, le_warnings = _resolve_16bit_byte_order(
                        little_endian_flag, self._endianness_policy
                    )
                    disk_dtype = np.dtype(dtype_code)
                    storage_dtype_str = "uint16"
                    warnings.extend(le_warnings)

                # Periksa trailer timestamp opsional (FrameCount * 8 byte setelah seluruh frame piksel)
                trailer_size = int(frame_count) * 8
                expected_with_trailer = expected_pixel_end + trailer_size
                remaining_bytes = file_size - expected_pixel_end

                timestamps: list[SerFrameTimestamp] = []
                has_trailer = False
                valid_ts_count = 0

                if remaining_bytes >= trailer_size:
                    has_trailer = True
                    f.seek(expected_pixel_end)
                    raw_trailer = f.read(trailer_size)
                    ticks_tuple = struct.unpack(f"<{frame_count}q", raw_trailer)

                    first_ticks: int | None = None
                    prev_ticks: int | None = None
                    non_monotonic = False

                    for idx, t_val in enumerate(ticks_tuple):
                        iso_str = ser_ticks_to_iso8601(t_val, is_utc=True)
                        if iso_str is not None:
                            valid_ts_count += 1
                            if first_ticks is None:
                                first_ticks = int(t_val)
                            # Pengurangan integer 64-bit murni agar tidak kehilangan presisi float64
                            rel_sec = max(0.0, float(int(t_val) - first_ticks) / 10_000_000.0)
                            if prev_ticks is not None and t_val < prev_ticks:
                                non_monotonic = True
                            prev_ticks = int(t_val)
                        else:
                            rel_sec = None

                        timestamps.append(
                            SerFrameTimestamp(
                                frame_index=idx,
                                ticks=int(t_val),
                                timestamp_utc_str=iso_str,
                                relative_sec=rel_sec,
                            )
                        )

                    if valid_ts_count == 0:
                        warnings.append(
                            "Trailer timestamp SER ditemukan tetapi seluruh nilai timestamp bernilai <= 0 "
                            "(kamera/perekam tidak mengisi timestamp per-frame)."
                        )
                    elif valid_ts_count < frame_count:
                        warnings.append(
                            f"Sebagian frame pada trailer SER tidak memiliki timestamp valid "
                            f"({valid_ts_count}/{frame_count} frame valid)."
                        )
                    if non_monotonic:
                        warnings.append(
                            "Urutan waktu pada trailer timestamp SER tidak monotonik (terdapat frame "
                            "dengan timestamp lebih kecil dari frame sebelumnya)."
                        )
                else:
                    if remaining_bytes > 0:
                        warnings.append(
                            f"Terdapat {remaining_bytes} byte tambahan di akhir berkas SER yang tidak "
                            f"mencukupi ukuran trailer timestamp lengkap ({trailer_size} byte); "
                            "trailer diabaikan."
                        )
                    for idx in range(frame_count):
                        timestamps.append(
                            SerFrameTimestamp(
                                frame_index=idx,
                                ticks=0,
                                timestamp_utc_str=None,
                                relative_sec=None,
                            )
                        )

        except ImageReadError:
            raise
        except Exception as exc:
            raise ImageReadError(
                f"Gagal membaca berkas SER '{self._path.name}': {exc}"
            ) from exc

        observer_str = _clean_ascii_field(raw_observer)
        instrument_str = _clean_ascii_field(raw_instrument)
        telescope_str = _clean_ascii_field(raw_telescope)
        dt_local_str = ser_ticks_to_iso8601(dt_ticks, is_utc=False)
        dt_utc_str = ser_ticks_to_iso8601(dt_utc_ticks, is_utc=True)

        if is_cfa:
            honesty_note = (
                f"Data ilmiah disimpan sebagai mosaik sensor 2D asli ({color_name}, {storage_dtype_str}) "
                "tanpa demosaicing permanen. Demosaicing hanya diterapkan secara terpisah untuk "
                "membentuk pratinjau visual 8-bit di layar."
            )
        elif color_id == 101:
            honesty_note = (
                f"Berkas SER disimpan dalam urutan kanal BGR ({storage_dtype_str}); "
                "data ilmiah dan pratinjau disajikan dengan urutan kanal RGB secara lossless "
                "tanpa mengubah nilai numerik piksel."
            )
        else:
            honesty_note = (
                f"Data ilmiah SER ({color_name}, {storage_dtype_str}) dipertahankan utuh sesuai "
                "nilai piksel asli tanpa pengubahan skala permanen; pratinjau layar 8-bit "
                "dibentuk secara terpisah."
            )

        meta = SerMetadataInfo(
            file_name=self._path.name,
            file_size_bytes=file_size,
            file_id=file_id_str,
            lu_id=int(lu_id),
            color_id=int(color_id),
            color_format_name=color_name,
            num_planes=int(num_planes),
            is_cfa_mosaic=is_cfa,
            cfa_pattern_str=cfa_pattern,
            little_endian_header_flag=int(little_endian_flag),
            endianness_policy=self._endianness_policy,
            effective_byte_order=effective_byte_order,
            width=int(width),
            height=int(height),
            pixel_depth_per_plane=int(pixel_depth),
            bytes_per_pixel_plane=int(bytes_per_plane),
            storage_dtype_str=storage_dtype_str,
            frame_count=int(frame_count),
            frame_size_bytes=frame_size_bytes,
            observer=observer_str,
            instrument=instrument_str,
            telescope=telescope_str,
            date_time_ticks=int(dt_ticks),
            date_time_local_str=dt_local_str,
            date_time_utc_ticks=int(dt_utc_ticks),
            date_time_utc_str=dt_utc_str,
            has_timestamp_trailer=has_trailer,
            trailer_valid_count=valid_ts_count,
            warnings=tuple(warnings),
            honesty_note=honesty_note,
        )
        return meta, tuple(timestamps), disk_dtype

    def read_frame(self, frame_index: int) -> SerDecodedFrame:
        """Membaca satu frame SER secara *on-demand* berdasarkan byte offset (dengan LRU cache)."""
        total = self._metadata.frame_count
        if frame_index < 0 or frame_index >= total:
            raise ImageReadError(
                f"Indeks frame SER di luar jangkauan: {frame_index + 1} (total frame: {total})."
            )

        if frame_index in self._cache:
            self._cache.move_to_end(frame_index)
            return self._cache[frame_index]

        byte_offset = SER_HEADER_SIZE + frame_index * self._metadata.frame_size_bytes
        try:
            with open(self._path, "rb") as f:
                f.seek(byte_offset)
                raw_bytes = f.read(self._metadata.frame_size_bytes)
        except OSError as exc:
            raise ImageReadError(
                f"Gagal membaca data frame #{frame_index + 1} dari berkas SER '{self._path.name}': {exc}"
            ) from exc

        if len(raw_bytes) < self._metadata.frame_size_bytes:
            raise ImageReadError(
                f"Data frame #{frame_index + 1} pada berkas SER '{self._path.name}' terpotong: "
                f"hanya terbaca {len(raw_bytes)} dari {self._metadata.frame_size_bytes} byte."
            )

        h = self._metadata.height
        w = self._metadata.width
        planes = self._metadata.num_planes

        # Konversi buffer sesuai disk_dtype (<u2, >u2, atau uint8) lalu salin ke native uint8/uint16
        native_dtype = np.uint8 if self._metadata.bytes_per_pixel_plane == 1 else np.uint16
        arr_disk = np.frombuffer(raw_bytes, dtype=self._disk_dtype)
        if planes == 1:
            raw_stored = arr_disk.reshape((h, w)).astype(native_dtype, copy=True)
        else:
            raw_stored = arr_disk.reshape((h, w, planes)).astype(native_dtype, copy=True)

        demosaiced_rgb: np.ndarray | None = None
        if self._metadata.color_id == 101:
            # BGR -> RGB secara lossless (tanpa mengubah nilai piksel, hanya urutan kanal 0 dan 2)
            scientific_data = np.ascontiguousarray(raw_stored[..., ::-1])
            preview = build_display_preview(scientific_data)
            channels = 3
        elif self._metadata.color_id == 100:
            scientific_data = raw_stored
            preview = build_display_preview(scientific_data)
            channels = 3
        elif self._metadata.is_cfa_mosaic:
            # Data ilmiah tetap 2D mosaik sensor asli!
            scientific_data = raw_stored
            channels = 1
            pattern = self._metadata.cfa_pattern_str or ""
            if set(pattern) == {"R", "G", "B"} and len(pattern) == 4:
                demosaiced_rgb = _demosaic_bayer_2x2_bilinear(scientific_data, pattern)
                preview = build_display_preview(demosaiced_rgb)
            else:
                # Untuk CFA non-RGB (CYYM/YCMY/YMCY/MYYC), tampilkan pratinjau langsung dari mosaik
                preview = build_display_preview(scientific_data)
        else:
            # MONO (ColorID == 0)
            scientific_data = raw_stored
            preview = build_display_preview(scientific_data)
            channels = 1

        ts_info = self._timestamps[frame_index]
        stored_dtype_desc = (
            f"{self._disk_dtype.str} ({self._metadata.color_format_name})"
            if self._metadata.bytes_per_pixel_plane == 2
            else f"uint8 ({self._metadata.color_format_name})"
        )

        decoded = SerDecodedFrame(
            frame_index=frame_index,
            width=w,
            height=h,
            channels=channels,
            bit_depth=self._metadata.pixel_depth_per_plane,
            dtype_str=self._metadata.storage_dtype_str,
            stored_dtype_str=stored_dtype_desc,
            color_format_name=self._metadata.color_format_name,
            is_cfa_mosaic=self._metadata.is_cfa_mosaic,
            cfa_pattern_str=self._metadata.cfa_pattern_str,
            timestamp_ticks=ts_info.ticks if ts_info.ticks > 0 else None,
            timestamp_utc_str=ts_info.timestamp_utc_str,
            timestamp_relative_sec=ts_info.relative_sec,
            scientific_data=scientific_data,
            preview=preview,
            raw_stored_data=raw_stored,
            demosaiced_rgb=demosaiced_rgb,
        )

        self._cache[frame_index] = decoded
        while len(self._cache) > self._max_cache_size:
            self._cache.popitem(last=False)

        return decoded

    # Alias agar seragam dengan antarmuka VideoSession
    decode_frame = read_frame


def inspect_ser(
    path: str | Path,
    endianness_policy: str = "siril_default",
) -> SerMetadataInfo:
    """Memeriksa header 178-byte dan trailer berkas SER tanpa memuat frame piksel ke RAM."""
    session = SerSession(path, max_cache_size=1, endianness_policy=endianness_policy)
    meta = session.metadata
    session.close()
    return meta
