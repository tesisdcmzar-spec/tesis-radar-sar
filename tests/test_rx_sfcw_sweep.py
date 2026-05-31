"""
Unit tests for acquisition/rx_sfcw_sweep.py.

All tests use synthetic data only — no bladeRF, no USB, no hardware, no TX.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from acquisition.rx_sfcw_sweep import (
    SweepConfig,
    SweepResult,
    coherent_average_iq,
    compute_sweep_metrics,
    extract_h_from_iq_bursts,
    make_frequency_grid,
    make_synthetic_scan_from_h,
)
from processing.range_profile import compute_range_profiles
from simulation.synthetic_scan import SyntheticScan


# ===========================================================================
# make_frequency_grid
# ===========================================================================

class TestMakeFrequencyGrid:
    def test_basic_grid(self):
        g = make_frequency_grid(1e6, 5e6, 1e6)
        np.testing.assert_allclose(g, [1e6, 2e6, 3e6, 4e6, 5e6])

    def test_float64_dtype(self):
        g = make_frequency_grid(2.3e9, 2.5e9, 10e6)
        assert g.dtype == np.float64

    def test_pilot_grid_length(self):
        g = make_frequency_grid(2.3e9, 2.5e9, 10e6)
        assert len(g) == 21

    def test_full_grid_length(self):
        g = make_frequency_grid(2.3e9, 2.5e9, 1e6)
        assert len(g) == 201

    def test_grid_is_monotonic(self):
        g = make_frequency_grid(900e6, 5e9, 100e6)
        assert np.all(np.diff(g) > 0)

    def test_negative_step_raises(self):
        with pytest.raises(ValueError, match="step_hz must be positive"):
            make_frequency_grid(1e6, 5e6, -1e6)

    def test_zero_step_raises(self):
        with pytest.raises(ValueError):
            make_frequency_grid(1e6, 5e6, 0)

    def test_stop_le_start_raises(self):
        with pytest.raises(ValueError):
            make_frequency_grid(5e6, 1e6, 1e6)

    def test_stop_equal_start_raises(self):
        with pytest.raises(ValueError):
            make_frequency_grid(2.4e9, 2.4e9, 1e6)

    def test_single_point_at_start(self):
        # stop just above start (within half a step) → 1 point
        g = make_frequency_grid(2.4e9, 2.4e9 + 0.4e6, 1e6)
        assert len(g) == 1
        np.testing.assert_allclose(g[0], 2.4e9)


# ===========================================================================
# coherent_average_iq
# ===========================================================================

class TestCoherentAverageIQ:
    def test_cw_tone_recovery(self):
        # CW tone at DC (relative) → coherent average = amplitude * exp(j*phase)
        n = 10_000
        amp, phase = 0.5, 1.23
        iq = np.full(n, amp * np.exp(1j * phase), dtype=np.complex128)
        result = coherent_average_iq(iq)
        np.testing.assert_allclose(abs(result), amp, rtol=1e-9)
        np.testing.assert_allclose(np.angle(result), phase, atol=1e-9)

    def test_noise_averages_to_near_zero(self):
        rng = np.random.default_rng(42)
        iq = (rng.standard_normal(100_000) + 1j * rng.standard_normal(100_000)) * 0.01
        avg = coherent_average_iq(iq)
        # RMS of mean ≈ 0.01 / sqrt(100000) ≈ 3e-5
        assert abs(avg) < 1e-3

    def test_returns_complex(self):
        iq = np.ones(10, dtype=np.complex128)
        result = coherent_average_iq(iq)
        assert isinstance(result, complex)

    def test_2d_array_raises(self):
        iq = np.ones((10, 2), dtype=np.complex128)
        with pytest.raises(ValueError, match="1-D"):
            coherent_average_iq(iq)

    def test_empty_array_raises(self):
        with pytest.raises(ValueError, match="empty"):
            coherent_average_iq(np.array([], dtype=np.complex128))

    def test_float_input_converted(self):
        # float32 real-only input should not crash
        iq = np.ones(100, dtype=np.float32)
        result = coherent_average_iq(iq)
        assert isinstance(result, complex)


# ===========================================================================
# extract_h_from_iq_bursts
# ===========================================================================

class TestExtractHFromIQBursts:
    def _make_bursts(self, n_freqs: int, n_samples: int = 1000):
        rng = np.random.default_rng(7)
        freqs = make_frequency_grid(1e9, 1e9 + (n_freqs - 1) * 1e6, 1e6)
        bursts = [
            (rng.standard_normal(n_samples) + 1j * rng.standard_normal(n_samples))
            * 0.01
            for _ in range(n_freqs)
        ]
        return freqs, bursts

    def test_output_shape(self):
        freqs, bursts = self._make_bursts(7)
        H = extract_h_from_iq_bursts(freqs, bursts)
        assert H.shape == (7,)
        assert H.dtype == np.complex128

    def test_output_matches_individual_averages(self):
        freqs, bursts = self._make_bursts(5)
        H = extract_h_from_iq_bursts(freqs, bursts)
        for i, b in enumerate(bursts):
            np.testing.assert_allclose(H[i], coherent_average_iq(np.asarray(b)))

    def test_length_mismatch_raises(self):
        freqs = make_frequency_grid(1e9, 3e9, 1e9)  # 3 freqs
        bursts = [np.ones(100, dtype=np.complex128)] * 2  # only 2 bursts
        with pytest.raises(ValueError, match="Length mismatch"):
            extract_h_from_iq_bursts(freqs, bursts)

    def test_2d_burst_raises(self):
        freqs = make_frequency_grid(1e9, 2e9, 1e9)  # 2 freqs
        bad_burst = np.ones((100, 2), dtype=np.complex128)
        with pytest.raises(ValueError, match="1-D"):
            extract_h_from_iq_bursts(freqs, [bad_burst, np.ones(100, dtype=np.complex128)])

    def test_cw_tones_recovered(self):
        n_freqs, n_samples = 5, 50_000
        freqs = make_frequency_grid(2.3e9, 2.3e9 + (n_freqs - 1) * 10e6, 10e6)
        amps   = [0.1, 0.2, 0.3, 0.4, 0.5]
        phases = [0.0, 0.5, 1.0, 1.5, 2.0]
        bursts = [
            np.full(n_samples, amps[i] * np.exp(1j * phases[i]), dtype=np.complex128)
            for i in range(n_freqs)
        ]
        H = extract_h_from_iq_bursts(freqs, bursts)
        np.testing.assert_allclose(np.abs(H), amps, rtol=1e-9)
        np.testing.assert_allclose(np.angle(H), phases, atol=1e-9)


# ===========================================================================
# make_synthetic_scan_from_h
# ===========================================================================

class TestMakeSyntheticScanFromH:
    def _make_inputs(self, n_freqs: int = 21):
        freqs = make_frequency_grid(2.3e9, 2.5e9, 10e6)[:n_freqs]
        rng = np.random.default_rng(99)
        h = (rng.standard_normal(n_freqs) + 1j * rng.standard_normal(n_freqs)) * 0.01
        return freqs, h

    def test_returns_synthetic_scan(self):
        freqs, h = self._make_inputs()
        scan = make_synthetic_scan_from_h(freqs, h)
        assert isinstance(scan, SyntheticScan)

    def test_h_shape_is_nf_by_1(self):
        freqs, h = self._make_inputs(21)
        scan = make_synthetic_scan_from_h(freqs, h)
        assert scan.H.shape == (21, 1)

    def test_x_az_m_default(self):
        freqs, h = self._make_inputs()
        scan = make_synthetic_scan_from_h(freqs, h)
        np.testing.assert_allclose(scan.x_az_m, [0.0])

    def test_x_az_m_custom(self):
        freqs, h = self._make_inputs()
        scan = make_synthetic_scan_from_h(freqs, h, x_az_m=0.15)
        np.testing.assert_allclose(scan.x_az_m, [0.15])

    def test_freqs_preserved(self):
        freqs, h = self._make_inputs()
        scan = make_synthetic_scan_from_h(freqs, h)
        np.testing.assert_array_equal(scan.freqs_hz, freqs)

    def test_h_values_preserved(self):
        freqs, h = self._make_inputs()
        scan = make_synthetic_scan_from_h(freqs, h)
        np.testing.assert_array_equal(scan.H[:, 0], h)

    def test_2d_h_raises(self):
        freqs = make_frequency_grid(2.3e9, 2.5e9, 10e6)
        h_2d = np.ones((21, 3), dtype=np.complex128)
        with pytest.raises(ValueError, match="1-D"):
            make_synthetic_scan_from_h(freqs, h_2d)

    def test_length_mismatch_raises(self):
        freqs = make_frequency_grid(2.3e9, 2.5e9, 10e6)
        h_wrong = np.ones(10, dtype=np.complex128)
        with pytest.raises(ValueError):
            make_synthetic_scan_from_h(freqs, h_wrong)


# ===========================================================================
# Range profile compatibility
# ===========================================================================

class TestRangeProfileCompatibility:
    def _make_scan_with_point_target(self) -> SyntheticScan:
        c = 3e8
        R0 = 2.0  # target at 2 m
        freqs = make_frequency_grid(2.3e9, 2.5e9, 10e6)
        h = np.exp(-1j * 4 * np.pi * freqs * R0 / c)
        return make_synthetic_scan_from_h(freqs, h, x_az_m=0.0)

    def test_range_profile_runs_without_error(self):
        n_freqs = 21
        freqs = make_frequency_grid(2.3e9, 2.5e9, 10e6)
        rng = np.random.default_rng(5)
        h = (rng.standard_normal(n_freqs) + 1j * rng.standard_normal(n_freqs)) * 0.01
        scan = make_synthetic_scan_from_h(freqs, h)
        range_m, profiles = compute_range_profiles(scan, padding_factor=4, window='none')
        assert range_m.ndim == 1
        assert profiles.shape[0] == len(range_m)
        assert profiles.shape[1] == 1

    def test_range_profile_hanning_window(self):
        freqs = make_frequency_grid(2.3e9, 2.5e9, 10e6)
        rng = np.random.default_rng(6)
        h = (rng.standard_normal(21) + 1j * rng.standard_normal(21)) * 0.01
        scan = make_synthetic_scan_from_h(freqs, h)
        range_m, profiles = compute_range_profiles(scan, padding_factor=8, window='hanning')
        assert range_m.ndim == 1
        assert profiles.ndim == 2

    def test_synthetic_point_target_peak_location(self):
        scan = self._make_scan_with_point_target()
        range_m, profiles = compute_range_profiles(scan, padding_factor=16, window='none')
        profile_mag = np.abs(profiles[:, 0])
        peak_idx    = int(np.argmax(profile_mag))
        peak_range  = float(range_m[peak_idx])
        # peak should be within ±50 cm of R0 = 2.0 m
        assert abs(peak_range - 2.0) < 0.5, (
            f"Range peak at {peak_range:.3f} m, expected ~2.0 m"
        )

    def test_bandwidth_and_step_properties(self):
        freqs = make_frequency_grid(2.3e9, 2.5e9, 10e6)
        scan  = make_synthetic_scan_from_h(freqs, np.ones(21, dtype=np.complex128))
        assert abs(scan.bandwidth_hz - 200e6) < 1e3
        assert abs(scan.f_step_hz - 10e6) < 1e3


# ===========================================================================
# compute_sweep_metrics
# ===========================================================================

class TestComputeSweepMetrics:
    def test_bandwidth(self):
        freqs = make_frequency_grid(2.3e9, 2.5e9, 10e6)
        H = np.ones(len(freqs), dtype=np.complex128)
        m = compute_sweep_metrics(freqs, H)
        assert abs(m["bandwidth_hz"] - 200e6) < 1e3
        assert abs(m["bandwidth_mhz"] - 200.0) < 0.01

    def test_range_resolution(self):
        freqs = make_frequency_grid(2.3e9, 2.5e9, 10e6)
        H = np.ones(len(freqs), dtype=np.complex128)
        m = compute_sweep_metrics(freqs, H)
        # c / (2 * 200e6) = 0.75 m
        assert abs(m["range_resolution_m"] - 0.75) < 0.001

    def test_unambiguous_range_pilot(self):
        freqs = make_frequency_grid(2.3e9, 2.5e9, 10e6)
        H = np.ones(len(freqs), dtype=np.complex128)
        m = compute_sweep_metrics(freqs, H)
        # c / (2 * 10e6) = 15 m
        assert abs(m["unambiguous_range_m"] - 15.0) < 0.01

    def test_unambiguous_range_full(self):
        freqs = make_frequency_grid(2.3e9, 2.5e9, 1e6)
        H = np.ones(len(freqs), dtype=np.complex128)
        m = compute_sweep_metrics(freqs, H)
        # c / (2 * 1e6) = 150 m
        assert abs(m["unambiguous_range_m"] - 150.0) < 0.1

    def test_n_freqs(self):
        freqs = make_frequency_grid(2.3e9, 2.5e9, 10e6)
        H = np.ones(len(freqs), dtype=np.complex128)
        m = compute_sweep_metrics(freqs, H)
        assert m["n_freqs"] == 21


# ===========================================================================
# SweepConfig dataclass
# ===========================================================================

class TestSweepConfig:
    def _pilot(self):
        return SweepConfig(
            mode="pilot",
            f_start_hz=2.3e9,
            f_stop_hz=2.5e9,
            step_hz=10e6,
            n_samples=100_000,
            sample_rate_hz=10e6,
            bandwidth_hz=10e6,
            rx_gain_db=20.0,
        )

    def test_n_freqs_expected_pilot(self):
        assert self._pilot().n_freqs_expected == 21

    def test_n_freqs_expected_full(self):
        cfg = SweepConfig("full", 2.3e9, 2.5e9, 1e6, 100_000, 10e6, 10e6, 20.0)
        assert cfg.n_freqs_expected == 201

    def test_to_dict_keys(self):
        d = self._pilot().to_dict()
        for key in ["mode", "f_start_hz", "f_stop_hz", "step_hz",
                    "n_freqs_expected", "n_samples", "sample_rate_hz",
                    "bandwidth_hz", "rx_gain_db"]:
            assert key in d


# ===========================================================================
# No bladeRF import in rx_sfcw_sweep.py
# ===========================================================================

class TestNoBladeRFImport:
    def test_rx_sfcw_sweep_has_no_bladerf_import(self):
        src_path = REPO_ROOT / "acquisition" / "rx_sfcw_sweep.py"
        src = src_path.read_text(encoding="utf-8")
        assert "import bladerf" not in src, (
            "acquisition/rx_sfcw_sweep.py must not import bladerf"
        )
        assert 'import_module("bladerf")' not in src, (
            "acquisition/rx_sfcw_sweep.py must not use import_module('bladerf')"
        )
        assert "import_module('bladerf')" not in src

    def test_module_imports_without_bladerf_side_effect(self):
        import sys
        # Ensure importing rx_sfcw_sweep does not trigger bladerf USB
        before = set(sys.modules.keys())
        import acquisition.rx_sfcw_sweep  # noqa: F401
        after = set(sys.modules.keys())
        newly_imported = after - before
        bladerf_modules = [m for m in newly_imported if "bladerf" in m.lower()]
        assert bladerf_modules == [], (
            f"Importing rx_sfcw_sweep triggered bladeRF import: {bladerf_modules}"
        )
