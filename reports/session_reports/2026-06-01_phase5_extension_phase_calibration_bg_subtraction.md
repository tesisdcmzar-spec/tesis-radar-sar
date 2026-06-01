# Informe de Sesion: Extension Fase 5 -- Calibracion de Fase y Sustraccion de Fondo

**Fecha:** 2026-06-01
**Tipo de sesion:** Autonoma (software-only, sin hardware)
**Arquitectura:** UWB-OFDM-SAR
**Commit base:** 6af720d (Phase 5 heatmap pipeline)

---

## Objetivo

Extender el pipeline de Fase 5 con tres capacidades nuevas:
1. Modulo de calibracion de fase entre bloques OFDM (necesario para stitching en hardware).
2. Demostracion de sustraccion de fondo en la simulacion 2D (detectar ambas inclusiones).
3. Entrypoint supervisado para escaneo azimutal manual 2D con hardware real.

---

## Que se realizo

### A. Calibracion de fase entre bloques OFDM

**`processing/ofdm_block_phase_calibration.py`** (nuevo):
- `find_overlapping_bins(freqs_lo, freqs_hi, freq_tol_hz)`:
  Encuentra indices de subportadoras con frecuencias coincidentes entre dos bloques.
- `estimate_inter_block_phase_offset(H_lo, f_lo, H_hi, f_hi)`:
  Estima el salto de fase del LO entre bloques adyacentes usando subportadoras solapadas.
  Metodo: phi = angle(mean(H_hi[overlap] * conj(H_lo[overlap]))).
- `apply_phase_correction(H, phase_rad)`:
  Aplica correccion de fase: H_corr = H * exp(-j * phi).
- `calibrate_h_matrix_list(blocks_H, blocks_f)`:
  Calibracion secuencial de N bloques usando el bloque 0 como referencia.
- `phase_calibration_summary(blocks_f, offsets_rad)`:
  Resumen de resultados de calibracion.

Limitacion documentada: solo elimina el termino de fase de orden cero (constante).
Rampas de fase lineales (error de retardo de grupo del LO) NO se corrigen sin una
ruta de calibracion de hardware.

**`tests/test_ofdm_block_phase_calibration.py`** (nuevo, 31 tests):
- TestFindOverlappingBins (6 tests): sin overlap, overlap total, parcial, tolerancia.
- TestEstimateInterBlockPhaseOffset (6 tests): offset conocido recuperado, sin overlap, insufficiente.
- TestApplyPhaseCorrection (5 tests): inverso, magnitud invariante, forma preservada.
- TestCalibrateHMatrixList (8 tests): vacio, 1 bloque, coherencia de fase, referencia.
- TestPhaseCalibrationSummary (5 tests): claves requeridas, conversion de grados.
- TestPhaseCalibrationIntegration (1 test): pico CIR mejora o es igual despues de calibracion.

Nota tecnica: Los tests usan grillas de frecuencia alineadas (mismo df, offset entero)
para garantizar coincidencia exacta de bins. Con grillas no alineadas y tolerancia
insuficiente, no se detectan bins solapados. Esto es comportamiento correcto.

### B. Demostracion de sustraccion de fondo en simulacion 2D

**`experiments/run_relative_permittivity_heatmap_simulation.py`** (actualizado):
- Nuevo escenario de sustraccion de fondo:
  - Reflector metalico de fondo (clutte) en (x=0, z=1.8 m), amplitud=0.8.
  - Escena de fondo: solo el reflector de clutter.
  - Escena de objeto: reflector de clutter + 2 inclusiones dielectricas.
  - H_delta = H_obj - H_bg: elimina el clutter, revela las inclusiones.
- Nueva Figura 6: `background_subtraction_comparison.png`
  - Panel 1: H_obj con clutter (sin sustraccion de fondo).
  - Panel 2: H_obj sin clutter (resultado base de Fase 5).
  - Panel 3: H_delta despues de sustraccion de fondo.

### C. Entrypoint para escaneo azimutal manual 2D

**`experiments/run_phase5_2d_scan_hardware_entrypoint.py`** (nuevo):
- Modos:
  - (default): imprime checklist fisico y sale.
  - `--prepare-only`: vista previa sintetica usando simulacion.
  - `--dry-run`: flujo completo con dispositivo falso (sin hardware).
  - `--run-supervised`: escaneo real con bladeRF, gates interactivos.
- Flujo de `--run-supervised`:
  1. Checklist fisico.
  2. Gate: "CONFIRM HARDWARE RUN".
  3. Gate: "REFLECTOR SETUP READY".
  4. Escaneo de fondo: usuario mueve antena a N posiciones, captura H_bg.
  5. Escaneo de objeto: mismas N posiciones, captura H_obj.
  6. H_delta = H_obj - H_bg -> retroproyeccion -> mapa de calor.
- Calibracion de fase entre bloques aplicada automaticamente en cada posicion.
- Guardado de H_bg_matrix.npy, H_obj_matrix.npy, H_delta_matrix.npy, heatmap.png.
- Verificado: `--prepare-only` PASS, `--dry-run` PASS.

---

## Tests

**477/477 tests pasan.** (+31 nuevos para calibracion de fase)

---

## Uso de hardware

**Hardware:** NO -- software y simulacion pura.
**TX de RF:** NO.
**Movimiento de motor:** NO.

---

## Canales usados

Solo TX1/RX1. TX2/RX2 no mencionados en codigo ejecutable.
Auditoria TX1/RX1: PASS (42 archivos escaneados).

---

## Limitaciones

1. La calibracion de fase requiere bins solapados entre bloques adyacentes.
   Con los 3 bloques de hardware (2.40, 2.42, 2.44 GHz con 20 MHz BW cada uno),
   hay solapamiento de ~80 subportadoras entre bloques adyacentes.
2. La sustraccion de fondo en simulacion muestra el principio pero con
   datos sinteticos -- la validacion real requiere el hardware.
3. La BW disponible con 3 bloques de 20 MHz = 60 MHz BW efectivo,
   resolucion en distancia = c/(2*60e6) ~ 2.5 m (solo demostracion de pipeline).
4. El escaneo azimutal manual requiere posicionamiento fisico preciso (+-1 cm).

---

## Proximo paso

```powershell
# Paso 1: Validacion hardware Fase 4
py experiments/run_phase4_hardware_entrypoint.py --run-supervised

# Paso 2: Escaneo azimutal manual Fase 5 (despues de Paso 1)
py experiments/run_phase5_2d_scan_hardware_entrypoint.py --run-supervised
```

Ambos pasos requieren:
- bladeRF 2.0 micro conectado por USB
- Antenas wideband en TX1 y RX1
- Reflector metalico a ~0.5-1.0 metro de distancia
- Usuario presente fisicamente

---

**Sin afirmaciones clinicas. Sin permitividad absoluta. Sin deteccion de cancer.**
*477/477 tests pasan. TX1/RX1 auditado: PASS.*
