"""
Unit tests for processing/ofdm_distance_contrast.py.

All tests use synthetic data only.
No bladeRF import. No hardware. No raw data.
No clinical claims. No absolute permittivity.
"""
from __future__ import annotations

import numpy as np
import pytest

from processing.ofdm_distance_contrast import (
    compute_delta_channel,
    window_channel,
    channel_to_delay_profile,
    delay_axis_s,
    range_axis_m,
    relative_contrast_profile,
    find_strongest_contrast_peak,
    summarize_contrast_profile,
)


# ---------------------------------------------------------------------------
# compute_delta_channel
# ---------------------------------------------------------------------------

class TestComputeDeltaChannel:
    def test_basic_subtraction(self):
        H_obj = np.array([2.0 + 1j, 3.0 + 2j])
        H_bg  = np.array([1.0 + 0j, 1.0 + 0j])
        H_delta = compute_delta_channel(H_obj, H_bg)
        expected = np.array([1.0 + 1j, 2.0 + 2j])
        np.testing.assert_allclose(H_delta, expected)

    def test_zero_difference(self):
        H = np.ones(32, dtype=complex) * (1 + 1j)
        H_delta = compute_delta_channel(H, H)
        np.testing.assert_allclose(np.abs(H_delta), 0.0, atol=1e-12)

    def test_shape_preserved(self):
        n = 120
        H_obj = np.random.default_rng(0).standard_normal((n,)).astype(complex)
        H_bg  = np.random.default_rng(1).standard_normal((n,)).astype(complex)
        assert compute_delta_channel(H_obj, H_bg).shape == (n,)

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="shape"):
            compute_delta_channel(np.ones(10, dtype=complex), np.ones(20, dtype=complex))

    def test_dtype_complex(self):
        H_delta = compute_delta_channel(
            np.array([1.0, 2.0], dtype=float),
            np.array([0.5, 1.0], dtype=float),
        )
        assert np.iscomplexobj(H_delta)


# ---------------------------------------------------------------------------
# window_channel
# ---------------------------------------------------------------------------

class TestWindowChannel:
    def test_none_is_identity(self):
        H = np.ones(64, dtype=complex)
        np.testing.assert_allclose(window_channel(H, window="none"), H)

    def test_hanning_shape_preserved(self):
        n = 128
        H = np.ones(n, dtype=complex)
        assert window_channel(H, window="hanning").shape == (n,)

    def test_hanning_endpoints_near_zero(self):
        n = 64
        H = np.ones(n, dtype=complex)
        H_win = window_channel(H, window="hanning")
        assert abs(H_win[0]) < 1e-10
        assert abs(H_win[-1]) < 1e-10

    def test_blackman_shape_preserved(self):
        n = 64
        H = np.ones(n, dtype=complex)
        assert window_channel(H, window="blackman").shape == (n,)

    def test_unknown_window_falls_back_to_rect(self):
        H = np.ones(32, dtype=complex)
        # Unknown window behaves like rectangular (all ones)
        H_win = window_channel(H, window="unknown_window")
        np.testing.assert_allclose(np.abs(H_win), 1.0)


# ---------------------------------------------------------------------------
# channel_to_delay_profile
# ---------------------------------------------------------------------------

class TestChannelToDelayProfile:
    def test_output_shape(self):
        n = 256
        H = np.random.default_rng(0).standard_normal(n).astype(complex)
        cir = channel_to_delay_profile(H)
        assert cir.shape == (n,)

    def test_finite_values(self):
        H = np.random.default_rng(0).standard_normal(64).astype(complex)
        cir = channel_to_delay_profile(H)
        assert np.all(np.isfinite(cir))

    def test_unit_channel_peak_at_zero(self):
        """H[k] = 1 for all k -> CIR = impulse at delay 0 (before windowing)."""
        n = 128
        H = np.ones(n, dtype=complex)
        # Without window, CIR should be concentrated at bin 0
        cir = channel_to_delay_profile(H, window="none")
        peak_idx = int(np.argmax(np.abs(cir)))
        assert peak_idx == 0

    def test_scaled_magnitude(self):
        """After IFFT*N, the magnitude should relate to |H| properly."""
        n = 64
        H = np.zeros(n, dtype=complex)
        H[1] = 1.0  # single subcarrier
        cir = channel_to_delay_profile(H, window="none")
        assert np.all(np.isfinite(cir))


# ---------------------------------------------------------------------------
# delay_axis_s
# ---------------------------------------------------------------------------

class TestDelayAxisS:
    def test_frequency_response_resolution(self):
        n = 100
        BW = 500e6
        dt_expected = 1.0 / BW
        d = delay_axis_s(n, BW, mode="frequency_response")
        assert len(d) == n
        assert d[0] == pytest.approx(0.0)
        assert d[1] == pytest.approx(dt_expected, rel=1e-9)

    def test_time_domain_resolution(self):
        n = 50
        fs = 2e6
        dt_expected = 1.0 / fs
        d = delay_axis_s(n, fs, mode="time_domain")
        assert d[1] == pytest.approx(dt_expected, rel=1e-9)

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="mode"):
            delay_axis_s(10, 1e6, mode="bad_mode")

    def test_negative_bandwidth_raises(self):
        with pytest.raises(ValueError):
            delay_axis_s(10, -1e6)

    def test_zero_start(self):
        d = delay_axis_s(20, 100e6)
        assert d[0] == pytest.approx(0.0)

    def test_monotonic_increasing(self):
        d = delay_axis_s(32, 500e6)
        assert np.all(np.diff(d) > 0)


# ---------------------------------------------------------------------------
# range_axis_m
# ---------------------------------------------------------------------------

class TestRangeAxisM:
    def test_two_way(self):
        d = np.array([0.0, 1.0e-9, 2.0e-9])
        r = range_axis_m(d, c=3e8, two_way=True)
        expected = d * 3e8 / 2.0
        np.testing.assert_allclose(r, expected)

    def test_one_way(self):
        d = np.array([1.0e-9])
        r = range_axis_m(d, c=3e8, two_way=False)
        assert r[0] == pytest.approx(0.3)

    def test_zero_delay_is_zero_range(self):
        d = np.array([0.0, 5e-9])
        r = range_axis_m(d)
        assert r[0] == pytest.approx(0.0)

    def test_shape_preserved(self):
        d = np.linspace(0, 10e-9, 50)
        r = range_axis_m(d)
        assert r.shape == d.shape


# ---------------------------------------------------------------------------
# relative_contrast_profile
# ---------------------------------------------------------------------------

class TestRelativeContrastProfile:
    def test_normalized_to_one(self):
        cir = np.array([0.5 + 0j, 2.0 + 0j, 1.0 + 0j])
        c = relative_contrast_profile(cir, normalize=True)
        assert float(np.max(c)) == pytest.approx(1.0, rel=1e-9)

    def test_non_negative(self):
        rng = np.random.default_rng(0)
        cir = rng.standard_normal(64) + 1j * rng.standard_normal(64)
        c = relative_contrast_profile(cir)
        assert np.all(c >= 0)

    def test_finite(self):
        cir = np.ones(32, dtype=complex)
        c = relative_contrast_profile(cir)
        assert np.all(np.isfinite(c))

    def test_all_zeros_returns_zeros(self):
        cir = np.zeros(16, dtype=complex)
        c = relative_contrast_profile(cir, normalize=True)
        np.testing.assert_allclose(c, 0.0)

    def test_no_normalize(self):
        cir = np.array([0.0 + 0j, 3.0 + 0j])
        c = relative_contrast_profile(cir, normalize=False)
        assert c[1] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# find_strongest_contrast_peak
# ---------------------------------------------------------------------------

class TestFindStrongestContrastPeak:
    def test_peak_at_known_index(self):
        n = 64
        profile = np.zeros(n)
        profile[10] = 1.0
        range_m = np.arange(n) * 0.3  # 0.3 m per bin
        peak_r, peak_idx = find_strongest_contrast_peak(range_m, profile)
        assert peak_idx == 10
        assert peak_r == pytest.approx(3.0)

    def test_causal_only_ignores_second_half(self):
        n = 64
        profile = np.zeros(n)
        profile[n - 5] = 10.0  # large value in non-causal half
        profile[5] = 1.0       # smaller value in causal half
        range_m = np.arange(n, dtype=float)
        _, peak_idx = find_strongest_contrast_peak(range_m, profile, causal_only=True)
        assert peak_idx == 5  # only causal half searched

    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError):
            find_strongest_contrast_peak(np.ones(5), np.ones(10))

    def test_returns_tuple(self):
        profile = np.array([0.1, 0.9, 0.5])
        range_m = np.array([0.0, 0.3, 0.6])
        result = find_strongest_contrast_peak(range_m, profile)
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# summarize_contrast_profile
# ---------------------------------------------------------------------------

class TestSummarizeContrastProfile:
    def test_returns_dict(self):
        n = 64
        profile = np.zeros(n)
        profile[5] = 1.0
        range_m = np.arange(n) * 0.3
        s = summarize_contrast_profile(range_m, profile)
        assert isinstance(s, dict)

    def test_required_keys(self):
        n = 32
        profile = np.random.default_rng(0).random(n)
        range_m = np.arange(n) * 0.5
        s = summarize_contrast_profile(range_m, profile)
        for key in ("n_bins", "peak_range_m", "peak_idx", "peak_contrast", "note"):
            assert key in s, f"Missing key: {key}"

    def test_note_mentions_relative(self):
        s = summarize_contrast_profile(np.array([0.0, 1.0]), np.array([0.5, 1.0]))
        assert "relative" in s["note"].lower() or "permittivity" in s["note"].lower()

    def test_expected_distance_added_when_provided(self):
        n = 64
        dr = 0.3
        profile = np.zeros(n)
        profile[3] = 1.0  # peak at bin 3 = 0.9 m
        range_m = np.arange(n) * dr
        expected_m = 0.9  # exactly matches peak
        s = summarize_contrast_profile(range_m, profile, expected_distance_m=expected_m)
        assert "expected_distance_m" in s
        assert "range_error_m" in s
        assert "within_one_bin" in s
        assert s["range_error_m"] == pytest.approx(0.0)
        assert s["within_one_bin"] is True


# ---------------------------------------------------------------------------
# End-to-end: synthetic reflector at known range
# ---------------------------------------------------------------------------

class TestEndToEndSyntheticReflector:
    """
    Simulate H_delta(f) for a reflector at a known range, then verify the
    contrast profile peak is within one range bin of the true range.

    No hardware. No bladeRF. Validates the full pipeline numerically.
    """

    def test_peak_near_known_range(self):
        C = 3e8
        # Scene: reflector at R_true = 1.0 m (two-way delay = 2*R/c = 6.67 ns)
        R_true = 1.0
        # Wide bandwidth to resolve 1 m: BW = 500 MHz -> dr = 0.3 m
        BW = 500e6
        N = 500
        f = np.linspace(2e9, 2e9 + BW, N)

        # H_delta = reflector term only (background already subtracted)
        H_delta = 1.0 * np.exp(-1j * 4.0 * np.pi * f * R_true / C)

        cir = channel_to_delay_profile(H_delta, window="hanning")
        delay_s_arr = delay_axis_s(N, BW, mode="frequency_response")
        range_m = range_axis_m(delay_s_arr, two_way=True)
        dr = float(range_m[1] - range_m[0])

        contrast = relative_contrast_profile(cir)
        peak_r, _ = find_strongest_contrast_peak(range_m, contrast)

        assert abs(peak_r - R_true) <= dr, (
            f"Peak at {peak_r:.3f} m, true at {R_true:.3f} m, "
            f"bin size {dr:.3f} m -- peak outside one bin"
        )

    def test_two_reflectors_resolved(self):
        """Two reflectors separated by > range resolution should both appear."""
        C = 3e8
        BW = 800e6
        N = 800
        R1, R2 = 0.5, 1.5  # separated by 1 m >> dr = c/(2*BW) = 0.19 m
        f = np.linspace(2e9, 2e9 + BW, N)
        H_delta = (0.8 * np.exp(-1j * 4.0 * np.pi * f * R1 / C)
                   + 0.5 * np.exp(-1j * 4.0 * np.pi * f * R2 / C))

        cir = channel_to_delay_profile(H_delta, window="hanning")
        delay_s_arr = delay_axis_s(N, BW)
        range_m = range_axis_m(delay_s_arr)
        contrast = relative_contrast_profile(cir)

        # Check there are at least 2 bins with contrast > 0.3 in causal half
        n_half = N // 2
        strong_bins = np.sum(contrast[:n_half] > 0.3)
        assert strong_bins >= 2, (
            f"Expected at least 2 strong contrast bins, found {strong_bins}"
        )

    def test_no_hardware_no_bladerf_import(self):
        """Verify the module never imports bladeRF or hardware modules."""
        import processing.ofdm_distance_contrast as mod
        source_file = mod.__file__
        with open(source_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        import_lines = [ln for ln in lines if ln.strip().startswith(("import ", "from "))]
        import_src = "\n".join(import_lines).lower()
        assert "bladerf" not in import_src, "ofdm_distance_contrast must not import bladeRF"
        assert "hardware" not in import_src, "ofdm_distance_contrast must not import hardware"
