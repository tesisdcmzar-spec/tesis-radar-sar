# OFDM UWB SAR — lectura consolidada de fuentes

> Fuente canónica: este archivo.
> Espejo Notion (solo lectura humana): https://www.notion.so/3714f30e6f4c81eabd74e09d110993b9
> Última sincronización desde Notion: 2026-05-31

---

## Propósito

Esta nota convierte las fuentes OFDM/UWB/SAR subidas como PDF/DOCX en una nota legible para el proyecto. No reemplaza los PDFs originales ni copia artículos completos: resume los conceptos que deben guiar el repositorio, Claude Code y la tesis.

---

## Idea central corregida

El proyecto debe tratarse como un sistema **UWB-OFDM-SAR**. La señal de sondeo principal es OFDM, no SFCW puro.

La forma correcta de describir el sistema es:

```
símbolo OFDM conocido
→ transmisión por bladeRF
→ recepción del eco
→ sincronización
→ remoción de prefijo cíclico
→ FFT
→ estimación del canal H[k] = Y[k] / X[k]
→ repetición por bloque RF y por posición azimutal
→ H(f, x_az)
→ perfil de rango / backprojection
→ imagen 2D de reflectividad o contraste dieléctrico relativo
```

---

## Por qué OFDM es central

OFDM permite dividir una señal de banda ancha en muchas subportadoras ortogonales. En comunicaciones se usa para transmitir datos; en este proyecto se usa como **forma de onda conocida de sondeo**. Como el símbolo transmitido es conocido, se puede estimar la respuesta del canal por subportadora:

```
H[k] = Y[k] / X[k]
```

Donde:
- `X[k]` es la subportadora transmitida conocida.
- `Y[k]` es la subportadora recibida.
- `H[k]` contiene magnitud y fase del canal.

---

## Qué aporta H[k]

La respuesta por subportadora permite estudiar:
- atenuación
- fase acumulada
- retardo
- dispersión
- respuesta impulsional por IFFT
- cambios de canal entre fondo y objetivo

---

## Relación con permitividad dieléctrica

OFDM no entrega directamente un mapa de permitividad. Lo que entrega es una estimación del canal. La permitividad compleja del medio afecta la propagación electromagnética: cambia la velocidad de fase, la atenuación, la impedancia y los coeficientes de reflexión.

La cadena física defendible es:

```
contraste dieléctrico
→ cambio de impedancia / atenuación / fase
→ cambio en H[k]
→ cambio en perfil de rango / imagen SAR
→ detección de contraste relativo
```

**No afirmar todavía:**
- diagnóstico clínico
- cáncer detectado
- mapa absoluto de permitividad
- caracterización dieléctrica completa

**Sí afirmar como objetivo técnico:**
- estimación del canal electromagnético
- detección/localización de contrastes dieléctricos en simulación y luego phantom
- reconstrucción 2D experimental en condiciones controladas

---

## Fuentes y conceptos extraídos

### TIF / simulación UWB-OFDM-SAR de Josa

Conceptos clave:
- UWB mejora la resolución en rango.
- SAR mejora la resolución transversal.
- OFDM facilita estimación del canal por subportadora.
- El medio mamario debe modelarse como dispersivo y con pérdidas.
- Se usa permitividad compleja tipo Cole-Cole.
- Backprojection es adecuado por campo cercano y geometría flexible.
- En cada posición SAR se transmite el mismo símbolo OFDM conocido.
- Se obtiene H(k,m), dependiente de subportadora y posición azimutal.

Impacto en el repo:
- OFDM debe estar en `processing/ofdm_channel.py`.
- La simulación principal debe estar en `simulation/ofdm_uwb_sar_simulator.py`.
- SFCW/RX-only debe reclasificarse como validación de infraestructura.

### OFDM Radar Algorithms — Braun

Conceptos clave:
- OFDM radar usa una señal OFDM transmitida y una señal retrodispersada recibida para estimar blancos.
- Analiza estructura física de OFDM, subportadoras, CP, PAPR, parametrización, estimación de rango/Doppler e interferencias.
- La selección de parámetros OFDM afecta resolución, rango no ambiguo, SNR, procesamiento y robustez.

Impacto en el repo:
- Crear módulo de parametrización OFDM.
- Probar distintos `n_fft`, subcarrier spacing, CP y subcarrier allocation.
- Documentar PAPR y limitaciones prácticas.

### CP-OFDM SAR / ISAR

Conceptos clave:
- El prefijo cíclico suficiente convierte un canal con multitrayecto en subcanales sin ISI.
- En radar SAR/ISAR, por analogía, puede reducir interferencia entre celdas de rango.
- La longitud del CP debe cubrir el retardo máximo de la escena o swath.

Impacto en el repo:
- CP no es decoración: debe dimensionarse contra el rango máximo.
- Si CP es insuficiente, se rompe la ortogonalidad y aparece ISI/IRCI.

### UWB OFDM SAR multiple targets / Cross-range SAR with multicarrier OFDM

Conceptos clave:
- OFDM-SAR permite combinar reconstrucción en rango y cross-range.
- Las subportadoras pueden usarse para estimar historia de fase y mejorar la reconstrucción en slow-time.
- La resolución en rango depende del ancho de banda total.
- La resolución azimutal depende de la apertura sintética.

Impacto en el repo:
- La matriz final debe ser `H(f, x_az)`.
- El movimiento azimutal no es opcional para imagen 2D.

### Informe de avance bladeRF

Conceptos clave:
- bladeRF tiene limitación de ancho de banda instantáneo.
- Para sintetizar ancho de banda grande se requieren múltiples capturas por bloques.
- El movimiento azimutal multiplica la cantidad de datos y tiempo de ensayo.

Impacto en el repo:
- Diseñar captura por bloques OFDM.
- Guardar metadata por bloque y posición.
- Implementar stitching, calibración de fase y sustracción de fondo.

---

## Nueva arquitectura oficial propuesta

```
Para cada posición azimutal x_m:
    Para cada bloque RF b:
        elegir frecuencia central f_c,b
        generar símbolo OFDM conocido X_b[k]
        transmitir símbolo/frame
        recibir IQ
        sincronizar
        remover CP
        FFT
        estimar H_b[k, x_m] = Y_b[k, x_m] / X_b[k]
        guardar H_b, metadata y calidad de captura
    coser bloques en frecuencia → H_total(f, x_m)

Luego:
    calibrar / restar fondo
    IFFT sobre frecuencia → perfiles de rango
    backprojection campo cercano → imagen 2D
```

---

## Decisión importante sobre el trabajo existente

No hay que borrar lo hecho. El trabajo SFCW/RX-only validó:
- control de bladeRF
- lectura IQ
- metadata
- tests
- range profile
- postprocesamiento
- flujo de reportes

Pero debe quedar como **infraestructura preliminar**, no como arquitectura final.

---

## Próximo paso recomendado

Ejecutar una reorientación del repositorio:
- documentación oficial UWB-OFDM-SAR
- módulo OFDM offline (`processing/ofdm_channel.py`)
- simulador OFDM-UWB-SAR (`simulation/ofdm_uwb_sar_simulator.py`)
- tests
- actualización de README / CLAUDE.md / tesis
- sin hardware todavía
