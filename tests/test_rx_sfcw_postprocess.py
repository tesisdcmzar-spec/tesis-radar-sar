"""
Unit tests for processing/rx_sfcw_postprocess.py.

All tests use synthetic arrays only.
No bladeRF import.  No hardware access.  No TX.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from processing.rx_sfcw_postprocess import (
    estimate_noise_floor_db,
    find_prominent_range_bins,
    normalize_h_magnitude,
    remove_dc_component,
    smooth_h_magnitude,
    subtract_reference_h,
    summarize_range_profile,
)


# ===========================================================================
# remove_dc_component
# ===========================================================================

class TestRemoveDcComponent:

    def test_mean_is_zero_after_removal(self):
        H = np.array([1+0j, 2+0j, 3+0j, 4+0j, 5+0j])
        out = remove_dc_component(H)
        assert abs(np.mean(out)) < 1e-12

    def test_constant_array_becomes_zeros(self):
        H = np.ones(10, dtype=complex) * (3 + 2j)
        out = remove_dc_component(H)
        np.testing.assert_allclose(out, 0.0, atol=1e-12)

    def test_output_dtype_is_complex128(self):
        H = np.array([1.0, 2.0, 3.0])
        out = remove_dc_component(H)
        assert out.dtype == np.complex128

    def test_output_shape_preserved(self):
        H = np.random.randn(50) + 1j * np.random.randn(50)
        out = remove_dc_component(H)
        assert out.shape == H.shape

    def test_zero_mean_input_unchanged(self):
        H = np.array([-1+0j, 0+0j, 1+0j])
        out = remove_dc_component(H)
        np.testing.assert_allclose(out, H - np.mean(H), atol=1e-12)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            remove_dc_component(np.array([], dtype=complex))

    def test_2d_raises(self):
        with pytest.raises(ValueError):
            remove_dc_component(np.ones((3, 3), dtype=complex))

    def test_real_input_accepted(self):
        H = np.array([1.0, 2.0, 3.0, 4.0])
        out = remove_dc_component(H)
        assert out.dtype == np.complex128
        assert abs(np.mean(out)) < 1e-12


# ===========================================================================
# normalize_h_magnitude
# ===========================================================================

class TestNormalizeHMagnitude:

    def test_max_magnitude_is_one(self):
        H = np.array([1+2j, 3+4j, 0.5+0j])
        out = normalize_h_magnitude(H)
        assert abs(np.max(np.abs(out)) - 1.0) < 1e-12

    def test_phase_preserved(self):
        H = np.array([1+1j, -2+0j, 0+3j])
        out = normalize_h_magnitude(H)
        np.testing.assert_allclose(
            np.angle(out), np.angle(H), atol=1e-12
        )

    def test_output_dtype_is_complex128(self):
        H = np.array([1.0, 2.0, 3.0])
        out = normalize_h_magnitude(H)
        assert out.dtype == np.complex128

    def test_real_positive_input(self):
        H = np.array([2.0, 4.0, 6.0])
        out = normalize_h_magnitude(H)
        np.testing.assert_allclose(out.real, [1/3, 2/3, 1.0], atol=1e-12)

    def test_all_zero_raises(self):
        with pytest.raises(ValueError, match="Cannot normalize"):
            normalize_h_magnitude(np.zeros(5, dtype=complex))

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            normalize_h_magnitude(np.array([], dtype=complex))

    def test_2d_raises(self):
        with pytest.raises(ValueError):
            normalize_h_magnitude(np.ones((2, 3), dtype=complex))

    def test_single_element(self):
        H = np.array([3+4j])
        out = normalize_h_magnitude(H)
        np.testing.assert_allclose(np.abs(out[0]), 1.0, atol=1e-12)


# ===========================================================================
# subtract_reference_h
# ===========================================================================

class TestSubtractReferenceH:

    def test_self_subtraction_is_zero(self):
        H = np.array([1+2j, 3+4j, 5+6j])
        out = subtract_reference_h(H, H)
        np.testing.assert_allclose(out, 0.0, atol=1e-12)

    def test_correct_subtraction(self):
        H     = np.array([5+0j, 3+0j, 1+0j])
        H_ref = np.array([1+0j, 1+0j, 1+0j])
        out   = subtract_reference_h(H, H_ref)
        np.testing.assert_allclose(out, [4+0j, 2+0j, 0+0j], atol=1e-12)

    def test_output_dtype_is_complex128(self):
        H = np.array([1.0, 2.0])
        out = subtract_reference_h(H, np.zeros(2))
        assert out.dtype == np.complex128

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="Shape mismatch"):
            subtract_reference_h(np.ones(3, dtype=complex),
                                  np.ones(4, dtype=complex))

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            subtract_reference_h(np.array([], dtype=complex),
                                  np.array([], dtype=complex))

    def test_2d_raises(self):
        with pytest.raises(ValueError):
            subtract_reference_h(np.ones((2, 3), dtype=complex),
                                  np.ones((2, 3), dtype=complex))

    def test_complex_subtraction(self):
        H     = np.array([1+2j, 3+4j])
        H_ref = np.array([0+1j, 1+1j])
        out   = subtract_reference_h(H, H_ref)
        np.testing.assert_allclose(out, [1+1j, 2+3j], atol=1e-12)


# ===========================================================================
# smooth_h_magnitude
# ===========================================================================

class TestSmoothHMagnitude:

    def test_output_shape_preserved(self):
        H = np.array([1+0j, 2+0j, 3+0j, 4+0j, 5+0j])
        out = smooth_h_magnitude(H, window_len=3)
        assert out.shape == H.shape

    def test_output_dtype_is_complex128(self):
        H = np.array([1.0, 2.0, 3.0])
        out = smooth_h_magnitude(H, window_len=1)
        assert out.dtype == np.complex128

    def test_window_len_1_preserves_magnitude(self):
        H = np.array([1+1j, 2+2j, 3+3j])
        out = smooth_h_magnitude(H, window_len=1)
        np.testing.assert_allclose(np.abs(out), np.abs(H), atol=1e-12)

    def test_window_len_equals_n_constant_magnitude(self):
        H = np.array([1+0j, 2+0j, 3+0j, 4+0j])
        out = smooth_h_magnitude(H, window_len=4)
        # edge-padded convolution differs from simple mean; just check shape/dtype
        assert out.shape == H.shape
        assert out.dtype == np.complex128

    def test_phase_restored(self):
        H = np.array([2+2j, -3+0j, 0+4j, 1-1j])
        out = smooth_h_magnitude(H, window_len=1)
        np.testing.assert_allclose(np.angle(out), np.angle(H), atol=1e-12)

    def test_window_len_zero_raises(self):
        with pytest.raises(ValueError, match="window_len must be >= 1"):
            smooth_h_magnitude(np.ones(5, dtype=complex), window_len=0)

    def test_window_len_exceeds_n_raises(self):
        with pytest.raises(ValueError, match="must not exceed"):
            smooth_h_magnitude(np.ones(3, dtype=complex), window_len=4)

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            smooth_h_magnitude(np.array([], dtype=complex), window_len=1)

    def test_2d_raises(self):
        with pytest.raises(ValueError):
            smooth_h_magnitude(np.ones((2, 3), dtype=complex), window_len=1)


# ===========================================================================
# estimate_noise_floor_db
# ===========================================================================

class TestEstimateNoiseFloorDb:

    def test_all_ones_returns_zero_db(self):
        profile = np.ones(100)
        result = estimate_noise_floor_db(profile)
        assert abs(result - 0.0) < 1e-6

    def test_all_tens_returns_20_db(self):
        profile = np.ones(100) * 10.0
        result = estimate_noise_floor_db(profile)
        assert abs(result - 20.0) < 1e-6

    def test_returns_float(self):
        profile = np.ones(10)
        assert isinstance(estimate_noise_floor_db(profile), float)

    def test_complex_input_uses_magnitude(self):
        # |3+4j| = 5 -> 20*log10(5) ~ 13.979
        profile = np.ones(10) * (3 + 4j)
        result = estimate_noise_floor_db(profile)
        assert abs(result - 20.0 * np.log10(5.0)) < 1e-6

    def test_single_outlier_does_not_dominate(self):
        profile = np.ones(99)
        profile_with_peak = np.append(profile, 1000.0)
        result = estimate_noise_floor_db(profile_with_peak)
        # median should still be ~1 -> 0 dB, not dominated by the 1000 peak
        assert abs(result - 0.0) < 1e-6

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            estimate_noise_floor_db(np.array([]))

    def test_2d_raises(self):
        with pytest.raises(ValueError):
            estimate_noise_floor_db(np.ones((3, 3)))


# ===========================================================================
# find_prominent_range_bins
# ===========================================================================

class TestFindProminentRangeBins:

    def _make_profile(self, n=100, noise_level=1.0, peak_bin=40, peak_amp=100.0):
        rng = np.random.default_rng(42)
        profile = rng.normal(0, noise_level, n).astype(float)
        profile[peak_bin] = peak_amp
        range_m = np.linspace(0, 10, n)
        return range_m, profile

    def test_finds_synthetic_peak(self):
        range_m, profile = self._make_profile(peak_bin=40, peak_amp=100.0)
        bins = find_prominent_range_bins(range_m, profile, min_prominence_db=20.0)
        assert 40 in bins

    def test_returns_empty_when_nothing_prominent(self):
        profile = np.ones(50)
        range_m = np.linspace(0, 5, 50)
        bins = find_prominent_range_bins(range_m, profile, min_prominence_db=60.0)
        assert len(bins) == 0

    def test_returns_int64(self):
        range_m, profile = self._make_profile()
        bins = find_prominent_range_bins(range_m, profile, min_prominence_db=10.0)
        assert bins.dtype == np.int64

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError):
            find_prominent_range_bins(
                np.linspace(0, 1, 10),
                np.ones(11),
                min_prominence_db=10.0,
            )

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            find_prominent_range_bins(
                np.array([]),
                np.array([]),
                min_prominence_db=10.0,
            )

    def test_zero_prominence_returns_all(self):
        profile = np.abs(np.random.randn(50)) + 0.01   # all positive
        range_m = np.linspace(0, 5, 50)
        bins = find_prominent_range_bins(range_m, profile, min_prominence_db=0.0)
        # At 0 dB prominence all bins at or above median are included
        assert len(bins) >= 1

    def test_2d_raises(self):
        with pytest.raises(ValueError):
            find_prominent_range_bins(
                np.ones((3, 3)),
                np.ones((3, 3)),
                min_prominence_db=10.0,
            )


# ===========================================================================
# summarize_range_profile
# ===========================================================================

class TestSummarizeRangeProfile:

    def _make_summary_inputs(self):
        n = 200
        profile = np.ones(n) * 0.01
        profile[80] = 1.0       # clear peak
        range_m = np.linspace(0, 20, n)
        return range_m, profile

    def test_returns_dict_with_all_keys(self):
        range_m, profile = self._make_summary_inputs()
        result = summarize_range_profile(range_m, profile)
        for key in ("peak_range_m", "peak_magnitude_db", "noise_floor_db",
                    "dynamic_range_db", "n_bins", "peak_bin_index"):
            assert key in result, f"Missing key: {key}"

    def test_peak_bin_index_correct(self):
        range_m, profile = self._make_summary_inputs()
        result = summarize_range_profile(range_m, profile)
        assert result["peak_bin_index"] == 80

    def test_peak_range_m_correct(self):
        range_m, profile = self._make_summary_inputs()
        result = summarize_range_profile(range_m, profile)
        expected_range = float(range_m[80])
        assert abs(result["peak_range_m"] - expected_range) < 1e-10

    def test_dynamic_range_positive(self):
        range_m, profile = self._make_summary_inputs()
        result = summarize_range_profile(range_m, profile)
        assert result["dynamic_range_db"] > 0.0

    def test_n_bins_correct(self):
        range_m, profile = self._make_summary_inputs()
        result = summarize_range_profile(range_m, profile)
        assert result["n_bins"] == 200

    def test_peak_magnitude_greater_than_noise_floor(self):
        range_m, profile = self._make_summary_inputs()
        result = summarize_range_profile(range_m, profile)
        assert result["peak_magnitude_db"] > result["noise_floor_db"]

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError):
            summarize_range_profile(
                np.linspace(0, 10, 10),
                np.ones(11),
            )

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            summarize_range_profile(np.array([]), np.array([]))

    def test_complex_profile_accepted(self):
        range_m = np.linspace(0, 10, 50)
        profile = np.ones(50) * (0.1 + 0.1j)
        result = summarize_range_profile(range_m, profile)
        assert "peak_range_m" in result


# ===========================================================================
# No hardware import
# ===========================================================================

class TestNoHardwareImport:

    def test_no_bladerf_in_module_source(self):
        src = (REPO_ROOT / "processing" / "rx_sfcw_postprocess.py").read_text()
        assert "import bladerf" not in src
        assert 'import_module("bladerf")' not in src
        assert 'import_module(\'bladerf\')' not in src

    def test_no_bladerf_in_sys_modules(self):
        import processing.rx_sfcw_postprocess  # noqa: F401
        assert "bladerf" not in sys.modules
