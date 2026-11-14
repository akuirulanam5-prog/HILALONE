"""Unit tests untuk sistem Collapsible Accordion Image Inspector Panel HILALONE."""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget
import tifffile

from hilalone.gui.accordion import AccordionGroup, AccordionHeader, AccordionSection
from hilalone.gui.main_window import MainWindow


def test_accordion_standalone_behavior(qapp: QApplication) -> None:
    """Menguji perilaku dasar AccordionSection: expand, collapse, icon, dan summary badge."""
    section = AccordionSection("Test Section", is_nested=False)
    content_lbl = QLabel("Inner Content")
    section.content_layout.addWidget(content_lbl)

    # State awal: collapsed (default)
    assert not section.is_expanded()
    assert section.content_container.isHidden()

    # Buka section
    section.set_expanded(True)
    assert section.is_expanded()
    assert not section.content_container.isHidden()
    # Summary label harus tersembunyi saat section terbuka
    section.set_summary("100 Frames | Ready")
    assert section.summary_label.isHidden()

    # Tutup section
    section.set_expanded(False)
    assert not section.is_expanded()
    assert section.content_container.isHidden()
    # Summary label harus tampil saat section tertutup dan summary tidak kosong
    assert not section.summary_label.isHidden()
    assert section.summary_label.text() == "100 Frames | Ready"

    # Klik header secara manual mentoggle kondisi
    section.header_button.click()
    assert section.is_expanded()
    section.header_button.click()
    assert not section.is_expanded()


def test_accordion_group_exclusivity(qapp: QApplication) -> None:
    """Menguji sifat eksklusif AccordionGroup: membuka satu section menutup yang lain."""
    group = AccordionGroup(exclusive=True)
    sec1 = AccordionSection("Section 1")
    sec2 = AccordionSection("Section 2")
    sec3 = AccordionSection("Section 3")

    group.add_section(sec1)
    group.add_section(sec2)
    group.add_section(sec3)

    # Buka Section 1
    sec1.set_expanded(True)
    assert sec1.is_expanded()
    assert not sec2.is_expanded()
    assert not sec3.is_expanded()

    # Buka Section 2 -> Section 1 otomatis tertutup
    sec2.set_expanded(True)
    assert not sec1.is_expanded()
    assert sec2.is_expanded()
    assert not sec3.is_expanded()

    # Klik Section 2 lagi (header button click) -> Section 2 tertutup kembali
    sec2.header_button.click()
    assert not sec1.is_expanded()
    assert not sec2.is_expanded()
    assert not sec3.is_expanded()

    # Buka Section 3 lalu panggil collapse_all()
    sec3.set_expanded(True)
    assert sec3.is_expanded()
    group.collapse_all()
    assert not sec1.is_expanded()
    assert not sec2.is_expanded()
    assert not sec3.is_expanded()


def test_main_window_accordion_structure(qapp: QApplication) -> None:
    """Menguji struktur accordion utama dan nested accordion di MainWindow."""
    win = MainWindow()

    # Pastikan section utama bertipe AccordionSection
    assert isinstance(win.section_input_sequence, AccordionSection)
    assert isinstance(win.section_processing, AccordionSection)
    assert isinstance(win.section_image_info, AccordionSection)
    assert isinstance(win.section_sensor_info, AccordionSection)
    assert isinstance(win.section_camera_metadata, AccordionSection)
    assert isinstance(win.section_fits_info, AccordionSection)
    assert isinstance(win.section_video_info, AccordionSection)
    assert isinstance(win.section_ser_info, AccordionSection)

    # Verifikasi state awal:
    # Section Processing (B) terbuka secara default
    assert win.section_processing.is_expanded()
    # Section lainnya tertutup secara default
    assert not win.section_input_sequence.is_expanded()
    assert not win.section_image_info.is_expanded()
    assert not win.section_sensor_info.is_expanded()

    # Verifikasi eksklusivitas accordion utama:
    win.section_input_sequence.header_button.click()
    assert win.section_input_sequence.is_expanded()
    assert not win.section_processing.is_expanded()

    win.section_image_info.header_button.click()
    assert not win.section_input_sequence.is_expanded()
    assert win.section_image_info.is_expanded()

    win.section_processing.header_button.click()
    assert win.section_processing.is_expanded()
    assert not win.section_image_info.is_expanded()


def test_nested_accordion_structure_and_controls(qapp: QApplication) -> None:
    """Menguji nested accordion di dalam B. AUTOMATED IMAGE PROCESSING dan keberadaan kontrol utama."""
    win = MainWindow()

    # Kontrol utama di Processing Section harus selalu ada dan terlihat langsung
    assert win.profile_combo is not None
    assert win.flat_checkbox is not None
    assert win.start_auto_process_button is not None
    assert win.start_stacking_button is not None
    assert win.stacking_progress_bar is not None
    assert win.stacking_status_label is not None

    # Nested accordions
    assert isinstance(win.acc_nested_adv_settings, AccordionSection)
    assert isinstance(win.acc_nested_flat_calib, AccordionSection)
    assert isinstance(win.acc_nested_flat_info, AccordionSection)
    assert isinstance(win.acc_nested_preview, AccordionSection)
    assert isinstance(win.acc_nested_histogram, AccordionSection)
    assert isinstance(win.acc_nested_results, AccordionSection)

    # Default state nested accordions: semua collapsed agar tampilan ringkas
    assert not win.acc_nested_adv_settings.is_expanded()
    assert not win.acc_nested_flat_calib.is_expanded()
    assert not win.acc_nested_flat_info.is_expanded()
    assert not win.acc_nested_preview.is_expanded()
    assert not win.acc_nested_histogram.is_expanded()
    assert not win.acc_nested_results.is_expanded()

    # Eksklusivitas nested accordion
    win.acc_nested_adv_settings.header_button.click()
    assert win.acc_nested_adv_settings.is_expanded()
    assert not win.acc_nested_flat_calib.is_expanded()

    win.acc_nested_flat_calib.header_button.click()
    assert not win.acc_nested_adv_settings.is_expanded()
    assert win.acc_nested_flat_calib.is_expanded()


def test_accordion_state_persistence_and_no_duplication(qapp: QApplication) -> None:
    """Menguji bahwa state kontrol (checkbox, combobox, dll) tidak hilang saat accordion ditutup dan dibuka."""
    win = MainWindow()

    # Buka advanced settings, ubah setting
    win.acc_nested_adv_settings.set_expanded(True)
    win.adv_clahe_enable_checkbox.setChecked(False)
    win.adv_bg_method_combo.setCurrentIndex(2)  # TPS RBF

    # Tutup lalu buka kembali berulang kali
    for _ in range(3):
        win.acc_nested_adv_settings.set_expanded(False)
        assert not win.acc_nested_adv_settings.is_expanded()
        win.acc_nested_adv_settings.set_expanded(True)
        assert win.acc_nested_adv_settings.is_expanded()

    # Nilai pengaturan harus tetap tersimpan
    assert not win.adv_clahe_enable_checkbox.isChecked()
    assert win.adv_bg_method_combo.currentIndex() == 2

    # Profil di processing card juga harus tetap tersimpan saat accordion processing ditutup dan dibuka
    win.profile_combo.setCurrentIndex(0)  # Basic
    win.section_processing.set_expanded(False)
    win.section_processing.set_expanded(True)
    assert win.profile_combo.currentIndex() == 0


def test_dynamic_summary_updates_on_file_load(qapp: QApplication, tmp_path: Path) -> None:
    """Menguji bahwa ringkasan dinamis pada header diperbarui saat citra dibuka."""
    win = MainWindow()

    # Buat file gambar sintetis
    img_path = tmp_path / "test_synth.tif"
    arr = (np.ones((48, 64), dtype=np.uint8) * 100)
    tifffile.imwrite(str(img_path), arr)

    ok = win.load_path(str(img_path))
    assert ok

    # Summary Input & Sequence harus terisi
    summary_seq = win.section_input_sequence.summary_label.text()
    assert "1 Frame" in summary_seq

    # Summary Image Info harus terisi dengan nama dan dimensi
    summary_img = win.section_image_info.summary_label.text()
    assert "test_synth.tif" in summary_img
    assert "64 × 48" in summary_img

    # Summary Sensor Info harus terisi
    summary_sensor = win.section_sensor_info.summary_label.text()
    assert "Mono" in summary_sensor
    assert "uint8" in summary_sensor

    # Processing summary harus terisi
    summary_proc = win.section_processing.summary_label.text()
    assert "Medium" in summary_proc or "Basic" in summary_proc

    # Tutup citra -> summary harus dibersihkan
    win.close_image()
    assert win.section_input_sequence.summary_label.text() == ""
    assert win.section_image_info.summary_label.text() == ""
    assert win.section_sensor_info.summary_label.text() == ""
