"""
Small multi-block OFDM frequency-stitching pilot.

Tests the frequency stitching pipeline with a small number of OFDM RF blocks.
Uses processing/ofdm_block_stitcher.py to merge H[k] blocks into H_total(f).
Computes stitched CIR and relative distance-contrast profile.

RF center frequencies (conservative):
  Block 0: 2.390 GHz
  Block 1: 2.400 GHz
  Block 2: 2.410 GHz

Modes
-----
  --prepare-only   (default) Simulate 3 blocks from synthetic multi-path
                   channel, stitch, generate all figures. No hardware. No RF.
  --dry-run        Exercise capture path with fake device backend.
  --run-hardware   Real hardware 3-block capture and stitching.
  --analyze        Load existing stitched data and generate figures.

Safety
------
  Same as run_bladerf_ofdm_phase4_validation.py.
  No motor scan. No SAR scan. No clinical claims.
  TX gain: -20 dB. OFDM burst <= 10 ms per block.

Scientific note
---------------
  Three 2 MHz blocks at 10 MHz spacing provide:
    - Stitched coverage: 3 * ~1 MHz BW = ~23 MHz total span
    - Range resolution: c / (2 * 23 MHz) ~ 6.5 m
  This is a pipeline demonstration, not UWB performance.
  Full UWB performance requires hundreds of blocks or direct wideband hardware.
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
    capture_ofdm_block,
    summarize_ofdm_block_result,
)
from processing.ofdm_block_stitcher import (
    OFDMStitchBlock,
    stitch_ofdm_blocks,
    summarize_stitched_response,
)
from processing.ofdm_channel import channel_impulse_response, simulate_ofdm_channel_from_paths
from hardware.bladerf_device import BladeRFConfig, BladeRFDevice

REPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "reports", "generated",
)
RAW_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "raw", "ofdm_stitch_pilot",
)

# Conservative hardware defaults
FS_HZ = 2e6
BW_HZ = 2e6
RX_GAIN_DB = 20.0
TX_GAIN_DB = -20.0
N_FFT = 256
N_ACTIVE = 160
CP_LEN = 64
GUARD_BINS = 20

# Three RF centers for the pilot
BLOCK_CENTERS_HZ = [2.390e9, 2.400e9, 2.410e9]

C = 3e8


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mkdir(*paths: str) -> None:
    for p in paths:
        os.makedirs(p, exist_ok=True)


def _write_text(path: str, lines: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _ofdm_config_for(center_hz: float) -> OFDMBlockConfig:
    return OFDMBlockConfig(
        center_freq_hz=center_hz,
        sample_rate_hz=FS_HZ,
        bandwidth_hz=BW_HZ,
        n_fft=N_FFT, n_active=N_ACTIVE, cp_len=CP_LEN, guard_bins=GUARD_BINS,
        dc_null=True, pilot_type="bpsk", pilot_seed=42,
        repetitions=8,
        tx_gain_db=TX_GAIN_DB, rx_gain_db=RX_GAIN_DB,
    )


def _result_to_stitch_block(result) -> OFDMStitchBlock:
    # Sort by frequency so validate_blocks() passes (FFT ordering is not monotonic)
    sort_idx = np.argsort(result.freqs_hz)
    return OFDMStitchBlock(
        freqs_hz=result.freqs_hz[sort_idx].copy(),
        H=result.H_active[sort_idx].copy(),
        block_id=f"block_{result.config.center_freq_hz/1e6:.0f}MHz",
    )


def _stitched_range_profile(
    freqs_hz: np.ndarray,
    H_total: np.ndarray,
    n_half: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Compute range axis and normalised CIR magnitude from stitched H(f).

    Returns (range_m, contrast) where contrast = |CIR| / max(|CIR|).
    """
    N = len(H_total)
    if n_half is None:
        n_half = N // 2

    win = np.hanning(N)
    cir = np.fft.ifft(H_total * win) * N
    cir_mag = np.abs(cir)

    # Delay / range axis
    if len(freqs_hz) >= 2:
        df = float(freqs_hz[1] - freqs_hz[0])
        BW = N * df
        dt = 1.0 / BW
    else:
        dt = 1.0 / FS_HZ
    range_m = np.arange(N) * dt * C / 2.0

    contrast = cir_mag / (np.max(cir_mag) + 1e-15)
    return range_m, contrast


def _validate_stitched(freqs_hz: np.ndarray, H_total: np.ndarray) -> str:
    """Return 'PASS' or 'FAIL: ...'"""
    if not np.all(np.isfinite(H_total)):
        return "FAIL: H_total contains NaN or Inf"
    if len(freqs_hz) == 0:
        return "FAIL: empty frequency axis"
    diffs = np.diff(freqs_hz)
    if np.any(diffs <= 0):
        return "FAIL: frequency axis not sorted"
    if np.all(np.abs(H_total) < 1e-9):
        return "FAIL: H_total is all zeros"
    return "PASS"


# ---------------------------------------------------------------------------
# Mode: prepare-only (synthetic)
# ---------------------------------------------------------------------------

def run_prepare_only() -> str:
    """
    Simulate 3 OFDM blocks from a synthetic multi-path channel, stitch.

    Synthetic scenario:
      Reflector A at R = 0.5 m (amplitude 1.0)
      Reflector B at R = 1.5 m (amplitude 0.5)
      AWGN noise: std = 0.01

    Demonstrates: stitching pipeline, H_total(f), stitched CIR, range profile.
    """
    print("\n=== Phase 4G: Small Stitching Pilot (prepare-only, synthetic) ===")
    print("  Mode: prepare-only. No hardware. No RF. No clinical claims.")
    _mkdir(REPORT_DIR, RAW_DIR)

    # Synthetic scene
    paths = [(1.0 + 0j, 0.5), (0.5 + 0j, 1.5)]
    rng = np.random.default_rng(seed=99)
    noise_std = 0.01

    blocks = []
    for i, center_hz in enumerate(BLOCK_CENTERS_HZ):
        cfg = _ofdm_config_for(center_hz)
        from processing.ofdm_channel import allocate_active_subcarriers
        active_idx = allocate_active_subcarriers(
            cfg.n_fft, cfg.n_active, dc_null=cfg.dc_null, guard_bins=cfg.guard_bins
        )
        df = cfg.sample_rate_hz / cfg.n_fft
        n = cfg.n_fft
        shifts = np.where(active_idx <= n // 2, active_idx, active_idx - n).astype(float)
        freqs_hz = cfg.center_freq_hz + shifts * df

        H = simulate_ofdm_channel_from_paths(freqs_hz, paths, two_way=True)
        H += (rng.standard_normal(len(H)) + 1j * rng.standard_normal(len(H))) * noise_std

        # Sort by frequency (FFT ordering is not monotonic)
        sort_idx = np.argsort(freqs_hz)
        freqs_hz = freqs_hz[sort_idx]
        H = H[sort_idx]

        blk = OFDMStitchBlock(
            freqs_hz=freqs_hz,
            H=H,
            block_id=f"synth_{center_hz/1e6:.0f}MHz",
        )
        blocks.append(blk)
        print(f"  Block {i}: center={center_hz/1e9:.3f} GHz, "
              f"n_sub={len(freqs_hz)}, |H| mean={float(np.mean(np.abs(H))):.3f}")

    freqs_total, H_total = stitch_ofdm_blocks(blocks, use_overlap=True)
    bw_mhz = (float(freqs_total[-1]) - float(freqs_total[0])) / 1e6
    print(f"\n  Stitched n_sub  : {len(freqs_total)}")
    print(f"  Stitched BW     : {bw_mhz:.3f} MHz")

    gate = _validate_stitched(freqs_total, H_total)
    print(f"  Stitch validate : {gate}")

    range_m, contrast = _stitched_range_profile(freqs_total, H_total)
    n_half = len(H_total) // 2
    peak_idx = int(np.argmax(contrast[:n_half]))
    peak_range_m = float(range_m[peak_idx]) if len(range_m) > peak_idx else 0.0

    df_eff = float(freqs_total[1] - freqs_total[0]) if len(freqs_total) > 1 else 1.0
    BW_total = len(freqs_total) * df_eff
    dr_m = C / (2.0 * BW_total)
    print(f"  Range resolution: {dr_m*100:.1f} cm")
    print(f"  CIR peak at     : {peak_range_m*100:.1f} cm")

    _save_stitching_figures(
        blocks, freqs_total, H_total, range_m, contrast,
        peak_range_m, paths, "synthetic-prepare-only"
    )

    summary_txt = summarize_stitched_response(freqs_total, H_total)
    print(f"\n{summary_txt}")

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines = [
        "# Phase 4 Stitching Pilot Summary",
        "",
        f"Generated: {ts}",
        f"STITCHING_GATE: {gate}",
        "",
        "## Mode",
        "- prepare-only: synthetic data, no hardware, no RF",
        f"- 3 synthetic blocks at {[f'{c/1e9:.3f}' for c in BLOCK_CENTERS_HZ]} GHz",
        f"- Synthetic reflectors: A at 0.5m (amp 1.0), B at 1.5m (amp 0.5)",
        "",
        "## Stitched H(f)",
        summary_txt,
        "",
        "## Range Profile",
        f"- Range resolution: {dr_m*100:.1f} cm",
        f"- CIR peak: {peak_range_m*100:.1f} cm",
        "",
        "## Phase Offset Handling",
        "- overlap-based phase correction applied between blocks",
        "- no LO retune artifact since data is synthetic (no real phase jump)",
        "",
        "## Scientific Claims",
        "- Pipeline demonstration only. No real electromagnetic measurement.",
        "- 'perfil de contraste dielelectrico relativo' -- not absolute permittivity.",
        "- Real hardware stitching requires phase calibration between LO retunes.",
        "",
        f"## STITCHING_GATE: {gate}",
    ]
    summary_path = os.path.join(REPORT_DIR, "phase4_stitching_summary.md")
    _write_text(summary_path, lines)
    print(f"  Summary: {summary_path}")
    print(f"  STITCHING_GATE: {gate}")
    return gate


# ---------------------------------------------------------------------------
# Mode: dry-run (fake device)
# ---------------------------------------------------------------------------

class _FakeDevice:
    """Minimal fake device for dry-run mode."""
    def configure_tx(self): pass
    def configure_rx(self): pass
    def transmit_iq_burst(self, iq, **kwargs):
        return {"dry_run": True, "n_samples_tx": len(iq)}
    def capture_rx(self):
        rng = np.random.default_rng(seed=0)
        n = 2560
        return (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * 0.01
    def close(self): pass


def run_dry_run() -> str:
    """
    Exercise capture + stitching path with a fake device. No hardware. No RF.
    """
    print("\n=== Phase 4G: Stitching Pilot (dry-run) ===")
    print("  Mode: dry-run. Fake device backend. No hardware. No RF.")
    _mkdir(REPORT_DIR)

    blocks = []
    for center_hz in BLOCK_CENTERS_HZ:
        cfg = _ofdm_config_for(center_hz)
        device = _FakeDevice()
        result = capture_ofdm_block(device, cfg, dry_run=True)
        print(f"  Block {center_hz/1e9:.3f} GHz: "
              f"n_act={len(result.active_indices)}, "
              f"|H| mean={float(np.mean(np.abs(result.H_active))):.4f}")
        blk = _result_to_stitch_block(result)
        blocks.append(blk)

    freqs_total, H_total = stitch_ofdm_blocks(blocks, use_overlap=True)
    gate = _validate_stitched(freqs_total, H_total)

    range_m, contrast = _stitched_range_profile(freqs_total, H_total)
    n_half = len(H_total) // 2
    peak_idx = int(np.argmax(contrast[:n_half]))
    peak_range_m = float(range_m[peak_idx]) if len(range_m) > peak_idx else 0.0

    _save_stitching_figures(
        blocks, freqs_total, H_total, range_m, contrast,
        peak_range_m, None, "dry-run"
    )

    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary_txt = summarize_stitched_response(freqs_total, H_total)
    lines = [
        "# Phase 4 Stitching Pilot Summary (dry-run)",
        "",
        f"Generated: {ts}",
        f"STITCHING_GATE: {gate}",
        "",
        summary_txt,
        "",
        "## Notes",
        "- dry-run: fake device backend, identity channel (H approx 1)",
        "- CIR peak at delay 0 is expected with trivial channel",
        "",
        f"## STITCHING_GATE: {gate}",
    ]
    summary_path = os.path.join(REPORT_DIR, "phase4_stitching_summary.md")
    _write_text(summary_path, lines)
    print(f"  Summary: {summary_path}")
    print(f"  STITCHING_GATE: {gate}")
    return gate


# ---------------------------------------------------------------------------
# Mode: hardware
# ---------------------------------------------------------------------------

def run_hardware(confirmation: str, reflector_ready: str) -> str:
    """
    Capture 3 real OFDM blocks, stitch, save figures + summary.
    """
    print("\n=== Phase 4G: Stitching Pilot (hardware) ===")
    _mkdir(REPORT_DIR, RAW_DIR)

    blocks = []
    gate = "FAIL: unknown"
    ts_tag = time.strftime("%Y%m%d_%H%M%S")

    for i, center_hz in enumerate(BLOCK_CENTERS_HZ):
        device = None
        try:
            cfg_ofdm = _ofdm_config_for(center_hz)
            sym_len = cfg_ofdm.cp_len + cfg_ofdm.n_fft
            n_needed = sym_len * cfg_ofdm.repetitions

            hw_cfg = BladeRFConfig(
                center_freq_hz=center_hz,
                sample_rate_hz=FS_HZ,
                bandwidth_hz=BW_HZ,
                rx_gain_db=RX_GAIN_DB,
                tx_gain_db=TX_GAIN_DB,
                n_samples=n_needed,
                dry_run=False,
            )
            device = BladeRFDevice(hw_cfg, confirmation=confirmation)
            print(f"  Block {i}: {center_hz/1e9:.3f} GHz ...")

            result = capture_ofdm_block(
                device, cfg_ofdm,
                dry_run=False,
                confirmation=confirmation,
                reflector_setup_ready=reflector_ready,
            )
            print(f"    |H| mean={float(np.mean(np.abs(result.H_active))):.4f}")
            blk = _result_to_stitch_block(result)
            blocks.append(blk)

            raw_path = os.path.join(RAW_DIR, f"block{i}_{ts_tag}")
            os.makedirs(raw_path, exist_ok=True)
            np.save(os.path.join(raw_path, "H.npy"), result.H_active)
            np.save(os.path.join(raw_path, "freqs_hz.npy"), result.freqs_hz)

        except ImportError as exc:
            print(f"  SKIPPED block {i}: bladeRF not installed ({exc})")
            gate = f"SKIPPED: bladeRF not installed ({exc})"
            break
        except Exception as exc:
            print(f"  FAIL block {i}: {exc}")
            gate = f"FAIL at block {i}: {exc}"
            break
        finally:
            if device is not None:
                device.close()

    if not blocks:
        print(f"  STITCHING_GATE: {gate}")
        return gate

    try:
        freqs_total, H_total = stitch_ofdm_blocks(blocks, use_overlap=True)
        gate = _validate_stitched(freqs_total, H_total)
        range_m, contrast = _stitched_range_profile(freqs_total, H_total)
        n_half = len(H_total) // 2
        peak_idx = int(np.argmax(contrast[:n_half]))
        peak_range_m = float(range_m[peak_idx]) if len(range_m) > peak_idx else 0.0

        _save_stitching_figures(
            blocks, freqs_total, H_total, range_m, contrast,
            peak_range_m, None, f"hardware-{len(blocks)}-blocks"
        )

        summary_txt = summarize_stitched_response(freqs_total, H_total)
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        lines = [
            "# Phase 4 Stitching Pilot Summary (hardware)",
            "",
            f"Generated: {ts}",
            f"STITCHING_GATE: {gate}",
            "",
            summary_txt,
            "",
            "## Hardware Details",
            f"- Blocks: {[f'{c/1e9:.3f}' for c in BLOCK_CENTERS_HZ[:len(blocks)]]} GHz",
            f"- tx_gain_db: {TX_GAIN_DB:.1f} dB",
            "- Phase offset correction applied at block boundaries",
            "- LO retune phase jump cannot be fully removed without calibration",
            "",
            "## Scientific Claims",
            "- H_total(f) is a pilot estimate -- not a calibrated channel.",
            "- 'perfil de contraste dielelectrico relativo' -- not absolute permittivity.",
            "",
            f"## STITCHING_GATE: {gate}",
        ]
        summary_path = os.path.join(REPORT_DIR, "phase4_stitching_summary.md")
        _write_text(summary_path, lines)
        print(f"  Summary: {summary_path}")

    except Exception as exc:
        gate = f"FAIL: stitching error ({exc})"

    print(f"  STITCHING_GATE: {gate}")
    return gate


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

def _save_stitching_figures(
    blocks: list,
    freqs_total: np.ndarray,
    H_total: np.ndarray,
    range_m: np.ndarray,
    contrast: np.ndarray,
    peak_range_m: float,
    known_paths: list | None,
    mode_label: str,
) -> None:
    _mkdir(REPORT_DIR)
    n_half = len(H_total) // 2

    # 1. Stitched H magnitude per block + total
    fig, ax = plt.subplots(figsize=(10, 4))
    for blk in blocks:
        ax.plot(blk.freqs_hz / 1e6,
                20 * np.log10(np.abs(blk.H) + 1e-15),
                alpha=0.7, linewidth=0.8,
                label=f"Block {blk.block_id}")
    ax.plot(freqs_total / 1e6,
            20 * np.log10(np.abs(H_total) + 1e-15),
            "k--", linewidth=1.2, label="H_total (stitched)")
    ax.set_xlabel("Frequency [MHz]")
    ax.set_ylabel("|H[k]| [dB]")
    ax.set_title(f"Stitched H(f) -- {mode_label}")
    ax.legend(fontsize=7)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, "phase4_stitched_H_magnitude.png"), dpi=100)
    plt.close(fig)

    # 2. Stitched H phase
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(freqs_total / 1e6, np.degrees(np.angle(H_total)))
    ax.set_xlabel("Frequency [MHz]")
    ax.set_ylabel("Phase [deg]")
    ax.set_title("Stitched H(f) phase")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, "phase4_stitched_H_phase.png"), dpi=100)
    plt.close(fig)

    # 3. Stitched CIR / range profile
    fig, ax = plt.subplots(figsize=(9, 4))
    r_show = range_m[:n_half]
    ax.plot(r_show * 100, contrast[:n_half], color="navy", label="Stitched CIR")
    if known_paths is not None:
        for amp, R in known_paths:
            ax.axvline(R * 100, color="r", linestyle="--", alpha=0.7,
                       label=f"True reflector at {R*100:.0f} cm")
    ax.axvline(peak_range_m * 100, color="orange", linestyle=":",
               label=f"CIR peak at {peak_range_m*100:.0f} cm")
    ax.set_xlabel("One-way range [cm]")
    ax.set_ylabel("Relative contrast (normalised)")
    ax.set_title(
        "Stitched CIR -- relative dielectric-contrast profile\n"
        "(NOT absolute permittivity)"
    )
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, min(r_show[-1] * 100, 600))
    fig.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, "phase4_stitched_cir.png"), dpi=100)
    plt.close(fig)

    print("  Figures: stitched H_magnitude, H_phase, CIR saved")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Small OFDM stitching pilot. "
            "Default: --prepare-only (synthetic, no hardware)."
        )
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--prepare-only", action="store_true",
                   help="Synthetic demo -- no hardware (default).")
    g.add_argument("--dry-run", action="store_true",
                   help="Fake device backend -- no hardware.")
    g.add_argument("--run-hardware", action="store_true",
                   help="Real hardware 3-block capture + stitch.")
    g.add_argument("--analyze", action="store_true",
                   help="Analyze existing raw data and stitch.")
    parser.add_argument("--confirm", default=None, metavar="PHRASE")
    parser.add_argument("--reflector-ready", default=None, metavar="PHRASE")
    args = parser.parse_args()

    if not any([args.prepare_only, args.dry_run, args.run_hardware, args.analyze]):
        args.prepare_only = True

    if args.prepare_only:
        gate = run_prepare_only()
        print(f"\nFinal: STITCHING_GATE={gate}")
        return

    if args.dry_run:
        gate = run_dry_run()
        print(f"\nFinal: STITCHING_GATE={gate}")
        return

    if args.analyze:
        # Load existing raw data and re-stitch
        print("\n=== Stitching Pilot: Analyze ===")
        _mkdir(RAW_DIR)
        blocks = []
        for entry in sorted(os.listdir(RAW_DIR)):
            path = os.path.join(RAW_DIR, entry)
            if not os.path.isdir(path):
                continue
            h_path = os.path.join(path, "H.npy")
            f_path = os.path.join(path, "freqs_hz.npy")
            if not (os.path.exists(h_path) and os.path.exists(f_path)):
                continue
            H = np.load(h_path)
            freqs_hz = np.load(f_path)
            blocks.append(OFDMStitchBlock(
                freqs_hz=freqs_hz, H=H, block_id=entry
            ))
        if not blocks:
            print("  No data found in RAW_DIR.")
            return
        freqs_total, H_total = stitch_ofdm_blocks(blocks, use_overlap=True)
        gate = _validate_stitched(freqs_total, H_total)
        range_m, contrast = _stitched_range_profile(freqs_total, H_total)
        n_half = len(H_total) // 2
        peak_idx = int(np.argmax(contrast[:n_half]))
        peak_range_m = float(range_m[peak_idx]) if len(range_m) > peak_idx else 0.0
        _save_stitching_figures(blocks, freqs_total, H_total, range_m, contrast,
                                peak_range_m, None, "analyze")
        print(f"\nFinal: STITCHING_GATE={gate}")
        return

    if args.run_hardware:
        if args.confirm == "CONFIRM HARDWARE RUN":
            confirmation = args.confirm
        else:
            print("\n  Enter: CONFIRM HARDWARE RUN")
            confirmation = input("  Confirmation: ").strip()
        if args.reflector_ready == "REFLECTOR SETUP READY":
            reflector_ready = args.reflector_ready
        else:
            print("  Enter: REFLECTOR SETUP READY")
            reflector_ready = input("  Reflector: ").strip()
        gate = run_hardware(confirmation, reflector_ready)
        print(f"\nFinal: STITCHING_GATE={gate}")


if __name__ == "__main__":
    main()
