"""Verifikasi end-to-end fitur inti di dalam runtime executable HILALONE terbundel.

Hanya dijalankan ketika aplikasi dipanggil dengan argumen ``--bundle-verify <dir>``
untuk memastikan seluruh modul, aset, plugin Qt, dan pustaka C/DLL di bundle bekerja.
"""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

import av
import numpy as np
from PIL import Image
from PySide6.QtWidgets import QApplication
import rawpy
import tifffile
from astropy.io import fits

from hilalone import APP_NAME, __version__
from hilalone.gui.main_window import MainWindow
from hilalone.gui.resources import get_app_icon, get_logo_pixmap, get_project_root
from hilalone.processing import (
    PreviewMode,
    ProcessingPipelineOrchestrator,
    ProcessingProfile,
    run_background_extraction,
    run_image_enhancement,
)


def _write_synthetic_ser(path: Path, n_frames: int = 3, h: int = 48, w: int = 64) -> None:
    """Membuat berkas SER 8-bit monokrom sintetis sesuai spesifikasi header 178-byte."""
    header = bytearray(178)
    header[0:14] = b"LUCAM-RECORDER"
    struct.pack_into("<IIIIIII", header, 14, 0, 0, 0, w, h, 8, n_frames)
    rng = np.random.default_rng(42)
    frames = []
    for _ in range(n_frames):
        frame = np.clip(rng.normal(80, 5, (h, w)), 0, 255).astype(np.uint8)
        frame[20:26, 28:38] = 200
        frames.append(frame.tobytes())
    with open(path, "wb") as f:
        f.write(header)
        for chunk in frames:
            f.write(chunk)


def _write_synthetic_video(path: Path, codec: str, n_frames: int = 4, h: int = 48, w: int = 64) -> None:
    """Membuat berkas video sintetis (AVI/MP4) menggunakan PyAV terbundel."""
    container = av.open(str(path), mode="w")
    try:
        stream = container.add_stream(codec, rate=10)
        stream.width = w
        stream.height = h
        stream.pix_fmt = "yuv420p" if codec in {"mpeg4", "libx264"} else "rgb24"
        for i in range(n_frames):
            arr = np.full((h, w, 3), 50 + i * 10, dtype=np.uint8)
            arr[18:24, 24:40] = 220
            frame = av.VideoFrame.from_ndarray(arr, format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    finally:
        container.close()


def run_bundle_verification(work_dir: Path, app: QApplication) -> int:
    """Menjalankan pengujian menyeluruh dalam runtime executable terbundel dan menyimpan JSON."""
    work_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict[str, str]] = {}

    def record(key: str, status: str, detail: str) -> None:
        results[key] = {"status": status, "detail": detail}

    win = MainWindow()
    try:
        win.show()
        app.processEvents()
        record("app_launch", "PASS", f"{APP_NAME} v{__version__} frozen={hasattr(sys, '_MEIPASS')} root={get_project_root()}")

        # 2-4. Logo & Tema
        logo_std = get_logo_pixmap(False)
        logo_nv = get_logo_pixmap(True)
        ico = get_app_icon()
        if not logo_std.isNull() and not logo_nv.isNull() and not ico.isNull():
            record("logo_and_icon", "PASS", f"std={logo_std.size().toTuple()}, nv={logo_nv.size().toTuple()}")
        else:
            record("logo_and_icon", "FAIL", "Salah satu aset logo/ikon bernilai null")

        record("theme_standard_dark", "PASS" if not win._is_night_vision else "FAIL", f"night_vision={win._is_night_vision}")
        win.toggle_night_vision_theme(True, persist=False)
        app.processEvents()
        nv_ok = win._is_night_vision and "#c84b4b" in win.viewer._empty_primary_label.styleSheet().lower()
        win.toggle_night_vision_theme(False, persist=False)
        app.processEvents()
        record("theme_night_vision", "PASS" if nv_ok and not win._is_night_vision else "FAIL", f"nv_ok={nv_ok}")

        # 21. Console/Log
        win.toggle_console_panel(True)
        app.processEvents()
        log_vis = not win.console_panel.isHidden() and len(win.log_manager.entries) > 0
        win.toggle_console_panel(False)
        record("console_log", "PASS" if log_vis else "FAIL", f"entries={len(win.log_manager.entries)}")

        # 5-8. PNG, JPEG, TIFF, FITS
        rng = np.random.default_rng(7)
        base_f32 = np.clip(rng.normal(0.25, 0.02, (64, 80)), 0.0, 1.0).astype(np.float32)
        base_f32[25:35, 30:45] = 0.85
        u8_rgb = np.stack([(base_f32 * 255).astype(np.uint8)] * 3, axis=-1)

        png_path = work_dir / "test.png"
        jpg_path = work_dir / "test.jpg"
        tif_path = work_dir / "test.tif"
        fits_path = work_dir / "test.fits"
        Image.fromarray(u8_rgb).save(png_path)
        Image.fromarray(u8_rgb).save(jpg_path, quality=95)
        tifffile.imwrite(tif_path, (base_f32 * 65535.0).astype(np.uint16))
        fits.writeto(fits_path, base_f32, overwrite=True)

        for key, p in [("open_png_jpeg", png_path), ("open_jpeg", jpg_path), ("open_tiff", tif_path), ("open_fits", fits_path)]:
            ok = win.load_path(p)
            app.processEvents()
            record(key, "PASS" if ok and win.viewer.has_image() else "FAIL", f"file={p.name}, has_image={win.viewer.has_image()}")

        # 9. RAW (cek modul rawpy/DLL aktif; jika belum ada kamera RAW asli maka PARTIAL/verifikasi DLL)
        try:
            _ = rawpy.libraw_version
            bad_raw = work_dir / "dummy.dng"
            bad_raw.write_bytes(b"NOT_A_RAW")
            threw_expected = False
            try:
                with rawpy.imread(str(bad_raw)):
                    pass
            except Exception:
                threw_expected = True
            record("raw_support", "PARTIAL" if threw_expected else "FAIL", f"LibRaw={rawpy.libraw_version}; tidak ada berkas RAW kamera asli di paket uji")
        except Exception as exc:
            record("raw_support", "FAIL", repr(exc))

        # 10-11. AVI & MP4 via PyAV terbundel
        avi_path = work_dir / "test.avi"
        mp4_path = work_dir / "test.mp4"
        _write_synthetic_video(avi_path, "mpeg4")
        _write_synthetic_video(mp4_path, "mpeg4")
        ok_avi = win.load_video_path(avi_path)
        app.processEvents()
        record("open_avi", "PASS" if ok_avi and win.sequence_manager.frame_count >= 1 else "FAIL", f"frames={win.sequence_manager.frame_count}")

        ok_mp4 = win.load_video_path(mp4_path)
        app.processEvents()
        record("open_mp4_mov", "PASS" if ok_mp4 and win.sequence_manager.frame_count >= 1 else "FAIL", f"frames={win.sequence_manager.frame_count}")

        # 12. SER
        ser_path = work_dir / "test.ser"
        _write_synthetic_ser(ser_path)
        ok_ser = win.load_ser_path(ser_path)
        app.processEvents()
        record("open_ser", "PASS" if ok_ser and win.sequence_manager.frame_count == 3 else "FAIL", f"frames={win.sequence_manager.frame_count}")

        # 13-15. Multiple Images, Folder Sequence, Frame List
        seq_dir = work_dir / "seq"
        seq_dir.mkdir(exist_ok=True)
        seq_files = []
        for i in range(3):
            fp = seq_dir / f"frame_{i:02d}.tif"
            tifffile.imwrite(fp, (base_f32 * (0.9 + 0.05 * i)).astype(np.float32))
            seq_files.append(fp)

        ok_multi = win.load_sequence_paths(seq_files)
        app.processEvents()
        fl_count = win.panel_b.list_widget.count() if hasattr(win, "panel_b") else win.sequence_manager.frame_count
        record("multiple_images", "PASS" if ok_multi and win.sequence_manager.frame_count == 3 else "FAIL", f"count={win.sequence_manager.frame_count}")
        record("frame_list", "PASS" if fl_count == 3 else "FAIL", f"rows={fl_count}")

        ok_folder = win.load_folder_sequence(seq_dir)
        app.processEvents()
        record("folder_sequence", "PASS" if ok_folder and win.sequence_manager.frame_count == 3 else "FAIL", f"count={win.sequence_manager.frame_count}")

        # 16-19. Flat Calibration, Stacking Basic/Medium/High, Background Extraction, Enhancement
        flat_path = work_dir / "master_flat.fits"
        flat_arr = np.full((64, 80), 0.5, dtype=np.float32)
        fits.writeto(flat_path, flat_arr, overwrite=True)
        flat_loaded = win.set_master_flat_path(flat_path)
        record("flat_calibration", "PASS" if flat_loaded and win._loaded_master_flat is not None else "FAIL", f"loaded={flat_loaded}")

        bg_res = run_background_extraction(base_f32, ProcessingProfile.BASIC)
        enh_res = run_image_enhancement(bg_res.linear_corrected_data, ProcessingProfile.MEDIUM)
        record("background_extraction", "PASS" if bg_res.linear_corrected_data.shape == base_f32.shape else "FAIL", f"shape={bg_res.linear_corrected_data.shape}")
        record("image_enhancement", "PASS" if enh_res.enhanced_data.shape == base_f32.shape else "FAIL", f"shape={enh_res.enhanced_data.shape}")

        stack_statuses = []
        last_pipe_res = None
        for prof in (ProcessingProfile.BASIC, ProcessingProfile.MEDIUM, ProcessingProfile.HIGH):
            orchestrator = ProcessingPipelineOrchestrator(
                prof,
                master_flat=win._loaded_master_flat,
            )
            pres = orchestrator.run_on_sequence(win.sequence_manager)
            last_pipe_res = pres
            stack_statuses.append(f"{prof.name}:{pres.linear_result.shape}")
        record("stacking_profiles", "PASS" if len(stack_statuses) == 3 else "FAIL", ", ".join(stack_statuses))

        # 20. Histogram
        win._last_pipeline_result = last_pipe_res
        win.viewer.set_image(last_pipe_res.previews[PreviewMode.FINAL_DISPLAY], last_pipe_res.linear_result)
        win.open_histogram_window()
        app.processEvents()
        hist_ok = win.histogram_window is not None and win.histogram_window.isVisible()
        if win.histogram_window is not None:
            win.histogram_window.close()
        record("histogram", "PASS" if hist_ok else "FAIL", f"visible={hist_ok}")

        # 22-24. Save (Linear FITS/TIFF & Display PNG), Snapshot, Open output kembali
        out_fits = work_dir / "out_linear.fits"
        out_tif = work_dir / "out_linear.tif"
        out_png = work_dir / "out_display.png"
        saved_fits = win.save_pipeline_result_to_path(out_fits, save_target="LINEAR")
        saved_tif = win.save_pipeline_result_to_path(out_tif, save_target="LINEAR")
        saved_png = win.save_pipeline_result_to_path(out_png, save_target="DISPLAY")
        win._last_dir = str(work_dir)
        snap_path = win.take_quick_snapshot()
        save_ok = (
            saved_fits is not None and saved_fits.exists()
            and saved_tif is not None and saved_tif.exists()
            and saved_png is not None and saved_png.exists()
        )
        snap_ok = snap_path is not None and snap_path.exists()
        reopen_ok = win.load_path(saved_fits) if saved_fits else False
        app.processEvents()

        # Uji preferensi konfigurasi pengguna tersimpan & terbaca kembali
        cfg_file = work_dir / "test_config.ini"
        win.toggle_night_vision_theme(True, persist=False)
        win._save_user_preferences(cfg_file)
        win.toggle_night_vision_theme(False, persist=False)
        win._load_user_preferences(cfg_file)
        pref_ok = cfg_file.exists() and win._is_night_vision is True
        win.toggle_night_vision_theme(False, persist=False)
        record("user_preferences", "PASS" if pref_ok else "FAIL", f"cfg={cfg_file.name}, restored={pref_ok}")

        record("save_outputs", "PASS" if save_ok else "FAIL", f"fits={saved_fits}, tif={saved_tif}, png={saved_png}")
        record("snapshot", "PASS" if snap_ok else "FAIL", f"snap={snap_path}")
        record("reopen_output", "PASS" if reopen_ok and win.viewer.has_image() else "FAIL", f"reopened={reopen_ok}")

        # 25. Tutup bersih
        win.close_image()
        win.close()
        app.processEvents()
        record("clean_close", "PASS", "MainWindow ditutup bersih tanpa exception")
    except Exception as exc:
        record("fatal_error", "FAIL", repr(exc))
    finally:
        report_path = work_dir / "bundle_verify_report.json"
        report_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    has_fail = any(v["status"] == "FAIL" for v in results.values())
    return 1 if has_fail else 0
