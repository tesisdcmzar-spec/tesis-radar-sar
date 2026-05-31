"""
Offline post-processing analysis of the latest RX-only SFCW sweep.

Loads freqs_hz.npy and H_raw.npy from the most recent capture directory under:
    data/raw/rx_sfcw_sweep/full/     (preferred)
    data/raw/rx_sfcw_sweep/pilot/    (fallback)

If no local capture data exists (data/raw/ is gitignored; data may be absent
after a fresh clone or in a different session), generates synthetic noise data
and labels all outputs clearly as SYNTHETIC.  This keeps the pipeline
runnable and testable without requiring the bladeRF session data to persist.

OUTPUTS (written to reports/generated/)
    rx_sfcw_postprocess_h_comparison.png
    rx_sfcw_postprocess_range_comparison.png
    rx_sfcw_postprocess_peak_table.md
    rx_sfcw_postprocess_summary.md

SAFETY CONTRACT
---------------
- RX-ONLY analysis.  No hardware access.  No bladeRF.  No TX.  No motors.
- All H(f) operations are pure numpy -- no USB, no RF.
- No target detection claims.  No SAR imaging.  No clinical claims.
- H(f) from RX-only captures is environmental noise, NOT a radar transfer
  function.  Range profiles shown here are pipeline validation, NOT object
  detection.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from acquisition.rx_sfcw_sweep import (
    compute_sweep_metrics,
    make_synthetic_scan_from_h,
)
from processing.range_profile import compute_range_profiles
from processing.rx_sfcw_postprocess import (
    estimate_noise_floor_db,
    find_prominent_range_bins,
    normalize_h_magnitude,
    remove_dc_component,
    smooth_h_magnitude,
    summarize_range_profile,
)

REPORTS_DIR = REPO_ROOT / "reports" / "generated"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

RAW_BASE = REPO_ROOT / "data" / "raw" / "rx_sfcw_sweep"


# ---------------------------------------------------------------------------
# Data discovery
# ---------------------------------------------------------------------------

def find_latest_capture_dir() -> tuple[Path | None, str]:
    """
    Return (capture_dir, mode) for the most recent SFCW sweep session.

    Prefers full/ over pilot/.  Returns (None, 'none') if no data found.
    """
    for mode in ("full", "pilot"):
        mode_dir = RAW_BASE / mode
        if not mode_dir.exists():
            continue
        sessions = sorted(
            [d for d in mode_dir.iterdir() if d.is_dir()],
            key=lambda d: d.name,
        )
        if sessions:
            return sessions[-1], mode
    return None, "none"


def load_sweep_data(
    capture_dir: Path,
) -> tuple[np.ndarray, np.ndarray, dict, dict]:
    """
    Load freqs_hz, H_raw, metadata, sweep_summary from a capture directory.

    Does NOT load per-frequency IQ burst files (*.npy cap_*) to avoid reading
    large raw datasets.

    Returns
    -------
    (freqs_hz, H_raw, metadata, sweep_summary)
    """
    freqs_hz     = np.load(capture_dir / "freqs_hz.npy")
    H_raw        = np.load(capture_dir / "H_raw.npy")
    metadata     = json.loads((capture_dir / "metadata.json").read_text(encoding="utf-8"))
    sweep_summary= json.loads((capture_dir / "sweep_summary.json").read_text(encoding="utf-8"))
    return freqs_hz, H_raw, metadata, sweep_summary


def make_synthetic_data() -> tuple[np.ndarray, np.ndarray, dict, dict]:
    """
    Generate synthetic Gaussian-noise H(f) to demonstrate the pipeline.

    Used when no real capture data is available on disk.
    """
    rng = np.random.default_rng(0)
    freqs_hz = np.arange(2.3e9, 2.5e9 + 0.5e6, 1e6, dtype=np.float64)  # 201 pts
    # Simulate RX-only noise: complex Gaussian with small amplitude
    H_raw = (rng.normal(0, 0.004, len(freqs_hz)) +
             1j * rng.normal(0, 0.004, len(freqs_hz)))
    # Inject a weak ISM elevation near 2420 MHz to mimic observed Wi-Fi
    wifi_idx = np.argmin(np.abs(freqs_hz - 2.42e9))
    H_raw[wifi_idx] *= 2.5

    metadata = {
        "timestamp": "SYNTHETIC",
        "mode": "full_synthetic",
        "f_start_hz": float(freqs_hz[0]),
        "f_stop_hz":  float(freqs_hz[-1]),
        "step_hz": 1e6,
        "n_freqs": len(freqs_hz),
        "rx_only": True,
        "tx_enabled": False,
        "motors": False,
        "human_subject": False,
        "note": "Synthetic Gaussian noise -- no real hardware data present.",
    }
    sweep_summary = {
        "mode": "full_synthetic",
        "n_captured": len(freqs_hz),
        "n_clipped": 0,
        "n_failed": 0,
        "success": True,
    }
    return freqs_hz, H_raw, metadata, sweep_summary


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def compute_postprocess_variants(
    freqs_hz: np.ndarray,
    H_raw: np.ndarray,
) -> dict[str, np.ndarray]:
    """Return a dict of H(f) variants after various postprocessing steps."""
    H_dc  = remove_dc_component(H_raw)
    H_norm = normalize_h_magnitude(H_raw)
    H_smooth = smooth_h_magnitude(H_raw, window_len=5)
    H_dc_norm = normalize_h_magnitude(H_dc)
    return {
        "raw":      H_raw,
        "dc_removed": H_dc,
        "normalized": H_norm,
        "smoothed":   H_smooth,
        "dc_removed_normalized": H_dc_norm,
    }


def compute_profile_for_H(
    freqs_hz: np.ndarray,
    H: np.ndarray,
    window: str = 'hanning',
    padding_factor: int = 8,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute magnitude range profile in dB for a given H(f)."""
    scan = make_synthetic_scan_from_h(freqs_hz, H)
    range_m, prof = compute_range_profiles(scan, padding_factor=padding_factor, window=window)
    p_col = np.abs(prof[:, 0])
    return range_m, p_col


# ---------------------------------------------------------------------------
# Figure generation
# ---------------------------------------------------------------------------

def plot_h_comparison(
    freqs_hz: np.ndarray,
    variants: dict[str, np.ndarray],
    tag: str,
    out_path: Path,
) -> None:
    """Generate H(f) magnitude/phase comparison figure."""
    freqs_mhz = freqs_hz / 1e6
    keys_to_plot = ["raw", "dc_removed", "smoothed"]
    labels = {
        "raw":        "Raw H(f)",
        "dc_removed": "DC-removed H(f)",
        "smoothed":   "Smoothed |H(f)|",
    }
    colors = {
        "raw":        "steelblue",
        "dc_removed": "darkorange",
        "smoothed":   "forestgreen",
    }

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 8), sharex=True)

    for key in keys_to_plot:
        H = variants[key]
        mag_db = 20.0 * np.log10(np.abs(H) + 1e-12)
        ax1.plot(freqs_mhz, mag_db, color=colors[key], linewidth=1.2,
                 label=labels[key], alpha=0.85)

    ax1.set_ylabel("|H(f)| [dB]")
    ax1.set_title(
        f"RX-Only SFCW Post-Processing -- H(f) Comparison ({tag})\n"
        "NOTE: H(f) = noise, NOT a radar transfer function"
    )
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    # Phase of raw only
    ax2.plot(freqs_mhz, np.angle(variants["raw"], deg=True),
             color="steelblue", linewidth=1.0, alpha=0.8, label="Raw phase")
    ax2.set_ylabel("Phase [deg]")
    ax2.set_xlabel("Frequency [MHz]")
    ax2.set_ylim(-185, 185)
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path.name}")


def plot_range_comparison(
    freqs_hz: np.ndarray,
    variants: dict[str, np.ndarray],
    tag: str,
    out_path: Path,
) -> dict[str, dict]:
    """
    Generate range profile comparison figure.

    Returns a dict of summarize_range_profile outputs keyed by variant name.
    """
    keys_to_plot = ["raw", "dc_removed", "dc_removed_normalized"]
    labels = {
        "raw":                   "Raw H(f)",
        "dc_removed":            "DC-removed",
        "dc_removed_normalized": "DC-removed + normalized",
    }
    colors = {
        "raw":                   "steelblue",
        "dc_removed":            "darkorange",
        "dc_removed_normalized": "forestgreen",
    }
    summaries: dict[str, dict] = {}

    fig, ax = plt.subplots(figsize=(13, 6))
    for key in keys_to_plot:
        range_m, p = compute_profile_for_H(freqs_hz, variants[key])
        p_db = 20.0 * np.log10(p + 1e-12)
        ax.plot(range_m, p_db, color=colors[key], linewidth=1.2,
                label=labels[key], alpha=0.85)
        summaries[key] = summarize_range_profile(range_m, p)

    ax.set_xlabel("One-way range [m]")
    ax.set_ylabel("Amplitude [dB]")
    ax.set_title(
        f"RX-Only SFCW Post-Processing -- Range Profile Comparison ({tag})\n"
        "NOTE: Profiles show noise IFFT -- no coherent target -- pipeline validation only"
    )
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, 30.0)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"  Saved: {out_path.name}")
    return summaries


# ---------------------------------------------------------------------------
# Peak table
# ---------------------------------------------------------------------------

def write_peak_table(
    freqs_hz: np.ndarray,
    H_raw: np.ndarray,
    tag: str,
    out_path: Path,
) -> None:
    """Write a Markdown table of prominent range bins from DC-removed H(f)."""
    H_dc = remove_dc_component(H_raw)
    range_m, p = compute_profile_for_H(freqs_hz, H_dc)
    bins = find_prominent_range_bins(range_m, p, min_prominence_db=6.0)

    lines = [
        f"# Prominent Range Bins -- {tag}",
        "",
        "> **IMPORTANT:** These are noise-floor features in an RX-only IFFT profile.",
        "> They are NOT physical radar targets.  No RF was transmitted.",
        "> Prominence threshold: +6 dB above median noise floor.",
        "",
        f"| Bin index | Range [m] | |Profile| [dB] | Prominence [dB] |",
        f"|-----------|-----------|---------------|-----------------|",
    ]

    noise_db = estimate_noise_floor_db(p)
    if len(bins) == 0:
        lines.append("| — | — | — | (no prominent bins at +6 dB threshold) |")
    else:
        for idx in bins[:20]:    # limit table to 20 rows
            r    = float(range_m[idx])
            mag  = float(np.abs(p[idx]))
            mdb  = float(20.0 * np.log10(mag + 1e-12))
            prom = mdb - noise_db
            lines.append(f"| {idx} | {r:.3f} | {mdb:.1f} | {prom:.1f} |")
        if len(bins) > 20:
            lines.append(f"| ... | ... | ... | ({len(bins)-20} more bins omitted) |")

    lines += ["", f"Noise floor (median): {noise_db:.1f} dB", ""]
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Saved: {out_path.name}")


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def write_postprocess_summary(
    tag: str,
    data_source: str,
    metadata: dict,
    sweep_summary: dict,
    variants: dict[str, np.ndarray],
    profile_summaries: dict[str, dict],
    freqs_hz: np.ndarray,
    out_path: Path,
) -> None:
    """Write Markdown summary of postprocessing results."""
    metrics_raw = compute_sweep_metrics(freqs_hz, variants["raw"])

    lines = [
        "# RX-Only SFCW Post-Processing Summary",
        "",
        "## Scientific honesty statement",
        "",
        "> **IMPORTANT**",
        "> - No RF was transmitted in this session.",
        "> - H(f) = coherent mean of environmental RF / thermal noise at each frequency.",
        "> - H(f) is NOT a radar transfer function from an emitted signal.",
        "> - Range profiles are IFFT of noise data: NOT object detection.",
        "> - This is NOT SAR imaging, NOT dielectric characterization,",
        ">   NOT a phantom measurement, NOT a medical or clinical test.",
        "",
        "## Data source",
        f"- Tag: {tag}",
        f"- Source: {data_source}",
        f"- Timestamp: {metadata.get('timestamp', 'n/a')}",
        f"- Mode: {metadata.get('mode', 'n/a')}",
        f"- Captured: {sweep_summary.get('n_captured', 'n/a')} / "
        f"{metadata.get('n_freqs', 'n/a')} frequencies",
        f"- Failures: {sweep_summary.get('n_failed', 'n/a')}",
        f"- Clipped: {sweep_summary.get('n_clipped', 'n/a')}",
        "",
        "## Sweep parameters",
        f"- Frequency range: {freqs_hz[0]/1e9:.3f} -- {freqs_hz[-1]/1e9:.3f} GHz",
        f"- Step: {metrics_raw['step_mhz']:.1f} MHz",
        f"- N frequencies: {metrics_raw['n_freqs']}",
        f"- Bandwidth: {metrics_raw['bandwidth_mhz']:.1f} MHz",
        f"- Range resolution: {metrics_raw['range_resolution_cm']:.1f} cm "
        f"({metrics_raw['range_resolution_m']:.2f} m)",
        f"- Unambiguous range: {metrics_raw['unambiguous_range_m']:.1f} m",
        "",
        "## H(f) statistics",
        f"- Raw H(f) dynamic range: {metrics_raw['dynamic_range_db']:.1f} dB",
        f"- Peak |H(f)| bin: {metrics_raw['peak_freq_mhz']:.1f} MHz "
        f"({metrics_raw['peak_magnitude_db']:.1f} dB)",
        "",
        "## Range profile summaries",
        "",
        "| Variant | Peak range [m] | Peak [dB] | Noise floor [dB] | Dynamic range [dB] |",
        "|---------|---------------|-----------|------------------|--------------------|",
    ]

    variant_labels = {
        "raw":                   "Raw H(f)",
        "dc_removed":            "DC-removed",
        "dc_removed_normalized": "DC-removed + norm.",
    }
    for key, label in variant_labels.items():
        if key in profile_summaries:
            s = profile_summaries[key]
            lines.append(
                f"| {label} | {s['peak_range_m']:.3f} | "
                f"{s['peak_magnitude_db']:.1f} | "
                f"{s['noise_floor_db']:.1f} | "
                f"{s['dynamic_range_db']:.1f} |"
            )

    lines += [
        "",
        "## Post-processing applied",
        "1. `remove_dc_component(H)` -- subtract mean; eliminates 0-range IFFT spike.",
        "2. `normalize_h_magnitude(H)` -- scale to max|H|=1; shape comparison.",
        "3. `smooth_h_magnitude(H, 5)` -- boxcar smoothing for amplitude visualization.",
        "4. `find_prominent_range_bins(...)` -- detect noise bins >+6 dB above floor.",
        "5. `summarize_range_profile(...)` -- statistics for each variant.",
        "",
        "## Figures generated",
        "- `reports/generated/rx_sfcw_postprocess_h_comparison.png`",
        "- `reports/generated/rx_sfcw_postprocess_range_comparison.png`",
        "- `reports/generated/rx_sfcw_postprocess_peak_table.md`",
        "",
        "## Interpretation",
        "- DC removal shifts the range profile peak away from 0 m.",
        "- Normalization allows shape comparison regardless of gain.",
        "- Smoothing reduces amplitude speckle in the H(f) plot.",
        "- No range bin can be attributed to a physical object: no TX was used.",
        "- Pipeline is validated end-to-end from H(f) loading to range profile plot.",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Saved: {out_path.name}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("\n" + "=" * 64)
    print("  RX-ONLY SFCW POST-PROCESSING ANALYSIS")
    print("  No hardware.  No RF.  No TX.  Pipeline validation only.")
    print("=" * 64)

    # --- Discover data -------------------------------------------------------
    capture_dir, mode = find_latest_capture_dir()

    if capture_dir is not None:
        print(f"\n[DATA] Found {mode} sweep data: {capture_dir}")
        freqs_hz, H_raw, metadata, sweep_summary = load_sweep_data(capture_dir)
        data_source = str(capture_dir)
        tag = mode
        print(f"  freqs_hz: shape={freqs_hz.shape}, "
              f"{freqs_hz[0]/1e9:.3f}--{freqs_hz[-1]/1e9:.3f} GHz")
        print(f"  H_raw: shape={H_raw.shape}, dtype={H_raw.dtype}")
    else:
        print("\n[DATA] No local capture data found under data/raw/rx_sfcw_sweep/")
        print("       Generating synthetic noise data for pipeline demonstration.")
        print("       (Real data is not committed; run the hardware sweep to generate it.)")
        freqs_hz, H_raw, metadata, sweep_summary = make_synthetic_data()
        data_source = "SYNTHETIC (no real data on disk)"
        tag = "synthetic"
        print(f"  freqs_hz: shape={freqs_hz.shape}")
        print(f"  H_raw: shape={H_raw.shape} [SYNTHETIC NOISE]")

    # --- Compute postprocessing variants ------------------------------------
    print("\n[POST] Computing H(f) variants...")
    variants = compute_postprocess_variants(freqs_hz, H_raw)
    print(f"  Variants: {list(variants.keys())}")

    # --- Figures and tables ------------------------------------------------
    print("\n[PLOT] Generating figures and tables...")

    plot_h_comparison(
        freqs_hz, variants, tag,
        REPORTS_DIR / "rx_sfcw_postprocess_h_comparison.png",
    )

    profile_summaries = plot_range_comparison(
        freqs_hz, variants, tag,
        REPORTS_DIR / "rx_sfcw_postprocess_range_comparison.png",
    )

    write_peak_table(
        freqs_hz, H_raw, tag,
        REPORTS_DIR / "rx_sfcw_postprocess_peak_table.md",
    )

    write_postprocess_summary(
        tag, data_source, metadata, sweep_summary,
        variants, profile_summaries, freqs_hz,
        REPORTS_DIR / "rx_sfcw_postprocess_summary.md",
    )

    # --- Console summary ---------------------------------------------------
    print("\n" + "=" * 64)
    print("  RESULTS")
    print("=" * 64)
    print(f"  Data source: {data_source[:60]}")
    print(f"  N frequencies: {len(freqs_hz)}")
    print(f"  BW: {(freqs_hz[-1]-freqs_hz[0])/1e6:.0f} MHz")

    for key in ("raw", "dc_removed", "dc_removed_normalized"):
        if key in profile_summaries:
            s = profile_summaries[key]
            print(f"  [{key:22s}] peak={s['peak_range_m']:.3f} m  "
                  f"dyn={s['dynamic_range_db']:.1f} dB  "
                  f"noise={s['noise_floor_db']:.1f} dB")

    print()
    print("  INTERPRETATION:")
    print("  H(f) = RX noise -- NOT a radar transfer function.")
    print("  Range profiles = pipeline validation -- NOT object detection.")
    print("  No TX used.  No RF transmitted.  No physical targets present.")
    print("=" * 64)

    return 0


if __name__ == "__main__":
    sys.exit(main())
