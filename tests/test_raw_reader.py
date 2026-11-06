"""Pengujian unit untuk Camera RAW Reader HILALONE (Sub-Tahap 2B).

Cakupan pengujian:
  1. Pendaftaran ekstensi kandidat RAW pada ``supported_extensions()``.
  2. Pelestarian ``raw_image`` (penuh) dan ``raw_image_visible`` (aktif) sebagai
     array sensor terpisah, disalin sebelum ``RawPy.close()`` dipanggil, tanpa
     normalisasi permanen, dan dikunci ``writeable = False``.
  3. Ekstraksi metadata CFA: Bayer 2×2 (RGGB, BGGR, GRBG, GBRG), X-Trans 6×6,
     dan sensor Non-CFA/Stacked tanpa mengasumsikan semua sensor Bayer 2×2.
  4. Pemisahan tegas antara ``scientific_data`` (mosaic sensor 2D ``uint16``),
     ``demosaiced_rgb`` (RGB turunan 16-bit), dan ``preview`` (``QImage`` 8-bit),
     serta verifikasi parameter eksplisit ``postprocess``:
       * ``no_auto_bright=True``
       * ``gamma=(1, 1)``
       * ``output_bps=16``
       * ``fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off``
       * ``median_filter_passes=0``
  5. Ekstraksi metadata kamera (Make/Model dari header TIFF/CR3/RAF maupun objek,
     ISO, shutter speed, aperture, focal length, black level, white level,
     white balance, dan timestamp) serta penanganan metadata tidak lengkap.
  6. Penanganan kamera tidak didukung (``LibRawFileUnsupportedError``) dan
     berkas rusak (menggunakan LibRaw C++ nyata dan mock) dengan pesan Bahasa
     Indonesia serta penutupan file handle.
  7. Integritas berkas sumber menggunakan hash SHA-256.
  8. Integrasi dengan ``SequenceManager`` (lazy loading tanpa demosaicing di awal).
  9. Pengujian otomatis dengan berkas RAW kamera nyata bila tersedia di disk.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import struct
from typing import Any

import numpy as np
import pytest
import rawpy

from hilalone.input_manager.adapters.raw_reader import (
    DEMOSAIC_HONESTY_NOTE,
    RAW_EXTENSIONS,
    inspect_raw_header,
    read_raw,
)
from hilalone.input_manager.image_reader import (
    ImageReadError,
    inspect_image_header,
    read_image,
    supported_extensions,
)
from hilalone.input_manager.models import FrameStatus
from hilalone.input_manager.sequence_manager import SequenceManager


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_minimal_tiff_ifd0_header(
    path: Path,
    make: str = "Canon",
    model: str = "Canon EOS 60D",
    date_time: str = "2026:06:16 17:25:10",
) -> None:
    """Menulis header biner TIFF IFD0 minimal berisi tag Make (271), Model (272), DateTime (306)."""
    make_b = make.encode("ascii") + b"\x00"
    model_b = model.encode("ascii") + b"\x00"
    dt_b = date_time.encode("ascii") + b"\x00"

    ifd_offset = 8
    num_entries = 3
    data_start = ifd_offset + 2 + (num_entries * 12) + 4

    make_off = data_start
    model_off = make_off + len(make_b)
    dt_off = model_off + len(model_b)

    buf = bytearray()
    buf += b"II"
    buf += struct.pack("<HI", 42, ifd_offset)
    buf += struct.pack("<H", num_entries)
    buf += struct.pack("<HHII", 271, 2, len(make_b), make_off)
    buf += struct.pack("<HHII", 272, 2, len(model_b), model_off)
    buf += struct.pack("<HHII", 306, 2, len(dt_b), dt_off)
    buf += struct.pack("<I", 0)
    buf += make_b + model_b + dt_b
    path.write_bytes(bytes(buf))


class _MockRawPy:
    """Mock realistis untuk ``rawpy.RawPy`` yang mensimulasikan memori C++ LibRaw.

    Saat ``close()`` dipanggil, buffer internal ``_raw_full_buf`` dan
    ``_raw_vis_buf`` sengaja dihancurkan (diisi 0) untuk membuktikan bahwa
    ``read_raw()`` benar-benar telah menyalin (``.copy()``) array sebelum
    menutup objek ``RawPy``.
    """

    def __init__(
        self,
        raw_full: np.ndarray,
        raw_visible: np.ndarray,
        raw_pattern: np.ndarray | None = None,
        color_desc: bytes = b"RGBG",
        raw_type: Any = rawpy.RawType.Flat,
        num_colors: int = 3,
        black_level: tuple[int, ...] = (512, 512, 512, 512),
        white_level: int = 16383,
        camera_wb: tuple[float, ...] = (2.105, 1.0, 1.482, 0.0),
        daylight_wb: tuple[float, ...] = (2.25, 1.0, 1.35, 0.0),
        iso_speed: float = 400.0,
        shutter_speed: float = 0.008,  # 1/125 s
        aperture: float = 5.6,
        focal_length: float = 200.0,
        timestamp: float = 1781630710.0,
        top_margin: int = 4,
        left_margin: int = 6,
    ) -> None:
        self._raw_full_buf = raw_full.copy()
        self._raw_vis_buf = raw_visible.copy()
        self.raw_pattern = (
            raw_pattern
            if raw_pattern is not None
            else np.array([[0, 1], [3, 2]], dtype=np.uint8)
        )
        self.color_desc = color_desc
        self.raw_type = raw_type
        self.num_colors = num_colors
        self.black_level_per_channel = list(black_level)
        self.camera_white_level_per_channel = [white_level] * 4
        self.white_level = white_level
        self.camera_whitebalance = list(camera_wb)
        self.daylight_whitebalance = list(daylight_wb)

        raw_h, raw_w = self._raw_full_buf.shape[:2]
        vis_h, vis_w = self._raw_vis_buf.shape[:2]
        self.sizes = rawpy.ImageSizes(
            raw_height=raw_h,
            raw_width=raw_w,
            height=vis_h,
            width=vis_w,
            top_margin=top_margin,
            left_margin=left_margin,
            iheight=vis_h,
            iwidth=vis_w,
            pixel_aspect=1.0,
            flip=0,
            crop_left_margin=0,
            crop_top_margin=0,
            crop_width=vis_w,
            crop_height=vis_h,
        )
        self.other = rawpy.Other(
            iso_speed=iso_speed,
            shutter_speed=shutter_speed,
            aperture=aperture,
            focal_length=focal_length,
            timestamp=timestamp,
            shot_order=0,
            artist="",
        )
        self.lens = rawpy.Lens(
            model="EF 200mm f/2.8L",
            make="Canon",
            min_focal=200.0,
            max_focal=200.0,
        )
        self.closed: bool = False
        self.postprocess_called: bool = False
        self.last_postprocess_kwargs: dict[str, Any] = {}

    @property
    def raw_image(self) -> np.ndarray:
        if self.closed:
            raise RuntimeError("Akses ke raw_image setelah RawPy.close() dilarang!")
        return self._raw_full_buf

    @property
    def raw_image_visible(self) -> np.ndarray:
        if self.closed:
            raise RuntimeError("Akses ke raw_image_visible setelah RawPy.close() dilarang!")
        return self._raw_vis_buf

    def postprocess(self, params: Any = None, **kwargs: Any) -> np.ndarray:
        if self.closed:
            raise RuntimeError("Akses ke postprocess setelah RawPy.close() dilarang!")
        self.postprocess_called = True
        self.last_postprocess_kwargs = dict(kwargs)
        vis_h, vis_w = self._raw_vis_buf.shape[:2]
        # Buat representasi RGB 16-bit deterministik yang berbeda dari mosaic 2D
        rgb = np.zeros((vis_h, vis_w, 3), dtype=np.uint16)
        base = self._raw_vis_buf if self._raw_vis_buf.ndim == 2 else self._raw_vis_buf[:, :, 0]
        rgb[:, :, 0] = np.clip(base.astype(np.uint32) + 100, 0, 65535).astype(np.uint16)
        rgb[:, :, 1] = np.clip(base.astype(np.uint32) + 200, 0, 65535).astype(np.uint16)
        rgb[:, :, 2] = np.clip(base.astype(np.uint32) + 300, 0, 65535).astype(np.uint16)
        return rgb

    def close(self) -> None:
        self.closed = True
        # Hancurkan isi buffer internal seperti LibRaw::recycle() di C++
        self._raw_full_buf.fill(0)
        self._raw_vis_buf.fill(0)


def test_supported_extensions_include_raw_formats() -> None:
    exts = supported_extensions()
    for raw_ext in RAW_EXTENSIONS:
        assert raw_ext in exts, f"Ekstensi RAW .{raw_ext} belum terdaftar di supported_extensions()"


def test_raw_sensor_preservation_and_copy_before_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memastikan raw_image & raw_image_visible disalin sebelum close() dan nilainya utuh."""
    cr2_path = tmp_path / "hilal_001.cr2"
    _write_minimal_tiff_ifd0_header(cr2_path, make="Canon", model="Canon EOS 60D")
    before_hash = _sha256(cr2_path)

    # Buat sensor penuh 24x32 dengan margin (top=4, left=6) dan area aktif 16x20
    full_sensor = np.arange(24 * 32, dtype=np.uint16).reshape(24, 32) + 512
    vis_sensor = full_sensor[4 : 4 + 16, 6 : 6 + 20].copy()
    expected_vis = vis_sensor.copy()
    expected_full = full_sensor.copy()

    mock_instance = _MockRawPy(raw_full=full_sensor, raw_visible=vis_sensor)
    monkeypatch.setattr(rawpy, "imread", lambda _p: mock_instance)

    loaded = read_image(cr2_path)

    # 1. Objek RawPy wajib sudah ditutup
    assert mock_instance.closed is True

    # 2. Sekalipun buffer internal mock telah dihancurkan saat close(), data kita tetap utuh!
    assert loaded.scientific_data is not None
    assert loaded.raw_image_visible is not None
    assert loaded.raw_image_full is not None
    assert loaded.scientific_data.dtype == np.uint16
    assert loaded.scientific_data.shape == (16, 20)
    assert loaded.raw_image_full.shape == (24, 32)
    np.testing.assert_array_equal(loaded.scientific_data, expected_vis)
    np.testing.assert_array_equal(loaded.raw_image_visible, expected_vis)
    np.testing.assert_array_equal(loaded.raw_image_full, expected_full)

    # 3. Semua array ilmiah dikunci (read-only)
    assert loaded.scientific_data.flags.writeable is False
    assert loaded.raw_image_visible.flags.writeable is False
    assert loaded.raw_image_full.flags.writeable is False

    # 4. Dimensi aktif vs dimensi sensor penuh tercatat jujur
    assert loaded.info.width == 20
    assert loaded.info.height == 16
    assert loaded.info.stored_width == 32
    assert loaded.info.stored_height == 24
    assert loaded.info.original_bit_depth == 16
    assert loaded.info.dtype_str == "uint16"

    # 5. Berkas sumber tidak pernah berubah
    assert _sha256(cr2_path) == before_hash


def test_raw_demosaicing_explicit_parameters_and_separation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memastikan postprocess dipanggil dengan parameter jujur dan tidak menggantikan data sensor."""
    nef_path = tmp_path / "moon_raw.nef"
    _write_minimal_tiff_ifd0_header(nef_path, make="Nikon", model="Nikon D850")

    vis_sensor = np.full((12, 18), 4096, dtype=np.uint16)
    mock_instance = _MockRawPy(raw_full=vis_sensor, raw_visible=vis_sensor, top_margin=0, left_margin=0)
    monkeypatch.setattr(rawpy, "imread", lambda _p: mock_instance)

    loaded = read_image(nef_path)

    # Periksa argumen eksplisit pada postprocess
    assert mock_instance.postprocess_called is True
    kw = mock_instance.last_postprocess_kwargs
    assert kw["no_auto_bright"] is True
    assert kw["gamma"] == (1, 1)
    assert kw["output_bps"] == 16
    assert kw["fbdd_noise_reduction"] == rawpy.FBDDNoiseReductionMode.Off
    assert kw["median_filter_passes"] == 0

    # Pastikan scientific_data tetap mosaic 2D (12, 18), sedangkan demosaiced_rgb adalah 3D (12, 18, 3)
    assert loaded.scientific_data is not None
    assert loaded.demosaiced_rgb is not None
    assert loaded.scientific_data.ndim == 2
    assert loaded.scientific_data.shape == (12, 18)
    assert loaded.demosaiced_rgb.ndim == 3
    assert loaded.demosaiced_rgb.shape == (12, 18, 3)
    assert loaded.demosaiced_rgb.dtype == np.uint16
    assert loaded.demosaiced_rgb.flags.writeable is False

    # Preview adalah QImage 8-bit terpisah untuk layar
    assert not loaded.preview.isNull()
    assert loaded.preview.width() == 18
    assert loaded.preview.height() == 12
    assert loaded.info.preview_bit_depth == 8

    # Catatan kejujuran demosaicing tercatat di metadata
    assert loaded.info.raw_metadata is not None
    assert loaded.info.raw_metadata.demosaic_note == DEMOSAIC_HONESTY_NOTE
    assert "BUKAN data sensor RAW asli" in loaded.info.raw_metadata.summary_text()


@pytest.mark.parametrize(
    ("pattern_arr", "color_desc", "expected_label"),
    [
        (np.array([[0, 1], [3, 2]], dtype=np.uint8), b"RGBG", "RGGB (Bayer 2×2)"),
        (np.array([[2, 1], [3, 0]], dtype=np.uint8), b"RGBG", "BGGR (Bayer 2×2)"),
        (np.array([[1, 0], [2, 3]], dtype=np.uint8), b"RGBG", "GRBG (Bayer 2×2)"),
        (np.array([[1, 2], [0, 3]], dtype=np.uint8), b"RGBG", "GBRG (Bayer 2×2)"),
    ],
)
def test_raw_cfa_bayer_2x2_variants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pattern_arr: np.ndarray,
    color_desc: bytes,
    expected_label: str,
) -> None:
    """Memeriksa berbagai susunan Bayer 2x2 (RGGB, BGGR, GRBG, GBRG)."""
    arw_path = tmp_path / "bayer_test.arw"
    _write_minimal_tiff_ifd0_header(arw_path, make="Sony", model="ILCE-7M3")

    sensor = np.ones((8, 10), dtype=np.uint16) * 1024
    mock_instance = _MockRawPy(
        raw_full=sensor,
        raw_visible=sensor,
        raw_pattern=pattern_arr,
        color_desc=color_desc,
    )
    monkeypatch.setattr(rawpy, "imread", lambda _p: mock_instance)

    res = read_raw(arw_path)
    assert res.metadata.cfa_pattern_str == expected_label
    assert res.metadata.color_desc == "RGBG"
    assert res.metadata.is_cfa_mosaic is True
    assert res.metadata.raw_pattern_matrix == tuple(
        tuple(int(v) for v in row) for row in pattern_arr.tolist()
    )


def test_raw_non_bayer_xtrans_6x6_and_stacked_sensors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memastikan RAW Reader tidak mengasumsikan semua sensor Bayer 2x2 (mendukung X-Trans 6x6 & Stacked)."""
    raf_path = tmp_path / "fujifilm_xtrans.raf"
    # Tulis header RAF Fujifilm
    raf_header = b"FUJIFILMCCD-RAW 0201" + b"\x00" * 8 + b"X-T4\x00".ljust(32, b"\x00")
    raf_path.write_bytes(raf_header + b"\x00" * 128)

    # Buat matriks 6x6 X-Trans
    xtrans_pattern = np.zeros((6, 6), dtype=np.uint8)
    xtrans_pattern[0] = [1, 0, 1, 1, 2, 1]
    xtrans_pattern[1] = [2, 1, 2, 0, 1, 0]

    sensor = np.ones((12, 12), dtype=np.uint16) * 2048
    mock_xtrans = _MockRawPy(
        raw_full=sensor,
        raw_visible=sensor,
        raw_pattern=xtrans_pattern,
        color_desc=b"RGB",
    )
    monkeypatch.setattr(rawpy, "imread", lambda _p: mock_xtrans)

    res_xtrans = read_raw(raf_path)
    assert "6×6" in res_xtrans.metadata.cfa_pattern_str
    assert res_xtrans.metadata.is_cfa_mosaic is True
    assert res_xtrans.metadata.camera_make == "Fujifilm"
    assert res_xtrans.metadata.camera_model == "X-T4"
    assert len(res_xtrans.metadata.raw_pattern_matrix or ()) == 6

    # Uji sensor Stacked / Non-CFA (mis. Foveon / Linear DNG)
    dng_path = tmp_path / "linear_stacked.dng"
    _write_minimal_tiff_ifd0_header(dng_path, make="Sigma", model="sd Quattro")
    stacked_sensor = np.ones((10, 14, 3), dtype=np.uint16) * 1500
    mock_stacked = _MockRawPy(
        raw_full=stacked_sensor,
        raw_visible=stacked_sensor,
        raw_pattern=None,
        raw_type=rawpy.RawType.Stack,
    )
    monkeypatch.setattr(rawpy, "imread", lambda _p: mock_stacked)

    res_stacked = read_raw(dng_path)
    assert res_stacked.metadata.is_cfa_mosaic is False
    assert "Non-CFA" in res_stacked.metadata.cfa_pattern_str
    assert res_stacked.channels == 3


def test_raw_metadata_extraction_complete_and_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memeriksa ekstraksi metadata lengkap maupun ketika sebagian metadata tidak tersedia."""
    cr2_path = tmp_path / "meta_complete.cr2"
    _write_minimal_tiff_ifd0_header(cr2_path, make="Canon", model="EOS R6")

    sensor = np.ones((10, 16), dtype=np.uint16) * 1000
    mock_complete = _MockRawPy(
        raw_full=sensor,
        raw_visible=sensor,
        black_level=(512, 512, 512, 512),
        white_level=16383,
        iso_speed=800.0,
        shutter_speed=0.004,  # 1/250 s
        aperture=4.0,
        focal_length=300.0,
        timestamp=1781630710.0,
    )
    monkeypatch.setattr(rawpy, "imread", lambda _p: mock_complete)

    res = read_raw(cr2_path)
    meta = res.metadata
    assert meta.camera_make == "Canon"
    assert meta.camera_model == "EOS R6"
    assert meta.iso_speed == 800.0
    assert meta.shutter_speed_sec == pytest.approx(0.004)
    assert meta.aperture_fnumber == pytest.approx(4.0)
    assert meta.focal_length_mm == pytest.approx(300.0)
    assert meta.black_level_per_channel == (512, 512, 512, 512)
    assert meta.white_level == 16383
    assert meta.timestamp_str == "2026-06-16T17:25:10Z"

    disp = meta.to_display_dict()
    assert disp["CAMERA"] == "Canon EOS R6"
    assert disp["ISO"] == "800"
    assert "1/250 s" in disp["SHUTTER"]
    assert disp["APERTURE"] == "f/4.0"
    assert disp["FOCAL_LENGTH"] == "300.0 mm"

    # Sekarang uji berkas dengan metadata eksposur tidak tersedia (0 / None)
    empty_path = tmp_path / "meta_incomplete.orf"
    empty_path.write_bytes(b"NOT_A_TIFF_HEADER_JUST_RAW_BYTES")
    mock_incomplete = _MockRawPy(
        raw_full=sensor,
        raw_visible=sensor,
        black_level=(),
        white_level=0,
        camera_wb=(0.0, 0.0, 0.0, 0.0),
        iso_speed=0.0,
        shutter_speed=0.0,
        aperture=0.0,
        focal_length=0.0,
        timestamp=0.0,
    )
    monkeypatch.setattr(rawpy, "imread", lambda _p: mock_incomplete)

    res_inc = read_raw(empty_path)
    disp_inc = res_inc.metadata.to_display_dict()
    assert disp_inc["CAMERA"] == "Tidak tersedia"
    assert disp_inc["ISO"] == "Tidak tersedia"
    assert disp_inc["SHUTTER"] == "Tidak tersedia"
    assert disp_inc["APERTURE"] == "Tidak tersedia"
    assert disp_inc["FOCAL_LENGTH"] == "Tidak tersedia"
    assert disp_inc["TIMESTAMP"] == "Tidak tersedia"


def test_unsupported_raw_camera_and_corrupt_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Menguji penanganan berkas rusak (LibRaw C++ asli) dan kamera yang belum didukung."""
    # 1. Pengujian langsung dengan LibRaw C++ asli pada berkas .CR2 / .NEF rusak
    corrupt_cr2 = tmp_path / "corrupt_camera.cr2"
    corrupt_cr2.write_bytes(b"THIS_IS_CORRUPT_RAW_DATA_1234567890")
    before_hash = _sha256(corrupt_cr2)

    with pytest.raises(ImageReadError) as exc_info:
        read_image(corrupt_cr2)
    assert "corrupt_camera.cr2" in str(exc_info.value)

    # Pastikan file tidak berubah dan file handle ditutup (dapat diganti namanya di Windows)
    assert _sha256(corrupt_cr2) == before_hash
    renamed = tmp_path / "corrupt_camera_renamed.cr2"
    corrupt_cr2.rename(renamed)
    renamed.rename(corrupt_cr2)

    # 2. Pengujian spesifik saat LibRaw menyatakan model kamera belum didukung
    unsupported_cr3 = tmp_path / "future_camera.cr3"
    unsupported_cr3.write_bytes(b"FUTURE_CAMERA_RAW")

    def _raise_unsupported(_path: str) -> Any:
        raise rawpy.LibRawFileUnsupportedError("Unsupported camera model")

    monkeypatch.setattr(rawpy, "imread", _raise_unsupported)
    with pytest.raises(ImageReadError) as exc_unsup:
        read_image(unsupported_cr3)
    msg = str(exc_unsup.value)
    assert "belum didukung oleh LibRaw" in msg
    assert "Tidak semua kamera" in msg


def test_raw_sequence_lazy_loading_and_navigation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memastikan SequenceManager memeriksa header RAW secara lazy tanpa menjalankan postprocess."""
    f1 = tmp_path / "raw_1.cr2"
    f2 = tmp_path / "raw_2.cr2"
    _write_minimal_tiff_ifd0_header(f1, make="Canon", model="EOS 60D")
    _write_minimal_tiff_ifd0_header(f2, make="Canon", model="EOS 60D")

    sensor1 = np.full((14, 22), 1000, dtype=np.uint16)
    sensor2 = np.full((14, 22), 2000, dtype=np.uint16)
    mocks = {
        str(f1): _MockRawPy(raw_full=sensor1, raw_visible=sensor1, timestamp=1781630701.0),
        str(f2): _MockRawPy(raw_full=sensor2, raw_visible=sensor2, timestamp=1781630705.0),
    }

    postprocess_count = 0

    def _mock_imread(path_str: str) -> _MockRawPy:
        # Buat instance baru setiap kali dibuka agar status closed dapat diuji berulang
        base = mocks[path_str]
        m = _MockRawPy(
            raw_full=base._raw_full_buf if not base.closed else sensor1,
            raw_visible=base._raw_vis_buf if not base.closed else sensor1,
            timestamp=base.other.timestamp,
        )
        orig_pp = m.postprocess

        def _tracked_pp(*args: Any, **kwargs: Any) -> np.ndarray:
            nonlocal postprocess_count
            postprocess_count += 1
            return orig_pp(*args, **kwargs)

        m.postprocess = _tracked_pp  # type: ignore[method-assign]
        return m

    monkeypatch.setattr(rawpy, "imread", _mock_imread)

    mgr = SequenceManager()
    report = mgr.open_files([f1, f2], sort_by="timestamp")

    # Saat open_files (lazy header inspection), postprocess TIDAK boleh dipanggil sama sekali!
    assert postprocess_count == 0
    assert mgr.stacking_required is True
    assert report.is_ready_for_stacking is True
    assert report.compatible_count == 2
    assert all(e.status == FrameStatus.COMPATIBLE for e in mgr.entries)
    assert all(e.is_pixel_loaded is False for e in mgr.entries)

    # Ketika load_frame(1) dipanggil, barulah frame ke-2 didekode & di-demosaic
    loaded_1 = mgr.load_frame(1)
    assert postprocess_count == 1
    assert mgr.entries[1].is_pixel_loaded is True
    assert loaded_1.scientific_data is not None
    assert loaded_1.scientific_data.shape == (14, 22)


def test_gui_raw_metadata_label_and_honest_bit_depth(
    qapp: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memastikan GUI menampilkan 4 kelompok informasi, QScrollArea, dan bit depth jujur."""
    from PySide6.QtCore import Qt
    from hilalone.gui.main_window import STACKING_HONESTY_NOTE, MainWindow

    nef1 = tmp_path / "nikon_z6_01.nef"
    nef2 = tmp_path / "nikon_z6_02.nef"
    _write_minimal_tiff_ifd0_header(nef1, make="NIKON CORPORATION", model="NIKON Z 6")
    _write_minimal_tiff_ifd0_header(
        nef2,
        make="NIKON CORPORATION",
        model="NIKON Z 6 II - Astro Modified Edition with Extended Long Metadata Name",
    )

    full1 = np.full((24, 32), 2048, dtype=np.uint16)
    vis1 = full1[2:22, 4:28].copy()  # 20x24 aktif vs 24x32 penuh
    full2 = np.full((24, 32), 3000, dtype=np.uint16)
    vis2 = full2[2:22, 4:28].copy()

    def _mock_imread(path_str: str) -> _MockRawPy:
        if path_str.endswith("01.nef"):
            return _MockRawPy(
                raw_full=full1,
                raw_visible=vis1,
                white_level=16383,
                iso_speed=400.0,
                shutter_speed=0.008,
                aperture=5.6,
                focal_length=200.0,
                timestamp=1781630701.0,
            )
        return _MockRawPy(
            raw_full=full2,
            raw_visible=vis2,
            white_level=16383,
            iso_speed=1600.0,
            shutter_speed=0.02,
            aperture=0.0,  # tidak tersedia (mis. teleskop tanpa chip bukaan)
            focal_length=0.0,  # tidak tersedia
            timestamp=1781630715.0,
        )

    monkeypatch.setattr(rawpy, "imread", _mock_imread)

    win = MainWindow()
    win.show()
    qapp.processEvents()
    try:
        # 1. Pastikan QScrollArea tersedia dan horizontal scrollbar dinonaktifkan
        assert win.info_scroll_area.widgetResizable() is True
        assert (
            win.info_scroll_area.horizontalScrollBarPolicy()
            == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        # 2. Uji Single RAW pada resolusi jendela 1333x768
        win.resize(1333, 768)
        qapp.processEvents()
        assert win.load_path(nef1) is True
        qapp.processEvents()

        assert win._info_values["input_mode"].text() == "Single Image"
        assert win._info_values["stacking_requirement"].text() == "Tidak diperlukan"
        # Baris khusus sequence harus tersembunyi pada mode Single Image
        assert win._info_values["frame_count"].isHidden() is True
        assert win._info_values["active_frame"].isHidden() is True
        assert win._info_values["structural_readiness"].isHidden() is True

        # Resolusi aktif vs penuh (tampil karena 24x20 != 32x24)
        assert win._info_values["active_resolution"].text() == "24 × 20 px"
        assert win._info_values["full_resolution"].isHidden() is False
        assert win._info_values["full_resolution"].text() == "32 × 24 px"

        # Sensor Information: storage dtype, white level, black level, preview
        assert win._info_values["storage_dtype"].text() == "uint16"
        assert win._info_values["white_level"].text() == "16383"
        assert win._info_values["black_level"].text() == "512, 512, 512, 512"
        assert win._info_values["preview_info"].text() == "3 kanal (RGB Demosaiced), 8-bit"
        assert (
            win._info_values["bit_depth"].text()
            == "Storage dtype: uint16 | White level: 16383 | Display preview: 8-bit"
        )
        assert "16-bit" not in win._info_values["bit_depth"].text()

        # Camera Metadata: tampil lengkap untuk nef1 dengan judul 'Metadata RAW' (bukan Header FITS)
        assert win.header_camera_metadata.text() == "Metadata RAW"
        assert win.section_camera_metadata.isHidden() is False
        assert win.section_fits_info.isHidden() is True
        assert win._info_values["camera_model"].text() == "NIKON CORPORATION NIKON Z 6"
        assert win._info_values["iso"].text() == "400"
        assert win._info_values["aperture"].isHidden() is False
        assert win._info_values["aperture"].text() == "f/5.6"

        # 3. Uji Multiple RAW & perpindahan frame serta ukuran jendela kecil (800x560)
        win.resize(800, 560)
        qapp.processEvents()
        assert win.load_sequence_paths([nef1, nef2]) is True
        qapp.processEvents()

        assert win._info_values["input_mode"].text() == "Multiple Images"
        assert win._info_values["frame_count"].isHidden() is False
        assert win._info_values["frame_count"].text() == "2 frame"
        assert win._info_values["active_frame"].text() == "1/2 (KOMPATIBEL)"
        assert win._info_values["stacking_requirement"].text() == "Stacking: Wajib"
        assert win._info_values["structural_readiness"].text() == "Siap"
        assert STACKING_HONESTY_NOTE in win._info_values["stacking_note"].text()

        # Pindah ke frame ke-2: metadata harus mengikuti file ke-2 dan menyembunyikan aperture/focal_length yang kosong
        win.show_next_frame()
        qapp.processEvents()
        assert win._info_values["active_frame"].text() == "2/2 (KOMPATIBEL)"
        assert win._info_values["file_name"].text() == "nikon_z6_02.nef"
        assert "Astro Modified Edition" in win._info_values["camera_model"].text()
        assert win._info_values["iso"].text() == "1600"
        assert win._info_values["aperture"].isHidden() is True
        assert win._info_values["focal_length"].isHidden() is True

        # Panel tetap terlihat dan tidak tersembunyi pada jendela kecil
        assert win.info_panel.isVisible() is True
        assert win.viewer.isVisible() is True

        win.close_image()
        assert win._info_keys["fits_metadata"].text() == "Metadata sumber"
    finally:
        win.close()


def test_real_camera_raw_file_if_present() -> None:
    """Menguji pembacaan berkas RAW kamera nyata di C:\\Astrofotografer bila tersedia."""
    search_root = Path(r"C:\Astrofotografer")
    if not search_root.exists():
        pytest.skip("Folder C:\\Astrofotografer tidak ditemukan.")

    exts = {f".{e}" for e in RAW_EXTENSIONS}
    candidates = [
        p for p in search_root.rglob("*") if p.is_file() and p.suffix.lower() in exts
    ]
    if not candidates:
        pytest.skip("Belum ada berkas Camera RAW nyata di C:\\Astrofotografer.")

    sample = candidates[0]
    before_hash = _sha256(sample)
    info = inspect_image_header(sample)
    loaded = read_image(sample)
    after_hash = _sha256(sample)

    assert before_hash == after_hash
    assert info.width == loaded.info.width
    assert loaded.scientific_data is not None
    assert loaded.scientific_data.flags.writeable is False
    assert loaded.demosaiced_rgb is not None
    assert not loaded.preview.isNull()
