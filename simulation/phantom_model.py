"""
Synthetic phantom: point targets in 2D (cross-range x, down-range z).

Computes the ideal complex SFCW frequency response H(f, x_az) for a
monostatic configuration (co-located TX/RX).

Signal model (single target at one-way range R from aperture):
  H(f) = A * exp(-j * 4pi * f * R / c)
  where R = sqrt((x_az - x_t)^2 + z_t^2)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass
class PointTarget:
    x_m: float          # cross-range position [m]
    z_m: float          # down-range (depth) position [m]
    amplitude: float = 1.0


@dataclass
class PhantomModel:
    targets: List[PointTarget]
    c: float = 3e8      # propagation speed [m/s]

    def frequency_response(
        self,
        freqs_hz: np.ndarray,
        x_az: np.ndarray,
        noise_std: float = 0.0,
        rng: Optional[np.random.Generator] = None,
    ) -> np.ndarray:
        """
        H[n_freq, n_az] = sum_targets A * exp(-j*4pi*f*R/c).

        Parameters
        ----------
        freqs_hz : (N_f,)  frequency grid [Hz]
        x_az     : (N_az,) aperture positions [m]
        noise_std: std of additive complex Gaussian noise (0 = noiseless)

        Returns
        -------
        H : complex128 array of shape (N_f, N_az)
        """
        N_f = len(freqs_hz)
        N_az = len(x_az)
        H = np.zeros((N_f, N_az), dtype=complex)

        for t in self.targets:
            # one-way range from each aperture position to this target
            R = np.sqrt((x_az - t.x_m) ** 2 + t.z_m ** 2)  # (N_az,)
            # two-way phase delay: phi = 4pi * f * R / c
            phase = -4 * np.pi * np.outer(freqs_hz, R) / self.c  # (N_f, N_az)
            H += t.amplitude * np.exp(1j * phase)

        if noise_std > 0.0:
            rng = rng or np.random.default_rng()
            noise = rng.standard_normal(H.shape) + 1j * rng.standard_normal(H.shape)
            H += noise * (noise_std / np.sqrt(2))

        return H


def phantom_from_config(cfg: dict) -> PhantomModel:
    """Build a PhantomModel from a simulation YAML config dict."""
    rcs = float(cfg["phantom"].get("target_rcs", 1.0))
    targets = [
        PointTarget(x_m=float(t["x_m"]), z_m=float(t["z_m"]), amplitude=rcs)
        for t in cfg["phantom"]["targets"]
    ]
    c = float(cfg["reconstruction"].get("speed_of_light", 3e8))
    return PhantomModel(targets=targets, c=c)
