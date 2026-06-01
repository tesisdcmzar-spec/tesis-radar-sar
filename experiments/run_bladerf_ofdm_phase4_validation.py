"""
Phase 4 bladeRF OFDM hardware validation.

Modes
-----
  --rx-smoke       RX-only hardware smoke test (opens bladeRF, captures IQ,
                   computes stats, saves PSD figure and summary).
  --tx-iq-smoke    Very short OFDM IQ TX smoke test (1 symbol burst).
  --single-block   Single-block real OFDM H[k] acquisition.
  --run-phase4     Run full Phase 4 hardware gate sequence.

Default (no args): print help and exit safely. No hardware. No RF.

Safety
------
  TX gain: -20 dB. OFDM burst duration <= 10 ms.
  TX disabled in finally block regardless of exceptions.
  Hardware requires 'CONFIRM HARDWARE RUN' and 'REFLECTOR SETUP READY'.
  No human subjects. No phantom. No motor movement. No SAR scan.
  No clinical claims. No absolute permittivity mapping.

Pass --confirm 'CONFIRM HARDWARE RUN' and --reflector-ready 'REFLECTOR SETUP READY'
to skip interactive prompts.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from acquisition.ofdm_block_capture import (
    OFDMBlockConfig,
    build_known_ofdm_frame,
    capture_ofdm_block,
    summarize_ofdm_block_result,
)
from hardware.bladerf_device import BladeRFConfig, BladeRFDevice

REPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "generated",
)
RAW_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "raw", "ofdm_phase4",
)

# Conservative hardware defaults
CENTER_HZ = 2.4e9
FS_HZ = 2e6
BW_HZ = 2e6
RX_GAIN_DB = 20.0
TX_GAIN_DB = -20.0
N_SAMPLES = 40_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mkdir(*paths: str) -> None:
    for p in paths:
        os.makedirs(p, exist_ok=True)


def _ask_confirmation() -> str:
    print("\n  Enter confirmation phrase: CONFIRM HARDWARE RUN")
    return input("  Confirmation: ").strip()


def _ask_reflector() -> str:
    print("  Enter reflector phrase: REFLECTOR SETUP READY")
    return input("  Reflector: ").strip()


def _write_text(path: str, lines: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Phase 4C: RX smoke test
# ---------------------------------------------------------------------------

def rx_smoke(confirmation: str) -> str:
    """
    Open bladeRF, capture IQ at 2.4 GHz, compute stats, save figure + summary.

    Returns gate string: 'PASS' | 'FAIL: ...' | 'SKIPPED: ...'
    """
    print("\n=== Phase 4C: RX Smoke Test ===")
    _mkdir(REPORT_DIR, RAW_DIR)

    device = None
    gate = "FAIL: unknown"
    stats: dict = {}

    try:
        cfg = BladeRFConfig(
            center_freq_hz=CENTER_HZ,
            sample_rate_hz=FS_HZ,
            bandwidth_hz=BW_HZ,
            rx_gain_db=RX_GAIN_DB,
            tx_gain_db=TX_GAIN_DB,
            n_samples=N_SAMPLES,
            dry_run=False,
        )
        device = BladeRFDevice(cfg, confirmation=confirmation)
        device.configure_rx()
        print("  Capturing IQ ...")
        iq = device.capture_rx()

        rms = float(np.sqrt(np.mean(np.abs(iq) ** 2)))
        peak = float(np.max(np.abs(iq)))
        clip_ratio = float(np.sum(np.abs(iq) > 0.95) / len(iq))
        dc_i = float(np.mean(np.real(iq)))
        dc_q = float(np.mean(np.imag(iq)))
        n_cap = len(iq)

        stats = dict(
            center_freq_hz=CENTER_HZ,
            sample_rate_hz=FS_HZ,
            rx_gain_db=RX_GAIN_DB,
            n_samples_captured=n_cap,
            rms=rms,
            peak=peak,
            clipping_ratio=clip_ratio,
            dc_offset_i=dc_i,
            dc_offset_q=dc_q,
        )
        print(f"  n_samples   : {n_cap}")
        print(f"  RMS         : {rms:.6f}")
        print(f"  peak        : {peak:.6f}")
        print(f"  clip_ratio  : {clip_ratio*100:.3f}%")
        print(f"  DC (I,Q)    : {dc_i:.5f}, {dc_q:.5f}")

        # --- PSD + time-domain figure ---
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))

        ax = axes[0]
        disp_n = min(2000, n_cap)
        t_us = np.arange(disp_n) / FS_HZ * 1e6
        ax.plot(t_us, np.real(iq[:disp_n]), alpha=0.7, label="I")
        ax.plot(t_us, np.imag(iq[:disp_n]), alpha=0.7, label="Q")
        ax.axhline(0, color="k", linewidth=0.5)
        ax.set_xlabel("Time [us]")
        ax.set_ylabel("Amplitude (normalised)")
        ax.set_title(f"RX IQ time domain ({CENTER_HZ/1e9:.3f} GHz)")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

        ax = axes[1]
        win = np.hanning(n_cap)
        Pxx = np.abs(np.fft.fft(iq * win)) ** 2 / (np.sum(win ** 2) + 1e-15)
        Pxx_db = 10 * np.log10(np.fft.fftshift(Pxx) + 1e-15)
        f_mhz = np.fft.fftshift(np.fft.fftfreq(n_cap, d=1.0 / FS_HZ)) / 1e6
        ax.plot(f_mhz, Pxx_db)
        ax.set_xlabel("Baseband frequency [MHz]")
        ax.set_ylabel("PSD [dB]")
        ax.set_title("RX PSD (periodogram, Hanning)")
        ax.grid(True, alpha=0.3)

        fig.suptitle(
            f"Phase 4 RX Smoke -- {CENTER_HZ/1e9:.3f} GHz, "
            f"gain={RX_GAIN_DB:.0f} dB -- HARDWARE"
        )
        fig.tight_layout()
        fig_path = os.path.join(REPORT_DIR, "phase4_rx_smoke_psd.png")
        fig.savefig(fig_path, dpi=100)
        plt.close(fig)
        print(f"  Figure: {fig_path}")

        # --- gate ---
        if rms < 1e-6:
            gate = "FAIL: RMS near zero -- IQ may be all zeros"
        elif clip_ratio > 0.05:
            gate = f"FAIL: severe clipping ({clip_ratio*100:.1f}% samples clipped)"
        elif n_cap < N_SAMPLES - 100:
            gate = f"FAIL: capture too short ({n_cap} < {N_SAMPLES})"
        else:
            gate = "PASS"

    except ImportError as exc:
        gate = f"SKIPPED: bladeRF Python package not installed ({exc})"
        print(f"  {gate}")
    except Exception as exc:
        gate = f"FAIL: {exc}"
        print(f"  Exception: {exc}")
    finally:
        if device is not None:
            device.close()

    # --- summary ---
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines = [
        "# Phase 4 RX Smoke Summary",
        "",
        f"Generated: {ts}",
        f"RX_GATE: {gate}",
        "",
        "## Config",
        f"- center_freq_hz: {CENTER_HZ:.0f}",
        f"- sample_rate_hz: {FS_HZ:.0f}",
        f"- rx_gain_db: {RX_GAIN_DB:.1f}",
        f"- n_samples: {N_SAMPLES}",
        "",
        "## Statistics",
    ]
    for k, v in stats.items():
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        "## Safety",
        "- hardware=True, human_subject=False, phantom=False",
        "- biological_material=False, motor_scan=False, sar_scan=False",
        "",
        f"## RX_GATE: {gate}",
    ]
    summary_path = os.path.join(REPORT_DIR, "phase4_rx_smoke_summary.md")
    _write_text(summary_path, lines)
    print(f"  Summary: {summary_path}")
    print(f"  RX_GATE: {gate}")
    return gate


# ---------------------------------------------------------------------------
# Phase 4D: TX IQ smoke test
# ---------------------------------------------------------------------------

def tx_iq_smoke(confirmation: str, reflector_ready: str) -> str:
    """
    Transmit one minimal OFDM symbol burst via bladeRF. TX disabled in finally.

    Returns gate string: 'PASS' | 'FAIL: ...' | 'SKIPPED: ...'
    """
    print("\n=== Phase 4D: TX IQ Smoke Test ===")
    _mkdir(REPORT_DIR)

    # Build minimal OFDM frame: 1 symbol = (cp_len+n_fft) = 320 samples
    # @ 2 MS/s = 0.16 ms << 10 ms limit
    cfg_ofdm = OFDMBlockConfig(
        center_freq_hz=CENTER_HZ,
        sample_rate_hz=FS_HZ,
        bandwidth_hz=BW_HZ,
        n_fft=256, n_active=160, cp_len=64, guard_bins=20,
        dc_null=True, pilot_type="bpsk", pilot_seed=42,
        repetitions=1,
        tx_gain_db=TX_GAIN_DB, rx_gain_db=RX_GAIN_DB,
    )
    tx_time, _ = build_known_ofdm_frame(cfg_ofdm)
    n_tx = len(tx_time)
    dur_ms = n_tx / FS_HZ * 1000.0
    print(f"  TX samples  : {n_tx}")
    print(f"  TX duration : {dur_ms:.3f} ms (limit 10 ms)")
    assert dur_ms <= 10.0, f"TX duration {dur_ms:.3f} ms exceeds 10 ms safety limit"

    device = None
    gate = "FAIL: unknown"
    tx_meta: dict = {}

    try:
        cfg = BladeRFConfig(
            center_freq_hz=CENTER_HZ,
            sample_rate_hz=FS_HZ,
            bandwidth_hz=BW_HZ,
            rx_gain_db=RX_GAIN_DB,
            tx_gain_db=TX_GAIN_DB,
            n_samples=n_tx,
            dry_run=False,
        )
        device = BladeRFDevice(cfg, confirmation=confirmation)
        device.configure_tx()
        print("  Transmitting OFDM IQ burst ...")
        tx_meta = device.transmit_iq_burst(
            tx_time,
            reflector_setup_ready=reflector_ready,
            human_subject=False,
            phantom=False,
            biological_material=False,
            motor_scan=False,
            sar_scan=False,
        )
        gate = "PASS"
        print(f"  TX complete: {tx_meta.get('duration_s', 0)*1000:.3f} ms")

    except ImportError as exc:
        gate = f"SKIPPED: bladeRF Python package not installed ({exc})"
        print(f"  {gate}")
    except Exception as exc:
        gate = f"FAIL: {exc}"
        print(f"  Exception: {exc}")
    finally:
        if device is not None:
            device.close()  # close() disables TX module

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines = [
        "# Phase 4 TX IQ Smoke Summary",
        "",
        f"Generated: {ts}",
        f"TX_GATE: {gate}",
        "",
        "## TX Parameters",
        f"- center_freq_hz: {CENTER_HZ:.0f}",
        f"- sample_rate_hz: {FS_HZ:.0f}",
        f"- tx_gain_db: {TX_GAIN_DB:.1f}",
        f"- n_tx_samples: {n_tx}",
        f"- tx_duration_ms: {dur_ms:.3f}",
    ]
    for k, v in tx_meta.items():
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        "## Safety",
        "- TX disabled in finally block",
        "- TX duration << 10 ms safety limit",
        "- human_subject=False, phantom=False, biological_material=False",
        "- motor_scan=False, sar_scan=False",
        "",
        f"## TX_GATE: {gate}",
    ]
    summary_path = os.path.join(REPORT_DIR, "phase4_tx_smoke_summary.md")
    _write_text(summary_path, lines)
    print(f"  Summary: {summary_path}")
    print(f"  TX_GATE: {gate}")
    return gate


# ---------------------------------------------------------------------------
# Phase 4E: Single-block OFDM H[k]
# ---------------------------------------------------------------------------

def single_block_hw(confirmation: str, reflector_ready: str) -> str:
    """
    Capture one real OFDM block, estimate H[k], save figures + summary.

    Returns gate string: 'PASS' | 'FAIL: ...' | 'SKIPPED: ...'
    """
    print("\n=== Phase 4E: Single-Block OFDM H[k] ===")
    _mkdir(REPORT_DIR, RAW_DIR)

    device = None
    gate = "FAIL: unknown"

    try:
        cfg_ofdm = OFDMBlockConfig(
            center_freq_hz=CENTER_HZ,
            sample_rate_hz=FS_HZ,
            bandwidth_hz=BW_HZ,
            n_fft=256, n_active=160, cp_len=64, guard_bins=20,
            dc_null=True, pilot_type="bpsk", pilot_seed=42,
            repetitions=8,
            tx_gain_db=TX_GAIN_DB, rx_gain_db=RX_GAIN_DB,
        )
        sym_len = cfg_ofdm.cp_len + cfg_ofdm.n_fft
        n_needed = sym_len * cfg_ofdm.repetitions

        hw_cfg = BladeRFConfig(
            center_freq_hz=CENTER_HZ,
            sample_rate_hz=FS_HZ,
            bandwidth_hz=BW_HZ,
            rx_gain_db=RX_GAIN_DB,
            tx_gain_db=TX_GAIN_DB,
            n_samples=n_needed,
            dry_run=False,
        )
        device = BladeRFDevice(hw_cfg, confirmation=confirmation)
        print(f"  Capturing OFDM block at {CENTER_HZ/1e9:.3f} GHz ...")

        result = capture_ofdm_block(
            device, cfg_ofdm,
            dry_run=False,
            confirmation=confirmation,
            reflector_setup_ready=reflector_ready,
        )

        summary_text = summarize_ofdm_block_result(result)
        print(summary_text)

        # Gate checks
        H_mag = np.abs(result.H_active)
        n_act = len(result.active_indices)
        if not np.all(np.isfinite(result.H)):
            gate = "FAIL: H[k] contains NaN or Inf"
        elif n_act == 0:
            gate = "FAIL: zero active subcarriers"
        elif np.sum(H_mag > 1e-6) < n_act * 0.5:
            gate = f"FAIL: majority of active bins near zero ({np.sum(H_mag>1e-6)}/{n_act} nonzero)"
        else:
            gate = "PASS"

        # Save raw data
        ts_tag = time.strftime("%Y%m%d_%H%M%S")
        raw_path = os.path.join(RAW_DIR, f"single_block_{ts_tag}")
        os.makedirs(raw_path, exist_ok=True)
        np.save(os.path.join(raw_path, "H.npy"), result.H)
        np.save(os.path.join(raw_path, "freqs_hz.npy"), result.freqs_hz)
        np.save(os.path.join(raw_path, "cir.npy"), result.cir)
        print(f"  Raw data: {raw_path}")

        # Figures
        _save_single_block_figures(result)

        # Summary report
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        lines = [
            "# Phase 4 Single-Block H[k] Summary",
            "",
            f"Generated: {ts}",
            f"SINGLE_BLOCK_GATE: {gate}",
            "",
            "## Result",
            summary_text,
            "",
            "## Safety",
            f"- hardware=True, dry_run=False",
            f"- tx_gain_db={TX_GAIN_DB:.1f} dB, center_freq={CENTER_HZ/1e9:.3f} GHz",
            "- human_subject=False, phantom=False, biological_material=False",
            "- motor_scan=False, sar_scan=False",
            "",
            "## Scientific Claims",
            "- H[k] = Y[k] / X[k] per subcarrier (pilot-based channel estimation).",
            "- H[k] represents the combined cable, antenna, and environment response.",
            "- No object detection. No dielectric characterization. No clinical claims.",
            "- Calibration against a known reference is required before interpreting H[k].",
            "",
            f"## SINGLE_BLOCK_GATE: {gate}",
        ]
        report_path = os.path.join(REPORT_DIR, "phase4_single_block_h_summary.md")
        _write_text(report_path, lines)
        print(f"  Report: {report_path}")

    except ImportError as exc:
        gate = f"SKIPPED: bladeRF Python package not installed ({exc})"
        print(f"  {gate}")
    except Exception as exc:
        gate = f"FAIL: {exc}"
        print(f"  Exception: {exc}")
    finally:
        if device is not None:
            device.close()

    print(f"  SINGLE_BLOCK_GATE: {gate}")
    return gate


def _save_single_block_figures(result) -> None:
    """Save H[k] magnitude, H[k] phase, and CIR figures."""
    freqs_mhz = result.freqs_hz / 1e6
    H_mag_db = 20 * np.log10(np.abs(result.H_active) + 1e-15)
    H_phase_deg = np.degrees(np.angle(result.H_active))
    cir_mag = np.abs(result.cir)
    n = len(cir_mag)
    t_us = np.arange(n) / result.config.sample_rate_hz * 1e6

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(freqs_mhz, H_mag_db)
    ax.set_xlabel("Frequency [MHz]")
    ax.set_ylabel("|H[k]| [dB]")
    ax.set_title(
        f"OFDM H[k] magnitude -- {result.config.center_freq_hz/1e9:.3f} GHz "
        f"({'HW' if not result.dry_run else 'dry-run'})"
    )
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, "phase4_single_block_H_magnitude.png"), dpi=100)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(freqs_mhz, H_phase_deg)
    ax.set_xlabel("Frequency [MHz]")
    ax.set_ylabel("Phase [deg]")
    ax.set_title("OFDM H[k] phase")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, "phase4_single_block_H_phase.png"), dpi=100)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(t_us[:n // 2], cir_mag[:n // 2])
    ax.set_xlabel("Delay [us]")
    ax.set_ylabel("|CIR| (linear)")
    ax.set_title("Channel Impulse Response from OFDM H[k]")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, "phase4_single_block_cir.png"), dpi=100)
    plt.close(fig)
    print("  Figures: H_magnitude, H_phase, CIR saved")


# ---------------------------------------------------------------------------
# Phase 4 full sequence
# ---------------------------------------------------------------------------

def run_phase4_sequence(confirmation: str, reflector_ready: str) -> dict:
    """
    Run all hardware gates in sequence, stopping on hard failures.

    Returns dict of gate_name -> gate_string.
    """
    print("\n=== Phase 4: Full Hardware Gate Sequence ===")
    gates: dict[str, str] = {}

    rx_gate = rx_smoke(confirmation)
    gates["RX_GATE"] = rx_gate
    if rx_gate.startswith("FAIL"):
        print(f"\nHARD STOP: RX_GATE={rx_gate}")
        print("Cannot proceed to TX. Document blocker and check hardware.")
        return gates

    tx_gate = tx_iq_smoke(confirmation, reflector_ready)
    gates["TX_GATE"] = tx_gate
    if tx_gate.startswith("FAIL"):
        print(f"\nHARD STOP: TX_GATE={tx_gate}")
        print("Cannot proceed to single-block. Document blocker.")
        return gates

    sb_gate = single_block_hw(confirmation, reflector_ready)
    gates["SINGLE_BLOCK_GATE"] = sb_gate

    return gates


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 4 bladeRF OFDM hardware validation. "
            "Default: print help and exit (no hardware, no RF)."
        )
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--rx-smoke", action="store_true", help="RX-only smoke test.")
    g.add_argument("--tx-iq-smoke", action="store_true", help="Short OFDM TX IQ smoke.")
    g.add_argument("--single-block", action="store_true", help="Single-block OFDM H[k].")
    g.add_argument("--run-phase4", action="store_true", help="Full Phase 4 gate sequence.")
    parser.add_argument(
        "--confirm", default=None, metavar="PHRASE",
        help="Hardware confirmation phrase (default: prompt interactively).",
    )
    parser.add_argument(
        "--reflector-ready", default=None, metavar="PHRASE",
        help="Reflector setup phrase (default: prompt interactively).",
    )
    args = parser.parse_args()

    needs_hw = any([args.rx_smoke, args.tx_iq_smoke, args.single_block, args.run_phase4])
    if not needs_hw:
        parser.print_help()
        print("\n  No mode selected. This script performs hardware operations.")
        print("  Modes: --rx-smoke, --tx-iq-smoke, --single-block, --run-phase4")
        print("  Default is safe: no hardware, no RF.")
        sys.exit(0)

    # Obtain confirmation
    if args.confirm == "CONFIRM HARDWARE RUN":
        confirmation = args.confirm
    else:
        confirmation = _ask_confirmation()

    needs_reflector = args.tx_iq_smoke or args.single_block or args.run_phase4
    if needs_reflector:
        if args.reflector_ready == "REFLECTOR SETUP READY":
            reflector_ready = args.reflector_ready
        else:
            reflector_ready = _ask_reflector()
    else:
        reflector_ready = None

    print("\n--- Phase 4 hardware validation ---")
    print(f"  center_freq : {CENTER_HZ/1e9:.3f} GHz")
    print(f"  tx_gain_db  : {TX_GAIN_DB:.1f} dB")
    print(f"  rx_gain_db  : {RX_GAIN_DB:.1f} dB")
    print(f"  sample_rate : {FS_HZ/1e6:.1f} MS/s")

    if args.rx_smoke:
        gate = rx_smoke(confirmation)
        print(f"\nFinal: RX_GATE={gate}")

    elif args.tx_iq_smoke:
        gate = tx_iq_smoke(confirmation, reflector_ready)
        print(f"\nFinal: TX_GATE={gate}")

    elif args.single_block:
        gate = single_block_hw(confirmation, reflector_ready)
        print(f"\nFinal: SINGLE_BLOCK_GATE={gate}")

    elif args.run_phase4:
        gates = run_phase4_sequence(confirmation, reflector_ready)
        print("\n=== Phase 4 Gate Summary ===")
        for name, val in gates.items():
            print(f"  {name}: {val}")
        not_run = {"RX_GATE", "TX_GATE", "SINGLE_BLOCK_GATE"} - set(gates)
        for name in sorted(not_run):
            print(f"  {name}: SKIPPED (previous gate blocked sequence)")


if __name__ == "__main__":
    main()
