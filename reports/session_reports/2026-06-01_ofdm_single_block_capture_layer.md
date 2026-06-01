# Sesion: Capa de Captura OFDM de Bloque Unico

**Fecha:** 2026-06-01
**Rama:** main
**Commit de partida:** f365e39 (Reorient project to UWB-OFDM-SAR architecture)

---

## Objetivo

Implementar la siguiente capa de ingenieria real despues del pivote de arquitectura UWB-OFDM-SAR.
El objetivo inmediato es obtener H[k] de un unico bloque OFDM, ya sea en modo sintetico (prepare-only),
con backend falso (dry-run), o con hardware real (run-hardware).

No se realiza SAR. No se escanea en azimut. No se usa ningun objetivo fisico, maniqui,
ni sujeto humano. Solo se valida la infraestructura de estimacion de canal OFDM.

---

## Archivos Creados

| Archivo | Descripcion |
|---|---|
| `acquisition/ofdm_block_capture.py` | Abstraccion de captura OFDM de bloque unico. Hardware-independiente. |
| `processing/ofdm_block_stitcher.py` | Scaffold de stitching de bloques OFDM. Hardware-independiente. |
| `experiments/run_ofdm_single_block_capture.py` | Experimento: prepare-only, dry-run, run-hardware. |
| `configs/ofdm_single_block_2p4ghz.yaml` | Config conservadora: 2.4 GHz, 2 MS/s, n_fft=256. |
| `tests/test_ofdm_block_capture.py` | 28 tests con datos sinteticos y backend falso. |
| `tests/test_ofdm_block_stitcher.py` | 26 tests con datos sinteticos. Sin hardware. |
| `docs/ofdm_single_block_capture_plan.md` | Documentacion del plan y limitaciones. |

## Archivos Modificados

| Archivo | Cambio |
|---|---|
| `hardware/bladerf_device.py` | Agrega `transmit_iq_burst()` para IQ arbitrario (OFDM). |
| `hardware/safety.py` | Agrega constante `MAX_OFDM_IQ_BURST_DURATION_S = 0.01` (10 ms). |

---

## Configuracion OFDM (2.4 GHz, conservadora)

```
center_freq_hz : 2.4e9   (2.4 GHz)
sample_rate_hz : 2e6     (2 MS/s)
bandwidth_hz   : 2e6     (2 MHz)
n_fft          : 256
n_active       : 160
cp_len         : 64
guard_bins     : 20
pilot_type     : bpsk
pilot_seed     : 42
repetitions    : 8
tx_gain_db     : -20.0   (limite conservador)
rx_gain_db     : 20.0
```

Subcarriers activos reales: 120 (despues de guard y DC null).
Ancho de banda activo: ~937.5 kHz.
Duracion del frame OFDM: 8 * (64 + 256) / 2e6 = 1.28 ms (< limite de seguridad de 10 ms).

---

## Tests

- **Tests corridos:** 347
- **Tests pasados:** 347
- **Tests fallados:** 0
- Sin importacion de bladeRF en ningun test.
- Los tests de `test_ofdm_block_capture.py` incluyen:
  - Validacion de config (rechazo de flags prohibidos, tipos invalidos).
  - Generacion de frame OFDM (forma, magnitud de pilotos BPSK/QPSK, reproducibilidad).
  - Estimacion de H[k] con canal identidad (H ~= 1 en bins activos).
  - Estimacion de H[k] con canal de delay (recuperacion de CIR).
  - Captura con fake device (dry_run=True y dry_run=False con confirmacion).
  - Verificacion de que bladeRF NO es importado en modo dry-run.
  - Summary ASCII (sin caracteres Unicode).
- Los tests de `test_ofdm_block_stitcher.py` incluyen:
  - Validacion de bloques (lista vacia, longitudes inconsistentes, frecuencias no monotonास).
  - Descarte de subcarriers invalidos.
  - Normalizacion de magnitud.
  - Estimacion de phase offset en zona de solapamiento.
  - Aplicacion de phase offset.
  - Stitching: dos bloques sin solapamiento, ordenados por frecuencia.
  - Stitching: eliminacion de frecuencias duplicadas.
  - Stitching: correccion de phase offset conocido.
  - Summary ASCII.

---

## Soporte de TX IQ Arbitrario en bladeRF

**Estado:** `transmit_iq_burst()` implementado en `hardware/bladerf_device.py`.

- En modo dry-run: registra la llamada, NO transmite RF.
- En modo real: escala IQ a SC16_Q11 (~25% de escala completa), llama `sync_tx()`,
  deshabilita TX en bloque `finally`.
- Duracion maxima: `MAX_OFDM_IQ_BURST_DURATION_S = 10 ms`.
- Ganancia TX: capped en -20 dB (limite conservador existente).
- Requiere: `confirmation='CONFIRM HARDWARE RUN'` y `reflector_setup_ready='REFLECTOR SETUP READY'`.

El bladeRF 2.0 micro soporta TX de formas de onda arbitrarias via la interfaz `sync_tx`.
`transmit_iq_burst()` usa esta interfaz correctamente.

---

## Resultado de prepare-only

```
Mode: prepare-only. No hardware. No RF. No clinical claims.
center_freq   : 2.40 GHz
sample_rate   : 2.0 MS/s
n_fft         : 256
n_active      : 160 (120 activos tras guard y DC null)
TX frame      : 2560 samples
H active bins : 120
|H| mean      : 1.0673
|H| max       : 1.7730
CIR peak idx  : 30
est delay     : 15000.0 ns  (camino sintetico de 30 muestras a 2 MS/s)
est range     : 225000.0 cm (camino sintetico, NO es una medicion real)
active BW     : 937.5 kHz
```

Nota: el delay y rango son sinteticos. El camino sintetico usa delay=30 muestras a 2 MS/s,
lo que equivale a 15 us = 15000 ns. Esto no representa una distancia fisica real.
En hardware real con antenas, el delay tipico a ~1 m seria ~6.7 ns, bien por debajo
de la resolucion de 1 muestra a 2 MS/s (500 ns). Para medir delays de ~1 m se requiere
mayor sample rate o mayor bandwidth efectivo.

---

## Resultado de dry-run

```
Mode: dry-run. Fake device backend. No hardware. No RF.
dry_run       : True
H shape       : (256,)
active bins   : 120
|H| mean      : 1.0130
CIR peak idx  : 0
est delay     : 0.0 ns
```

H[k] ~= 1 en todos los bins activos (canal identidad con ruido minimo). OK.

---

## Hardware

**Hardware corrido en esta sesion:** NO.
- No hay bladeRF conectado durante esta sesion de IA.
- El modo `--run-hardware` fue implementado pero no ejecutado.
- `transmit_iq_burst()` fue implementado y probado con backend falso.
- No se transmitio RF real.

---

## Lo que queda sin validar

1. **Hardware real:** `--run-hardware` no fue ejecutado. Requiere bladeRF conectado y supervision.
2. **Calibracion de H[k]:** ninguna calibracion contra reflector conocido.
3. **Stitching multi-bloque:** el scaffold existe pero no fue ejercido con hardware.
4. **Phase discontinuity:** el salto de fase entre retuneos del LO es un problema abierto serio.
5. **SAR:** no se realizo ningun escaneo de azimut.
6. **Phantom:** ningun experimento con objetivos fisicos.
7. **Estimacion de constante dielectrica:** no posible en esta etapa.

---

## Reclamaciones

- Esta sesion valida la infraestructura de estimacion de H[k] para un bloque OFDM.
- No se detecta ningun objeto real.
- No se realizan afirmaciones diagnosticas clinicas.
- No se caracteriza ninguna propiedad dielectrica.
- El sistema es un prototipo experimental de laboratorio controlado.
- No tiene aprobacion regulatoria.
- No es apto para uso clinico.

---

## Siguiente Paso Recomendado

1. Conectar el bladeRF con antenas y un reflector metalico conocido a ~1 m.
2. Ejecutar con supervision:
   ```
   py experiments/run_ofdm_single_block_capture.py --run-hardware
   ```
3. Inspeccionar H[k] y CIR del hardware real.
4. Calibrar usando distancia conocida del reflector.
5. Si la calibracion es exitosa, extender a multiples bloques de frecuencia.
6. Implementar stitching multi-bloque con referencia de calibracion.
7. Agregar escaneo de azimut y backprojection SAR.
