"""Tema tampilan (QSS) HILALONE: gelap, sederhana, bernuansa perangkat lunak astronomi."""

APP_STYLESHEET = """
QMainWindow, QWidget#central {
    background-color: #0b1220;
}
QWidget {
    color: #e6ecf7;
    font-family: "Segoe UI", sans-serif;
    font-size: 10pt;
}

/* Header */
QLabel#headerTitle {
    font-size: 20pt;
    font-weight: 600;
    letter-spacing: 4px;
    color: #e6ecf7;
}
QLabel#headerSubtitle {
    font-size: 10pt;
    color: #7f8fb0;
}
QFrame#headerLine {
    background-color: #1e2a45;
    max-height: 1px;
    min-height: 1px;
}

/* Tombol */
QPushButton {
    background-color: #4f8cff;
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
}
QPushButton:hover { background-color: #6b9fff; }
QPushButton:pressed { background-color: #3f74d8; }
QPushButton:disabled {
    background-color: #1a243c;
    color: #5b6a8a;
}
QPushButton#secondaryButton {
    background-color: #1a243c;
    color: #c9d4ea;
    border: 1px solid #2a3a5e;
}
QPushButton#secondaryButton:hover { background-color: #22304f; }
QPushButton#secondaryButton:disabled {
    background-color: #111a2e;
    color: #4a5878;
    border: 1px solid #1a243c;
}

/* Pemilih frame (ComboBox) */
QComboBox {
    background-color: #111a2e;
    color: #e6ecf7;
    border: 1px solid #2a3a5e;
    border-radius: 6px;
    padding: 5px 10px;
}
QComboBox:disabled {
    color: #4a5878;
    border: 1px solid #1a243c;
}
QComboBox QAbstractItemView {
    background-color: #111a2e;
    color: #e6ecf7;
    selection-background-color: #22304f;
}

/* Viewer */
QLabel#imageViewer {
    background-color: #05080f;
    border: 1px solid #1e2a45;
    border-radius: 8px;
    color: #5b6a8a;
    font-size: 11pt;
}

/* Panel informasi */
QFrame#infoPanel {
    background-color: #111a2e;
    border: 1px solid #1e2a45;
    border-radius: 8px;
}
QScrollArea#infoScrollArea {
    background-color: transparent;
    border: none;
}
QWidget#infoScrollContent {
    background-color: #111a2e;
}
QFrame#infoSectionCard {
    background-color: #0e1628;
    border: 1px solid #1c2944;
    border-radius: 6px;
}
QLabel#infoTitle {
    font-size: 9.5pt;
    font-weight: 600;
    letter-spacing: 2px;
    color: #93a6cc;
}
QLabel#sectionHeader {
    font-size: 8.5pt;
    font-weight: 600;
    letter-spacing: 1.2px;
    color: #6b9fff;
    padding-bottom: 2px;
}
QLabel#subSectionHeader {
    font-size: 8pt;
    font-weight: 600;
    letter-spacing: 1px;
    color: #93a6cc;
    padding-top: 6px;
    padding-bottom: 2px;
    border-top: 1px solid #1a2640;
}
QPushButton#collapsibleButton {
    background-color: #15223b;
    color: #9ec0ff;
    border: 1px solid #2a3a5e;
    border-radius: 5px;
    padding: 6px 10px;
    text-align: left;
    font-size: 9pt;
    font-weight: 600;
}
QPushButton#collapsibleButton:hover {
    background-color: #1d2e4f;
}
QFrame#fullHeaderBox {
    background-color: #090f1d;
    border: 1px solid #1c2944;
    border-radius: 5px;
}
QLabel#infoKey {
    color: #8a9bbd;
    font-size: 9.5pt;
}
QLabel#infoValue {
    color: #e6ecf7;
    font-size: 9.5pt;
}
QScrollBar:vertical {
    background: #0e1628;
    width: 8px;
    margin: 2px 0 2px 0;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #2a3a5e;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #4f8cff;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Panel Pemrosesan Citra (IMAGE PROCESSING) */
QFrame#processingCard {
    background-color: #0f1b33;
    border: 1px solid #2c4778;
    border-radius: 6px;
}
QPushButton#startStackingButton {
    background-color: #2f7cf6;
    color: #ffffff;
    border: 1px solid #599bff;
    border-radius: 6px;
    padding: 9px 16px;
    font-size: 10pt;
    font-weight: 700;
}
QPushButton#startStackingButton:hover {
    background-color: #468dff;
}
QPushButton#startStackingButton:disabled {
    background-color: #162138;
    color: #526282;
    border: 1px solid #1f2e4d;
}
QPushButton#startAutoProcessButton {
    background-color: #10b981;
    color: #ffffff;
    border: 1px solid #34d399;
    border-radius: 6px;
    padding: 10px 18px;
    font-size: 10.5pt;
    font-weight: 700;
    letter-spacing: 0.5px;
}
QPushButton#startAutoProcessButton:hover {
    background-color: #059669;
}
QPushButton#startAutoProcessButton:disabled {
    background-color: #162624;
    color: #436359;
    border: 1px solid #1d332d;
}
QPushButton#toggleBeforeAfterButton {
    background-color: #243552;
    color: #93c5fd;
    border: 1px solid #3b82f6;
    border-radius: 5px;
    padding: 6px 12px;
    font-size: 9pt;
    font-weight: 600;
}
QPushButton#toggleBeforeAfterButton:hover {
    background-color: #2f456c;
}
QPushButton#toggleBeforeAfterButton:checked {
    background-color: #3b82f6;
    color: #ffffff;
}
QLabel#histogramBox {
    background-color: #090f1d;
    border: 1px solid #1c2944;
    border-radius: 6px;
}
QProgressBar {
    background-color: #09101f;
    color: #e6ecf7;
    border: 1px solid #243659;
    border-radius: 5px;
    text-align: center;
    min-height: 18px;
    font-size: 8.5pt;
}
QProgressBar::chunk {
    background-color: #3b82f6;
    border-radius: 4px;
}
QCheckBox {
    color: #d4e0f5;
    font-size: 9.5pt;
    spacing: 6px;
}

/* Image Action Toolbar (Icon-Only di bawah gambar) */
QFrame#imageActionToolbar {
    background-color: #0b1220;
    border: 1px solid #1c2944;
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
    background-color: #172542;
    border: 1px solid #2e4470;
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

/* Menu Dropdown Popup (Magnifier & Save) */
QMenu {
    background-color: #0b1220;
    color: #e2e8f0;
    border: 1px solid #2a3a5e;
    border-radius: 6px;
    padding: 4px 0px;
}
QMenu::item {
    padding: 6px 20px 6px 14px;
    font-size: 9pt;
}
QMenu::item:selected {
    background-color: #1a2948;
    color: #38bdf8;
}
QMenu::separator {
    height: 1px;
    background-color: #1c2944;
    margin: 4px 8px;
}

/* Tooltip */
QToolTip {
    background-color: #0f172a;
    color: #f8fafc;
    border: 1px solid #38bdf8;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 8.5pt;
}

/* Status bar */
QStatusBar {
    background-color: #0b1220;
    color: #7f8fb0;
    border-top: 1px solid #1e2a45;
}

/* Kotak pesan */
QMessageBox { background-color: #111a2e; }
"""
