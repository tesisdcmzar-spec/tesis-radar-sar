# Thesis Structure — Radar SAR SFCW

**Project:** Undergraduate thesis — near-field SAR microwave radar platform.
**Hardware:** bladeRF 2.0 micro + motorized azimuth stage.
**Code commit reference:** `1e64f1f` (2026-05-31).

---

## Proposed Chapter Order (8 chapters)

| Cap | Final filename (proposed) | Current filename | Status |
|-----|--------------------------|-----------------|--------|
| 1 | `cap1_introduccion.md` | `cap1_introduccion.md` | Draft — committed |
| 2 | `cap2_marco_teorico.md` | `cap2_marco_teorico.md` | Draft — committed |
| 3 | `cap3_simulacion.md` | `cap3_simulacion.md` | Draft — committed |
| 4 | `cap4_adquisicion.md` | `cap4_adquisicion.md` | Draft — committed |
| 5 | `cap5_validacion_offline_legacy.md` | `cap4_validacion_offline_legacy.md` | Draft — needs rename |
| 6 | `cap6_abstraccion_hardware_bladerf.md` | `cap5_abstraccion_hardware_bladerf.md` | Partial draft — needs rename + Phase 3b addendum |
| 7 | `cap7_experimentos_fantasma.md` | *(does not exist)* | Pending — write after Phase 4–5 |
| 8 | `cap8_conclusiones.md` | *(does not exist)* | Pending — write last |

---

## Which files are current drafts

- **Ready for external review:** cap1, cap2, cap3, cap4 (acquisition), cap4 (offline validation).
- **Ready after small update:** cap5 (abstraction) — needs a section on Phase 3b prepared RX path.
- **Not yet written:** cap7 (experiments), cap8 (conclusions).

---

## Files that need renaming before final submission

| Current name | Rename to |
|---|---|
| `cap4_validacion_offline_legacy.md` | `cap5_validacion_offline_legacy.md` |
| `cap5_abstraccion_hardware_bladerf.md` | `cap6_abstraccion_hardware_bladerf.md` |

**Do not rename now.** Rename in a single commit when producing the first integrated draft
for the advisor. Renaming early creates confusion in intermediate sessions.

---

## Session reports that support each chapter

| Chapter | Supporting session reports |
|---------|---------------------------|
| Cap 3 (Simulation) | `2026-05-30_simulation_pipeline_resolution_and_thesis_draft.md` |
| Cap 4 (Acquisition) | `2026-05-31_phase2_sfcw_loader.md`, `2026-05-31_loader_capturas_sfcw.md` |
| Cap 5 (Offline validation) | `2026-05-31_phase2_offline_closure.md` |
| Cap 6 (HW abstraction) | `2026-05-31_phase3_bladerf_dry_run_abstraction.md`, `2026-05-31_phase3_prepare_real_rx_capture.md` |

---

## What must NOT be claimed yet

- No real RX captures have been taken from the bladeRF.
- No RF has been transmitted.
- No azimuth scan data exists from active hardware.
- No experimental SAR image exists.
- The `sc16q11_to_complex()` function has been tested only with synthetic data.

---

## Immediate next steps

1. **Commit cap1_introduccion.md** (untracked as of 2026-05-31).
2. **Add Phase 3b addendum** to `cap5_abstraccion_hardware_bladerf.md`: mention
   `sc16q11_to_complex`, `_import_bladerf`, `_capture_rx_real`, and fake-backend tests.
3. **First supervised real RX capture** (requires hardware presence + `CONFIRM HARDWARE RUN`).
4. **After real capture:** update cap6 with measured IQ amplitude, spectrum, and noise floor.
5. **After azimuth scan:** write cap7 (experiments with dielectric phantom).
