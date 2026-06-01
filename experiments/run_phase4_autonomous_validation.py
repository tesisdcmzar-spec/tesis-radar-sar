"""
Phase 4 autonomous software validation.

Runs all safe (offline/simulation/dry-run) Phase 4 validation steps
without any hardware access. No bladeRF. No RF. No motors.

Modes
-----
  --offline           Run offline simulation only (OFDM UWB-SAR).
  --dry-run           Run OFDM single-block dry-run.
  --prepare-hardware  Run all prepare-only/dry-run modes and generate hardware
                      readiness checklist. Still no real hardware.
  --all-safe          (default) Run every software-safe step end-to-end:
                      simulation + prepare-only + dry-run + synthetic contrast
                      profile + stitching pilot + gate summary.

All modes are safe by default.
No flags are needed for autonomous operation.
Never transmits RF. Never opens real TX. Never moves motors.

Output
------
  reports/generated/phase4_gate_summary.md
  reports/generated/phase3_offline_verification_summary.md
  All figures from simulation, background/object, and stitching modes.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "generated",
)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYTHON = sys.executable


# ---------------------------------------------------------------------------
# Gate tracker
# ---------------------------------------------------------------------------

class GateTracker:
    def __init__(self) -> None:
        self._gates: dict[str, str] = {}

    def set(self, name: str, result: str) -> None:
        self._gates[name] = result
        print(f"  {name}: {result}")

    def all_pass(self, *names: str) -> bool:
        return all(self._gates.get(n, "FAIL").startswith("PASS") for n in names)

    def summary(self) -> dict[str, str]:
        return dict(self._gates)


GATES = GateTracker()


# ---------------------------------------------------------------------------
# Subprocess runner
# ---------------------------------------------------------------------------

def _run(cmd: list[str], label: str, timeout: int = 120) -> str:
    """Run a subprocess. Returns 'PASS' on success or 'FAIL: ...' on error."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=_ROOT,
        )
        if result.returncode == 0:
            return "PASS"
        stderr_snippet = result.stderr.strip()[-500:] if result.stderr else ""
        stdout_snippet = result.stdout.strip()[-500:] if result.stdout else ""
        return f"FAIL: {label} exit={result.returncode} -- {stderr_snippet or stdout_snippet}"
    except subprocess.TimeoutExpired:
        return f"FAIL: {label} timed out after {timeout}s"
    except Exception as exc:
        return f"FAIL: {label} exception: {exc}"


# ---------------------------------------------------------------------------
# Individual validation steps
# ---------------------------------------------------------------------------

def step_compile() -> str:
    gate = _run(
        [PYTHON, "-m", "compileall",
         "acquisition", "processing", "hardware",
         "experiments", "tests", "simulation", "-q"],
        "compileall",
    )
    GATES.set("COMPILE_GATE", gate)
    return gate


def step_tests() -> str:
    gate = _run([PYTHON, "-m", "pytest", "tests", "-q", "--tb=short"], "pytest")
    GATES.set("TESTS_GATE", gate)
    return gate


def step_simulation() -> str:
    gate = _run(
        [PYTHON, "experiments/run_ofdm_uwb_sar_simulation.py"],
        "ofdm_sar_simulation",
    )
    GATES.set("SIMULATION_GATE", gate)
    return gate


def step_single_block_prepare() -> str:
    gate = _run(
        [PYTHON, "experiments/run_ofdm_single_block_capture.py", "--prepare-only"],
        "single_block_prepare",
    )
    GATES.set("SINGLE_BLOCK_PREPARE_GATE", gate)
    return gate


def step_single_block_dryrun() -> str:
    gate = _run(
        [PYTHON, "experiments/run_ofdm_single_block_capture.py", "--dry-run"],
        "single_block_dryrun",
    )
    GATES.set("SINGLE_BLOCK_DRYRUN_GATE", gate)
    return gate


def step_synthetic_contrast() -> str:
    gate = _run(
        [PYTHON, "experiments/run_ofdm_background_object_profile.py", "--prepare-only"],
        "synthetic_contrast",
    )
    GATES.set("SYNTHETIC_DISTANCE_PROFILE_GATE", gate)
    return gate


def step_stitching_prepare() -> str:
    gate = _run(
        [PYTHON, "experiments/run_ofdm_small_stitching_pilot.py", "--prepare-only"],
        "stitching_prepare",
    )
    GATES.set("STITCHING_PREPARE_GATE", gate)
    return gate


def step_stitching_dryrun() -> str:
    gate = _run(
        [PYTHON, "experiments/run_ofdm_small_stitching_pilot.py", "--dry-run"],
        "stitching_dryrun",
    )
    GATES.set("STITCHING_DRYRUN_GATE", gate)
    return gate


# ---------------------------------------------------------------------------
# Offline verification summary
# ---------------------------------------------------------------------------

def _write_offline_verification_summary() -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    gates = GATES.summary()

    lines = [
        "# Phase 3 / Phase 4 Offline Verification Summary",
        "",
        f"Generated: {ts}",
        "",
        "## OFFLINE_GATE Summary",
    ]
    for name, val in gates.items():
        lines.append(f"- {name}: {val}")

    offline_keys = [
        "COMPILE_GATE", "TESTS_GATE", "SIMULATION_GATE",
        "SINGLE_BLOCK_PREPARE_GATE", "SINGLE_BLOCK_DRYRUN_GATE",
    ]
    offline_pass = all(gates.get(k, "FAIL").startswith("PASS") for k in offline_keys)
    offline_gate = "PASS" if offline_pass else "FAIL"

    lines += [
        "",
        f"## OFFLINE_GATE: {offline_gate}",
        "",
        "## What was validated",
        "- Compile: all Python modules compile without errors.",
        "- Tests: all unit tests pass (no hardware, no bladeRF).",
        "- Simulation: UWB-OFDM-SAR offline simulation runs and generates figures.",
        "- Single-block prepare-only: OFDM frame + synthetic channel + H[k] estimation.",
        "- Single-block dry-run: capture abstraction with fake device backend.",
        "",
        "## Generated figures",
        "- ofdm_sim_h_magnitude.png",
        "- ofdm_sim_range_profiles.png",
        "- ofdm_sim_sar_image.png",
        "- ofdm_uwb_sar_simulation_summary.md",
        "- ofdm_single_block_prepare_summary.md",
        "",
        "## Safety",
        "- No hardware. No RF. No bladeRF opened.",
        "- No clinical claims. No absolute permittivity.",
        "- human_subject=False, phantom=False, biological_material=False",
        "- motor_scan=False, sar_scan=False",
    ]
    path = os.path.join(REPORT_DIR, "phase3_offline_verification_summary.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Saved: {path}")
    return offline_gate


# ---------------------------------------------------------------------------
# Gate summary
# ---------------------------------------------------------------------------

def _write_gate_summary() -> None:
    os.makedirs(REPORT_DIR, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    gates = GATES.summary()

    # Derived composite gates
    offline_keys = ["COMPILE_GATE", "TESTS_GATE", "SIMULATION_GATE",
                    "SINGLE_BLOCK_PREPARE_GATE", "SINGLE_BLOCK_DRYRUN_GATE"]
    offline_pass = all(gates.get(k, "FAIL").startswith("PASS") for k in offline_keys)
    offline_gate = "PASS" if offline_pass else "FAIL"

    synthetic_gate = gates.get("SYNTHETIC_DISTANCE_PROFILE_GATE", "SKIPPED")
    stitching_gate = gates.get("STITCHING_DRYRUN_GATE", "SKIPPED")

    lines = [
        "# Phase 4 Gate Summary",
        "",
        f"Generated: {ts}",
        "",
        "## Software Gates",
        f"- OFFLINE_GATE: {offline_gate}",
        f"- COMPILE_GATE: {gates.get('COMPILE_GATE', 'SKIPPED')}",
        f"- TESTS_GATE: {gates.get('TESTS_GATE', 'SKIPPED')}",
        f"- SIMULATION_GATE: {gates.get('SIMULATION_GATE', 'SKIPPED')}",
        f"- SINGLE_BLOCK_PREPARE_GATE: {gates.get('SINGLE_BLOCK_PREPARE_GATE', 'SKIPPED')}",
        f"- SINGLE_BLOCK_DRYRUN_GATE: {gates.get('SINGLE_BLOCK_DRYRUN_GATE', 'SKIPPED')}",
        f"- SYNTHETIC_DISTANCE_PROFILE_GATE: {synthetic_gate}",
        f"- STITCHING_PREPARE_GATE: {gates.get('STITCHING_PREPARE_GATE', 'SKIPPED')}",
        f"- STITCHING_DRYRUN_GATE: {stitching_gate}",
        "",
        "## Hardware Gates (require physical intervention)",
        "- RX_GATE: SKIPPED -- requires bladeRF connected and user present",
        "- TX_GATE: SKIPPED -- requires user present + CONFIRM HARDWARE RUN",
        "- SINGLE_BLOCK_HARDWARE_GATE: SKIPPED -- requires user present + REFLECTOR SETUP READY",
        "- BACKGROUND_OBJECT_HARDWARE_GATE: SKIPPED -- requires object placement",
        "- STITCHING_HARDWARE_GATE: SKIPPED -- requires user present",
        "",
        "## Report Gate",
        f"- REPORT_GATE: {'PASS' if offline_pass else 'FAIL'}",
        "",
        "## Next step (hardware)",
        "  py experiments/run_phase4_hardware_entrypoint.py --run-supervised",
        "  (Requires user physically present with bladeRF + metallic reflector at ~1 m)",
        "",
        "## No clinical claims",
        "- No absolute permittivity mapping.",
        "- No cancer detection. No clinical diagnosis.",
        "- Output: relative dielectric-contrast profile only.",
    ]
    path = os.path.join(REPORT_DIR, "phase4_gate_summary.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"  Gate summary: {path}")


# ---------------------------------------------------------------------------
# Mode runners
# ---------------------------------------------------------------------------

def run_offline() -> None:
    print("\n--- Offline simulation ---")
    step_simulation()


def run_dry_run() -> None:
    print("\n--- Single-block dry-run ---")
    step_single_block_dryrun()


def run_prepare_hardware() -> None:
    """Run all prepare-only modes and generate readiness summary."""
    print("\n--- Prepare hardware (no actual hardware) ---")
    step_compile()
    step_tests()
    step_simulation()
    step_single_block_prepare()
    step_single_block_dryrun()
    step_synthetic_contrast()
    step_stitching_prepare()
    step_stitching_dryrun()
    _write_offline_verification_summary()
    _write_gate_summary()


def run_all_safe() -> None:
    """Run every software-safe validation step."""
    print("\n=== Phase 4 Autonomous Software Validation ===")
    print("  Mode: --all-safe. No hardware. No RF. No clinical claims.")

    print("\n--- Compile ---")
    step_compile()

    print("\n--- Tests ---")
    step_tests()

    print("\n--- OFDM UWB-SAR simulation ---")
    step_simulation()

    print("\n--- OFDM single-block prepare-only ---")
    step_single_block_prepare()

    print("\n--- OFDM single-block dry-run ---")
    step_single_block_dryrun()

    print("\n--- Synthetic background/object contrast profile ---")
    step_synthetic_contrast()

    print("\n--- Stitching pilot prepare-only ---")
    step_stitching_prepare()

    print("\n--- Stitching pilot dry-run ---")
    step_stitching_dryrun()

    print("\n--- Writing summaries ---")
    offline_gate = _write_offline_verification_summary()
    _write_gate_summary()

    print("\n=== Gate Summary ===")
    for name, val in GATES.summary().items():
        print(f"  {name}: {val}")

    print(f"\nOFFLINE_GATE: {offline_gate}")
    print("STITCHING_DRYRUN_GATE:", GATES.summary().get("STITCHING_DRYRUN_GATE", "SKIPPED"))
    print("SYNTHETIC_DISTANCE_PROFILE_GATE:",
          GATES.summary().get("SYNTHETIC_DISTANCE_PROFILE_GATE", "SKIPPED"))
    print("\nDone. All software-only Phase 4 steps complete.")
    print("Next: attach bladeRF and run --run-supervised for hardware validation.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 4 autonomous software validation. Default: --all-safe."
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--offline", action="store_true", help="Run offline simulation only.")
    g.add_argument("--dry-run", action="store_true", help="Run single-block dry-run only.")
    g.add_argument("--prepare-hardware", action="store_true",
                   help="Prepare all software modes for hardware readiness.")
    g.add_argument("--all-safe", action="store_true", help="Run all safe steps (default).")
    args = parser.parse_args()

    if args.offline:
        run_offline()
    elif args.dry_run:
        run_dry_run()
    elif args.prepare_hardware:
        run_prepare_hardware()
    else:
        run_all_safe()


if __name__ == "__main__":
    main()
