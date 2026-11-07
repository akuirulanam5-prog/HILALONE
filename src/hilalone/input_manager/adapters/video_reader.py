"""Pembaca berkas Video HILALONE berbasis PyAV / FFmpeg (Sub-Tahap 2C, mode baca saja).

Format wadah (container) yang didukung pada Sub-Tahap 2C:
  * ``.MP4``
  * ``.MOV``
  * ``.AVI``

Prinsip utama modul ini:
  1. **Keamanan Berkas Sumber**:
     Berkas video dibuka hanya dalam mode baca (``av.open(..., mode="r")``).
     Berkas sumber tidak pernah diubah, ditimpa, atau dihapus.
  2. **Inspeksi Stream & Deteksi VFR / Timestamp Jujur**:
     - Membaca metadata container, codec, resolusi, format piksel asli
       (``pix_fmt``), frame rate, durasi, jumlah frame, bit rate, serta
       *color range* / *color space* bila tersedia.
     - Menyimpan ``PTS`` (*Presentation Timestamp*), ``time_base``, dan
       menghitung ``timestamp_sec = float(PTS * time_base)`` untuk setiap frame.
     - **Tidak mengasumsikan** ``frame_index / FPS`` selalu menghasilkan
       timestamp yang benar; mendukung *Variable Frame Rate* (VFR) dan memberi
       peringatan Bahasa Indonesia yang spesifik bila ``PTS`` tidak tersedia.
  3. **Pelestarian Format Piksel Hasil Dekode vs Preview Layar**:
     - Mempertahankan informasi ``pix_fmt`` asli hasil dekoder (mis. ``yuv420p``,
       ``gray``, ``gray16le``, ``rgb24``) beserta bidang piksel mentah
       (``native_planes``) sebelum konversi tampilan.
     - Video monokrom (``gray*``) dipertahankan sebagai monokrom 2D ``(H, W)``
       tanpa dikonversi ke RGB.
     - Mencatat secara eksplisit bahwa frame hasil dekode video **bukan** data
       sensor RAW asli.
  4. **Lazy Frame Decoding & Bounded LRU Frame Cache**:
     - Tidak pernah memuat seluruh video ke RAM.
     - Menyimpan paling banyak ``max_cache_size`` (default 8) frame terakhir di
       dalam *Bounded LRU Cache* agar navigasi ``Previous`` / ``Next`` maupun
       *random frame access* berjalan cepat dan hemat memori.
     - Menutup container PyAV secara bersih saat ``close()`` dipanggil.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterator

import av
import av.error
import numpy as np
from PySide6.QtGui import QImage

from hilalone.input_manager.preview_builder import array_to_preview_qimage

UNAVAILABLE_TEXT = "Tidak tersedia"

VIDEO_EXTENSIONS: tuple[str, ...] = ("mp4", "mov", "avi")

DEFAULT_FRAME_CACHE_SIZE = 8

VIDEO_HONESTY_NOTE = (
    "Frame hasil dekode video telah melalui kompresi/pemrosesan codec video "
    "dan BUKAN data sensor RAW asli."
)


@dataclass(frozen=True)
class VideoPacketIndexEntry:
    """Catatan waktu satu frame hasil pemindaian paket/header video."""

    frame_index: int
    pts: int | None
    time_base: Fraction | None
    timestamp_sec: float | None

    def format_timestamp(self) -> str:
        """Teks timestamp untuk daftar frame & panel GUI."""
        if self.timestamp_sec is None or not np.isfinite(self.timestamp_sec):
            return UNAVAILABLE_TEXT
        return f"{self.timestamp_sec:.6f} s (PTS={self.pts})"


@dataclass(frozen=True)
class VideoMetadataInfo:
    """Metadata berkas video, stream, codec, dan warna."""

    file_name: str
    file_size_bytes: int
    container_format: str
    video_stream_index: int
    total_video_streams: int
    codec_name: str
    codec_long_name: str | None
    width: int
    height: int
    pix_fmt: str
    bits_per_component: int
    is_monochrome: bool
    average_rate_fps: float | None
    base_rate_fps: float | None
    time_base_str: str
    duration_sec: float | None
    frame_count: int
    bit_rate_bps: int | None
    color_range: str | None
    color_space: str | None
    color_primaries: str | None
    color_trc: str | None
    is_variable_frame_rate: bool
    has_missing_timestamps: bool
    warnings: tuple[str, ...] = ()
    honesty_note: str = VIDEO_HONESTY_NOTE

    def format_file_size(self) -> str:
        b = self.file_size_bytes
        if b < 1024:
            return f"{b} B"
        if b < 1024 * 1024:
            return f"{b / 1024.0:.2f} KB"
        return f"{b / (1024.0 * 1024.0):.2f} MB"

    def format_fps(self) -> str:
        mode_tag = "VFR (Variable)" if self.is_variable_frame_rate else "CFR (Tetap)"
        if self.average_rate_fps is not None and self.average_rate_fps > 0:
            return f"{self.average_rate_fps:.3f} fps ({mode_tag})"
        if self.base_rate_fps is not None and self.base_rate_fps > 0:
            return f"{self.base_rate_fps:.3f} fps ({mode_tag})"
        return UNAVAILABLE_TEXT

    def format_duration(self) -> str:
        if self.duration_sec is None or self.duration_sec <= 0 or not np.isfinite(self.duration_sec):
            return UNAVAILABLE_TEXT
        return f"{self.duration_sec:.3f} s"

    def format_bit_rate(self) -> str:
        if self.bit_rate_bps is None or self.bit_rate_bps <= 0:
            return UNAVAILABLE_TEXT
        kbps = self.bit_rate_bps / 1000.0
        if kbps >= 1000.0:
            return f"{kbps / 1000.0:.2f} Mbps"
        return f"{kbps:.1f} kbps"

    def format_color_info(self) -> str:
        parts: list[str] = []
        if self.color_range:
            parts.append(f"Range: {self.color_range}")
        if self.color_space:
            parts.append(f"Space: {self.color_space}")
        if self.color_primaries:
            parts.append(f"Primaries: {self.color_primaries}")
        if self.color_trc:
            parts.append(f"TRC: {self.color_trc}")
        return " | ".join(parts) if parts else UNAVAILABLE_TEXT

    def to_display_dict(self) -> dict[str, str]:
        codec_txt = (
            f"{self.codec_name} ({self.codec_long_name})"
            if self.codec_long_name
            else self.codec_name
        )
        return {
            "FILE_NAME": self.file_name,
            "FILE_SIZE": self.format_file_size(),
            "CONTAINER": self.container_format,
            "VIDEO_STREAM": f"Stream #{self.video_stream_index} (dari {self.total_video_streams} video stream)",
            "CODEC": codec_txt or UNAVAILABLE_TEXT,
            "RESOLUTION": f"{self.width} × {self.height} px",
            "PIX_FMT": f"{self.pix_fmt} ({self.bits_per_component}-bit)",
            "FRAME_RATE": self.format_fps(),
            "TIME_BASE": self.time_base_str or UNAVAILABLE_TEXT,
            "DURATION": self.format_duration(),
            "FRAME_COUNT": f"{self.frame_count} frame",
            "BIT_RATE": self.format_bit_rate(),
            "COLOR_META": self.format_color_info(),
            "HONESTY_NOTE": self.honesty_note,
        }

    def summary_text(self) -> str:
        d = self.to_display_dict()
        lines = [
            f"Container: {d['CONTAINER']} | Ukuran: {d['FILE_SIZE']}",
            f"Stream: {d['VIDEO_STREAM']}",
            f"Codec: {d['CODEC']}",
            f"Resolusi: {d['RESOLUTION']} | Pixel Format: {d['PIX_FMT']}",
            f"Frame Rate: {d['FRAME_RATE']} | time_base: {d['TIME_BASE']}",
            f"Durasi: {d['DURATION']} | Total Frame: {d['FRAME_COUNT']}",
            f"Bit Rate: {d['BIT_RATE']}",
            f"Color Metadata: {d['COLOR_META']}",
            f"Catatan: {d['HONESTY_NOTE']}",
        ]
        return "\n".join(lines)


@dataclass(frozen=True)
class VideoDecodedFrame:
    """Satu frame video hasil dekode beserta bidang piksel asli dan pratinjau 8-bit terpisah."""

    frame_index: int
    pts: int | None
    time_base: Fraction | None
    timestamp_sec: float | None
    decoded_pix_fmt: str
    width: int
    height: int
    channels: int
    bit_depth: int
    dtype_str: str
    native_planes: tuple[np.ndarray, ...]
    scientific_data: np.ndarray
    rgb_representation: np.ndarray | None
    preview: QImage


def _detect_bits_and_mono(pix_fmt: str | None, bits_per_raw: int | None) -> tuple[int, bool]:
    """Menentukan bit depth per komponen dan apakah format piksel adalah monokrom."""
    fmt = (pix_fmt or "yuv420p").lower()
    is_mono = fmt.startswith("gray") or fmt in ("monob", "monow", "ya8", "ya16le", "ya16be")

    if bits_per_raw and bits_per_raw > 0:
        return int(bits_per_raw), is_mono

    for b in (16, 14, 12, 10, 9):
        if f"{b}le" in fmt or f"{b}be" in fmt or fmt.endswith(str(b)):
            return b, is_mono
    if "48" in fmt or "64" in fmt:
        return 16, is_mono
    return 8, is_mono


def _extract_color_metadata(codec_ctx: Any) -> tuple[str | None, str | None, str | None, str | None]:
    """Mengekstrak color_range, color_space, color_primaries, dan color_trc jika tersedia."""

    def _clean(val: Any) -> str | None:
        if val is None:
            return None
        name = getattr(val, "name", str(val))
        text = str(name).strip()
        if not text or text.lower() in ("unspecified", "unknown", "none", "0", "2"):
            return None
        return text

    c_range = _clean(getattr(codec_ctx, "color_range", None))
    c_space = _clean(getattr(codec_ctx, "colorspace", None) or getattr(codec_ctx, "color_space", None))
    c_prim = _clean(getattr(codec_ctx, "color_primaries", None))
    c_trc = _clean(getattr(codec_ctx, "color_trc", None))
    return c_range, c_space, c_prim, c_trc


def _copy_native_planes(av_frame: Any) -> tuple[np.ndarray, ...]:
    """Menyalin buffer tiap plane asli dari AVFrame sebelum konversi warna apa pun."""
    planes_out: list[np.ndarray] = []
    try:
        for plane in getattr(av_frame, "planes", ()):
            buf = np.frombuffer(plane, dtype=np.uint8).copy()
            buf.flags.writeable = False
            planes_out.append(buf)
    except Exception:
        return ()
    return tuple(planes_out)


def _extract_frame_arrays(
    av_frame: Any,
    is_monochrome: bool,
    bits_per_component: int,
) -> tuple[np.ndarray, np.ndarray | None, QImage, int, int]:
    """Mengekstrak array hasil dekode dan pratinjau QImage 8-bit secara terpisah.

    - Jika video monokrom (``gray*``): ``scientific_data`` tetap 2D monokrom
      (``uint8`` atau ``uint16``), ``rgb_representation`` bernilai ``None``.
    - Jika video warna (``yuv*`` / ``rgb*``):
        * Untuk format >8-bit (10/12/16-bit), dikonversi ke ``rgb48le`` (``uint16``)
          agar presisi >8-bit tidak hilang.
        * Untuk format 8-bit, ``scientific_data`` menyimpan array ``(H, W, 3)``
          ``uint8`` hasil dekode sementara ``native_planes`` menyimpan plane YUV
          asli sebelum konversi.
    """
    if is_monochrome:
        if bits_per_component > 8:
            sci = np.array(av_frame.to_ndarray(format="gray16le"), copy=True)
            bit_depth = 16
        else:
            sci = np.array(av_frame.to_ndarray(format="gray"), copy=True)
            bit_depth = 8
        sci.flags.writeable = False
        preview = array_to_preview_qimage(sci)
        return sci, None, preview, 1, bit_depth

    if bits_per_component > 8:
        rgb16 = np.array(av_frame.to_ndarray(format="rgb48le"), copy=True)
        rgb16.flags.writeable = False
        preview = array_to_preview_qimage(rgb16)
        return rgb16, rgb16, preview, 3, 16

    rgb8 = np.array(av_frame.to_ndarray(format="rgb24"), copy=True)
    rgb8.flags.writeable = False
    preview = array_to_preview_qimage(rgb8)
    return rgb8, rgb8, preview, 3, 8


def _translate_av_exception(path: Path, exc: Exception) -> Exception:
    """Menerjemahkan eksepsi PyAV / FFmpeg ke ImageReadError berbahasa Indonesia."""
    from hilalone.input_manager.image_reader import ImageReadError

    if isinstance(exc, ImageReadError):
        return exc

    msg_low = str(exc).lower()
    if isinstance(exc, av.error.PatchWelcomeError) or "codec" in msg_low or "decoder" in msg_low:
        return ImageReadError(
            f"Codec video pada berkas '{path.name}' belum didukung oleh FFmpeg/PyAV: {exc}"
        )
    if isinstance(exc, (av.error.InvalidDataError, av.error.EOFError)):
        return ImageReadError(
            f"Berkas video '{path.name}' rusak, tidak lengkap, atau bukan video yang valid: {exc}"
        )
    return ImageReadError(
        f"Gagal membaca berkas video '{path.name}': {exc}"
    )


class VideoSession:
    """Sesi pembacaan video berbasis PyAV dengan *Lazy Frame Decoding* dan *Bounded LRU Cache*.

    Strategi Navigasi & Memori:
      * Seluruh video TIDAK pernah dimuat ke RAM sekaligus.
      * Menyimpan maksimal ``max_cache_size`` frame terakhir di dalam ``OrderedDict``
        (*Least Recently Used*).
      * **Next Frame** (``index == _last_decoded_index + 1``): melanjutkan iterator
        dekoder maju 1 langkah tanpa ``seek`` ulang.
      * **Previous Frame** (``index`` ada di dalam cache): langsung diambil dari
        cache dalam waktu $O(1)$ tanpa dekode ulang.
      * **Random Frame Access** (lompat jauh ke frame di luar cache): melakukan
        ``container.seek`` ke keyframe terdekat sebelum ``PTS`` target, lalu
        mendekode maju sampai mencapai ``index``.
    """

    def __init__(
        self,
        path: str | Path,
        max_cache_size: int = DEFAULT_FRAME_CACHE_SIZE,
    ) -> None:
        from hilalone.input_manager.image_reader import ImageReadError

        self._path = Path(path)
        if not self._path.exists():
            raise ImageReadError(f"File video tidak ditemukan: {self._path}")
        if not self._path.is_file():
            raise ImageReadError(f"Jalur yang dipilih bukan sebuah file video: {self._path}")

        self._max_cache_size = max(2, int(max_cache_size))
        self._cache: OrderedDict[int, VideoDecodedFrame] = OrderedDict()
        self._container: Any = None
        self._stream_index: int = 0
        self._decode_iter: Iterator[Any] | None = None
        self._last_decoded_index: int = -1
        self._closed: bool = False

        self._metadata: VideoMetadataInfo
        self._frame_entries: tuple[VideoPacketIndexEntry, ...]
        self._metadata, self._frame_entries = self._open_and_inspect()

    # ---------------------------------------------------------------- properti
    @property
    def path(self) -> Path:
        return self._path

    @property
    def is_closed(self) -> bool:
        return self._closed

    @property
    def metadata(self) -> VideoMetadataInfo:
        return self._metadata

    @property
    def frame_entries(self) -> tuple[VideoPacketIndexEntry, ...]:
        return self._frame_entries

    @property
    def frame_count(self) -> int:
        return len(self._frame_entries)

    @property
    def cached_frame_indices(self) -> tuple[int, ...]:
        """Indeks frame yang saat ini berada di dalam bounded cache."""
        return tuple(self._cache.keys())

    # ------------------------------------------------- pembukaan & inspeksi
    def _open_and_inspect(self) -> tuple[VideoMetadataInfo, tuple[VideoPacketIndexEntry, ...]]:
        from hilalone.input_manager.image_reader import ImageReadError

        try:
            container = av.open(str(self._path), mode="r")
        except Exception as exc:
            raise _translate_av_exception(self._path, exc) from exc

        try:
            video_streams = list(container.streams.video)
            if not video_streams:
                container.close()
                raise ImageReadError(
                    f"Berkas '{self._path.name}' tidak memiliki video stream yang dapat dibaca."
                )

            vstream = video_streams[0]
            self._stream_index = int(vstream.index)
            codec_ctx = vstream.codec_context

            codec_name = str(getattr(codec_ctx, "name", "") or getattr(vstream, "name", "") or "unknown")
            codec_long = getattr(getattr(codec_ctx, "codec", None), "long_name", None)

            width = int(getattr(codec_ctx, "width", 0) or getattr(vstream, "width", 0) or 0)
            height = int(getattr(codec_ctx, "height", 0) or getattr(vstream, "height", 0) or 0)
            if width <= 0 or height <= 0:
                container.close()
                raise ImageReadError(
                    f"Video stream pada '{self._path.name}' memiliki resolusi tidak valid ({width}×{height})."
                )

            pix_fmt = str(getattr(codec_ctx, "pix_fmt", None) or getattr(vstream, "pix_fmt", None) or "unknown")
            bits_raw = getattr(codec_ctx, "bits_per_raw_sample", None)
            bits_comp, is_mono = _detect_bits_and_mono(pix_fmt, bits_raw)

            tb_raw = vstream.time_base
            tb: Fraction | None = Fraction(tb_raw.numerator, tb_raw.denominator) if tb_raw is not None else None
            tb_str = f"{tb.numerator}/{tb.denominator}" if tb is not None else UNAVAILABLE_TEXT

            avg_rate = float(vstream.average_rate) if vstream.average_rate is not None else None
            base_rate = float(vstream.base_rate) if vstream.base_rate is not None else None

            # Pindai paket (demux) tanpa mendekode piksel untuk mendata PTS setiap frame & VFR
            pts_list: list[int | None] = []
            for packet in container.demux(vstream):
                if packet.dts is None and packet.pts is None and packet.size == 0:
                    continue
                pts_list.append(int(packet.pts) if packet.pts is not None else None)

            if not pts_list:
                container.close()
                raise ImageReadError(
                    f"Berkas video '{self._path.name}' tidak berisi frame video yang dapat didekode."
                )

            # Urutkan PTS sesuai urutan presentasi bila seluruh PTS tersedia (mis. B-frames)
            valid_pts = [p for p in pts_list if p is not None]
            has_missing_ts = len(valid_pts) < len(pts_list) or tb is None
            if not has_missing_ts and len(valid_pts) == len(pts_list):
                ordered_pts: list[int | None] = sorted(valid_pts)
            else:
                ordered_pts = pts_list

            entries: list[VideoPacketIndexEntry] = []
            for idx, p_val in enumerate(ordered_pts):
                ts_sec = float(Fraction(p_val, 1) * tb) if (p_val is not None and tb is not None) else None
                entries.append(
                    VideoPacketIndexEntry(
                        frame_index=idx,
                        pts=p_val,
                        time_base=tb,
                        timestamp_sec=ts_sec,
                    )
                )

            # Deteksi Variable Frame Rate (VFR) dari variasi delta PTS
            is_vfr = False
            if len(valid_pts) >= 3:
                s_pts = sorted(valid_pts)
                deltas = [s_pts[i + 1] - s_pts[i] for i in range(len(s_pts) - 1) if s_pts[i + 1] > s_pts[i]]
                if deltas:
                    min_d, max_d = min(deltas), max(deltas)
                    if max_d - min_d > max(1, int(0.05 * min_d)):
                        is_vfr = True
            if not is_vfr and avg_rate and base_rate and abs(avg_rate - base_rate) > 0.5:
                is_vfr = True

            # Hitung durasi
            dur_sec: float | None = None
            if vstream.duration is not None and tb is not None:
                dur_sec = float(Fraction(int(vstream.duration), 1) * tb)
            elif container.duration is not None:
                dur_sec = float(container.duration) / float(av.time_base)
            elif entries and entries[-1].timestamp_sec is not None and entries[0].timestamp_sec is not None:
                dur_sec = max(0.0, entries[-1].timestamp_sec - entries[0].timestamp_sec)

            bit_rate = int(vstream.bit_rate or container.bit_rate or 0) or None
            c_range, c_space, c_prim, c_trc = _extract_color_metadata(codec_ctx)

            warnings: list[str] = []
            if has_missing_ts:
                warnings.append(
                    f"Sebagian atau seluruh frame pada video '{self._path.name}' tidak memiliki "
                    "timestamp (PTS) yang valid; waktu tidak ditebak dari FPS."
                )
            if is_vfr:
                warnings.append(
                    f"Video '{self._path.name}' terdeteksi menggunakan Variable Frame Rate (VFR); "
                    "timestamp setiap frame dihitung langsung dari PTS × time_base."
                )

            fmt_name = str(getattr(container.format, "name", "") or self._path.suffix.lstrip(".")).upper()
            meta = VideoMetadataInfo(
                file_name=self._path.name,
                file_size_bytes=self._path.stat().st_size,
                container_format=fmt_name,
                video_stream_index=self._stream_index,
                total_video_streams=len(video_streams),
                codec_name=codec_name,
                codec_long_name=str(codec_long) if codec_long else None,
                width=width,
                height=height,
                pix_fmt=pix_fmt,
                bits_per_component=bits_comp,
                is_monochrome=is_mono,
                average_rate_fps=avg_rate,
                base_rate_fps=base_rate,
                time_base_str=tb_str,
                duration_sec=dur_sec,
                frame_count=len(entries),
                bit_rate_bps=bit_rate,
                color_range=c_range,
                color_space=c_space,
                color_primaries=c_prim,
                color_trc=c_trc,
                is_variable_frame_rate=is_vfr,
                has_missing_timestamps=has_missing_ts,
                warnings=tuple(warnings),
            )

            # Tutup container inspeksi/demux dan buka container baru yang bersih dari byte 0
            # untuk menghindari rusaknya palette / stream extradata context FFmpeg pada format AVI (mis. pal8 / rawvideo)
            try:
                container.close()
            except Exception:
                pass
            self._container = av.open(str(self._path), mode="r")
            self._decode_iter = None
            self._last_decoded_index = -1
            return meta, tuple(entries)
        except Exception as exc:
            try:
                container.close()
            except Exception:
                pass
            raise _translate_av_exception(self._path, exc) from exc

    # ------------------------------------------------- ekstraksi frame (lazy)
    def _store_in_cache(self, index: int, frame_obj: VideoDecodedFrame) -> None:
        if index in self._cache:
            self._cache.move_to_end(index)
        self._cache[index] = frame_obj
        while len(self._cache) > self._max_cache_size:
            self._cache.popitem(last=False)

    def _reset_decoder_to_start(self) -> None:
        """Mengatur ulang dekoder ke awal video secara bersih tanpa merusak konteks palette/ekstradata."""
        if self._container is not None:
            try:
                self._container.close()
            except Exception:
                pass
        self._container = av.open(str(self._path), mode="r")
        self._decode_iter = self._container.decode(video=self._stream_index)
        self._last_decoded_index = -1

    def _build_decoded_frame(self, index: int, av_frame: Any) -> VideoDecodedFrame:
        pkt_entry = self._frame_entries[index]
        vstream = self._container.streams.video[0]
        tb_raw = av_frame.time_base or vstream.time_base
        tb = Fraction(tb_raw.numerator, tb_raw.denominator) if tb_raw is not None else pkt_entry.time_base

        pts = int(av_frame.pts) if av_frame.pts is not None else pkt_entry.pts
        ts_sec = float(Fraction(pts, 1) * tb) if (pts is not None and tb is not None) else pkt_entry.timestamp_sec

        orig_pix_fmt = str(getattr(getattr(av_frame, "format", None), "name", None) or self._metadata.pix_fmt)
        native_planes = _copy_native_planes(av_frame)
        sci, rgb_rep, preview, channels, bit_depth = _extract_frame_arrays(
            av_frame,
            is_monochrome=self._metadata.is_monochrome,
            bits_per_component=self._metadata.bits_per_component,
        )

        return VideoDecodedFrame(
            frame_index=index,
            pts=pts,
            time_base=tb,
            timestamp_sec=ts_sec,
            decoded_pix_fmt=orig_pix_fmt,
            width=int(sci.shape[1]),
            height=int(sci.shape[0]),
            channels=channels,
            bit_depth=bit_depth,
            dtype_str=str(sci.dtype),
            native_planes=native_planes,
            scientific_data=sci,
            rgb_representation=rgb_rep,
            preview=preview,
        )

    def decode_frame(self, index: int) -> VideoDecodedFrame:
        """Mendekode frame ke-`index` secara *on-demand* dengan memanfaatkan *Bounded LRU Cache*."""
        from hilalone.input_manager.image_reader import ImageReadError

        if self._closed or self._container is None:
            raise ImageReadError(f"Sesi video '{self._path.name}' sudah ditutup.")
        if index < 0 or index >= len(self._frame_entries):
            raise ImageReadError(
                f"Indeks frame video tidak valid: {index + 1} (total frame: {len(self._frame_entries)})."
            )

        # 1. Periksa apakah frame sudah ada di dalam Bounded LRU Cache (mis. tombol Previous)
        if index in self._cache:
            self._cache.move_to_end(index)
            return self._cache[index]

        # 2. Jika belum ada atau meminta frame sebelum posisi dekoder saat ini, reset / seek
        try:
            if self._decode_iter is None or index <= self._last_decoded_index:
                self._reset_decoder_to_start()

            while self._last_decoded_index < index:
                try:
                    av_frame = next(self._decode_iter)  # type: ignore[arg-type]
                except StopIteration as stop_exc:
                    raise ImageReadError(
                        f"Gagal mendekode frame #{index + 1} pada video '{self._path.name}': "
                        "aliran video berakhir lebih awal atau frame rusak."
                    ) from stop_exc

                self._last_decoded_index += 1
                curr_idx = self._last_decoded_index
                # Simpan ke cache untuk frame target maupun beberapa frame tepat sebelumnya
                # agar tombol '◀ Sebelumnya' langsung instan dari cache
                if index - curr_idx < self._max_cache_size:
                    decoded_obj = self._build_decoded_frame(curr_idx, av_frame)
                    self._store_in_cache(curr_idx, decoded_obj)

            return self._cache[index]
        except Exception as exc:
            raise _translate_av_exception(self._path, exc) from exc

    def close(self) -> None:
        """Menutup container video PyAV dan mengosongkan cache frame di RAM."""
        self._closed = True
        self._decode_iter = None
        self._cache.clear()
        if self._container is not None:
            try:
                self._container.close()
            except Exception:
                pass
            self._container = None

    def __enter__(self) -> VideoSession:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


def inspect_video(path: str | Path) -> VideoMetadataInfo:
    """Memeriksa metadata berkas video dan langsung menutup container."""
    with VideoSession(path) as session:
        return session.metadata
