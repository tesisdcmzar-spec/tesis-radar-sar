"""
OFDM background/object channel-difference profile.

Estimates a relative dielectric-contrast indicator versus distance by comparing
an OFDM block captured without an object (background) and one with an object
(test reflector at known distance).

Pipeline
--------
  H_delta[k] = H_object[k] - H_background[k]
  CIR_delta   = IFFT(H_delta * Hanning window)
  range_axis  = two-way propagation from delay axis
  contrast(r) = |CIR_delta(r)| / max(|CIR_delta|)

This is NOT absolute permittivity mapping.
Output is labeled as:
  'perfil de contraste dielelectrico relativo'
  'relative dielectric-contrast profile'
  'estimacion preliminar de region reflectiva en distancia'
  'no calibrado en permitividad absoluta'

Modes
-----
  --prepare-only   (default) Synthesize BG + OBJ from known paths, run
                   full pipeline, generate figures. No hardware. No RF.
  --background     Capture real bladeRF background block.
  --object         Capture real bladeRF object block.
  --analyze        Load latest background + object data and compute profile.
  --run-sequence   Capture background, then object, then analyze (hardware).

Safety
------
  Same as run_bladerf_ofdm_phase4_validation.py.
  No clinical claims. No absolute permittivity.
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
    "data", "raw", "ofdm_bg_obj",
)

# Hardware defaults (conservative)
CENTER_HZ = 2.4e9
FS_HZ = 2e6
BW_HZ = 2e6
RX_GAIN_DB = 20.0
TX_GAIN_DB = -20.0

# Speed of light [m/s]
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


def _default_ofdm_config() -> OFDMBlockConfig:
    return OFDMBlockConfig(
        center_freq_hz=CENTER_HZ,
        sample_rate_hz=FS_HZ,
        bandwidth_hz=BW_HZ,
        n_fft=256, n_active=160, cp_len=64, guard_bins=20,
        dc_null=True, pilot_type="bpsk", pilot_seed=42,
        repetitions=8,
        tx_gain_db=TX_GAIN_DB, rx_gain_db=RX_GAIN_DB,
    )


def _range_axis_from_h(freqs_hz: np.ndarray) -> tuple[np.ndarray, float]:
    """
    Compute two-way range axis from a uniform frequency grid.

    Returns (range_m, dr_m) where dr_m is the range resolution bin size.
    For frequency spacing df and N points:
      dt = 1/(N*df) -> dr_two_way = c*dt/2 = c/(2*N*df) = c/(2*BW)
    """
    N = len(freqs_hz)
    if N < 2:
        return np.array([0.0]), 0.0
    df = float(freqs_hz[1] - freqs_hz[0])
    BW = N * df
    dt = 1.0 / BW          # delay per CIR bin [s]
    dr = C * dt / 2.0      # range per bin (two-way) [m]
    t_axis = np.arange(N) * dt
    range_m = t_axis * C / 2.0
    return range_m, dr


def _compute_contrast_profile(
    H_bg: np.ndarray,
    H_obj: np.ndarray,
    freqs_hz: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """
    Compute H_delta, CIR_delta, contrast profile, and peak range.

    Returns (H_delta, cir_delta, contrast_profile, peak_range_m)
    """
    H_delta = H_obj - H_bg
    N = len(H_delta)
    win = np.hanning(N)
    cir_delta = np.fft.ifft(H_delta * win) * N

    cir_mag = np.abs(cir_delta)
    contrast = cir_mag / (np.max(cir_mag) + 1e-15)

    range_m, dr = _range_axis_from_h(freqs_hz)
    # Only look at the causal part (first half)
    half = N // 2
    peak_idx = int(np.argmax(contrast[:half]))
    peak_range = float(range_m[peak_idx]) if len(range_m) > peak_idx else 0.0

    return H_delta, cir_delta, contrast, peak_range


# ---------------------------------------------------------------------------
# Synthetic channel helpers
# ---------------------------------------------------------------------------

def _synthetic_h(
    freqs_hz: np.ndarray,
    paths: list[tuple[float, float]],
    noise_std: float = 0.02,
    seed: int = 7,
) -> np.ndarray:
    """
    Simulate H(f) = sum_i a_i * exp(-j*4*pi*f*R_i/c) + noise.

    paths: list of (amplitude, range_m) tuples.
    """
    H = np.zeros(len(freqs_hz), dtype=complex)
    for amp, R in paths:
        H += amp * np.exp(-1j * 4.0 * np.pi * freqs_hz * R / C)
    rng = np.random.default_rng(seed=seed)
    H += (rng.standard_normal(len(H)) + 1j * rng.standard_normal(len(H))) * noise_std
    return H


def _synthetic_prepare() -> dict:
    """
    Build synthetic BG and OBJ channel estimates.

    Scenario:
      BW = 500 MHz (represents multi-block stitched result)
      Background: internal cable/antenna path at R_bg = 0.30 m (30 cm cable equivalent)
      Object: same background + reflector at R_obj = 1.0 m (two-way)
      H_delta = reflector contribution at 1.0 m

    Range resolution at 500 MHz: dr = c/(2*500 MHz) = 0.30 m
    """
    f_start = 2.0e9
    f_end = 2.5e9
    N = 500
    freqs_hz = np.linspace(f_start, f_end, N)

    # Background: cable/antenna response (simulates clutter, not real object)
    H_bg = _synthetic_h(freqs_hz, [(1.0, 0.30)], noise_std=0.02, seed=11)

    # Object: background + reflector at 1.0 m
    H_obj = _synthetic_h(freqs_hz, [(1.0, 0.30), (0.5, 1.0)], noise_std=0.02, seed=17)

    return dict(freqs_hz=freqs_hz, H_bg=H_bg, H_obj=H_obj, known_range_m=1.0,
                mode="synthetic-prepare-only",
                note="500 MHz BW -- represents stitched multi-block result. Not real hardware.")


# ---------------------------------------------------------------------------
# Figure generation
# ---------------------------------------------------------------------------

def _save_bg_obj_figures(
    freqs_hz: np.ndarray,
    H_bg: np.ndarray,
    H_obj: np.ndarray,
    H_delta: np.ndarray,
    cir_delta: np.ndarray,
    contrast: np.ndarray,
    peak_range_m: float,
    known_range_m: float | None,
    mode_label: str,
    prefix: str = "background_object",
) -> None:
    _mkdir(REPORT_DIR)
    freqs_mhz = freqs_hz / 1e6
    range_m, dr = _range_axis_from_h(freqs_hz)
    N = len(H_bg)
    half = N // 2

    # Derive file names from prefix
    p = f"phase4_{prefix}"

    # 1. H magnitude comparison (BG vs OBJ)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(freqs_mhz, 20*np.log10(np.abs(H_bg)+1e-15), label="H_bg", alpha=0.8)
    ax.plot(freqs_mhz, 20*np.log10(np.abs(H_obj)+1e-15), label="H_obj", alpha=0.8)
    ax.set_xlabel("Frequency [MHz]")
    ax.set_ylabel("|H[k]| [dB]")
    ax.set_title(f"Channel magnitude: background vs object ({mode_label})")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, f"{p}_H_background_object.png"), dpi=100)
    plt.close(fig)

    # 2. H phase comparison
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(freqs_mhz, np.degrees(np.angle(H_bg)), label="H_bg", alpha=0.8)
    ax.plot(freqs_mhz, np.degrees(np.angle(H_obj)), label="H_obj", alpha=0.8)
    ax.set_xlabel("Frequency [MHz]")
    ax.set_ylabel("Phase [deg]")
    ax.set_title("Channel phase: background vs object")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, f"{p}_H_phase.png"), dpi=100)
    plt.close(fig)

    # 3. H_delta magnitude
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(freqs_mhz, 20*np.log10(np.abs(H_delta)+1e-15), color="red", alpha=0.9)
    ax.set_xlabel("Frequency [MHz]")
    ax.set_ylabel("|H_delta[k]| [dB]")
    ax.set_title("H_delta = H_obj - H_bg  (channel difference)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, f"{p}_delta_H.png"), dpi=100)
    plt.close(fig)

    # 4. Relative contrast profile vs range
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(range_m[:half]*100, contrast[:half], color="navy")
    if known_range_m is not None:
        ax.axvline(known_range_m * 100, color="r", linestyle="--",
                   label=f"Known object at {known_range_m*100:.0f} cm")
    ax.axvline(peak_range_m * 100, color="orange", linestyle=":",
               label=f"CIR peak at {peak_range_m*100:.0f} cm")
    ax.set_xlabel("One-way range [cm]")
    ax.set_ylabel("Relative contrast (normalised to 1.0)")
    ax.set_title(
        "Relative dielectric-contrast profile vs distance\n"
        "(NOT absolute permittivity -- no calibration)"
    )
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(0, min(range_m[half-1]*100, 500))
    fig.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, f"{p}_contrast_vs_distance.png"), dpi=100)
    plt.close(fig)

    # 5. Distance-contrast heatmap (1 azimuth column -> 1D as 2D image)
    fig, ax = plt.subplots(figsize=(4, 7))
    half_contrast = contrast[:half].reshape(-1, 1)
    extent_r = [0, 1, range_m[half-1]*100, 0]
    im = ax.imshow(half_contrast, aspect="auto", cmap="hot",
                   extent=extent_r, vmin=0, vmax=1)
    plt.colorbar(im, ax=ax, label="Relative contrast")
    if known_range_m is not None:
        ax.axhline(known_range_m * 100, color="c", linestyle="--",
                   linewidth=1.5, label=f"Object at {known_range_m*100:.0f} cm")
    ax.set_xlabel("Azimuth (single position)")
    ax.set_ylabel("One-way range [cm]")
    ax.set_title(
        "Relative dielectric-contrast heatmap\n"
        "(1 azimuth position -- not SAR image)"
    )
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(os.path.join(REPORT_DIR, f"{p}_distance_heatmap.png"), dpi=100)
    plt.close(fig)

    print(f"  Figures: {p}_H_background_object, H_phase, delta_H, contrast_profile, heatmap saved")


# ---------------------------------------------------------------------------
# Mode: prepare-only (synthetic)
# ---------------------------------------------------------------------------

def run_prepare_only() -> str:
    """
    Synthetic BG/OBJ demo. No hardware. No RF.

    Returns gate string.
    """
    print("\n=== Phase 4F: Background/Object Profile (prepare-only, synthetic) ===")
    print("  Mode: prepare-only. No hardware. No RF. No clinical claims.")
    _mkdir(REPORT_DIR, RAW_DIR)

    data = _synthetic_prepare()
    freqs_hz = data["freqs_hz"]
    H_bg = data["H_bg"]
    H_obj = data["H_obj"]
    known_range_m = data["known_range_m"]
    bw_mhz = (freqs_hz[-1] - freqs_hz[0]) / 1e6

    print(f"  Synthetic BW    : {bw_mhz:.0f} MHz (stitched representation)")
    print(f"  N_freq points   : {len(freqs_hz)}")
    print(f"  Known object at : {known_range_m*100:.0f} cm")

    H_delta, cir_delta, contrast, peak_range_m = _compute_contrast_profile(
        H_bg, H_obj, freqs_hz
    )

    _, dr = _range_axis_from_h(freqs_hz)
    print(f"  Range resolution: {dr*100:.1f} cm")
    print(f"  CIR peak at     : {peak_range_m*100:.1f} cm")
    print(f"  Known object at : {known_range_m*100:.0f} cm")
    err_cm = abs(peak_range_m - known_range_m) * 100
    print(f"  Peak-to-object  : {err_cm:.1f} cm error")

    _save_bg_obj_figures(
        freqs_hz, H_bg, H_obj, H_delta, cir_delta, contrast,
        peak_range_m, known_range_m, "synthetic-prepare-only",
        prefix="synthetic",
    )

    # Assertions
    assert np.all(np.isfinite(H_delta)), "H_delta contains NaN/Inf"
    assert np.all(np.isfinite(cir_delta)), "CIR_delta contains NaN/Inf"
    assert np.all(np.isfinite(contrast)), "contrast contains NaN/Inf"
    assert peak_range_m >= 0, "peak_range_m must be >= 0"

    gate = "PASS"

    # Summary
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines = [
        "# Phase 4 Synthetic Background/Object Profile Summary",
        "",
        f"Generated: {ts}",
        f"BACKGROUND_OBJECT_GATE: {gate}",
        "",
        "## Mode",
        "- prepare-only: synthetic data, no hardware, no RF",
        f"- Synthetic BW: {bw_mhz:.0f} MHz (represents stitched multi-block result)",
        f"- Background: synthetic cable path at 30 cm",
        f"- Object: synthetic reflector at {known_range_m*100:.0f} cm",
        "",
        "## Pipeline",
        "- H_delta[k] = H_object[k] - H_background[k]",
        "- CIR_delta = IFFT(H_delta * Hanning window)",
        "- contrast(r) = |CIR_delta(r)| / max(|CIR_delta|)",
        "",
        "## Results",
        f"- Range resolution: {dr*100:.1f} cm (= c / (2 * BW))",
        f"- CIR peak range: {peak_range_m*100:.1f} cm",
        f"- Known object range: {known_range_m*100:.0f} cm",
        f"- Peak-to-object error: {err_cm:.1f} cm",
        "",
        "## Scientific Claims",
        "- Output: 'relative dielectric-contrast profile' (perfil de contraste dielelectrico relativo).",
        "- NOT absolute permittivity. NOT calibrated. NOT validated for dielectric characterization.",
        "- Peak indicates strong channel-difference at that range -- consistent with a reflector.",
        "- Calibration with known phantom/reference needed for epsilon_r estimation.",
        "",
        "## Figures",
        "- phase4_synthetic_H_background_object.png",
        "- phase4_synthetic_H_phase.png",
        "- phase4_synthetic_delta_H.png",
        "- phase4_synthetic_contrast_vs_distance.png",
        "- phase4_synthetic_distance_heatmap.png",
        "",
        f"## BACKGROUND_OBJECT_GATE: {gate}",
    ]
    summary_path = os.path.join(REPORT_DIR, "phase4_synthetic_background_object_summary.md")
    _write_text(summary_path, lines)
    print(f"  Summary: {summary_path}")
    print(f"  BACKGROUND_OBJECT_GATE: {gate}")
    return gate


# ---------------------------------------------------------------------------
# Mode: hardware background/object capture
# ---------------------------------------------------------------------------

def _hw_capture_block(label: str, confirmation: str, reflector_ready: str) -> str | None:
    """
    Capture one OFDM block with real hardware. Save H and freqs_hz.

    Returns path to raw data directory, or None on failure.
    """
    _mkdir(RAW_DIR)
    device = None

    try:
        cfg_ofdm = _default_ofdm_config()
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
        print(f"  Capturing {label} OFDM block at {CENTER_HZ/1e9:.3f} GHz ...")

        result = capture_ofdm_block(
            device, cfg_ofdm,
            dry_run=False,
            confirmation=confirmation,
            reflector_setup_ready=reflector_ready,
        )
        print(summarize_ofdm_block_result(result))

        ts_tag = time.strftime("%Y%m%d_%H%M%S")
        raw_path = os.path.join(RAW_DIR, f"{label}_{ts_tag}")
        os.makedirs(raw_path, exist_ok=True)
        np.save(os.path.join(raw_path, "H.npy"), result.H_active)
        np.save(os.path.join(raw_path, "freqs_hz.npy"), result.freqs_hz)
        # Write a label file so analysis can identify capture type
        with open(os.path.join(raw_path, "label.txt"), "w") as f:
            f.write(label)
        print(f"  Saved: {raw_path}")
        return raw_path

    except ImportError as exc:
        print(f"  SKIPPED: bladeRF not installed ({exc})")
        return None
    except Exception as exc:
        print(f"  FAIL: {exc}")
        return None
    finally:
        if device is not None:
            device.close()


def run_background_hw(confirmation: str, reflector_ready: str) -> str:
    """Capture hardware background block. Returns gate."""
    print("\n=== Capturing background (no object) ===")
    path = _hw_capture_block("background", confirmation, reflector_ready)
    if path is None:
        gate = "FAIL: hardware capture failed"
    else:
        gate = f"PASS (data at {path})"
    print(f"  Background capture gate: {gate}")
    return gate


def run_object_hw(confirmation: str, reflector_ready: str) -> str:
    """Capture hardware object block. Returns gate."""
    print("\n=== Capturing object (reflector in place) ===")
    path = _hw_capture_block("object", confirmation, reflector_ready)
    if path is None:
        gate = "FAIL: hardware capture failed"
    else:
        gate = f"PASS (data at {path})"
    print(f"  Object capture gate: {gate}")
    return gate


def run_analyze() -> str:
    """
    Load latest background and object captures and compute contrast profile.

    Returns gate.
    """
    print("\n=== Analyzing background/object captures ===")
    _mkdir(RAW_DIR)

    # Find latest background and object directories
    def _latest_dir(label: str) -> str | None:
        dirs = [
            d for d in os.listdir(RAW_DIR)
            if os.path.isdir(os.path.join(RAW_DIR, d)) and d.startswith(label)
        ]
        if not dirs:
            return None
        dirs.sort()
        return os.path.join(RAW_DIR, dirs[-1])

    bg_dir = _latest_dir("background")
    obj_dir = _latest_dir("object")

    if bg_dir is None or obj_dir is None:
        msg = f"FAIL: missing captures (bg={bg_dir}, obj={obj_dir})"
        print(f"  {msg}")
        return msg

    try:
        H_bg = np.load(os.path.join(bg_dir, "H.npy"))
        H_obj = np.load(os.path.join(obj_dir, "H.npy"))
        freqs_hz = np.load(os.path.join(bg_dir, "freqs_hz.npy"))
    except Exception as exc:
        gate = f"FAIL: cannot load data ({exc})"
        print(f"  {gate}")
        return gate

    if H_bg.shape != H_obj.shape:
        gate = f"FAIL: shape mismatch H_bg={H_bg.shape} vs H_obj={H_obj.shape}"
        print(f"  {gate}")
        return gate

    H_delta, cir_delta, contrast, peak_range_m = _compute_contrast_profile(
        H_bg, H_obj, freqs_hz
    )
    _, dr = _range_axis_from_h(freqs_hz)
    print(f"  Range resolution : {dr*100:.1f} cm")
    print(f"  CIR peak at      : {peak_range_m*100:.1f} cm")

    _save_bg_obj_figures(
        freqs_hz, H_bg, H_obj, H_delta, cir_delta, contrast,
        peak_range_m, None, "hardware",
        prefix="background_object",
    )

    if not np.all(np.isfinite(contrast)):
        return "FAIL: contrast profile contains NaN/Inf"

    gate = "PASS"
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines = [
        "# Phase 4 Background/Object Analysis Summary",
        "",
        f"Generated: {ts}",
        f"BACKGROUND_OBJECT_GATE: {gate}",
        "",
        "## Data Sources",
        f"- background: {bg_dir}",
        f"- object: {obj_dir}",
        "",
        "## Pipeline",
        "- H_delta[k] = H_obj[k] - H_bg[k]",
        "- CIR_delta = IFFT(H_delta * Hanning)",
        "- contrast(r) = |CIR_delta(r)| / max(|CIR_delta|)",
        "",
        "## Results",
        f"- Range resolution: {dr*100:.1f} cm",
        f"- CIR peak range: {peak_range_m*100:.1f} cm",
        "- NOTE: single-block BW ~ 1 MHz -> range resolution ~ 150 m",
        "  Peak at bin 0 is expected. UWB stitching needed for sub-meter resolution.",
        "",
        "## Scientific Claims",
        "- 'perfil de contraste dielelectrico relativo' -- not absolute permittivity.",
        "- No clinical claims. No dielectric permittivity mapping.",
        "",
        f"## BACKGROUND_OBJECT_GATE: {gate}",
    ]
    summary_path = os.path.join(REPORT_DIR, "phase4_background_object_summary.md")
    _write_text(summary_path, lines)
    print(f"  Summary: {summary_path}")
    print(f"  BACKGROUND_OBJECT_GATE: {gate}")
    return gate


# ---------------------------------------------------------------------------
# Dry-run mode (fake device backend)
# ---------------------------------------------------------------------------

class _FakeBgObjDevice:
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


def _run_dry_run_mode() -> str:
    """
    Dry-run: exercise capture code path with fake device, then compute contrast profile.
    """
    print("\n=== Background/Object Profile (dry-run) ===")
    print("  Mode: dry-run. Fake device backend. No hardware. No RF.")
    _mkdir(REPORT_DIR)

    cfg = _default_ofdm_config()
    rng = np.random.default_rng(seed=1)

    result_bg = capture_ofdm_block(_FakeBgObjDevice(), cfg, dry_run=True)
    result_obj = capture_ofdm_block(_FakeBgObjDevice(), cfg, dry_run=True)
    # Manually perturb obj H to simulate a difference
    H_obj_perturbed = result_obj.H_active + (
        rng.standard_normal(len(result_obj.H_active))
        + 1j * rng.standard_normal(len(result_obj.H_active))
    ) * 0.5

    H_bg = result_bg.H_active
    freqs_hz = result_bg.freqs_hz
    H_delta, cir_delta, contrast, peak_range_m = _compute_contrast_profile(
        H_bg, H_obj_perturbed, freqs_hz
    )
    _, dr = _range_axis_from_h(freqs_hz)
    print(f"  Range resolution: {dr*100:.1f} cm")
    print(f"  CIR peak at     : {peak_range_m*100:.1f} cm")

    _save_bg_obj_figures(
        freqs_hz, H_bg, H_obj_perturbed, H_delta, cir_delta, contrast,
        peak_range_m, None, "dry-run",
        prefix="synthetic",
    )

    gate = "PASS" if np.all(np.isfinite(contrast)) else "FAIL: contrast has NaN/Inf"
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    lines = [
        "# Phase 4 Background/Object Dry-Run Summary",
        "",
        f"Generated: {ts}",
        f"BACKGROUND_OBJECT_GATE: {gate}",
        "",
        "## Mode: dry-run (fake device backend)",
        "- No hardware. No RF. No bladeRF.",
        "- Fake captures with added perturbation to simulate object difference.",
        "",
        f"## BACKGROUND_OBJECT_GATE: {gate}",
    ]
    summary_path = os.path.join(REPORT_DIR, "phase4_synthetic_background_object_summary.md")
    _write_text(summary_path, lines)
    print(f"  Summary: {summary_path}")
    print(f"  BACKGROUND_OBJECT_GATE: {gate}")
    return gate


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "OFDM background/object contrast profile. "
            "Default: --prepare-only (synthetic, no hardware)."
        )
    )
    g = parser.add_mutually_exclusive_group()
    g.add_argument("--prepare-only", action="store_true",
                   help="Synthetic demo -- no hardware (default).")
    g.add_argument("--dry-run", action="store_true",
                   help="Fake device backend -- exercises capture path.")
    g.add_argument("--background", action="store_true",
                   help="Capture hardware background block.")
    g.add_argument("--object", action="store_true",
                   help="Capture hardware object block.")
    g.add_argument("--analyze", action="store_true",
                   help="Analyze existing background+object data.")
    g.add_argument("--run-sequence", action="store_true",
                   help="Background + object + analyze (hardware).")
    parser.add_argument("--confirm", default=None, metavar="PHRASE")
    parser.add_argument("--reflector-ready", default=None, metavar="PHRASE")
    args = parser.parse_args()

    needs_hw = args.background or args.object or args.run_sequence
    if not (args.prepare_only or getattr(args, "dry_run", False) or args.background
            or args.object or args.analyze or args.run_sequence):
        args.prepare_only = True

    if args.prepare_only:
        gate = run_prepare_only()
        print(f"\nFinal: BACKGROUND_OBJECT_GATE={gate}")
        return

    if getattr(args, "dry_run", False):
        gate = _run_dry_run_mode()
        print(f"\nFinal: BACKGROUND_OBJECT_GATE={gate}")
        return

    if args.analyze:
        gate = run_analyze()
        print(f"\nFinal: BACKGROUND_OBJECT_GATE={gate}")
        return

    # Hardware modes need confirmation
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

    if args.background:
        gate = run_background_hw(confirmation, reflector_ready)
        print(f"\nFinal: {gate}")
    elif args.object:
        gate = run_object_hw(confirmation, reflector_ready)
        print(f"\nFinal: {gate}")
    elif args.run_sequence:
        print("\n=== Background/Object Full Sequence ===")
        bg_gate = run_background_hw(confirmation, reflector_ready)
        if bg_gate.startswith("FAIL"):
            print(f"HARD STOP: background failed: {bg_gate}")
            return
        input("\n  Place reflector in position, then press Enter to continue ...")
        obj_gate = run_object_hw(confirmation, reflector_ready)
        if obj_gate.startswith("FAIL"):
            print(f"HARD STOP: object capture failed: {obj_gate}")
            return
        analyze_gate = run_analyze()
        print(f"\nFinal gates:")
        print(f"  Background: {bg_gate}")
        print(f"  Object: {obj_gate}")
        print(f"  BACKGROUND_OBJECT_GATE: {analyze_gate}")


if __name__ == "__main__":
    main()
