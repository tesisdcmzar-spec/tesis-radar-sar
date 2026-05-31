# Capítulo 3 — Validación mediante Simulación Sintética

> **Estado:** borrador — resultados basados exclusivamente en simulación computacional (sin datos de hardware).
> **Reproducibilidad:** `configs/simulation.yaml` (commit `31bc9ee`), script `experiments/run_simulation.py`, Python 3.12.5, NumPy, Matplotlib.

---

## 3.1 Motivación

Antes de operar el sistema real de radar SAR de apertura sintética basado en bladeRF, se construyó un pipeline de simulación independiente del hardware con tres objetivos: (1) verificar la corrección del modelo de señal SFCW (*Stepped-Frequency Continuous Wave*), (2) validar el algoritmo de retroproyección (*backprojection*) y (3) establecer parámetros de referencia de resolución que luego puedan compararse con mediciones reales.

---

## 3.2 Modelo de Señal

### 3.2.1 Configuración monoestática

Se modela una configuración monoestática en la que el transmisor y el receptor están coubicados en la misma posición de apertura $x_\text{az}$. El blanco puntual $k$ se encuentra en las coordenadas $(x_k, z_k)$, donde $x$ es la dimensión transversal (*cross-range*) y $z$ es la profundidad (*down-range*) medida desde el plano de apertura.

La distancia monoestática (un solo sentido) entre la posición de apertura y el blanco es:

$$R_k(x_\text{az}) = \sqrt{(x_\text{az} - x_k)^2 + z_k^2}$$

### 3.2.2 Respuesta en frecuencia SFCW

Para una señal SFCW con $N_f$ frecuencias $f_n = f_\text{inicio} + n \,\Delta f$, $n = 0, \ldots, N_f-1$, la respuesta compleja recibida de un blanco de amplitud $A_k$ en la posición de apertura $x_\text{az}$ es:

$$H(f_n,\, x_\text{az}) = \sum_k A_k \exp\!\left(-j\,\frac{4\pi f_n R_k(x_\text{az})}{c}\right)$$

donde $c$ es la velocidad de propagación ($c = 3 \times 10^8$ m/s en espacio libre). El factor $4\pi$ corresponde al retardo de doble trayecto (*two-way*). Para múltiples blancos, la respuesta es una superposición lineal.

---

## 3.3 Parámetros de Simulación

Los parámetros empleados se especifican completamente en el archivo `configs/simulation.yaml` (Tabla 3.1). No se realizó ningún ajuste manual durante la generación de resultados.

**Tabla 3.1 — Parámetros del experimento de simulación**

| Parámetro | Valor | Unidad |
|---|---|---|
| Frecuencia de inicio ($f_\text{inicio}$) | 500 | MHz |
| Frecuencia de fin ($f_\text{fin}$) | 2500 | MHz |
| Ancho de banda ($BW$) | 2000 | MHz |
| Paso en frecuencia ($\Delta f$) | 5 | MHz |
| Número de frecuencias ($N_f$) | 401 | — |
| Inicio de apertura ($x_\text{inicio}$) | −15 | cm |
| Fin de apertura ($x_\text{fin}$) | +15 | cm |
| Paso de apertura ($\Delta x$) | 2 | cm |
| Posiciones de apertura ($N_\text{az}$) | 16 | — |
| Velocidad de propagación ($c$) | $3 \times 10^8$ | m/s |
| Ruido añadido | ninguno | — |
| Factor de sobremuestra IFFT | 4× | — |

**Tabla 3.2 — Blancos del fantasma sintético**

| Blanco | $x$ (cm) | $z$ (cm) | Amplitud relativa |
|---|---|---|---|
| T1 | −6 | 9 | 1.0 |
| T2 | +6 | 19 | 1.0 |

Separación en profundidad: $\Delta z = 10$ cm. Separación transversal: $\Delta x = 12$ cm.

---

## 3.4 Método de Procesamiento

### 3.4.1 Perfil de rango por IFFT

Para cada posición de apertura $x_\text{az}$, se aplica la IFFT sobre el eje de frecuencias con sobremuestra (*zero-padding*) de factor 4:

$$h[n,\, x_\text{az}] = \text{IFFT}\!\left\{w[n_f] \cdot H(f_{n_f}, x_\text{az})\right\}_{N_\text{IFFT}}$$

donde $w[n_f]$ es la función de ventana y $N_\text{IFFT} = 4 N_f$. El eje de rango resultante es:

$$r_n = \frac{c \cdot n}{2\, N_\text{IFFT}\, \Delta f}$$

Este eje corresponde al rango monoestático (un solo sentido) al blanco que produce un pico en el bin $n$.

Se evaluaron dos ventanas:

- **Rectangular** (`none`): resolución de rango $\delta r = c/(2\,BW) = 7.5$ cm; lóbulos laterales a $-13$ dB.
- **Hanning**: resolución $\approx 15$ cm; lóbulos laterales a $-31$ dB.

### 3.4.2 Corrección de fase portadora

Dado que el barrido SFCW comienza en $f_\text{inicio} = 500$ MHz y no en DC, la IFFT de $H(f_n)$ retiene un término de fase portadora $\exp(-j\,4\pi f_\text{inicio} R/c)$ que varía con el rango. Sin esta corrección, la suma coherente en retroproyección es destructiva. La corrección aplicada multiplica cada contribución de apertura por el factor conjugado antes de acumular:

$$\text{corrección}(R) = \exp\!\left(+j\,\frac{4\pi f_\text{inicio}\, R}{c}\right)$$

Esta corrección fue verificada analíticamente y validada mediante la prueba unitaria `test_frequency_response_phase_single_target` (ver §3.5).

### 3.4.3 Retroproyección SAR

La imagen SAR se forma mediante retroproyección coherente sobre una cuadrícula de píxeles $(x_p, z_p)$:

$$I(x_p, z_p) = \sum_{x_\text{az}} \left[\tilde{h}\!\left(R_0(x_\text{az}),\, x_\text{az}\right) \cdot \exp\!\left(+j\,\frac{4\pi f_\text{inicio}\, R_0}{c}\right)\right]$$

donde $\tilde{h}(r, x_\text{az})$ es el perfil de rango interpolado linealmente en $r = R_0(x_\text{az}) = \sqrt{(x_\text{az}-x_p)^2+z_p^2}$ y la exponencial es la corrección de portadora descrita en §3.4.2.

La cuadrícula de imagen empleada cubre $x \in [-20,\,+20]$ cm y $z \in [2,\,26]$ cm con $300 \times 300$ píxeles (paso $\approx 1.3$ mm en $x$ y $\approx 0.8$ mm en $z$).

---

## 3.5 Validación del Código

Se implementó una suite de 12 pruebas unitarias en `tests/test_simulation.py`. Las pruebas relevantes son:

| Prueba | Verificación |
|---|---|
| `test_frequency_response_phase_single_target` | La fase de $H(f)$ sigue $-4\pi f R/c$ con error $< 10^{-10}$ rad |
| `test_frequency_response_superposition` | Linealidad: $H_\text{total} = H_{T1} + H_{T2}$ |
| `test_scan_shape` | Dimensiones del cubo $H[N_f, N_\text{az}]$ consistentes con la grilla |
| `test_range_profile_peak_location` | Pico de rango dentro de 2 bins del rango verdadero |
| `test_reconstruction_locates_single_target` | Pico de imagen SAR a menos de 2 cm del blanco verdadero |
| `test_reconstruction_two_targets_both_visible` | Amplitud local $> 30\%$ del máximo global en vecindad de cada blanco |
| `test_no_bladerf_imports` | Los módulos de simulación/procesamiento no importan hardware bladeRF |

**Resultado:** 12/12 pruebas aprobadas (commit `31bc9ee`, Python 3.12.5).

---

## 3.6 Resultados

### 3.6.1 Perfiles de rango

> **[Figura 3.1]** `reports/generated/range_profiles.png` — Perfil de rango de la apertura central ($x_\text{az} = 0$) con ventana rectangular (izquierda) y Hanning (derecha). Las líneas discontinuas indican el rango oblicuo (*slant range*) de cada blanco desde el centro de apertura: T1 a 10.8 cm, T2 a 19.9 cm.

Con ventana rectangular, el perfil muestra dos máximos locales claramente separados en torno a los rangos oblicuos esperados, con un mínimo local entre ellos. Con ventana Hanning, los dos máximos se fusionan en un único lóbulo ancho, demostrando el compromiso entre resolución y nivel de lóbulos laterales.

### 3.6.2 Imagen SAR 2D

> **[Figura 3.2]** `reports/generated/sar_window_comparison.png` — Imagen SAR de retroproyección con ventana rectangular (izquierda) y Hanning (derecha), en escala logarítmica con umbral de −25 dB. Las marcas en cian (+) indican las posiciones verdaderas de T1 y T2.

> **[Figura 3.3]** `reports/generated/sar_image.png` — Imagen SAR de mejor resolución (ventana rectangular) en amplitud lineal (izquierda) y dB (derecha).

Con ventana rectangular, ambos blancos aparecen como manchas (*spots*) diferenciadas centradas sobre sus posiciones verdaderas. La separación visual en la imagen es consistente con la resolución de rango teórica de 7.5 cm y con la separación real de 10 cm entre blancos.

Con ventana Hanning, los dos blancos quedan fusionados en un único lóbulo más amplio, confirmando que la separación de 10 cm en rango y 12 cm en azimut es insuficiente para resolución con esta ventana.

### 3.6.3 Resolución de rango verificada

La resolución teórica de rango para un sistema SFCW con ancho de banda $BW$ es:

$$\delta r = \frac{c}{2\,BW} = \frac{3\times10^8\;\text{m/s}}{2 \times 2\times10^9\;\text{Hz}} = 7.5 \;\text{cm}$$

La separación en rango entre T1 ($z=9$ cm) y T2 ($z=19$ cm) es $\Delta z = 10\,\text{cm} > \delta r = 7.5\,\text{cm}$, condición necesaria para la resolución de Rayleigh. La imagen simulada con ventana rectangular confirma esta predicción: los dos blancos son visualmente distinguibles con un mínimo local entre ellos a nivel de imagen.

---

## 3.7 Interpretación y Limitaciones

**Interpretación:** El pipeline de simulación reproduce fielmente el modelo teórico de señal SFCW para una apertura sintética monoestática. La retroproyección con corrección de fase portadora logra enfocar correctamente blancos puntuales en condiciones de campo cercano ($z < $ apertura), lo que valida la cadena de procesamiento para su aplicación posterior con datos reales del bladeRF.

**Limitaciones de esta etapa:**

1. **Modelo de blanco:** Se emplearon reflectores puntuales isótropos con amplitud unitaria. Los blancos reales (objetos dieléctricos, alambres, esferas metálicas) tienen sección transversal radar (RCS) dependiente del ángulo y la frecuencia.
2. **Ruido:** La simulación se realizó sin ruido añadido (`noise_std = 0`). La relación señal-a-ruido (SNR) real dependerá del hardware (ganancia TX/RX, pérdidas de cable, temperatura del receptor).
3. **Canal de propagación:** Se asume espacio libre y medio homogéneo ($\varepsilon_r = 1$). No se modelan reflexiones múltiples, dispersión, ni efectos de la antena (diagrama de radiación, acoplamiento TX-RX).
4. **Resolución en azimut:** La resolución transversal no fue cuantificada analíticamente en esta etapa; se evaluó únicamente la separación transversal de los blancos a nivel visual.
5. **Sin datos hardware:** Todos los resultados corresponden a señal sintética ideal. No se puede garantizar que el comportamiento del bladeRF (no linealidades, fase de LO, jitter de sincronía) sea equivalente.

---

## 3.8 Trabajo Futuro Inmediato

1. ~~Conectar el pipeline de procesamiento existente con capturas reales del bladeRF mediante un cargador de datos (`acquisition/load_sfcw_capture.py`) que lea los archivos `.npy` de `legacy/capturas_barrido/` y los adapte al formato `SyntheticScan[N_f, N_az]`.~~ **[Completado — commit `4fd93a1`. Ver Capítulo 4.]**
2. Implementar substracción de fondo (`processing/background_subtraction.py`) para aislar la respuesta del phantom de las reflexiones estáticas del entorno antes de procesar datos reales.
3. Comparar perfiles de rango simulados versus medidos para un blanco de referencia conocido (p.ej., esfera metálica o alambre).
4. Cuantificar la resolución transversal mediante el ancho a −3 dB del lóbulo principal de un blanco puntual en la imagen SAR real.
5. Evaluar el impacto del ruido real sobre la relación señal-a-ruido de los perfiles de rango.

---

*Fin del Capítulo 3 (borrador de simulación).*
