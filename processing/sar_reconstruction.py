"""
SAR image reconstruction from synthetic-aperture SFCW data.

Backprojection algorithm:
  For each image pixel (x_px, z_px) and each aperture position x_az:
    1. Compute one-way range R = sqrt((x_az - x_px)^2 + z_px^2).
    2. Interpolate the complex range profile at range R.
    3. Accumulate (coherent sum) across all aperture positions.
"""
from __future__ import annotations

import numpy as np
from simulation.synthetic_scan import SyntheticScan


def backprojection(
    scan: SyntheticScan,
    x_img: np.ndarray,
    z_img: np.ndarray,
    c: float = 3e8,
    padding_factor: int = 4,
    window: bool = True,
) -> np.ndarray:
    """
    Backprojection SAR reconstruction.

    Parameters
    ----------
    scan          : SyntheticScan holding H[N_f, N_az]
    x_img         : 1D cross-range image grid [m], shape (N_x,)
    z_img         : 1D down-range image grid [m], shape (N_z,)
    c             : propagation speed [m/s]
    padding_factor: IFFT zero-padding factor forwarded to range_profile
    window        : Hanning window flag forwarded to range_profile

    Returns
    -------
    img : complex 2D array (N_x, N_z), focused SAR image
    """
    from processing.range_profile import compute_range_profiles

    range_m, profiles = compute_range_profiles(
        scan, padding_factor=padding_factor, window=window, c=c
    )

    N_x = len(x_img)
    N_z = len(z_img)

    # Pixel coordinate grids
    XX, ZZ = np.meshgrid(x_img, z_img, indexing="ij")  # (N_x, N_z)
    img = np.zeros((N_x, N_z), dtype=complex)

    # The IFFT of a non-baseband signal (f_start ≠ 0) retains a carrier term
    # exp(-j·4π·f_start·R_target/c) in the range profile.  To achieve coherent
    # summation, each contribution is multiplied by the conjugate carrier at the
    # pixel's range, which acts as a matched-filter re-reference to f_start.
    f_start = scan.freqs_hz[0]

    for i_az, x_ap in enumerate(scan.x_az_m):
        prof = profiles[:, i_az]                              # complex (N_range,)
        R = np.sqrt((x_ap - XX) ** 2 + ZZ ** 2)             # one-way range (N_x, N_z)
        R_flat = R.ravel()
        # Interpolate complex range profile at each pixel's range
        real_part = np.interp(R_flat, range_m, prof.real)
        imag_part = np.interp(R_flat, range_m, prof.imag)
        # Carrier correction: re-reference phase to f_start at pixel range
        carrier = np.exp(1j * 4 * np.pi * f_start * R / c)
        img += ((real_part + 1j * imag_part).reshape(N_x, N_z)) * carrier

    return img


def image_grid_from_config(cfg: dict, N_x: int = 200, N_z: int = 200) -> tuple:
    """
    Build a default image grid from the simulation YAML config.

    The cross-range extent matches the aperture plus a small margin.
    The range extent covers 0.01 m to 0.50 m (suitable for near-field phantoms).

    Returns
    -------
    x_img : 1D array [m]
    z_img : 1D array [m]
    """
    az = cfg["azimuth"]
    margin = 0.05  # m
    x_img = np.linspace(float(az["x_start_m"]) - margin, float(az["x_stop_m"]) + margin, N_x)
    z_img = np.linspace(0.01, 0.50, N_z)
    return x_img, z_img
