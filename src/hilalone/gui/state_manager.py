"""Pengelola state pemrosesan GUI HILALONE.

Menyediakan mesin status (state machine) eksplisit untuk siklus hidup pemrosesan citra,
memastikan tombol kontrol antarmuka pengguna (input toolbar, viewer, aksi) selalu berada
pada kondisi yang valid dan tidak terkunci saat pemrosesan selesai, gagal, atau dibatalkan.
"""

from __future__ import annotations

from enum import Enum
from PySide6.QtCore import QObject, Signal


class ProcessingState(str, Enum):
    """Status siklus hidup pemrosesan citra HILALONE."""

    IDLE = "IDLE"              # Menunggu input pengguna; antarmuka siap digunakan.
    LOADING = "LOADING"        # Sedang memuat berkas citra / sequence ke memori.
    PROCESSING = "PROCESSING"  # Pipeline otomatis atau Stacking sedang berjalan di worker thread.
    CANCELLING = "CANCELLING"  # Permintaan pembatalan dikirim; menunggu worker berhenti aman.
    COMPLETED = "COMPLETED"    # Pemrosesan selesai sukses; produk ilmiah & pratinjau tersedia.
    FAILED = "FAILED"          # Pemrosesan mengalami galat; resource dibersihkan, kontrol dipulihkan.
    CANCELLED = "CANCELLED"    # Pemrosesan dibatalkan tuntas; worker dihentikan dan dibersihkan.


class ProcessingStateManager(QObject):
    """Pengelola transisi state pemrosesan citra terpusat untuk MainWindow."""

    state_changed = Signal(object)  # Mengirimkan enum ProcessingState baru

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._state: ProcessingState = ProcessingState.IDLE

    @property
    def current_state(self) -> ProcessingState:
        """Mengembalikan status pemrosesan saat ini."""
        return self._state

    @property
    def is_busy(self) -> bool:
        """Apakah sistem sedang sibuk menjalankan proses atau membatalkan proses."""
        return self._state in (
            ProcessingState.LOADING,
            ProcessingState.PROCESSING,
            ProcessingState.CANCELLING,
        )

    @property
    def is_processing(self) -> bool:
        """Apakah pemrosesan latar belakang (pipeline/stacking) aktif berjalan."""
        return self._state in (
            ProcessingState.PROCESSING,
            ProcessingState.CANCELLING,
        )

    def transition_to(self, new_state: ProcessingState) -> None:
        """Melakukan transisi ke state baru dan memancarkan sinyal ke GUI."""
        if self._state == new_state:
            return
        self._state = new_state
        self.state_changed.emit(new_state)
