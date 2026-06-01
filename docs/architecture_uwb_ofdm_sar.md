# Arquitectura oficial: UWB-OFDM-SAR

> Documento canonico de arquitectura del sistema.
> Fuente para Claude Code y para la tesis.
> Ultima actualizacion: 2026-05-31

---

## 1. Decision arquitectural

El sistema de la tesis es un **radar UWB-OFDM-SAR** para estimacion de contraste dielectrico en condiciones controladas. Esta decision corrige una clasificacion anterior en la que el trabajo se describia como "radar SFCW validado". La corrección es la siguiente:

| Componente | Clasificacion correcta |
|-----------|----------------------|
| Barridos SFCW / RX-only | Validacion de infraestructura y soporte practico de stitching |
| OFDM con simbolo conocido | **Forma de onda de sondeo principal** |
| Multiples bloques RF + azimut | Captura H(f, x_az) completa |
| Backprojection campo cercano | Reconstruccion 2D |

**Lo que SI es la arquitectura final:** UWB-OFDM-SAR.
**Lo que NO es la arquitectura final:** radar SFCW puro con barrido de frecuencia sin simbolo conocido.

---

## 2. Por que OFDM es central

OFDM (Orthogonal Frequency Division Multiplexing) divide una senal de banda ancha en muchas subportadoras ortogonales. En telecomunicaciones se usa para transmitir datos. En este proyecto se usa como **forma de onda de sondeo conocida**.

Ventaja clave: como el simbolo transmitido X[k] es conocido en cada subportadora, se puede estimar la respuesta del canal H[k] por division directa:

```
H[k] = Y[k] / X[k]
```

donde:
- `X[k]` es el simbolo OFDM transmitido conocido en la subportadora k.
- `Y[k]` es la senal recibida en esa subportadora despues de retirar el prefijo ciclico y aplicar FFT.
- `H[k]` contiene la magnitud y fase del canal electromagnetico.

Esto es cualitativamente diferente a SFCW, donde se estima H(f) por promediado coherente de IQ sin un simbolo transmitido conocido.

---

## 3. Por que SFCW/RX-only es solo validacion de infraestructura

El trabajo SFCW/RX-only realizado previamente es valioso como validacion de la infraestructura, pero NO como arquitectura final de la tesis por estas razones:

1. **Sin simbolo transmitido conocido:** En RX-only no hay transmision propia; lo recibido es ruido ambiental, no el eco de un simbolo conocido.
2. **Sin estimacion coherente del canal:** La H(f) del barrido RX-only es el promedio coherente de IQ de ruido, no una estimacion de canal calibrada.
3. **Sin imagen SAR real:** Sin TX propio y sin azimut activo, no puede generarse una imagen 2D de reflectividad.

Lo que el trabajo SFCW/RX-only si valido:
- Control del bladeRF (frecuencia, sample rate, ganancia, SC16_Q11).
- Captura IQ real (sin ruidos de USB, sin clipping, con metadata).
- Pipeline de procesamiento: DC removal, normalizacion, resta de fondo, perfil de rango.
- Tests de infraestructura (220+ tests).

---

## 4. Pipeline completo UWB-OFDM-SAR

### 4.1 Pipeline de adquisicion (activo)

```
Para cada posicion azimutal x_m:
    Para cada bloque RF con frecuencia central f_c,b:
        Generar simbolo OFDM conocido X_b[k] en subportadoras activas
        Transmitir simbolo/frame via bladeRF TX1
        Recibir eco IQ via bladeRF RX1
        Sincronizar inicio de simbolo (correlacion con preambulo)
        Retirar prefijo ciclico (CP removal)
        FFT -> Y_b[k]
        Estimar H_b[k, x_m] = Y_b[k, x_m] / X_b[k]
        Guardar H_b, metadata y metricas de calidad por bloque

    Coser bloques en frecuencia -> H_total(f, x_m)

Producto final: H(f, x_az) - cubo de datos de canal
```

### 4.2 Pipeline de procesamiento (offline)

```
H(f, x_az)
    |
    |--> Sustraccion de fondo: H_target(f, x) = H_total(f, x) - H_background(f, x)
    |
    |--> Calibracion de magnitud y fase por bloque
    |
    |--> IFFT sobre frecuencia -> perfiles de rango r(t, x_az)
    |
    |--> Backprojection campo cercano -> imagen 2D I(x, z)
    |
    |--> Interpretacion: contraste dielectrico relativo
```

---

## 5. Ecuaciones clave

### 5.1 Estimacion del canal

La ecuacion central del sistema:

```
H[k] = Y[k] / X[k]
```

Valida para cada subportadora activa k, en cada bloque RF b y en cada posicion azimutal x_m.

### 5.2 Perfil de rango

La respuesta impulsional del canal (CIR):

```
h(tau) = IFFT{H(f) * w(f)}
```

donde w(f) es una ventana de apodizacion (Hanning, Blackman) para reducir lobulos laterales. El pico de |h(tau)| corresponde al retardo de propagacion tau = 2R/c.

### 5.3 Rango desde retardo

Para un radar monostatico (TX = RX en el mismo punto):

```
R = c * tau / 2
```

### 5.4 Resolucion en rango

La resolucion en rango depende del ancho de banda efectivo total B_total:

```
dR = c / (2 * B_total)
```

Para el sistema con bladeRF limitado a BW instantaneo de ~60 MHz pero con stitching de multiples bloques:
- Un solo bloque a 40 MS/s: dR ~ 3.75 m (insuficiente)
- Stitching de N bloques con solapamiento: dR puede llegar a decenas de centimetros

Ver `docs/ofdm_bladerf_block_stitching_plan.md` para el analisis detallado.

### 5.5 Prefijo ciclico

El prefijo ciclico debe cubrir el retardo maximo de la escena para evitar ISI (interferencia entre simbolos) y IRCI (interferencia entre celdas de rango):

```
T_CP >= 2 * R_max / c
```

Para R_max = 1 m: T_CP >= 6.67 ns. A 40 MS/s: T_CP >= 1 muestra. En la practica se usan 32-64 muestras para margen de seguridad.

### 5.6 Backprojection campo cercano

Para cada pixel de imagen (x_px, z_px) y cada posicion azimutal x_ap:

```
I(x_px, z_px) = sum_{x_ap} h(R(x_ap, x_px, z_px), x_ap) * exp(+j*4*pi*f0*R/c)
```

donde:
- R = sqrt((x_ap - x_px)^2 + z_px^2) es el rango monostatico
- f0 es la frecuencia mas baja del bloque (correccion de portadora)

---

## 6. Limitacion del bladeRF: necesidad de stitching

El bladeRF 2.0 micro puede sintonizarse de 47 MHz a 6 GHz, pero su ancho de banda instantaneo maximo es de ~60 MHz (40 MHz practico). Para sintetizar varios GHz de BW, el sistema debe:

1. **Adquirir multiples bloques** con diferentes frecuencias centrales f_c,b.
2. **Estimar H_b[k]** en cada bloque.
3. **Coser los bloques en frecuencia** para obtener H_total(f).

Esta estrategia de stitching de bloques es la que permite al sistema UWB-OFDM-SAR lograr resolucion en rango de centimetros con hardware limitado a BW de decenas de MHz.

Ver `docs/ofdm_bladerf_block_stitching_plan.md` para la estrategia completa.

---

## 7. Relacion con el modelo dielectrico

OFDM no entrega directamente un mapa de permitividad absoluta. Entrega una estimacion del canal electromagnetico H(f, x_az). La permitividad compleja del medio afecta:

- La constante de propagacion gamma = alpha + j*beta
- La velocidad de fase v_ph = omega/beta
- La atenuacion e^{-alpha*d}
- La impedancia eta y el coeficiente de reflexion en interfaces

Para simulacion, se usa el modelo Cole-Cole de permitividad compleja del tejido biologico. Para la escena experimental, se usan phantoms de gel o liquidos con propiedades conocidas.

La cadena defensible:

```
Contraste dielectrico
  -> Cambio en impedancia/reflexion/atenuacion en la interfaz
  -> Cambio en H[k] (magnitud y/o fase)
  -> Cambio en perfil de rango (pico de |h(tau)|)
  -> Cambio en imagen SAR (punto brillante en I(x,z))
  -> Deteccion/localizacion de contraste dielectrico relativo
```

Ver `docs/ofdm_dielectric_interpretation.md` para el analisis completo.

---

## 8. Lo que puede y no puede afirmarse

### Puede afirmarse (claims defensibles)

- Estimacion del canal electromagnetico H[k] = Y[k]/X[k] por subportadora.
- Deteccion y localizacion de contrastes dielectricos en simulacion y luego en phantoms.
- Reconstruccion 2D experimental en condiciones controladas de laboratorio.
- Validacion de la plataforma de adquisicion con bladeRF.
- Comparacion entre condiciones de fondo y objetivo.

### No puede afirmarse todavia

- Diagnostico clinico de ninguna enfermedad.
- Deteccion de cancer de mama en sujetos humanos o animales.
- Mapa absoluto de permitividad compleja sin modelo inverso validado.
- Caracterizacion dielectrica completa del tejido.
- Comparacion directa con valores de referencia clinica.

---

## 9. Modulos del repositorio asociados a esta arquitectura

| Modulo | Funcion |
|--------|---------|
| `processing/ofdm_channel.py` | H[k]=Y[k]/X[k], CP removal, FFT, CIR, grupo de retardo |
| `simulation/ofdm_uwb_sar_simulator.py` | Simulacion de H(f, x_az), perfiles de rango, backprojection |
| `experiments/run_ofdm_uwb_sar_simulation.py` | Demo offline, sin hardware |
| `processing/range_profile.py` | IFFT con ventana y zero-padding (compartido con SFCW) |
| `processing/sar_reconstruction.py` | Backprojection (compartido con SFCW) |
| `acquisition/rx_sfcw_sweep.py` | Soporte de barrido por bloques de frecuencia (validacion) |
| `hardware/bladerf_device.py` | Abstraccion de hardware RX+TX (dry-run por defecto) |
| `hardware/safety.py` | Validadores de seguridad para TX real |

---

## 10. Estado actual del repositorio (2026-05-31)

| Componente | Estado |
|-----------|--------|
| Simulador OFDM-UWB-SAR | Implementado y validado (59 tests) |
| Modulo de canal OFDM | Implementado y validado (41 tests) |
| Barrido SFCW RX-only | Validado con hardware real (226c5b3) |
| Infraestructura TX bladeRF | Implementada, lista para experimento |
| Primer experimento TX/RX reflector | Pendiente (requiere presencia fisica) |
| Stitching de bloques OFDM | Pendiente (siguiente fase) |
| Azimut activo con motor | Pendiente |
| Imagen SAR con hardware real | Pendiente |
