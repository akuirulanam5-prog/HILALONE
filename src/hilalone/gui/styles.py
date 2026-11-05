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
QLabel#infoTitle {
    font-size: 9pt;
    font-weight: 600;
    letter-spacing: 2px;
    color: #7f8fb0;
}
QLabel#infoKey { color: #7f8fb0; }
QLabel#infoValue { color: #e6ecf7; }

/* Status bar */
QStatusBar {
    background-color: #0b1220;
    color: #7f8fb0;
    border-top: 1px solid #1e2a45;
}

/* Kotak pesan */
QMessageBox { background-color: #111a2e; }
"""
