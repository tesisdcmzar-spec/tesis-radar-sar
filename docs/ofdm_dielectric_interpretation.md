# Interpretacion dielectrica de H(f, x_az) en UWB-OFDM-SAR

> Documento canonico de interpretacion fisica de los resultados.
> Limita y define los claims defensibles de la tesis.
> Ultima actualizacion: 2026-05-31

---

## 1. Que entrega el sistema

El sistema UWB-OFDM-SAR entrega:

```
H(f, x_az) = H[k, x_m]
```

Esta es una estimacion del canal electromagnetico por subportadora (k) y por posicion azimutal (x_m). H es un numero complejo con magnitud y fase.

Lo que H entrega:
- Magnitud |H[k]|: atenuacion relativa del eco en la frecuencia f_k
- Fase angle(H[k]): retardo de fase acumulado en la frecuencia f_k
- IFFT de H -> CIR -> posicion del blanco en rango
- Backprojection de H sobre (f, x_az) -> imagen 2D de reflectividad relativa

Lo que H NO entrega directamente:
- Permitividad absoluta del medio en cada punto espacial
- Conductividad electrica del tejido
- Temperatura del tejido
- Diagnostico clinico de ninguna enfermedad

---

## 2. Relacion entre propiedades dielectricas y H[k]

### 2.1 Permitividad compleja

Un medio biologico tiene permitividad compleja epsilon*(f):

```
epsilon*(f) = epsilon'(f) - j * epsilon''(f)
```

donde:
- epsilon' es la parte real (permitividad relativa, o constante dielectrica)
- epsilon'' es la parte imaginaria (relacionada con la conductividad y las perdidas)
- j es la unidad imaginaria

En tejidos biologicos, epsilon* depende fuertemente de la frecuencia (medio dispersivo) y del tipo de tejido (agua, grasa, tumor, sangre, etc.).

### 2.2 Modelo Cole-Cole

Para simulacion, el modelo Cole-Cole describe la dispersion dielectrica de los tejidos:

```
epsilon*(f) = epsilon_inf + (epsilon_s - epsilon_inf) / (1 + (j*f/f_c)^(1-alpha)) - j * sigma / (2*pi*f*epsilon_0)
```

donde:
- epsilon_inf: permitividad a frecuencia infinita
- epsilon_s: permitividad estatica (DC)
- f_c: frecuencia de relajacion caracteristica
- alpha: factor de distribucion de tiempos de relajacion (0 = Debye puro)
- sigma: conductividad ionizada

El modelo Cole-Cole es estandar en la literatura de microondas para tejidos biologicos (Gabriel et al., 1996; Josa et al.).

### 2.3 Constante de propagacion

En un medio de permitividad epsilon* y permeabilidad mu*:

```
gamma = alpha_att + j * beta = j * omega * sqrt(mu* * epsilon*)
```

donde:
- alpha_att: constante de atenuacion [Np/m] (perdidas)
- beta: constante de fase [rad/m] (velocidad de propagacion)

La velocidad de fase:
```
v_ph = omega / beta = c / Re(sqrt(epsilon*_r))
```

Para tejido biologico con alta permitividad, v_ph < c, lo que produce un retardo mayor que en el aire.

### 2.4 Impedancia y coeficiente de reflexion

En una interfaz entre dos medios con impedancias eta_1 y eta_2:

```
Gamma = (eta_2 - eta_1) / (eta_2 + eta_1)
```

donde eta = sqrt(mu/epsilon*) ~ eta_0 / sqrt(epsilon*_r).

Para una interfaz aire (epsilon_r ~ 1) con tejido graso (epsilon_r ~ 5) vs tejido tumoral (epsilon_r ~ 50):
- La diferencia de epsilon_r entre grasa y tumor es grande (factor ~10)
- Esto produce un coeficiente de reflexion mayor en el tumor que en la grasa
- El tumor aparece como un blanco mas brillante en la imagen SAR

### 2.5 Como afecta esto a H[k]

Cuando una onda OFDM atraviesa un medio heterogeneo y regresa al receptor:

1. La atenuacion exponencial e^(-2*alpha_att*d) reduce la magnitud de H[k] de forma dependiente de la frecuencia.
2. El retardo 2d/v_ph cambia la fase de H[k]: H[k] ~ exp(-j*2*pi*f*2d/v_ph).
3. El coeficiente de reflexion Gamma escala la amplitud de H[k].
4. La dispersion (variacion de v_ph con f) produce que distintas frecuencias k lleguen con distintos retardos, ensanchando el pico de la CIR.

En resumen: cualquier cambio en la permitividad del medio produce cambios en la magnitud, la fase, el retardo y la forma del pico de H(f).

---

## 3. Lo que el sistema puede detectar en la practica

### 3.1 Contraste dielectrico relativo

El sistema puede detectar:

```
Diferencia H_target(f, x) - H_background(f, x)
```

Si H_target /= H_background, existe un blanco que modifica el canal con respecto al fondo. Esta diferencia puede ser causada por:
- Un objeto con distinta permitividad (blanco dielectrico)
- Un cambio geometrico (inclusion, cavidad, superficie)
- Cambio de temperatura o estado del medio

### 3.2 Localizacion del blanco en 2D

El backprojection de la diferencia (H_target - H_background)(f, x_az) produce una imagen 2D donde:
- Los picos de intensidad corresponden a la posicion de los blancos dielectricos
- La intensidad del pico es proporcional al contraste dielectrico
- La forma del pico depende del BW (rango) y la apertura (cross-range)

### 3.3 Que puede decirse de los resultados

En experimentos controlados con phantoms:
- La posicion del pico identifica la localizacion del blanco con precision ~dR en rango y ~apertura_efectiva en cross-range.
- La intensidad del pico indica la magnitud del contraste dielectrico, no la permitividad absoluta.
- La comparacion entre phantoms con distintos contrastes dielectricos puede mostrar sensibilidad al contraste.

---

## 4. Limites y claims prohibidos

### 4.1 Claims prohibidos en la tesis

Nunca afirmar:
- "El sistema detecta cancer."
- "El sistema diagnostica tumores mamarios."
- "El sistema mide la permitividad del tejido."
- "Los resultados con phantoms son equivalentes a resultados clinicos."
- "El sistema puede reemplazar a la mamografia, ecografia o RMN."

### 4.2 Claims defensibles en la tesis

Si puede afirmarse:
- "El sistema estima el canal electromagnetico H[k] por subportadora."
- "El sistema detecta y localiza cambios de contraste dielectrico en simulacion."
- "El sistema produce imagenes 2D de reflectividad en phantoms controlados."
- "El contraste dielectrico afecta la magnitud y fase de H[k], y ese efecto es observable en los perfiles de rango y en las imagenes SAR."
- "La plataforma es un prototipo experimental para investigacion, no un dispositivo medico."

### 4.3 Declaracion etica

Este sistema es un prototipo de investigacion academica. No esta aprobado para uso clinico. Ninguna medicion se realiza sobre seres humanos ni animales. Todos los experimentos se realizan con phantoms sinteticos o sobre objetos metalicos en condiciones de laboratorio controladas.

---

## 5. Implicancias para el simulador

El simulador `simulation/ofdm_uwb_sar_simulator.py` usa un modelo libre de dispersion (v_ph = c constante). Para incluir efectos dielectricos reales en la simulacion:

1. Calcular la constante de propagacion gamma(f) usando el modelo Cole-Cole para cada tejido.
2. Aplicar el factor de atenuacion y retardo dependiente de la frecuencia a cada trayectoria.
3. Usar el coeficiente de reflexion Gamma calculado a partir de epsilon* como reflectivity del blanco.

Esta extension se planea para fases futuras despues de validar el sistema basico con blancos metalicos en aire.

---

## 6. Fuentes bibliograficas relevantes

Internamente referenciadas en `docs/sources/ofdm_uwb_sar_fuentes_consolidadas.md`:
- **Josa TIF Simulator:** simulador UWB-OFDM-SAR con medio Cole-Cole para tejido mamario.
- **Braun OFDM Radar:** parametrizacion OFDM, PAPR, sincronizacion, estimacion de canal.
- **CP-OFDM SAR:** dimension del CP para escenas SAR multi-rango.
- **Informe bladeRF:** limitaciones de BW y estrategia de bloques.

Las referencias completas deben incluirse en el capitulo de marco teorico de la tesis.
