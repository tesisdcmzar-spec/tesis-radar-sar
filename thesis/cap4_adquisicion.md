# Capítulo 4 — Sistema de Adquisición SFCW

> **Estado:** borrador — sección 4.1–4.3 describe el hardware y el protocolo de captura según la documentación disponible en `legacy/`; sección 4.4–4.6 describe el módulo de carga de datos implementado y validado en `acquisition/load_sfcw_capture.py` (commit `4fd93a1`); sección 4.7 analiza las capturas reales disponibles.
> **Reproducibilidad:** análisis de capturas legacy reproducible ejecutando `py -c "np.load(path, mmap_mode='r')"` sobre cualquier archivo de `legacy/capturas_barrido/`; módulo de carga reproducible con `py -m pytest tests/test_load_sfcw_capture.py -v` (30/30 pruebas aprobadas, Python 3.12.5).
> **Datos de hardware:** los archivos `.npy` en `legacy/capturas_barrido/` (99 archivos, ~60 MB totales) son las únicas capturas reales disponibles a la fecha de redacción de este borrador. No se dispone de datos con barrido de azimut.

---

## 4.1 Plataforma de Hardware

### 4.1.1 Radio definido por software: bladeRF 2.0 micro

El subsistema de radiofrecuencia de la plataforma experimental es el bladeRF 2.0 micro (Nuand LLC), un radio definido por software (*Software-Defined Radio*, SDR) de doble canal con las siguientes características relevantes para la aplicación de radar:

| Parámetro | Valor |
|---|---|
| Rango de frecuencia de sintonía | 47 MHz – 6 GHz |
| Ancho de banda instantáneo máximo | 56 MHz |
| Resolución del ADC/DAC | 12 bits |
| Tasa de muestreo máxima | 61.44 MSPS |
| Interfaz con el host | USB 3.0 |
| Sistema operativo host | Windows 10 |

El bladeRF opera con señales IQ (*In-phase/Quadrature*) en banda base: internamente el hardware realiza la conversión entre la frecuencia de RF y la banda base analógica mediante un mezclador controlado por un oscilador local (*Local Oscillator*, LO) sintonizable. El usuario controla la frecuencia central del LO, la ganancia, el ancho de banda analógico y la tasa de muestreo digital.

Para la aplicación SFCW de esta tesis, el bladeRF se configura en modo **RX monocanal** a una frecuencia central fija durante cada paso del barrido. El canal de transmisión (TX) del bladeRF no fue activado en las capturas legacy disponibles (ver §4.7.1).

### 4.1.2 Configuración de captura conocida (parámetros validados)

Los parámetros de captura documentados en `legacy/test_barrido_frec_captura.py` y confirmados por inspección de los archivos generados son:

| Parámetro | Símbolo | Valor | Unidad |
|---|---|---|---|
| Tasa de muestreo RX | $f_s$ | 40 | MHz |
| Ancho de banda analógico | $BW_\text{IF}$ | 40 | MHz |
| Ganancia RX | — | 60 | dB |
| Número de muestras por paso | $N_s$ | 40,000 | muestras |
| Duración de captura por paso | $T_s = N_s/f_s$ | 1 | ms |
| Número de buffers | — | 16 | — |
| Tamaño de buffer | — | 8,192 | muestras |
| Número de transferencias | — | 8 | — |
| Timeout de stream | — | 3,500 | ms |
| Formato interno bladeRF | — | SC16\_Q11 | — |
| Factor de normalización ADC | — | 2,048 | cuentas/unidad |

El formato SC16\_Q11 almacena cada muestra IQ como dos enteros de 16 bits (componente I y componente Q). El script de captura convierte este formato a números complejos en punto flotante y normaliza por el rango del DAC (±2,048 cuentas → rango $[-1,\, +1]$):

```python
# Extracción de I y Q desde el buffer SC16_Q11 (legacy/test_barrido_frec_captura.py)
datos_crudos = np.frombuffer(buffer_rx, dtype=np.int16)
datos_iq = datos_crudos[0::2].astype(float) + 1j * datos_crudos[1::2].astype(float)
datos_iq /= 2048.0    # normalización: rango [-1, +1]
```

---

## 4.2 Protocolo de Barrido SFCW

### 4.2.1 Secuencia de operación por paso de frecuencia

La adquisición SFCW se realiza mediante un bucle de pasos de frecuencia. Para cada paso $n$:

1. **Sintonía del LO:** el LO del bladeRF se programa a la frecuencia central $f_n = f_\text{inicio} + n\,\Delta f$.
2. **Espera de asentamiento:** el hardware requiere un tiempo de asentamiento del PLL (*Phase-Locked Loop*) antes de que la señal sea estable. En las capturas legacy, el tiempo de sintonía medido fue del orden de decenas de milisegundos (cuantificado en `estadisticas_barrido.txt`).
3. **Captura:** se adquieren $N_s = 40,000$ muestras IQ a $f_s = 40$ MHz.
4. **Almacenamiento:** el vector IQ complejo se guarda en disco como archivo `.npy` con nombre `cap_NNN_XXXMHz.npy`, donde `NNN` es el índice del paso y `XXX` es la frecuencia central en MHz.

### 4.2.2 Extracción de la respuesta de canal por promediado coherente

Para una señal SFCW, el bladeRF transmite (o recibe, en el caso de las capturas legacy) un tono continuo a frecuencia $f_n$. La señal IQ capturada puede escribirse como:

$$s[m] = A_n \,e^{\,j(2\pi \Delta f_\text{off} m/f_s + \phi_n)} + \eta[m], \quad m = 0,\ldots, N_s-1$$

donde $A_n$ es la amplitud compleja del eco en el paso $n$, $\Delta f_\text{off}$ es la diferencia entre la frecuencia de la señal de interés y el LO (cero en el caso ideal), $\phi_n$ es la fase inicial del tono en ese paso, y $\eta[m]$ es ruido blanco aditivo del receptor.

En la condición ideal ($\Delta f_\text{off} = 0$), el flujo IQ es un fasor constante perturbado por ruido:

$$s[m] = A_n \,e^{\,j\phi_n} + \eta[m]$$

La respuesta de canal en la frecuencia $f_n$ se estima como el promedio coherente de todas las muestras del paso:

$$\hat{H}(f_n) = \frac{1}{N_s} \sum_{m=0}^{N_s-1} s[m] = A_n\,e^{j\phi_n} + \frac{1}{N_s}\sum_{m=0}^{N_s-1}\eta[m]$$

El segundo término tiene varianza $\sigma_\eta^2 / N_s$. La ganancia de integración coherente respecto a una sola muestra es:

$$G_\text{int} = 10\log_{10}(N_s) = 10\log_{10}(40000) \approx 46\;\text{dB}$$

Este cálculo asume ruido gaussiano blanco no correlacionado. Es implementado en el módulo de carga mediante la instrucción:

```python
# acquisition/load_sfcw_capture.py — función _load_legacy_directory
responses.append(complex(np.mean(iq)))
```

donde `iq` es el vector de 40,000 muestras complejas del archivo correspondiente a la frecuencia $f_n$.

### 4.2.3 Construcción del vector de respuesta de canal

Al completar el barrido de $N_f$ pasos, el vector:

$$\mathbf{h} = \left[\hat{H}(f_0),\, \hat{H}(f_1),\, \ldots,\, \hat{H}(f_{N_f-1})\right] \in \mathbb{C}^{N_f}$$

contiene la respuesta de canal compleja en la banda de frecuencias barrida. Este vector es equivalente al vector de columna del cubo de datos $\mathbf{H}[N_f, N_\text{az}]$ para una posición de apertura. Para obtener una imagen SAR es necesario repetir el proceso para cada una de las $N_\text{az}$ posiciones de apertura del riel azimutal (véase §4.8).

---

## 4.3 Posicionador Azimutal

### 4.3.1 Configuración del sistema de movimiento

El riel azimutal motorizado es el segundo subsistema físico de la plataforma. En la configuración de diseño de esta tesis, una antena monoestática se desplaza a lo largo del eje $x$ en pasos discretos, permitiendo la síntesis de la apertura virtual necesaria para la formación de imagen SAR.

El controlador de movimiento previsto es una tarjeta basada en Arduino/ESP32 con firmware GRBL/FluidNC. Los parámetros de diseño del posicionador son:

| Parámetro | Valor de diseño |
|---|---|
| Longitud total del riel | 30 cm |
| Rango de apertura $[x_\text{inicio},\, x_\text{fin}]$ | $[-15,\, +15]$ cm |
| Paso de posición $\Delta x$ | 2 cm |
| Número de posiciones $N_\text{az}$ | 16 |
| Tiempo de asentamiento por posición | TBD (medición experimental pendiente) |

> **Nota de estado:** a la fecha de redacción de este capítulo, el posicionador azimutal no ha sido integrado con el software de adquisición. El hardware de movimiento (motor, controlador, riel) está físicamente disponible pero el firmware de control y la interfaz software (Fase 5 del plan maestro) están pendientes de implementación. Todos los resultados de imagen SAR presentados en el Capítulo 3 se obtuvieron con datos sintéticos y un perfil de apertura simulado de 16 posiciones.

**Restricción de seguridad:** el movimiento del posicionador requiere aprobación explícita del operador en cada sesión, mediante el protocolo de modo *dry-run* implementado en el módulo de hardware (a desarrollar en la Fase 3). No se ejecuta ningún movimiento de motor de forma automática.

---

## 4.4 Módulo de Carga de Capturas: `acquisition/load_sfcw_capture.py`

### 4.4.1 Motivación y diseño

El módulo `acquisition/load_sfcw_capture.py` (commit `4fd93a1`) implementa el puente entre las capturas `.npy` reales y el pipeline de procesamiento existente (`compute_range_profiles`, `backprojection`). Su diseño responde a tres requisitos:

1. **Compatibilidad hacia adelante:** producir objetos `SyntheticScan(freqs_hz, x_az_m, H)` idénticos en interfaz a los que genera la simulación, para que todo el código de `processing/` funcione sin modificaciones.
2. **Compatibilidad con datos legacy:** soportar el formato de directorio de archivos por frecuencia producido por `test_barrido_frec_captura.py`, que es el único formato de datos reales disponible.
3. **Validación de dimensiones:** rechazar archivos incompatibles con mensajes de error claros que indiquen el mismatch concreto (número de frecuencias, número de posiciones).

La API pública del módulo es una única función:

```python
load_capture(path, cfg, azimuth_position_m=0.0) -> SyntheticScan
```

donde `path` puede ser un archivo `.npy` o un directorio de capturas, `cfg` es el diccionario de configuración (misma estructura que `configs/simulation.yaml`) y `azimuth_position_m` es la posición de apertura en metros para capturas de posición única.

### 4.4.2 Formatos de archivo soportados

El módulo reconoce tres formatos de captura:

**Tabla 4.1 — Formatos de captura soportados por `load_capture`**

| Formato | Tipo de entrada | Shape del array | Descripción | Disponibilidad |
|---|---|---|---|---|
| A | Archivo `.npy` | `(N_f, N_az)` complejo | Matriz H completa con barrido de azimut | Futuro (aún no disponible) |
| B | Archivo `.npy` | `(N_f,)` complejo | Respuesta de canal en una sola posición | Futuro (tras implementar sweep con TX) |
| C | Directorio | N/A | Conjunto de archivos `cap_NNN_XXXMHz.npy` | **Disponible — capturas legacy** |

**Formato A** es el formato objetivo para experimentos futuros con barrido de azimut completo: un único archivo `.npy` que contiene la matriz $\mathbf{H}[N_f, N_\text{az}]$ lista para procesar directamente.

**Formato B** es el formato de transición para capturas de posición única: un vector $\mathbf{h}[N_f]$ correspondiente a una sola posición de apertura. El loader lo convierte en $\mathbf{H}[N_f, 1]$ y asigna la posición indicada por `azimuth_position_m`.

**Formato C** es el formato de las capturas legacy del bladeRF: un directorio con 99 archivos, uno por frecuencia, cada uno con 40,000 muestras IQ. El loader extrae la frecuencia de cada archivo del nombre de archivo mediante la expresión regular `_(\d+)MHz\.npy$`, ordena los archivos por frecuencia ascendente, calcula `np.mean(iq)` para cada archivo y construye el vector $\mathbf{h}[N_f]$ → $\mathbf{H}[N_f, 1]$.

### 4.4.3 Diagrama de flujo del módulo de carga

> **[Figura 4.1]** Diagrama de flujo de `load_capture`. Entrada: `path` (archivo o directorio). Ramificación: ¿es directorio? → Formato C (inferir frecuencias de filenames, `np.mean` por archivo). ¿es `.npy` 2D? → Formato A (validar dims vs config). ¿es `.npy` 1D? → Formato B (validar $N_f$, expandir a 2D). Salida común: `SyntheticScan(freqs_hz, x_az_m, H)`.

### 4.4.4 Validación del módulo

El módulo fue validado mediante 18 pruebas unitarias en `tests/test_load_sfcw_capture.py`. Todas las pruebas utilizan arrays sintéticos generados en memoria (no se leen archivos de hardware durante los tests):

**Tabla 4.2 — Pruebas unitarias del módulo de carga**

| Grupo | N° | Qué verifica |
|---|---|---|
| Formato A | 4 | Carga correcta `(N_f, N_az)`, grilla de frecuencias, grilla de apertura, error claro por mismatch de $N_f$ y $N_\text{az}$ |
| Formato B | 3 | Shape resultante `(N_f, 1)`, propagación de `azimuth_position_m`, error por $N_f$ incorrecto |
| Formato C | 6 | Carga desde directorio, frecuencias inferidas correctas, orden correcto con archivos desordenados, $H[k] = \texttt{np.mean}(\text{iq}_k)$, propagación de posición, error en directorio vacío |
| Errores | 3 | `FileNotFoundError` para path inexistente, `ValueError` para extensión inválida, `ValueError` para array 3D |
| Integración | 2 | El `SyntheticScan` producido alimenta correctamente `compute_range_profiles`; el módulo no contiene sentencias `import bladerf` |

**Resultado:** 30/30 pruebas aprobadas (18 nuevas + 12 existentes de simulación, sin regresiones), commit `4fd93a1`, Python 3.12.5.

---

## 4.5 Análisis de las Capturas Legacy

### 4.5.1 Descripción del conjunto de datos

El directorio `legacy/capturas_barrido/` contiene 99 archivos `.npy` generados por el script `legacy/test_barrido_frec_captura.py` con el bladeRF 2.0 micro. La inspección de los archivos con `numpy.load(..., mmap_mode='r')` (sin cargar los datos completos en RAM) revela:

**Tabla 4.3 — Propiedades de las capturas legacy**

| Propiedad | Valor |
|---|---|
| Número de archivos | 99 |
| Frecuencia inicial | 100 MHz |
| Frecuencia final | 5,980 MHz |
| Paso de frecuencia $\Delta f$ | 60 MHz |
| Número de pasos $N_f$ | 99 |
| Ancho de banda total | 5,880 MHz |
| Shape por archivo | `(40,000,)` |
| Dtype por archivo | `complex128` |
| Tamaño por archivo | ~625 KB |
| Tamaño total | ~60 MB |
| Posiciones de apertura $N_\text{az}$ | **1** |

Las frecuencias están uniformemente espaciadas a $\Delta f = 60$ MHz sobre el rango de 100 MHz a 5,980 MHz. Todos los archivos tienen forma y tipo idénticos (`(40000,)` complex128), lo que indica consistencia en el protocolo de captura.

### 4.5.2 Parámetros de imagen teóricos derivados

A partir de los parámetros del conjunto de datos es posible calcular las métricas de imagen teóricas que se obtendrían si las capturas contuvieran señales de eco coherentes:

**Tabla 4.4 — Métricas de imagen teóricas para las capturas legacy**

| Métrica | Expresión | Valor |
|---|---|---|
| Resolución de rango (rect.) | $\delta r = c / (2\,BW)$ | **2.55 cm** |
| Rango no ambiguo | $R_\text{max} = c / (2\,\Delta f)$ | 2.50 m |
| Paso de rango (IFFT, 4×) | $\Delta r = c / (2 \times 4\,N_f\,\Delta f)$ | ~1.6 mm |
| Posiciones de apertura | 1 | (sin barrido de azimut) |
| Imagen SAR 2D posible | No | (requiere $N_\text{az} > 1$) |

El ancho de banda de 5,880 MHz corresponde a una resolución de rango teórica de 2.55 cm, significativamente mejor que la resolución de 7.5 cm del sistema de simulación (BW = 2 GHz). Sin embargo, esta resolución solo es alcanzable si la señal transmitida es coherente y la respuesta de canal es estable durante el tiempo de captura.

### 4.5.3 Comparación con el config de simulación

Los parámetros de las capturas legacy difieren notablemente del config de simulación usado en el Capítulo 3:

| Parámetro | Legacy (`capturas_barrido/`) | Simulación (`simulation.yaml`) |
|---|---|---|
| $f_\text{inicio}$ | 100 MHz | 500 MHz |
| $f_\text{fin}$ | 5,980 MHz | 2,500 MHz |
| $\Delta f$ | 60 MHz | 5 MHz |
| $N_f$ | 99 | 401 |
| BW | 5,880 MHz | 2,000 MHz |
| $N_\text{az}$ | **1** | 16 |

Esta discrepancia implica que el módulo de carga en Formato C opera de forma autónoma (infiere la grilla de frecuencias desde los nombres de archivo) y no puede validarse directamente contra el config de simulación. Para el procesamiento de las capturas legacy se deberá usar un config actualizado con los parámetros correspondientes, o utilizar directamente los `freqs_hz` retornados por el objeto `SyntheticScan`.

> **[Figura 4.2]** Comparación de las grillas de frecuencia: barrido legacy (100–5,980 MHz, 99 puntos, $\Delta f = 60$ MHz) versus barrido de simulación (500–2,500 MHz, 401 puntos, $\Delta f = 5$ MHz). Eje horizontal: frecuencia [MHz]. Se remarcan la diferencia de paso (resolución espectral) y la diferencia de ancho de banda (resolución de rango).

---

## 4.6 Limitaciones de los Datos Legacy para Formación de Imagen SAR

### 4.6.1 Ausencia de canal de transmisión activo

El script `legacy/test_barrido_frec_captura.py` configura únicamente el canal RX del bladeRF (`canal.enable = True` sobre `CHANNEL_RX(0)`). No hay evidencia documental ni de código de que el canal TX estuviera activo durante la toma de las capturas.

Para un sistema de radar activo, el TX y el RX deben operar coherentemente: el transmisor emite el tono de referencia y el receptor captura el eco reflejado por el blanco. Sin TX activo, el canal RX captura únicamente:

- Ruido térmico del receptor.
- Señales de RF del ambiente (emisiones externas en la banda de sintonía).
- *Self-leakage* del oscilador local del propio bladeRF.

Por tanto, el valor `np.mean(iq)` para las capturas legacy representa la amplitud de las señales ambientales en la frecuencia $f_n$, no la respuesta de canal de un blanco de interés. Las capturas legacy **no pueden utilizarse directamente para formar perfiles de rango de un blanco**.

Esta limitación es estructural y no puede resolverse en postprocesado. Se requiere una nueva sesión de adquisición con TX activo y un blanco de referencia conocido para validar la cadena completa TX → blanco → RX → procesamiento.

### 4.6.2 Ausencia de barrido de azimut

Las 99 capturas legacy corresponden a una única posición de la antena. Sin variación de posición de apertura ($N_\text{az} = 1$), la formación de imagen SAR 2D no es posible. El loader produce un objeto `SyntheticScan` con `x_az_m = [0.0]` y `H.shape = (99, 1)`, que permite únicamente el cálculo de un perfil de rango 1D.

Para obtener una imagen SAR real se requiere:
1. Repetir el barrido de frecuencias en cada posición del riel azimutal (16 posiciones, $\Delta x = 2$ cm).
2. Almacenar las 16 respuestas de canal en un único archivo `(N_f, N_\text{az})` o en 16 conjuntos de archivos por frecuencia.
3. Integrar el posicionador azimutal con el software de adquisición (Fase 5 del plan maestro).

### 4.6.3 Ausencia de substracción de fondo

En un experimento de imagen con phantom, la señal de retorno tiene dos componentes:

$$H_\text{medida}(f) = H_\text{fondo}(f) + H_\text{phantom}(f)$$

donde $H_\text{fondo}(f)$ incluye reflexiones de las paredes del recinto, el soporte mecánico, los cables y el *self-leakage* del TX. La componente de interés es $H_\text{phantom}(f)$, que se obtiene restando una captura de referencia sin phantom:

$$H_\text{phantom}(f) = H_\text{medida}(f) - H_\text{fondo}(f)$$

El pipeline actual no incluye este módulo de substracción. Su ausencia implica que cualquier imagen SAR obtenida con datos reales estará dominada por las reflexiones estáticas del entorno, enmascarando la señal del phantom. La substracción de fondo es prerrequisito para cualquier experimento cuantitativo con datos reales.

### 4.6.4 Resumen de bloqueos para uso con hardware real

| Bloqueo | Causa | Fase de resolución |
|---|---|---|
| Sin eco de blanco | TX no activo en capturas legacy | Fase 3–4 (abstracción hardware + sweep) |
| Sin imagen SAR 2D | $N_\text{az} = 1$ | Fase 5 (posicionador azimutal) |
| Imagen dominada por fondo | Sin substracción de fondo | Inmediato (próximo módulo de procesamiento) |
| Discrepancia de config | Parámetros legacy ≠ simulación | Crear `configs/legacy.yaml` antes de procesar |

---

## 4.7 Reproducibilidad

### 4.7.1 Inspección de capturas

Para reproducir el análisis del §4.5, ejecutar desde la raíz del repositorio:

```python
import numpy as np, os, glob, re

base = r'legacy/capturas_barrido'
files = sorted(glob.glob(os.path.join(base, '*.npy')))
print(f'Total archivos: {len(files)}')
for path in files[:3]:
    arr = np.load(path, mmap_mode='r')
    print(f'  {os.path.basename(path):30s}  shape={arr.shape}  dtype={arr.dtype}')
```

### 4.7.2 Carga con el módulo implementado

Para cargar las capturas legacy mediante el módulo de adquisición:

```python
from acquisition.load_sfcw_capture import load_capture
import yaml

with open('configs/simulation.yaml') as f:
    cfg = yaml.safe_load(f)

# Carga Formato C: directorio de capturas legacy
scan = load_capture('legacy/capturas_barrido', cfg, azimuth_position_m=0.0)
print(f'freqs_hz: {scan.freqs_hz[[0,-1]]/1e6} MHz (inicio, fin)')
print(f'H.shape:  {scan.H.shape}')    # → (99, 1)
```

> **Nota:** el config de simulación `simulation.yaml` no se usa para construir las frecuencias en Formato C (se infieren de los nombres de archivo). Sin embargo, se requiere por la firma de la función; un futuro `configs/legacy.yaml` deberá crearse con los parámetros reales de las capturas.

### 4.7.3 Trazabilidad de archivos y código

| Artefacto | Path | Commit |
|---|---|---|
| Script de captura legacy | `legacy/test_barrido_frec_captura.py` | (anterior al sistema de versiones) |
| Archivos de captura legacy | `legacy/capturas_barrido/cap_000_100MHz.npy` … `cap_098_5980MHz.npy` | N/A (gitignore recomendado para archivos binarios grandes; presentes en el repo actual) |
| Módulo de carga | `acquisition/load_sfcw_capture.py` | `4fd93a1` |
| Tests del módulo | `tests/test_load_sfcw_capture.py` | `4fd93a1` |
| Informe de sesión | `reports/session_reports/2026-05-31_loader_capturas_sfcw.md` | `0a915d4` |

---

## 4.8 Trabajo Futuro del Subsistema de Adquisición

Las siguientes tareas son necesarias para completar el subsistema de adquisición y habilitar experimentos cuantitativos con el sistema de radar:

1. **Substracción de fondo** (`processing/background_subtraction.py`): módulo que resta la respuesta del canal de referencia (sin phantom) de la respuesta medida (con phantom), produciendo un `SyntheticScan` con solo la contribución del blanco. Este es el **próximo paso inmediato** (no requiere hardware adicional; puede validarse con datos sintéticos).

2. **Abstracción del hardware bladeRF** (`hardware/bladerf_device.py`, Fase 3): envoltorio que expone `tune(freq_hz)`, `rx_block(n_samples)` y `tx_enable(bool)` con modo *dry-run* por defecto. Requiere aprobación explícita del operador para cualquier transmisión de RF.

3. **Script de barrido SFCW con TX** (`acquisition/sfcw_sweep.py`, Fase 4): implementa el bucle de sintonía → TX → RX → `np.mean(iq)` para un barrido completo, produciendo un vector `H(f)` listo para guardar en Formato B.

4. **Integración del posicionador** (Fase 5): extiende el sweep a múltiples posiciones de apertura, produciendo la matriz `H(f, x_az)` en Formato A.

5. **Configuración para datos legacy** (`configs/legacy.yaml`): archivo de config con los parámetros reales de las capturas legacy (100–5,980 MHz, $\Delta f = 60$ MHz) para poder usar el loader en Formatos A/B con datos provenientes de hardware reconfigurado.

---

## 4.9 Fuentes

**Fuentes internas:**
- `legacy/test_barrido_frec_captura.py` — fuente de verdad sobre el protocolo de captura legacy: parámetros de configuración del bladeRF, formato SC16\_Q11, factor de normalización 2048.
- `legacy/capturas_barrido/cap_000_100MHz.npy` … `cap_098_5980MHz.npy` — archivos inspeccionados con `mmap_mode='r'`; shapes confirmados como `(40000,)` complex128 en todos los archivos.
- `acquisition/load_sfcw_capture.py` — implementación del módulo de carga, commit `4fd93a1`.
- `tests/test_load_sfcw_capture.py` — validación mediante 18 pruebas unitarias, 30/30 aprobadas.
- `simulation/synthetic_scan.py` — contrato de `SyntheticScan` que el loader debe cumplir.
- `reports/session_reports/2026-05-31_loader_capturas_sfcw.md` — informe detallado de la sesión de implementación.

**Fuentes externas:** No se consultaron fuentes externas durante la redacción de este capítulo. Los fundamentos del estimador de respuesta de canal por promediado coherente son de dominio público en el área de comunicaciones y radar; las referencias académicas correspondientes se incorporarán en la versión final de la tesis.

---

*Fin del Capítulo 4 (borrador — sistema de adquisición).*
