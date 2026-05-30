# CLAUDE.md - Radar SAR Thesis Project

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
