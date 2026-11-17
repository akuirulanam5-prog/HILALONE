"""Dialog Pembaruan Aplikasi (Check for Updates) HILALONE.

Menampilkan detail rilis baru dari GitHub Releases, progres unduhan installer di
background thread (UpdateWorker), validasi SHA-256, serta konfirmasi aman sebelum
menjalankan installer Inno Setup.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hilalone.gui.resources import get_app_icon
from hilalone.gui.styles import DARK_TOKENS, NIGHT_VISION_TOKENS
from hilalone.updates.github_updater import (
    download_verified_installer,
    is_frozen_app,
    launch_installer,
    parse_sha256_digest,
)
from hilalone.updates.models import (
    DownloadResult,
    ReleaseAsset,
    UpdateCheckResult,
    UpdateIntegrityError,
)
from hilalone.updates.update_worker import UpdateWorker, UpdateWorkerMode


def format_installer_size(size_bytes: int) -> str:
    """Memformat ukuran berkas installer agar mudah dibaca pengguna."""
    if size_bytes <= 0:
        return "Tidak diketahui"
    mb_val = size_bytes / (1024.0 * 1024.0)
    return f"{mb_val:.1f} MB ({size_bytes:,} byte)"


def format_release_date(published_at: str) -> str:
    """Memformat tanggal rilis ISO-8601 dari GitHub API ke format ringkas."""
    raw = (published_at or "").strip()
    if not raw:
        return "-"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return raw


class UpdateDialog(QDialog):
    """Dialog pembaruan aplikasi HILALONE dengan unduhan terverifikasi SHA-256."""

    log_message_requested = Signal(str, str, str)  # (level, source, detail)
    install_close_requested = Signal()

    def __init__(
        self,
        check_result: UpdateCheckResult,
        *,
        night_vision: bool = False,
        is_frozen: bool | None = None,
        download_dir: Path | None = None,
        download_func: Callable[..., DownloadResult] | None = None,
        launch_func: Callable[..., Any] | None = None,
        active_processing_checker: Callable[[], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._check_result = check_result
        self._is_night_vision = bool(night_vision)
        self._is_frozen = is_frozen_app() if is_frozen is None else bool(is_frozen)
        self._download_dir = download_dir
        self._download_func = download_func or download_verified_installer
        self._launch_func = launch_func or launch_installer
        self._active_processing_checker = active_processing_checker
        self._download_worker: UpdateWorker | None = None
        self._is_downloading = False

        self.setWindowTitle("Pembaruan HILALONE Tersedia")
        self.setMinimumWidth(540)
        self.resize(580, 500)

        release = check_result.release
        asset = check_result.installer_asset

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        self.header_title = QLabel("Versi Baru HILALONE Tersedia")
        self.header_subtitle = QLabel(check_result.message)
        self.header_subtitle.setWordWrap(True)
        root.addWidget(self.header_title)
        root.addWidget(self.header_subtitle)

        # Kartu ringkasan versi, tanggal rilis, ukuran installer, dan digest
        self.meta_card = QFrame()
        self.meta_card.setObjectName("updateMetaCard")
        form = QFormLayout(self.meta_card)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        latest_ver_text = f"v{release.version.normalized}" if release is not None else "-"
        release_date_text = format_release_date(release.published_at) if release is not None else "-"
        size_text = format_installer_size(asset.size) if asset is not None else "-"
        asset_name_text = asset.name if asset is not None else "-"

        digest_status_text = "Tidak tersedia (instalasi otomatis dinonaktifkan)"
        if asset is not None and asset.digest:
            try:
                sha_hex = parse_sha256_digest(asset.digest)
                digest_status_text = f"SHA-256 tersedia ({sha_hex[:16]}...)"
            except UpdateIntegrityError:
                digest_status_text = "Format digest tidak valid (instalasi ditolak)"

        self.lbl_current_ver = QLabel(f"v{check_result.local_version}")
        self.lbl_latest_ver = QLabel(latest_ver_text)
        self.lbl_release_date = QLabel(release_date_text)
        self.lbl_installer_name = QLabel(asset_name_text)
        self.lbl_installer_size = QLabel(size_text)
        self.lbl_digest_status = QLabel(digest_status_text)

        self._form_key_labels: list[QLabel] = []
        for title, val_lbl in (
            ("Current version:", self.lbl_current_ver),
            ("Latest version:", self.lbl_latest_ver),
            ("Release date:", self.lbl_release_date),
            ("Installer file:", self.lbl_installer_name),
            ("Installer size:", self.lbl_installer_size),
            ("Verifikasi SHA-256:", self.lbl_digest_status),
        ):
            k_lbl = QLabel(title)
            self._form_key_labels.append(k_lbl)
            form.addRow(k_lbl, val_lbl)

        root.addWidget(self.meta_card)

        # Catatan Rilis
        self.notes_header = QLabel("Release Notes")
        root.addWidget(self.notes_header)

        self.notes_edit = QTextEdit()
        self.notes_edit.setReadOnly(True)
        self.notes_edit.setPlainText(
            release.body if (release is not None and release.body) else "(Tidak ada catatan rilis.)"
        )
        root.addWidget(self.notes_edit, 1)

        # Pemberitahuan mode pengembangan (source)
        self.dev_notice_label = QLabel(
            "Aplikasi saat ini dijalankan dari source / environment pengembangan. "
            "Pembaruan installer tidak dijalankan otomatis agar environment pengembangan "
            "tidak tertimpa. Gunakan 'Open Release Page' untuk melihat rilis resmi."
        )
        self.dev_notice_label.setWordWrap(True)
        self.dev_notice_label.setVisible(not self._is_frozen)
        root.addWidget(self.dev_notice_label)

        # Area progress unduhan
        self.progress_status_label = QLabel("")
        self.progress_status_label.setWordWrap(True)
        self.progress_status_label.setVisible(False)
        root.addWidget(self.progress_status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        root.addWidget(self.progress_bar)

        # Tombol aksi
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_row.setSpacing(8)

        self.btn_later = QPushButton("Later")
        self.btn_later.setObjectName("secondaryButton")
        self.btn_later.clicked.connect(self._on_later_or_cancel_clicked)

        self.btn_open_release = QPushButton("Open Release Page")
        self.btn_open_release.setObjectName("secondaryButton")
        self.btn_open_release.clicked.connect(self._on_open_release_page)

        self.btn_download_install = QPushButton("Download & Install")
        self.btn_download_install.setDefault(True)
        self.btn_download_install.clicked.connect(self._on_download_and_install_clicked)

        btn_row.addWidget(self.btn_later)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_open_release)
        btn_row.addWidget(self.btn_download_install)
        root.addLayout(btn_row)

        self.apply_theme(self._is_night_vision)

    def apply_theme(self, is_night_vision: bool) -> None:
        """Menyesuaikan tampilan dialog pembaruan dengan tema aktif."""
        self._is_night_vision = bool(is_night_vision)
        tokens = NIGHT_VISION_TOKENS if self._is_night_vision else DARK_TOKENS

        icon = get_app_icon(night_vision=self._is_night_vision)
        if not icon.isNull():
            self.setWindowIcon(icon)

        self.header_title.setStyleSheet(
            f"font-size: 13pt; font-weight: 700; color: {tokens.text_primary};"
        )
        self.header_subtitle.setStyleSheet(
            f"font-size: 9.5pt; color: {tokens.text_secondary};"
        )
        self.meta_card.setStyleSheet(
            f"QFrame#updateMetaCard {{"
            f"background-color: {tokens.bg_surface};"
            f"border: 1px solid {tokens.border_color};"
            f"border-radius: 8px;"
            f"}}"
        )
        for k_lbl in self._form_key_labels:
            k_lbl.setStyleSheet(f"color: {tokens.text_muted}; font-weight: 600;")
        for val_lbl in (
            self.lbl_current_ver,
            self.lbl_release_date,
            self.lbl_installer_name,
            self.lbl_installer_size,
            self.lbl_digest_status,
        ):
            val_lbl.setStyleSheet(f"color: {tokens.text_primary};")
        self.lbl_latest_ver.setStyleSheet(
            f"color: {tokens.status_info}; font-weight: 700;"
        )
        self.notes_header.setStyleSheet(
            f"font-size: 9.5pt; font-weight: 700; color: {tokens.text_secondary};"
        )
        self.dev_notice_label.setStyleSheet(
            f"background-color: {tokens.bg_surface}; border: 1px solid {tokens.status_warning}; "
            f"border-radius: 6px; padding: 8px 10px; color: {tokens.status_warning}; font-size: 9pt;"
        )
        self.progress_status_label.setStyleSheet(
            f"color: {tokens.status_info}; font-size: 9pt;"
        )

    def _on_open_release_page(self) -> None:
        url_str = (
            self._check_result.release.html_url
            if self._check_result.release is not None
            else "https://github.com/akuirulanam5-prog/HILALONE/releases"
        )
        QDesktopServices.openUrl(QUrl(url_str))
        self.log_message_requested.emit(
            "INFO",
            "Buka Halaman Rilis",
            f"Membuka {url_str} pada browser default.",
        )

    def _on_later_or_cancel_clicked(self) -> None:
        if self._is_downloading and self._download_worker is not None:
            self._download_worker.request_cancel()
            self.btn_later.setEnabled(False)
            self.progress_status_label.setText("Membatalkan pengunduhan secara aman...")
            return
        self.reject()

    def _on_download_and_install_clicked(self) -> None:
        if not self._is_frozen:
            reply = QMessageBox.information(
                self,
                "Mode Pengembangan Terdeteksi",
                "HILALONE dijalankan dari environment sumber (development), bukan aplikasi terinstal (.exe).\n\n"
                "Demi keamanan, installer pembaruan tidak dijalankan agar environment pengembangan Anda "
                "tidak tertimpa.\n\nApakah Anda ingin membuka halaman GitHub Releases resmi di browser?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._on_open_release_page()
            return

        if self._active_processing_checker is not None and self._active_processing_checker():
            QMessageBox.warning(
                self,
                "Pemrosesan Masih Berjalan",
                "Pemrosesan citra atau stacking masih berjalan di latar belakang.\n"
                "Selesaikan atau batalkan pemrosesan terlebih dahulu sebelum memperbarui aplikasi.",
            )
            return

        asset: ReleaseAsset | None = self._check_result.installer_asset
        if asset is None:
            QMessageBox.warning(
                self,
                "Asset Installer Tidak Ditemukan",
                "Berkas installer Windows tidak ditemukan pada rilis ini.",
            )
            return

        # Mulai download di QThread pekerja terpisah
        self._is_downloading = True
        self.btn_download_install.setEnabled(False)
        self.btn_open_release.setEnabled(False)
        self.btn_later.setText("Batalkan")
        self.progress_status_label.setVisible(True)
        self.progress_bar.setVisible(True)

        if asset.size > 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_status_label.setText("Menghubungkan ke server GitHub untuk mengunduh...")
        else:
            self.progress_bar.setRange(0, 0)
            self.progress_status_label.setText("Mengunduh installer pembaruan...")

        worker = UpdateWorker(
            mode=UpdateWorkerMode.DOWNLOAD_AND_VERIFY,
            local_version=self._check_result.local_version,
            asset=asset,
            dest_dir=self._download_dir,
            download_func=self._download_func,
            parent=self,
        )
        self._download_worker = worker
        worker.download_progress.connect(self._on_download_progress)
        worker.download_finished.connect(self._on_download_finished)
        worker.download_failed.connect(self._on_download_failed)
        worker.hash_verification_finished.connect(self._on_hash_verification_finished)
        worker.cancelled.connect(self._on_download_cancelled)
        worker.finished.connect(self._on_worker_finished)

        self.log_message_requested.emit(
            "INFO",
            "Unduh Pembaruan",
            f"Memulai unduhan {asset.name} dari GitHub Releases...",
        )
        worker.start()

    def _on_download_progress(self, bytes_downloaded: int, total_bytes: int) -> None:
        dl_mb = bytes_downloaded / (1024.0 * 1024.0)
        if total_bytes > 0:
            pct = max(0, min(100, int((bytes_downloaded * 100) / total_bytes)))
            total_mb = total_bytes / (1024.0 * 1024.0)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(pct)
            self.progress_status_label.setText(
                f"Mengunduh installer... {pct}% ({dl_mb:.1f} / {total_mb:.1f} MB)"
            )
        else:
            self.progress_bar.setRange(0, 0)
            self.progress_status_label.setText(f"Mengunduh installer... {dl_mb:.1f} MB")

    def _on_hash_verification_finished(self, passed: bool, detail: str) -> None:
        if passed:
            self.log_message_requested.emit(
                "SUCCESS",
                "Verifikasi SHA-256",
                f"Hash SHA-256 installer cocok: {detail}",
            )
        else:
            self.log_message_requested.emit(
                "ERROR",
                "Verifikasi SHA-256 Gagal",
                detail,
            )

    def _reset_download_ui(self) -> None:
        self._is_downloading = False
        self.btn_download_install.setEnabled(True)
        self.btn_open_release.setEnabled(True)
        self.btn_later.setEnabled(True)
        self.btn_later.setText("Later")

    def _on_download_failed(self, error_message: str) -> None:
        self._reset_download_ui()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_status_label.setText(f"Gagal: {error_message}")
        QMessageBox.warning(
            self,
            "Gagal Mengunduh Pembaruan",
            error_message,
        )

    def _on_download_cancelled(self, message: str) -> None:
        self._reset_download_ui()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_status_label.setText(message)
        self.log_message_requested.emit("WARNING", "Unduhan Dibatalkan", message)

    def _on_download_finished(self, result: DownloadResult) -> None:
        self._reset_download_ui()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_status_label.setText(
            f"Unduhan selesai & SHA-256 terverifikasi ({result.sha256_hex[:12]}...)."
        )

        ans = QMessageBox.question(
            self,
            "Jalankan Installer Pembaruan",
            f"Installer {result.file_path.name} berhasil diunduh dan integritas SHA-256 terverifikasi.\n\n"
            f"Lokasi: {result.file_path}\n\n"
            "HILALONE akan ditutup agar proses instalasi pembaruan berjalan aman "
            "dengan tetap mempertahankan pengaturan dan data pengguna Anda.\n\n"
            "Lanjutkan menutup HILALONE dan menjalankan installer?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self.progress_status_label.setText(
                f"Installer tersimpan di: {result.file_path}. Anda dapat menjalankannya kapan saja."
            )
            return

        if self._active_processing_checker is not None and self._active_processing_checker():
            QMessageBox.warning(
                self,
                "Pemrosesan Masih Berjalan",
                "Terdapat pemrosesan aktif yang baru dimulai. Selesaikan atau batalkan pemrosesan "
                "terlebih dahulu sebelum menutup HILALONE.",
            )
            return

        try:
            self._launch_func(
                result.file_path,
                expected_sha256=result.sha256_hex,
            )
        except Exception as exc:
            self.log_message_requested.emit("ERROR", "Gagal Menjalankan Installer", str(exc))
            QMessageBox.critical(
                self,
                "Gagal Menjalankan Installer",
                f"Installer tidak dapat dijalankan: {exc}",
            )
            return

        self.log_message_requested.emit(
            "INFO",
            "Menutup Aplikasi",
            "Installer dijalankan; HILALONE menutup jendela secara aman.",
        )
        self.accept()
        self.install_close_requested.emit()

    def _on_worker_finished(self) -> None:
        worker = self.sender()
        if isinstance(worker, UpdateWorker):
            worker.wait(500)
            if self._download_worker is worker:
                self._download_worker = None
            worker.deleteLater()

    def cancel_active_download(self) -> None:
        """Membatalkan unduhan aktif dan menunggu thread berhenti secara aman."""
        worker = self._download_worker
        if worker is not None:
            if worker.isRunning():
                worker.request_cancel()
            worker.wait(2000)

    def reject(self) -> None:
        self.cancel_active_download()
        super().reject()

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        self.cancel_active_download()
        super().closeEvent(event)
