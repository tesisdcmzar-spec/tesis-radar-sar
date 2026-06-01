"""
2D relative dielectric contrast heatmap from SAR backprojection.

Converts complex SAR imagery to normalized contrast indicators and
supports comparison with ground-truth Fresnel reflectivity maps.

Pipeline
--------
  SAR image (complex, n_x x n_z)
    -> magnitude: |img(x,z)|
    -> normalize: heatmap = |img| / max|img|    (relative, in [0,1])
  Ground-truth phantom
    -> Fresnel |Gamma(x,z)| map from permittivity contrast
    -> normalize to [0,1]
  Comparison: heatmap vs ground_truth

Scientific note
---------------
The output is a "relative dielectric contrast heatmap":
  - Pixel brightness indicates relative microwave reflectivity contrast.
  - Brighter pixels correspond to stronger dielectric discontinuities.
  - Values are normalized to [0,1] relative to the strongest reflector.
  - This is NOT absolute permittivity.
  - Ground-truth uses simplified Fresnel model (non-dispersive, non-magnetic,
    point-scatterer approximation). Not a validated measurement method.
  - No clinical claims. No cancer detection. No medical conclusions.

Hardware-independent. No bladeRF import. Safe to run offline.
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "sar_image_to_contrast_heatmap",
    "permittivity_map_to_reflectivity_map",
    "compare_heatmaps",
    "locate_contrast_peaks_2d",
    "heatmap_summary",
]


def sar_image_to_contrast_heatmap(
    img: np.ndarray,
    normalize: bool = True,
) -> np.ndarray:
    """
    Convert complex SAR backprojection image to relative contrast heatmap.

    Parameters
    ----------
    img       : complex or real array (n_x, n_z). Backprojected SAR image.
    normalize : bool. Divide by max magnitude to produce [0,1] range.

    Returns
    -------
    heatmap : float array (n_x, n_z). Normalized magnitude map.
    """
    magnitude = np.abs(np.asarray(img, dtype=complex))
    if normalize:
        peak = float(np.max(magnitude))
        if peak < 1e-15:
            return np.zeros_like(magnitude, dtype=float)
        return (magnitude / peak).astype(float)
    return magnitude.astype(float)


def permittivity_map_to_reflectivity_map(
    eps_r_map: np.ndarray,
    eps_r_bg: float = 1.0,
    normalize: bool = True,
) -> np.ndarray:
    """
    Convert 2D permittivity map to Fresnel reflectivity magnitude map.

    |Gamma(x,z)| = |sqrt(eps_bg) - sqrt(eps(x,z))| / |sqrt(eps_bg) + sqrt(eps(x,z))|

    Parameters
    ----------
    eps_r_map : float array (n_x, n_z). Relative permittivity at each pixel.
    eps_r_bg  : float. Background permittivity.
    normalize : bool. Normalize to [0, 1]. Default True.

    Returns
    -------
    refl_map : float array (n_x, n_z). Fresnel |Gamma| map.
    """
    eps_r_map = np.asarray(eps_r_map, dtype=float)
    n1 = np.sqrt(max(eps_r_bg, 1e-9))
    n2 = np.sqrt(np.maximum(eps_r_map, 1e-9))
    gamma = np.abs((n1 - n2) / (n1 + n2 + 1e-30))
    if normalize:
        peak = float(np.max(gamma))
        if peak < 1e-15:
            return np.zeros_like(gamma, dtype=float)
        return (gamma / peak).astype(float)
    return gamma.astype(float)


def compare_heatmaps(
    reconstructed: np.ndarray,
    ground_truth: np.ndarray,
) -> dict:
    """
    Compare reconstructed contrast heatmap to ground-truth reflectivity map.

    Both arrays must have the same shape and be normalized to [0, 1].

    Parameters
    ----------
    reconstructed : float array (n_x, n_z). SAR contrast heatmap [0,1].
    ground_truth  : float array (n_x, n_z). Reference reflectivity map [0,1].

    Returns
    -------
    metrics : dict with mse, rmse, max_abs_error, peak location indices, note.

    Raises
    ------
    ValueError
        If shapes differ.
    """
    r = np.asarray(reconstructed, dtype=float)
    g = np.asarray(ground_truth, dtype=float)
    if r.shape != g.shape:
        raise ValueError(
            f"Shape mismatch: reconstructed {r.shape} vs ground_truth {g.shape}"
        )
    diff = r - g
    mse = float(np.mean(diff ** 2))
    rmse = float(np.sqrt(mse))
    max_abs_err = float(np.max(np.abs(diff)))

    r_peak = tuple(int(i) for i in np.unravel_index(np.argmax(r), r.shape))
    g_peak = tuple(int(i) for i in np.unravel_index(np.argmax(g), g.shape))

    return {
        "mse": mse,
        "rmse": rmse,
        "max_abs_error": max_abs_err,
        "reconstructed_peak_idx": r_peak,
        "ground_truth_peak_idx": g_peak,
        "peak_location_match": (r_peak == g_peak),
        "note": (
            "Comparison uses simplified Fresnel model as ground truth. "
            "Not a validated absolute permittivity measurement."
        ),
    }


def locate_contrast_peaks_2d(
    heatmap: np.ndarray,
    x_grid: np.ndarray,
    z_grid: np.ndarray,
    n_peaks: int = 5,
    threshold: float = 0.3,
) -> list[dict]:
    """
    Locate the strongest contrast peaks in a 2D heatmap using iterative suppression.

    Parameters
    ----------
    heatmap   : float array (n_x, n_z). Normalized contrast heatmap [0,1].
    x_grid    : float array (n_x,). Cross-range axis [m].
    z_grid    : float array (n_z,). Down-range axis [m].
    n_peaks   : int. Maximum number of peaks to find.
    threshold : float. Minimum contrast level to report.

    Returns
    -------
    peaks : list of dicts, each with: x_m, z_m, value, ix, iz.
    """
    h = np.asarray(heatmap, dtype=float).copy()
    n_x, n_z = h.shape
    win_x = max(3, n_x // 10)
    win_z = max(3, n_z // 10)

    peaks: list[dict] = []
    for _ in range(n_peaks):
        peak_val = float(np.max(h))
        if peak_val < threshold:
            break
        ix, iz = np.unravel_index(np.argmax(h), h.shape)
        peaks.append({
            "x_m": float(x_grid[int(ix)]),
            "z_m": float(z_grid[int(iz)]),
            "value": peak_val,
            "ix": int(ix),
            "iz": int(iz),
        })
        x_lo = max(0, ix - win_x)
        x_hi = min(n_x, ix + win_x + 1)
        z_lo = max(0, iz - win_z)
        z_hi = min(n_z, iz + win_z + 1)
        h[x_lo:x_hi, z_lo:z_hi] = 0.0

    return peaks


def heatmap_summary(
    heatmap: np.ndarray,
    x_grid: np.ndarray,
    z_grid: np.ndarray,
    inclusions: list | None = None,
) -> dict:
    """
    Compute summary statistics and peak positions for a contrast heatmap.

    Parameters
    ----------
    heatmap    : float array (n_x, n_z). Normalized contrast heatmap.
    x_grid     : float array (n_x,). Cross-range axis [m].
    z_grid     : float array (n_z,). Down-range axis [m].
    inclusions : list of DielectricInclusion or None.

    Returns
    -------
    summary : dict with shape, grid ranges, statistics, peaks, optional inclusion matches.
    """
    heatmap = np.asarray(heatmap, dtype=float)
    peaks = locate_contrast_peaks_2d(heatmap, x_grid, z_grid)

    summary: dict = {
        "shape": heatmap.shape,
        "x_range_m": (float(x_grid[0]), float(x_grid[-1])),
        "z_range_m": (float(z_grid[0]), float(z_grid[-1])),
        "mean_contrast": float(np.mean(heatmap)),
        "max_contrast": float(np.max(heatmap)),
        "n_peaks_found": len(peaks),
        "peaks": peaks,
        "note": (
            "Relative contrast heatmap. "
            "Not absolute permittivity. Calibration required for epsilon_r."
        ),
    }

    if inclusions is not None:
        matches = []
        for incl in inclusions:
            best_dist = float("inf")
            best_peak = None
            for pk in peaks:
                d = float(
                    np.sqrt((pk["x_m"] - incl.x_m) ** 2 + (pk["z_m"] - incl.z_m) ** 2)
                )
                if d < best_dist:
                    best_dist = d
                    best_peak = pk
            matches.append({
                "label": getattr(incl, "label", ""),
                "true_x_m": float(incl.x_m),
                "true_z_m": float(incl.z_m),
                "epsilon_r": float(incl.epsilon_r),
                "nearest_peak": best_peak,
                "distance_error_m": best_dist if best_peak is not None else None,
            })
        summary["inclusion_matches"] = matches

    return summary
