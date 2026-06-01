"""
OFDM block stitcher for UWB-OFDM-SAR.

Stitches multiple OFDM channel-estimate blocks (each covering one bladeRF
center frequency) into a single wideband H(f) vector.

Hardware-independent. No bladeRF import. Safe to call offline.

Architecture context
--------------------
The bladeRF instantaneous bandwidth is ~56 MHz.  To cover the UWB range
(e.g. 500 MHz -- 3 GHz), multiple center frequencies are used.  Each block
provides H[k] over a contiguous sub-band.  Stitching concatenates these
sub-bands into one H(f) estimate.

Key challenges in real hardware stitching (documented, not fully solved here)
---------------------------------------------------------------------------
1. Phase discontinuity: the LO phase at each retune is random.  Overlap
   correction partially mitigates this but cannot remove it completely without
   a common reference (e.g. a reflector or cable calibration).
2. Gain variation: RX gain and cable loss vary across sub-bands.  Amplitude
   normalization reduces this but is not a substitute for a calibrated path.
3. Frequency grid alignment: blocks may have different subcarrier spacings or
   sample rates.  This version assumes a uniform grid within each block.

First-version strategy (implemented here)
-----------------------------------------
1. Sort blocks by center frequency.
2. Map each block's active subcarrier indices to absolute RF frequencies.
3. Merge frequency grids (concatenate, remove duplicates by taking the lower
   block's value at overlapping frequencies).
4. Optionally estimate and correct the phase offset at each block boundary
   using overlapping subcarriers.
5. Return (freqs_hz, H_total).

This is a scaffold: the logic is correct for simulation but real hardware
stitching will require calibration data (reflector, known-target, or
through-path).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "OFDMStitchBlock",
    "validate_blocks",
    "discard_invalid_subcarriers",
    "normalize_block_magnitude",
    "estimate_overlap_phase_offset",
    "apply_phase_offset",
    "stitch_ofdm_blocks",
    "summarize_stitched_response",
]


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------

@dataclass
class OFDMStitchBlock:
    """
    One frequency block for stitching.

    Fields
    ------
    freqs_hz  : float array (n,).  Absolute RF frequencies for active subcarriers.
    H         : complex array (n,).  Channel estimate at those frequencies.
    block_id  : Identifier string (e.g., center frequency label).
    valid_mask: bool array (n,).  True for subcarriers to include in stitch.
    metadata  : Arbitrary key-value dict.
    """
    freqs_hz: np.ndarray
    H: np.ndarray
    block_id: str = "block"
    valid_mask: np.ndarray = field(default_factory=lambda: np.array([], dtype=bool))
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if len(self.valid_mask) == 0:
            self.valid_mask = np.ones(len(self.freqs_hz), dtype=bool)

    @property
    def n_subcarriers(self) -> int:
        return len(self.freqs_hz)

    @property
    def center_freq_hz(self) -> float:
        if len(self.freqs_hz) == 0:
            return 0.0
        return float(np.mean(self.freqs_hz))

    @property
    def freq_min_hz(self) -> float:
        return float(np.min(self.freqs_hz)) if len(self.freqs_hz) > 0 else 0.0

    @property
    def freq_max_hz(self) -> float:
        return float(np.max(self.freqs_hz)) if len(self.freqs_hz) > 0 else 0.0


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_blocks(blocks: list[OFDMStitchBlock]) -> None:
    """
    Raise ValueError if any block is invalid or the list is empty.

    Checks:
    - At least one block.
    - Each block has freqs_hz and H with the same length > 0.
    - freqs_hz values are strictly increasing within each block.
    - valid_mask has the same length as freqs_hz.
    """
    if not blocks:
        raise ValueError("blocks list is empty.")
    for i, blk in enumerate(blocks):
        if len(blk.freqs_hz) == 0:
            raise ValueError(f"Block {i} ('{blk.block_id}') has zero subcarriers.")
        if len(blk.freqs_hz) != len(blk.H):
            raise ValueError(
                f"Block {i} ('{blk.block_id}'): "
                f"len(freqs_hz)={len(blk.freqs_hz)} != len(H)={len(blk.H)}."
            )
        if len(blk.valid_mask) != len(blk.freqs_hz):
            raise ValueError(
                f"Block {i} ('{blk.block_id}'): "
                f"len(valid_mask)={len(blk.valid_mask)} != len(freqs_hz)={len(blk.freqs_hz)}."
            )
        if len(blk.freqs_hz) > 1:
            diffs = np.diff(blk.freqs_hz)
            if np.any(diffs <= 0):
                raise ValueError(
                    f"Block {i} ('{blk.block_id}'): freqs_hz must be strictly increasing."
                )


# ---------------------------------------------------------------------------
# Per-block operations
# ---------------------------------------------------------------------------

def discard_invalid_subcarriers(
    H: np.ndarray,
    mask: np.ndarray,
) -> np.ndarray:
    """
    Return H with invalid (mask=False) subcarriers set to zero.

    Parameters
    ----------
    H    : complex array (n,).
    mask : bool array (n,).  True = keep.

    Returns
    -------
    H_masked : complex array (n,).
    """
    result = H.copy()
    result[~mask] = 0.0
    return result


def normalize_block_magnitude(block: OFDMStitchBlock) -> OFDMStitchBlock:
    """
    Return a copy of block with |H| normalized to unit mean over valid bins.

    Useful for correcting gross gain differences between blocks before stitching.
    Does not correct phase.  Real calibration requires a known path.

    Parameters
    ----------
    block : OFDMStitchBlock.

    Returns
    -------
    OFDMStitchBlock with normalized H.
    """
    valid_H = block.H[block.valid_mask]
    mean_mag = float(np.mean(np.abs(valid_H))) if len(valid_H) > 0 else 1.0
    if mean_mag < 1e-15:
        mean_mag = 1.0
    H_norm = block.H / mean_mag
    return OFDMStitchBlock(
        freqs_hz=block.freqs_hz.copy(),
        H=H_norm,
        block_id=block.block_id,
        valid_mask=block.valid_mask.copy(),
        metadata=dict(block.metadata, normalized=True, norm_factor=mean_mag),
    )


# ---------------------------------------------------------------------------
# Phase offset estimation and correction
# ---------------------------------------------------------------------------

def estimate_overlap_phase_offset(
    block_a: OFDMStitchBlock,
    block_b: OFDMStitchBlock,
    freq_tol_hz: float = 1e3,
) -> float:
    """
    Estimate the phase offset between two adjacent blocks using overlapping frequencies.

    For each frequency f in block_a that also appears in block_b (within
    freq_tol_hz), compute angle(H_b[f]) - angle(H_a[f]).  Return the circular
    mean of those differences.

    Limitation: this can only remove a static phase offset, not a linear phase
    ramp (which would imply a delay difference between retunes).

    Parameters
    ----------
    block_a, block_b : OFDMStitchBlock.  Must be sorted by frequency.
    freq_tol_hz      : Frequency matching tolerance [Hz].

    Returns
    -------
    phase_offset_rad : float.  Add this to block_b's phase to align with block_a.
                       Returns 0.0 if no overlapping frequencies found.
    """
    offsets = []
    for fa, ha in zip(block_a.freqs_hz, block_a.H):
        diffs = np.abs(block_b.freqs_hz - fa)
        best = int(np.argmin(diffs))
        if diffs[best] <= freq_tol_hz:
            if block_a.valid_mask[np.where(block_a.freqs_hz == fa)[0][0]] and block_b.valid_mask[best]:
                if np.abs(ha) > 1e-12 and np.abs(block_b.H[best]) > 1e-12:
                    offsets.append(np.angle(block_b.H[best]) - np.angle(ha))
    if not offsets:
        return 0.0
    # Circular mean
    offsets_arr = np.array(offsets)
    return float(np.angle(np.mean(np.exp(1j * offsets_arr))))


def apply_phase_offset(
    block: OFDMStitchBlock,
    phase_offset_rad: float,
) -> OFDMStitchBlock:
    """
    Return a copy of block with H multiplied by exp(-j * phase_offset_rad).

    This corrects the LO phase jump between retunes when stitching blocks.

    Parameters
    ----------
    block            : OFDMStitchBlock.
    phase_offset_rad : Phase offset to remove [radians].

    Returns
    -------
    OFDMStitchBlock with corrected phase.
    """
    H_corrected = block.H * np.exp(-1j * phase_offset_rad)
    return OFDMStitchBlock(
        freqs_hz=block.freqs_hz.copy(),
        H=H_corrected,
        block_id=block.block_id,
        valid_mask=block.valid_mask.copy(),
        metadata=dict(block.metadata, phase_corrected_rad=phase_offset_rad),
    )


# ---------------------------------------------------------------------------
# Stitching
# ---------------------------------------------------------------------------

def stitch_ofdm_blocks(
    blocks: list[OFDMStitchBlock],
    use_overlap: bool = True,
    freq_tol_hz: float = 1e3,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Stitch multiple OFDM blocks into a single wideband H(f) estimate.

    Steps:
    1. Validate blocks.
    2. Sort blocks by center frequency.
    3. Apply valid_mask to each block.
    4. Optionally estimate and remove phase offsets at block boundaries.
    5. Merge all (freq, H) pairs, discarding duplicate frequencies
       (preferring the lower block's value at boundaries).
    6. Sort merged result by frequency.

    Limitations (documented):
    - Phase correction removes only static offset, not LO phase ramp.
    - Amplitude normalization is not applied here; use normalize_block_magnitude
      before stitching if blocks have different gain levels.
    - Real hardware stitching requires calibration (reflector or cable path).

    Parameters
    ----------
    blocks      : list of OFDMStitchBlock.
    use_overlap : If True, estimate and apply phase offset at each boundary.
    freq_tol_hz : Frequency matching tolerance for overlap detection [Hz].

    Returns
    -------
    freqs_hz : float array (N_total,).  Merged frequency grid, sorted.
    H_total  : complex array (N_total,).  Stitched channel estimate.
    """
    validate_blocks(blocks)

    # Sort by center frequency
    sorted_blocks = sorted(blocks, key=lambda b: b.center_freq_hz)

    # Apply valid masks
    masked = []
    for blk in sorted_blocks:
        f = blk.freqs_hz[blk.valid_mask]
        h = blk.H[blk.valid_mask]
        masked.append(OFDMStitchBlock(freqs_hz=f, H=h, block_id=blk.block_id))

    # Phase offset correction using adjacent block boundaries
    if use_overlap and len(masked) > 1:
        corrected = [masked[0]]
        for i in range(1, len(masked)):
            offset = estimate_overlap_phase_offset(corrected[-1], masked[i], freq_tol_hz)
            corrected.append(apply_phase_offset(masked[i], offset))
        masked = corrected

    # Merge: concatenate all (freq, H) pairs
    all_freqs = np.concatenate([b.freqs_hz for b in masked])
    all_H = np.concatenate([b.H for b in masked])

    # Sort by frequency
    sort_idx = np.argsort(all_freqs)
    all_freqs = all_freqs[sort_idx]
    all_H = all_H[sort_idx]

    # Remove duplicates: keep first occurrence (lower block's value)
    _, unique_idx = np.unique(np.round(all_freqs / freq_tol_hz).astype(int), return_index=True)
    freqs_hz = all_freqs[unique_idx]
    H_total = all_H[unique_idx]

    return freqs_hz, H_total


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def summarize_stitched_response(
    freqs_hz: np.ndarray,
    H: np.ndarray,
) -> str:
    """
    Return a human-readable ASCII summary of a stitched H(f) response.

    Safe for Windows cp1252 console. No Unicode arrows or special chars.
    """
    n = len(freqs_hz)
    if n == 0:
        return "Stitched response: empty."

    mag = np.abs(H)
    mag_mean = float(np.mean(mag))
    mag_max = float(np.max(mag))
    mag_min = float(np.min(mag))
    mag_db_range = (
        20.0 * np.log10(mag_max / max(mag_min, 1e-15)) if mag_max > 0 else 0.0
    )
    bw_hz = float(np.max(freqs_hz)) - float(np.min(freqs_hz))

    lines = [
        "Stitched H(f) Summary",
        "=" * 40,
        f"  n_subcarriers : {n}",
        f"  freq min      : {float(np.min(freqs_hz))/1e6:.3f} MHz",
        f"  freq max      : {float(np.max(freqs_hz))/1e6:.3f} MHz",
        f"  bandwidth     : {bw_hz/1e6:.3f} MHz",
        f"  |H| mean      : {mag_mean:.4f}",
        f"  |H| max       : {mag_max:.4f}",
        f"  |H| dB range  : {mag_db_range:.1f} dB",
    ]
    return "\n".join(lines)
