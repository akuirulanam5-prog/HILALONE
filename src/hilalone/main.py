"""Titik masuk aplikasi HILALONE: menyiapkan Qt, diagnostik, dan menampilkan jendela utama."""

import faulthandler
import logging
import os
from pathlib import Path
import sys
import traceback

from PySide6.QtWidgets import QApplication

from hilalone import APP_NAME, __version__
from hilalone.gui.resources import get_user_log_dir


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


def _enable_diagnostic_console() -> None:
    """Membuka console Windows khusus untuk mode diagnostik executable windowed."""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        if sys.stdout is None or sys.stderr is None:
            kernel32 = ctypes.windll.kernel32
            if not kernel32.AttachConsole(-1):
                kernel32.AllocConsole()
            if sys.stdout is None:
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", buffering=1)
            if sys.stderr is None:
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", buffering=1)
    except Exception:
        pass


def _setup_logging_and_crash_hooks(diagnostic_mode: bool = False) -> Path | None:
    """Mengonfigurasi log runtime & crash handler di folder data pengguna Windows."""
    log_dir: Path | None = None
    try:
        log_dir = get_user_log_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        runtime_log = log_dir / "hilalone.log"
        crash_log = log_dir / "crash.log"

        handlers: list[logging.Handler] = [
            logging.FileHandler(runtime_log, mode="a", encoding="utf-8"),
        ]
        if diagnostic_mode or sys.stderr is not None:
            handlers.append(logging.StreamHandler(sys.stderr))

        logging.basicConfig(
            level=logging.DEBUG if diagnostic_mode else logging.INFO,
            format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            handlers=handlers,
            force=True,
        )

        # Tangkap fatal crash level C / PySide jika terjadi saat frozen
        try:
            fh = open(crash_log, "a", encoding="utf-8")
            faulthandler.enable(file=fh, all_threads=False)
        except Exception:
            pass

        def _excepthook(exc_type: type[BaseException], exc_val: BaseException, exc_tb: object) -> None:
            tb_text = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
            logging.critical("Uncaught exception:\n%s", tb_text)
            try:
                with open(crash_log, "a", encoding="utf-8") as cf:
                    cf.write("\n=== HILALONE UNCAUGHT EXCEPTION ===\n")
                    cf.write(tb_text)
            except Exception:
                pass
            if sys.__excepthook__ is not None:
                sys.__excepthook__(exc_type, exc_val, exc_tb)

        sys.excepthook = _excepthook
    except Exception:
        pass
    return log_dir


def main() -> int:
    """Menjalankan aplikasi dan mengembalikan kode keluar (0 = normal)."""
    diagnostic_mode = (
        "--diagnostic" in sys.argv
        or "--console" in sys.argv
        or os.environ.get("HILALONE_DIAGNOSTIC") == "1"
    )
    if diagnostic_mode:
        _enable_diagnostic_console()

    _setup_logging_and_crash_hooks(diagnostic_mode=diagnostic_mode)
    _setup_windows_app_id()
    logging.info("Memulai %s v%s (frozen=%s)", APP_NAME, __version__, hasattr(sys, "_MEIPASS"))

    try:
        from hilalone.gui.main_window import MainWindow
        from hilalone.gui.resources import get_app_icon
        from hilalone.gui.styles import APP_STYLESHEET

        qt_args = [arg for arg in sys.argv if arg not in {"--diagnostic", "--console"}]
        app = QApplication(qt_args)
        app.setApplicationName(APP_NAME)
        app.setApplicationVersion(__version__)
        app.setStyleSheet(APP_STYLESHEET)

        # Pasang ikon resmi pada tingkat QApplication (mempengaruhi dialog dan taskbar)
        app_icon = get_app_icon()
        if not app_icon.isNull():
            app.setWindowIcon(app_icon)

        if "--bundle-verify" in sys.argv:
            idx = sys.argv.index("--bundle-verify")
            target = Path(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else Path.cwd() / "bundle_verify_out"
            from hilalone._bundle_verify import run_bundle_verification

            return run_bundle_verification(target, app)

        window = MainWindow()
        window.show()
        return app.exec()
    except Exception:
        logging.critical("Kesalahan fatal saat menjalankan HILALONE:\n%s", traceback.format_exc())
        if "--bundle-verify" in sys.argv:
            return 1
        raise


if __name__ == "__main__":
    sys.exit(main())
