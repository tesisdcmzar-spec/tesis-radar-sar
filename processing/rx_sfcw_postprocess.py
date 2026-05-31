"""
Post-processing for RX-only SFCW H(f) arrays and range profiles.

IMPORTANT: Functions in this module operate on H(f) captured in RX-only mode
(no RF transmission).  This H(f) represents the coherent mean of environmental
RF noise at each tuned frequency, NOT a radar transfer function from a
controlled TX/RX pair.  Consequently:

  - remove_dc_component, normalize_h_magnitude, subtract_reference_h, and
    smooth_h_magnitude are preprocessing tools for pipeline validation.
  - Range profiles computed from RX-only H(f) show the noise IFFT response,
    NOT target reflections.
  - find_prominent_range_bins detects features in the profile but cannot
    attribute them to physical targets without a controlled TX signal.
  - summarize_range_profile reports statistics of a noise-floor IFFT result
    when called on RX-only data.

All functions are hardware-independent and fully testable with synthetic data.
No bladeRF import.  No hardware access.  No TX operations.
"""
from __future__ import annotations

import numpy as np


# ---------------------------------------------------------------------------
# H(f) preprocessing
# ---------------------------------------------------------------------------

def remove_dc_component(H: np.ndarray) -> np.ndarray:
    """
    Remove the DC (mean) component from H(f).

    Subtracting the mean prevents the zero-range IFFT spike that dominates
    range profiles of RX-only noise captures.  For a future TX/RX measurement
    this would remove common-mode bias, leaving only range-varying information.

    NOTE: H(f) from RX-only captures is NOT a radar transfer function.

    Parameters
    ----------
    H : np.ndarray   1-D complex array.

    Returns
    -------
    np.ndarray   complex128, same shape as H, mean subtracted.

    Raises
    ------
    ValueError   If H is empty or not a 1-D array.
    """
    H_arr = np.asarray(H, dtype=np.complex128)
    if H_arr.ndim != 1 or H_arr.size == 0:
        raise ValueError("H must be a non-empty 1-D array")
    return H_arr - np.mean(H_arr)


def normalize_h_magnitude(H: np.ndarray) -> np.ndarray:
    """
    Scale H so that max |H| = 1, preserving phase.

    Useful for comparing H(f) shapes between sweeps regardless of absolute
    gain.  Phase information is retained exactly.

    NOTE: H(f) from RX-only captures is NOT a radar transfer function.

    Parameters
    ----------
    H : np.ndarray   1-D complex array.

    Returns
    -------
    np.ndarray   complex128, max |H| = 1.

    Raises
    ------
    ValueError   If H is empty, not 1-D, or all-zero.
    """
    H_arr = np.asarray(H, dtype=np.complex128)
    if H_arr.ndim != 1 or H_arr.size == 0:
        raise ValueError("H must be a non-empty 1-D array")
    peak = float(np.max(np.abs(H_arr)))
    if peak == 0.0:
        raise ValueError("Cannot normalize: all H values are zero")
    return H_arr / peak


def subtract_reference_h(
    H: np.ndarray,
    H_ref: np.ndarray,
) -> np.ndarray:
    """
    Background subtraction: return H - H_ref (element-wise).

    In a calibrated TX/RX system this removes static background (antenna
    coupling, cable reflections) leaving only target-induced changes.  For
    RX-only noise data the result is still noise; this function prepares the
    pipeline for future calibrated TX/RX measurements.

    NOTE: H(f) from RX-only captures is NOT a radar transfer function.
    Background subtraction on RX-only data is a pipeline validation step only.

    Parameters
    ----------
    H     : np.ndarray   Signal H(f), shape (N,).
    H_ref : np.ndarray   Reference H(f), shape (N,).

    Returns
    -------
    np.ndarray   complex128, H - H_ref, shape (N,).

    Raises
    ------
    ValueError   If H and H_ref have different shapes or are empty.
    """
    H_arr   = np.asarray(H,     dtype=np.complex128)
    ref_arr = np.asarray(H_ref, dtype=np.complex128)
    if H_arr.size == 0:
        raise ValueError("H must not be empty")
    if H_arr.ndim != 1:
        raise ValueError("H must be a 1-D array")
    if H_arr.shape != ref_arr.shape:
        raise ValueError(
            f"Shape mismatch: H has shape {H_arr.shape} "
            f"but H_ref has {ref_arr.shape}"
        )
    return H_arr - ref_arr


def smooth_h_magnitude(H: np.ndarray, window_len: int) -> np.ndarray:
    """
    Smooth |H(f)| with a uniform (boxcar) window, preserving original phase.

    The magnitude is convolved with a normalised boxcar; the original complex
    phase angle is then reapplied.  This reduces fast-varying amplitude noise
    while keeping the frequency structure visible.

    NOTE: H(f) from RX-only captures is NOT a radar transfer function.

    Parameters
    ----------
    H          : np.ndarray   1-D complex array, shape (N,).
    window_len : int          Boxcar length (>= 1 and <= len(H)).

    Returns
    -------
    np.ndarray   complex128, smoothed magnitude * exp(j * original phase).

    Raises
    ------
    ValueError   If H is empty, not 1-D, window_len < 1, or window_len > len(H).
    """
    H_arr = np.asarray(H, dtype=np.complex128)
    if H_arr.ndim != 1 or H_arr.size == 0:
        raise ValueError("H must be a non-empty 1-D array")
    wl = int(window_len)
    if wl < 1:
        raise ValueError(f"window_len must be >= 1; got {wl}")
    if wl > H_arr.size:
        raise ValueError(
            f"window_len ({wl}) must not exceed len(H) ({H_arr.size})"
        )
    kernel = np.ones(wl) / wl
    mag_smooth = np.convolve(np.abs(H_arr), kernel, mode='same')
    return mag_smooth * np.exp(1j * np.angle(H_arr))


# ---------------------------------------------------------------------------
# Range profile analysis
# ---------------------------------------------------------------------------

def estimate_noise_floor_db(profile: np.ndarray) -> float:
    """
    Estimate noise floor as the median |profile| in dB.

    Uses the median rather than the mean so that a few bright range bins
    (noise peaks or future targets) do not bias the estimate.

    Parameters
    ----------
    profile : np.ndarray   1-D real or complex range profile.

    Returns
    -------
    float   Noise floor estimate in dB (re: linear units of |profile|).

    Raises
    ------
    ValueError   If profile is empty or not 1-D.
    """
    arr = np.asarray(profile)
    if arr.ndim != 1 or arr.size == 0:
        raise ValueError("profile must be a non-empty 1-D array")
    return float(20.0 * np.log10(np.median(np.abs(arr)) + 1e-12))


def find_prominent_range_bins(
    range_m: np.ndarray,
    profile: np.ndarray,
    min_prominence_db: float,
) -> np.ndarray:
    """
    Find range bins that exceed the noise floor by >= min_prominence_db.

    Prominence is measured relative to the median noise floor from
    estimate_noise_floor_db.  Returns indices of bins where:
        20*log10(|profile[i]|) >= noise_floor_db + min_prominence_db

    NOTE: In RX-only data these are noise features, NOT physical targets.
    Attributing bins to real objects requires a controlled TX/RX measurement.

    Parameters
    ----------
    range_m           : np.ndarray   Range axis [m], shape (N,).
    profile           : np.ndarray   Range profile (real or complex), shape (N,).
    min_prominence_db : float        Minimum excess above noise floor [dB].

    Returns
    -------
    np.ndarray   int64 array of prominent bin indices (may be empty).

    Raises
    ------
    ValueError   If range_m and profile have different lengths or are empty.
    """
    r_arr = np.asarray(range_m, dtype=np.float64)
    p_arr = np.asarray(profile)
    if r_arr.size == 0:
        raise ValueError("range_m must not be empty")
    if r_arr.ndim != 1 or p_arr.ndim != 1:
        raise ValueError("range_m and profile must be 1-D arrays")
    if r_arr.shape != p_arr.shape:
        raise ValueError(
            f"range_m and profile must have the same shape; "
            f"got {r_arr.shape} vs {p_arr.shape}"
        )
    noise_db  = estimate_noise_floor_db(p_arr)
    threshold_db = noise_db + float(min_prominence_db)
    mag_db = 20.0 * np.log10(np.abs(p_arr) + 1e-12)
    return np.where(mag_db >= threshold_db)[0].astype(np.int64)


def summarize_range_profile(
    range_m: np.ndarray,
    profile: np.ndarray,
) -> dict:
    """
    Compute summary statistics for a range profile.

    NOTE: For RX-only captures the 'peak' is the strongest noise IFFT bin,
    NOT a reflection from a physical target.

    Parameters
    ----------
    range_m : np.ndarray   Range axis [m], 1-D, shape (N,).
    profile : np.ndarray   Range profile (real or complex), 1-D, shape (N,).

    Returns
    -------
    dict with keys:
        peak_range_m        : float   Range of the strongest bin [m].
        peak_magnitude_db   : float   |profile| at the strongest bin [dB].
        noise_floor_db      : float   Median noise floor [dB].
        dynamic_range_db    : float   peak_magnitude_db - noise_floor_db [dB].
        n_bins              : int     Total number of range bins.
        peak_bin_index      : int     Index of the strongest bin.

    Raises
    ------
    ValueError   If range_m and profile have different lengths or are empty.
    """
    r_arr = np.asarray(range_m, dtype=np.float64)
    p_arr = np.asarray(profile)
    if r_arr.size == 0:
        raise ValueError("range_m must not be empty")
    if r_arr.ndim != 1 or p_arr.ndim != 1:
        raise ValueError("range_m and profile must be 1-D arrays")
    if r_arr.shape != p_arr.shape:
        raise ValueError(
            f"range_m and profile must have the same shape; "
            f"got {r_arr.shape} vs {p_arr.shape}"
        )
    mag_db    = 20.0 * np.log10(np.abs(p_arr) + 1e-12)
    peak_idx  = int(np.argmax(mag_db))
    noise_db  = estimate_noise_floor_db(p_arr)
    peak_db   = float(mag_db[peak_idx])

    return {
        "peak_range_m":      float(r_arr[peak_idx]),
        "peak_magnitude_db": peak_db,
        "noise_floor_db":    noise_db,
        "dynamic_range_db":  peak_db - noise_db,
        "n_bins":            int(r_arr.size),
        "peak_bin_index":    peak_idx,
    }
