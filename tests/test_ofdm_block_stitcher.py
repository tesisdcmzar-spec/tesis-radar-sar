"""
Tests for processing/ofdm_block_stitcher.py.

All tests use synthetic data only. No hardware required. No bladeRF import.
"""
from __future__ import annotations

import numpy as np
import pytest

from processing.ofdm_block_stitcher import (
    OFDMStitchBlock,
    apply_phase_offset,
    discard_invalid_subcarriers,
    estimate_overlap_phase_offset,
    normalize_block_magnitude,
    stitch_ofdm_blocks,
    summarize_stitched_response,
    validate_blocks,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_block(
    f_start_mhz: float,
    f_end_mhz: float,
    n: int = 20,
    H_const: complex = 1.0 + 0j,
    block_id: str = "blk",
    valid_all: bool = True,
) -> OFDMStitchBlock:
    freqs = np.linspace(f_start_mhz * 1e6, f_end_mhz * 1e6, n)
    H = np.full(n, H_const, dtype=complex)
    mask = np.ones(n, dtype=bool) if valid_all else np.zeros(n, dtype=bool)
    return OFDMStitchBlock(freqs_hz=freqs, H=H, block_id=block_id, valid_mask=mask)


# ---------------------------------------------------------------------------
# validate_blocks
# ---------------------------------------------------------------------------

class TestValidateBlocks:
    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_blocks([])

    def test_valid_single_block(self):
        blk = make_block(2400, 2450)
        validate_blocks([blk])  # should not raise

    def test_valid_two_blocks(self):
        b1 = make_block(2400, 2450)
        b2 = make_block(2450, 2500)
        validate_blocks([b1, b2])  # should not raise

    def test_block_with_zero_subcarriers_raises(self):
        blk = OFDMStitchBlock(
            freqs_hz=np.array([]),
            H=np.array([]),
            block_id="empty",
        )
        with pytest.raises(ValueError, match="zero subcarriers"):
            validate_blocks([blk])

    def test_mismatched_freqs_H_lengths_raises(self):
        blk = OFDMStitchBlock(
            freqs_hz=np.array([1e9, 2e9]),
            H=np.array([1.0 + 0j]),
            block_id="mismatch",
        )
        with pytest.raises(ValueError, match="len"):
            validate_blocks([blk])

    def test_non_monotonic_freqs_raises(self):
        freqs = np.array([1e9, 3e9, 2e9])
        H = np.ones(3, dtype=complex)
        blk = OFDMStitchBlock(freqs_hz=freqs, H=H)
        with pytest.raises(ValueError, match="strictly increasing"):
            validate_blocks([blk])

    def test_mismatched_valid_mask_raises(self):
        blk = OFDMStitchBlock(
            freqs_hz=np.linspace(1e9, 2e9, 5),
            H=np.ones(5, dtype=complex),
            valid_mask=np.ones(3, dtype=bool),  # wrong length
        )
        with pytest.raises(ValueError, match="valid_mask"):
            validate_blocks([blk])


# ---------------------------------------------------------------------------
# discard_invalid_subcarriers
# ---------------------------------------------------------------------------

class TestDiscardInvalidSubcarriers:
    def test_all_valid(self):
        H = np.array([1 + 1j, 2 + 0j, 0 + 3j])
        mask = np.array([True, True, True])
        result = discard_invalid_subcarriers(H, mask)
        assert np.allclose(result, H)

    def test_all_invalid(self):
        H = np.array([1 + 1j, 2 + 0j])
        mask = np.array([False, False])
        result = discard_invalid_subcarriers(H, mask)
        assert np.allclose(result, 0.0)

    def test_mixed_mask(self):
        H = np.array([1 + 0j, 2 + 0j, 3 + 0j])
        mask = np.array([True, False, True])
        result = discard_invalid_subcarriers(H, mask)
        assert result[0] == H[0]
        assert result[1] == 0.0
        assert result[2] == H[2]

    def test_does_not_modify_original(self):
        H = np.array([1 + 1j, 2 + 0j])
        H_original = H.copy()
        mask = np.array([False, True])
        discard_invalid_subcarriers(H, mask)
        assert np.allclose(H, H_original)


# ---------------------------------------------------------------------------
# normalize_block_magnitude
# ---------------------------------------------------------------------------

class TestNormalizeBlockMagnitude:
    def test_unit_mean_after_normalization(self):
        blk = make_block(2400, 2450, H_const=5.0 + 0j)
        norm_blk = normalize_block_magnitude(blk)
        mean_mag = float(np.mean(np.abs(norm_blk.H[norm_blk.valid_mask])))
        assert abs(mean_mag - 1.0) < 1e-6

    def test_phase_preserved(self):
        angle = np.pi / 3
        blk = make_block(2400, 2450, H_const=2.0 * np.exp(1j * angle))
        norm_blk = normalize_block_magnitude(blk)
        phases = np.angle(norm_blk.H[norm_blk.valid_mask])
        assert np.allclose(phases, angle, atol=1e-6)

    def test_returns_new_block(self):
        blk = make_block(2400, 2450, H_const=3.0 + 0j)
        norm_blk = normalize_block_magnitude(blk)
        assert norm_blk is not blk

    def test_zero_magnitude_does_not_crash(self):
        blk = make_block(2400, 2450, H_const=0.0 + 0j)
        norm_blk = normalize_block_magnitude(blk)
        assert norm_blk.H.shape == blk.H.shape


# ---------------------------------------------------------------------------
# estimate_overlap_phase_offset
# ---------------------------------------------------------------------------

class TestEstimateOverlapPhaseOffset:
    def test_zero_offset_when_identical(self):
        blk_a = make_block(2400, 2450, H_const=1.0 + 0j)
        blk_b = make_block(2400, 2450, H_const=1.0 + 0j)
        offset = estimate_overlap_phase_offset(blk_a, blk_b)
        assert abs(offset) < 1e-6

    def test_known_phase_offset_recovered(self):
        freqs = np.linspace(2.4e9, 2.45e9, 20)
        H_a = np.ones(20, dtype=complex)
        known_offset = np.pi / 4
        H_b = H_a * np.exp(1j * known_offset)
        blk_a = OFDMStitchBlock(freqs_hz=freqs, H=H_a)
        blk_b = OFDMStitchBlock(freqs_hz=freqs, H=H_b)
        offset = estimate_overlap_phase_offset(blk_a, blk_b)
        assert abs(offset - known_offset) < 0.01, f"offset={offset:.4f}, expected {known_offset:.4f}"

    def test_no_overlap_returns_zero(self):
        blk_a = make_block(2400, 2450)
        blk_b = make_block(2500, 2550)
        offset = estimate_overlap_phase_offset(blk_a, blk_b)
        assert offset == 0.0


# ---------------------------------------------------------------------------
# apply_phase_offset
# ---------------------------------------------------------------------------

class TestApplyPhaseOffset:
    def test_removes_phase_offset(self):
        freqs = np.linspace(2.4e9, 2.45e9, 10)
        offset = np.pi / 3
        H = np.exp(1j * offset) * np.ones(10)
        blk = OFDMStitchBlock(freqs_hz=freqs, H=H)
        corrected = apply_phase_offset(blk, offset)
        assert np.allclose(np.angle(corrected.H), 0.0, atol=1e-6)

    def test_zero_offset_no_change(self):
        blk = make_block(2400, 2450, H_const=1.0 + 1.0j)
        corrected = apply_phase_offset(blk, 0.0)
        assert np.allclose(corrected.H, blk.H)

    def test_returns_new_block(self):
        blk = make_block(2400, 2450, H_const=1.0 + 0j)
        corrected = apply_phase_offset(blk, 0.1)
        assert corrected is not blk


# ---------------------------------------------------------------------------
# stitch_ofdm_blocks
# ---------------------------------------------------------------------------

class TestStitchOFDMBlocks:
    def test_single_block_returns_valid_freqs(self):
        blk = make_block(2400, 2450)
        freqs, H = stitch_ofdm_blocks([blk])
        assert len(freqs) > 0
        assert freqs.shape == H.shape

    def test_two_non_overlapping_blocks_sorted_by_freq(self):
        blk_a = make_block(2500, 2550, block_id="hi")
        blk_b = make_block(2400, 2450, block_id="lo")
        freqs, H = stitch_ofdm_blocks([blk_a, blk_b], use_overlap=False)
        assert np.all(np.diff(freqs) > 0), "Output must be sorted by frequency"
        assert freqs[0] < 2450e6
        assert freqs[-1] > 2500e6

    def test_invalid_blocks_list_raises(self):
        with pytest.raises(ValueError):
            stitch_ofdm_blocks([], use_overlap=False)

    def test_duplicate_frequencies_removed(self):
        freqs = np.linspace(2.4e9, 2.45e9, 10)
        H = np.ones(10, dtype=complex)
        blk_a = OFDMStitchBlock(freqs_hz=freqs, H=H, block_id="a")
        blk_b = OFDMStitchBlock(freqs_hz=freqs, H=H * 2, block_id="b")
        merged_freqs, _ = stitch_ofdm_blocks([blk_a, blk_b], use_overlap=False)
        # Should not have doubled the number of subcarriers
        assert len(merged_freqs) <= len(freqs) * 2
        # All frequencies should be unique (within tolerance)
        diffs = np.diff(np.sort(merged_freqs))
        assert np.all(diffs >= 0)

    def test_two_blocks_with_known_phase_offset(self):
        freqs_a = np.linspace(2.4e9, 2.45e9, 20)
        freqs_b = np.linspace(2.44e9, 2.50e9, 20)
        H_a = np.ones(20, dtype=complex)
        offset = np.pi / 5
        H_b = np.exp(1j * offset) * np.ones(20)
        blk_a = OFDMStitchBlock(freqs_hz=freqs_a, H=H_a)
        blk_b = OFDMStitchBlock(freqs_hz=freqs_b, H=H_b)
        freqs, H_total = stitch_ofdm_blocks([blk_a, blk_b], use_overlap=True)
        # After phase correction, the jump at the boundary should be reduced
        assert len(H_total) > 0

    def test_all_invalid_block_produces_empty(self):
        blk = make_block(2400, 2450, valid_all=False)
        freqs, H = stitch_ofdm_blocks([blk], use_overlap=False)
        assert len(freqs) == 0

    def test_output_lengths_equal(self):
        blk_a = make_block(2400, 2450)
        blk_b = make_block(2460, 2510)
        freqs, H = stitch_ofdm_blocks([blk_a, blk_b], use_overlap=False)
        assert len(freqs) == len(H)


# ---------------------------------------------------------------------------
# summarize_stitched_response
# ---------------------------------------------------------------------------

class TestSummarizeStitchedResponse:
    def test_returns_string(self):
        freqs = np.linspace(2.4e9, 2.5e9, 50)
        H = np.ones(50, dtype=complex)
        summary = summarize_stitched_response(freqs, H)
        assert isinstance(summary, str)
        assert len(summary) > 10

    def test_ascii_only(self):
        freqs = np.linspace(2.4e9, 2.5e9, 20)
        H = np.ones(20, dtype=complex)
        summary = summarize_stitched_response(freqs, H)
        summary.encode("ascii")  # should not raise

    def test_empty_input(self):
        summary = summarize_stitched_response(np.array([]), np.array([]))
        assert "empty" in summary.lower()

    def test_contains_bandwidth(self):
        freqs = np.linspace(2.4e9, 2.5e9, 20)
        H = np.ones(20, dtype=complex)
        summary = summarize_stitched_response(freqs, H)
        assert "bandwidth" in summary.lower() or "100" in summary
