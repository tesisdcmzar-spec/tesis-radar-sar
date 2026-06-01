# Configuracion del experimento de reflector metalico

## Objetivo

Realizar la primera prueba supervisada TX/RX con antenas reales y un reflector metalico
a distancia conocida (aproximadamente 1 m), para verificar que el perfil de rango muestra
un pico coherente cerca de la distancia esperada.

**Este experimento no es SAR. No es una prueba medica. No involucra personas ni material biologico.**

---

## Limitacion del equipo disponible

No se dispone de carga de 50 ohmios ni atenuador externo en esta sesion.
La prueba se realiza directamente con antenas TX y RX separadas, apuntando al reflector.
Esta limitacion se documenta explicitamente en el informe de sesion.
El riesgo de transmision directa entre antenas es bajo dado que:
- TX gain es el minimo conservador (-20 dB).
- La duracion de TX por frecuencia es <= 20 ms.
- Las antenas se mantienen separadas fisicamente.

---

## Materiales necesarios

- bladeRF 2.0 micro conectado por USB.
- Antena TX conectada al puerto TX1 del bladeRF.
- Antena RX conectada al puerto RX1 del bladeRF.
- Reflector metalico (placa de acero o aluminio de al menos 20x20 cm, o superficie plana metalica equivalente).
- Cinta metrica o regla para medir la distancia entre las antenas y el reflector.
- Cable USB de alta calidad (el mismo que funciono en las sesiones RX anteriores).
- Computadora con bladeRF conectado y entorno Python activo.
- Usuario fisicamente presente durante toda la transmision.

---

## Montaje fisico

### Paso 1: Conexion de antenas

1. Conectar la antena TX al puerto marcado **TX1** en el bladeRF.
2. Conectar la antena RX al puerto marcado **RX1** en el bladeRF.
3. Verificar que los conectores esten bien apretados (SMA o U.FL segun modelo).
4. **No conectar TX y RX al mismo puerto ni entre si.**

### Paso 2: Colocacion del reflector

1. Colocar el reflector metalico sobre una superficie plana, apoyado verticalmente o a 45 grados.
2. Medir la distancia desde el plano de las antenas hasta la superficie del reflector con cinta metrica.
3. Anotar la distancia exacta medida (objetivo: 1.0 m; rango aceptable: 0.5 m a 3.0 m).
4. Asegurarse de que el reflector sea la unica superficie reflectante dominante frente a las antenas.

### Paso 3: Orientacion de las antenas

1. Apuntar ambas antenas (TX y RX) hacia el reflector metalico.
2. Mantener las antenas proximas entre si pero sin contacto directo.
3. Las antenas deben estar fijas durante toda la captura.
4. No mover las antenas entre la captura de fondo y la captura con reflector.

### Paso 4: Zona de seguridad

1. **Verificar que no haya personas en la direccion de las antenas durante la transmision.**
2. Mantener una distancia de al menos 0.5 m entre cualquier persona y las antenas mientras el software esta ejecutandose en modo real.
3. El bladeRF opera con una potencia de salida maxima de aproximadamente 6 dBm (~4 mW). Con ganancia TX de -20 dB se estima una potencia mucho menor. Aun asi, no apuntar directamente a ojos ni equipos sensibles.

---

## Secuencia de captura

### Captura de fondo (background)

1. Retirar el reflector metalico del area de prueba, o cubrir la zona con material absorbente si es posible.
2. Si retirar el reflector no es posible, documentar la limitacion y proceder solo con captura de reflector.
3. Ejecutar el script con `--background` para capturar H_background(f).
4. Guardar los datos en `data/raw/tx_rx_reflector/background/`.

### Captura con reflector

1. Colocar el reflector en la posicion medida (sin moverlo desde el paso de montaje).
2. Ejecutar el script con `--reflector` para capturar H_reflector(f).
3. Guardar los datos en `data/raw/tx_rx_reflector/reflector/`.

### Analisis

1. Calcular H_target(f) = H_reflector(f) - H_background(f).
2. Aplicar IFFT con ventana Hanning y zero-padding para obtener el perfil de rango.
3. Identificar el bin de pico mas prominente.
4. Comparar con la distancia medida del reflector.
5. Documentar si el pico aparece dentro de +/- 0.5 m de la distancia esperada.

---

## Lo que este experimento NO valida

- No es SAR. No hay movimiento de apertura. No hay imagen 2D.
- No es una prueba de deteccion de cancer ni de tejido biologico.
- No es una caracterizacion dielectrica.
- No es una prueba clinica ni medica de ninguna clase.
- Un pico visible en el perfil de rango cerca de 1 m indica que el sistema TX/RX
  funciona como radar SFCW simple. No implica ninguna aplicacion medica ni de imagen avanzada.

---

## Frase de confirmacion requerida antes de TX

Antes de que el software inicie la transmision real, el script solicitara que el usuario
escriba exactamente las dos frases siguientes en la consola:

```
REFLECTOR SETUP READY
CONFIRM HARDWARE RUN
```

No se acepta ningun otro texto. Las frases deben escribirse exactamente como aparecen,
sin tildes, sin comillas, en mayusculas.

---

## Limites de configuracion RF conservadores

| Parametro              | Valor        |
|------------------------|--------------|
| TX gain                | -20 dB       |
| Frecuencia piloto      | 2.400 GHz    |
| Duracion TX piloto     | 20 ms        |
| SFCW inicio            | 2.300 GHz    |
| SFCW fin               | 2.500 GHz    |
| Paso SFCW              | 20 MHz       |
| Puntos SFCW            | 11           |
| Duracion TX/frecuencia | 20 ms        |
| Sample rate            | 1 MS/s       |
| Ancho de banda         | 1 MHz        |
| RX gain                | 20 dB        |

---

## Condiciones que detienen el experimento

El software detendera la transmision si ocurre cualquiera de las siguientes condiciones:

- Error USB o de hardware del bladeRF.
- Fallo en la prueba piloto.
- El usuario no proporciona las frases de confirmacion exactas.
- Cualquier flag de sujeto humano, maniqui, material biologico, motor o SAR esta activo.

En caso de error, no reintentar automaticamente. Documentar el error y detener la sesion.
