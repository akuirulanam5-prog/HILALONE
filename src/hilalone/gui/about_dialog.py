"""Dialog 'About HILALONE' terpisah dari ImageInformationDialog.

Menampilkan identitas resmi aplikasi, versi terpasang dari ``hilalone.__version__``,
logo tema aktif dari ``resources.py``, tagline ilmiah, tautan situs & GitHub,
serta mendukung tema Standard Dark dan Night Vision Red.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from hilalone import APP_NAME, APP_SUBTITLE, __version__
from hilalone.gui.resources import get_app_icon, get_compact_logo_pixmap
from hilalone.gui.styles import DARK_TOKENS, NIGHT_VISION_TOKENS
from hilalone.updates.models import GITHUB_OWNER, GITHUB_REPO, OFFICIAL_WEBSITE_URL

GITHUB_REPOSITORY_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
SCIENTIFIC_TAGLINE = "Enhance the Signal, Never Invent the Signal"


class AboutDialog(QDialog):
    """Jendela informasi resmi tentang aplikasi HILALONE."""

    def __init__(
        self,
        *,
        night_vision: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._is_night_vision = bool(night_vision)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setMinimumWidth(520)
        self.resize(560, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(12)

        # Kartu identitas utama (logo + nama + versi)
        self.identity_card = QFrame()
        self.identity_card.setObjectName("aboutIdentityCard")
        card_layout = QHBoxLayout(self.identity_card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(16)

        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.logo_label.setFixedSize(88, 88)
        card_layout.addWidget(self.logo_label, 0, Qt.AlignmentFlag.AlignTop)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(4)

        self.name_label = QLabel(APP_NAME)
        self.subtitle_label = QLabel(APP_SUBTITLE)
        self.version_label = QLabel(f"Versi {__version__}")
        self.tagline_label = QLabel(f'"{SCIENTIFIC_TAGLINE}"')
        self.tagline_label.setWordWrap(True)

        title_col.addWidget(self.name_label)
        title_col.addWidget(self.subtitle_label)
        title_col.addWidget(self.version_label)
        title_col.addWidget(self.tagline_label)
        card_layout.addLayout(title_col, 1)

        root.addWidget(self.identity_card)

        # Deskripsi singkat aplikasi
        self.description_label = QLabel(
            "Aplikasi desktop Windows untuk pengolahan citra pengamatan hilal dan bulan sabit "
            "muda secara deterministik dan jujur secara ilmiah menggunakan representasi internal "
            "float32 linear serta pemisahan tegas antara hasil linear dan tampilan visual."
        )
        self.description_label.setWordWrap(True)
        root.addWidget(self.description_label)

        # Ringkasan Pembaruan Terbaru (What's New in Current Release)
        self.whats_new_card = QFrame()
        self.whats_new_card.setObjectName("aboutWhatsNewCard")
        whats_new_layout = QVBoxLayout(self.whats_new_card)
        whats_new_layout.setContentsMargins(16, 12, 16, 12)
        whats_new_layout.setSpacing(6)

        self.whats_new_title_label = QLabel(f"Apa yang Baru di v{__version__}")
        self.whats_new_body_label = QLabel(
            "• Scientific Processing Log & Console System terpusat (Run ID, Session ID, .log & .jsonl).\n"
            "• Mode Detail bertingkat nyata: Normal, Verbose (metadata & rumus ilmiah), dan Debug (diagnostik).\n"
            "• Standardisasi seluruh durasi ke format 'Duration: 0.00 s' & perbaikan tombol Auto-scroll.\n"
            "• Export Visible & Export Complete Log otomatis mengarah ke folder sumber citra aktif.\n"
            "• Sistem Pembaruan Otomatis (GitHub Releases + verifikasi SHA-256) & aset branding resmi baru."
        )
        self.whats_new_body_label.setWordWrap(True)
        whats_new_layout.addWidget(self.whats_new_title_label)
        whats_new_layout.addWidget(self.whats_new_body_label)
        root.addWidget(self.whats_new_card)

        # Tautan resmi (Website & GitHub)
        self.links_card = QFrame()
        self.links_card.setObjectName("aboutLinksCard")
        links_layout = QVBoxLayout(self.links_card)
        links_layout.setContentsMargins(16, 12, 16, 12)
        links_layout.setSpacing(8)

        self.website_link_label = QLabel()
        self.website_link_label.setOpenExternalLinks(False)
        self.website_link_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.website_link_label.linkActivated.connect(self._open_external_url)

        self.github_link_label = QLabel()
        self.github_link_label.setOpenExternalLinks(False)
        self.github_link_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self.github_link_label.linkActivated.connect(self._open_external_url)

        links_layout.addWidget(self.website_link_label)
        links_layout.addWidget(self.github_link_label)
        root.addWidget(self.links_card)

        # Copyright & tombol tutup
        footer_row = QHBoxLayout()
        footer_row.setContentsMargins(0, 4, 0, 0)
        footer_row.setSpacing(8)

        self.copyright_label = QLabel("Copyright © 2026 HILALONE Project")
        footer_row.addWidget(self.copyright_label, 1, Qt.AlignmentFlag.AlignVCenter)

        self.close_button = QPushButton("Tutup")
        self.close_button.setObjectName("secondaryButton")
        self.close_button.setDefault(True)
        self.close_button.clicked.connect(self.accept)
        footer_row.addWidget(self.close_button, 0)

        root.addLayout(footer_row)
        self.apply_theme(self._is_night_vision)

    @staticmethod
    def _open_external_url(url_text: str) -> None:
        """Membuka URL tautan resmi melalui browser default pengguna."""
        QDesktopServices.openUrl(QUrl(url_text))

    def apply_theme(self, is_night_vision: bool) -> None:
        """Menyelaraskan logo, ikon jendela, dan warna komponen dengan tema aktif."""
        self._is_night_vision = bool(is_night_vision)
        tokens = NIGHT_VISION_TOKENS if self._is_night_vision else DARK_TOKENS

        icon = get_app_icon(night_vision=self._is_night_vision)
        if not icon.isNull():
            self.setWindowIcon(icon)

        raw_logo: QPixmap = get_compact_logo_pixmap(night_vision=self._is_night_vision)
        if not raw_logo.isNull():
            scaled = raw_logo.scaled(
                84,
                84,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.logo_label.setPixmap(scaled)

        self.identity_card.setStyleSheet(
            f"QFrame#aboutIdentityCard {{"
            f"background-color: {tokens.bg_surface};"
            f"border: 1px solid {tokens.border_color};"
            f"border-radius: 8px;"
            f"}}"
        )
        self.links_card.setStyleSheet(
            f"QFrame#aboutLinksCard {{"
            f"background-color: {tokens.bg_surface};"
            f"border: 1px solid {tokens.border_color};"
            f"border-radius: 8px;"
            f"}}"
        )
        self.whats_new_card.setStyleSheet(
            f"QFrame#aboutWhatsNewCard {{"
            f"background-color: {tokens.bg_surface};"
            f"border: 1px solid {tokens.border_color};"
            f"border-radius: 8px;"
            f"}}"
        )
        self.whats_new_title_label.setStyleSheet(
            f"font-size: 9.5pt; font-weight: 700; color: {tokens.text_primary};"
        )
        self.whats_new_body_label.setStyleSheet(
            f"font-size: 8.8pt; color: {tokens.text_secondary}; line-height: 1.35;"
        )
        self.name_label.setStyleSheet(
            f"font-size: 16pt; font-weight: 700; letter-spacing: 2px; color: {tokens.text_primary};"
        )
        self.subtitle_label.setStyleSheet(
            f"font-size: 10pt; font-weight: 500; color: {tokens.text_secondary};"
        )
        self.version_label.setStyleSheet(
            f"font-size: 9.5pt; font-weight: 700; color: {tokens.status_info};"
        )
        self.tagline_label.setStyleSheet(
            f"font-size: 9pt; font-style: italic; color: {tokens.text_secondary};"
        )
        self.description_label.setStyleSheet(
            f"font-size: 9.5pt; color: {tokens.text_secondary}; line-height: 1.4;"
        )
        self.copyright_label.setStyleSheet(
            f"font-size: 8.5pt; color: {tokens.text_muted};"
        )

        link_color = tokens.status_info
        self.website_link_label.setText(
            f"<span style='color:{tokens.text_secondary};'>Website Resmi:</span> "
            f"<a href='{OFFICIAL_WEBSITE_URL}' style='color:{link_color}; text-decoration:none;'>"
            f"{OFFICIAL_WEBSITE_URL}</a>"
        )
        self.github_link_label.setText(
            f"<span style='color:{tokens.text_secondary};'>GitHub Repository:</span> "
            f"<a href='{GITHUB_REPOSITORY_URL}' style='color:{link_color}; text-decoration:none;'>"
            f"{GITHUB_REPOSITORY_URL}</a>"
        )
