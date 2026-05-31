# Informe de sesion — Primer smoke test RX real con bladeRF

**Fecha:** 2026-05-31  
**Tipo:** Hardware supervisado — RX-only  
**Autor:** Claude Code (claude-sonnet-4-6)  
**Estado:** EXITOSO

---

## 1. Objetivo

Ejecutar el primer smoke test supervisado de captura RX real con el bladeRF,
validando que la ruta de adquisicion IQ implementada en `hardware/bladerf_device.py`
funciona sobre el hardware fisico.  Esta prueba es exclusivamente de recepcion
(RX); no se transmite RF, no se mueven motores, no se usa sujeto humano y no se
realiza imagen SAR.

---

## 2. Lista de verificacion de seguridad (pre-vuelo)

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

## 3. Hardware utilizado

- **SDR:** bladeRF 2.0 micro (conectado via USB)
- **RX:** RX1 con antena o carga 50 ohm
- **TX:** no conectado, no habilitado, no configurado
- **Etapa acimutal:** no utilizada
- **Fantoma:** no utilizado

---

## 4. Configuracion RX exacta

| Parametro | Valor |
|-----------|-------|
| `center_freq_hz` | 2 400 000 000 Hz (2.4 GHz — banda WiFi) |
| `sample_rate_hz` | 10 000 000 S/s (10 MS/s) |
| `bandwidth_hz` | 10 000 000 Hz (10 MHz) |
| `rx_gain_db` | 20.0 dB |
| `tx_gain_db` | -20.0 dB (limite conservador, no utilizado) |
| `n_samples` | 100 000 (duracion ~10 ms) |
| `dry_run` | False |
| Frase de confirmacion | `CONFIRM HARDWARE RUN` |

---

## 5. Archivos creados en esta sesion

### Codigo
- [`experiments/run_bladerf_rx_smoke_test.py`](../../experiments/run_bladerf_rx_smoke_test.py) — script de smoke test supervisado

### Hardware abstraction (modificados)
- [`hardware/bladerf_device.py`](../../hardware/bladerf_device.py):
  - `_capture_rx_real`: correccion de ruta de enumeraciones `ChannelLayout`/`Format` (acceso via `mod._bladerf`)
  - `configure_rx` (modo real): anadido `enable_module(CHANNEL_RX(0), True)` requerido para streaming
  - `close` (modo real): anadido `enable_module(CHANNEL_RX(0), False)` antes de cerrar
- [`tests/test_bladerf_device.py`](../../tests/test_bladerf_device.py):
  - `_FakeBladeRFDevice`: anadido metodo `enable_module(ch_id, enable)`
  - `_FakeBladeRFModule`: anadido atributo `_bladerf` con submodulo fake que expone `ChannelLayout` y `Format`

### Datos locales (no versionados)
- `data/raw/rx_smoke/20260531_161436/rx_iq.npy` — 100 000 muestras IQ (complex128)
- `data/raw/rx_smoke/20260531_161436/metadata.json` — metadatos de la captura

### Figuras locales (no versionadas)
- `reports/generated/bladerf_rx_smoke_time_domain.png` — dominio temporal I/Q
- `reports/generated/bladerf_rx_smoke_spectrum.png` — espectro FFT
- `reports/generated/bladerf_rx_smoke_summary.md` — resumen de diagnostico

---

## 6. Comando ejecutado

```powershell
py experiments/run_bladerf_rx_smoke_test.py
```

---

## 7. Resultado: apertura del dispositivo bladeRF

El dispositivo se abrio exitosamente con `bladerf.BladeRF()` en modo real
(`dry_run=False`, confirmacion provista).  La advertencia
`[WARNING] Setting gain mode to manual` es normal: libbladeRF cambia
automaticamente al modo de ganancia manual al asignar un valor de ganancia
explicito.

---

## 8. Resultado: captura IQ

La captura fue exitosa.  `sync_rx()` lleno el buffer de `100 000 * 4 = 400 000`
bytes sin errores de timeout.

**Nota tecnica:** la primera ejecucion fallo con `TimeoutError` en `sync_rx`
porque `configure_rx` no llamaba a `enable_module` antes del streaming.  La
correccion consistio en agregar `device.enable_module(CHANNEL_RX(0), True)` al
final de `configure_rx` (modo real).  Este es el patron correcto de la API
libbladeRF para habilitar el modulo RX antes de `sync_config`/`sync_rx`.

---

## 9. Estadisticas IQ

| Metrica | Valor |
|---------|-------|
| Shape | (100 000,) |
| dtype | complex128 |
| Amplitud media | 0.00336 |
| Amplitud maxima | 0.01424 |
| Amplitud RMS | 0.00386 |
| Razon de recorte | 0.000000 (sin clipping) |
| Offset DC (I, Q) | (0.00037, 0.00012) |
| Magnitud DC | 0.00039 |

---

## 10. Interpretacion del espectro

| Metrica | Valor |
|---------|-------|
| Bin mas fuerte | +0.000 MHz desde el centro (componente DC residual) |
| Magnitud del pico | -68.3 dB |

- La amplitud media es muy baja (~0.003 de la escala maxima), lo que indica que
  la senal capturada es principalmente ruido termico ambiental mas posibles
  trazas de WiFi u otras transmisiones en 2.4 GHz.
- No hay clipping (razon de recorte = 0): la ganancia de 20 dB es apropiada.
- El offset DC (0.00039) es tipico en receptores de conversion directa.  No
  interfiere con el procesamiento SAR porque la calibracion posterior
  (background subtraction) lo elimina.
- El pico espectral en 0 MHz (DC) es la componente de offset DC; no indica
  presencia de objeto o blanco.
- No se observa ninguna senal coherente que permita inferir objetos, distancias
  ni imagenes.  La senal capturada es ruido ambiental de RF.

---

## 11. Que fue validado

- La abstraccion hardware `BladeRFDevice` funciona sobre el dispositivo real.
- La secuencia `configure_rx() -> capture_rx() -> close()` ejecuta sin errores.
- `enable_module` es requerido antes de `sync_rx` (hallazgo de esta sesion).
- La conversion SC16_Q11 a complex128 funciona correctamente sobre datos reales.
- La ruta de guardado de datos (`data/raw/rx_smoke/`) funciona.
- Las figuras de diagnostico se generan sin errores.
- La frase de confirmacion `CONFIRM HARDWARE RUN` actua como compuerta.
- El modo real (`dry_run=False`) abre el dispositivo USB fisico.

---

## 12. Que NO fue validado

- Calibracion RF (reflexion, background, canal).
- Barrido SFCW multi-frecuencia.
- Senal coherente de TX y recepcion de eco.
- Imagen SAR 2D.
- Caracterizacion dielectrica de fantomas.
- Movimiento de etapa acimutal.
- Funcionamiento de la etapa de transmision.
- Deteccion de objetos.
- Prueba sobre sujeto humano (no permitida en este proyecto).

---

## 13. Limitaciones

- El script captura a 2.4 GHz, una frecuencia con alto nivel de interferencia
  WiFi.  Las capturas futuras para radar SAR usaran frecuencias de operacion
  apropiadas (a definir en el diseno del sistema).
- Solo se captura un burst de 10 ms.  No se verifica estabilidad de larga
  duracion ni multiples capturas.
- No se comprueba sincronizacion con TX (no implementado aun).

---

## 14. Errores encontrados y resueltos

### Error 1: `UnicodeEncodeError` en consola Windows
- **Causa:** caracteres Unicode de cuadro (U+2554, etc.) no soportados por `cp1252`.
- **Solucion:** reemplazados por caracteres ASCII (`+`, `-`, `|`).

### Error 2: `TimeoutError` en `sync_rx`
- **Causa:** faltaba llamada a `enable_module(CHANNEL_RX(0), True)` en `configure_rx`.
- **Solucion:** agregado `self._device.enable_module(rx_ch, True)` al final del bloque real de `configure_rx`.

### Error 3: `AttributeError: '_FakeBladeRFDevice' has no attribute 'enable_module'`
- **Causa:** el mock de tests no tenia el metodo `enable_module`.
- **Solucion:** agregado metodo `enable_module(ch_id, enable)` a `_FakeBladeRFDevice`.

### Error 4: `AttributeError: '_FakeBladeRFModule' has no attribute '_bladerf'`
- **Causa:** `_capture_rx_real` accede a `mod._bladerf.ChannelLayout` y `mod._bladerf.Format`, pero el mock no tenia el submodulo `_bladerf`.
- **Solucion:** agregada clase `_FakeBladeRFSubmodule` con `ChannelLayout` y `Format`, y asignada como `self._bladerf` en `_FakeBladeRFModule`.

---

## 15. Tests

| Suite | Antes | Despues |
|-------|-------|---------|
| tests/test_simulation.py | 12 | 12 |
| tests/test_load_sfcw_capture.py | 19 | 19 |
| tests/test_bladerf_device.py | 51 | 51 |
| **Total** | **82** | **82** |

**Sin regresiones.** Todos los tests pasaron en 2.50 s.

---

## 16. Proximo paso recomendado

El siguiente paso seguro es implementar la captura multi-frecuencia SFCW
en modo supervisado: barrer entre `f_start` y `f_stop` en pasos `delta_f`,
capturar un burst IQ por frecuencia, y combinar en la matriz `H(f, x_az)`.

**No hacer todavia:** TX, movimiento de etapa acimutal, experimento con fantoma.

---

*Informe generado por Claude Code como parte del flujo de trabajo de tesis SAR.*  
*RX-only. Sin TX. Sin transmision RF. Sin motor. Sin sujeto humano.*  
*No es prueba medica. No es imagen SAR. No es caracterizacion dielectrica.*
