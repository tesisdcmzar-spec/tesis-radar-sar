# CLAUDE.md - Radar SAR Thesis Project

## PRIMARY ARCHITECTURE OVERRIDE

The thesis architecture is UWB-OFDM-SAR.
OFDM is the central probing waveform: H[k] = Y[k] / X[k] per subcarrier.
SFCW/RX-only modules are infrastructure validation and practical frequency-block/stitching support, not the final architecture.
The final acquisition product is H(f, x_az), estimated from known OFDM symbols over stitched RF blocks and azimuth positions.
Do not design future work as pure SFCW unless explicitly requested.
Do not treat TX/RX reflector SFCW as the main thesis goal.
No clinical claims.

See: `docs/architecture_uwb_ofdm_sar.md` (canonical architecture document).
See: `docs/ofdm_bladerf_block_stitching_plan.md` (block stitching strategy).
See: `docs/ofdm_dielectric_interpretation.md` (safe and unsafe claims).
See: `docs/sources/ofdm_uwb_sar_fuentes_consolidadas.md` (source notes).
See: `docs/ofdm_effective_bandwidth_bladerf.md` (BW analysis).

---

Project: undergraduate telecommunications thesis. Build an experimental microwave SAR radar platform using bladeRF, SFCW/OFDM sweeps, azimuth motion, DSP, and 2D image reconstruction for dielectric-contrast phantoms.

Environment:
- Native Windows + PowerShell. Do not suggest WSL unless the user explicitly asks.
- Main language: Python. Hardware: bladeRF SDR and Arduino/ESP32/GRBL/FluidNC azimuth stage.
- Scope: simulation, phantom experiments, controlled lab validation. No clinical claims, no patient/person tests.

Working rules:
1. Be concise. Use English for code, prompts, filenames, docstrings, and technical docs unless the user asks Spanish.
2. Before editing code, inspect only relevant files and propose a short plan.
3. Prefer small reversible changes. Do not rewrite working acquisition scripts unless requested.
4. Preserve physical meaning: amplitude, phase, sample rate, center frequency, bandwidth, gain, azimuth position, timestamps, config version, and calibration state.
5. Do not directly read large raw datasets (*.npy, *.bin, large *.csv). Write scripts that report shape, dtype, metadata, stats, and small previews.
6. Use simulation and tests before real hardware.
7. Keep raw data, processed data, figures, reports, and thesis text separated.
8. Hardware safety comes first: dry-run mode, homing, soft limits, emergency stop notes, logs, and explicit user approval before RF transmission or motor motion.

Preferred repo layout:
- hardware/: bladeRF and azimuth-stage abstractions.
- acquisition/: SFCW/OFDM capture and scan sessions.
- processing/: calibration, stitching, range profiles, SAR reconstruction.
- simulation/: synthetic phantoms and synthetic scans.
- experiments/: runnable scripts.
- configs/: YAML configs.
- tests/: unit and smoke tests.
- reports/: logs, generated figures, session notes.
- thesis/: chapters and thesis material.

Safe commands:
- git status
- git diff
- git log --oneline -10
- python --version
- py --version
- python -m pytest
- py -m pytest
- pytest

Danger zone: do not run RF transmission, motor movement, firmware flashing, file deletion, credential access, or long full scans unless the user explicitly approves in the current session.
