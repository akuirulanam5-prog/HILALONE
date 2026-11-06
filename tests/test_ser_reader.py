"""Pengujian unit untuk SER Reader (Sub-Tahap 2D).

Mencakup pengujian sintetis menyeluruh untuk:
  1. SER 8-bit Monochrome (ColorID = 0).
  2. SER 16-bit Monochrome dengan pengujian eksplisit Little-Endian (<u2) dan
     Big-Endian (>u2) beserta kebijakan endianness_policy ('siril_default',
     'strict_spec', 'force_le', 'force_be').
  3. SER Bayer CFA (RGGB=8, GRBG=9, GBRG=16, BGGR=17, serta CYYM=18) — memastikan
     data ilmiah (scientific_data) tetap berupa mosaik sensor 2D asli tanpa
     demosaicing permanen, sedangkan preview 8-bit ter-demosaic secara terpisah.
  4. SER RGB (ColorID=100) dan BGR (ColorID=101) — memastikan urutan kanal R-G-B
     benar dan data disk asli tetap utuh.
  5. SER dengan trailer timestamp 64-bit ticks (100-ns) dan SER tanpa trailer.
  6. Lazy loading berbasis byte-offset seeking, bounded LRU cache, serta navigasi
     Previous, Next, dan lompat acak pada SequenceManager.
  7. Penanganan berkas korup: header < 178 byte, FileID salah, ColorID tidak
     dikenal, dimensi/FrameCount tidak valid, dan ukuran berkas terpotong.
  8. Integritas berkas sumber (SHA-256 identik dan handle berkas tertutup rapat).
  9. Integrasi GUI MainWindow untuk membuka dan menavigasi berkas SER.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
from pathlib import Path
import struct

import numpy as np
import pytest
from PySide6.QtWidgets import QApplication

from hilalone.gui.main_window import MainWindow
from hilalone.input_manager.adapters.ser_reader import (
    SER_HEADER_SIZE,
    SerSession,
    inspect_ser,
    ser_ticks_to_iso8601,
)
from hilalone.input_manager.image_reader import ImageReadError
from hilalone.input_manager.models import FrameStatus, InputMode
from hilalone.input_manager.sequence_manager import SequenceManager

_HEADER_STRUCT = struct.Struct("<14siiiiiii40s40s40sqq")


def _datetime_to_ser_ticks(dt: datetime) -> int:
    """Mengonversi objek datetime ke satuan ticks SER (100-nanodetik sejak 0001-01-01)."""
    delta: timedelta = dt - datetime(1, 1, 1)
    total_seconds = int(delta.days) * 86400 + int(delta.seconds)
    return total_seconds * 10_000_000 + int(delta.microseconds) * 10


def _build_synthetic_ser_file(
    path: Path,
    frames: list[np.ndarray],
    *,
    color_id: int = 0,
    little_endian_flag: int = 1,
    pixel_depth_per_plane: int | None = None,
    disk_byte_order: str = "<",
    lu_id: int = 42,
    observer: str = "Tim Rukyat HILALONE",
    instrument: str = "ZWO ASI290MM",
    telescope: str = "Takahashi FSQ-106ED",
    dt_local_ticks: int | None = None,
    dt_utc_ticks: int | None = None,
    trailer_ticks: list[int] | None = None,
    file_id: bytes = b"LUCAM-RECORDER",
) -> Path:
    """Membuat berkas .ser sintetis sesuai spesifikasi biner SER v3."""
    assert len(frames) > 0
    first = frames[0]
    h, w = first.shape[:2]

    if pixel_depth_per_plane is None:
        pixel_depth_per_plane = 8 if first.dtype == np.uint8 else 16

    if dt_local_ticks is None:
        dt_local_ticks = _datetime_to_ser_ticks(datetime(2026, 6, 15, 18, 12, 30, 500000))
    if dt_utc_ticks is None:
        dt_utc_ticks = _datetime_to_ser_ticks(datetime(2026, 6, 15, 11, 12, 30, 500000))

    header_bytes = _HEADER_STRUCT.pack(
        file_id.ljust(14, b"\x00")[:14],
        int(lu_id),
        int(color_id),
        int(little_endian_flag),
        int(w),
        int(h),
        int(pixel_depth_per_plane),
        len(frames),
        observer.encode("latin-1").ljust(40, b"\x00")[:40],
        instrument.encode("latin-1").ljust(40, b"\x00")[:40],
        telescope.encode("latin-1").ljust(40, b"\x00")[:40],
        int(dt_local_ticks),
        int(dt_utc_ticks),
    )
    assert len(header_bytes) == SER_HEADER_SIZE

    with open(path, "wb") as f:
        f.write(header_bytes)
        for arr in frames:
            if pixel_depth_per_plane <= 8:
                raw = np.ascontiguousarray(arr, dtype=np.uint8).tobytes()
            else:
                dt_disk = np.dtype("<u2" if disk_byte_order == "<" else ">u2")
                raw = np.ascontiguousarray(arr, dtype=dt_disk).tobytes()
            f.write(raw)

        if trailer_ticks is not None:
            f.write(struct.pack(f"<{len(trailer_ticks)}q", *trailer_ticks))

    return path


def test_ser_8bit_mono_exact_preservation(tmp_path: Path) -> None:
    """SER 8-bit Mono (ColorID=0) membaca header 178-byte dan piksel 2D uint8 secara identik."""
    f0 = np.arange(12 * 16, dtype=np.uint8).reshape(12, 16)
    f1 = (f0 + 25).astype(np.uint8)
    ser_path = _build_synthetic_ser_file(
        tmp_path / "mono8.ser",
        [f0, f1],
        color_id=0,
        pixel_depth_per_plane=8,
        observer="Ahmad Pengamat",
        instrument="QHY5III462C",
        telescope="Celestron C8",
    )

    meta = inspect_ser(ser_path)
    assert meta.file_id == "LUCAM-RECORDER"
    assert meta.color_id == 0
    assert meta.color_format_name == "MONO"
    assert meta.num_planes == 1
    assert not meta.is_cfa_mosaic
    assert meta.width == 16
    assert meta.height == 12
    assert meta.pixel_depth_per_plane == 8
    assert meta.storage_dtype_str == "uint8"
    assert meta.frame_count == 2
    assert meta.observer == "Ahmad Pengamat"
    assert meta.instrument == "QHY5III462C"
    assert meta.telescope == "Celestron C8"
    assert meta.date_time_local_str == "2026-06-15T18:12:30.500000"
    assert meta.date_time_utc_str == "2026-06-15T11:12:30.500000Z"

    session = SerSession(ser_path)
    dec0 = session.read_frame(0)
    dec1 = session.read_frame(1)

    assert dec0.channels == 1
    assert dec0.scientific_data.shape == (12, 16)
    assert dec0.scientific_data.dtype == np.uint8
    assert np.array_equal(dec0.scientific_data, f0)
    assert np.array_equal(dec1.scientific_data, f1)
    assert not dec0.preview.isNull()
    assert dec0.preview.width() == 16
    assert dec0.preview.height() == 12
    session.close()


def test_ser_16bit_mono_little_endian_and_big_endian_policies(tmp_path: Path) -> None:
    """SER 16-bit menguji Little-Endian (<u2) dan Big-Endian (>u2) serta anomali LittleEndian=0."""
    pattern_16 = np.array(
        [
            [0, 258, 1024, 4095, 32768, 65535],
            [17, 513, 2049, 8191, 49152, 60123],
            [99, 777, 3333, 9999, 12345, 54321],
            [42, 888, 4444, 7777, 23456, 65000],
        ],
        dtype=np.uint16,
    )

    # Kasus 1: Disimpan Little-Endian (<u2) di disk namun header LittleEndian=0 (quirk Lucam-Recorder/Siril)
    ser_le_flag0 = _build_synthetic_ser_file(
        tmp_path / "mono16_le_flag0.ser",
        [pattern_16],
        color_id=0,
        little_endian_flag=0,
        pixel_depth_per_plane=12,  # 12-bit sensor dalam wadah uint16
        disk_byte_order="<",
    )

    # Default 'siril_default' membaca sebagai Little-Endian (<u2) dan mencatat peringatan
    s_siril = SerSession(ser_le_flag0, endianness_policy="siril_default")
    d_siril = s_siril.read_frame(0)
    assert d_siril.bit_depth == 12
    assert d_siril.dtype_str == "uint16"
    assert np.array_equal(d_siril.scientific_data, pattern_16)
    assert any("LittleEndian=0" in w for w in s_siril.metadata.warnings)
    s_siril.close()

    # Kasus 2: Disimpan Big-Endian (>u2) murni sesuai teks spesifikasi SER v3 (LittleEndian=0)
    ser_be_spec = _build_synthetic_ser_file(
        tmp_path / "mono16_be_spec.ser",
        [pattern_16],
        color_id=0,
        little_endian_flag=0,
        pixel_depth_per_plane=16,
        disk_byte_order=">",
    )

    # Dengan 'strict_spec' maupun 'force_be', nilai 16-bit Big-Endian terbaca identik 100%
    for policy in ("strict_spec", "force_be"):
        s_be = SerSession(ser_be_spec, endianness_policy=policy)
        d_be = s_be.read_frame(0)
        assert np.array_equal(d_be.scientific_data, pattern_16)
        assert d_be.scientific_data.dtype == np.uint16
        s_be.close()


@pytest.mark.parametrize(
    ("color_id", "expected_name", "expected_cfa"),
    [
        (8, "BAYER_RGGB", "RGGB"),
        (9, "BAYER_GRBG", "GRBG"),
        (16, "BAYER_GBRG", "GBRG"),
        (17, "BAYER_BGGR", "BGGR"),
        (18, "BAYER_CYYM", "CYYM"),
    ],
)
def test_ser_bayer_cfa_variants_preserve_2d_mosaic_and_demosaic_preview(
    tmp_path: Path,
    color_id: int,
    expected_name: str,
    expected_cfa: str,
) -> None:
    """Data ilmiah Bayer CFA tetap berupa mosaik 2D (H, W) asli, sedangkan preview ter-demosaic."""
    mosaic = np.arange(8 * 10, dtype=np.uint16).reshape(8, 10) * 500
    ser_path = _build_synthetic_ser_file(
        tmp_path / f"cfa_{color_id}.ser",
        [mosaic],
        color_id=color_id,
        pixel_depth_per_plane=16,
    )

    session = SerSession(ser_path)
    meta = session.metadata
    assert meta.color_id == color_id
    assert meta.color_format_name == expected_name
    assert meta.is_cfa_mosaic is True
    assert meta.cfa_pattern_str == expected_cfa

    frame = session.read_frame(0)
    # 1. Data ilmiah wajib tetap 2D mosaik sensor asli!
    assert frame.channels == 1
    assert frame.scientific_data.ndim == 2
    assert frame.scientific_data.shape == (8, 10)
    assert np.array_equal(frame.scientific_data, mosaic)

    # 2. Untuk Bayer RGB 2x2, demosaiced_rgb tersedia secara terpisah (3 kanal) untuk preview
    if color_id in (8, 9, 16, 17):
        assert frame.demosaiced_rgb is not None
        assert frame.demosaiced_rgb.shape == (8, 10, 3)
    assert not frame.preview.isNull()
    session.close()


def test_ser_rgb_and_bgr_channel_order_preservation(tmp_path: Path) -> None:
    """SER RGB (100) dan BGR (101) menghasilkan scientific_data berurutan R-G-B tanpa menukar warna."""
    h, w = 6, 8
    rgb_img = np.zeros((h, w, 3), dtype=np.uint16)
    rgb_img[..., 0] = 60000  # Kanal R tinggi
    rgb_img[..., 1] = 20000  # Kanal G sedang
    rgb_img[..., 2] = 5000   # Kanal B rendah

    # Untuk berkas BGR (ColorID=101), data di disk tersimpan dalam urutan B, G, R
    bgr_on_disk = rgb_img[..., ::-1].copy()

    rgb_path = _build_synthetic_ser_file(
        tmp_path / "color_rgb.ser",
        [rgb_img],
        color_id=100,
        pixel_depth_per_plane=16,
    )
    bgr_path = _build_synthetic_ser_file(
        tmp_path / "color_bgr.ser",
        [bgr_on_disk],
        color_id=101,
        pixel_depth_per_plane=16,
    )

    s_rgb = SerSession(rgb_path)
    f_rgb = s_rgb.read_frame(0)
    assert f_rgb.channels == 3
    assert f_rgb.scientific_data.shape == (h, w, 3)
    assert np.array_equal(f_rgb.scientific_data, rgb_img)

    s_bgr = SerSession(bgr_path)
    f_bgr = s_bgr.read_frame(0)
    assert f_bgr.channels == 3
    assert f_bgr.scientific_data.shape == (h, w, 3)
    # scientific_data dinormalisasi urutan kanalnya menjadi R-G-B secara lossless
    assert np.array_equal(f_bgr.scientific_data, rgb_img)
    # raw_stored_data tetap menyimpan urutan B-G-R persis seperti di disk
    assert np.array_equal(f_bgr.raw_stored_data, bgr_on_disk)

    # Pastikan warna piksel preview layar (8-bit RGB) identik antara RGB dan BGR
    px_rgb = f_rgb.preview.pixelColor(2, 2)
    px_bgr = f_bgr.preview.pixelColor(2, 2)
    assert px_rgb.red() == px_bgr.red()
    assert px_rgb.green() == px_bgr.green()
    assert px_rgb.blue() == px_bgr.blue()
    assert px_rgb.red() > px_rgb.blue()

    s_rgb.close()
    s_bgr.close()


def test_ser_timestamp_trailer_and_without_trailer(tmp_path: Path) -> None:
    """Memverifikasi pembacaan trailer timestamp 64-bit ticks (100-ns) serta berkas tanpa trailer."""
    frames = [np.full((4, 6), i * 20, dtype=np.uint8) for i in range(3)]
    base_dt = datetime(2026, 7, 14, 11, 0, 0, 123456)
    t0 = _datetime_to_ser_ticks(base_dt)
    t1 = _datetime_to_ser_ticks(base_dt + timedelta(milliseconds=50))
    t2 = _datetime_to_ser_ticks(base_dt + timedelta(milliseconds=125))

    with_trailer_path = _build_synthetic_ser_file(
        tmp_path / "with_trailer.ser",
        frames,
        color_id=0,
        trailer_ticks=[t0, t1, t2],
    )
    no_trailer_path = _build_synthetic_ser_file(
        tmp_path / "no_trailer.ser",
        frames,
        color_id=0,
        trailer_ticks=None,
    )

    s_with = SerSession(with_trailer_path)
    assert s_with.metadata.has_timestamp_trailer is True
    assert s_with.metadata.trailer_valid_count == 3
    assert s_with.frame_timestamps[0].ticks == t0
    assert s_with.frame_timestamps[0].timestamp_utc_str == "2026-07-14T11:00:00.123456Z"
    assert s_with.frame_timestamps[0].relative_sec == pytest.approx(0.0, abs=1e-7)
    assert s_with.frame_timestamps[1].relative_sec == pytest.approx(0.050, abs=1e-6)
    assert s_with.frame_timestamps[2].relative_sec == pytest.approx(0.125, abs=1e-6)
    s_with.close()

    s_no = SerSession(no_trailer_path)
    assert s_no.metadata.has_timestamp_trailer is False
    assert s_no.metadata.trailer_valid_count == 0
    assert s_no.frame_timestamps[0].timestamp_utc_str is None
    assert s_no.frame_timestamps[0].relative_sec is None
    s_no.close()

    # Nilai ticks <= 0 harus ditangani dengan aman tanpa crash
    assert ser_ticks_to_iso8601(0) is None
    assert ser_ticks_to_iso8601(-500) is None


def test_ser_lazy_loading_bounded_lru_cache_and_navigation(tmp_path: Path) -> None:
    """Memastikan SerSession dan SequenceManager bekerja secara lazy dan membatasi ukuran cache."""
    frames = [np.full((6, 8), idx * 10, dtype=np.uint16) for idx in range(6)]
    ser_path = _build_synthetic_ser_file(
        tmp_path / "sequence6.ser",
        frames,
        color_id=0,
        pixel_depth_per_plane=16,
    )

    session = SerSession(ser_path, max_cache_size=3)
    # Saat baru dibuka, belum ada piksel frame yang dimuat ke cache
    assert session.cached_frame_indices == ()

    # Navigasi lompat acak, mundur, dan maju
    for idx in (4, 1, 0, 5):
        dec = session.read_frame(idx)
        assert int(dec.scientific_data[0, 0]) == idx * 10
        assert len(session.cached_frame_indices) <= 3

    assert session.cached_frame_indices == (1, 0, 5)
    session.close()
    assert session.cached_frame_indices == ()

    # Uji integrasi dengan SequenceManager
    sm = SequenceManager()
    report = sm.open_ser_file(ser_path, max_cache_size=2)
    assert sm.input_mode == InputMode.SER
    assert sm.stacking_required is True
    assert sm.frame_count == 6
    assert report.is_ready_for_stacking is True
    assert all(not e.is_pixel_loaded for e in sm.entries)

    loaded_3 = sm.load_frame(3)
    assert sm.entries[3].is_pixel_loaded is True
    assert sm.entries[0].is_pixel_loaded is False
    assert int(loaded_3.scientific_data[0, 0]) == 30
    sm.clear()


def test_ser_corrupt_header_unknown_color_id_and_truncated_file(tmp_path: Path) -> None:
    """Memastikan berkas SER korup, ColorID tidak dikenal, dan berkas terpotong ditolak dengan jelas."""
    # 1. Header kurang dari 178 byte
    short_path = tmp_path / "short.ser"
    short_path.write_bytes(b"LUCAM-RECORDER" + b"\x00" * 20)
    with pytest.raises(ImageReadError, match="178 byte"):
        inspect_ser(short_path)

    # 2. FileID salah
    bad_id_path = _build_synthetic_ser_file(
        tmp_path / "bad_id.ser",
        [np.zeros((4, 4), dtype=np.uint8)],
        file_id=b"NOT-A-SER-FILE",
    )
    with pytest.raises(ImageReadError, match="FileID"):
        inspect_ser(bad_id_path)

    # 3. ColorID tidak dikenal (mis. 999)
    bad_color_path = _build_synthetic_ser_file(
        tmp_path / "bad_color.ser",
        [np.zeros((4, 4), dtype=np.uint8)],
        color_id=999,
    )
    with pytest.raises(ImageReadError, match="ColorID tidak dikenal"):
        inspect_ser(bad_color_path)

    # 4. PixelDepthPerPlane di luar 1..16
    bad_depth_path = _build_synthetic_ser_file(
        tmp_path / "bad_depth.ser",
        [np.zeros((4, 4), dtype=np.uint8)],
        pixel_depth_per_plane=24,
    )
    with pytest.raises(ImageReadError, match="PixelDepthPerPlane"):
        inspect_ser(bad_depth_path)

    # 5. Berkas terpotong (truncated pixel block)
    valid_path = _build_synthetic_ser_file(
        tmp_path / "truncated.ser",
        [np.zeros((10, 10), dtype=np.uint16) for _ in range(4)],
        color_id=0,
        pixel_depth_per_plane=16,
    )
    full_bytes = valid_path.read_bytes()
    valid_path.write_bytes(full_bytes[:-50])  # Potong 50 byte terakhir
    with pytest.raises(ImageReadError, match="terpotong atau korup"):
        inspect_ser(valid_path)


def test_ser_source_file_sha256_integrity_and_handle_closed(tmp_path: Path) -> None:
    """Berkas sumber .ser tidak boleh berubah sedikit pun dan handle file harus langsung tertutup."""
    frames = [np.arange(64, dtype=np.uint16).reshape(8, 8) + i for i in range(3)]
    ser_path = _build_synthetic_ser_file(
        tmp_path / "integrity.ser",
        frames,
        color_id=8,  # BAYER_RGGB
        pixel_depth_per_plane=16,
    )
    sha_before = hashlib.sha256(ser_path.read_bytes()).hexdigest()

    sm = SequenceManager()
    sm.open_ser_file(ser_path)
    _ = sm.load_frame(0)
    _ = sm.load_frame(2)
    sm.clear()

    sha_after = hashlib.sha256(ser_path.read_bytes()).hexdigest()
    assert sha_before == sha_after

    # Di Windows, rename akan gagal dengan PermissionError bila masih ada handle file terbuka
    renamed = tmp_path / "integrity_renamed.ser"
    ser_path.rename(renamed)
    assert renamed.exists()


def test_gui_ser_opening_navigation_and_metadata_card(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Menguji pembukaan berkas SER melalui MainWindow, kartu Informasi SER, dan navigasi frame."""
    _app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(MainWindow, "_show_warning", lambda self, msg: None)
    monkeypatch.setattr(MainWindow, "_show_error", lambda self, msg: None)

    frames = [
        np.full((12, 16), 1000, dtype=np.uint16),
        np.full((12, 16), 3000, dtype=np.uint16),
        np.full((12, 16), 6000, dtype=np.uint16),
    ]
    base_dt = datetime(2026, 8, 1, 12, 0, 0)
    ticks = [
        _datetime_to_ser_ticks(base_dt + timedelta(milliseconds=i * 100))
        for i in range(3)
    ]
    ser_path = _build_synthetic_ser_file(
        tmp_path / "hilal_capture.ser",
        frames,
        color_id=8,  # BAYER_RGGB
        little_endian_flag=1,
        pixel_depth_per_plane=14,
        observer="Observatorium Bosscha",
        instrument="ZWO ASI178MC",
        telescope="Refraktor 106mm",
        trailer_ticks=ticks,
    )

    win = MainWindow()
    ok = win.load_ser_path(ser_path)
    assert ok is True
    assert win.sequence_manager.input_mode == InputMode.SER
    assert not win.section_ser_info.isHidden()
    assert win.section_video_info.isHidden()
    assert win.section_fits_info.isHidden()

    assert win._info_values["input_mode"].text() == "SER Sequence"
    assert win._info_values["stacking_requirement"].text() == "Stacking: Wajib"
    assert "BAYER_RGGB" in win._info_values["ser_color_id"].text()
    assert win._info_values["ser_cfa_pattern"].text() == "RGGB"
    assert "14-bit" in win._info_values["ser_pixel_depth"].text()
    assert win._info_values["ser_observer"].text() == "Observatorium Bosscha"
    assert win._info_values["ser_instrument"].text() == "ZWO ASI178MC"

    # Navigasi ke frame berikutnya dan sebelumnya
    win.show_next_frame()
    assert win.sequence_manager.current_index == 1
    assert "2/3" in win._info_values["active_frame"].text()

    win.show_previous_frame()
    assert win.sequence_manager.current_index == 0

    win.close_image()
    assert win.section_ser_info.isHidden()
    assert win.sequence_manager.input_mode == InputMode.EMPTY
