"""
Synthetic SFCW scan: generates H(f, x_az) data cube from a PhantomModel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from simulation.phantom_model import PhantomModel


@dataclass
class SyntheticScan:
    freqs_hz: np.ndarray    # (N_f,)  frequency grid [Hz]
    x_az_m: np.ndarray      # (N_az,) aperture positions [m]
    H: np.ndarray           # complex (N_f, N_az)  frequency response

    @property
    def bandwidth_hz(self) -> float:
        return float(self.freqs_hz[-1] - self.freqs_hz[0])

    @property
    def f_step_hz(self) -> float:
        return float(self.freqs_hz[1] - self.freqs_hz[0])

    @property
    def shape(self) -> tuple:
        return self.H.shape


def make_scan(
    phantom: PhantomModel,
    f_start_hz: float,
    f_stop_hz: float,
    f_step_hz: float,
    x_start_m: float,
    x_stop_m: float,
    x_step_m: float,
    noise_std: float = 0.0,
    rng: Optional[np.random.Generator] = None,
) -> SyntheticScan:
    """Build a SyntheticScan from explicit SFCW and aperture parameters."""
    freqs = np.arange(f_start_hz, f_stop_hz + f_step_hz * 0.5, f_step_hz)
    x_az = np.arange(x_start_m, x_stop_m + x_step_m * 0.5, x_step_m)
    H = phantom.frequency_response(freqs, x_az, noise_std=noise_std, rng=rng)
    return SyntheticScan(freqs_hz=freqs, x_az_m=x_az, H=H)


def scan_from_config(
    phantom: PhantomModel,
    cfg: dict,
    noise_std: float = 0.0,
    rng: Optional[np.random.Generator] = None,
) -> SyntheticScan:
    """Build a SyntheticScan from a simulation YAML config dict."""
    sfcw = cfg["sfcw"]
    az = cfg["azimuth"]
    return make_scan(
        phantom=phantom,
        f_start_hz=float(sfcw["f_start_hz"]),
        f_stop_hz=float(sfcw["f_stop_hz"]),
        f_step_hz=float(sfcw["f_step_hz"]),
        x_start_m=float(az["x_start_m"]),
        x_stop_m=float(az["x_stop_m"]),
        x_step_m=float(az["x_step_m"]),
        noise_std=noise_std,
        rng=rng,
    )
