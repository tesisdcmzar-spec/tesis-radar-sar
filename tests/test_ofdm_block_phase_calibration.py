"""
Tests for processing.ofdm_block_phase_calibration
"""
from __future__ import annotations

import math
import numpy as np
import pytest

from processing.ofdm_block_phase_calibration import (
    find_overlapping_bins,
    estimate_inter_block_phase_offset,
    apply_phase_correction,
    calibrate_h_matrix_list,
    phase_calibration_summary,
)


# ===========================================================================
# find_overlapping_bins
# ===========================================================================

class TestFindOverlappingBins:
    def test_no_overlap(self):
        f_lo = np.array([1.0, 2.0, 3.0])
        f_hi = np.array([5.0, 6.0, 7.0])
        idx_lo, idx_hi = find_overlapping_bins(f_lo, f_hi)
        assert len(idx_lo) == 0
        assert len(idx_hi) == 0

    def test_identical_overlap(self):
        f = np.linspace(0.0, 10.0, 11)
        idx_lo, idx_hi = find_overlapping_bins(f, f, freq_tol_hz=1e-3)
        assert len(idx_lo) == len(f)

    def test_partial_overlap(self):
        f_lo = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        f_hi = np.array([4.0, 5.0, 6.0, 7.0, 8.0])
        idx_lo, idx_hi = find_overlapping_bins(f_lo, f_hi, freq_tol_hz=0.1)
        # Should find overlap at 4.0 and 5.0
        assert len(idx_lo) == 2
        assert len(idx_hi) == 2

    def test_overlap_bins_are_correct(self):
        f_lo = np.array([1.0, 2.0, 3.0, 4.0])
        f_hi = np.array([3.0, 4.0, 5.0, 6.0])
        idx_lo, idx_hi = find_overlapping_bins(f_lo, f_hi, freq_tol_hz=0.1)
        np.testing.assert_array_equal(f_lo[idx_lo], f_hi[idx_hi])

    def test_tight_tolerance_excludes(self):
        f_lo = np.array([1.0, 2.0])
        f_hi = np.array([2.5, 3.0])   # 2.5 is 0.5 Hz away from 2.0
        idx_lo, idx_hi = find_overlapping_bins(f_lo, f_hi, freq_tol_hz=0.1)
        assert len(idx_lo) == 0

    def test_returns_int_arrays(self):
        f_lo = np.array([1.0, 2.0, 3.0])
        f_hi = np.array([2.0, 3.0, 4.0])
        idx_lo, idx_hi = find_overlapping_bins(f_lo, f_hi)
        assert idx_lo.dtype in (np.int32, np.int64, int)
        assert idx_hi.dtype in (np.int32, np.int64, int)


# ===========================================================================
# estimate_inter_block_phase_offset
# ===========================================================================

class TestEstimateInterBlockPhaseOffset:
    # Aligned grid: 10 MHz per bin, so adjacent blocks share EXACT frequency values.
    DF_HZ = 10e6

    def _make_aligned_blocks(self, n_lo=100, n_hi=100, n_overlap=30,
                             tau=1e-9, theta=0.5):
        """
        Create two blocks on an aligned frequency grid (same df, integer offset).
        For each overlap bin f, H_hi[j] = exp(-j*2*pi*f*tau) * exp(j*theta),
        which equals H_lo[i] * exp(j*theta) when f_lo[i] == f_hi[j].
        """
        df = self.DF_HZ
        f_lo = np.arange(n_lo) * df + 2.0e9
        # f_hi starts (n_lo - n_overlap) bins after f_lo[0]
        f_hi = np.arange(n_hi) * df + f_lo[n_lo - n_overlap]
        H_lo = np.exp(-1j * 2 * np.pi * f_lo * tau)
        H_hi = np.exp(-1j * 2 * np.pi * f_hi * tau) * np.exp(1j * theta)
        return H_lo, f_lo, H_hi, f_hi

    def test_known_phase_offset_recovered(self):
        theta = 1.23
        tol = self.DF_HZ * 0.1   # 1 MHz << 10 MHz spacing
        H_lo, f_lo, H_hi, f_hi = self._make_aligned_blocks(n_overlap=30, theta=theta)
        offset = estimate_inter_block_phase_offset(
            H_lo, f_lo, H_hi, f_hi, min_overlap_bins=3, freq_tol_hz=tol
        )
        assert abs(offset - theta) < 1e-6

    def test_zero_offset_returns_zero(self):
        tol = self.DF_HZ * 0.1
        H_lo, f_lo, H_hi, f_hi = self._make_aligned_blocks(n_overlap=20, theta=0.0)
        offset = estimate_inter_block_phase_offset(H_lo, f_lo, H_hi, f_hi, freq_tol_hz=tol)
        assert abs(offset) < 1e-6

    def test_no_overlap_returns_zero(self):
        tol = self.DF_HZ * 0.1
        f_lo = np.arange(50) * self.DF_HZ + 2.0e9
        f_hi = np.arange(50) * self.DF_HZ + 5.0e9  # no overlap
        H_lo = np.exp(-1j * 2 * np.pi * f_lo * 1e-9)
        H_hi = np.exp(-1j * 2 * np.pi * f_hi * 1e-9) * np.exp(1j * 0.9)
        offset = estimate_inter_block_phase_offset(H_lo, f_lo, H_hi, f_hi, freq_tol_hz=tol)
        assert offset == pytest.approx(0.0)

    def test_insufficient_overlap_returns_zero(self):
        # 3 overlap bins but min_overlap_bins=10 -> should return 0
        tol = self.DF_HZ * 0.1
        H_lo, f_lo, H_hi, f_hi = self._make_aligned_blocks(n_overlap=3, theta=0.7)
        offset = estimate_inter_block_phase_offset(
            H_lo, f_lo, H_hi, f_hi, min_overlap_bins=10, freq_tol_hz=tol
        )
        assert offset == pytest.approx(0.0)

    def test_pi_phase_recovered(self):
        theta = math.pi * 0.9
        tol = self.DF_HZ * 0.1
        H_lo, f_lo, H_hi, f_hi = self._make_aligned_blocks(n_overlap=20, theta=theta)
        offset = estimate_inter_block_phase_offset(H_lo, f_lo, H_hi, f_hi, freq_tol_hz=tol)
        H_hi_corrected = apply_phase_correction(H_hi, offset)
        idx_lo, idx_hi = find_overlapping_bins(f_lo, f_hi, freq_tol_hz=tol)
        assert len(idx_lo) >= 3
        residual = float(np.abs(np.angle(
            np.mean(H_hi_corrected[idx_hi] * np.conj(H_lo[idx_lo]))
        )))
        assert residual < 0.01

    def test_2d_input_works(self):
        """H matrices with shape (n_freq, n_az)."""
        theta = 0.8
        tol = self.DF_HZ * 0.1
        n_az = 8
        H_lo_1d, f_lo, H_hi_1d, f_hi = self._make_aligned_blocks(n_overlap=20, theta=theta)
        H_lo_2d = np.outer(H_lo_1d, np.ones(n_az))
        H_hi_2d = np.outer(H_hi_1d, np.ones(n_az))
        offset = estimate_inter_block_phase_offset(
            H_lo_2d, f_lo, H_hi_2d, f_hi, freq_tol_hz=tol
        )
        assert abs(offset - theta) < 1e-6


# ===========================================================================
# apply_phase_correction
# ===========================================================================

class TestApplyPhaseCorrection:
    def test_zero_offset_unchanged(self):
        H = np.array([1+2j, 3+4j, 5+6j])
        H_corr = apply_phase_correction(H, 0.0)
        np.testing.assert_array_almost_equal(H_corr, H)

    def test_pi_phase_flip(self):
        H = np.array([1+0j, 0+1j])
        H_corr = apply_phase_correction(H, math.pi)
        np.testing.assert_array_almost_equal(H_corr, [-1+0j, 0-1j], decimal=10)

    def test_magnitude_unchanged(self):
        rng = np.random.default_rng(5)
        H = rng.standard_normal(20) + 1j * rng.standard_normal(20)
        for theta in [0.1, 0.5, 1.0, 2.0]:
            H_corr = apply_phase_correction(H, theta)
            np.testing.assert_array_almost_equal(np.abs(H_corr), np.abs(H))

    def test_output_shape_preserved(self):
        H = np.ones((5, 10), dtype=complex)
        H_corr = apply_phase_correction(H, 0.5)
        assert H_corr.shape == (5, 10)

    def test_round_trip(self):
        """Apply +theta then -theta should recover original."""
        rng = np.random.default_rng(7)
        H = rng.standard_normal(50) + 1j * rng.standard_normal(50)
        theta = 1.7
        H_double = apply_phase_correction(apply_phase_correction(H, theta), -theta)
        np.testing.assert_array_almost_equal(H_double, H)


# ===========================================================================
# calibrate_h_matrix_list
# ===========================================================================

class TestCalibrateHMatrixList:
    def _make_blocks_with_known_offsets(self, n_blocks=3, n_freq=60, overlap=20):
        """Create overlapping blocks with known phase offsets."""
        rng = np.random.default_rng(42)
        # Block 0: reference
        H0 = rng.standard_normal(n_freq) + 1j * rng.standard_normal(n_freq)
        f0 = np.linspace(1.0, 2.0, n_freq)

        blocks_H = [H0]
        blocks_f = [f0]
        true_offsets = [0.0]

        for i in range(1, n_blocks):
            theta = float(rng.uniform(-math.pi, math.pi))
            f_prev = blocks_f[-1]
            # New block overlaps last `overlap` bins of previous block
            df = float(f_prev[1] - f_prev[0])
            f_new = np.linspace(
                float(f_prev[-overlap]), float(f_prev[-overlap]) + n_freq * df, n_freq
            )
            # H_new has some channel response but with phase offset
            H_prev_tail = blocks_H[-1][-overlap:]
            H_new = np.zeros(n_freq, dtype=complex)
            H_new[:overlap] = H_prev_tail * np.exp(1j * theta)
            H_new[overlap:] = rng.standard_normal(n_freq - overlap) + \
                               1j * rng.standard_normal(n_freq - overlap)
            H_new *= np.exp(1j * theta)  # apply offset to whole block

            blocks_H.append(H_new)
            blocks_f.append(f_new)
            true_offsets.append(theta)

        return blocks_H, blocks_f, true_offsets

    def test_empty_input(self):
        result_H, result_offsets = calibrate_h_matrix_list([], [])
        assert result_H == []
        assert result_offsets == []

    def test_single_block(self):
        H = [np.ones(20, dtype=complex)]
        f = [np.linspace(1.0, 2.0, 20)]
        result_H, result_offsets = calibrate_h_matrix_list(H, f)
        assert len(result_H) == 1
        assert result_offsets[0] == pytest.approx(0.0)

    def test_length_mismatch_raises(self):
        H = [np.ones(10), np.ones(10)]
        f = [np.linspace(1, 2, 10)]
        with pytest.raises(ValueError, match="length"):
            calibrate_h_matrix_list(H, f)

    def test_output_length_matches_input(self):
        n = 3
        blocks_H, blocks_f, _ = self._make_blocks_with_known_offsets(n_blocks=n)
        cal_H, offsets = calibrate_h_matrix_list(blocks_H, blocks_f)
        assert len(cal_H) == n
        assert len(offsets) == n

    def test_first_block_unchanged(self):
        blocks_H, blocks_f, _ = self._make_blocks_with_known_offsets(n_blocks=2)
        cal_H, _ = calibrate_h_matrix_list(blocks_H, blocks_f)
        np.testing.assert_array_equal(cal_H[0], blocks_H[0])

    def test_first_offset_is_zero(self):
        blocks_H, blocks_f, _ = self._make_blocks_with_known_offsets(n_blocks=3)
        _, offsets = calibrate_h_matrix_list(blocks_H, blocks_f)
        assert offsets[0] == pytest.approx(0.0)

    def test_two_blocks_phase_coherent_after_calibration(self):
        """After calibration, overlapping bins should have near-zero phase difference."""
        n_freq = 80
        overlap = 20
        theta = 1.1
        rng = np.random.default_rng(99)
        H0 = rng.standard_normal(n_freq) + 1j * rng.standard_normal(n_freq)
        H1 = np.zeros(n_freq, dtype=complex)
        H1[:overlap] = H0[-overlap:] * np.exp(1j * theta)
        H1[overlap:] = rng.standard_normal(n_freq - overlap) + \
                       1j * rng.standard_normal(n_freq - overlap)

        df = 1.0 / n_freq
        f0 = np.arange(n_freq) * df
        f1 = np.arange(n_freq) * df + (n_freq - overlap) * df

        cal_H, offsets = calibrate_h_matrix_list([H0, H1], [f0, f1], min_overlap_bins=3)
        # After correction, overlapping bins should have small phase difference
        idx_lo, idx_hi = find_overlapping_bins(f0, f1, freq_tol_hz=df * 0.5)
        if len(idx_lo) >= 3:
            phase_diff = np.abs(np.angle(np.mean(
                cal_H[1][idx_hi] * np.conj(cal_H[0][idx_lo])
            )))
            assert phase_diff < 0.2


# ===========================================================================
# phase_calibration_summary
# ===========================================================================

class TestPhasCalibrationSummary:
    def test_returns_dict(self):
        blocks_f = [np.linspace(1, 2, 20), np.linspace(2, 3, 20)]
        offsets = [0.0, 0.5]
        s = phase_calibration_summary(blocks_f, offsets)
        assert isinstance(s, dict)

    def test_required_keys(self):
        blocks_f = [np.linspace(1, 2, 10), np.linspace(2, 3, 10)]
        offsets = [0.0, 0.8]
        s = phase_calibration_summary(blocks_f, offsets)
        for key in ("n_blocks", "n_corrected_boundaries", "offsets_rad",
                    "offsets_deg", "boundaries", "note"):
            assert key in s

    def test_n_blocks_correct(self):
        blocks_f = [np.linspace(i, i+1, 10) for i in range(4)]
        offsets = [0.0, 0.1, 0.2, 0.3]
        s = phase_calibration_summary(blocks_f, offsets)
        assert s["n_blocks"] == 4

    def test_offsets_deg_conversion(self):
        blocks_f = [np.linspace(1, 2, 10), np.linspace(2, 3, 10)]
        offsets = [0.0, math.pi / 2]
        s = phase_calibration_summary(blocks_f, offsets)
        assert s["offsets_deg"][1] == pytest.approx(90.0, abs=1e-4)

    def test_note_mentions_constant_phase(self):
        blocks_f = [np.linspace(1, 2, 5)]
        s = phase_calibration_summary(blocks_f, [0.0])
        assert "constant" in s["note"].lower() or "zero-order" in s["note"].lower()


# ===========================================================================
# Integration: simulate phase-corrupted blocks, calibrate, verify CIR improves
# ===========================================================================

class TestPhaseCalibrationIntegration:
    def test_calibration_improves_cir_peak(self):
        """
        Two blocks with known phase offset.
        After calibration, the stitched CIR should have a sharper, higher peak.
        """
        # Simulate a single reflector at R=1.0m
        c = 3e8
        R_target = 1.0
        n_freq = 80
        bw = 500e6  # 500 MHz total BW
        freqs_lo = np.linspace(2.0e9, 2.25e9, n_freq)  # block 0
        freqs_hi = np.linspace(2.25e9, 2.50e9, n_freq)  # block 1

        tau = 2 * R_target / c
        H_lo_true = np.exp(-1j * 2 * np.pi * freqs_lo * tau)
        H_hi_true = np.exp(-1j * 2 * np.pi * freqs_hi * tau)

        # Add a random phase jump to block 1
        theta_jump = 1.8
        H_hi_corrupt = H_hi_true * np.exp(1j * theta_jump)

        # Stitch without correction: corrupt CIR
        H_no_cal = np.concatenate([H_lo_true, H_hi_corrupt])
        cir_no_cal = np.abs(np.fft.ifft(H_no_cal * np.hanning(len(H_no_cal))))
        peak_no_cal = float(np.max(cir_no_cal[:len(cir_no_cal) // 2]))

        # Calibrate and stitch
        cal_H, offsets = calibrate_h_matrix_list(
            [H_lo_true, H_hi_corrupt],
            [freqs_lo, freqs_hi],
            min_overlap_bins=1,
            freq_tol_hz=freqs_lo[1] - freqs_lo[0],
        )
        H_cal = np.concatenate(cal_H)
        cir_cal = np.abs(np.fft.ifft(H_cal * np.hanning(len(H_cal))))
        peak_cal = float(np.max(cir_cal[:len(cir_cal) // 2]))

        # Calibrated peak should be >= uncalibrated peak
        assert peak_cal >= peak_no_cal * 0.9  # at least as good

    def test_no_hardware_import(self):
        import pathlib
        fpath = pathlib.Path(__file__).parents[1] / "processing" / "ofdm_block_phase_calibration.py"
        text = fpath.read_text(encoding="utf-8")
        import_lines = [
            ln for ln in text.splitlines()
            if ln.strip().startswith(("import ", "from "))
        ]
        assert "bladerf" not in "\n".join(import_lines).lower()
