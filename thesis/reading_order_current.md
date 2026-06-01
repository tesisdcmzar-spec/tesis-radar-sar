# Current Reading Order (Phase 5 Heatmap Pipeline)

Last updated: 2026-06-01. Architecture: UWB-OFDM-SAR (primary).

---

## 1. Architecture (start here)

- `docs/architecture_uwb_ofdm_sar.md`
  Canonical system architecture. OFDM is the thesis waveform.
  Defines H[k] = Y[k]/X[k] and the data cube H(f, x_az).

## 2. Effective bandwidth analysis

- `docs/ofdm_effective_bandwidth_bladerf.md`
  Explains why a single bladeRF block has limited BW and why stitching is needed.

## 3. Dielectric interpretation (what we can and cannot claim)

- `docs/ofdm_dielectric_interpretation.md`
  Safe vs. unsafe scientific claims. Required reading before writing thesis chapters.

## 4. Block stitching strategy

- `docs/ofdm_bladerf_block_stitching_plan.md`
  How multiple RF blocks are merged into H_total(f).

## 5. Phase 4 distance-contrast pipeline (1D)

- `docs/phase4_ofdm_distance_contrast_profile.md`
  H_delta[k], CIR_delta, relative contrast profile, range resolution,
  why this is not epsilon_r, what calibration is required.

## 6. Phase 5 dielectric contrast heatmap (2D)

- `docs/phase5_relative_dielectric_contrast_heatmap.md`
  Full 2D pipeline: phantom -> simulate_h_matrix -> backprojection -> heatmap.
  Results, limitations, hardware equivalent.

## 7. Phase 4 distance-contrast thesis addendum

- `thesis/addendum_phase4_ofdm_relative_contrast_profile.md`
  Spanish thesis addendum for 1D contrast profile.

## 8. Phase 5 heatmap thesis addendum

- `thesis/addendum_phase5_relative_dielectric_contrast_heatmap.md`
  Spanish thesis addendum for 2D heatmap simulation.

## 9. Phase 3 closure (SFCW/RX-only reclassified)

- `reports/session_reports/2026-06-01_phase3_closure_after_ofdm_pivot.md`
  Why Phase 3 RX-only SFCW work is now infrastructure validation, not thesis core.

## 10. Phase 4 autonomous preparation report

- `reports/session_reports/2026-06-01_phase4_autonomous_ofdm_preparation.md`
  What was done, what figures were generated, hardware readiness status.

## 11. Phase 5 heatmap sprint report

- `reports/session_reports/2026-06-01_phase5_relative_dielectric_heatmap_software_sprint.md`
  Objectives, scripts, figures, limitations, next hardware step.

## 12. Hardware checklist (before any hardware run)

- `docs/phase4_hardware_intervention_checklist.md`
  Physical setup, exact command, expected outputs, scientific wording guide.

## 13. Source literature notes

- `docs/sources/ofdm_uwb_sar_fuentes_consolidadas.md`
  OFDM radar and UWB-SAR source annotations.

---

## Next hardware step

```powershell
py experiments/run_phase4_hardware_entrypoint.py --run-supervised
```

Requires: bladeRF connected, TX/RX antennas, metallic reflector at ~1 m.
After hardware validation of Phase 4, Phase 5 hardware equivalent would use:
  H_delta = H_obj - H_bg -> backprojection -> 2D relative contrast heatmap.
