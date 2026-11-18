"""Pengujian Komprehensif (Unit, Integration, GUI, Multi-Workflow, & Backward Compatibility)
untuk HILALONE Scientific Processing Timeline & Report Schema v2.0 + Typography & Alignment Addendum.

Mencakup:
  - Addendum Bagian X (13 Kriteria Tipografi & Alignment Tiga Kolom):
    1. Label dengan panjang berbeda
    2. Alignment vertikal seluruh tanda titik dua (:)
    3. Alignment horizontal seluruh nilai (VALUE)
    4. Label terpanjang tanpa pemotongan
    5. Nilai panjang (long value)
    6. Baris lanjutan (wrapped line) tepat di bawah kolom VALUE
    7. Format durasi terpusat (0.00 s)
    8. Nilai kosong (empty value -> N/A)
    9. Nilai null (None -> N/A)
    10. Ekspor ke TXT (bebas ANSI escape sequence, rapi untuk Notepad)
    11. Ekspor ke LOG (bebas ANSI escape sequence, rapi untuk Notepad)
    12. Tema Standard Dark (hanya nilai status yang diwarnai khusus pada baris ringkasan)
    13. Tema Night Vision Red
  - Master Prompt Bagian XIX (A–G):
    A. Timestamp & Timezone (ISO-8601 + offset lokal)
    B. Duration (input, stage, idle, action interval, save dialog, image write, end-to-end)
    C. Timeline (urutan sequence, USER_ACTION vs OPERATION_*, latensi startup, idle interval)
    D. Processing stages (11 sub-tahap termasuk Flat, Master Flat, Stacking, Background, Enhancement, Histogram, Curve, Display)
    E. Output Save Transaction, pasangan JSON v2.0, penanganan gagal tulis JSON tanpa menghapus foto, & backward compatibility v1.0
    F. Integritas data ilmiah float32 & berkas sumber read-only
    G. Multi-workflow (Single Image, Multiple Images, Folder Sequence, Video deduplikasi, SER deduplikasi)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import time

from astropy.io import fits
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
import tifffile

from hilalone.core.logging import (
    HilaloneLogger,
    LogFilterCriteria,
    LogModule,
    LogVerbosity,
    ProcessingRunSummary,
    format_aligned_row,
    format_aligned_summary,
    format_console_line,
    format_duration_seconds,
)
from hilalone.gui.console_panel import ConsoleLogPanel
from hilalone.gui.main_window import MainWindow
from hilalone.output_manager.pipeline_writer import save_pipeline_result
from hilalone.processing.processing_history import (
    REPORT_SCHEMA_VERSION,
    format_report_text_summary,
    load_processing_report,
)
from hilalone.processing.processing_models import ProcessingProfile
from hilalone.processing.processing_pipeline import ProcessingPipelineOrchestrator


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _write_synthetic_fits(path: Path, data: np.ndarray, *, object_name: str = "Hilal Crescent") -> Path:
    hdu = fits.PrimaryHDU(data=data.astype(np.float32))
    hdu.header["OBJECT"] = object_name
    hdu.header["TELESCOP"] = "Takahashi FSQ-106"
    hdu.header["INSTRUME"] = "ZWO ASI2600MM"
    hdu.header["EXPTIME"] = 0.05
    hdu.header["DATE-OBS"] = "2026-11-18T11:15:00"
    hdu.header["FILTER"] = "IR-Pass 685nm"
    hdu.writeto(path, overwrite=True)
    return path


def _write_synthetic_ser(path: Path, frames: list[np.ndarray]) -> Path:
    n_frames = len(frames)
    h, w = frames[0].shape[:2]
    header = bytearray(178)
    header[0:14] = b"LUCAM-RECORDER"
    header[18:22] = (0).to_bytes(4, "little")
    header[26:30] = int(w).to_bytes(4, "little")
    header[30:34] = int(h).to_bytes(4, "little")
    header[34:38] = (8).to_bytes(4, "little")
    header[38:42] = int(n_frames).to_bytes(4, "little")
    header[42:82] = b"Observer Hilal".ljust(40, b"\x00")
    header[82:122] = b"ASI290MM".ljust(40, b"\x00")
    header[122:162] = b"Celestron C8".ljust(40, b"\x00")
    with open(path, "wb") as f:
        f.write(header)
        for frame in frames:
            f.write(np.clip(frame, 0, 255).astype(np.uint8).tobytes())
    return path


# ==============================================================================
# I. ADDENDUM TYPOGRAPHY & ALIGNMENT TESTS (Kriteria 1–13)
# ==============================================================================
class TestReportTypographyAndAlignment:
    def test_1_to_6_aligned_summary_colons_values_longest_label_and_wrapping(self) -> None:
        """Menguji kriteria 1–6: label berbeda panjang, titik dua sejajar vertikal,
        nilai sejajar horizontal, label panjang tidak terpotong, dan wrapping nilai panjang."""
        long_label = "Extremely Long Custom Astronomical Calibration Parameter Label"
        long_path = (
            r"D:\Astronomy\Hilal\Observations\2026\November\Session_18\Results"
            r"\moon_observation_sequence_2026_11_18_linear_master_processed.fits"
        )
        sections = [
            (
                "SESSION INFORMATION",
                [
                    ("Run ID", "RUN-20261118-101413-B01F87"),
                    ("Status", "SUCCESS"),
                    ("Profile", "BASIC"),
                ],
            ),
            (
                "PROCESSING RESULTS",
                [
                    ("Flat Calibration", "SKIPPED"),
                    (long_label, "COMPLETED"),
                ],
            ),
            (
                "OUTPUT INFORMATION",
                [
                    ("Output location", long_path),
                ],
            ),
        ]

        block = format_aligned_summary(
            sections,
            title="PROCESSING SUMMARY",
            footer="AUTOMATED PROCESSING COMPLETED",
            label_width=24,
            max_value_width=48,
        )
        lines = block.splitlines()

        # 1. Pastikan label terpanjang tetap utuh (tidak dipotong)
        assert any(long_label in line for line in lines)

        # 2. Ambil seluruh baris yang memiliki tanda titik dua ' : '
        kv_lines = [line for line in lines if " : " in line]
        assert len(kv_lines) == 6
        colon_positions = {line.index(" : ") for line in kv_lines}
        # Semua tanda titik dua WAJIB berada pada kolom horizontal yang persis sama!
        assert len(colon_positions) == 1
        colon_col = colon_positions.pop()
        value_col = colon_col + 3
        assert colon_col >= len(long_label)

        # 3. Semua nilai dimulai pada kolom value_col yang sama
        for line in kv_lines:
            assert line[colon_col : colon_col + 3] == " : "
            assert len(line) > value_col
            assert line[value_col] != " "

        # 4. Periksa baris lanjutan (wrapped line) dari long_path:
        #    Harus dimulai dengan spasi sepanjang value_col (tepat di bawah kolom VALUE, bukan kolom LABEL)
        out_idx = next(i for i, line in enumerate(lines) if line.startswith("Output location"))
        cont_line = lines[out_idx + 1]
        assert " : " not in cont_line
        assert cont_line[:value_col] == " " * value_col
        assert cont_line[value_col] != " "
        # Gabungan baris pertama dan baris lanjutan harus memuat akhir nama file
        assert "processed.fits" in block

    def test_7_to_9_duration_empty_and_null_formatting(self) -> None:
        """Menguji kriteria 7–9: format durasi 0.00 s, nilai kosong, dan nilai None."""
        assert format_duration_seconds(74179.24) == "74.18 s"
        assert format_duration_seconds(18707.36) == "18.71 s"
        assert format_duration_seconds(19.94) == "0.02 s"
        assert format_duration_seconds(264.1) == "0.26 s"
        assert format_duration_seconds(1207) == "1.21 s"
        assert format_duration_seconds(0) == "0.00 s"
        assert format_duration_seconds(None) == "0.00 s"

        row_empty = format_aligned_row("Empty Label", "", 20)[0]
        row_none = format_aligned_row("Null Label", None, 20)[0]
        assert row_empty.endswith(" : N/A")
        assert row_none.endswith(" : N/A")
        assert row_empty.index(" : ") == row_none.index(" : ") == 20

    def test_10_to_13_export_txt_log_and_themes_standard_dark_night_vision(
        self,
        qapp: QApplication,
        tmp_path: Path,
    ) -> None:
        """Menguji kriteria 10–13: ProcessingRunSummary aktual, ekspor TXT/LOG tanpa ANSI,
        serta pewarnaan nilai status di Standard Dark & Night Vision Red."""
        logger = HilaloneLogger(log_dir=tmp_path / "TypoLogs")
        panel = ConsoleLogPanel(logger)
        panel.show()

        summary = ProcessingRunSummary(
            run_id="RUN-20261118-101413-B01F87",
            session_id=logger.session_id,
            status="SUCCESS",
            profile="BASIC",
            input_mode="MULTI",
            input_files_summary="4 files (light_01.fits, ...)",
            input_frames=4,
            compatible_frames=4,
            incompatible_frames=0,
            frames_processed=4,
            frames_excluded=0,
            flat_calibration_status="SKIPPED",
            master_flat_status="SKIPPED",
            stacking_status="COMPLETED",
            background_status="COMPLETED",
            enhancement_status="COMPLETED",
            histogram_status="COMPLETED",
            curve_status="NOT USED",
            output_files=("hilal_linear_basic.fits",),
            save_status="SAVED",
            input_loading_sec=0.25,
            processing_time_sec=6.04,
            workflow_idle_sec=12.50,
            image_write_sec=0.04,
            end_to_end_sec=18.83,
        )
        logger.log_processing_summary(summary)
        qapp.processEvents()

        # Ekspor ke .txt dan .log
        txt_path = tmp_path / "summary_export.txt"
        log_path = tmp_path / "summary_export.log"
        logger.export_visible_log(txt_path, LogFilterCriteria())
        logger.export_complete_log(log_path)

        for p in (txt_path, log_path):
            content = p.read_text(encoding="utf-8")
            # Tidak boleh ada ANSI escape sequence
            assert "\x1b[" not in content
            assert "SESSION INFORMATION" in content
            assert "INPUT INFORMATION" in content
            assert "PROCESSING RESULTS" in content
            assert "OUTPUT INFORMATION" in content
            assert "TIME SUMMARY" in content
            assert "6.04 s" in content
            assert "18.83 s" in content

            # Semua baris ' : ' di dalam blok PROCESSING SUMMARY harus sejajar vertikal
            summary_kv_lines = [
                line for line in content.splitlines()
                if " : " in line and not line.startswith("[")
            ]
            assert len(summary_kv_lines) >= 15
            assert len({line.index(" : ") for line in summary_kv_lines}) == 1

        # Uji Standard Dark vs Night Vision Red pada ConsoleLogPanel
        panel.set_night_vision(False)
        qapp.processEvents()
        fmt_succ_dark = panel._resolve_value_status_format("COMPLETED")
        fmt_skip_dark = panel._resolve_value_status_format("SKIPPED")
        assert fmt_succ_dark.foreground().color().name().upper() == "#65DDA5"
        assert fmt_skip_dark.foreground().color().name().upper() == "#94A3B8"

        panel.set_night_vision(True)
        qapp.processEvents()
        fmt_succ_nv = panel._resolve_value_status_format("COMPLETED")
        fmt_skip_nv = panel._resolve_value_status_format("SKIPPED")
        assert fmt_succ_nv.foreground().color().name().upper() == "#FFA8A8"
        assert fmt_skip_nv.foreground().color().name().upper() == "#B88686"

        panel.close()


# ==============================================================================
# II. SCIENTIFIC PROCESSING TIMELINE & REPORT v2.0 TESTS (Bagian XIX A–G)
# ==============================================================================
class TestScientificProcessingReportV2:
    def test_a_to_e_end_to_end_gui_workflow_timeline_and_report_v2(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Menguji perjalanan lengkap dari Open Image -> Flat Calibration -> Pipeline -> Curve -> Save Image
        beserta validasi struktur JSON Report Schema v2.0, timeline, idle interval, dan save transaction."""
        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "critical", lambda *a, **kw: QMessageBox.StandardButton.Ok)

        win = MainWindow()
        try:
            # Atur threshold idle ke 10 ms agar jeda uji singkat tercatat sebagai WORKFLOW_IDLE_INTERVAL
            win.log_manager.timeline_tracker._idle_threshold_ms = 10.0

            # Buat 3 berkas FITS sequence + 1 Master Flat
            seq_dir = tmp_path / "obs_seq"
            seq_dir.mkdir()
            y, x = np.mgrid[0:48, 0:48].astype(np.float32)
            base_signal = 110.0 + 1.2 * y + 0.5 * x + 40.0 * np.exp(-((x - 24.0) ** 2 + (y - 24.0) ** 2) / 15.0).astype(np.float32)
            src_paths: list[Path] = []
            src_hashes: dict[Path, str] = {}
            for i in range(1, 4):
                p = _write_synthetic_fits(seq_dir / f"hilal_{i:02d}.fits", base_signal + i * 0.4)
                src_paths.append(p)
                src_hashes[p] = hashlib.sha256(p.read_bytes()).hexdigest()

            flat_path = _write_synthetic_fits(tmp_path / "master_flat.fits", np.full((48, 48), 1000.0, dtype=np.float32))

            # 1. Pengguna membuka Folder Sequence
            assert win.load_folder_sequence(seq_dir) is True

            # Simulasikan waktu idle aplikasi (30 ms) sebelum tindakan pengguna berikutnya
            time.sleep(0.035)

            # 2. Pengguna mengaktifkan Flat Calibration & memilih Master Flat
            win.flat_checkbox.setChecked(True)
            assert win.set_master_flat_path(flat_path) is True

            # Simulasikan waktu idle aplikasi (30 ms) sebelum menekan Start Automated Processing
            time.sleep(0.035)

            # 3. Pengguna menjalankan Automated Processing Pipeline
            assert win.start_automated_pipeline(wait_for_completion=True) is True
            assert win._last_pipeline_result is not None
            linear_before_save = win._last_pipeline_result.linear_result.copy()

            # 4. Pengguna membuka dan menerapkan Curve Transformation
            win.open_curves_window()
            assert win.curves_window is not None
            win.curves_window._preset_scurve()
            win.curves_window._on_apply_clicked()

            # 5. Pengguna menyimpan hasil melalui Save Dialog (uji Save Transaction lengkap dengan Save Dialog Duration)
            out_fits = tmp_path / "hilal_processed_v2.fits"

            def _mock_save_dialog(*args, **kwargs):
                time.sleep(0.025)  # Simulasikan dialog terbuka selama 25 ms
                return str(out_fits), "FITS Linear Float32 (*.fits *.fit)"

            monkeypatch.setattr(QFileDialog, "getSaveFileName", _mock_save_dialog)
            saved_img = win.save_pipeline_result_dialog(target_type="LINEAR_FITS")
            assert saved_img == out_fits
            assert out_fits.exists()

            report_json_path = tmp_path / "hilal_processed_v2_processing_report.json"
            assert report_json_path.exists()

            # 6. Verifikasi struktur lengkap JSON Report Schema v2.0
            report = json.loads(report_json_path.read_text(encoding="utf-8"))

            for section_key in (
                "report_metadata",
                "session_information",
                "source_data",
                "user_interaction_timeline",
                "workflow_idle_intervals",
                "processing_pipeline",
                "scientific_data_branches",
                "output_information",
                "timing_summary",
                "human_readable_timeline",
                "human_readable_summary",
                "warnings",
                "scientific_notes",
            ):
                assert section_key in report, f"Missing required v2.0 section: {section_key}"

            # IV. Report Metadata
            rm = report["report_metadata"]
            assert rm["schema_version"] == REPORT_SCHEMA_VERSION == "2.0"
            assert rm["report_id"].startswith("RPT-")
            assert rm["run_id"].startswith("RUN-")
            assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$", rm["generated_at"])

            # V. Session Information
            si = report["session_information"]
            assert si["session_id"].startswith("SES-")
            assert si["run_id"] == rm["run_id"]
            assert si["processing_profile"] == "BASIC"
            assert si["final_status"] == "SUCCESS"
            assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$", si["session_start_timestamp"])
            assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$", si["session_end_timestamp"])

            # VI. Source Data (3 berkas FITS unik)
            sd = report["source_data"]
            assert sd["file_count"] == 3
            assert sd["total_decoded_frames"] == 3
            assert len(sd["files"]) == 3
            assert sd["files"][0]["source_id"] == "SOURCE_001"
            assert sd["files"][0]["fits_metadata"]["TELESCOP"] == "Takahashi FSQ-106"

            # VII & VIII. User Interaction Timeline & Workflow Idle Intervals
            timeline = report["user_interaction_timeline"]
            assert len(timeline) >= 8
            seqs = [ev["sequence"] for ev in timeline]
            assert seqs == list(range(1, len(timeline) + 1))
            actions = [ev["action"] for ev in timeline]
            assert "OPEN_FOLDER_SEQUENCE_CLICKED" in actions
            assert "INPUT_LOADING_STARTED" in actions
            assert "INPUT_LOADING_COMPLETED" in actions
            assert "FLAT_FILE_SELECTED" in actions
            assert "START_AUTOMATIC_PROCESSING_CLICKED" in actions
            assert "AUTOMATED_PROCESSING_STARTED" in actions
            assert "AUTOMATED_PROCESSING_COMPLETED" in actions
            assert "CURVE_APPLIED" in actions
            assert "SAVE_CLICKED" in actions
            assert "SAVE_DIALOG_OPENED" in actions
            assert "OUTPUT_FILENAME_CONFIRMED" in actions
            assert "OUTPUT_WRITE_STARTED" in actions
            assert "OUTPUT_WRITE_COMPLETED" in actions

            # Event pertama memiliki interval_since_previous_action_ms == None; event user berikutnya > 0
            user_events = [ev for ev in timeline if ev["event_type"] == "USER_ACTION"]
            assert user_events[0]["interval_since_previous_action_ms"] is None
            assert any(
                ev["interval_since_previous_action_ms"] is not None and ev["interval_since_previous_action_ms"] > 0
                for ev in user_events[1:]
            )

            # Workflow Idle Intervals tercatat terpisah
            idles = report["workflow_idle_intervals"]
            assert len(idles) >= 1
            assert all(idl["interval_type"] == "WORKFLOW_IDLE_INTERVAL" for idl in idles)
            assert all(idl["duration_ms"] >= 10.0 for idl in idles)
            assert all(idl["duration_display"].endswith(" s") for idl in idles)

            # IX. Detailed Processing Pipeline (11 stages)
            pp = report["processing_pipeline"]
            for stg_name in (
                "input_loading",
                "input_validation",
                "flat_calibration",
                "master_flat_generation",
                "stacking",
                "background_extraction",
                "image_enhancement",
                "histogram_transformation",
                "curve_processing",
                "display_generation",
                "output_preparation",
            ):
                assert stg_name in pp
            assert pp["flat_calibration"]["status"] == "COMPLETED"
            assert pp["stacking"]["status"] == "COMPLETED"
            assert pp["curve_processing"]["status"] == "COMPLETED"
            assert pp["curve_processing"]["parameters"]["control_point_count"] >= 2
            # Histogram LINEAR_MTF tidak menampilkan parameter asinh_parameters atau ghs_parameters yang tidak dipakai
            assert "asinh_parameters" not in pp["histogram_transformation"]["parameters"]
            assert "ghs_parameters" not in pp["histogram_transformation"]["parameters"]

            # X. Output Save Transaction
            oi = report["output_information"]
            assert oi["transaction_id"].startswith("TX-")
            assert oi["save_dialog_duration_ms"] is not None and oi["save_dialog_duration_ms"] >= 15.0
            assert oi["image_write_duration_ms"] >= 0.0
            assert len(oi["output_artifacts"]) == 1
            art0 = oi["output_artifacts"][0]
            assert art0["artifact_id"] == "ART-001"
            assert art0["filename"] == "hilal_processed_v2.fits"
            assert art0["verified_on_disk"] is True
            assert oi["companion_json_report"]["referenced_artifact_id"] == "ART-001"
            assert oi["companion_json_report"]["referenced_image_filename"] == "hilal_processed_v2.fits"

            # XI. Timing Summary
            ts = report["timing_summary"]
            assert ts["end_to_end_elapsed_ms"] > 0.0
            assert ts["input_loading_ms"] > 0.0
            assert ts["processing_compute_sum_ms"] > 0.0
            assert ts["workflow_idle_total_ms"] >= 20.0
            assert ts["save_dialog_duration_ms"] >= 15.0
            assert ts["image_write_duration_ms"] >= 0.0
            assert ts["end_to_end_elapsed_display"].endswith(" s")

            # F. Data Integrity: Berkas sumber asli & array linear_result tidak berubah
            for p, orig_sha in src_hashes.items():
                assert hashlib.sha256(p.read_bytes()).hexdigest() == orig_sha
            np.testing.assert_array_equal(win._last_pipeline_result.linear_result, linear_before_save)
        finally:
            if win.curves_window is not None:
                win.curves_window.close()
            win.close()

    def test_video_and_ser_source_deduplication_and_skipped_stages(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Menguji Bagian VI & XIV: Satu berkas Video/SER dengan banyak frame hanya ditulis 1 kali
        pada source_data['files'] dengan decoded_frame_count = N (tidak diulang N kali)."""
        import av

        monkeypatch.setattr(QMessageBox, "warning", lambda *a, **kw: QMessageBox.StandardButton.Ok)
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: QMessageBox.StandardButton.Ok)

        # 1. Buat berkas video .avi dengan 6 frame
        vid_path = tmp_path / "hilal_capture.avi"
        cont = av.open(str(vid_path), mode="w")
        stream = cont.add_stream("mpeg4", rate=25)
        stream.width = 64
        stream.height = 48
        stream.pix_fmt = "yuv420p"
        for idx in range(6):
            rgb = np.full((48, 64, 3), 60 + idx * 5, dtype=np.uint8)
            vf = av.VideoFrame.from_ndarray(rgb, format="rgb24").reformat(64, 48, "yuv420p")
            vf.pts = idx
            for pkt in stream.encode(vf):
                cont.mux(pkt)
        for pkt in stream.encode(None):
            cont.mux(pkt)
        cont.close()

        win = MainWindow()
        try:
            assert win.load_video_path(vid_path) is True
            win.flat_checkbox.setChecked(False)
            assert win.start_automated_pipeline(wait_for_completion=True) is True

            out_vid_fits = tmp_path / "vid_stacked.fits"
            assert win.save_pipeline_result_to_path(out_vid_fits, save_target="LINEAR") == out_vid_fits
            vid_report = json.loads((tmp_path / "vid_stacked_processing_report.json").read_text(encoding="utf-8"))

            # Pastikan tidak mengulang 'hilal_capture.avi' 6 kali!
            assert vid_report["source_data"]["input_mode"] == "VIDEO"
            assert vid_report["source_data"]["file_count"] == 1
            assert vid_report["source_data"]["total_decoded_frames"] == 6
            assert len(vid_report["source_data"]["files"]) == 1
            assert vid_report["source_data"]["files"][0]["filename"] == "hilal_capture.avi"
            assert vid_report["source_data"]["files"][0]["decoded_frame_count"] == 6
            assert vid_report["source_file_names"] == ["hilal_capture.avi"]

            # Flat Calibration & Curve tidak dipakai -> status SKIPPED dan duration_ms == None
            assert vid_report["processing_pipeline"]["flat_calibration"]["status"] == "SKIPPED"
            assert vid_report["processing_pipeline"]["flat_calibration"]["duration_ms"] is None
            assert vid_report["processing_pipeline"]["curve_processing"]["status"] == "SKIPPED"
            assert vid_report["processing_pipeline"]["curve_processing"]["duration_ms"] is None

            # 2. Uji berkas SER dengan 5 frame
            ser_path = _write_synthetic_ser(
                tmp_path / "hilal_stream.ser",
                [np.full((32, 32), 100 + i * 4, dtype=np.uint8) for i in range(5)],
            )
            assert win.load_ser_path(ser_path) is True
            assert win.start_automated_pipeline(wait_for_completion=True) is True
            out_ser_fits = tmp_path / "ser_stacked.fits"
            assert win.save_pipeline_result_to_path(out_ser_fits, save_target="LINEAR") == out_ser_fits
            ser_report = json.loads((tmp_path / "ser_stacked_processing_report.json").read_text(encoding="utf-8"))

            assert ser_report["source_data"]["input_mode"] == "SER"
            assert ser_report["source_data"]["file_count"] == 1
            assert ser_report["source_data"]["total_decoded_frames"] == 5
            assert len(ser_report["source_data"]["files"]) == 1
            assert ser_report["source_data"]["files"][0]["filename"] == "hilal_stream.ser"
            assert ser_report["source_data"]["files"][0]["decoded_frame_count"] == 5
        finally:
            win.close()

    def test_report_write_failure_preserves_saved_image_and_logs_warning(
        self,
        qapp: QApplication,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Menguji Bagian X.B: Jika pembuatan JSON report gagal setelah foto tersimpan,
        foto yang sudah tersimpan TIDAK dihapus dan peringatan dicatat."""
        arr = np.linspace(0.1, 0.9, 32 * 32, dtype=np.float32).reshape(32, 32)
        orch = ProcessingPipelineOrchestrator(ProcessingProfile.BASIC)
        res = orch.run_on_single_image(arr)

        import hilalone.output_manager.pipeline_writer as pw_mod

        def _fail_report(*args, **kwargs):
            raise OSError("Simulated disk permission error while writing JSON report")

        monkeypatch.setattr(pw_mod, "build_pipeline_history_dict", _fail_report)

        out_img = tmp_path / "safe_photo.fits"
        saved_img, saved_json = save_pipeline_result(res, out_img, save_target="LINEAR", write_json_report=True)

        # Foto hasil WAJIB tetap ada dan utuh di disk, sedangkan json_path bernilai None
        assert saved_img == out_img
        assert saved_img.exists() and saved_img.stat().st_size > 0
        assert saved_json is None

    def test_backward_compatibility_v1_report_archive_reader(self, tmp_path: Path) -> None:
        """Menguji Bagian XVII: Laporan JSON v1.0 lama tetap dapat dibuka sebagai arsip."""
        legacy_v1 = {
            "application": "HILALONE",
            "timestamp_utc": "2026-11-15T12:00:00Z",
            "profile": "BASIC",
            "input_mode": "VIDEO",
            "source_file_names": ["hilal_old.avi"] * 10,
            "data_branches": {
                "linear_result": {"dtype": "float32", "shape": [48, 64], "min": 0.0, "max": 1.0, "nature": "SCIENTIFIC_LINEAR_FLOAT32"}
            },
            "warnings": [],
            "notes": ["Legacy note"],
        }
        v1_path = tmp_path / "legacy_v1_processing_report.json"
        v1_path.write_text(json.dumps(legacy_v1, indent=2), encoding="utf-8")

        loaded = load_processing_report(v1_path)
        assert loaded["report_metadata"]["schema_version"] == "1.0"
        assert loaded["source_data"]["file_count"] == 1
        assert loaded["source_data"]["total_decoded_frames"] == 10
        assert loaded["source_data"]["files"][0]["filename"] == "hilal_old.avi"
        assert loaded["source_data"]["files"][0]["decoded_frame_count"] == 10

        summary_txt = format_report_text_summary(loaded)
        assert "PROCESSING SUMMARY" in summary_txt
        assert "hilal_old.avi" in summary_txt
