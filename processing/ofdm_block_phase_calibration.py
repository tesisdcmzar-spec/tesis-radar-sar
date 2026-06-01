"""
LO phase calibration for adjacent OFDM frequency blocks.

When the bladeRF retunes its LO to a new center frequency the RF oscillator
relocks with an arbitrary initial phase. Consecutive captures at different
LO frequencies will have random per-block phase offsets that break coherence
across the stitched band.

Algorithm (overlap-based):
  For consecutive blocks i and i+1:
    1. Find overlapping frequency bins (bins present in both blocks).
    2. Estimate phase offset:
         phi = angle( mean( H_{i+1}[overlap] * conj(H_i[overlap]) ) )
    3. Apply: H_{i+1}_corrected = H_{i+1} * exp(-j * phi)
    4. If overlap < min_overlap_bins: no correction (offset left as 0.0).

After calibration all blocks share the same phase reference (block 0).
A linear-phase ramp (group delay error from LO settling) is NOT removed
by this method -- that requires a calibrated hardware reference path.

Scientific note
---------------
Phase calibration improves stitching coherence for range-compressed CIR.
Without it, random phase jumps at block boundaries introduce spurious
sidelobes in the CIR and degrade localization accuracy.
Calibration is applied per-column of H(f, x_az); a single per-block offset
is estimated from all azimuth positions combined for robustness.

Hardware-independent. No bladeRF import. Safe to run offline.
"""
from __future__ import annotations

import numpy as np

__all__ = [
    "estimate_inter_block_phase_offset",
    "apply_phase_correction",
    "find_overlapping_bins",
    "calibrate_h_matrix_list",
    "phase_calibration_summary",
]


def find_overlapping_bins(
    freqs_lo: np.ndarray,
    freqs_hi: np.ndarray,
    freq_tol_hz: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Find overlapping frequency indices between two blocks.

    Parameters
    ----------
    freqs_lo    : float array (n_lo,). Sorted frequencies of lower block [Hz].
    freqs_hi    : float array (n_hi,). Sorted frequencies of upper block [Hz].
    freq_tol_hz : float. Frequency tolerance for matching bins [Hz].

    Returns
    -------
    idx_lo : int array. Indices into freqs_lo that have matches in freqs_hi.
    idx_hi : int array. Corresponding indices into freqs_hi.
    """
    freqs_lo = np.asarray(freqs_lo, dtype=float)
    freqs_hi = np.asarray(freqs_hi, dtype=float)
    idx_lo_list: list[int] = []
    idx_hi_list: list[int] = []

    # Overlap region: frequencies that exist in both blocks
    overlap_min = max(float(freqs_lo[0]), float(freqs_hi[0]))
    overlap_max = min(float(freqs_lo[-1]), float(freqs_hi[-1]))

    if overlap_max < overlap_min:
        # No overlap
        return np.array([], dtype=int), np.array([], dtype=int)

    # Restrict search to overlap window
    lo_mask = (freqs_lo >= overlap_min - freq_tol_hz) & (freqs_lo <= overlap_max + freq_tol_hz)
    for i_lo in np.where(lo_mask)[0]:
        diffs = np.abs(freqs_hi - freqs_lo[i_lo])
        i_hi = int(np.argmin(diffs))
        if diffs[i_hi] <= freq_tol_hz:
            idx_lo_list.append(int(i_lo))
            idx_hi_list.append(i_hi)

    return np.array(idx_lo_list, dtype=int), np.array(idx_hi_list, dtype=int)


def estimate_inter_block_phase_offset(
    H_lo: np.ndarray,
    freqs_lo: np.ndarray,
    H_hi: np.ndarray,
    freqs_hi: np.ndarray,
    min_overlap_bins: int = 3,
    freq_tol_hz: float = 1.0,
) -> float:
    """
    Estimate the LO phase jump between two adjacent frequency blocks.

    Uses overlapping subcarriers to estimate the constant phase offset
    that must be removed from H_hi to make it phase-coherent with H_lo.

    Method: phi = angle( mean( H_hi[overlap] * conj(H_lo[overlap]) ) )

    Parameters
    ----------
    H_lo            : complex array (n_lo,) or (n_lo, n_az).
                      Channel estimate for lower block.
    freqs_lo        : float array (n_lo,). Frequencies of H_lo [Hz].
    H_hi            : complex array (n_hi,) or (n_hi, n_az).
                      Channel estimate for upper (higher-frequency) block.
    freqs_hi        : float array (n_hi,). Frequencies of H_hi [Hz].
    min_overlap_bins: int. Minimum overlapping bins required for correction.
    freq_tol_hz     : float. Frequency matching tolerance [Hz].

    Returns
    -------
    phase_offset_rad : float. Estimated phase offset in radians.
                       Returns 0.0 if overlap < min_overlap_bins.
    """
    H_lo = np.asarray(H_lo, dtype=complex)
    H_hi = np.asarray(H_hi, dtype=complex)

    idx_lo, idx_hi = find_overlapping_bins(freqs_lo, freqs_hi, freq_tol_hz)

    if len(idx_lo) < min_overlap_bins:
        return 0.0

    h_lo_ov = H_lo[idx_lo]  # shape (n_ov,) or (n_ov, n_az)
    h_hi_ov = H_hi[idx_hi]

    # Cross-correlation phase: angle of mean(H_hi * conj(H_lo))
    cross = h_hi_ov * np.conj(h_lo_ov)
    mean_cross = float(np.angle(np.mean(cross)))
    return mean_cross


def apply_phase_correction(
    H: np.ndarray,
    phase_rad: float,
) -> np.ndarray:
    """
    Apply a constant phase correction to a channel estimate.

    H_corrected = H * exp(-j * phase_rad)

    Parameters
    ----------
    H          : complex array, any shape.
    phase_rad  : float. Phase offset in radians to remove.

    Returns
    -------
    H_corrected : complex array, same shape as H.
    """
    H = np.asarray(H, dtype=complex)
    return H * np.exp(-1j * float(phase_rad))


def calibrate_h_matrix_list(
    blocks_H: list[np.ndarray],
    blocks_f: list[np.ndarray],
    min_overlap_bins: int = 3,
    freq_tol_hz: float = 1.0,
) -> tuple[list[np.ndarray], list[float]]:
    """
    Sequentially calibrate inter-block phase offsets for a list of H blocks.

    Block 0 is used as the phase reference. Each subsequent block is
    phase-corrected relative to the previous (already-corrected) block.

    This is appropriate for contiguous or slightly overlapping frequency blocks
    sorted in ascending center frequency order.

    Parameters
    ----------
    blocks_H        : list of complex arrays, each (n_freq_b,) or (n_freq_b, n_az).
    blocks_f        : list of float arrays, each (n_freq_b,). Must be sorted ascending.
    min_overlap_bins: int. Minimum bins required for overlap-based correction.
    freq_tol_hz     : float. Frequency matching tolerance [Hz].

    Returns
    -------
    calibrated_H   : list of phase-corrected H arrays (same shapes as input).
    offsets_rad    : list of float. Estimated phase offsets per block boundary.
                     offsets_rad[0] = 0.0 (reference block 0),
                     offsets_rad[i] = offset applied to block i for i >= 1.

    Notes
    -----
    If two consecutive blocks have no overlap, the offset for that boundary is
    set to 0.0 (no correction applied). This leaves a potential phase discontinuity
    that will cause sidelobes in the range-compressed output.
    """
    if not blocks_H:
        return [], []
    if len(blocks_H) != len(blocks_f):
        raise ValueError(
            f"blocks_H length {len(blocks_H)} != blocks_f length {len(blocks_f)}"
        )

    calibrated: list[np.ndarray] = [np.asarray(blocks_H[0], dtype=complex)]
    offsets: list[float] = [0.0]  # block 0: no correction (reference)

    for i in range(1, len(blocks_H)):
        offset = estimate_inter_block_phase_offset(
            H_lo=calibrated[i - 1],
            freqs_lo=blocks_f[i - 1],
            H_hi=blocks_H[i],
            freqs_hi=blocks_f[i],
            min_overlap_bins=min_overlap_bins,
            freq_tol_hz=freq_tol_hz,
        )
        calibrated.append(apply_phase_correction(blocks_H[i], offset))
        offsets.append(offset)

    return calibrated, offsets


def phase_calibration_summary(
    blocks_f: list[np.ndarray],
    offsets_rad: list[float],
) -> dict:
    """
    Produce a human-readable summary of the phase calibration results.

    Parameters
    ----------
    blocks_f    : list of float arrays. Block frequency ranges.
    offsets_rad : list of float. Estimated offsets per block from calibrate_h_matrix_list().

    Returns
    -------
    summary : dict with n_blocks, block_boundaries_hz, offsets_rad, offsets_deg,
              n_corrected, n_uncorrected (offset == 0.0 after block 0), note.
    """
    n = len(offsets_rad)
    offsets_deg = [float(np.degrees(o)) for o in offsets_rad]

    # A boundary is "corrected" if the offset is non-zero (block 0 is reference)
    n_corrected = sum(1 for i, o in enumerate(offsets_rad) if i > 0 and o != 0.0)
    n_uncorrected = sum(1 for i, o in enumerate(offsets_rad) if i > 0 and o == 0.0)

    boundaries: list[dict] = []
    for i in range(1, n):
        f_lo = blocks_f[i - 1]
        f_hi = blocks_f[i]
        boundaries.append({
            "boundary_idx": i,
            "block_lo_max_hz": float(f_lo[-1]),
            "block_hi_min_hz": float(f_hi[0]),
            "gap_hz": float(f_hi[0] - f_lo[-1]),
            "offset_rad": offsets_rad[i],
            "offset_deg": offsets_deg[i],
        })

    return {
        "n_blocks": n,
        "n_corrected_boundaries": n_corrected,
        "n_uncorrected_boundaries": n_uncorrected,
        "offsets_rad": offsets_rad,
        "offsets_deg": offsets_deg,
        "boundaries": boundaries,
        "note": (
            "Only constant (zero-order) phase removed. "
            "Linear ramp (group delay) and higher-order terms not corrected. "
            "Calibration requires overlap between adjacent blocks."
        ),
    }
