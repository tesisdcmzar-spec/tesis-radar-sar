"""
Hardware-independent SFCW sweep helper.

Provides frequency-grid building, coherent IQ averaging, H(f) extraction,
SyntheticScan packaging, sweep configuration/result dataclasses, and basic
sweep metrics.  Contains NO bladeRF imports, NO hardware access, NO TX
operations — fully testable with synthetic data.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from simulation.synthetic_scan import SyntheticScan


# ---------------------------------------------------------------------------
# Frequency grid
# ---------------------------------------------------------------------------

def make_frequency_grid(
    f_start_hz: float,
    f_stop_hz: float,
    step_hz: float,
) -> np.ndarray:
    """
    Build a linearly spaced frequency grid.

    Parameters
    ----------
    f_start_hz : float   Start frequency [Hz].
    f_stop_hz  : float   Stop frequency [Hz] (inclusive within half a step).
    step_hz    : float   Step size [Hz].

    Returns
    -------
    np.ndarray   1D float64 array.

    Raises
    ------
    ValueError   If step_hz <= 0, f_stop_hz <= f_start_hz, or the resulting
                 grid would be empty.
    """
    if step_hz <= 0:
        raise ValueError(f"step_hz must be positive; got {step_hz!r}")
    if f_stop_hz <= f_start_hz:
        raise ValueError(
            f"f_stop_hz ({f_stop_hz}) must be strictly greater than "
            f"f_start_hz ({f_start_hz})"
        )
    grid = np.arange(
        f_start_hz, f_stop_hz + 0.5 * step_hz, step_hz, dtype=np.float64
    )
    if grid.size == 0:
        raise ValueError(
            f"Empty frequency grid: start={f_start_hz}, stop={f_stop_hz}, "
            f"step={step_hz}"
        )
    return grid


# ---------------------------------------------------------------------------
# Coherent averaging
# ---------------------------------------------------------------------------

def coherent_average_iq(iq: np.ndarray) -> complex:
    """
    Coherent mean of a 1D complex IQ burst.

    Equivalent to matched-filter integration of a CW tone at DC relative to
    the tuned frequency.  For broadband thermal noise the result converges to
    zero.  For a coherent tone at DC the result recovers the complex phasor.

    Parameters
    ----------
    iq : np.ndarray   1D complex array (any complex dtype).

    Returns
    -------
    complex   Complex128 coherent average.

    Raises
    ------
    ValueError   If iq is not 1D or is empty.
    """
    if iq.ndim != 1:
        raise ValueError(f"iq must be 1-D; got ndim={iq.ndim}")
    if iq.size == 0:
        raise ValueError("iq must not be empty")
    return complex(np.mean(iq.astype(np.complex128)))


# ---------------------------------------------------------------------------
# H(f) extraction
# ---------------------------------------------------------------------------

def extract_h_from_iq_bursts(
    freqs_hz: np.ndarray,
    iq_by_freq: Sequence[np.ndarray],
) -> np.ndarray:
    """
    Extract H(f) by coherently averaging each per-frequency IQ burst.

    Parameters
    ----------
    freqs_hz   : np.ndarray   1D array of N frequencies [Hz].
    iq_by_freq : Sequence     Length-N sequence of 1D complex IQ arrays,
                              one per frequency step.

    Returns
    -------
    np.ndarray   1D complex128 array of shape (N,) — one complex phasor per
                 frequency.

    Raises
    ------
    ValueError   On length mismatch or non-1D IQ arrays.
    """
    freqs = np.asarray(freqs_hz, dtype=np.float64)
    if freqs.ndim != 1 or freqs.size == 0:
        raise ValueError("freqs_hz must be a non-empty 1-D array")
    if len(iq_by_freq) != freqs.size:
        raise ValueError(
            f"Length mismatch: freqs_hz has {freqs.size} element(s) but "
            f"iq_by_freq has {len(iq_by_freq)}"
        )
    H = np.empty(freqs.size, dtype=np.complex128)
    for i, iq in enumerate(iq_by_freq):
        arr = np.asarray(iq)
        if arr.ndim != 1:
            raise ValueError(
                f"iq_by_freq[{i}] must be 1-D; got ndim={arr.ndim}"
            )
        H[i] = coherent_average_iq(arr)
    return H


# ---------------------------------------------------------------------------
# SyntheticScan packaging
# ---------------------------------------------------------------------------

def make_synthetic_scan_from_h(
    freqs_hz: np.ndarray,
    h: np.ndarray,
    x_az_m: float = 0.0,
) -> SyntheticScan:
    """
    Wrap a 1-D H(f) vector into a SyntheticScan with a single azimuth position.

    Parameters
    ----------
    freqs_hz : np.ndarray   1-D frequency grid [Hz], shape (N_f,).
    h        : np.ndarray   1-D complex H(f) vector, shape (N_f,).
    x_az_m   : float        Aperture position [m] (default 0.0).

    Returns
    -------
    SyntheticScan   H has shape (N_f, 1); ready for compute_range_profiles.

    Raises
    ------
    ValueError   On shape mismatches or non-1D inputs.
    """
    freqs = np.asarray(freqs_hz, dtype=np.float64)
    h_arr = np.asarray(h, dtype=np.complex128)
    if freqs.ndim != 1 or freqs.size == 0:
        raise ValueError("freqs_hz must be a non-empty 1-D array")
    if h_arr.ndim != 1:
        raise ValueError(f"h must be 1-D; got ndim={h_arr.ndim}")
    if h_arr.size != freqs.size:
        raise ValueError(
            f"h has {h_arr.size} element(s) but freqs_hz has {freqs.size}"
        )
    return SyntheticScan(
        freqs_hz=freqs,
        x_az_m=np.array([float(x_az_m)]),
        H=h_arr[:, None],        # (N_f, 1)
    )


# ---------------------------------------------------------------------------
# Sweep metrics
# ---------------------------------------------------------------------------

def compute_sweep_metrics(
    freqs_hz: np.ndarray,
    H: np.ndarray,
    c: float = 3e8,
) -> dict:
    """
    Compute basic sweep metrics from H(f).

    Parameters
    ----------
    freqs_hz : np.ndarray   1-D frequency grid [Hz].
    H        : np.ndarray   1-D complex H(f) array.
    c        : float        Propagation speed [m/s] (default 3e8).

    Returns
    -------
    dict with keys:
        bandwidth_hz, bandwidth_mhz, step_hz, step_mhz, n_freqs,
        range_resolution_m, range_resolution_cm,
        unambiguous_range_m,
        peak_freq_hz, peak_freq_mhz, peak_magnitude_db, dynamic_range_db.
    """
    freqs = np.asarray(freqs_hz, dtype=np.float64)
    H_arr = np.asarray(H, dtype=np.complex128)

    bw_hz  = float(freqs[-1] - freqs[0]) if freqs.size > 1 else 0.0
    df_hz  = float(freqs[1] - freqs[0])  if freqs.size > 1 else float("nan")

    range_res_m  = c / (2.0 * bw_hz)   if bw_hz > 0 else float("inf")
    unamb_rng_m  = c / (2.0 * df_hz)   if df_hz > 0 else float("inf")

    mag_db   = 20.0 * np.log10(np.abs(H_arr) + 1e-12)
    peak_idx = int(np.argmax(mag_db))

    return {
        "bandwidth_hz":       bw_hz,
        "bandwidth_mhz":      bw_hz / 1e6,
        "step_hz":            df_hz,
        "step_mhz":           df_hz / 1e6,
        "n_freqs":            int(freqs.size),
        "range_resolution_m": range_res_m,
        "range_resolution_cm":range_res_m * 100.0,
        "unambiguous_range_m":unamb_rng_m,
        "peak_freq_hz":       float(freqs[peak_idx]),
        "peak_freq_mhz":      float(freqs[peak_idx]) / 1e6,
        "peak_magnitude_db":  float(mag_db[peak_idx]),
        "dynamic_range_db":   float(np.max(mag_db) - np.min(mag_db)),
    }


# ---------------------------------------------------------------------------
# Sweep configuration / result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class SweepConfig:
    """Parameters for one SFCW sweep pass (pilot or full)."""
    mode:          str    # 'pilot' or 'full'
    f_start_hz:    float
    f_stop_hz:     float
    step_hz:       float
    n_samples:     int
    sample_rate_hz:float
    bandwidth_hz:  float
    rx_gain_db:    float

    @property
    def n_freqs_expected(self) -> int:
        return int(make_frequency_grid(
            self.f_start_hz, self.f_stop_hz, self.step_hz
        ).size)

    def to_dict(self) -> dict:
        return {
            "mode":            self.mode,
            "f_start_hz":      self.f_start_hz,
            "f_stop_hz":       self.f_stop_hz,
            "step_hz":         self.step_hz,
            "n_freqs_expected":self.n_freqs_expected,
            "n_samples":       self.n_samples,
            "sample_rate_hz":  self.sample_rate_hz,
            "bandwidth_hz":    self.bandwidth_hz,
            "rx_gain_db":      self.rx_gain_db,
        }


@dataclass
class SweepResult:
    """Results from one completed SFCW sweep pass."""
    config:      SweepConfig
    freqs_hz:    np.ndarray   # (N_f,) captured frequencies
    H:           np.ndarray   # (N_f,) complex coherent averages
    n_captured:  int
    n_clipped:   int
    n_failed:    int
    capture_dir: str
    errors:      list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return (
            self.n_captured == len(self.freqs_hz)
            and self.n_failed == 0
            and self.n_clipped == 0
        )

    def to_dict(self) -> dict:
        return {
            "mode":             self.config.mode,
            "n_freqs_expected": len(self.freqs_hz),
            "n_captured":       self.n_captured,
            "n_clipped":        self.n_clipped,
            "n_failed":         self.n_failed,
            "success":          self.success,
            "capture_dir":      self.capture_dir,
            "errors":           self.errors,
        }
