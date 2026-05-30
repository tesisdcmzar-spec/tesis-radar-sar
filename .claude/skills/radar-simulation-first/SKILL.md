---
name: radar-simulation-first
description: Build or improve the simulation-first SFCW/SAR pipeline before hardware work.
disable-model-invocation: true
---

Create or improve a hardware-independent simulation pipeline.

Required modules if missing:
- `simulation/phantom_model.py`
- `simulation/synthetic_scan.py`
- `processing/range_profile.py`
- `processing/sar_reconstruction.py`
- `tests/` for basic synthetic cases

Requirements:
1. Synthetic complex frequency response H(f, x_az).
2. Configurable frequency grid, azimuth positions, target location, amplitude, noise, and propagation speed assumption.
3. IFFT-based range profile.
4. Simple delay-and-sum or backprojection reconstruction.
5. Save small example figures under `reports/generated/` or `thesis/figures/generated/`.
6. No bladeRF imports and no hardware access.
7. Run only safe tests.
