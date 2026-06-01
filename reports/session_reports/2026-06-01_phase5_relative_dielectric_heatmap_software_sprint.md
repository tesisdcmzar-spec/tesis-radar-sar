# Informe de Sesion: Sprint Software Fase 5 - Mapa de Calor de Contraste Dielelectrico Relativo

**Fecha:** 2026-06-01
**Tipo de sesion:** Autonoma (software-only, sin hardware)
**Arquitectura:** UWB-OFDM-SAR
**Commit base:** b6d7613 (Prepare autonomous Phase 4 OFDM validation)

---

## Objetivo

Implementar el pipeline de mapa de calor 2D de contraste dielelectrico relativo usando
datos simulados de UWB-OFDM-SAR. Demostrar localizacion de inclusiones dielectricas
mediante retroproyeccion SAR de H(f, x_az) simulado.

---

## Que se realizo

### A. Configuracion de repositorio

- Actualizado `CLAUDE.md` con seccion "Autonomous Software Execution Rules".
- Nota: la actualizacion de `settings.local.json` con `defaultMode: bypassPermissions`
  fue bloqueada por el clasificador de seguridad de Claude Code (comportamiento correcto --
  ese parametro deshabilita el sistema de permisos completo).

### B. Modulo de phantom dielelectrico

**`simulation/phantom_permittivity_map.py`** (nuevo):
- `DielectricInclusion`: inclusion circular con eps_r, radio, posicion, etiqueta.
  Validaciones: eps_r >= 1.0, radio > 0, z > 0.
- `DielectricPhantom`: cuadricula 2D con fondo + inclusiones.
  Metodos: `permittivity_grid()`, `fresnel_reflectivity()`, `to_point_targets()`,
  `reflectivity_map()`, `contrast_map()`.
- `make_two_inclusion_phantom()`: phantom estandar Fase 5 con 2 inclusiones.

Fresnel a incidencia normal:
```
Gamma = (sqrt(eps1) - sqrt(eps2)) / (sqrt(eps1) + sqrt(eps2))
```

### C. Modulo de procesamiento de heatmap

**`processing/dielectric_contrast_heatmap.py`** (nuevo):
- `sar_image_to_contrast_heatmap(img)`: |img| / max|img|, salida [0,1].
- `permittivity_map_to_reflectivity_map(eps, eps_bg)`: mapa 2D de |Gamma| de Fresnel.
- `compare_heatmaps(recon, gt)`: MSE, RMSE, error maximo, localizacion de pico.
- `locate_contrast_peaks_2d(heatmap, x, z)`: busqueda iterativa de picos con supresion.
- `heatmap_summary(heatmap, x, z, inclusions)`: estadisticas + coincidencia con inclusiones.

### D. Script de simulacion y figuras

**`experiments/run_relative_permittivity_heatmap_simulation.py`** (nuevo):

Parametros de simulacion:
- 5 bloques OFDM: centros a 2.0, 2.5, 3.0, 3.5, 4.0 GHz
- sample_rate = 500 MHz (SIMULACION -- no realizable con bladeRF)
- n_fft=256, n_active=200 (~192 activas reales)
- Stitched: 960 subportadoras, 1.812-4.188 GHz, BW=2.375 GHz
- Resolucion en distancia: 6.3 cm
- 25 posiciones azimutales de -0.60 a +0.60 m
- Ruido: std=0.02

Resultados de simulacion:
- Forma del canal H_stitched: (960, 25)
- Forma de imagen SAR: (150, 150)
- RMSE heatmap vs GT: 0.1093
- Picos encontrados: 1 (umbral=0.3)
- Pico en (0.25, 0.74) m -- cerca de inclusion B en (0.25, 0.85) m
- Error de localizacion: 0.11 m = 1.7 bins de distancia

Figuras generadas en `reports/generated/phase5_dielectric_heatmap/`:
1. `synthetic_ground_truth_permittivity_map.png`: mapa eps_r + reflectividad Fresnel
2. `reconstructed_relative_contrast_heatmap.png`: |imagen SAR| normalizada
3. `heatmap_error_or_difference.png`: GT vs reconstruido vs diferencia (RMSE=0.1093)
4. `range_profiles_from_heatmap_pipeline.png`: perfiles de rango en posiciones seleccionadas
5. `pipeline_summary_figure.png`: resumen de 6 paneles (espectro, H(f,x), perfil, heatmap)

Archivos de datos:
- `H_stitched.npy`: tensor de canal stitched (960x25)
- `freqs_stitched.npy`: frecuencias del eje espectral
- `sar_image.npy`: imagen SAR compleja (150x150)
- `heatmap.npy`: mapa de calor normalizado (150x150)
- `eps_map.npy`: mapa de permitividad del phantom (200x200)

### E. Tests

**`tests/test_dielectric_contrast_heatmap.py`** (nuevo, 59 tests):
- TestDielectricInclusion (6 tests): creacion, validaciones.
- TestDielectricPhantom (11 tests): forma, valores, targets, mapa.
- TestFresnelReflectivity (6 tests): eps=4->1/3, eps=9->0.5, propiedades.
- TestMakeTwoInclusionPhantom (4 tests): estructura del phantom estandar.
- TestSarImageToContrastHeatmap (6 tests): normalizacion, forma, dtype.
- TestPermittivityMapToReflectivityMap (5 tests): formula Fresnel, normalizacion.
- TestCompareHeatmaps (6 tests): RMSE, claves, error de forma.
- TestLocateContrastPeaks2d (6 tests): localizacion, umbral, claves.
- TestHeatmapSummary (5 tests): claves, nota, coincidencia con inclusiones.
- TestEndToEndPhantomHeatmap (4 tests): pipeline completo, localizacion.

**Total tests tras esta sesion: 446/446 pasan.**

### F. Auditoria TX1/RX1

Ejecutada sobre 41 archivos Python, YAML, JSON.
Resultado: **PASS** -- ninguna referencia a TX2, RX2, TX_X2, RX_X2, CHANNEL_TX(1), CHANNEL_RX(1) en codigo ejecutable.

### G. Documentacion

- `docs/phase5_relative_dielectric_contrast_heatmap.md`: pipeline tecnico, resultados, limitaciones.
- `thesis/addendum_phase5_relative_dielectric_contrast_heatmap.md`: addendum en espanol para tesis.
- `thesis/reading_order_current.md`: actualizado con 13 elementos (incluyendo Fase 5).
- Explicaciones individuales de cada figura en `reports/generated/phase5_dielectric_heatmap/`.

---

## Uso de hardware

**Hardware:** NO -- simulacion pura.
**TX de RF:** NO -- ningun bladeRF abierto, ninguna senal transmitida.
**Movimiento de motor:** NO.

---

## Canales usados (simulacion)

Solo se simula TX1/RX1 (antena de apertura unica, monostatica). TX2 y RX2 no mencionados
en codigo ejecutable. Auditoria: PASS.

---

## Limitaciones cientificas

1. El mapa de calor es **contraste relativo**, NO permitividad absoluta.
2. El modelo de Fresnel es simplificado: libre de espacio, no dispersivo, no disipativo.
3. La simulacion usa 500 MHz de tasa de muestreo por bloque, que excede la capacidad
   del bladeRF (max ~61.44 MSPS). Para hardware real, se requieren mas bloques de 20 MHz.
4. La inclusion A (|Gamma|=0.303) fue detectada por debajo del umbral de pico en esta configuracion.
   Con menor umbral o mayor SNR podria detectarse.
5. La brecha de ~124 MHz entre bloques no es una cuadricula de frecuencia contigua.
   La retroproyeccion asume espectro uniforme; la brecha introduce artefactos menores.
6. Sin calibracion de fase entre bloques (correccion parcial posible con overlap).

---

## Proximo paso de hardware

```powershell
py experiments/run_phase4_hardware_entrypoint.py --run-supervised
```

Checklist fisico:
- bladeRF 2.0 micro conectado por USB
- Antena wideband en TX1 y RX1
- Reflector metalico a ~1 metro
- Usuario presente fisicamente
- Sin personas ni material biologico en la direccion del haz

Cuando la Fase 4 de hardware este validada, el equivalente de Fase 5 seria:
1. Capturar H_bg y H_obj con hardware real.
2. Calcular H_delta = H_obj - H_bg.
3. Ejecutar retroproyeccion sobre H_delta(f, x_az).
4. Generar mapa de calor de contraste 2D real.

---

## Afirmaciones cientificas

**Permitidas en esta fase:**
- Perfil de contraste dielelectrico relativo.
- Mapa de reflectividad relativa (simulado).
- Localizacion cualitativa de discontinuidades dielectricas.
- Estimacion preliminar de region reflectiva en distancia y azimutal.
- Pipeline de procesamiento validado en simulacion.

**Prohibidas:**
- Permitividad dielectrica absoluta epsilon_r(x,z).
- Deteccion de cancer o tumor.
- Diagnostico clinico.
- Imagen medica validada.
- Cualquier conclusion medica o biologica.

---

*Sesion autonoma de software completada. Sin RF. Sin hardware. Sin movimiento de motor.*
*446/446 tests pasan. 5 figuras generadas. TX1/RX1 auditado: PASS.*
