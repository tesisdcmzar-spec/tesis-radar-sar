"""
IFFT-based range profile from SFCW frequency response.

Range axis convention: range_m[k] = c * k / (2 * N_fft * df)
which equals the one-way range to a target that produces a peak at bin k.

Window options and their resolution/sidelobe tradeoff (2 GHz BW):
  'none'     -> rectangular: 7.5 cm range resolution, -13 dB sidelobes
  'hanning'  -> Hanning:    ~15 cm range resolution, -31 dB sidelobes
  'blackman' -> Blackman:   ~22 cm range resolution, -58 dB sidelobes
"""
from __future__ import annotations

import numpy as np
from simulation.synthetic_scan import SyntheticScan

_WINDOWS = {
    'none':     lambda n: np.ones(n),
    'hanning':  np.hanning,
    'blackman': np.blackman,
}


def compute_range_profiles(
    scan: SyntheticScan,
    padding_factor: int = 4,
    window: str = 'hanning',
    c: float = 3e8,
) -> tuple:
    """
    IFFT along frequency axis to produce range-compressed profiles.

    Parameters
    ----------
    scan           : SyntheticScan
    padding_factor : IFFT zero-padding factor (>=1, integer)
    window         : taper applied across frequency before IFFT.
                     'none' (rectangular), 'hanning', or 'blackman'.
    c              : propagation speed [m/s]

    Returns
    -------
    range_m  : 1D array, one-way range bins [m], shape (N_fft//2,)
    profiles : complex array (N_fft//2, N_az), range-compressed data
    """
    N_f = len(scan.freqs_hz)
    N_fft = N_f * padding_factor

    H = scan.H.copy()
    win_fn = _WINDOWS.get(str(window).lower(), np.hanning)
    w = win_fn(N_f)
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
