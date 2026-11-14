"""Unit tests komprehensif untuk Redesign Antarmuka HILALONE (Siril-style UI/UX overhaul).

Menguji:
1. Top Navigation Bar & Menu Dropdown (Open Image, Image Processing, Tools, View).
2. Tiga Panel Utama Sejajar (OpenImagePanel, FrameListPanel, ImageInfoPanel).
3. Image Information Dialog (ala Siril FITS Header Editor, proteksi FITS structural keywords, copy, edit, add).
4. Console / Processing Log Panel (LogManager, levels, export TXT/CSV/JSON, clear).
5. Night Vision Red Theme (toggle stylesheet tanpa mengubah nilai piksel citra).
6. Histogram & Image Statistics Window (QPainter canvas, scale linear/log, filled/line, statistik, ekspor PNG & CSV).
7. Integrasi Seleksi Frame Panel B ke Stacking & Automated Pipeline.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile

import numpy as np
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication

from hilalone.gui.console_panel import ConsoleLogPanel, LogEntry, LogLevel, LogManager
from hilalone.gui.histogram_window import (
    HistogramCanvas,
    HistogramWindow,
)
from hilalone.gui.info_dialog import (
    FITS_PROTECTED_KEYWORDS,
    ImageInformationDialog,
)
from hilalone.gui.main_window import MainWindow
from hilalone.gui.styles import ThemeMode, get_theme_stylesheet
from hilalone.gui.top_panels import FrameListPanel, ImageInfoPanel, OpenImagePanel
from hilalone.input_manager.image_reader import ImageInfo
from hilalone.input_manager.models import (
    FrameStatus,
    InputMode,
    SequenceFrameEntry,
)
from hilalone.processing.stacking import StackingProfile
from hilalone.processing.processing_models import ProcessingProfile


def _make_dummy_entry(index: int, name: str, tmp_path: Path) -> SequenceFrameEntry:
    p = tmp_path / name
    info = ImageInfo(
        path=p,
        file_name=name,
        file_format="FITS",
        width=100,
        height=100,
        stored_width=100,
        stored_height=100,
        channels=1,
        has_alpha=False,
        original_bit_depth=16,
        original_is_float=False,
        preview_bit_depth=8,
        exif_orientation="normal",
        orientation_applied=False,
    )
    return SequenceFrameEntry(
        frame_index=index,
        source_path=p,
        info=info,
        status=FrameStatus.COMPATIBLE,
    )


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ==============================================================================
# 1. Console / Processing Log Tests
# ==============================================================================
class TestConsoleLog:
    def test_log_manager_and_export(self, qapp: QApplication, tmp_path: Path) -> None:
        manager = LogManager()
        manager.info("INPUT", "File Dimuat", "moon.fits berhasil dimuat")
        manager.success("STACKING", "Selesai", "10 frame digabungkan")
        manager.warning("CHECK", "Shift", "Pergeseran kecil terdeteksi")
        manager.error("IO", "Error", "Gagal membaca berkas")

        assert len(manager.entries) == 4
        assert manager.entries[0].level == LogLevel.INFO
        assert manager.entries[1].level == LogLevel.SUCCESS
        assert manager.entries[2].level == LogLevel.WARNING
        assert manager.entries[3].level == LogLevel.ERROR

        # Export TXT
        txt_path = tmp_path / "log.txt"
        assert manager.export_to_txt(txt_path)
        content_txt = txt_path.read_text(encoding="utf-8")
        assert "File Dimuat" in content_txt
        assert "SUCCESS" in content_txt

        # Export CSV
        csv_path = tmp_path / "log.csv"
        assert manager.export_to_csv(csv_path)
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        assert len(rows) == 5  # header + 4 rows
        assert rows[0] == ["Timestamp", "Level", "Module", "Action", "Detail"]

        # Export JSON
        json_path = tmp_path / "log.json"
        assert manager.export_to_json(json_path)
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert len(data) == 4
        assert data[0]["action"] == "File Dimuat"

        # Clear log
        manager.clear()
        assert len(manager.entries) == 0

    def test_console_log_panel_widget(self, qapp: QApplication) -> None:
        manager = LogManager()
        panel = ConsoleLogPanel(manager)
        manager.info("TEST", "Action1", "Detail 1")
        assert "Action1" in panel.text_edit.toPlainText()

        panel.clear_btn.click()
        assert panel.text_edit.toPlainText().strip() == ""


# ==============================================================================
# 2. Night Vision Red Theme Tests
# ==============================================================================
class TestNightVisionTheme:
    def test_stylesheets_validity(self) -> None:
        dark_css = get_theme_stylesheet(ThemeMode.STANDARD_DARK)
        red_css = get_theme_stylesheet(ThemeMode.NIGHT_VISION_RED)
        assert len(dark_css) > 100
        assert len(red_css) > 100
        assert "#e57373" in red_css  # Red theme soft red accent
        assert "#0d0404" in red_css  # Dark charcoal red background

    def test_main_window_theme_toggle(self, qapp: QApplication) -> None:
        win = MainWindow()
        try:
            assert win._is_night_vision is False
            win.toggle_night_vision_theme(True)
            assert win._is_night_vision is True
            assert win.act_night_vision.isChecked()
            assert win.btn_quick_night_vision.isChecked()

            win.toggle_night_vision_theme(False)
            assert win._is_night_vision is False
            assert not win.act_night_vision.isChecked()
            assert not win.btn_quick_night_vision.isChecked()
        finally:
            win.close()


# ==============================================================================
# 3. Image Information Dialog (FITS Header Editor ala Siril)
# ==============================================================================
class TestImageInformationDialog:
    def test_fits_structural_keywords_protection(self, qapp: QApplication) -> None:
        dlg = ImageInformationDialog()
        cards = [
            ("SIMPLE", "T", "Standard FITS format"),
            ("BITPIX", "16", "Bits per pixel"),
            ("NAXIS", "2", "Number of axes"),
            ("EXPTIME", "0.05", "Exposure time in seconds"),
            ("TELESCOP", "Celestron C8", "Telescope model"),
        ]
        dlg.populate_metadata(cards, "test.fits")

        # Seleksi baris BITPIX (index 1) -> Structural keyword, tombol Edit & Delete harus disabled
        dlg.table.selectRow(1)
        dlg._on_table_selection_changed()
        assert not dlg.btn_edit.isEnabled()
        assert not dlg.btn_delete.isEnabled()

        # Seleksi baris EXPTIME (index 3) -> Non-structural, tombol Edit & Delete harus enabled
        dlg.table.selectRow(3)
        dlg._on_table_selection_changed()
        assert dlg.btn_edit.isEnabled()
        assert dlg.btn_delete.isEnabled()

    def test_copy_metadata(self, qapp: QApplication) -> None:
        dlg = ImageInformationDialog()
        cards = [
            ("EXPTIME", "0.05", "Exposure time"),
            ("FILTER", "Red", "Color filter"),
        ]
        dlg.populate_metadata(cards, "test.fits")

        dlg.copy_all_to_clipboard()
        cb_text = QApplication.clipboard().text()
        assert "EXPTIME" in cb_text
        assert "FILTER" in cb_text

    def test_add_and_delete_metadata_row(self, qapp: QApplication) -> None:
        dlg = ImageInformationDialog()
        cards = [("OBSERVER", "Observer 1", "Observatory staff")]
        dlg.populate_metadata(cards, "test.fits")

        # Add custom row
        dlg._add_metadata_row("SITE", "Bosscha Observatory", "Location")
        assert dlg.table.rowCount() == 2
        assert dlg.table.item(1, 0).text() == "SITE"
        assert dlg.table.item(1, 1).text() == "Bosscha Observatory"

        # Delete row
        dlg.table.selectRow(1)
        dlg.delete_selected()
        assert dlg.table.rowCount() == 1

    def test_main_window_image_information_integration(self, qapp: QApplication, tmp_path: Path) -> None:
        from hilalone.gui.main_window import MainWindow
        import tifffile

        win = MainWindow()

        # 1. Panggil saat tidak ada gambar (tidak boleh crash, dialog harus muncul)
        win.open_image_information_dialog()
        assert win.info_dialog is not None
        assert win.info_dialog.isVisible()
        assert win.info_dialog.table.rowCount() >= 1
        assert win.info_dialog.table.item(0, 0).text() == "STATUS"

        # 2. Muat gambar sintetis TIFF
        test_file = tmp_path / "test_info_img.tif"
        synth_img = (np.ones((64, 64, 3)) * 128).astype(np.uint8)
        tifffile.imwrite(str(test_file), synth_img)

        ok = win.load_path(str(test_file))
        assert ok is True

        # Buka kembali dialog informasi
        win.open_image_information_dialog()
        assert win.info_dialog.isVisible()
        # Periksa kartu-kartu penting
        row_keys = [win.info_dialog.table.item(r, 0).text() for r in range(win.info_dialog.table.rowCount())]
        assert "FILENAME" in row_keys
        assert "FILE_PATH" in row_keys
        assert "FILE_FORMAT" in row_keys
        assert "NAXIS1" in row_keys
        assert "NAXIS2" in row_keys

        # Quick button info harus ada di header
        assert hasattr(win, "btn_quick_info")
        assert win.btn_quick_info is not None

        win.close_image()
        win.info_dialog.close()
        win.close()


# ==============================================================================
# 4. Histogram & Image Statistics Window Tests
# ==============================================================================
class TestHistogramWindow:
    def test_histogram_canvas_rendering(self, qapp: QApplication) -> None:
        canvas = HistogramCanvas()
        data = np.random.uniform(0.1, 0.9, (100, 100)).astype(np.float32)
        canvas.set_data(data, bins=256, is_log=False, is_filled=True)
        assert canvas._data is not None
        assert len(canvas._hist_cache) > 0

        # Uji toggle linear vs log
        canvas.set_data(data, bins=256, is_log=True, is_filled=False)
        assert canvas._is_log_scale is True
        assert canvas._is_filled is False

        # Uji reset view
        canvas.reset_view()
        assert canvas._zoom_factor == 1.0

    def test_histogram_window_statistics_and_export(self, qapp: QApplication, tmp_path: Path) -> None:
        win = HistogramWindow()
        # Data sintetis dengan min=0.0, max=1.0, mean~0.5
        data = np.linspace(0.0, 1.0, 1000, dtype=np.float32)
        win.set_image_data(data)

        # Verifikasi statistik terisi
        assert win._stats_labels["min"].text() != "-"
        assert float(win._stats_labels["min"].text()) == 0.0
        assert float(win._stats_labels["max"].text()) == 1.0
        assert "1,000" in win._stats_labels["total"].text()

        # Export PNG
        png_path = tmp_path / "hist.png"
        assert win.export_chart_png(png_path)
        assert png_path.exists() and png_path.stat().st_size > 0

        # Export CSV
        csv_path = tmp_path / "hist.csv"
        assert win.export_table_csv(csv_path)
        assert csv_path.exists()
        content = csv_path.read_text(encoding="utf-8")
        assert "Bin_Index" in content
        assert "Bin_Center" in content


# ==============================================================================
# 5. Top Panels (Panel A, B, C) Tests
# ==============================================================================
class TestTopPanels:
    def test_open_image_panel_buttons(self, qapp: QApplication) -> None:
        panel = OpenImagePanel()
        assert panel.btn_open_single is not None
        assert panel.btn_open_multi is not None
        assert panel.btn_open_folder is not None
        assert panel.btn_open_video is not None
        assert panel.btn_open_ser is not None
        assert panel.btn_close is not None

    def test_frame_list_panel_checkboxes(self, qapp: QApplication, tmp_path: Path) -> None:
        panel = FrameListPanel()
        entries = [
            _make_dummy_entry(0, "f1.fits", tmp_path),
            _make_dummy_entry(1, "f2.fits", tmp_path),
            _make_dummy_entry(2, "f3.fits", tmp_path),
        ]
        panel.populate_sequence(entries)
        assert panel.total_count() == 3
        assert len(panel.get_selected_frame_indices()) == 3
        assert "Selected: 3 / 3 Frames" in panel.counter_label.text()

        # Deselect all
        panel.btn_deselect_all.click()
        assert len(panel.get_selected_frame_indices()) == 0
        assert "Selected: 0 / 3 Frames" in panel.counter_label.text()

        # Select all
        panel.btn_select_all.click()
        assert len(panel.get_selected_frame_indices()) == 3

        # Uncheck single item
        item = panel.list_widget.item(1)
        item.setCheckState(Qt.CheckState.Unchecked)
        panel._on_item_changed(item)
        assert panel.get_selected_frame_indices() == [0, 2]
        assert "Selected: 2 / 3 Frames" in panel.counter_label.text()

    def test_image_info_panel(self, qapp: QApplication, tmp_path: Path) -> None:
        panel = ImageInfoPanel()
        entry = _make_dummy_entry(0, "sample.fits", tmp_path)
        panel.update_info(entry)
        assert panel.lbl_file.text() == "sample.fits"
        assert panel.lbl_format.text() == "FITS"

        panel.clear()
        assert panel.lbl_file.text() == "-"


# ==============================================================================
# 6. MainWindow Redesign Integration Tests
# ==============================================================================
class TestMainWindowRedesignIntegration:
    def test_menu_bar_structure(self, qapp: QApplication) -> None:
        win = MainWindow()
        try:
            mb = win.menuBar()
            menus = [act.text() for act in mb.actions()]
            assert "Open Image" in menus
            assert "Image Processing" in menus
            assert "Tools" in menus
            assert "View" in menus
        finally:
            win.close()

    def test_flat_info_dialog_popup(self, qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
        win = MainWindow()
        try:
            called = False
            def mock_info(parent, title, text):
                nonlocal called
                called = True
                assert "Flat-Field" in title

            from PySide6.QtWidgets import QMessageBox
            monkeypatch.setattr(QMessageBox, "information", mock_info)
            win.show_flat_info_dialog()
            assert called is True
        finally:
            win.close()

    def test_histogram_window_trigger(self, qapp: QApplication) -> None:
        win = MainWindow()
        try:
            win.open_histogram_window()
            assert win.histogram_window is not None
            assert win.histogram_window.isVisible()
        finally:
            if win.histogram_window:
                win.histogram_window.close()
            win.close()

    def test_image_info_dialog_trigger(self, qapp: QApplication) -> None:
        win = MainWindow()
        try:
            win.open_image_information_dialog()
            assert win.info_dialog is not None
            assert win.info_dialog.isVisible()
        finally:
            if win.info_dialog:
                win.info_dialog.close()
            win.close()

    def test_console_log_toggle(self, qapp: QApplication) -> None:
        win = MainWindow()
        try:
            # Default: Console Log tertutup agar ruang tampilan utama lebih luas
            assert win.console_panel.isHidden()
            assert not win.act_console_log.isChecked()
            assert not win.act_toggle_console.isChecked()
            assert not win.btn_quick_console.isChecked()

            win.toggle_console_panel(True)
            assert not win.console_panel.isHidden()
            assert win.act_console_log.isChecked()
            assert win.act_toggle_console.isChecked()
            assert win.btn_quick_console.isChecked()

            win.toggle_console_panel(False)
            assert win.console_panel.isHidden()
            assert not win.act_console_log.isChecked()
            assert not win.act_toggle_console.isChecked()
            assert not win.btn_quick_console.isChecked()
        finally:
            win.close()

    def test_top_panels_hidden_by_default_and_toggleable(self, qapp: QApplication) -> None:
        win = MainWindow()
        try:
            assert win.top_panels_widget.isHidden()
            assert win.panel_a.isHidden()
            assert win.panel_b.isHidden()
            assert win.panel_c.isHidden()

            # Toggle visible
            win._set_top_panels_visible(True)
            assert not win.top_panels_widget.isHidden()

            # Toggle hidden kembali
            win._set_top_panels_visible(False)
            assert win.top_panels_widget.isHidden()
        finally:
            win.close()

    def test_buttons_minimum_height_and_no_cut_off(self, qapp: QApplication) -> None:
        win = MainWindow()
        try:
            assert win.btn_quick_night_vision.minimumHeight() >= 28
            assert win.btn_quick_histogram.minimumHeight() >= 28
            assert win.btn_quick_curves.minimumHeight() >= 28
            assert win.btn_quick_console.minimumHeight() >= 28
            assert win.console_panel.clear_btn.minimumHeight() >= 28
            assert win.console_panel.export_btn.minimumHeight() >= 28
            assert win.console_panel.toggle_hide_btn.minimumHeight() >= 28
        finally:
            win.close()

    def test_dark_and_night_vision_stylesheets_complete(self) -> None:
        from hilalone.gui.styles import APP_STYLESHEET, NIGHT_VISION_RED_STYLESHEET
        for qss in (APP_STYLESHEET, NIGHT_VISION_RED_STYLESHEET):
            assert "QMenuBar" in qss
            assert "QListWidget" in qss
            assert "QPlainTextEdit" in qss
            assert "infoScrollContent" in qss
            assert "collapsibleButton" in qss
            assert "toggleBeforeAfterButton" in qss

    def test_preview_controls_box_always_visible(self, qapp: QApplication) -> None:
        win = MainWindow()
        try:
            # 1. Tampilan pratinjau harus terus muncul sejak dari awal
            assert not win.preview_controls_box.isHidden()

            # 2. Tetap muncul setelah data dibersihkan atau reset
            win.close_image()
            assert not win.preview_controls_box.isHidden()

            # 3. Tetap muncul saat update result section tanpa pipeline
            win._update_result_section()
            assert not win.preview_controls_box.isHidden()

            # 4. Interaksi tombol sebelum/sesudah aman walau belum ada pipeline
            win.toggle_before_after_button.click()
            assert win.toggle_before_after_button.isChecked()
            assert win._is_showing_before is True

            win.toggle_before_after_button.click()
            assert not win.toggle_before_after_button.isChecked()
            assert win._is_showing_before is False
        finally:
            win.close()

    def test_curves_window_trigger_and_presets(self, qapp: QApplication) -> None:
        from PySide6.QtGui import QImage
        from hilalone.gui.curves_window import CurvesWindow, compute_pchip_lut
        win = MainWindow()
        try:
            # Set dummy image to viewer dengan variasi piksel (gradient 0.0 s.d 1.0)
            dummy_img = QImage(100, 100, QImage.Format.Format_RGB888)
            dummy_img.fill(70)
            grad = np.linspace(0.0, 1.0, 100 * 100, dtype=np.float32).reshape(100, 100, 1)
            dummy_arr = np.repeat(grad, 3, axis=2)
            win.viewer.set_image(dummy_img, dummy_arr)

            # Trigger curves window
            win.open_curves_window()
            assert win.curves_window is not None
            assert win.curves_window.isVisible()

            # Test presets
            win.curves_window._preset_scurve()
            lut = win.curves_window.canvas.get_lut()
            assert len(lut) == 256
            assert 0.0 <= lut[0] <= 0.05
            assert 0.95 <= lut[-1] <= 1.0

            # Test apply pada piksel x=28 (nilai awal ~0.28)
            init_val = win.viewer.scientific_data()[28, 0, 0]
            win.curves_window.chk_live_preview.setChecked(False)
            win.curves_window._preset_scurve()
            win.curves_window.btn_apply.click()
            qapp.processEvents()
            assert win.viewer.has_image()
            # Nilai data ilmiah harus berubah setelah kurva S-Curve diterapkan (0.28 -> ~0.16)
            new_val = win.viewer.scientific_data()[28, 0, 0]
            assert not np.isclose(init_val, new_val)
            assert "Diterapkan" in win.curves_window.btn_apply.text()

            # Test reset
            win.curves_window.btn_reset.click()
            lut_reset = win.curves_window.canvas.get_lut()
            assert np.allclose(lut_reset, np.linspace(0.0, 1.0, 256), atol=1e-2)
        finally:
            if win.curves_window:
                win.curves_window.close()
            win.close()
