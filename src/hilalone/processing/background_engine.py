"""Engine 1 — Background Extraction HILALONE.

Memodelkan dan mengoreksi gradien background langit senja secara subtractive:
    I_corrected(x, y) = I_linear(x, y) - B_model(x, y)

Prinsip Ilmiah & Keselamatan Data (AGENTS.md Bagian 5 & 7):
  1. Koreksi gradien aditif langit WAJIB menggunakan pengurangan (subtraction),
     BUKAN pembagian (division adalah untuk kalibrasi flat-field).
  2. Data sumber (``I_linear``) tidak pernah diubah secara in-place; hasil
     dikembalikan sebagai array ``float32`` baru (nilai negatif dipertahankan).
  3. Mendukung tiga profil:
       * BASIC  : Polinomial derajat 1, sampling grid dengan median robust.
       * MEDIUM : Polinomial derajat 2 atau Thin Plate Spline (TPS) RBF dengan
                  penolakan outlier berbasis MAD dan regularisasi.
       * HIGH   : Estimasi mesh otomatis + iterasi penolakan outlier MAD +
                  Regularized Thin Plate Spline RBF adaptif.
  4. Wilayah Proteksi Manual (Protected Region ROI — Rectangle/Polygon)
     dikecualikan dari pemilihan sampel background tanpa mengklaim deteksi
     hilal otomatis.
  5. Untuk citra Bayer CFA 2D (RAW/SER), setiap sub-kanal Bayer 2×2 dimodelkan
     secara terpisah tanpa demosaicing. Pola CFA non-Bayer (seperti X-Trans
     atau pola tidak dikenal) ditolak secara jujur dengan pesan Bahasa Indonesia.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from scipy.interpolate import RBFInterpolator
from scipy.ndimage import zoom

from hilalone.input_manager.preview_builder import array_to_preview_qimage
from hilalone.processing.processing_models import (
    BackgroundExtractionConfig,
    BackgroundExtractionResult,
    BackgroundModelMethod,
    BackgroundResidualStats,
    BackgroundSamplePoint,
    ProcessingCancelledError,
    ProcessingError,
    ProcessingProfile,
)
from hilalone.processing.profile_manager import get_unified_profile_config

SUPPORTED_BAYER_2X2_PATTERNS: frozenset[str] = frozenset(
    {
        "RGGB",
        "BGGR",
        "GRBG",
        "GBRG",
        "RGBE",
        "CYGM",
        "CYYM",
        "YCMY",
        "YMCY",
        "BAYER_RGGB",
        "BAYER_BGGR",
        "BAYER_GRBG",
        "BAYER_GBRG",
        "BAYER_CYYM",
        "BAYER_YCMY",
        "BAYER_YMCY",
    }
)


def _check_cancel(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check is not None and cancel_check():
        raise ProcessingCancelledError("Background Extraction dibatalkan oleh pengguna.")


def _robust_median_and_mad(values: np.ndarray) -> tuple[float, float]:
    """Menghitung median dan MAD yang diskalakan (1.4826 * MAD) pada array 1D."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0, 0.0
    med = float(np.median(finite))
    mad = float(np.median(np.abs(finite - med))) * 1.4826
    return med, mad


def build_combined_protected_mask(
    height: int,
    width: int,
    config: BackgroundExtractionConfig,
) -> np.ndarray:
    """Menggabungkan seluruh ``ProtectedRegionROI`` dan ``protected_mask`` menjadi mask 2D bool."""
    combined = np.zeros((height, width), dtype=bool)
    if config.protected_mask is not None:
        pm = np.asarray(config.protected_mask, dtype=bool)
        if pm.shape == (height, width):
            combined |= pm
        else:
            raise ProcessingError(
                f"Ukuran protected_mask ({pm.shape}) tidak sesuai dengan dimensi citra ({height}, {width})."
            )
    for roi in config.protected_regions:
        combined |= roi.build_mask(height, width)
    return combined


def _compute_2d_luminance_proxy(image: np.ndarray) -> np.ndarray:
    """Menghasilkan representasi 2D float64 untuk keperluan penentuan posisi sampel & outlier."""
    if image.ndim == 2:
        return np.asarray(image, dtype=np.float64)
    if image.ndim == 3 and image.shape[2] >= 3:
        r = np.asarray(image[:, :, 0], dtype=np.float64)
        g = np.asarray(image[:, :, 1], dtype=np.float64)
        b = np.asarray(image[:, :, 2], dtype=np.float64)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    return np.asarray(image[:, :, 0], dtype=np.float64)


def _fit_polynomial_coeffs(
    xs: np.ndarray,
    ys: np.ndarray,
    zs: np.ndarray,
    weights: np.ndarray,
    height: int,
    width: int,
    degree: int,
    ridge_lambda: float = 1e-3,
) -> np.ndarray:
    """Menghitung koefisien polinomial 2D pada koordinat ternormalisasi [-1, 1]."""
    if zs.size == 0:
        return np.zeros(3 if degree <= 1 else 6, dtype=np.float64)

    half_w = max(1.0, (width - 1) * 0.5)
    half_h = max(1.0, (height - 1) * 0.5)
    nx = (xs - half_w) / half_w
    ny = (ys - half_h) / half_h

    if degree <= 1 or zs.size < 6:
        design = np.column_stack([np.ones_like(nx), nx, ny])
        reg_diag = np.array([0.0, 1e-6, 1e-6], dtype=np.float64)
    else:
        design = np.column_stack(
            [
                np.ones_like(nx),
                nx,
                ny,
                nx * nx,
                nx * ny,
                ny * ny,
            ]
        )
        reg_diag = np.array(
            [0.0, 1e-5, 1e-5, ridge_lambda, ridge_lambda, ridge_lambda],
            dtype=np.float64,
        )

    w_sqrt = np.sqrt(np.clip(weights, 1e-6, None))
    a_mat = design * w_sqrt[:, None]
    b_vec = zs * w_sqrt

    ata = a_mat.T @ a_mat + np.diag(reg_diag * float(max(1, zs.size)))
    atb = a_mat.T @ b_vec
    try:
        coeffs = np.linalg.solve(ata, atb)
    except np.linalg.LinAlgError:
        coeffs, *_ = np.linalg.lstsq(a_mat, b_vec, rcond=None)
    return coeffs


def _evaluate_polynomial_at_coords(
    xs: np.ndarray,
    ys: np.ndarray,
    coeffs: np.ndarray,
    height: int,
    width: int,
) -> np.ndarray:
    """Evaluasi cepat nilai polinomial pada koordinat sampel tertentu (O(N) tanpa alokasi grid)."""
    if xs.size == 0 or coeffs.size == 0:
        return np.empty(0, dtype=np.float64)
    half_w = max(1.0, (width - 1) * 0.5)
    half_h = max(1.0, (height - 1) * 0.5)
    nx = (xs - half_w) / half_w
    ny = (ys - half_h) / half_h
    val = coeffs[0] + coeffs[1] * nx + coeffs[2] * ny
    if coeffs.size >= 6:
        val = (
            val
            + coeffs[3] * (nx * nx)
            + coeffs[4] * (nx * ny)
            + coeffs[5] * (ny * ny)
        )
    return val


def _fit_polynomial_surface(
    xs: np.ndarray,
    ys: np.ndarray,
    zs: np.ndarray,
    weights: np.ndarray,
    height: int,
    width: int,
    degree: int,
    ridge_lambda: float = 1e-3,
) -> np.ndarray:
    """Mencocokkan permukaan polinomial 2D secara vectorized cepat dengan 1D broadcasting."""
    if zs.size == 0:
        return np.zeros((height, width), dtype=np.float32)

    coeffs = _fit_polynomial_coeffs(
        xs, ys, zs, weights, height, width, degree=degree, ridge_lambda=ridge_lambda
    )

    half_w = max(1.0, (width - 1) * 0.5)
    half_h = max(1.0, (height - 1) * 0.5)

    ny_1d = ((np.arange(height, dtype=np.float32) - np.float32(half_h)) / np.float32(half_h))[:, None]
    nx_1d = ((np.arange(width, dtype=np.float32) - np.float32(half_w)) / np.float32(half_w))[None, :]
    c0 = np.float32(coeffs[0])
    c1 = np.float32(coeffs[1])
    c2 = np.float32(coeffs[2])

    if coeffs.size < 6:
        surface = c0 + c1 * nx_1d + c2 * ny_1d
    else:
        c3 = np.float32(coeffs[3])
        c4 = np.float32(coeffs[4])
        c5 = np.float32(coeffs[5])
        surface = (
            (c0 + c1 * nx_1d + c3 * (nx_1d * nx_1d))
            + ny_1d * (c2 + c4 * nx_1d)
            + (c5 * (ny_1d * ny_1d))
        )
    return surface.astype(np.float32)


def _fit_tps_rbf_surface(
    xs: np.ndarray,
    ys: np.ndarray,
    zs: np.ndarray,
    weights: np.ndarray,
    height: int,
    width: int,
    smoothing: float,
) -> np.ndarray:
    """Mencocokkan permukaan Regularized Thin Plate Spline RBF menggunakan SciPy RBFInterpolator."""
    if zs.size < 4:
        return _fit_polynomial_surface(xs, ys, zs, weights, height, width, degree=1)

    half_w = max(1.0, (width - 1) * 0.5)
    half_h = max(1.0, (height - 1) * 0.5)
    nx = (xs - half_w) / half_w
    ny = (ys - half_h) / half_h
    pts = np.column_stack([ny, nx])

    # Jika titik-titik sampel kolinear, mundur dengan aman ke polinomial derajat 1
    if np.linalg.matrix_rank(np.column_stack([np.ones_like(nx), nx, ny])) < 3:
        return _fit_polynomial_surface(xs, ys, zs, weights, height, width, degree=1)

    # Skala regularisasi proporsional terhadap jumlah titik agar tidak overfit
    eff_smooth = max(1e-4, float(smoothing) * 0.05 * float(zs.size))
    try:
        rbf = RBFInterpolator(
            pts,
            zs,
            kernel="thin_plate_spline",
            smoothing=eff_smooth,
            degree=1,
        )
    except Exception:
        return _fit_polynomial_surface(xs, ys, zs, weights, height, width, degree=2)

    # Evaluasi pada grid kontrol (maks 64x64) lalu interpolasi bicubic halus agar hemat memori & cepat
    eval_h = min(height, 64)
    eval_w = min(width, 64)
    cy = np.linspace(-1.0, 1.0, eval_h, dtype=np.float64)
    cx = np.linspace(-1.0, 1.0, eval_w, dtype=np.float64)
    gy, gx = np.meshgrid(cy, cx, indexing="ij")
    query_pts = np.column_stack([gy.ravel(), gx.ravel()])

    try:
        coarse_vals = rbf(query_pts).reshape((eval_h, eval_w))
    except Exception:
        return _fit_polynomial_surface(xs, ys, zs, weights, height, width, degree=2)

    if (eval_h, eval_w) == (height, width):
        return coarse_vals.astype(np.float32)

    try:
        from PIL import Image as _PILImage
        coarse_f32 = coarse_vals.astype(np.float32)
        pil_coarse = _PILImage.fromarray(coarse_f32)
        full_pil = pil_coarse.resize((width, height), resample=_PILImage.Resampling.BICUBIC)
        full_surface = np.array(full_pil, dtype=np.float32)
    except Exception:
        zoom_y = float(height) / float(eval_h)
        zoom_x = float(width) / float(eval_w)
        full_surface = zoom(coarse_vals, (zoom_y, zoom_x), order=3, mode="nearest")
    # Pastikan ukuran tepat (height, width)
    full_surface = full_surface[:height, :width]
    if full_surface.shape != (height, width):
        padded = np.zeros((height, width), dtype=np.float32)
        sh = min(height, full_surface.shape[0])
        sw = min(width, full_surface.shape[1])
        padded[:sh, :sw] = full_surface[:sh, :sw]
        return padded
    return full_surface.astype(np.float32)


def _sample_and_reject_outliers_2d(
    lum_2d: np.ndarray,
    protected_mask: np.ndarray,
    config: BackgroundExtractionConfig,
    *,
    effective_rows: int,
    effective_cols: int,
) -> tuple[list[BackgroundSamplePoint], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Membangun sampel grid otomatis + titik manual serta menolak sampel berobjek terang/outlier."""
    height, width = lum_2d.shape
    row_edges = np.linspace(0, height, effective_rows + 1, dtype=int)
    col_edges = np.linspace(0, width, effective_cols + 1, dtype=int)

    raw_candidates: list[dict[str, object]] = []
    manual_excl = list(config.manual_exclude_points)

    for r_idx in range(effective_rows):
        y0, y1 = int(row_edges[r_idx]), int(row_edges[r_idx + 1])
        if y1 <= y0:
            continue
        for c_idx in range(effective_cols):
            x0, x1 = int(col_edges[c_idx]), int(col_edges[c_idx + 1])
            if x1 <= x0:
                continue

            cx = 0.5 * (x0 + x1 - 1)
            cy = 0.5 * (y0 + y1 - 1)

            # Periksa apakah sel ini dihapus manual oleh pengguna
            manually_excluded = False
            for mx, my in manual_excl:
                if x0 <= mx < x1 and y0 <= my < y1:
                    manually_excluded = True
                    break

            cell_data = lum_2d[y0:y1, x0:x1]
            cell_prot = protected_mask[y0:y1, x0:x1]

            # Subsampling cepat jika ukuran sel melebihi 1600 piksel agar real-time dan hemat RAM
            c_h, c_w = cell_data.shape
            if c_h * c_w > 1600:
                sy = max(1, c_h // 40)
                sx = max(1, c_w // 40)
                cell_s = cell_data[::sy, ::sx]
                prot_s = cell_prot[::sy, ::sx]
            else:
                cell_s = cell_data
                prot_s = cell_prot

            valid_mask = np.isfinite(cell_s) & (~prot_s)
            total_px = max(1, cell_s.size)
            valid_px = int(np.count_nonzero(valid_mask))

            if manually_excluded:
                val = float(np.nanmedian(cell_s)) if np.any(np.isfinite(cell_s)) else 0.0
                raw_candidates.append(
                    {
                        "x": cx,
                        "y": cy,
                        "y0": y0,
                        "y1": y1,
                        "x0": x0,
                        "x1": x1,
                        "val": val,
                        "mad": 0.0,
                        "accepted": False,
                        "is_manual": False,
                        "reason": "Dihapus secara manual oleh pengguna",
                    }
                )
                continue

            if valid_px < max(4, int(0.20 * total_px)):
                val = float(np.nanmedian(cell_s)) if np.any(np.isfinite(cell_s)) else 0.0
                raw_candidates.append(
                    {
                        "x": cx,
                        "y": cy,
                        "y0": y0,
                        "y1": y1,
                        "x0": x0,
                        "x1": x1,
                        "val": val,
                        "mad": 0.0,
                        "accepted": False,
                        "is_manual": False,
                        "reason": "Berada pada Wilayah Proteksi (Protected ROI) atau piksel NaN/Inf",
                    }
                )
                continue

            vals = cell_s[valid_mask]
            med0, mad0 = _robust_median_and_mad(vals)
            # Clip piksel bintang/sabit lokal di dalam sel sebelum mengambil median background sel
            if mad0 > 1e-9:
                bg_vals = vals[vals <= med0 + 2.2 * mad0]
                if bg_vals.size >= max(3, int(0.3 * vals.size)):
                    med_cell, mad_cell = _robust_median_and_mad(bg_vals)
                else:
                    med_cell, mad_cell = med0, mad0
            else:
                med_cell, mad_cell = med0, mad0

            raw_candidates.append(
                {
                    "x": cx,
                    "y": cy,
                    "y0": y0,
                    "y1": y1,
                    "x0": x0,
                    "x1": x1,
                    "val": med_cell,
                    "mad": mad_cell,
                    "accepted": True,
                    "is_manual": False,
                    "reason": None,
                }
            )

    # Tambahkan titik sampel manual dari pengguna (jika berada di luar wilayah proteksi)
    half_box = max(2, min(height, width) // 32)
    for mx, my in config.manual_include_points:
        ix = max(0, min(width - 1, int(mx)))
        iy = max(0, min(height - 1, int(my)))
        y0 = max(0, iy - half_box)
        y1 = min(height, iy + half_box + 1)
        x0 = max(0, ix - half_box)
        x1 = min(width, ix + half_box + 1)
        patch = lum_2d[y0:y1, x0:x1]
        patch_prot = protected_mask[y0:y1, x0:x1]
        valid_mask = np.isfinite(patch) & (~patch_prot)
        if np.any(valid_mask):
            m_val, m_mad = _robust_median_and_mad(patch[valid_mask])
            raw_candidates.append(
                {
                    "x": float(ix),
                    "y": float(iy),
                    "y0": y0,
                    "y1": y1,
                    "x0": x0,
                    "x1": x1,
                    "val": m_val,
                    "mad": m_mad,
                    "accepted": True,
                    "is_manual": True,
                    "reason": None,
                }
            )

    # Iterasi penolakan outlier berbasis permukaan awal & MAD residual
    active_indices = [i for i, c in enumerate(raw_candidates) if bool(c["accepted"])]
    min_keep = max(4, min(len(active_indices), max(6, len(active_indices) // 3)))

    if len(active_indices) > min_keep:
        # 1. Tolak sel yang memiliki local_mad sangat ekstrem (mengandung tepi objek tajam/bintang terang)
        mads = np.array([float(raw_candidates[i]["mad"]) for i in active_indices], dtype=np.float64)
        med_mad, mad_of_mad = _robust_median_and_mad(mads)
        if mad_of_mad > 1e-9:
            mad_limit = med_mad + (config.mad_sigma_clip + 1.0) * mad_of_mad
            for idx in list(active_indices):
                if len(active_indices) <= min_keep:
                    break
                if bool(raw_candidates[idx]["is_manual"]):
                    continue
                if float(raw_candidates[idx]["mad"]) > mad_limit:
                    raw_candidates[idx]["accepted"] = False
                    raw_candidates[idx]["reason"] = (
                        "Variasi lokal sel terlalu tinggi (didominasi objek/struktur tajam)"
                    )
                    active_indices.remove(idx)

        # 2. Iterasi penolakan residual positif terhadap permukaan polinomial derajat 1/2
        poly_deg_for_rej = 1 if config.method == BackgroundModelMethod.POLYNOMIAL_DEG_1 else 2
        for _it in range(max(1, config.max_rejection_iterations)):
            if len(active_indices) <= min_keep:
                break
            xs = np.array([float(raw_candidates[i]["x"]) for i in active_indices], dtype=np.float64)
            ys = np.array([float(raw_candidates[i]["y"]) for i in active_indices], dtype=np.float64)
            zs = np.array([float(raw_candidates[i]["val"]) for i in active_indices], dtype=np.float64)
            ws = 1.0 / (
                np.array([float(raw_candidates[i]["mad"]) for i in active_indices], dtype=np.float64)
                + 1e-3
            )
            coeffs_rej = _fit_polynomial_coeffs(
                xs, ys, zs, ws, height, width, degree=poly_deg_for_rej
            )
            pred = _evaluate_polynomial_at_coords(xs, ys, coeffs_rej, height, width)
            res = zs - pred
            res_med, res_mad = _robust_median_and_mad(res)
            sigma_eff = max(res_mad, med_mad * 0.5, 1e-6)
            high_thresh = res_med + config.mad_sigma_clip * sigma_eff
            low_thresh = res_med - (config.mad_sigma_clip + 1.0) * sigma_eff

            # Urutkan kandidat dengan penyimpangan terbesar terlebih dahulu
            deviations = np.abs(res - res_med)
            order = np.argsort(-deviations)
            rejected_this_iter = 0
            for pos in order:
                if len(active_indices) <= min_keep:
                    break
                cand_idx = active_indices[int(pos)]
                if bool(raw_candidates[cand_idx]["is_manual"]):
                    continue
                r_val = float(res[int(pos)])
                if r_val > high_thresh:
                    raw_candidates[cand_idx]["accepted"] = False
                    raw_candidates[cand_idx]["reason"] = (
                        f"Ditolak oleh outlier rejection MAD (residual terang +{r_val:.3g} > ambang)"
                    )
                    rejected_this_iter += 1
                elif r_val < low_thresh:
                    raw_candidates[cand_idx]["accepted"] = False
                    raw_candidates[cand_idx]["reason"] = (
                        f"Ditolak oleh outlier rejection MAD (anomali gelap {r_val:.3g} < ambang)"
                    )
                    rejected_this_iter += 1

            active_indices = [i for i, c in enumerate(raw_candidates) if bool(c["accepted"])]
            if rejected_this_iter == 0:
                break

    sample_points: list[BackgroundSamplePoint] = []
    acc_x: list[float] = []
    acc_y: list[float] = []
    acc_val: list[float] = []
    acc_w: list[float] = []
    acc_boxes: list[tuple[int, int, int, int]] = []

    for c in raw_candidates:
        is_acc = bool(c["accepted"])
        sp = BackgroundSamplePoint(
            x=float(c["x"]),
            y=float(c["y"]),
            value=float(c["val"]),
            local_mad=float(c["mad"]),
            accepted=is_acc,
            is_manual=bool(c["is_manual"]),
            rejection_reason=str(c["reason"]) if c["reason"] is not None else None,
        )
        sample_points.append(sp)
        if is_acc:
            acc_x.append(sp.x)
            acc_y.append(sp.y)
            acc_val.append(sp.value)
            acc_w.append(1.0 / (sp.local_mad + 1.0))
            acc_boxes.append((int(c["y0"]), int(c["y1"]), int(c["x0"]), int(c["x1"])))

    return (
        sample_points,
        np.asarray(acc_x, dtype=np.float64),
        np.asarray(acc_y, dtype=np.float64),
        np.asarray(acc_val, dtype=np.float64),
        np.asarray(acc_w, dtype=np.float64),
    )


def _fit_channel_surface_from_accepted_coords(
    channel_2d: np.ndarray,
    protected_mask: np.ndarray,
    acc_x: np.ndarray,
    acc_y: np.ndarray,
    acc_w: np.ndarray,
    *,
    cell_half_h: int,
    cell_half_w: int,
    method: BackgroundModelMethod,
    rbf_smoothing: float,
) -> tuple[np.ndarray, float]:
    """Mencocokkan permukaan model background untuk satu kanal 2D pada posisi sampel yang diterima."""
    height, width = channel_2d.shape
    finite_all = channel_2d[np.isfinite(channel_2d) & (~protected_mask)]
    if finite_all.size == 0:
        finite_all = channel_2d[np.isfinite(channel_2d)]
    if finite_all.size == 0:
        return np.zeros((height, width), dtype=np.float32), 0.0

    global_med, global_mad = _robust_median_and_mad(finite_all)
    if global_mad <= 1e-12 and float(np.ptp(finite_all)) <= 1e-9:
        # Citra konstan / seragam sempurna
        return np.full((height, width), global_med, dtype=np.float32), float(rbf_smoothing)

    if acc_x.size < 3:
        return np.full((height, width), global_med, dtype=np.float32), float(rbf_smoothing)

    # Hitung median lokal pada tiap koordinat sampel yang diterima untuk kanal ini
    zs = np.empty(acc_x.size, dtype=np.float64)
    for idx in range(acc_x.size):
        cx = int(round(acc_x[idx]))
        cy = int(round(acc_y[idx]))
        y0 = max(0, cy - cell_half_h)
        y1 = min(height, cy + cell_half_h + 1)
        x0 = max(0, cx - cell_half_w)
        x1 = min(width, cx + cell_half_w + 1)
        patch = channel_2d[y0:y1, x0:x1]
        p_prot = protected_mask[y0:y1, x0:x1]

        # Subsampling cepat jika patch berukuran besar (> 1600 piksel)
        p_h, p_w = patch.shape
        if p_h * p_w > 1600:
            sy = max(1, p_h // 40)
            sx = max(1, p_w // 40)
            patch_s = patch[::sy, ::sx]
            prot_s = p_prot[::sy, ::sx]
        else:
            patch_s = patch
            prot_s = p_prot

        v_mask = np.isfinite(patch_s) & (~prot_s)
        if np.any(v_mask):
            vals = patch_s[v_mask]
            m0, d0 = _robust_median_and_mad(vals)
            if d0 > 1e-9:
                clipped = vals[vals <= m0 + 2.2 * d0]
                zs[idx] = float(np.median(clipped)) if clipped.size > 0 else m0
            else:
                zs[idx] = m0
        else:
            zs[idx] = global_med

    if method == BackgroundModelMethod.POLYNOMIAL_DEG_1:
        surf = _fit_polynomial_surface(acc_x, acc_y, zs, acc_w, height, width, degree=1)
        return surf, 0.0

    if method == BackgroundModelMethod.POLYNOMIAL_DEG_2:
        surf = _fit_polynomial_surface(
            acc_x, acc_y, zs, acc_w, height, width, degree=2, ridge_lambda=2e-3
        )
        return surf, 0.0

    # TPS_RBF atau AUTO_ROBUST_RBF
    grad_span = max(1e-6, float(np.percentile(zs, 95) - np.percentile(zs, 5)))
    noise_to_grad = global_mad / grad_span
    if method == BackgroundModelMethod.AUTO_ROBUST_RBF:
        # Semakin tinggi rasio derau terhadap gradien, semakin kuat regularisasi agar tidak overfit
        adaptive_factor = float(np.clip(1.0 + 4.0 * noise_to_grad, 0.75, 6.0))
        eff_smoothing = max(0.25, float(rbf_smoothing) * adaptive_factor)
    else:
        eff_smoothing = max(0.05, float(rbf_smoothing))

    rbf_surf = _fit_tps_rbf_surface(
        acc_x,
        acc_y,
        zs,
        acc_w,
        height,
        width,
        smoothing=eff_smoothing,
    )
    # Safeguard anti-overfitting pada RBF: batasi deviasi lokal RBF terhadap bidang kuadratik
    poly2_surf = _fit_polynomial_surface(
        acc_x, acc_y, zs, acc_w, height, width, degree=2, ridge_lambda=5e-3
    )
    diff_surf = rbf_surf - poly2_surf
    max_allowed_curv = max(2.5 * global_mad, 0.35 * grad_span)
    if float(np.max(np.abs(diff_surf))) > max_allowed_curv and max_allowed_curv > 0.0:
        blend_w = float(np.clip(max_allowed_curv / float(np.max(np.abs(diff_surf))), 0.25, 1.0))
        rbf_surf = (poly2_surf + blend_w * diff_surf).astype(np.float32)

    return rbf_surf, eff_smoothing


def render_background_overlay_preview(
    base_preview: QImage,
    sample_points: tuple[BackgroundSamplePoint, ...],
    protected_mask: np.ndarray,
    config: BackgroundExtractionConfig,
) -> QImage:
    """Menggambar overlay lokasi sampel background dan Wilayah Proteksi (Protected ROI) di atas QImage."""
    canvas = base_preview.convertToFormat(QImage.Format.Format_RGB888).copy()
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    height = canvas.height()
    width = canvas.width()

    # Gambar Wilayah Proteksi (Protected Region ROI) dengan bingkai kuning/sian terang
    pen_roi = QPen(QColor(255, 204, 0, 230))
    pen_roi.setWidth(max(1, min(width, height) // 180))
    painter.setPen(pen_roi)
    painter.setBrush(QColor(255, 204, 0, 48))

    for roi in config.protected_regions:
        kind = roi.shape_type.strip().upper()
        if kind == "RECTANGLE" and roi.rect is not None:
            rx, ry, rw, rh = roi.rect
            painter.drawRect(int(rx), int(ry), int(rw), int(rh))
        elif kind == "POLYGON" and roi.polygon is not None and len(roi.polygon) >= 3:
            from PySide6.QtCore import QPointF
            from PySide6.QtGui import QPolygonF

            poly_q = QPolygonF([QPointF(float(px), float(py)) for px, py in roi.polygon])
            painter.drawPolygon(poly_q)

    # Jika ada protected_mask langsung tanpa objek ROI, tandai kotak pembatasnya
    if not config.protected_regions and np.any(protected_mask):
        ys, xs = np.nonzero(protected_mask)
        x0, x1 = int(np.min(xs)), int(np.max(xs))
        y0, y1 = int(np.min(ys)), int(np.max(ys))
        painter.drawRect(x0, y0, max(1, x1 - x0 + 1), max(1, y1 - y0 + 1))

    # Gambar titik-titik sampel (Hijau = Diterima, Merah/Oranye = Ditolak)
    marker_r = max(2, min(6, min(width, height) // 90))
    pen_acc = QPen(QColor(34, 197, 94, 235))
    pen_acc.setWidth(1)
    pen_rej = QPen(QColor(239, 68, 68, 235))
    pen_rej.setWidth(1)

    for sp in sample_points:
        ix = int(round(sp.x))
        iy = int(round(sp.y))
        if sp.accepted:
            painter.setPen(pen_acc)
            painter.setBrush(QColor(34, 197, 94, 160))
            painter.drawEllipse(ix - marker_r, iy - marker_r, 2 * marker_r, 2 * marker_r)
        else:
            painter.setPen(pen_rej)
            painter.setBrush(QColor(239, 68, 68, 150))
            painter.drawLine(ix - marker_r, iy - marker_r, ix + marker_r, iy + marker_r)
            painter.drawLine(ix - marker_r, iy + marker_r, ix + marker_r, iy - marker_r)

    painter.end()
    return canvas


def run_background_extraction(
    linear_image: np.ndarray,
    config: BackgroundExtractionConfig | ProcessingProfile | str = ProcessingProfile.MEDIUM,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> BackgroundExtractionResult:
    """Menjalankan Engine 1 — Background Extraction secara subtractive pada citra linear.

    Rumus:
        I_corrected(x, y) = I_linear(x, y) - B_model(x, y)

    Args:
        linear_image: Array ilmiah linear (2D ``(H, W)`` atau 3D ``(H, W, C)``).
                      Data asli TIDAK diubah.
        config: Objek ``BackgroundExtractionConfig`` atau profil ``BASIC``/``MEDIUM``/``HIGH``.
        cancel_check: Fungsi opsional penghenti proses secara aman.

    Returns:
        ``BackgroundExtractionResult`` lengkap dengan ``linear_corrected_data`` (``float32``),
        ``background_model`` (``float32``), daftar titik sampel, statistik residual,
        peringatan overcorrection, dan pratinjau ``QImage``.
    """
    _check_cancel(cancel_check)

    if isinstance(config, (ProcessingProfile, str)):
        cfg = get_unified_profile_config(config).background_config
    else:
        cfg = config

    src = np.asarray(linear_image)
    if src.ndim not in (2, 3):
        raise ProcessingError(
            f"Background Extraction membutuhkan citra 2D atau 3D, tetapi menerima dimensi {src.shape}."
        )
    height, width = int(src.shape[0]), int(src.shape[1])
    if height < 4 or width < 4:
        raise ProcessingError(
            f"Ukuran citra ({width}×{height} px) terlalu kecil untuk pemodelan background."
        )

    # Validasi kompatibilitas domain Bayer CFA bila merupakan mosaic sensor mentah
    cfa_subchannel_modeled = False
    if cfg.is_cfa_mosaic:
        pat_norm = (cfg.cfa_pattern_str or "").strip().upper()
        if not pat_norm or pat_norm not in SUPPORTED_BAYER_2X2_PATTERNS:
            raise ProcessingError(
                f"Pola CFA '{cfg.cfa_pattern_str or 'Tidak dikenal'}' tidak didukung untuk "
                "Background Extraction domain mosaic secara langsung (hanya Bayer 2×2 standar "
                "yang didukung tanpa demosaicing)."
            )
        if src.ndim != 2 or (height % 2 != 0) or (width % 2 != 0):
            raise ProcessingError(
                f"Citra Bayer CFA harus berukuran genap 2D (diterima {src.shape})."
            )
        cfa_subchannel_modeled = True

    work_f32 = np.array(src, dtype=np.float32, copy=True)
    protected_mask = build_combined_protected_mask(height, width, cfg)
    protected_pixel_count = int(np.count_nonzero(protected_mask))

    warnings: list[str] = []
    notes: list[str] = []

    if protected_pixel_count > 0:
        pct_prot = 100.0 * float(protected_pixel_count) / float(max(1, height * width))
        notes.append(
            f"Wilayah Proteksi Manual aktif: {protected_pixel_count} piksel ({pct_prot:.1f}%) "
            "dikecualikan dari pemilihan sampel background."
        )
        if pct_prot > 80.0:
            warnings.append(
                f"Wilayah Proteksi menutupi {pct_prot:.1f}% area citra; jumlah sampel background "
                "yang tersisa sangat terbatas."
            )

    # Tentukan kerapatan mesh efektif (adaptif pada AUTO_ROBUST_RBF)
    if cfg.method == BackgroundModelMethod.AUTO_ROBUST_RBF:
        min_dim = min(height, width)
        auto_n = int(np.clip(min_dim // 16, 6, 14))
        eff_rows = max(4, min(16, max(cfg.grid_rows, auto_n)))
        eff_cols = max(4, min(16, max(cfg.grid_cols, auto_n)))
    else:
        eff_rows = max(2, min(height // 2, int(cfg.grid_rows)))
        eff_cols = max(2, min(width // 2, int(cfg.grid_cols)))

    _check_cancel(cancel_check)

    # Bangun proxy luminansi 2D untuk menentukan posisi sel background yang bebas objek terang
    if cfa_subchannel_modeled:
        # Rata-rata blok 2x2 Bayer untuk mendeteksi lokasi bintang/sabit secara konsisten
        lum_2x2 = (
            0.25
            * (
                work_f32[0::2, 0::2].astype(np.float64)
                + work_f32[0::2, 1::2].astype(np.float64)
                + work_f32[1::2, 0::2].astype(np.float64)
                + work_f32[1::2, 1::2].astype(np.float64)
            )
        )
        lum_proxy = np.repeat(np.repeat(lum_2x2, 2, axis=0), 2, axis=1)
    else:
        lum_proxy = _compute_2d_luminance_proxy(work_f32)

    (
        sample_points,
        acc_x,
        acc_y,
        _acc_val,
        acc_w,
    ) = _sample_and_reject_outliers_2d(
        lum_proxy,
        protected_mask,
        cfg,
        effective_rows=eff_rows,
        effective_cols=eff_cols,
    )

    accepted_count = int(acc_x.size)
    rejected_count = int(len(sample_points) - accepted_count)

    if accepted_count == 0:
        raise ProcessingError(
            "Background Extraction gagal: Tidak ada titik sampel background yang valid "
            "(seluruh area tertutup Wilayah Proteksi atau bernilai NaN/Inf)."
        )

    _check_cancel(cancel_check)

    cell_half_h = max(2, height // (2 * eff_rows))
    cell_half_w = max(2, width // (2 * eff_cols))
    eff_rbf_smoothing = float(cfg.rbf_smoothing)

    # C. Pemodelan permukaan per jenis sensor (2D Mono, 2D Bayer CFA 2x2, atau 3D RGB)
    if cfa_subchannel_modeled:
        bg_model = np.zeros_like(work_f32, dtype=np.float32)
        sub_h, sub_w = height // 2, width // 2
        sub_acc_x = acc_x * 0.5
        sub_acc_y = acc_y * 0.5
        for dy in (0, 1):
            for dx in (0, 1):
                _check_cancel(cancel_check)
                sub_img = work_f32[dy::2, dx::2]
                sub_prot = protected_mask[dy::2, dx::2]
                sub_surf, eff_rbf_smoothing = _fit_channel_surface_from_accepted_coords(
                    sub_img,
                    sub_prot,
                    sub_acc_x,
                    sub_acc_y,
                    acc_w,
                    cell_half_h=max(1, cell_half_h // 2),
                    cell_half_w=max(1, cell_half_w // 2),
                    method=cfg.method,
                    rbf_smoothing=cfg.rbf_smoothing,
                )
                bg_model[dy::2, dx::2] = sub_surf[:sub_h, :sub_w]
        notes.append(
            f"Mode Bayer CFA ({cfg.cfa_pattern_str}): Keempat sub-kanal Bayer 2×2 dimodelkan "
            "secara independen tanpa demosaicing."
        )
    elif work_f32.ndim == 2:
        bg_model, eff_rbf_smoothing = _fit_channel_surface_from_accepted_coords(
            work_f32,
            protected_mask,
            acc_x,
            acc_y,
            acc_w,
            cell_half_h=cell_half_h,
            cell_half_w=cell_half_w,
            method=cfg.method,
            rbf_smoothing=cfg.rbf_smoothing,
        )
    else:
        num_ch = work_f32.shape[2]
        bg_model = np.zeros_like(work_f32, dtype=np.float32)
        for ch_idx in range(num_ch):
            _check_cancel(cancel_check)
            ch_surf, eff_rbf_smoothing = _fit_channel_surface_from_accepted_coords(
                work_f32[:, :, ch_idx],
                protected_mask,
                acc_x,
                acc_y,
                acc_w,
                cell_half_h=cell_half_h,
                cell_half_w=cell_half_w,
                method=cfg.method,
                rbf_smoothing=cfg.rbf_smoothing,
            )
            bg_model[:, :, ch_idx] = ch_surf
        notes.append(
            f"Citra multi-kanal ({num_ch} kanal): Lokasi sampel disinkronkan secara luminance-consistent "
            "agar keseimbangan warna latar tetap terjaga."
        )

    _check_cancel(cancel_check)

    # D. Koreksi Subtractive: I_corrected(x, y) = I_linear(x, y) - B_model(x, y)
    # Piksel NaN/Inf pada input tetap dipertahankan apa adanya tanpa merusak model
    finite_mask_full = np.isfinite(work_f32)
    if cfg.preserve_mean_sky_pedestal:
        pedestal = float(np.median(bg_model[np.isfinite(bg_model)]))
        effective_model = (bg_model - pedestal).astype(np.float32)
    else:
        effective_model = bg_model.astype(np.float32, copy=False)

    corrected = np.where(
        finite_mask_full,
        work_f32 - effective_model,
        work_f32,
    ).astype(np.float32)

    # E. Evaluasi Statistik Residual & Safeguard Peringatan Overcorrection
    corr_lum = _compute_2d_luminance_proxy(corrected)
    model_lum = _compute_2d_luminance_proxy(effective_model)
    valid_bg_mask = np.isfinite(lum_proxy) & (~protected_mask)
    if not np.any(valid_bg_mask):
        valid_bg_mask = np.isfinite(lum_proxy)

    # Subsampling cepat jika citra berukuran besar untuk kalkulasi statistik residual (< 15 ms vs 8.5 s)
    if height * width > 100000:
        sy = max(1, height // 300)
        sx = max(1, width // 300)
        sub_proxy = lum_proxy[::sy, ::sx]
        sub_corr = corr_lum[::sy, ::sx]
        sub_mask = valid_bg_mask[::sy, ::sx]
        if not np.any(sub_mask):
            sub_mask = np.isfinite(sub_proxy)
        bg_med_before, bg_mad_before = _robust_median_and_mad(sub_proxy[sub_mask])
        bg_med_after, bg_mad_after = _robust_median_and_mad(sub_corr[sub_mask])
        res_vals = sub_corr[sub_mask] - bg_med_after
        residual_rms = float(np.sqrt(np.mean(res_vals * res_vals))) if res_vals.size > 0 else 0.0
        finite_corr_sub = sub_corr[np.isfinite(sub_corr)]
        sigma_ref = max(bg_mad_after, bg_mad_before, 1e-6)
        deep_negative_ratio = float(
            np.count_nonzero(finite_corr_sub < (bg_med_after - 3.2 * sigma_ref))
        ) / float(max(1, finite_corr_sub.size))
    else:
        bg_med_before, bg_mad_before = _robust_median_and_mad(lum_proxy[valid_bg_mask])
        bg_med_after, bg_mad_after = _robust_median_and_mad(corr_lum[valid_bg_mask])
        res_vals = corr_lum[valid_bg_mask] - bg_med_after
        residual_rms = float(np.sqrt(np.mean(res_vals * res_vals))) if res_vals.size > 0 else 0.0
        finite_corr_all = corr_lum[np.isfinite(corr_lum)]
        sigma_ref = max(bg_mad_after, bg_mad_before, 1e-6)
        deep_negative_ratio = float(
            np.count_nonzero(finite_corr_all < (bg_med_after - 3.2 * sigma_ref))
        ) / float(max(1, finite_corr_all.size))

    # Ukur penurunan gradien makro pada titik-titik sampel yang diterima
    if acc_x.size >= 2:
        ix = np.clip(np.round(acc_x).astype(int), 0, width - 1)
        iy = np.clip(np.round(acc_y).astype(int), 0, height - 1)
        before_samples = lum_proxy[iy, ix]
        after_samples = corr_lum[iy, ix]
        init_ptp = float(np.percentile(before_samples, 95) - np.percentile(before_samples, 5))
        res_ptp = float(np.percentile(after_samples, 95) - np.percentile(after_samples, 5))
    else:
        init_ptp = 0.0
        res_ptp = 0.0

    if init_ptp > 1e-6:
        grad_reduction = float(np.clip(1.0 - (res_ptp / init_ptp), -1.0, 1.0))
    else:
        grad_reduction = 0.0

    # Bandingkan juga kelengkungan orde tinggi terhadap bidang linear
    if acc_x.size >= 4 and cfg.method != BackgroundModelMethod.POLYNOMIAL_DEG_1:
        if height * width > 100000:
            sub_h = min(height, 300)
            sub_w = min(width, 300)
            lin_sub = _fit_polynomial_surface(
                acc_x * (sub_w / width),
                acc_y * (sub_h / height),
                lum_proxy[np.clip(np.round(acc_y).astype(int), 0, height - 1), np.clip(np.round(acc_x).astype(int), 0, width - 1)],
                acc_w,
                sub_h,
                sub_w,
                degree=1,
            )
            sy = max(1, height // 300)
            sx = max(1, width // 300)
            curv_ratio = float(np.std(model_lum[::sy, ::sx][:sub_h, :sub_w] - lin_sub)) / float(max(init_ptp, sigma_ref, 1e-6))
        else:
            lin_ref = _fit_polynomial_surface(
                acc_x,
                acc_y,
                lum_proxy[np.clip(np.round(acc_y).astype(int), 0, height - 1), np.clip(np.round(acc_x).astype(int), 0, width - 1)],
                acc_w,
                height,
                width,
                degree=1,
            )
            curv_ratio = float(np.std(model_lum - lin_ref)) / float(max(init_ptp, sigma_ref, 1e-6))
    else:
        curv_ratio = 0.0

    overcorrection_score = float(max(deep_negative_ratio, 0.25 * curv_ratio))
    overcorrection_warning = bool(overcorrection_score > cfg.overcorrection_warn_ratio)
    if overcorrection_warning:
        warnings.append(
            f"Peringatan Risiko Overcorrection (skor={overcorrection_score:.2f} > {cfg.overcorrection_warn_ratio:.2f}): "
            "Model background cukup melengkung dan berpotensi mereduksi struktur sabit ber-kontras rendah. "
            "Pertimbangkan menandai Wilayah Proteksi (Protected ROI) di sekitar sabit atau gunakan profil Basic."
        )

    residual_stats = BackgroundResidualStats(
        initial_gradient_ptp=init_ptp,
        residual_gradient_ptp=res_ptp,
        gradient_reduction_ratio=grad_reduction,
        background_median_before=bg_med_before,
        background_median_after=bg_med_after,
        residual_rms=residual_rms,
        residual_mad_sigma=bg_mad_after,
        overcorrection_score=overcorrection_score,
        overcorrection_warning=overcorrection_warning,
    )

    # F. Bangun QImage pratinjau model, overlay sampel/ROI, dan citra terkoreksi
    base_prev = array_to_preview_qimage(work_f32)
    model_prev = array_to_preview_qimage(effective_model)
    corrected_prev = array_to_preview_qimage(corrected)
    overlay_prev = render_background_overlay_preview(
        base_prev,
        tuple(sample_points),
        protected_mask,
        cfg,
    )

    return BackgroundExtractionResult(
        linear_corrected_data=corrected,
        background_model=effective_model,
        sample_points=tuple(sample_points),
        accepted_sample_count=accepted_count,
        rejected_sample_count=rejected_count,
        protected_pixel_count=protected_pixel_count,
        protected_mask=protected_mask,
        residual_stats=residual_stats,
        config_used=cfg,
        effective_method=cfg.method,
        effective_rbf_smoothing=eff_rbf_smoothing,
        cfa_subchannel_modeled=cfa_subchannel_modeled,
        model_preview=model_prev,
        overlay_preview=overlay_prev,
        corrected_preview=corrected_prev,
        warnings=tuple(warnings),
        notes=tuple(notes),
    )
