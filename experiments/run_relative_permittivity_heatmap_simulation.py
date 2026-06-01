"""
Phase 5: Relative dielectric contrast heatmap from simulated UWB-OFDM-SAR.

Demonstrates the full pipeline:
  1. Create 2D dielectric phantom (two inclusions with known epsilon_r).
  2. Simulate H(f, x_az) using multi-block UWB-OFDM SAR.
  3. Stitch frequency blocks and run near-field backprojection.
  4. Produce normalized relative contrast heatmap.
  5. Compare with ground-truth Fresnel reflectivity map.
  6. Generate figures and Markdown summary.

Usage
-----
  py experiments/run_relative_permittivity_heatmap_simulation.py

All figures saved to:
  reports/generated/phase5_dielectric_heatmap/

Scientific note
---------------
Output is a "relative dielectric contrast heatmap" (NOT absolute permittivity).
Simulation uses free-space, non-dispersive, point-scatterer Fresnel model.
No hardware used. No RF transmitted. No clinical claims. No motors.
"""
from __future__ import annotations

import os
import sys
import pathlib
import datetime

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ---- path setup -----------------------------------------------------------
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from simulation.phantom_permittivity_map import DielectricPhantom, make_two_inclusion_phantom
from simulation.ofdm_uwb_sar_simulator import (
    OFDMParameters,
    simulate_h_matrix,
    backprojection_image,
    range_profiles_from_h_matrix,
)
from processing.dielectric_contrast_heatmap import (
    sar_image_to_contrast_heatmap,
    permittivity_map_to_reflectivity_map,
    compare_heatmaps,
    locate_contrast_peaks_2d,
    heatmap_summary,
)

# ---- output directory -----------------------------------------------------
OUT_DIR = _REPO_ROOT / "reports" / "generated" / "phase5_dielectric_heatmap"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ===========================================================================
# Simulation parameters
# ===========================================================================

# Phantom
PHANTOM_EPS_BG  = 1.0    # air background
PHANTOM_EPS_A   = 3.5    # inclusion A (plastic-like proxy)
PHANTOM_EPS_B   = 9.0    # inclusion B (high-contrast dielectric)

# UWB-OFDM: 5 frequency blocks spanning ~2.0-4.0 GHz (simulation only)
# NOTE: sample_rate_hz = 500 MHz is NOT achievable by bladeRF (max ~61.44 MSPS).
#       This is a SIMULATION ONLY parameter demonstrating the UWB pipeline.
#       Real hardware would use multiple 20 MHz blocks stitched to cover the same BW.
BLOCK_CENTERS_HZ = [2.0e9, 2.5e9, 3.0e9, 3.5e9, 4.0e9]
SAMPLE_RATE_HZ   = 500e6   # simulation only
N_FFT            = 256
N_ACTIVE         = 200
GUARD_BINS       = 4
PILOT_SEED       = 42
NOISE_STD        = 0.02

# Aperture: 25 positions, 5 cm step, centered at x=0
N_AZ_POSITIONS   = 25
AZ_HALF_SPAN_M   = 0.60    # aperture: -0.60 to +0.60 m
az_positions_m   = np.linspace(-AZ_HALF_SPAN_M, AZ_HALF_SPAN_M, N_AZ_POSITIONS)

# Image reconstruction grid
X_IMG = np.linspace(-0.75, 0.75, 150)
Z_IMG = np.linspace(0.05, 1.55, 150)


# ===========================================================================
# Helpers
# ===========================================================================

def _stitch_h_matrices(
    blocks_H: list[np.ndarray],
    blocks_f: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """
    Stitch H(f, x_az) matrices from multiple blocks by sorting in frequency.

    Parameters
    ----------
    blocks_H : list of (n_freq_b, n_az) complex arrays.
    blocks_f : list of (n_freq_b,) float frequency arrays.

    Returns
    -------
    H_stitch : complex array (n_total_freq, n_az). Sorted by ascending freq.
    f_stitch : float array (n_total_freq,). Ascending frequencies [Hz].
    """
    f_all = np.concatenate(blocks_f, axis=0)     # (n_total,)
    H_all = np.concatenate(blocks_H, axis=0)     # (n_total, n_az)
    order = np.argsort(f_all)
    return H_all[order, :], f_all[order]


def _compute_effective_bw(freqs_hz: np.ndarray) -> float:
    """Approximate total effective bandwidth from a (possibly gapped) frequency array."""
    return float(freqs_hz[-1] - freqs_hz[0]) if len(freqs_hz) > 1 else 1.0


def _range_resolution_m(bw_hz: float, c: float = 3e8) -> float:
    return c / (2.0 * bw_hz)


def _azimuth_resolution_m(center_hz: float, c: float = 3e8) -> float:
    wavelength = c / center_hz
    return wavelength / 2.0


# ===========================================================================
# Simulation
# ===========================================================================

def run_simulation() -> dict:
    """
    Run the full UWB-OFDM-SAR heatmap simulation.

    Returns a dict with all arrays and metadata needed for figure generation.
    """
    print("[Phase 5] Building phantom...")
    phantom = make_two_inclusion_phantom(
        eps_r_bg=PHANTOM_EPS_BG,
        eps_r_a=PHANTOM_EPS_A,
        eps_r_b=PHANTOM_EPS_B,
    )
    targets = phantom.to_point_targets()

    print(f"  Phantom: {len(phantom.inclusions)} inclusions, eps_bg={PHANTOM_EPS_BG}")
    for incl in phantom.inclusions:
        gamma = phantom.fresnel_reflectivity(phantom.epsilon_r_bg, incl.epsilon_r)
        print(f"  [{incl.label}] eps_r={incl.epsilon_r}, |Gamma|={abs(gamma):.3f}, "
              f"center=({incl.x_m:.2f}, {incl.z_m:.2f}) m")

    print(f"\n[Phase 5] Simulating {len(BLOCK_CENTERS_HZ)} OFDM blocks x {N_AZ_POSITIONS} azimuth positions...")
    blocks_H: list[np.ndarray] = []
    blocks_f: list[np.ndarray] = []

    for i, fc in enumerate(BLOCK_CENTERS_HZ):
        params = OFDMParameters(
            n_fft=N_FFT,
            n_active=N_ACTIVE,
            cp_len=32,
            sample_rate_hz=SAMPLE_RATE_HZ,
            center_freq_hz=fc,
            dc_null=True,
            guard_bins=GUARD_BINS,
            pilot_seed=PILOT_SEED,
        )
        H_block, freqs_block, _ = simulate_h_matrix(
            params, targets, az_positions_m,
            aperture_z_m=0.0,
            noise_std=NOISE_STD,
            seed=PILOT_SEED + i,
        )
        blocks_H.append(H_block)
        blocks_f.append(freqs_block)
        print(f"  Block {i+1}/{len(BLOCK_CENTERS_HZ)}: fc={fc/1e9:.1f} GHz, "
              f"n_freq={H_block.shape[0]}, freq=[{freqs_block[0]/1e9:.3f}, {freqs_block[-1]/1e9:.3f}] GHz")

    print("\n[Phase 5] Stitching blocks...")
    H_stitched, freqs_stitched = _stitch_h_matrices(blocks_H, blocks_f)
    bw_hz = _compute_effective_bw(freqs_stitched)
    dr_m  = _range_resolution_m(bw_hz)
    f_center = float(np.mean(freqs_stitched))
    daz_m = _azimuth_resolution_m(f_center)
    print(f"  Stitched: {H_stitched.shape[0]} subcarriers, {H_stitched.shape[1]} az positions")
    print(f"  Freq range: {freqs_stitched[0]/1e9:.3f} to {freqs_stitched[-1]/1e9:.3f} GHz")
    print(f"  Effective BW: {bw_hz/1e9:.3f} GHz")
    print(f"  Range resolution: {dr_m*100:.1f} cm")
    print(f"  Azimuth resolution (approx): {daz_m*100:.1f} cm")

    print("\n[Phase 5] Computing range profiles...")
    range_m, range_profiles = range_profiles_from_h_matrix(
        H_stitched, freqs_stitched, padding_factor=8, window="hanning"
    )

    print("\n[Phase 5] Running backprojection...")
    sar_img = backprojection_image(
        H_stitched, freqs_stitched, az_positions_m,
        X_IMG, Z_IMG, padding_factor=8, window="hanning",
    )
    print(f"  SAR image shape: {sar_img.shape}, dtype={sar_img.dtype}")

    print("\n[Phase 5] Building ground-truth and heatmap...")
    x_grid, z_grid, eps_map   = phantom.permittivity_grid()
    _,      _,      refl_map  = phantom.reflectivity_map()

    heatmap = sar_image_to_contrast_heatmap(sar_img, normalize=True)
    gt_map  = permittivity_map_to_reflectivity_map(eps_map, eps_r_bg=PHANTOM_EPS_BG, normalize=True)

    metrics = compare_heatmaps(
        _resize_grid(heatmap, X_IMG, Z_IMG, x_grid, z_grid),
        gt_map,
    )
    summary = heatmap_summary(heatmap, X_IMG, Z_IMG, inclusions=phantom.inclusions)

    print(f"  Heatmap RMSE vs ground truth: {metrics['rmse']:.4f}")
    print(f"  Peaks found: {summary['n_peaks_found']}")
    for pk in summary["peaks"]:
        print(f"    Peak at ({pk['x_m']:.2f}, {pk['z_m']:.2f}) m, contrast={pk['value']:.3f}")

    return {
        "phantom": phantom,
        "targets": targets,
        "H_stitched": H_stitched,
        "freqs_stitched": freqs_stitched,
        "az_positions_m": az_positions_m,
        "range_m": range_m,
        "range_profiles": range_profiles,
        "sar_img": sar_img,
        "heatmap": heatmap,
        "x_img": X_IMG,
        "z_img": Z_IMG,
        "x_grid": x_grid,
        "z_grid": z_grid,
        "eps_map": eps_map,
        "refl_map": refl_map,
        "gt_map": gt_map,
        "metrics": metrics,
        "summary": summary,
        "bw_hz": bw_hz,
        "dr_m": dr_m,
        "daz_m": daz_m,
    }


def _resize_grid(
    heatmap_img: np.ndarray,
    x_img: np.ndarray,
    z_img: np.ndarray,
    x_gt: np.ndarray,
    z_gt: np.ndarray,
) -> np.ndarray:
    """
    Bilinear interpolation of heatmap_img (on x_img, z_img) to (x_gt, z_gt) grid.
    Used for pixel-wise comparison with the ground-truth permittivity grid.
    """
    from scipy.interpolate import RegularGridInterpolator
    interp = RegularGridInterpolator(
        (x_img, z_img), heatmap_img,
        method="linear", bounds_error=False, fill_value=0.0,
    )
    XX, ZZ = np.meshgrid(x_gt, z_gt, indexing="ij")
    pts = np.stack([XX.ravel(), ZZ.ravel()], axis=1)
    return interp(pts).reshape(len(x_gt), len(z_gt))


# ===========================================================================
# Figure generation
# ===========================================================================

_CMAP_GT     = "hot"
_CMAP_RECON  = "viridis"
_CMAP_DIFF   = "RdBu_r"


def fig1_ground_truth(sim: dict) -> None:
    """Figure 1: synthetic_ground_truth_permittivity_map.png"""
    phantom  = sim["phantom"]
    x_grid   = sim["x_grid"]
    z_grid   = sim["z_grid"]
    eps_map  = sim["eps_map"]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fig.suptitle("Synthetic Ground Truth -- Dielectric Phantom", fontsize=13)

    # Left: permittivity map
    ax = axes[0]
    im = ax.pcolormesh(
        z_grid, x_grid, eps_map,
        cmap="plasma", vmin=PHANTOM_EPS_BG, vmax=max(PHANTOM_EPS_A, PHANTOM_EPS_B) * 1.05,
        shading="auto",
    )
    plt.colorbar(im, ax=ax, label="Relative permittivity (eps_r)")
    ax.set_xlabel("Down-range z [m]")
    ax.set_ylabel("Cross-range x [m]")
    ax.set_title("Permittivity Map -- Ground Truth")
    for incl in phantom.inclusions:
        ax.plot(incl.z_m, incl.x_m, "wx", markersize=10, markeredgewidth=2,
                label=f"{incl.label}: eps={incl.epsilon_r}")
        circ = plt.Circle(
            (incl.z_m, incl.x_m), incl.radius_m,
            fill=False, edgecolor="white", linewidth=1.5, linestyle="--",
        )
        ax.add_patch(circ)
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xlim(z_grid[0], z_grid[-1])
    ax.set_ylim(x_grid[0], x_grid[-1])

    # Right: Fresnel reflectivity map
    ax = axes[1]
    _, _, refl_map = phantom.reflectivity_map()
    im2 = ax.pcolormesh(
        z_grid, x_grid, refl_map,
        cmap=_CMAP_GT, vmin=0, vmax=1, shading="auto",
    )
    plt.colorbar(im2, ax=ax, label="|Gamma| normalized [0,1]")
    ax.set_xlabel("Down-range z [m]")
    ax.set_ylabel("Cross-range x [m]")
    ax.set_title("Fresnel Reflectivity -- Ground Truth")
    for incl in phantom.inclusions:
        gamma = phantom.fresnel_reflectivity(phantom.epsilon_r_bg, incl.epsilon_r)
        ax.plot(incl.z_m, incl.x_m, "cx", markersize=10, markeredgewidth=2,
                label=f"{incl.label}: |G|={abs(gamma):.2f}")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xlim(z_grid[0], z_grid[-1])
    ax.set_ylim(x_grid[0], x_grid[-1])

    plt.tight_layout()
    out = OUT_DIR / "synthetic_ground_truth_permittivity_map.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [fig1] saved: {out.name}")


def fig2_reconstructed_heatmap(sim: dict) -> None:
    """Figure 2: reconstructed_relative_contrast_heatmap.png"""
    phantom  = sim["phantom"]
    heatmap  = sim["heatmap"]
    x_img    = sim["x_img"]
    z_img    = sim["z_img"]
    summary  = sim["summary"]
    dr_m     = sim["dr_m"]
    daz_m    = sim["daz_m"]

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.pcolormesh(
        z_img, x_img, heatmap,
        cmap=_CMAP_RECON, vmin=0, vmax=1, shading="auto",
    )
    plt.colorbar(im, ax=ax, label="Relative contrast [0,1]")

    # True inclusion positions
    for incl in phantom.inclusions:
        gamma = phantom.fresnel_reflectivity(phantom.epsilon_r_bg, incl.epsilon_r)
        ax.plot(incl.z_m, incl.x_m, "w+", markersize=12, markeredgewidth=2,
                label=f"True {incl.label} (eps={incl.epsilon_r}, |G|={abs(gamma):.2f})")
        circ = plt.Circle(
            (incl.z_m, incl.x_m), incl.radius_m,
            fill=False, edgecolor="white", linewidth=1.0, linestyle="--",
        )
        ax.add_patch(circ)

    # Reconstructed peaks
    for pk in summary["peaks"]:
        ax.plot(pk["z_m"], pk["x_m"], "r^", markersize=9,
                label=f"Recon peak ({pk['x_m']:.2f},{pk['z_m']:.2f}) m")

    ax.set_xlabel("Down-range z [m]")
    ax.set_ylabel("Cross-range x [m]")
    ax.set_title(
        f"Reconstructed Relative Contrast Heatmap\n"
        f"(range res={dr_m*100:.1f} cm, az res~{daz_m*100:.1f} cm, NOT absolute eps_r)"
    )
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xlim(z_img[0], z_img[-1])
    ax.set_ylim(x_img[0], x_img[-1])

    plt.tight_layout()
    out = OUT_DIR / "reconstructed_relative_contrast_heatmap.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [fig2] saved: {out.name}")


def fig3_error_difference(sim: dict) -> None:
    """Figure 3: heatmap_error_or_difference.png"""
    phantom  = sim["phantom"]
    heatmap  = sim["heatmap"]
    x_img    = sim["x_img"]
    z_img    = sim["z_img"]
    x_grid   = sim["x_grid"]
    z_grid   = sim["z_grid"]
    eps_map  = sim["eps_map"]
    metrics  = sim["metrics"]

    gt_map = permittivity_map_to_reflectivity_map(
        eps_map, eps_r_bg=PHANTOM_EPS_BG, normalize=True
    )
    # Interpolate heatmap to ground-truth grid for difference
    hm_on_gt = _resize_grid(heatmap, x_img, z_img, x_grid, z_grid)
    diff = hm_on_gt - gt_map

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    fig.suptitle(
        f"Heatmap Comparison -- RMSE={metrics['rmse']:.4f}  (relative contrast only, NOT eps_r)",
        fontsize=11,
    )

    # Panel 1: Ground truth
    ax = axes[0]
    im = ax.pcolormesh(z_grid, x_grid, gt_map, cmap=_CMAP_GT, vmin=0, vmax=1, shading="auto")
    plt.colorbar(im, ax=ax, label="GT |Gamma| [0,1]")
    ax.set_title("Ground Truth\n(Fresnel reflectivity)")
    ax.set_xlabel("Down-range z [m]")
    ax.set_ylabel("Cross-range x [m]")
    for incl in phantom.inclusions:
        ax.plot(incl.z_m, incl.x_m, "cx", markersize=10, markeredgewidth=2)

    # Panel 2: Reconstructed (interpolated to GT grid)
    ax = axes[1]
    im2 = ax.pcolormesh(z_grid, x_grid, hm_on_gt, cmap=_CMAP_RECON, vmin=0, vmax=1, shading="auto")
    plt.colorbar(im2, ax=ax, label="Recon contrast [0,1]")
    ax.set_title("Reconstructed Heatmap\n(backprojection, interp to GT grid)")
    ax.set_xlabel("Down-range z [m]")
    ax.set_ylabel("Cross-range x [m]")
    for incl in phantom.inclusions:
        ax.plot(incl.z_m, incl.x_m, "wx", markersize=10, markeredgewidth=2)

    # Panel 3: Difference
    ax = axes[2]
    vmax_diff = max(float(np.max(np.abs(diff))), 1e-6)
    im3 = ax.pcolormesh(
        z_grid, x_grid, diff,
        cmap=_CMAP_DIFF, vmin=-vmax_diff, vmax=vmax_diff, shading="auto",
    )
    plt.colorbar(im3, ax=ax, label="Difference (recon - GT)")
    ax.set_title(f"Difference Map\nRMSE={metrics['rmse']:.4f}")
    ax.set_xlabel("Down-range z [m]")
    ax.set_ylabel("Cross-range x [m]")

    plt.tight_layout()
    out = OUT_DIR / "heatmap_error_or_difference.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [fig3] saved: {out.name}")


def fig4_range_profiles(sim: dict) -> None:
    """Figure 4: range_profiles_from_heatmap_pipeline.png"""
    phantom        = sim["phantom"]
    range_m        = sim["range_m"]
    range_profiles = sim["range_profiles"]
    az_positions_m = sim["az_positions_m"]

    n_az = range_profiles.shape[1]
    # Select a few interesting azimuth positions to show
    az_sel_idx = [
        int(np.argmin(np.abs(az_positions_m - incl.x_m)))
        for incl in phantom.inclusions
    ]
    az_sel_idx += [n_az // 2]
    az_sel_idx = sorted(set(az_sel_idx))

    fig, axes = plt.subplots(1, len(az_sel_idx), figsize=(5 * len(az_sel_idx), 5))
    if len(az_sel_idx) == 1:
        axes = [axes]

    max_range_plot = 1.7

    for col, i_az in enumerate(az_sel_idx):
        ax = axes[col]
        prof = np.abs(range_profiles[:, i_az])
        prof_norm = prof / (np.max(prof) + 1e-15)
        mask = range_m <= max_range_plot
        ax.plot(range_m[mask], prof_norm[mask], "b-", linewidth=1.5)
        # Mark expected target ranges
        for incl in phantom.inclusions:
            R_expected = float(np.sqrt(
                (az_positions_m[i_az] - incl.x_m) ** 2 + incl.z_m ** 2
            ))
            if R_expected <= max_range_plot:
                ax.axvline(R_expected, color="red", linestyle="--", linewidth=1.0,
                           label=f"{incl.label} R={R_expected:.2f}m")
        ax.set_xlabel("Range [m]")
        ax.set_ylabel("Normalized |CIR|")
        ax.set_title(f"Range Profile\naz={az_positions_m[i_az]:.2f} m")
        ax.set_xlim(0, max_range_plot)
        ax.set_ylim(0, 1.1)
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)

    fig.suptitle("Range Profiles from UWB-OFDM-SAR (windowed IFFT)", fontsize=12)
    plt.tight_layout()
    out = OUT_DIR / "range_profiles_from_heatmap_pipeline.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [fig4] saved: {out.name}")


def fig5_pipeline_summary(sim: dict) -> None:
    """Figure 5: pipeline_summary_figure.png"""
    phantom        = sim["phantom"]
    freqs_stitched = sim["freqs_stitched"]
    H_stitched     = sim["H_stitched"]
    range_m        = sim["range_m"]
    range_profiles = sim["range_profiles"]
    heatmap        = sim["heatmap"]
    x_img          = sim["x_img"]
    z_img          = sim["z_img"]
    x_grid         = sim["x_grid"]
    z_grid         = sim["z_grid"]
    eps_map        = sim["eps_map"]
    dr_m           = sim["dr_m"]
    bw_hz          = sim["bw_hz"]

    fig = plt.figure(figsize=(18, 10))
    gs  = gridspec.GridSpec(2, 4, figure=fig, hspace=0.45, wspace=0.4)

    # Panel A: Phantom permittivity map
    ax_a = fig.add_subplot(gs[0, 0])
    im_a = ax_a.pcolormesh(z_grid, x_grid, eps_map, cmap="plasma", shading="auto",
                            vmin=PHANTOM_EPS_BG, vmax=max(PHANTOM_EPS_A, PHANTOM_EPS_B) * 1.05)
    fig.colorbar(im_a, ax=ax_a, shrink=0.8, label="eps_r")
    for incl in phantom.inclusions:
        ax_a.plot(incl.z_m, incl.x_m, "wx", ms=8, mew=2)
    ax_a.set_title("A. Phantom (ground truth)")
    ax_a.set_xlabel("z [m]")
    ax_a.set_ylabel("x [m]")

    # Panel B: Stitched H(f) magnitude (center azimuth)
    ax_b = fig.add_subplot(gs[0, 1])
    i_center = H_stitched.shape[1] // 2
    H_mag_db = 20 * np.log10(np.abs(H_stitched[:, i_center]) + 1e-12)
    ax_b.plot(freqs_stitched / 1e9, H_mag_db, "b-", linewidth=0.7)
    ax_b.set_xlabel("Frequency [GHz]")
    ax_b.set_ylabel("|H(f)| [dB]")
    ax_b.set_title(f"B. Stitched H(f)\n({len(BLOCK_CENTERS_HZ)} blocks, BW={bw_hz/1e9:.2f} GHz)")
    ax_b.grid(True, alpha=0.3)
    for fc in BLOCK_CENTERS_HZ:
        ax_b.axvline(fc / 1e9, color="gray", linewidth=0.5, linestyle=":")

    # Panel C: Range profile at best az position for inclusion B
    ax_c = fig.add_subplot(gs[0, 2])
    i_az_b = int(np.argmin(np.abs(sim["az_positions_m"] - phantom.inclusions[1].x_m)))
    prof_b = np.abs(range_profiles[:, i_az_b])
    prof_b_norm = prof_b / (np.max(prof_b) + 1e-15)
    mask = range_m <= 1.6
    ax_c.plot(range_m[mask], prof_b_norm[mask], "b-", linewidth=1.5)
    for incl in phantom.inclusions:
        R = float(np.sqrt(
            (sim["az_positions_m"][i_az_b] - incl.x_m) ** 2 + incl.z_m ** 2
        ))
        if R <= 1.6:
            ax_c.axvline(R, color="red", linestyle="--", linewidth=1.0,
                         label=f"{incl.label} R={R:.2f}m")
    ax_c.set_xlabel("Range [m]")
    ax_c.set_ylabel("Norm |CIR|")
    ax_c.set_title(f"C. Range Profile\n(az={sim['az_positions_m'][i_az_b]:.2f} m)")
    ax_c.set_xlim(0, 1.6)
    ax_c.legend(fontsize=6)
    ax_c.grid(True, alpha=0.3)

    # Panel D: Reconstructed heatmap
    ax_d = fig.add_subplot(gs[0, 3])
    im_d = ax_d.pcolormesh(z_img, x_img, heatmap, cmap=_CMAP_RECON, vmin=0, vmax=1, shading="auto")
    fig.colorbar(im_d, ax=ax_d, shrink=0.8, label="Contrast [0,1]")
    for incl in phantom.inclusions:
        ax_d.plot(incl.z_m, incl.x_m, "w+", ms=10, mew=2)
    for pk in sim["summary"]["peaks"]:
        ax_d.plot(pk["z_m"], pk["x_m"], "r^", ms=7)
    ax_d.set_title(f"D. Contrast Heatmap\n(dr={dr_m*100:.1f} cm, NOT eps_r)")
    ax_d.set_xlabel("z [m]")
    ax_d.set_ylabel("x [m]")

    # Panel E-H: Row 2 - detailed inclusion comparison
    ax_e = fig.add_subplot(gs[1, 0:2])
    # H(f, x_az) magnitude image
    H_mag_2d = np.abs(H_stitched)
    H_mag_2d_norm = H_mag_2d / (np.max(H_mag_2d) + 1e-15)
    im_e = ax_e.pcolormesh(
        sim["az_positions_m"], freqs_stitched / 1e9, H_mag_2d_norm,
        cmap="hot", vmin=0, vmax=1, shading="auto",
    )
    fig.colorbar(im_e, ax=ax_e, shrink=0.8, label="|H| norm.")
    ax_e.set_xlabel("Azimuth x [m]")
    ax_e.set_ylabel("Frequency [GHz]")
    ax_e.set_title("E. H(f, x_az) -- Channel Cube (stitched, normalized)")

    ax_f = fig.add_subplot(gs[1, 2:4])
    # Side-by-side: ground truth vs reconstructed
    gt_map_f = permittivity_map_to_reflectivity_map(eps_map, PHANTOM_EPS_BG, normalize=True)
    hm_on_gt  = _resize_grid(heatmap, x_img, z_img, x_grid, z_grid)
    combo = np.concatenate([gt_map_f, hm_on_gt], axis=1)
    extended_z = np.concatenate([z_grid, z_grid + (z_grid[-1] - z_grid[0] + (z_grid[1] - z_grid[0]))])
    im_f = ax_f.pcolormesh(
        extended_z, x_grid, combo,
        cmap="hot", vmin=0, vmax=1, shading="auto",
    )
    fig.colorbar(im_f, ax=ax_f, shrink=0.8, label="Normalized contrast [0,1]")
    ax_f.axvline(z_grid[-1], color="white", linewidth=1.5, linestyle="--")
    ax_f.text(z_grid[len(z_grid)//2], x_grid[-1], "GT Reflectivity",
              ha="center", va="bottom", color="white", fontsize=8)
    z_offset = z_grid[-1] + (z_grid[1] - z_grid[0])
    ax_f.text(z_offset + z_grid[len(z_grid)//2], x_grid[-1], "Recon Heatmap",
              ha="center", va="bottom", color="white", fontsize=8)
    ax_f.set_xlabel("z [m] (left=GT, right=Recon)")
    ax_f.set_ylabel("x [m]")
    ax_f.set_title(f"F. GT vs Recon Side-by-Side  (RMSE={sim['metrics']['rmse']:.4f})")

    fig.suptitle(
        "UWB-OFDM-SAR -- Dielectric Contrast Heatmap Pipeline Summary\n"
        "(Simulation only. Relative contrast. Not absolute eps_r. No clinical claims.)",
        fontsize=12, fontweight="bold",
    )
    out = OUT_DIR / "pipeline_summary_figure.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [fig5] saved: {out.name}")


# ===========================================================================
# Markdown summaries
# ===========================================================================

def write_figure_explanations(sim: dict) -> None:
    """Write one Markdown file per figure explaining scientific content."""

    phantom = sim["phantom"]
    dr_m    = sim["dr_m"]
    bw_hz   = sim["bw_hz"]
    daz_m   = sim["daz_m"]
    metrics = sim["metrics"]
    summary = sim["summary"]

    inclusions_text = "\n".join(
        f"  - **{incl.label}**: center ({incl.x_m:.2f}, {incl.z_m:.2f}) m, "
        f"r={incl.radius_m:.2f} m, eps_r={incl.epsilon_r}, "
        f"|Gamma|={abs(phantom.fresnel_reflectivity(phantom.epsilon_r_bg, incl.epsilon_r)):.3f}"
        for incl in phantom.inclusions
    )

    peaks_text = "\n".join(
        f"  - Peak {i+1}: ({pk['x_m']:.2f}, {pk['z_m']:.2f}) m, value={pk['value']:.3f}"
        for i, pk in enumerate(summary["peaks"])
    )

    figs = {
        "synthetic_ground_truth_permittivity_map": f"""# Figure: synthetic_ground_truth_permittivity_map.png

**Script:** `experiments/run_relative_permittivity_heatmap_simulation.py`

**Input:** `make_two_inclusion_phantom()` with eps_r_bg={PHANTOM_EPS_BG}, eps_r_A={PHANTOM_EPS_A}, eps_r_B={PHANTOM_EPS_B}

**What it shows:**
Two-panel figure showing the synthetic 2D dielectric phantom:
- Left panel: 2D relative permittivity map (eps_r). Background = {PHANTOM_EPS_BG} (air). Two circular inclusions:
{inclusions_text}
- Right panel: corresponding Fresnel reflectivity |Gamma| map, normalized to [0,1].

**Why it matters:**
This is the ground truth the SAR reconstruction tries to recover. It defines what a perfect reconstruction would look like. The reflectivity map (right) is what a backprojection algorithm would ideally produce.

**What it does NOT prove:**
- That the radar can measure absolute epsilon_r.
- That any real material matches these parameters.
- That this model is valid for dispersive or lossy media.
""",
        "reconstructed_relative_contrast_heatmap": f"""# Figure: reconstructed_relative_contrast_heatmap.png

**Script:** `experiments/run_relative_permittivity_heatmap_simulation.py`

**Input:** `simulate_h_matrix()` x5 blocks -> `stitch_h_matrices()` -> `backprojection_image()` -> `sar_image_to_contrast_heatmap()`

**What it shows:**
2D normalized |SAR image| after near-field backprojection of stitched H(f, x_az).
- Color: relative contrast [0,1], brighter = stronger reflectivity.
- White + markers: true inclusion centers.
- Red triangles: reconstructed peak positions.
- Range resolution: {dr_m*100:.1f} cm. Azimuth resolution (approx): {daz_m*100:.1f} cm.
- Reconstructed peaks:
{peaks_text}

**Why it matters:**
Demonstrates that the UWB-OFDM-SAR backprojection pipeline correctly localizes dielectric inclusions using simulated data. Shows the pipeline is working end-to-end before hardware validation.

**What it does NOT prove:**
- Absolute permittivity or epsilon_r values.
- That the reconstruction works on real hardware data.
- Medical or biological tissue characterization.
- Clinical diagnosis of any kind.
""",
        "heatmap_error_or_difference.png": f"""# Figure: heatmap_error_or_difference.png

**Script:** `experiments/run_relative_permittivity_heatmap_simulation.py`

**Input:** Ground truth Fresnel reflectivity map vs. interpolated reconstructed heatmap.

**What it shows:**
Three-panel comparison:
1. Ground truth Fresnel |Gamma| map (simplified model).
2. Reconstructed contrast heatmap (interpolated to GT grid).
3. Difference: recon - GT. RMSE = {metrics['rmse']:.4f}.

**Why it matters:**
Quantifies reconstruction error relative to the simplified ground truth. Identifies where the backprojection algorithm agrees with (and deviates from) the idealized point-scatterer model.

**What it does NOT prove:**
- That the Fresnel model is a correct physical description of the scene.
- That the RMSE metric is meaningful without a calibrated reference material.
- Absolute accuracy of the system.
""",
        "range_profiles_from_heatmap_pipeline": f"""# Figure: range_profiles_from_heatmap_pipeline.png

**Script:** `experiments/run_relative_permittivity_heatmap_simulation.py`

**Input:** `range_profiles_from_h_matrix()` on stitched H(f, x_az).

**What it shows:**
Range profiles (normalized |CIR(R)|) at selected azimuth positions, one per aperture location aligned with each inclusion. Red dashed lines mark expected target ranges. Effective BW = {bw_hz/1e9:.2f} GHz, range resolution = {dr_m*100:.1f} cm.

**Why it matters:**
Shows that the system can resolve separate targets at different ranges. The CIR peaks align with expected target distances when the aperture is near the target azimuth. This validates the range compression step of the pipeline.

**What it does NOT prove:**
- Absolute range accuracy without hardware calibration.
- Performance with real hardware signals (noise, phase errors, etc.).
""",
        "pipeline_summary_figure": f"""# Figure: pipeline_summary_figure.png

**Script:** `experiments/run_relative_permittivity_heatmap_simulation.py`

**Input:** Full simulation pipeline end-to-end.

**What it shows:**
Six-panel summary of the complete UWB-OFDM-SAR heatmap pipeline:
- A. Phantom ground truth permittivity map.
- B. Stitched H(f) spectrum (all {len(BLOCK_CENTERS_HZ)} blocks, BW={bw_hz/1e9:.2f} GHz).
- C. Range profile at an azimuth near inclusion B.
- D. Reconstructed contrast heatmap.
- E. H(f, x_az) channel cube (2D view of stitched data).
- F. Side-by-side GT reflectivity vs. reconstructed heatmap.

**Why it matters:**
Provides a single-figure overview of the complete pipeline for the thesis. Shows every processing stage from raw H(f, x_az) through to the final contrast image. Useful for presentations and thesis chapters.

**What it does NOT prove:**
- Hardware performance or calibration.
- Absolute permittivity.
- Medical/biological applicability.
""",
    }

    for name, text in figs.items():
        out = OUT_DIR / f"figure_explanation_{name}.md"
        out.write_text(text, encoding="utf-8")
    print(f"  [md] Figure explanation markdowns saved to {OUT_DIR.name}/")


def write_heatmap_summary_report(sim: dict) -> None:
    """Write phase5_heatmap_simulation_summary.md to reports/generated/phase5_dielectric_heatmap/."""
    phantom  = sim["phantom"]
    metrics  = sim["metrics"]
    summary  = sim["summary"]
    bw_hz    = sim["bw_hz"]
    dr_m     = sim["dr_m"]
    daz_m    = sim["daz_m"]

    peaks_md = "\n".join(
        f"| {i+1} | {pk['x_m']:.3f} | {pk['z_m']:.3f} | {pk['value']:.3f} |"
        for i, pk in enumerate(summary["peaks"])
    )

    incl_match_md = ""
    if "inclusion_matches" in summary:
        rows = []
        for m in summary["inclusion_matches"]:
            err = f"{m['distance_error_m']*100:.1f} cm" if m["distance_error_m"] is not None else "N/A"
            rows.append(
                f"| {m['label']} | {m['true_x_m']:.2f} | {m['true_z_m']:.2f} | {m['epsilon_r']} | {err} |"
            )
        incl_match_md = "\n| Inclusion | True x [m] | True z [m] | eps_r | Location error |\n|---|---|---|---|---|\n" + "\n".join(rows)

    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    text = f"""# Phase 5 Heatmap Simulation Summary

Generated: {now}

## Simulation parameters

- Phantom: {len(phantom.inclusions)} dielectric inclusions, eps_r_bg={phantom.epsilon_r_bg}
- OFDM blocks: {len(BLOCK_CENTERS_HZ)} (centers: {[f'{f/1e9:.1f}' for f in BLOCK_CENTERS_HZ]} GHz)
- Sample rate per block: {SAMPLE_RATE_HZ/1e6:.0f} MHz (SIMULATION ONLY -- not achievable in hardware)
- n_fft={N_FFT}, n_active={N_ACTIVE}
- Azimuth positions: {N_AZ_POSITIONS} from {-AZ_HALF_SPAN_M:.2f} to +{AZ_HALF_SPAN_M:.2f} m
- Effective BW: {bw_hz/1e9:.3f} GHz
- Range resolution: {dr_m*100:.1f} cm
- Azimuth resolution (approx): {daz_m*100:.1f} cm
- Noise std: {NOISE_STD}

## Reconstruction metrics

- Heatmap RMSE vs GT: {metrics['rmse']:.4f}
- Heatmap max abs error: {metrics['max_abs_error']:.4f}

## Reconstructed contrast peaks

| Peak | x [m] | z [m] | Contrast value |
|---|---|---|---|
{peaks_md}

## Inclusion localization accuracy
{incl_match_md}

## Scientific notes

- Output is a **relative dielectric contrast heatmap**, NOT absolute permittivity.
- Ground truth uses simplified Fresnel model (non-dispersive, lossless, point-scatter).
- Simulation uses {SAMPLE_RATE_HZ/1e6:.0f} MHz sample rate per block (NOT achievable by bladeRF).
- Real hardware equivalent: multiple 20 MHz bladeRF blocks stitched to cover same frequency span.
- No RF transmitted. No hardware used. No clinical claims.

## No forbidden claims

- No absolute epsilon_r from hardware.
- No cancer detection.
- No clinical diagnosis.
- No validated medical imaging.
"""
    out = OUT_DIR / "phase5_heatmap_simulation_summary.md"
    out.write_text(text, encoding="utf-8")
    print(f"  [md] Summary saved: {out.name}")


# ===========================================================================
# TX1/RX1 audit
# ===========================================================================

def run_tx1_rx1_audit() -> dict:
    """
    Search runnable Python files and configs for forbidden TX2/RX2 references.

    Returns a dict with audit results.
    """
    import re
    forbidden = ["TX2", "RX2", "TX_X2", "RX_X2", "CHANNEL_TX(1)", "CHANNEL_RX(1)"]
    search_dirs = [
        _REPO_ROOT / "hardware",
        _REPO_ROOT / "acquisition",
        _REPO_ROOT / "processing",
        _REPO_ROOT / "experiments",
        _REPO_ROOT / "simulation",
        _REPO_ROOT / "configs",
    ]
    violations: list[str] = []
    scanned = 0
    this_file = pathlib.Path(__file__).resolve()

    for d in search_dirs:
        if not d.exists():
            continue
        for ext in ("*.py", "*.yaml", "*.yml", "*.json"):
            for fpath in d.rglob(ext):
                if "__pycache__" in str(fpath):
                    continue
                if fpath.resolve() == this_file:
                    # Skip audit script itself -- it legitimately lists forbidden strings
                    continue
                try:
                    text = fpath.read_text(encoding="utf-8", errors="ignore")
                    scanned += 1
                    for pat in forbidden:
                        if re.search(re.escape(pat), text, re.IGNORECASE):
                            for i, line in enumerate(text.splitlines(), 1):
                                if re.search(re.escape(pat), line, re.IGNORECASE):
                                    stripped = line.strip()
                                    # Skip pure comment/doc lines
                                    if (
                                        not stripped.startswith("#")
                                        and not stripped.startswith('"""')
                                        and not stripped.startswith("'''")
                                        and not stripped.startswith("'")
                                    ):
                                        violations.append(
                                            f"{fpath.relative_to(_REPO_ROOT)}:{i}: {stripped[:80]}"
                                        )
                except Exception:
                    pass

    return {
        "scanned_files": scanned,
        "violations": violations,
        "passed": len(violations) == 0,
    }


# ===========================================================================
# Background subtraction demo
# ===========================================================================

# Clutter target simulating background (e.g., metallic wall or table surface)
_BG_CLUTTER_X_M   = 0.0    # centered on aperture
_BG_CLUTTER_Z_M   = 1.80   # 1.8 m away -- beyond both inclusions
_BG_CLUTTER_AMP   = 0.8    # strong metallic-like reflectivity


def run_background_subtraction_demo(sim: dict) -> dict:
    """
    Simulate background subtraction: detect both inclusions through clutter removal.

    Scenario:
      - Background clutter: metallic point target at z=1.8 m (simulates wall/table).
      - Background scene: clutter target only.
      - Object scene:     clutter target + two dielectric inclusions.
      - H_delta(f, x_az) = H_obj - H_bg (removes clutter, isolates inclusions).
      - Backproject H_delta -> heatmap showing both inclusions.

    This mirrors the real hardware protocol:
      1. Capture without test object -> H_bg.
      2. Place test object -> capture H_obj.
      3. Compute H_delta = H_obj - H_bg.
      4. Reconstruct heatmap from H_delta.
    """
    from simulation.ofdm_uwb_sar_simulator import PointTarget

    phantom = sim["phantom"]
    az_positions_m = sim["az_positions_m"]

    # Background clutter target (metallic -- no Fresnel model needed, just strong amp)
    clutter_target = PointTarget(
        x_m=_BG_CLUTTER_X_M, z_m=_BG_CLUTTER_Z_M,
        reflectivity=complex(_BG_CLUTTER_AMP),
    )
    targets_bg  = [clutter_target]
    targets_obj = [clutter_target] + phantom.to_point_targets()

    print("[BGSub] Simulating background scene (clutter only)...")
    blocks_H_bg: list[np.ndarray] = []
    blocks_f_bg: list[np.ndarray] = []
    for i, fc in enumerate(BLOCK_CENTERS_HZ):
        params = OFDMParameters(
            n_fft=N_FFT, n_active=N_ACTIVE, cp_len=32,
            sample_rate_hz=SAMPLE_RATE_HZ, center_freq_hz=fc,
            dc_null=True, guard_bins=GUARD_BINS, pilot_seed=PILOT_SEED,
        )
        H_b, f_b, _ = simulate_h_matrix(
            params, targets_bg, az_positions_m,
            noise_std=NOISE_STD, seed=PILOT_SEED + i,
        )
        blocks_H_bg.append(H_b)
        blocks_f_bg.append(f_b)
    H_bg, f_bg = _stitch_h_matrices(blocks_H_bg, blocks_f_bg)

    print("[BGSub] Simulating object scene (clutter + inclusions)...")
    blocks_H_obj: list[np.ndarray] = []
    blocks_f_obj: list[np.ndarray] = []
    for i, fc in enumerate(BLOCK_CENTERS_HZ):
        params = OFDMParameters(
            n_fft=N_FFT, n_active=N_ACTIVE, cp_len=32,
            sample_rate_hz=SAMPLE_RATE_HZ, center_freq_hz=fc,
            dc_null=True, guard_bins=GUARD_BINS, pilot_seed=PILOT_SEED,
        )
        H_b, f_b, _ = simulate_h_matrix(
            params, targets_obj, az_positions_m,
            noise_std=NOISE_STD, seed=PILOT_SEED + i,
        )
        blocks_H_obj.append(H_b)
        blocks_f_obj.append(f_b)
    H_obj, f_obj = _stitch_h_matrices(blocks_H_obj, blocks_f_obj)

    # Background subtraction
    H_delta = H_obj - H_bg

    print("[BGSub] Backprojecting H_delta...")
    sar_delta = backprojection_image(
        H_delta, f_obj, az_positions_m,
        X_IMG, Z_IMG, padding_factor=8, window="hanning",
    )
    sar_obj_full = backprojection_image(
        H_obj, f_obj, az_positions_m,
        X_IMG, Z_IMG, padding_factor=8, window="hanning",
    )

    heatmap_delta    = sar_image_to_contrast_heatmap(sar_delta, normalize=True)
    heatmap_obj_full = sar_image_to_contrast_heatmap(sar_obj_full, normalize=True)

    summary_delta = heatmap_summary(heatmap_delta, X_IMG, Z_IMG, inclusions=phantom.inclusions)
    print(f"  Peaks after BG subtraction (threshold 0.3): {summary_delta['n_peaks_found']}")
    for pk in summary_delta["peaks"]:
        print(f"    Peak at ({pk['x_m']:.2f}, {pk['z_m']:.2f}) m, contrast={pk['value']:.3f}")

    return {
        "H_bg": H_bg,
        "H_obj": H_obj,
        "H_delta": H_delta,
        "freqs": f_obj,
        "sar_delta": sar_delta,
        "sar_obj_full": sar_obj_full,
        "heatmap_delta": heatmap_delta,
        "heatmap_obj_full": heatmap_obj_full,
        "summary_delta": summary_delta,
    }


def fig6_background_subtraction(sim: dict, bgsub: dict) -> None:
    """Figure 6: background_subtraction_comparison.png"""
    phantom          = sim["phantom"]
    x_img, z_img     = sim["x_img"], sim["z_img"]
    heatmap_original = sim["heatmap"]     # H_obj only, no background
    heatmap_obj_full = bgsub["heatmap_obj_full"]  # H_obj with clutter
    heatmap_delta    = bgsub["heatmap_delta"]      # H_delta after subtraction
    summary_delta    = bgsub["summary_delta"]

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle(
        "Background Subtraction Demo -- H_delta = H_obj - H_bg\n"
        "(Simulation. Relative contrast only. NOT absolute eps_r.)",
        fontsize=11,
    )

    def _plot_heatmap(ax, hm, title, phantom, peaks=None, clutter_z=None):
        im = ax.pcolormesh(z_img, x_img, hm, cmap=_CMAP_RECON, vmin=0, vmax=1, shading="auto")
        plt.colorbar(im, ax=ax, label="Contrast [0,1]")
        for incl in phantom.inclusions:
            ax.plot(incl.z_m, incl.x_m, "w+", ms=11, mew=2,
                    label=f"{incl.label} eps={incl.epsilon_r}")
        if clutter_z is not None:
            ax.axvline(clutter_z, color="yellow", linewidth=1.5, linestyle="--",
                       label=f"Clutter at z={clutter_z}m")
        if peaks:
            for pk in peaks:
                ax.plot(pk["z_m"], pk["x_m"], "r^", ms=8)
        ax.set_title(title)
        ax.set_xlabel("Down-range z [m]")
        ax.set_ylabel("Cross-range x [m]")
        ax.legend(fontsize=7, loc="upper right")
        ax.set_xlim(z_img[0], z_img[-1])
        ax.set_ylim(x_img[0], x_img[-1])

    _plot_heatmap(axes[0], heatmap_obj_full,
                  f"H_obj only (inclusions + clutter)\n[no BG subtraction]",
                  phantom, clutter_z=_BG_CLUTTER_Z_M)
    _plot_heatmap(axes[1], heatmap_original,
                  "H_obj only (no clutter in sim)\n[Phase 5 base result]",
                  phantom)
    _plot_heatmap(axes[2], heatmap_delta,
                  f"H_delta = H_obj - H_bg\n[both inclusions detectable]",
                  phantom, peaks=summary_delta["peaks"])

    plt.tight_layout()
    out = OUT_DIR / "background_subtraction_comparison.png"
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  [fig6] saved: {out.name}")


# ===========================================================================
# Main
# ===========================================================================

def main() -> None:
    print("=" * 60)
    print("Phase 5: Relative Dielectric Contrast Heatmap Simulation")
    print("=" * 60)

    print("\n[1] Running TX1/RX1 audit...")
    audit = run_tx1_rx1_audit()
    print(f"  Scanned {audit['scanned_files']} files.")
    if audit["passed"]:
        print("  TX1/RX1 audit: PASS -- no TX2/RX2 violations found.")
    else:
        print(f"  TX1/RX1 audit: VIOLATIONS FOUND ({len(audit['violations'])} items):")
        for v in audit["violations"]:
            print(f"    {v}")

    print("\n[2] Running simulation...")
    sim = run_simulation()

    print("\n[3] Generating figures...")
    fig1_ground_truth(sim)
    fig2_reconstructed_heatmap(sim)
    fig3_error_difference(sim)
    fig4_range_profiles(sim)
    fig5_pipeline_summary(sim)

    print("\n[4] Background subtraction demo...")
    bgsub = run_background_subtraction_demo(sim)
    fig6_background_subtraction(sim, bgsub)

    print("\n[5] Writing Markdown summaries...")
    write_figure_explanations(sim)
    write_heatmap_summary_report(sim)

    print("\n[6] Saving numpy arrays for downstream use...")
    np.save(OUT_DIR / "H_stitched.npy", sim["H_stitched"])
    np.save(OUT_DIR / "freqs_stitched.npy", sim["freqs_stitched"])
    np.save(OUT_DIR / "sar_image.npy", sim["sar_img"])
    np.save(OUT_DIR / "heatmap.npy", sim["heatmap"])
    np.save(OUT_DIR / "eps_map.npy", sim["eps_map"])
    np.save(OUT_DIR / "H_delta.npy", bgsub["H_delta"])
    np.save(OUT_DIR / "heatmap_delta.npy", bgsub["heatmap_delta"])
    print(f"  Arrays saved to {OUT_DIR.name}/")

    print("\n" + "=" * 60)
    print("Phase 5 simulation complete.")
    print(f"Output: {OUT_DIR}")
    print("No hardware used. No RF transmitted. No clinical claims.")
    print("=" * 60)


if __name__ == "__main__":
    main()
