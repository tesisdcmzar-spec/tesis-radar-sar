# Addendum Fase 5: Mapa de Calor de Contraste Dielelectrico Relativo

**Fecha:** 2026-06-01
**Arquitectura:** UWB-OFDM-SAR
**Estado:** Validacion por simulacion completa. Hardware pendiente.

---

## 1. Contexto

En la Fase 4 se valido el pipeline de perfil de contraste en distancia (1D):
- H_delta[k] = H_obj[k] - H_bg[k]
- CIR_delta = IFFT(H_delta * ventana)
- contraste(R) = |CIR_delta(R)| / max

La Fase 5 extiende este resultado a un **mapa de calor 2D** usando retroproyeccion SAR:
- El objeto se localiza en dos dimensiones: distancia (down-range z) y posicion azimutal (x).
- El resultado es una imagen de reflectividad relativa, no permitividad absoluta.

---

## 2. Modelo de phantom sintetico

Se definio un phantom 2D con:
- **Fondo:** eps_r = 1.0 (aire)
- **Inclusion A** (proxy de plastico): centro (-0.15 m, 0.50 m), r=0.08 m, eps_r=3.5
- **Inclusion B** (alto contraste): centro (+0.25 m, 0.85 m), r=0.06 m, eps_r=9.0

El coeficiente de reflexion de Fresnel a incidencia normal desde el fondo a la inclusion:
```
Gamma = (sqrt(eps_bg) - sqrt(eps_incl)) / (sqrt(eps_bg) + sqrt(eps_incl))
```
- A: |Gamma_A| = 0.303
- B: |Gamma_B| = 0.500

Este modelo es una **aproximacion de dispersor puntual**. No modela:
- Permitividad dependiente de frecuencia (modelo Cole-Cole para tejido)
- Dispersiones multiples entre inclusiones
- Propagacion dentro de la inclusion (solo reflexion en la superficie)
- Medios con perdidas (parte imaginaria de epsilon_r)
- Efectos de campo cercano

---

## 3. Pipeline de simulacion

```
Phantom (eps_r(x,z))
    |
    v
Targets (PointTarget con Gamma de Fresnel como reflectividad)
    |
    v
simulate_h_matrix() x5 bloques OFDM (2.0, 2.5, 3.0, 3.5, 4.0 GHz)
    |
    v
_stitch_h_matrices()  ->  H_stitched (f, x_az)
    Freq: 1.812 a 4.188 GHz, BW efectivo: 2.375 GHz
    Resolucion en distancia: 6.3 cm
    |
    v
backprojection_image()  ->  img_SAR(x, z)  [compleja, 150x150]
    |
    v
sar_image_to_contrast_heatmap()  ->  heatmap(x,z) = |img| / max|img|  [0,1]
```

---

## 4. Resultados de simulacion

| Parametro | Valor |
|---|---|
| Subportadoras stitched | 960 |
| BW efectivo total | 2.375 GHz |
| Resolucion en distancia | 6.3 cm |
| Resolucion azimutal (aprox.) | 5.0 cm a 3 GHz |
| RMSE heatmap vs GT | 0.1093 |
| Picos encontrados | 1 (threshold=0.3) |
| Posicion del pico (B) | (0.25, 0.74) m |
| Posicion verdadera (B) | (0.25, 0.85) m |
| Error de localizacion | 0.11 m (~1.7 bins) |

**Observaciones:**
- La inclusion B (mayor contraste) fue correctamente localizada en x (error=0) y aproximadamente en z (error<2 bins).
- La inclusion A (contraste menor) no fue detectada como pico separado con threshold=0.3, lo cual es coherente con su menor reflectividad (|Gamma|=0.303 ~ umbral).
- La retroproyeccion funciona correctamente para el caso de simulacion libre de ruido con BW suficiente.

---

## 5. Lo que esta imagen representa y lo que NO representa

### Representa:
- **Mapa de contraste dielelectrico relativo**: indica donde hay mayor contraste electromagnetico en la escena.
- **Localizacion cualitativa de discontinuidades dielectricas**: la inclusion de mayor contraste se localiza correctamente.
- **Validacion del pipeline computacional**: la cadena completa desde H(f, x_az) hasta la imagen 2D funciona.

### NO representa:
- **Permitividad dielectrica absoluta epsilon_r(x,z)**: la normalizacion al maximo elimina la escala absoluta.
- **Medicion calibrada de material**: no hay referencia de permitividad conocida ni modelo inverso.
- **Desempeno con hardware real**: esta es una simulacion con modelo simplificado.
- **Imagen medica validada**: no hay material biologico, no hay datos clinicos, no hay afirmaciones clinicas.
- **Deteccion de cancer o tumor**: absolutamente prohibido afirmarlo a partir de este resultado.

---

## 6. Camino hacia permitividad relativa calibrada

Para avanzar de "contraste relativo" a "permitividad relativa estimada":

1. **Medicion de referencia**: capturar H_ref(f) con un material de eps_r conocida (ej. agua: ~78, gel fisiologico: ~65, HDPE: ~2.3).
2. **Calibracion de amplitud**: normalizar H_obj por H_ref para eliminar respuesta de antena/cable.
3. **Modelo de propagacion**: invertir H_delta para obtener eps_r(R) usando un modelo de propagacion (Born, difraccion escalar, etc.).
4. **Validacion con fantoma fisico**: comparar resultado con fantoma de propiedades conocidas.
5. **Repetibilidad**: demostrar resultado consistente en condiciones controladas.

Esto es trabajo para la Fase 6 o capitulos posteriores de la tesis.

---

## 7. Equivalente en hardware

Para obtener una imagen de contraste real con el bladeRF:
1. Conectar bladeRF, antena TX1 y RX1.
2. Colocar reflector metalico en campo de vision.
3. Capturar H_bg (sin objeto de prueba).
4. Colocar objeto de prueba (ej. botella de agua).
5. Capturar H_obj.
6. Calcular H_delta = H_obj - H_bg.
7. Ejecutar stitching de bloques y retroproyeccion.
8. Generar mapa de calor de contraste relativo.

Limitacion actual: con bladeRF en modo de un solo bloque (20 MHz), la resolucion en distancia es ~7.5 m (inutilizable para objetos a 1 m). Se necesita stitching real de multiples bloques con re-sintonizacion del LO.

---

## 8. Figuras de referencia

Todas las figuras se encuentran en `reports/generated/phase5_dielectric_heatmap/`:

| Figura | Descripcion |
|---|---|
| `synthetic_ground_truth_permittivity_map.png` | Mapa eps_r(x,z) sintetico y reflectividad de Fresnel (referencia) |
| `reconstructed_relative_contrast_heatmap.png` | Mapa de calor reconstruido por retroproyeccion SAR |
| `heatmap_error_or_difference.png` | Comparacion GT vs. reconstruido y mapa de diferencias |
| `range_profiles_from_heatmap_pipeline.png` | Perfiles de rango en posiciones azimutales seleccionadas |
| `pipeline_summary_figure.png` | Resumen de 6 paneles del pipeline completo |

---

**Sin afirmaciones clinicas. Sin permitividad absoluta. Sin deteccion de cancer.**
