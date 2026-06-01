"""
Tests for:
  - simulation.phantom_permittivity_map
  - processing.dielectric_contrast_heatmap
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from simulation.phantom_permittivity_map import (
    DielectricInclusion,
    DielectricPhantom,
    make_two_inclusion_phantom,
)
from processing.dielectric_contrast_heatmap import (
    sar_image_to_contrast_heatmap,
    permittivity_map_to_reflectivity_map,
    compare_heatmaps,
    locate_contrast_peaks_2d,
    heatmap_summary,
)


# ===========================================================================
# DielectricInclusion
# ===========================================================================

class TestDielectricInclusion:
    def test_basic_creation(self):
        incl = DielectricInclusion(x_m=0.1, z_m=0.5, radius_m=0.05, epsilon_r=4.0)
        assert incl.x_m == pytest.approx(0.1)
        assert incl.z_m == pytest.approx(0.5)
        assert incl.radius_m == pytest.approx(0.05)
        assert incl.epsilon_r == pytest.approx(4.0)
        assert incl.label == ""

    def test_label_attribute(self):
        incl = DielectricInclusion(x_m=0.0, z_m=0.3, radius_m=0.05, epsilon_r=3.0, label="test")
        assert incl.label == "test"

    def test_epsilon_r_below_one_raises(self):
        with pytest.raises(ValueError, match="epsilon_r must be >= 1.0"):
            DielectricInclusion(x_m=0.0, z_m=0.5, radius_m=0.05, epsilon_r=0.5)

    def test_zero_radius_raises(self):
        with pytest.raises(ValueError, match="radius_m must be > 0"):
            DielectricInclusion(x_m=0.0, z_m=0.5, radius_m=0.0, epsilon_r=4.0)

    def test_zero_depth_raises(self):
        with pytest.raises(ValueError, match="z_m must be > 0"):
            DielectricInclusion(x_m=0.0, z_m=0.0, radius_m=0.05, epsilon_r=4.0)

    def test_epsilon_r_equals_one_ok(self):
        incl = DielectricInclusion(x_m=0.0, z_m=0.5, radius_m=0.05, epsilon_r=1.0)
        assert incl.epsilon_r == pytest.approx(1.0)


# ===========================================================================
# DielectricPhantom
# ===========================================================================

class TestDielectricPhantom:
    def _make_phantom(self):
        return DielectricPhantom(
            x_min_m=-0.5, x_max_m=0.5,
            z_min_m=0.1, z_max_m=1.1,
            n_x=100, n_z=100,
            epsilon_r_bg=1.0,
            inclusions=[
                DielectricInclusion(x_m=0.0, z_m=0.5, radius_m=0.05, epsilon_r=4.0, label="A"),
            ],
        )

    def test_x_grid_shape(self):
        ph = self._make_phantom()
        assert ph.x_grid.shape == (100,)

    def test_z_grid_shape(self):
        ph = self._make_phantom()
        assert ph.z_grid.shape == (100,)

    def test_permittivity_grid_shape(self):
        ph = self._make_phantom()
        x, z, eps = ph.permittivity_grid()
        assert eps.shape == (100, 100)

    def test_background_value(self):
        ph = self._make_phantom()
        _, _, eps = ph.permittivity_grid()
        # Corner pixels should be background
        assert eps[0, 0] == pytest.approx(1.0)

    def test_inclusion_center_value(self):
        ph = self._make_phantom()
        _, _, eps = ph.permittivity_grid()
        # Inclusion is at x=0, z=0.5 -- find nearest grid index
        ix = int(np.argmin(np.abs(ph.x_grid - 0.0)))
        iz = int(np.argmin(np.abs(ph.z_grid - 0.5)))
        assert eps[ix, iz] == pytest.approx(4.0)

    def test_to_point_targets_count(self):
        ph = self._make_phantom()
        targets = ph.to_point_targets()
        assert len(targets) == 1

    def test_to_point_targets_position(self):
        ph = self._make_phantom()
        targets = ph.to_point_targets()
        t = targets[0]
        assert t.x_m == pytest.approx(0.0)
        assert t.z_m == pytest.approx(0.5)

    def test_to_point_targets_reflectivity_nonzero(self):
        ph = self._make_phantom()
        targets = ph.to_point_targets()
        assert abs(targets[0].reflectivity) > 0.0

    def test_reflectivity_map_shape(self):
        ph = self._make_phantom()
        x, z, refl = ph.reflectivity_map()
        assert refl.shape == (100, 100)

    def test_reflectivity_map_normalized(self):
        ph = self._make_phantom()
        _, _, refl = ph.reflectivity_map()
        assert float(np.max(refl)) == pytest.approx(1.0, abs=1e-6)

    def test_reflectivity_map_nonnegative(self):
        ph = self._make_phantom()
        _, _, refl = ph.reflectivity_map()
        assert float(np.min(refl)) >= 0.0


# ===========================================================================
# DielectricPhantom.fresnel_reflectivity
# ===========================================================================

class TestFresnelReflectivity:
    def test_same_medium_gives_zero(self):
        gamma = DielectricPhantom.fresnel_reflectivity(1.0, 1.0)
        assert abs(gamma) == pytest.approx(0.0, abs=1e-12)

    def test_eps4_from_air(self):
        # From air (eps=1) to eps=4: Gamma = (1-2)/(1+2) = -1/3
        gamma = DielectricPhantom.fresnel_reflectivity(1.0, 4.0)
        assert abs(gamma) == pytest.approx(1.0 / 3.0, abs=1e-6)

    def test_eps9_from_air(self):
        # From air (eps=1) to eps=9: Gamma = (1-3)/(1+3) = -0.5
        gamma = DielectricPhantom.fresnel_reflectivity(1.0, 9.0)
        assert abs(gamma) == pytest.approx(0.5, abs=1e-6)

    def test_returns_complex(self):
        gamma = DielectricPhantom.fresnel_reflectivity(1.0, 4.0)
        assert isinstance(gamma, complex)

    def test_magnitude_less_than_one(self):
        for eps in [1.5, 2.0, 4.0, 9.0, 16.0]:
            gamma = DielectricPhantom.fresnel_reflectivity(1.0, eps)
            assert abs(gamma) < 1.0

    def test_negative_for_higher_eps(self):
        # Going from lower to higher eps: Gamma should be negative (real part)
        gamma = DielectricPhantom.fresnel_reflectivity(1.0, 4.0)
        assert gamma.real < 0.0


# ===========================================================================
# make_two_inclusion_phantom
# ===========================================================================

class TestMakeTwoInclusionPhantom:
    def test_returns_phantom(self):
        ph = make_two_inclusion_phantom()
        assert isinstance(ph, DielectricPhantom)

    def test_two_inclusions(self):
        ph = make_two_inclusion_phantom()
        assert len(ph.inclusions) == 2

    def test_default_eps_bg(self):
        ph = make_two_inclusion_phantom()
        assert ph.epsilon_r_bg == pytest.approx(1.0)

    def test_custom_eps(self):
        ph = make_two_inclusion_phantom(eps_r_a=5.0, eps_r_b=12.0)
        assert ph.inclusions[0].epsilon_r == pytest.approx(5.0)
        assert ph.inclusions[1].epsilon_r == pytest.approx(12.0)


# ===========================================================================
# sar_image_to_contrast_heatmap
# ===========================================================================

class TestSarImageToContrastHeatmap:
    def test_output_shape(self):
        img = np.random.randn(50, 60) + 1j * np.random.randn(50, 60)
        hm = sar_image_to_contrast_heatmap(img)
        assert hm.shape == (50, 60)

    def test_normalized_to_one(self):
        img = np.random.randn(20, 20) + 1j * np.random.randn(20, 20)
        hm = sar_image_to_contrast_heatmap(img, normalize=True)
        assert float(np.max(hm)) == pytest.approx(1.0, abs=1e-6)

    def test_nonnegative(self):
        img = np.random.randn(20, 20) + 1j * np.random.randn(20, 20)
        hm = sar_image_to_contrast_heatmap(img)
        assert float(np.min(hm)) >= 0.0

    def test_no_normalize(self):
        img = 3.0 * np.ones((5, 5), dtype=complex)
        hm = sar_image_to_contrast_heatmap(img, normalize=False)
        assert float(np.max(hm)) == pytest.approx(3.0, abs=1e-9)

    def test_all_zeros_returns_zeros(self):
        img = np.zeros((10, 10), dtype=complex)
        hm = sar_image_to_contrast_heatmap(img, normalize=True)
        assert float(np.max(hm)) == pytest.approx(0.0, abs=1e-12)

    def test_output_dtype_float(self):
        img = np.ones((5, 5), dtype=complex)
        hm = sar_image_to_contrast_heatmap(img)
        assert hm.dtype == float or np.issubdtype(hm.dtype, np.floating)


# ===========================================================================
# permittivity_map_to_reflectivity_map
# ===========================================================================

class TestPermittivityMapToReflectivityMap:
    def test_uniform_bg_gives_zeros(self):
        eps = np.ones((20, 20)) * 1.0
        r = permittivity_map_to_reflectivity_map(eps, eps_r_bg=1.0)
        assert float(np.max(np.abs(r))) == pytest.approx(0.0, abs=1e-9)

    def test_shape_preserved(self):
        eps = np.ones((30, 40))
        eps[10, 10] = 4.0
        r = permittivity_map_to_reflectivity_map(eps, eps_r_bg=1.0)
        assert r.shape == (30, 40)

    def test_normalized_to_one(self):
        eps = np.ones((20, 20))
        eps[5, 5] = 9.0
        r = permittivity_map_to_reflectivity_map(eps, eps_r_bg=1.0, normalize=True)
        assert float(np.max(r)) == pytest.approx(1.0, abs=1e-6)

    def test_correct_fresnel_value_at_inclusion(self):
        # eps_r = 4 -> |Gamma| = 1/3
        eps = np.ones((10, 10))
        eps[5, 5] = 4.0
        r = permittivity_map_to_reflectivity_map(eps, eps_r_bg=1.0, normalize=False)
        assert r[5, 5] == pytest.approx(1.0 / 3.0, abs=1e-4)

    def test_no_normalize(self):
        eps = np.ones((10, 10))
        eps[3, 3] = 9.0   # |Gamma| = 0.5
        r = permittivity_map_to_reflectivity_map(eps, eps_r_bg=1.0, normalize=False)
        assert r[3, 3] == pytest.approx(0.5, abs=1e-4)
        assert r[0, 0] == pytest.approx(0.0, abs=1e-9)


# ===========================================================================
# compare_heatmaps
# ===========================================================================

class TestCompareHeatmaps:
    def test_identical_gives_zero_rmse(self):
        a = np.random.rand(20, 20)
        m = compare_heatmaps(a, a)
        assert m["rmse"] == pytest.approx(0.0, abs=1e-10)

    def test_different_nonzero_rmse(self):
        a = np.zeros((10, 10))
        b = np.ones((10, 10))
        m = compare_heatmaps(a, b)
        assert m["rmse"] > 0.0

    def test_required_keys_present(self):
        a = np.zeros((5, 5))
        m = compare_heatmaps(a, a)
        for key in ("mse", "rmse", "max_abs_error", "reconstructed_peak_idx",
                    "ground_truth_peak_idx", "peak_location_match", "note"):
            assert key in m

    def test_shape_mismatch_raises(self):
        a = np.zeros((5, 5))
        b = np.zeros((5, 6))
        with pytest.raises(ValueError, match="Shape mismatch"):
            compare_heatmaps(a, b)

    def test_note_mentions_fresnel(self):
        a = np.zeros((5, 5))
        m = compare_heatmaps(a, a)
        assert "Fresnel" in m["note"]

    def test_max_abs_error_correct(self):
        a = np.zeros((10, 10))
        b = np.zeros((10, 10))
        b[3, 7] = 0.8
        m = compare_heatmaps(a, b)
        assert m["max_abs_error"] == pytest.approx(0.8, abs=1e-6)


# ===========================================================================
# locate_contrast_peaks_2d
# ===========================================================================

class TestLocateContrastPeaks2d:
    def _make_test_heatmap(self):
        h = np.zeros((100, 100))
        h[25, 30] = 1.0   # peak A
        h[70, 65] = 0.7   # peak B
        x = np.linspace(-0.5, 0.5, 100)
        z = np.linspace(0.1, 1.1, 100)
        return h, x, z

    def test_finds_strongest_peak(self):
        h, x, z = self._make_test_heatmap()
        peaks = locate_contrast_peaks_2d(h, x, z, n_peaks=1, threshold=0.1)
        assert len(peaks) == 1
        assert peaks[0]["value"] == pytest.approx(1.0, abs=1e-9)

    def test_finds_two_peaks(self):
        h, x, z = self._make_test_heatmap()
        peaks = locate_contrast_peaks_2d(h, x, z, n_peaks=2, threshold=0.1)
        assert len(peaks) == 2

    def test_threshold_filters(self):
        h, x, z = self._make_test_heatmap()
        h[70, 65] = 0.2  # below threshold
        peaks = locate_contrast_peaks_2d(h, x, z, n_peaks=5, threshold=0.5)
        assert len(peaks) == 1

    def test_peak_has_required_keys(self):
        h, x, z = self._make_test_heatmap()
        peaks = locate_contrast_peaks_2d(h, x, z, n_peaks=1, threshold=0.1)
        assert peaks[0].keys() >= {"x_m", "z_m", "value", "ix", "iz"}

    def test_peak_position_correct(self):
        h = np.zeros((50, 50))
        h[10, 20] = 1.0
        x = np.linspace(0, 1, 50)
        z = np.linspace(0, 1, 50)
        peaks = locate_contrast_peaks_2d(h, x, z, n_peaks=1, threshold=0.1)
        assert peaks[0]["ix"] == 10
        assert peaks[0]["iz"] == 20

    def test_empty_heatmap_returns_nothing(self):
        h = np.zeros((20, 20))
        x = np.linspace(0, 1, 20)
        z = np.linspace(0, 1, 20)
        peaks = locate_contrast_peaks_2d(h, x, z, n_peaks=3, threshold=0.1)
        assert len(peaks) == 0


# ===========================================================================
# heatmap_summary
# ===========================================================================

class TestHeatmapSummary:
    def test_returns_dict(self):
        h = np.random.rand(30, 30)
        x = np.linspace(-0.5, 0.5, 30)
        z = np.linspace(0.1, 1.1, 30)
        s = heatmap_summary(h, x, z)
        assert isinstance(s, dict)

    def test_required_keys(self):
        h = np.random.rand(20, 20)
        x = np.linspace(0, 1, 20)
        z = np.linspace(0, 1, 20)
        s = heatmap_summary(h, x, z)
        for key in ("shape", "x_range_m", "z_range_m", "mean_contrast",
                    "max_contrast", "n_peaks_found", "peaks", "note"):
            assert key in s

    def test_note_mentions_relative(self):
        h = np.random.rand(10, 10)
        x = np.linspace(0, 1, 10)
        z = np.linspace(0, 1, 10)
        s = heatmap_summary(h, x, z)
        assert "relative" in s["note"].lower() or "Relative" in s["note"]

    def test_with_inclusions(self):
        h = np.zeros((50, 50))
        h[12, 25] = 1.0
        x = np.linspace(-0.5, 0.5, 50)
        z = np.linspace(0.1, 1.1, 50)
        incl = DielectricInclusion(x_m=x[12], z_m=z[25], radius_m=0.02, epsilon_r=4.0)
        s = heatmap_summary(h, x, z, inclusions=[incl])
        assert "inclusion_matches" in s
        assert len(s["inclusion_matches"]) == 1

    def test_shape_matches_input(self):
        h = np.random.rand(15, 25)
        x = np.linspace(0, 1, 15)
        z = np.linspace(0, 1, 25)
        s = heatmap_summary(h, x, z)
        assert s["shape"] == (15, 25)


# ===========================================================================
# End-to-end: phantom -> simulation -> heatmap
# ===========================================================================

class TestEndToEndPhantomHeatmap:
    def test_phantom_to_targets_reflectivities_match_fresnel(self):
        ph = make_two_inclusion_phantom(eps_r_bg=1.0, eps_r_a=4.0, eps_r_b=9.0)
        targets = ph.to_point_targets()
        assert len(targets) == 2
        # Check magnitudes approximately match Fresnel
        # A: eps=4 -> |Gamma|=1/3
        # B: eps=9 -> |Gamma|=0.5
        mags = sorted([abs(t.reflectivity) for t in targets])
        expected = sorted([1.0 / 3.0, 0.5])
        for m, e in zip(mags, expected):
            assert m == pytest.approx(e, abs=1e-4)

    def test_reflectivity_map_peak_at_inclusion(self):
        ph = DielectricPhantom(
            x_min_m=-0.5, x_max_m=0.5,
            z_min_m=0.1, z_max_m=1.1,
            n_x=100, n_z=100,
            epsilon_r_bg=1.0,
            inclusions=[
                DielectricInclusion(x_m=0.0, z_m=0.6, radius_m=0.05, epsilon_r=9.0),
            ],
        )
        x, z, refl = ph.reflectivity_map()
        ix_peak, iz_peak = np.unravel_index(np.argmax(refl), refl.shape)
        # Peak should be near inclusion center
        assert abs(x[ix_peak] - 0.0) < 0.1   # within 10 cm
        assert abs(z[iz_peak] - 0.6) < 0.1

    def test_sar_heatmap_pipeline_full(self):
        """Full pipeline: phantom -> simulate_h_matrix -> backprojection -> heatmap."""
        from simulation.ofdm_uwb_sar_simulator import OFDMParameters, simulate_h_matrix, backprojection_image

        ph = make_two_inclusion_phantom(eps_r_bg=1.0, eps_r_a=4.0, eps_r_b=9.0)
        targets = ph.to_point_targets()

        params = OFDMParameters(
            n_fft=128, n_active=80, cp_len=16,
            sample_rate_hz=500e6, center_freq_hz=3.0e9,
            dc_null=True, guard_bins=4, pilot_seed=42,
        )
        az = np.linspace(-0.5, 0.5, 11)
        H, freqs, _ = simulate_h_matrix(params, targets, az, noise_std=0.0, seed=0)

        x_img = np.linspace(-0.75, 0.75, 50)
        z_img = np.linspace(0.05, 1.55, 50)
        sar_img = backprojection_image(H, freqs, az, x_img, z_img, padding_factor=4)
        heatmap = sar_image_to_contrast_heatmap(sar_img, normalize=True)

        assert heatmap.shape == (50, 50)
        assert float(np.max(heatmap)) == pytest.approx(1.0, abs=1e-6)
        assert float(np.min(heatmap)) >= 0.0

        # Find reconstructed peak: should be near one of the inclusions
        peaks = locate_contrast_peaks_2d(heatmap, x_img, z_img, n_peaks=2, threshold=0.3)
        assert len(peaks) >= 1
        # At least one peak should be within 0.3 m of a true inclusion
        true_positions = [(incl.x_m, incl.z_m) for incl in ph.inclusions]
        any_close = any(
            any(
                math.sqrt((pk["x_m"] - tx) ** 2 + (pk["z_m"] - tz) ** 2) < 0.30
                for tx, tz in true_positions
            )
            for pk in peaks
        )
        assert any_close, f"No reconstructed peak within 0.30 m of any true inclusion. Peaks: {peaks}"

    def test_no_bladerf_import_in_new_modules(self):
        """Verify that phantom_permittivity_map and dielectric_contrast_heatmap do not import bladerf."""
        import pathlib
        import re
        files_to_check = [
            pathlib.Path(__file__).parents[1] / "simulation" / "phantom_permittivity_map.py",
            pathlib.Path(__file__).parents[1] / "processing" / "dielectric_contrast_heatmap.py",
        ]
        for fpath in files_to_check:
            text = fpath.read_text(encoding="utf-8")
            import_lines = [
                ln for ln in text.splitlines()
                if ln.strip().startswith(("import ", "from "))
            ]
            import_src = "\n".join(import_lines).lower()
            assert "bladerf" not in import_src, (
                f"{fpath.name} contains a bladeRF import in import lines: {import_src[:200]}"
            )
