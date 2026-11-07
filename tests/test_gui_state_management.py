"""Pengujian integrasi untuk GUI state management, siklus hidup QThread worker,
dan pemulihan kontrol tombol antarmuka HILALONE.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from astropy.io import fits
from PySide6.QtWidgets import QApplication

from hilalone.gui.main_window import MainWindow
from hilalone.gui.pipeline_worker import PipelineWorker
from hilalone.gui.state_manager import ProcessingState, ProcessingStateManager
from hilalone.input_manager.image_reader import ImageInfo
from hilalone.processing.processing_models import (
    PipelineResult,
    ProcessingCancelledError,
    ProcessingError,
    ProcessingProfile,
)


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Fixture sesi untuk instance QApplication."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def synthetic_fits(tmp_path: Path) -> Path:
    """Membuat berkas FITS sintetis untuk pengujian."""
    fits_file = tmp_path / "test_hilal.fits"
    data = np.full((60, 60), 200.0, dtype=np.float32)
    fits.writeto(str(fits_file), data, overwrite=True)
    return fits_file


@pytest.fixture
def synthetic_fits_second(tmp_path: Path) -> Path:
    """Membuat berkas FITS sintetis kedua."""
    fits_file = tmp_path / "test_hilal_2.fits"
    data = np.full((40, 40), 150.0, dtype=np.float32)
    fits.writeto(str(fits_file), data, overwrite=True)
    return fits_file


def test_state_manager_transitions(qapp: QApplication) -> None:
    """Menguji fungsionalitas dan transisi state pada ProcessingStateManager."""
    sm = ProcessingStateManager()
    assert sm.current_state == ProcessingState.IDLE
    assert not sm.is_busy
    assert not sm.is_processing

    received_states = []
    sm.state_changed.connect(lambda s: received_states.append(s))

    sm.transition_to(ProcessingState.PROCESSING)
    assert sm.current_state == ProcessingState.PROCESSING
    assert sm.is_busy
    assert sm.is_processing

    sm.transition_to(ProcessingState.CANCELLING)
    assert sm.current_state == ProcessingState.CANCELLING
    assert sm.is_busy
    assert sm.is_processing

    sm.transition_to(ProcessingState.COMPLETED)
    assert sm.current_state == ProcessingState.COMPLETED
    assert not sm.is_busy
    assert not sm.is_processing

    assert received_states == [
        ProcessingState.PROCESSING,
        ProcessingState.CANCELLING,
        ProcessingState.COMPLETED,
    ]


def test_pipeline_success_restores_all_input_controls(
    qapp: QApplication, synthetic_fits: Path
) -> None:
    """Poin 1, 2, 3, 4, 5: Setelah pipeline berhasil, semua kontrol input & close aktif."""
    window = MainWindow()
    try:
        assert window.load_path(synthetic_fits)
        assert window.open_button.isEnabled()
        assert window.close_button.isEnabled()

        # Eksekusi pipeline otomatis
        success = window.start_automated_pipeline(wait_for_completion=True)
        assert success
        assert window.state_manager.current_state == ProcessingState.COMPLETED

        # 1. Open Image aktif
        assert window.open_button.isEnabled()
        # 2. Multiple Images aktif
        assert window.open_multi_button.isEnabled()
        # 3. Folder Sequence aktif
        assert window.open_folder_button.isEnabled()
        # 4. Video dan SER aktif
        assert window.open_video_button.isEnabled()
        assert window.open_ser_button.isEnabled()
        # 5. Close Image aktif jika ada gambar terbuka
        assert window.close_button.isEnabled()
        # Viewer dan Toolbar aktif
        assert window.viewer.has_image()
        assert window.save_result_button.isEnabled()
    finally:
        window.close()


def test_pipeline_failure_restores_controls(
    qapp: QApplication, synthetic_fits: Path
) -> None:
    """Poin 6: Setelah processing gagal, semua kontrol GUI dipulihkan."""
    window = MainWindow()
    try:
        assert window.load_path(synthetic_fits)

        # Simulasikan kegagalan pada worker dan cegah modal dialog
        with patch.object(window, "_show_error"):
            window._on_pipeline_failed("Simulasi galat internal")

        assert window.state_manager.current_state == ProcessingState.FAILED
        assert window.open_button.isEnabled()
        assert window.open_multi_button.isEnabled()
        assert window.open_folder_button.isEnabled()
        assert window.open_video_button.isEnabled()
        assert window.open_ser_button.isEnabled()
        assert window.close_button.isEnabled()
        assert not window.cancel_pipeline_button.isEnabled()
    finally:
        window.close()


def test_pipeline_cancelled_restores_controls(
    qapp: QApplication, synthetic_fits: Path
) -> None:
    """Poin 7: Setelah processing dibatalkan, semua kontrol GUI dipulihkan."""
    window = MainWindow()
    try:
        assert window.load_path(synthetic_fits)

        window.start_automated_pipeline(wait_for_completion=False)
        assert window.state_manager.is_busy

        # Batalkan pipeline
        window.cancel_automated_pipeline()
        assert window.state_manager.current_state == ProcessingState.CANCELLING

        # Tangani sinyal pembatalan selesai
        window._on_pipeline_cancelled("Dibatalkan pengujian")

        assert window.state_manager.current_state == ProcessingState.CANCELLED
        assert window.open_button.isEnabled()
        assert window.open_multi_button.isEnabled()
        assert window.open_folder_button.isEnabled()
        assert window.open_video_button.isEnabled()
        assert window.open_ser_button.isEnabled()
        assert window.close_button.isEnabled()
    finally:
        window.close()


def test_worker_exception_does_not_lock_gui(
    qapp: QApplication, synthetic_fits: Path
) -> None:
    """Poin 8: Exception saat menampilkan hasil tidak membuat GUI terkunci."""
    window = MainWindow()
    try:
        assert window.load_path(synthetic_fits)

        # Panggil _on_pipeline_finished dengan error rendering dan cegah modal dialog
        with patch.object(window, "_update_displayed_preview", side_effect=RuntimeError("Crash rendering")), \
             patch.object(window, "_show_error"):
            dummy_result = MagicMock(spec=PipelineResult)
            dummy_result.profile = ProcessingProfile.BASIC
            dummy_result.stacking_result = None
            window._on_pipeline_finished(dummy_result)

        # Kontrol input tetap harus diaktifkan kembali lewat blok finally
        assert window.open_button.isEnabled()
        assert window.open_multi_button.isEnabled()
        assert window.open_folder_button.isEnabled()
        assert window.open_video_button.isEnabled()
        assert window.open_ser_button.isEnabled()
        assert window.close_button.isEnabled()
        assert window.state_manager.current_state == ProcessingState.FAILED
    finally:
        window.close()


def test_qthread_and_worker_cleanup(
    qapp: QApplication, synthetic_fits: Path
) -> None:
    """Poin 9: Worker dan QThread dibersihkan saat proses selesai."""
    window = MainWindow()
    try:
        assert window.load_path(synthetic_fits)
        window.start_automated_pipeline(wait_for_completion=True)

        # Worker harus sudah di-set ke None dan tidak berjalan
        assert window._pipeline_worker is None
        assert not window._is_pipeline_running()
    finally:
        window.close()


def test_open_new_input_releases_old_session(
    qapp: QApplication, synthetic_fits: Path, synthetic_fits_second: Path
) -> None:
    """Poin 10: Membuka input baru melepaskan sesi lama dan memperbarui tampilan."""
    window = MainWindow()
    try:
        assert window.load_path(synthetic_fits)
        assert window.sequence_manager.entries[0].info.width == 60

        # Muat gambar kedua yang berukuran berbeda
        assert window.load_path(synthetic_fits_second)
        assert window.sequence_manager.entries[0].info.width == 40
        assert window.open_button.isEnabled()
        assert window.close_button.isEnabled()
    finally:
        window.close()


def test_scientific_result_retained_until_close(
    qapp: QApplication, synthetic_fits: Path
) -> None:
    """Poin 11: Hasil scientific terakhir tetap tersimpan pada state window."""
    window = MainWindow()
    try:
        assert window.load_path(synthetic_fits)
        assert window.start_automated_pipeline(wait_for_completion=True)

        assert window._last_pipeline_result is not None
        assert window._last_pipeline_result.linear_result is not None
        assert window.save_result_button.isEnabled()

        # Ketika close image dipanggil, barulah dibersihkan
        window.close_image()
        assert window._last_pipeline_result is None
        assert not window.viewer.has_image()
        assert not window.close_button.isEnabled()
        assert window.open_button.isEnabled()
        assert window.state_manager.current_state == ProcessingState.IDLE
    finally:
        window.close()
