"""
Run the hardware-independent simulation pipeline and save figures.

Usage (from project root):
    python experiments/run_simulation.py
    python experiments/run_simulation.py --config configs/simulation.yaml
    python experiments/run_simulation.py --noise 0.05
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import yaml

# Ensure project root is on path when run as a script
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import matplotlib
matplotlib.use("Agg")  # no display required
import matplotlib.pyplot as plt

from simulation.phantom_model import phantom_from_config
from simulation.synthetic_scan import scan_from_config
from processing.range_profile import compute_range_profiles
from processing.sar_reconstruction import backprojection, image_grid_from_config


def _save_range_profile_figure(scan, range_m, profiles, out_path: pathlib.Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Left: 2D range profile matrix
    ax = axes[0]
    ax.imshow(
        np.abs(profiles),
        aspect="auto",
        origin="lower",
        extent=[scan.x_az_m[0], scan.x_az_m[-1], range_m[0], range_m[-1]],
    )
    ax.set_xlabel("Azimuth position [m]")
    ax.set_ylabel("Range [m]")
    ax.set_ylim(0.0, 0.30)
    ax.set_title("|h(range, x_az)|")

    # Right: center aperture range profile (1D)
    ax2 = axes[1]
    center = profiles.shape[1] // 2
    ax2.plot(range_m, np.abs(profiles[:, center]))
    ax2.set_xlabel("Range [m]")
    ax2.set_ylabel("Amplitude [a.u.]")
    ax2.set_title(f"Range profile — center aperture (x={scan.x_az_m[center]:.3f} m)")
    ax2.set_xlim(0.0, 0.30)
    ax2.grid(True, alpha=0.4)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def _save_sar_image(phantom, scan, img, x_img, z_img, out_path: pathlib.Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    amp_db = 20 * np.log10(np.abs(img) / np.abs(img).max() + 1e-12)

    for ax, data, title in [
        (axes[0], np.abs(img).T, "SAR image — linear amplitude"),
        (axes[1], amp_db.T, "SAR image — dB (re peak)"),
    ]:
        im = ax.imshow(
            data,
            aspect="auto",
            origin="lower",
            extent=[x_img[0], x_img[-1], z_img[0], z_img[-1]],
        )
        fig.colorbar(im, ax=ax, fraction=0.046)
        for t in phantom.targets:
            ax.plot(
                t.x_m, t.z_m,
                "r+", markersize=14, markeredgewidth=2,
                label=f"({t.x_m:.2f}, {t.z_m:.2f}) m",
            )
        ax.set_xlabel("Cross-range [m]")
        ax.set_ylabel("Range [m]")
        ax.set_title(title)
        ax.legend(loc="upper right", fontsize=8)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Radar SAR simulation pipeline")
    parser.add_argument("--config", default="configs/simulation.yaml", help="YAML config path")
    parser.add_argument("--noise", type=float, default=0.0, help="Additive noise std (0=off)")
    args = parser.parse_args()

    config_path = pathlib.Path(args.config)
    if not config_path.exists():
        sys.exit(f"Config not found: {config_path}")

    with config_path.open() as f:
        cfg = yaml.safe_load(f)

    out_dir = pathlib.Path(cfg["output"]["figures_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== Radar SAR - Simulation Pipeline ===")
    print(f"  Config : {config_path}")
    print(f"  Output : {out_dir}")
    print(f"  Noise  : {args.noise}")
    print()

    # ---- Phantom ---------------------------------------------------------
    phantom = phantom_from_config(cfg)
    print(f"Phantom: {len(phantom.targets)} target(s)")
    for i, t in enumerate(phantom.targets):
        print(f"  [{i}] x={t.x_m:.3f} m  z={t.z_m:.3f} m  A={t.amplitude}")

    # ---- Synthetic scan --------------------------------------------------
    rng = np.random.default_rng(0)
    scan = scan_from_config(phantom, cfg, noise_std=args.noise, rng=rng)
    BW_GHz = scan.bandwidth_hz / 1e9
    range_res_cm = phantom.c / (2 * scan.bandwidth_hz) * 100
    print(f"\nScan: {scan.H.shape[0]} freq pts × {scan.H.shape[1]} az pts")
    print(f"  f = {scan.freqs_hz[0]/1e6:.0f}-{scan.freqs_hz[-1]/1e6:.0f} MHz  BW={BW_GHz:.2f} GHz")
    print(f"  Range resolution ~= {range_res_cm:.1f} cm  (Hanning window broadens ~2x)")

    # ---- Range profiles --------------------------------------------------
    pad = int(cfg["reconstruction"]["range_padding"])
    c = float(cfg["reconstruction"]["speed_of_light"])
    print(f"\nRange profiles: IFFT padding={pad}x")
    range_m, profiles = compute_range_profiles(scan, padding_factor=pad, c=c)
    print(f"  Output shape: {profiles.shape}  range step={1e3*(range_m[1]-range_m[0]):.2f} mm")

    _save_range_profile_figure(scan, range_m, profiles, out_dir / "range_profiles.png")

    # ---- SAR reconstruction ----------------------------------------------
    method = cfg["reconstruction"].get("method", "backprojection")
    print(f"\nSAR reconstruction: {method}")
    x_img, z_img = image_grid_from_config(cfg, N_x=200, N_z=200)
    img = backprojection(scan, x_img, z_img, c=c, padding_factor=pad)
    print(f"  Image shape: {img.shape}")

    _save_sar_image(phantom, scan, img, x_img, z_img, out_dir / "sar_image.png")

    print("\nDone. All figures saved to:", out_dir.resolve())


if __name__ == "__main__":
    main()
