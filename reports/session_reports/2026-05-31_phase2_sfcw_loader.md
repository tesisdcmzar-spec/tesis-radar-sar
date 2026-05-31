# Session Report — Phase 2: SFCW Capture Loader
**Date:** 2026-05-31
**Goal:** Implement `acquisition/load_sfcw_capture.py` to bridge real `.npy` captures into the existing processing pipeline.

---

## What the Loader Does

`acquisition/load_sfcw_capture.py` exposes a single public function:

```python
load_capture(path, cfg, azimuth_position_m=0.0) -> SyntheticScan
```

It converts three distinct `.npy` capture formats into a `SyntheticScan(freqs_hz, x_az_m, H)` object compatible with `compute_range_profiles` and `backprojection` without any changes to the processing modules.

### Format A — 2D file, shape `(N_f, N_az)`, complex
The ideal format for future multi-position captures.
- `N_f` must match the config's SFCW frequency grid.
- `N_az` must match the config's azimuth step grid.
- `H` is used directly as the frequency-response matrix.

### Format B — 1D file, shape `(N_f,)`, complex
Single-aperture-position frequency response.
- `N_f` must match the config's SFCW frequency grid.
- `H` is reshaped to `(N_f, 1)`; position is `azimuth_position_m`.

### Format C — Directory of per-frequency IQ files (legacy bladeRF captures)
Matches the legacy `capturas_barrido/` directory produced by `test_barrido_frec_captura.py`.
- Files are named `cap_NNN_XXXMHz.npy`.
- Each file contains `(N_samples,)` complex128 IQ samples at center frequency `XXX` MHz.
- The loader **coherently averages** each IQ stream (`np.mean(iq)`) to extract the complex channel response `H(f)` — equivalent to matched-filter integration of a single-tone CW signal.
- Frequencies are inferred from filenames (not from config), sorted ascending.
- Result: `(N_f, 1)` matrix; position is `azimuth_position_m`.

---

## Legacy Capture Files Found in `legacy/capturas_barrido/`

| Property | Value |
|---|---|
| Number of files | 99 |
| Frequency range | 100 MHz to 5980 MHz |
| Frequency step | 60 MHz |
| Sample count per file | 40,000 |
| Sample rate | 40 MHz (1 ms per step) |
| Format per file | `(40000,)` complex128 |
| Implied bandwidth | 5880 MHz |
| Implied range resolution | c / (2 × BW) ≈ **2.55 cm** |
| Azimuth positions | **1** (single static position — no azimuth scan in legacy) |
| Normalization | ADC counts ÷ 2048 (DAC scale ±2048, SC16\_Q11) |

The legacy captures were taken with the bladeRF configured at a single antenna position. There is no azimuth dimension. They are useful for **1D range profiling** (to verify hardware RF performance) but cannot produce a SAR image without a matching azimuth scan.

---

## What Still Blocks Real Hardware Use

1. **No azimuth scan in legacy data.** The 99 files are all from one position. Backprojection requires captures at multiple aperture positions. A new multi-position scan session is needed.

2. **No TX in legacy captures.** The legacy script captures receive-only IQ. There is no transmitted reference signal for coherent SFCW. Real SFCW requires transmitting a CW tone at each step and receiving the backscattered echo. The current legacy captures likely contain only ambient/noise signals or leakage — not a proper radar return.

3. **No background reference.** The processing pipeline has no background-subtraction step yet. Real captures require subtracting a background (scene without target) from the target scene to isolate the phantom response.

4. **Config mismatch.** The legacy frequency grid (100–5980 MHz, 60 MHz step) does not match the simulation config (500–2500 MHz, 5 MHz step). The loader handles Format C without needing the config's SFCW section, but downstream processing (image grid, expected range resolution) must be reconfigured to match.

5. **bladeRF hardware abstraction not yet built.** `hardware/` is empty. A safe bladeRF abstraction with dry-run mode, TX/RX control, and emergency stop is the next hardware-facing task (Phase 3).

---

## Next Step After the Loader

**Phase 3 — bladeRF hardware abstraction (`hardware/bladerf_device.py`):**
- Wrap the bladeRF Python bindings with explicit dry-run mode (no RF output by default).
- Expose safe `tune(freq_hz)`, `rx_block(n_samples)`, and `tx_enable(bool)` methods.
- Require `CONFIRM HARDWARE RUN` before any RF transmission.
- Then Phase 4: implement a proper SFCW sweep (`acquisition/sfcw_sweep.py`) that:
  1. Steps through frequencies using the bladeRF device abstraction.
  2. Captures IQ at each step.
  3. Computes `H(f) = np.mean(iq)` per step.
  4. Saves a single `(N_f,)` or `(N_f, N_az)` `.npy` file for the loader.

---

## Files Created This Session

| File | Purpose |
|---|---|
| `acquisition/__init__.py` | Makes `acquisition` a Python package |
| `acquisition/load_sfcw_capture.py` | SFCW capture loader (formats A, B, C) |
| `tests/test_load_sfcw_capture.py` | 18 unit tests, all synthetic fixtures |
| `reports/session_reports/2026-05-31_phase2_sfcw_loader.md` | This report |

---

## Test Results

```
30 passed in 0.37s
```

- 18 new tests in `test_load_sfcw_capture.py` — all passed.
- 12 existing simulation/processing tests — all still passing (no regressions).
- Hardware actions: none. All tests use small in-memory synthetic arrays.
