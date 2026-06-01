# OFDM — análisis de ancho de banda efectivo con bladeRF

> Fuente canónica: este archivo.
> Espejo Notion (solo lectura humana): https://www.notion.so/3714f30e6f4c816c92a1dbbd06d972ed
> Última sincronización desde Notion: 2026-05-31

---

## Propósito

Esta página resume los problemas que reducen el ancho de banda efectivo del sistema UWB-OFDM-SAR con bladeRF. El objetivo es evitar asumir que `60 MHz nominales` equivalen a `60 MHz útiles`.

---

## Punto de partida

El bladeRF puede sintonizar un rango RF amplio, pero su ancho de banda instantáneo está limitado por sample rate, filtros analógicos/digitales y flujo USB. Por eso el sistema debe trabajar por bloques.

Arquitectura corregida:

```
bloque OFDM limitado por BW instantáneo
+ múltiples frecuencias centrales
+ stitching de bloques
= ancho de banda sintético UWB
```

---

## Diferencia entre conceptos

### Rango de sintonía RF

Es el rango de frecuencias centrales que el bladeRF puede seleccionar.

### Ancho de banda instantáneo

Es el ancho de espectro que puede capturarse en una sola adquisición IQ.

### Ancho de banda efectivo OFDM

Es la parte realmente confiable del bloque OFDM después de considerar filtros, subportadoras de guarda, DC null, CP, sincronización, PAPR, calibración y SNR.

---

## Problemas que reducen el ancho de banda efectivo

### 1. Sample rate máximo

Aunque se configure un sample rate alto, el ancho de banda digital útil queda limitado por Nyquist y por la calidad real del ADC/DAC, USB y firmware.

Ejemplo conceptual:

```
Fs = 60 MS/s
Nyquist ideal ≈ 60 MHz complejos IQ
BW útil real < 60 MHz
```

### 2. Filtros analógicos internos

El front-end del bladeRF usa filtros analógicos con respuesta no perfectamente plana. Cerca de los bordes del bloque puede haber atenuación, ripple de ganancia y distorsión de fase.

Consecuencia:
- no conviene usar subportadoras pegadas a los bordes
- se necesitan guard bands
- cada bloque debe calibrarse en magnitud y fase

### 3. Filtros digitales / DSP interno

La cadena digital también puede introducir respuesta no plana, decimación/interpolación y restricciones de ancho de banda configurado.

Consecuencia:
- `sample_rate` y `bandwidth` no son equivalentes
- hay que medir la respuesta real por configuración
- conviene guardar metadata exacta de `sample_rate`, `bandwidth`, ganancias y centro de frecuencia

### 4. Subportadoras de guarda

OFDM no debería ocupar todo el ancho del bloque. Hay que dejar subportadoras apagadas en los extremos para evitar leakage, aliasing, roll-off de filtros e interferencia.

```
N_fft = 1024
N_activas < N_fft
bordes apagados
DC apagada
```

### 5. Subportadora DC

La portadora central suele apagarse para evitar problemas de DC offset, LO leakage y componentes espurias alrededor de cero IF/baseband.

Consecuencia:
- queda un hueco en el centro del bloque
- al hacer stitching hay que saber que esa subportadora no es válida

### 6. Prefijo cíclico

El CP no reduce el ancho de banda ocupado, pero sí reduce eficiencia temporal y energética. Además, debe cubrir el retardo máximo de la escena.

Regla conceptual:

```
T_CP >= delay_spread_max
```

Para radar monostático:

```
delay ≈ 2R/c
```

Si CP es demasiado corto:
- aparece ISI
- se pierde ortogonalidad
- aparece interferencia entre celdas de rango (IRCI)
- H[k] queda contaminado

Si CP es demasiado largo:
- baja eficiencia
- baja SNR por unidad de tiempo útil
- aumenta tiempo de captura

### 7. PAPR de OFDM

OFDM puede tener alto peak-to-average power ratio. Para no saturar DAC/ADC ni PA, hay que aplicar backoff.

Consecuencia:
- se baja potencia media transmitida
- cae SNR
- pueden empeorar detección y estimación de fase

### 8. Cuantización ADC/DAC

El bladeRF trabaja con muestras I/Q de resolución limitada. Si se usa menos profundidad efectiva o hay clipping, se degrada H[k].

Consecuencia:
- hay que medir clipping ratio
- guardar RMS, peak, DC offset
- evitar saturación
- considerar que 8/4 bits efectivos pueden ser un cuello de botella si se transmiten OFDM complejos

### 9. Sincronización temporal

Para estimar OFDM hace falta encontrar correctamente el inicio del símbolo y remover CP. Un error de sincronización produce fase lineal, ICI y error de canal.

Se necesita:
- preámbulo o correlación con símbolo conocido
- estimación de offset temporal
- corrección antes de FFT

### 10. Offset de frecuencia CFO y error de sample rate SFO

Diferencias de oscilador entre TX/RX o errores de frecuencia generan rotación de subportadoras e ICI.

Aunque TX/RX estén en el mismo bladeRF, pueden existir:
- offset residual de LO
- deriva térmica
- saltos de fase al retunear bloques

### 11. ICI por offset o Doppler

OFDM es sensible a errores de frecuencia. Si las subportadoras dejan de ser ortogonales, aparece interferencia interportadora (ICI).

Para este proyecto, los blancos mamarios o phantoms son estáticos, así que Doppler no debería ser el problema principal. Pero sí pueden serlo CFO, SFO, fase entre bloques e inestabilidad de LO.

### 12. Phase discontinuity entre bloques

Cuando el bladeRF cambia de frecuencia central entre bloques, la fase absoluta puede saltar. Para coser bloques, no alcanza con concatenar magnitudes.

Se necesita:
- bloque solapado entre frecuencias
- referencia conocida
- medición de fondo
- calibración de fase
- quizá reflector de referencia

### 13. Stitching entre bloques

Para sintetizar varios GHz, cada bloque OFDM debe ubicarse en frecuencia absoluta.

Problemas:
- diferencia de ganancia por bloque
- fase arbitraria por retune
- bordes no confiables
- subportadoras apagadas
- ruido distinto por banda
- interferencia externa

Estrategia recomendada:

```
usar BW nominal menor que el máximo
usar subportadoras activas solo en zona plana
usar solapamiento entre bloques
calibrar magnitud/fase con fondo o referencia
coser solo regiones válidas
```

### 14. Interferencia externa

La banda 2.4 GHz contiene Wi-Fi/Bluetooth. OFDM puede ser robusto, pero no inmune. Las subportadoras afectadas pueden apagarse o ponderarse.

Estrategia:
- medir espectro RX-only
- marcar subportadoras contaminadas
- excluirlas o bajar peso en reconstrucción

### 15. Respuesta de antenas

Las antenas UWB no son planas. Su ganancia, fase y patrón cambian con la frecuencia.

Esto afecta:
- magnitud de H[k]
- fase
- comparación entre bloques
- reconstrucción SAR

Se necesita calibración o al menos medición de referencia.

---

## Fórmulas útiles

Resolución en rango ideal:

```
dR = c / (2 * B_total)
```

Rango no ambiguo por espaciado de subportadora:

```
R_unamb = c / (2 * df)
```

Subcarrier spacing:

```
df = Fs / N_fft
```

Duración OFDM útil:

```
T = 1 / df
```

Duración total del símbolo:

```
T_OFDM = T + T_CP
```

CP para rango máximo:

```
T_CP >= 2 * R_max / c
```

Canal por subportadora:

```
H[k] = Y[k] / X[k]
```

---

## Recomendación práctica inicial

No diseñar al límite de 60 MHz. Para las primeras pruebas:

```
Fs:                    20 a 40 MS/s
BW analógico:          cercano pero menor al Fs
N_fft:                 256 / 512 / 1024
subportadoras activas: zona central
DC:                    apagada
guard bands:           en extremos
CP:                    suficiente para escena de 1 a 3 m
simbolo:               conocido y repetido
```

Luego aumentar hacia el máximo solo cuando:
- sincronización funcione
- H[k] sea estable
- no haya clipping
- el stitching esté calibrado
- el reflector de referencia aparezca en rango correcto

---

## Conclusión

El ancho de banda nominal del bladeRF no debe confundirse con ancho de banda útil para OFDM radar. El sistema debe estimar experimentalmente el ancho de banda efectivo por configuración, seleccionar subportadoras válidas, calibrar magnitud/fase y recién después coser bloques para UWB-SAR.
