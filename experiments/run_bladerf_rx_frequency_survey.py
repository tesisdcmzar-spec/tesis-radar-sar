"""
Supervised RX-only bladeRF frequency survey.

SAFETY CONTRACT
---------------
- RX ONLY.  No TX.  No configure_tx().  No transmit_tone().
- No motor movement.  No azimuth stage.
- No human subject.  No phantom.
- Not a SAR scan.  Not a medical test.  No clinical claims.
- Not dielectric characterization.
- Confirmation phrase: 'CONFIRM HARDWARE RUN' (hard-coded).
- Each capture: 100 000 samples (~10 ms at 10 MS/s).
- Seven frequencies swept sequentially; script runs once and exits.

PURPOSE: characterize bladeRF RX behavior and local RF environment
across frequency — receiver diagnostic only, not radar.

PRE-FLIGHT CHECKLIST
---------------------
1. User is physically present.
2. bladeRF is connected by USB.
3. RX1 has an antenna or 50-ohm load connected.
4. TX1 is not used.
5. No human subject is being tested.
6. No motor or moving stage will be used.
7. This session is RX-only.
8. Confirmation phrase is exactly 'CONFIRM HARDWARE RUN'.
"""
from __future__ import annotations

import json
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# --- path setup -----------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hardware.bladerf_device import BladeRFConfig, BladeRFDevice  # noqa: E402

# --------------------------------------------------------------------------
# Survey parameters
# --------------------------------------------------------------------------

CONFIRMATION   = "CONFIRM HARDWARE RUN"
SAMPLE_RATE_HZ = 10e6
BANDWIDTH_HZ   = 10e6
RX_GAIN_DB     = 20.0
TX_GAIN_DB     = -20.0   # conservative; TX not used
N_SAMPLES      = 100_000  # ~10 ms per burst

SURVEY_FREQUENCIES_HZ: list[float] = [
    900e6,
    1200e6,
    1800e6,
    2400e6,
    3000e6,
    4000e6,
    5000e6,
]

REPORTS_DIR = REPO_ROOT / "reports" / "generated"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

TS = datetime.now().strftime("%Y%m%d_%H%M%S")
CAPTURE_DIR = REPO_ROOT / "data" / "raw" / "rx_frequency_survey" / TS
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Data structures
# --------------------------------------------------------------------------

@dataclass
class FreqResult:
    freq_hz: float
    success: bool
    iq: Optional[np.ndarray] = None
    error_msg: Optional[str] = None
    mean_amp: float = 0.0
    rms_amp: float = 0.0
    max_amp: float = 0.0
    clip_ratio: float = 0.0
    dc_mag: float = 0.0
    peak_offset_hz: float = 0.0
    peak_db: float = 0.0
    classification: str = ""


# --------------------------------------------------------------------------
# Pre-flight
# --------------------------------------------------------------------------

def print_preflight() -> None:
    lines = [
        "",
        "+------------------------------------------------------------------+",
        "|       SUPERVISED RX-ONLY bladeRF FREQUENCY SURVEY               |",
        "|       Pre-flight checklist                                       |",
        "+------------------------------------------------------------------+",
        "|  [1] User is physically present                                  |",
        "|  [2] bladeRF connected via USB                                   |",
        "|  [3] RX1 has antenna or 50-ohm load                              |",
        "|  [4] TX1 is NOT used                                             |",
        "|  [5] No human subject being tested                               |",
        "|  [6] No motor or moving stage                                    |",
        "|  [7] RX-ONLY session                                             |",
        "|  [8] Confirmation phrase: CONFIRM HARDWARE RUN                   |",
        "+------------------------------------------------------------------+",
        "",
    ]
    print("\n".join(lines))


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------

def analyze_iq(iq: np.ndarray, sample_rate_hz: float) -> dict:
    amp = np.abs(iq)
    mean_amp   = float(np.mean(amp))
    rms_amp    = float(np.sqrt(np.mean(amp**2)))
    max_amp    = float(np.max(amp))
    clip_ratio = float(np.mean(amp >= 0.99))
    dc_i       = float(np.mean(iq.real))
    dc_q       = float(np.mean(iq.imag))
    dc_mag     = float(np.abs(complex(dc_i, dc_q)))

    n = len(iq)
    freqs_hz = np.fft.fftfreq(n, d=1.0 / sample_rate_hz)
    mag      = np.abs(np.fft.fft(iq)) / n
    mag_db   = 20.0 * np.log10(mag + 1e-12)
    peak_bin = int(np.argmax(mag_db))
    peak_offset_hz = float(freqs_hz[peak_bin])
    peak_db        = float(mag_db[peak_bin])

    return {
        "n_samples":       n,
        "dtype":           str(iq.dtype),
        "mean_amp":        mean_amp,
        "rms_amp":         rms_amp,
        "max_amp":         max_amp,
        "clip_ratio":      clip_ratio,
        "dc_i":            dc_i,
        "dc_q":            dc_q,
        "dc_mag":          dc_mag,
        "peak_offset_hz":  peak_offset_hz,
        "peak_db":         peak_db,
    }


def classify_capture(
    mean_amp: float,
    clip_ratio: float,
    dc_mag: float,
    peak_offset_hz: float,
    peak_db: float,
) -> str:
    if clip_ratio > 0.01:
        return "CLIPPED"
    if mean_amp < 5e-4:
        return "very-low (possible open port or disconnected antenna)"
    if dc_mag > 0.10:
        return "DC-dominated"
    if abs(peak_offset_hz) > 1e3 and peak_db > -50.0:
        return "interference-peak"
    return "noise-like"


# --------------------------------------------------------------------------
# Plots
# --------------------------------------------------------------------------

def plot_noise_floor(results: list[FreqResult], out_path: Path) -> None:
    freqs_mhz = [r.freq_hz / 1e6 for r in results if r.success]
    rms_vals  = [r.rms_amp for r in results if r.success]
    if not freqs_mhz:
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar([f"{f:.0f}" for f in freqs_mhz], rms_vals, color="steelblue", edgecolor="navy")
    ax.set_xlabel("Center frequency [MHz]")
    ax.set_ylabel("RMS amplitude (normalized)")
    ax.set_title("RX noise floor vs frequency")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_dc_offset(results: list[FreqResult], out_path: Path) -> None:
    freqs_mhz = [r.freq_hz / 1e6 for r in results if r.success]
    dc_vals   = [r.dc_mag for r in results if r.success]
    if not freqs_mhz:
        return
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar([f"{f:.0f}" for f in freqs_mhz], dc_vals, color="darkorange", edgecolor="saddlebrown")
    ax.set_xlabel("Center frequency [MHz]")
    ax.set_ylabel("DC offset magnitude (normalized)")
    ax.set_title("RX DC offset vs frequency")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_peak_bins(results: list[FreqResult], out_path: Path) -> None:
    freqs_mhz  = [r.freq_hz / 1e6 for r in results if r.success]
    peaks_db   = [r.peak_db for r in results if r.success]
    offsets_khz = [r.peak_offset_hz / 1e3 for r in results if r.success]
    if not freqs_mhz:
        return
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    x_labels = [f"{f:.0f}" for f in freqs_mhz]
    ax1.bar(x_labels, peaks_db, color="seagreen", edgecolor="darkgreen")
    ax1.set_ylabel("Peak FFT magnitude [dB]")
    ax1.set_title("Strongest spectral bin vs frequency")
    ax1.grid(axis="y", alpha=0.3)
    ax2.bar(x_labels, offsets_khz, color="mediumpurple", edgecolor="indigo")
    ax2.set_xlabel("Center frequency [MHz]")
    ax2.set_ylabel("Peak bin offset from center [kHz]")
    ax2.axhline(0, color="gray", linewidth=0.8, linestyle="--")
    ax2.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def write_summary(results: list[FreqResult], out_path: Path) -> None:
    lines = [
        "# bladeRF RX Frequency Survey -- Summary",
        "",
        f"**Timestamp:** {TS}",
        f"**Sample rate:** {SAMPLE_RATE_HZ/1e6:.1f} MS/s",
        f"**Bandwidth:** {BANDWIDTH_HZ/1e6:.1f} MHz",
        f"**RX gain:** {RX_GAIN_DB:.1f} dB",
        f"**N samples per burst:** {N_SAMPLES:,}",
        f"**dry_run:** False",
        "",
        "## Per-frequency results",
        "",
        "| Freq (MHz) | Status | Mean amp | RMS | Max | Clip% | DC mag | Peak offset (kHz) | Peak (dB) | Class |",
        "|------------|--------|----------|-----|-----|-------|--------|-------------------|-----------|-------|",
    ]
    for r in results:
        if r.success:
            lines.append(
                f"| {r.freq_hz/1e6:.0f} | OK "
                f"| {r.mean_amp:.5f} | {r.rms_amp:.5f} | {r.max_amp:.5f} "
                f"| {r.clip_ratio*100:.4f} | {r.dc_mag:.5f} "
                f"| {r.peak_offset_hz/1e3:+.2f} | {r.peak_db:.1f} "
                f"| {r.classification} |"
            )
        else:
            lines.append(f"| {r.freq_hz/1e6:.0f} | FAILED | — | — | — | — | — | — | — | — |")
    lines += [
        "",
        "## Safety attestation",
        "- RX-only survey. No TX enabled.",
        "- No RF transmitted.",
        "- No motor movement.",
        "- No human subject.",
        "- Not a SAR scan. Not a medical test.",
        "- Not dielectric characterization.",
        "- This survey only characterizes RX behavior and local RF environment.",
    ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    print_preflight()

    print(f"Survey: {len(SURVEY_FREQUENCIES_HZ)} frequencies, "
          f"{N_SAMPLES:,} samples each (~{N_SAMPLES/SAMPLE_RATE_HZ*1e3:.0f} ms per burst)")
    print(f"Output: {CAPTURE_DIR}")
    print()

    results: list[FreqResult] = []
    device: BladeRFDevice | None = None

    for idx, freq_hz in enumerate(SURVEY_FREQUENCIES_HZ):
        freq_mhz = freq_hz / 1e6
        print(f"[{idx+1}/{len(SURVEY_FREQUENCIES_HZ)}] {freq_mhz:.0f} MHz ...", end=" ", flush=True)

        config = BladeRFConfig(
            center_freq_hz=freq_hz,
            sample_rate_hz=SAMPLE_RATE_HZ,
            bandwidth_hz=BANDWIDTH_HZ,
            rx_gain_db=RX_GAIN_DB,
            tx_gain_db=TX_GAIN_DB,
            n_samples=N_SAMPLES,
            dry_run=False,
        )
        result = FreqResult(freq_hz=freq_hz, success=False)

        try:
            device = BladeRFDevice(config, confirmation=CONFIRMATION)
            device.configure_rx()
            iq = device.capture_rx()
            device.close()
            device = None

            stats = analyze_iq(iq, SAMPLE_RATE_HZ)
            result.iq        = iq
            result.mean_amp  = stats["mean_amp"]
            result.rms_amp   = stats["rms_amp"]
            result.max_amp   = stats["max_amp"]
            result.clip_ratio = stats["clip_ratio"]
            result.dc_mag    = stats["dc_mag"]
            result.peak_offset_hz = stats["peak_offset_hz"]
            result.peak_db   = stats["peak_db"]
            result.classification = classify_capture(
                result.mean_amp, result.clip_ratio,
                result.dc_mag, result.peak_offset_hz, result.peak_db,
            )
            result.success = True

            print(f"OK  rms={result.rms_amp:.4f}  dc={result.dc_mag:.4f}  "
                  f"peak={result.peak_db:.1f} dB @ {result.peak_offset_hz/1e3:+.1f} kHz  "
                  f"[{result.classification}]")

        except Exception:
            err = traceback.format_exc()
            result.error_msg = err
            print(f"FAILED\n{err}")
            if device is not None:
                try:
                    device.close()
                except Exception:
                    pass
                device = None

        results.append(result)

    # --- Save IQ data -------------------------------------------------------
    print("\n[Saving IQ data]")
    saved_npy: list[str] = []
    for r in results:
        if r.success and r.iq is not None:
            fname = f"rx_{r.freq_hz/1e6:.0f}MHz.npy"
            np.save(CAPTURE_DIR / fname, r.iq)
            saved_npy.append(fname)
            print(f"  {fname}")

    # Metadata
    metadata = {
        "timestamp": TS,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "bandwidth_hz": BANDWIDTH_HZ,
        "rx_gain_db": RX_GAIN_DB,
        "n_samples": N_SAMPLES,
        "dry_run": False,
        "rx_only": True,
        "tx_enabled": False,
        "motors": False,
        "human_subject": False,
        "confirmation_phrase": CONFIRMATION,
        "frequencies_hz": SURVEY_FREQUENCIES_HZ,
        "results": [
            {
                "freq_hz": r.freq_hz,
                "success": r.success,
                "mean_amp": r.mean_amp if r.success else None,
                "rms_amp": r.rms_amp if r.success else None,
                "max_amp": r.max_amp if r.success else None,
                "clip_ratio": r.clip_ratio if r.success else None,
                "dc_mag": r.dc_mag if r.success else None,
                "peak_offset_hz": r.peak_offset_hz if r.success else None,
                "peak_db": r.peak_db if r.success else None,
                "classification": r.classification if r.success else None,
                "error": r.error_msg if not r.success else None,
            }
            for r in results
        ],
    }
    meta_path = CAPTURE_DIR / "metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"  metadata.json")

    # --- Plots ---------------------------------------------------------------
    print("\n[Generating plots]")

    p1 = REPORTS_DIR / "bladerf_rx_frequency_survey_noise_floor.png"
    plot_noise_floor(results, p1)
    print(f"  {p1.name}")

    p2 = REPORTS_DIR / "bladerf_rx_frequency_survey_dc_offset.png"
    plot_dc_offset(results, p2)
    print(f"  {p2.name}")

    p3 = REPORTS_DIR / "bladerf_rx_frequency_survey_peak_bins.png"
    plot_peak_bins(results, p3)
    print(f"  {p3.name}")

    p4 = REPORTS_DIR / "bladerf_rx_frequency_survey_summary.md"
    write_summary(results, p4)
    print(f"  {p4.name}")

    # --- Console summary -----------------------------------------------------
    n_ok   = sum(1 for r in results if r.success)
    n_fail = len(results) - n_ok
    print(f"\n{'='*60}")
    print(f"FREQUENCY SURVEY COMPLETE:  {n_ok}/{len(results)} captures successful")
    if n_fail:
        print(f"  {n_fail} failed -- see output above")
    print(f"{'='*60}")
    print(f"{'Freq (MHz)':<12} {'RMS':>8} {'DC':>8} {'Peak (dB)':>10} {'Class'}")
    print("-" * 60)
    for r in results:
        if r.success:
            print(f"  {r.freq_hz/1e6:<10.0f} {r.rms_amp:>8.5f} {r.dc_mag:>8.5f} "
                  f"{r.peak_db:>10.1f}  {r.classification}")
        else:
            print(f"  {r.freq_hz/1e6:<10.0f} {'FAILED':>8}")
    print(f"{'='*60}")
    print()
    print("INTERPRETATION")
    print("-" * 60)
    print("  This survey only characterizes RX behavior and local RF environment.")
    print("  No object detection. No SAR imaging. No TX/RX radar operation.")
    print("  No dielectric characterization. No medical claims.")
    print(f"{'='*60}")

    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
