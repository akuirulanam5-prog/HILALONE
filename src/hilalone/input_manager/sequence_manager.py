"""Sequence Manager HILALONE (Sub-Tahap 2A).

Mengelola pembukaan Single Image maupun Multiple Images / Folder Sequence
dengan prinsip:
  * **Lazy Loading**: saat membuka sequence, hanya header setiap berkas yang
    diperiksa lewat ``inspect_image_header``. Array piksel penuh
    (``scientific_data`` + ``preview``) hanya dimuat untuk satu frame yang
    sedang diminta lewat ``load_frame()``.
  * **Tidak Membuang Frame Diam-Diam**: berkas yang rusak (``ERROR``) atau
    berbeda dimensi/kanal/orientasi (``INCOMPATIBLE``) tetap berada di dalam
    daftar ``entries`` sesuai urutan beserta alasan berbahasa Indonesia.
  * **Pratinjau Individual**: baik frame ``COMPATIBLE`` maupun ``INCOMPATIBLE``
    tetap dapat dibuka dan dipratinjau satu per satu.
  * **Perbedaan Bit Depth**: tidak otomatis menjadi ``INCOMPATIBLE``; frame
    tetap ``COMPATIBLE`` dan diberi catatan bahwa konversi numerik terkontrol
    ke ``float32`` akan diterapkan saat preprocessing/stacking.
"""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from hilalone.input_manager.image_reader import (
    PREVIEW_BIT_DEPTH,
    ImageInfo,
    ImageReadError,
    LoadedImage,
    inspect_image_header,
    read_image,
    supported_extensions,
)
from hilalone.input_manager.models import (
    FrameStatus,
    InputMode,
    SequenceCompatibilityReport,
    SequenceFrameEntry,
)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hilalone.input_manager.adapters.ser_reader import SerSession
    from hilalone.input_manager.adapters.video_reader import VideoSession

SORT_NATURAL_LABEL = "Natural filename sorting"
SORT_TIMESTAMP_LABEL = "Timestamp pengamatan (DATE-OBS)"
SORT_TIMESTAMP_FALLBACK_LABEL = (
    "Natural filename sorting (sebagian frame tidak memiliki timestamp valid)"
)

_NATURAL_SPLIT_RE = re.compile(r"(\d+)")


def natural_sort_key(path: str | Path) -> tuple[tuple[int, int | str], ...]:
    """Kunci pengurutan natural untuk nama berkas (mis. img_2 sebelum img_10)."""
    name = Path(path).name.lower()
    parts = _NATURAL_SPLIT_RE.split(name)
    key: list[tuple[int, int | str]] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part))
    return tuple(key)


def _extract_timestamp_str(info: ImageInfo | None) -> str | None:
    """Mengambil string timestamp pengamatan (DATE-OBS pada FITS atau timestamp pada RAW) bila ada."""
    if info is None:
        return None
    if info.fits_header is not None and info.fits_header.date_obs is not None:
        cleaned = str(info.fits_header.date_obs).strip()
        if cleaned:
            return cleaned
    if info.raw_metadata is not None and info.raw_metadata.timestamp_str is not None:
        cleaned = str(info.raw_metadata.timestamp_str).strip()
        if cleaned:
            return cleaned
    return None


def discover_supported_files_in_folder(folder_path: str | Path) -> list[Path]:
    """Mencari seluruh berkas gambar yang didukung di dalam satu folder (tidak rekursif)."""
    folder = Path(folder_path)
    if not folder.exists():
        raise ImageReadError(f"Folder tidak ditemukan: {folder}")
    if not folder.is_dir():
        raise ImageReadError(f"Jalur yang dipilih bukan sebuah folder: {folder}")

    exts = set(supported_extensions())
    files: list[Path] = []
    for item in folder.iterdir():
        if item.is_file() and item.suffix.lower().lstrip(".") in exts:
            files.append(item)
    files.sort(key=natural_sort_key)
    return files


class SequenceManager:
    """Pengelola sesi masukan gambar tunggal maupun urutan multi-gambar."""

    def __init__(self) -> None:
        self._mode: InputMode = InputMode.EMPTY
        self._entries: list[SequenceFrameEntry] = []
        self._sorting_method: str = SORT_NATURAL_LABEL
        self._report: SequenceCompatibilityReport = self._empty_report()
        self._current_index: int = -1
        self._video_session: VideoSession | None = None
        self._ser_session: SerSession | None = None

    # ---------------------------------------------------------------- properti
    @property
    def input_mode(self) -> InputMode:
        return self._mode

    @property
    def video_session(self) -> VideoSession | None:
        return self._video_session

    @property
    def ser_session(self) -> SerSession | None:
        return self._ser_session

    @property
    def stacking_required(self) -> bool:
        """False untuk Single Image (atau kosong), True untuk Multiple Images, Video, dan SER."""
        return self._mode in (InputMode.MULTI, InputMode.VIDEO, InputMode.SER)

    @property
    def sorting_method(self) -> str:
        return self._sorting_method

    @property
    def entries(self) -> tuple[SequenceFrameEntry, ...]:
        return tuple(self._entries)

    @property
    def frame_count(self) -> int:
        return len(self._entries)

    @property
    def compatibility_report(self) -> SequenceCompatibilityReport:
        return self._report

    @property
    def current_index(self) -> int:
        return self._current_index

    # ---------------------------------------------------------- metode pembuka
    def _close_active_video_session(self) -> None:
        if self._video_session is not None:
            try:
                self._video_session.close()
            except Exception:
                pass
            self._video_session = None
        if self._ser_session is not None:
            try:
                self._ser_session.close()
            except Exception:
                pass
            self._ser_session = None

    def clear(self) -> None:
        """Mengosongkan seluruh sesi sequence dan menutup container video aktif."""
        self._close_active_video_session()
        self._mode = InputMode.EMPTY
        self._entries = []
        self._sorting_method = SORT_NATURAL_LABEL
        self._report = self._empty_report()
        self._current_index = -1

    def open_single_file(
        self,
        path: str | Path,
        page_index: int | None = None,
        hdu_index: int | None = None,
    ) -> LoadedImage:
        """Membuka satu berkas gambar sebagai mode SINGLE (stacking_required = False)."""
        loaded = read_image(path, page_index=page_index, hdu_index=hdu_index)
        self._close_active_video_session()
        entry = SequenceFrameEntry(
            frame_index=0,
            source_path=loaded.info.path,
            info=loaded.info,
            status=FrameStatus.COMPATIBLE,
            is_pixel_loaded=True,
            timestamp_str=_extract_timestamp_str(loaded.info),
            issues=(),
            notes=(),
        )
        self._mode = InputMode.SINGLE
        self._entries = [entry]
        self._sorting_method = "Berkas tunggal (tidak diurutkan)"
        self._current_index = 0
        self._report = SequenceCompatibilityReport(
            is_ready_for_stacking=False,
            reference_frame_index=0,
            total_files=1,
            compatible_count=1,
            incompatible_count=0,
            error_count=0,
            mixed_bit_depth=False,
            warnings=(),
            notes=("Mode Single Image: stacking tidak diperlukan.",),
        )
        return loaded

    def open_folder(
        self,
        folder_path: str | Path,
        sort_by: str = "natural",
    ) -> SequenceCompatibilityReport:
        """Membuka seluruh berkas gambar yang didukung di dalam sebuah folder."""
        files = discover_supported_files_in_folder(folder_path)
        if not files:
            exts = ", ".join(e.upper() for e in supported_extensions())
            raise ImageReadError(
                f"Tidak ditemukan berkas gambar yang didukung di dalam folder '{Path(folder_path).name}'. "
                f"Format yang didukung: {exts}."
            )
        return self.open_files(files, sort_by=sort_by)

    def open_files(
        self,
        paths: Iterable[str | Path],
        sort_by: str = "natural",
    ) -> SequenceCompatibilityReport:
        """Membuka daftar berkas secara *lazy* (hanya memeriksa header di awal).

        - Jika daftar hanya berisi 1 berkas, mode ditetapkan ke ``SINGLE``
          (``stacking_required = False``).
        - Jika daftar berisi ≥2 berkas, mode ditetapkan ke ``MULTI``
          (``stacking_required = True``).
        """
        raw_paths = [Path(p) for p in paths]
        if not raw_paths:
            raise ImageReadError("Tidak ada berkas gambar yang dipilih.")

        # 1. Urutkan awalnya dengan natural filename sorting
        natural_sorted = sorted(raw_paths, key=natural_sort_key)

        # 2. Inspeksi header secara lazy (tanpa memuat array piksel penuh)
        inspected: list[tuple[Path, ImageInfo | None, str | None, str | None]] = []
        for p in natural_sorted:
            try:
                info = inspect_image_header(p)
                ts = _extract_timestamp_str(info)
                inspected.append((p, info, ts, None))
            except ImageReadError as err:
                inspected.append((p, None, None, str(err)))
            except Exception as err:
                inspected.append((p, None, None, f"Gagal memeriksa berkas '{p.name}': {err}"))

        # 3. Bila sort_by == "timestamp", gunakan timestamp HANYA jika seluruh berkas valid punya timestamp
        if sort_by == "timestamp":
            all_have_ts = all(item[2] is not None for item in inspected)
            if all_have_ts:
                inspected.sort(key=lambda item: (item[2] or "", natural_sort_key(item[0])))
                self._sorting_method = SORT_TIMESTAMP_LABEL
            else:
                self._sorting_method = SORT_TIMESTAMP_FALLBACK_LABEL
        else:
            self._sorting_method = SORT_NATURAL_LABEL

        self._close_active_video_session()
        self._mode = InputMode.SINGLE if len(inspected) == 1 else InputMode.MULTI
        self._build_entries_and_report(inspected)
        self._current_index = 0 if self._entries else -1
        return self._report

    def open_video_file(
        self,
        path: str | Path,
        max_cache_size: int = 8,
    ) -> SequenceCompatibilityReport:
        """Membuka berkas video (.MP4, .MOV, .AVI) secara *lazy* sebagai sequence multi-frame.

        - ``stacking_required`` bernilai ``True``.
        - Seluruh frame didaftarkan sesuai urutan presentasi tanpa memuat piksel
          seluruh video ke RAM.
        """
        from hilalone.input_manager.adapters.video_reader import (
            VIDEO_EXTENSIONS,
            VideoSession,
        )

        video_path = Path(path)
        if not video_path.exists():
            raise ImageReadError(f"File video tidak ditemukan: {video_path}")
        if not video_path.is_file():
            raise ImageReadError(f"Jalur yang dipilih bukan sebuah file video: {video_path}")

        ext = video_path.suffix.lower().lstrip(".")
        if ext not in VIDEO_EXTENSIONS:
            shown = ", ".join(f".{e.upper()}" for e in VIDEO_EXTENSIONS)
            raise ImageReadError(
                f"Format file video '.{ext}' belum didukung pada Video Reader ini. "
                f"Format video yang didukung: {shown}."
            )

        session = VideoSession(video_path, max_cache_size=max_cache_size)
        self._close_active_video_session()
        self._video_session = session

        meta = session.metadata
        channels = 1 if meta.is_monochrome else 3
        dtype_str = "uint16" if meta.bits_per_component > 8 else "uint8"
        bit_depth = 16 if meta.bits_per_component > 8 else 8
        fmt_label = f"VIDEO ({ext.upper()} / {meta.codec_name})"

        entries: list[SequenceFrameEntry] = []
        for pkt_entry in session.frame_entries:
            ts_str = (
                f"{pkt_entry.timestamp_sec:.6f} s (PTS={pkt_entry.pts})"
                if pkt_entry.timestamp_sec is not None
                else None
            )
            frame_info = ImageInfo(
                path=video_path,
                file_name=f"{video_path.name} [Frame #{pkt_entry.frame_index + 1}]",
                file_format=fmt_label,
                width=meta.width,
                height=meta.height,
                stored_width=meta.width,
                stored_height=meta.height,
                channels=channels,
                has_alpha=False,
                original_bit_depth=bit_depth,
                original_is_float=False,
                preview_bit_depth=PREVIEW_BIT_DEPTH,
                exif_orientation="Normal (tanpa rotasi)",
                orientation_applied=False,
                dtype_str=dtype_str,
                stored_dtype_str=meta.pix_fmt,
                video_metadata=meta,
                frame_pts=pkt_entry.pts,
                frame_timestamp_sec=pkt_entry.timestamp_sec,
                decoded_pix_fmt=meta.pix_fmt,
            )
            entries.append(
                SequenceFrameEntry(
                    frame_index=pkt_entry.frame_index,
                    source_path=video_path,
                    info=frame_info,
                    status=FrameStatus.COMPATIBLE,
                    is_pixel_loaded=False,
                    timestamp_str=ts_str,
                    issues=(),
                    notes=(),
                )
            )

        self._mode = InputMode.VIDEO
        self._entries = entries
        if meta.has_missing_timestamps:
            self._sorting_method = "Urutan presentasi video (sebagian/seluruh PTS tidak tersedia)"
        elif meta.is_variable_frame_rate:
            self._sorting_method = "Urutan presentasi video VFR (PTS × time_base)"
        else:
            self._sorting_method = "Urutan presentasi video CFR (PTS × time_base)"

        self._report = SequenceCompatibilityReport(
            is_ready_for_stacking=len(entries) >= 2,
            reference_frame_index=0 if entries else None,
            total_files=len(entries),
            compatible_count=len(entries),
            incompatible_count=0,
            error_count=0,
            mixed_bit_depth=False,
            warnings=meta.warnings,
            notes=(meta.honesty_note,),
        )
        self._current_index = 0 if entries else -1
        return self._report

    def open_ser_file(
        self,
        path: str | Path,
        max_cache_size: int = 8,
        endianness_policy: str = "siril_default",
    ) -> SequenceCompatibilityReport:
        """Membuka berkas video astronomi SER (.ser) secara *lazy* sebagai sequence multi-frame.

        - ``stacking_required`` bernilai ``True``.
        - Hanya header 178 byte dan trailer timestamp opsional yang dibaca di awal;
          piksel setiap frame baru dibaca secara *on-demand* berdasarkan byte offset
          ketika ``load_frame(index)`` dipanggil.
        """
        from hilalone.input_manager.adapters.ser_reader import (
            SER_EXTENSIONS,
            SerSession,
        )

        ser_path = Path(path)
        if not ser_path.exists():
            raise ImageReadError(f"File SER tidak ditemukan: {ser_path}")
        if not ser_path.is_file():
            raise ImageReadError(f"Jalur yang dipilih bukan sebuah file SER: {ser_path}")

        ext = ser_path.suffix.lower().lstrip(".")
        if ext not in SER_EXTENSIONS:
            raise ImageReadError(
                f"Format file '.{ext}' bukan berkas SER (.SER) yang didukung."
            )

        session = SerSession(
            ser_path,
            max_cache_size=max_cache_size,
            endianness_policy=endianness_policy,
        )
        self._close_active_video_session()
        self._ser_session = session

        meta = session.metadata
        channels = 1 if meta.num_planes == 1 else 3
        fmt_label = f"SER ({meta.color_format_name}, {meta.pixel_depth_per_plane}-bit)"

        entries: list[SequenceFrameEntry] = []
        for ts_entry in session.frame_timestamps:
            if ts_entry.timestamp_utc_str is not None and ts_entry.relative_sec is not None:
                ts_str = f"{ts_entry.timestamp_utc_str} (+{ts_entry.relative_sec:.4f} s)"
            elif ts_entry.timestamp_utc_str is not None:
                ts_str = ts_entry.timestamp_utc_str
            else:
                ts_str = None

            frame_info = ImageInfo(
                path=ser_path,
                file_name=f"{ser_path.name} [Frame #{ts_entry.frame_index + 1}]",
                file_format=fmt_label,
                width=meta.width,
                height=meta.height,
                stored_width=meta.width,
                stored_height=meta.height,
                channels=channels,
                has_alpha=False,
                original_bit_depth=meta.pixel_depth_per_plane,
                original_is_float=False,
                preview_bit_depth=PREVIEW_BIT_DEPTH,
                exif_orientation="Normal (tanpa rotasi)",
                orientation_applied=False,
                dtype_str=meta.storage_dtype_str,
                stored_dtype_str=f"{meta.storage_dtype_str} ({meta.color_format_name})",
                ser_metadata=meta,
                frame_timestamp_sec=ts_entry.relative_sec,
                frame_timestamp_ticks=ts_entry.ticks if ts_entry.ticks > 0 else None,
                frame_timestamp_utc_str=ts_entry.timestamp_utc_str,
            )
            entries.append(
                SequenceFrameEntry(
                    frame_index=ts_entry.frame_index,
                    source_path=ser_path,
                    info=frame_info,
                    status=FrameStatus.COMPATIBLE,
                    is_pixel_loaded=False,
                    timestamp_str=ts_str,
                    issues=(),
                    notes=(),
                )
            )

        self._mode = InputMode.SER
        self._entries = entries
        if meta.has_timestamp_trailer and meta.trailer_valid_count == meta.frame_count:
            self._sorting_method = "Urutan indeks rekaman SER (dengan timestamp trailer 100-ns)"
        elif meta.has_timestamp_trailer:
            self._sorting_method = (
                f"Urutan indeks rekaman SER (trailer parsial: {meta.trailer_valid_count}/{meta.frame_count} frame)"
            )
        else:
            self._sorting_method = "Urutan indeks rekaman SER (tanpa trailer timestamp)"

        self._report = SequenceCompatibilityReport(
            is_ready_for_stacking=len(entries) >= 2,
            reference_frame_index=0 if entries else None,
            total_files=len(entries),
            compatible_count=len(entries),
            incompatible_count=0,
            error_count=0,
            mixed_bit_depth=False,
            warnings=meta.warnings,
            notes=(meta.honesty_note,),
        )
        self._current_index = 0 if entries else -1
        return self._report

    def load_frame(self, index: int) -> LoadedImage:
        """Memuat piksel penuh (`scientific_data` + `preview`) untuk satu frame (*Lazy Load*).

        Baik frame berstatus ``COMPATIBLE`` maupun ``INCOMPATIBLE`` tetap dapat
        dibuka dan dipratinjau secara individual.
        """
        if index < 0 or index >= len(self._entries):
            raise ImageReadError(
                f"Indeks frame tidak valid: {index + 1} (total frame: {len(self._entries)})."
            )
        entry = self._entries[index]
        if entry.status == FrameStatus.ERROR:
            reason = "; ".join(entry.issues) if entry.issues else "Berkas tidak valid."
            raise ImageReadError(
                f"Frame [{index + 1}/{len(self._entries)}] '{entry.file_name}' tidak dapat ditampilkan: {reason}"
            )

        if self._video_session is not None and self._mode == InputMode.VIDEO:
            try:
                vframe = self._video_session.decode_frame(index)
            except ImageReadError as err:
                # Jangan hilangkan frame secara diam-diam; tandai ERROR di tempatnya
                failed_entry = replace(
                    entry,
                    status=FrameStatus.ERROR,
                    is_pixel_loaded=False,
                    issues=(str(err),),
                )
                self._entries[index] = failed_entry
                self._recompute_video_report_counts()
                raise

            meta = self._video_session.metadata
            ext_upper = entry.source_path.suffix.lower().lstrip(".").upper()
            fmt_label = f"VIDEO ({ext_upper} / {meta.codec_name})"
            ts_str = (
                f"{vframe.timestamp_sec:.6f} s (PTS={vframe.pts})"
                if vframe.timestamp_sec is not None
                else None
            )
            updated_info = ImageInfo(
                path=entry.source_path,
                file_name=entry.source_path.name,
                file_format=fmt_label,
                width=vframe.width,
                height=vframe.height,
                stored_width=vframe.width,
                stored_height=vframe.height,
                channels=vframe.channels,
                has_alpha=False,
                original_bit_depth=vframe.bit_depth,
                original_is_float=False,
                preview_bit_depth=PREVIEW_BIT_DEPTH,
                exif_orientation="Normal (tanpa rotasi)",
                orientation_applied=False,
                dtype_str=vframe.dtype_str,
                stored_dtype_str=vframe.decoded_pix_fmt,
                video_metadata=meta,
                frame_pts=vframe.pts,
                frame_timestamp_sec=vframe.timestamp_sec,
                decoded_pix_fmt=vframe.decoded_pix_fmt,
            )
            self._entries[index] = replace(
                entry,
                info=updated_info,
                is_pixel_loaded=True,
                timestamp_str=ts_str,
            )
            self._current_index = index
            return LoadedImage(
                info=updated_info,
                preview=vframe.preview,
                scientific_data=vframe.scientific_data,
                native_video_planes=vframe.native_planes,
            )

        if self._ser_session is not None and self._mode == InputMode.SER:
            try:
                sframe = self._ser_session.read_frame(index)
            except ImageReadError as err:
                failed_entry = replace(
                    entry,
                    status=FrameStatus.ERROR,
                    is_pixel_loaded=False,
                    issues=(str(err),),
                )
                self._entries[index] = failed_entry
                self._recompute_video_report_counts()
                raise

            meta = self._ser_session.metadata
            fmt_label = f"SER ({meta.color_format_name}, {meta.pixel_depth_per_plane}-bit)"
            if sframe.timestamp_utc_str is not None and sframe.timestamp_relative_sec is not None:
                ts_str = f"{sframe.timestamp_utc_str} (+{sframe.timestamp_relative_sec:.4f} s)"
            elif sframe.timestamp_utc_str is not None:
                ts_str = sframe.timestamp_utc_str
            else:
                ts_str = None

            updated_info = ImageInfo(
                path=entry.source_path,
                file_name=entry.source_path.name,
                file_format=fmt_label,
                width=sframe.width,
                height=sframe.height,
                stored_width=sframe.width,
                stored_height=sframe.height,
                channels=sframe.channels,
                has_alpha=False,
                original_bit_depth=sframe.bit_depth,
                original_is_float=False,
                preview_bit_depth=PREVIEW_BIT_DEPTH,
                exif_orientation="Normal (tanpa rotasi)",
                orientation_applied=False,
                dtype_str=sframe.dtype_str,
                stored_dtype_str=sframe.stored_dtype_str,
                ser_metadata=meta,
                frame_timestamp_sec=sframe.timestamp_relative_sec,
                frame_timestamp_ticks=sframe.timestamp_ticks,
                frame_timestamp_utc_str=sframe.timestamp_utc_str,
            )
            self._entries[index] = replace(
                entry,
                info=updated_info,
                is_pixel_loaded=True,
                timestamp_str=ts_str,
            )
            self._current_index = index
            return LoadedImage(
                info=updated_info,
                preview=sframe.preview,
                scientific_data=sframe.scientific_data,
                demosaiced_rgb=sframe.demosaiced_rgb,
                raw_stored_data=sframe.raw_stored_data,
            )

        loaded = read_image(entry.source_path)
        self._entries[index] = replace(entry, info=loaded.info, is_pixel_loaded=True)
        self._current_index = index
        return loaded

    def _recompute_video_report_counts(self) -> None:
        comp = sum(1 for e in self._entries if e.status == FrameStatus.COMPATIBLE)
        incomp = sum(1 for e in self._entries if e.status == FrameStatus.INCOMPATIBLE)
        err = sum(1 for e in self._entries if e.status == FrameStatus.ERROR)
        ready = len(self._entries) >= 2 and comp >= 2 and incomp == 0 and err == 0
        self._report = replace(
            self._report,
            is_ready_for_stacking=ready,
            compatible_count=comp,
            incompatible_count=incomp,
            error_count=err,
        )

    # ------------------------------------------------- logika validasi internal
    def _build_entries_and_report(
        self,
        inspected: list[tuple[Path, ImageInfo | None, str | None, str | None]],
    ) -> None:
        entries: list[SequenceFrameEntry] = []
        warnings: list[str] = []
        notes: list[str] = []

        # Tentukan frame referensi: berkas pertama yang berhasil dibaca headernya
        ref_index: int | None = None
        ref_info: ImageInfo | None = None
        for idx, (_, info, _, err_msg) in enumerate(inspected):
            if info is not None and err_msg is None:
                ref_index = idx
                ref_info = info
                break

        compatible_count = 0
        incompatible_count = 0
        error_count = 0
        mixed_bit_depth = False

        for idx, (path, info, ts, err_msg) in enumerate(inspected):
            if info is None or err_msg is not None:
                msg = err_msg or f"Berkas '{path.name}' tidak dapat dibaca."
                entry = SequenceFrameEntry(
                    frame_index=idx,
                    source_path=path,
                    info=None,
                    status=FrameStatus.ERROR,
                    is_pixel_loaded=False,
                    timestamp_str=None,
                    issues=(msg,),
                    notes=(),
                )
                entries.append(entry)
                warnings.append(f"Frame #{idx + 1} ({path.name}) [GAGAL DIBACA]: {msg}")
                error_count += 1
                continue

            assert ref_info is not None
            frame_issues: list[str] = []
            frame_notes: list[str] = []

            # 1. Periksa dimensi (width x height)
            if (info.width, info.height) != (ref_info.width, ref_info.height):
                frame_issues.append(
                    f"Dimensi {info.width}×{info.height} px berbeda dari frame referensi "
                    f"(#{(ref_index or 0) + 1} {ref_info.file_name}: {ref_info.width}×{ref_info.height} px)."
                )

            # 2. Periksa jumlah kanal (mono vs RGB tidak boleh dicampur)
            if info.channels != ref_info.channels:
                frame_issues.append(
                    f"Jumlah kanal ({info.channels}) berbeda dari frame referensi "
                    f"({ref_info.channels}). Sequence tidak boleh mencampur monokrom dan RGB."
                )

            # 3. Periksa orientasi
            if info.exif_orientation != ref_info.exif_orientation:
                frame_issues.append(
                    f"Orientasi '{info.exif_orientation}' berbeda dari frame referensi "
                    f"('{ref_info.exif_orientation}')."
                )

            # 4. Periksa bit depth / dtype (TIDAK membuat INCOMPATIBLE; dicatat sebagai konversi terkontrol)
            if (
                info.original_bit_depth != ref_info.original_bit_depth
                or info.dtype_str != ref_info.dtype_str
            ):
                mixed_bit_depth = True
                note_msg = (
                    f"Tipe/bit depth ({info.dtype_str or info.original_bit_depth}) berbeda dari "
                    f"frame referensi ({ref_info.dtype_str or ref_info.original_bit_depth}); "
                    "akan dikonversi secara terkontrol ke float32 saat stacking tanpa mengubah data asli."
                )
                frame_notes.append(note_msg)
                notes.append(f"Frame #{idx + 1} ({path.name}): {note_msg}")

            if frame_issues:
                status = FrameStatus.INCOMPATIBLE
                incompatible_count += 1
                for issue in frame_issues:
                    warnings.append(
                        f"Frame #{idx + 1} ({path.name}) [TIDAK KOMPATIBEL]: {issue}"
                    )
            else:
                status = FrameStatus.COMPATIBLE
                compatible_count += 1

            entries.append(
                SequenceFrameEntry(
                    frame_index=idx,
                    source_path=path,
                    info=info,
                    status=status,
                    is_pixel_loaded=False,
                    timestamp_str=ts,
                    issues=tuple(frame_issues),
                    notes=tuple(frame_notes),
                )
            )

        is_multi = len(entries) >= 2
        structural_ready = (
            is_multi
            and compatible_count >= 2
            and incompatible_count == 0
            and error_count == 0
        )

        self._entries = entries
        self._report = SequenceCompatibilityReport(
            is_ready_for_stacking=structural_ready,
            reference_frame_index=ref_index,
            total_files=len(entries),
            compatible_count=compatible_count,
            incompatible_count=incompatible_count,
            error_count=error_count,
            mixed_bit_depth=mixed_bit_depth,
            warnings=tuple(warnings),
            notes=tuple(notes),
        )

    @staticmethod
    def _empty_report() -> SequenceCompatibilityReport:
        return SequenceCompatibilityReport(
            is_ready_for_stacking=False,
            reference_frame_index=None,
            total_files=0,
            compatible_count=0,
            incompatible_count=0,
            error_count=0,
            mixed_bit_depth=False,
            warnings=(),
            notes=(),
        )
