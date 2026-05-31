# Next Phase: TX/RX Safety Plan and Future Prompt

## CRITICAL: Read this before starting any TX session

**DO NOT execute TX automatically.**
**DO NOT enable TX without explicit user confirmation in the current session.**
**DO NOT connect an antenna to TX1 until the dry-run load test is complete.**
**TX with antenna is forbidden until explicitly reviewed and approved by the user.**

---

## Current state (as of 2026-05-31, commit after 226c5b3)

Validated so far (RX-only):
- bladeRF opens/closes correctly in RX mode.
- H(f) assembly from IQ bursts works end-to-end.
- Range profile pipeline (IFFT, windowing, range axis) is functional.
- Post-processing functions (DC removal, normalization, subtraction, smoothing) are tested.
- Error handling for USB timeouts is verified.

NOT yet implemented:
- Real TX path in hardware/bladerf_device.py (configure_tx, enable_tx).
- Any TX/RX calibrated measurement.
- Background subtraction with a known reflector.
- Range profile with a coherent target peak.

---

## Phase plan (ordered steps -- do NOT skip steps)

### Step 1: Implement TX hardware abstraction (dry-run only)

Add to `hardware/bladerf_device.py`:
- `configure_tx(center_freq_hz, sample_rate_hz, bandwidth_hz, tx_gain_db)` -- configures TX channel.
- `enable_tx(enable: bool)` -- enables/disables TX module.
- Explicit safety locks:
  - TX gain must be <= TX_GAIN_MAX_DB (currently -20 dB or user-chosen low value).
  - TX is disabled by default; must be explicitly enabled per-capture.
  - TX confirmation must match CONFIRMATION = "CONFIRM HARDWARE RUN".
- Dry-run mode must ignore TX configuration (same as current pattern).
- Log all TX operations to metadata: tx_enabled, center_freq_hz, tx_gain_db, duration_s.

### Step 2: Load test (TX into 50-ohm load, no antenna)

Create `experiments/run_bladerf_tx_load_test.py`:
- TX1 connected to 50-ohm terminator or >= 30 dB attenuator + load.
- RX1 connected to antenna or 50-ohm load (NOT connected to TX output).
- Transmit a single CW tone at a single frequency for < 1 second.
- Verify: no USB error, no hardware fault, TX level within expected range.
- Verify: RX does NOT detect the TX signal (load absorbs power; no leakage into RX).
- User physically present. Confirmation phrase required.
- Save metadata: tx_enabled=True, load_type='50ohm_terminator', antenna_connected=False.

This step MUST be completed successfully before any antenna is connected to TX1.

### Step 3: First TX with antenna, aimed at known metallic reflector

Create `experiments/run_bladerf_tx_rx_reflector.py`:
- Setup: TX1 antenna pointing toward a flat metallic plate (>= 30x30 cm, steel or aluminum).
- Reflector at known distance (1--3 m, measured with tape).
- No human subject. No phantom. No biological material.
- TX gain: minimum possible (e.g., -20 dB or lower).
- Duration: < 100 ms per frequency step.
- Perform SFCW sweep: capture V_TX(f) and V_RX(f) per step.
- Compute H(f) = V_RX(f) / V_TX(f) (or equivalent with reference channel).
- Apply background subtraction: H_target(f) = H_with_obj(f) - H_no_obj(f).
- Compute range profile and verify peak at expected distance.
- Save metadata: reflector_type, reflector_distance_m, tx_gain_db, antenna_type.

### Step 4: Quantitative validation

Verify that:
- Range profile peak is within +/- 0.5 * dr of expected distance.
- Dynamic range (peak above noise floor) is >= 10 dB.
- Range resolution matches theoretical dr = c / (2 * BW).
- No false peaks > 6 dB above noise in unexpected range bins.

Only after this step can the system be described as a validated SFCW radar.

### Step 5: Multi-azimuth scan (requires motorized stage)

This step requires the azimuth motor stage (Arduino/ESP32/GRBL/FluidNC):
- Motor homing and soft limits must be verified before any scan.
- Emergency stop must be tested before any scan.
- Start with a single azimuth position (Step 3 result).
- Add azimuth dimension one step at a time.
- SAR image reconstruction only after full 2D H(f, x_az) dataset is validated.

---

## Frequency and power safety checklist

Before any TX:
- [ ] Frequency is in a legal ISM or licensed band for your jurisdiction.
  - 2.400--2.4835 GHz: ISM band, unlicensed in most countries (check local regulations).
  - Confirm power limit for your country (e.g., 100 mW EIRP in most ISM applications).
- [ ] TX gain is set to minimum needed to receive a usable signal.
- [ ] TX duration is the minimum needed per frequency step.
- [ ] No humans in the near-field of the antenna during TX.
- [ ] Antenna is aimed at the reflector, not at people or sensitive electronics.
- [ ] bladeRF TX power is well below regulatory limits (bladeRF max output ~6 dBm; use attenuators).

---

## Session prompt template for the next TX session

When starting the next TX session, use a prompt similar to the following:

```
Context:
- Repo: C:\tesis-radar-sar
- Previous state: RX-only SFCW sweep complete (226c5b3 + postprocessing commit).
- Hardware: bladeRF connected via USB. TX1 will be used for the first time.
- Bench: TX1 connected to [50-ohm load / attenuated setup / antenna aimed at reflector].
- Reflector: [none / metallic plate at X m].
- Human subject: NONE.
- Phantom: NONE.
- Confirmation phrase: CONFIRM HARDWARE RUN.

Task:
1. Implement configure_tx() and enable_tx() in hardware/bladerf_device.py.
   Add safety locks: gain <= -10 dB, explicit enable required, logged to metadata.
2. Create experiments/run_bladerf_tx_load_test.py.
   TX into 50-ohm load only. Single frequency. < 1 second. Verify no errors.
3. Run the load test (user present, confirmation required).
4. Report result. If successful, proceed to Step 3 of next_phase_tx_safety_plan.md.

DO NOT:
- Connect antenna before load test passes.
- Transmit toward humans.
- Use a phantom or biological material.
- Run a SAR scan before single-point TX/RX is validated.
- Make any target detection or clinical claims.
```

---

## Files to read at the start of the next TX session

1. `hardware/bladerf_device.py` -- current state of hardware abstraction.
2. `hardware/safety.py` -- current safety limits (TX_GAIN_MAX_DB, etc.).
3. `reports/ai_session_log.md` -- last session state.
4. `reports/session_reports/2026-05-31_rx_sfcw_postprocess_and_next_phase.md` -- this phase plan.
5. `docs/prompts/next_phase_tx_safety_plan.md` -- this file.

---

## What to commit after the TX session

- Source code: hardware/bladerf_device.py (with TX), experiments/run_bladerf_tx_load_test.py.
- Tests: tests/test_bladerf_device.py (updated with TX dry-run tests).
- Session report in Spanish.
- Updated ai_session_log.md.

Do NOT commit: raw IQ data (*.npy), data/raw/, generated figures.

Commit message format:
```
Add supervised TX/RX load test -- first bladeRF TX validation

- No human subject. No phantom. No RF toward personnel.
- TX into 50-ohm load only. No antenna. No radiating.
- [outcome: pass/fail and what was observed]
```
