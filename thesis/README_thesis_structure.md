# Thesis Structure -- UWB-OFDM-SAR Radar Platform

**Project:** Undergraduate thesis -- near-field microwave UWB-OFDM-SAR platform.
**Hardware:** bladeRF 2.0 micro + motorized azimuth stage.
**Architecture:** UWB-OFDM-SAR (OFDM is the primary probing waveform).

---

## Architecture status

The thesis architecture is officially **UWB-OFDM-SAR**:
- OFDM is the central sounding waveform.
- H[k] = Y[k] / X[k] is the channel estimate per subcarrier.
- Multiple RF center-frequency blocks are stitched to synthesize UWB bandwidth.
- H(f, x_az) is the final data product, fed to backprojection for 2D imaging.

**SFCW/RX-only chapters and reports are preliminary hardware/software validation,
not the final thesis architecture.** They should be presented as:
- Phase 1-2: infrastructure validation (simulation pipeline)
- Phase 3: hardware validation (RX-only bladeRF smoke test, frequency survey, SFCW sweep)
- Phase 4+: main thesis results (OFDM TX/RX, multi-block acquisition, SAR imaging)

---

## Proposed Chapter Order (8 chapters, updated)

| Cap | Proposed filename | Current filename | Status |
|-----|------------------|-----------------|--------|
| 1 | `cap1_introduccion.md` | `cap1_introduccion.md` | Draft -- committed |
| 2 | `cap2_marco_teorico.md` | `cap2_marco_teorico.md` | Draft -- needs OFDM addendum |
| 3 | `cap3_simulacion.md` | `cap3_simulacion.md` | Draft -- needs OFDM simulator section |
| 4 | `cap4_adquisicion.md` | `cap4_adquisicion.md` | Draft -- needs OFDM channel module |
| 5 | `cap5_validacion_offline_legacy.md` | `cap4_validacion_offline_legacy.md` | Draft -- needs rename |
| 6 | `cap6_abstraccion_hardware_bladerf.md` | `cap5_abstraccion_hardware_bladerf.md` | Partial -- needs Phase 3 addendum |
| 7 | `cap7_experimentos_phantom.md` | *(does not exist)* | Pending -- write after hardware experiments |
| 8 | `cap8_conclusiones.md` | *(does not exist)* | Pending -- write last |

---

## OFDM sources for each chapter

| Chapter | Key source documents |
|---------|---------------------|
| Cap 2 (Marco teorico) | `docs/architecture_uwb_ofdm_sar.md`, `docs/ofdm_dielectric_interpretation.md`, `docs/sources/ofdm_uwb_sar_fuentes_consolidadas.md` |
| Cap 3 (Simulacion) | `simulation/ofdm_uwb_sar_simulator.py`, `experiments/run_ofdm_uwb_sar_simulation.py` |
| Cap 4 (Adquisicion) | `docs/ofdm_bladerf_block_stitching_plan.md`, `docs/ofdm_effective_bandwidth_bladerf.md`, `processing/ofdm_channel.py` |
| Cap 5 (Validacion offline) | `reports/session_reports/2026-05-31_*.md`, `acquisition/rx_sfcw_sweep.py` |
| Cap 6 (HW abstraction) | `hardware/bladerf_device.py`, `hardware/safety.py`, `experiments/run_bladerf_tx_rx_reflector.py` |
| Cap 7 (Experimentos) | To be written after first TX/RX measurements |

---

## Academic addenda available

| File | Content |
|------|---------|
| `thesis/addendum_rx_only_sfcw_pipeline.md` | RX-only SFCW pipeline (infrastructure validation) |
| `thesis/addendum_ofdm_uwb_sar_architecture.md` | OFDM architecture (main thesis waveform) |

---

## Files that need renaming before final submission

| Current name | Rename to |
|---|---|
| `cap4_validacion_offline_legacy.md` | `cap5_validacion_offline_legacy.md` |
| `cap5_abstraccion_hardware_bladerf.md` | `cap6_abstraccion_hardware_bladerf.md` |

**Do not rename now.** Rename in a single commit when producing the first integrated draft
for the advisor.

---

## What must NOT be claimed in the thesis

- No cancer detection, clinical diagnosis, or medical imaging claims.
- No absolute permittivity mapping without validated inverse model.
- SFCW/RX-only results must be presented as infrastructure validation, not main results.
- Simulation results are mathematical demonstrations, not experimental evidence.

---

## Session reports supporting each chapter

| Chapter | Supporting session reports |
|---------|---------------------------|
| Cap 3 (Simulation) | `2026-05-30_simulation_pipeline_resolution_and_thesis_draft.md` |
| Cap 3 (OFDM sim) | `2026-06-01_project_reorientation_uwb_ofdm_sar.md` |
| Cap 4 (Acquisition) | `2026-05-31_phase2_sfcw_loader.md`, `2026-05-31_rx_only_sfcw_sweep.md` |
| Cap 5 (Offline validation) | `2026-05-31_phase2_offline_closure.md`, `2026-05-31_rx_sfcw_postprocess_and_next_phase.md` |
| Cap 6 (HW abstraction) | `2026-05-31_phase3_bladerf_dry_run_abstraction.md`, `2026-05-31_infraestructura_tx_y_pivot_ofdm.md` |

---

## Immediate next steps

1. Run supervised TX/RX reflector experiment (hardware present, confirmation phrases required).
2. Create `acquisition/ofdm_block_capture.py` (multi-block OFDM capture).
3. Create `processing/ofdm_block_stitcher.py` (block stitching with phase calibration).
4. Update cap2_marco_teorico.md with OFDM theory and dielectric model.
5. Update cap3_simulacion.md with OFDM simulator results.
