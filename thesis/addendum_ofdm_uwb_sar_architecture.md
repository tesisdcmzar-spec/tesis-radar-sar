# Addendum: Arquitectura UWB-OFDM-SAR

**Tesis:** Plataforma experimental de radar SAR de microondas para deteccion de contraste dielectrico.
**Fecha:** 2026-05-31
**Tipo:** Correccion y ampliacion arquitectural -- reemplaza la descripcion anterior de "radar SFCW".

---

## Contexto de este addendum

Los capitulos previos describieron el sistema principalmente como un radar SFCW (Stepped-Frequency Continuous Wave) con barridos RX-only. Esta descripcion era parcialmente correcta para la fase de validacion de infraestructura, pero no refleja la arquitectura final de la tesis.

Este addendum corrige la arquitectura y describe el sistema completo como se implementara.

---

## 1. Forma de onda principal: OFDM

La forma de onda de sondeo del sistema es **OFDM (Orthogonal Frequency Division Multiplexing)**, no SFCW puro. La diferencia fundamental:

| Aspecto | SFCW puro (barrido CW) | OFDM (este sistema) |
|---------|----------------------|---------------------|
| Senal transmitida | CW a una frecuencia por vez | Simbolo OFDM con N subportadoras simultaneas |
| Simbolo conocido | No (o solo el carrier) | Si: X[k] determinista |
| Estimacion del canal | Promedio coherente de IQ | H[k] = Y[k] / X[k] por subportadora |
| Eficiencia espectral | Baja (una freq. por adquisicion) | Alta (N frecuencias simultaneas) |
| Prefijo ciclico | No | Si: elimina ISI en multipath |

OFDM permite estimar H[k] en N subportadoras simultaneas con una sola transmision, lo que es mas eficiente y mas robusto que SFCW.

---

## 2. Ecuacion central: estimacion del canal

Dado un simbolo OFDM transmitido conocido X[k] y la senal recibida Y[k] (despues de remover el prefijo ciclico y aplicar FFT):

```
H[k] = Y[k] / X[k]
```

Esta ecuacion es valida para cada subportadora activa k. H[k] contiene:
- |H[k]|: magnitud del canal en la frecuencia f_k (atenuacion total)
- angle(H[k]): fase del canal (retardo de propagacion + fase de reflexion)

La respuesta impulsional del canal se obtiene por IFFT:

```
h(tau) = IFFT{H[k] * w[k]}
```

donde w[k] es una ventana de apodizacion (Hanning, Blackman). El pico de |h(tau)| corresponde al retardo de propagacion tau = 2R/c para un blanco a distancia R.

---

## 3. Producto de datos final: H(f, x_az)

Repitiendo la estimacion del canal para multiples bloques RF y multiples posiciones azimutales se obtiene el cubo de datos:

```
H(f, x_az)  (o equivalentemente  H[k, x_m])
```

donde:
- f (o k): frecuencia RF, cubriendo el BW sintetico construido por stitching de bloques
- x_az (o x_m): posicion azimutal del radar a lo largo de la apertura sintetica

Este cubo H(f, x_az) es el insumo del algoritmo de reconstruccion SAR.

---

## 4. Por que UWB: resolucion en rango

La resolucion en rango del sistema depende del ancho de banda total B:

```
dR = c / (2 * B)
```

El bladeRF tiene BW instantaneo de ~40 MHz (practico), lo que daria dR ~ 3.75 m -- insuficiente para imagenes de milimetros a centimetros.

Para lograr resolucion de 10 cm o mejor se necesita B >= 1.5 GHz. Esto se consigue mediante **stitching de bloques**:

```
B_total = N_bloques * BW_bloque_efectivo
```

Cada bloque OFDM adquiere un fragmento de BW en una frecuencia central diferente. Los bloques se calibran y cosen en frecuencia para sintetizar B_total.

---

## 5. Por que SAR: resolucion azimutal

La resolucion azimutal (cross-range) del sistema depende de la longitud de la apertura sintetica L:

```
d_az ~ lambda / 2 para campo lejano
d_az ~ D_antena / 2 para campo cercano (backprojection)
```

En campo cercano con backprojection, la resolucion azimutal efectiva mejora conforme la apertura L aumenta (hasta cierto limite geometrico). El sistema usa una plataforma mecanica que desplaza el radar sobre una apertura lineal de varios centimetros.

---

## 6. Limitacion de bladeRF y stitching de bloques

El bladeRF no puede capturar varios GHz de forma instantanea. La arquitectura de adquisicion es:

```
Para cada posicion azimutal x_m:
    Para cada bloque b con f_c,b en {f_1, f_2, ..., f_N}:
        Transmitir simbolo OFDM X_b[k]
        Recibir eco Y_b[k]
        Estimar H_b[k, x_m] = Y_b[k, x_m] / X_b[k]

    Coser H_b[k, x_m] para todos b -> H_total(f, x_m)
```

Los 15 factores que reducen el BW util por bloque se documentan en:
`docs/ofdm_bladerf_block_stitching_plan.md`

---

## 7. Modelo dielectrico y relacion con propiedades del tejido

El sistema no mide permitividad directamente. Estima el canal electromagnetico H[k], que es una funcion integral de las propiedades del medio a lo largo del trayecto de propagacion.

La permitividad compleja de los tejidos biologicos se modela con Cole-Cole:

```
epsilon*(f) = epsilon_inf + (epsilon_s - epsilon_inf) / (1 + (j*f/f_c)^(1-alpha))
              - j * sigma / (2*pi*f*epsilon_0)
```

El contraste dielectrico entre tejido sano (grasa, epsilon_r ~ 5-10) y tejido con alta contenido de agua o tumor (epsilon_r ~ 50-70) genera una diferencia en el coeficiente de reflexion:

```
Gamma = (eta_2 - eta_1) / (eta_2 + eta_1)
```

Esta diferencia se manifiesta como:
- Mayor intensidad del pico de |H[k]| en la frecuencia correspondiente a la interfaz
- Mayor amplitud del pico de |h(tau)| a la posicion de la interfaz
- Mayor intensidad en la imagen SAR en la posicion del blanco dielectrico

---

## 8. Backprojection de campo cercano

El algoritmo de reconstruccion es backprojection de campo cercano:

```
I(x_px, z_px) = sum_{x_ap} h(R(x_ap, x_px, z_px), x_ap) * exp(+j*4*pi*f0*R/c)
```

donde R es el rango monostatico (una via) desde la posicion del radar x_ap al pixel (x_px, z_px). El factor exp(+j*4*pi*f0*R/c) corrige el termino de portadora que aparece en la IFFT de una senal no-banda base.

Backprojection es elegido por:
- Adecuado para geometria de campo cercano
- No asume trayectorias rectas de onda plana
- Computacionalmente manejable para escenas pequenas

---

## 9. Claims defensibles y limitaciones

### Puede afirmarse en la tesis

1. El sistema implementa estimacion del canal electromagnetico H[k] = Y[k]/X[k] por subportadora OFDM.
2. La simulacion offline del sistema muestra que H(f, x_az) permite localizar blancos de contraste dielectrico con precision de ~10 cm en rango y ~3 cm en azimut.
3. La plataforma bladeRF adquiere senales IQ coherentes en multiples frecuencias (validado RX-only, infraestructura TX lista).
4. El pipeline completo (OFDM -> H[k] -> perfil de rango -> imagen SAR) esta implementado y validado en simulacion.

### No puede afirmarse todavia

1. Resultados experimentales con OFDM TX/RX real (pendiente).
2. Imagen SAR real con azimut activo (pendiente).
3. Caracterizacion de phantom dielectrico con el sistema (pendiente).
4. Ninguna comparacion con datos clinicos o diagnostico medico.

---

## 10. Estado del repositorio al 2026-05-31

| Modulo | Implementado | Validado | Probado con hardware |
|--------|-------------|---------|---------------------|
| `processing/ofdm_channel.py` | Si | Si (41 tests) | No |
| `simulation/ofdm_uwb_sar_simulator.py` | Si | Si (18 tests) | N/A |
| `experiments/run_ofdm_uwb_sar_simulation.py` | Si | Si (corrido, peak a 0.2 cm del target) | N/A |
| `hardware/bladerf_device.py` (RX) | Si | Si (hardware real) | Si |
| `hardware/bladerf_device.py` (TX) | Si | Si (fake backend) | No (pendiente) |
| OFDM TX/RX real | No | No | No |
| Stitching de bloques | No | No | No |
| Azimut activo | No | No | No |
