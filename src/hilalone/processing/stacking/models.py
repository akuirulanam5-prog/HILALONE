"""Model data, konfigurasi profil, dan struktur laporan Automatic Stacking Engine (Sub-Tahap 3A).

Prinsip utama:
  1. Ketiga profil (``BASIC``, ``MEDIUM``, ``HIGH``) didefinisikan sebagai objek
     konfigurasi ``StackingProfileConfig``, bukan percabangan ``if`` yang tersebar.
  2. Seluruh keputusan kompatibilitas, pengecualian frame, metrik kualitas,
     pergeseran posisi, serta penggunaan master flat dicatat secara transparan
     di dalam ``StackingResult``.
  3. Pesan galat dan peringatan menggunakan Bahasa Indonesia yang jelas dan
     spesifik.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
from PySide6.QtGui import QImage


class StackingError(Exception):
    """Galat selama validasi atau eksekusi stacking; pesan siap tampil dalam Bahasa Indonesia."""


class StackingConfirmationRequiredError(StackingError):
    """Dilempar ketika stacking membutuhkan keputusan eksplisit dari pengguna.

    Contoh:
      * Terdapat frame ``INCOMPATIBLE`` atau ``ERROR`` tetapi pengguna belum
        menyetujui pengecualian frame tersebut.
      * Terdapat pergeseran posisi > ambang (``MELEBIHI_AMBANG``) atau
        ``INDETERMINATE`` tetapi pengguna belum mengonfirmasi lanjut dengan
        risiko blur.
    """


class StackingCancelledError(StackingError):
    """Dilempar ketika proses stacking dibatalkan oleh pengguna melalui cancel_check."""


class StackingProfile(str, Enum):
    """Tiga profil pemrosesan HILALONE untuk tahap stacking."""

    BASIC = "BASIC"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class StackingAlgorithm(str, Enum):
    """Algoritma matematika yang digunakan pada mesin stacking."""

    ARITHMETIC_MEAN = "ARITHMETIC_MEAN"
    SIGMA_CLIPPED_MEAN = "SIGMA_CLIPPED_MEAN"
    QUALITY_WEIGHTED_ROBUST = "QUALITY_WEIGHTED_ROBUST"


class PositionStabilityStatus(str, Enum):
    """Status kestabilan posisi satu frame terhadap frame referensi (FR-CP-06)."""

    OK = "OK"
    MELEBIHI_AMBANG = "MELEBIHI_AMBANG"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class StackingProfileConfig:
    """Konfigurasi deklaratif untuk setiap profil stacking."""

    profile: StackingProfile
    algorithm: StackingAlgorithm
    description_id: str
    use_sigma_clipping: bool
    sigma_low: float
    sigma_high: float
    max_clip_iterations: int
    min_frames_for_clipping: int
    min_kept_fraction: float
    use_quality_weights: bool
    weight_clamp_min: float
    weight_clamp_max: float


# Tabel konfigurasi resmi profil BASIC, MEDIUM, dan HIGH (AGENTS.md Bagian 3 & 8)
STACKING_PROFILE_CONFIGS: dict[StackingProfile, StackingProfileConfig] = {
    StackingProfile.BASIC: StackingProfileConfig(
        profile=StackingProfile.BASIC,
        algorithm=StackingAlgorithm.ARITHMETIC_MEAN,
        description_id="Arithmetic Mean Stacking (rata-rata aritmetika murni)",
        use_sigma_clipping=False,
        sigma_low=0.0,
        sigma_high=0.0,
        max_clip_iterations=0,
        min_frames_for_clipping=2,
        min_kept_fraction=1.0,
        use_quality_weights=False,
        weight_clamp_min=1.0,
        weight_clamp_max=1.0,
    ),
    StackingProfile.MEDIUM: StackingProfileConfig(
        profile=StackingProfile.MEDIUM,
        algorithm=StackingAlgorithm.SIGMA_CLIPPED_MEAN,
        description_id="Iterative Sigma-Clipped Mean berbasis Median & MAD",
        use_sigma_clipping=True,
        sigma_low=3.0,
        sigma_high=3.0,
        max_clip_iterations=2,
        min_frames_for_clipping=5,
        min_kept_fraction=0.5,
        use_quality_weights=False,
        weight_clamp_min=1.0,
        weight_clamp_max=1.0,
    ),
    StackingProfile.HIGH: StackingProfileConfig(
        profile=StackingProfile.HIGH,
        algorithm=StackingAlgorithm.QUALITY_WEIGHTED_ROBUST,
        description_id="Quality-Weighted Robust Stacking (bobot invers varians derau + penolakan outlier MAD)",
        use_sigma_clipping=True,
        sigma_low=3.0,
        sigma_high=3.0,
        max_clip_iterations=2,
        min_frames_for_clipping=5,
        min_kept_fraction=0.5,
        use_quality_weights=True,
        weight_clamp_min=0.25,
        weight_clamp_max=4.0,
    ),
}


def get_stacking_profile_config(profile: StackingProfile | str) -> StackingProfileConfig:
    """Mengambil objek konfigurasi profil stacking berdasarkan enum atau nama string."""
    if isinstance(profile, StackingProfile):
        return STACKING_PROFILE_CONFIGS[profile]
    norm = str(profile).strip().upper()
    try:
        enum_val = StackingProfile(norm)
    except ValueError as exc:
        valid = ", ".join(p.value for p in StackingProfile)
        raise StackingError(
            f"Profil stacking '{profile}' tidak dikenal. Pilihan yang valid: {valid}."
        ) from exc
    return STACKING_PROFILE_CONFIGS[enum_val]


@dataclass(frozen=True)
class ExcludedFrameRecord:
    """Catatan eksplisit untuk setiap frame yang tidak diikutkan dalam stacking."""

    frame_index: int
    file_name: str
    reason: str


@dataclass(frozen=True)
class FrameShiftMeasurement:
    """Hasil pengukuran pergeseran translasi satu frame terhadap frame referensi (baca-saja)."""

    frame_index: int
    file_name: str
    dx_px: float | None
    dy_px: float | None
    shift_magnitude_px: float | None
    confidence_psr: float
    status: PositionStabilityStatus
    note: str


@dataclass(frozen=True)
class PositionStabilityReport:
    """Laporan lengkap pemeriksaan kestabilan posisi seluruh frame sebelum stacking."""

    reference_frame_index: int
    threshold_px: float
    measurements: tuple[FrameShiftMeasurement, ...]
    max_shift_px: float | None
    mean_shift_px: float | None
    ok_count: int
    exceeded_count: int
    indeterminate_count: int
    has_warnings: bool
    warnings: tuple[str, ...]

    @property
    def is_fully_stable(self) -> bool:
        """True hanya jika seluruh frame terukur OK (<= ambang) dan tidak ada INDETERMINATE."""
        return self.exceeded_count == 0 and self.indeterminate_count == 0


@dataclass(frozen=True)
class FrameQualityMetrics:
    """Metrik kualitas satu frame (hanya untuk pembobotan pada profil HIGH, bukan alignment)."""

    frame_index: int
    file_name: str
    background_median: float
    robust_noise_sigma: float
    gradient_energy: float
    raw_weight: float
    normalized_weight: float


@dataclass(frozen=True)
class PreStackValidationReport:
    """Hasil pemeriksaan menyeluruh pra-stacking (struktural, CFA, metadata, dan posisi)."""

    is_valid_to_proceed: bool
    requires_user_confirmation: bool
    reference_frame_index: int | None
    included_frame_indices: tuple[int, ...]
    excluded_frames: tuple[ExcludedFrameRecord, ...]
    width: int
    height: int
    channels: int
    is_cfa_mosaic: bool
    cfa_pattern_str: str | None
    mixed_bit_depth: bool
    normalize_integers_to_unit: bool
    metadata_warnings: tuple[str, ...]
    structural_warnings: tuple[str, ...]
    stability_report: PositionStabilityReport | None


@dataclass(frozen=True)
class FlatCalibrationReport:
    """Laporan validasi dan penerapan Master Flat opsional."""

    applied: bool
    source_description: str
    width: int
    height: int
    channels: int
    is_cfa_mosaic: bool
    cfa_pattern_str: str | None
    flat_mean_before_norm: float
    protected_zero_pixels_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class StackingResult:
    """Hasil akhir Automatic Stacking Engine beserta seluruh rekaman ilmiahnya."""

    stacked_scientific_data: np.ndarray  # Selalu float32 linear baru
    preview: QImage                      # Salinan 8-bit terpisah untuk tampilan layar
    rejection_map: np.ndarray            # (H, W) uint16: jumlah frame ditolak pada tiap piksel
    effective_frame_count_map: np.ndarray  # (H, W) uint16: jumlah frame efektif pada tiap piksel
    profile_config: StackingProfileConfig
    effective_algorithm: StackingAlgorithm
    total_input_frames: int
    stacked_frame_count: int
    included_frame_indices: tuple[int, ...]
    included_file_names: tuple[str, ...]
    excluded_frames: tuple[ExcludedFrameRecord, ...]
    frame_quality_metrics: tuple[FrameQualityMetrics, ...]
    validation_report: PreStackValidationReport
    flat_report: FlatCalibrationReport | None
    strip_count_used: int
    working_memory_limit_mb: int
    warnings: tuple[str, ...]
    notes: tuple[str, ...]

    @property
    def total_rejected_pixel_samples(self) -> int:
        """Jumlah total sampel piksel yang ditolak oleh outlier rejection di seluruh citra."""
        return int(np.sum(self.rejection_map, dtype=np.int64))
