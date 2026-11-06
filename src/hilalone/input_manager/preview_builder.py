"""Pembuat pratinjau layar (display preview) 8-bit dari array NumPy ilmiah.

Modul ini dipakai bersama oleh adapter pembaca ilmiah (TIFF dan FITS) agar
logika pembuatan ``QImage`` 8-bit tidak diduplikasi.

Aturan utama:
  * Array ``scientific_data`` sumber TIDAK PERNAH diubah di tempat (in-place).
  * Konversi ke 8-bit hanya dilakukan pada salinan baru untuk tampilan layar.
  * Citra monokrom tetap monokrom (``Format_Grayscale8``), dan citra warna
    tetap warna (``Format_RGB888`` / ``Format_RGBA8888``).
"""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

PREVIEW_BIT_DEPTH = 8


def scale_to_uint8_for_preview(data: np.ndarray) -> np.ndarray:
    """Membuat salinan ``uint8`` HANYA untuk tampilan layar (preview).

    Data ilmiah asli TIDAK diubah sama sekali.
    - ``uint8``  : disalin langsung.
    - ``uint16`` : digeser 8 bit (dibagi 256) memetakan 0..65535 -> 0..255 secara jujur.
    - ``uint32`` : digeser 24 bit memetakan rentang penuh uint32 -> 0..255.
    - ``uint64`` : digeser 56 bit memetakan rentang penuh uint64 -> 0..255.
    - Bilangan bertanda (``int8``, ``int16``, ``int32``) atau floating-point
      (``float16``, ``float32``, ``float64``): dipetakan secara linear ke 0..255
      pada salinan baru agar citra dapat terlihat pada Image Viewer.
    """
    dtype = data.dtype
    if dtype == np.uint8:
        return np.ascontiguousarray(data.copy())
    if dtype == np.uint16:
        return np.ascontiguousarray((data >> 8).astype(np.uint8))
    if dtype == np.uint32:
        return np.ascontiguousarray((data >> 24).astype(np.uint8))
    if dtype == np.uint64:
        return np.ascontiguousarray((data >> 56).astype(np.uint8))

    work = np.asarray(data, dtype=np.float64)
    finite_mask = np.isfinite(work)
    if not np.any(finite_mask):
        return np.zeros(data.shape, dtype=np.uint8)

    vmin = float(np.min(work[finite_mask]))
    vmax = float(np.max(work[finite_mask]))

    if np.issubdtype(dtype, np.floating) and vmin >= 0.0 and vmax <= 1.0:
        scaled = np.clip(work * 255.0, 0.0, 255.0)
    elif vmax > vmin:
        scaled = (work - vmin) / (vmax - vmin) * 255.0
        scaled = np.clip(scaled, 0.0, 255.0)
    else:
        scaled = np.zeros_like(work)

    scaled = np.where(finite_mask, scaled, 0.0)
    return np.ascontiguousarray(scaled.astype(np.uint8))


def array_to_preview_qimage(data: np.ndarray) -> QImage:
    """Mengonversi array citra ``(H, W)`` atau ``(H, W, C)`` menjadi ``QImage`` 8-bit terpisah."""
    preview_u8 = scale_to_uint8_for_preview(data)
    if preview_u8.ndim == 2:
        h, w = preview_u8.shape
        bytes_per_line = w
        qimg = QImage(preview_u8.data, w, h, bytes_per_line, QImage.Format.Format_Grayscale8)
        return qimg.copy()

    h, w, c = preview_u8.shape
    if c == 3:
        bytes_per_line = w * 3
        qimg = QImage(preview_u8.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
        return qimg.copy()
    if c == 4:
        bytes_per_line = w * 4
        qimg = QImage(preview_u8.data, w, h, bytes_per_line, QImage.Format.Format_RGBA8888)
        return qimg.copy()

    raise ValueError(f"Jumlah kanal tidak didukung untuk preview layar: {c}")
