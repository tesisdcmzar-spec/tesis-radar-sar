"""
Offline analysis of legacy bladeRF captures from legacy/capturas_barrido/.

This script is hardware-free: it reads .npy files that already exist on disk,
converts them to a SyntheticScan via load_capture(), computes frequency-domain
and range-domain characterisations, and writes figures + a markdown summary to
reports/generated/.

Run from repo root:
    py experiments/run_legacy_offline_analysis.py

No bladeRF, no motors, no RF transmission, no hardware of any kind required.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow import from repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import matplotlib
matplotlib.use("Agg")   # headless — no display required
import matplotlib.pyplot as plt

from acquisition.load_sfcw_capture import load_capture
from processing.range_profile import compute_range_profiles

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
LEGACY_DIR = REPO_ROOT / "legacy" / "capturas_barrido"
OUT_DIR = REPO_ROOT / "reports" / "generated"

OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Public helpers (importable for testing)
# ---------------------------------------------------------------------------

def compute_sfcw_performance(freqs_hz: np.ndarray, c: float = 3e8) -> dict:
    """Return theoretical SFCW performance figures for a given frequency grid."""
    bw = freqs_hz[-1] - freqs_hz[0]
    f_step = float(np.mean(np.diff(freqs_hz)))
    return {
        "bw_hz": bw,
        "f_step_hz": f_step,
        "range_res_m": c / (2.0 * bw),
        "unamb_range_m": c / (2.0 * f_step),
    }


def profile_peak_range_m(range_m: np.ndarray, profile_abs: np.ndarray) -> float:
    """Return the range [m] of the maximum in profile_abs."""
    return float(range_m[np.argmax(profile_abs)])


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def main() -> None:
    print("Loading legacy captures ...")
    # Format C: cfg is unused for directory loads; frequencies inferred from filenames.
    scan = load_capture(LEGACY_DIR, cfg={}, azimuth_position_m=0.0)

    N_f = len(scan.freqs_hz)
    freqs_mhz = scan.freqs_hz / 1e6
    H = scan.H[:, 0]   # (N_f,) complex – single aperture position

    perf = compute_sfcw_performance(scan.freqs_hz)
    bw_mhz = perf["bw_hz"] / 1e6
    f_step_mhz = perf["f_step_hz"] / 1e6
    range_res_cm = perf["range_res_m"] * 100
    unamb_range_m = perf["unamb_range_m"]

    print(f"  N_f            = {N_f}")
    print(f"  Freq range     = {freqs_mhz[0]:.0f} – {freqs_mhz[-1]:.0f} MHz")
    print(f"  Bandwidth      = {bw_mhz:.0f} MHz")
    print(f"  Range res      ~ {range_res_cm:.2f} cm  (rectangular window)")
    print(f"  Unamb. range   ~ {unamb_range_m:.2f} m")
    print(f"  Azimuth pos.   = {scan.x_az_m} m  (single position)")

    # -----------------------------------------------------------------------
    # Figure 1 — Frequency response: magnitude and phase
    # -----------------------------------------------------------------------
    print("Generating frequency response figure ...")
    mag_db = 20.0 * np.log10(np.abs(H) + 1e-20)
    phase_deg = np.angle(H, deg=True)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)

    ax1.plot(freqs_mhz, mag_db, linewidth=0.8, color="steelblue")
    ax1.set_ylabel("Magnitude [dB]")
    ax1.set_title(
        f"Legacy bladeRF — H(f) frequency response\n"
        f"{N_f} steps, {freqs_mhz[0]:.0f}–{freqs_mhz[-1]:.0f} MHz, "
        f"{f_step_mhz:.0f} MHz step, single aperture"
    )
    ax1.grid(True, alpha=0.3)

    ax2.plot(freqs_mhz, phase_deg, linewidth=0.8, color="darkorange")
    ax2.set_xlabel("Frequency [MHz]")
    ax2.set_ylabel("Phase [deg]")
    ax2.set_ylim(-185, 185)
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    _save(fig, OUT_DIR / "legacy_frequency_response.png")

    # -----------------------------------------------------------------------
    # Range profiles
    # -----------------------------------------------------------------------
    print("Computing range profiles ...")
    PADDING = 8

    range_rect, profiles_rect = compute_range_profiles(
        scan, padding_factor=PADDING, window="none"
    )
    range_hann, profiles_hann = compute_range_profiles(
        scan, padding_factor=PADDING, window="hanning"
    )

    prof_rect = np.abs(profiles_rect[:, 0])
    prof_hann = np.abs(profiles_hann[:, 0])

    # Display up to unamb_range + 10 %, capped at 3 m
    x_max_cm = min(unamb_range_m * 1.1, 3.0) * 100

    # -----------------------------------------------------------------------
    # Figure 2 — Rectangular window
    # -----------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(range_rect * 100, 20 * np.log10(prof_rect + 1e-20),
            linewidth=0.9, color="steelblue")
    ax.axvline(unamb_range_m * 100, color="red", linestyle="--", linewidth=0.8,
               label=f"Unamb. range = {unamb_range_m*100:.0f} cm")
    ax.set_xlabel("One-way range [cm]")
    ax.set_ylabel("Amplitude [dB]")
    ax.set_title(
        "Range Profile — Rectangular window\n"
        "(single aperture, legacy bladeRF, no calibration)"
    )
    ax.set_xlim(0, x_max_cm)
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    _save(fig, OUT_DIR / "legacy_range_profile_rectangular.png")

    # -----------------------------------------------------------------------
    # Figure 3 — Hanning window
    # -----------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(range_hann * 100, 20 * np.log10(prof_hann + 1e-20),
            linewidth=0.9, color="darkorange")
    ax.axvline(unamb_range_m * 100, color="red", linestyle="--", linewidth=0.8,
               label=f"Unamb. range = {unamb_range_m*100:.0f} cm")
    ax.set_xlabel("One-way range [cm]")
    ax.set_ylabel("Amplitude [dB]")
    ax.set_title(
        "Range Profile — Hanning window\n"
        "(single aperture, legacy bladeRF, no calibration)"
    )
    ax.set_xlim(0, x_max_cm)
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    _save(fig, OUT_DIR / "legacy_range_profile_hanning.png")

    # -----------------------------------------------------------------------
    # Figure 4 — Side-by-side comparison
    # -----------------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 4))
    ax1.plot(range_rect * 100, 20 * np.log10(prof_rect + 1e-20),
             linewidth=0.9, color="steelblue")
    ax1.axvline(unamb_range_m * 100, color="red", linestyle="--", linewidth=0.8,
                label=f"Unamb. range")
    ax1.set_xlabel("One-way range [cm]")
    ax1.set_ylabel("Amplitude [dB]")
    ax1.set_title("Rectangular window")
    ax1.set_xlim(0, x_max_cm)
    ax1.legend(fontsize=8)
    ax1.grid(True, alpha=0.3)

    ax2.plot(range_hann * 100, 20 * np.log10(prof_hann + 1e-20),
             linewidth=0.9, color="darkorange")
    ax2.axvline(unamb_range_m * 100, color="red", linestyle="--", linewidth=0.8,
                label=f"Unamb. range")
    ax2.set_xlabel("One-way range [cm]")
    ax2.set_title("Hanning window")
    ax2.set_xlim(0, x_max_cm)
    ax2.legend(fontsize=8)
    ax2.grid(True, alpha=0.3)

    fig.suptitle(
        f"Range Profile Comparison — legacy bladeRF "
        f"({freqs_mhz[0]:.0f}–{freqs_mhz[-1]:.0f} MHz, {f_step_mhz:.0f} MHz step)\n"
        "Single aperture — no SAR focussing possible",
        fontsize=10,
    )
    plt.tight_layout()
    _save(fig, OUT_DIR / "legacy_range_profile_comparison.png")

    # -----------------------------------------------------------------------
    # Markdown summary
    # -----------------------------------------------------------------------
    print("Writing offline summary ...")
    mag = np.abs(H)
    mag_db_arr = 20 * np.log10(mag + 1e-20)
    peak_rect_cm = profile_peak_range_m(range_rect, prof_rect) * 100
    peak_hann_cm = profile_peak_range_m(range_hann, prof_hann) * 100

    summary = f"""\
# Legacy Offline Analysis Summary

**Generated by:** `experiments/run_legacy_offline_analysis.py`
**Data source:** `legacy/capturas_barrido/` ({N_f} files)
**Hardware used:** None — offline analysis only.

---

## Capture metadata

| Parameter | Value |
|-----------|-------|
| Number of frequency steps | {N_f} |
| First frequency | {freqs_mhz[0]:.0f} MHz |
| Last frequency | {freqs_mhz[-1]:.0f} MHz |
| Frequency step | {f_step_mhz:.0f} MHz |
| Bandwidth | {bw_mhz:.0f} MHz |
| Samples per step | 40 000 |
| Sample dtype | complex128 |
| Azimuth positions | 1 (single static aperture) |

## Theoretical SFCW performance

| Metric | Value |
|--------|-------|
| Range resolution (rectangular) | {range_res_cm:.2f} cm |
| Unambiguous range | {unamb_range_m:.2f} m |

## Frequency response statistics

| Stat | Value |
|------|-------|
| Magnitude min | {mag_db_arr.min():.1f} dB |
| Magnitude max | {mag_db_arr.max():.1f} dB |
| Magnitude span | {mag_db_arr.max() - mag_db_arr.min():.1f} dB |
| Phase range | {phase_deg.min():.0f}° to {phase_deg.max():.0f}° |

## Range profile peak positions

| Window | Peak range |
|--------|-----------|
| Rectangular | {peak_rect_cm:.1f} cm |
| Hanning | {peak_hann_cm:.1f} cm |

**Interpretation note:** Without background subtraction, calibration, and a known
target at a controlled geometry, range profile peaks may correspond to system
internal reflections (leakage between TX and RX), reflections from the measurement
setup, or noise maxima — not to a resolved target. No target detection or object
identification is claimed.

## Scientific limitations

1. **Single aperture position.** Only a 1D frequency-to-range transform is possible.
   SAR backprojection requires H(f, x_az) with N_az ≥ 2 independent coherent
   aperture positions. The legacy data has N_az = 1; no SAR image is achievable.

2. **No calibration.** The frequency response H(f) includes contributions from the
   RF chain (cable loss, connector mismatch, bladeRF frequency-dependent gain) and
   cannot be separated from any environmental reflection without a reference measurement.

3. **No background subtraction.** Without a reference measurement of the empty scene,
   static clutter cannot be removed.

4. **Unknown acquisition scenario.** Target type, distance, and orientation are not
   documented in the capture filenames or associated metadata.

5. **No clinical claims.** This data was not acquired in a medical or controlled
   phantom experiment. No dielectric characterisation, tissue detection, or cancer
   detection is claimed.

## Generated figures

All figures are in `reports/generated/` (gitignored — regenerate with the script).

| File | Contents |
|------|----------|
| `legacy_frequency_response.png` | H(f) magnitude [dB] and phase vs frequency |
| `legacy_range_profile_rectangular.png` | IFFT range profile, rectangular window |
| `legacy_range_profile_hanning.png` | IFFT range profile, Hanning window |
| `legacy_range_profile_comparison.png` | Side-by-side window comparison |

## Regeneration

```
py experiments/run_legacy_offline_analysis.py
```

## Next phase

Real hardware acquisition requires:
1. `hardware/bladerf_device.py` — safe bladeRF abstraction with TX/RX guard.
2. A hardware scan script with azimuth motion and coherent SFCW sweep, saving Format A.
3. Background subtraction (`processing/background_subtraction.py`) before range profiling.
4. Explicit **`CONFIRM HARDWARE RUN`** gate before any RF transmission or motor motion.
"""

    (OUT_DIR / "legacy_offline_summary.md").write_text(summary, encoding="utf-8")
    print(f"  Saved -> {OUT_DIR / 'legacy_offline_summary.md'}")

    print()
    print("All outputs written to:", OUT_DIR)
    print("Done.")


def _save(fig: "plt.Figure", path: Path) -> None:
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved -> {path}")


if __name__ == "__main__":
    main()
