"""
Supervised antenna TX/RX metallic-reflector experiment.

No 50-ohm load or external attenuator is available; TX is performed directly
with TX1 and RX1 antennas aimed at the reflector.  This limitation is
documented in the session report.

Usage
-----
  py experiments/run_bladerf_tx_rx_reflector.py --prepare-only
  py experiments/run_bladerf_tx_rx_reflector.py --pilot
  py experiments/run_bladerf_tx_rx_reflector.py --background
  py experiments/run_bladerf_tx_rx_reflector.py --reflector
  py experiments/run_bladerf_tx_rx_reflector.py --analyze
  py experiments/run_bladerf_tx_rx_reflector.py --run-sequence

No flags = --prepare-only (never transmits).

Safety
------
Real TX requires two exact confirmation phrases typed interactively:
  REFLECTOR SETUP READY
  CONFIRM HARDWARE RUN

TX is always disabled in a finally block regardless of exceptions.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import yaml

# Ensure project root is on sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from hardware.bladerf_device import BladeRFConfig, BladeRFDevice
from hardware.safety import (
    SafetyError,
    REFLECTOR_TX_GAIN_DB,
    MAX_REFLECTOR_TX_DURATION_PER_FREQ_S,
    MAX_FIRST_TX_PILOT_DURATION_S,
)
from acquisition.rx_sfcw_sweep import (
    make_frequency_grid,
    coherent_average_iq,
    extract_h_from_iq_bursts,
    compute_sweep_metrics,
)
from processing.range_profile import compute_range_profiles
from processing.rx_sfcw_postprocess import (
    subtract_reference_h,
    summarize_range_profile,
)
from simulation.synthetic_scan import SyntheticScan


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CONFIG_PATH = _ROOT / "configs" / "tx_rx_reflector_1m.yaml"
DATA_ROOT   = _ROOT / "data" / "raw" / "tx_rx_reflector"
REPORTS_GEN = _ROOT / "reports" / "generated"

PILOT_FREQ_HZ    = 2.4e9
PILOT_DURATION_S = 0.02   # 20 ms
SFCW_F_START     = 2.3e9
SFCW_F_STOP      = 2.5e9
SFCW_STEP        = 20e6   # 11 points
SFCW_DURATION_S  = 0.02   # 20 ms per frequency step
SAMPLE_RATE_HZ   = 1e6
BANDWIDTH_HZ     = 1e6
TX_GAIN_DB       = -20.0  # conservative; matches safety limit
RX_GAIN_DB       = 20.0
N_SAMPLES        = 20000  # 20 ms at 1 MS/s
ANTENNA_MODE     = "antenna_reflector_test"
REFLECTOR_DIST_M = 1.0


# ---------------------------------------------------------------------------
# Confirmation (interactive, required once before first TX)
# ---------------------------------------------------------------------------

_HW_CONFIRMATION:      str | None = None
_REFLECTOR_CONFIRMED:  str | None = None


def _get_confirmations() -> tuple[str, str]:
    """
    Print the safety checklist and collect the two required phrases
    interactively.  Called at most once per process; results are cached.
    """
    global _HW_CONFIRMATION, _REFLECTOR_CONFIRMED
    if _HW_CONFIRMATION == "CONFIRM HARDWARE RUN" and \
       _REFLECTOR_CONFIRMED == "REFLECTOR SETUP READY":
        return _HW_CONFIRMATION, _REFLECTOR_CONFIRMED

    print()
    print("=" * 60)
    print("SUPERVISED TX/RX REFLECTOR TEST")
    print()
    print("Confirm physical setup:")
    print("- User is physically present.")
    print("- TX antenna is connected to TX1.")
    print("- RX antenna is connected to RX1.")
    print("- Metallic reflector is near 1.0 m from antenna plane.")
    print("- Antennas are fixed and pointed at reflector.")
    print("- No humans are in antenna direction.")
    print("- No phantom.")
    print("- No biological material.")
    print("- No motor movement.")
    print("- This is not SAR.")
    print("- This is not a medical test.")
    print()
    print("To proceed with TX, type exactly:")
    print("  REFLECTOR SETUP READY")
    print("  CONFIRM HARDWARE RUN")
    print("=" * 60)
    print()

    r1 = input("First phrase: ").strip()
    r2 = input("Second phrase: ").strip()

    if r1 != "REFLECTOR SETUP READY":
        print(f"ERROR: First phrase does not match.  Got: {r1!r}")
        sys.exit(1)
    if r2 != "CONFIRM HARDWARE RUN":
        print(f"ERROR: Second phrase does not match.  Got: {r2!r}")
        sys.exit(1)

    _REFLECTOR_CONFIRMED = r1
    _HW_CONFIRMATION     = r2
    print()
    print("Confirmations accepted.  Proceeding with TX/RX experiment.")
    print()
    return _HW_CONFIRMATION, _REFLECTOR_CONFIRMED


# ---------------------------------------------------------------------------
# Data directory helpers
# ---------------------------------------------------------------------------

def _capture_dir(mode: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = DATA_ROOT / mode / ts
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Phase 1: Prepare-only (no TX, just validate config and environment)
# ---------------------------------------------------------------------------

def cmd_prepare_only() -> None:
    print("=== PREPARE-ONLY MODE (no TX) ===")
    cfg = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    print(f"Config loaded: {CONFIG_PATH.name}")
    print(f"  experiment_type      : {cfg.get('experiment_type')}")
    print(f"  reflector_distance_m : {cfg.get('reflector_distance_m')}")
    print(f"  human_subject        : {cfg.get('human_subject')}")
    print(f"  phantom              : {cfg.get('phantom')}")
    print(f"  motor_scan           : {cfg.get('motor_scan')}")
    print(f"  sar_scan             : {cfg.get('sar_scan')}")
    print()
    # Validate config via BladeRFConfig dry-run
    bcfg = BladeRFConfig(
        center_freq_hz=PILOT_FREQ_HZ,
        sample_rate_hz=SAMPLE_RATE_HZ,
        bandwidth_hz=BANDWIDTH_HZ,
        rx_gain_db=RX_GAIN_DB,
        tx_gain_db=TX_GAIN_DB,
        n_samples=N_SAMPLES,
        dry_run=True,
    )
    dev = BladeRFDevice(bcfg)
    dev.configure_tx()
    meta = dev.transmit_cw_burst(
        duration_s=PILOT_DURATION_S,
        antenna_mode=ANTENNA_MODE,
        reflector_distance_m=REFLECTOR_DIST_M,
    )
    dev.close()
    print("Dry-run TX/RX validation passed.")
    print(f"  Pilot freq: {meta['freq_hz']/1e9:.3f} GHz")
    print(f"  TX gain:    {meta['tx_gain_db']:.1f} dB")
    print(f"  Duration:   {meta['duration_s']*1e3:.1f} ms")
    print()
    print("Ready for real TX.  Run with --pilot when hardware is set up.")


# ---------------------------------------------------------------------------
# Phase 2: Pilot (single-frequency TX/RX)
# ---------------------------------------------------------------------------

def cmd_pilot(hw_confirmation: str, reflector_ready: str) -> dict:
    print("=== PILOT TX/RX (single frequency: 2.400 GHz) ===")
    cap_dir = _capture_dir("pilot")

    bcfg = BladeRFConfig(
        center_freq_hz=PILOT_FREQ_HZ,
        sample_rate_hz=SAMPLE_RATE_HZ,
        bandwidth_hz=BANDWIDTH_HZ,
        rx_gain_db=RX_GAIN_DB,
        tx_gain_db=TX_GAIN_DB,
        n_samples=N_SAMPLES,
        dry_run=False,
    )
    dev = BladeRFDevice(bcfg, confirmation=hw_confirmation)
    result = {"success": False, "capture_dir": str(cap_dir), "error": None}

    try:
        dev.configure_tx()
        dev.configure_rx()

        print(f"  TX: {PILOT_FREQ_HZ/1e9:.3f} GHz, gain={TX_GAIN_DB:.1f} dB, dur={PILOT_DURATION_S*1e3:.1f} ms")
        tx_meta = dev.transmit_cw_burst(
            duration_s=PILOT_DURATION_S,
            reflector_setup_ready=reflector_ready,
            antenna_mode=ANTENNA_MODE,
            reflector_distance_m=REFLECTOR_DIST_M,
            human_subject=False,
            phantom=False,
            biological_material=False,
            motor_scan=False,
            sar_scan=False,
        )
        print("  TX burst complete.")

        print(f"  RX: capturing {N_SAMPLES} samples...")
        iq = dev.capture_rx()
        mean_amp = float(np.mean(np.abs(iq)))
        print(f"  RX mean amplitude: {mean_amp:.5f}")

        np.save(str(cap_dir / "pilot_iq.npy"), iq)
        meta = {
            "timestamp": datetime.now().isoformat(),
            "mode": "pilot",
            "freq_hz": PILOT_FREQ_HZ,
            "tx_gain_db": TX_GAIN_DB,
            "rx_gain_db": RX_GAIN_DB,
            "tx_duration_s": PILOT_DURATION_S,
            "sample_rate_hz": SAMPLE_RATE_HZ,
            "n_samples": N_SAMPLES,
            "mean_amplitude": mean_amp,
            "antenna_mode": ANTENNA_MODE,
            "reflector_distance_m": REFLECTOR_DIST_M,
            "tx_meta": tx_meta,
        }
        (cap_dir / "metadata.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        result["success"] = True
        result["mean_amplitude"] = mean_amp
        print(f"  Pilot saved: {cap_dir}")

    except Exception as exc:
        result["error"] = str(exc)
        print(f"  PILOT FAILED: {exc}")
    finally:
        dev.close()

    return result


# ---------------------------------------------------------------------------
# Phase 3: SFCW sweep (background or reflector)
# ---------------------------------------------------------------------------

def cmd_sfcw_sweep(
    mode: str,
    hw_confirmation: str,
    reflector_ready: str,
) -> dict:
    label = "BACKGROUND" if mode == "background" else "REFLECTOR"
    print(f"=== SFCW SWEEP: {label} ===")
    freqs = make_frequency_grid(SFCW_F_START, SFCW_F_STOP, SFCW_STEP)
    n_freqs = len(freqs)
    print(f"  {n_freqs} frequencies: {SFCW_F_START/1e9:.3f}--{SFCW_F_STOP/1e9:.3f} GHz, step={SFCW_STEP/1e6:.0f} MHz")

    cap_dir = _capture_dir(mode)
    H = np.zeros(n_freqs, dtype=np.complex128)
    iq_bursts = []
    errors = []

    for i, freq_hz in enumerate(freqs):
        bcfg = BladeRFConfig(
            center_freq_hz=float(freq_hz),
            sample_rate_hz=SAMPLE_RATE_HZ,
            bandwidth_hz=BANDWIDTH_HZ,
            rx_gain_db=RX_GAIN_DB,
            tx_gain_db=TX_GAIN_DB,
            n_samples=N_SAMPLES,
            dry_run=False,
        )
        dev = BladeRFDevice(bcfg, confirmation=hw_confirmation)
        try:
            dev.configure_tx()
            dev.configure_rx()
            dev.transmit_cw_burst(
                duration_s=SFCW_DURATION_S,
                reflector_setup_ready=reflector_ready,
                antenna_mode=ANTENNA_MODE,
                reflector_distance_m=REFLECTOR_DIST_M,
                human_subject=False,
                phantom=False,
                biological_material=False,
                motor_scan=False,
                sar_scan=False,
            )
            iq = dev.capture_rx()
            h_val = coherent_average_iq(iq)
            H[i] = h_val
            iq_bursts.append(iq)
            print(f"  [{i+1:2d}/{n_freqs}] f={freq_hz/1e9:.3f} GHz  |H|={abs(h_val):.5f}")
        except Exception as exc:
            errors.append(f"f={freq_hz/1e9:.3f} GHz: {exc}")
            H[i] = 0.0 + 0.0j
            iq_bursts.append(np.zeros(N_SAMPLES, dtype=np.complex128))
            print(f"  [{i+1:2d}/{n_freqs}] FAILED: {exc}")
        finally:
            dev.close()

        time.sleep(0.01)  # brief inter-step pause

    np.save(str(cap_dir / "H_raw.npy"), H)
    np.save(str(cap_dir / "freqs_hz.npy"), freqs)
    meta = {
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "f_start_hz": SFCW_F_START,
        "f_stop_hz": SFCW_F_STOP,
        "step_hz": SFCW_STEP,
        "n_freqs": n_freqs,
        "n_captured": n_freqs - len(errors),
        "n_failed": len(errors),
        "tx_gain_db": TX_GAIN_DB,
        "rx_gain_db": RX_GAIN_DB,
        "tx_duration_per_freq_s": SFCW_DURATION_S,
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "antenna_mode": ANTENNA_MODE,
        "reflector_distance_m": REFLECTOR_DIST_M,
        "errors": errors,
    }
    (cap_dir / "metadata.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print(f"  Sweep saved: {cap_dir}  ({n_freqs - len(errors)}/{n_freqs} OK, {len(errors)} failed)")
    return {
        "success": len(errors) == 0,
        "H": H,
        "freqs_hz": freqs,
        "capture_dir": str(cap_dir),
        "n_captured": n_freqs - len(errors),
        "n_failed": len(errors),
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Phase 4: Analysis
# ---------------------------------------------------------------------------

def cmd_analyze(
    H_background: np.ndarray | None,
    H_reflector:  np.ndarray | None,
    freqs_hz:     np.ndarray | None,
    reflector_distance_m: float = REFLECTOR_DIST_M,
) -> dict:
    print("=== ANALYSIS ===")
    REPORTS_GEN.mkdir(parents=True, exist_ok=True)

    # If arrays not provided, try loading from latest captures
    if freqs_hz is None or H_reflector is None:
        print("  Searching for latest reflector capture...")
        ref_dirs = sorted((DATA_ROOT / "reflector").glob("*/H_raw.npy")) if \
                   (DATA_ROOT / "reflector").exists() else []
        if not ref_dirs:
            print("  ERROR: No reflector capture found.  Run --reflector first.")
            return {"success": False, "error": "no reflector data"}
        latest_ref = ref_dirs[-1].parent
        H_reflector = np.load(str(latest_ref / "H_raw.npy"))
        freqs_hz    = np.load(str(latest_ref / "freqs_hz.npy"))
        print(f"  Loaded H_reflector from: {latest_ref}")

    if H_background is None:
        bg_dirs = sorted((DATA_ROOT / "background").glob("*/H_raw.npy")) if \
                  (DATA_ROOT / "background").exists() else []
        if bg_dirs:
            latest_bg = bg_dirs[-1].parent
            H_background = np.load(str(latest_bg / "H_raw.npy"))
            print(f"  Loaded H_background from: {latest_bg}")
        else:
            print("  WARNING: No background capture found.  Using zeros as reference.")
            H_background = np.zeros_like(H_reflector)

    # Background subtraction
    H_target = H_reflector - H_background

    # Range profile
    scan = SyntheticScan(
        freqs_hz=freqs_hz,
        x_az_m=np.array([0.0]),
        H=H_target[:, None],
    )
    range_m, profiles = compute_range_profiles(scan, padding_factor=8, window="hanning")
    profile_1d = np.abs(profiles[:, 0])

    summary = summarize_range_profile(range_m, profile_1d)
    peak_range   = summary["peak_range_m"]
    peak_db      = summary["peak_magnitude_db"]
    noise_db     = summary["noise_floor_db"]
    dyn_range    = summary["dynamic_range_db"]
    error_m      = abs(peak_range - reflector_distance_m)
    peak_found   = error_m <= 0.5 and dyn_range >= 6.0

    print(f"  H_background: {len(freqs_hz)} freqs, mean|H|={float(np.mean(np.abs(H_background))):.5f}")
    print(f"  H_reflector:  {len(freqs_hz)} freqs, mean|H|={float(np.mean(np.abs(H_reflector))):.5f}")
    print(f"  H_target:     mean|H|={float(np.mean(np.abs(H_target))):.5f}")
    print(f"  Peak range:   {peak_range:.3f} m  (expected {reflector_distance_m:.2f} m, error={error_m:.3f} m)")
    print(f"  Peak mag:     {peak_db:.1f} dB")
    print(f"  Noise floor:  {noise_db:.1f} dB")
    print(f"  Dyn range:    {dyn_range:.1f} dB")
    if peak_found:
        print(f"  >>> PEAK DETECTED near {reflector_distance_m:.1f} m -- TX/RX coherent reflection CONFIRMED <<<")
    else:
        print(f"  >>> No clear peak near {reflector_distance_m:.1f} m (error={error_m:.3f} m, dyn={dyn_range:.1f} dB) <<<")

    # --- Figures ---
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    axes[0].plot(freqs_hz / 1e9, np.abs(H_background), label="|H_bg|", color="gray")
    axes[0].plot(freqs_hz / 1e9, np.abs(H_reflector),  label="|H_ref|", color="blue")
    axes[0].plot(freqs_hz / 1e9, np.abs(H_target),     label="|H_tgt|", color="red")
    axes[0].set_xlabel("Frequency (GHz)")
    axes[0].set_ylabel("|H(f)|")
    axes[0].set_title("H(f) comparison")
    axes[0].legend(fontsize=8)
    axes[0].grid(True)

    axes[1].plot(freqs_hz / 1e9, np.unwrap(np.angle(H_target)), color="purple")
    axes[1].set_xlabel("Frequency (GHz)")
    axes[1].set_ylabel("Phase (rad)")
    axes[1].set_title("H_target phase (unwrapped)")
    axes[1].grid(True)

    mag_db_profile = 20 * np.log10(profile_1d + 1e-12)
    axes[2].plot(range_m, mag_db_profile, color="green")
    axes[2].axvline(reflector_distance_m, color="red", linestyle="--", label=f"Expected {reflector_distance_m:.1f} m")
    axes[2].axvline(peak_range, color="orange", linestyle=":", label=f"Peak {peak_range:.2f} m")
    axes[2].set_xlabel("Range (m)")
    axes[2].set_ylabel("|profile| (dB)")
    axes[2].set_title("Range profile (H_target)")
    axes[2].legend(fontsize=8)
    axes[2].set_xlim([0, min(range_m[-1], 5.0)])
    axes[2].grid(True)

    fig.tight_layout()
    fig_path = REPORTS_GEN / "tx_rx_reflector_h_comparison.png"
    fig.savefig(str(fig_path), dpi=150)
    plt.close(fig)
    print(f"  Figure saved: {fig_path}")

    # --- Text summary ---
    ts = datetime.now().isoformat()
    summary_text = (
        f"# TX/RX Reflector Analysis Summary\n\n"
        f"Generated: {ts}\n\n"
        f"## Configuration\n"
        f"- SFCW: {SFCW_F_START/1e9:.3f}--{SFCW_F_STOP/1e9:.3f} GHz, step={SFCW_STEP/1e6:.0f} MHz\n"
        f"- N_freqs: {len(freqs_hz)}\n"
        f"- TX gain: {TX_GAIN_DB:.1f} dB\n"
        f"- RX gain: {RX_GAIN_DB:.1f} dB\n"
        f"- Expected reflector distance: {reflector_distance_m:.2f} m\n\n"
        f"## Results\n"
        f"- Peak range: {peak_range:.3f} m\n"
        f"- Error vs expected: {error_m:.3f} m\n"
        f"- Peak magnitude: {peak_db:.1f} dB\n"
        f"- Noise floor: {noise_db:.1f} dB\n"
        f"- Dynamic range: {dyn_range:.1f} dB\n\n"
        f"## Verdict\n"
    )
    if peak_found:
        summary_text += (
            f"**PEAK DETECTED** near {reflector_distance_m:.1f} m "
            f"(error={error_m:.3f} m, dyn={dyn_range:.1f} dB).\n"
            f"TX/RX coherent reflection confirmed for metallic reflector at ~{reflector_distance_m:.1f} m.\n\n"
        )
    else:
        summary_text += (
            f"**No clear peak** near {reflector_distance_m:.1f} m "
            f"(error={error_m:.3f} m, dyn={dyn_range:.1f} dB).\n"
            f"Target reflection not confirmed.  Possible causes: insufficient BW, "
            f"low SNR, antenna coupling, or reflector geometry.\n\n"
        )
    summary_text += (
        f"## Disclaimers\n"
        f"- This is not SAR.\n"
        f"- This is not a medical test.\n"
        f"- No human subject. No phantom. No biological material.\n"
        f"- No clinical or diagnostic claims.\n"
    )

    summary_path = REPORTS_GEN / "tx_rx_reflector_summary.md"
    summary_path.write_text(summary_text, encoding="utf-8")
    print(f"  Summary saved: {summary_path}")

    return {
        "success": True,
        "peak_found": peak_found,
        "peak_range_m": peak_range,
        "error_m": error_m,
        "peak_magnitude_db": peak_db,
        "noise_floor_db": noise_db,
        "dynamic_range_db": dyn_range,
        "figure_path": str(fig_path),
        "summary_path": str(summary_path),
    }


# ---------------------------------------------------------------------------
# run-sequence: pilot -> background -> reflector -> analyze
# ---------------------------------------------------------------------------

def cmd_run_sequence(hw_confirmation: str, reflector_ready: str) -> None:
    print()
    print("=== RUN SEQUENCE: pilot -> background -> reflector -> analyze ===")
    print()

    # Step 1: pilot
    pilot_result = cmd_pilot(hw_confirmation, reflector_ready)
    if not pilot_result["success"]:
        print()
        print("PILOT FAILED.  Stopping sequence.  Document error before retrying.")
        print(f"  Error: {pilot_result.get('error')}")
        sys.exit(1)
    print()

    # Step 2: background
    print("NOTE: If reflector cannot be removed, type 'skip' to skip background.")
    ans = input("Remove reflector for background capture? (yes/skip): ").strip().lower()
    H_background = None
    freqs_hz = None
    if ans == "yes":
        bg_result = cmd_sfcw_sweep("background", hw_confirmation, reflector_ready)
        H_background = bg_result["H"]
        freqs_hz     = bg_result["freqs_hz"]
        print()
    else:
        print("Skipping background capture.  Analysis will use zero reference.")
        print()

    # Step 3: reflector
    print("Place reflector at measured distance (~1.0 m) and press Enter.")
    input("Press Enter when reflector is in place: ")
    ref_result = cmd_sfcw_sweep("reflector", hw_confirmation, reflector_ready)
    if freqs_hz is None:
        freqs_hz = ref_result["freqs_hz"]
    H_reflector = ref_result["H"]
    print()

    # Step 4: analyze
    analysis = cmd_analyze(H_background, H_reflector, freqs_hz)
    print()

    if analysis.get("peak_found"):
        print("=== SEQUENCE COMPLETE: coherent reflector peak DETECTED near 1 m ===")
    else:
        print("=== SEQUENCE COMPLETE: peak NOT detected near 1 m ===")
        print("    Results documented.  System not yet validated as SFCW radar.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Supervised antenna TX/RX metallic-reflector experiment"
    )
    grp = parser.add_mutually_exclusive_group()
    grp.add_argument("--prepare-only", action="store_true", default=False)
    grp.add_argument("--pilot",        action="store_true", default=False)
    grp.add_argument("--background",   action="store_true", default=False)
    grp.add_argument("--reflector",    action="store_true", default=False)
    grp.add_argument("--analyze",      action="store_true", default=False)
    grp.add_argument("--run-sequence", action="store_true", default=False)
    args = parser.parse_args()

    # Default: prepare-only
    if not any([args.pilot, args.background, args.reflector,
                args.analyze, args.run_sequence]):
        args.prepare_only = True

    if args.prepare_only:
        cmd_prepare_only()
        return

    if args.analyze:
        cmd_analyze(None, None, None)
        return

    # All hardware modes require confirmation
    hw_conf, ref_conf = _get_confirmations()

    if args.pilot:
        result = cmd_pilot(hw_conf, ref_conf)
        if result["success"]:
            print("Pilot PASSED.")
        else:
            print(f"Pilot FAILED: {result['error']}")
            sys.exit(1)

    elif args.background:
        result = cmd_sfcw_sweep("background", hw_conf, ref_conf)
        print(f"Background sweep: {result['n_captured']}/{len(result['freqs_hz'])} OK")

    elif args.reflector:
        result = cmd_sfcw_sweep("reflector", hw_conf, ref_conf)
        print(f"Reflector sweep: {result['n_captured']}/{len(result['freqs_hz'])} OK")

    elif args.run_sequence:
        cmd_run_sequence(hw_conf, ref_conf)


if __name__ == "__main__":
    main()
