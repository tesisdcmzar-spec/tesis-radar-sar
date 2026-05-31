"""
IFFT-based range profile from SFCW frequency response.

Range axis convention: range_m[k] = c * k / (2 * N_fft * df)
which equals the one-way range to a target that produces a peak at bin k.
"""
from __future__ import annotations

import numpy as np
from simulation.synthetic_scan import SyntheticScan


def compute_range_profiles(
    scan: SyntheticScan,
    padding_factor: int = 4,
    window: bool = True,
    c: float = 3e8,
) -> tuple:
    """
    IFFT along frequency axis to produce range-compressed profiles.

    Parameters
    ----------
    scan           : SyntheticScan
    padding_factor : IFFT zero-padding factor (≥1, integer)
    window         : apply Hanning window across frequency before IFFT
    c              : propagation speed [m/s]

    Returns
    -------
    range_m  : 1D array, one-way range bins [m], shape (N_fft//2,)
    profiles : complex array (N_fft//2, N_az), range-compressed data
    """
    N_f = len(scan.freqs_hz)
    N_fft = N_f * padding_factor

    H = scan.H.copy()
    if window:
        w = np.hanning(N_f)
        H = H * w[:, None]

    # IFFT along frequency axis (axis 0); output length N_fft via zero-padding
    h = np.fft.ifft(H, n=N_fft, axis=0)

    # Keep only the causal (positive-delay) half
    h = h[: N_fft // 2, :]

    # Delay axis: tau[k] = k / (N_fft * df)
    # Range axis: r = c * tau / 2  (one-way range)
    df = scan.f_step_hz
    tau = np.arange(N_fft // 2) / (N_fft * df)
    range_m = c * tau / 2.0

    return range_m, h
