"""
Supervised RX-only SFCW-style sweep with bladeRF.

SAFETY CONTRACT
---------------
- RX ONLY.  No TX.  No configure_tx().  No transmit_tone().
- No motor movement.  No azimuth stage.
- No human subject.  No phantom.
- Not a SAR scan.  Not a SAR image.  Not a medical test.
- Not dielectric characterization.  No clinical claims.
- This is an infrastructure/process validation of the H(f) and range-profile
  pipeline.  H(f) captured here is environmental RF noise, NOT a radar
  transfer function from an emitted signal.
- Confirmation phrase: 'CONFIRM HARDWARE RUN' (hard-coded, not configurable).
- Script runs once and exits.  No infinite loops.

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

MODES
-----
Pilot: 2.300–2.500 GHz, 10 MHz step, 21 frequencies, 100 000 samples each.
Full : 2.300–2.500 GHz,  1 MHz step, 201 frequencies, 100 000 samples each.
       Full runs automatically only if pilot passes all safety conditions.

OUTPUT (local only, not committed)
-----------------------------------
data/raw/rx_sfcw_sweep/{pilot,full}/YYYYMMDD_HHMMSS/
    cap_{N:03d}_{freq_mhz:.0f}MHz.npy   per-frequency IQ burst
    freqs_hz.npy
    H_raw.npy
    metadata.json
    sweep_summary.json

reports/generated/
    rx_sfcw_pilot_h_magnitude_phase.png
    rx_sfcw_pilot_range_profile.png
    rx_sfcw_full_h_magnitude_phase.png   (if full mode ran)
    rx_sfcw_full_range_profile.png       (if full mode ran)
    rx_sfcw_sweep_summary.md
"""
from __future__ import annotations

import json
import shutil
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

from hardware.bladerf_device import BladeRFConfig, BladeRFDevice         # noqa: E402
from acquisition.rx_sfcw_sweep import (                                   # noqa: E402
    SweepConfig,
    SweepResult,
    coherent_average_iq,
    compute_sweep_metrics,
    extract_h_from_iq_bursts,
    make_frequency_grid,
    make_synthetic_scan_from_h,
)
from processing.range_profile import compute_range_profiles               # noqa: E402

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

CONFIRMATION = "CONFIRM HARDWARE RUN"

SAMPLE_RATE_HZ = 10e6
BANDWIDTH_HZ   = 10e6
RX_GAIN_DB     = 20.0
TX_GAIN_DB     = -20.0   # conservative default; TX NOT used
N_SAMPLES      = 100_000  # ~10 ms per burst at 10 MS/s

# Sweep frequency range (same for both modes)
F_START_HZ = 2.300e9
F_STOP_HZ  = 2.500e9

PILOT_CONFIG = SweepConfig(
    mode="pilot",
    f_start_hz=F_START_HZ,
    f_stop_hz=F_STOP_HZ,
    step_hz=10e6,         # 21 points
    n_samples=N_SAMPLES,
    sample_rate_hz=SAMPLE_RATE_HZ,
    bandwidth_hz=BANDWIDTH_HZ,
    rx_gain_db=RX_GAIN_DB,
)

FULL_CONFIG = SweepConfig(
    mode="full",
    f_start_hz=F_START_HZ,
    f_stop_hz=F_STOP_HZ,
    step_hz=1e6,          # 201 points
    n_samples=N_SAMPLES,
    sample_rate_hz=SAMPLE_RATE_HZ,
    bandwidth_hz=BANDWIDTH_HZ,
    rx_gain_db=RX_GAIN_DB,
)

MIN_FREE_DISK_BYTES = 3e9   # 3 GB

REPORTS_DIR = REPO_ROOT / "reports" / "generated"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------
# Pre-flight banner
# --------------------------------------------------------------------------

def print_preflight() -> None:
    print(
        "\n"
        "+------------------------------------------------------------------+\n"
        "|      SUPERVISED RX-ONLY bladeRF SFCW SWEEP                      |\n"
        "|      Pre-flight checklist                                         |\n"
        "+------------------------------------------------------------------+\n"
        "|  [1] User is physically present                                   |\n"
        "|  [2] bladeRF connected via USB                                    |\n"
        "|  [3] RX1 has antenna or 50-ohm load                               |\n"
        "|  [4] TX1 is NOT used                                              |\n"
        "|  [5] No human subject being tested                                |\n"
        "|  [6] No motor or moving stage                                     |\n"
        "|  [7] RX-ONLY session -- no RF transmitted                         |\n"
        "|  [8] Confirmation phrase: CONFIRM HARDWARE RUN                    |\n"
        "+------------------------------------------------------------------+\n"
        "SCIENTIFIC HONESTY:\n"
        "  H(f) = coherent mean of environmental RF noise at each tuned freq.\n"
        "  NOT a radar transfer function from an emitted signal.\n"
        "  Range profile = infrastructure/processing pipeline validation.\n"
        "  NOT object detection. NOT SAR imaging. NOT dielectric measurement.\n"
        "  NOT a medical or clinical test.\n"
    )


# --------------------------------------------------------------------------
# IQ clipping check
# --------------------------------------------------------------------------

def count_clipped_samples(iq: np.ndarray, threshold: float = 0.99) -> int:
    return int(np.sum(np.abs(iq) >= threshold))


# --------------------------------------------------------------------------
# Capture one sweep pass
# --------------------------------------------------------------------------

def run_sweep_pass(
    sweep_cfg: SweepConfig,
    confirmation: str,
) -> SweepResult:
    """
    Capture one complete sweep pass (pilot or full).

    Opens and closes a BladeRFDevice per frequency step.  Each capture is one
    IQ burst of sweep_cfg.n_samples samples, coherently averaged to extract
    H[k].  Raw IQ arrays and the assembled H(f) vector are saved locally.

    Returns
    -------
    SweepResult with freqs_hz, H, per-freq statistics, and capture_dir.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    capture_dir = (
        REPO_ROOT / "data" / "raw" / "rx_sfcw_sweep" / sweep_cfg.mode / ts
    )
    capture_dir.mkdir(parents=True, exist_ok=True)

    freqs_hz = make_frequency_grid(
        sweep_cfg.f_start_hz, sweep_cfg.f_stop_hz, sweep_cfg.step_hz
    )
    n_freqs = len(freqs_hz)

    print(f"\n{'='*64}")
    print(f"  SWEEP MODE: {sweep_cfg.mode.upper()}")
    print(f"  {freqs_hz[0]/1e9:.3f} – {freqs_hz[-1]/1e9:.3f} GHz")
    print(f"  step={sweep_cfg.step_hz/1e6:.0f} MHz,  {n_freqs} frequencies")
    print(f"  {sweep_cfg.n_samples:,} samples each (~"
          f"{sweep_cfg.n_samples/sweep_cfg.sample_rate_hz*1e3:.0f} ms)")
    print(f"  Output: {capture_dir}")
    print(f"{'='*64}")

    iq_bursts: list[np.ndarray] = []
    H_list:    list[complex] = []
    n_captured = 0
    n_clipped  = 0
    n_failed   = 0
    errors:    list[str] = []

    for idx, freq_hz in enumerate(freqs_hz):
        freq_mhz = freq_hz / 1e6
        print(
            f"  [{idx+1:3d}/{n_freqs}]  {freq_mhz:7.1f} MHz ...",
            end=" ", flush=True,
        )
        config = BladeRFConfig(
            center_freq_hz=freq_hz,
            sample_rate_hz=sweep_cfg.sample_rate_hz,
            bandwidth_hz=sweep_cfg.bandwidth_hz,
            rx_gain_db=sweep_cfg.rx_gain_db,
            tx_gain_db=TX_GAIN_DB,
            n_samples=sweep_cfg.n_samples,
            dry_run=False,
        )
        device: BladeRFDevice | None = None
        iq: np.ndarray | None = None
        try:
            device = BladeRFDevice(config, confirmation=confirmation)
            device.configure_rx()
            iq = device.capture_rx()
            device.close()
            device = None

            n_clip = count_clipped_samples(iq)
            h_val  = coherent_average_iq(iq)
            iq_bursts.append(iq)
            H_list.append(h_val)
            n_captured += 1
            if n_clip > 0:
                n_clipped += 1

            rms  = float(np.sqrt(np.mean(np.abs(iq)**2)))
            print(
                f"OK  rms={rms:.5f}  h_mag={abs(h_val):.5f}  "
                f"clip={n_clip}",
                flush=True,
            )

            # Save IQ burst locally
            fname = f"cap_{idx:03d}_{freq_mhz:.0f}MHz.npy"
            np.save(capture_dir / fname, iq)

        except Exception:
            err = traceback.format_exc()
            errors.append(f"freq={freq_hz/1e6:.1f} MHz: {err}")
            n_failed += 1
            # Pad H with zero so indices stay aligned
            iq_bursts.append(np.zeros(1, dtype=np.complex128))
            H_list.append(0.0 + 0.0j)
            print(f"FAILED\n{err}", flush=True)
            if device is not None:
                try:
                    device.close()
                except Exception:
                    pass

    H_arr = np.array(H_list, dtype=np.complex128)

    # Save sweep-level arrays
    np.save(capture_dir / "freqs_hz.npy", freqs_hz)
    np.save(capture_dir / "H_raw.npy", H_arr)

    metadata = {
        "timestamp":       ts,
        "mode":            sweep_cfg.mode,
        "f_start_hz":      sweep_cfg.f_start_hz,
        "f_stop_hz":       sweep_cfg.f_stop_hz,
        "step_hz":         sweep_cfg.step_hz,
        "n_freqs":         int(n_freqs),
        "n_samples":       sweep_cfg.n_samples,
        "sample_rate_hz":  sweep_cfg.sample_rate_hz,
        "bandwidth_hz":    sweep_cfg.bandwidth_hz,
        "rx_gain_db":      sweep_cfg.rx_gain_db,
        "dry_run":         False,
        "rx_only":         True,
        "tx_enabled":      False,
        "motors":          False,
        "human_subject":   False,
        "confirmation_phrase": confirmation,
        "n_captured":      n_captured,
        "n_clipped":       n_clipped,
        "n_failed":        n_failed,
    }
    (capture_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )

    result = SweepResult(
        config=sweep_cfg,
        freqs_hz=freqs_hz,
        H=H_arr,
        n_captured=n_captured,
        n_clipped=n_clipped,
        n_failed=n_failed,
        capture_dir=str(capture_dir),
        errors=errors,
    )
    sweep_summary = result.to_dict()
    (capture_dir / "sweep_summary.json").write_text(
        json.dumps(sweep_summary, indent=2, default=str), encoding="utf-8"
    )

    print(f"\n  --> {sweep_cfg.mode.upper()} complete: "
          f"{n_captured}/{n_freqs} captured, "
          f"{n_clipped} clipped, {n_failed} failed")

    return result


# --------------------------------------------------------------------------
# Analysis and plotting
# --------------------------------------------------------------------------

def analyze_and_plot(result: SweepResult, tag: str) -> dict:
    """
    Compute range profiles (rectangular + Hanning), generate plots, return metrics.

    Parameters
    ----------
    result : SweepResult
    tag    : str   'pilot' or 'full' — used for output filenames.

    Returns
    -------
    dict of metrics from compute_sweep_metrics.
    """
    freqs_hz = result.freqs_hz
    H        = result.H

    metrics = compute_sweep_metrics(freqs_hz, H)

    # --- Build SyntheticScan (single azimuth = 0 m) -----------------------
    scan = make_synthetic_scan_from_h(freqs_hz, H, x_az_m=0.0)

    # --- Range profiles: rectangular and Hanning ---------------------------
    range_rect,   prof_rect   = compute_range_profiles(scan, padding_factor=8, window='none')
    range_hann,   prof_hann   = compute_range_profiles(scan, padding_factor=8, window='hanning')

    # Take the single azimuth column
    p_rect = np.abs(prof_rect[:, 0])
    p_hann = np.abs(prof_hann[:, 0])

    p_rect_db = 20.0 * np.log10(p_rect + 1e-12)
    p_hann_db = 20.0 * np.log10(p_hann + 1e-12)

    # --- Plot 1: H(f) magnitude and phase ---------------------------------
    fig_h, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
    freqs_mhz = freqs_hz / 1e6
    mag_db = 20.0 * np.log10(np.abs(H) + 1e-12)
    phase_deg = np.angle(H, deg=True)

    ax1.plot(freqs_mhz, mag_db, color="steelblue", linewidth=1.2, marker="o",
             markersize=3)
    ax1.set_ylabel("|H(f)| [dB]")
    ax1.set_title(
        f"RX-Only SFCW {tag.capitalize()} — H(f) magnitude and phase\n"
        f"({freqs_mhz[0]:.0f}–{freqs_mhz[-1]:.0f} MHz, "
        f"step={result.config.step_hz/1e6:.0f} MHz, "
        f"{result.n_captured}/{len(freqs_hz)} captured)"
    )
    ax1.grid(True, alpha=0.3)

    ax2.plot(freqs_mhz, phase_deg, color="darkorange", linewidth=1.0,
             marker="o", markersize=3)
    ax2.set_ylabel("Phase [°]")
    ax2.set_xlabel("Frequency [MHz]")
    ax2.set_ylim(-185, 185)
    ax2.grid(True, alpha=0.3)

    fig_h.tight_layout()
    h_out = REPORTS_DIR / f"rx_sfcw_{tag}_h_magnitude_phase.png"
    fig_h.savefig(h_out, dpi=150)
    plt.close(fig_h)
    print(f"  Saved: {h_out.name}")

    # --- Plot 2: Range profiles (rectangular vs Hanning) ------------------
    fig_r, ax = plt.subplots(figsize=(12, 5))
    ax.plot(range_rect, p_rect_db, color="steelblue",  linewidth=1.2,
            label="Rectangular (no window)")
    ax.plot(range_hann, p_hann_db, color="darkorange", linewidth=1.2,
            label="Hanning window")
    ax.set_xlabel("One-way range [m]")
    ax.set_ylabel("Amplitude [dB]")
    ax.set_title(
        f"RX-Only SFCW {tag.capitalize()} — Range profile\n"
        f"BW={metrics['bandwidth_mhz']:.0f} MHz -> "
        f"dr={metrics['range_resolution_cm']:.1f} cm  |  "
        f"Unambiguous range={metrics['unambiguous_range_m']:.1f} m\n"
        "NOTE: RX-only noise — no coherent target — pipeline validation only"
    )
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, min(range_rect[-1], 30.0))  # show first 30 m
    fig_r.tight_layout()
    r_out = REPORTS_DIR / f"rx_sfcw_{tag}_range_profile.png"
    fig_r.savefig(r_out, dpi=150)
    plt.close(fig_r)
    print(f"  Saved: {r_out.name}")

    # Strongest range bin
    peak_range_bin = int(np.argmax(p_rect))
    peak_range_m   = float(range_rect[peak_range_bin])
    peak_range_db  = float(p_rect_db[peak_range_bin])

    metrics["peak_range_m"]      = peak_range_m
    metrics["peak_range_bin"]    = peak_range_bin
    metrics["peak_range_db"]     = peak_range_db
    metrics["profile_dyn_db_rect"] = float(np.max(p_rect_db) - np.min(p_rect_db))
    metrics["profile_dyn_db_hann"] = float(np.max(p_hann_db) - np.min(p_hann_db))

    return metrics


# --------------------------------------------------------------------------
# Summary report
# --------------------------------------------------------------------------

def write_sweep_summary(
    pilot_result: SweepResult,
    pilot_metrics: dict,
    full_result: SweepResult | None,
    full_metrics: dict | None,
) -> None:
    lines = [
        "# RX-Only SFCW Sweep — Summary",
        "",
        "## Scientific honesty statement",
        "",
        "> **IMPORTANT**: This is a supervised RX-only infrastructure test.",
        "> - No RF was transmitted.",
        "> - No TX was used.",
        "> - H(f) = coherent mean of environmental RF/thermal noise at each "
        "tuned frequency.",
        "> - H(f) is NOT a radar transfer function from an emitted signal.",
        "> - The range profile is a processing pipeline validation, NOT target "
        "detection.",
        "> - This is NOT SAR imaging, NOT dielectric characterization,",
        ">   NOT a phantom measurement, NOT a medical or clinical test.",
        "> - True SFCW radar requires controlled TX/RX and background "
        "subtraction.",
        "",
        "## Safety attestation",
        "- RX-only.  No TX enabled.",
        "- No RF transmitted.",
        "- No motor movement.",
        "- No human subject.",
        "- Not a SAR scan.  Not a medical test.",
        "",
        "## Pilot sweep",
        f"- Mode:       {pilot_result.config.mode}",
        f"- Range:      {pilot_result.freqs_hz[0]/1e9:.3f} – "
        f"{pilot_result.freqs_hz[-1]/1e9:.3f} GHz",
        f"- Step:       {pilot_result.config.step_hz/1e6:.0f} MHz",
        f"- Captured:   {pilot_result.n_captured}/{len(pilot_result.freqs_hz)}",
        f"- Clipped:    {pilot_result.n_clipped}",
        f"- Failed:     {pilot_result.n_failed}",
        f"- Success:    {pilot_result.success}",
        "",
        "### Pilot H(f) metrics",
        f"- Bandwidth:          {pilot_metrics['bandwidth_mhz']:.1f} MHz",
        f"- Step:               {pilot_metrics['step_mhz']:.1f} MHz",
        f"- Range resolution:   {pilot_metrics['range_resolution_cm']:.1f} cm "
        f"({pilot_metrics['range_resolution_m']:.2f} m)",
        f"- Unambiguous range:  {pilot_metrics['unambiguous_range_m']:.1f} m",
        f"- Peak |H(f)| bin:    {pilot_metrics['peak_freq_mhz']:.1f} MHz  "
        f"({pilot_metrics['peak_magnitude_db']:.1f} dB)",
        f"- H(f) dynamic range: {pilot_metrics['dynamic_range_db']:.1f} dB",
        "",
        "### Pilot range profile",
        f"- Strongest range bin: {pilot_metrics['peak_range_m']:.3f} m  "
        f"({pilot_metrics['peak_range_db']:.1f} dB)",
        f"- Profile dynamic range (rect):   "
        f"{pilot_metrics['profile_dyn_db_rect']:.1f} dB",
        f"- Profile dynamic range (Hanning):{pilot_metrics['profile_dyn_db_hann']:.1f} dB",
        "",
    ]

    if full_result is not None and full_metrics is not None:
        lines += [
            "## Full sweep",
            f"- Mode:       {full_result.config.mode}",
            f"- Range:      {full_result.freqs_hz[0]/1e9:.3f} – "
            f"{full_result.freqs_hz[-1]/1e9:.3f} GHz",
            f"- Step:       {full_result.config.step_hz/1e6:.0f} MHz",
            f"- Captured:   {full_result.n_captured}/{len(full_result.freqs_hz)}",
            f"- Clipped:    {full_result.n_clipped}",
            f"- Failed:     {full_result.n_failed}",
            f"- Success:    {full_result.success}",
            "",
            "### Full H(f) metrics",
            f"- Bandwidth:          {full_metrics['bandwidth_mhz']:.1f} MHz",
            f"- Step:               {full_metrics['step_mhz']:.1f} MHz",
            f"- Range resolution:   {full_metrics['range_resolution_cm']:.1f} cm",
            f"- Unambiguous range:  {full_metrics['unambiguous_range_m']:.1f} m",
            f"- Peak |H(f)| bin:    {full_metrics['peak_freq_mhz']:.1f} MHz  "
            f"({full_metrics['peak_magnitude_db']:.1f} dB)",
            "",
            "### Full range profile",
            f"- Strongest range bin: {full_metrics['peak_range_m']:.3f} m  "
            f"({full_metrics['peak_range_db']:.1f} dB)",
            f"- Profile dynamic range (rect):   "
            f"{full_metrics['profile_dyn_db_rect']:.1f} dB",
            "",
        ]
    else:
        lines += [
            "## Full sweep",
            "- Full sweep was NOT run (pilot did not meet all go/no-go criteria).",
            "",
        ]

    lines += [
        "## Figures generated",
        f"- `reports/generated/rx_sfcw_pilot_h_magnitude_phase.png`",
        f"- `reports/generated/rx_sfcw_pilot_range_profile.png`",
    ]
    if full_result is not None:
        lines += [
            f"- `reports/generated/rx_sfcw_full_h_magnitude_phase.png`",
            f"- `reports/generated/rx_sfcw_full_range_profile.png`",
        ]

    out = REPORTS_DIR / "rx_sfcw_sweep_summary.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  Summary: {out}")


# --------------------------------------------------------------------------
# Go / no-go evaluation for full mode
# --------------------------------------------------------------------------

def evaluate_full_go_nogo(pilot: SweepResult) -> tuple[bool, list[str]]:
    """Return (go, reasons_list).  go=True means full mode should run."""
    reasons: list[str] = []
    go = True

    n_expected = len(pilot.freqs_hz)
    if pilot.n_captured < n_expected:
        go = False
        reasons.append(
            f"Pilot captured {pilot.n_captured}/{n_expected} -- must be 100%"
        )
    if pilot.n_clipped > 0:
        go = False
        reasons.append(f"Pilot had {pilot.n_clipped} clipped frequency/ies")
    if pilot.n_failed > 0:
        go = False
        reasons.append(f"Pilot had {pilot.n_failed} USB/capture error(s)")

    free_bytes = shutil.disk_usage(REPO_ROOT).free
    if free_bytes < MIN_FREE_DISK_BYTES:
        go = False
        reasons.append(
            f"Free disk {free_bytes/1e9:.2f} GB < required "
            f"{MIN_FREE_DISK_BYTES/1e9:.0f} GB"
        )

    return go, reasons


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    print_preflight()

    # Safety guard: never call configure_tx or transmit_tone in this script
    assert not hasattr(BladeRFDevice, "_tx_armed"), "Unexpected TX-arm attribute"

    # -------------------------------------------------------------------------
    # Pilot sweep
    # -------------------------------------------------------------------------
    print("\n[PILOT] Starting pilot sweep...")
    pilot_result = run_sweep_pass(PILOT_CONFIG, confirmation=CONFIRMATION)

    print(f"\n[PILOT] Analyzing and plotting...")
    pilot_metrics = analyze_and_plot(pilot_result, tag="pilot")

    print(f"\n[PILOT] H(f) metrics:")
    print(f"  BW={pilot_metrics['bandwidth_mhz']:.1f} MHz  "
          f"step={pilot_metrics['step_mhz']:.1f} MHz  "
          f"dr={pilot_metrics['range_resolution_cm']:.1f} cm  "
          f"R_unamb={pilot_metrics['unambiguous_range_m']:.1f} m")
    print(f"  Peak range bin: {pilot_metrics['peak_range_m']:.3f} m  "
          f"({pilot_metrics['peak_range_db']:.1f} dB)")

    # -------------------------------------------------------------------------
    # Go / no-go for full sweep
    # -------------------------------------------------------------------------
    full_result:  SweepResult | None = None
    full_metrics: dict | None        = None

    go, reasons = evaluate_full_go_nogo(pilot_result)

    if go:
        print(f"\n[FULL] Go / no-go: GO -- all conditions met.  Starting full sweep...")
        full_result  = run_sweep_pass(FULL_CONFIG, confirmation=CONFIRMATION)
        print(f"\n[FULL] Analyzing and plotting...")
        full_metrics = analyze_and_plot(full_result, tag="full")
        print(f"\n[FULL] H(f) metrics:")
        print(f"  BW={full_metrics['bandwidth_mhz']:.1f} MHz  "
              f"step={full_metrics['step_mhz']:.1f} MHz  "
              f"dr={full_metrics['range_resolution_cm']:.1f} cm  "
              f"R_unamb={full_metrics['unambiguous_range_m']:.1f} m")
        print(f"  Peak range bin: {full_metrics['peak_range_m']:.3f} m  "
              f"({full_metrics['peak_range_db']:.1f} dB)")
    else:
        print(f"\n[FULL] Go / no-go: NO-GO.  Full sweep skipped.")
        for r in reasons:
            print(f"  - {r}")

    # -------------------------------------------------------------------------
    # Summary report
    # -------------------------------------------------------------------------
    print("\n[REPORT] Writing sweep summary...")
    write_sweep_summary(pilot_result, pilot_metrics, full_result, full_metrics)

    # -------------------------------------------------------------------------
    # Final console summary
    # -------------------------------------------------------------------------
    print("\n" + "=" * 64)
    print("RESULT SUMMARY")
    print("=" * 64)
    print(f"  Pilot:  {pilot_result.n_captured}/{len(pilot_result.freqs_hz)} captured  "
          f"clipped={pilot_result.n_clipped}  failed={pilot_result.n_failed}  "
          f"success={pilot_result.success}")
    if full_result is not None:
        print(f"  Full:   {full_result.n_captured}/{len(full_result.freqs_hz)} captured  "
              f"clipped={full_result.n_clipped}  failed={full_result.n_failed}  "
              f"success={full_result.success}")
    else:
        print("  Full:   NOT RUN")
    print()
    print("INTERPRETATION")
    print("-" * 64)
    print("  H(f) = coherent mean of RX noise -- NOT a radar transfer function.")
    print("  Range profile = pipeline validation -- NOT object detection.")
    print("  No TX used.  No RF transmitted.  No motors.  No human subject.")
    print("  Not SAR imaging.  Not dielectric characterization.")
    print("  Not a medical or clinical test.")
    print("=" * 64)

    return 0 if pilot_result.success else 1


if __name__ == "__main__":
    sys.exit(main())
