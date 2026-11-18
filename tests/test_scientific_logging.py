"""Pengujian Komprehensif (Unit, Integration, GUI, Multithreading, & Performance)
untuk HILALONE Scientific Processing Log & Console System (v1.0.0).

Mencakup seluruh daftar pengujian pada Bagian XXXIII Master Prompt:
  - 15 Unit Tests (inisialisasi, format, timestamp, level, modul, Run ID, JSONL,
    file writing, rotasi log, filter, search, export, clear view, palet warna, exception).
  - 16 Integration Tests (Single Image, Multiple Images, Folder, Video, SER,
    Master Flat, Flat Calibration, Stacking, Background, Enhancement, Histogram,
    Curve, Output Generation, Error, Cancel, Skipped, Processing Summary).
  - 12 GUI Tests (buka/tutup Console, filter, search, copy, export, clear view-only,
    auto-scroll, pause scroll, Standard Dark, Night Vision Red, worker thread safety).
  - Performance & Scientific Integrity Tests (sequence 120 frame, rate-limiting progress,
    jaminan hasil numerik float32 tidak berubah).
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import threading
import time

from astropy.io import fits
import numpy as np
import pytest
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import QApplication, QMessageBox
import tifffile

from hilalone import __version__
from hilalone.core.logging import (
    ConsoleFilterCategory,
    HilaloneLogger,
    LogEvent,
    LogEventType,
    LogFilterCriteria,
    LogLevel,
    LogManager,
    LogModule,
    LogVerbosity,
    NIGHT_VISION_RED_LOG_PALETTE,
    PersistentLogFileHandler,
    ProcessingRunSummary,
    ProgressRateLimiter,
    STANDARD_DARK_LOG_PALETTE,
    format_console_line,
    format_duration,
    format_jsonl_line,
    format_persistent_line,
    format_timestamps,
    generate_run_id,
    generate_session_id,
    get_log_color,
    normalize_module_name,
)
from hilalone.gui.console_panel import ConsoleLogPanel
from hilalone.gui.main_window import MainWindow


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _write_synthetic_fits(
    path: Path,
    data: np.ndarray,
    *,
    object_name: str = "Hilal Crescent",
    telescop: str = "Takahashi FSQ-106",
    instrume: str = "ZWO ASI2600MM",
    exptime: float = 0.05,
    date_obs: str | None = "2026-11-17T11:15:00",
    filter_name: str = "IR-Pass 685nm",
) -> Path:
    hdu = fits.PrimaryHDU(data=data)
    hdu.header["OBJECT"] = object_name
    hdu.header["TELESCOP"] = telescop
    hdu.header["INSTRUME"] = instrume
    hdu.header["EXPTIME"] = exptime
    if date_obs is not None:
        hdu.header["DATE-OBS"] = date_obs
    hdu.header["FILTER"] = filter_name
    hdu.writeto(path, overwrite=True)
    return path


def _write_synthetic_ser(path: Path, frames: list[np.ndarray]) -> Path:
    """Membuat berkas biner .SER astronomi 8-bit monokrom sintetis yang valid."""
    n_frames = len(frames)
    h, w = frames[0].shape[:2]
    header = bytearray(178)
    header[0:14] = b"LUCAM-RECORDER"
    header[14:18] = (0).to_bytes(4, "little")      # LuID
    header[18:22] = (0).to_bytes(4, "little")      # ColorID = 0 (MONO)
    header[22:26] = (0).to_bytes(4, "little")      # LittleEndian
    header[26:30] = int(w).to_bytes(4, "little")   # ImageWidth
    header[30:34] = int(h).to_bytes(4, "little")   # ImageHeight
    header[34:38] = (8).to_bytes(4, "little")      # PixelDepthPerPlane = 8
    header[38:42] = int(n_frames).to_bytes(4, "little")
    header[42:82] = b"Observer Hilal".ljust(40, b"\x00")
    header[82:122] = b"ASI290MM".ljust(40, b"\x00")
    header[122:162] = b"Celestron C8".ljust(40, b"\x00")

    with open(path, "wb") as f:
        f.write(header)
        for frame in frames:
            u8 = np.clip(frame, 0, 255).astype(np.uint8)
            f.write(u8.tobytes())
    return path


# ==============================================================================
# I. UNIT TESTS (15 Kriteria Bagian XXXIII)
# ==============================================================================
class TestLoggingUnit:
    def test_1_logger_initialization_and_startup(self, qapp: QApplication, tmp_path: Path) -> None:
        logger = HilaloneLogger(log_dir=tmp_path / "Logs")
        logger.log_application_startup()

        assert logger.session_id.startswith("SES-")
        assert len(logger.entries) >= 7
        lines = [format_console_line(e) for e in logger.entries]
        joined = "\n".join(lines)
        assert "=== HILALONE APPLICATION STARTUP ===" in joined
        assert f"HILALONE v{__version__} initialized." in joined
        assert "Operating system:" in joined
        assert "Architecture:" in joined
        assert "Python runtime:" in joined
        assert "Qt framework initialized" in joined
        assert "Logging initialized." in joined
        assert "Application startup completed." in joined

    def test_2_and_3_log_and_timestamp_formatting(self, qapp: QApplication, tmp_path: Path) -> None:
        ui_ts, iso_ts = format_timestamps()
        # UI timestamp: HH:MM:SS.mmm
        assert re.match(r"^\d{2}:\d{2}:\d{2}\.\d{3}$", ui_ts)
        # ISO 8601 timestamp dengan timezone offset
        assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$", iso_ts)

        logger = HilaloneLogger(log_dir=tmp_path / "Logs")
        ev = logger.info(
            LogModule.INPUT,
            "Loading Light sequence...",
            details={"format": "FITS", "frames": 10},
        )
        console_line = format_console_line(ev)
        assert console_line == f"[{ev.timestamp}] [INFO] [INPUT] Loading Light sequence... | format=FITS, frames=10"

        persist_line = format_persistent_line(ev)
        assert persist_line.startswith(f"[{ev.iso_timestamp}] [INFO] [INPUT] Loading Light sequence...")

        sec_ev = logger.section("FLAT FIELD CALIBRATION", module=LogModule.CALIBRATION)
        assert format_console_line(sec_ev) == "=== FLAT FIELD CALIBRATION ==="

    def test_4_and_5_levels_and_module_naming(self, qapp: QApplication, tmp_path: Path) -> None:
        logger = HilaloneLogger(log_dir=tmp_path / "Logs")
        e_dbg = logger.debug("STACKING", "Allocated output buffer: 1280 × 960 float32.")
        e_inf = logger.info("INPUT", "Loading Light sequence...")
        e_suc = logger.success("CALIBRATION", "Flat Calibration completed successfully.")
        e_wrn = logger.warning("SEQUENCE", "3 frames excluded due to incompatible dimensions.")
        e_err = logger.error("FLAT", "Master Flat contains no valid pixels.")
        e_crt = logger.critical("SYSTEM", "Out of disk space.")
        e_prg = logger.progress("STACKING", 50, 100, "150/300 frames processed (50%).", force=True)
        e_sec = logger.section("FLAT FIELD CALIBRATION")
        e_can = logger.cancelled("SESSION", "Processing cancelled by user.")
        e_skp = logger.skipped("CALIBRATION", "Flat Calibration skipped.", reason="Disabled by user")

        assert e_dbg.level == LogLevel.DEBUG
        assert e_inf.level == LogLevel.INFO
        assert e_suc.level == LogLevel.SUCCESS and e_suc.event_type == LogEventType.SUCCESS
        assert e_wrn.level == LogLevel.WARNING
        assert e_err.level == LogLevel.ERROR
        assert e_crt.level == LogLevel.CRITICAL
        assert e_prg is not None and e_prg.level == LogLevel.PROGRESS
        assert e_sec.level == LogLevel.SECTION
        assert e_can.level == LogLevel.CANCELLED
        assert e_skp.level == LogLevel.SKIPPED

        # Pastikan CANCELLED dan SKIPPED tidak disamakan dengan ERROR
        assert e_can.level != LogLevel.ERROR
        assert e_skp.level != LogLevel.ERROR

        # Verifikasi normalisasi nama modul standar
        assert normalize_module_name("CURVES") == "CURVE"
        assert normalize_module_name("FRAME_SELECTION") == "SEQUENCE"
        assert normalize_module_name("PREVIEW") == "DISPLAY"
        assert normalize_module_name("VIEW") == "VIEWER"

    def test_6_run_id_and_session_management(self, qapp: QApplication, tmp_path: Path) -> None:
        logger = HilaloneLogger(log_dir=tmp_path / "Logs")
        ses_id = logger.session_id
        assert ses_id.startswith("SES-")

        # Sebelum processing run dimulai, event menggunakan session_id
        e0 = logger.info("INPUT", "Image opened.")
        assert e0.run_id == ses_id

        # Mulai Run 1
        rec1 = logger.start_processing_run(input_summary={"frames": 5})
        assert rec1.run_id.startswith("RUN-")
        e1 = logger.info("STACKING", "Stacking run 1...")
        assert e1.run_id == rec1.run_id
        logger.finish_processing_run("SUCCESS", output_files=["out1.fits"])
        assert rec1.final_status == "SUCCESS"
        assert rec1.duration_ms >= 0.0

        # Mulai Run 2: Run 1 tetap tersimpan di histori
        rec2 = logger.start_processing_run(input_summary={"frames": 10})
        assert rec2.run_id != rec1.run_id
        e2 = logger.info("STACKING", "Stacking run 2...")
        assert e2.run_id == rec2.run_id
        logger.finish_processing_run("CANCELLED")

        all_runs = logger.session_manager.all_run_records()
        assert len(all_runs) == 2
        assert all_runs[0].run_id == rec1.run_id
        assert all_runs[1].run_id == rec2.run_id

    def test_7_and_8_jsonl_serialization_and_persistent_files(self, qapp: QApplication, tmp_path: Path) -> None:
        log_root = tmp_path / "HILALONE" / "Logs"
        logger = HilaloneLogger(log_dir=log_root)
        logger.info(
            LogModule.INPUT,
            "Loading Light sequence",
            details={
                "filename": "hilal_01.fits",
                "api_token": "secret-should-be-redacted",
            },
        )
        logger.debug(LogModule.STACKING, "Allocated float32 buffer")

        fh = logger.file_handler
        assert fh is not None
        assert fh.application_log_path.exists()
        assert fh.session_log_path.exists()
        assert fh.session_jsonl_path.exists()
        assert fh.diagnostic_log_path.exists()

        # Periksa validitas setiap baris JSONL dan redaksi data sensitif
        jsonl_lines = [
            line for line in fh.session_jsonl_path.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        assert len(jsonl_lines) == 2
        parsed0 = json.loads(jsonl_lines[0])
        assert parsed0["level"] == "INFO"
        assert parsed0["module"] == "INPUT"
        assert parsed0["message"] == "Loading Light sequence"
        assert parsed0["details"]["filename"] == "hilal_01.fits"
        assert parsed0["details"]["api_token"] == "[REDACTED]"

        # DEBUG tertulis di diagnostic_latest.log tetapi tidak memenuhi session_log_path normal
        session_txt = fh.session_log_path.read_text(encoding="utf-8")
        diag_txt = fh.diagnostic_log_path.read_text(encoding="utf-8")
        assert "Loading Light sequence" in session_txt
        assert "Allocated float32 buffer" not in session_txt
        assert "Allocated float32 buffer" in diag_txt

    def test_9_log_rotation_without_silent_deletion(self, tmp_path: Path) -> None:
        log_root = tmp_path / "LogsRotate"
        handler = PersistentLogFileHandler(base_dir=log_root, max_bytes=1024)
        logger = HilaloneLogger(log_dir=log_root, enable_file_logging=False)
        logger._file_handler = handler

        for i in range(40):
            logger.info(LogModule.SYSTEM, f"Rotation test message number {i} with padding text " + ("X" * 40))

        archives = list(handler.application_dir.glob("application_archive_*.log"))
        assert len(archives) >= 1
        assert handler.application_log_path.exists()

    def test_10_and_11_filtering_verbosity_and_search(self, qapp: QApplication, tmp_path: Path) -> None:
        logger = HilaloneLogger(log_dir=tmp_path / "Logs")
        logger.info("INPUT", "Loaded moon_crescent.fits", details={"filename": "moon_crescent.fits"})
        logger.verbose("INPUT", "BITPIX=16, BZERO=32768")
        logger.debug("STACKING", "Strip buffer 64MB allocated")
        logger.success("STACKING", "Integration finished")
        logger.warning("SEQUENCE", "1 frame excluded")
        logger.error("FLAT", "Master flat invalid", error_code="ERR_FLAT_01")

        # Mode NORMAL (default): DEBUG dan VERBOSE disembunyikan
        norm_list = logger.filter_entries(
            LogFilterCriteria(category=ConsoleFilterCategory.ALL, verbosity=LogVerbosity.NORMAL)
        )
        assert len(norm_list) == 4
        assert all(e.level != LogLevel.DEBUG for e in norm_list)

        # Mode VERBOSE: VERBOSE tampil, DEBUG tetap tersembunyi
        verb_list = logger.filter_entries(
            LogFilterCriteria(category=ConsoleFilterCategory.ALL, verbosity=LogVerbosity.VERBOSE)
        )
        assert len(verb_list) == 5

        # Mode DEBUG: semua 6 pesan tampil
        dbg_list = logger.filter_entries(
            LogFilterCriteria(category=ConsoleFilterCategory.ALL, verbosity=LogVerbosity.DEBUG)
        )
        assert len(dbg_list) == 6

        # Filter ERROR saja
        err_list = logger.filter_entries(
            LogFilterCriteria(category=ConsoleFilterCategory.ERROR, verbosity=LogVerbosity.NORMAL)
        )
        assert len(err_list) == 1
        assert err_list[0].module == "FLAT"

        # Search berdasarkan error_code dan filename
        by_code = logger.filter_entries(LogFilterCriteria(search_query="ERR_FLAT_01"))
        assert len(by_code) == 1
        by_file = logger.filter_entries(LogFilterCriteria(search_query="moon_crescent.fits"))
        assert len(by_file) == 1

    def test_12_and_13_export_and_clear_console_behavior(self, qapp: QApplication, tmp_path: Path) -> None:
        logger = HilaloneLogger(log_dir=tmp_path / "Logs")
        logger.info("INPUT", "First message before clear")
        logger.warning("SEQUENCE", "Warning message before clear")

        # Clear Console hanya membersihkan tampilan GUI
        logger.clear_console_view()
        assert len(logger.visible_entries_after_clear) == 0
        assert len(logger.session_entries) == 2

        logger.success("STACKING", "Message after clear")
        assert len(logger.visible_entries_after_clear) == 1
        assert len(logger.session_entries) == 3

        # Export Visible Log hanya mengekspor 1 baris yang tampil setelah Clear
        vis_path = tmp_path / "visible.log"
        logger.export_visible_log(vis_path, LogFilterCriteria())
        vis_text = vis_path.read_text(encoding="utf-8")
        assert "Message after clear" in vis_text
        assert "First message before clear" not in vis_text

        # Export Complete Log mengekspor seluruh 3 baris sesi tanpa hilang
        comp_log = tmp_path / "complete.log"
        comp_jsonl = tmp_path / "complete.jsonl"
        logger.export_complete_log(comp_log)
        logger.export_complete_log(comp_jsonl)

        comp_text = comp_log.read_text(encoding="utf-8")
        assert "First message before clear" in comp_text
        assert "Warning message before clear" in comp_text
        assert "Message after clear" in comp_text

        jsonl_rows = [json.loads(line) for line in comp_jsonl.read_text(encoding="utf-8").splitlines() if line]
        assert len(jsonl_rows) == 3

    def test_14_theme_color_palettes(self) -> None:
        # Standard Dark Palette (Bagian VII)
        assert get_log_color(LogLevel.INFO, night_vision=False) == "#C7D5E8"
        assert get_log_color(LogLevel.SUCCESS, night_vision=False) == "#65DDA5"
        assert get_log_color(LogLevel.WARNING, night_vision=False) == "#F0B65C"
        assert get_log_color(LogLevel.ERROR, night_vision=False) == "#FF7777"
        assert get_log_color(LogLevel.CRITICAL, night_vision=False) == "#FF4242"
        assert get_log_color(LogLevel.PROGRESS, night_vision=False) == "#57CFFF"
        assert get_log_color(LogLevel.DEBUG, night_vision=False) == "#8292AA"
        assert get_log_color(LogLevel.SECTION, night_vision=False) == "#EAF3FF"

        # Night Vision Red Palette (Bagian VIII)
        assert get_log_color(LogLevel.INFO, night_vision=True) == "#D9AAAA"
        assert get_log_color(LogLevel.SUCCESS, night_vision=True) == "#FFA8A8"
        assert get_log_color(LogLevel.WARNING, night_vision=True) == "#F3A18D"
        assert get_log_color(LogLevel.ERROR, night_vision=True) == "#FF6666"
        assert get_log_color(LogLevel.CRITICAL, night_vision=True) == "#FF3333"
        assert get_log_color(LogLevel.PROGRESS, night_vision=True) == "#F28F8F"
        assert get_log_color(LogLevel.DEBUG, night_vision=True) == "#A87878"
        assert get_log_color(LogLevel.SECTION, night_vision=True) == "#FFD0D0"

    def test_15_exception_logging_and_diagnostic_traceback(self, qapp: QApplication, tmp_path: Path) -> None:
        log_root = tmp_path / "DiagLogs"
        logger = HilaloneLogger(log_dir=log_root)
        try:
            raise ValueError("Invalid Master Flat dimensions (640x480 vs 1280x960)")
        except ValueError as exc:
            ev = logger.error(
                LogModule.FLAT,
                "Master Flat validation failed.",
                str(exc),
                exc=exc,
                operation="validate_flat",
                error_code="FLAT_DIM_MISMATCH",
                suggested_action="Gunakan Master Flat dengan resolusi yang sama dengan Light frame.",
            )

        console_line = format_console_line(ev)
        # Console normal tidak menampilkan traceback multiline panjang
        assert "Traceback (most recent call last)" not in console_line
        assert "exception_type=ValueError" in console_line
        assert "error_code=FLAT_DIM_MISMATCH" in console_line

        # Namun diagnostic_latest.log menyimpan traceback lengkap
        assert logger.file_handler is not None
        diag_content = logger.file_handler.diagnostic_log_path.read_text(encoding="utf-8")
        assert "Traceback (most recent call last)" in diag_content
        assert "ValueError: Invalid Master Flat dimensions" in diag_content


# ==============================================================================
# II. INTEGRATION & GUI TESTS (Bagian XXXIII)
# ==============================================================================
class TestLoggingIntegrationAndGUI:
    def test_gui_console_panel_controls_and_themes(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        logger = HilaloneLogger(log_dir=tmp_path / "GuiLogs")
        panel = ConsoleLogPanel(logger)
        panel.show()

        logger.info("INPUT", "Opening FITS image...", details={"filename": "hilal.fits"})
        logger.debug("STACKING", "Internal strip buffer initialized")
        logger.success("STACKING", "Stacking completed")
        logger.warning("SEQUENCE", "1 frame excluded")
        logger.error("OUTPUT", "Disk write failed")
        qapp.processEvents()

        # Default (NORMAL verbosity): DEBUG tidak ditampilkan (4 baris tampil)
        text_normal = panel.text_edit.toPlainText()
        assert "Opening FITS image..." in text_normal
        assert "Internal strip buffer initialized" not in text_normal

        # Ubah verbosity ke DEBUG -> pesan DEBUG langsung muncul tanpa restart
        panel.set_verbosity(LogVerbosity.DEBUG)
        qapp.processEvents()
        assert "Internal strip buffer initialized" in panel.text_edit.toPlainText()

        # Uji Filter kategori Warning
        panel.set_filter_category(ConsoleFilterCategory.WARNING)
        qapp.processEvents()
        filtered_txt = panel.text_edit.toPlainText()
        assert "1 frame excluded" in filtered_txt
        assert "Opening FITS image..." not in filtered_txt

        # Kembalikan filter ke ALL dan uji Search
        panel.set_filter_category(ConsoleFilterCategory.ALL)
        panel.set_search_query("hilal.fits")
        qapp.processEvents()
        assert "Opening FITS image..." in panel.text_edit.toPlainText()
        assert "Disk write failed" not in panel.text_edit.toPlainText()
        assert "1 /" in panel.search_count_label.text()

        panel.set_search_query("")
        qapp.processEvents()

        # Uji Copy All & Copy Selected
        copied_all = panel.copy_all_to_clipboard()
        assert "Opening FITS image..." in copied_all
        assert QApplication.clipboard().text() == copied_all

        cursor = panel.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        cursor.movePosition(QTextCursor.MoveOperation.EndOfLine, QTextCursor.MoveMode.KeepAnchor)
        panel.text_edit.setTextCursor(cursor)
        copied_sel = panel.copy_selected_to_clipboard()
        assert "Opening FITS image..." in copied_sel

        # Uji Auto-scroll & Pause Scroll
        panel.pause_scroll_btn.setChecked(True)
        assert panel._auto_scroll is False
        panel.auto_scroll_btn.setChecked(True)
        assert panel._auto_scroll is True

        # Uji pergantian tema Standard Dark <-> Night Vision Red
        panel.set_night_vision(True)
        fmt_nv = panel._build_char_format(logger.entries[0])
        assert fmt_nv.foreground().color().name().upper() == "#D9AAAA"

        panel.set_night_vision(False)
        fmt_std = panel._build_char_format(logger.entries[0])
        assert fmt_std.foreground().color().name().upper() == "#C7D5E8"

        # Uji Clear Console: hanya membersihkan tampilan, tidak menghapus file log atau session_entries
        panel.clear_btn.click()
        qapp.processEvents()
        assert panel.text_edit.toPlainText().strip() == ""
        assert panel.status_notice_label.isVisible()
        assert "Session log remains available" in panel.status_notice_label.text()
        assert len(logger.session_entries) == 6
        assert logger.file_handler is not None
        assert logger.file_handler.session_log_path.stat().st_size > 0

        panel.close()

    def test_full_workflow_logging_fits_ser_flat_pipeline_curve_and_output(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: QMessageBox.StandardButton.Ok)

        win = MainWindow()
        try:
            # 1. Pastikan startup log tercatat
            startup_mods = [e.module for e in win.log_manager.entries]
            assert "SYSTEM" in startup_mods
            win.log_manager.set_verbosity(LogVerbosity.VERBOSE, log_change=False)

            # 2. Uji pembukaan Single Image FITS dengan metadata lengkap
            y, x = np.mgrid[0:64, 0:64].astype(np.float32)
            sky_grad = 100.0 + 1.5 * y + 0.5 * x
            crescent = 45.0 * np.exp(-((x - 32.0) ** 2 + (y - 32.0) ** 2) / 18.0).astype(np.float32)
            img1 = sky_grad + crescent
            fits_p1 = _write_synthetic_fits(tmp_path / "hilal_frame_01.fits", img1)

            assert win.load_path(fits_p1) is True
            all_text = "\n".join(format_console_line(e) for e in win.log_manager.session_entries)
            assert "hilal_frame_01.fits" in all_text
            assert "Takahashi FSQ-106" in all_text
            assert "ZWO ASI2600MM" in all_text

            # 3. Uji pembukaan Folder Sequence & Sequence Validation
            seq_dir = tmp_path / "seq_folder"
            seq_dir.mkdir()
            for idx in range(1, 5):
                frame_arr = img1 + np.random.default_rng(idx).normal(0.0, 1.2, img1.shape).astype(np.float32)
                _write_synthetic_fits(seq_dir / f"light_{idx:02d}.fits", frame_arr)

            assert win.load_folder_sequence(seq_dir) is True
            all_text = "\n".join(format_console_line(e) for e in win.log_manager.session_entries)
            assert "=== SEQUENCE VALIDATION ===" in all_text
            assert "Total frames detected: 4" in all_text
            assert "Compatible frames: 4." in all_text

            # 4. Uji Master Flat & Flat Calibration
            flat_arr = np.full((64, 64), 1000.0, dtype=np.float32)
            flat_arr[10:54, 10:54] = 1150.0
            flat_path = _write_synthetic_fits(tmp_path / "master_flat.fits", flat_arr)
            assert win.set_master_flat_path(flat_path) is True
            all_text = "\n".join(format_console_line(e) for e in win.log_manager.session_entries)
            assert "Master Flat generated and validated successfully." in all_text
            assert "Normalization method: F_norm(x,y) = F(x,y) / median(F_valid)" in all_text

            # 5. Jalankan Automated Processing Pipeline dengan Flat Calibration aktif
            win.flat_checkbox.setChecked(True)
            assert win.start_automated_pipeline(wait_for_completion=True) is True
            all_text = "\n".join(format_console_line(e) for e in win.log_manager.session_entries)
            assert "=== AUTOMATED PROCESSING PIPELINE ===" in all_text
            assert "=== FLAT FIELD CALIBRATION ===" in all_text
            assert "=== IMAGE STACKING ===" in all_text
            assert "=== BACKGROUND EXTRACTION ===" in all_text
            assert "=== IMAGE ENHANCEMENT ===" in all_text
            assert "=== HISTOGRAM TRANSFORMATION ===" in all_text
            assert "Display transformation applies only to DISPLAY branch; scientific linear data remains unchanged." in all_text
            assert "PROCESSING SUMMARY" in all_text
            assert "AUTOMATED PROCESSING COMPLETED" in all_text

            # 6. Uji Curve Transformation logging
            win.open_curves_window()
            assert win.curves_window is not None
            win.curves_window._preset_scurve()
            win.curves_window._on_apply_clicked()
            all_text = "\n".join(format_console_line(e) for e in win.log_manager.session_entries)
            assert "Curve adjustment applied" in all_text
            assert "Curve transformation completed." in all_text

            # 7. Uji Output Generation logging (FITS, TIFF, PNG)
            out_fits = tmp_path / "out_master_linear.fits"
            out_tiff = tmp_path / "out_master_linear.tif"
            out_png = tmp_path / "out_display.png"
            assert win.save_pipeline_result_to_path(out_fits, save_target="LINEAR") == out_fits
            assert win.save_pipeline_result_to_path(out_tiff, save_target="LINEAR") == out_tiff
            assert win.save_pipeline_result_to_path(out_png, save_target="DISPLAY") == out_png

            all_text = "\n".join(format_console_line(e) for e in win.log_manager.session_entries)
            assert "=== OUTPUT GENERATION ===" in all_text
            assert "Writing Scientific Master FITS" in all_text
            assert "Writing Scientific TIFF Export" in all_text
            assert "Writing Display Preview PNG" in all_text
            assert "File saved and verified successfully." in all_text

            # 8. Uji SER Sequence loading & Optional Stage Skipped (Flat disabled)
            ser_frames = [np.full((32, 32), 120 + i, dtype=np.uint8) for i in range(4)]
            ser_path = _write_synthetic_ser(tmp_path / "moon_test.ser", ser_frames)
            assert win.load_ser_path(ser_path) is True
            win.flat_checkbox.setChecked(False)
            assert win.start_automated_pipeline(wait_for_completion=True) is True
            all_text = "\n".join(format_console_line(e) for e in win.log_manager.session_entries)
            assert "SER Sequence loaded successfully." in all_text
            assert "SER astronomy stream metadata: 4 frames" in all_text
            assert "[SKIPPED] [CALIBRATION] Flat Calibration skipped. | Reason: Disabled by user" in all_text

            # 8b. Uji Video Sequence loading (.avi)
            import av

            vid_path = tmp_path / "hilal_test.avi"
            cont = av.open(str(vid_path), mode="w")
            stream = cont.add_stream("mpeg4", rate=25)
            stream.width = 64
            stream.height = 48
            stream.pix_fmt = "yuv420p"
            for idx in range(4):
                rgb = np.full((48, 64, 3), 80 + idx * 10, dtype=np.uint8)
                vf = av.VideoFrame.from_ndarray(rgb, format="rgb24").reformat(64, 48, "yuv420p")
                vf.pts = idx
                for pkt in stream.encode(vf):
                    cont.mux(pkt)
            for pkt in stream.encode(None):
                cont.mux(pkt)
            cont.close()

            assert win.load_video_path(vid_path) is True
            all_text = "\n".join(format_console_line(e) for e in win.log_manager.session_entries)
            assert "Video Sequence loaded successfully." in all_text
            assert "mpeg4" in all_text.lower()

            # 9. Uji Cancellation logging
            win._on_pipeline_cancelled("Dibatalkan oleh pengguna saat pengujian.")
            all_text = "\n".join(format_console_line(e) for e in win.log_manager.session_entries)
            assert "[CANCELLED] [SESSION] Processing cancelled by user." in all_text
        finally:
            if win.curves_window is not None:
                win.curves_window.close()
            win.close()


# ==============================================================================
# III. MULTITHREADING & PERFORMANCE TESTS (Bagian XXVIII, XXIX, XXX, XXXIII)
# ==============================================================================
class TestMultithreadingAndPerformance:
    def test_multithreaded_logging_safety(self, qapp: QApplication, tmp_path: Path) -> None:
        logger = HilaloneLogger(log_dir=tmp_path / "ThreadLogs")
        panel = ConsoleLogPanel(logger)
        run_rec = logger.start_processing_run()

        errors: list[Exception] = []

        def _worker_task(tid: int) -> None:
            try:
                for step in range(25):
                    logger.info(
                        LogModule.STACKING,
                        f"Worker {tid} step {step}",
                        details={"thread": tid, "step": step},
                        run_id=run_rec.run_id,
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=_worker_task, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        qapp.processEvents()
        assert len(errors) == 0
        assert len(logger.session_entries) == 100
        # Nomor sequence harus unik dan terurut 1..100
        seqs = sorted(e.sequence for e in logger.session_entries)
        assert seqs == list(range(1, 101))
        panel.close()

    def test_large_sequence_progress_rate_limiting_and_numerical_integrity(
        self,
        qapp: QApplication,
        tmp_path: Path,
    ) -> None:
        """Menguji sequence 120 frame: progress tidak membanjiri console dan hasil numerik identik."""
        from hilalone.input_manager.sequence_manager import SequenceManager
        from hilalone.processing.stacking.engine import run_stacking_on_sequence
        from hilalone.processing.stacking.models import StackingProfile

        rng = np.random.default_rng(42)
        seq_dir = tmp_path / "perf_seq"
        seq_dir.mkdir()
        n_frames = 120
        base = np.linspace(100.0, 500.0, 48 * 48, dtype=np.float32).reshape(48, 48)
        paths: list[Path] = []
        for i in range(n_frames):
            noisy = base + rng.normal(0.0, 2.0, base.shape).astype(np.float32)
            p = seq_dir / f"f_{i:03d}.tif"
            tifffile.imwrite(str(p), noisy)
            paths.append(p)

        sm = SequenceManager()
        sm.open_files(paths)

        # 1. Eksekusi tanpa logging callback
        t0 = time.perf_counter()
        res_no_log = run_stacking_on_sequence(sm, StackingProfile.BASIC)
        dt_no_log = time.perf_counter() - t0

        # 2. Eksekusi dengan logging progress & hasil
        logger = HilaloneLogger(log_dir=tmp_path / "PerfLogs")
        run_rec = logger.start_processing_run()

        def _prog_cb(cur: int, tot: int, msg: str) -> None:
            pct = int(round(100.0 * cur / max(1, tot)))
            logger.progress(
                LogModule.STACKING,
                cur,
                tot,
                f"{pct}% completed ({cur}/{tot} frames).",
                operation="perf_stack",
                run_id=run_rec.run_id,
            )

        t1 = time.perf_counter()
        res_with_log = run_stacking_on_sequence(
            sm,
            StackingProfile.BASIC,
            progress_callback=_prog_cb,
        )
        dt_with_log = time.perf_counter() - t1

        # Pastikan rate-limiter menahan jumlah pesan PROGRESS (<= 15 pesan untuk 120 frame)
        prog_events = [e for e in logger.session_entries if e.level == LogLevel.PROGRESS]
        assert 1 <= len(prog_events) <= 15

        # Pastikan hasil ilmiah float32 identik bit-demi-bit (logging tidak mengubah hasil numerik)
        np.testing.assert_array_equal(
            res_no_log.stacked_scientific_data,
            res_with_log.stacked_scientific_data,
        )
        # Overhead logging harus tetap ringan
        assert dt_with_log < max(2.5, dt_no_log * 3.0 + 0.5)
        sm.clear()


# ==============================================================================
# IV. CONSOLE LOG REFINEMENT & FUNCTIONAL FIXES TESTS (4 Perbaikan Utama)
# ==============================================================================
class TestConsoleLogRefinements:
    def test_refinement_1_auto_scroll_button_no_clipping_and_responsive_widths(
        self,
        qapp: QApplication,
        tmp_path: Path,
    ) -> None:
        """Menguji Perbaikan 1: Tombol 'Auto-scroll: ON' / 'Auto-scroll: OFF' tidak terpotong
        pada ukuran jendela normal, jendela kecil, Standard Dark, dan Night Vision Red."""
        from PySide6.QtGui import QFont, QFontMetrics

        win = MainWindow()
        try:
            win.show()
            win.console_panel.setVisible(True)
            qapp.processEvents()

            panel = win.console_panel
            btn = panel.auto_scroll_btn

            for width in (1440, 1024, 860):
                for night_mode in (False, True):
                    win.resize(width, 760)
                    win.toggle_night_vision_theme(night_mode)
                    qapp.processEvents()

                    for checked, expected_label in ((True, "Auto-scroll: ON"), (False, "Auto-scroll: OFF")):
                        btn.setChecked(checked)
                        qapp.processEvents()

                        assert btn.text() == expected_label
                        # Hitung lebar teks dengan bobot tebal (font-weight 600 saat checked)
                        bold_font = QFont(btn.font())
                        bold_font.setWeight(QFont.Weight.DemiBold)
                        fm = QFontMetrics(bold_font)
                        text_px = fm.horizontalAdvance(expected_label)

                        # Pastikan lebar aktual dan minimumWidth tombol memiliki margin aman (>= text_px + 20px)
                        assert btn.minimumWidth() >= text_px + 20
                        assert btn.width() >= text_px + 20

            # Kembalikan ke ON
            btn.setChecked(True)
            qapp.processEvents()
            assert panel._auto_scroll is True
        finally:
            win.close()

    def test_refinement_2_standardized_duration_format_across_all_modules(
        self,
        qapp: QApplication,
        tmp_path: Path,
    ) -> None:
        """Menguji Perbaikan 2: Seluruh durasi manusia menggunakan format 'Duration: 0.00 s',
        sedangkan JSONL tetap menyimpan nilai numerik presisi penuh 'duration_ms'."""
        assert format_duration(264.1) == "Duration: 0.26 s"
        assert format_duration(1207) == "Duration: 1.21 s"
        assert format_duration(5000) == "Duration: 5.00 s"
        assert format_duration(25) == "Duration: 0.03 s"
        assert format_duration(0) == "Duration: 0.00 s"
        assert format_duration(duration_s=1.207) == "Duration: 1.21 s"

        logger = HilaloneLogger(log_dir=tmp_path / "DurLogs")
        ev = logger.success(
            LogModule.CURVE,
            "Curve transformation completed.",
            details={"channel": "RGB", "duration_ms": 264.1},
        )
        console_line = format_console_line(ev)
        persist_line = format_persistent_line(ev)

        assert "Duration: 0.26 s" in console_line
        assert "Duration: 0.26 s" in persist_line
        assert "duration_ms=" not in console_line
        assert "264.1 ms" not in console_line

        # Pastikan JSONL tetap menyimpan nilai numerik presisi penuh duration_ms
        jsonl_obj = json.loads(format_jsonl_line(ev))
        assert jsonl_obj["details"]["duration_ms"] == pytest.approx(264.1)

        # Pastikan ProcessingRunSummary juga menggunakan 'Duration: 0.00 s'
        summary = ProcessingRunSummary(
            run_id="RUN-TEST-01",
            status="SUCCESS",
            profile="BASIC",
            input_frames=4,
            frames_processed=4,
            frames_excluded=0,
            flat_calibration_status="COMPLETED",
            stacking_status="COMPLETED",
            background_status="COMPLETED",
            enhancement_status="COMPLETED",
            histogram_status="COMPLETED",
            curve_status="USED",
            output_files=("out.fits",),
            processing_time_sec=1.207,
        )
        summary_block = summary.format_summary_block()
        assert "Processing duration" in summary_block
        assert "1.21 s" in summary_block
        assert "ms" not in summary_block

    def test_refinement_3_detail_modes_normal_verbose_debug_distinct_outputs(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Menguji Perbaikan 3: Mode NORMAL, VERBOSE, dan DEBUG menghasilkan kedalaman log
        yang benar-benar berbeda dari setiap modul tanpa mengubah hasil ilmiah float32."""
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: QMessageBox.StandardButton.Ok)

        # Buat dataset sintetis yang identik untuk ketiga mode
        seq_dir = tmp_path / "detail_seq"
        seq_dir.mkdir()
        y, x = np.mgrid[0:48, 0:48].astype(np.float32)
        base_img = 120.0 + 1.2 * y + 0.4 * x + 35.0 * np.exp(-((x - 24.0) ** 2 + (y - 24.0) ** 2) / 14.0).astype(np.float32)
        for idx in range(1, 4):
            _write_synthetic_fits(seq_dir / f"frame_{idx:02d}.fits", base_img + idx * 0.5)

        flat_path = _write_synthetic_fits(tmp_path / "flat_detail.fits", np.full((48, 48), 1000.0, dtype=np.float32))

        mode_logs: dict[LogVerbosity, str] = {}
        mode_counts: dict[LogVerbosity, int] = {}
        mode_results: dict[LogVerbosity, np.ndarray] = {}

        for mode in (LogVerbosity.NORMAL, LogVerbosity.VERBOSE, LogVerbosity.DEBUG):
            win = MainWindow()
            try:
                start_idx = len(win.log_manager.session_entries)
                win.log_manager.set_verbosity(mode, log_change=True)

                assert win.load_folder_sequence(seq_dir) is True
                assert win.set_master_flat_path(flat_path) is True
                win.flat_checkbox.setChecked(True)
                assert win.start_automated_pipeline(wait_for_completion=True) is True

                out_file = tmp_path / f"out_{mode.value.lower()}.fits"
                assert win.save_pipeline_result_to_path(out_file, save_target="LINEAR") == out_file

                run_entries = win.log_manager.session_entries[start_idx:]
                mode_counts[mode] = len(run_entries)
                mode_logs[mode] = "\n".join(format_console_line(e) for e in run_entries)
                assert win._last_pipeline_result is not None
                mode_results[mode] = win._last_pipeline_result.linear_result.copy()
            finally:
                win.close()

        # 1. Jumlah baris harus meningkat secara nyata: NORMAL < VERBOSE < DEBUG
        assert mode_counts[LogVerbosity.NORMAL] < mode_counts[LogVerbosity.VERBOSE] < mode_counts[LogVerbosity.DEBUG]

        # 2. NORMAL: ringkas, tidak memuat FITS header detail panjang atau diagnostik array internal
        normal_txt = mode_logs[LogVerbosity.NORMAL]
        assert "FITS header metadata:" not in normal_txt
        assert "[DEBUG]" not in normal_txt
        assert "Duration:" in normal_txt
        assert "duration_ms=" not in normal_txt

        # 3. VERBOSE: memuat detail ilmiah lengkap (FITS header, rumus normalisasi flat, detail frame) tetapi bukan DEBUG
        verbose_txt = mode_logs[LogVerbosity.VERBOSE]
        assert "Detail mode changed: NORMAL -> VERBOSE." in verbose_txt
        assert "FITS header metadata:" in verbose_txt
        assert "Normalization method: F_norm(x,y) = F(x,y) / median(F_valid)" in verbose_txt
        assert "[DEBUG]" not in verbose_txt

        # 4. DEBUG: memuat seluruh informasi VERBOSE ditambah diagnostik teknis internal [DEBUG]
        debug_txt = mode_logs[LogVerbosity.DEBUG]
        assert "Detail mode changed: NORMAL -> DEBUG." in debug_txt
        assert "[DEBUG]" in debug_txt
        assert "Reader diagnostics:" in debug_txt
        assert "Output verification diagnostics:" in debug_txt
        assert "Stacking engine diagnostics:" in debug_txt

        # 5. Hasil ilmiah float32 identik bit-demi-bit di ketiga mode
        np.testing.assert_array_equal(mode_results[LogVerbosity.NORMAL], mode_results[LogVerbosity.VERBOSE])
        np.testing.assert_array_equal(mode_results[LogVerbosity.VERBOSE], mode_results[LogVerbosity.DEBUG])

    def test_refinement_4_export_directory_context_and_overwrite_safety(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Menguji Perbaikan 4: Export Visible & Export Complete Log otomatis mengarah ke
        folder sumber citra aktif (atau fallback folder log jika belum ada input)."""
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)

        win = MainWindow()
        try:
            panel = win.console_panel

            # Kasus 6: Belum ada gambar dibuka -> fallback ke default log_dir + catat log [EXPORT]
            default_vis = panel.get_default_export_path(complete=False)
            assert default_vis.parent == win.log_manager.log_dir.resolve()
            assert re.match(r"^HILALONE_Log_Visible_\d{8}_\d{6}\.log$", default_vis.name)
            export_logs = [
                format_console_line(e)
                for e in win.log_manager.session_entries
                if e.module == "EXPORT"
            ]
            assert any("No active source directory. Using default HILALONE log folder." in line for line in export_logs)

            # Kasus 1: Single Image -> folder tempat file gambar berada
            single_dir = tmp_path / "case1_single"
            single_dir.mkdir()
            p_single = _write_synthetic_fits(single_dir / "hilal_single.fits", np.ones((32, 32), dtype=np.float32))
            assert win.load_path(p_single) is True
            assert panel.get_default_export_path(complete=False).parent == single_dir.resolve()
            assert panel.get_default_export_path(complete=True).parent == single_dir.resolve()
            assert re.match(r"^HILALONE_Log_Complete_\d{8}_\d{6}\.log$", panel.get_default_export_path(complete=True).name)

            # Kasus 2: Multiple Images -> folder dari file utama/pertama
            multi_dir = tmp_path / "case2_multi"
            multi_dir.mkdir()
            p_m1 = _write_synthetic_fits(multi_dir / "m1.fits", np.ones((32, 32), dtype=np.float32))
            p_m2 = _write_synthetic_fits(multi_dir / "m2.fits", np.ones((32, 32), dtype=np.float32))
            assert win.load_sequence_paths([p_m1, p_m2]) is True
            assert panel.get_default_export_path(complete=False).parent == multi_dir.resolve()

            # Kasus 3: Folder Sequence -> folder sequence yang dipilih
            folder_seq = tmp_path / "case3_folder_seq"
            folder_seq.mkdir()
            _write_synthetic_fits(folder_seq / "seq1.fits", np.ones((32, 32), dtype=np.float32))
            _write_synthetic_fits(folder_seq / "seq2.fits", np.ones((32, 32), dtype=np.float32))
            assert win.load_folder_sequence(folder_seq) is True
            assert panel.get_default_export_path(complete=True).parent == folder_seq.resolve()

            # Kasus 5: SER -> folder tempat file SER berada
            ser_dir = tmp_path / "case5_ser"
            ser_dir.mkdir()
            ser_file = _write_synthetic_ser(ser_dir / "obs.ser", [np.ones((32, 32), dtype=np.uint8) for _ in range(3)])
            assert win.load_ser_path(ser_file) is True
            assert panel.get_default_export_path(complete=False).parent == ser_dir.resolve()

            # Kasus 4: Video -> folder tempat file video berada
            import av

            vid_dir = tmp_path / "case4_video"
            vid_dir.mkdir()
            vid_file = vid_dir / "obs.avi"
            cont = av.open(str(vid_file), mode="w")
            stream = cont.add_stream("mpeg4", rate=25)
            stream.width = 64
            stream.height = 48
            stream.pix_fmt = "yuv420p"
            for idx in range(3):
                rgb = np.full((48, 64, 3), 90 + idx * 5, dtype=np.uint8)
                vf = av.VideoFrame.from_ndarray(rgb, format="rgb24").reformat(64, 48, "yuv420p")
                vf.pts = idx
                for pkt in stream.encode(vf):
                    cont.mux(pkt)
            for pkt in stream.encode(None):
                cont.mux(pkt)
            cont.close()

            assert win.load_video_path(vid_file) is True
            assert panel.get_default_export_path(complete=True).parent == vid_dir.resolve()

            # Setelah close_image, source_directory di-reset kembali ke None
            win.close_image()
            assert win.log_manager.source_directory is None
        finally:
            win.close()

