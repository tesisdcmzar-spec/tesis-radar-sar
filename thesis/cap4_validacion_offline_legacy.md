# Capítulo 4 — Validación Offline con Capturas Legacy

## 4.1 Propósito de la validación offline

El desarrollo de un sistema SAR de microondas experimental requiere verificar, antes de comprometer tiempo de instrumentación real, que la cadena de procesamiento de señal opera correctamente sobre datos adquiridos por el hardware. Con ese objetivo, se dispone de un conjunto de capturas archivadas («capturas legacy») obtenidas previamente con el dispositivo bladeRF en modo de recepción estático.

Este capítulo describe la validación offline de dicho conjunto: se carga cada captura mediante la interfaz unificada `load_capture()`, se construye una representación `SyntheticScan`, se obtienen perfiles de rango mediante transformada inversa de Fourier (IFFT), y se interpretan los resultados en el contexto de las limitaciones propias de una adquisición de apertura única.

El objetivo no es extraer información sobre un blanco específico, sino verificar que la cadena de software —desde la lectura de archivos `.npy` hasta el cálculo del perfil de rango— funciona sin errores con datos reales del hardware.

---

## 4.2 Descripción del formato de captura legacy

### 4.2.1 Organización de archivos

Las capturas legacy se encuentran en el directorio `legacy/capturas_barrido/`. Cada archivo corresponde a una frecuencia de operación discreta del barrido SFCW (*Stepped-Frequency Continuous Wave*) y sigue la convención de nombres:

```
cap_NNN_XXXMHz.npy
```

donde `NNN` es un índice ordinal de tres dígitos y `XXX` es la frecuencia central de captura en megahercios.

### 4.2.2 Contenido de cada archivo

Cada archivo contiene un vector complejo unidimensional de tipo `complex128` con 40 000 muestras:

- **Forma:** `(40 000,)` complex128
- **Dominio temporal:** muestras IQ adquiridas a 40 MHz de tasa de muestreo
- **Duración de captura:** 40 000 / 40×10⁶ = 1 ms por frecuencia

El conjunto completo comprende 99 archivos que cubren el rango 100–5980 MHz en pasos de 60 MHz:

| Parámetro | Valor |
|-----------|-------|
| Número de pasos en frecuencia | 99 |
| Frecuencia inicial | 100 MHz |
| Frecuencia final | 5 980 MHz |
| Paso en frecuencia | 60 MHz |
| Ancho de banda total | 5 880 MHz |
| Número de posiciones acimutal | 1 (apertura única estática) |

---

## 4.3 Conversión de flujos IQ a respuesta en frecuencia H(f)

### 4.3.1 Fundamento físico

En un sistema SFCW, el receptor captura la señal reflejada mientras el transmisor irradia una onda continua a la frecuencia $f_k$. La respuesta en frecuencia discreta se define como:

$$H(f_k) = \frac{s_{\text{rx}}(f_k)}{s_{\text{tx}}(f_k)}$$

donde $s_{\text{rx}}$ es la señal recibida y $s_{\text{tx}}$ es la señal transmitida de referencia.

En ausencia de una medición simultánea de la referencia de transmisión, la implementación práctica en este sistema extrae $H(f_k)$ como la media coherente de las muestras IQ:

$$H(f_k) = \langle x_{\text{IQ}}(t; f_k) \rangle = \frac{1}{N} \sum_{n=0}^{N-1} x_n(f_k)$$

Este promedio es equivalente a la integración coherente de una señal CW de duración $T = N / f_s$, lo que reduce el ruido de receptor en un factor $\sqrt{N}$ en amplitud (≈ 46 dB para $N=40\,000$).

### 4.3.2 Implementación en `load_capture()`

La función pública `load_capture(path, cfg, azimuth_position_m)` del módulo `acquisition.load_sfcw_capture` detecta automáticamente que el argumento `path` es un directorio y delega en `_load_legacy_directory()`:

```python
for freq_mhz, fpath in freq_file_pairs:
    iq = np.load(str(fpath), mmap_mode="r")   # no copia RAM completa
    responses.append(complex(np.mean(iq)))     # H(f_k) = media IQ

freqs_hz = np.array([f * 1e6 for f, _ in freq_file_pairs])
H = np.array(responses, dtype=complex)[:, None]  # (N_f, 1)
```

La carga usa `mmap_mode='r'`: el archivo se mapea en memoria sin cargar los 40 000 valores de cada frecuencia en RAM activa, lo que es seguro para conjuntos de datos de varias decenas de megabytes.

### 4.3.3 Relación con SyntheticScan

El resultado de `load_capture()` es un objeto `SyntheticScan` con:

- `freqs_hz` : vector de frecuencias $[f_0, f_1, \ldots, f_{N_f-1}]$ en Hz, inferidas del nombre de archivo.
- `x_az_m` : vector de posición acimutal $[0.0]$ m (única posición).
- `H` : matriz compleja de dimensiones $(N_f, 1)$.

Esta estructura es idéntica a la que produce la simulación sintética, lo que permite reutilizar sin modificaciones `compute_range_profiles()` y `backprojection()`.

---

## 4.4 Análisis de rango en 1D

### 4.4.1 Parámetros SFCW teóricos

Con el conjunto de capturas legacy se obtienen las siguientes figuras de mérito teóricas del sistema SFCW:

| Métrica | Expresión | Valor |
|---------|-----------|-------|
| Resolución en rango (rect.) | $\delta r = c / (2 B)$ | ≈ 2.55 cm |
| Rango no ambiguo | $R_{\text{max}} = c / (2 \Delta f)$ | 2.50 m |

donde $B = 5\,880$ MHz y $\Delta f = 60$ MHz.

### 4.4.2 Perfil de rango mediante IFFT

El perfil de rango se obtiene aplicando la IFFT a lo largo del eje de frecuencia de $H(f)$:

$$h(\tau) = \mathcal{F}^{-1} \left\{ W(f) \cdot H(f) \right\}$$

con $W(f)$ la función ventana (rectangular o Hanning) y $\tau$ la variable de retardo. El eje de rango correspondiente es:

$$r_k = \frac{c \, k}{2 \, N_{\text{FFT}} \, \Delta f}, \quad k = 0, 1, \ldots, N_{\text{FFT}}/2 - 1$$

La función `compute_range_profiles()` del módulo `processing.range_profile` implementa esta operación con zero-padding configurable ($\times 8$ en el análisis offline, que produce una resolución de grilla ≈ 3.2 mm frente a la resolución real de ≈ 2.55 cm).

### 4.4.3 Comparación de ventanas

Se evaluaron dos configuraciones de ventana:

| Ventana | Resolución en rango | Nivel de lóbulos laterales |
|---------|--------------------|-----------------------------|
| Rectangular | ≈ 2.55 cm | −13 dB |
| Hanning | ≈ 5.1 cm | −31 dB |

Para los datos legacy, la diferencia práctica entre ambas ventanas indica principalmente si la estructura del ruido residual es sensible al apodamiento espectral, no la presencia o ausencia de un blanco resuelto.

---

## 4.5 Por qué no es posible obtener una imagen SAR 2D

La reconstrucción SAR por retroproyección requiere la función de transferencia $H(f, x_{\text{az}})$ medida en $N_{\text{az}} \geq 2$ posiciones acimutales coherentes. Para cada píxel de imagen $(x_p, z_p)$:

$$I(x_p, z_p) = \sum_{n=1}^{N_{\text{az}}} h\!\left(\frac{2R_n}{c}; x_{\text{az},n}\right) \, e^{+j4\pi f_0 R_n / c}$$

con $R_n = \sqrt{(x_{\text{az},n} - x_p)^2 + z_p^2}$ la distancia apertura-píxel.

El conjunto de capturas legacy tiene **$N_{\text{az}} = 1$** (apertura única). Sin variación de posición acimutal:

- No existe información sobre el ángulo de llegada.
- La suma sobre apertura colapsa a un único término: no hay ganancia de apertura sintética.
- El perfil obtenido es equivalente al de un radar monoestático puntual sin síntesis de apertura.

Por tanto, **no es posible generar una imagen SAR 2D** a partir de estos datos. La validación offline se limita a confirmar que la cadena de procesamiento produce perfiles de rango 1D correctamente a partir de datos reales del hardware.

---

## 4.6 Interpretación científica de los perfiles de rango

La interpretación de los perfiles de rango obtenidos de las capturas legacy debe realizarse con cautela:

1. **Sin calibración.** La respuesta $H(f)$ incluye contribuciones del cable RF, pérdidas en conectores, variación de ganancia del bladeRF con la frecuencia, y reflexiones internas del sistema. Sin una medición de referencia (*back-to-back* o *short circuit*), no es posible extraer la respuesta del canal ambiente de forma separada.

2. **Sin sustracción de fondo.** Un pico en el perfil de rango puede corresponder a una reflexión interna, al fondo de la sala, o a un máximo de ruido — no necesariamente a un blanco de interés.

3. **Escenario de adquisición desconocido.** Los metadatos de captura no registran la distancia al blanco, el tipo de blanco, ni si el transmisor estaba activo con una señal coherente o si se trató de una captura de receptor pasivo.

4. **Sin detección de objetos.** No se afirma la detección de ningún objeto, tejido, o blanco específico. No se realizan afirmaciones clínicas de ningún tipo.

---

## 4.7 Qué valida y qué no valida esta etapa

### 4.7.1 Qué valida

- La función `load_capture()` procesa correctamente un directorio de capturas legacy en formato C (per-frecuencia).
- La inferencia de frecuencias desde nombres de archivo es correcta y produce un vector ordenado.
- La media coherente IQ produce un valor `H(f_k)` complejo para cada frecuencia.
- El objeto `SyntheticScan` resultante es compatible con `compute_range_profiles()`.
- Los perfiles de rango 1D se calculan sin errores numéricos para datos reales del hardware.
- Las ventanas rectangular y Hanning producen los efectos esperados sobre el perfil.
- Todo el flujo es reproducible offline sin conexión al hardware.

### 4.7.2 Qué no valida

- La corrección radiométrica o la calibración del canal RF.
- La capacidad de detectar o localizar un blanco específico.
- La calidad de la imagen SAR 2D (imposible con apertura única).
- La coherencia entre barridos (requiere múltiples posiciones acimutales).
- El rendimiento del sistema bajo condiciones de laboratorio controladas.

---

## 4.8 Transición a la fase de adquisición hardware

El cierre de la validación offline establece los siguientes requisitos para la fase de hardware:

1. **Abstracción hardware segura.** El módulo `hardware/bladerf_device.py` debe implementar una capa de seguridad con: modo de ensayo en seco (*dry-run*), compuerta explícita `CONFIRM HARDWARE RUN` antes de cualquier transmisión RF, y registro (*log*) de todas las operaciones.

2. **Barrido acimutal coherente.** El script de adquisición debe registrar $H(f, x_{\text{az}})$ en al menos 8–16 posiciones acimutales coherentes con paso ≤ 2 cm para conseguir resolución cruzada ≤ 5 cm.

3. **Sustracción de fondo.** Antes de cada experimento con blanco, se debe medir y almacenar una captura de referencia (*empty scene*) para restar la respuesta estática del sistema.

4. **Experimento con fantasma.** El primer experimento controlado usará un fantasma dieléctrico de geometría conocida (cilindro o esfera de permitividad conocida) en posición y distancia documentadas.

5. **Verificación cruzada.** Los perfiles de rango medidos deben compararse con los obtenidos por simulación sintética con la misma geometría para verificar la calibración del sistema.

---

*Este capítulo es parte de la tesis de pregrado en Telecomunicaciones. Trabajo de alcance estrictamente experimental y de validación de software. Sin afirmaciones médicas ni clínicas.*
