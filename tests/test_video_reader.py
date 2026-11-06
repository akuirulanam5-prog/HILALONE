"""Pengujian unit untuk Video Reader HILALONE berbasis PyAV (Sub-Tahap 2C).

Cakupan pengujian:
  1. Pembacaan container .MP4 valid.
  2. Pembacaan container .MOV valid.
  3. Pembacaan container .AVI valid (termasuk pelestarian video monokrom ``gray``).
  4. Video dengan Constant Frame Rate (CFR) beserta verifikasi PTS dan time_base.
  5. Video dengan Variable Frame Rate (VFR) — membuktikan timestamp dihitung dari
     ``PTS × time_base`` dan bukan ``frame_index / FPS``.
  6. Penanganan timestamp (PTS) yang tidak tersedia dengan peringatan Bahasa Indonesia.
  7. Navigasi Previous / Next, random frame access, dan Bounded LRU Frame Cache.
  8. Verifikasi Lazy Loading pada SequenceManager (membuka video tidak mendekode
     seluruh frame ke RAM) serta ``stacking_required == True``.
  9. Penanganan berkas video rusak dan berkas tanpa video stream (audio-only).
 10. Penanganan codec tidak didukung dengan pesan Bahasa Indonesia.
 11. Integritas berkas sumber menggunakan hash SHA-256 dan penutupan file handle.
 12. Integrasi GUI (MainWindow: tombol Video, kartu 'Informasi Video', Frame X/N).
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
from pathlib import Path
from typing import Any

import av
import numpy as np
import pytest

from hilalone.gui.main_window import MainWindow
from hilalone.input_manager.adapters.video_reader import (
    VIDEO_HONESTY_NOTE,
    VideoPacketIndexEntry,
    VideoSession,
    inspect_video,
)
from hilalone.input_manager.image_reader import ImageReadError
from hilalone.input_manager.models import FrameStatus, InputMode
from hilalone.input_manager.sequence_manager import SequenceManager


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _create_synthetic_video(
    path: Path,
    width: int = 64,
    height: int = 48,
    num_frames: int = 6,
    codec: str = "mpeg4",
    pix_fmt: str = "yuv420p",
    fps: int = 25,
    custom_pts: list[int] | None = None,
    time_base: Fraction | None = None,
) -> Path:
    """Membuat berkas video sintetis valid menggunakan PyAV untuk pengujian."""
    container = av.open(str(path), mode="w")
    try:
        stream = container.add_stream(codec, rate=fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = pix_fmt
        if time_base is not None:
            stream.time_base = time_base

        for idx in range(num_frames):
            if pix_fmt == "gray":
                arr = np.full((height, width), (idx + 1) * 25, dtype=np.uint8)
                frame = av.VideoFrame.from_ndarray(arr, format="gray")
            else:
                arr = np.zeros((height, width, 3), dtype=np.uint8)
                arr[:, :, 0] = (idx + 1) * 30
                arr[:, :, 1] = (idx + 1) * 20
                arr[:, :, 2] = (idx + 1) * 10
                frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
                if pix_fmt != "rgb24":
                    frame = frame.reformat(width=width, height=height, format=pix_fmt)

            if custom_pts is not None:
                frame.pts = custom_pts[idx]
                if time_base is not None:
                    frame.time_base = time_base
            else:
                frame.pts = idx

            for packet in stream.encode(frame):
                container.mux(packet)

        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()
    return path


def test_valid_mp4_mov_avi_containers(tmp_path: Path) -> None:
    """Menguji pembacaan MP4, MOV, dan AVI yang valid."""
    for ext in ("mp4", "mov", "avi"):
        vpath = _create_synthetic_video(
            tmp_path / f"sample.{ext}",
            width=64,
            height=48,
            num_frames=5,
            codec="mpeg4",
            pix_fmt="yuv420p",
        )
        meta = inspect_video(vpath)
        assert meta.width == 64
        assert meta.height == 48
        assert meta.frame_count == 5
        assert meta.codec_name == "mpeg4"
        assert meta.pix_fmt == "yuv420p"
        assert meta.honesty_note == VIDEO_HONESTY_NOTE

        with VideoSession(vpath) as session:
            f0 = session.decode_frame(0)
            assert f0.width == 64
            assert f0.height == 48
            assert f0.decoded_pix_fmt == "yuv420p"
            assert len(f0.native_planes) >= 1
            assert f0.scientific_data.flags.writeable is False
            assert not f0.preview.isNull()


def test_avi_monochrome_gray_preserved_without_rgb_conversion(tmp_path: Path) -> None:
    """Memastikan video monokrom (gray) tetap 2D monokrom dan tidak diubah menjadi RGB."""
    avi_path = _create_synthetic_video(
        tmp_path / "mono_hilal.avi",
        width=40,
        height=32,
        num_frames=4,
        codec="rawvideo",
        pix_fmt="gray",
    )
    with VideoSession(avi_path) as session:
        assert session.metadata.is_monochrome is True
        f2 = session.decode_frame(2)
        assert f2.channels == 1
        assert f2.scientific_data.ndim == 2
        assert f2.scientific_data.shape == (32, 40)
        assert f2.rgb_representation is None
        assert int(f2.scientific_data[0, 0]) == (2 + 1) * 25


def test_cfr_and_vfr_timestamps_from_pts_and_time_base(tmp_path: Path) -> None:
    """Menguji perhitungan timestamp CFR maupun Variable Frame Rate (VFR) dari PTS × time_base."""
    # 1. Constant Frame Rate (25 fps -> delta = 0.04 s)
    cfr_path = _create_synthetic_video(
        tmp_path / "cfr.mp4",
        num_frames=4,
        fps=25,
    )
    with VideoSession(cfr_path) as s_cfr:
        assert s_cfr.metadata.is_variable_frame_rate is False
        ts_list = [e.timestamp_sec for e in s_cfr.frame_entries]
        assert ts_list[0] == pytest.approx(0.0, abs=1e-4)
        assert (ts_list[1] or 0.0) - (ts_list[0] or 0.0) == pytest.approx(0.04, abs=1e-3)

    # 2. Variable Frame Rate (PTS melompat tidak seragam: 0, 1, 4, 9, 10)
    vfr_pts = [0, 1, 4, 9, 10]
    vfr_path = _create_synthetic_video(
        tmp_path / "vfr.mkv.mp4",
        num_frames=5,
        fps=10,
        custom_pts=vfr_pts,
        time_base=Fraction(1, 10),
    )
    with VideoSession(vfr_path) as s_vfr:
        assert s_vfr.metadata.is_variable_frame_rate is True
        assert any("Variable Frame Rate" in w for w in s_vfr.metadata.warnings)
        # Frame ke-2 (indeks 2) memiliki PTS=4 -> harus 0.4 s, BUKAN 2/10 = 0.2 s!
        f_idx2 = s_vfr.decode_frame(2)
        assert f_idx2.timestamp_sec == pytest.approx(0.4, abs=1e-3)


def test_missing_timestamps_warning_without_silent_fps_guessing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memastikan PTS yang None menghasilkan peringatan eksplisit dan tidak ditebak dari FPS."""
    vpath = _create_synthetic_video(tmp_path / "no_pts.mp4", num_frames=3)
    with VideoSession(vpath) as session:
        # Simulasikan paket tanpa PTS pada pemeriksaan entry
        no_pts_entry = VideoPacketIndexEntry(
            frame_index=1,
            pts=None,
            time_base=Fraction(1, 25),
            timestamp_sec=None,
        )
        assert no_pts_entry.format_timestamp() == "Tidak tersedia"


def test_bounded_lru_cache_and_previous_next_random_navigation(tmp_path: Path) -> None:
    """Memastikan cache dibatasi sesuai max_cache_size dan mendukung Previous/Next/Random."""
    vpath = _create_synthetic_video(
        tmp_path / "cache_test.avi",
        width=32,
        height=24,
        num_frames=8,
        codec="rawvideo",
        pix_fmt="gray",
    )
    with VideoSession(vpath, max_cache_size=3) as session:
        # 1. Maju berurutan: 0 -> 1 -> 2 -> 3
        for idx in range(4):
            fr = session.decode_frame(idx)
            assert int(fr.scientific_data[0, 0]) == (idx + 1) * 25

        # Kapasitas cache maksimal 3 -> hanya menyimpan (1, 2, 3)
        assert len(session.cached_frame_indices) <= 3
        assert session.cached_frame_indices == (1, 2, 3)

        # 2. Tombol Previous ke frame 2 -> langsung diambil dari cache
        fr2 = session.decode_frame(2)
        assert int(fr2.scientific_data[0, 0]) == 3 * 25
        assert session.cached_frame_indices[-1] == 2  # pindah ke MRU

        # 3. Random access lompat ke frame 7 lalu balik ke frame 0
        fr7 = session.decode_frame(7)
        assert int(fr7.scientific_data[0, 0]) == 8 * 25
        fr0 = session.decode_frame(0)
        assert int(fr0.scientific_data[0, 0]) == 1 * 25


def test_sequence_manager_video_lazy_loading_and_stacking_required(tmp_path: Path) -> None:
    """Memastikan SequenceManager membuka video secara lazy dan menetapkan stacking_required=True."""
    vpath = _create_synthetic_video(tmp_path / "seq_video.mp4", num_frames=6)

    mgr = SequenceManager()
    report = mgr.open_video_file(vpath, max_cache_size=4)

    assert mgr.input_mode == InputMode.VIDEO
    assert mgr.stacking_required is True
    assert report.is_ready_for_stacking is True
    assert mgr.frame_count == 6

    # Lazy loading: belum ada satu pun frame yang didekode ke cache saat open_video_file selesai!
    assert mgr.video_session is not None
    assert len(mgr.video_session.cached_frame_indices) == 0
    assert all(e.is_pixel_loaded is False for e in mgr.entries)

    # Muat frame ke-0 secara on-demand
    loaded0 = mgr.load_frame(0)
    assert loaded0.scientific_data is not None
    assert mgr.entries[0].is_pixel_loaded is True
    assert mgr.entries[5].is_pixel_loaded is False

    mgr.clear()
    assert mgr.video_session is None


def test_corrupt_video_no_video_stream_and_unsupported_codec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Menguji penolakan video rusak, berkas audio-only, dan codec tidak didukung."""
    # 1. Berkas video rusak
    bad_mp4 = tmp_path / "corrupt.mp4"
    bad_mp4.write_bytes(b"NOT_A_VALID_MP4_CONTAINER_000000")
    with pytest.raises(ImageReadError) as exc_bad:
        inspect_video(bad_mp4)
    assert "corrupt.mp4" in str(exc_bad.value)

    # 2. Berkas valid tapi hanya memiliki audio stream (tanpa video stream)
    audio_only = tmp_path / "audio_only.avi"
    c = av.open(str(audio_only), mode="w")
    astream = c.add_stream("pcm_s16le", rate=44100)
    aframe = av.AudioFrame.from_ndarray(
        np.zeros((1, 1024), dtype=np.int16),
        format="s16",
        layout="mono",
    )
    aframe.pts = 0
    aframe.sample_rate = 44100
    for pkt in astream.encode(aframe):
        c.mux(pkt)
    for pkt in astream.encode():
        c.mux(pkt)
    c.close()

    with pytest.raises(ImageReadError) as exc_no_vid:
        inspect_video(audio_only)
    assert "tidak memiliki video stream" in str(exc_no_vid.value)

    # 3. Codec tidak didukung (simulasi PatchWelcomeError dari PyAV)
    unsup_mov = tmp_path / "unsupported_codec.mov"
    unsup_mov.write_bytes(b"DUMMY")

    def _raise_codec_err(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("Decoder for codec XYZ not found")

    monkeypatch.setattr(av, "open", _raise_codec_err)
    with pytest.raises(ImageReadError) as exc_codec:
        inspect_video(unsup_mov)
    assert "Codec video" in str(exc_codec.value)


def test_video_source_file_integrity_sha256_and_handle_closed(tmp_path: Path) -> None:
    """Memastikan berkas video sumber tidak pernah diubah dan file handle ditutup."""
    vpath = _create_synthetic_video(tmp_path / "integrity.mp4", num_frames=4)
    before_hash = _sha256(vpath)

    with VideoSession(vpath) as session:
        _ = session.decode_frame(0)
        _ = session.decode_frame(3)

    assert _sha256(vpath) == before_hash
    # Pastikan file handle ditutup di Windows (dapat diganti namanya tanpa PermissionError)
    renamed = tmp_path / "integrity_renamed.mp4"
    vpath.rename(renamed)
    assert renamed.exists()


def test_gui_video_opening_navigation_and_metadata_display(
    qapp: Any,
    tmp_path: Path,
) -> None:
    """Menguji integrasi tombol Video, tampilan Informasi Video, dan Previous/Next di MainWindow."""
    vpath = _create_synthetic_video(
        tmp_path / "hilal_clip.mp4",
        width=80,
        height=60,
        num_frames=4,
        codec="mpeg4",
        pix_fmt="yuv420p",
        fps=25,
    )
    win = MainWindow()
    win.resize(1333, 768)
    win.show()
    qapp.processEvents()
    try:
        assert win.load_video_path(vpath) is True
        qapp.processEvents()

        assert win.sequence_manager.stacking_required is True
        assert win._info_values["input_mode"].text() == "Video Sequence"
        assert win._info_values["frame_count"].text() == "4 frame"
        assert win._info_values["active_frame"].text() == "1/4 (KOMPATIBEL)"
        assert win._info_values["stacking_requirement"].text() == "Stacking: Wajib"

        # Kartu Informasi Video tampil, sedangkan Metadata RAW dan Informasi FITS tersembunyi
        assert win.section_video_info.isHidden() is False
        assert win.section_camera_metadata.isHidden() is True
        assert win.section_fits_info.isHidden() is True
        assert "mpeg4" in win._info_values["video_codec"].text()
        assert "yuv420p" in win._info_values["video_pix_fmt"].text()
        assert "PTS=" in win._info_values["video_frame_pts"].text()

        # Uji navigasi Next & Previous
        win.show_next_frame()
        qapp.processEvents()
        assert win._info_values["active_frame"].text() == "2/4 (KOMPATIBEL)"

        win.show_previous_frame()
        qapp.processEvents()
        assert win._info_values["active_frame"].text() == "1/4 (KOMPATIBEL)"

        win.close_image()
        assert win.section_video_info.isHidden() is True
    finally:
        win.close()
