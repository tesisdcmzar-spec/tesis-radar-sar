# Informe de sesion -- Reorientacion del proyecto a UWB-OFDM-SAR

**Fecha:** 2026-06-01
**Tipo:** Sesion de desarrollo -- reorientacion arquitectural completa
**Estado de hardware:** Sin acceso fisico. Sin TX. Sin RX real. Sin motores.
**Commit HEAD:** (pendiente en esta sesion)
**Tests:** 281/281 pasando. Sin regresiones.

---

## 1. Objetivo de la sesion

Reorientar el repositorio a la arquitectura correcta de la tesis: **UWB-OFDM-SAR**. Esta es la correccion arquitectural mas importante del proyecto.

El problema que se buscaba resolver: el repositorio y la documentacion previa describían el sistema como "radar SFCW" con barridos RX-only, cuando la arquitectura correcta de la tesis es OFDM como forma de onda de sondeo principal, con estimacion del canal H[k] = Y[k]/X[k] por subportadora, multiples bloques RF stitcheados para BW sintetico, y apertura sintetica azimutal para imagen 2D.

Objetivos especificos:
1. Crear el modulo de canal OFDM (`processing/ofdm_channel.py`)
2. Crear el simulador OFDM-UWB-SAR (`simulation/ofdm_uwb_sar_simulator.py`)
3. Crear tests unitarios para ambos modulos
4. Crear el script de demo de simulacion offline
5. Crear documentacion arquitectural canonicaen repo
6. Actualizar CLAUDE.md, README.md, y documentacion de tesis

---

## 2. Contexto tecnico previo

Al inicio de la sesion, el repositorio tenia:
- Tests: 220/220 pasando (82 bladeRF, 43 SFCW sweep, 57 SFCW postprocess, 38 TX safety)
- Hardware RX validado: smoke test, survey de 7 frecuencias, barrido SFCW completo
- Infraestructura TX implementada: safety validators, real TX path, script de reflector
- Notas fuente OFDM en repo: `docs/sources/ofdm_uwb_sar_fuentes_consolidadas.md`, `docs/ofdm_effective_bandwidth_bladerf.md`
- Sin modulo de canal OFDM
- Sin simulador OFDM-UWB-SAR
- Sin documentacion arquitectural UWB-OFDM-SAR
- CLAUDE.md sin override de arquitectura

Lo que faltaba:
- `processing/ofdm_channel.py`
- `simulation/ofdm_uwb_sar_simulator.py`
- `tests/test_ofdm_channel.py`
- `tests/test_ofdm_uwb_sar_simulator.py`
- `experiments/run_ofdm_uwb_sar_simulation.py`
- `docs/architecture_uwb_ofdm_sar.md`
- `docs/ofdm_bladerf_block_stitching_plan.md`
- `docs/ofdm_dielectric_interpretation.md`
- `thesis/addendum_ofdm_uwb_sar_architecture.md`
- Override de arquitectura en CLAUDE.md y README.md

---

## 3. Archivos creados

### `processing/ofdm_channel.py`
- **Proposito:** Modulo de estimacion de canal OFDM, sin dependencia de hardware.
- **Longitud:** ~310 lineas
- **Funciones principales:**
  - `generate_bpsk_pilots(n, seed)` -- genera X[k] = {+1, -1} por subportadora
  - `generate_qpsk_pilots(n, seed)` -- genera X[k] con magnitud 1 y cuatro fases
  - `allocate_active_subcarriers(n_fft, n_active, dc_null, guard_bins)` -- indices de subportadoras activas
  - `make_ofdm_symbol(freq_domain, n_fft, cp_len)` -- IFFT + CP
  - `remove_cyclic_prefix(rx_time, cp_len, n_fft)` -- extrae payload
  - `fft_ofdm_symbol(rx_no_cp)` -- FFT
  - `estimate_channel_rx_tx(rx_freq, tx_freq, eps)` -- H[k] = Y[k]/X[k]
  - `channel_impulse_response(H, window)` -- IFFT de H con ventana
  - `estimate_group_delay(freqs_hz, H)` -- tau_g(f) = -d(phase)/d(omega)
  - `estimate_delay_peak(cir, Fs)` -- retardo en segundos desde el pico del CIR
  - `estimate_range_from_delay(tau, c, two_way)` -- rango en metros
  - `simulate_ofdm_channel_from_paths(freqs, paths, two_way)` -- H(f) sintetico
  - `summarize_ofdm_channel(H, freqs, cir, Fs)` -- estadisticas del canal

### `simulation/ofdm_uwb_sar_simulator.py`
- **Proposito:** Simulador UWB-OFDM-SAR completo, sin hardware.
- **Longitud:** ~300 lineas
- **Clases:**
  - `OFDMParameters` -- parametros de un bloque OFDM (n_fft, n_active, cp_len, Fs, f_c, guard_bins, pilot_seed)
  - `PointTarget` -- blanco puntual (x_m, z_m, reflectivity)
- **Funciones:**
  - `simulate_h_block(params, targets, az_pos_m, ...)` -- H[k] para un bloque y posicion azimutal
  - `simulate_h_matrix(params, targets, az_positions_m, ...)` -- H(f, x_az) completo
  - `stitch_blocks(blocks)` -- concatena bloques por frecuencia
  - `range_profiles_from_h_matrix(H_matrix, freqs_hz, ...)` -- IFFT por columna
  - `backprojection_image(H_matrix, freqs_hz, az_m, x_img, z_img, ...)` -- imagen SAR 2D
- **Nota de diseno:** Las frecuencias se ordenan por valor creciente antes de retornar (sort_order), garantizando que el IFFT de range_profiles_from_h_matrix reciba un grid monotono.

### `tests/test_ofdm_channel.py`
- **Proposito:** Tests unitarios para el modulo de canal OFDM.
- **Longitud:** ~280 lineas
- **Tests:** 41 tests, todos pasando.
- **Cobertura:**
  - BPSK/QPSK pilot generation (determinismo, magnitudes, fases)
  - Subcarrier allocation (DC null, guard bins, limites)
  - OFDM symbol construction (longitud, CP = tail of body)
  - CP removal (longitud, slice correcto, error si corto)
  - FFT/IFFT round-trip
  - Channel estimation (recupera H conocida, zeros en pilotes inactivos)
  - CIR peak at expected bin
  - Group delay constante para canal de un trayecto
  - Range estimation two-way / one-way
  - Simulate channel from paths
  - No hardware imports

### `tests/test_ofdm_uwb_sar_simulator.py`
- **Proposito:** Tests unitarios para el simulador OFDM-UWB-SAR.
- **Longitud:** ~270 lineas
- **Tests:** 18 tests, todos pasando.
- **Cobertura:**
  - OFDMParameters properties (df, indices, freqs, centrado)
  - simulate_h_block (shapes, cero sin targets, no-cero con target, ruido)
  - simulate_h_matrix (shape, reproducibilidad con seed)
  - stitch_blocks (ordena y concatena)
  - range_profiles (shape, pico cerca del target, respuesta en cada rango)
  - backprojection_image (shape, pico cerca del target)
  - No hardware imports

### `experiments/run_ofdm_uwb_sar_simulation.py`
- **Proposito:** Demo offline del pipeline UWB-OFDM-SAR completo.
- **Longitud:** ~220 lineas
- **Escena simulada:** 2 blancos (T1: x=-5 cm, z=30 cm; T2: x=8 cm, z=55 cm)
- **Parametros OFDM:** N_fft=512, N_active=400, cp=64, Fs=2 GHz (sintetico), f_c=5 GHz, guard=4
- **Figuras generadas:**
  - `ofdm_sim_h_magnitude.png` -- |H[k]| vs frecuencia y cubo H(f, x_az)
  - `ofdm_sim_range_profiles.png` -- perfil de rango central + waterfall
  - `ofdm_sim_sar_image.png` -- imagen SAR backprojection
- **Resultado:** pico de imagen a 0.2 cm de T1. Pipeline funciona correctamente.

### `docs/architecture_uwb_ofdm_sar.md`
- **Proposito:** Documento canonico de arquitectura del sistema UWB-OFDM-SAR.
- **Contenido:** Por que OFDM, por que SFCW es solo validacion, pipeline completo, ecuaciones clave, relacion con modelo dielectrico, claims defensibles vs. prohibidos, estado del repositorio.

### `docs/ofdm_bladerf_block_stitching_plan.md`
- **Proposito:** Estrategia de adquisicion multi-bloque para sintetizar BW UWB con bladeRF.
- **Contenido:** Los 15 factores que reducen BW efectivo (filtros, guard, DC, CP, PAPR, ADC, sync, CFO/SFO, ICI, phase discontinuity, stitching, interferencia, antenas), parametros recomendados, metadata por bloque, numero de bloques para dR=10 cm.

### `docs/ofdm_dielectric_interpretation.md`
- **Proposito:** Interpretacion fisica de H(f, x_az) en terminos de propiedades dielectricas del medio.
- **Contenido:** Permitividad compleja, modelo Cole-Cole, constante de propagacion gamma, coeficiente de reflexion, lo que H[k] puede y no puede entregar, claims defensibles y prohibidos.

### `thesis/addendum_ofdm_uwb_sar_architecture.md`
- **Proposito:** Addendum academico en espanol para la tesis que corrige la descripcion arquitectural.
- **Contenido:** OFDM como forma de onda principal, H[k] = Y[k]/X[k], H(f, x_az), stitching de bloques, backprojection de campo cercano, Cole-Cole, claims defensibles y estado actual.

---

## 4. Archivos modificados

### `CLAUDE.md`
- Se agrego una seccion "PRIMARY ARCHITECTURE OVERRIDE" al inicio del archivo.
- Contiene: arquitectura es UWB-OFDM-SAR, OFDM es central, SFCW es validacion, producto final es H(f, x_az), no claims clinicos.
- Referencias a los documentos canonicos del repositorio.

### `README.md`
- Reescrito para reflejar la arquitectura UWB-OFDM-SAR.
- Incluye: pipeline de adquisicion y procesamiento, estado de validacion, lo que esta reclasificado, proximos pasos, quick start actualizado.

### `thesis/README_thesis_structure.md`
- Actualizado para reflejar que OFDM es la arquitectura primaria.
- Indica que capitulos SFCW/RX-only son validacion de infraestructura.
- Asocia cada capitulo con los documentos fuente OFDM.

### `tests/test_rx_sfcw_postprocess.py`
- Se corrigo un test fragil (`test_no_bladerf_in_sys_modules`) que fallaba por aislamiento de tests: otro test carga bladerf en sys.modules y el check global fallaba.
- Nuevo test: `test_no_bladerf_added_by_rx_sfcw_postprocess_import` usa delta check (before/after) en lugar de check global.
- La semantica es la misma pero el test es robusto al orden de ejecucion.

---

## 5. Codigo relevante incorporado

### `processing/ofdm_channel.py` -- `estimate_channel_rx_tx`

Ecuacion central del sistema:

```python
def estimate_channel_rx_tx(rx_freq, tx_freq, eps=1e-12):
    active = np.abs(tx_freq) >= eps
    H = np.zeros_like(rx_freq, dtype=complex)
    H[active] = rx_freq[active] / tx_freq[active]
    return H
```

Las subportadoras inactivas (pilotes = 0) no producen division por cero: H[k] = 0 en esas posiciones.

### `simulation/ofdm_uwb_sar_simulator.py` -- sort por frecuencia

```python
H_full = estimate_channel_rx_tx(Y_full, X_full)
H_active = H_full[idx]
sort_order = np.argsort(freqs)
return H_active[sort_order], freqs[sort_order]
```

Las frecuencias activas en FFT-bin order no son monotonicamente crecientes (el bloque positivo va primero, luego el negativo). Para que el IFFT en `range_profiles_from_h_matrix` produzca un CIR correcto, H y freqs se ordenan por frecuencia antes de retornar.

### `simulation/ofdm_uwb_sar_simulator.py` -- backprojection

```python
for i_az, x_ap in enumerate(az_positions_m):
    prof = profiles[:, i_az]
    R = np.sqrt((x_ap - XX)**2 + ZZ**2)
    R_flat = R.ravel()
    real_interp = np.interp(R_flat, range_m, prof.real)
    imag_interp = np.interp(R_flat, range_m, prof.imag)
    carrier = np.exp(1j * 4.0 * np.pi * f0 * R / c)
    img += (real_interp + 1j*imag_interp).reshape(n_x, n_z) * carrier
```

La correccion de portadora `exp(+j*4*pi*f0*R/c)` compensa el termino residual del carrier que aparece en la IFFT de una senal no-banda base (f0 != 0). Sin esta correccion, la imagen SAR pierde coherencia.

---

## 6. Logica tecnica y decisiones de diseno

### Decision 1: Frecuencias ordenadas antes de retornar de simulate_h_block

En FFT-bin ordering, las subportadoras activas tienen frecuencias en orden: [f_c+1*df, ..., f_c+100*df, f_c-100*df, ..., f_c-1*df] (bloque positivo primero, luego negativo). No es monotono. El IFFT de H en este orden produciria una CIR incorrecta con el pico desplazado.

Alternativa considerada: ordenar en `range_profiles_from_h_matrix`. Se eligio ordenar en `simulate_h_block` porque garantiza que el output siempre tenga frecuencias monotonicamente crecientes, lo que simplifica todos los modulos aguas abajo.

### Decision 2: Parametros sinteticos en tests (Fs=2 GHz)

Los tests del simulador usan Fs=2 GHz (sintetico, no real en bladeRF) para obtener resolucion en rango de ~10 cm con n_fft=512 y n_active=400. Esto permite verificar que el pico de backprojection este cerca del blanco. Con Fs=40 MHz reales, se necesitarian mas bloques stitcheados para obtener la misma resolucion.

Esta eleccion es correcta para tests unitarios porque:
- La fisica del OFDM es la misma independientemente de Fs
- Los tests verifican la logica matematica, no los parametros de hardware

### Decision 3: Test de presencia de respuesta vs. top-N peaks

Se descarto usar `np.argsort(mag)[::-1][:2]` para detectar los dos picos porque los bins adyacentes del mismo pico pueden ser los dos mas altos. En su lugar, se verifica que cada blanco tiene una respuesta prominente en una ventana de +-0.15 m alrededor de su rango esperado. Este enfoque es mas robusto y mas fisicamente correcto.

### Decision 4: Estructura de OFDMParameters

Se uso una dataclass con propiedades calculadas (`active_indices`, `active_freqs_hz`, `subcarrier_spacing_hz`) para que todos los modulos accedan a parametros derivados de forma consistente. Alternativa descartada: pasar cada parametro por separado a cada funcion (fragil, propenso a inconsistencias).

---

## 7. Errores encontrados y solucion

### Error 1: Frecuencias no monotonicamente crecientes en simulate_h_block

**Sintoma:** `test_range_profile_peak_near_known_target` fallaba con pico en 0m en lugar de 0.5m. `test_backprojection_peak_near_target` fallaba con pico en el borde de la imagen.

**Causa raiz:** `active_freqs_hz` devuelve frecuencias en orden FFT-bin (bloque positivo, luego negativo), no en orden de frecuencia creciente. El IFFT en `range_profiles_from_h_matrix` interpretaba el vector no-monotono como si fuera contiguo, produciendo CIR incorrecta.

**Solucion:** Agregar `sort_order = np.argsort(freqs)` al final de `simulate_h_block` y devolver H y freqs reordenados por frecuencia creciente.

**Verificacion:** 59/59 tests del modulo OFDM pasan.

### Error 2: Test fragil por aislamiento de sys.modules

**Sintoma:** `test_no_bladerf_in_sys_modules` en `test_rx_sfcw_postprocess.py` fallaba con 281 tests (280 prev + 59 new) aunque pasaba con 220.

**Causa raiz:** Al ejecutar el suite completo con 59 tests adicionales, el orden de ejecucion cambio. `test_import_bladerf_raises_when_not_installed` en `test_bladerf_device.py` usa `patch.dict(sys.modules, {"bladerf": None})`. Si bladerf ya estaba en sys.modules por alguna causa, el patch lo restauraba al valor original. Esto dejaba bladerf en sys.modules para el test posterior.

**Solucion:** Reemplazar el check global por un delta check: guardar el estado de sys.modules antes de importar el modulo y verificar que bladerf no se agrega en esa importacion especifica.

**Verificacion:** 281/281 tests pasan.

### Error 3: "bladerf" en docstring del simulador detectado por test de imports

**Sintoma:** `test_no_hardware_import_in_simulator` fallaba porque el docstring del simulador contiene la palabra "bladeRF" (como descripcion de hardware, no como import).

**Causa raiz:** El test buscaba la substring "bladerf" en el source del modulo, que matcheaba el docstring "No bladeRF. No USB."

**Solucion:** Cambiar el check a buscar `"import bladerf"` y `"from bladerf"` (patrones de import real) en lugar de la substring "bladerf" sola.

**Verificacion:** Test pasa.

---

## 8. Comandos ejecutados

| Comando | Resultado |
|---------|-----------|
| `py -m compileall processing/ofdm_channel.py simulation/ofdm_uwb_sar_simulator.py ...` | OK |
| `py -m pytest tests/test_ofdm_channel.py tests/test_ofdm_uwb_sar_simulator.py -v` | 56/59 inicialmente (3 fallos) |
| `py -m pytest tests/test_ofdm_channel.py tests/test_ofdm_uwb_sar_simulator.py -q` | 59/59 despues de fixes |
| `py -m pytest -q` | 281/281 pasando |
| `py experiments/run_ofdm_uwb_sar_simulation.py` | OK -- peak a 0.2 cm del target T1 |

---

## 9. Tests y validacion

**Total:** 281 tests, 281 pasando.

**Nuevos en esta sesion:** 61 tests
- `tests/test_ofdm_channel.py`: 41 tests
- `tests/test_ofdm_uwb_sar_simulator.py`: 18 tests
- 2 tests modificados en `tests/test_rx_sfcw_postprocess.py` (cambio de test fragil)

**Tests previos:** 220 tests (sin cambios en el codigo que testean)

**Cobertura de la arquitectura OFDM:**
- Generacion de pilotes BPSK/QPSK
- Asignacion de subportadoras activas con DC null y guard bins
- Construccion y remocion de prefijo ciclico
- Round-trip FFT/IFFT
- Estimacion del canal H[k] = Y[k]/X[k] (incluye caso de pilotes inactivos)
- Respuesta impulsional del canal y estimacion de retardo/rango
- Grupo de retardo constante para canal de un trayecto
- Simulacion de H(f) desde blancos puntuales con fase correcta
- Pipeline completo simulador: H[k] -> H(f, x_az) -> range profiles -> imagen SAR
- Pico de imagen a <0.2 cm del blanco T1 en el script de demo

---

## 10. Resultados de la demo de simulacion

**Script:** `py experiments/run_ofdm_uwb_sar_simulation.py`

**Escena:**
- T1: x=-5.0 cm, z=30.0 cm, |rho|=1.00
- T2: x=8.0 cm, z=55.0 cm, |rho|=0.70

**Parametros OFDM (sinteticos):**
- N_fft=512, N_active=400 (392 efectivos con guard=4)
- cp=64, Fs=2 GHz, f_c=5 GHz
- BW efectivo: 1531 MHz, dR teorico: 9.8 cm

**Resultado:**
- H_matrix: (392, 21) -- 392 subportadoras, 21 posiciones azimutales
- Canal en azimut central: mag_mean=1.0682, dyn_range=15.7 dB
- Pico de imagen SAR: x=-4.9 cm, z=30.2 cm
- Target T1: x=-5.0 cm, z=30.0 cm
- **Distancia pico-target: 0.2 cm** (bien dentro del rango de resolucion)

**Figuras generadas:**
- `reports/generated/ofdm_sim_h_magnitude.png`
- `reports/generated/ofdm_sim_range_profiles.png`
- `reports/generated/ofdm_sim_sar_image.png`
- `reports/generated/ofdm_uwb_sar_simulation_summary.md`

---

## 11. Relacion con la tesis

**Adquisicion:** La implementacion de `processing/ofdm_channel.py` es la base del pipeline de adquisicion OFDM real. Las funciones `remove_cyclic_prefix`, `fft_ofdm_symbol`, y `estimate_channel_rx_tx` se usaran directamente con IQ real del bladeRF.

**Simulacion:** `simulation/ofdm_uwb_sar_simulator.py` es el simulador principal de la tesis. Reemplaza al simulador SFCW sintetico como fuente de datos de referencia para validar el pipeline.

**Procesamiento DSP:** `channel_impulse_response`, `estimate_group_delay`, y `estimate_delay_peak` implementan el DSP de canal necesario para la tesis.

**Reconstruccion SAR:** El `backprojection_image` del simulador reutiliza la misma logica del `sar_reconstruction.py` existente, con la adaptacion para frecuencias OFDM ordenadas y correccion de portadora.

**Redaccion de capitulos:** Los documentos creados (`docs/architecture_uwb_ofdm_sar.md`, `docs/ofdm_bladerf_block_stitching_plan.md`, `docs/ofdm_dielectric_interpretation.md`, `thesis/addendum_ofdm_uwb_sar_architecture.md`) proveen el material para el capitulo de marco teorico y de metodologia.

**Claims cientificos defensibles:** Los datos de simulacion muestran que el pipeline es matematicamente correcto (pico a 0.2 cm del target). Esto es un resultado de validacion de la plataforma, no de medicion experimental.

---

## 12. Fuentes y trazabilidad

**Fuentes internas:**
- `docs/sources/ofdm_uwb_sar_fuentes_consolidadas.md` -- fuentes de literatura (Josa TIF, Braun, CP-OFDM SAR)
- `docs/ofdm_effective_bandwidth_bladerf.md` -- analisis de BW del bladeRF
- `processing/sar_reconstruction.py` -- referencia para logica de backprojection y correccion de portadora
- `simulation/synthetic_scan.py` -- referencia para `SyntheticScan` (patron reutilizado en OFDMParameters)
- Commits previos: `d4b9814` (OFDM pivot source notes), `61027df` (SFCW postprocess)

**Fuentes externas:** No se consulto internet en esta sesion. Las fuentes bibliograficas estan referenciadas en los documentos internos del repositorio.

---

## 13. Problemas abiertos

1. **Multi-bloque OFDM (stitching real):** `stitch_blocks` en el simulador hace concatenacion naive sin calibracion de fase. Para hardware real se necesita `processing/ofdm_block_stitcher.py` con calibracion de fase inter-bloque.

2. **Sincronizacion temporal OFDM:** No implementada. El simulador asume sincronizacion perfecta. En hardware real se necesita correlacion con preambulo para encontrar el inicio del simbolo.

3. **Modelo Cole-Cole en simulador:** El simulador usa propagacion en espacio libre (c constante). Para modelar tejido biologico se necesita aplicar gamma(f) de Cole-Cole a cada trayectoria.

4. **Primer experimento TX/RX real:** El script esta listo pero el experimento no se ha ejecutado. Requiere presencia fisica del usuario.

5. **Azimut activo:** El motor de azimut no esta integrado aun. Los experimentos futuros requeriran control del motor y sincronizacion con la captura OFDM.

6. **Test de aislamiento de test_bladerf_device:** Revisar si algun test en ese modulo carga bladerf en sys.modules. El delta check en test_rx_sfcw_postprocess.py es una workaround, no una solucion raiz.

---

## 14. Proximo paso exacto

**Opcion A (hardware):** Ejecutar el experimento TX/RX de reflector cuando el usuario este disponible:
```
py experiments/run_bladerf_tx_rx_reflector.py --run-sequence
```

**Opcion B (offline, siguiente modulo logico):** Crear `acquisition/ofdm_block_capture.py`:
- Funcion `capture_ofdm_block(device, params)` que usa `transmit_cw_burst` + `capture_rx` del bladeRF
- Retorna H[k] para un bloque
- Sin sincronizacion de preambulo (primera version)
- Tests con fake backend

**Por que este orden:** El experimento de reflector valida el hardware TX/RX. El modulo de captura OFDM generaliza esa captura. Ambos requieren hardware. Si no hay hardware disponible, el siguiente paso offline es el stitcher.

**Que NO conviene hacer todavia:** Implementar sincronizacion de simbolo o stitching con calibracion de fase antes de tener captura real basica.

---

## 15. Commit sugerido

```
Reorient project to UWB-OFDM-SAR architecture

- OFDM is now the primary waveform architecture.
  H[k] = Y[k] / X[k] is the channel estimate per subcarrier.
  H(f, x_az) is the final acquisition data product.
- SFCW/RX-only work retained as infrastructure validation.

- Add processing/ofdm_channel.py: pilot generation (BPSK/QPSK),
  subcarrier allocation, OFDM symbol construction, CP removal,
  FFT, channel estimation, CIR, group delay, range estimation,
  synthetic channel from paths, channel summary.

- Add simulation/ofdm_uwb_sar_simulator.py: OFDMParameters,
  PointTarget, simulate_h_block, simulate_h_matrix, stitch_blocks,
  range_profiles_from_h_matrix, backprojection_image.
  Frequencies returned sorted by value for correct IFFT.

- Add experiments/run_ofdm_uwb_sar_simulation.py: 2-target scene,
  H(f, x_az) simulation, range profiles, SAR image. Peak at 0.2 cm
  from target. Figures saved to reports/generated/.

- Add bladeRF block stitching plan (docs/ofdm_bladerf_block_stitching_plan.md):
  15 BW-reduction factors, conservative parameters, metadata schema,
  phase continuity problem, block overlap strategy.

- Add dielectric interpretation doc (docs/ofdm_dielectric_interpretation.md):
  Cole-Cole model, gamma(f), reflection coefficient, safe/unsafe claims.

- Add canonical architecture doc (docs/architecture_uwb_ofdm_sar.md):
  full pipeline, key equations, SFCW reclassification.

- Update CLAUDE.md with PRIMARY ARCHITECTURE OVERRIDE.
- Update README.md: UWB-OFDM-SAR architecture, validated work,
  reclassified work, next steps.
- Update thesis/README_thesis_structure.md: OFDM primary, chapter mapping.
- Add thesis/addendum_ofdm_uwb_sar_architecture.md: academic addendum.

- Add 61 new tests (41 ofdm_channel, 18 ofdm_simulator, 2 revised).
  281/281 tests pass. No regressions.

- No hardware actions. No RF transmission. No clinical claims.
```
