# Informe Retrospectivo de Ingeniería — Pipeline de Simulación SAR, Mejora de Resolución y Borrador de Tesis

**Fecha de sesiones:** 30 de mayo de 2026  
**Commits cubiertos:** `eb75b1e`, `232ef92`, `31bc9ee`, `2ce6cfe`  
**Autor:** matambrito (asistido por Claude Sonnet 4.6)  
**Estado del pipeline:** validado, 12/12 pruebas aprobadas, sin acceso a hardware  

---

## Tabla de Contenidos

1. [Contexto y objetivo de las sesiones](#1-contexto-y-objetivo-de-las-sesiones)
2. [Arquitectura del pipeline de simulación](#2-arquitectura-del-pipeline-de-simulacion)
3. [Por qué la simulación antes del hardware bladeRF](#3-por-qué-la-simulación-antes-del-hardware-bladerf)
4. [Modelo de señal: generación de H(f, x_az)](#4-modelo-de-señal-generación-de-hf-xaz)
5. [El factor de doble trayecto en la fase](#5-el-factor-de-doble-trayecto-en-la-fase)
6. [Perfiles de rango por IFFT](#6-perfiles-de-rango-por-ifft)
7. [Algoritmo de retroproyección SAR](#7-algoritmo-de-retroproyección-sar)
8. [Corrección de fase portadora para SFCW no-banda-base](#8-corrección-de-fase-portadora-para-sfcw-no-banda-base)
9. [Bugs de conversión YAML/cadena y sus correcciones](#9-bugs-de-conversión-yamlcadena-y-sus-correcciones)
10. [Problema de codificación del terminal Windows](#10-problema-de-codificación-del-terminal-windows)
11. [Por qué la ventana Hanning fusionaba los blancos](#11-por-qué-la-ventana-hanning-fusionaba-los-blancos)
12. [Por qué la ventana rectangular mejoró la resolución](#12-por-qué-la-ventana-rectangular-mejoró-la-resolución)
13. [Por qué la configuración inicial de dos blancos no era físicamente resoluble](#13-por-qué-la-configuración-inicial-de-dos-blancos-no-era-físicamente-resoluble)
14. [Separación de blancos en simulation.yaml](#14-separación-de-blancos-en-simulationyaml)
15. [Figuras generadas e interpretación](#15-figuras-generadas-e-interpretación)
16. [Suite de pruebas: resultados y cobertura](#16-suite-de-pruebas-resultados-y-cobertura)
17. [Contenido de thesis/cap3_simulacion.md](#17-contenido-de-thesiscap3_simulacionmd)
18. [Cómo este trabajo apoya la tesis](#18-cómo-este-trabajo-apoya-la-tesis)
19. [Limitaciones conocidas](#19-limitaciones-conocidas)
20. [Próximo paso exacto: acquisition/load_sfcw_capture.py](#20-próximo-paso-exacto-acquisitionload_sfcw_capturepy)

---

## 1. Contexto y objetivo de las sesiones

El proyecto de tesis construye una plataforma experimental de radar SAR (Synthetic Aperture Radar) de microondas basada en el SDR bladeRF. La plataforma realizará barridos SFCW (*Stepped-Frequency Continuous Wave*) con movimiento azimutal motorizado para obtener imágenes 2D de contraste dieléctrico en objetos de laboratorio (*phantoms*).

Las sesiones del 30 de mayo de 2026 corresponden a la **Fase 1 del roadmap**: construir un pipeline completamente independiente del hardware que:

- Modele matemáticamente la señal SFCW de un phantom sintético.
- Procese esa señal para obtener perfiles de rango e imagen SAR.
- Valide la cadena con 12 pruebas unitarias automatizadas.
- Genere figuras reproducibles para la tesis.
- Produzca el borrador del Capítulo 3 de la tesis.

No se realizó ninguna acción sobre el hardware (bladeRF, motores, antenas) en estas sesiones.

---

## 2. Arquitectura del pipeline de simulación

La sesión creó o modificó los siguientes archivos de código (en el orden lógico de la cadena de datos):

```
configs/simulation.yaml
    └─ phantom_from_config()  ──►  simulation/phantom_model.py   (PhantomModel, PointTarget)
    └─ scan_from_config()     ──►  simulation/synthetic_scan.py   (SyntheticScan, make_scan)
                                       │  H[N_f, N_az]
                                       ▼
                              processing/range_profile.py         (compute_range_profiles)
                                       │  profiles[N_range, N_az]
                                       ▼
                              processing/sar_reconstruction.py    (backprojection)
                                       │  img[N_x, N_z]
                                       ▼
                              experiments/run_simulation.py       (script principal)
                                       │
                                       ▼
                              reports/generated/
                                  range_profiles.png
                                  sar_window_comparison.png
                                  sar_image.png
```

El flujo completo es ejecutado por `experiments/run_simulation.py`, que también acepta argumentos de línea de comandos (`--config`, `--noise`, `--window`) para experimentación sin modificar el código.

---

## 3. Por qué la simulación antes del hardware bladeRF

Operar el bladeRF antes de validar el algoritmo introduce un riesgo metodológico grave: si la imagen SAR no muestra los blancos esperados, no se puede saber si el error está en el hardware (calibración, ganancia, sincronía de fase), en la adquisición (formato de datos, frecuencias), o en el procesamiento (IFFT, retroproyección). La simulación permite aislar completamente el algoritmo:

| Riesgo en hardware directo | Mitigación por simulación |
|---|---|
| Ruido real de RF enmascarando errores | Señal sintética sin ruido — errores de fase son visibles directamente |
| Bug de adquisición vs. bug de procesamiento | El modelo sintético es la fuente de verdad |
| Tiempo de setup hardware (>30 min) | Pipeline simulado corre en segundos |
| Daño accidental al equipo | Sin riesgo: sin RF, sin movimiento mecánico |
| Resultados no reproducibles | Config en YAML + semilla aleatoria fija → resultados bit-a-bit reproducibles |

Adicionalmente, la tesis exige una sección de validación matemática antes de presentar resultados experimentales. La Fase 1 genera esa sección (Capítulo 3).

---

## 4. Modelo de señal: generación de H(f, x_az)

### 4.1 Geometría

Se modela una apertura sintética monoestática en el eje $x$ (dimensión transversal). Cada posición de apertura $x_\text{az}$ actúa como transmisor y receptor simultáneamente. El phantom contiene $K$ blancos puntuales, cada uno en coordenadas $(x_k, z_k)$, donde $z_k$ es la profundidad (*down-range*) medida desde el plano de apertura.

La distancia monoestática (un sentido) entre la posición de apertura y el blanco $k$ es:

$$R_k(x_\text{az}) = \sqrt{(x_\text{az} - x_k)^2 + z_k^2}$$

### 4.2 Respuesta en frecuencia

Para una señal SFCW con frecuencias $f_n = f_\text{inicio} + n\,\Delta f$, $n = 0,\ldots,N_f-1$, la respuesta compleja recibida de todos los blancos en la posición de apertura $x_\text{az}$ es la superposición lineal:

$$H(f_n,\, x_\text{az}) = \sum_{k=1}^{K} A_k \,\exp\!\left(-j\,\frac{4\pi f_n\, R_k(x_\text{az})}{c}\right)$$

donde $A_k$ es la amplitud relativa del blanco (RCS normalizado) y $c = 3\times10^8$ m/s.

### 4.3 Implementación en `phantom_model.py`

```python
# simulation/phantom_model.py  (líneas 55-66)
for t in self.targets:
    R = np.sqrt((x_az - t.x_m) ** 2 + t.z_m ** 2)   # (N_az,)
    phase = -4 * np.pi * np.outer(freqs_hz, R) / self.c  # (N_f, N_az)
    H += t.amplitude * np.exp(1j * phase)
```

`np.outer(freqs_hz, R)` construye la matriz de fase $(N_f \times N_\text{az})$ en una operación vectorizada, evitando bucles dobles. El resultado `H` tiene forma `(N_f, N_az)` y tipo `complex128`.

---

## 5. El factor de doble trayecto en la fase

El factor $4\pi$ en la expresión de fase —en lugar del $2\pi$ habitual de la transformada de Fourier— se origina en el modelo monoestático de radar:

- La onda electromagnética viaja desde el radar hasta el blanco: retardo de fase $= 2\pi f \cdot (R/c)$.
- La onda reflejada viaja de vuelta desde el blanco hasta el radar: otro retardo de fase $= 2\pi f \cdot (R/c)$.
- **Total (doble trayecto):** $2 \times 2\pi f \cdot (R/c) = 4\pi f R/c$.

En términos de tiempo: el retardo total es $\tau = 2R/c$ (ida y vuelta), y la fase es $-2\pi f \cdot \tau = -4\pi f R/c$.

Este factor es fundamental. Si se usara $2\pi$ en lugar de $4\pi$, la IFFT produciría picos al doble del rango real, y la corrección de fase portadora sería incorrecta.

---

## 6. Perfiles de rango por IFFT

### 6.1 Principio

Para cada posición de apertura $x_\text{az}$, se tiene el vector complejo $H(f_n, x_\text{az})$ con $N_f$ puntos en frecuencia. Este vector es la respuesta en frecuencia de un sistema cuya respuesta al impulso en el dominio del tiempo de retardo es una suma de deltas en $\tau_k = 2R_k/c$.

Aplicar la IFFT sobre el eje de frecuencias convierte el dominio frecuencial al dominio del tiempo de retardo (equivalente al dominio del rango):

$$h[\tau_n,\, x_\text{az}] = \text{IFFT}\{w(f)\cdot H(f,\, x_\text{az})\}$$

donde $w(f)$ es una función de ventana aplicada antes de la IFFT para controlar los lóbulos laterales.

### 6.2 Eje de rango

Con $N_\text{IFFT} = \text{padding\_factor} \times N_f = 4 \times 401 = 1604$ puntos y paso frecuencial $\Delta f = 5$ MHz:

$$r_n = \frac{c \cdot n}{2\, N_\text{IFFT}\, \Delta f}$$

El paso de rango resultante es $\Delta r = c/(2\, N_\text{IFFT}\, \Delta f) = 3\times10^8/(2\times1604\times5\times10^6) \approx 18.7$ mm. Solo se conserva la mitad causal (retardos positivos), es decir, `h[:N_fft//2, :]`.

### 6.3 Implementación en `range_profile.py`

```python
# processing/range_profile.py  (líneas 46-66)
N_f  = len(scan.freqs_hz)
N_fft = N_f * padding_factor          # 401 * 4 = 1604

w = win_fn(N_f)
H = scan.H * w[:, None]               # ventana por columna

h = np.fft.ifft(H, n=N_fft, axis=0)  # IFFT sobre eje de frecuencias
h = h[: N_fft // 2, :]               # mitad causal

df  = scan.f_step_hz
tau = np.arange(N_fft // 2) / (N_fft * df)
range_m = c * tau / 2.0               # rango monoestático
```

El factor `axis=0` es crítico: la IFFT se aplica sobre el eje de frecuencias (filas), no sobre el eje azimutal (columnas).

---

## 7. Algoritmo de retroproyección SAR

### 7.1 Principio

La retroproyección (*backprojection*) es el algoritmo de referencia para formación de imagen SAR. Para cada píxel de imagen $(x_p, z_p)$:

1. Se calcula la distancia monoestática $R_0(x_\text{az}) = \sqrt{(x_\text{az}-x_p)^2 + z_p^2}$ desde cada posición de apertura.
2. Se interpola el perfil de rango complejo `prof(r, x_az)` en el valor $r = R_0(x_\text{az})$.
3. Se acumula coherentemente (suma compleja) sobre todas las posiciones de apertura.

$$I(x_p, z_p) = \sum_{x_\text{az}} \tilde{h}(R_0(x_\text{az}),\, x_\text{az}) \cdot e^{+j\,4\pi f_\text{inicio} R_0/c}$$

La exponencial final es la corrección de fase portadora (sección 8).

### 7.2 Implementación en `sar_reconstruction.py`

```python
# processing/sar_reconstruction.py  (líneas 59-68)
for i_az, x_ap in enumerate(scan.x_az_m):
    prof   = profiles[:, i_az]                         # perfil complejo
    R      = np.sqrt((x_ap - XX)**2 + ZZ**2)          # rango a cada píxel
    R_flat = R.ravel()
    real_part = np.interp(R_flat, range_m, prof.real)
    imag_part = np.interp(R_flat, range_m, prof.imag)
    carrier = np.exp(1j * 4 * np.pi * f_start * R / c)
    img += ((real_part + 1j*imag_part).reshape(N_x, N_z)) * carrier
```

La interpolación lineal de parte real e imaginaria por separado es equivalente a la interpolación compleja y evita artefactos de fase que aparecerían si se interpolara la amplitud y la fase por separado.

### 7.3 Cuadrícula de imagen

La cuadrícula de imagen cubre:
- Cross-range: $x \in [-20,\, +20]$ cm, 300 puntos → paso $\approx 1.3$ mm
- Down-range: $z \in [2,\, 26]$ cm, 300 puntos → paso $\approx 0.8$ mm

Esta resolución de cuadrícula es mucho más fina que la resolución física del sistema ($\delta r = 7.5$ cm), lo que garantiza que los picos de imagen no queden subestreados por la discretización de la cuadrícula.

---

## 8. Corrección de fase portadora para SFCW no-banda-base

### 8.1 El problema

El barrido SFCW no comienza en DC sino en $f_\text{inicio} = 500$ MHz. La IFFT de $H(f_n)$ trata el primer bin de frecuencia como si fuera DC. El resultado es que el perfil de rango contiene un factor de modulación residual:

$$h(\tau) \approx \delta(\tau - 2R/c) \cdot e^{-j\,4\pi f_\text{inicio} R/c}$$

Este término de fase depende del rango $R$ y varía de pixel a pixel. Al sumar coherentemente las contribuciones de las $N_\text{az} = 16$ posiciones de apertura en la retroproyección, las fases son incoherentes entre posiciones y la suma destructiva impide el enfoque correcto: el pico aparecía en $z = 7.4$ cm en lugar de $z = 10$ cm.

### 8.2 La corrección

Antes de acumular la contribución de cada posición de apertura, se multiplica por el factor conjugado de la portadora evaluado en el rango del píxel:

$$\text{corrección}(R) = e^{+j\,4\pi f_\text{inicio} R / c}$$

Esto cancela exactamente el término residual, re-referenciando la fase al inicio del barrido. Después de la corrección, todas las contribuciones de apertura tienen la misma fase para un blanco puntual y la suma es constructiva.

### 8.3 Por qué es necesaria solo en retroproyección y no en el perfil de rango

El perfil de rango 1D (por apertura) sí muestra el pico en el rango correcto, porque el módulo `|h(tau)|` no depende de la fase absoluta. El problema surge en la suma coherente multi-apertura de la retroproyección, donde las fases deben alinearse entre posiciones para que la suma sea constructiva.

---

## 9. Bugs de conversión YAML/cadena y sus correcciones

### 9.1 Descripción del bug

PyYAML en la instalación de Windows (Python 3.12.5) interpreta valores en notación científica como cadenas de texto cuando aparecen en ciertos contextos YAML. Por ejemplo:

```yaml
f_start_hz: 500.0e6   # PyYAML lo lee como str '500.0e6' en lugar de float 5e8
speed_of_light: 3.0e8  # ídem
```

Al intentar usar estos valores en operaciones aritméticas de NumPy (`np.outer(freqs_hz, R) / self.c`), Python lanzaba `TypeError: unsupported operand type(s) for /: 'str' and 'float'`.

### 9.2 La corrección

En todas las funciones que leen valores del diccionario de configuración YAML, se aplicaron conversiones explícitas de tipo:

```python
# simulation/phantom_model.py
c = float(cfg["reconstruction"].get("speed_of_light", 3e8))

# simulation/synthetic_scan.py
f_start_hz = float(sfcw["f_start_hz"])
f_stop_hz  = float(sfcw["f_stop_hz"])
f_step_hz  = float(sfcw["f_step_hz"])

# experiments/run_simulation.py
pad = int(cfg["reconstruction"]["range_padding"])
c   = float(cfg["reconstruction"]["speed_of_light"])
```

Esta conversión explícita es necesaria en cualquier punto donde un valor numérico proviene de YAML y se usa en cálculos, independientemente de cómo esté escrito en el archivo `.yaml`.

---

## 10. Problema de codificación del terminal Windows

### 10.1 Descripción

La consola de Windows (CP1252 / CP850) no puede codificar caracteres Unicode como flechas (`→`, `►`) ni símbolos matemáticos especiales. Al ejecutar `experiments/run_simulation.py`, Python lanzaba:

```
UnicodeEncodeError: 'charmap' codec can't encode character '→' in position N
```

### 10.2 La corrección

Se reemplazaron todos los caracteres Unicode en los f-strings de `print()` por equivalentes ASCII:

```python
# Antes (causaba error en Windows):
print(f"  f = {f0/1e6:.0f}–{f1/1e6:.0f} MHz  BW={BW:.2f} GHz")

# Después (compatible con CP1252):
print(f"  f = {f0/1e6:.0f}-{f1/1e6:.0f} MHz  BW={BW:.2f} GHz")
```

La corrección afectó únicamente a mensajes de consola; no modificó la lógica del algoritmo ni los datos. Las figuras de Matplotlib no tuvieron este problema porque usan su propio sistema de renderizado de texto.

---

## 11. Por qué la ventana Hanning fusionaba los blancos

La ventana Hanning multiplica el vector de frecuencias por una función de peso que atenúa suavemente los extremos del barrido:

$$w_H[n] = 0.5 \left(1 - \cos\!\frac{2\pi n}{N_f-1}\right)$$

Esta atenuación reduce la energía efectiva en los extremos del barrido, lo que equivale a **reducir el ancho de banda efectivo** utilizado para la compresión en rango. El ancho de banda efectivo de una ventana Hanning es aproximadamente la mitad del nominal:

$$BW_\text{eff,Hanning} \approx BW/2 = 1\text{ GHz}$$

La resolución de rango resultante es:

$$\delta r_\text{Hanning} = \frac{c}{2 \cdot BW_\text{eff}} \approx \frac{3\times10^8}{2\times10^9} = 15\text{ cm}$$

La separación en rango entre los dos blancos era $\Delta z = 10$ cm (configuración inicial) o $\Delta z = 10$ cm (configuración final). Como $10\text{ cm} < 15\text{ cm}$, la ventana Hanning no puede resolver los dos blancos. Aparecen como un único lóbulo ancho en el perfil de rango y en la imagen SAR.

---

## 12. Por qué la ventana rectangular mejoró la resolución

La ventana rectangular no atenúa ninguna frecuencia: $w_R[n] = 1$. El ancho de banda efectivo es igual al nominal $BW = 2$ GHz, y la resolución de rango teórica de Rayleigh es:

$$\delta r_\text{rect} = \frac{c}{2 \cdot BW} = \frac{3\times10^8}{2\times2\times10^9} = 7.5\text{ cm}$$

Con separación $\Delta z = 10\text{ cm} > 7.5\text{ cm}$, los dos blancos cumplen el criterio de resolución de Rayleigh y aparecen como lóbulos distintos tanto en el perfil de rango como en la imagen SAR 2D.

La desventaja de la ventana rectangular es el nivel de lóbulos laterales: $-13$ dB. En escenas con blancos de muy diferente RCS, los lóbulos laterales de un blanco fuerte pueden enmascarar un blanco débil cercano. La ventana Hanning reduce los lóbulos laterales a $-31$ dB a costa de duplicar el lóbulo principal.

---

## 13. Por qué la configuración inicial de dos blancos no era físicamente resoluble

### 13.1 Configuración inicial (commit `eb75b1e`)

Los dos blancos del phantom original estaban en:
- **T1:** $(x=0\text{ cm},\, z=10\text{ cm})$
- **T2:** $(x=5\text{ cm},\, z=12\text{ cm})$

La separación en rango era $\Delta z = 12 - 10 = 2$ cm. La separación en azimut era $\Delta x = 5$ cm.

### 13.2 Por qué no se resolvían

La resolución de rango con ventana rectangular es $\delta r = 7.5$ cm. Como $\Delta z = 2\text{ cm} \ll 7.5\text{ cm}$, los dos blancos caen dentro del mismo bin de rango. La IFFT no puede distinguirlos: la suma de sus exponenciales produce un único pico cuya posición y amplitud dependen de las fases relativas.

La separación en azimut de 5 cm tampoco era suficiente para resolución cross-range dado el corto barrido azimutal (30 cm de apertura). Ambos blancos aparecían fusionados en un único manchón en la imagen SAR.

Esta configuración era válida para probar la corrección general del pipeline (el pico principal sí aparecía en la región esperada), pero no permitía demostrar la capacidad de resolución de dos blancos separados.

---

## 14. Separación de blancos en simulation.yaml

### 14.1 Criterio de separación

Para demostrar resolución física de dos blancos, ambas separaciones deben superar las resoluciones teóricas del sistema:

- **Separación en rango:** $\Delta z > \delta r = 7.5$ cm
- **Separación en azimut:** $\Delta x$ debe ser suficiente para que los dos blancos sean distinguibles en la imagen SAR 2D

### 14.2 Nueva configuración (commit `31bc9ee`)

```yaml
# configs/simulation.yaml
phantom:
  targets:
    - {x_m: -0.06, z_m: 0.09}   # T1: x=-6 cm, z=9 cm
    - {x_m:  0.06, z_m: 0.19}   # T2: x=+6 cm, z=19 cm
```

Las separaciones resultantes son:
- **Separación en rango:** $\Delta z = 19 - 9 = 10\text{ cm} > 7.5\text{ cm}$ ✓
- **Separación en azimut:** $\Delta x = 6 - (-6) = 12\text{ cm}$ ✓
- Los blancos están también en diferentes rangos oblicuos desde el centro de apertura: T1 a $\approx 10.8$ cm y T2 a $\approx 19.9$ cm.

Con esta configuración, la ventana rectangular resuelve ambos blancos tanto en el perfil de rango 1D como en la imagen SAR 2D. La ventana Hanning los fusiona, lo que convierte la comparación en una demostración pedagógica del compromiso resolución/lóbulos laterales.

---

## 15. Figuras generadas e interpretación

Las figuras se guardan en `reports/generated/` (directorio ignorado por git; se regeneran con `py experiments/run_simulation.py`).

### 15.1 `reports/generated/range_profiles.png`

**Qué muestra:** Dos paneles lado a lado. Cada panel es el perfil de amplitud del rango comprimido de la apertura central ($x_\text{az} \approx 0$):
- Panel izquierdo: ventana rectangular
- Panel derecho: ventana Hanning

Las líneas verticales discontinuas marcan el rango oblicuo (*slant range*) de cada blanco desde el centro de apertura:
- T1: $R_1 = \sqrt{(-0\text{ m}-(-0.06\text{ m}))^2 + (0.09\text{ m})^2} \approx 10.8$ cm
- T2: $R_2 = \sqrt{(0-0.06)^2 + 0.19^2} \approx 19.9$ cm

**Cómo interpretar:**
- Con ventana rectangular: dos picos claramente separados, cada uno cerca de su línea de referencia. El mínimo local entre los picos confirma que el sistema resuelve ambos blancos.
- Con ventana Hanning: los dos picos se fusionan en un único lóbulo amplio. No se puede determinar visualmente la posición de cada blanco.

### 15.2 `reports/generated/sar_window_comparison.png`

**Qué muestra:** Imagen SAR 2D en escala dB (umbral −25 dB), dos paneles:
- Panel izquierdo: retroproyección con ventana rectangular
- Panel derecho: retroproyección con ventana Hanning

El eje $x$ es el cross-range (−20 a +20 cm), el eje $y$ es el down-range (2 a 26 cm). Las marcas `+` en cian indican las posiciones verdaderas de T1 (−6, 9) cm y T2 (+6, 19) cm.

**Cómo interpretar:**
- Ventana rectangular: dos manchas (*spots*) focalizadas, cada una centrada sobre su marca de verdad. Confirma que el algoritmo de retroproyección localiza correctamente los blancos en 2D.
- Ventana Hanning: las dos manchas se fusionan en un lóbulo más grande y difuso. La posición del centroide queda entre las dos posiciones reales.

Esta figura es la demostración clave del compromiso resolución/lóbulos laterales para la tesis.

### 15.3 `reports/generated/sar_image.png`

**Qué muestra:** Imagen SAR de mejor resolución (ventana rectangular) en dos representaciones:
- Panel izquierdo: amplitud lineal (colormap `viridis`)
- Panel derecho: amplitud en dB (colormap `inferno`, umbral −25 dB)

Las marcas `+` en rojo indican las posiciones verdaderas de T1 y T2.

**Cómo interpretar:**
- La amplitud lineal muestra la morfología real de los lóbulos (útil para verificar simetría y lóbulos laterales).
- La representación dB facilita ver estructuras de baja amplitud (lóbulos laterales, artefactos de interpolación).
- La coincidencia entre las marcas `+` y los picos de la imagen confirma que la retroproyección con corrección de portadora localiza correctamente los blancos.

Esta figura es candidata directa para la Figura 3.3 del Capítulo 3 de la tesis.

---

## 16. Suite de pruebas: resultados y cobertura

**Resultado:** 12/12 pruebas aprobadas en todos los commits de la sesión.  
**Archivo:** `tests/test_simulation.py`  
**Comando:** `py -m pytest tests/test_simulation.py -v`

### Grupo 1: PhantomModel (4 pruebas)

| Prueba | Qué valida |
|---|---|
| `test_frequency_response_phase_single_target` | La fase de $H(f)$ sigue exactamente $-4\pi f R/c$ con error $< 10^{-10}$ rad. Es la prueba más importante: verifica el modelo de señal desde primeros principios. |
| `test_frequency_response_superposition` | La respuesta de dos blancos es igual a la suma de las respuestas individuales (linealidad del modelo). |
| `test_noise_changes_response` | El modo ruidoso (`noise_std > 0`) produce una señal diferente de la limpia; verifica que el generador de ruido está activo. |
| `test_phantom_from_config` | La función `phantom_from_config()` crea correctamente el objeto desde el diccionario YAML, incluyendo conversión de tipos. |

### Grupo 2: SyntheticScan (2 pruebas)

| Prueba | Qué valida |
|---|---|
| `test_scan_shape` | `H` tiene forma `(N_f, N_az)` consistente con las grillas de frecuencia y apertura; tipo `complex128`. |
| `test_scan_bandwidth` | `bandwidth_hz` devuelve el ancho de banda correcto (2 GHz). |

### Grupo 3: Perfil de rango (2 pruebas)

| Prueba | Qué valida |
|---|---|
| `test_range_profile_peak_location` | El pico de la IFFT cae dentro de 2 bins del rango verdadero (10 cm) para un blanco en eje. Valida que la IFFT mide el rango correcto. |
| `test_range_profile_shape` | El array de perfiles tiene dimensiones `(N_f*padding//2, N_az)`. |

### Grupo 4: Retroproyección SAR (3 pruebas)

| Prueba | Qué valida |
|---|---|
| `test_reconstruction_locates_single_target` | El pico de imagen SAR está a menos de 2 cm del blanco verdadero en ambas dimensiones. Valida la corrección de portadora y la interpolación. |
| `test_reconstruction_two_targets_both_visible` | La amplitud local cerca de cada blanco supera el 30% del máximo global. Valida que ambos blancos son distinguibles en la imagen. |
| `test_image_grid_from_config` | La cuadrícula de imagen generada desde config tiene el número correcto de puntos y los márgenes aplicados. |

### Grupo 5: Aislamiento de hardware (1 prueba)

| Prueba | Qué valida |
|---|---|
| `test_no_bladerf_imports` | Ninguno de los módulos de simulación/procesamiento importa bladeRF. Garantiza que el pipeline corre sin hardware y puede usarse en CI. |

---

## 17. Contenido de thesis/cap3_simulacion.md

El archivo `thesis/cap3_simulacion.md` (creado en el commit `2ce6cfe`) contiene el borrador completo del Capítulo 3 de la tesis, con las siguientes secciones:

| Sección | Contenido |
|---|---|
| **3.1 Motivación** | Justificación de la simulación antes del hardware: verificación del modelo de señal, validación del algoritmo de retroproyección, establecimiento de parámetros de referencia de resolución. |
| **3.2 Modelo de Señal** | Derivación matemática formal de $R_k(x_\text{az})$ y $H(f_n, x_\text{az})$ con ecuaciones LaTeX. Explicación del factor $4\pi$ (doble trayecto). |
| **3.3 Parámetros de Simulación** | Tabla 3.1 con todos los parámetros de `simulation.yaml`. Tabla 3.2 con las posiciones y amplitudes de T1 y T2. Notas de reproducibilidad (commit, versión de Python). |
| **3.4 Método de Procesamiento** | §3.4.1: derivación del eje de rango de la IFFT y comparación de ventanas. §3.4.2: corrección de fase portadora (derivación y validación). §3.4.3: ecuación de retroproyección con cuadrícula de imagen. |
| **3.5 Validación del Código** | Tabla de 7 pruebas clave con su verificación. Resultado: 12/12. |
| **3.6 Resultados** | Descripción de las tres figuras generadas. Verificación numérica de la resolución de rango ($\delta r = 7.5$ cm, $\Delta z = 10$ cm $> \delta r$). |
| **3.7 Interpretación y Limitaciones** | Modelo de blanco puntual isotrópico, ruido cero, canal de espacio libre, resolución azimutal no cuantificada, sin datos hardware. |
| **3.8 Trabajo Futuro Inmediato** | 4 pasos: loader de datos reales, comparación simulado vs. medido, cuantificación de resolución transversal, evaluación de SNR real. |

El capítulo está escrito directamente en LaTeX-Markdown, listo para incorporarse al documento de tesis con ajustes menores de formato.

---

## 18. Cómo este trabajo apoya la tesis

### 18.1 Estructura metodológica

La tesis sigue el flujo estándar de una tesis de ingeniería experimental:

```
Modelo teórico → Simulación → Validación → Hardware → Comparación
     (cap. 2)       (cap. 3)       (cap. 3)    (cap. 4)    (cap. 4-5)
```

La Fase 1 cubre los tres primeros eslabones. Sin esta etapa, los resultados experimentales carecerían de una línea de base teórica con la cual comparar.

### 18.2 Contribuciones concretas

1. **Verificación del modelo matemático:** La prueba `test_frequency_response_phase_single_target` verifica que la implementación Python reproduce exactamente la ecuación $H(f) = A\,e^{-j4\pi f R/c}$ con error de fase $< 10^{-10}$ rad. Esto garantiza que cualquier discrepancia futura con datos reales es atribuible al hardware, no al modelo.

2. **Parámetros de resolución verificados:** Se estableció empíricamente (y corroborado teóricamente) que $\delta r = 7.5$ cm con el barrido 500–2500 MHz y ventana rectangular. Este será el parámetro de comparación con el sistema real.

3. **Corrección de portadora documentada:** El bug de portadora (§8) es un error clásico en implementaciones SFCW de estudiantes. Haberlo encontrado y corregido en simulación —donde la causa es clara— evita horas de depuración cuando aparezca con datos reales.

4. **Pipeline reutilizable:** El módulo `processing/sar_reconstruction.py` está escrito para recibir un objeto `SyntheticScan[N_f, N_az]`. El cargador de datos reales (Fase 2) solo necesita producir ese mismo objeto a partir de los archivos `.npy`; el resto del pipeline (perfiles de rango, retroproyección, figuras) funciona sin modificación.

5. **Capítulo 3 redactado:** El borrador en `thesis/cap3_simulacion.md` reduce significativamente el trabajo de escritura en la etapa final de la tesis.

---

## 19. Limitaciones conocidas

### 19.1 Modelo de blanco

Los blancos son reflectores puntuales isótropos con amplitud unitaria (`target_rcs = 1.0`). Los objetos reales del laboratorio (alambres, esferas, objetos dieléctricos) tienen:
- Sección transversal radar (RCS) dependiente del ángulo de incidencia y la frecuencia.
- Variación de fase y amplitud con la orientación relativa a la apertura.

La imagen simulada de un blanco real puede diferir significativamente de la predicción del modelo puntual.

### 19.2 Ausencia de ruido

La simulación usa `noise_std = 0.0`. El sistema bladeRF real introduce ruido térmico del receptor, phase noise del oscilador local, y ruido cuántico de cuantización del ADC. La SNR real es desconocida hasta que se procesen capturas reales.

### 19.3 Canal idealizado

El modelo asume:
- Propagación en espacio libre ($\varepsilon_r = 1.0$, sin pérdidas).
- No hay reflexiones múltiples (ecos de la caverna, múltiples rebotes entre blancos).
- No hay diagrama de radiación de antena (se asume isotrópica).
- No hay acoplamiento TX-RX (el bladeRF opera con la misma antena en TX y RX con un circulador o conmutador).

### 19.4 Resolución azimutal no cuantificada

La resolución transversal (cross-range) no fue calculada analíticamente. Se evaluó únicamente que los dos blancos son visualmente distinguibles con 12 cm de separación en azimut. La cuantificación del ancho a −3 dB del lóbulo principal en azimut queda pendiente.

### 19.5 Apertura corta

La apertura sintética es de solo 30 cm (−15 a +15 cm, 16 posiciones). Para un blanco a $z = 19$ cm, el ángulo máximo de visión es $\theta_\text{max} = \arctan(15/19) \approx 38°$. Una apertura mayor o un blanco más lejano mejoraría la resolución azimutal.

---

## 20. Próximo paso exacto: acquisition/load_sfcw_capture.py

El siguiente paso de la tesis (Fase 2) es conectar el pipeline de procesamiento existente con capturas reales del bladeRF. Para ello se debe crear el archivo `acquisition/load_sfcw_capture.py`.

### 20.1 Objetivo

El loader debe leer los archivos `.npy` en `legacy/capturas_barrido/` (capturas reales del sistema bladeRF anterior) y convertirlos al formato `SyntheticScan(freqs_hz, x_az_m, H)` que ya consume el pipeline de procesamiento.

### 20.2 Interfaz esperada

```python
# acquisition/load_sfcw_capture.py  (esquema)
from simulation.synthetic_scan import SyntheticScan

def load_sfcw_capture(
    npy_path: str | pathlib.Path,
    cfg: dict,
) -> SyntheticScan:
    """
    Lee un archivo .npy de captura SFCW del bladeRF y lo convierte
    a un SyntheticScan compatible con el pipeline de procesamiento.

    El array .npy debe tener forma (N_f, N_az) y dtype complex128
    (o equivalente). Los parámetros de frecuencia y apertura se leen
    de cfg (mismo formato que configs/simulation.yaml).
    """
    ...
```

### 20.3 Pasos a implementar

1. **Inspección de los archivos `.npy`:** Antes de escribir el loader, ejecutar un script de inspección (sin cargar los arrays completos) que reporte `shape`, `dtype`, nombre de archivo, y metadatos (si existen en un `.json` asociado). Esto determina el formato real de los datos.

2. **Mapeo de dimensiones:** Verificar que la primera dimensión corresponde al eje de frecuencias y la segunda al eje azimutal, o transponer si es necesario.

3. **Validación de parámetros:** Comprobar que las frecuencias y posiciones azimutales del archivo coinciden con los del YAML de configuración (o leerlos del metadata del archivo si existe).

4. **Prueba de integración:** Ejecutar `experiments/run_simulation.py` modificado para aceptar un `SyntheticScan` cargado desde el archivo real, y comparar el perfil de rango simulado con el medido para un blanco conocido.

### 20.4 Comando de arranque recomendado

```bash
# Paso 0: Inspeccionar sin cargar datos completos
py -c "
import numpy as np, pathlib
for p in pathlib.Path('legacy/capturas_barrido').glob('*.npy'):
    a = np.load(p, mmap_mode='r')
    print(p.name, a.shape, a.dtype)
"
```

Este comando lista los arrays sin cargarlos en memoria, en cumplimiento de la regla de no leer arrays grandes directamente.

---

## Referencias internas

| Recurso | Descripción |
|---|---|
| `configs/simulation.yaml` | Parámetros completos de la simulación (commit `31bc9ee`) |
| `simulation/phantom_model.py` | Modelo de señal SFCW, clase `PhantomModel` |
| `simulation/synthetic_scan.py` | Generación del cubo de datos `H[N_f, N_az]` |
| `processing/range_profile.py` | IFFT con ventana y eje de rango |
| `processing/sar_reconstruction.py` | Retroproyección con corrección de portadora |
| `experiments/run_simulation.py` | Script de ejecución completa y generación de figuras |
| `tests/test_simulation.py` | 12 pruebas unitarias (12/12 aprobadas) |
| `thesis/cap3_simulacion.md` | Borrador del Capítulo 3 listo para incorporar a la tesis |
| `reports/ai_session_log.md` | Registro cronológico de sesiones de trabajo con IA |

---

*Informe generado el 2026-05-31. Cubre las sesiones de trabajo del 2026-05-30.*  
*Pipeline validado en commit `31bc9ee`. Sin acceso a hardware en ningún momento de las sesiones reportadas.*
