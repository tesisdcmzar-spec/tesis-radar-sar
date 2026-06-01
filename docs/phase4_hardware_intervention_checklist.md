# Phase 4 Hardware Intervention Checklist

This file describes the physical setup required before running real hardware
OFDM experiments. Read this before running any hardware mode.

---

## When to use this

Run the hardware script when:
- All software-only gates have passed (see `reports/generated/phase4_gate_summary.md`).
- bladeRF is physically available.
- User is physically present.
- Metallic reflector is ready.

---

## Physical setup

### Step 1: Connect bladeRF
- Connect bladeRF 2.0 micro to PC via USB.
- Verify device is recognized: `bladeRF-cli -p` should show the device.
- Verify Python bindings: `python -c "import bladerf; print('OK')"`.

### Step 2: Connect TX antenna
- Connect wideband antenna (or coax termination for bench test) to TX1 port.
- Verify connector is tight (SMA or SMA-to-N adapter as needed).
- TX gain will be set to -20 dB (conservative). Do not increase without justification.

### Step 3: Connect RX antenna
- Connect wideband antenna to RX1 port.
- Keep TX and RX antennas at least 20 cm apart (antenna-to-antenna isolation).
- Point both antennas toward the reflector test object.

### Step 4: Place test object
- Use a flat metallic plate (aluminum or copper) at approximately 1 meter distance.
- Measure the actual distance and record it.
- Recommended: R = 0.8 m to 1.2 m (within the conservative operating range).
- The object should be in the main beam direction of both antennas.
- No biological material (tissue, water bottles, food) in the antenna beam.
- No person in the main antenna direction.

### Step 5: Clear the area
- Ensure no person is standing in front of the antennas during TX.
- Ensure no biological material (phantom, food, tissue) is in the beam.
- Keep electronics (laptop, bladeRF) behind or to the side of antennas.

### Step 6: Emergency stop
- If anything goes wrong: unplug the bladeRF USB cable immediately.
- TX is always disabled in the software's `finally` block, but USB disconnect
  is the hardware emergency stop.

---

## Software safety parameters

These settings are hardcoded in the scripts. Do not change them:
- Center frequency : 2.400 GHz
- TX gain          : -20 dB (conservative, safe for bench testing)
- OFDM burst       : <= 10 ms per block
- TX disabled      : always in `finally` block (even on exception)
- No motor scan    : motor_scan=False enforced
- No SAR scan      : sar_scan=False enforced
- No subjects      : human_subject=False, phantom=False, biological_material=False

---

## Exact command to run

```powershell
cd C:\tesis-radar-sar
py experiments/run_phase4_hardware_entrypoint.py --run-supervised
```

The script will:
1. Ask for confirmation phrase: type `CONFIRM HARDWARE RUN`
2. Ask for reflector phrase: type `REFLECTOR SETUP READY`
3. Run RX smoke test (captures IQ, no TX).
4. Run TX IQ smoke test (very short 0.16 ms OFDM burst).
5. Run single-block OFDM H[k] acquisition.
6. Prompt to remove object, then capture background.
7. Prompt to place object, then capture object.
8. Analyze and compute relative contrast profile.
9. Optionally run 3-block stitching pilot.

---

## Expected outputs

After a successful run:
- `reports/generated/phase4_rx_smoke_psd.png`
- `reports/generated/phase4_rx_smoke_summary.md`
- `reports/generated/phase4_tx_smoke_summary.md`
- `reports/generated/phase4_single_block_H_magnitude.png`
- `reports/generated/phase4_single_block_H_phase.png`
- `reports/generated/phase4_single_block_cir.png`
- `reports/generated/phase4_single_block_h_summary.md`
- `reports/generated/phase4_background_object_H_background_object.png`
- `reports/generated/phase4_background_object_contrast_vs_distance.png`
- `reports/generated/phase4_background_object_summary.md`
- `reports/generated/phase4_hardware_gate_report.md`
- Raw data under: `data/raw/ofdm_phase4/` and `data/raw/ofdm_bg_obj/`

---

## What to report after the run

Copy the following back for documentation:
1. Content of `reports/generated/phase4_hardware_gate_report.md`.
2. Content of `reports/generated/phase4_single_block_h_summary.md`.
3. Content of `reports/generated/phase4_background_object_summary.md`.
4. Filenames of generated figures.
5. Whether the CIR peak appeared near the known reflector distance.
6. Any error messages or FAIL gates.

---

## Scientific wording

Do NOT say:
- "measured dielectric permittivity of the sample"
- "detected cancer" or "diagnosed tumor"
- "epsilon_r = X at position Y"
- "validated medical imaging result"

DO say:
- "relative dielectric-contrast profile"
- "perfil de contraste dielelectrico relativo"
- "reflectivity-vs-distance indicator (not calibrated)"
- "CIR peak consistent with a reflective object at approximately X cm"
- "no calibrado en permitividad absoluta"
