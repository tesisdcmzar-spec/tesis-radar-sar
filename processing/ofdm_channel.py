"""
OFDM channel estimation functions for UWB-OFDM-SAR.

All functions are hardware-independent. No bladeRF import. No USB. No RF.
Safe to run offline.

Architecture context
--------------------
The UWB-OFDM-SAR system transmits a known OFDM probing waveform X[k] and
receives the echo Y[k] after CP removal and FFT.  The per-subcarrier
channel estimate is:

    H[k] = Y[k] / X[k]

Repeating this over multiple RF center-frequency blocks (to overcome the
bladeRF instantaneous bandwidth limit) and over multiple azimuth positions
yields the full data cube H(f, x_az), which feeds range-profile computation
and SAR backprojection.

Docstring safe-use labels
--------------------------
  Baseband            -- operates on complex baseband IQ (not absolute RF).
  RF-frequency-aware  -- uses absolute RF frequency for phase/delay.
  Simulation-only     -- not for direct hardware output.
  Hardware-compatible -- suitable with real bladeRF IQ captures.
  No hardware         -- safe without any SDR connected.
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "generate_bpsk_pilots",
    "generate_qpsk_pilots",
    "allocate_active_subcarriers",
    "make_ofdm_symbol",
    "remove_cyclic_prefix",
    "fft_ofdm_symbol",
    "estimate_channel_rx_tx",
    "channel_impulse_response",
    "unwrap_phase_vs_frequency",
    "estimate_group_delay",
    "estimate_delay_peak",
    "estimate_range_from_delay",
    "simulate_ofdm_channel_from_paths",
    "summarize_ofdm_channel",
]

# ---------------------------------------------------------------------------
# Pilot (known symbol) generation
# ---------------------------------------------------------------------------

def generate_bpsk_pilots(n_subcarriers: int, seed: int | None = None) -> np.ndarray:
    """
    Generate a BPSK pilot sequence (+1 or -1) for use as known OFDM symbols.

    Baseband. No hardware. Simulation-compatible and hardware-compatible.
    Deterministic when seed is provided.

    Parameters
    ----------
    n_subcarriers : int   Number of active subcarriers.
    seed          : int or None.  Fixed seed for reproducibility.

    Returns
    -------
    X : complex128 array, shape (n_subcarriers,), values in {+1+0j, -1+0j}.
    """
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, size=n_subcarriers)
    return (2 * bits - 1).astype(np.complex128)


def generate_qpsk_pilots(n_subcarriers: int, seed: int | None = None) -> np.ndarray:
    """
    Generate a QPSK pilot sequence for use as known OFDM symbols.

    Each symbol has unit magnitude and phase in {pi/4, 3pi/4, 5pi/4, 7pi/4}.
    Baseband. No hardware. Simulation-compatible and hardware-compatible.

    Parameters
    ----------
    n_subcarriers : int
    seed          : int or None

    Returns
    -------
    X : complex128 array, shape (n_subcarriers,), |X[k]| == 1 for all k.
    """
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, 4, size=n_subcarriers)
    phases = np.pi / 4.0 * (2 * idx + 1)
    return np.exp(1j * phases)


# ---------------------------------------------------------------------------
# Subcarrier allocation
# ---------------------------------------------------------------------------

def allocate_active_subcarriers(
    n_fft: int,
    n_active: int,
    dc_null: bool = True,
    guard_bins: int = 0,
) -> np.ndarray:
    """
    Return sorted indices of active (non-zero) OFDM subcarriers in FFT ordering.

    The active region consists of the central n_active subcarriers in standard FFT
    ordering: positive bins [1 .. n_active//2] and negative bins
    [n_fft - n_active//2 .. n_fft - 1].  guard_bins removes the outermost
    guard_bins subcarriers from each half (the ones closest to filter roll-off).

    Baseband. No hardware. Simulation-compatible and hardware-compatible.

    Parameters
    ----------
    n_fft      : int   DFT size.
    n_active   : int   Subcarriers in the active region before guard removal.
    dc_null    : bool  If True, exclude DC bin (index 0).
    guard_bins : int   Guard bins to remove from each edge of each half.

    Returns
    -------
    indices : int array, sorted active subcarrier indices in [0, n_fft).
    """
    if n_active > n_fft:
        raise ValueError(f"n_active ({n_active}) must be <= n_fft ({n_fft})")
    half = n_active // 2

    pos_end = half - guard_bins    # inclusive, positive-frequency half
    neg_start = n_fft - half + guard_bins  # inclusive, negative-frequency half

    indices: list[np.ndarray] = []

    if pos_end >= 1:
        indices.append(np.arange(1, pos_end + 1))
    if neg_start <= n_fft - 1:
        indices.append(np.arange(neg_start, n_fft))
    if not dc_null:
        indices.append(np.array([0], dtype=int))

    if not indices:
        return np.array([], dtype=int)
    return np.sort(np.concatenate(indices))


# ---------------------------------------------------------------------------
# OFDM symbol construction
# ---------------------------------------------------------------------------

def make_ofdm_symbol(
    freq_domain: np.ndarray,
    n_fft: int,
    cp_len: int,
) -> np.ndarray:
    """
    Build a time-domain OFDM symbol with cyclic prefix from a frequency-domain vector.

    Inactive subcarriers (DC, guard, unused) must already be zero in freq_domain.

    Baseband. No hardware. Simulation-compatible and hardware-compatible.

    Parameters
    ----------
    freq_domain : complex array, shape (n_fft,).  Full FFT-bin vector.
    n_fft       : int   DFT size.  Must equal len(freq_domain).
    cp_len      : int   Cyclic-prefix length in samples (>= 0).

    Returns
    -------
    tx : complex array, shape (cp_len + n_fft,).
         First cp_len samples are the CP (= last cp_len samples of IFFT output).
    """
    if len(freq_domain) != n_fft:
        raise ValueError(
            f"freq_domain length {len(freq_domain)} != n_fft {n_fft}"
        )
    if cp_len < 0:
        raise ValueError("cp_len must be >= 0")
    body = np.fft.ifft(freq_domain, n=n_fft)
    cp = body[-cp_len:] if cp_len > 0 else np.array([], dtype=complex)
    return np.concatenate([cp, body])


def remove_cyclic_prefix(
    rx_time: np.ndarray,
    cp_len: int,
    n_fft: int,
) -> np.ndarray:
    """
    Strip the cyclic prefix from a received OFDM symbol.

    Requires prior frame synchronization (correct start-of-symbol alignment).
    Baseband. No hardware. Simulation-compatible and hardware-compatible.

    Parameters
    ----------
    rx_time : complex array, length >= cp_len + n_fft.
    cp_len  : int   CP samples to discard.
    n_fft   : int   Samples to keep after the CP.

    Returns
    -------
    payload : complex array, shape (n_fft,).
    """
    if len(rx_time) < cp_len + n_fft:
        raise ValueError(
            f"rx_time length {len(rx_time)} < cp_len+n_fft = {cp_len + n_fft}"
        )
    return rx_time[cp_len: cp_len + n_fft]


def fft_ofdm_symbol(rx_no_cp: np.ndarray) -> np.ndarray:
    """
    FFT an OFDM payload (after CP removal) to obtain per-subcarrier values.

    Baseband. No hardware. Simulation-compatible and hardware-compatible.

    Parameters
    ----------
    rx_no_cp : complex array, shape (n_fft,).

    Returns
    -------
    Y : complex array, shape (n_fft,).  Per-subcarrier received values.
    """
    return np.fft.fft(rx_no_cp)


# ---------------------------------------------------------------------------
# Channel estimation
# ---------------------------------------------------------------------------

def estimate_channel_rx_tx(
    rx_freq: np.ndarray,
    tx_freq: np.ndarray,
    eps: float = 1e-12,
) -> np.ndarray:
    """
    Per-subcarrier channel estimation: H[k] = Y[k] / X[k].

    Subcarriers where |X[k]| < eps are treated as inactive; H[k] = 0 there.

    Baseband. No hardware. Simulation-compatible and hardware-compatible.

    Parameters
    ----------
    rx_freq : complex array (n_fft,).  Y[k]: received per-subcarrier values.
    tx_freq : complex array (n_fft,).  X[k]: known transmitted pilot values.
    eps     : float.  Magnitude threshold protecting against divide-by-zero.

    Returns
    -------
    H : complex array (n_fft,).  Zero at inactive subcarriers.
    """
    if rx_freq.shape != tx_freq.shape:
        raise ValueError("rx_freq and tx_freq must have the same shape")
    active = np.abs(tx_freq) >= eps
    H = np.zeros_like(rx_freq, dtype=complex)
    H[active] = rx_freq[active] / tx_freq[active]
    return H


# ---------------------------------------------------------------------------
# Channel characterization
# ---------------------------------------------------------------------------

def channel_impulse_response(
    H: np.ndarray,
    window: str = "hanning",
) -> np.ndarray:
    """
    Channel impulse response (CIR) via windowed IFFT of H[k].

    Time-axis resolution = 1/Fs where Fs = n_fft * df (subcarrier spacing).
    Peak location gives propagation delay.

    Baseband. No hardware. Simulation-compatible and hardware-compatible.

    Parameters
    ----------
    H      : complex array, shape (n_fft,).  Channel estimate.
    window : str  -- 'hanning', 'blackman', or 'none' (rectangular).

    Returns
    -------
    cir : complex array, shape (n_fft,).
    """
    n = len(H)
    _windows = {"hanning": np.hanning, "blackman": np.blackman}
    w = _windows.get(window, lambda n: np.ones(n))(n)
    return np.fft.ifft(H * w)


def unwrap_phase_vs_frequency(H: np.ndarray) -> np.ndarray:
    """
    Unwrap phase of H[k] across subcarriers.

    Baseband. No hardware. Simulation-compatible.

    Returns
    -------
    phase_unwrapped : float array (n_fft,), radians.
    """
    return np.unwrap(np.angle(H))


def estimate_group_delay(
    freqs_hz: np.ndarray,
    H: np.ndarray,
) -> np.ndarray:
    """
    Estimate group delay tau_g(f) = -d(phase)/d(omega) from H[k].

    For a single-path channel with delay tau, group delay is constant = tau.

    RF-frequency-aware. No hardware. Simulation-compatible.

    Parameters
    ----------
    freqs_hz : float array (n,).  Absolute RF frequencies [Hz].
    H        : complex array (n,).  Channel estimate at those frequencies.

    Returns
    -------
    tau_g : float array (n,), group delay [s].
    """
    phase = np.unwrap(np.angle(H))
    omega = 2.0 * np.pi * freqs_hz
    return -np.gradient(phase, omega)


def estimate_delay_peak(
    cir: np.ndarray,
    sample_rate_hz: float,
) -> float:
    """
    Estimate propagation delay from the peak of the CIR.

    Baseband. No hardware. Simulation-compatible and hardware-compatible.

    Parameters
    ----------
    cir            : complex array (n_fft,).  Output of channel_impulse_response.
    sample_rate_hz : float.  Fs = n_fft * df [Hz].

    Returns
    -------
    delay_s : float.  Estimated one-way delay [s] (positive, causal).
    """
    peak_idx = int(np.argmax(np.abs(cir)))
    n = len(cir)
    if peak_idx > n // 2:
        peak_idx -= n
    return peak_idx / sample_rate_hz


def estimate_range_from_delay(
    delay_s: float,
    c: float = 3e8,
    two_way: bool = True,
) -> float:
    """
    Convert a propagation delay to a physical range.

    RF-frequency-aware. No hardware. Simulation-compatible and hardware-compatible.

    Parameters
    ----------
    delay_s : float.  Propagation delay [s].
    c       : float.  Propagation speed [m/s].
    two_way : bool.  True -> monostatic (TX=RX): range = c*tau/2.
                     False -> one-way: range = c*tau.

    Returns
    -------
    range_m : float [m].
    """
    return delay_s * c / (2.0 if two_way else 1.0)


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------

def simulate_ofdm_channel_from_paths(
    freqs_hz: np.ndarray,
    paths: list[tuple[complex, float]],
    two_way: bool = True,
) -> np.ndarray:
    """
    Simulate H(f) for a set of point scatterers.

    Free-space, non-dispersive model.  For lossy media, apply Cole-Cole
    attenuation factors externally before calling this function.

    RF-frequency-aware. Simulation-only. No hardware.

    Parameters
    ----------
    freqs_hz : float array (n_freq,).  Absolute RF frequencies [Hz].
    paths    : list of (amplitude: complex, one_way_range_m: float).
    two_way  : bool.  True for monostatic radar (TX=RX at same position).
               H[k] = sum_i  a_i * exp(-j * 4*pi * f_k * R_i / c)  (two-way)
               H[k] = sum_i  a_i * exp(-j * 2*pi * f_k * R_i / c)  (one-way)

    Returns
    -------
    H : complex array (n_freq,).
    """
    factor = 4.0 * np.pi / 3e8 if two_way else 2.0 * np.pi / 3e8
    H = np.zeros(len(freqs_hz), dtype=complex)
    for amp, range_m in paths:
        H += amp * np.exp(-1j * factor * freqs_hz * range_m)
    return H


def summarize_ofdm_channel(
    H: np.ndarray,
    freqs_hz: np.ndarray | None = None,
    cir: np.ndarray | None = None,
    sample_rate_hz: float | None = None,
) -> dict:
    """
    Compute summary statistics for a channel estimate H[k].

    Baseband / RF-frequency-aware (if freqs_hz provided). No hardware.
    Simulation-compatible and hardware-compatible.

    Parameters
    ----------
    H             : complex array (n_subcarriers,).
    freqs_hz      : optional float array (n_subcarriers,).  For group delay.
    cir           : optional complex array.  Pre-computed CIR.
    sample_rate_hz: optional float.  Converts CIR peak index to delay [s].

    Returns
    -------
    summary : dict with keys:
        n_subcarriers, mag_mean, mag_max, mag_min, mag_db_range,
        phase_range_rad, cir_peak_idx, cir_peak_magnitude,
        [delay_s, range_m, group_delay_mean_s]
    """
    mag = np.abs(H)
    phase = np.angle(H)
    mag_max = float(np.max(mag))
    mag_min = float(np.min(mag))
    mag_db_range = (
        20.0 * np.log10(mag_max / max(mag_min, 1e-15)) if mag_max > 0 else 0.0
    )

    summary: dict = {
        "n_subcarriers": int(len(H)),
        "mag_mean": float(np.mean(mag)),
        "mag_max": mag_max,
        "mag_min": mag_min,
        "mag_db_range": mag_db_range,
        "phase_range_rad": float(float(np.max(phase)) - float(np.min(phase))),
    }

    if cir is None:
        cir = channel_impulse_response(H)
    cir_mag = np.abs(cir)
    peak_idx = int(np.argmax(cir_mag))
    summary["cir_peak_idx"] = peak_idx
    summary["cir_peak_magnitude"] = float(cir_mag[peak_idx])

    if sample_rate_hz is not None:
        delay_s = estimate_delay_peak(cir, sample_rate_hz)
        summary["delay_s"] = float(delay_s)
        summary["range_m"] = float(estimate_range_from_delay(delay_s))

    if freqs_hz is not None and len(freqs_hz) == len(H):
        gd = estimate_group_delay(freqs_hz, H)
        summary["group_delay_mean_s"] = float(np.mean(gd))

    return summary
