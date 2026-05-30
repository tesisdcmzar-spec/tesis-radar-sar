# Radar SAR de Microondas — Tesis de Grado

Experimental microwave SAR radar platform for dielectric-contrast phantom imaging.
Built on bladeRF 2.0 micro, SFCW/OFDM frequency sweeps, a GRBL/FluidNC azimuth stage, and a
Python DSP + 2D reconstruction pipeline.

**Scope:** lab validation with tissue-mimicking phantoms. No clinical claims, no patient tests.

---

## Hardware

| Component | Details |
|-----------|---------|
| SDR | Nuand bladeRF 2.0 micro (47 MHz – 6 GHz, 12-bit DAC/ADC, 61.44 MSPS max) |
| Azimuth stage | Arduino/ESP32 + GRBL/FluidNC stepper controller |
| Host | Windows 10 + Python, USB 3.0 |

Known-good parameters (from `legacy/`): 40 MHz sample rate, 40 MHz BW, SC16\_Q11 format,
16 buffers × 8192 buffer\_size × 8 transfers, 3500 ms stream timeout, DAC scale ±2048.

---

## Repository Layout

```
hardware/        bladeRF device abstraction + azimuth stage + safety checks
acquisition/     SFCW sweep, full-duplex capture, scan session orchestration
processing/      Background subtraction, stitching, phase correction, SAR reconstruction
simulation/      Synthetic phantom model and synthetic scan generator
experiments/     Runnable top-level scripts
configs/         YAML parameter files (simulation, phantom, benchmark)
tests/           Unit and smoke tests (pytest)
reports/         session_logs/ (Markdown) + generated/ (figures)
thesis/          Chapters and final figures
legacy/          Working scripts from early experiments — read-only reference
data/            Gitignored: raw/ (.npy captures) and processed/ outputs
```

---

## Phase Roadmap

| Phase | Goal | Status |
|-------|------|--------|
| 0 | Repository setup and Claude Code pack | Done |
| 1 | Audit, README, configs, legacy inventory | **Active** |
| 2 | Simulation-first SFCW/SAR pipeline | Pending |
| 3 | bladeRF hardware abstraction layer | Pending |
| 4 | Frequency sweep + OFDM channel estimation | Pending |
| 5 | Azimuth stage control (dry-run first) | Pending |
| 6 | Integrated scan session | Pending |
| 7 | DSP and frequency stitching pipeline | Pending |
| 8 | SAR 2D reconstruction and phantom validation | Pending |
| 9 | Thesis writing support | Continuous |

---

## Safety Rules

- **Dry-run by default.** Real RF or motor motion requires typing `CONFIRM HARDWARE RUN`
  in the current Claude Code session.
- Never edit files in `legacy/`. They are the source of truth for known-good hardware parameters.
- Never commit files from `data/raw/` or `data/processed/` — gitignored for good reason.

---

## Quick Start

```powershell
# Clone and enter repo
cd C:\tesis-radar-sar

# Install Python deps (once)
pip install numpy scipy matplotlib bladerf

# Run tests (simulation only, no hardware)
python -m pytest tests/

# Start Claude Code session
claude
```

First Claude Code commands each session:

```
/status
/radar-session-start
```
