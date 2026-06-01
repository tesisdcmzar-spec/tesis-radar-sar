"""
Distance-domain relative contrast profile for OFDM radar.

Computes a relative dielectric-contrast indicator versus distance from
OFDM channel-difference measurements.

Pipeline
--------
  H_delta[k]  = H_object[k] - H_background[k]
  CIR_delta   = IFFT(H_delta * window)
  contrast(r) = |CIR_delta(r)| / max(|CIR_delta|)

Scientific context
------------------
This module produces a "relative dielectric-contrast profile" or
"perfil de contraste dielelectrico relativo".

It is NOT an absolute dielectric permittivity map.
A calibrated forward model and a known phantom/reference measurement
are required to convert contrast profiles to absolute epsilon_r(r).
Two-way radar propagation (monostatic) is assumed unless specified.

All functions are hardware-independent. No bladeRF import. No USB.
Safe to call offline.
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "compute_delta_channel",
    "window_channel",
    "channel_to_delay_profile",
    "delay_axis_s",
    "range_axis_m",
    "relative_contrast_profile",
    "find_strongest_contrast_peak",
    "summarize_contrast_profile",
]

# Speed of light in free space [m/s]
_C = 3.0e8


# ---------------------------------------------------------------------------
# Channel difference
# ---------------------------------------------------------------------------

def compute_delta_channel(
    H_object: np.ndarray,
    H_background: np.ndarray,
) -> np.ndarray:
    """
    Compute the per-subcarrier channel difference H_delta = H_object - H_background.

    Removes the background response (cable, antenna, room clutter) to isolate
    the contribution from the test object.

    This is NOT absolute permittivity mapping.  The result represents the
    relative electromagnetic contrast introduced by the object.

    Parameters
    ----------
    H_object     : complex array (n,). Channel estimate with object present.
    H_background : complex array (n,). Channel estimate without object.

    Returns
    -------
    H_delta : complex array (n,). Channel difference.

    Raises
    ------
    ValueError
        If H_object and H_background have different shapes.
    """
    H_object = np.asarray(H_object, dtype=complex)
    H_background = np.asarray(H_background, dtype=complex)
    if H_object.shape != H_background.shape:
        raise ValueError(
            f"H_object shape {H_object.shape} != H_background shape {H_background.shape}."
        )
    return H_object - H_background


# ---------------------------------------------------------------------------
# Windowing
# ---------------------------------------------------------------------------

def window_channel(
    H: np.ndarray,
    window: str = "hanning",
) -> np.ndarray:
    """
    Apply a spectral window to H[k] before IFFT.

    Windowing reduces range sidelobes at the cost of range resolution.

    Parameters
    ----------
    H      : complex array (n,). Channel estimate.
    window : str -- 'hanning', 'blackman', or 'none' (rectangular).

    Returns
    -------
    H_windowed : complex array (n,). Same shape as H.
    """
    H = np.asarray(H, dtype=complex)
    n = len(H)
    _windows = {
        "hanning":  np.hanning,
        "blackman": np.blackman,
        "none":     lambda m: np.ones(m),
    }
    w_fn = _windows.get(window.lower(), lambda m: np.ones(m))
    return H * w_fn(n)


# ---------------------------------------------------------------------------
# Delay profile
# ---------------------------------------------------------------------------

def channel_to_delay_profile(
    H: np.ndarray,
    window: str = "hanning",
) -> np.ndarray:
    """
    Compute Channel Impulse Response (CIR) via windowed IFFT of H[k].

    The peak of |CIR(tau)| gives the dominant propagation delay.
    For a monostatic radar, delay tau corresponds to range R = c*tau/2.

    This function returns the raw complex CIR.  Use relative_contrast_profile()
    to normalize the magnitude to a [0, 1] indicator.

    Parameters
    ----------
    H      : complex array (n,). Channel estimate.
    window : str -- 'hanning', 'blackman', or 'none'.

    Returns
    -------
    cir : complex array (n,). Channel impulse response.
    """
    H_win = window_channel(H, window=window)
    # Scale by N so amplitude is proportional to H magnitude (not N-dependent)
    return np.fft.ifft(H_win) * len(H)


# ---------------------------------------------------------------------------
# Delay and range axes
# ---------------------------------------------------------------------------

def delay_axis_s(
    n: int,
    bandwidth_hz_or_sample_rate_hz: float,
    mode: str = "frequency_response",
) -> np.ndarray:
    """
    Compute the delay axis [s] for a CIR output.

    Two modes are supported:

    frequency_response
        H(f) is defined at n uniform frequency points with spacing
        df = bandwidth_hz / n (or total_BW / n).
        IFFT gives n delay points with spacing dt = 1 / (n * df) = 1 / BW.
        Total delay range: T = n / BW = n * dt.
        Use this mode when the input is a frequency-domain channel estimate.
        Pass bandwidth_hz_or_sample_rate_hz = total bandwidth [Hz].

    time_domain
        IQ samples at sample rate fs [samples/s].
        Each sample has period dt = 1 / fs.
        Total delay range: T = n / fs.
        Use this mode when the input is raw IQ.
        Pass bandwidth_hz_or_sample_rate_hz = sample_rate_hz.

    Parameters
    ----------
    n                               : int. Number of delay bins.
    bandwidth_hz_or_sample_rate_hz  : float. See mode description above.
    mode                            : 'frequency_response' or 'time_domain'.

    Returns
    -------
    delay_s : float array (n,). Delay values [s].

    Raises
    ------
    ValueError
        If mode is unknown or bandwidth_hz_or_sample_rate_hz is <= 0.
    """
    if bandwidth_hz_or_sample_rate_hz <= 0:
        raise ValueError(
            f"bandwidth_hz_or_sample_rate_hz must be > 0, "
            f"got {bandwidth_hz_or_sample_rate_hz}"
        )
    mode_lower = mode.lower()
    if mode_lower == "frequency_response":
        # dt = 1 / BW (each CIR bin spans 1/BW seconds)
        dt = 1.0 / bandwidth_hz_or_sample_rate_hz
    elif mode_lower == "time_domain":
        # dt = 1 / fs
        dt = 1.0 / bandwidth_hz_or_sample_rate_hz
    else:
        raise ValueError(
            f"Unknown mode {mode!r}. Use 'frequency_response' or 'time_domain'."
        )
    return np.arange(n) * dt


def range_axis_m(
    delay_s: np.ndarray,
    c: float = _C,
    two_way: bool = True,
) -> np.ndarray:
    """
    Convert a delay axis [s] to a range axis [m].

    For monostatic (two-way) radar:
        range = c * delay / 2

    For one-way propagation:
        range = c * delay

    Parameters
    ----------
    delay_s  : float array (n,). Delay axis [s].
    c        : float. Propagation speed [m/s]. Default: 3e8 (free space).
    two_way  : bool. True for monostatic radar (default). False for one-way.

    Returns
    -------
    range_m : float array (n,). Range values [m].
    """
    delay_s = np.asarray(delay_s, dtype=float)
    return delay_s * c / (2.0 if two_way else 1.0)


# ---------------------------------------------------------------------------
# Contrast profile
# ---------------------------------------------------------------------------

def relative_contrast_profile(
    cir_delta: np.ndarray,
    normalize: bool = True,
) -> np.ndarray:
    """
    Compute the relative dielectric-contrast profile from CIR_delta.

    Returns |CIR_delta|, optionally normalized to [0, 1] by the maximum value.

    This is NOT absolute permittivity.  The profile indicates the relative
    strength of the electromagnetic contrast introduced by the object at each
    delay/range bin, compared to the background.

    Parameters
    ----------
    cir_delta : complex array (n,). Channel-difference impulse response.
    normalize : bool. If True, divide by max(|CIR_delta|). Default: True.

    Returns
    -------
    contrast : float array (n,). Relative contrast indicator in [0, 1].
    """
    cir_delta = np.asarray(cir_delta)
    magnitude = np.abs(cir_delta)
    if normalize:
        peak = float(np.max(magnitude))
        if peak < 1e-15:
            return np.zeros_like(magnitude, dtype=float)
        return magnitude / peak
    return magnitude


# ---------------------------------------------------------------------------
# Peak detection
# ---------------------------------------------------------------------------

def find_strongest_contrast_peak(
    range_m: np.ndarray,
    profile: np.ndarray,
    causal_only: bool = True,
) -> tuple[float, int]:
    """
    Find the range of the strongest contrast peak.

    Only the causal (positive-delay) half of the CIR is searched by default,
    since physical reflectors produce positive-delay echoes.

    Parameters
    ----------
    range_m     : float array (n,). Range axis [m].
    profile     : float array (n,). Relative contrast profile.
    causal_only : bool. If True, search only range_m >= 0 (first n//2 samples).

    Returns
    -------
    (peak_range_m, peak_idx) : tuple of float and int.

    Raises
    ------
    ValueError
        If range_m and profile have different lengths.
    """
    range_m = np.asarray(range_m, dtype=float)
    profile = np.asarray(profile, dtype=float)
    if len(range_m) != len(profile):
        raise ValueError(
            f"range_m length {len(range_m)} != profile length {len(profile)}."
        )
    n = len(profile)
    search_n = n // 2 if (causal_only and n >= 2) else n
    if search_n == 0:
        return 0.0, 0
    peak_idx = int(np.argmax(profile[:search_n]))
    peak_range_m = float(range_m[peak_idx]) if n > peak_idx else 0.0
    return peak_range_m, peak_idx


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def summarize_contrast_profile(
    range_m: np.ndarray,
    profile: np.ndarray,
    expected_distance_m: float | None = None,
) -> dict:
    """
    Compute summary statistics for a relative contrast profile.

    Parameters
    ----------
    range_m             : float array (n,). Range axis [m].
    profile             : float array (n,). Relative contrast (0 to 1).
    expected_distance_m : float or None. Known object distance for validation.

    Returns
    -------
    summary : dict with keys:
        n_bins, range_min_m, range_max_m, peak_range_m, peak_idx,
        peak_contrast, mean_contrast, [expected_distance_m, range_error_m,
        within_one_bin]

    Notes
    -----
    This summary describes a RELATIVE contrast indicator, NOT an absolute
    dielectric permittivity.  Calibration against a known phantom/reference
    is required for epsilon_r estimation.
    """
    range_m = np.asarray(range_m, dtype=float)
    profile = np.asarray(profile, dtype=float)
    n = len(profile)
    if n == 0:
        return {"n_bins": 0, "error": "empty profile"}

    peak_range_m, peak_idx = find_strongest_contrast_peak(range_m, profile)
    peak_contrast = float(profile[peak_idx]) if n > peak_idx else 0.0

    # Range bin size
    dr = float(range_m[1] - range_m[0]) if n > 1 else 0.0

    summary: dict = {
        "n_bins": n,
        "range_min_m": float(range_m[0]),
        "range_max_m": float(range_m[-1]),
        "range_bin_m": dr,
        "peak_range_m": peak_range_m,
        "peak_idx": peak_idx,
        "peak_contrast": peak_contrast,
        "mean_contrast": float(np.mean(profile)),
        "note": (
            "relative contrast -- not absolute permittivity. "
            "Calibration required for epsilon_r estimation."
        ),
    }

    if expected_distance_m is not None:
        err = abs(peak_range_m - expected_distance_m)
        within_one_bin = dr > 0 and err <= dr
        summary["expected_distance_m"] = float(expected_distance_m)
        summary["range_error_m"] = float(err)
        summary["within_one_bin"] = bool(within_one_bin)

    return summary
