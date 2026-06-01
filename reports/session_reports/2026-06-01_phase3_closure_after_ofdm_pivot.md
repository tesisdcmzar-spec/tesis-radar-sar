# Cierre Formal de Fase 3 despues del Pivote UWB-OFDM-SAR

**Fecha:** 2026-06-01
**Estado:** Cierre de Fase 3 -- validacion offline completa post-pivote
**Commit de referencia:** 777d85e (Add OFDM single-block acquisition and stitching layer)
**Commit de arquitectura:** f365e39 (Reorient project to UWB-OFDM-SAR architecture)

---

## 1. Que valido originalmente la Fase 3

La Fase 3 consistio en la validacion del hardware RX-only del bladeRF:

- **Smoke test RX:** apertura del dispositivo, captura de IQ, verificacion de nivel de ruido.
- **Survey de frecuencias:** barrido RX en bandas de 400 MHz a 4 GHz para identificar niveles de ruido y senales de interferencia.
- **Barrido SFCW RX-only:** captura de multiples frecuencias de center para simular un barrido SFCW.
- **Postproceso SFCW:** perfil de rango RX-only usando H[k] estimado sin transmision propia.

Resultado: el bladeRF captura IQ con SNR razonable, sin clipping severo, con respuesta espectral coherente.

---

## 2. Por que el pivote OFDM cambia la interpretacion

El commit f365e39 reorienta la arquitectura del proyecto de SFCW a UWB-OFDM-SAR:

- La forma de onda de sondeo principal es ahora OFDM, no SFCW.
- H[k] = Y[k] / X[k] (estimacion piloto por subportadora), no H[k] = Y[k] / X_cw.
- El producto de adquisicion es H(f, x_az): funcion de transferencia del canal versus frecuencia y posicion azimutal.
- La imagen SAR se obtiene por retroproyeccion de H(f, x_az), no por SFCW.

En consecuencia:
- Los resultados SFCW RX-only son **validacion de infraestructura**, no el objetivo de la tesis.
- Los perfiles de rango SFCW son referencias de calibracion, no la imagen final.
- El barrido de frecuencias es util para identificar bandas limpias para TX OFDM.

---

## 3. Lo que sigue siendo valido de la Fase 3

- **Hardware bladeRF operativo:** el dispositivo abre, captura IQ, y presenta niveles de ruido normales.
- **Abstraccion BladeRFDevice:** `hardware/bladerf_device.py` con dry_run, confirmacion, y close() seguro.
- **Capa de seguridad:** `hardware/safety.py` con limites de ganancia, duracion TX, y flags de sujeto.
- **Captura SFCW como referencia:** util para calibrar la respuesta del canal antes de TX OFDM.
- **Survey de frecuencias:** identifica 2.4 GHz como banda limpia inicial para TX/RX OFDM.
- **Tests 347/347:** todos los tests de Fase 3 siguen pasando.

---

## 4. Lo que se reclasifica como validacion de infraestructura

Los siguientes componentes de Fase 3 son ahora **infraestructura de soporte**, no el pipeline principal:

| Componente | Nueva clasificacion |
|---|---|
| `acquisition/rx_sfcw_sweep.py` | Infraestructura: captura RX para calibracion |
| `processing/rx_sfcw_postprocess.py` | Infraestructura: perfil de rango de referencia |
| `experiments/run_bladerf_rx_sfcw_sweep.py` | Infraestructura: barrido de calibracion |
| Figuras `rx_sfcw_*` | Referencia de validacion hardware |

Estos modulos no se eliminan; se conservan como herramientas de calibracion y comparacion.

---

## 5. Nuevos componentes OFDM offline de Fase 3 post-pivote

Los siguientes modulos se implementaron como parte del pivote y constituyen el nucleo de la tesis:

| Componente | Funcion |
|---|---|
| `processing/ofdm_channel.py` | H[k]=Y[k]/X[k], CIR, retardo, rango, simulacion de canal |
| `simulation/ofdm_uwb_sar_simulator.py` | Simulacion UWB-OFDM-SAR: H(f, x_az), range profiles, backprojection |
| `acquisition/ofdm_block_capture.py` | Captura de un bloque OFDM, estimacion H[k] |
| `processing/ofdm_block_stitcher.py` | Stitching de multiples bloques en H_total(f) |
| `hardware/bladerf_device.py` | transmit_iq_burst() para TX OFDM arbitrario |

Todos estos modulos tienen tests exhaustivos y funcionan sin hardware.

---

## 6. Por que la Fase 3 puede considerarse cerrada

La Fase 3 esta cerrada porque:

1. El hardware bladeRF fue validado (RX operativo, niveles de ruido normales).
2. La abstraccion BladeRFDevice esta implementada y probada con backend falso.
3. La capa de seguridad esta operativa (confirmaciones, limites de ganancia, flags).
4. El pivote OFDM no invalida estos logros; los reutiliza.
5. Todos los tests siguen pasando (347/347 -> 387/387 con los nuevos de Fase 4).
6. La simulacion UWB-OFDM-SAR funciona offline (imagen SAR sintetica con error < 0.2 cm).

La Fase 3 no requiere rehacer su hardware RX. Sus resultados de validacion son correctos y se conservan.

---

## 7. Lo que la Fase 4 debe validar

La Fase 4 (en progreso) debe validar:

1. **TX OFDM real:** transmit_iq_burst() funciona con bladeRF fisico.
2. **H[k] real:** estimacion del canal OFDM en un bloque de hardware real.
3. **Sustraccion de fondo:** H_delta[k] = H_obj - H_bg con objeto real.
4. **Perfil de contraste relativo:** IFFT(H_delta) -> indicador de reflectividad vs distancia.
5. **Stitching piloto:** 3 bloques adyacentes stitched en H_total(f).

Lo que la Fase 4 NO debe afirmar todavia:
- Permitividad absoluta epsilon_r(r).
- Deteccion de cancer o tumor.
- Imagen SAR calibrada de material biologico.

---

## 8. Estado de los gates al cierre de Fase 3

- OFFLINE_GATE: PASS (compile, tests 387/387, simulation, prepare-only, dry-run)
- STITCHING_DRYRUN_GATE: PASS
- SYNTHETIC_DISTANCE_PROFILE_GATE: PASS
- RX_GATE: PASS (validado en session anterior con hardware real)
- TX_GATE: SKIPPED (requiere supervision fisica)
- SINGLE_BLOCK_HARDWARE_GATE: SKIPPED (requiere supervision fisica)

**Sin afirmaciones clinicas. Sin permitividad absoluta. Sin deteccion de cancer.**
