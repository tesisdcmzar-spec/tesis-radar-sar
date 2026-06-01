# AI Session Log — Radar SAR Thesis

---

## Session 2026-05-30

**Goal:** Build the hardware-independent simulation pipeline (Phase 1 of thesis roadmap).

**Files created (all new):**
- `conftest.py` — root sys.path fix for pytest
- `simulation/__init__.py`
- `simulation/phantom_model.py` — `PhantomModel`, `PointTarget`, `phantom_from_config`
- `simulation/synthetic_scan.py` — `SyntheticScan`, `make_scan`, `scan_from_config`
- `processing/__init__.py`
- `processing/range_profile.py` — IFFT range profile with Hanning window + zero-padding
- `processing/sar_reconstruction.py` — backprojection SAR reconstruction + `image_grid_from_config`
- `tests/test_simulation.py` — 12 unit tests
- `experiments/run_simulation.py` — end-to-end script, saves figures to `reports/generated/`

**Commands run:**
```
py -m pytest tests/test_simulation.py -v     # all tests
py experiments/run_simulation.py             # figure generation
git add ... && git commit                    # commit eb75b1e
```

**Test results:** 12/12 passed.

**Figures generated:** `reports/generated/range_profiles.png`, `reports/generated/sar_image.png`.

**Hardware actions:** None. Fully simulated.

**Issues found and fixed:**
1. Backprojection peak at wrong range (z=0.074 instead of z=0.10 m). Root cause: IFFT of a non-baseband SFCW signal (f_start=500 MHz) retains a carrier term exp(−j·4π·f_start·R/c) in the range profile. Fix: multiply each aperture contribution by exp(+j·4π·f_start·R_pixel/c) before coherent summation.
2. PyYAML on this machine parses scientific notation (`5.0e6`, `3.0e8`) as strings. Fix: explicit `float()`/`int()` conversion on all config reads.
3. Windows console encoding rejects Unicode arrows/symbols in f-strings. Fix: replaced with ASCII equivalents.

**Open issues:** None blocking. `reports/generated/` is gitignored so figures are local only.

**Next recommended step (Phase 2):** Write a loader (`acquisition/load_sfcw_capture.py`) that reads the real `.npy` captures from `legacy/capturas_barrido/` into the same `SyntheticScan`-compatible H(f, x_az) array, then run the existing processing pipeline on real data.

---

## Session 2026-05-30 (continued — resolution improvements)

**Goal:** Improve SAR image resolution and demonstrate target resolving capability.

**Files modified:**
- `processing/range_profile.py` — replaced `window: bool` with `window: str` ('none', 'hanning', 'blackman'); 'none' = rectangular = 7.5 cm range resolution
- `processing/sar_reconstruction.py` — updated `window` signature to match; zoomed default image grid from z=0.50 m to z=0.25 m
- `tests/test_simulation.py` — updated `window=False` call to `window='none'`
- `experiments/run_simulation.py` — default window changed to 'none' (best resolution); image grid zoomed to 2–26 cm range, 300×300 pixels; added `sar_window_comparison.png` side-by-side figure; range profile dashed lines made dynamic (slant range from center aperture per target)
- `configs/simulation.yaml` — targets moved from (0,10)/(5,12) cm to (-6,9)/(6,19) cm to exceed the 7.5 cm resolution cell in both range (10 cm sep) and cross-range (12 cm sep)

**Commands run:**
```
py -m pytest tests/test_simulation.py -v     # 12/12 passed
py experiments/run_simulation.py             # regenerated all figures
git commit && git push                       # commits 232ef92, 31bc9ee
```

**Test results:** 12/12 passed (no regressions).

**Figures generated:**
- `reports/generated/range_profiles.png` — rectangular vs Hanning 1D profiles with per-target slant-range markers
- `reports/generated/sar_window_comparison.png` — side-by-side SAR images showing resolution vs sidelobe tradeoff
- `reports/generated/sar_image.png` — best-resolution (rectangular window) image with both targets clearly resolved

**Hardware actions:** None. Fully simulated.

**Open issues:** None blocking.

**Next recommended step (Phase 2):** Write a loader (`acquisition/load_sfcw_capture.py`) that reads the real `.npy` captures from `legacy/capturas_barrido/` into a `SyntheticScan`-compatible H(f, x_az) array, then run the existing processing pipeline on real data.

---

## Session 2026-05-31 (Phase 2 — SFCW capture loader)

**Goal:** Implement `acquisition/load_sfcw_capture.py` — bridge from real `.npy` captures to the existing simulation pipeline (`SyntheticScan`).

**Key discovery:** 99 legacy files in `capturas_barrido/` are per-frequency IQ streams, not a 2D H matrix. Shape: `(40000,)` complex128, 100–5980 MHz at 60 MHz step, single aperture position only. Range profiles possible; SAR image blocked until azimuth scan data exists.

**Files created:**
- `acquisition/__init__.py` — package init
- `acquisition/load_sfcw_capture.py` — loader supporting Format A (2D file), B (1D file), C (legacy directory). Public API: `load_capture(path, cfg, azimuth_position_m=0.0) -> SyntheticScan`.
- `tests/test_load_sfcw_capture.py` — 18 unit tests (all synthetic fixtures, no hardware).
- `reports/session_reports/2026-05-31_phase2_sfcw_loader.md` — intermediate English report.

**Test results:** 30/30 passed (18 new + 12 existing, no regressions).
**Commit:** `4fd93a1` — pushed to `origin/main`.
**Next step:** `processing/background_subtraction.py` — required before any real-hardware phantom experiment.

**Full session report:** [reports/session_reports/2026-05-31_loader_capturas_sfcw.md](session_reports/2026-05-31_loader_capturas_sfcw.md)

---

## Session 2026-05-31 (retrospective report + session close)

**Goal:** Generate a thesis-grade retrospective engineering report covering all simulation work from 2026-05-30; then write the formal session-close report for today.

**Files created:**
- `reports/session_reports/2026-05-30_simulation_pipeline_resolution_and_thesis_draft.md` — 20-section retrospective in Spanish (631 lines): signal model, double-path phase, IFFT profiles, backprojection, carrier correction, YAML/encoding bugs, window resolution tradeoff, target separation, figures, tests, Chapter 3, thesis impact, limitations, next steps.
- `reports/session_reports/2026-05-31_sesion_informe_retrospectivo_simulacion.md` — formal 15-section session-close report for today's documentation session.

**Hardware actions:** None. Documentation only.

**Commits:** `755763c` (retrospective report, pushed to origin/main). Session-close report pending commit.

**Full session-close report:** `reports/session_reports/2026-05-31_sesion_informe_retrospectivo_simulacion.md`

---

## Session 2026-05-31 (Phase 2 Offline — closure)

**Goal:** Close the entire offline phase: legacy capture inspection, offline analysis script, range profile figures, thesis note, closure report, and updated tests.

**Legacy capture inspection results:**
- 99 files in `legacy/capturas_barrido/`, shape `(40000,)` complex128 each.
- Filename pattern: `cap_NNN_XXXMHz.npy`, range 100–5980 MHz, step 60 MHz.
- BW = 5880 MHz → range resolution ≈ 2.55 cm; unambiguous range = 2.50 m.
- Single azimuth position only — no SAR 2D image possible from this data.
- Total size: 63.4 MB; all loaded with `mmap_mode='r'` only.

**Files created:**
- [`experiments/run_legacy_offline_analysis.py`](../experiments/run_legacy_offline_analysis.py) — offline analysis script: loads legacy captures via `load_capture()`, computes H(f) and range profiles (rectangular + Hanning, ×8 zero-pad), saves 4 figures + Markdown summary to `reports/generated/`.
- [`thesis/cap4_validacion_offline_legacy.md`](../thesis/cap4_validacion_offline_legacy.md) — Spanish academic thesis note: IQ-to-H(f) derivation, SyntheticScan bridge, 1D range analysis, why SAR 2D is impossible with single aperture, transition to hardware.
- [`reports/session_reports/2026-05-31_phase2_offline_closure.md`](2026-05-31_phase2_offline_closure.md) — Spanish engineering closure report (14 sections): inspection, workflow, figures, tests, what is/isn't validated, next hardware phase.

**Files modified:**
- [`tests/test_load_sfcw_capture.py`](../tests/test_load_sfcw_capture.py) — added `test_sfcw_point_target_range_peak_in_format_c`: synthetic SFCW point-target signal through Format-C loader → range profile peak within ±5 cm of R₀ = 1.0 m.
- [`reports/ai_session_log.md`](ai_session_log.md) — this entry.

**Generated local figures** (gitignored, regenerate with script):
- `reports/generated/legacy_frequency_response.png`
- `reports/generated/legacy_range_profile_rectangular.png`
- `reports/generated/legacy_range_profile_hanning.png`
- `reports/generated/legacy_range_profile_comparison.png`
- `reports/generated/legacy_offline_summary.md`

**Test results:** ≥ 31 tests passed (30 prior + 1 new), no regressions.

**Hardware actions:** None. Fully offline. No RF, no motors, no bladeRF API.

**Next step (Phase 3):** `hardware/bladerf_device.py` — safe bladeRF abstraction with dry-run mode and explicit `CONFIRM HARDWARE RUN` gate before any RF transmission.

---

## Session 2026-05-31 (Phase 3 — bladeRF dry-run abstraction)

**Goal:** Create the hardware abstraction layer for the bladeRF; dry-run only, no hardware actions.

**Files created:**
- [`hardware/__init__.py`](../hardware/__init__.py) — package documentation.
- [`hardware/safety.py`](../hardware/safety.py) — `SafetyError`, `HardwareConfirmation`, `require_hardware_confirmation()`, safety constants (70 MHz – 6 GHz, 61.44 MS/s, 56 MHz BW, −20 dBm TX limit), 5 validation functions.
- [`hardware/bladerf_device.py`](../hardware/bladerf_device.py) — `BladeRFConfig` dataclass (validated on init), `BladeRFDevice` with dry-run synthetic IQ and real-hardware stubs.
- [`configs/bladerf_dry_run.yaml`](../configs/bladerf_dry_run.yaml) — reference YAML config, `dry_run: true`.
- [`experiments/run_bladerf_dry_run.py`](../experiments/run_bladerf_dry_run.py) — dry-run demo: configure, capture, transmit_tone (no RF), status, close; saves figure and summary.
- [`tests/test_bladerf_device.py`](../tests/test_bladerf_device.py) — 30 hardware/safety tests (no bladeRF required).
- [`docs/hardware_bladerf_safety.md`](../docs/hardware_bladerf_safety.md) — Spanish safety guide.
- [`thesis/cap5_abstraccion_hardware_bladerf.md`](../thesis/cap5_abstraccion_hardware_bladerf.md) — Spanish thesis Chapter 5.
- [`reports/session_reports/2026-05-31_phase3_bladerf_dry_run_abstraction.md`](2026-05-31_phase3_bladerf_dry_run_abstraction.md) — Spanish session report.

**Generated local outputs** (gitignored):
- `reports/generated/bladerf_dry_run_iq_preview.png`
- `reports/generated/bladerf_dry_run_summary.md`

**Test results:** 61/61 passed (31 prior + 30 new), no regressions.

**Hardware actions:** None. Dry-run only. No RF, no USB, no bladeRF API, no motors.

**Next step (Phase 3 cont.):** Implement real `capture_rx()` in `BladeRFDevice` using lazy `bladerf` import; first real capture requires `"CONFIRM HARDWARE RUN"` in session.

---

## Session 2026-05-31 (continuidad — sin actividad nueva)

**Goal:** Verify repo state after context compaction; confirm Phase 3 was already complete.

**Result:** No changes. Commit `be03e66` confirmed at HEAD, working tree clean, 65/65 tests still passing from prior session.

**Hardware actions:** None.

**Full note:** [reports/session_reports/2026-05-31_verificacion_continuidad_fase3.md](session_reports/2026-05-31_verificacion_continuidad_fase3.md)

---

## Session 2026-05-31 (Phase 3 cont. — prepare real RX path)

**Goal:** Implement the real RX capture code path in `hardware/bladerf_device.py` without executing any hardware operations.

**Files modified:**
- [`hardware/bladerf_device.py`](../hardware/bladerf_device.py) — Added `sc16q11_to_complex()`, `_import_bladerf()`, `_capture_rx_real()`, `BladeRFDevice._bladerf_module` injection parameter; real-mode `configure_rx()` now sets channel frequency/sample_rate/bandwidth/gain via libbladeRF API.
- [`tests/test_bladerf_device.py`](../tests/test_bladerf_device.py) — 18 new tests: SC16_Q11 conversion (8 tests), `_import_bladerf` (1 test), fake-backend real-mode path (9 tests).
- [`docs/hardware_bladerf_safety.md`](../docs/hardware_bladerf_safety.md) — Added section 10: "Ruta RX real preparada — no ejecutada aún".

**Files created:**
- [`reports/session_reports/2026-05-31_phase3_prepare_real_rx_capture.md`](session_reports/2026-05-31_phase3_prepare_real_rx_capture.md) — Spanish session report.

**What was prepared:**
- Lazy bladeRF import via `importlib.import_module("bladerf")` — never triggered at module load.
- `sc16q11_to_complex(raw)`: converts interleaved int16 [I0,Q0,...] → complex128 by dividing by 2048.0.
- `_capture_rx_real()`: full sync_config + bytearray buffer + sync_rx + SC16_Q11 conversion.
- Fake-backend injection (`_bladerf_module` parameter) so tests exercise real-mode code without USB.

**Test results:** 82/82 passed (65 prior + 17 new), no regressions.

**Hardware actions:** None. No bladeRF opened. No USB accessed. No RF transmitted. No motors moved.

**Next step (Phase 3 — first supervised real RX):** Connect bladeRF, install `pip install bladerf`, connect RX antenna/load, user present, provide `confirmation="CONFIRM HARDWARE RUN"` in session.

---

## Session 2026-05-31 (thesis documentation audit)

**Goal:** Audit and organize thesis documentation after Phase 2 offline closure and Phase 3 RX-path preparation. Documentation-only session — no code changes, no hardware.

**Files created:**
- [`reports/session_reports/2026-05-31_thesis_docs_audit_after_phase3_rx.md`](session_reports/2026-05-31_thesis_docs_audit_after_phase3_rx.md) — Full Spanish audit report.
- [`thesis/README_thesis_structure.md`](../thesis/README_thesis_structure.md) — Short (≤120 lines) chapter map with proposed renaming and pending work.

**Files committed:**
- `thesis/cap1_introduccion.md` — Previously untracked; now added to git.

**Key findings:**
- 6 chapter files exist; correct final structure is 8 chapters.
- Two files share the `cap4_*` prefix — naming conflict; `cap4_validacion_offline_legacy.md` should become `cap5_*`.
- `cap5_abstraccion_hardware_bladerf.md` should become `cap6_*` and needs a Phase 3b addendum (sc16q11_to_complex, _capture_rx_real, fake-backend tests).
- `cap1_introduccion.md` is complete and was not committed until now.
- Chapters 7 (experiments) and 8 (conclusions) do not yet exist.

**Chapter renaming:** proposed but NOT executed. Rename in one commit when producing the first integrated draft for the advisor.

**Hardware actions:** None. No code changes. No RF. No USB.

**What to read next:** `reports/session_reports/2026-05-31_thesis_docs_audit_after_phase3_rx.md` (sections 9 and 10) and `thesis/README_thesis_structure.md`.

---

## Session 2026-05-31 (Phase 3 — first supervised real RX-only smoke test)

**Goal:** Run the first real bladeRF RX-only capture under user supervision.

**Hardware actions:** Real bladeRF device opened (USB). RX channel configured and captured. No TX. No RF transmitted. No motor movement. No human subject. Not a SAR scan. Not a medical test.

**Bugs found and fixed in this session:**
1. `_capture_rx_real`: `ChannelLayout`/`Format` enums accessed as `mod._bladerf.ChannelLayout` (correct) not `mod.ChannelLayout` (wrong — not at top-level bladerf).
2. `configure_rx` (real mode): missing `enable_module(CHANNEL_RX(0), True)` before sync streaming — caused `TimeoutError` on first run.
3. `close` (real mode): added `enable_module(CHANNEL_RX(0), False)` before `device.close()`.
4. `_FakeBladeRFDevice` test fake: added `enable_module(ch_id, enable)` method.
5. `_FakeBladeRFModule` test fake: added `_bladerf` submodule (`_FakeBladeRFSubmodule`) with `ChannelLayout` and `Format`.

**Files created:**
- [`experiments/run_bladerf_rx_smoke_test.py`](../experiments/run_bladerf_rx_smoke_test.py) — supervised RX-only smoke test script.
- [`reports/session_reports/2026-05-31_first_real_rx_smoke_test.md`](session_reports/2026-05-31_first_real_rx_smoke_test.md) — Spanish session report.

**Files modified:**
- [`hardware/bladerf_device.py`](../hardware/bladerf_device.py) — enable_module fix, ChannelLayout/Format path fix, close cleanup.
- [`tests/test_bladerf_device.py`](../tests/test_bladerf_device.py) — fake backend updated to match real API.

**Capture result:**
- IQ shape: (100000,)  dtype: complex128
- Mean amplitude: 0.00336  Max: 0.01424  RMS: 0.00386
- Clipping ratio: 0.0 (no clipping at 20 dB gain)
- DC offset magnitude: 0.00039 (normal for direct-conversion SDR)
- Strongest FFT bin: DC (+0.0 MHz), -68.3 dB — environmental noise floor, no coherent target signal

**Local outputs (not committed):**
- `data/raw/rx_smoke/20260531_161436/rx_iq.npy`
- `data/raw/rx_smoke/20260531_161436/metadata.json`
- `reports/generated/bladerf_rx_smoke_time_domain.png`
- `reports/generated/bladerf_rx_smoke_spectrum.png`
- `reports/generated/bladerf_rx_smoke_summary.md`

**Test results:** 82/82 passed (no regressions).

**Next step:** Supervised multi-frequency SFCW sweep — capture one IQ burst per frequency step, build H(f, x_az) matrix. No TX yet.

---

## Session 2026-05-31 (Phase 3 — supervised RX-only frequency survey)

**Goal:** Characterize bladeRF RX behavior across 7 frequencies (900 MHz – 5 GHz). Receiver diagnostic only — not radar.

**Hardware actions:** Real bladeRF device opened and closed 7 times (once per frequency). RX-only. No TX. No RF transmitted. No motor movement. No human subject. Not a SAR scan. Not a medical test.

**Files created:**
- [`experiments/run_bladerf_rx_frequency_survey.py`](../experiments/run_bladerf_rx_frequency_survey.py) — RX frequency survey script.
- [`reports/session_reports/2026-05-31_rx_frequency_survey.md`](session_reports/2026-05-31_rx_frequency_survey.md) — Spanish session report.

**Per-frequency results (7/7 successful):**

| Freq (MHz) | RMS | DC mag | Peak (dB) | Classification |
|------------|-----|--------|-----------|----------------|
| 900 | 0.00423 | 0.00035 | -69.2 | noise-like |
| 1200 | 0.00678 | 0.00036 | -68.9 | noise-like |
| 1800 | 0.00385 | 0.00039 | -68.2 | noise-like |
| 2400 | 0.00379 | 0.00038 | -68.5 | noise-like |
| 3000 | 0.00381 | 0.00037 | -68.7 | noise-like |
| 4000 | 0.00370 | 0.00003 | -80.4 | noise-like |
| 5000 | 0.00432 | 0.00081 | -61.8 | noise-like |

**Key observations:**
- All captures: noise-like; no clipping (0.000% at all frequencies); gain=20 dB is appropriate.
- RMS noise floor consistent ~0.0037–0.0068 across the range — receiver is functional.
- 1200 MHz: slightly elevated RMS (0.00678) and max (0.0315), likely LTE/GPS activity.
- 4000 MHz: DC offset ~0 (0.00003); strongest bin at -4667 kHz from center (possible FPGA decimation artifact or OOB signal).
- 5000 MHz: peak at -61.8 dB (highest in survey), consistent with WiFi 5 GHz activity.

**Local outputs (not committed):**
- `data/raw/rx_frequency_survey/20260531_162522/` — 7 .npy files + metadata.json
- `reports/generated/bladerf_rx_frequency_survey_noise_floor.png`
- `reports/generated/bladerf_rx_frequency_survey_dc_offset.png`
- `reports/generated/bladerf_rx_frequency_survey_peak_bins.png`
- `reports/generated/bladerf_rx_frequency_survey_summary.md`

**Test results:** 82/82 passed (no regressions).

**Next step:** Supervised SFCW sweep (RX-only) over a narrow band (e.g. 2.3–2.5 GHz, 1 MHz steps) to build H(f) and compute range profile. No TX yet.

---

## Session 2026-05-31 — CIERRE (commits d3b5cfe + 44392be)

**Tipo:** Cierre de sesión hardware Fase 3 — smoke test RX + survey de frecuencias.

**Resumen:** Primera sesión con hardware real bladeRF conectado. Se realizaron dos tareas supervisadas RX-only. El smoke test (d3b5cfe) abrió el dispositivo por primera vez en modo real, capturó 100 000 muestras IQ a 2.4 GHz y corrigió tres bugs en `hardware/bladerf_device.py` no visibles sin hardware. El survey de frecuencias (44392be) caracterizó el receptor en 7 bandas (900 MHz–5 GHz), con 7/7 capturas exitosas, todas clasificadas como noise-like.

**Datos brutos:** Almacenados localmente en `data/raw/rx_smoke/` y `data/raw/rx_frequency_survey/`. Excluidos de git por `.gitignore` (`data/raw/`, `*.npy`). No versionados.

**Tests:** 82/82 pasando. Sin regresiones.

**Informe completo de cierre:** [reports/session_reports/2026-05-31_sesion_cierre_hardware_rx_fase3.md](session_reports/2026-05-31_sesion_cierre_hardware_rx_fase3.md)

**Próxima fase:** `experiments/run_bladerf_rx_sfcw_sweep.py` — barrido SFCW estrecho supervisado, RX-only, sin TX, para ensamblar H(f) y calcular primer perfil de rango con `processing/range_profile.py`.

---

## Session 2026-05-31 (Phase 3 — supervised RX-only SFCW sweep + range profile)

**Goal:** Run a supervised RX-only narrowband SFCW-style sweep (2.3–2.5 GHz) and
exercise the full H(f) → range profile pipeline with real hardware data.

**Hardware actions:** Real bladeRF opened and closed 221 times (21 pilot + 200 full).
RX-only. No TX. No RF transmitted. No motor movement. No human subject.
Not a SAR scan. Not a medical test.

**Files created:**
- [`acquisition/rx_sfcw_sweep.py`](../acquisition/rx_sfcw_sweep.py) — hardware-independent
  SFCW sweep helper: `make_frequency_grid`, `coherent_average_iq`,
  `extract_h_from_iq_bursts`, `make_synthetic_scan_from_h`, `compute_sweep_metrics`,
  `SweepConfig`, `SweepResult`. No bladeRF import.
- [`experiments/run_bladerf_rx_sfcw_sweep.py`](../experiments/run_bladerf_rx_sfcw_sweep.py)
  — supervised real-hardware sweep script: pilot mode (21 freqs, 10 MHz step),
  full mode (201 freqs, 1 MHz step), go/no-go logic, range profile generation.
- [`tests/test_rx_sfcw_sweep.py`](../tests/test_rx_sfcw_sweep.py) — 43 unit tests
  (synthetic data only, no hardware).
- [`reports/session_reports/2026-05-31_rx_only_sfcw_sweep.md`](2026-05-31_rx_only_sfcw_sweep.md)
  — Spanish session report.

**Pilot sweep results (21/21):**
- Frequencies: 2.300 – 2.500 GHz, step 10 MHz, 21 points
- All 21 captures OK. Clipping: 0. Failures: 0.
- BW = 200 MHz, dr = 75 cm, R_unamb = 15 m
- Peak |H(f)| at 2470 MHz, -67.0 dB (noise floor)
- H(f) dynamic range: 2.7 dB (nearly flat, consistent with noise)
- Peak range bin: 0.000 m, -86.1 dB (DC bin of noise IFFT)

**Full sweep results (200/201):**
- Frequencies: 2.300 – 2.500 GHz, step 1 MHz, 201 points
- 200 captures OK, 1 failure at 2452 MHz (USB NIOS II timeout, device recovered)
- Clipping: 0.
- R_unamb increased to 150 m with 1 MHz step
- Notable elevated RMS at 2416-2420 MHz (Wi-Fi 802.11b/g/n ISM, expected)
- Peak range bin: 0.000 m, -86.2 dB (noise floor)

**Scientific honesty:**
- H(f) = coherent mean of RX noise, NOT a radar transfer function.
- Range profile = pipeline validation, NOT target detection.
- No SAR imaging. No object detection. No dielectric characterization. No clinical claims.

**Local outputs (not committed):**
- `data/raw/rx_sfcw_sweep/pilot/20260531_164839/` -- 21 IQ bursts + H_raw.npy + metadata
- `data/raw/rx_sfcw_sweep/full/20260531_165012/` -- 200 IQ bursts + H_raw.npy + metadata
- `reports/generated/rx_sfcw_{pilot,full}_{h_magnitude_phase,range_profile}.png`
- `reports/generated/rx_sfcw_sweep_summary.md`

**Test results:** 125/125 passed (43 new + 82 prior), no regressions.

**Bug fixed during session:** Unicode cp1252 UnicodeEncodeError in print() statements
on Windows PowerShell -- replaced delta, em-dashes, arrows with ASCII equivalents in
all print/console paths.

**Full session report:** [reports/session_reports/2026-05-31_rx_only_sfcw_sweep.md](session_reports/2026-05-31_rx_only_sfcw_sweep.md)

**Next step:** First calibrated TX/RX experiment -- implement real TX path in
`hardware/bladerf_device.py`, mount bladeRF with known reflector, measure S21,
verify range-profile peak at expected distance.

---

## Session 2026-05-31 (SFCW post-processing + next-phase preparation)

**Goal:** Convert the RX-only SFCW sweep into a validated engineering milestone and
prepare the TX/RX next phase, without transmitting.

**Hardware actions:** None. No bladeRF. No RF. No TX. No motors. No human subject.
Pure offline analysis and infrastructure work.

**Files created:**
- [`processing/rx_sfcw_postprocess.py`](../processing/rx_sfcw_postprocess.py) --
  hardware-independent postprocessing module: `remove_dc_component`,
  `normalize_h_magnitude`, `subtract_reference_h`, `smooth_h_magnitude`,
  `estimate_noise_floor_db`, `find_prominent_range_bins`, `summarize_range_profile`.
  No bladeRF import. All docstrings explain RX-only H(f) is NOT a radar transfer function.
- [`tests/test_rx_sfcw_postprocess.py`](../tests/test_rx_sfcw_postprocess.py) --
  57 new unit tests (synthetic data only, no hardware).
- [`experiments/analyze_latest_rx_sfcw_sweep.py`](../experiments/analyze_latest_rx_sfcw_sweep.py) --
  offline analysis script: finds latest capture data (falls back to synthetic if absent),
  applies postprocessing pipeline, generates 4 output files.
- [`reports/session_reports/2026-05-31_rx_sfcw_postprocess_and_next_phase.md`](2026-05-31_rx_sfcw_postprocess_and_next_phase.md) --
  Spanish session report (14 sections).
- [`thesis/addendum_rx_only_sfcw_pipeline.md`](../thesis/addendum_rx_only_sfcw_pipeline.md) --
  Spanish academic addendum for thesis chapters 6/7: methodology, results,
  RX-only vs calibrated radar distinction, preparation for TX/RX phase.
- [`docs/prompts/next_phase_tx_safety_plan.md`](../docs/prompts/next_phase_tx_safety_plan.md) --
  Detailed TX safety plan: ordered steps (load test first, then antenna), per-step
  requirements, frequency/power checklist, session prompt template.

**Post-processing outputs (generated locally, not committed):**
- `reports/generated/rx_sfcw_postprocess_h_comparison.png`
- `reports/generated/rx_sfcw_postprocess_range_comparison.png`
- `reports/generated/rx_sfcw_postprocess_peak_table.md`
- `reports/generated/rx_sfcw_postprocess_summary.md`

**Key technical findings:**
- DC removal (`remove_dc_component`) eliminates the 0-range IFFT spike caused by
  the mean of the noise H(f) vector; the range profile now shows the distributed noise floor.
- Normalization and smoothing allow visual comparison of H(f) shapes between sweeps.
- `find_prominent_range_bins` with +6 dB threshold detected a small number of bins
  elevated above the median -- consistent with ISM interference, NOT physical targets.
- Analysis script falls back to synthetic Gaussian noise if real data is absent,
  keeping the pipeline runnable in any environment.

**Scientific honesty:** H(f) from RX-only captures = coherent mean of environmental
noise. Range profile = noise IFFT. No target detection. No SAR imaging. No clinical claims.

**Test results:** 182/182 passed (57 new + 125 prior), no regressions.

**Next step (next TX session):**
1. Implement `configure_tx()` + `enable_tx()` in `hardware/bladerf_device.py` with safety locks.
2. Run `experiments/run_bladerf_tx_load_test.py` -- TX into 50-ohm load, no antenna,
   < 1 second, user present, explicit confirmation.
3. If load test passes: first TX with antenna toward metallic reflector at known distance.
4. See `docs/prompts/next_phase_tx_safety_plan.md` for complete ordered plan.

---

## Session 2026-05-31 -- OFDM pivot source notes + TX infrastructure

**Goal:** Mirror Notion OFDM/UWB/SAR source notes into repo-local Markdown; build supervised TX/RX reflector experiment infrastructure.

**Hardware actions:** None. No RF. No TX. No bladeRF. No motors.

**Files created:**
- [`docs/sources/ofdm_uwb_sar_fuentes_consolidadas.md`](../docs/sources/ofdm_uwb_sar_fuentes_consolidadas.md) -- Canonical repo-local mirror of Notion "OFDM UWB SAR -- lectura consolidada de fuentes". Establishes UWB-OFDM-SAR as the primary architecture: OFDM is the sounding waveform, H[k]=Y[k]/X[k] is the channel estimate, SFCW/RX-only is reclassified as infrastructure validation, H(f,x_az) is the final data product for SAR backprojection.
- [`docs/ofdm_effective_bandwidth_bladerf.md`](../docs/ofdm_effective_bandwidth_bladerf.md) -- Canonical repo-local mirror of Notion "OFDM -- analisis de ancho de banda efectivo con bladeRF". Documents 15 factors that reduce effective BW (analog/digital filters, guard subcarriers, DC null, CP sizing, PAPR, ADC quantization, sync error, CFO/SFO, ICI, inter-block phase jumps, stitching, external interference, antenna response). Recommends conservative start: Fs=20-40 MS/s, N_fft=256-1024, central subcarriers only.
- [`hardware/safety.py`](../hardware/safety.py) (modified) -- Added TX safety constants and validators: `validate_tx_duration_s`, `validate_tx_gain_db`, `validate_tx_antenna_mode`, `validate_reflector_distance_m`, `validate_no_subject_flags`, `validate_no_motion_flags`, `require_reflector_setup_ready`.
- [`hardware/bladerf_device.py`](../hardware/bladerf_device.py) (modified) -- Implemented real TX path: `configure_tx()`, `enable_tx()`, `transmit_cw_burst()` with always-disable finally block, `_transmit_cw_burst_real()` via sync_tx.
- [`tests/test_bladerf_device.py`](../tests/test_bladerf_device.py) (modified) -- Added 38 new TX safety and real-mode tests (subject flags, motion flags, duration, gain, antenna mode, reflector distance, fake-backend TX, finally-block disable).
- [`configs/tx_rx_reflector_1m.yaml`](../configs/tx_rx_reflector_1m.yaml) -- Reflector experiment config: 2.3-2.5 GHz, 20 MHz step, 11 points, 20 ms TX/freq, -20 dB TX gain.
- [`docs/reflector_experiment_setup.md`](../docs/reflector_experiment_setup.md) -- Physical setup guide in Spanish.
- [`experiments/run_bladerf_tx_rx_reflector.py`](../experiments/run_bladerf_tx_rx_reflector.py) -- Supervised TX/RX reflector script: --prepare-only, --pilot, --background, --reflector, --analyze, --run-sequence. Requires "REFLECTOR SETUP READY" + "CONFIRM HARDWARE RUN" before any real TX.

**Architecture decision:** Project is officially UWB-OFDM-SAR. SFCW/RX-only is infrastructure. OFDM is the primary waveform. Notion pages are mirrors only; repo files are canonical.

**Test results:** 220/220 passed (38 new TX tests + 182 prior). No regressions.

**Next step:** Run supervised TX/RX reflector experiment (user physically present, confirmation required). Then reorient repo to full UWB-OFDM-SAR architecture: `processing/ofdm_channel.py`, `simulation/ofdm_uwb_sar_simulator.py`.

---

## Session 2026-05-31 -- CIERRE (commit 61027df, sin actividad nueva)

**Tipo:** Cierre de sesion -- reanudacion de contexto solamente.

**Resumen:** La sesion de trabajo tecnico de post-procesamiento SFCW habia sido completada y commiteada (`61027df`) antes de este bloque de contexto. En esta instancia solo se resumio el estado del repositorio, se confirmo que el working tree estaba limpio (182/182 tests pasando), y se ejecuto el skill `radar-session-close`. No se creo ni modifico codigo fuente. No se accedio a hardware.

**Hardware:** Ninguna accion de hardware.

**Tests:** 182/182 pasando (sin cambios desde `61027df`).

**Informe de cierre:** [reports/session_reports/2026-05-31_cierre_sesion_postproceso_sfcw.md](session_reports/2026-05-31_cierre_sesion_postproceso_sfcw.md)

**Proximo paso:** Implementar `configure_tx()` y `enable_tx()` en `hardware/bladerf_device.py` con bloqueos de seguridad, y crear `experiments/run_bladerf_tx_load_test.py`. Ver plan completo en `docs/prompts/next_phase_tx_safety_plan.md`.

---

## Session 2026-05-31 -- CIERRE (post-compactacion, sin actividad nueva)

**Tipo:** Cierre de sesion -- reanudacion tras compactacion de contexto.

**Resumen:** El trabajo tecnico de la sesion anterior (infraestructura TX + notas fuente OFDM) ya estaba commiteado y pusheado como `d4b9814` antes de que se iniciara este bloque de contexto. En esta instancia el usuario ejecuto `/compact` y luego el skill `radar-session-close`. No se creo ni modifico codigo fuente. No se accedio a hardware.

**Hardware:** Ninguna accion de hardware.

**Tests:** 220/220 pasando (sin cambios desde `d4b9814`).

**Informe detallado:** [reports/session_reports/2026-05-31_infraestructura_tx_y_pivot_ofdm.md](session_reports/2026-05-31_infraestructura_tx_y_pivot_ofdm.md)

**Proximo paso A (hardware):** `py experiments/run_bladerf_tx_rx_reflector.py --run-sequence` -- experimento supervisado TX/RX con reflector metalico a ~1 m. Requiere presencia fisica del usuario y las frases "REFLECTOR SETUP READY" y "CONFIRM HARDWARE RUN".

**Proximo paso B (offline):** Crear `processing/ofdm_channel.py` (CP removal, FFT, H[k]=Y[k]/X[k]) y `simulation/ofdm_uwb_sar_simulator.py` (generacion de simbolo OFDM, simulacion de canal, H(f, x_az) sintetico).
