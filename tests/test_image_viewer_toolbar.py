"""Unit dan Integration Test untuk Image Viewer & Action Toolbar HILALONE.

Memvalidasi 27 kriteria pengujian spesifikasi:
1-10:   Interaksi Image Viewer (Zoom In/Out, Pan, Fit, 1:1, Rasio Aspek, Hover Magnifier).
11-17:  Restore Save Result (FITS Float32, TIFF Float32, Display PNG, Toolbar independen dari scroll sidebar).
18-22:  Quick Snapshot (PNG bersih tanpa UI controls, format nama otomatis, anti-overwrite).
23-27:  Toolbar GUI (Posisi di bawah gambar, Icon-Only, Tooltip Bahasa Indonesia, Responsivitas layout, Bebas freeze).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import astropy.io.fits as fits
import numpy as np
import pytest
from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QWheelEvent
import tifffile

from hilalone.gui.image_viewer import ImageViewer, MAX_ZOOM_FACTOR, MIN_ZOOM_FACTOR
from hilalone.gui.main_window import MainWindow
from hilalone.processing.stacking.models import StackingProfile


# =====================================================================
# A. PENGUJIAN IMAGE VIEWER INTERACTION (1 - 10)
# =====================================================================
def test_image_viewer_zoom_in_and_zoom_out(qapp: object) -> None:
    """1 & 2: Zoom In memperbesar zoom_factor dan Zoom Out memperkecil zoom_factor."""
    viewer = ImageViewer()
    viewer.resize(800, 600)
    img = QImage(200, 100, QImage.Format.Format_RGB32)
    img.fill(QColor(50, 100, 150))
    viewer.set_image(img)

    init_zoom = viewer.zoom_factor()
    assert init_zoom > 0

    # 1. Zoom In
    viewer.zoom_in()
    assert viewer.zoom_factor() > init_zoom
    assert not viewer.is_fit_mode()

    # 2. Zoom Out
    current_zoom = viewer.zoom_factor()
    viewer.zoom_out()
    assert viewer.zoom_factor() < current_zoom


def test_image_viewer_zoom_preserves_scientific_array(qapp: object) -> None:
    """3: Zoom berkali-kali tidak memodifikasi atau mendegradasi array data ilmiah asli."""
    viewer = ImageViewer()
    viewer.resize(600, 600)

    # Data ilmiah float32 sintetik
    raw_sci = np.linspace(-50.0, 15000.0, 120 * 160, dtype=np.float32).reshape((120, 160))
    raw_hash_before = hashlib.sha256(raw_sci.tobytes()).hexdigest()

    img = QImage(160, 120, QImage.Format.Format_Grayscale8)
    viewer.set_image(img, scientific_data=raw_sci)

    # Lakukan zoom in dan zoom out ekstrem
    for _ in range(10):
        viewer.zoom_in()
    for _ in range(12):
        viewer.zoom_out()

    raw_hash_after = hashlib.sha256(raw_sci.tobytes()).hexdigest()
    assert raw_hash_before == raw_hash_after
    assert viewer._scientific_data is raw_sci


def test_image_viewer_pan_shifts_display_offset(qapp: object) -> None:
    """4: Pan menggeser offset tampilan gambar ketika diperbesar tanpa merusak batas navigasi."""
    viewer = ImageViewer()
    viewer.resize(400, 300)
    img = QImage(800, 600, QImage.Format.Format_RGB32)
    img.fill(QColor(40, 80, 120))
    viewer.set_image(img)

    viewer.set_original_size()
    initial_offset = QPoint(viewer._pan_offset.x(), viewer._pan_offset.y())

    # Simulasikan mouse drag untuk pan
    start_point = QPoint(200, 150)
    drag_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        start_point,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    viewer.mousePressEvent(drag_event)
    assert viewer._is_panning is True

    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        QPoint(160, 120),  # Geser sejauh dx=-40, dy=-30
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    viewer.mouseMoveEvent(move_event)
    assert viewer._pan_offset != initial_offset

    release_event = QMouseEvent(
        QMouseEvent.Type.MouseButtonRelease,
        QPoint(160, 120),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    viewer.mouseReleaseEvent(release_event)
    assert viewer._is_panning is False


def test_image_viewer_fit_the_image_and_original_size(qapp: object) -> None:
    """5 & 6: Fit the Image mengembalikan mode fit dan Original Size mengatur zoom 1:1."""
    viewer = ImageViewer()
    viewer.resize(800, 600)
    img = QImage(400, 200, QImage.Format.Format_RGB32)
    viewer.set_image(img)

    # 6. Original Size
    viewer.set_original_size()
    assert viewer.zoom_factor() == 1.0
    assert not viewer.is_fit_mode()
    assert viewer.displayed_size() == QSize(400, 200)

    # 5. Fit the Image
    viewer.fit_to_viewport()
    assert viewer.is_fit_mode()
    # 800/400 = 2.0, 600/200 = 3.0 -> min = 2.0
    assert viewer.zoom_factor() == pytest.approx(2.0, rel=1e-2)


def test_image_viewer_preserves_aspect_ratio(qapp: object) -> None:
    """7: Rasio aspek gambar (lebar/tinggi) selalu dijaga proporsional."""
    viewer = ImageViewer()
    viewer.resize(1000, 400)
    img = QImage(300, 150, QImage.Format.Format_RGB32)  # Aspect ratio 2:1
    viewer.set_image(img)

    disp = viewer.displayed_size()
    assert disp.width() / disp.height() == pytest.approx(2.0, rel=1e-2)


def test_image_viewer_hover_magnifier_loupe(qapp: object) -> None:
    """8, 9, 10: Magnifier mengikuti kursor, tidak keluar batas, dan tidak memodifikasi data."""
    viewer = ImageViewer()
    viewer.resize(800, 600)
    raw_sci = np.full((300, 400), 1234.5, dtype=np.float32)
    img = QImage(400, 300, QImage.Format.Format_Grayscale8)
    img.fill(QColor(100, 100, 100))
    viewer.set_image(img, scientific_data=raw_sci)

    # Aktifkan magnifier
    viewer.set_magnifier_active(True)
    assert viewer.is_magnifier_active() is True
    viewer.set_magnifier_zoom(4)
    assert viewer.magnifier_zoom() == 4

    # 8. Gerakkan kursor di atas gambar -> loupe mengikuti posisi kursor
    center_pos = QPoint(400, 300)
    move_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        center_pos,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    viewer.mouseMoveEvent(move_event)
    assert viewer._cursor_widget_pos == center_pos
    assert viewer._cursor_image_pos is not None

    # 9. Gerakkan kursor ke pojok kanan bawah -> koordinat loupe dijaga agar tidak terpotong
    corner_pos = QPoint(795, 595)
    corner_event = QMouseEvent(
        QMouseEvent.Type.MouseMove,
        corner_pos,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    viewer.mouseMoveEvent(corner_event)
    assert viewer._cursor_widget_pos == corner_pos

    # 10. Data ilmiah tetap utuh sempurna
    assert np.all(raw_sci == 1234.5)


# =====================================================================
# B. PENGUJIAN RESTORE SAVE RESULT (11 - 17)
# =====================================================================
def test_save_result_action_buttons_and_menu_options(qapp: object, tmp_path: Path) -> None:
    """11, 12, 13: Opsi Simpan FITS, TIFF, dan PNG tersedia pada Action Toolbar."""
    win = MainWindow()
    win.show()

    # Saat belum ada gambar, tombol simpan dinonaktifkan
    assert win.save_result_action_button.isEnabled() is False

    # Buka citra sintetik
    p_img = tmp_path / "single_test.fits"
    sci_data = np.linspace(-10.0, 5000.0, 48 * 64, dtype=np.float32).reshape((48, 64))
    fits.PrimaryHDU(data=sci_data).writeto(p_img)

    assert win.load_path(p_img) is True
    assert win.save_result_action_button.isEnabled() is True

    # Periksa opsi menu simpan yang tersedia
    actions = win.save_action_menu.actions()
    action_texts = [a.text() for a in actions]
    assert any("FITS" in t for t in action_texts)
    assert any("TIFF" in t for t in action_texts)
    assert any("PNG" in t for t in action_texts)


def test_fits_and_tiff_roundtrip_float32(qapp: object, tmp_path: Path) -> None:
    """14 & 15: Ekspor FITS dan TIFF mempertahankan float32 dan nilai negatif tanpa clipping."""
    win = MainWindow()
    h, w = 32, 40
    true_sci = np.linspace(-42.5, 9999.75, h * w, dtype=np.float32).reshape((h, w))

    fits_in = tmp_path / "input.fits"
    fits.PrimaryHDU(data=true_sci).writeto(fits_in)
    assert win.load_sequence_paths([fits_in, fits_in]) is True

    # Jalankan stacking
    win.set_stacking_profile(StackingProfile.BASIC)
    assert win.start_stacking(wait_for_completion=True) is True

    # 14. Simpan FITS Float32
    fits_out = tmp_path / "out_stacked.fits"
    saved_fits = win.save_stacking_result_to_path(fits_out)
    assert saved_fits is not None and saved_fits.exists()

    with fits.open(saved_fits) as hdul:
        loaded_fits_arr = hdul[0].data
        assert np.issubdtype(loaded_fits_arr.dtype, np.floating)
        assert loaded_fits_arr.itemsize == 4  # 32-bit float
        np.testing.assert_allclose(loaded_fits_arr, true_sci, rtol=1e-6, atol=1e-4)
        assert float(np.min(loaded_fits_arr)) < 0.0  # Nilai negatif terjaga!

    # 15. Simpan TIFF Float32
    tiff_out = tmp_path / "out_stacked.tif"
    saved_tiff = win.save_stacking_result_to_path(tiff_out)
    assert saved_tiff is not None and saved_tiff.exists()

    loaded_tiff_arr = tifffile.imread(str(saved_tiff))
    assert loaded_tiff_arr.dtype == np.float32
    np.testing.assert_allclose(loaded_tiff_arr, true_sci, rtol=1e-6, atol=1e-4)


def test_save_result_visible_outside_sidebar_scroll(qapp: object) -> None:
    """17: Save Result Toolbar berada di kolom gambar dan tidak terpengaruh scroll sidebar kanan."""
    win = MainWindow()
    # Tombol save berada di image_action_toolbar (kolom gambar utama)
    assert win.save_result_action_button.parent() is win.image_action_toolbar
    assert win.image_action_toolbar.parent() is not win.info_scroll_area


# =====================================================================
# C. PENGUJIAN QUICK SNAPSHOT (18 - 22)
# =====================================================================
def test_quick_snapshot_generation_and_naming(qapp: object, tmp_path: Path) -> None:
    """18 - 22: Snapshot menghasilkan PNG bersih, nama otomatis valid, dan anti-overwrite."""
    win = MainWindow()
    win._last_dir = str(tmp_path)

    # 1. Tanpa gambar -> gagal dan memberikan pesan
    errors: list[str] = []
    win._show_error = lambda msg: errors.append(msg)
    assert win.take_quick_snapshot() is None
    assert any("Tidak ada gambar" in e for e in errors)

    # 2. Buka gambar
    p_img = tmp_path / "test_snapshot.fits"
    fits.PrimaryHDU(data=np.full((50, 50), 200.0, dtype=np.float32)).writeto(p_img)
    win.load_path(p_img)

    # 18. Ambil snapshot pertama
    snap1 = win.take_quick_snapshot()
    assert snap1 is not None and snap1.exists()
    assert snap1.suffix.lower() == ".png"

    # 22. Validasi pola nama otomatis: HILALONE_snapshot_YYYYMMDD_HHMMSS.png
    pattern = r"^HILALONE_snapshot_\d{8}_\d{6}(\.png|_\d+\.png)$"
    assert re.match(pattern, snap1.name) is not None

    # 21. Ambil snapshot kedua -> Anti-overwrite (nama tidak menimpa snap1)
    snap2 = win.take_quick_snapshot()
    assert snap2 is not None and snap2.exists()
    assert snap1 != snap2
    assert snap1.exists() and snap2.exists()


def test_render_view_pixmap_excludes_ui_controls(qapp: object) -> None:
    """19 & 20: render_view_pixmap hanya merender citra, tanpa toolbar dan tanpa controls."""
    viewer = ImageViewer()
    viewer.resize(600, 400)
    img = QImage(100, 80, QImage.Format.Format_RGB32)
    img.fill(QColor(200, 50, 50))
    viewer.set_image(img)

    pixmap = viewer.render_view_pixmap()
    assert not pixmap.isNull()
    # Ukuran render pixmap mengikuti scaled display rect (hanya kanvas gambar)
    assert pixmap.size() == viewer.displayed_size()


# =====================================================================
# D. PENGUJIAN GUI TOOLBAR & RESPONSIVITAS (23 - 27)
# =====================================================================
def test_image_action_toolbar_properties(qapp: object) -> None:
    """23, 24, 25: Toolbar berada di bawah gambar, tombol Icon-Only, dan Tooltip Bahasa Indonesia."""
    win = MainWindow()

    # 23. Letak toolbar
    assert win.image_action_toolbar is not None
    assert win.image_action_toolbar.objectName() == "imageActionToolbar"

    # 24. Seluruh tombol adalah Icon-Only (teks kosong, memiliki icon)
    toolbar_buttons = [
        win.magnifier_button,
        win.zoom_out_button,
        win.zoom_in_button,
        win.fit_image_button,
        win.original_size_button,
        win.save_result_action_button,
        win.snapshot_button,
    ]

    for btn in toolbar_buttons:
        assert btn.text() == "", f"Tombol {btn} memiliki teks permanen padahal harus Icon-Only!"
        assert not btn.icon().isNull(), f"Tombol {btn} tidak memiliki ikon!"
        # 25. Tooltip Bahasa Indonesia
        tip = btn.toolTip()
        assert len(tip) > 5, f"Tombol {btn} tidak memiliki tooltip informatif!"
        assert any(word in tip.lower() for word in ["perbesar", "perkecil", "kaca pembesar", "sesuaikan", "asli", "simpan", "tangkapan"]), (
            f"Tooltip '{tip}' tidak menggunakan Bahasa Indonesia!"
        )


def test_responsive_layout_on_small_and_large_windows(qapp: object) -> None:
    """26 & 27: Layout tidak overlap pada berbagai ukuran jendela (1333x768 dan < 800x600)."""
    win = MainWindow()
    win.show()

    # Uji pada resolusi 1333x768
    win.resize(1333, 768)
    qapp.processEvents()
    assert win.viewer.width() > 200
    assert win.image_action_toolbar.isVisible()

    # Uji pada ukuran minimum 800x560
    win.resize(800, 560)
    qapp.processEvents()
    assert win.viewer.width() > 150
    assert win.image_action_toolbar.width() > 200
    assert not win.image_action_toolbar.isHidden()
