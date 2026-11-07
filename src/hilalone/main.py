"""Titik masuk aplikasi HILALONE: menyiapkan Qt dan menampilkan jendela utama."""

import sys

from PySide6.QtWidgets import QApplication

from hilalone import APP_NAME, __version__
from hilalone.gui.main_window import MainWindow
from hilalone.gui.resources import get_app_icon
from hilalone.gui.styles import APP_STYLESHEET


def _setup_windows_app_id() -> None:
    """Mengatur Application User Model ID khusus Windows.

    Langkah ini memastikan Windows menampilkan ikon aplikasi resmi pada taskbar
    dan Alt+Tab, alih-alih mengelompokkannya di bawah ikon Python generic.
    """
    if sys.platform == "win32":
        try:
            import ctypes

            app_id = "hilalone.hilalone.desktop.1.0"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            # Lewati tanpa menghentikan startup bila OS tidak mendukung
            pass


def main() -> int:
    """Menjalankan aplikasi dan mengembalikan kode keluar (0 = normal)."""
    _setup_windows_app_id()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyleSheet(APP_STYLESHEET)

    # Pasang ikon resmi pada tingkat QApplication (mempengaruhi dialog dan taskbar)
    app_icon = get_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
