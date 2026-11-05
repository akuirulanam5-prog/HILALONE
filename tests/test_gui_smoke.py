"""Tes asap (smoke test) jendela utama HILALONE dalam mode offscreen."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtGui import QImage

from hilalone import APP_NAME, APP_SUBTITLE
from hilalone.gui.main_window import EMPTY_VALUE, STATUS_EMPTY, MainWindow


@pytest.fixture
def window(qapp):  # noqa: ANN001
    win = MainWindow()
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def _make_png(path: Path, width: int, height: int, fmt=QImage.Format.Format_RGB32) -> Path:
    image = QImage(width, height, fmt)
    image.fill(0)
    assert image.save(str(path))
    return path


def _info_texts(win: MainWindow) -> dict[str, str]:
    return {key: label.text() for key, label in win._info_values.items()}


def test_window_basic_properties(window: MainWindow) -> None:
    assert APP_NAME in window.windowTitle()
    assert window.title_label.text() == "HILALONE"
    assert window.subtitle_label.text() == "Automated Hilal Image Processing" == APP_SUBTITLE
    assert (window.width(), window.height()) == (1200, 800)


def test_initial_state_is_empty(window: MainWindow) -> None:
    assert not window.viewer.has_image()
    assert window.close_button.isEnabled() is False
    assert window.open_button.isEnabled() is True
    assert window.statusBar().currentMessage() == STATUS_EMPTY
    assert all(text == EMPTY_VALUE for text in _info_texts(window).values())


def test_open_valid_image_shows_viewer_and_info(window: MainWindow, tmp_path: Path) -> None:
    path = _make_png(tmp_path / "hilal.png", 300, 200)
    assert window.load_path(path) is True

    assert window.viewer.has_image()
    assert window.close_button.isEnabled() is True
    info = _info_texts(window)
    assert info["file_name"] == "hilal.png"
    assert info["file_format"] == "PNG"
    assert info["width"] == "300 px"
    assert info["height"] == "200 px"
    assert info["channels"].startswith("3")
    assert info["bit_depth"] == "Original: 8-bit | Display Preview: 8-bit"


def test_16bit_info_text_is_honest(window: MainWindow, tmp_path: Path) -> None:
    path = _make_png(tmp_path / "g16.png", 40, 30, QImage.Format.Format_Grayscale16)
    assert window.load_path(path) is True
    assert _info_texts(window)["bit_depth"] == "Original: 16-bit | Display Preview: 8-bit"
    assert _info_texts(window)["channels"].startswith("1")


def test_viewer_keeps_aspect_ratio_and_fits(window: MainWindow, tmp_path: Path) -> None:
    window.load_path(_make_png(tmp_path / "wide.png", 2000, 500))  # rasio 4:1, lebih besar dari viewer
    size = window.viewer.displayed_size()
    area = window.viewer.contentsRect().size()

    assert size.width() <= area.width() and size.height() <= area.height()  # tidak terpotong
    assert size.width() / size.height() == pytest.approx(4.0, rel=0.02)  # rasio terjaga

    window.resize(900, 700)  # ubah ukuran jendela: gambar menyesuaikan lagi
    size2 = window.viewer.displayed_size()
    assert size2.width() / size2.height() == pytest.approx(4.0, rel=0.02)


def test_invalid_file_shows_indonesian_error_and_keeps_state(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    messages: list[str] = []
    monkeypatch.setattr(window, "_show_error", messages.append)

    # Tanpa gambar terbuka: galat, viewer tetap kosong.
    bad = tmp_path / "rusak.png"
    bad.write_bytes(b"\x89PNG\r\n\x1a\nxxxx")
    assert window.load_path(bad) is False
    assert len(messages) == 1 and "rusak" in messages[0].lower()
    assert not window.viewer.has_image()

    # Dengan gambar terbuka: gambar lama dipertahankan saat berkas baru gagal.
    window.load_path(_make_png(tmp_path / "ok.png", 50, 50))
    assert window.load_path(tmp_path / "tidak_ada.png") is False
    assert "File tidak ditemukan" in messages[-1]
    assert window.viewer.has_image()
    assert _info_texts(window)["file_name"] == "ok.png"


def test_close_image_resets_to_initial_state(window: MainWindow, tmp_path: Path) -> None:
    path = _make_png(tmp_path / "x.png", 60, 40)
    window.load_path(path)
    window.close_image()

    assert not window.viewer.has_image()
    assert window.close_button.isEnabled() is False
    assert window.statusBar().currentMessage() == STATUS_EMPTY
    assert all(text == EMPTY_VALUE for text in _info_texts(window).values())
    assert path.exists()  # berkas di disk tidak disentuh


def test_file_dialog_filter_lists_only_supported_formats(window: MainWindow) -> None:
    text = window._file_dialog_filter()
    assert "*.png" in text and "*.jpg" in text and "*.bmp" in text
    assert "Semua file" in text
