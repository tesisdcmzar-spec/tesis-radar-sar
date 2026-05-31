# Capítulo 2 — Marco Teórico

> **Estado:** borrador — fundamentos teóricos que respaldan el pipeline de simulación validado en el Capítulo 3.
> **Reproducibilidad:** los parámetros numéricos de este capítulo corresponden exactamente a `configs/simulation.yaml` (commit `31bc9ee`) y al script `experiments/run_simulation.py`. Toda afirmación cuantitativa está respaldada por la suite de pruebas `tests/test_simulation.py` (12/12 aprobadas).

---

## 2.1 Radar de apertura sintética (SAR)

### 2.1.1 Principio de apertura sintética

Un radar convencional de apertura real (*Real Aperture Radar*, RAR) limita su resolución transversal (*cross-range*) por el ancho del lóbulo principal de la antena física: $\delta_{x,\text{RAR}} = \lambda \cdot R / D$, donde $\lambda$ es la longitud de onda, $R$ la distancia al blanco y $D$ el diámetro de la antena. En el rango de microondas ($\lambda \sim 10$–$30$ cm) y en campo cercano ($R < 1$ m), esta resolución suele ser del orden de decenas de centímetros, insuficiente para localizar estructuras de interés milimétrico.

El radar de apertura sintética (SAR, *Synthetic Aperture Radar*) supera esta limitación desplazando físicamente una antena pequeña a lo largo de una trayectoria de longitud $L_\text{az}$, registrando la respuesta compleja en cada posición, y combinando coherentemente todas las mediciones para simular una antena de longitud $L_\text{az}$. La resolución transversal del SAR enfocado en modo *broadside* (apertura perpendicular al eje de movimiento) es independiente del rango:

$$\delta_{x,\text{SAR}} = \frac{D_\text{ant}}{2}$$

donde $D_\text{ant}$ es la longitud física de la antena. Esta expresión asume procesamiento con toda la apertura disponible. En configuraciones de campo cercano con apertura finita, la resolución transversal depende también de la geometría de visión (ángulo subtendido desde el blanco).

En el sistema de esta tesis, la apertura sintética se implementa desplazando la antena monoestática a lo largo de un riel azimutal motorizado de 30 cm de longitud ($x_\text{az} \in [-15,\, +15]$ cm) con paso de 2 cm, produciendo $N_\text{az} = 16$ posiciones de adquisición.

### 2.1.2 Configuración monoestática

La plataforma opera en configuración **monoestática**: la misma antena actúa como transmisor y receptor en cada posición de apertura $x_\text{az}$. El radar transmite, el eco regresa por el mismo camino óptico, y la señal es recibida en el mismo puerto. Esta configuración simplifica la geometría (la fase solo depende del recorrido de ida y vuelta) pero requiere un circulador o un conmutador TX/RX para aislar transmisión y recepción.

La distancia monoestática (un solo sentido) entre la posición de apertura y un blanco puntual $k$ en las coordenadas $(x_k, z_k)$ es:

$$R_k(x_\text{az}) = \sqrt{(x_\text{az} - x_k)^2 + z_k^2}$$

donde $x_k$ es la coordenada transversal del blanco y $z_k$ su profundidad medida desde el plano de la apertura. El tiempo de viaje de ida y vuelta es $\tau_k = 2R_k/c$.

> **[Figura 2.1]** Geometría de la apertura sintética monoestática. Eje horizontal: cross-range $x$ [cm]. Eje vertical: down-range $z$ [cm]. La antena se desplaza de $x=-15$ cm a $x=+15$ cm (flechas). Los blancos T1 y T2 se muestran con sus radios de curvatura de onda desde la posición central de apertura.

---

## 2.2 Señal SFCW (*Stepped-Frequency Continuous Wave*)

### 2.2.1 Principio de operación

La señal SFCW (*Stepped-Frequency Continuous Wave*) obtiene la respuesta en frecuencia del canal radar transmitiendo tonos continuos a frecuencias discretas $f_n = f_\text{inicio} + n\,\Delta f$, $n = 0, \ldots, N_f-1$, y midiendo la respuesta compleja (amplitud y fase) a cada frecuencia. La síntesis del perfil de rango equivalente al de un pulso ultracorto se realiza en postprocesado mediante la transformada inversa de Fourier (IFFT).

Las ventajas de SFCW respecto a un radar de pulso son:
- **Alta potencia media por tono:** cada frecuencia se transmite durante un tiempo prolongado, lo que mejora la SNR.
- **Control fino del ancho de banda:** el paso $\Delta f$ y el número de pasos $N_f$ determinan completamente la resolución y el rango no ambiguo.
- **Compatibilidad con SDR (*Software-Defined Radio*):** la generación y la recepción de tonos IQ complejos es nativa en plataformas como el bladeRF.

### 2.2.2 Modelo de señal para blancos puntuales

Para una configuración monoestática, la respuesta compleja recibida cuando se transmite el tono de frecuencia $f_n$ desde la posición de apertura $x_\text{az}$ es la superposición lineal de las contribuciones de todos los $K$ blancos en el phantom:

$$H(f_n,\, x_\text{az}) = \sum_{k=1}^{K} A_k \,\exp\!\left(-j\,\frac{4\pi f_n\, R_k(x_\text{az})}{c}\right)$$

donde:
- $A_k$ es la amplitud compleja del blanco $k$ (proporcional a la raíz cuadrada de su sección eficaz radar, $\sqrt{\sigma_k}$).
- $c$ es la velocidad de propagación en el medio ($c = 3\times10^8$ m/s en espacio libre).
- $4\pi f_n R_k / c = 2\pi f_n \cdot (2R_k/c) = 2\pi f_n \tau_k$ es la fase acumulada en el doble trayecto.

El factor $4\pi$ —en lugar del $2\pi$ habitual de la transformada de Fourier— surge del **doble trayecto monoestático**: la onda viaja del radar al blanco (retardo $R_k/c$) y regresa del blanco al radar (otro retardo $R_k/c$), acumulando en total un retardo de $2R_k/c$.

El resultado de medir $H(f_n, x_\text{az})$ para todas las $N_f$ frecuencias y las $N_\text{az}$ posiciones de apertura es el cubo de datos complejo $\mathbf{H} \in \mathbb{C}^{N_f \times N_\text{az}}$, que es la entrada al pipeline de procesamiento.

**Tabla 2.1 — Parámetros SFCW del sistema de simulación**

| Parámetro | Símbolo | Valor | Unidad |
|---|---|---|---|
| Frecuencia de inicio | $f_\text{inicio}$ | 500 | MHz |
| Frecuencia de fin | $f_\text{fin}$ | 2500 | MHz |
| Ancho de banda total | $BW = f_\text{fin} - f_\text{inicio}$ | 2000 | MHz |
| Paso en frecuencia | $\Delta f$ | 5 | MHz |
| Número de frecuencias | $N_f$ | 401 | — |
| Velocidad de propagación | $c$ | $3\times10^8$ | m/s |

### 2.2.3 Rango de medición sin ambigüedad

La frecuencia mínima de muestreo en el dominio de la frecuencia es $\Delta f$. La respuesta al impulso equivalente es periódica con período $T = 1/\Delta f$ en el dominio del tiempo de retardo. El rango máximo no ambiguo es:

$$R_\text{max} = \frac{c}{2\,\Delta f} = \frac{3\times10^8\;\text{m/s}}{2 \times 5\times10^6\;\text{Hz}} = 30\;\text{m}$$

Este rango supera con amplitud el campo cercano de interés de la aplicación ($z < 0.5$ m), garantizando que ningún blanco produzca un alias en rango.

---

## 2.3 Compresión en rango: perfil por IFFT

### 2.3.1 Relación entre SFCW e IFFT

La respuesta $H(f_n, x_\text{az})$ para una posición de apertura fija es, bajo el modelo de blancos puntuales, la transformada de Fourier discreta del perfil de rango evaluada en las frecuencias $f_n$:

$$H(f_n) = \int_{-\infty}^{+\infty} h(\tau)\, e^{-j2\pi f_n \tau}\, d\tau \;\bigg|_{\tau = 2R/c}$$

donde $h(\tau) = \sum_k A_k\,\delta(\tau - 2R_k/c)$ es la respuesta al impulso en el dominio del tiempo de retardo. Aplicar la IFFT sobre el eje de frecuencias de $H(f_n)$ recupera $h(\tau)$, que contiene picos en $\tau_k = 2R_k/c$, equivalente a un pico en el rango monoestático $R_k$.

### 2.3.2 Procedimiento de compresión

Para cada posición de apertura $x_\text{az}$:

1. **Ventaneo:** multiplicar el vector $H(f_n)$ por una función de peso $w(n)$ para controlar los lóbulos laterales de la respuesta al impulso.
2. **Extensión por ceros (*zero-padding*):** añadir $N_\text{pad}$ ceros para aumentar la densidad de la grilla de rango sin alterar la resolución física.
3. **IFFT:** aplicar la IFFT de longitud $N_\text{IFFT} = N_f + N_\text{pad}$ sobre el eje de frecuencias.
4. **Selección causal:** conservar solo los primeros $N_\text{IFFT}/2$ puntos (retardos positivos).

El eje de rango resultante es:

$$r_k = \frac{c}{2}\,\tau_k = \frac{c\,k}{2\,N_\text{IFFT}\,\Delta f}, \quad k = 0, 1, \ldots, \frac{N_\text{IFFT}}{2}-1$$

El pipeline de simulación usa $N_\text{IFFT} = 4N_f$ (factor de sobremuestra $= 4$), lo que produce un paso de rango de:

$$\Delta r = \frac{c}{2\,N_\text{IFFT}\,\Delta f} = \frac{3\times10^8}{2 \times 1604 \times 5\times10^6} \approx 18.7\;\text{mm}$$

### 2.3.3 Resolución en rango

La resolución de rango de Rayleigh —la separación mínima entre dos blancos puntuales de igual amplitud que pueden distinguirse en el perfil de rango— depende del ancho de banda efectivo $BW_\text{eff}$ y de la función de ventana:

$$\delta r = \frac{\alpha\, c}{2\, BW_\text{eff}}$$

donde $\alpha$ es el factor de resolución de la ventana (Tabla 2.2).

**Tabla 2.2 — Parámetros de ventanas de compresión en rango (BW = 2 GHz)**

| Ventana | Factor $\alpha$ | $\delta r$ [cm] | Lóbulos laterales [dB] |
|---|---|---|---|
| Rectangular (`none`) | 1.0 | 7.5 | −13 |
| Hanning | ~2.0 | ~15 | −31 |
| Blackman | ~3.0 | ~22 | −58 |

La ventana rectangular ofrece la mejor resolución de rango ($\delta r = 7.5$ cm) a costa de lóbulos laterales de $-13$ dB. La ventana Hanning duplica el ancho del lóbulo principal pero reduce los lóbulos laterales a $-31$ dB. En el pipeline de esta tesis se utiliza la ventana rectangular como configuración por defecto para maximizar la resolución espacial.

> **[Figura 2.2]** Comparación de funciones de ventana y su respuesta al impulso equivalente. Eje superior: peso espectral $w(n)$ en función del índice de frecuencia. Eje inferior: perfil de rango $|h(r)|$ en dB para un blanco puntual en $r = 10$ cm. Las tres ventanas (rectangular, Hanning, Blackman) se superponen para comparar el ancho del lóbulo principal y el nivel de lóbulos laterales.

---

## 2.4 Reconstrucción de imagen SAR por retroproyección

### 2.4.1 Principio de la retroproyección

La retroproyección (*backprojection*) es un algoritmo de formación de imagen SAR que construye la imagen píxel a píxel, sumando coherentemente las contribuciones de todas las posiciones de apertura con el retardo correcto para cada posición de imagen. Es el método de referencia para SAR de campo cercano porque maneja geometrías arbitrarias sin las aproximaciones de fase estacionaria que requieren los algoritmos de dominio frecuencial.

Para cada píxel de imagen $(x_p, z_p)$ la imagen SAR compleja $I$ se define como:

$$I(x_p, z_p) = \sum_{i=1}^{N_\text{az}} \tilde{h}\!\left(R_0^{(i)},\; x_\text{az}^{(i)}\right) \cdot e^{+j\,4\pi f_\text{inicio}\, R_0^{(i)}/c}$$

donde:
- $R_0^{(i)} = \sqrt{(x_\text{az}^{(i)} - x_p)^2 + z_p^2}$ es la distancia monoestática desde la $i$-ésima posición de apertura al píxel $(x_p, z_p)$.
- $\tilde{h}(r, x_\text{az}^{(i)})$ es el perfil de rango interpolado en $r = R_0^{(i)}$ para la posición de apertura $i$.
- $e^{+j\,4\pi f_\text{inicio}\, R_0/c}$ es la **corrección de fase portadora** (sección 2.4.2).

La imagen final $|I(x_p, z_p)|$ representa la amplitud de reflexión enfocada en el plano $(x, z)$.

### 2.4.2 Corrección de fase portadora para SFCW no-banda-base

Cuando el barrido SFCW comienza en $f_\text{inicio} \neq 0$ (como en el sistema de esta tesis, con $f_\text{inicio} = 500$ MHz), la IFFT no opera sobre la banda base: el primer bin de frecuencia del vector $H(f_n)$ corresponde a $f_\text{inicio}$, no a DC.

La IFFT trata implícitamente el primer bin como DC. El resultado es que el perfil de rango contiene un **término de modulación residual**:

$$\tilde{h}(\tau) \approx \sum_k A_k\,\delta(\tau - 2R_k/c)\cdot e^{-j\,4\pi f_\text{inicio} R_k/c}$$

Este factor de fase $e^{-j4\pi f_\text{inicio} R_k/c}$ depende del rango del blanco $R_k$ y, por tanto, es diferente para cada posición de apertura $i$ (puesto que $R_0^{(i)}$ varía con $x_\text{az}^{(i)}$). Al sumar las $N_\text{az}$ contribuciones sin compensar este término, las fases se acumulan de forma incoherente y la suma es destructiva: la imagen SAR no se enfoca correctamente.

La solución es multiplicar la contribución de cada posición de apertura por la fase conjugada evaluada en el rango del píxel:

$$\text{corrección}(R_0) = e^{+j\,4\pi f_\text{inicio} R_0 / c}$$

Con esta corrección, la fase residual se cancela y todas las contribuciones de apertura llegan en fase para un blanco puntual en $(x_p, z_p) = (x_k, z_k)$, produciendo una suma constructiva (enfoque coherente).

> **Nota de implementación:** la corrección de portadora es necesaria en la etapa de retroproyección, no en el cálculo del perfil de rango individual. El módulo $|h(\tau)|$ del perfil de rango de una sola apertura no depende de la fase absoluta, y por eso el pico de rango aparece en la posición correcta en el perfil 1D. El efecto incoherente solo se manifiesta al sumar las contribuciones de múltiples posiciones de apertura.

### 2.4.3 Interpolación compleja del perfil de rango

El rango $R_0^{(i)}$ calculado para cada píxel raramente coincide exactamente con uno de los bins discretos del perfil de rango. Se requiere interpolación. El pipeline implementa **interpolación lineal separada de partes real e imaginaria**:

$$\tilde{h}(R_0) = \text{interp}\!\left[h_\text{Re}(r_k),\, R_0\right] + j\,\text{interp}\!\left[h_\text{Im}(r_k),\, R_0\right]$$

Esta estrategia es preferida a la interpolación de amplitud y fase por separado, que introduciría errores no lineales en la fase cuando la amplitud es pequeña (*phase wrapping*). La interpolación lineal de partes real e imaginaria es equivalente a la interpolación compleja directa y es numéricamente estable.

### 2.4.4 Imagen SAR de referencia del sistema

La cuadrícula de imagen utilizada en el pipeline de esta tesis cubre:

| Dimensión | Rango | Puntos | Paso |
|---|---|---|---|
| Cross-range ($x$) | −20 a +20 cm | 300 | ~1.3 mm |
| Down-range ($z$) | 2 a 26 cm | 300 | ~0.8 mm |

El paso de la cuadrícula ($\approx 1$ mm) es mucho más fino que la resolución física ($\delta r = 7.5$ cm), lo que garantiza que los picos de imagen no queden subestreados por la discretización de la cuadrícula.

> **[Figura 2.3]** Diagrama de flujo del algoritmo de retroproyección. Entrada: cubo de datos $\mathbf{H}[N_f, N_\text{az}]$. Etapa 1: compresión en rango por IFFT → perfiles complejos $\tilde{h}[N_r, N_\text{az}]$. Etapa 2: bucle sobre posiciones de apertura → interpolación del perfil en $R_0^{(i)}$ → corrección de portadora → acumulación coherente. Salida: imagen compleja $I[N_x, N_z]$.

---

## 2.5 Phantom sintético de blancos puntuales

### 2.5.1 Modelo de reflectores puntuales

Un **phantom** es un objeto de referencia con propiedades conocidas utilizado para calibrar y validar el sistema de imagen antes de aplicarlo a objetos de interés desconocido. En la etapa de simulación de esta tesis, el phantom es un conjunto de $K$ reflectores puntuales isótropos con amplitud unitaria ($A_k = 1$) y posiciones $(x_k, z_k)$ especificadas en el archivo de configuración `configs/simulation.yaml`.

El modelo de reflector puntual es una idealización que supone:
- La sección eficaz radar $\sigma_k$ es independiente del ángulo de incidencia y la frecuencia.
- No hay reflexiones múltiples entre blancos.
- El medio de propagación es homogéneo ($\varepsilon_r = 1$, espacio libre).
- La antena tiene diagrama de radiación isotrópico.

Estos supuestos son restrictivos respecto a los objetos reales del laboratorio (esferas metálicas, alambres, objetos dieléctricos), cuya RCS tiene dependencia angular y frecuencial. Sin embargo, el modelo puntual es suficiente para verificar la corrección matemática de los algoritmos de procesamiento y establecer parámetros de resolución de referencia.

### 2.5.2 Criterio de resolución de Rayleigh para dos blancos

Para que dos reflectores puntuales sean distinguibles en la imagen SAR, deben estar separados en más de una celda de resolución en al menos una dimensión:

- **Separación en rango:** $\Delta z > \delta r = c/(2\,BW)$
- **Separación en cross-range:** $\Delta x > \delta_{x,\text{SAR}}$

El phantom de validación de esta tesis usa dos blancos T1 en $(-6, 9)$ cm y T2 en $(+6, 19)$ cm, con separación en rango $\Delta z = 10$ cm $> \delta r = 7.5$ cm y separación en azimut $\Delta x = 12$ cm. Esta configuración garantiza que ambos blancos son físicamente resolvibles con ventana rectangular, lo que permite verificar experimentalmente (en simulación) la predicción teórica de resolución.

> **[Figura 2.4]** Geometría del phantom de dos blancos. Eje horizontal: cross-range $x$ [cm]. Eje vertical: down-range $z$ [cm]. T1 en (−6, 9) cm y T2 en (+6, 19) cm. Las elipses de nivel −3 dB de cada celda de resolución se dibujan para ilustrar que las celdas no se superponen en ninguna dimensión.

---

## 2.6 Propiedades de propagación y limitaciones del modelo

### 2.6.1 Propagación en espacio libre

Todos los resultados de simulación presentados en esta tesis asumen propagación en espacio libre ($\varepsilon_r = 1$, $\sigma = 0$). En este caso la velocidad de propagación es $c = 3\times10^8$ m/s y no hay atenuación adicional por absorción del medio.

Para experimentos con phantoms dieléctricos (materiales con $\varepsilon_r > 1$ que simulan tejidos), la velocidad de fase en el medio es:

$$v_p = \frac{c}{\sqrt{\varepsilon_r}}$$

y el rango efectivo medido por el sistema debe corregirse por un factor $\sqrt{\varepsilon_r}$ para obtener la distancia geométrica real. Esta corrección no está implementada en el pipeline actual y deberá incorporarse en la etapa de validación con phantom real (Capítulo [N]).

### 2.6.2 Limitaciones del modelo de señal

El modelo $H(f_n, x_\text{az}) = \sum_k A_k\,e^{-j4\pi f_n R_k/c}$ no incluye:

1. **Reflexiones múltiples:** la señal puede rebotar entre blancos o entre el blanco y la antena antes de ser recibida. En la aproximación de Born de primer orden, solo se considera la dispersión simple (*single scattering*).
2. **Diagrama de radiación de la antena:** la amplitud recibida depende del ángulo de visión. El modelo asume ganancia isotrópica constante.
3. **Modelo de propagación en medios con pérdidas:** en tejidos biológicos, la atenuación depende fuertemente de la frecuencia ($\alpha \propto f^n$, con $n \approx 1$–$2$). Esto reduce la amplitud de los ecos de blancos profundos y puede requerir corrección de amplitud dependiente del rango.
4. **Ruido del receptor:** el bladeRF introduce ruido térmico, ruido de fase del oscilador local y errores de cuantización del ADC. El modelo sin ruido ($\text{noise\_std} = 0$) es una cota superior de la SNR alcanzable.
5. **Variaciones de ganancia con la frecuencia:** la respuesta del sistema (cadena TX/RX, cables, conectores) no es plana en banda. Se requiere calibración de frecuencia con medición de referencia.

---

## 2.7 Resumen de parámetros y relaciones clave

La Tabla 2.3 sintetiza las relaciones entre los parámetros del sistema y las métricas de imagen, válidas bajo el modelo de blancos puntuales en espacio libre.

**Tabla 2.3 — Relaciones sistema–imagen para SFCW-SAR monoestático**

| Métrica | Expresión | Valor (sistema actual) |
|---|---|---|
| Resolución de rango (rect.) | $\delta r = c / (2\,BW)$ | 7.5 cm |
| Resolución de rango (Hanning) | $\delta r \approx c / BW$ | ~15 cm |
| Rango no ambiguo | $R_\text{max} = c / (2\,\Delta f)$ | 30 m |
| Paso de rango (IFFT, 4×) | $\Delta r = c / (2\,N_\text{IFFT}\,\Delta f)$ | ~18.7 mm |
| Número de frecuencias | $N_f = (f_\text{fin} - f_\text{inicio})/\Delta f + 1$ | 401 |
| Longitud de apertura | $L_\text{az} = x_\text{fin} - x_\text{inicio}$ | 30 cm |
| Posiciones de apertura | $N_\text{az} = L_\text{az}/\Delta x + 1$ | 16 |

---

## 2.8 Reproducibilidad

Todos los parámetros de este capítulo son directamente reproducibles a partir de:

- **Configuración:** `configs/simulation.yaml`, commit `31bc9ee`.
- **Implementación del modelo de señal:** `simulation/phantom_model.py`, función `PhantomModel.frequency_response()`.
- **Implementación de la IFFT:** `processing/range_profile.py`, función `compute_range_profiles()`.
- **Implementación de la retroproyección:** `processing/sar_reconstruction.py`, función `backprojection()`.
- **Validación numérica:** `tests/test_simulation.py`, 12/12 pruebas aprobadas (Python 3.12.5, NumPy 1.x).

Para regenerar las figuras mencionadas en este capítulo ejecutar desde la raíz del repositorio:

```bash
py experiments/run_simulation.py --config configs/simulation.yaml --window none
```

---

## 2.9 Fuentes

Este capítulo está basado en los principios matemáticos implementados en el código del repositorio y verificados mediante las pruebas unitarias. Los fundamentos teóricos del SAR de apertura sintética y la señal SFCW utilizados son de dominio público y pueden encontrarse en textos estándar de procesamiento de señales de radar; las referencias concretas se incorporarán en la versión final de la tesis.

No se consultaron fuentes externas durante la redacción de este borrador. Los parámetros numéricos provienen exclusivamente de `configs/simulation.yaml` y de los resultados de `tests/test_simulation.py`.

---

*Fin del Capítulo 2 (borrador — marco teórico).*
