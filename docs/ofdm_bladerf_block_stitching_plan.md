# Plan de stitching de bloques OFDM para bladeRF

> Documento canonico de estrategia de adquisicion multi-bloque.
> Referencia para Claude Code y para la tesis.
> Ultima actualizacion: 2026-05-31

---

## 1. El problema central: BW nominal no es BW util

El bladeRF 2.0 micro tiene un rango de sintonizacion de RF de 47 MHz a 6 GHz. Esto lleva a confundir dos conceptos:

| Concepto | Definicion | Valor tipico bladeRF |
|---------|-----------|---------------------|
| Rango de sintonizacion RF | Rango de frecuencias centrales | 47 MHz -- 6 GHz |
| Ancho de banda instantaneo | BW captureable en una sola adquisicion IQ | ~40 MHz practico |
| BW nominal | BW configurado en el driver | Hasta 61.44 MHz |
| BW efectivo OFDM | BW util despues de filtros, guards, DC, CP | Menor al nominal |

El bladeRF **no puede** capturar varios GHz en una sola adquisicion. Para sintetizar un ancho de banda UWB de 1-3 GHz, se necesita adquirir multiples bloques OFDM en diferentes frecuencias centrales y luego coserlos.

---

## 2. Arquitectura de captura por bloques

```
Adquisicion UWB = suma de N bloques OFDM

Bloque 1: f_c = 2.3 GHz, BW_bloque ~ 30 MHz
Bloque 2: f_c = 2.6 GHz, BW_bloque ~ 30 MHz
...
Bloque N: f_c = f_c,1 + (N-1)*paso, BW_bloque ~ 30 MHz

BW_total (sintetico) ~ N * BW_bloque - solapamiento
```

El stitching convierte N capturas de BW limitado en un solo H_total(f) de BW ancho.

---

## 3. Los 15 factores que reducen el BW efectivo por bloque

Ninguno de estos factores es exclusivo del bladeRF; todos son inherentes al diseno de sistemas OFDM. El bladeRF los introduce en forma mas severa que SDRs de mayor gama.

### 3.1 Sample rate maximo

El sample rate maximo del bladeRF es ~61.44 MS/s, limitado por el ADC/DAC y el bus USB. A mayor sample rate, mayor latencia, mayor probabilidad de overflow. Valor practico conservador: 40 MS/s.

```
Fs_max_practico ~ 40 MS/s
BW_Nyquist_complejo = Fs = 40 MHz
BW_util < 40 MHz (por los factores siguientes)
```

### 3.2 Filtros analogicos del front-end

El bladeRF tiene filtros de banda pasante en el front-end RF. Estos filtros tienen:
- Respuesta no plana cerca de los bordes
- Ripple de ganancia
- Distorsion de fase no lineal en los bordes

Consecuencia: no conviene usar subportadoras pegadas a los bordes del BW configurado. Los extremos del espectro tienen respuesta degradada.

### 3.3 Filtros digitales internos

La cadena de procesamiento digital (decimacion/interpolacion en FPGA) introduce filtraje adicional. La configuracion `bandwidth` del driver limita el BW de los filtros digitales. Esta configuracion debe ser <= sample_rate.

Consecuencia:
- `sample_rate` y `bandwidth` no son equivalentes.
- Un sample_rate de 40 MS/s con bandwidth de 40 MHz tiene filtros digitales mas anchos que con bandwidth de 20 MHz.
- Cada configuracion debe medirse experimentalmente.

### 3.4 Subportadoras de guarda

OFDM requiere subportadoras apagadas en los bordes del bloque para evitar:
- Leakage espectral de las subportadoras activas hacia fuera del bloque
- Interferencia con el roll-off de los filtros analogicos
- Aliasing en los bordes de la banda de Nyquist

Regla practica:
```
guard_bins >= 10% de N_fft en cada extremo
DC siempre apagada
N_activas ~ 0.8 * N_fft
```

### 3.5 Subportadora DC (bin 0)

La subportadora DC (frecuencia 0 en banda base, equivalente a la frecuencia central RF) siempre debe apagarse. Razones:
- DC offset del ADC/DAC contamina esta subportadora
- LO leakage del oscilador local inyecta potencia espuria en DC
- El filtrado digital puede tener notch o rolloff en DC

Consecuencia: H[0] = 0, hueco en el centro del espectro. Al coser bloques, este hueco debe documentarse y gestionarse.

### 3.6 Prefijo ciclico (CP)

El CP no reduce el BW del bloque, pero si reduce la eficiencia temporal y energetica. Cada muestra de CP es una muestra "de overhead" que no aporta capacidad de radar.

Regla de diseno:
```
T_CP >= 2 * R_max / c    (para radar monostatico)
```

Para R_max = 1 m: T_CP >= 6.67 ns = 0.27 muestras a 40 MS/s (redondar a 1 o mas).
Para R_max = 3 m: T_CP >= 20 ns = 0.8 muestras a 40 MS/s.

CP tipico: 32 a 64 muestras para dar margen ante imprecision de sincronizacion.

Si CP es demasiado corto:
- ISI (interferencia entre simbolos consecutivos)
- IRCI (interferencia entre celdas de rango en radar)
- H[k] queda contaminado por el simbolo anterior

Si CP es demasiado largo:
- Menor SNR por unidad de tiempo
- Mayor tiempo de captura por frame

### 3.7 PAPR de OFDM

OFDM puede tener PAPR (peak-to-average power ratio) alto porque las N subportadoras pueden sumar constructivamente en ciertos instantes de tiempo. Para evitar saturacion del DAC/PA:
- Se aplica backoff de potencia media (tipicamente 3-8 dB por debajo de la saturacion)
- Esto reduce la potencia transmitida media
- La SNR de recepcion disminuye

Alternativas: PAPR reduction (clipping, tone reservation, SLM), o uso de simbolos BPSK/QPSK que tienen menor PAPR que QAM.

### 3.8 Cuantizacion ADC

El bladeRF usa muestras SC16_Q11 (16 bits, 11 bits de fraccion). La resolucion efectiva puede ser menor si hay clipping, ruido de cuantizacion o baja ocupacion de rango dinamico. Medidas:
- Monitorear RMS y peak de las muestras recibidas
- Ajustar ganancia RX para que el RMS ocupe ~25-50% del rango dinamico
- Evitar clipping (reduce ENOB efectivo)

### 3.9 Sincronizacion temporal

Para que H[k] = Y[k]/X[k] sea valido, la FFT del receptor debe aplicarse exactamente sobre los N_fft muestras del simbolo (sin el CP). Un error de sincronizacion Dt produce:
- Rotacion de fase lineal en H[k]: H[k] -> H[k] * exp(-j*2*pi*k*Dt/N_fft)
- Esto no cambia la magnitud pero si la fase y por tanto el retardo estimado

En el sistema TX=RX con el mismo bladeRF, la sincronizacion es mas controlable que en sistemas separados, pero igual requiere correlacion con un preambulo o simbolo de referencia.

### 3.10 Offset de frecuencia (CFO) y offset de sample rate (SFO)

Aunque TX y RX comparten el mismo oscilador en el bladeRF, pueden existir:
- Offset residual de LO por deriva termica
- Saltos de fase al retunear la frecuencia central entre bloques
- Diferencia de sample rate entre TX y RX (SFO)

CFO produce rotacion de subportadoras e ICI (inter-carrier interference). SFO produce drift temporal que empeora con el tiempo.

### 3.11 ICI (inter-carrier interference)

Si las subportadoras no son perfectamente ortogonales (por CFO, SFO, Doppler o ventaneo incorrecto), hay fuga entre subportadoras adyacentes. En blancos estaticos (phantoms) el Doppler es despreciable, pero el CFO y SFO son reales.

### 3.12 Discontinuidad de fase entre bloques

Al retunear el bladeRF a una nueva frecuencia central, la fase absoluta del oscilador salta a un valor arbitrario. Por tanto, no es posible coser bloques simplemente concatenando sus H[k]:
- H_bloque_1 tiene fase relativa al oscilador en f_c,1
- H_bloque_2 tiene fase relativa al oscilador en f_c,2, posiblemente con offset arbitrario

Estrategias de correccion de fase inter-bloque:
1. **Bloque solapado:** Capturar N_overlap subportadoras de solapamiento entre bloques consecutivos y usar la diferencia de fase como referencia.
2. **Reflector de referencia:** Incluir en la escena un reflector de posicion conocida cuyo pico de rango sirva como referencia de fase.
3. **Medicion de fondo:** Medir el fondo sin el objetivo y usarlo como referencia de fase absoluta.

Sin correccion de fase, el stitching de magnitudes es posible pero la coherencia de fase se pierde, lo que degrada la resolucion en rango.

### 3.13 Stitching en frecuencia

Para coser N bloques OFDM en un H_total(f) coherente:

```
Estrategia conservadora:
  1. Adquirir bloques con solapamiento de al menos 10% del BW por bloque
  2. Calibrar ganancia relativa entre bloques (normalizacion)
  3. Estimar y corregir offset de fase entre bloques
  4. Descartar subportadoras con baja SNR o alta varianza
  5. Concatenar en orden de frecuencia ascendente
  6. Interpolar suavemente los bordes entre bloques si es necesario
```

Problema del solapamiento: en la region solapada, los dos bloques deben dar el mismo H(f). Si no coinciden, hay error de calibracion o de fase.

### 3.14 Interferencia externa

La banda 2.4 GHz contiene WiFi (802.11 b/g/n), Bluetooth, microondas domesticos y otros dispositivos ISM. Las subportadoras en esas frecuencias pueden estar contaminadas.

Estrategia:
1. Medir espectro RX-only antes del experimento (survey de frecuencias, ya realizado).
2. Identificar subportadoras contaminadas.
3. Excluirlas del stitching o bajar su peso en el procesamiento.
4. Documentar en el informe de ensayo.

### 3.15 Respuesta de antenas

Las antenas UWB no son planas. Su ganancia, patron de radiacion y fase varian con la frecuencia. Para un sistema con stitching de 1-3 GHz de BW:
- La respuesta de la antena puede variar 5-10 dB a lo largo del BW
- La fase de la antena tiene un retardo de grupo que varia con la frecuencia

Correccion: medir la respuesta de antenas en libre espacio (con reflector de referencia conocido) y aplicar el inverso como calibracion antes del stitching.

---

## 4. Diseno de bloques OFDM para el bladeRF

### 4.1 Parametros conservadores de primer paso

Para las primeras pruebas del sistema con bladeRF real:

| Parametro | Valor recomendado | Razon |
|-----------|------------------|-------|
| Fs | 20 a 40 MS/s | Estable y sin overflow USB |
| N_fft | 256 a 1024 | Latencia manejable |
| N_activas | 0.7 * N_fft | Dejar guard bands de 15% en cada extremo |
| DC null | Si | Siempre |
| guard_bins | N_fft * 0.15 | Roll-off de filtros analogicos |
| CP | >= 32 muestras | Margen para sincronizacion y R_max hasta 1-2 m |
| Piloto | BPSK o QPSK | Bajo PAPR, facil de generar |
| Solapamiento entre bloques | >= 10% del BW | Para calibracion de fase inter-bloque |

### 4.2 Numero de bloques para UWB

Si se desea dR = 10 cm en rango:

```
B_total = c / (2 * dR) = 3e8 / (2 * 0.10) = 1.5 GHz
```

Con BW_efectivo por bloque = 30 MHz (Fs=40MS/s, 75% activas):

```
N_bloques = B_total / BW_bloque = 1500 / 30 = 50 bloques
```

50 bloques x 21 posiciones azimutales = 1050 capturas por scan completo.

Con ~10 ms por captura (TX burst + RX + procesamiento): ~10 segundos por scan.

Este tiempo es manejable para experimentos de laboratorio con blancos estaticos.

### 4.3 Metadata por bloque

Cada bloque OFDM capturado debe guardar:

```json
{
  "timestamp_iso": "...",
  "center_freq_hz": 2300000000,
  "sample_rate_hz": 40000000,
  "bandwidth_hz": 40000000,
  "tx_gain_db": -20.0,
  "rx_gain_db": 20.0,
  "n_fft": 512,
  "n_active": 360,
  "cp_len": 64,
  "guard_bins": 50,
  "dc_null": true,
  "pilot_seed": 42,
  "az_position_m": 0.05,
  "block_index": 3,
  "snr_estimate_db": null,
  "clipping_ratio": 0.0,
  "rms_rx": 0.0032
}
```

---

## 5. Relacion entre stitching y calidad de imagen

La calidad de la imagen SAR depende directamente de la coherencia del stitching:

| Calidad de stitching | Efecto en imagen |
|--------------------|----------------|
| Solo magnitud, sin fase | Imagen incoherente, resolucion degradada |
| Fase corregida por reflector de referencia | Imagen coherente, buena resolucion |
| Fase corregida + calibracion de ganancia | Imagen optima |
| Sin solapamiento entre bloques | Artefactos en bordes de bloque |

---

## 6. Proximos pasos para implementar stitching

En orden logico:

1. **Validar un bloque OFDM TX/RX con reflector conocido** (experimento de reflector ya listo).
2. **Medir H[k] coherente** por bloque y por posicion azimutal.
3. **Implementar `acquisition/ofdm_block_capture.py`** para captura sistematica de bloques.
4. **Implementar `processing/ofdm_block_stitcher.py`** para calibracion y concatenacion.
5. **Validar con simulacion primero** (`simulation/ofdm_uwb_sar_simulator.py` ya disponible).
6. **Luego validar con hardware** en escena controlada.
