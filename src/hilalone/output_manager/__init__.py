"""Paket Output Manager HILALONE.

Mengelola penyimpanan hasil pemrosesan citra ilmiah (linear float32) dan
pratinjau visual secara aman tanpa pernah menimpa berkas sumber.
"""

from __future__ import annotations

from hilalone.output_manager.pipeline_writer import save_pipeline_result
from hilalone.output_manager.stacking_writer import (
    OutputWriteError,
    save_stacking_result,
)

__all__ = [
    "OutputWriteError",
    "save_pipeline_result",
    "save_stacking_result",
]
