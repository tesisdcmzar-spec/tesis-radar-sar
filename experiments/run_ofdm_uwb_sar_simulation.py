"""
Offline UWB-OFDM-SAR simulation demo.

No hardware. No bladeRF. No RF. No motors. No clinical claims.
This script is a mathematical demonstration of the UWB-OFDM-SAR pipeline.

Usage
-----
  py experiments/run_ofdm_uwb_sar_simulation.py

Outputs
-------
  reports/generated/ofdm_sim_h_magnitude.png
  reports/generated/ofdm_sim_range_profiles.png
  reports/generated/ofdm_sim_sar_image.png
  reports/generated/ofdm_uwb_sar_simulation_summary.md
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from simulation.ofdm_uwb_sar_simulator import (
    OFDMParameters,
    PointTarget,
    simulate_h_matrix,
    range_profiles_from_h_matrix,
    backprojection_image,
)
from processing.ofdm_channel import summarize_ofdm_channel

REPORTS_GEN = _ROOT / "reports" / "generated"
REPORTS_GEN.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Scene configuration
# Two point targets at different cross-range and down-range positions.
# ---------------------------------------------------------------------------

TARGETS = [
    PointTarget(x_m=-0.05, z_m=0.30, reflectivity=1.0 + 0j),
    PointTarget(x_m=+0.08, z_m=0.55, reflectivity=0.7 + 0j),
]

# OFDM parameters -- synthetic for simulation only.
# Real bladeRF hardware would use lower Fs and stitched blocks.
PARAMS = OFDMParameters(
    n_fft=512,
    n_active=400,
    cp_len=64,
    sample_rate_hz=2e9,    # synthetic: df = 3.9 MHz, BW ~ 1.56 GHz, dR ~ 9.6 cm
    center_freq_hz=5.0e9,
    dc_null=True,
    guard_bins=4,
    pilot_seed=42,
)

AZ_POSITIONS_M = np.linspace(-0.15, 0.15, 21)
X_IMG = np.linspace(-0.20, 0.20, 120)
Z_IMG = np.linspace(0.05, 0.80, 120)


def run() -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] UWB-OFDM-SAR offline simulation")
    print("  No hardware. No RF. No clinical claims.")
    print(f"  Targets: {len(TARGETS)}")
    for i, t in enumerate(TARGETS):
        print(f"    T{i+1}: x={t.x_m*100:.1f} cm, z={t.z_m*100:.1f} cm, "
              f"|rho|={abs(t.reflectivity):.2f}")
    print(f"  OFDM: N_fft={PARAMS.n_fft}, N_active={PARAMS.n_active}, "
          f"cp={PARAMS.cp_len}, Fs={PARAMS.sample_rate_hz/1e6:.0f} MS/s (synthetic)")
    n_active = len(PARAMS.active_indices)
    df = PARAMS.subcarrier_spacing_hz
    bw_mhz = n_active * df / 1e6
    dr_cm = 3e8 / (2 * n_active * df) * 100
    print(f"  Active subcarriers: {n_active}, BW ~ {bw_mhz:.1f} MHz, "
          f"range resolution ~ {dr_cm:.1f} cm")
    print(f"  Azimuth: {len(AZ_POSITIONS_M)} positions, "
          f"{AZ_POSITIONS_M[0]*100:.0f} to {AZ_POSITIONS_M[-1]*100:.0f} cm")

    # --- 1. Simulate H(f, x_az) ---
    print("  Simulating H(f, x_az) ...")
    H_mat, freqs_hz, az_m = simulate_h_matrix(
        PARAMS, TARGETS, AZ_POSITIONS_M, aperture_z_m=0.0, noise_std=0.01, seed=7
    )
    print(f"  H_matrix shape: {H_mat.shape}")

    # --- 2. Summary of center aperture column ---
    center_az = len(az_m) // 2
    H_center = H_mat[:, center_az]
    summary = summarize_ofdm_channel(H_center, freqs_hz=freqs_hz,
                                     sample_rate_hz=PARAMS.sample_rate_hz)
    print(f"  Center az channel: mag_mean={summary['mag_mean']:.4f}, "
          f"mag_db_range={summary['mag_db_range']:.1f} dB")

    # --- 3. Range profiles ---
    print("  Computing range profiles ...")
    range_m, profiles = range_profiles_from_h_matrix(
        H_mat, freqs_hz, padding_factor=8, window="hanning"
    )

    # --- 4. Backprojection image ---
    print("  Running backprojection ...")
    img = backprojection_image(
        H_mat, freqs_hz, az_m, X_IMG, Z_IMG, padding_factor=8, window="hanning"
    )
    img_db = 20 * np.log10(np.abs(img) / (np.max(np.abs(img)) + 1e-15))

    # --- 5. Peak detection ---
    peak_idx = np.argmax(np.abs(img))
    ix, iz = np.unravel_index(peak_idx, img.shape)
    peak_x, peak_z = float(X_IMG[ix]), float(Z_IMG[iz])
    nearest_target = min(TARGETS, key=lambda t: (t.x_m - peak_x)**2 + (t.z_m - peak_z)**2)
    range_error_cm = 100 * np.sqrt(
        (peak_x - nearest_target.x_m)**2 + (peak_z - nearest_target.z_m)**2
    )
    print(f"  Image peak: x={peak_x*100:.1f} cm, z={peak_z*100:.1f} cm")
    print(f"  Nearest target: x={nearest_target.x_m*100:.1f} cm, "
          f"z={nearest_target.z_m*100:.1f} cm")
    print(f"  Peak-to-target distance: {range_error_cm:.1f} cm")

    # --- 6. Figures ---
    _plot_h_magnitude(H_mat, freqs_hz, az_m)
    _plot_range_profiles(range_m, profiles, az_m)
    _plot_sar_image(img_db, X_IMG, Z_IMG)

    # --- 7. Summary markdown ---
    _write_summary(H_mat, freqs_hz, az_m, summary, peak_x, peak_z,
                   nearest_target, range_error_cm, ts, bw_mhz, dr_cm)

    print("  Done. Outputs in reports/generated/")


def _plot_h_magnitude(H_mat, freqs_hz, az_m):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    # H magnitude vs frequency (center az column)
    ax = axes[0]
    center_az = len(az_m) // 2
    mag_db = 20 * np.log10(np.abs(H_mat[:, center_az]) + 1e-15)
    ax.plot(freqs_hz / 1e9, mag_db)
    ax.set_xlabel("Frequency [GHz]")
    ax.set_ylabel("|H[k]| [dB]")
    ax.set_title(f"Channel magnitude (az={az_m[center_az]*100:.0f} cm)")
    ax.grid(True, alpha=0.3)

    # H magnitude image H(f, x_az)
    ax = axes[1]
    img_disp = 20 * np.log10(np.abs(H_mat) + 1e-15)
    im = ax.imshow(
        img_disp, aspect="auto",
        extent=[az_m[0]*100, az_m[-1]*100, freqs_hz[-1]/1e9, freqs_hz[0]/1e9],
        cmap="viridis",
    )
    plt.colorbar(im, ax=ax, label="|H| [dB]")
    ax.set_xlabel("Azimuth [cm]")
    ax.set_ylabel("Frequency [GHz]")
    ax.set_title("H(f, x_az) -- channel data cube")

    fig.suptitle("OFDM channel estimate H[k] -- simulation only, no hardware")
    fig.tight_layout()
    path = REPORTS_GEN / "ofdm_sim_h_magnitude.png"
    fig.savefig(path, dpi=100)
    plt.close(fig)
    print(f"  Saved: {path.name}")


def _plot_range_profiles(range_m, profiles, az_m):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4))

    # Single range profile
    ax = axes[0]
    center_az = len(az_m) // 2
    mag_db = 20 * np.log10(np.abs(profiles[:, center_az]) + 1e-15)
    mask = range_m < 1.5
    ax.plot(range_m[mask] * 100, mag_db[mask])
    for t in TARGETS:
        ax.axvline(t.z_m * 100, color="r", linestyle="--", alpha=0.6,
                   label=f"T z={t.z_m*100:.0f} cm")
    ax.set_xlabel("One-way range [cm]")
    ax.set_ylabel("Magnitude [dB]")
    ax.set_title(f"Range profile (az={az_m[center_az]*100:.0f} cm)")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # Range profile waterfall
    ax = axes[1]
    mag_all = 20 * np.log10(np.abs(profiles) + 1e-15)
    mask = range_m < 1.5
    im = ax.imshow(
        mag_all[mask, :], aspect="auto",
        extent=[az_m[0]*100, az_m[-1]*100,
                range_m[mask][-1]*100, range_m[mask][0]*100],
        cmap="plasma", origin="upper",
    )
    plt.colorbar(im, ax=ax, label="Magnitude [dB]")
    ax.set_xlabel("Azimuth [cm]")
    ax.set_ylabel("Range [cm]")
    ax.set_title("Range profiles H(range, x_az)")

    fig.suptitle("Range profiles -- simulation only, no hardware")
    fig.tight_layout()
    path = REPORTS_GEN / "ofdm_sim_range_profiles.png"
    fig.savefig(path, dpi=100)
    plt.close(fig)
    print(f"  Saved: {path.name}")


def _plot_sar_image(img_db, x_img, z_img):
    fig, ax = plt.subplots(figsize=(7, 6))
    vmin = max(img_db.max() - 40, img_db.min())
    im = ax.imshow(
        img_db.T, aspect="equal", origin="lower",
        extent=[x_img[0]*100, x_img[-1]*100, z_img[0]*100, z_img[-1]*100],
        cmap="hot", vmin=vmin, vmax=img_db.max(),
    )
    plt.colorbar(im, ax=ax, label="Normalized [dB re peak]")
    for i, t in enumerate(TARGETS):
        ax.plot(t.x_m*100, t.z_m*100, "c+", markersize=12, markeredgewidth=2,
                label=f"T{i+1} ({t.x_m*100:.0f}, {t.z_m*100:.0f}) cm")
    ax.set_xlabel("Cross-range [cm]")
    ax.set_ylabel("Down-range [cm]")
    ax.set_title("UWB-OFDM-SAR backprojection image\n"
                 "(simulation only -- no hardware, no clinical claims)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = REPORTS_GEN / "ofdm_sim_sar_image.png"
    fig.savefig(path, dpi=100)
    plt.close(fig)
    print(f"  Saved: {path.name}")


def _write_summary(H_mat, freqs_hz, az_m, summary, peak_x, peak_z,
                   nearest_target, range_error_cm, ts, bw_mhz, dr_cm):
    n_active = H_mat.shape[0]
    df_khz = (freqs_hz[1] - freqs_hz[0]) / 1e3 if len(freqs_hz) > 1 else 0.0
    lines = [
        "# UWB-OFDM-SAR Simulation Summary",
        "",
        f"**Generated:** {ts}",
        f"**Status:** Simulation only. No hardware. No RF. No clinical claims.",
        "",
        "## OFDM Parameters",
        f"- N_fft: {PARAMS.n_fft}",
        f"- N_active: {n_active} (dc_null={PARAMS.dc_null}, guard_bins={PARAMS.guard_bins})",
        f"- CP length: {PARAMS.cp_len} samples",
        f"- Sample rate (synthetic): {PARAMS.sample_rate_hz/1e6:.0f} MS/s",
        f"- Center frequency: {PARAMS.center_freq_hz/1e9:.2f} GHz",
        f"- Subcarrier spacing: {df_khz:.2f} kHz",
        f"- Active BW: {bw_mhz:.1f} MHz",
        f"- Range resolution (ideal): {dr_cm:.1f} cm",
        "",
        "## Scene",
    ]
    for i, t in enumerate(TARGETS):
        lines.append(f"- T{i+1}: x={t.x_m*100:.1f} cm, z={t.z_m*100:.1f} cm, "
                     f"|rho|={abs(t.reflectivity):.2f}")
    lines += [
        f"- Azimuth positions: {len(az_m)} ({az_m[0]*100:.0f} to {az_m[-1]*100:.0f} cm)",
        "",
        "## Channel Summary (center aperture position)",
        f"- Active subcarriers: {summary['n_subcarriers']}",
        f"- |H| mean: {summary['mag_mean']:.4f}",
        f"- |H| max: {summary['mag_max']:.4f}",
        f"- Dynamic range: {summary['mag_db_range']:.1f} dB",
        f"- CIR peak index: {summary['cir_peak_idx']}",
        "",
        "## Image Result",
        f"- Image peak: x={peak_x*100:.1f} cm, z={peak_z*100:.1f} cm",
        f"- Nearest target: x={nearest_target.x_m*100:.1f} cm, "
          f"z={nearest_target.z_m*100:.1f} cm",
        f"- Peak-to-target distance: {range_error_cm:.1f} cm",
        "",
        "## Figures",
        "- `ofdm_sim_h_magnitude.png` -- H(f) and H(f, x_az) data cube",
        "- `ofdm_sim_range_profiles.png` -- Range profiles and waterfall",
        "- `ofdm_sim_sar_image.png` -- SAR backprojection image",
        "",
        "## Scientific Claims",
        "- This is a mathematical simulation of the UWB-OFDM-SAR pipeline.",
        "- No real electromagnetic wave was transmitted or received.",
        "- No physical medium was imaged.",
        "- Result demonstrates pipeline correctness, not clinical utility.",
        "- Safe claim: H[k] = Y[k] / X[k] recovers a known synthetic channel.",
        "- Backprojection localizes synthetic targets in simulation.",
        "- Not validated for clinical imaging. No cancer claims.",
    ]
    path = REPORTS_GEN / "ofdm_uwb_sar_simulation_summary.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Saved: {path.name}")


if __name__ == "__main__":
    run()
