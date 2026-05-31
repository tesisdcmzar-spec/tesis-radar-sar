"""
Run the hardware-independent simulation pipeline and save figures.

Usage (from project root):
    python experiments/run_simulation.py
    python experiments/run_simulation.py --config configs/simulation.yaml
    python experiments/run_simulation.py --noise 0.05
    python experiments/run_simulation.py --window none       # rectangular (best resolution)
    python experiments/run_simulation.py --window hanning    # Hanning (best sidelobes)
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from simulation.phantom_model import phantom_from_config
from simulation.synthetic_scan import scan_from_config
from processing.range_profile import compute_range_profiles
from processing.sar_reconstruction import backprojection, image_grid_from_config

# dB floor for all image displays
_DB_FLOOR = -25.0


def _db(amp: np.ndarray) -> np.ndarray:
    return 20 * np.log10(np.abs(amp) / np.abs(amp).max() + 1e-12)


def _save_range_profile_figure(
    phantom, scan, range_m_rect, profiles_rect, range_m_han, profiles_han, out_path: pathlib.Path
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Slant range to each target from the center aperture position
    x_center = scan.x_az_m[len(scan.x_az_m) // 2]
    slant_ranges_cm = [
        np.sqrt((x_center - t.x_m)**2 + t.z_m**2) * 100
        for t in phantom.targets
    ]
    target_colors = ['r', 'orange', 'lime', 'cyan']

    for ax, range_m, profiles, label in [
        (axes[0], range_m_rect, profiles_rect, "Rectangular window (best resolution)"),
        (axes[1], range_m_han,  profiles_han,  "Hanning window (low sidelobes)"),
    ]:
        center = profiles.shape[1] // 2
        ax.plot(range_m * 100, np.abs(profiles[:, center]), label="center aperture")
        for i, (t, sr) in enumerate(zip(phantom.targets, slant_ranges_cm)):
            ax.axvline(sr, color=target_colors[i], lw=0.9, ls='--',
                       label=f"T{i+1} slant range ({sr:.1f} cm)")
        ax.set_xlabel("Range [cm]")
        ax.set_ylabel("Amplitude [a.u.]")
        ax.set_title(label)
        ax.set_xlim(0, max(slant_ranges_cm) * 1.6)
        ax.grid(True, alpha=0.4)
        ax.legend(fontsize=8)

    t_desc = "  |  ".join(
        f"T{i+1}: ({t.x_m*100:.0f}, {t.z_m*100:.0f}) cm"
        for i, t in enumerate(phantom.targets)
    )
    fig.suptitle(f"Range profiles — center aperture  ({t_desc})")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def _save_sar_comparison(
    phantom, scan, img_rect, img_han, x_img, z_img, out_path: pathlib.Path
) -> None:
    """Side-by-side SAR images: rectangular vs Hanning window."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    for ax, img, title in [
        (axes[0], img_rect, "Rectangular window\n(7.5 cm range resolution)"),
        (axes[1], img_han,  "Hanning window\n(~15 cm range resolution)"),
    ]:
        amp_db = _db(img)
        im = ax.imshow(
            np.clip(amp_db, _DB_FLOOR, 0).T,
            aspect="auto",
            origin="lower",
            extent=[x_img[0] * 100, x_img[-1] * 100, z_img[0] * 100, z_img[-1] * 100],
            vmin=_DB_FLOOR, vmax=0,
            cmap="inferno",
        )
        fig.colorbar(im, ax=ax, fraction=0.046, label="dB")
        for t in phantom.targets:
            ax.plot(t.x_m * 100, t.z_m * 100, "c+", markersize=12, markeredgewidth=2,
                    label=f"({t.x_m*100:.0f}, {t.z_m*100:.0f}) cm")
        ax.set_xlabel("Cross-range [cm]")
        ax.set_ylabel("Range [cm]")
        ax.set_title(title)
        ax.legend(loc="upper right", fontsize=7)

    fig.suptitle(f"SAR backprojection — window comparison  (dB floor {_DB_FLOOR} dB)")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def _save_best_image(
    phantom, scan, img, x_img, z_img, window_label: str, out_path: pathlib.Path
) -> None:
    """High-resolution single SAR image panel (linear + dB)."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    amp = np.abs(img)
    amp_db = _db(img)

    for ax, data, title, cmap in [
        (axes[0], amp.T,                             "Linear amplitude",             "viridis"),
        (axes[1], np.clip(amp_db, _DB_FLOOR, 0).T,  f"dB (floor {_DB_FLOOR} dB)",  "inferno"),
    ]:
        im = ax.imshow(
            data,
            aspect="auto",
            origin="lower",
            extent=[x_img[0] * 100, x_img[-1] * 100, z_img[0] * 100, z_img[-1] * 100],
            cmap=cmap,
        )
        fig.colorbar(im, ax=ax, fraction=0.046)
        for t in phantom.targets:
            ax.plot(t.x_m * 100, t.z_m * 100, "r+", markersize=14, markeredgewidth=2,
                    label=f"({t.x_m*100:.0f}, {t.z_m*100:.0f}) cm")
        ax.set_xlabel("Cross-range [cm]")
        ax.set_ylabel("Range [cm]")
        ax.set_title(title)
        ax.legend(loc="upper right", fontsize=8)

    fig.suptitle(f"SAR image — {window_label} window  |  2 GHz BW  |  16 az positions")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Radar SAR simulation pipeline")
    parser.add_argument("--config", default="configs/simulation.yaml")
    parser.add_argument("--noise",  type=float, default=0.0)
    parser.add_argument("--window", default="none",
                        choices=["none", "hanning", "blackman"],
                        help="Range window (none=rectangular for best resolution)")
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
    print(f"  Window : {args.window}")
    print(f"  Noise  : {args.noise}")

    # ---- Phantom ---------------------------------------------------------
    phantom = phantom_from_config(cfg)
    print(f"\nPhantom: {len(phantom.targets)} target(s)")
    for i, t in enumerate(phantom.targets):
        print(f"  [{i}] x={t.x_m*100:.1f} cm  z={t.z_m*100:.1f} cm  A={t.amplitude}")

    # ---- Synthetic scan --------------------------------------------------
    rng = np.random.default_rng(0)
    scan = scan_from_config(phantom, cfg, noise_std=args.noise, rng=rng)
    BW_GHz = scan.bandwidth_hz / 1e9
    c = float(cfg["reconstruction"]["speed_of_light"])
    pad = int(cfg["reconstruction"]["range_padding"])
    range_res_cm = c / (2 * scan.bandwidth_hz) * 100

    print(f"\nScan: {scan.H.shape[0]} freq pts x {scan.H.shape[1]} az pts")
    print(f"  f = {scan.freqs_hz[0]/1e6:.0f}-{scan.freqs_hz[-1]/1e6:.0f} MHz  BW={BW_GHz:.2f} GHz")
    print(f"  Theoretical range resolution: {range_res_cm:.1f} cm (rectangular) / ~{2*range_res_cm:.0f} cm (Hanning)")

    # ---- Range profiles (both windows) -----------------------------------
    print(f"\nRange profiles: IFFT padding={pad}x")
    range_m_rect, profiles_rect = compute_range_profiles(scan, padding_factor=pad, window='none',    c=c)
    range_m_han,  profiles_han  = compute_range_profiles(scan, padding_factor=pad, window='hanning', c=c)
    print(f"  Shape: {profiles_rect.shape}  range step={1e3*(range_m_rect[1]-range_m_rect[0]):.1f} mm")

    _save_range_profile_figure(
        phantom, scan, range_m_rect, profiles_rect, range_m_han, profiles_han,
        out_dir / "range_profiles.png"
    )

    # ---- SAR reconstruction (both windows, zoomed ROI) -------------------
    # Zoom image to near-field phantom region with finer pixel grid
    x_img = np.linspace(-0.20, 0.20, 300)
    z_img = np.linspace(0.02, 0.26, 300)

    print(f"\nSAR reconstruction: backprojection")
    print(f"  Image grid: {len(x_img)} x {len(z_img)} pixels "
          f"({x_img[0]*100:.0f}-{x_img[-1]*100:.0f} cm x {z_img[0]*100:.0f}-{z_img[-1]*100:.0f} cm)")

    img_rect = backprojection(scan, x_img, z_img, c=c, padding_factor=pad, window='none')
    img_han  = backprojection(scan, x_img, z_img, c=c, padding_factor=pad, window='hanning')

    # Window comparison figure
    _save_sar_comparison(phantom, scan, img_rect, img_han, x_img, z_img,
                         out_dir / "sar_window_comparison.png")

    # Best-resolution standalone figure (user-selected window, default 'none')
    img_best = img_rect if args.window == 'none' else (
        img_han if args.window == 'hanning' else
        backprojection(scan, x_img, z_img, c=c, padding_factor=pad, window=args.window)
    )
    _save_best_image(phantom, scan, img_best, x_img, z_img, args.window,
                     out_dir / "sar_image.png")

    print(f"\nDone. Figures saved to: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
