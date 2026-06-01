"""
Phase 5 hardware entrypoint: manual azimuth scan for 2D relative contrast heatmap.

The user physically moves the antenna to N azimuth positions along a tape measure
or ruled rail.  At each position, two captures are taken:
  1. Background capture: H_bg(f) -- no test object in the field of view.
  2. Object capture:     H_obj(f) -- test object placed at target location.

After all N positions are captured, the script:
  - Stitches frequency blocks for each position.
  - Applies inter-block phase calibration (overlap-based).
  - Computes H_delta = H_obj - H_bg for each azimuth position.
  - Runs near-field backprojection.
  - Generates the 2D relative contrast heatmap.
  - Saves all data and figures.

Usage
-----
  py experiments/run_phase5_2d_scan_hardware_entrypoint.py          (show checklist + exit)
  py experiments/run_phase5_2d_scan_hardware_entrypoint.py --prepare-only   (simulate preview)
  py experiments/run_phase5_2d_scan_hardware_entrypoint.py --dry-run        (fake device)
  py experiments/run_phase5_2d_scan_hardware_entrypoint.py --run-supervised (real hardware)

Hardware gates (all required before --run-supervised):
  - CONFIRM HARDWARE RUN   (typed interactively)
  - REFLECTOR SETUP READY  (typed interactively)

Physical setup requirements:
  - bladeRF 2.0 micro connected via USB (TX1 + RX1 only).
  - TX gain <= -20 dBm. Burst <= 10 ms.
  - Antenna TX1 and RX1 at marked aperture position.
  - Metallic test reflector (or dielectric object) at known position.
  - N physical position marks on a ruler/rail (e.g., every 5 cm over 20 cm).
  - No persons or biological material in the antenna beam.

Scientific note
---------------
Output is a "relative dielectric contrast heatmap" -- NOT absolute permittivity.
Background subtraction H_delta = H_obj - H_bg isolates the object contribution.
Calibrated epsilon_r estimation requires a reference phantom measurement.
No clinical claims. No biological material.
"""
from __future__ import annotations

import argparse
import pathlib
import sys
import datetime

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from hardware.safety import (
    MAX_OFDM_IQ_BURST_DURATION_S,
    BLADERF_MAX_TX_GAIN_DB,
)
from acquisition.ofdm_block_capture import OFDMBlockConfig, capture_ofdm_block
from processing.dielectric_contrast_heatmap import (
    sar_image_to_contrast_heatmap,
    locate_contrast_peaks_2d,
    heatmap_summary,
)
from processing.ofdm_block_phase_calibration import (
    calibrate_h_matrix_list,
    phase_calibration_summary,
)
from simulation.ofdm_uwb_sar_simulator import backprojection_image

# ---------------------------------------------------------------------------
# Default scan configuration
# ---------------------------------------------------------------------------

# Azimuth positions (m): user places antenna at each mark
DEFAULT_AZ_POSITIONS_M = [
    -0.10, -0.05, 0.00, 0.05, 0.10,
]  # 5 positions, 5 cm spacing, centered at 0

# OFDM block configurations for hardware (bladeRF-compatible, 20 MHz per block)
DEFAULT_BLOCK_CONFIGS = [
    OFDMBlockConfig(center_freq_hz=2.40e9, sample_rate_hz=20e6, n_fft=256,
                    n_active=120, cp_len=32, tx_gain_db=BLADERF_MAX_TX_GAIN_DB,
                    rx_gain_db=20.0),
    OFDMBlockConfig(center_freq_hz=2.42e9, sample_rate_hz=20e6, n_fft=256,
                    n_active=120, cp_len=32, tx_gain_db=BLADERF_MAX_TX_GAIN_DB,
                    rx_gain_db=20.0),
    OFDMBlockConfig(center_freq_hz=2.44e9, sample_rate_hz=20e6, n_fft=256,
                    n_active=120, cp_len=32, tx_gain_db=BLADERF_MAX_TX_GAIN_DB,
                    rx_gain_db=20.0),
]

# Image reconstruction grid
X_IMG = np.linspace(-0.20, 0.20, 80)
Z_IMG = np.linspace(0.10, 1.50, 80)

OUT_DIR = _REPO_ROOT / "reports" / "generated" / "phase5_2d_scan_hardware"


# ---------------------------------------------------------------------------
# Hardware checklist
# ---------------------------------------------------------------------------

_CHECKLIST = """
============================================================
Phase 5 Hardware Checklist -- 2D Manual Azimuth Scan
============================================================

BEFORE running --run-supervised, verify ALL of the following:

[1] Hardware
    [ ] bladeRF 2.0 micro connected via USB
    [ ] Wideband antenna on TX1 port (NOT TX2)
    [ ] Wideband antenna on RX1 port (NOT RX2)
    [ ] bladeRF-cli --probe confirms device found

[2] Aperture setup
    [ ] N = {n_pos} position marks on rail/tape measure
        Positions (m): {positions}
    [ ] Antenna mount can be moved to each mark and held stable
    [ ] Position 0 is the reference (center of aperture)
    [ ] Aperture is horizontal, antenna beam aimed at test zone

[3] Test object
    [ ] Metallic reflector OR dielectric object at approx. {z_obj:.1f} m from aperture
    [ ] Object is STABLE -- will not move between background and object captures
    [ ] No persons in the antenna beam direction
    [ ] No biological material in the test zone

[4] Safety
    [ ] TX gain locked at {tx_gain:.1f} dBm (bladeRF safety limit)
    [ ] Burst duration <= {burst_ms:.1f} ms per capture
    [ ] TX disabled in finally block (enforced by capture script)

[5] Script readiness
    [ ] Run --prepare-only first to verify synthetic preview
    [ ] Run --dry-run to verify script flow without hardware

[6] Expected output
    [ ] reports/generated/phase5_2d_scan_hardware/
    [ ] bg_capture_az{{}}_block{{}}.npy  (one per position x block)
    [ ] obj_capture_az{{}}_block{{}}.npy (one per position x block)
    [ ] phase5_2d_scan_heatmap.png
    [ ] phase5_2d_scan_summary.md

To run:
  py experiments/run_phase5_2d_scan_hardware_entrypoint.py --run-supervised

When prompted:
  -> Type: CONFIRM HARDWARE RUN
  -> Type: REFLECTOR SETUP READY

Scientific note:
  Output is a relative contrast heatmap (NOT absolute epsilon_r).
  Background subtraction H_delta = H_obj - H_bg applied automatically.
  No clinical claims. No biological material.
============================================================
"""


def print_hardware_checklist(
    az_positions: list[float],
    z_object_m: float = 0.80,
) -> None:
    """Print the physical setup checklist and exit."""
    print(_CHECKLIST.format(
        n_pos=len(az_positions),
        positions=", ".join(f"{x:.2f}" for x in az_positions),
        z_obj=z_object_m,
        tx_gain=BLADERF_MAX_TX_GAIN_DB,
        burst_ms=MAX_OFDM_IQ_BURST_DURATION_S * 1000,
    ))


# ---------------------------------------------------------------------------
# Scan helpers
# ---------------------------------------------------------------------------

def _stitch_blocks(blocks_H, blocks_f):
    """Stitch H(f, 1) blocks from multiple RF center frequencies, sorted by frequency."""
    f_all = np.concatenate(blocks_f)
    H_all = np.concatenate(blocks_H)
    order = np.argsort(f_all)
    return H_all[order], f_all[order]


def _capture_one_position(
    az_idx: int,
    az_pos_m: float,
    block_configs: list[OFDMBlockConfig],
    scene_label: str,
    dry_run: bool,
    device=None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Capture all blocks at one azimuth position.

    Returns (H_stitched, freqs_stitched) -- shape (n_total_freq,).
    """
    blocks_H: list[np.ndarray] = []
    blocks_f: list[np.ndarray] = []

    for b_idx, cfg in enumerate(block_configs):
        try:
            result = capture_ofdm_block(device, cfg, dry_run=dry_run)
            H_b = result.H_active
            f_b = result.freqs_hz
        except Exception as exc:
            print(f"    [WARN] Block {b_idx} failed at az={az_pos_m:.2f} m: {exc}")
            # Fill with zeros for failed blocks to keep matrix shape consistent
            n_freq = cfg.n_active
            H_b = np.zeros(n_freq, dtype=complex)
            f_b = np.linspace(
                cfg.center_freq_hz - cfg.sample_rate_hz / 4,
                cfg.center_freq_hz + cfg.sample_rate_hz / 4,
                n_freq,
            )

        # Sort by frequency (FFT bin ordering fix)
        order = np.argsort(f_b)
        blocks_H.append(H_b[order])
        blocks_f.append(f_b[order])

    # Phase calibrate across blocks
    df_est = float(blocks_f[0][1] - blocks_f[0][0]) if len(blocks_f[0]) > 1 else 1e6
    cal_H, offsets = calibrate_h_matrix_list(
        blocks_H, blocks_f, min_overlap_bins=3, freq_tol_hz=df_est * 0.5
    )
    H_stitch, f_stitch = _stitch_blocks(cal_H, blocks_f)

    print(f"    az[{az_idx}]={az_pos_m:.2f}m {scene_label}: "
          f"n_freq={len(H_stitch)}, f=[{f_stitch[0]/1e9:.3f},{f_stitch[-1]/1e9:.3f}] GHz, "
          f"phase offsets=[{', '.join(f'{o:.2f}' for o in offsets)}] rad")

    return H_stitch, f_stitch


def _build_h_matrix_from_scans(
    az_positions_m: list[float],
    block_configs: list[OFDMBlockConfig],
    scene_label: str,
    dry_run: bool,
    device=None,
    interactive: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Capture H(f) at each azimuth position, assemble into H(f, x_az) matrix.

    Returns (H_matrix, freqs_hz) where H_matrix has shape (n_freq, n_az).
    """
    H_columns: list[np.ndarray] = []
    freqs_ref: np.ndarray | None = None

    for i_az, az_pos_m in enumerate(az_positions_m):
        if interactive:
            input(
                f"\n  -> Move antenna to position {i_az+1}/{len(az_positions_m)} "
                f"(x = {az_pos_m:.2f} m). Press Enter when stable..."
            )

        H_col, freqs = _capture_one_position(
            az_idx=i_az, az_pos_m=az_pos_m,
            block_configs=block_configs,
            scene_label=scene_label,
            dry_run=dry_run,
            device=device,
        )

        if freqs_ref is None:
            freqs_ref = freqs
        H_columns.append(H_col)

    # Stack into matrix (n_freq, n_az) -- interpolate if freq axes differ
    n_freq = len(freqs_ref)
    n_az = len(az_positions_m)
    H_matrix = np.zeros((n_freq, n_az), dtype=complex)
    for i_az, H_col in enumerate(H_columns):
        if len(H_col) == n_freq:
            H_matrix[:, i_az] = H_col
        else:
            # Interpolate to reference grid
            H_matrix[:, i_az] = np.interp(freqs_ref, np.linspace(freqs_ref[0], freqs_ref[-1], len(H_col)),
                                            H_col.real) + \
                                  1j * np.interp(freqs_ref, np.linspace(freqs_ref[0], freqs_ref[-1], len(H_col)),
                                                  H_col.imag)

    return H_matrix, freqs_ref


def _save_heatmap_figure(
    heatmap: np.ndarray,
    x_img: np.ndarray,
    z_img: np.ndarray,
    peaks: list[dict],
    az_positions_m: list[float],
    bw_hz: float,
    out_path: pathlib.Path,
    title_suffix: str = "",
) -> None:
    """Save a 2D heatmap figure."""
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.pcolormesh(z_img, x_img, heatmap, cmap="viridis", vmin=0, vmax=1, shading="auto")
    plt.colorbar(im, ax=ax, label="Relative contrast [0,1]")
    for pk in peaks:
        ax.plot(pk["z_m"], pk["x_m"], "r^", ms=9,
                label=f"Peak ({pk['x_m']:.2f},{pk['z_m']:.2f}) m")
    # Mark aperture positions
    for az in az_positions_m:
        ax.axhline(az, color="cyan", linewidth=0.5, alpha=0.4)
    dr_m = 3e8 / (2.0 * bw_hz) if bw_hz > 0 else 0.0
    ax.set_xlabel("Down-range z [m]")
    ax.set_ylabel("Cross-range x [m]")
    ax.set_title(
        f"2D Relative Contrast Heatmap -- H_delta{title_suffix}\n"
        f"(BW={bw_hz/1e9:.3f} GHz, dr={dr_m*100:.1f} cm, NOT abs eps_r)"
    )
    ax.legend(fontsize=8, loc="upper right")
    ax.set_xlim(z_img[0], z_img[-1])
    ax.set_ylim(x_img[0], x_img[-1])
    plt.tight_layout()
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _write_scan_summary(
    az_positions_m: list[float],
    block_configs: list[OFDMBlockConfig],
    bw_hz: float,
    peaks: list[dict],
    out_path: pathlib.Path,
    mode: str,
) -> None:
    """Write a Markdown summary of the 2D scan result."""
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dr_m = 3e8 / (2.0 * bw_hz) if bw_hz > 0 else 0.0
    block_freqs = [f"{cfg.center_freq_hz/1e9:.3f}" for cfg in block_configs]
    peaks_md = "\n".join(
        f"| {i+1} | {pk['x_m']:.3f} | {pk['z_m']:.3f} | {pk['value']:.3f} |"
        for i, pk in enumerate(peaks)
    ) or "| -- | -- | -- | -- |"

    text = f"""# Phase 5 2D Scan Summary

Generated: {now}
Mode: {mode}

## Scan parameters

- Azimuth positions: {len(az_positions_m)} ({[f'{x:.2f}' for x in az_positions_m]} m)
- OFDM blocks: {len(block_configs)} centers at {block_freqs} GHz
- Sample rate per block: {block_configs[0].sample_rate_hz/1e6:.0f} MHz
- Effective BW: {bw_hz/1e9:.3f} GHz
- Range resolution: {dr_m*100:.1f} cm

## Reconstructed contrast peaks

| Peak | x [m] | z [m] | Contrast |
|---|---|---|---|
{peaks_md}

## Scientific note

- Output is a **relative dielectric contrast heatmap** (H_delta = H_obj - H_bg).
- NOT absolute permittivity. Calibration required for epsilon_r estimation.
- TX1/RX1 only. TX2/RX2 not used.
- No clinical claims. No biological material.
"""
    out_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def run_prepare_only() -> None:
    """Generate a synthetic preview using simulation parameters."""
    print("\n[prepare-only] Generating synthetic preview...")
    from simulation.phantom_permittivity_map import make_two_inclusion_phantom
    from simulation.ofdm_uwb_sar_simulator import (
        OFDMParameters, simulate_h_matrix, backprojection_image,
    )

    phantom = make_two_inclusion_phantom()
    targets = phantom.to_point_targets()
    az_positions_m = np.array(DEFAULT_AZ_POSITIONS_M)

    blocks_H: list[np.ndarray] = []
    blocks_f: list[np.ndarray] = []
    for i, cfg in enumerate(DEFAULT_BLOCK_CONFIGS):
        params = OFDMParameters(
            n_fft=cfg.n_fft, n_active=cfg.n_active, cp_len=cfg.cp_len,
            sample_rate_hz=cfg.sample_rate_hz, center_freq_hz=cfg.center_freq_hz,
            pilot_seed=42,
        )
        H_b, f_b, _ = simulate_h_matrix(params, targets, az_positions_m, seed=i)
        order = np.argsort(f_b)
        blocks_H.append(H_b[order, :])
        blocks_f.append(f_b[order])

    H_matrix = np.concatenate(blocks_H, axis=0)
    freqs = np.concatenate(blocks_f)
    order = np.argsort(freqs)
    H_matrix = H_matrix[order, :]
    freqs = freqs[order]

    sar_img = backprojection_image(H_matrix, freqs, az_positions_m, X_IMG, Z_IMG)
    heatmap = sar_image_to_contrast_heatmap(sar_img, normalize=True)
    peaks = locate_contrast_peaks_2d(heatmap, X_IMG, Z_IMG, n_peaks=3, threshold=0.3)
    bw_hz = float(freqs[-1] - freqs[0])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_fig = OUT_DIR / "phase5_prepare_only_preview.png"
    _save_heatmap_figure(heatmap, X_IMG, Z_IMG, peaks, DEFAULT_AZ_POSITIONS_M,
                         bw_hz, out_fig, title_suffix=" (synthetic preview)")
    _write_scan_summary(DEFAULT_AZ_POSITIONS_M, DEFAULT_BLOCK_CONFIGS, bw_hz, peaks,
                        OUT_DIR / "phase5_prepare_only_summary.md", mode="prepare-only")

    print(f"  Synthetic preview: {out_fig.name}")
    print(f"  Peaks: {peaks}")
    print("  [prepare-only] PASS")


def run_dry_run() -> None:
    """Run scan using a fake bladeRF device (no hardware required)."""
    print("\n[dry-run] Simulating hardware scan with fake device...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    az_positions_m = DEFAULT_AZ_POSITIONS_M

    H_bg_cols: list[np.ndarray] = []
    H_obj_cols: list[np.ndarray] = []
    freqs_ref: np.ndarray | None = None

    for i_az, az_pos_m in enumerate(az_positions_m):
        # Background capture (dry_run=True uses fake device)
        H_col_bg, freqs = _capture_one_position(
            az_idx=i_az, az_pos_m=az_pos_m,
            block_configs=DEFAULT_BLOCK_CONFIGS,
            scene_label="BG",
            dry_run=True,
        )
        H_bg_cols.append(H_col_bg)
        if freqs_ref is None:
            freqs_ref = freqs

        H_col_obj, _ = _capture_one_position(
            az_idx=i_az, az_pos_m=az_pos_m,
            block_configs=DEFAULT_BLOCK_CONFIGS,
            scene_label="OBJ",
            dry_run=True,
        )
        H_obj_cols.append(H_col_obj)

    n_freq = len(freqs_ref)
    n_az = len(az_positions_m)
    H_bg_mat = np.array(H_bg_cols).T   # (n_freq, n_az)
    H_obj_mat = np.array(H_obj_cols).T
    H_delta_mat = H_obj_mat - H_bg_mat

    sar_img = backprojection_image(H_delta_mat, freqs_ref, np.array(az_positions_m), X_IMG, Z_IMG)
    heatmap = sar_image_to_contrast_heatmap(sar_img, normalize=True)
    peaks = locate_contrast_peaks_2d(heatmap, X_IMG, Z_IMG, n_peaks=3, threshold=0.3)
    bw_hz = float(freqs_ref[-1] - freqs_ref[0]) if freqs_ref is not None else 1.0

    out_fig = OUT_DIR / "phase5_dry_run_heatmap.png"
    _save_heatmap_figure(heatmap, X_IMG, Z_IMG, peaks, az_positions_m, bw_hz,
                         out_fig, title_suffix=" (dry-run)")
    _write_scan_summary(az_positions_m, DEFAULT_BLOCK_CONFIGS, bw_hz, peaks,
                        OUT_DIR / "phase5_dry_run_summary.md", mode="dry-run")

    print(f"  Heatmap: {out_fig.name}")
    print(f"  Peaks: {peaks}")
    print("  [dry-run] PASS")


def run_supervised() -> None:
    """Full supervised interactive 2D scan with real hardware."""
    print("\n[supervised] Phase 5 -- Real hardware 2D scan")
    print_hardware_checklist(DEFAULT_AZ_POSITIONS_M)

    # Gate 1: hardware confirmation
    print("\nStep 1 of 2: Hardware safety confirmation.")
    confirm = input("  Type 'CONFIRM HARDWARE RUN' to proceed: ").strip()
    if confirm != "CONFIRM HARDWARE RUN":
        print("  Confirmation not received. Aborting.")
        sys.exit(1)

    # Gate 2: reflector/object confirmation
    print("\nStep 2 of 2: Object setup confirmation.")
    reflector = input("  Type 'REFLECTOR SETUP READY' to proceed: ").strip()
    if reflector != "REFLECTOR SETUP READY":
        print("  Object not set up. Aborting.")
        sys.exit(1)

    print("\n  Both gates confirmed. Starting supervised 2D scan...")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    az_positions_m = DEFAULT_AZ_POSITIONS_M
    block_configs = DEFAULT_BLOCK_CONFIGS

    try:
        from hardware.bladerf_device import BladeRFDevice
        device = BladeRFDevice(dry_run=False)
        device.open()
    except Exception as e:
        print(f"\n  [ERROR] Could not open bladeRF device: {e}")
        print("  If bladeRF is not connected, use --dry-run instead.")
        sys.exit(1)

    try:
        print("\n--- BACKGROUND SCAN (no object in field) ---")
        print("  Remove test object from antenna beam. Press Enter at each position.\n")
        H_bg_mat, freqs_ref = _build_h_matrix_from_scans(
            az_positions_m, block_configs, "BG", dry_run=False, device=device, interactive=True,
        )
        np.save(OUT_DIR / "H_bg_matrix.npy", H_bg_mat)
        np.save(OUT_DIR / "freqs_ref.npy", freqs_ref)
        print(f"\n  Background matrix saved. Shape: {H_bg_mat.shape}")

        print("\n--- OBJECT SCAN (test object in field) ---")
        print("  Place test object at target position. Press Enter at each position.\n")
        H_obj_mat, _ = _build_h_matrix_from_scans(
            az_positions_m, block_configs, "OBJ", dry_run=False, device=device, interactive=True,
        )
        np.save(OUT_DIR / "H_obj_matrix.npy", H_obj_mat)
        print(f"\n  Object matrix saved. Shape: {H_obj_mat.shape}")

    finally:
        device.close()
        print("  bladeRF closed.")

    print("\n--- RECONSTRUCTION ---")
    H_delta = H_obj_mat - H_bg_mat
    np.save(OUT_DIR / "H_delta_matrix.npy", H_delta)

    sar_img = backprojection_image(
        H_delta, freqs_ref, np.array(az_positions_m), X_IMG, Z_IMG,
        padding_factor=8, window="hanning",
    )
    heatmap = sar_image_to_contrast_heatmap(sar_img, normalize=True)
    peaks = locate_contrast_peaks_2d(heatmap, X_IMG, Z_IMG, n_peaks=3, threshold=0.2)
    bw_hz = float(freqs_ref[-1] - freqs_ref[0])

    np.save(OUT_DIR / "sar_image.npy", sar_img)
    np.save(OUT_DIR / "heatmap.npy", heatmap)

    out_fig = OUT_DIR / "phase5_2d_scan_heatmap.png"
    _save_heatmap_figure(heatmap, X_IMG, Z_IMG, peaks, az_positions_m, bw_hz,
                         out_fig, title_suffix=" (hardware)")
    _write_scan_summary(az_positions_m, block_configs, bw_hz, peaks,
                        OUT_DIR / "phase5_2d_scan_summary.md", mode="hardware-supervised")

    print(f"\n  Heatmap saved: {out_fig}")
    print(f"  Peaks: {peaks}")
    print("\n  Phase 5 2D scan complete. No further RF transmission.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 5 hardware entrypoint: manual azimuth 2D scan."
    )
    parser.add_argument("--prepare-only", action="store_true",
                        help="Generate synthetic preview using simulation (no hardware).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run script flow with fake bladeRF device.")
    parser.add_argument("--run-supervised", action="store_true",
                        help="Full supervised real-hardware scan (requires bladeRF + gates).")
    args = parser.parse_args()

    if args.prepare_only:
        run_prepare_only()
    elif args.dry_run:
        run_dry_run()
    elif args.run_supervised:
        run_supervised()
    else:
        print_hardware_checklist(DEFAULT_AZ_POSITIONS_M)
        print("\nTo run with real hardware: add --run-supervised")
        print("To preview (simulation):   add --prepare-only")
        print("To test script flow:       add --dry-run")


if __name__ == "__main__":
    main()
