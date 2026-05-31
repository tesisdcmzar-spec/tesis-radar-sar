"""
Dry-run demonstration of the bladeRF hardware abstraction layer.

Loads configs/bladerf_dry_run.yaml, instantiates BladeRFDevice in dry-run
mode, exercises all public methods, and writes a summary and a preview figure
to reports/generated/.

Run from repo root:
    py experiments/run_bladerf_dry_run.py

No bladeRF hardware required.  No RF is transmitted.  No USB access.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from hardware.bladerf_device import BladeRFConfig, BladeRFDevice


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "configs" / "bladerf_dry_run.yaml"
OUT_DIR = REPO_ROOT / "reports" / "generated"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Helper for offline config loading (importable for tests)
# ---------------------------------------------------------------------------

def load_bladerf_config_from_yaml(yaml_path: Path) -> BladeRFConfig:
    """Load a BladeRFConfig from a YAML file."""
    with open(yaml_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    hw = raw["hardware"]
    return BladeRFConfig(
        center_freq_hz=float(hw["center_freq_hz"]),
        sample_rate_hz=float(hw["sample_rate_hz"]),
        bandwidth_hz=float(hw["bandwidth_hz"]),
        rx_gain_db=float(hw["rx_gain_db"]),
        tx_gain_db=float(hw["tx_gain_db"]),
        n_samples=int(hw["n_samples"]),
        channel=str(hw.get("channel", "x1")),
        dry_run=bool(hw.get("dry_run", True)),
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("bladeRF dry-run demonstration")
    print("=" * 40)
    print(f"Config: {CONFIG_PATH}")
    print(f"Output: {OUT_DIR}")
    print()

    # ---- Load config -------------------------------------------------------
    config = load_bladerf_config_from_yaml(CONFIG_PATH)
    print(f"  dry_run           = {config.dry_run}")
    print(f"  center_freq_hz    = {config.center_freq_hz/1e6:.1f} MHz")
    print(f"  sample_rate_hz    = {config.sample_rate_hz/1e6:.1f} MS/s")
    print(f"  bandwidth_hz      = {config.bandwidth_hz/1e6:.1f} MHz")
    print(f"  rx_gain_db        = {config.rx_gain_db:.1f} dB")
    print(f"  tx_gain_db        = {config.tx_gain_db:.1f} dB (placeholder)")
    print(f"  n_samples         = {config.n_samples:,}")
    print(f"  channel           = {config.channel}")
    print()

    # ---- Instantiate device ------------------------------------------------
    print("Creating BladeRFDevice ...")
    device = BladeRFDevice(config)

    # ---- Configure ---------------------------------------------------------
    print("configure_rx() ...")
    device.configure_rx()

    print("configure_tx() ...")
    device.configure_tx()

    # ---- Capture -----------------------------------------------------------
    print("capture_rx() ...")
    iq = device.capture_rx()
    print(f"  IQ shape  = {iq.shape}")
    print(f"  IQ dtype  = {iq.dtype}")
    print(f"  |IQ| mean = {np.mean(np.abs(iq)):.6f}")
    print(f"  |IQ| std  = {np.std(np.abs(iq)):.6f}")

    # ---- Transmit tone (dry-run — no RF) -----------------------------------
    print("transmit_tone() [dry-run: no RF] ...")
    device.transmit_tone(freq_offset_hz=1e6, amplitude=0.5, duration_s=0.001)

    # ---- Status ------------------------------------------------------------
    st = device.status()
    print("status():")
    for k, v in st.items():
        print(f"  {k}: {v}")

    # ---- Close -------------------------------------------------------------
    print("close() ...")
    device.close()
    print()

    # ---- Figure: IQ preview ------------------------------------------------
    print("Generating IQ preview figure ...")
    n_preview = min(200, len(iq))
    t_us = np.arange(n_preview) / (config.sample_rate_hz / 1e6)  # time in microseconds

    fig, axes = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
    axes[0].plot(t_us, iq[:n_preview].real, linewidth=0.8, color="steelblue")
    axes[0].set_ylabel("I (real)")
    axes[0].set_title(
        f"bladeRF dry-run IQ preview -- {n_preview} samples @ "
        f"{config.sample_rate_hz/1e6:.0f} MS/s, {config.center_freq_hz/1e6:.0f} MHz "
        f"(synthetic noise)"
    )
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(t_us, iq[:n_preview].imag, linewidth=0.8, color="darkorange")
    axes[1].set_ylabel("Q (imag)")
    axes[1].set_xlabel("Time [us]")
    axes[1].grid(True, alpha=0.3)

    plt.tight_layout()
    fig_path = OUT_DIR / "bladerf_dry_run_iq_preview.png"
    fig.savefig(fig_path, dpi=150)
    plt.close(fig)
    print(f"  Saved -> {fig_path}")

    # ---- Markdown summary --------------------------------------------------
    print("Writing summary ...")
    summary = f"""\
# bladeRF Dry-Run Summary

**Script:** `experiments/run_bladerf_dry_run.py`
**Config:** `configs/bladerf_dry_run.yaml`
**Hardware used:** None -- dry-run mode only.

---

## Configuration

| Parameter | Value |
|-----------|-------|
| center_freq_hz | {config.center_freq_hz/1e6:.1f} MHz |
| sample_rate_hz | {config.sample_rate_hz/1e6:.1f} MS/s |
| bandwidth_hz | {config.bandwidth_hz/1e6:.1f} MHz |
| rx_gain_db | {config.rx_gain_db:.1f} dB |
| tx_gain_db | {config.tx_gain_db:.1f} dB (placeholder) |
| n_samples | {config.n_samples:,} |
| channel | {config.channel} |
| dry_run | {config.dry_run} |

## Captured IQ statistics (synthetic)

| Stat | Value |
|------|-------|
| Shape | {iq.shape} |
| Dtype | {iq.dtype} |
| Mean amplitude | {np.mean(np.abs(iq)):.6f} |
| Std amplitude | {np.std(np.abs(iq)):.6f} |

## Device status at close

| Key | Value |
|-----|-------|
"""
    for k, v in st.items():
        summary += f"| {k} | {v} |\n"

    summary += """
## Generated figures

| File | Contents |
|------|----------|
| `bladerf_dry_run_iq_preview.png` | First 200 I and Q samples (synthetic noise) |

Figures are in `reports/generated/` (gitignored). Regenerate with:
```
py experiments/run_bladerf_dry_run.py
```

## Safety notes

- No bladeRF device was opened.
- No RF was transmitted.
- No USB access occurred.
- Synthetic IQ is deterministic (fixed RNG seed derived from config params).

## Next step

Real hardware acquisition requires:
1. `dry_run=False` in config.
2. The exact confirmation string `'CONFIRM HARDWARE RUN'` in the session.
3. Verified antenna or RF load connected.
4. Implementation of real capture in `BladeRFDevice.capture_rx()`.
"""

    summary_path = OUT_DIR / "bladerf_dry_run_summary.md"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"  Saved -> {summary_path}")

    print()
    print("Dry-run completed successfully.")
    print("No hardware was accessed.  No RF was transmitted.")


if __name__ == "__main__":
    main()
