# Addendum Phase 4: Perfil de Contraste Relativo con OFDM

*Addendum al capitulo de validacion experimental. Fase 4.*
*Fecha: 2026-06-01.*

---

## 1. Contexto

La arquitectura del sistema es UWB-OFDM-SAR.
La forma de onda de sondeo es una senal OFDM con simbolos piloto conocidos.
El bladeRF 2.0 micro transmite y recibe los simbolos OFDM dentro de su ancho
de banda instantaneo (~2 MHz para validacion inicial, ~56 MHz en configuracion amplia).

Esta fase (Fase 4) no realiza todavia una imagen SAR completa.
El objetivo es validar la cadena de estimacion del canal y obtener un
primer perfil de reflectividad relativa versus distancia.

---

## 2. Estimacion del canal: H[k] = Y[k] / X[k]

Para cada subportadora OFDM de indice k:
- X[k]: simbolo piloto conocido transmitido.
- Y[k]: senal recibida (despues de eliminar prefijo ciclico y aplicar FFT).
- H[k]: estimacion del canal en la subportadora k.

La estimacion se promedia sobre multiples simbolos (repeticiones) para
reducir el ruido:

```
H[k] = (1/N_rep) * sum_n (Y_n[k] / X[k])
```

H[k] refleja la respuesta combinada de: cables, antenas, canal de
propagacion libre, y objetos en el area de cobertura.

---

## 3. Sustraccion de fondo: H_delta[k] = H_obj[k] - H_bg[k]

Para aislar la contribucion del objeto de prueba:
1. Se captura H_bg[k]: bloque OFDM sin objeto (fondo/clutter del entorno).
2. Se captura H_obj[k]: bloque OFDM con objeto (reflector metalico) en posicion.
3. Se calcula la diferencia:

```
H_delta[k] = H_obj[k] - H_bg[k]
```

H_delta[k] cancela la respuesta estacionaria del fondo y conserva
solo el campo dispersado por el objeto.

---

## 4. Respuesta impulsional diferencial: CIR_delta

La respuesta impulsional del canal diferencial se obtiene por IFFT ventanada:

```
CIR_delta(tau) = IFFT(H_delta[k] * ventana[k])
```

La ventana (Hanning por defecto) reduce los lobulos laterales a costa de
un ensanchamiento del lobulo principal.

El dominio del tiempo tau corresponde al retardo de propagacion de ida y vuelta.

---

## 5. Perfil de contraste relativo versus distancia

La distancia equivalente al retardo tau es:

```
R = c * tau / 2        (propagacion de dos vias, radar monostatico)
```

El perfil de contraste normalizado:

```
contraste(R) = |CIR_delta(R)| / max(|CIR_delta(R)|)
```

es un indicador relativo. Valores altos (cerca de 1.0) indican que en esa
distancia existe un mayor contraste electromagnetico diferencial respecto
al fondo.

Este perfil se denomina en este trabajo:
- "perfil de contraste dielelectrico relativo"
- "estimacion preliminar de region reflectiva en distancia"
- "no calibrado en permitividad absoluta"

---

## 6. Limitaciones y afirmaciones seguras

### Lo que SI puede afirmarse:

- H[k] = Y[k] / X[k] es una estimacion valida del canal OFDM por subportadora.
- H_delta[k] cancela la respuesta de fondo estacionaria (suponiendo que
  el entorno no cambia entre capturas).
- La IFFT de H_delta produce un perfil de retardo donde los picos indican
  retardos dominantes asociados al objeto.
- El pico mas prominente en contraste(R) es consistente con un objeto
  altamente reflectivo a esa distancia (si se verifica experimentalmente).

### Lo que NO puede afirmarse sin calibracion adicional:

- "La permitividad en R es epsilon_r = X."
- "Detecte tejido canceroso."
- "El contraste es proporcional a epsilon_r(r)."
- "La imagen tiene resolucion sub-centimetrica."

Para obtener epsilon_r(r) absoluta se requiere:
1. Modelo de propagacion calibrado (respuesta de antena real incluida).
2. Medicion de referencia con material de permitividad conocida.
3. Inversion del modelo dielectrico (Born, Cole-Cole, etc.).
4. Validacion con fantoma fisico de propiedades conocidas.

---

## 7. Efecto del stitching de bloques en la resolucion

La resolucion en distancia depende del ancho de banda total:

```
dR = c / (2 * BW_total)
```

| Configuracion | BW_total | dR |
|---|---|---|
| 1 bloque a 2 MS/s | ~1 MHz activo | ~150 m |
| 3 bloques a 2 MS/s (piloto) | ~23 MHz | ~6.5 m |
| 28 bloques a 2 MS/s @ 2 MHz spacing | ~56 MHz | ~2.7 m |
| bladeRF a 56 MS/s (un bloque) | ~42 MHz activo | ~3.6 m |
| 10 bloques a 56 MS/s @ 50 MHz spacing | ~500 MHz | ~0.30 m |
| UWB: 100 bloques, 56 MS/s, 50 MHz spacing | ~5 GHz | ~3 cm |

El pilot de Fase 4 usa 3 bloques (BW ~ 23 MHz, dR ~ 6.5 m).
No es suficiente para localizar un objeto a 1 m con resolucion sub-metrica.
Pero valida que la cadena de software funciona correctamente.

---

## 8. Continuidad de fase en el stitching

Al resintonizar el OLA entre bloques, la fase inicial del receptor cambia
de manera aleatoria (jitter de fase del OLA). Esto introduce una
discontinuidad de fase entre bloques adyacentes.

El modulo `ofdm_block_stitcher.py` estima y corrige un desfase de fase
estatico entre bloques usando subportadoras solapadas. Esta correccion
es parcial: no compensa una rampa de fase lineal (que equivale a un error
de retardo de grupo entre bloques).

La calibracion completa de fase requiere:
- Medicion de referencia (reflector de cable conocido) en cada bloque.
- Modelo de compensacion lineal de fase entre bloques.
- Esto es un objetivo de la Fase 5 del proyecto.

---

## 9. Modulos de codigo implementados en Fase 4

| Modulo | Descripcion |
|---|---|
| `processing/ofdm_distance_contrast.py` | compute_delta_channel, channel_to_delay_profile, range_axis_m, relative_contrast_profile, summarize_contrast_profile |
| `processing/ofdm_block_stitcher.py` | stitch_ofdm_blocks, phase offset correction |
| `experiments/run_ofdm_background_object_profile.py` | pipeline completo fondo/objeto |
| `experiments/run_ofdm_small_stitching_pilot.py` | piloto 3 bloques |
| `experiments/run_phase4_autonomous_validation.py` | validacion autonoma software |
| `experiments/run_phase4_hardware_entrypoint.py` | entrypoint supervisado |

---

*Sin afirmaciones clinicas. Sin permitividad absoluta. Sin deteccion de cancer.*
*Salida: solo perfil de contraste relativo no calibrado.*
