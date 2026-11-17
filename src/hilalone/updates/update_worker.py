"""Worker thread (QThread) untuk pemeriksaan pembaruan dan pengunduhan installer HILALONE.

Menjaga main GUI thread tetap responsif selama permintaan HTTPS GitHub Releases API,
streaming unduhan installer, maupun perhitungan SHA-256.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
import threading
from typing import Callable

from PySide6.QtCore import QObject, QThread, Signal

from hilalone import __version__
from hilalone.updates.github_updater import check_for_updates, download_verified_installer
from hilalone.updates.models import (
    DownloadResult,
    ReleaseAsset,
    UpdateCancelledError,
    UpdateCheckResult,
    UpdateError,
    UpdateIntegrityError,
    UpdateStatus,
)


class UpdateWorkerMode(str, Enum):
    """Mode eksekusi thread pembaruan."""

    CHECK_ONLY = "CHECK_ONLY"
    DOWNLOAD_AND_VERIFY = "DOWNLOAD_AND_VERIFY"


class UpdateWorker(QThread):
    """QThread pekerja untuk cek rilis GitHub Releases dan unduh installer terverifikasi."""

    check_completed = Signal(object)  # Mengirimkan UpdateCheckResult
    update_available = Signal(object)  # Mengirimkan UpdateCheckResult
    up_to_date = Signal(object)  # Mengirimkan UpdateCheckResult
    check_failed = Signal(str)

    download_progress = Signal(int, int)  # (bytes_downloaded, total_bytes)
    download_finished = Signal(object)  # Mengirimkan DownloadResult
    download_failed = Signal(str)
    hash_verification_finished = Signal(bool, str)  # (valid, sha256_or_error_msg)
    cancelled = Signal(str)

    def __init__(
        self,
        mode: UpdateWorkerMode = UpdateWorkerMode.CHECK_ONLY,
        *,
        local_version: str = __version__,
        asset: ReleaseAsset | None = None,
        dest_dir: Path | None = None,
        check_func: Callable[..., UpdateCheckResult] | None = None,
        download_func: Callable[..., DownloadResult] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.mode = mode
        self.local_version = local_version
        self.asset = asset
        self.dest_dir = dest_dir
        self._check_func = check_func or check_for_updates
        self._download_func = download_func or download_verified_installer
        self._cancel_lock = threading.Lock()
        self._cancel_requested = False

    def request_cancel(self) -> None:
        """Meminta pembatalan operasi jaringan atau unduhan secara thread-safe."""
        with self._cancel_lock:
            self._cancel_requested = True

    def is_cancel_requested(self) -> bool:
        """Mengembalikan True apabila pengguna meminta pembatalan."""
        with self._cancel_lock:
            return self._cancel_requested

    def _run_check(self) -> None:
        try:
            result = self._check_func(local_version=self.local_version)
        except UpdateCancelledError as cancel_err:
            self.cancelled.emit(str(cancel_err))
            return
        except UpdateError as err:
            self.check_failed.emit(str(err))
            return
        except Exception as exc:
            self.check_failed.emit(f"Terjadi galat tak terduga saat memeriksa pembaruan: {exc}")
            return

        if self.is_cancel_requested():
            self.cancelled.emit("Pemeriksaan pembaruan dibatalkan oleh pengguna.")
            return

        self.check_completed.emit(result)
        if result.status == UpdateStatus.UPDATE_AVAILABLE and result.is_update_available:
            self.update_available.emit(result)
        else:
            self.up_to_date.emit(result)

    def _run_download(self) -> None:
        if self.asset is None:
            err_msg = "Metadata aset installer tidak tersedia untuk diunduh."
            self.hash_verification_finished.emit(False, err_msg)
            self.download_failed.emit(err_msg)
            return

        def _on_progress(downloaded: int, total: int) -> None:
            self.download_progress.emit(int(downloaded), int(total))

        try:
            dl_result = self._download_func(
                self.asset,
                dest_dir=self.dest_dir,
                progress_callback=_on_progress,
                cancel_check=self.is_cancel_requested,
            )
        except UpdateCancelledError as cancel_err:
            self.cancelled.emit(str(cancel_err))
            return
        except UpdateIntegrityError as int_err:
            msg = str(int_err)
            self.hash_verification_finished.emit(False, msg)
            self.download_failed.emit(msg)
            return
        except UpdateError as upd_err:
            msg = str(upd_err)
            self.hash_verification_finished.emit(False, msg)
            self.download_failed.emit(msg)
            return
        except Exception as exc:
            msg = f"Terjadi galat tak terduga saat mengunduh installer: {exc}"
            self.hash_verification_finished.emit(False, msg)
            self.download_failed.emit(msg)
            return

        if self.is_cancel_requested():
            self.cancelled.emit("Pengunduhan pembaruan dibatalkan oleh pengguna.")
            return

        self.hash_verification_finished.emit(True, dl_result.sha256_hex)
        self.download_finished.emit(dl_result)

    def run(self) -> None:  # pragma: no cover - dijalankan oleh QThread atau langsung di tes
        if self.mode == UpdateWorkerMode.CHECK_ONLY:
            self._run_check()
        elif self.mode == UpdateWorkerMode.DOWNLOAD_AND_VERIFY:
            self._run_download()
        else:
            self.check_failed.emit(f"Mode UpdateWorker tidak dikenal: {self.mode}")
