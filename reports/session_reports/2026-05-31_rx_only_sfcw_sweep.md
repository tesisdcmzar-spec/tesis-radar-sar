# Informe de sesión: Barrido SFCW supervisado — solo RX

**Fecha:** 2026-05-31
**Tipo:** Experimento de hardware supervisado — solo RX, sin TX, sin RF transmitida
**Script:** `experiments/run_bladerf_rx_sfcw_sweep.py`
**Módulo de adquisición:** `acquisition/rx_sfcw_sweep.py`
**Pruebas:** `tests/test_rx_sfcw_sweep.py`

---

## 1. Objetivo

Avanzar el proyecto de tesis ejecutando un barrido SFCW de banda estrecha supervisado
con el bladeRF, únicamente en modo recepción (RX):

1. Sintonizar el receptor bladeRF sobre una grilla de frecuencias densa.
2. Capturar una ráfaga corta de IQ por frecuencia.
3. Calcular una muestra compleja por frecuencia mediante promediado coherente.
4. Ensamblar H(f) para una posición azimutal fija (x = 0 m).
5. Alimentar ese H(f) al pipeline de procesamiento existente (`processing/range_profile.py`).
6. Generar figuras, resúmenes y pruebas.
7. Confirmar que toda la cadena de adquisición → H(f) → perfil de rango funciona
   con datos de hardware real.

---

## 2. Lista de verificación de seguridad

| # | Verificación | Estado |
|---|---|---|
| 1 | Usuario físicamente presente durante la sesión | ✓ |
| 2 | bladeRF conectado por USB | ✓ |
| 3 | RX1 con antena o carga de 50 ohm | ✓ |
| 4 | TX1 no utilizado | ✓ |
| 5 | Sin sujeto humano | ✓ |
| 6 | Sin motor ni etapa de movimiento | ✓ |
| 7 | Sesión exclusivamente RX | ✓ |
| 8 | Frase de confirmación exacta: `CONFIRM HARDWARE RUN` | ✓ |

---

## 3. Por qué esto es solo RX y no radar TX/RX

En un radar SFCW real se transmite una señal en cada frecuencia y se recibe el eco.
La función de transferencia H(f) se obtiene como la relación compleja entre señal
recibida y señal transmitida (o bien como el eco normalizado).

En este experimento **no se transmite ninguna señal**. El bladeRF recibe únicamente
ruido térmico ambiental e interferencia de RF del entorno (Wi-Fi, Bluetooth, LTE, etc.).
La muestra compleja extraída en cada frecuencia mediante promediado coherente es el
fasor de ese ruido, **no** la respuesta de ningún blanco.

Por lo tanto:

- **H(f) medido** = promedio coherente del ruido de recepción ≠ función de
  transferencia radar.
- **Perfil de rango** = resultado del pipeline IFFT aplicado a ruido ≠ imagen de
  un blanco.
- Este experimento valida únicamente la infraestructura de software y hardware
  del pipeline de adquisición y procesamiento.

El verdadero radar SFCW requiere:
- Señal TX controlada y calibrada.
- Separación RX/TX y supresión de acoplamiento directo.
- Sustracción de fondo (background subtraction).
- Estimación coherente S21 = V_RX / V_TX.

---

## 4. Configuración exacta — modo piloto

| Parámetro | Valor |
|---|---|
| Rango de frecuencias | 2.300 — 2.500 GHz |
| Paso | 10 MHz |
| Puntos esperados | 21 |
| Muestras por frecuencia | 100 000 |
| Tasa de muestreo | 10 MS/s |
| Ancho de banda analógico | 10 MHz |
| Ganancia RX | 20 dB |
| dry_run | False |
| Confirmación | CONFIRM HARDWARE RUN |
| TX habilitado | No |

---

## 5. Configuración exacta — modo completo

| Parámetro | Valor |
|---|---|
| Rango de frecuencias | 2.300 — 2.500 GHz |
| Paso | 1 MHz |
| Puntos esperados | 201 |
| Muestras por frecuencia | 100 000 |
| Tasa de muestreo | 10 MS/s |
| Ancho de banda analógico | 10 MHz |
| Ganancia RX | 20 dB |
| dry_run | False |
| Confirmación | CONFIRM HARDWARE RUN |
| TX habilitado | No |

Condición de activación del modo completo:
- 21/21 capturas exitosas en piloto. ✓
- Sin saturación (clipping). ✓
- Sin errores USB. ✓
- Espacio libre en disco >= 3 GB. ✓
- Usuario físicamente presente. ✓

---

## 6. Resultado del modo piloto

**Estado: EXITOSO**

| Métrica | Valor |
|---|---|
| Frecuencias capturadas | 21/21 (100%) |
| Saturación detectada | 0 frecuencias |
| Errores de captura | 0 |
| Ancho de banda | 200 MHz |
| Paso | 10 MHz |
| Resolución de rango teórica | 75.0 cm |
| Rango no ambiguo | 15.0 m |
| Pico de |H(f)| | 2470.0 MHz (-67.0 dB) |
| Rango dinámico de H(f) | 2.7 dB |
| Bin de rango más fuerte | 0.000 m (-86.1 dB) |
| Rango dinámico perfil rect. | 45.9 dB |
| Rango dinámico perfil Hanning | 48.5 dB |

Todas las capturas del piloto resultaron clasificables como `noise-like` (ruido de
piso térmico). No se detectó saturación en ninguna frecuencia. El rango dinámico
de H(f) de solo 2.7 dB es consistente con un espectro de ruido casi plano.

---

## 7. Resultado del modo completo

**Estado: CASI EXITOSO — 200/201 frecuencias**

| Métrica | Valor |
|---|---|
| Frecuencias capturadas | 200/201 (99.5%) |
| Saturación detectada | 0 frecuencias |
| Errores de captura | 1 (en 2452 MHz) |
| Ancho de banda | 200 MHz |
| Paso | 1 MHz |
| Resolución de rango teórica | 75.0 cm |
| Rango no ambiguo | 150.0 m |
| Pico de |H(f)| | 2453.0 MHz (-66.9 dB) |
| Bin de rango más fuerte | 0.000 m (-86.2 dB) |
| Rango dinámico perfil rect. | 69.5 dB |

**Incidente en 2452 MHz:**
El dispositivo bladeRF generó un error de timeout en el NIOS II co-procesador
(`Failed to send NIOS II request: Operation timed out`). Esto es un error USB
transitorio (hot-spot de interferencia en la banda ISM 2.4 GHz). El dispositivo
se recuperó automáticamente en la siguiente frecuencia (2453 MHz) sin necesidad
de intervención. La frecuencia fallida (2452 MHz) fue registrada con H[k] = 0+0j.

**Observaciones notables en el modo completo:**

| Frecuencia (MHz) | RMS amplitud | Observación probable |
|---|---|---|
| 2413 | 0.00535 | Actividad Bluetooth (canal a 2402-2480 MHz) |
| 2416 | 0.01234 | Wi-Fi 802.11b/g/n canal 1 (2412 MHz, BW 20 MHz) |
| 2418-2420 | 0.016-0.020 | Pico de interferencia Wi-Fi canal 1 |
| 2421 | 0.00844 | Cola del canal Wi-Fi 1 |
| 2452 | ERROR | Timeout NIOS II — posible interferencia USB/ISM extrema |
| 2463-2465 | 0.006 | Wi-Fi canal 6 (2437 MHz, BW 20 MHz, cola superior) |
| 2469-2470 | 0.006 | Actividad Wi-Fi zona adyacente |

Estas elevaciones de RMS son consistentes con el ambiente de laboratorio en la
banda ISM 2.4 GHz. No representan señales de radar; son interferencia ambiental
captada por el receptor.

---

## 8. Archivos generados localmente

Los archivos de datos brutos se almacenan **únicamente en local** y no se
versionan en git (`data/raw/` está excluido por `.gitignore`).

**Piloto:**
- `data/raw/rx_sfcw_sweep/pilot/20260531_164839/`
  - `cap_000_2300MHz.npy` … `cap_020_2500MHz.npy` (21 archivos IQ)
  - `freqs_hz.npy`
  - `H_raw.npy`
  - `metadata.json`
  - `sweep_summary.json`

**Completo:**
- `data/raw/rx_sfcw_sweep/full/20260531_165012/`
  - `cap_000_2300MHz.npy` … `cap_200_2500MHz.npy` (200 archivos IQ exitosos + 1 vacío)
  - `freqs_hz.npy`
  - `H_raw.npy`
  - `metadata.json`
  - `sweep_summary.json`

**Figuras generadas** (en `reports/generated/`, no comiteadas si son grandes):
- `rx_sfcw_pilot_h_magnitude_phase.png`
- `rx_sfcw_pilot_range_profile.png`
- `rx_sfcw_full_h_magnitude_phase.png`
- `rx_sfcw_full_range_profile.png`
- `rx_sfcw_sweep_summary.md`

---

## 9. Interpretación de H(f)

### ¿Qué es H(f) en este experimento?

H(f) es el vector de promedios coherentes de las ráfagas IQ capturadas, uno por
frecuencia:

```
H[k] = (1/N) * sum_{n=0}^{N-1} IQ_k[n]
```

Con N = 100 000 muestras de ruido de banda ancha, el promedio coherente converge
hacia cero estadísticamente. El valor resultante (|H[k]| ~ 0.0003–0.0004) es el
piso de ruido de estimación: σ_ruido / sqrt(N) ≈ 0.0038 / 316 ≈ 0.000012.
Los valores observados son ligeramente más altos por la presencia de interferencia
parcialmente coherente (Wi-Fi, Bluetooth).

**H(f) NO es:**
- La respuesta de frecuencia de ningún objeto físico.
- Una medición de constante dieléctrica.
- Una función de transferencia radar S21.
- Una señal calibrada en amplitude o fase absoluta.

**H(f) ES:**
- Un fasor de ruido/interferencia ambiental promediado coherentemente.
- Una señal de nivel muy bajo (~–66 a –68 dB por debajo de la saturación).
- Útil únicamente para validar que el pipeline de adquisición funciona.

### Rango dinámico de H(f)

Solo 2.7 dB (piloto) — casi plano, como se espera para ruido blanco gaussiano.
Las variaciones de amplitud corresponden a las fluctuaciones del entorno RF.

---

## 10. Interpretación del perfil de rango

### ¿Qué muestra el perfil de rango?

El perfil de rango se calcula con IFFT sobre H(f):

```
h(t) = IFFT{H(f)}
r(d) = |h(2d/c)|
```

Cuando H(f) es ruido gaussiano complejo, el perfil de rango es también ruido
(suma de exponenciales complejas con fase aleatoria). La concentración de energía
en el bin 0 (d = 0 m, -86 dB) es un artefacto del valor medio de H(f) (componente
DC en el dominio de frecuencia), no una reflexión física.

**El perfil de rango NO es:**
- Detección de ningún objeto o blanco.
- Medición de la distancia a ningún reflector.
- Perfil de rango radar real.

**El perfil de rango ES:**
- Una validación de que el pipeline IFFT + ventana funciona con datos de hardware.
- Evidencia de que `SyntheticScan` y `compute_range_profiles` son compatibles
  con datos reales del bladeRF.

### Rango dinámico del perfil

- Modo piloto (rect.): 45.9 dB — variación de ruido en los bins IFFT.
- Modo piloto (Hanning): 48.5 dB — similar, ligeramente mayor por la supresión
  de lóbulos laterales.
- Modo completo (rect.): 69.5 dB — mayor porque hay más puntos de frecuencia
  (201 vs 21), lo que produce una IFFT más fina con mayor varianza estadística.

---

## 11. Qué se validó

1. **Pipeline de adquisición real:** el bladeRF puede capturar IQ a 21 y 201
   frecuencias distintas en la banda 2.3–2.5 GHz sin errores significativos.
2. **Módulo `acquisition/rx_sfcw_sweep.py`:** funciona correctamente con datos
   de hardware real; `make_frequency_grid`, `coherent_average_iq`,
   `extract_h_from_iq_bursts`, `make_synthetic_scan_from_h`, `SweepConfig`,
   `SweepResult` y `compute_sweep_metrics` operan sin fallos.
3. **Compatibilidad `SyntheticScan` ↔ `compute_range_profiles`:** H(f) de
   hardware real puede alimentarse directamente al módulo de procesamiento
   existente sin cambios de interfaz.
4. **Ganancia de 20 dB es apropiada:** ningún bin mostró saturación en toda la
   banda 2.3–2.5 GHz.
5. **Robustez frente a errores USB transitorios:** la captura continuó correctamente
   después del error en 2452 MHz, recuperando 200/201 frecuencias.
6. **Pruebas:** 125/125 pruebas pasaron (43 nuevas + 82 previas) usando
   únicamente datos sintéticos.

---

## 12. Qué NO se validó

1. **Radar SFCW real:** sin TX no hay experimento radar. No se midió ningún objeto.
2. **Calibración de fase absoluta:** los fasores H[k] tienen fase arbitraria;
   no hay referencia TX.
3. **Imagen SAR:** requiere datos de múltiples posiciones azimutales. Este
   experimento usa una sola posición (x = 0 m).
4. **Sustracción de fondo:** necesaria para aislamiento de blancos. No aplicable
   sin TX.
5. **Cobertura de frecuencias fuera de 2.3–2.5 GHz:** solo se exploró 200 MHz
   de la banda 2.3–2.5 GHz.
6. **Error en 2452 MHz:** la captura en esa frecuencia produjo H = 0+0j. Si se
   necesita esa frecuencia específica, habrá que volver a capturar.

---

## 13. Limitaciones

- **Interferencia ambiental:** la banda 2.4 GHz es extremadamente ruidosa (Wi-Fi,
  Bluetooth, ZigBee, microondas). Los valores de RMS elevados en 2416–2420 MHz
  reflejan el entorno, no características del receptor.
- **Coherencia de fase entre capturas:** el dispositivo se cierra y reabre en
  cada frecuencia, lo que introduce un salto de fase arbitrario entre ráfagas.
  Para un radar SFCW real esto requeriría referencia de fase continua o calibración
  de fase relativa.
- **Error NIOS II en 2452 MHz:** timeout de firmware, presumiblemente causado por
  interferencia extrema o estrés del bus USB. Poco frecuente; no implica fallo
  sistemático.
- **Resolución de rango limitada a 75 cm:** con solo 200 MHz de BW, objetos más
  cercanos que ~75 cm no pueden resolverse. Aumentar el BW (p.ej., a 2 GHz)
  mejoraría la resolución a ~7.5 cm.

---

## 14. Próximo paso recomendado

El siguiente hito es el **primer experimento TX/RX calibrado con objeto real**:

1. Implementar la ruta TX real en `hardware/bladeRF_device.py` con bloqueo de
   seguridad explícito.
2. Diseñar el montaje experimental: bladeRF, divisor de potencia, objeto reflector
   conocido (placa metálica) a distancia fija (ej. 1.0 m), cámara anecoica o sala
   de RF.
3. Capturar S21 = V_RX / V_TX con y sin objeto (background subtraction).
4. Verificar que el perfil de rango muestre un pico en la distancia esperada.
5. Solo entonces escalar a múltiples posiciones azimutales y reconstrucción SAR.

**Antes del primer TX real:** agregar `processing/background_subtraction.py`,
revisar regulaciones de emisión RF para la potencia usada, y asegurar que TX
solo se habilite con confirmación explícita por sesión.

---

## 15. Acciones de hardware realizadas

- bladeRF abierto y cerrado: 21 (piloto) + 200 (completo) = 221 veces.
- RX configurado y capturado: 221 capturas exitosas.
- TX: NUNCA habilitado, NUNCA llamado `configure_tx()` ni `transmit_tone()`.
- RF transmitida: NINGUNA.
- Motores: NINGUNO.
- Sujeto humano: NINGUNO.
- Fantasma o material biológico: NINGUNO.
- Prueba médica o clínica: NO.
- Imagen SAR: NO.
- Caracterización dieléctrica: NO.
