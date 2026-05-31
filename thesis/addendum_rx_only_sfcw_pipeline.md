# Addendum: Validacion de la Cadena de Procesamiento SFCW con Datos RX-only

**Documento de apoyo para:** Capitulo 6 (Abstraccion de Hardware bladeRF) y Capitulo 7 (Experimentos)
**Fecha:** 2026-05-31
**Commits de referencia:** `226c5b3` (barrido SFCW), sesion de post-procesamiento

---

## A.1 Introduccion

En esta etapa del proyecto se realizo el primer barrido de frecuencias escalonadas (SFCW,
Stepped-Frequency Continuous Wave) con el bladeRF en modo recepcion exclusiva (RX-only).
El objetivo fue validar la cadena de procesamiento completa:

```
bladeRF RX -> IQ por frecuencia -> H(f) por promedio coherente -> SyntheticScan -> IFFT -> perfil de rango
```

Este experimento NO constituye una medicion de radar. No se emitio senal alguna.
La funcion de transferencia H(f) obtenida es el promedio coherente del ruido ambiental
en cada frecuencia sintonizada, y el perfil de rango resultante es una validacion de
la infraestructura de procesamiento, no una deteccion de objetivos.

---

## A.2 Metodologia del barrido RX-only

### A.2.1 Configuracion del barrido

Se realizaron dos pasadas supervisadas sobre el rango 2.300--2.500 GHz:

| Modo | Paso | Puntos | Muestras/freq | Duracion aprox. |
|------|------|--------|--------------|-----------------|
| Piloto | 10 MHz | 21 | 100 000 | ~2 min |
| Completo | 1 MHz | 201 | 100 000 | ~4 min |

Para cada frecuencia del barrido:
1. Se abre una instancia de `BladeRFDevice` con `BladeRFConfig`.
2. Se configura el canal RX: frecuencia central, tasa de muestreo (10 MS/s), ancho de banda (10 MHz), ganancia (20 dB).
3. Se captura una rafaga de 100 000 muestras IQ en formato SC16Q11.
4. Se convierte a complejo128 mediante `sc16q11_to_complex`.
5. Se calcula el promedio coherente: `H[k] = mean(IQ_k)`.
6. Se cierra el dispositivo y se avanza a la siguiente frecuencia.

### A.2.2 Ensamblado de H(f)

```python
H[k] = (1/N) * sum_{n=0}^{N-1} IQ_k[n]  ,  k = 0, 1, ..., K-1
```

Para ruido gaussiano complejo de media cero, `H[k]` converge a cero a medida que N
aumenta. Para una tono CW coherente en DC (relativo a la frecuencia sintonizada), `H[k]`
recupera el fasor complejo del tono. En este experimento, sin TX, `H[k]` es el residuo
estadistico del promedio de ruido mas los interferentes ISM ambientales.

### A.2.3 Perfil de rango

Se aplica una IFFT con relleno de ceros (padding_factor=8) y ventana Hanning:

```
h(tau) = IFFT{ H(f) }
r[n] = c * tau[n] / 2  (rango de ida)
```

El bin mas fuerte cae en r=0 m, correspondiente al termino DC del IFFT de la media
compleja. Esto confirma el comportamiento esperado para datos de ruido sin TX.

---

## A.3 Resultados del barrido

### A.3.1 Barrido piloto

- 21/21 capturas exitosas. Sin recorte de senal. Sin fallos USB.
- Rango dinamico de H(f): 2.7 dB (casi plano -- consistente con ruido de fondo).
- Bin de rango mas fuerte: 0.000 m / -86.1 dB.
- Interferentes visibles: elevacion de RMS en banda ISM 2.4 GHz (Wi-Fi 802.11b/g/n).

### A.3.2 Barrido completo

- 200/201 capturas exitosas (99.5%). Un timeout USB NIOS II en 2452 MHz (recuperacion automatica).
- Rango no ambiguo: R_unamb = c/(2*df) = 3e8 / (2 * 1e6) = 150 m (con paso de 1 MHz).
- Bin de rango mas fuerte: 0.000 m / -86.2 dB.

---

## A.4 Post-procesamiento implementado

Se implemento el modulo `processing/rx_sfcw_postprocess.py` con las siguientes funciones:

| Funcion | Proposito |
|---------|-----------|
| `remove_dc_component(H)` | Elimina el componente de media; reduce el pico en 0 m del IFFT |
| `normalize_h_magnitude(H)` | Escala a max|H|=1 para comparacion de formas |
| `subtract_reference_h(H, H_ref)` | Sustraccion de fondo (prepara el pipeline para TX/RX) |
| `smooth_h_magnitude(H, N)` | Suavizado boxcar de la magnitud, fase preservada |
| `estimate_noise_floor_db(profile)` | Piso de ruido como mediana del perfil en dB |
| `find_prominent_range_bins(...)` | Bins que superan el piso en >= umbral especificado |
| `summarize_range_profile(...)` | Estadisticas del perfil: pico, piso, rango dinamico |

Todas las funciones son independientes de hardware y estan validadas con datos sinteticos
(57 tests en `tests/test_rx_sfcw_postprocess.py`).

---

## A.5 Distincion entre validacion RX-only y medicion radar real

Esta distincion es critica para la integridad del trabajo de tesis:

| Aspecto | Barrido RX-only (este addendum) | Medicion SFCW calibrada (futura) |
|---------|--------------------------------|----------------------------------|
| TX | Ninguna | Senal CW por paso de frecuencia |
| H(f) | Ruido ambiental | Respuesta del canal radar |
| Perfil de rango | Validacion del pipeline | Mapa de reflectividad |
| Bin mas fuerte | DC del IFFT de ruido | Reflection del objetivo mas cercano |
| Puede detectar objetivos | No | Si (con calibracion) |
| Requiere sustraccion de fondo | No aplicable | Si (referencia sin objetivo) |

---

## A.6 Que prepara este experimento para la fase TX/RX

1. **Pipeline de procesamiento validado:** La cadena completa desde captura IQ hasta perfil
   de rango funciona correctamente con datos reales del bladeRF.

2. **Formato de datos establecido:** `freqs_hz.npy` + `H_raw.npy` + `metadata.json` es el
   formato de intercambio entre el script de captura y los modulos de procesamiento.

3. **Funciones de post-procesamiento listas:** `remove_dc_component`, `subtract_reference_h`
   y `summarize_range_profile` estan implementadas y testeadas, listas para datos TX/RX.

4. **Script de analisis offline disponible:** `experiments/analyze_latest_rx_sfcw_sweep.py`
   puede cargar cualquier directorio de captura y aplicar el pipeline sin modificaciones.

5. **Infraestructura de seguridad probada:** El mecanismo de confirmacion (`CONFIRM HARDWARE RUN`),
   el patron abrir/cerrar por frecuencia, y el manejador de errores USB estan validados.

---

## A.7 Proxima fase: primer experimento TX/RX calibrado

La siguiente etapa experimental requiere:

1. Implementacion de la ruta TX en `hardware/bladerf_device.py` con bloqueo de seguridad.
2. Primera prueba TX hacia carga de 50 ohm (sin antena, sin emision al entorno).
3. Primera prueba TX con antena hacia reflector metalico a distancia conocida.
4. Medicion de S21(f) = V_RX(f) / V_TX(f) con y sin objeto (sustraccion de fondo).
5. Verificacion de que el perfil de rango muestra un pico en la distancia esperada.

**Esta etapa requiere presencia fisica del usuario, configuracion de banco segura, y la
frase de confirmacion `CONFIRM HARDWARE RUN` introducida manualmente.**

No se realizara TX automaticamente. Ver `docs/prompts/next_phase_tx_safety_plan.md`.

---

## A.8 Notas para la escritura del capitulo de tesis

- El barrido RX-only debe describirse como "validacion de infraestructura" o
  "validacion de la cadena de procesamiento", no como "experimento de radar".
- El perfil de rango obtenido debe presentarse con la etiqueta
  "perfil de ruido ambiental -- validacion de pipeline -- sin TX".
- La Figura XX (por incluir) mostrara el H(f) del barrido completo y el perfil de rango,
  con nota explicita de que es datos de ruido sin emision.
- La comparacion entre H(f) raw y DC-removed ilustra el efecto del componente de media
  en el perfil IFFT y justifica la necesidad de sustraccion de fondo en el experimento TX/RX real.
