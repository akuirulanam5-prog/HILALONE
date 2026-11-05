"""Tes lingkungan: memastikan NumPy dan pytest berfungsi di .venv."""

import numpy as np


def test_numpy_float32_array_basic() -> None:
    """Array 2x2 float32 harus berbentuk (2, 2) dan bernilai rata-rata 2.5."""
    data = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)

    assert data.dtype == np.float32
    assert data.shape == (2, 2)
    assert data.mean() == 2.5
