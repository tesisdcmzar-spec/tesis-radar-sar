"""
UWB-OFDM-SAR offline simulator.

Hardware-independent. No bladeRF. No USB. No RF. No motors.
Safe to run offline. No clinical claims.

Architecture
------------
For each azimuth position x_m and each RF block center frequency f_c,b:
  1. Generate known OFDM pilot symbol X_b[k] over active subcarriers.
  2. Simulate received echo Y_b[k, x_m] from point scatterers.
  3. Estimate H_b[k, x_m] = Y_b[k, x_m] / X_b[k].

After all blocks and positions:
  4. Assemble H(f, x_az) from all valid blocks (stitched in frequency).
  5. IFFT over frequency -> range profiles per azimuth position.
  6. Near-field backprojection -> 2D reflectivity image.

Limitations (simulation simplifications)
-----------------------------------------
- Free-space, non-dispersive propagation model (constant c = 3e8 m/s).
- Dispersive lossy media (e.g. biological tissue) require Cole-Cole permittivity
  factors applied per frequency.  This can be layered on top of this simulator
  by weighting each path's amplitude with a frequency-dependent attenuation term.
- No thermal noise model beyond additive Gaussian.
- No azimuth squint or Doppler effects.
- Not a validated clinical imaging tool.
- Result: detection of dielectric contrast in controlled simulation, not diagnosis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from processing.ofdm_channel import (
    generate_bpsk_pilots,
    allocate_active_subcarriers,
    estimate_channel_rx_tx,
    channel_impulse_response,
)


# ---------------------------------------------------------------------------
# Parameter and target data structures
# ---------------------------------------------------------------------------

@dataclass
class OFDMParameters:
    """
    Parameters for one OFDM acquisition block.

    Attributes
    ----------
    n_fft          : DFT size.
    n_active       : Active subcarrier count before guard removal.
    cp_len         : Cyclic-prefix length in samples.  Must satisfy
                     cp_len >= 2 * R_max / c * sample_rate_hz (no ISI).
    sample_rate_hz : Baseband sample rate [Hz].  Fs = n_fft * subcarrier_spacing.
    center_freq_hz : RF center frequency of this block [Hz].
    dc_null        : Null the DC subcarrier (bin 0).
    guard_bins     : Guard bins removed from each edge of each frequency half.
    pilot_seed     : RNG seed for BPSK pilot generation (None = random each call).
    """
    n_fft: int = 256
    n_active: int = 200
    cp_len: int = 32
    sample_rate_hz: float = 20e6
    center_freq_hz: float = 2.4e9
    dc_null: bool = True
    guard_bins: int = 4
    pilot_seed: int | None = 42

    @property
    def subcarrier_spacing_hz(self) -> float:
        """df = Fs / N_fft [Hz]."""
        return self.sample_rate_hz / self.n_fft

    @property
    def active_indices(self) -> np.ndarray:
        """FFT bin indices of active subcarriers."""
        return allocate_active_subcarriers(
            self.n_fft, self.n_active,
            dc_null=self.dc_null, guard_bins=self.guard_bins,
        )

    @property
    def active_freqs_hz(self) -> np.ndarray:
        """Absolute RF frequencies of active subcarriers [Hz]."""
        k = self.active_indices
        df = self.subcarrier_spacing_hz
        # FFT bin k: positive freq for k < n_fft//2, negative for k >= n_fft//2
        k_signed = np.where(
            k < self.n_fft // 2, k.astype(float), (k - self.n_fft).astype(float)
        )
        return self.center_freq_hz + k_signed * df


@dataclass
class PointTarget:
    """
    Simulated point scatterer.

    Attributes
    ----------
    x_m          : Cross-range (azimuth) position [m].
    z_m          : Down-range (depth) position [m].  Must be > 0.
    reflectivity : Complex reflectivity amplitude (unitless).
    """
    x_m: float
    z_m: float
    reflectivity: complex = 1.0 + 0j


# ---------------------------------------------------------------------------
# Core simulation functions
# ---------------------------------------------------------------------------

def _one_way_range_to_target(
    ap_x: float, ap_z: float, target: PointTarget
) -> float:
    """Euclidean one-way range from aperture point to target [m]."""
    return float(np.sqrt((ap_x - target.x_m) ** 2 + (ap_z - target.z_m) ** 2))


def simulate_h_block(
    params: OFDMParameters,
    targets: list[PointTarget],
    az_pos_m: float,
    aperture_z_m: float = 0.0,
    noise_std: float = 0.0,
    rng: Optional[np.random.Generator] = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Simulate H[k] for one OFDM block at one azimuth position.

    Free-space non-dispersive model.  Simulation-only. No hardware.

    Algorithm
    ---------
    1. Generate known BPSK pilot X[k] at active subcarrier indices.
    2. For each target, compute two-way delay tau = 2*R/c and sum the
       attenuated/phase-shifted pilot contributions into Y[k].
    3. Estimate H[k] = Y[k] / X[k] at active subcarriers.

    Parameters
    ----------
    params        : OFDMParameters for this block.
    targets       : List of PointTarget scatterers.
    az_pos_m      : Aperture cross-range position [m].
    aperture_z_m  : Aperture depth [m] (usually 0.0 for surface array).
    noise_std     : Std of additive complex Gaussian noise on received bins.
    rng           : Optional RNG for reproducibility.

    Returns
    -------
    H_active : complex array (n_valid,).  H[k] at active subcarriers.
    freqs_hz : float array (n_valid,).   Absolute RF frequencies [Hz].
    """
    if rng is None:
        rng = np.random.default_rng()

    idx = params.active_indices
    freqs = params.active_freqs_hz
    n_active = len(idx)

    X_active = generate_bpsk_pilots(n_active, seed=params.pilot_seed)

    X_full = np.zeros(params.n_fft, dtype=complex)
    X_full[idx] = X_active

    Y_full = np.zeros(params.n_fft, dtype=complex)
    for target in targets:
        R = _one_way_range_to_target(az_pos_m, aperture_z_m, target)
        tau = 2.0 * R / 3e8          # two-way delay
        phase = -2.0 * np.pi * freqs * tau
        Y_full[idx] += target.reflectivity * X_active * np.exp(1j * phase)

    if noise_std > 0:
        noise = rng.normal(0, noise_std, params.n_fft) + \
                1j * rng.normal(0, noise_std, params.n_fft)
        Y_full += noise

    H_full = estimate_channel_rx_tx(Y_full, X_full)
    H_active = H_full[idx]
    # Sort by increasing absolute RF frequency so range_profiles_from_h_matrix
    # receives a monotone frequency grid and the IFFT produces a correct CIR.
    sort_order = np.argsort(freqs)
    return H_active[sort_order], freqs[sort_order]


def simulate_h_matrix(
    params: OFDMParameters,
    targets: list[PointTarget],
    az_positions_m: np.ndarray,
    aperture_z_m: float = 0.0,
    noise_std: float = 0.0,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Simulate H(f, x_az) for one OFDM block over all azimuth positions.

    Simulation-only. No hardware. Free-space propagation.

    Returns
    -------
    H_matrix : complex array (n_active, n_az).  Channel cube H(f, x_az).
    freqs_hz : float array (n_active,).  Absolute RF frequencies [Hz].
    az_m     : float array (n_az,).  Azimuth positions [m].
    """
    rng = np.random.default_rng(seed)
    idx = params.active_indices
    n_active = len(idx)
    n_az = len(az_positions_m)

    H_matrix = np.zeros((n_active, n_az), dtype=complex)
    freqs_hz: np.ndarray | None = None

    for i_az, x_ap in enumerate(az_positions_m):
        H_col, freqs = simulate_h_block(
            params, targets, float(x_ap), aperture_z_m, noise_std, rng
        )
        H_matrix[:, i_az] = H_col
        freqs_hz = freqs

    if freqs_hz is None:
        freqs_hz = params.active_freqs_hz

    return H_matrix, freqs_hz, az_positions_m.copy()


def stitch_blocks(
    blocks: list[tuple[np.ndarray, np.ndarray]],
) -> tuple[np.ndarray, np.ndarray]:
    """
    Concatenate H(f) blocks from multiple RF center frequencies.

    Naive stitching: sort by frequency and concatenate.  Real-hardware stitching
    requires phase calibration between blocks (see docs/ofdm_bladerf_block_stitching_plan.md).

    Simulation-only. No hardware.

    Parameters
    ----------
    blocks : list of (H_block, freqs_hz) pairs, each from simulate_h_matrix column
             or simulate_h_block.

    Returns
    -------
    H_total   : complex array (n_total_active,).
    freqs_all : float array (n_total_active,).  Sorted ascending.
    """
    all_H: list[np.ndarray] = []
    all_f: list[np.ndarray] = []
    for H_b, f_b in blocks:
        all_H.append(H_b)
        all_f.append(f_b)
    f_cat = np.concatenate(all_f)
    H_cat = np.concatenate(all_H)
    order = np.argsort(f_cat)
    return H_cat[order], f_cat[order]


# ---------------------------------------------------------------------------
# Range profile and image reconstruction
# ---------------------------------------------------------------------------

def range_profiles_from_h_matrix(
    H_matrix: np.ndarray,
    freqs_hz: np.ndarray,
    padding_factor: int = 8,
    window: str = "hanning",
) -> tuple[np.ndarray, np.ndarray]:
    """
    IFFT along frequency axis to produce range profiles from H(f, x_az).

    Baseband. No hardware. Simulation-compatible.

    Parameters
    ----------
    H_matrix       : complex array (n_freq, n_az).
    freqs_hz       : float array (n_freq,).  Absolute RF freqs [Hz].
    padding_factor : int.  Zero-padding factor (>= 1).
    window         : str.  'hanning', 'blackman', or 'none'.

    Returns
    -------
    range_m  : float array (n_fft_pad // 2,).  One-way range axis [m].
    profiles : complex array (n_fft_pad // 2, n_az).  Range-compressed data.
    """
    n_freq, n_az = H_matrix.shape
    n_pad = n_freq * padding_factor

    _win = {"hanning": np.hanning, "blackman": np.blackman}
    w = _win.get(window, lambda n: np.ones(n))(n_freq)
    H_win = H_matrix * w[:, None]

    h = np.fft.ifft(H_win, n=n_pad, axis=0)
    h = h[: n_pad // 2, :]

    df = float(freqs_hz[1] - freqs_hz[0]) if len(freqs_hz) > 1 else 1.0
    tau = np.arange(n_pad // 2) / (n_pad * df)
    range_m = 3e8 * tau / 2.0

    return range_m, h


def backprojection_image(
    H_matrix: np.ndarray,
    freqs_hz: np.ndarray,
    az_positions_m: np.ndarray,
    x_img: np.ndarray,
    z_img: np.ndarray,
    padding_factor: int = 8,
    window: str = "hanning",
    c: float = 3e8,
) -> np.ndarray:
    """
    Near-field backprojection from H(f, x_az) to a 2D reflectivity image.

    Simulation-only. No hardware. Free-space propagation model.

    Algorithm
    ---------
    For each aperture position x_ap:
      1. Compute range R(x_px, z_px) = sqrt((x_ap - x_px)^2 + z_px^2).
      2. Interpolate the range profile at R.
      3. Apply carrier correction exp(+j*4*pi*f0*R/c) to remove the
         non-baseband carrier term from the IFFT (f0 = freqs_hz[0]).
      4. Coherently accumulate across aperture.

    Parameters
    ----------
    H_matrix       : complex array (n_freq, n_az).
    freqs_hz       : float array (n_freq,).
    az_positions_m : float array (n_az,).
    x_img          : float array (n_x,).  Cross-range image grid [m].
    z_img          : float array (n_z,).  Down-range image grid [m].
    padding_factor : int.
    window         : str.
    c              : float.  Propagation speed [m/s].

    Returns
    -------
    img : complex array (n_x, n_z).  Focused SAR image.
    """
    range_m, profiles = range_profiles_from_h_matrix(
        H_matrix, freqs_hz, padding_factor, window
    )

    n_x = len(x_img)
    n_z = len(z_img)
    XX, ZZ = np.meshgrid(x_img, z_img, indexing="ij")
    img = np.zeros((n_x, n_z), dtype=complex)
    f0 = float(freqs_hz[0])

    for i_az, x_ap in enumerate(az_positions_m):
        prof = profiles[:, i_az]
        R = np.sqrt((x_ap - XX) ** 2 + ZZ ** 2)
        R_flat = R.ravel()
        real_interp = np.interp(R_flat, range_m, prof.real)
        imag_interp = np.interp(R_flat, range_m, prof.imag)
        carrier = np.exp(1j * 4.0 * np.pi * f0 * R / c)
        img += (real_interp + 1j * imag_interp).reshape(n_x, n_z) * carrier

    return img
