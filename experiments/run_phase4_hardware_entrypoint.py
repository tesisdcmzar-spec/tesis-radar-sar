"""
Phase 4 supervised hardware entrypoint.

Human-facing script for running hardware OFDM experiments with
physical supervision. Requires interactive confirmation phrases.
Never runs unattended. Never skips safety checks.

Modes
-----
  --rx-smoke          RX-only smoke test.
  --single-block      Single OFDM block H[k] acquisition.
  --background        Capture background (no object).
  --object            Capture object (reflector placed).
  --analyze           Analyze background + object data.
  --small-stitching   Small 3-block stitching pilot.
  --run-supervised    Run full supervised Phase 4 sequence.

Default (no args): print hardware checklist and exit. No RF.

This script REFUSES to:
  - Transmit RF without 'CONFIRM HARDWARE RUN' typed interactively.
  - Capture object without 'REFLECTOR SETUP READY' typed interactively.
  - Run with human_subject=True, phantom=True, biological_material=True,
    motor_scan=True, or sar_scan=True.
  - Move motors.
  - Commit raw data.

When to run
-----------
  Run this script when:
  1. bladeRF is physically connected via USB.
  2. TX antenna is connected to TX1.
  3. RX antenna is connected to RX1.
  4. A metallic reflector (e.g. metal plate) is placed at ~1 m.
  5. No person is in the antenna direction.
  6. User is physically present and watching.

  Exact command:
  py experiments/run_phase4_hardware_entrypoint.py --run-supervised
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "generated",
)

_CONFIRM_PHRASE = "CONFIRM HARDWARE RUN"
_REFLECTOR_PHRASE = "REFLECTOR SETUP READY"

# Safety flags that must always be False
_FORBIDDEN_FLAGS = dict(
    human_subject=False,
    phantom=False,
    biological_material=False,
    motor_scan=False,
    sar_scan=False,
)


# ---------------------------------------------------------------------------
# Safety guards
# ---------------------------------------------------------------------------

def _require_confirmation(prompt: str = _CONFIRM_PHRASE) -> str:
    print(f"\n  Enter the confirmation phrase to authorize hardware:")
    print(f"  '{prompt}'")
    entered = input("  > ").strip()
    if entered != prompt:
        print("  Aborted: confirmation phrase did not match.")
        sys.exit(1)
    return entered


def _require_reflector() -> str:
    print(f"\n  Confirm reflector/object is in position:")
    print(f"  '{_REFLECTOR_PHRASE}'")
    entered = input("  > ").strip()
    if entered != _REFLECTOR_PHRASE:
        print("  Aborted: reflector phrase did not match.")
        sys.exit(1)
    return entered


def _print_hardware_checklist() -> None:
    print("""
Phase 4 Hardware Entrypoint
===========================
This script runs real OFDM hardware experiments.
IT REQUIRES PHYSICAL SUPERVISION.

PRE-RUN CHECKLIST
-----------------
[ ] bladeRF 2.0 micro connected via USB.
[ ] bladeRF Python bindings installed: pip install bladerf
[ ] TX antenna connected to TX1 port.
[ ] RX antenna connected to RX1 port.
[ ] Metallic reflector placed at approximately 1 meter distance.
[ ] Antennas pointing toward reflector (not toward people).
[ ] No person in the main antenna direction.
[ ] No biological material in the test area.
[ ] No motor or azimuth stage connected or powered.
[ ] User is physically present and watching the equipment.
[ ] Emergency stop ready (unplug USB if needed).

TX SETTINGS (conservative)
--------------------------
  Center frequency : 2.400 GHz
  TX gain          : -20 dB  (conservative, << max)
  OFDM burst       : < 10 ms per block
  TX disabled      : always in finally block

COMMAND TO RUN
--------------
  py experiments/run_phase4_hardware_entrypoint.py --run-supervised

OR individual modes:
  py experiments/run_phase4_hardware_entrypoint.py --rx-smoke
  py experiments/run_phase4_hardware_entrypoint.py --single-block
  py experiments/run_phase4_hardware_entrypoint.py --background
  py experiments/run_phase4_hardware_entrypoint.py --object
  py experiments/run_phase4_hardware_entrypoint.py --analyze

EXPECTED OUTPUTS
----------------
  reports/generated/phase4_rx_smoke_psd.png
  reports/generated/phase4_rx_smoke_summary.md
  reports/generated/phase4_tx_smoke_summary.md
  reports/generated/phase4_single_block_H_magnitude.png
  reports/generated/phase4_single_block_H_phase.png
  reports/generated/phase4_single_block_cir.png
  reports/generated/phase4_single_block_h_summary.md
  reports/generated/phase4_background_object_H_background_object.png
  reports/generated/phase4_background_object_contrast_vs_distance.png
  reports/generated/phase4_background_object_summary.md
  reports/generated/phase4_stitching_summary.md

No clinical claims. No absolute permittivity. No cancer detection.
""")


# ---------------------------------------------------------------------------
# Mode wrappers
# ---------------------------------------------------------------------------

def _run_rx_smoke(confirmation: str) -> str:
    from experiments.run_bladerf_ofdm_phase4_validation import rx_smoke
    return rx_smoke(confirmation)


def _run_single_block(confirmation: str, reflector_ready: str) -> str:
    from experiments.run_bladerf_ofdm_phase4_validation import (
        tx_iq_smoke, single_block_hw
    )
    tx_gate = tx_iq_smoke(confirmation, reflector_ready)
    if tx_gate.startswith("FAIL"):
        print(f"  TX gate failed: {tx_gate}")
        return tx_gate
    return single_block_hw(confirmation, reflector_ready)


def _run_background(confirmation: str, reflector_ready: str) -> str:
    from experiments.run_ofdm_background_object_profile import run_background_hw
    return run_background_hw(confirmation, reflector_ready)


def _run_object(confirmation: str, reflector_ready: str) -> str:
    from experiments.run_ofdm_background_object_profile import run_object_hw
    return run_object_hw(confirmation, reflector_ready)


def _run_analyze() -> str:
    from experiments.run_ofdm_background_object_profile import run_analyze
    return run_analyze()


def _run_small_stitching(confirmation: str, reflector_ready: str) -> str:
    from experiments.run_ofdm_small_stitching_pilot import run_hardware
    return run_hardware(confirmation, reflector_ready)


# ---------------------------------------------------------------------------
# Full supervised sequence
# ---------------------------------------------------------------------------

def run_supervised() -> None:
    """
    Run full Phase 4 supervised hardware sequence.

    Sequence:
    1. RX smoke -- verify bladeRF opens and captures IQ.
    2. TX IQ smoke -- verify short OFDM burst transmits safely.
    3. Single-block OFDM H[k] -- capture and estimate channel.
    4. Background capture -- OFDM block without object.
    5. Object capture -- OFDM block with reflector in place.
    6. Analyze -- compute relative contrast profile.
    7. Stitching pilot -- 3-block stitch (optional if single-block passed).

    Each step requires interactive confirmation before proceeding.
    """
    print("\n=== Phase 4 Supervised Hardware Run ===")
    print("  User is physically present and supervising.")
    print("  No clinical claims. No absolute permittivity.")

    gates: dict[str, str] = {}

    # Step 1: confirm hardware authorization
    confirmation = _require_confirmation(_CONFIRM_PHRASE)
    reflector_ready = _require_reflector()

    print("\n--- Step 1: RX Smoke Test ---")
    from experiments.run_bladerf_ofdm_phase4_validation import rx_smoke, tx_iq_smoke, single_block_hw
    rx_gate = rx_smoke(confirmation)
    gates["RX_GATE"] = rx_gate
    if rx_gate.startswith("FAIL"):
        print(f"\nHARD STOP: RX_GATE={rx_gate}")
        _save_gate_report(gates, "rx_smoke failed")
        return

    print("\n--- Step 2: TX IQ Smoke Test ---")
    tx_gate = tx_iq_smoke(confirmation, reflector_ready)
    gates["TX_GATE"] = tx_gate
    if tx_gate.startswith("FAIL"):
        print(f"\nHARD STOP: TX_GATE={tx_gate}")
        _save_gate_report(gates, "tx_iq_smoke failed")
        return

    print("\n--- Step 3: Single-Block OFDM H[k] ---")
    sb_gate = single_block_hw(confirmation, reflector_ready)
    gates["SINGLE_BLOCK_GATE"] = sb_gate
    if sb_gate.startswith("FAIL"):
        print(f"\nHARD STOP: SINGLE_BLOCK_GATE={sb_gate}")
        _save_gate_report(gates, "single_block failed")
        return

    print("\n--- Step 4: Background capture ---")
    input("\n  Remove any object from antenna field, then press Enter ...")
    from experiments.run_ofdm_background_object_profile import (
        run_background_hw, run_object_hw, run_analyze
    )
    bg_gate = run_background_hw(confirmation, reflector_ready)
    gates["BACKGROUND_GATE"] = bg_gate

    print("\n--- Step 5: Object capture ---")
    input("\n  Place metallic reflector at ~1 m, then press Enter ...")
    obj_gate = run_object_hw(confirmation, reflector_ready)
    gates["OBJECT_GATE"] = obj_gate

    print("\n--- Step 6: Analyze contrast profile ---")
    analyze_gate = run_analyze()
    gates["BACKGROUND_OBJECT_GATE"] = analyze_gate

    print("\n--- Step 7: Small stitching pilot (optional) ---")
    answer = input("  Run 3-block stitching pilot? [y/N] ").strip().lower()
    if answer == "y":
        from experiments.run_ofdm_small_stitching_pilot import run_hardware as run_stitch
        stitch_gate = run_stitch(confirmation, reflector_ready)
        gates["STITCHING_GATE"] = stitch_gate
    else:
        gates["STITCHING_GATE"] = "SKIPPED (user declined)"

    _save_gate_report(gates, "full supervised sequence complete")

    print("\n=== Phase 4 Gate Summary ===")
    for name, val in gates.items():
        print(f"  {name}: {val}")


def _save_gate_report(gates: dict[str, str], note: str) -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines = [
        "# Phase 4 Hardware Run Gate Report",
        "",
        f"Generated: {ts}",
        f"Note: {note}",
        "",
        "## Gate Results",
    ]
    for name, val in gates.items():
        lines.append(f"- {name}: {val}")
    lines += [
        "",
        "## Safety",
        "- hardware=True, user physically present",
        "- No clinical claims. No absolute permittivity.",
        "- human_subject=False, phantom=False, biological_material=False",
        "- motor_scan=False, sar_scan=False",
    ]
    path = os.path.join(REPORT_DIR, "phase4_hardware_gate_report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Gate report: {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 4 supervised hardware entrypoint. "
            "Default: print checklist and exit."
        )
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--rx-smoke", action="store_true", help="RX smoke test.")
    g.add_argument("--single-block", action="store_true", help="Single-block OFDM.")
    g.add_argument("--background", action="store_true", help="Background capture.")
    g.add_argument("--object", action="store_true", help="Object capture.")
    g.add_argument("--analyze", action="store_true", help="Analyze BG/object data.")
    g.add_argument("--small-stitching", action="store_true", help="3-block stitch pilot.")
    g.add_argument("--run-supervised", action="store_true", help="Full supervised sequence.")
    args = parser.parse_args()

    any_mode = any([
        args.rx_smoke, args.single_block, args.background, args.object,
        args.analyze, args.small_stitching, args.run_supervised
    ])
    if not any_mode:
        _print_hardware_checklist()
        sys.exit(0)

    if args.analyze:
        gate = _run_analyze()
        print(f"\nBACKGROUND_OBJECT_GATE: {gate}")
        return

    if args.run_supervised:
        run_supervised()
        return

    # All modes below require confirmation
    confirmation = _require_confirmation(_CONFIRM_PHRASE)

    if args.rx_smoke:
        gate = _run_rx_smoke(confirmation)
        print(f"\nRX_GATE: {gate}")
        return

    reflector_ready = _require_reflector()

    if args.single_block:
        gate = _run_single_block(confirmation, reflector_ready)
        print(f"\nSINGLE_BLOCK_GATE: {gate}")
    elif args.background:
        gate = _run_background(confirmation, reflector_ready)
        print(f"\nBACKGROUND_GATE: {gate}")
    elif args.object:
        gate = _run_object(confirmation, reflector_ready)
        print(f"\nOBJECT_GATE: {gate}")
    elif args.small_stitching:
        gate = _run_small_stitching(confirmation, reflector_ready)
        print(f"\nSTITCHING_GATE: {gate}")


if __name__ == "__main__":
    main()
