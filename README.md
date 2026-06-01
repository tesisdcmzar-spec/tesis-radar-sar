# Radar SAR de Microondas -- Tesis de Grado

Experimental microwave UWB-OFDM-SAR platform for dielectric-contrast phantom imaging.
Built on bladeRF 2.0 micro, OFDM frequency sweeps with block stitching, a GRBL/FluidNC
azimuth stage, and a Python DSP + 2D reconstruction pipeline.

**Scope:** lab validation with tissue-mimicking phantoms. No clinical claims, no patient tests.

---

## Architecture (UWB-OFDM-SAR)

The corrected thesis architecture is **UWB-OFDM-SAR**:

```
For each azimuth position x_m:
  For each RF block center frequency f_c,b:
    Generate known OFDM symbol X_b[k]
    Transmit -> receive echo -> sync -> CP removal -> FFT
    Estimate H_b[k, x_m] = Y_b[k, x_m] / X_b[k]
  Stitch blocks -> H_total(f, x_m)

Then: background subtraction -> IFFT -> range profiles -> backprojection -> 2D image
Final data product: H(f, x_az)
```

**What is validated so far:**
- Simulation pipeline: OFDM channel estimation, range profiles, backprojection (281 tests).
- bladeRF RX-only: smoke test, frequency survey (7 bands), SFCW sweep (2.3-2.5 GHz).
- bladeRF TX infrastructure: safety validators, real TX path, supervised reflector experiment script.

**What is reclassified:**
- SFCW/RX-only work = infrastructure validation (not the final thesis architecture).
- SFCW is a practical frequency-block strategy for stepping through RF bands with bladeRF.

**What remains unimplemented:**
- Multi-block OFDM stitching (`processing/ofdm_block_stitcher.py`).
- OFDM acquisition with synchronized TX/RX bladeRF (`acquisition/ofdm_block_capture.py`).
- Azimuth stage control (motor not yet integrated).
- Full SAR scan with real hardware.

**Next technical steps:**
1. Run supervised TX/RX reflector experiment (`py experiments/run_bladerf_tx_rx_reflector.py --run-sequence`).
2. Implement `processing/ofdm_block_stitcher.py`.
3. First real OFDM TX/RX capture and channel estimate.
4. Full SAR scan with azimuth stage.

---

## Hardware

| Component | Details |
|-----------|---------|
| SDR | Nuand bladeRF 2.0 micro (47 MHz - 6 GHz, 12-bit DAC/ADC, 61.44 MSPS max) |
| Azimuth stage | Arduino/ESP32 + GRBL/FluidNC stepper controller |
| Host | Windows 10 + Python, USB 3.0 |

Known-good parameters (from `legacy/`): 40 MHz sample rate, 40 MHz BW, SC16\_Q11 format,
16 buffers x 8192 buffer\_size x 8 transfers, 3500 ms stream timeout.

---

## Repository Layout

```
hardware/        bladeRF device abstraction + safety checks (TX/RX)
acquisition/     SFCW sweep helpers (future: OFDM block capture)
processing/      ofdm_channel.py, range_profile.py, sar_reconstruction.py
simulation/      ofdm_uwb_sar_simulator.py, phantom_model.py, synthetic_scan.py
experiments/     Runnable scripts (simulation demo, TX/RX reflector)
configs/         YAML parameter files
tests/           Unit tests (281 passing, no hardware required)
reports/         session_reports/ + generated/ (figures, summaries)
thesis/          Chapters and academic addenda
docs/            Architecture docs, source notes, BW analysis
legacy/          Working scripts from early experiments (read-only)
data/            Gitignored: raw/ and processed/ outputs
```

---

## Key Documentation

| File | Content |
|------|---------|
| `docs/architecture_uwb_ofdm_sar.md` | Official UWB-OFDM-SAR architecture |
| `docs/ofdm_bladerf_block_stitching_plan.md` | Block stitching strategy |
| `docs/ofdm_dielectric_interpretation.md` | Physical interpretation + safe claims |
| `docs/sources/ofdm_uwb_sar_fuentes_consolidadas.md` | Source notes from bibliography |
| `docs/ofdm_effective_bandwidth_bladerf.md` | 15 BW-reduction factors |

---

## Safety Rules

- **Dry-run by default.** Real RF or motor motion requires typing `CONFIRM HARDWARE RUN`.
- TX additionally requires `REFLECTOR SETUP READY` before each burst.
- Never edit files in `legacy/`. They are the source of truth for known-good hardware parameters.
- Never commit files from `data/raw/` or `data/processed/` -- gitignored.

---

## Quick Start

```powershell
# Install deps (once)
pip install numpy scipy matplotlib bladerf pyyaml

# Run tests (no hardware required)
py -m pytest tests/ -q

# Run offline OFDM simulation demo (no hardware)
py experiments/run_ofdm_uwb_sar_simulation.py

# Run supervised TX/RX reflector experiment (hardware required)
py experiments/run_bladerf_tx_rx_reflector.py --prepare-only   # dry-run
py experiments/run_bladerf_tx_rx_reflector.py --run-sequence   # real TX
```
