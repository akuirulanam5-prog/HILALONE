"""Widget penampil gambar HILALONE (hanya tampilan; tidak mengubah data piksel)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import QLabel, QSizePolicy, QWidget

PLACEHOLDER_TEXT = "Klik \"Open Image\" untuk membuka foto hilal"


class ImageViewer(QLabel):
    """Menampilkan gambar agar muat di area viewer (fit-to-window).

    - Rasio aspek dipertahankan dan gambar tidak dipotong.
    - Penskalaan hanya untuk tampilan layar; ``QImage`` sumber tidak diubah.
    - Saat diperkecil memakai penskalaan halus; saat diperbesar memakai
      penskalaan tegas (tanpa interpolasi) agar tidak "mengarang" detail.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("imageViewer")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Ignored: label boleh menyusut lebih kecil dari gambar yang dimuat.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(200, 200)
        self._source: QPixmap | None = None
        self.clear_image()

    def set_image(self, image: QImage) -> None:
        """Menampilkan gambar (salinan preview) pada viewer."""
        self._source = QPixmap.fromImage(image)
        self._refresh()

    def clear_image(self) -> None:
        """Mengosongkan viewer dan kembali ke tampilan awal."""
        self._source = None
        self.setPixmap(QPixmap())
        self.setText(PLACEHOLDER_TEXT)

    def has_image(self) -> bool:
        """True bila ada gambar yang sedang ditampilkan."""
        return self._source is not None

    def displayed_size(self) -> QSize:
        """Ukuran gambar yang sedang tampil di layar (setelah penskalaan)."""
        pixmap = self.pixmap()
        return pixmap.size() if self._source is not None and not pixmap.isNull() else QSize(0, 0)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 (nama bawaan Qt)
        super().resizeEvent(event)
        self._refresh()

    def _refresh(self) -> None:
        """Menskalakan gambar agar muat di area viewer dengan rasio aspek tetap."""
        if self._source is None or self._source.isNull():
            return
        # Ruang yang tersedia dikurangi sedikit agar bingkai tidak menutupi gambar.
        available = self.contentsRect().size()
        if available.width() < 1 or available.height() < 1:
            return
        # Faktor skala > 1 berarti gambar diperbesar (gambar kecil di area besar).
        factor = min(
            available.width() / self._source.width(),
            available.height() / self._source.height(),
        )
        upscaling = factor > 1.0
        mode = Qt.TransformationMode.FastTransformation if upscaling else Qt.TransformationMode.SmoothTransformation
        scaled = self._source.scaled(available, Qt.AspectRatioMode.KeepAspectRatio, mode)
        self.setText("")
        self.setPixmap(scaled)
