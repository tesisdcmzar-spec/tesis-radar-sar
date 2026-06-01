# Phase 4: Perfil de Contraste Dielelectrico Relativo (OFDM)

## Descripcion general

Este documento describe la metodologia para obtener un perfil de
reflectividad relativa versus distancia a partir de mediciones OFDM.

La salida se denomina:
- "perfil de contraste dielelectrico relativo"
- "estimacion preliminar de region reflectiva en distancia"
- "respuesta de canal asociada a contrastes electromagneticos"
- "no calibrado en permitividad absoluta"

NO es un mapa de permitividad absoluta epsilon_r(r).
Se requiere calibracion con fantoma/referencia conocida para obtener epsilon_r.

---

## 1. Estimacion del canal OFDM: H[k] = Y[k] / X[k]

El sistema transmite un simbolo OFDM conocido X[k] en cada subportadora k.
Tras recibir la senal Y[k] (despues de eliminar el prefijo ciclico y aplicar FFT),
se estima el canal subportadora a subportadora:

```
H[k] = Y[k] / X[k]
```

Esta estimacion incluye la respuesta combinada de:
- Cable y conectores
- Antena transmisora (TX1)
- Canal de propagacion libre
- Antena receptora (RX1)
- Objetos en el area de cobertura

---

## 2. Diferencia de canal: H_delta[k] = H_objeto[k] - H_fondo[k]

Para aislar la contribucion del objeto de prueba, se capturan dos bloques:
1. Captura de fondo: sin objeto en el area de prueba.
2. Captura con objeto: con reflector metalico o material de contraste en posicion conocida.

La diferencia de canal resulta en:

```
H_delta[k] = H_objeto[k] - H_fondo[k]
```

Esto elimina la respuesta de fondo (cable, antena, clutter estacionario)
y conserva solo la contribucion diferencial del objeto.

---

## 3. Perfil de retardo: CIR_delta = IFFT(H_delta * ventana)

Aplicando una ventana espectral (Hanning por defecto) para reducir lobulos laterales
y luego calculando la IFFT:

```
CIR_delta(tau) = IFFT(H_delta[k] * ventana[k])
```

El resultado es la respuesta impulsional del canal diferencial en el dominio del tiempo.
El pico de |CIR_delta(tau)| indica el retardo dominante asociado al objeto.

---

## 4. Conversion retardo -> distancia (propagacion de dos vias)

Para un radar monostatico (TX = RX en la misma posicion), la propagacion es de ida y vuelta:

```
R = c * tau / 2
```

donde:
- R es la distancia al objeto [m]
- c es la velocidad de la luz en el medio (~3e8 m/s en aire libre)
- tau es el retardo de propagacion [s]

La resolucion en distancia depende del ancho de banda total:

```
dR = c / (2 * BW)
```

Para un bloque unico de 2 MHz: dR ~ 150 m (insuficiente para detectar objetos a 1 m).
Para stitching de 3 bloques de 2 MHz a 10 MHz de separacion: dR ~ 6.8 m.
Para UWB real (> 1 GHz de BW): dR < 0.15 m (15 cm).

---

## 5. Perfil de contraste relativo

El perfil normalizado:

```
contraste(R) = |CIR_delta(R)| / max(|CIR_delta(R)|)
```

es un indicador relativo de la reflectividad del canal en cada distancia.
Valores altos indican mayor contraste electromagnetico diferencial.

Este perfil NO es:
- Permitividad dielectrica absoluta epsilon_r(r)
- Mapa de conductividad del medio
- Imagen SAR calibrada
- Resultado clinico o diagnostico

---

## 6. Por que esto NO es permitividad absoluta

La estimacion H[k] incluye la respuesta completa del sistema:
- Respuesta de la antena (no plana, varía con frecuencia)
- Perdidas en el cable (no constantes)
- Acoplamiento TX-RX (back-coupling)
- Reflexiones multitrayecto del entorno

Para obtener epsilon_r(r) absoluta se necesita:
1. Modelo de propagacion calibrado con la respuesta de la antena real.
2. Captura de referencia con material de permitividad conocida (agua, aceite, etc.).
3. Inversion del modelo (p.ej. modelo de Born, Cole-Cole, etc.).
4. Validacion con fantoma fisico de permitividad conocida.

Nada de esto esta implementado en esta fase.
La salida actual es un indicador heuristico relativo.

---

## 7. Como el stitching mejora la resolucion en distancia

El bladeRF tiene un ancho de banda instantaneo de ~56 MHz.
Para cubrir una banda UWB (p.ej. 500 MHz -- 3 GHz), se usan multiples
bloques de frecuencia centrada (center frequencies) consecutivos.

Cada bloque captura H[k] en una sub-banda. El modulo
`processing/ofdm_block_stitcher.py` une estos bloques en H_total(f)
con correccion de desfase de fase entre bloques:

```
H_total(f) = stitch(H_bloque_0(f), H_bloque_1(f), ..., H_bloque_N(f))
```

El ancho de banda total BW_total = N_bloques * BW_por_bloque (sin solapamiento).
La resolucion mejora proporcionalmente: dR = c / (2 * BW_total).

---

## 8. Continuidad de fase y calibracion

Al resintonizar el OLA (oscilador local) entre bloques, la fase inicial
del receptor cambia aleatoriamente. Esto crea discontinuidades de fase
en H_total(f) que degradan la resolucion del CIR.

La correccion actual en `ofdm_block_stitcher.py` estima y elimina un
desfase de fase estatico entre bloques adyacentes (usando subportadoras
solapadas). Esto NO elimina una rampa de fase lineal (que equivale a
un desplazamiento de retardo entre bloques).

Para calibracion completa se requiere:
- Reflector de referencia a distancia conocida.
- Medicion de referencia por bloque para estimar la fase inicial del OLA.
- Modelo de compensacion de fase lineal entre bloques.

Esta calibracion es un objetivo de la Fase 5 del proyecto.

---

## 9. Limitaciones actuales (Fase 4)

1. BW de un bloque (~1 MHz activo a 2 MS/s): resolucion ~150 m. Inutil para 1 m.
2. BW de 3 bloques piloto (~23 MHz total): resolucion ~6.5 m. Inutil para 1 m.
3. Sin calibracion de fase entre bloques (correccion parcial con overlap).
4. Sin modelo de antena ni calibracion de cable.
5. Sin referencia de permitividad absoluta.
6. Salida: solo perfil de contraste relativo, no calibrado.

---

## 10. Modulos de codigo relevantes

| Modulo | Funcion |
|---|---|
| `processing/ofdm_channel.py` | H[k] = Y[k]/X[k], CIR, retardo, rango |
| `processing/ofdm_distance_contrast.py` | Pipeline completo: H_delta, CIR, contraste |
| `processing/ofdm_block_stitcher.py` | Stitching de multiples bloques en H_total(f) |
| `acquisition/ofdm_block_capture.py` | Captura hardware de un bloque OFDM |
| `experiments/run_ofdm_background_object_profile.py` | Script de fondo/objeto |
| `experiments/run_ofdm_small_stitching_pilot.py` | Pilot de stitching 3 bloques |

---

*Generado automaticamente. Sin afirmaciones clinicas. Sin permitividad absoluta.*
