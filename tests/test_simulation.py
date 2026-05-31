"""
Unit and smoke tests for the hardware-independent simulation pipeline.
No bladeRF imports, no hardware access.
"""
import numpy as np
import pytest

from simulation.phantom_model import PhantomModel, PointTarget, phantom_from_config
from simulation.synthetic_scan import SyntheticScan, make_scan, scan_from_config
from processing.range_profile import compute_range_profiles
from processing.sar_reconstruction import backprojection, image_grid_from_config


# ---------------------------------------------------------------------------
# PhantomModel
# ---------------------------------------------------------------------------

def test_frequency_response_phase_single_target():
    """H(f) phase must equal -4pi*f*R/c for a single on-axis target."""
    c = 3e8
    R = 0.10  # one-way range [m]
    phantom = PhantomModel(targets=[PointTarget(x_m=0.0, z_m=R)], c=c)
    freqs = np.array([500e6, 1000e6, 1500e6, 2000e6, 2500e6])
    x_az = np.array([0.0])

    H = phantom.frequency_response(freqs, x_az)

    expected_phase = -4 * np.pi * freqs * R / c
    actual_phase = np.angle(H[:, 0])
    # Compare modulo 2pi via phasor difference
    diff = np.angle(np.exp(1j * (actual_phase - expected_phase)))
    assert np.allclose(diff, 0, atol=1e-10), f"Phase error: {diff}"


def test_frequency_response_superposition():
    """Response for two targets must equal sum of individual responses."""
    c = 3e8
    t1 = PointTarget(x_m=0.00, z_m=0.10)
    t2 = PointTarget(x_m=0.05, z_m=0.12)
    phantom_both = PhantomModel(targets=[t1, t2], c=c)
    phantom_t1 = PhantomModel(targets=[t1], c=c)
    phantom_t2 = PhantomModel(targets=[t2], c=c)

    freqs = np.linspace(500e6, 2500e6, 50)
    x_az = np.array([-0.05, 0.0, 0.05])

    H_both = phantom_both.frequency_response(freqs, x_az)
    H_sum = phantom_t1.frequency_response(freqs, x_az) + phantom_t2.frequency_response(freqs, x_az)
    assert np.allclose(H_both, H_sum)


def test_noise_changes_response():
    """Non-zero noise_std must produce a different H from the noiseless case."""
    phantom = PhantomModel(targets=[PointTarget(x_m=0.0, z_m=0.10)], c=3e8)
    freqs = np.linspace(500e6, 2500e6, 100)
    x_az = np.linspace(-0.15, 0.15, 16)
    rng = np.random.default_rng(42)

    H_clean = phantom.frequency_response(freqs, x_az, noise_std=0.0)
    H_noisy = phantom.frequency_response(freqs, x_az, noise_std=0.1, rng=rng)
    assert not np.allclose(H_clean, H_noisy)


def test_phantom_from_config():
    cfg = {
        "phantom": {"targets": [{"x_m": 0.0, "z_m": 0.10}], "target_rcs": 1.0},
        "reconstruction": {"speed_of_light": 3e8},
    }
    phantom = phantom_from_config(cfg)
    assert len(phantom.targets) == 1
    assert phantom.targets[0].z_m == pytest.approx(0.10)
    assert phantom.c == pytest.approx(3e8)


# ---------------------------------------------------------------------------
# SyntheticScan
# ---------------------------------------------------------------------------

def test_scan_shape():
    """H must have shape (N_f, N_az) matching the requested grids."""
    phantom = PhantomModel(targets=[PointTarget(x_m=0.0, z_m=0.10)], c=3e8)
    scan = make_scan(
        phantom,
        f_start_hz=500e6, f_stop_hz=2500e6, f_step_hz=5e6,
        x_start_m=-0.15, x_stop_m=0.15, x_step_m=0.02,
    )
    # 500–2500 MHz in 5 MHz steps → 401 points; -0.15–0.15 in 0.02 m steps → 16
    assert scan.H.shape == (len(scan.freqs_hz), len(scan.x_az_m))
    assert scan.H.dtype == np.complex128
    assert scan.freqs_hz[0] == pytest.approx(500e6)
    assert scan.freqs_hz[-1] == pytest.approx(2500e6)
    assert scan.x_az_m[0] == pytest.approx(-0.15)
    assert scan.x_az_m[-1] == pytest.approx(0.15)


def test_scan_bandwidth():
    phantom = PhantomModel(targets=[PointTarget(x_m=0.0, z_m=0.10)], c=3e8)
    scan = make_scan(phantom, 500e6, 2500e6, 5e6, 0.0, 0.0, 1.0)
    assert scan.bandwidth_hz == pytest.approx(2e9, rel=1e-3)


# ---------------------------------------------------------------------------
# Range profile
# ---------------------------------------------------------------------------

def test_range_profile_peak_location():
    """IFFT peak must land within one range-bin of the true target range."""
    target_range = 0.10  # m, one-way
    c = 3e8
    phantom = PhantomModel(targets=[PointTarget(x_m=0.0, z_m=target_range)], c=c)
    # Single azimuth position, on-axis
    scan = make_scan(phantom, 500e6, 2500e6, 5e6, 0.0, 0.0, 1.0)

    range_m, profiles = compute_range_profiles(scan, padding_factor=4, window=False, c=c)
    peak_idx = int(np.argmax(np.abs(profiles[:, 0])))
    peak_range = range_m[peak_idx]

    range_bin = range_m[1] - range_m[0]
    assert abs(peak_range - target_range) <= 2 * range_bin, (
        f"Peak at {peak_range:.4f} m, expected {target_range:.4f} m, bin={range_bin:.4f} m"
    )


def test_range_profile_shape():
    phantom = PhantomModel(targets=[PointTarget(x_m=0.0, z_m=0.10)], c=3e8)
    scan = make_scan(phantom, 500e6, 2500e6, 5e6, -0.15, 0.15, 0.02)
    pad = 4
    range_m, profiles = compute_range_profiles(scan, padding_factor=pad)
    expected_range_bins = len(scan.freqs_hz) * pad // 2
    assert profiles.shape == (expected_range_bins, scan.H.shape[1])
    assert len(range_m) == expected_range_bins


# ---------------------------------------------------------------------------
# SAR reconstruction
# ---------------------------------------------------------------------------

def test_reconstruction_locates_single_target():
    """Backprojection image peak must be within 2 cm of the true target."""
    target_x, target_z = 0.0, 0.10
    c = 3e8
    phantom = PhantomModel(targets=[PointTarget(x_m=target_x, z_m=target_z)], c=c)
    scan = make_scan(phantom, 500e6, 2500e6, 5e6, -0.15, 0.15, 0.02)

    x_img = np.linspace(-0.20, 0.20, 81)
    z_img = np.linspace(0.02, 0.25, 121)
    img = backprojection(scan, x_img, z_img, c=c, padding_factor=4)

    amp = np.abs(img)
    ix, iz = np.unravel_index(np.argmax(amp), amp.shape)
    assert abs(x_img[ix] - target_x) < 0.02, f"Cross-range error: {x_img[ix]:.3f} m"
    assert abs(z_img[iz] - target_z) < 0.02, f"Range error: {z_img[iz]:.3f} m"


def test_reconstruction_two_targets_both_visible():
    """Reconstruction must have local maxima near each of two well-separated targets."""
    c = 3e8
    t1 = PointTarget(x_m=0.00, z_m=0.10)
    t2 = PointTarget(x_m=0.05, z_m=0.12)
    phantom = PhantomModel(targets=[t1, t2], c=c)
    scan = make_scan(phantom, 500e6, 2500e6, 5e6, -0.15, 0.15, 0.02)

    x_img = np.linspace(-0.20, 0.20, 81)
    z_img = np.linspace(0.02, 0.25, 121)
    img = backprojection(scan, x_img, z_img, c=c, padding_factor=4)
    amp = np.abs(img)

    # Check that amplitude near each target is above half the global max
    global_max = amp.max()
    for t in [t1, t2]:
        ix = int(np.argmin(np.abs(x_img - t.x_m)))
        iz = int(np.argmin(np.abs(z_img - t.z_m)))
        local_val = amp[max(0, ix-3):ix+4, max(0, iz-3):iz+4].max()
        assert local_val > 0.3 * global_max, (
            f"Target at ({t.x_m}, {t.z_m}) not visible: local={local_val:.3f}, global={global_max:.3f}"
        )


def test_image_grid_from_config():
    cfg = {
        "azimuth": {"x_start_m": -0.15, "x_stop_m": 0.15},
        "sfcw": {"f_start_hz": 500e6, "f_stop_hz": 2500e6},
        "reconstruction": {"speed_of_light": 3e8},
    }
    x_img, z_img = image_grid_from_config(cfg, N_x=100, N_z=100)
    assert len(x_img) == 100
    assert len(z_img) == 100
    assert x_img[0] < -0.15  # margin applied
    assert x_img[-1] > 0.15


def test_no_bladerf_imports():
    """Verify none of the simulation/processing modules import bladeRF."""
    import importlib
    import sys

    for module_name in [
        "simulation.phantom_model",
        "simulation.synthetic_scan",
        "processing.range_profile",
        "processing.sar_reconstruction",
    ]:
        mod = sys.modules.get(module_name) or importlib.import_module(module_name)
        src = getattr(mod, "__file__", "") or ""
        # Read source text and check for bladeRF import
        if src.endswith(".py"):
            text = open(src).read()
            assert "bladerf" not in text.lower(), f"{module_name} must not import bladeRF"
