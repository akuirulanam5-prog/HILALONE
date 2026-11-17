"""Dialog notifikasi pembaruan otomatis HILALONE.

Menampilkan ringkasan rilis terbaru yang stabil tanpa mengganggu alur kerja pengguna,
dengan dua tindakan utama: ``Update Now`` (membuka ``UpdateDialog``) dan ``Later``
(menunda pengingat selama 24 jam).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from hilalone.gui.resources import get_app_icon
from hilalone.gui.styles import DARK_TOKENS, NIGHT_VISION_TOKENS
from hilalone.gui.update_dialog import format_installer_size, format_release_date
from hilalone.updates.models import UpdateCheckResult

_MAX_SUMMARY_CHARS = 900


def summarize_release_notes(body: str, max_chars: int = _MAX_SUMMARY_CHARS) -> str:
    """Menyusun ringkasan catatan rilis agar nyaman dibaca pada dialog notifikasi."""
    text = (body or "").strip()
    if not text:
        return "(Tidak ada catatan rilis.)"
    if len(text) <= max_chars:
        return text
    cutoff = text[:max_chars].rstrip()
    return f"{cutoff}\n\n... (lihat detail lengkap setelah memilih Update Now)"


class UpdateNotificationDialog(QDialog):
    """Dialog notifikasi ringan saat pembaruan stabil HILALONE tersedia."""

    update_now_requested = Signal(object)  # Mengirimkan UpdateCheckResult
    later_requested = Signal(object)  # Mengirimkan UpdateCheckResult

    def __init__(
        self,
        check_result: UpdateCheckResult,
        *,
        night_vision: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._check_result = check_result
        self._is_night_vision = bool(night_vision)
        self._decision_emitted = False

        self.setWindowTitle("Pembaruan HILALONE Tersedia")
        self.setMinimumWidth(460)
        self.resize(500, 390)

        release = check_result.release
        asset = check_result.installer_asset

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(12)

        latest_text = f"v{release.version.normalized}" if release is not None else "-"
        self.header_title = QLabel(f"Pembaruan Tersedia: HILALONE {latest_text}")
        self.header_subtitle = QLabel(
            "Versi stabil terbaru HILALONE tersedia di GitHub Releases. "
            "Anda dapat memperbarui sekarang atau menunda selama 24 jam."
        )
        self.header_subtitle.setWordWrap(True)
        root.addWidget(self.header_title)
        root.addWidget(self.header_subtitle)

        # Ringkasan versi dan tanggal rilis
        self.info_card = QFrame()
        self.info_card.setObjectName("updateNotifInfoCard")
        form = QFormLayout(self.info_card)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.lbl_current_ver = QLabel(f"v{check_result.local_version}")
        self.lbl_latest_ver = QLabel(latest_text)
        self.lbl_release_date = QLabel(
            format_release_date(release.published_at) if release is not None else "-"
        )
        self.lbl_installer_size = QLabel(
            format_installer_size(asset.size) if asset is not None else "-"
        )

        self._form_key_labels: list[QLabel] = []
        for title, val_lbl in (
            ("Current version:", self.lbl_current_ver),
            ("Latest version:", self.lbl_latest_ver),
            ("Release date:", self.lbl_release_date),
            ("Installer size:", self.lbl_installer_size),
        ):
            k_lbl = QLabel(title)
            self._form_key_labels.append(k_lbl)
            form.addRow(k_lbl, val_lbl)

        root.addWidget(self.info_card)

        # Ringkasan Release Notes
        self.notes_label = QLabel("Ringkasan Release Notes")
        root.addWidget(self.notes_label)

        self.notes_summary_edit = QTextEdit()
        self.notes_summary_edit.setReadOnly(True)
        self.notes_summary_edit.setPlainText(
            summarize_release_notes(release.body if release is not None else "")
        )
        root.addWidget(self.notes_summary_edit, 1)

        # Dua tindakan utama: Later & Update Now
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_row.setSpacing(8)

        self.btn_later = QPushButton("Later")
        self.btn_later.setObjectName("secondaryButton")
        self.btn_later.clicked.connect(self._on_later_clicked)

        self.btn_update_now = QPushButton("Update Now")
        self.btn_update_now.setDefault(True)
        self.btn_update_now.clicked.connect(self._on_update_now_clicked)

        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_later)
        btn_row.addWidget(self.btn_update_now)
        root.addLayout(btn_row)

        self.apply_theme(self._is_night_vision)

    @property
    def check_result(self) -> UpdateCheckResult:
        """Hasil pemeriksaan pembaruan yang sedang diberitahukan."""
        return self._check_result

    def apply_theme(self, is_night_vision: bool) -> None:
        """Menyelaraskan tampilan dialog notifikasi dengan tema aktif."""
        self._is_night_vision = bool(is_night_vision)
        tokens = NIGHT_VISION_TOKENS if self._is_night_vision else DARK_TOKENS

        icon = get_app_icon(night_vision=self._is_night_vision)
        if not icon.isNull():
            self.setWindowIcon(icon)

        self.header_title.setStyleSheet(
            f"font-size: 12.5pt; font-weight: 700; color: {tokens.text_primary};"
        )
        self.header_subtitle.setStyleSheet(
            f"font-size: 9.5pt; color: {tokens.text_secondary};"
        )
        self.info_card.setStyleSheet(
            f"QFrame#updateNotifInfoCard {{"
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
            self.lbl_installer_size,
        ):
            val_lbl.setStyleSheet(f"color: {tokens.text_primary};")
        self.lbl_latest_ver.setStyleSheet(
            f"color: {tokens.status_info}; font-weight: 700;"
        )
        self.notes_label.setStyleSheet(
            f"font-size: 9.5pt; font-weight: 700; color: {tokens.text_secondary};"
        )

    def _on_update_now_clicked(self) -> None:
        if not self._decision_emitted:
            self._decision_emitted = True
            self.update_now_requested.emit(self._check_result)
        self.accept()

    def _on_later_clicked(self) -> None:
        if not self._decision_emitted:
            self._decision_emitted = True
            self.later_requested.emit(self._check_result)
        self.reject()

    def reject(self) -> None:
        if not self._decision_emitted:
            self._decision_emitted = True
            self.later_requested.emit(self._check_result)
        super().reject()
