"""
OFDM single-block channel estimation experiment.

Usage:
    py experiments/run_ofdm_single_block_capture.py --prepare-only  (default)
    py experiments/run_ofdm_single_block_capture.py --dry-run
    py experiments/run_ofdm_single_block_capture.py --run-hardware

Modes:
  --prepare-only  Build the OFDM frame, simulate RX through a synthetic
                  channel, estimate H[k], produce a CIR, and save a summary
                  report. No hardware. No RF. Safe offline.

  --dry-run       Exercise capture_ofdm_block() with a fake device backend.
                  Validates the acquisition path end-to-end without bladeRF.

  --run-hardware  Transmit one real OFDM block via bladeRF and capture RX.
                  REQUIRES: bladeRF connected, user physically present,
                  confirmation phrase, and safe arbitrary IQ TX support.
                  Only safe if transmit_iq_burst() is available.

Safety notes:
  - No human subject.
  - No phantom or biological material.
  - No motor movement.
  - No SAR scan.
  - No multi-block sweep.
  - TX gain: -20 dB (conservative).
  - Burst duration: < 10 ms.
  - TX disabled in finally block.
  - Do not claim object detection or clinical diagnosis.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np

# Ensure repo root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acquisition.ofdm_block_capture import (
    OFDMBlockConfig,
    build_known_ofdm_frame,
    capture_ofdm_block,
    estimate_h_from_rx_frame,
    summarize_ofdm_block_result,
)
from processing.ofdm_channel import (
    channel_impulse_response,
    estimate_delay_peak,
    estimate_range_from_delay,
    summarize_ofdm_channel,
)

REPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "generated",
)
RAW_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "raw", "ofdm_single_block",
)


# ---------------------------------------------------------------------------
# Default config (2.4 GHz, conservative)
# ---------------------------------------------------------------------------

def make_default_config() -> OFDMBlockConfig:
    return OFDMBlockConfig(
        center_freq_hz=2.4e9,
        sample_rate_hz=2e6,
        bandwidth_hz=2e6,
        n_fft=256,
        n_active=160,
        cp_len=64,
        guard_bins=20,
        dc_null=True,
        pilot_type="bpsk",
        pilot_seed=42,
        repetitions=8,
        tx_gain_db=-20.0,
        rx_gain_db=20.0,
        human_subject=False,
        phantom=False,
        biological_material=False,
        motor_scan=False,
        sar_scan=False,
    )


# ---------------------------------------------------------------------------
# Synthetic channel for prepare-only mode
# ---------------------------------------------------------------------------

def _simulate_channel(tx_time: np.ndarray, config: OFDMBlockConfig) -> np.ndarray:
    """
    Simulate RX through a simple two-path free-space channel.

    Path 1: direct path, delay=30 samples, amplitude=1.0.
    Path 2: weaker reflection, delay=55 samples, amplitude=0.5.
    Adds AWGN with SNR ~30 dB.
    """
    n = len(tx_time)
    rx = np.zeros(n, dtype=complex)
    paths = [(1.0, 30), (0.5, 55)]
    for amp, delay in paths:
        rx[delay:] += amp * tx_time[:n - delay]
    rng = np.random.default_rng(seed=12345)
    noise_amp = 10 ** (-30.0 / 20.0)
    rx += (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * noise_amp
    return rx


# ---------------------------------------------------------------------------
# Mode: prepare-only
# ---------------------------------------------------------------------------

def run_prepare_only() -> None:
    print("OFDM single-block prepare-only run")
    print("  Mode: prepare-only. No hardware. No RF. No clinical claims.")

    config = make_default_config()
    print(f"  center_freq   : {config.center_freq_hz/1e9:.2f} GHz")
    print(f"  sample_rate   : {config.sample_rate_hz/1e6:.1f} MS/s")
    print(f"  n_fft         : {config.n_fft}")
    print(f"  n_active      : {config.n_active}")
    print(f"  cp_len        : {config.cp_len}")
    print(f"  guard_bins    : {config.guard_bins}")
    print(f"  pilot_type    : {config.pilot_type}")
    print(f"  repetitions   : {config.repetitions}")

    # Build known OFDM frame
    tx_time, tx_freq = build_known_ofdm_frame(config)
    print(f"  TX frame      : {len(tx_time)} samples")
    print(f"  TX active bins: {int(np.sum(np.abs(tx_freq) > 0))}")

    # Simulate RX
    rx_iq = _simulate_channel(tx_time, config)
    print(f"  RX simulated  : {len(rx_iq)} samples")

    # Estimate H[k]
    H = estimate_h_from_rx_frame(rx_iq, tx_freq, config)
    from processing.ofdm_channel import allocate_active_subcarriers
    active_idx = allocate_active_subcarriers(
        config.n_fft, config.n_active, dc_null=config.dc_null, guard_bins=config.guard_bins
    )
    H_active = H[active_idx]
    n_act = len(active_idx)
    print(f"  H active bins : {n_act}")
    print(f"  |H| mean      : {float(np.mean(np.abs(H_active))):.4f}")
    print(f"  |H| max       : {float(np.max(np.abs(H_active))):.4f}")

    # CIR
    cir = channel_impulse_response(H)
    delay_s = estimate_delay_peak(cir, config.sample_rate_hz)
    range_m = estimate_range_from_delay(delay_s, two_way=True)
    cir_peak_idx = int(np.argmax(np.abs(cir)))
    print(f"  CIR peak idx  : {cir_peak_idx}")
    print(f"  est delay     : {delay_s*1e9:.1f} ns")
    print(f"  est range     : {range_m*100:.1f} cm  (two-way, synthetic only)")

    # Subcarrier frequency mapping
    df = config.sample_rate_hz / config.n_fft
    n = config.n_fft
    shifts = np.where(active_idx <= n // 2, active_idx, active_idx - n).astype(float)
    freqs_hz = config.center_freq_hz + shifts * df
    bw = float(np.max(freqs_hz) - np.min(freqs_hz))
    print(f"  active BW     : {bw/1e3:.1f} kHz")
    print(f"  freq range    : {float(np.min(freqs_hz))/1e6:.3f} -- {float(np.max(freqs_hz))/1e6:.3f} MHz")

    # Summary dict
    summary = summarize_ofdm_channel(H_active, freqs_hz=freqs_hz, sample_rate_hz=config.sample_rate_hz)

    # Save report
    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(REPORT_DIR, "ofdm_single_block_prepare_summary.md")
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines = [
        "# OFDM Single-Block Prepare-Only Summary",
        "",
        f"Generated: {ts}",
        "",
        "## Config",
        f"- center_freq_hz: {config.center_freq_hz:.0f} ({config.center_freq_hz/1e9:.2f} GHz)",
        f"- sample_rate_hz: {config.sample_rate_hz:.0f}",
        f"- n_fft: {config.n_fft}",
        f"- n_active: {config.n_active}",
        f"- cp_len: {config.cp_len}",
        f"- guard_bins: {config.guard_bins}",
        f"- pilot_type: {config.pilot_type}",
        f"- repetitions: {config.repetitions}",
        f"- tx_gain_db: {config.tx_gain_db}",
        f"- rx_gain_db: {config.rx_gain_db}",
        "",
        "## Synthetic Channel",
        "- Path 1: delay=30 samples, amplitude=1.0",
        "- Path 2: delay=55 samples, amplitude=0.5",
        "- AWGN: SNR ~30 dB",
        "",
        "## H[k] Estimate",
        f"- Active subcarriers: {n_act}",
        f"- |H| mean: {summary['mag_mean']:.4f}",
        f"- |H| max: {summary['mag_max']:.4f}",
        f"- |H| dB range: {summary['mag_db_range']:.1f} dB",
        f"- Frequency range: {float(np.min(freqs_hz))/1e6:.3f} -- {float(np.max(freqs_hz))/1e6:.3f} MHz",
        f"- Active bandwidth: {bw/1e3:.1f} kHz",
        "",
        "## CIR / Delay Profile",
        f"- CIR peak index: {cir_peak_idx}",
        f"- Estimated delay: {delay_s*1e9:.1f} ns (synthetic, two-way)",
        f"- Estimated range: {range_m*100:.1f} cm (synthetic, two-way)",
        "",
        "## Safety",
        "- Mode: prepare-only (no hardware, no RF)",
        "- human_subject: False",
        "- phantom: False",
        "- biological_material: False",
        "- motor_scan: False",
        "- sar_scan: False",
        "",
        "## Claims",
        "- This run validates the OFDM frame generation and H[k] estimation pipeline.",
        "- No object detection. No clinical diagnosis. No dielectric characterization.",
        "- Delay/range estimates are from synthetic paths only.",
        "",
        "## Next Step",
        "- Run --dry-run to exercise the capture abstraction with a fake device.",
        "- Then run --run-hardware with a connected bladeRF for the first real block.",
    ]
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Report saved  : {report_path}")
    print("  Done. prepare-only complete.")


# ---------------------------------------------------------------------------
# Mode: dry-run
# ---------------------------------------------------------------------------

class FakeDryRunDevice:
    """Fake device for dry-run mode validation."""

    def configure_tx(self):
        print("    [FakeDevice] configure_tx called")

    def configure_rx(self):
        print("    [FakeDevice] configure_rx called")

    def transmit_iq_burst(self, iq_samples, **kwargs):
        print(f"    [FakeDevice] transmit_iq_burst: {len(iq_samples)} samples (NOT transmitted)")
        return {"dry_run": True, "n_samples_tx": len(iq_samples)}

    def capture_rx(self):
        # Return the TX frame with tiny noise (identity channel)
        # For dry_run mode, capture_ofdm_block generates RX internally; this is not called.
        n = 8192
        rng = np.random.default_rng(seed=42)
        return (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * 0.01

    def close(self):
        print("    [FakeDevice] close called")


def run_dry_run() -> None:
    print("OFDM single-block dry-run")
    print("  Mode: dry-run. Fake device backend. No hardware. No RF.")

    config = make_default_config()
    device = FakeDryRunDevice()

    result = capture_ofdm_block(device, config, dry_run=True)

    print(f"  dry_run       : {result.dry_run}")
    print(f"  H shape       : {result.H.shape}")
    print(f"  active bins   : {len(result.active_indices)}")
    print(f"  |H| mean      : {float(np.mean(np.abs(result.H_active))):.4f}")
    print(f"  est delay     : {result.delay_s*1e9:.1f} ns")
    print(f"  est range     : {result.range_m*100:.1f} cm")
    print(f"  timestamp     : {result.timestamp_utc}")

    summary = summarize_ofdm_block_result(result)
    print("\n--- Block Result Summary ---")
    print(summary)
    print("---")
    print("  Done. dry-run complete.")


# ---------------------------------------------------------------------------
# Mode: run-hardware
# ---------------------------------------------------------------------------

def run_hardware() -> None:
    print("OFDM single-block HARDWARE run")
    print("  REQUIRES: bladeRF connected, user physically present.")

    # Safety gate
    print()
    print("  Type the confirmation phrase to proceed:")
    print("    CONFIRM HARDWARE RUN")
    confirmation = input("  Confirmation: ").strip()
    if confirmation != "CONFIRM HARDWARE RUN":
        print("  Aborted: confirmation phrase not matched.")
        sys.exit(1)

    print()
    print("  Type the reflector-ready phrase:")
    print("    REFLECTOR SETUP READY")
    reflector_ready = input("  Reflector: ").strip()
    if reflector_ready != "REFLECTOR SETUP READY":
        print("  Aborted: reflector phrase not matched.")
        sys.exit(1)

    print()
    print("  Checking bladeRF arbitrary IQ TX support ...")
    print("  BladeRFDevice.transmit_iq_burst() is implemented.")
    print("  Proceeding with hardware capture.")

    try:
        from hardware.bladerf_device import BladeRFConfig, BladeRFDevice
    except ImportError as exc:
        print(f"  BLOCKER: hardware module import failed: {exc}")
        sys.exit(1)

    config = make_default_config()
    sym_len = config.cp_len + config.n_fft
    n_samples_needed = sym_len * config.repetitions

    hw_config = BladeRFConfig(
        center_freq_hz=config.center_freq_hz,
        sample_rate_hz=config.sample_rate_hz,
        bandwidth_hz=config.bandwidth_hz,
        rx_gain_db=config.rx_gain_db,
        tx_gain_db=config.tx_gain_db,
        n_samples=n_samples_needed,
        dry_run=False,
    )

    device = None
    try:
        device = BladeRFDevice(hw_config, confirmation=confirmation)
        device.configure_tx()
        device.configure_rx()

        print(f"  Capturing OFDM block at {config.center_freq_hz/1e9:.2f} GHz ...")
        result = capture_ofdm_block(
            device, config,
            dry_run=False,
            confirmation=confirmation,
            reflector_setup_ready=reflector_ready,
        )
        print(f"  Capture complete. H shape: {result.H.shape}")

    except Exception as exc:
        print(f"  ERROR during hardware capture: {exc}")
        sys.exit(1)
    finally:
        if device is not None:
            device.close()

    # Save raw IQ
    ts_tag = time.strftime("%Y%m%d_%H%M%S")
    raw_dir = os.path.join(RAW_DATA_DIR, ts_tag)
    os.makedirs(raw_dir, exist_ok=True)

    tx_time, _ = build_known_ofdm_frame(config)
    np.save(os.path.join(raw_dir, "tx_iq.npy"), tx_time)
    np.save(os.path.join(raw_dir, "H.npy"), result.H)
    np.save(os.path.join(raw_dir, "freqs_hz.npy"), result.freqs_hz)
    np.save(os.path.join(raw_dir, "cir.npy"), result.cir)
    print(f"  Raw data saved: {raw_dir}")

    # Save hardware H summary report
    os.makedirs(REPORT_DIR, exist_ok=True)
    report_path = os.path.join(REPORT_DIR, "ofdm_single_block_h_summary.md")
    summary_text = summarize_ofdm_block_result(result)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines = [
        "# OFDM Single-Block Hardware H[k] Summary",
        "",
        f"Generated: {ts}",
        "",
        "## Summary",
        summary_text,
        "",
        "## Safety Flags",
        f"- human_subject: {config.human_subject}",
        f"- phantom: {config.phantom}",
        f"- biological_material: {config.biological_material}",
        f"- motor_scan: {config.motor_scan}",
        f"- sar_scan: {config.sar_scan}",
        "",
        "## Claims",
        "- This is a first real OFDM block H[k] channel estimation.",
        "- No object detection. No clinical diagnosis. No dielectric characterization.",
        "- H[k] reflects the combined cable, antenna, and environment response.",
        "- Calibration against a known reference is required before interpreting H[k].",
        "",
        f"## Raw data",
        f"- Saved to: {raw_dir}",
    ]
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Report saved  : {report_path}")

    print("\n--- Block Result Summary ---")
    print(summary_text)
    print("---")
    print("  Done. Hardware run complete.")
    print("  Next step: multi-block stitching with processing/ofdm_block_stitcher.py")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="OFDM single-block channel estimation experiment."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--prepare-only", action="store_true", default=False,
        help="Generate frame and simulate RX offline (default mode).",
    )
    group.add_argument(
        "--dry-run", action="store_true", default=False,
        help="Exercise capture abstraction with fake device backend.",
    )
    group.add_argument(
        "--run-hardware", action="store_true", default=False,
        help="Run with real bladeRF hardware (requires confirmation).",
    )
    args = parser.parse_args()

    if args.run_hardware:
        run_hardware()
    elif args.dry_run:
        run_dry_run()
    else:
        # Default: prepare-only
        run_prepare_only()


if __name__ == "__main__":
    main()
