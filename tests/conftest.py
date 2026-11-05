"""Pengaturan bersama untuk semua tes HILALONE.

Qt dijalankan dalam mode "offscreen" (tanpa jendela sungguhan) sehingga tes GUI
dapat berjalan otomatis tanpa layar.
"""

import os

# Harus diatur SEBELUM PySide6 dibuat; berlaku untuk seluruh sesi tes.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Satu QApplication untuk seluruh sesi tes (Qt hanya boleh punya satu)."""
    app = QApplication.instance() or QApplication([])
    return app  # type: ignore[return-value]
