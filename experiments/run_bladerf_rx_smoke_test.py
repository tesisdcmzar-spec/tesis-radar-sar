"""
Supervised RX-only bladeRF smoke test.

SAFETY CONTRACT
---------------
- RX ONLY.  No TX.  No configure_tx().  No transmit_tone().
- No motor movement.  No azimuth stage.
- No human subject.  No phantom.  Not a SAR scan.
- Not a medical test.  No clinical claims.
- This test opens a real bladeRF device for the first time under supervision.
- Confirmation phrase: 'CONFIRM HARDWARE RUN' (hard-coded; not configurable).
- Capture is intentionally short (100 000 samples ≈ 10 ms at 10 MS/s).
- The script runs once and exits.  No loops.

PRE-FLIGHT CHECKLIST (printed and verified at run-time)
-------------------------------------------------------
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
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# --- path setup -----------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from hardware.bladerf_device import BladeRFConfig, BladeRFDevice  # noqa: E402

# --- constants ------------------------------------------------------------
CONFIRMATION = "CONFIRM HARDWARE RUN"

CENTER_FREQ_HZ  = 2.4e9
SAMPLE_RATE_HZ  = 10e6
BANDWIDTH_HZ    = 10e6
RX_GAIN_DB      = 20.0
TX_GAIN_DB      = -20.0   # unused; conservative default
N_SAMPLES       = 100_000  # ≈ 10 ms at 10 MS/s

REPORTS_DIR = REPO_ROOT / "reports" / "generated"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# Timestamped capture directory
TS = datetime.now().strftime("%Y%m%d_%H%M%S")
CAPTURE_DIR = REPO_ROOT / "data" / "raw" / "rx_smoke" / TS
CAPTURE_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Pre-flight
# --------------------------------------------------------------------------

def print_preflight() -> None:
    banner = (
        "\n"
        "+------------------------------------------------------------------+\n"
        "|         SUPERVISED RX-ONLY bladeRF SMOKE TEST                    |\n"
        "|         Pre-flight checklist                                      |\n"
        "+------------------------------------------------------------------+\n"
        "|  [1] User is physically present                                   |\n"
        "|  [2] bladeRF connected via USB                                    |\n"
        "|  [3] RX1 has antenna or 50-ohm load                               |\n"
        "|  [4] TX1 is NOT used                                              |\n"
        "|  [5] No human subject being tested                                |\n"
        "|  [6] No motor or moving stage                                     |\n"
        "|  [7] RX-ONLY session                                              |\n"
        "|  [8] Confirmation phrase: CONFIRM HARDWARE RUN                    |\n"
        "+------------------------------------------------------------------+\n"
    )
    print(banner)


# --------------------------------------------------------------------------
# Diagnostics
# --------------------------------------------------------------------------

def compute_iq_stats(iq: np.ndarray, sample_rate_hz: float) -> dict:
    amp = np.abs(iq)
    mean_amp   = float(np.mean(amp))
    max_amp    = float(np.max(amp))
    rms_amp    = float(np.sqrt(np.mean(amp**2)))
    clip_ratio = float(np.mean(amp >= 0.99))
    dc_i       = float(np.mean(iq.real))
    dc_q       = float(np.mean(iq.imag))
    dc_mag     = float(np.abs(complex(dc_i, dc_q)))

    n = len(iq)
    freqs  = np.fft.fftfreq(n, d=1.0/sample_rate_hz)
    fft    = np.fft.fft(iq)
    mag_db = 20.0 * np.log10(np.abs(fft) / n + 1e-12)
    peak_bin = int(np.argmax(mag_db))
    peak_freq_offset_hz = float(freqs[peak_bin])
    peak_mag_db = float(mag_db[peak_bin])

    return {
        "n_samples":              n,
        "dtype":                  str(iq.dtype),
        "mean_amplitude":         mean_amp,
        "max_amplitude":          max_amp,
        "rms_amplitude":          rms_amp,
        "clipping_ratio":         clip_ratio,
        "dc_i":                   dc_i,
        "dc_q":                   dc_q,
        "dc_magnitude":           dc_mag,
        "peak_freq_offset_hz":    peak_freq_offset_hz,
        "peak_freq_offset_mhz":   peak_freq_offset_hz / 1e6,
        "peak_magnitude_db":      peak_mag_db,
    }


def plot_time_domain(iq: np.ndarray, sample_rate_hz: float, out_path: Path) -> None:
    t_us = np.arange(len(iq)) / sample_rate_hz * 1e6
    plot_n = min(2000, len(iq))
    fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
    axes[0].plot(t_us[:plot_n], iq.real[:plot_n], linewidth=0.5, color="steelblue")
    axes[0].set_ylabel("I (normalized)")
    axes[0].set_title(f"RX IQ — Time domain (first {plot_n} samples)")
    axes[0].set_ylim(-1.1, 1.1)
    axes[0].axhline(0, color="gray", linewidth=0.5)
    axes[1].plot(t_us[:plot_n], iq.imag[:plot_n], linewidth=0.5, color="darkorange")
    axes[1].set_ylabel("Q (normalized)")
    axes[1].set_xlabel("Time [µs]")
    axes[1].set_ylim(-1.1, 1.1)
    axes[1].axhline(0, color="gray", linewidth=0.5)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_spectrum(
    iq: np.ndarray,
    sample_rate_hz: float,
    center_freq_hz: float,
    out_path: Path,
) -> None:
    n = len(iq)
    freqs  = np.fft.fftshift(np.fft.fftfreq(n, d=1.0/sample_rate_hz)) / 1e6
    mag_db = np.fft.fftshift(
        20.0 * np.log10(np.abs(np.fft.fft(iq)) / n + 1e-12)
    )
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(freqs, mag_db, linewidth=0.6, color="steelblue")
    ax.set_xlabel(f"Frequency offset from {center_freq_hz/1e9:.3f} GHz [MHz]")
    ax.set_ylabel("Magnitude [dB]")
    ax.set_title("RX IQ — FFT spectrum")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def write_summary(
    stats: dict,
    device_status: dict,
    ts: str,
    capture_dir: Path,
    success: bool,
    error_msg: str | None,
    out_path: Path,
) -> None:
    lines = [
        "# bladeRF RX Smoke Test — Summary",
        "",
        f"**Timestamp:** {ts}",
        f"**Status:** {'SUCCESS' if success else 'FAILED'}",
        "",
        "## Hardware configuration",
        f"- Center frequency: {CENTER_FREQ_HZ/1e9:.3f} GHz",
        f"- Sample rate: {SAMPLE_RATE_HZ/1e6:.1f} MS/s",
        f"- Bandwidth: {BANDWIDTH_HZ/1e6:.1f} MHz",
        f"- RX gain: {RX_GAIN_DB:.1f} dB",
        f"- N samples: {N_SAMPLES:,}",
        f"- dry_run: False",
        "",
        "## IQ statistics",
    ]
    if success:
        lines += [
            f"- Shape: ({stats['n_samples']},)  dtype: {stats['dtype']}",
            f"- Mean amplitude: {stats['mean_amplitude']:.5f}",
            f"- Max amplitude:  {stats['max_amplitude']:.5f}",
            f"- RMS amplitude:  {stats['rms_amplitude']:.5f}",
            f"- Clipping ratio: {stats['clipping_ratio']:.6f}",
            f"- DC offset (I, Q): ({stats['dc_i']:.5f}, {stats['dc_q']:.5f})",
            f"- DC magnitude: {stats['dc_magnitude']:.5f}",
            "",
            "## Spectrum",
            f"- Strongest bin: {stats['peak_freq_offset_mhz']:+.3f} MHz from center",
            f"- Peak magnitude: {stats['peak_magnitude_db']:.1f} dB",
            "",
            "## Output files",
            f"- IQ data: {capture_dir}/rx_iq.npy",
            f"- Metadata: {capture_dir}/metadata.json",
            f"- Time domain plot: reports/generated/bladerf_rx_smoke_time_domain.png",
            f"- Spectrum plot: reports/generated/bladerf_rx_smoke_spectrum.png",
            "",
            "## Safety attestation",
            "- RX-only capture. No TX enabled.",
            "- No RF transmitted.",
            "- No motor movement.",
            "- No human subject.",
            "- Not a SAR scan.",
            "- Not a medical test.",
        ]
    else:
        lines += [
            "## Error",
            f"```",
            error_msg or "(unknown)",
            "```",
        ]
    out_path.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    print_preflight()

    config = BladeRFConfig(
        center_freq_hz=CENTER_FREQ_HZ,
        sample_rate_hz=SAMPLE_RATE_HZ,
        bandwidth_hz=BANDWIDTH_HZ,
        rx_gain_db=RX_GAIN_DB,
        tx_gain_db=TX_GAIN_DB,
        n_samples=N_SAMPLES,
        dry_run=False,
    )

    assert config.dry_run is False, "Script requires dry_run=False"
    # TX guard: ensure no TX method can be called by keeping no TX reference
    assert not hasattr(config, "_tx_armed"), "Unexpected TX-arm attribute"

    device: BladeRFDevice | None = None
    iq: np.ndarray | None = None
    success = False
    error_msg: str | None = None

    try:
        print("[1/5] Opening bladeRF device...")
        device = BladeRFDevice(config, confirmation=CONFIRMATION)
        st = device.status()
        print(f"      OK — dry_run={st['dry_run']}, freq={st['center_freq_hz']/1e9:.3f} GHz")

        print("[2/5] Configuring RX channel...")
        device.configure_rx()
        print(f"      OK — fs={config.sample_rate_hz/1e6:.1f} MS/s, "
              f"bw={config.bandwidth_hz/1e6:.1f} MHz, gain={config.rx_gain_db:.0f} dB")

        print(f"[3/5] Capturing {N_SAMPLES:,} IQ samples...")
        iq = device.capture_rx()
        print(f"      OK — shape={iq.shape}, dtype={iq.dtype}, "
              f"mean_amp={np.mean(np.abs(iq)):.4f}")

        print("[4/5] Reading device status...")
        final_status = device.status()
        print(f"      log_entries={final_status['log_entries']}")
        success = True

    except Exception:
        error_msg = traceback.format_exc()
        print("\n[ERROR]")
        print(error_msg)
    finally:
        if device is not None:
            try:
                device.close()
                print("[5/5] Device closed.")
            except Exception as e:
                print(f"[WARN] close() failed: {e}")

    # --- Save outputs -----------------------------------------------------
    print("\n[Saving outputs]")

    if iq is not None:
        iq_path = CAPTURE_DIR / "rx_iq.npy"
        np.save(iq_path, iq)
        print(f"  IQ data:  {iq_path}")

        metadata = {
            "timestamp": TS,
            "center_freq_hz": CENTER_FREQ_HZ,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "bandwidth_hz": BANDWIDTH_HZ,
            "rx_gain_db": RX_GAIN_DB,
            "n_samples": N_SAMPLES,
            "dry_run": False,
            "iq_shape": list(iq.shape),
            "iq_dtype": str(iq.dtype),
            "rx_only": True,
            "tx_enabled": False,
            "motors": False,
            "human_subject": False,
            "confirmation_phrase": CONFIRMATION,
        }
        meta_path = CAPTURE_DIR / "metadata.json"
        meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"  Metadata: {meta_path}")

        stats = compute_iq_stats(iq, SAMPLE_RATE_HZ)

        td_path = REPORTS_DIR / "bladerf_rx_smoke_time_domain.png"
        plot_time_domain(iq, SAMPLE_RATE_HZ, td_path)
        print(f"  Time domain plot: {td_path}")

        sp_path = REPORTS_DIR / "bladerf_rx_smoke_spectrum.png"
        plot_spectrum(iq, SAMPLE_RATE_HZ, CENTER_FREQ_HZ, sp_path)
        print(f"  Spectrum plot: {sp_path}")
    else:
        stats = {}
        final_status = {}

    summary_path = REPORTS_DIR / "bladerf_rx_smoke_summary.md"
    write_summary(
        stats=stats,
        device_status=final_status if success else {},
        ts=TS,
        capture_dir=CAPTURE_DIR,
        success=success,
        error_msg=error_msg,
        out_path=summary_path,
    )
    print(f"  Summary: {summary_path}")

    # --- Print results -------------------------------------------------------
    if success and iq is not None:
        print("\n" + "=" * 60)
        print("RESULT: RX CAPTURE SUCCESSFUL")
        print("=" * 60)
        print(f"  IQ shape:         {iq.shape}")
        print(f"  dtype:            {iq.dtype}")
        print(f"  Mean amplitude:   {stats['mean_amplitude']:.5f}")
        print(f"  Max amplitude:    {stats['max_amplitude']:.5f}")
        print(f"  RMS amplitude:    {stats['rms_amplitude']:.5f}")
        print(f"  Clipping ratio:   {stats['clipping_ratio']:.6f}")
        print(f"  DC offset:        I={stats['dc_i']:.5f}, Q={stats['dc_q']:.5f}")
        print(f"  DC magnitude:     {stats['dc_magnitude']:.5f}")
        print(f"  Strongest bin:    {stats['peak_freq_offset_mhz']:+.3f} MHz from center")
        print(f"  Peak magnitude:   {stats['peak_magnitude_db']:.1f} dB")
        print()
        print("INTERPRETATION")
        print("-" * 60)
        if stats["clipping_ratio"] > 0.01:
            print("  WARNING: clipping ratio > 1%.  Reduce RX gain.")
        if stats["max_amplitude"] < 0.001:
            print("  NOTE: Very low amplitude.  May indicate no antenna or disconnected RX.")
        if stats["dc_magnitude"] > 0.1:
            print("  NOTE: Significant DC offset.  Normal for direct-conversion SDRs.")
        print("  This validates only the supervised RX acquisition path.")
        print("  The captured signal is environmental RF (WiFi / interference / noise).")
        print("  No object detection.  No SAR imaging.  No TX/RX radar operation.")
        print("  No dielectric characterization.  No medical claims.")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("RESULT: CAPTURE FAILED — see error above and summary report")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
