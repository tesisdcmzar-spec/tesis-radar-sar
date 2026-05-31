# Informe de sesion — Survey RX supervisado por frecuencia con bladeRF

**Fecha:** 2026-05-31  
**Tipo:** Hardware supervisado — RX-only, diagnostico de receptor  
**Autor:** Claude Code (claude-sonnet-4-6)  
**Estado:** EXITOSO (7/7 frecuencias capturadas)

---

## 1. Objetivo

Caracterizar el comportamiento del receptor bladeRF y el entorno RF local
a traves de un barrido de 7 frecuencias centrales (900 MHz a 5 GHz).  La
prueba es un diagnostico de receptor: no se transmite RF, no se opera radar,
no se detectan objetos, no se realizan imagenes SAR.

---

## 2. Lista de verificacion de seguridad

| # | Condicion | Estado |
|---|-----------|--------|
| 1 | Usuario fisicamente presente | OK |
| 2 | bladeRF conectado por USB | OK |
| 3 | RX1 con antena o carga de 50 ohm | OK |
| 4 | TX1 no utilizado | OK |
| 5 | Sin sujeto humano bajo prueba | OK |
| 6 | Sin motor ni etapa de movimiento | OK |
| 7 | Sesion RX-only | OK |
| 8 | Frase de confirmacion exacta: `CONFIRM HARDWARE RUN` | OK |

---

## 3. Lista de frecuencias del survey

| # | Frecuencia central | Banda de referencia |
|---|--------------------|---------------------|
| 1 | 900 MHz | GSM / LTE 850/900 |
| 2 | 1200 MHz | L-band (navegacion, GPS L2) |
| 3 | 1800 MHz | LTE 1800 / DCS |
| 4 | 2400 MHz | WiFi 2.4 GHz / Bluetooth |
| 5 | 3000 MHz | S-band (radar meteorologico) |
| 6 | 4000 MHz | S-band / C-band limite |
| 7 | 5000 MHz | WiFi 5 GHz / C-band |

---

## 4. Configuracion RX exacta (igual para todas las frecuencias)

| Parametro | Valor |
|-----------|-------|
| `sample_rate_hz` | 10 000 000 S/s (10 MS/s) |
| `bandwidth_hz` | 10 000 000 Hz (10 MHz) |
| `rx_gain_db` | 20.0 dB |
| `tx_gain_db` | -20.0 dB (limite conservador, no utilizado) |
| `n_samples` | 100 000 (~10 ms por burst) |
| `dry_run` | False |
| Confirmacion | `CONFIRM HARDWARE RUN` |

Cada frecuencia abre y cierra el dispositivo independientemente.

---

## 5. Archivos generados

### Script de captura (versionado)
- [`experiments/run_bladerf_rx_frequency_survey.py`](../../experiments/run_bladerf_rx_frequency_survey.py)

### Datos locales (no versionados)
- `data/raw/rx_frequency_survey/20260531_162522/rx_900MHz.npy`
- `data/raw/rx_frequency_survey/20260531_162522/rx_1200MHz.npy`
- `data/raw/rx_frequency_survey/20260531_162522/rx_1800MHz.npy`
- `data/raw/rx_frequency_survey/20260531_162522/rx_2400MHz.npy`
- `data/raw/rx_frequency_survey/20260531_162522/rx_3000MHz.npy`
- `data/raw/rx_frequency_survey/20260531_162522/rx_4000MHz.npy`
- `data/raw/rx_frequency_survey/20260531_162522/rx_5000MHz.npy`
- `data/raw/rx_frequency_survey/20260531_162522/metadata.json`

### Figuras locales (no versionadas)
- `reports/generated/bladerf_rx_frequency_survey_noise_floor.png`
- `reports/generated/bladerf_rx_frequency_survey_dc_offset.png`
- `reports/generated/bladerf_rx_frequency_survey_peak_bins.png`
- `reports/generated/bladerf_rx_frequency_survey_summary.md`

---

## 6. Estadisticas IQ por frecuencia

| Freq (MHz) | Estado | Mean amp | RMS | Max amp | Clip% | DC mag | Peak offset (kHz) | Peak (dB) | Clasificacion |
|------------|--------|----------|-----|---------|-------|--------|-------------------|-----------|---------------|
| 900 | OK | 0.00372 | 0.00423 | 0.01478 | 0.000 | 0.00035 | +0.00 | -69.2 | noise-like |
| 1200 | OK | 0.00552 | 0.00678 | 0.03145 | 0.000 | 0.00036 | +0.00 | -68.9 | noise-like |
| 1800 | OK | 0.00337 | 0.00385 | 0.01416 | 0.000 | 0.00039 | +0.00 | -68.2 | noise-like |
| 2400 | OK | 0.00331 | 0.00379 | 0.01516 | 0.000 | 0.00038 | +0.00 | -68.5 | noise-like |
| 3000 | OK | 0.00332 | 0.00381 | 0.01293 | 0.000 | 0.00037 | +0.00 | -68.7 | noise-like |
| 4000 | OK | 0.00322 | 0.00370 | 0.01368 | 0.000 | 0.00003 | -4667.60 | -80.4 | noise-like |
| 5000 | OK | 0.00383 | 0.00432 | 0.01516 | 0.000 | 0.00081 | +0.00 | -61.8 | noise-like |

---

## 7. Interpretacion tecnica

### 7.1 Piso de ruido

El RMS normalizado oscila entre 0.0037 y 0.0068 en todas las frecuencias.
Esto representa ~0.4 % de la escala maxima del ADC (2048 counts en SC16_Q11).
El nivel es consistente con el piso de ruido termico esperado a 20 dB de ganancia
sin senal activa de TX.

La frecuencia de 1200 MHz muestra el RMS mas alto (0.00678) y el maximo mas alto
(0.03145 — todavia muy por debajo de 1.0).  Esto puede indicar presencia de
portadoras LTE o navegacion (GPS L2, Galileo E6) en esa ventana de 10 MHz, o
simplemente mayor sensibilidad del receptor en esa banda.

### 7.2 Offset DC

El offset DC es menor que 0.001 en todas las frecuencias, lo que es normal para
un receptor de conversion directa.  En 4 GHz el offset DC es casi cero (0.00003),
lo que sugiere que la calibracion interna del bladeRF es especialmente efectiva
en esa banda.

### 7.3 Bins espectrales dominantes

En 6 de las 7 frecuencias el bin mas fuerte es DC (offset = 0), con magnitudes
entre -68 y -70 dB, consistente con el DC residual del receptor y el piso de ruido.

La excepcion es 4000 MHz, donde el bin mas fuerte esta a -4667.6 kHz del centro
(cerca del borde de la banda de 10 MHz).  Esto puede ser un artefacto del canal
de decimacion del FPGA del bladeRF a esa frecuencia, o una portadora fuera de
banda que cae parcialmente dentro de la ventana.  El nivel es -80.4 dB, el mas
bajo de todo el survey.

En 5000 MHz el peak es -61.8 dB, el mas alto del survey.  La banda de 5 GHz
tiene alta actividad WiFi (IEEE 802.11a/n/ac/ax) que puede elevar el piso de
ruido efectivo.

### 7.4 Recorte (clipping)

Recorte: 0.000% en todas las frecuencias.  La ganancia de 20 dB es conservadora
y apropiada para diagnostico.  No es necesario reducirla.

### 7.5 Clasificacion de capturas

Todas las capturas se clasificaron como `noise-like`: amplitud baja, sin picos
de interferencia definidos por encima de -60 dB, sin clipping, DC pequeno.
El receptor funciona correctamente en todo el rango surveado.

---

## 8. Que fue validado

- El bladeRF abre y cierra limpiamente en 7 frecuencias distintas.
- La secuencia `BladeRFConfig -> BladeRFDevice -> configure_rx() -> capture_rx() -> close()`
  funciona de forma reproducible a traves del rango 900 MHz – 5 GHz.
- La abstraccion `hardware/bladerf_device.py` es estable para multiples configuraciones
  sin reiniciar el proceso.
- El piso de ruido RX es coherente entre frecuencias (~-68 dB), indicando funcionamiento
  normal del receptor.
- No se detectaron problemas de clipping, saturacion ni errores de USB.
- Los datos IQ se guardan correctamente como `complex128` en formato `.npy`.

---

## 9. Que NO fue validado

- Calibracion RF (reflexion de antena, balance IQ, background).
- Barrido SFCW sincronizado con TX.
- Senal coherente de eco de objeto.
- Imagen SAR 2D o 3D.
- Caracterizacion dielectrica de fantomas o materiales.
- Funcionamiento de la etapa de transmision.
- Deteccion de objetos o blancos.
- Movimiento de etapa acimutal.
- Estabilidad de largo plazo (multiples sesiones).

---

## 10. Limitaciones

- El survey captura RF ambiental, no una senal de radar controlada.
- La resolucion espectral es 100 Hz/bin (fs/N = 10 MHz / 100 000) lo cual no
  permite identificar portadoras estrechas (< 1 kHz).
- Un solo burst de 10 ms por frecuencia no captura fading temporal ni bursts
  intermitentes de WiFi/LTE.
- La ganancia fija de 20 dB puede ser suboptima para algunas bandas (especialmente
  5 GHz con alta actividad WiFi).

---

## 11. Proximo paso recomendado

**Implementar barrido SFCW supervisado (RX-only aun):**

1. Definir un rango SFCW: por ejemplo 2.3–2.5 GHz en pasos de 1 MHz
   (200 frecuencias, 200 bursts IQ de 10 ms cada uno).
2. Capturar H(f) en una posicion acimutal fija.
3. Calcular el perfil de rango con IFFT (usando el codigo ya implementado
   en `processing/range_profile.py`).
4. Validar que el perfil de rango coincide con la geometria esperada del lab.

**No hacer todavia:** TX activo, movimiento de etapa acimutal, experimento con
fantoma.

---

*Informe generado por Claude Code como parte del flujo de trabajo de tesis SAR.*  
*RX-only. Sin TX. Sin transmision RF. Sin motor. Sin sujeto humano.*  
*No es prueba medica. No es imagen SAR. No es caracterizacion dielectrica.*
