"""
Unit tests for simulation/ofdm_uwb_sar_simulator.py.

All tests use synthetic data only.
No bladeRF. No USB. No RF. No motors. No raw datasets.
"""
from __future__ import annotations

import pathlib
import numpy as np
import pytest

from simulation.ofdm_uwb_sar_simulator import (
    OFDMParameters,
    PointTarget,
    simulate_h_block,
    simulate_h_matrix,
    stitch_blocks,
    range_profiles_from_h_matrix,
    backprojection_image,
)

_ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Default parameters for tests
# Synthetic: high sample rate for sharp range resolution (not realistic for
# bladeRF, but valid for offline simulation testing).
# ---------------------------------------------------------------------------

def _test_params() -> OFDMParameters:
    """Small, fast parameters for unit tests."""
    return OFDMParameters(
        n_fft=256,
        n_active=200,
        cp_len=32,
        sample_rate_hz=2e9,   # synthetic: gives df=7.8 MHz, BW~1.5 GHz, dR~10 cm
        center_freq_hz=5e9,
        dc_null=True,
        guard_bins=0,
        pilot_seed=0,
    )


# ---------------------------------------------------------------------------
# OFDMParameters properties
# ---------------------------------------------------------------------------

def test_ofdm_params_subcarrier_spacing():
    p = OFDMParameters(n_fft=256, sample_rate_hz=20e6)
    assert abs(p.subcarrier_spacing_hz - 20e6 / 256) < 1


def test_ofdm_params_active_indices_length():
    p = OFDMParameters(n_fft=256, n_active=200, dc_null=True, guard_bins=0)
    assert len(p.active_indices) == 200


def test_ofdm_params_active_freqs_shape():
    p = _test_params()
    assert len(p.active_freqs_hz) == len(p.active_indices)


def test_ofdm_params_active_freqs_centered():
    p = _test_params()
    f = p.active_freqs_hz
    f_center = 0.5 * (f.min() + f.max())
    assert abs(f_center - p.center_freq_hz) < p.subcarrier_spacing_hz


# ---------------------------------------------------------------------------
# simulate_h_block
# ---------------------------------------------------------------------------

def test_simulate_h_block_output_shapes():
    p = _test_params()
    t = [PointTarget(x_m=0.0, z_m=0.5)]
    H, freqs = simulate_h_block(p, t, az_pos_m=0.0)
    assert H.shape == freqs.shape
    assert len(H) == len(p.active_indices)


def test_simulate_h_block_empty_targets_gives_near_zero_H():
    p = _test_params()
    H, _ = simulate_h_block(p, [], az_pos_m=0.0)
    assert np.allclose(H, 0.0)


def test_simulate_h_block_nonzero_with_target():
    p = _test_params()
    t = [PointTarget(x_m=0.0, z_m=1.0)]
    H, _ = simulate_h_block(p, t, az_pos_m=0.0)
    assert np.any(np.abs(H) > 0)


def test_simulate_h_block_noise_changes_result():
    p = _test_params()
    t = [PointTarget(x_m=0.0, z_m=0.5)]
    H_clean, _ = simulate_h_block(p, t, az_pos_m=0.0, noise_std=0.0)
    H_noisy, _ = simulate_h_block(p, t, az_pos_m=0.0, noise_std=0.1,
                                   rng=np.random.default_rng(0))
    assert not np.allclose(H_clean, H_noisy)


def test_simulate_h_block_unit_magnitude_zero_range():
    p = _test_params()
    # Target at z=0 -> range = 0 -> no delay -> H = reflectivity (=1 for BPSK / BPSK)
    # H[k] = X_active[k] * exp(0) / X_active[k] = 1 for all active bins
    t = [PointTarget(x_m=0.0, z_m=0.0, reflectivity=1.0)]
    H, _ = simulate_h_block(p, t, az_pos_m=0.0)
    assert np.allclose(np.abs(H), 1.0, atol=1e-10)


# ---------------------------------------------------------------------------
# simulate_h_matrix
# ---------------------------------------------------------------------------

def test_simulate_h_matrix_output_shape():
    p = _test_params()
    t = [PointTarget(x_m=0.0, z_m=0.5)]
    az = np.linspace(-0.1, 0.1, 5)
    H_mat, freqs, az_out = simulate_h_matrix(p, t, az)
    n_active = len(p.active_indices)
    assert H_mat.shape == (n_active, len(az))
    assert len(freqs) == n_active
    assert np.array_equal(az_out, az)


def test_simulate_h_matrix_reproducible_with_seed():
    p = _test_params()
    t = [PointTarget(x_m=0.0, z_m=0.5)]
    az = np.array([0.0])
    H1, _, _ = simulate_h_matrix(p, t, az, seed=99)
    H2, _, _ = simulate_h_matrix(p, t, az, seed=99)
    assert np.allclose(H1, H2)


# ---------------------------------------------------------------------------
# stitch_blocks
# ---------------------------------------------------------------------------

def test_stitch_blocks_concatenates_and_sorts():
    f1 = np.array([1.0, 2.0, 3.0])
    f2 = np.array([5.0, 4.0])
    H1 = np.array([1.0, 2.0, 3.0], dtype=complex)
    H2 = np.array([5.0, 4.0], dtype=complex)
    H_total, f_total = stitch_blocks([(H1, f1), (H2, f2)])
    assert np.all(np.diff(f_total) > 0)
    assert len(H_total) == 5


# ---------------------------------------------------------------------------
# range_profiles_from_h_matrix
# ---------------------------------------------------------------------------

def test_range_profiles_output_shape():
    p = _test_params()
    n_active = len(p.active_indices)
    n_az = 4
    H_mat = np.ones((n_active, n_az), dtype=complex)
    freqs = p.active_freqs_hz
    range_m, profiles = range_profiles_from_h_matrix(H_mat, freqs, padding_factor=4)
    assert profiles.shape == (n_active * 4 // 2, n_az)
    assert len(range_m) == n_active * 4 // 2


def test_range_profile_peak_near_known_target():
    # Place target at z=0.5 m; expect range profile peak within 0.2 m
    p = _test_params()
    target_range = 0.5
    t = [PointTarget(x_m=0.0, z_m=target_range)]
    az = np.array([0.0])
    H_mat, freqs, _ = simulate_h_matrix(p, t, az, seed=0)
    range_m, profiles = range_profiles_from_h_matrix(H_mat, freqs, padding_factor=8)
    peak_range = range_m[np.argmax(np.abs(profiles[:, 0]))]
    assert abs(peak_range - target_range) < 0.2, (
        f"Peak at {peak_range:.3f} m, expected near {target_range} m"
    )


def test_range_profile_has_response_at_each_target_range():
    # Each target should produce a prominent peak near its known range.
    # Test checks each target's expected range window independently to avoid
    # confusion from sidelobe-adjacent bins when using simple top-N selection.
    p = _test_params()
    t = [
        PointTarget(x_m=0.0, z_m=0.3),
        PointTarget(x_m=0.0, z_m=0.8),
    ]
    az = np.array([0.0])
    H_mat, freqs, _ = simulate_h_matrix(p, t, az, seed=0)
    range_m, profiles = range_profiles_from_h_matrix(H_mat, freqs, padding_factor=8)
    mag = np.abs(profiles[:, 0])

    background = float(np.median(mag))
    for target_range in [0.3, 0.8]:
        window = np.abs(range_m - target_range) < 0.15
        peak_in_window = float(np.max(mag[window])) if np.any(window) else 0.0
        assert peak_in_window > 3.0 * background, (
            f"No prominent peak near {target_range} m: "
            f"peak={peak_in_window:.4f}, median_bg={background:.4f}"
        )


# ---------------------------------------------------------------------------
# backprojection_image
# ---------------------------------------------------------------------------

def test_backprojection_image_shape():
    p = _test_params()
    t = [PointTarget(x_m=0.0, z_m=0.5)]
    az = np.linspace(-0.1, 0.1, 5)
    H_mat, freqs, az_m = simulate_h_matrix(p, t, az, seed=0)
    x_img = np.linspace(-0.15, 0.15, 20)
    z_img = np.linspace(0.1, 1.0, 20)
    img = backprojection_image(H_mat, freqs, az_m, x_img, z_img, padding_factor=4)
    assert img.shape == (20, 20)


def test_backprojection_peak_near_target():
    p = _test_params()
    t_x, t_z = 0.0, 0.5
    t = [PointTarget(x_m=t_x, z_m=t_z)]
    az = np.linspace(-0.2, 0.2, 11)
    H_mat, freqs, az_m = simulate_h_matrix(p, t, az, seed=0)

    x_img = np.linspace(-0.3, 0.3, 41)
    z_img = np.linspace(0.1, 1.0, 41)
    img = backprojection_image(H_mat, freqs, az_m, x_img, z_img, padding_factor=8)

    mag = np.abs(img)
    ix, iz = np.unravel_index(np.argmax(mag), mag.shape)
    peak_x = float(x_img[ix])
    peak_z = float(z_img[iz])
    assert abs(peak_x - t_x) < 0.1, f"Peak x={peak_x:.3f} m, expected {t_x} m"
    assert abs(peak_z - t_z) < 0.2, f"Peak z={peak_z:.3f} m, expected {t_z} m"


# ---------------------------------------------------------------------------
# No hardware imports
# ---------------------------------------------------------------------------

def test_no_hardware_import_in_simulator():
    src = (_ROOT / "simulation" / "ofdm_uwb_sar_simulator.py").read_text(
        encoding="utf-8"
    )
    forbidden = ["import bladerf", "from bladerf",
                 "from hardware", "import hardware",
                 "serial", "usb.core"]
    for term in forbidden:
        assert term not in src, f"Forbidden dependency found: {term!r}"
