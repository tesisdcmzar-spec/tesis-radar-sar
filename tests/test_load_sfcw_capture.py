"""
Tests for acquisition.load_sfcw_capture.
No bladeRF imports, no hardware access.
All fixtures use small synthetic arrays created in tmp_path.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from acquisition.load_sfcw_capture import load_capture
from simulation.synthetic_scan import SyntheticScan


# ---------------------------------------------------------------------------
# Shared fixture: 5-frequency × 3-azimuth config
# ---------------------------------------------------------------------------

@pytest.fixture
def cfg5x3():
    """5-point frequency grid, 3-point azimuth grid (all floats to avoid YAML quirks)."""
    return {
        "sfcw": {
            "f_start_hz": 1.0e9,
            "f_stop_hz":  3.0e9,
            "f_step_hz":  0.5e9,   # [1.0, 1.5, 2.0, 2.5, 3.0] GHz → 5 points
        },
        "azimuth": {
            "x_start_m": -0.10,
            "x_stop_m":   0.10,
            "x_step_m":   0.10,    # [-0.10, 0.00, 0.10] m → 3 points
        },
    }


# ---------------------------------------------------------------------------
# Helper: create a minimal legacy capture directory
# ---------------------------------------------------------------------------

def _make_legacy_dir(tmp_path: Path, freqs_mhz: list[int], n_samples: int = 200) -> Path:
    cap_dir = tmp_path / "capturas"
    cap_dir.mkdir()
    rng = np.random.default_rng(0)
    for i, f_mhz in enumerate(freqs_mhz):
        iq = rng.standard_normal(n_samples) + 1j * rng.standard_normal(n_samples)
        np.save(str(cap_dir / f"cap_{i:03d}_{f_mhz}MHz.npy"), iq)
    return cap_dir


# ---------------------------------------------------------------------------
# Format A — 2D (N_f, N_az) .npy file
# ---------------------------------------------------------------------------

def test_format_a_returns_synthetic_scan(tmp_path, cfg5x3):
    H = np.random.randn(5, 3) + 1j * np.random.randn(5, 3)
    fpath = tmp_path / "capture.npy"
    np.save(str(fpath), H)

    scan = load_capture(fpath, cfg5x3)

    assert isinstance(scan, SyntheticScan)
    assert scan.H.shape == (5, 3)
    assert scan.freqs_hz.shape == (5,)
    assert scan.x_az_m.shape == (3,)
    assert np.allclose(scan.H, H)


def test_format_a_frequency_grid_matches_config(tmp_path, cfg5x3):
    H = np.ones((5, 3), dtype=complex)
    fpath = tmp_path / "capture.npy"
    np.save(str(fpath), H)

    scan = load_capture(fpath, cfg5x3)

    assert scan.freqs_hz[0] == pytest.approx(1.0e9)
    assert scan.freqs_hz[-1] == pytest.approx(3.0e9)
    assert scan.x_az_m[0] == pytest.approx(-0.10)
    assert scan.x_az_m[-1] == pytest.approx(0.10)


def test_format_a_freq_mismatch_raises(tmp_path, cfg5x3):
    H = np.ones((7, 3), dtype=complex)   # 7 != 5 expected
    fpath = tmp_path / "bad_freq.npy"
    np.save(str(fpath), H)

    with pytest.raises(ValueError, match="Frequency dimension mismatch"):
        load_capture(fpath, cfg5x3)


def test_format_a_az_mismatch_raises(tmp_path, cfg5x3):
    H = np.ones((5, 8), dtype=complex)   # 8 != 3 expected
    fpath = tmp_path / "bad_az.npy"
    np.save(str(fpath), H)

    with pytest.raises(ValueError, match="Azimuth dimension mismatch"):
        load_capture(fpath, cfg5x3)


# ---------------------------------------------------------------------------
# Format B — 1D (N_f,) .npy file (single aperture position)
# ---------------------------------------------------------------------------

def test_format_b_shape_is_nf_1(tmp_path, cfg5x3):
    h = np.array([1 + 0j, 0 - 1j, -1 + 0j, 0 + 1j, 0.5 + 0.5j])
    fpath = tmp_path / "single_pos.npy"
    np.save(str(fpath), h)

    scan = load_capture(fpath, cfg5x3, azimuth_position_m=0.05)

    assert scan.H.shape == (5, 1)
    assert scan.x_az_m.shape == (1,)
    assert scan.x_az_m[0] == pytest.approx(0.05)
    assert np.allclose(scan.H[:, 0], h)


def test_format_b_default_position_is_zero(tmp_path, cfg5x3):
    h = np.ones(5, dtype=complex)
    fpath = tmp_path / "default_pos.npy"
    np.save(str(fpath), h)

    scan = load_capture(fpath, cfg5x3)
    assert scan.x_az_m[0] == pytest.approx(0.0)


def test_format_b_freq_mismatch_raises(tmp_path, cfg5x3):
    h = np.ones(10, dtype=complex)   # 10 != 5
    fpath = tmp_path / "bad_1d.npy"
    np.save(str(fpath), h)

    with pytest.raises(ValueError, match="Frequency dimension mismatch"):
        load_capture(fpath, cfg5x3)


# ---------------------------------------------------------------------------
# Format C — legacy directory of per-frequency IQ files
# ---------------------------------------------------------------------------

def test_format_c_returns_nf_1_scan(tmp_path, cfg5x3):
    cap_dir = _make_legacy_dir(tmp_path, [100, 200, 300, 400, 500])
    scan = load_capture(cap_dir, cfg5x3)

    assert isinstance(scan, SyntheticScan)
    assert scan.H.shape == (5, 1)
    assert scan.x_az_m.shape == (1,)


def test_format_c_freqs_inferred_from_filenames(tmp_path, cfg5x3):
    cap_dir = _make_legacy_dir(tmp_path, [100, 200, 300, 400, 500])
    scan = load_capture(cap_dir, cfg5x3)

    assert scan.freqs_hz[0] == pytest.approx(100e6)
    assert scan.freqs_hz[-1] == pytest.approx(500e6)


def test_format_c_unsorted_files_produce_sorted_freqs(tmp_path, cfg5x3):
    """Files written in arbitrary order must produce strictly ascending freqs."""
    cap_dir = _make_legacy_dir(tmp_path, [500, 100, 300, 200, 400])
    scan = load_capture(cap_dir, cfg5x3)

    assert np.all(np.diff(scan.freqs_hz) > 0)
    assert scan.freqs_hz[0] == pytest.approx(100e6)
    assert scan.freqs_hz[-1] == pytest.approx(500e6)


def test_format_c_h_equals_mean_of_iq(tmp_path, cfg5x3):
    """Each H[k] must equal np.mean of the IQ samples for frequency k."""
    freqs_mhz = [1000, 2000, 3000]
    cap_dir = tmp_path / "capturas_coh"
    cap_dir.mkdir()
    rng = np.random.default_rng(42)
    expected: list[complex] = []
    for i, f_mhz in enumerate(freqs_mhz):
        iq = rng.standard_normal(500) + 1j * rng.standard_normal(500)
        np.save(str(cap_dir / f"cap_{i:03d}_{f_mhz}MHz.npy"), iq)
        expected.append(complex(np.mean(iq)))

    scan = load_capture(cap_dir, cfg5x3)
    for k, exp in enumerate(expected):
        assert scan.H[k, 0] == pytest.approx(exp, abs=1e-14)


def test_format_c_azimuth_position_propagates(tmp_path, cfg5x3):
    cap_dir = _make_legacy_dir(tmp_path, [100, 200])
    scan = load_capture(cap_dir, cfg5x3, azimuth_position_m=0.07)
    assert scan.x_az_m[0] == pytest.approx(0.07)


def test_format_c_empty_dir_raises(tmp_path, cfg5x3):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(ValueError, match="No cap_"):
        load_capture(empty, cfg5x3)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_file_not_found_raises(cfg5x3):
    with pytest.raises(FileNotFoundError):
        load_capture("/does/not/exist.npy", cfg5x3)


def test_unsupported_extension_raises(tmp_path, cfg5x3):
    bad = tmp_path / "capture.csv"
    bad.write_text("1,2,3\n")
    with pytest.raises(ValueError, match="Unsupported file type"):
        load_capture(bad, cfg5x3)


def test_3d_array_raises(tmp_path, cfg5x3):
    arr = np.ones((5, 3, 2), dtype=complex)
    fpath = tmp_path / "bad3d.npy"
    np.save(str(fpath), arr)
    with pytest.raises(ValueError, match="Incompatible array shape"):
        load_capture(fpath, cfg5x3)


# ---------------------------------------------------------------------------
# Pipeline integration
# ---------------------------------------------------------------------------

def test_loader_output_feeds_range_profile(tmp_path, cfg5x3):
    """SyntheticScan from loader must work with compute_range_profiles."""
    from processing.range_profile import compute_range_profiles

    H = np.ones((5, 3), dtype=complex)
    fpath = tmp_path / "pipeline.npy"
    np.save(str(fpath), H)

    scan = load_capture(fpath, cfg5x3)
    range_m, profiles = compute_range_profiles(scan, padding_factor=2, window="none")

    assert profiles.shape == (5, 3)   # N_fft//2 = 5*2//2 = 5, N_az = 3
    assert len(range_m) == 5


def test_no_bladerf_import_in_loader():
    """The loader module must not have an 'import bladerf' statement."""
    import importlib, sys, re
    mod = sys.modules.get("acquisition.load_sfcw_capture") or \
          importlib.import_module("acquisition.load_sfcw_capture")
    src = open(mod.__file__).read()
    # Allow the word in docstrings/comments; reject actual import statements.
    assert not re.search(r"^\s*(import|from)\s+bladerf", src, re.MULTILINE), \
        "acquisition.load_sfcw_capture must not import bladeRF"


# ---------------------------------------------------------------------------
# Offline analysis smoke test
# ---------------------------------------------------------------------------

def test_sfcw_point_target_range_peak_in_format_c(tmp_path, cfg5x3):
    """
    A synthetic Format-C directory where IQ = exp(-j*4*pi*f*R0/c) for each
    frequency must yield a range-profile peak within ±5 cm of R0.

    This validates the full chain:
        _load_legacy_directory → SyntheticScan → compute_range_profiles
    for coherent SFCW data with a known target range.
    """
    from processing.range_profile import compute_range_profiles
    from experiments.run_legacy_offline_analysis import (
        compute_sfcw_performance, profile_peak_range_m,
    )

    C = 3e8
    R0 = 1.0          # target at 1.0 m
    freqs_mhz = list(range(100, 6001, 60))   # 100–6000 MHz, 60 MHz step → 100 files

    cap_dir = tmp_path / "sfcw_target"
    cap_dir.mkdir()
    for i, f_mhz in enumerate(freqs_mhz):
        f_hz = f_mhz * 1e6
        # Coherent CW response of a point target at range R0
        h_val = np.exp(-1j * 4 * np.pi * f_hz * R0 / C)
        iq = np.full(10, h_val, dtype=np.complex128)
        np.save(str(cap_dir / f"cap_{i:03d}_{f_mhz}MHz.npy"), iq)

    scan = load_capture(cap_dir, cfg={})

    perf = compute_sfcw_performance(scan.freqs_hz)
    range_m, profiles = compute_range_profiles(scan, padding_factor=8, window="none")
    peak_m = profile_peak_range_m(range_m, np.abs(profiles[:, 0]))

    # Peak must be within ±5 cm (two resolution cells of the 2.5 cm theory)
    assert abs(peak_m - R0) < 0.05, (
        f"Range peak at {peak_m:.4f} m is too far from R0={R0} m "
        f"(range_res ≈ {perf['range_res_m']*100:.2f} cm)"
    )
