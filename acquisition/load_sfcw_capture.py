"""
Real SFCW capture loader: converts .npy captures into SyntheticScan objects.

Supported formats
-----------------
Format A — 2D .npy file, shape (N_f, N_az), complex:
    Direct frequency-response matrix H[frequency, azimuth].  N_f must match
    the config's SFCW frequency grid; N_az must match the config's azimuth grid.

Format B — 1D .npy file, shape (N_f,), complex:
    Single-azimuth frequency response.  N_f must match the config's SFCW
    frequency grid.  The aperture position is set to azimuth_position_m.

Format C — directory of per-frequency .npy files (legacy bladeRF captures):
    Each file is named cap_NNN_XXXMHz.npy and holds a (N_samples,) complex128
    IQ stream captured at XXX MHz with the bladeRF at 40 MHz sample rate.
    The loader coherently averages each IQ stream (mean) to extract H(f), then
    stacks all frequency steps into an (N_f, 1) matrix.  The single aperture
    position is set to azimuth_position_m.

Config dict structure (same as configs/simulation.yaml)
--------------------------------------------------------
    sfcw:
      f_start_hz: <float>
      f_stop_hz:  <float>
      f_step_hz:  <float>
    azimuth:
      x_start_m:  <float>
      x_stop_m:   <float>
      x_step_m:   <float>
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Union

import numpy as np

from simulation.synthetic_scan import SyntheticScan


# ---------------------------------------------------------------------------
# Grid helpers
# ---------------------------------------------------------------------------

def _build_freq_grid(cfg: dict) -> np.ndarray:
    sfcw = cfg["sfcw"]
    f_start = float(sfcw["f_start_hz"])
    f_stop  = float(sfcw["f_stop_hz"])
    f_step  = float(sfcw["f_step_hz"])
    return np.arange(f_start, f_stop + 0.5 * f_step, f_step)


def _build_az_grid(cfg: dict) -> np.ndarray:
    az = cfg["azimuth"]
    x_start = float(az["x_start_m"])
    x_stop  = float(az["x_stop_m"])
    x_step  = float(az["x_step_m"])
    return np.arange(x_start, x_stop + 0.5 * x_step, x_step)


# ---------------------------------------------------------------------------
# Format-specific loaders
# ---------------------------------------------------------------------------

def _load_single_file(path: Path, cfg: dict, azimuth_position_m: float) -> SyntheticScan:
    """Load a single .npy file (format A or B)."""
    arr = np.load(str(path), mmap_mode="r")

    freqs_hz = _build_freq_grid(cfg)
    N_f_cfg = len(freqs_hz)

    if arr.ndim == 2:
        # Format A: (N_f, N_az)
        x_az_m = _build_az_grid(cfg)
        N_az_cfg = len(x_az_m)
        if arr.shape[0] != N_f_cfg:
            raise ValueError(
                f"Frequency dimension mismatch: file has {arr.shape[0]} rows "
                f"but config yields {N_f_cfg} frequency steps "
                f"({float(cfg['sfcw']['f_start_hz'])/1e6:.0f}–"
                f"{float(cfg['sfcw']['f_stop_hz'])/1e6:.0f} MHz "
                f"step {float(cfg['sfcw']['f_step_hz'])/1e6:.0f} MHz)."
            )
        if arr.shape[1] != N_az_cfg:
            raise ValueError(
                f"Azimuth dimension mismatch: file has {arr.shape[1]} columns "
                f"but config yields {N_az_cfg} aperture positions "
                f"({float(cfg['azimuth']['x_start_m'])} to "
                f"{float(cfg['azimuth']['x_stop_m'])} m "
                f"step {float(cfg['azimuth']['x_step_m'])} m)."
            )
        H = np.array(arr, dtype=complex)
        return SyntheticScan(freqs_hz=freqs_hz, x_az_m=x_az_m, H=H)

    elif arr.ndim == 1:
        # Format B: (N_f,) — single azimuth position
        if arr.shape[0] != N_f_cfg:
            raise ValueError(
                f"Frequency dimension mismatch: file has {arr.shape[0]} samples "
                f"but config yields {N_f_cfg} frequency steps."
            )
        H = np.array(arr, dtype=complex)[:, None]  # → (N_f, 1)
        x_az_m = np.array([azimuth_position_m])
        return SyntheticScan(freqs_hz=freqs_hz, x_az_m=x_az_m, H=H)

    else:
        raise ValueError(
            f"Incompatible array shape {arr.shape} in '{path.name}'. "
            "Expected 2D (N_f, N_az) or 1D (N_f,)."
        )


def _parse_freq_mhz(filename: str) -> int | None:
    m = re.search(r"_(\d+)MHz\.npy$", filename)
    return int(m.group(1)) if m else None


def _load_legacy_directory(dirpath: Path, azimuth_position_m: float) -> SyntheticScan:
    """
    Stitch a directory of per-frequency bladeRF captures into (N_f, 1).

    Each file contributes one row of H: the coherent mean of all IQ samples
    at that frequency (equivalent to matched-filter integration of a CW tone).
    """
    npy_files = sorted(dirpath.glob("cap_*.npy"))
    if not npy_files:
        raise ValueError(
            f"No cap_*.npy files found in '{dirpath}'. "
            "Expected legacy bladeRF captures named cap_NNN_XXXMHz.npy."
        )

    freq_file_pairs: list[tuple[int, Path]] = []
    for fpath in npy_files:
        freq_mhz = _parse_freq_mhz(fpath.name)
        if freq_mhz is None:
            raise ValueError(
                f"Cannot parse frequency from filename '{fpath.name}'. "
                "Expected pattern cap_NNN_XXXMHz.npy."
            )
        freq_file_pairs.append((freq_mhz, fpath))

    freq_file_pairs.sort(key=lambda x: x[0])

    responses: list[complex] = []
    for freq_mhz, fpath in freq_file_pairs:
        iq = np.load(str(fpath), mmap_mode="r")
        if iq.ndim != 1:
            raise ValueError(
                f"Expected 1D IQ array in '{fpath.name}', got shape {iq.shape}."
            )
        responses.append(complex(np.mean(iq)))

    freqs_hz = np.array([f * 1e6 for f, _ in freq_file_pairs])
    H = np.array(responses, dtype=complex)[:, None]  # (N_f, 1)
    x_az_m = np.array([azimuth_position_m])

    return SyntheticScan(freqs_hz=freqs_hz, x_az_m=x_az_m, H=H)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_capture(
    path: Union[str, Path],
    cfg: dict,
    azimuth_position_m: float = 0.0,
) -> SyntheticScan:
    """
    Load a real SFCW capture into a SyntheticScan object.

    Parameters
    ----------
    path : str or Path
        A .npy file (format A or B) or a directory of per-frequency .npy files
        (format C — legacy bladeRF captures).
    cfg : dict
        Config dict with 'sfcw' and 'azimuth' sections.  Used to reconstruct
        the frequency grid (all formats) and azimuth grid (format A only).
        For format C, frequencies are inferred from filenames; cfg is not used.
    azimuth_position_m : float, optional
        Aperture position [m] assigned to single-azimuth captures (format B
        and C).  Default 0.0.

    Returns
    -------
    SyntheticScan
        freqs_hz, x_az_m, and H arrays ready for compute_range_profiles and
        backprojection without any changes to the processing modules.

    Raises
    ------
    FileNotFoundError
        If the path does not exist.
    ValueError
        Shape mismatch, unsupported file type, or missing/malformed files.
    """
    p = Path(path)

    if not p.exists():
        raise FileNotFoundError(f"Path not found: {path}")

    if p.is_dir():
        return _load_legacy_directory(p, azimuth_position_m)

    if p.suffix != ".npy":
        raise ValueError(
            f"Unsupported file type '{p.suffix}'. Expected a .npy file or a directory."
        )

    return _load_single_file(p, cfg, azimuth_position_m)
