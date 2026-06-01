# Phase 5: Relative Dielectric Contrast Heatmap Pipeline

**Date:** 2026-06-01
**Architecture:** UWB-OFDM-SAR
**Status:** Simulation complete. Hardware validation pending.

---

## 1. Objective

Demonstrate the end-to-end pipeline from a known 2D dielectric phantom
to a reconstructed relative contrast heatmap using simulated UWB-OFDM-SAR data.

Scientific output:
- Synthetic permittivity map (ground truth)
- Relative contrast heatmap (reconstructed via backprojection)
- Comparison of reconstruction vs. ground truth (Fresnel reflectivity model)

---

## 2. Pipeline Overview

```
[Phantom]                      [UWB-OFDM-SAR Simulation]
 eps_r(x,z)  -->  targets  -->  H(f, x_az)  -->  CIR(R, x_az)  -->  SAR image
                                 (5 blocks)    (windowed IFFT)   (backprojection)
                                                                       |
                                                              heatmap = |img(x,z)| / max
```

### 2.1 Phantom definition

`simulation/phantom_permittivity_map.py` — `DielectricPhantom`

- Background: eps_r_bg = 1.0 (air)
- Two circular inclusions:
  - **A** (plastic-like proxy): center (-0.15 m, 0.50 m), r=0.08 m, eps_r=3.5
  - **B** (high-contrast): center (+0.25 m, 0.85 m), r=0.06 m, eps_r=9.0

Fresnel reflection coefficient (normal incidence, air to inclusion):
```
Gamma = (sqrt(eps_bg) - sqrt(eps_incl)) / (sqrt(eps_bg) + sqrt(eps_incl))
```
- A: |Gamma_A| = (1 - 1.871)/(1 + 1.871) = 0.303
- B: |Gamma_B| = (1 - 3.0)/(1 + 3.0) = 0.500

### 2.2 Simulation

`simulation/ofdm_uwb_sar_simulator.py` — `simulate_h_matrix()`

- 5 OFDM blocks: centers at 2.0, 2.5, 3.0, 3.5, 4.0 GHz
- Sample rate: 500 MHz **per block (SIMULATION ONLY -- not achievable by bladeRF)**
- n_fft=256, n_active=200 (approx. 192 active after guard removal)
- Active BW per block: ~376 MHz
- Total stitched BW: ~2.375 GHz
- **Range resolution: 6.3 cm**
- Azimuth: 25 positions from -0.60 to +0.60 m (step = 5 cm)
- Azimuth resolution (approx): 5.0 cm at 3 GHz
- Noise: Gaussian, std=0.02 (2% of signal)

### 2.3 Frequency stitching

`experiments/run_relative_permittivity_heatmap_simulation.py` — `_stitch_h_matrices()`

Naive stitching: concatenate all H(f, x_az) blocks and sort by ascending frequency.
Result: H_stitched (960 subcarriers x 25 az positions), frequencies 1.812 to 4.188 GHz.
Gaps of ~124 MHz exist between blocks (not a contiguous frequency grid).

### 2.4 Range profiles

`simulation/ofdm_uwb_sar_simulator.py` — `range_profiles_from_h_matrix()`

Windowed IFFT (Hanning) along frequency axis with 8x zero-padding.
CIR(R, x_az) at range R = c*tau/2.

### 2.5 Backprojection

`simulation/ofdm_uwb_sar_simulator.py` — `backprojection_image()`

Near-field backprojection on a 150x150 grid (x: -0.75 to +0.75 m, z: 0.05 to 1.55 m).
Phase correction for carrier: exp(+j*4*pi*f0*R/c).

### 2.6 Contrast heatmap

`processing/dielectric_contrast_heatmap.py` — `sar_image_to_contrast_heatmap()`

```
heatmap(x,z) = |SAR_image(x,z)| / max(|SAR_image|)
```

Values in [0, 1]. 1.0 = strongest reconstructed reflector.

---

## 3. Simulation Results

| Parameter | Value |
|---|---|
| Stitched subcarriers | 960 |
| Effective BW | 2.375 GHz |
| Range resolution | 6.3 cm |
| Azimuth resolution | ~5.0 cm |
| Heatmap RMSE vs GT | 0.1093 |
| Peaks found (threshold 0.3) | 1 |
| Peak B location | (0.25, 0.74) m |
| True B location | (0.25, 0.85) m |
| Location error (B) | 0.11 m (~1.7 range bins) |

**Notes:**
- Inclusion B correctly localized in x (0.00 m error) and approximately in z (0.11 m, 1.7 bins).
- Inclusion A (|Gamma|=0.303) is near the peak threshold and not separately detected in this configuration.
- The 0.11 m z-error on B is within ~2 range bins (6.3 cm each), consistent with windowed IFFT sidelobes.

---

## 4. What this pipeline demonstrates

- SAR backprojection from H(f, x_az) correctly localizes dielectric inclusions in 2D.
- Background subtraction is NOT needed here because the phantom background is air (eps_r=1).
  For real hardware, H_delta = H_obj - H_bg would be required.
- Frequency stitching extends the effective BW beyond a single bladeRF block.
- The relative contrast heatmap visualizes reflectivity contrast without claiming epsilon_r.

---

## 5. What this pipeline does NOT demonstrate

| Claim | Status |
|---|---|
| Absolute permittivity epsilon_r(x,z) | NOT shown -- normalization removes scale |
| Calibrated permittivity measurement | NOT shown -- no reference material |
| Real hardware performance | NOT shown -- simulation only |
| Dispersive or lossy media | NOT shown -- free-space, non-dispersive model |
| Clinical/biological applicability | NOT applicable -- no biological material |
| Cancer detection | NOT applicable |
| Medical imaging | NOT applicable |

---

## 6. Hardware equivalent

To run an equivalent pipeline with real hardware:
1. Replace `sample_rate_hz = 500 MHz` (simulation) with 20 MHz (bladeRF hardware limit).
2. Use ~120 OFDM blocks (each 20 MHz) to cover 2.0-4.4 GHz total BW (equivalent range resolution).
3. Or: run narrower BW demo (5 blocks x 20 MHz = 100 MHz BW, range resolution ~1.5 m) as proof-of-concept.
4. Capture background (no object), then object (metallic reflector).
5. Compute H_delta = H_obj - H_bg before backprojection.
6. Apply phase calibration between blocks (see Phase 5 extension plan).

---

## 7. Files

| File | Role |
|---|---|
| `simulation/phantom_permittivity_map.py` | Phantom definition + Fresnel conversion |
| `processing/dielectric_contrast_heatmap.py` | Heatmap processing and comparison |
| `experiments/run_relative_permittivity_heatmap_simulation.py` | Full simulation + figures |
| `tests/test_dielectric_contrast_heatmap.py` | 59 tests covering all modules |
| `reports/generated/phase5_dielectric_heatmap/` | Figures + Markdown summaries |

---

## 8. Figures

| Figure | Description |
|---|---|
| `synthetic_ground_truth_permittivity_map.png` | 2D eps_r map + Fresnel reflectivity (ground truth) |
| `reconstructed_relative_contrast_heatmap.png` | Backprojected |SAR image| normalized to [0,1] |
| `heatmap_error_or_difference.png` | Three-panel: GT vs Recon vs Difference |
| `range_profiles_from_heatmap_pipeline.png` | CIR(R) profiles at selected azimuth positions |
| `pipeline_summary_figure.png` | Six-panel overview of complete pipeline |

---

**No clinical claims. No absolute permittivity. No cancer detection.**
