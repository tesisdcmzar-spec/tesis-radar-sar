# Informe Fase 4: Validacion OFDM y Perfil de Contraste en Distancia

**Fecha:** 2026-06-01
**Arquitectura:** UWB-OFDM-SAR
**Commit base:** 777d85e
**Tipo:** Software/simulacion completado; hardware pendiente de supervision fisica

---

## Objetivo

Validar la cadena de adquisicion y procesamiento OFDM despues del pivote
de arquitectura, y obtener un primer perfil de contraste dielelectrico relativo
versus distancia usando la diferencia de canal H_delta = H_obj - H_bg.

---

## Resultado de verificacion offline

**Tests:** 387/387 pasan.
**Compilacion:** todos los modulos compilan sin errores.
**Simulacion UWB-OFDM-SAR:** imagen SAR sintetica correcta (error de pico: 0.2 cm).
**Single-block prepare-only:** H[k] estimado sobre 120 subportadoras activas.
**Single-block dry-run:** capture_ofdm_block() con backend falso, OK.

OFFLINE_GATE: **PASS**

---

## Resultado de perfil de contraste sintetico

Escenario sintetico de 500 MHz de ancho de banda (representa resultado stitched):
- Fondo: respuesta de cable/antena sintetica a 30 cm.
- Objeto: reflector sintetico a 100 cm.
- H_delta[k] = H_obj - H_bg: contribucion del objeto aislada.
- CIR_delta = IFFT(H_delta * Hanning): perfil de retardo.
- Pico de contraste(R): en ~90 cm (error de ~10 cm = < 1 bin de 30 cm).
- Resolucion en distancia: 30 cm (para BW = 500 MHz).

Figuras generadas:
- `phase4_synthetic_H_background_object.png`
- `phase4_synthetic_H_phase.png`
- `phase4_synthetic_delta_H.png`
- `phase4_synthetic_contrast_vs_distance.png`
- `phase4_synthetic_distance_heatmap.png`

BACKGROUND_OBJECT_GATE (sintetico): **PASS**

---

## Resultado de piloto de stitching

Tres bloques sinteticos en 2.390, 2.400, 2.410 GHz:
- BW total stitched: ~20.9 MHz.
- Subportadoras stitched: 360.
- Resolucion en distancia: ~7.1 m (solo demostracion de pipeline).
- Correccion de desfase de fase: aplicada con overlap-based correction.
- H_total(f): finito, frecuencias ordenadas, sin duplicados.

Figuras generadas:
- `phase4_stitched_H_magnitude.png`
- `phase4_stitched_H_phase.png`
- `phase4_stitched_cir.png`

STITCHING_GATE: **PASS** (dry-run y prepare-only)

---

## Estado del hardware

**RX_GATE:** SKIPPED -- bladeRF no conectado en esta sesion autonoma.
**TX_GATE:** SKIPPED -- requiere supervision fisica del usuario.
**SINGLE_BLOCK_GATE (hardware):** SKIPPED -- requiere supervision fisica.

Los scripts de hardware estan implementados y listos:
- `experiments/run_bladerf_ofdm_phase4_validation.py` -- smoke RX/TX, single-block.
- `experiments/run_phase4_hardware_entrypoint.py --run-supervised` -- secuencia completa.

---

## Por que esto no es permitividad absoluta

La salida de esta fase es un **perfil de contraste dielelectrico relativo**:

```
H_delta[k] = H_obj[k] - H_bg[k]
CIR_delta = IFFT(H_delta * Hanning)
contraste(R) = |CIR_delta(R)| / max(|CIR_delta|)
```

Para obtener permitividad absoluta epsilon_r(r) se requiere:
1. Modelo de propagacion calibrado (respuesta de antena real).
2. Referencia de permitividad conocida (agua, gel, etc.).
3. Inversion del modelo dielectrico.
4. Validacion con fantoma fisico de propiedades conocidas.

Nada de esto existe en la Fase 4. La salida es solo un indicador relativo.

---

## Que se necesitaria para permitividad real

1. Captura de referencia con material de epsilon_r conocida (p.ej. agua pura: epsilon_r ~ 78).
2. Modelo de propagacion con respuesta de antena calibrada en el rango de frecuencias.
3. Algoritmo de inversion (Born, aproximacion dielectrica, etc.).
4. Validacion con al menos 2-3 materiales de propiedades distintas y conocidas.
5. Repetitividad demostrada en condiciones controladas de laboratorio.

Esto es trabajo para la Fase 5 o capitulos posteriores de la tesis.

---

## Limitaciones

1. BW de un bloque (~1 MHz activo): resolucion en distancia ~150 m. No util para 1 m.
2. Piloto de 3 bloques (~23 MHz): resolucion ~6.5 m. Demostracion de pipeline solamente.
3. Sin calibracion de fase entre bloques (correccion parcial con overlap).
4. Sin modelo de antena ni calibracion de cable.
5. Sin validacion experimental de hardware en esta sesion.

---

## Proximo paso

**Intervencion fisica requerida:**

```powershell
py experiments/run_phase4_hardware_entrypoint.py --run-supervised
```

Requiere:
- bladeRF 2.0 micro conectado por USB.
- Antena wideband en TX1 y RX1.
- Reflector metalico a ~1 metro.
- Usuario presente fisicamente.
- Sin personas ni material biologico en la direccion del haz.

---

## Gates finales de esta sesion

| Gate | Estado |
|---|---|
| OFFLINE_GATE | PASS |
| TESTS_GATE | PASS (387/387) |
| SYNTHETIC_DISTANCE_PROFILE_GATE | PASS |
| STITCHING_DRYRUN_GATE | PASS |
| REPORT_GATE | PASS |
| RX_GATE | SKIPPED |
| TX_GATE | SKIPPED |
| SINGLE_BLOCK_HARDWARE_GATE | SKIPPED |
| BACKGROUND_OBJECT_HARDWARE_GATE | SKIPPED |

---

**Sin afirmaciones clinicas. Sin permitividad absoluta. Sin deteccion de cancer.**
