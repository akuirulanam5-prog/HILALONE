"""Titik masuk aplikasi HILALONE: menyiapkan Qt dan menampilkan jendela utama."""

import sys

from PySide6.QtWidgets import QApplication

from hilalone import APP_NAME, __version__
from hilalone.gui.main_window import MainWindow
from hilalone.gui.styles import APP_STYLESHEET


def main() -> int:
    """Menjalankan aplikasi dan mengembalikan kode keluar (0 = normal)."""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
