"""Tema tampilan (QSS) HILALONE: gelap astronomi standar & Night Vision Red.

Menerapkan standar desain UI/UX tingkat tinggi:
  - Prinsip Anti Design-Slop: Tidak ada border tebal (>=2px) pada container rounded,
    menghilangkan visual clutter / card soup, menggunakan hairline border 1px halus,
    whitespace yang proporsional, dan penataan hierarki yang fungsional.
  - Prinsip UI/UX Pro Max & Better Web UI: Konsistensi tipografi, rhythm spacing (4px/8px),
    kontras aksesibilitas tinggi (WCAG AA 4.5:1), tombol tindakan primer (Primary CTA)
    yang menonjol, dan interaksi yang halus.
  - Ikonografi vektor murni (Lucide SVG) tanpa emoji teks.
"""

from dataclasses import dataclass
from enum import Enum


class ThemeMode(str, Enum):
    """Pilihan tema visual aplikasi HILALONE."""
    STANDARD_DARK = "STANDARD_DARK"
    NIGHT_VISION_RED = "NIGHT_VISION_RED"


@dataclass(frozen=True)
class DesignTokens:
    """Design tokens terpusat untuk konsistensi palet warna, kontras, dan status."""
    bg_main: str
    bg_surface: str
    bg_elevated: str
    border_color: str
    border_focus: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent_primary: str
    accent_hover: str
    accent_active: str
    status_success: str
    status_warning: str
    status_danger: str
    status_info: str
    input_bg: str
    input_border: str
    disabled_bg: str
    disabled_text: str


DARK_TOKENS = DesignTokens(
    bg_main="#080c14",
    bg_surface="#0f172a",
    bg_elevated="#1e293b",
    border_color="#1a2538",
    border_focus="#38bdf8",
    text_primary="#f8fafc",
    text_secondary="#cbd5e1",
    text_muted="#64748b",
    accent_primary="#2563eb",
    accent_hover="#1d4ed8",
    accent_active="#1e40af",
    status_success="#22c55e",
    status_warning="#facc15",
    status_danger="#ef4444",
    status_info="#38bdf8",
    input_bg="#0f172a",
    input_border="#1e293b",
    disabled_bg="#111827",
    disabled_text="#475569",
)

NIGHT_VISION_TOKENS = DesignTokens(
    bg_main="#0d0404",
    bg_surface="#1a0808",
    bg_elevated="#2d0c0c",
    border_color="#3d1414",
    border_focus="#ef4444",
    text_primary="#fca5a5",
    text_secondary="#e57373",
    text_muted="#7f1d1d",
    accent_primary="#b91c1c",
    accent_hover="#dc2626",
    accent_active="#991b1b",
    status_success="#ef4444",
    status_warning="#f87171",
    status_danger="#b91c1c",
    status_info="#f87171",
    input_bg="#140606",
    input_border="#3d1414",
    disabled_bg="#0d0404",
    disabled_text="#4c1414",
)


APP_STYLESHEET = """
QMainWindow, QWidget#central {
    background-color: #080c14;
}
QWidget {
    color: #e2e8f0;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 10pt;
}

/* Header Aplikasi */
QLabel#headerTitle {
    font-size: 19pt;
    font-weight: 700;
    letter-spacing: 3px;
    color: #f8fafc;
}
QLabel#headerSubtitle {
    font-size: 9.5pt;
    color: #94a3b8;
    letter-spacing: 0.5px;
}
QFrame#headerLine {
    background-color: #1a2538;
    max-height: 1px;
    min-height: 1px;
}

/* Menu Bar Ala Siril */
QMenuBar {
    background-color: #080c14;
    color: #e2e8f0;
    border-bottom: 1px solid #1a2538;
    padding: 3px 6px;
}
QMenuBar::item {
    background-color: transparent;
    padding: 6px 14px;
    border-radius: 4px;
    color: #cbd5e1;
    font-weight: 500;
}
QMenuBar::item:selected {
    background-color: #131d2e;
    color: #38bdf8;
}
QMenuBar::item:pressed {
    background-color: #0284c7;
    color: #ffffff;
}

/* Tombol Utama (Primary Button) */
QPushButton {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #3b82f6;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
    min-height: 28px;
}
QPushButton:hover {
    background-color: #1d4ed8;
    border: 1px solid #60a5fa;
}
QPushButton:pressed {
    background-color: #1e40af;
}
QPushButton:disabled {
    background-color: #111827;
    color: #475569;
    border: 1px solid #1e293b;
}
QPushButton:focus,
QToolButton:focus,
QComboBox:focus,
QLineEdit:focus,
QListWidget:focus,
QTableWidget:focus,
QCheckBox:focus {
    border: 1px solid #38bdf8;
}

/* Tombol Sekunder (Secondary Button) */
QPushButton#secondaryButton {
    background-color: #0f172a;
    color: #cbd5e1;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 5px 12px;
    min-height: 28px;
    font-weight: 500;
}
QPushButton#secondaryButton:hover {
    background-color: #1e293b;
    border: 1px solid #38bdf8;
    color: #ffffff;
}
QPushButton#secondaryButton:pressed {
    background-color: #0f172a;
}
QPushButton#secondaryButton:checked {
    background-color: #0369a1;
    border: 1px solid #38bdf8;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#secondaryButton:disabled {
    background-color: #0b1120;
    color: #475569;
    border: 1px solid #172033;
}

/* Pemilih Frame (ComboBox) */
QComboBox {
    background-color: #0b1120;
    color: #f1f5f9;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 5px 10px;
    min-height: 22px;
}
QComboBox:hover {
    border: 1px solid #38bdf8;
}
QComboBox:disabled {
    color: #475569;
    border: 1px solid #172033;
    background-color: #080d1a;
}
QComboBox QAbstractItemView {
    background-color: #0b1120;
    color: #f1f5f9;
    selection-background-color: #1e293b;
    selection-color: #38bdf8;
    border: 1px solid #1e293b;
    padding: 4px;
}

/* Area Image Viewer */
QLabel#imageViewer {
    background-color: #04070e;
    border: 1px solid #1a2538;
    border-radius: 8px;
    color: #64748b;
    font-size: 10.5pt;
}

/* Sidebar & Panel Informasi */
QFrame#infoPanel {
    background-color: #0b1120;
    border: 1px solid #1a2538;
    border-radius: 8px;
}
QScrollArea#infoScrollArea {
    background-color: transparent;
    border: none;
}
QWidget#infoScrollContent {
    background-color: #0b1120;
}
QFrame#infoSectionCard {
    background-color: #090e1a;
    border: 1px solid #1a2538;
    border-radius: 6px;
}
QLabel#infoTitle {
    font-size: 9.5pt;
    font-weight: 700;
    letter-spacing: 1.5px;
    color: #94a3b8;
}
QLabel#sectionHeader {
    font-size: 8.5pt;
    font-weight: 700;
    letter-spacing: 1px;
    color: #38bdf8;
    padding-bottom: 2px;
}
QLabel#subSectionHeader {
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 0.8px;
    color: #94a3b8;
    padding-top: 6px;
    padding-bottom: 2px;
    border-top: 1px solid #1a2538;
}
QPushButton#collapsibleButton {
    background-color: #0e1628;
    color: #94a3b8;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 6px 10px;
    text-align: left;
    font-size: 9pt;
    font-weight: 600;
    min-height: 28px;
}
QPushButton#collapsibleButton:hover {
    background-color: #15223b;
    border: 1px solid #38bdf8;
    color: #f1f5f9;
}
QPushButton#collapsibleButton:checked {
    background-color: #111d33;
    color: #38bdf8;
    border: 1px solid #0284c7;
}
QFrame#fullHeaderBox {
    background-color: #060913;
    border: 1px solid #1a2538;
    border-radius: 6px;
}

/* =========================================================================
 * Collapsible Accordion System (Image Inspector Panel)
 * ========================================================================= */
QFrame#accordionSection {
    background-color: #0b1120;
    border: 1px solid #1a2538;
    border-radius: 6px;
    margin-bottom: 6px;
}
QPushButton#accordionHeader {
    background-color: #0e1628;
    border: 1px solid #1a2538;
    border-radius: 5px;
    padding: 6px 10px;
    min-height: 32px;
    text-align: left;
}
QPushButton#accordionHeader:hover {
    background-color: #15223b;
    border: 1px solid #38bdf8;
}
QPushButton#accordionHeader:checked {
    background-color: #121d33;
    border: 1px solid #0284c7;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
}
QLabel#accordionTitle {
    font-size: 9.5pt;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: #f1f5f9;
}
QLabel#accordionSummary {
    font-size: 8.5pt;
    font-weight: 500;
    color: #38bdf8;
    background-color: #0c182c;
    border: 1px solid #1e3a5f;
    border-radius: 4px;
    padding: 2px 7px;
}
QFrame#accordionContent {
    background-color: #080d1a;
    border-top: 1px solid #1a2538;
    border-bottom-left-radius: 5px;
    border-bottom-right-radius: 5px;
    padding: 8px 10px;
}

/* Nested Accordion System (Automated Image Processing Sub-sections) */
QFrame#nestedAccordionSection {
    background-color: #080d19;
    border: 1px solid #162033;
    border-radius: 5px;
    margin-bottom: 4px;
}
QPushButton#nestedAccordionHeader {
    background-color: #0b1222;
    border: 1px solid #162033;
    border-radius: 4px;
    padding: 5px 8px;
    min-height: 28px;
    text-align: left;
}
QPushButton#nestedAccordionHeader:hover {
    background-color: #101c33;
    border: 1px solid #38bdf8;
}
QPushButton#nestedAccordionHeader:checked {
    background-color: #0e1a30;
    border: 1px solid #0284c7;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
}
QLabel#nestedAccordionTitle {
    font-size: 9pt;
    font-weight: 600;
    color: #cbd5e1;
}
QLabel#nestedAccordionSummary {
    font-size: 8pt;
    font-weight: 500;
    color: #7dd3fc;
    background-color: #0b172a;
    border: 1px solid #172d4a;
    border-radius: 3px;
    padding: 1px 5px;
}
QFrame#nestedAccordionContent {
    background-color: #060913;
    border-top: 1px solid #162033;
    border-bottom-left-radius: 4px;
    border-bottom-right-radius: 4px;
    padding: 6px 8px;
}
QLabel#infoKey {
    color: #94a3b8;
    font-size: 9pt;
}
QLabel#infoValue {
    color: #f1f5f9;
    font-size: 9pt;
}

/* Scrollbar Elegan & Ramping */
QScrollBar:vertical {
    background: #080c14;
    width: 7px;
    margin: 2px 0 2px 0;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #1e293b;
    min-height: 24px;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover {
    background: #38bdf8;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background: #080c14;
    height: 7px;
    margin: 0 2px 0 2px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal {
    background: #1e293b;
    min-width: 24px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal:hover {
    background: #38bdf8;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Panel Pemrosesan Citra (Automated Pipeline Card) */
QFrame#processingCard {
    background-color: #0b1120;
    border: 1px solid #1a2538;
    border-radius: 6px;
}
QPushButton#startStackingButton {
    background-color: #1e40af;
    color: #ffffff;
    border: 1px solid #3b82f6;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 9.5pt;
    font-weight: 700;
    min-height: 32px;
}
QPushButton#startStackingButton:hover {
    background-color: #2563eb;
    border: 1px solid #60a5fa;
}
QPushButton#startStackingButton:disabled {
    background-color: #111827;
    color: #475569;
    border: 1px solid #1e293b;
}

/* Tombol Aksi Primer Utama (Hero CTA) */
QPushButton#startAutoProcessButton {
    background-color: #059669;
    color: #ffffff;
    border: 1px solid #10b981;
    border-radius: 6px;
    padding: 9px 18px;
    font-size: 10pt;
    font-weight: 700;
    letter-spacing: 0.5px;
    min-height: 34px;
}
QPushButton#startAutoProcessButton:hover {
    background-color: #10b981;
    border: 1px solid #34d399;
}
QPushButton#startAutoProcessButton:disabled {
    background-color: #0f231e;
    color: #33594e;
    border: 1px solid #16382f;
}

/* Tombol Before / After */
QPushButton#toggleBeforeAfterButton {
    background-color: #131d2e;
    color: #93c5fd;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 8.5pt;
    font-weight: 600;
    min-height: 28px;
}
QPushButton#toggleBeforeAfterButton:hover {
    background-color: #1e2d47;
    border: 1px solid #38bdf8;
    color: #ffffff;
}
QPushButton#toggleBeforeAfterButton:checked {
    background-color: #0284c7;
    color: #ffffff;
    border: 1px solid #38bdf8;
}
QPushButton#toggleBeforeAfterButton:disabled {
    background-color: #0b1120;
    color: #475569;
    border: 1px solid #172033;
}

/* Progress Bar */
QProgressBar {
    background-color: #070a12;
    color: #f1f5f9;
    border: 1px solid #1e293b;
    border-radius: 5px;
    text-align: center;
    min-height: 20px;
    font-size: 8.5pt;
    font-weight: 600;
}
QProgressBar::chunk {
    background-color: #0284c7;
    border-radius: 4px;
}

/* CheckBox */
QCheckBox {
    color: #e2e8f0;
    font-size: 9pt;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #334155;
    background-color: #0b1120;
    border-radius: 3px;
}
QCheckBox::indicator:hover {
    border: 1px solid #38bdf8;
}
QCheckBox::indicator:checked {
    background-color: #0284c7;
    border: 1px solid #38bdf8;
    image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiNmZmZmZmYiIHN0cm9rZS13aWR0aD0iMy41IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwb2x5bGluZSBwb2ludHM9IjIwIDYgOSAxNyA0IDEyIi8+PC9zdmc+");
}

/* Tombol Info Flat-Field */
QToolButton#flatInfoButton {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 4px;
    padding: 2px;
}
QToolButton#flatInfoButton:hover {
    background-color: #1e293b;
    border: 1px solid #38bdf8;
}
QToolButton#flatInfoButton:pressed {
    background-color: #0284c7;
    border: 1px solid #38bdf8;
}

/* Image Action Toolbar */
QFrame#imageActionToolbar {
    background-color: #080c14;
    border: 1px solid #1a2538;
    border-radius: 6px;
    padding: 3px 6px;
}
QToolButton.imageActionButton {
    background-color: transparent;
    color: #e2e8f0;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 4px;
    min-width: 30px;
    min-height: 30px;
    max-width: 30px;
    max-height: 30px;
}
QToolButton.imageActionButton:hover {
    background-color: #131d2e;
    border: 1px solid #1e293b;
}
QToolButton.imageActionButton:pressed {
    background-color: #0284c7;
    border: 1px solid #38bdf8;
}
QToolButton.imageActionButton:checked {
    background-color: #0369a1;
    border: 1px solid #38bdf8;
}
QToolButton.imageActionButton:disabled {
    background-color: transparent;
    border: 1px solid transparent;
}
QToolButton.imageActionButton::menu-indicator {
    image: none;
    width: 0px;
}

/* Menu Dropdown Popup */
QMenu {
    background-color: #0b1120;
    color: #e2e8f0;
    border: 1px solid #1e293b;
    border-radius: 6px;
    padding: 4px 0px;
}
QMenu::item {
    padding: 6px 20px 6px 14px;
    font-size: 9pt;
}
QMenu::item:selected {
    background-color: #131d2e;
    color: #38bdf8;
}
QMenu::separator {
    height: 1px;
    background-color: #1a2538;
    margin: 4px 8px;
}

/* Tooltip */
QToolTip {
    background-color: #0b1120;
    color: #f8fafc;
    border: 1px solid #38bdf8;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 8.5pt;
}

/* Top Panels (Panel A, B, C) & Console Card */
QFrame#topPanelCard, QFrame#consoleCard {
    background-color: #0b1120;
    border: 1px solid #1a2538;
    border-radius: 6px;
}
QLabel#panelTitle {
    font-size: 8.5pt;
    font-weight: 700;
    letter-spacing: 1px;
    color: #38bdf8;
    padding-bottom: 2px;
}
QLabel#panelCounter {
    color: #38bdf8;
    font-size: 8.5pt;
}
QLabel#panelFileName {
    font-weight: bold;
    color: #60a5fa;
}

/* List & Table Widgets */
QListWidget, QListWidget#frameListWidget, QTableView, QTableWidget {
    background-color: #060913;
    alternate-background-color: #090e1a;
    gridline-color: #141c2c;
    color: #f1f5f9;
    border: 1px solid #1a2538;
    border-radius: 6px;
    outline: none;
}
QListWidget::item:selected, QListWidget#frameListWidget::item:selected, QTableView::item:selected, QTableWidget::item:selected {
    background-color: #0284c7;
    color: #ffffff;
}
QListWidget::item:hover, QListWidget#frameListWidget::item:hover, QTableView::item:hover, QTableWidget::item:hover {
    background-color: #0f172a;
}
QHeaderView {
    background-color: #090e1a;
}
QHeaderView::section {
    background-color: #090e1a;
    color: #94a3b8;
    border: 1px solid #1a2538;
    padding: 5px;
    font-weight: 600;
}
QTableCornerButton::section, QTableView QTableCornerButton::section {
    background-color: #090e1a;
    border: 1px solid #1a2538;
}

/* Console Log & Text Editors */
QPlainTextEdit, QTextEdit {
    background-color: #04070e;
    color: #38bdf8;
    border: 1px solid #1a2538;
    border-radius: 6px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 9pt;
    selection-background-color: #0284c7;
    selection-color: #ffffff;
}

/* Input Fields */
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #060913;
    color: #f1f5f9;
    border: 1px solid #1e293b;
    border-radius: 5px;
    padding: 4px 8px;
    min-height: 22px;
}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border: 1px solid #38bdf8;
}

QGroupBox {
    font-weight: 700;
    font-size: 9pt;
    color: #94a3b8;
    border: 1px solid #1a2538;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    background-color: #080c14;
    color: #38bdf8;
}

/* Status Bar */
QStatusBar {
    background-color: #060913;
    color: #94a3b8;
    border-top: 1px solid #1a2538;
}

/* Dialog & Message Box */
QMessageBox, QDialog {
    background-color: #080c14;
    color: #f1f5f9;
}
"""

NIGHT_VISION_RED_STYLESHEET = """
QMainWindow, QWidget#central {
    background-color: #0d0404;
}
QWidget {
    color: #e57373;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 10pt;
}

/* Header */
QLabel#headerTitle {
    font-size: 19pt;
    font-weight: 700;
    letter-spacing: 3px;
    color: #fecaca;
}
QLabel#headerSubtitle {
    font-size: 9.5pt;
    color: #b91c1c;
    letter-spacing: 0.5px;
}
QFrame#headerLine {
    background-color: #2b0b0b;
    max-height: 1px;
    min-height: 1px;
}

/* Menu Bar */
QMenuBar {
    background-color: #080202;
    color: #fca5a5;
    border-bottom: 1px solid #2b0b0b;
    padding: 3px 6px;
}
QMenuBar::item {
    background-color: transparent;
    padding: 6px 14px;
    border-radius: 4px;
    color: #f87171;
    font-weight: 500;
}
QMenuBar::item:selected {
    background-color: #1a0505;
    color: #ef4444;
}
QMenuBar::item:pressed {
    background-color: #991b1b;
    color: #ffffff;
}

/* Tombol Utama */
QPushButton {
    background-color: #991b1b;
    color: #ffffff;
    border: 1px solid #dc2626;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 600;
    min-height: 28px;
}
QPushButton:hover {
    background-color: #b91c1c;
    border: 1px solid #ef4444;
}
QPushButton:pressed {
    background-color: #7f1d1d;
}
QPushButton:disabled {
    background-color: #140404;
    color: #551616;
    border: 1px solid #220606;
}
QPushButton:focus,
QToolButton:focus,
QComboBox:focus,
QLineEdit:focus,
QListWidget:focus,
QTableWidget:focus,
QCheckBox:focus {
    border: 1px solid #ef4444;
}

/* Tombol Sekunder */
QPushButton#secondaryButton {
    background-color: #110404;
    color: #fca5a5;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
    padding: 5px 12px;
    min-height: 28px;
    font-weight: 500;
}
QPushButton#secondaryButton:hover {
    background-color: #1a0505;
    border: 1px solid #ef4444;
    color: #ffffff;
}
QPushButton#secondaryButton:pressed {
    background-color: #110404;
}
QPushButton#secondaryButton:checked {
    background-color: #7f1d1d;
    border: 1px solid #ef4444;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#secondaryButton:disabled {
    background-color: #0a0202;
    color: #551616;
    border: 1px solid #1a0505;
}

/* ComboBox */
QComboBox {
    background-color: #0f0303;
    color: #fca5a5;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
    padding: 5px 10px;
    min-height: 22px;
}
QComboBox:hover {
    border: 1px solid #ef4444;
}
QComboBox:disabled {
    color: #551616;
    border: 1px solid #1a0505;
}
QComboBox QAbstractItemView {
    background-color: #0f0303;
    color: #fca5a5;
    selection-background-color: #2b0b0b;
    selection-color: #ef4444;
    border: 1px solid #2b0b0b;
}

/* Viewer */
QLabel#imageViewer {
    background-color: #040101;
    border: 1px solid #2b0b0b;
    border-radius: 8px;
    color: #7f1d1d;
    font-size: 10.5pt;
}

/* Panel Informasi */
QFrame#infoPanel {
    background-color: #0d0303;
    border: 1px solid #2b0b0b;
    border-radius: 8px;
}
QScrollArea#infoScrollArea {
    background-color: transparent;
    border: none;
}
QWidget#infoScrollContent {
    background-color: #0d0303;
}
QFrame#infoSectionCard {
    background-color: #0a0202;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
}
QLabel#infoTitle {
    font-size: 9.5pt;
    font-weight: 700;
    letter-spacing: 1.5px;
    color: #f87171;
}
QLabel#sectionHeader {
    font-size: 8.5pt;
    font-weight: 700;
    letter-spacing: 1px;
    color: #ef4444;
    padding-bottom: 2px;
}
QLabel#subSectionHeader {
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 0.8px;
    color: #b91c1c;
    padding-top: 6px;
    padding-bottom: 2px;
    border-top: 1px solid #2b0b0b;
}
QPushButton#collapsibleButton {
    background-color: #110404;
    color: #fca5a5;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
    padding: 6px 10px;
    text-align: left;
    font-size: 9pt;
    font-weight: 600;
    min-height: 28px;
}
QPushButton#collapsibleButton:hover {
    background-color: #1a0505;
    border: 1px solid #ef4444;
}
QPushButton#collapsibleButton:checked {
    background-color: #240707;
    color: #ef4444;
    border: 1px solid #dc2626;
}
QFrame#fullHeaderBox {
    background-color: #060101;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
}

/* =========================================================================
 * Collapsible Accordion System (Night Vision Red Theme)
 * ========================================================================= */
QFrame#accordionSection {
    background-color: #110404;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
    margin-bottom: 6px;
}
QPushButton#accordionHeader {
    background-color: #160606;
    border: 1px solid #2b0b0b;
    border-radius: 5px;
    padding: 6px 10px;
    min-height: 32px;
    text-align: left;
}
QPushButton#accordionHeader:hover {
    background-color: #240a0a;
    border: 1px solid #ef4444;
}
QPushButton#accordionHeader:checked {
    background-color: #200808;
    border: 1px solid #dc2626;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
}
QLabel#accordionTitle {
    font-size: 9.5pt;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: #fecaca;
}
QLabel#accordionSummary {
    font-size: 8.5pt;
    font-weight: 500;
    color: #f87171;
    background-color: #200606;
    border: 1px solid #451010;
    border-radius: 4px;
    padding: 2px 7px;
}
QFrame#accordionContent {
    background-color: #0b0202;
    border-top: 1px solid #2b0b0b;
    border-bottom-left-radius: 5px;
    border-bottom-right-radius: 5px;
    padding: 8px 10px;
}

/* Nested Accordion System (Night Vision Red) */
QFrame#nestedAccordionSection {
    background-color: #0d0303;
    border: 1px solid #220707;
    border-radius: 5px;
    margin-bottom: 4px;
}
QPushButton#nestedAccordionHeader {
    background-color: #130404;
    border: 1px solid #220707;
    border-radius: 4px;
    padding: 5px 8px;
    min-height: 28px;
    text-align: left;
}
QPushButton#nestedAccordionHeader:hover {
    background-color: #1c0707;
    border: 1px solid #ef4444;
}
QPushButton#nestedAccordionHeader:checked {
    background-color: #180505;
    border: 1px solid #b91c1c;
    border-bottom-left-radius: 0px;
    border-bottom-right-radius: 0px;
}
QLabel#nestedAccordionTitle {
    font-size: 9pt;
    font-weight: 600;
    color: #fca5a5;
}
QLabel#nestedAccordionSummary {
    font-size: 8pt;
    font-weight: 500;
    color: #f87171;
    background-color: #180404;
    border: 1px solid #360c0c;
    border-radius: 3px;
    padding: 1px 5px;
}
QFrame#nestedAccordionContent {
    background-color: #080202;
    border-top: 1px solid #220707;
    border-bottom-left-radius: 4px;
    border-bottom-right-radius: 4px;
    padding: 6px 8px;
}
QLabel#infoKey {
    color: #b91c1c;
    font-size: 9pt;
}
QLabel#infoValue {
    color: #fca5a5;
    font-size: 9pt;
}

/* Scrollbar */
QScrollBar:vertical {
    background: #080202;
    width: 7px;
    margin: 2px 0 2px 0;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #2b0b0b;
    min-height: 24px;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover {
    background: #ef4444;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Panel Pemrosesan */
QFrame#processingCard {
    background-color: #0d0303;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
}
QPushButton#startStackingButton {
    background-color: #7f1d1d;
    color: #ffffff;
    border: 1px solid #b91c1c;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 9.5pt;
    font-weight: 700;
    min-height: 32px;
}
QPushButton#startStackingButton:hover {
    background-color: #991b1b;
    border: 1px solid #ef4444;
}
QPushButton#startStackingButton:disabled {
    background-color: #140404;
    color: #551616;
    border: 1px solid #220606;
}
QPushButton#startAutoProcessButton {
    background-color: #991b1b;
    color: #ffffff;
    border: 1px solid #ef4444;
    border-radius: 6px;
    padding: 9px 18px;
    font-size: 10pt;
    font-weight: 700;
    letter-spacing: 0.5px;
    min-height: 34px;
}
QPushButton#startAutoProcessButton:hover {
    background-color: #b91c1c;
}
QPushButton#startAutoProcessButton:disabled {
    background-color: #140404;
    color: #551616;
    border: 1px solid #220606;
}
QPushButton#toggleBeforeAfterButton {
    background-color: #140404;
    color: #fca5a5;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 8.5pt;
    font-weight: 600;
    min-height: 28px;
}
QPushButton#toggleBeforeAfterButton:hover {
    background-color: #1e0606;
    border: 1px solid #ef4444;
}
QPushButton#toggleBeforeAfterButton:checked {
    background-color: #7f1d1d;
    color: #ffffff;
    border: 1px solid #ef4444;
}

QProgressBar {
    background-color: #060101;
    color: #fca5a5;
    border: 1px solid #2b0b0b;
    border-radius: 5px;
    text-align: center;
    min-height: 20px;
    font-size: 8.5pt;
    font-weight: 600;
}
QProgressBar::chunk {
    background-color: #991b1b;
    border-radius: 4px;
}
QCheckBox {
    color: #fca5a5;
    font-size: 9pt;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid #3d1414;
    background-color: #0f0303;
    border-radius: 3px;
}
QCheckBox::indicator:hover {
    border: 1px solid #ef4444;
}
QCheckBox::indicator:checked {
    background-color: #991b1b;
    border: 1px solid #ef4444;
    image: url("data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IiNmZmZmZmYiIHN0cm9rZS13aWR0aD0iMy41IiBzdHJva2UtbGluZWNhcD0icm91bmQiIHN0cm9rZS1saW5lam9pbj0icm91bmQiPjxwb2x5bGluZSBwb2ludHM9IjIwIDYgOSAxNyA0IDEyIi8+PC9zdmc+");
}

/* Tombol Info Flat-Field */
QToolButton#flatInfoButton {
    background-color: #110404;
    border: 1px solid #2b0b0b;
    border-radius: 4px;
    padding: 2px;
}
QToolButton#flatInfoButton:hover {
    background-color: #1a0505;
    border: 1px solid #ef4444;
}
QToolButton#flatInfoButton:pressed {
    background-color: #7f1d1d;
    border: 1px solid #ef4444;
}

/* Image Action Toolbar */
QFrame#imageActionToolbar {
    background-color: #080202;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
    padding: 3px 6px;
}
QToolButton.imageActionButton {
    background-color: transparent;
    color: #fca5a5;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 4px;
    min-width: 30px;
    min-height: 30px;
    max-width: 30px;
    max-height: 30px;
}
QToolButton.imageActionButton:hover {
    background-color: #170404;
    border: 1px solid #3d1414;
}
QToolButton.imageActionButton:pressed, QToolButton.imageActionButton:checked {
    background-color: #7f1d1d;
    border: 1px solid #ef4444;
}

/* Menu Dropdown */
QMenu {
    background-color: #0d0303;
    color: #fca5a5;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
    padding: 4px 0px;
}
QMenu::item {
    padding: 6px 20px 6px 14px;
    font-size: 9pt;
}
QMenu::item:selected {
    background-color: #1e0606;
    color: #ef4444;
}
QMenu::separator {
    height: 1px;
    background-color: #2b0b0b;
    margin: 4px 8px;
}

/* Tooltip */
QToolTip {
    background-color: #0d0303;
    color: #fecaca;
    border: 1px solid #ef4444;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 8.5pt;
}

/* Status Bar */
QStatusBar {
    background-color: #060101;
    color: #b91c1c;
    border-top: 1px solid #2b0b0b;
}

/* Top Panels Card & Console Card */
QFrame#topPanelCard, QFrame#consoleCard {
    background-color: #0d0303;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
}
QLabel#panelTitle {
    font-size: 8.5pt;
    font-weight: 700;
    letter-spacing: 1px;
    color: #ef4444;
    padding-bottom: 2px;
}
QLabel#panelCounter {
    color: #ef4444;
    font-size: 8.5pt;
}
QLabel#panelFileName {
    font-weight: bold;
    color: #ef4444;
}

/* List & Table Widgets */
QListWidget, QListWidget#frameListWidget, QTableView, QTableWidget {
    background-color: #060101;
    alternate-background-color: #0a0202;
    gridline-color: #1a0505;
    color: #fca5a5;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
    outline: none;
}
QListWidget::item:selected, QListWidget#frameListWidget::item:selected, QTableView::item:selected, QTableWidget::item:selected {
    background-color: #7f1d1d;
    color: #ffffff;
}
QListWidget::item:hover, QListWidget#frameListWidget::item:hover, QTableView::item:hover, QTableWidget::item:hover {
    background-color: #140404;
}
QHeaderView {
    background-color: #0a0202;
}
QHeaderView::section {
    background-color: #0a0202;
    color: #b91c1c;
    border: 1px solid #2b0b0b;
    padding: 5px;
    font-weight: 600;
}
QTableCornerButton::section, QTableView QTableCornerButton::section {
    background-color: #0a0202;
    border: 1px solid #2b0b0b;
}

/* Plain text / Console */
QPlainTextEdit, QTextEdit {
    background-color: #040101;
    color: #ef4444;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 9pt;
    selection-background-color: #7f1d1d;
    selection-color: #ffffff;
}

/* Input Fields */
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #060101;
    color: #fca5a5;
    border: 1px solid #2b0b0b;
    border-radius: 5px;
    padding: 4px 8px;
    min-height: 22px;
}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border: 1px solid #ef4444;
}

QGroupBox {
    font-weight: 700;
    font-size: 9pt;
    color: #b91c1c;
    border: 1px solid #2b0b0b;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 12px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    padding: 0 4px;
    background-color: #080202;
    color: #ef4444;
}

QMessageBox, QDialog {
    background-color: #080202;
    color: #fca5a5;
}
"""


def get_theme_stylesheet(mode: ThemeMode = ThemeMode.STANDARD_DARK) -> str:
    """Mengembalikan stylesheet QSS yang sesuai dengan mode tema yang aktif."""
    if mode == ThemeMode.NIGHT_VISION_RED:
        return NIGHT_VISION_RED_STYLESHEET
    return APP_STYLESHEET
