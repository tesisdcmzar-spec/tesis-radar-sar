# Capítulo 1 — Introducción

> **Estado:** borrador — capítulo introductorio. La motivación y los objetivos se basan en la arquitectura del sistema implementada a la fecha; los resultados citados corresponden a simulación y validación offline (sin datos de hardware activo).
> **Reproducibilidad:** los parámetros cuantitativos de §1.3 y §1.4 corresponden exactamente a `configs/simulation.yaml` y a los parámetros documentados en `legacy/capturas_barrido/` (99 capturas, 100–5 980 MHz). Todos los resultados de simulación son reproducibles mediante `py experiments/run_simulation.py` (Python 3.12.5).
> **⚠ Advertencia de numeración:** existen dos archivos denominados `cap4_*.md` (`cap4_adquisicion.md` y `cap4_validacion_offline_legacy.md`). El segundo debería renombrarse a `cap5_validacion_offline_legacy.md` antes de la entrega final de la tesis. La estructura de capítulos propuesta al final de este capítulo ya refleja la numeración correcta.

---

## 1.1 Motivación

La detección no invasiva de estructuras internas en objetos físicos mediante radiación electromagnética de microondas es un problema de relevancia en múltiples áreas de la ingeniería: pruebas no destructivas de materiales (*Non-Destructive Testing*, NDT), caracterización dieléctrica de medios heterogéneos, e investigación fundamental en interacción onda-materia. En particular, los materiales que presentan contraste de permitividad eléctrica relativa ($\varepsilon_r$) frente a su entorno producen reflexiones medibles cuando son iluminados por una señal de microondas de banda suficientemente ancha.

El radar de apertura sintética (*Synthetic Aperture Radar*, SAR) de campo cercano, combinado con barridos de frecuencia progresiva (*Stepped-Frequency Continuous Wave*, SFCW), constituye una arquitectura adecuada para la reconstrucción tomográfica bidimensional de estos contrastes. A diferencia de las técnicas de imagen por resonancia magnética (IRM) o tomografía computarizada (TC), la plataforma de microondas no utiliza campos magnéticos estáticos ni radiación ionizante, y puede construirse con equipamiento de bajo costo a partir de radios definidos por software (*Software-Defined Radio*, SDR).

La presente tesis desarrolla una plataforma experimental de radar SAR de microondas de campo cercano utilizando el SDR bladeRF 2.0 micro como subsistema de radiofrecuencia y un riel azimutal motorizado para la síntesis de apertura. El objetivo principal es demostrar la factibilidad de reconstruir imágenes bidimensionales de contraste dieléctrico en fantasmas de laboratorio de geometría conocida, y documentar en detalle la cadena de procesamiento de señal asociada.

**Alcance:** este trabajo es de naturaleza experimental y de validación de software. Los experimentos se realizan exclusivamente con fantasmas dieléctricos de laboratorio. No se realiza ningún experimento en tejido biológico, en personas, ni en animales. No se realizan afirmaciones de diagnóstico médico o clínico de ningún tipo.

---

## 1.2 Planteamiento del problema

Las plataformas SAR de microondas de campo cercano de bajo costo presentan varios desafíos de ingeniería que no están completamente resueltos en la literatura orientada a hardware comercial:

1. **Integración hardware-software.** Coordinar la sintonización de frecuencia de un SDR, la adquisición coherente de muestras IQ y el control de posición de un riel motorizado requiere un diseño cuidadoso de la cadena de adquisición para garantizar la coherencia de fase entre barridos.

2. **Calibración radiométrica.** La respuesta en frecuencia del sistema RF (cable, conector, ganancia dependiente de frecuencia del SDR) introduce distorsión sobre la señal recibida. Sin calibración, los perfiles de rango contienen artefactos atribuibles al hardware, no al escenario de medición.

3. **Sustracción de fondo.** La reflexión estática del entorno de medición (*clutter*) domina la señal recibida en la mayoría de escenarios de campo cercano. La sustracción de una captura de referencia (*empty scene*) es necesaria para extraer la señal del blanco.

4. **Reconstrucción 2D.** El algoritmo de retroproyección (*backprojection*) SAR requiere una coherencia de fase estricta entre posiciones de apertura. Errores de posicionamiento del orden de la décima parte de la longitud de onda degradan significativamente la imagen reconstruida.

5. **Validación con datos simulados.** Antes de operar el hardware, es necesario validar el pipeline completo (desde la respuesta SFCW hasta la imagen 2D) con señales sintéticas cuya respuesta correcta es conocida, para garantizar que los resultados del hardware puedan interpretarse correctamente.

Este trabajo aborda estas limitaciones de forma progresiva: primero mediante simulación sintética, luego mediante validación offline con capturas archivadas, y finalmente mediante experimentos controlados con hardware activo.

---

## 1.3 Objetivos

### 1.3.1 Objetivo general

Diseñar, implementar y validar una plataforma experimental de radar SAR de microondas de campo cercano capaz de reconstruir imágenes bidimensionales de contraste dieléctrico en fantasmas de laboratorio, utilizando el SDR bladeRF 2.0 micro y un riel azimutal motorizado.

### 1.3.2 Objetivos específicos

1. Implementar y validar mediante simulación sintética el pipeline de procesamiento SFCW–SAR: modelo de señal, generación de respuesta en frecuencia, perfiles de rango 1D e imagen de retroproyección 2D.

2. Construir y validar un cargador de capturas IQ (`acquisition/load_sfcw_capture.py`) compatible con múltiples formatos de datos archivados y con la interfaz `SyntheticScan` del pipeline de procesamiento.

3. Analizar el conjunto de capturas legacy disponibles (`legacy/capturas_barrido/`, 99 archivos, 100–5 980 MHz) para verificar la correcta operación del pipeline sobre datos reales de hardware en modo offline.

4. Implementar la abstracción hardware segura (`hardware/bladerf_device.py`) con modo de ensayo en seco y compuerta de seguridad explícita para transmisión RF.

5. Diseñar e implementar el protocolo de adquisición completo: barrido SFCW coordinado con movimiento del riel azimutal, sustracción de fondo y almacenamiento de metadatos de experimento.

6. Obtener y analizar imágenes SAR 2D de al menos un fantasma dieléctrico de geometría conocida bajo condiciones de laboratorio controladas.

7. Documentar todos los resultados, limitaciones y parámetros de reproducibilidad de manera que soporten la elaboración de la tesis de pregrado.

---

## 1.4 Hipótesis de trabajo

Una plataforma de radar SAR de campo cercano construida con el SDR bladeRF 2.0 micro (rango de sintonía 47 MHz–6 GHz, ADC de 12 bits, 40 MHz de tasa de muestreo) y un riel azimutal motorizado de 30 cm puede producir, mediante barridos SFCW de ancho de banda efectivo $B \leq 5{,}88$ GHz y apertura sintética de $N_{\text{az}} \geq 8$ posiciones coherentes, imágenes 2D con:

- **Resolución en rango** teórica $\delta r = c/(2B)$:
  - Para $B = 5{,}88$ GHz: $\delta r \approx 2{,}55$ cm.
  - Para $B = 2$ GHz (banda práctica con antena de banda limitada): $\delta r \approx 7{,}5$ cm.

- **Resolución transversal** determinada por la longitud de apertura $L_{\text{az}}$ y el ángulo de visión.

Esta hipótesis se sustenta en los resultados de simulación validados en el Capítulo 3, donde se obtuvo una resolución en rango de 2.55 cm y una resolución transversal de 4 cm con los parámetros nominales del sistema.

La confirmación experimental de esta hipótesis sobre fantasmas dieléctricos constituye el objetivo principal de la fase de hardware del proyecto.

---

## 1.5 Metodología

El desarrollo del proyecto se organiza en fases sucesivas con criterios de cierre explícitos antes de avanzar a la siguiente:

**Fase 1 — Simulación sintética** *(completada)*
Implementación del pipeline completo de simulación (señal SFCW sintética → perfil de rango → imagen SAR 2D) y validación mediante phantoms sintéticos de blancos puntuales con resolución conocida. Resultado: 12 tests unitarios aprobados; resolución medida concordante con la teoría.

**Fase 2 — Validación offline** *(completada)*
Implementación del cargador de capturas legacy, inspección de 99 archivos `.npy` archivados (100–5 980 MHz), generación de perfiles de rango 1D y documentación de limitaciones de apertura única. Resultado: 31 tests aprobados; perfiles de rango reproducibles sin hardware activo.

**Fase 3 — Abstracción hardware segura** *(en curso)*
Implementación de `hardware/bladerf_device.py` con modo *dry-run*, compuerta `CONFIRM HARDWARE RUN`, registro de operaciones y límites software de frecuencia y ganancia.

**Fase 4 — Protocolo de adquisición completo** *(pendiente)*
Script de barrido coordinado (bladeRF + riel azimutal), sustracción de fondo, almacenamiento de sesión con metadatos.

**Fase 5 — Experimentos con fantasma** *(pendiente)*
Adquisición controlada con fantasma dieléctrico de geometría conocida, reconstrucción 2D, comparación con simulación.

**Fase 6 — Análisis y documentación final** *(pendiente)*
Caracterización de resolución experimental vs. teórica, evaluación de limitaciones, redacción final de la tesis.

---

## 1.6 Contribuciones del trabajo

Las contribuciones técnicas concretas de este proyecto son:

1. **Pipeline de simulación SFCW–SAR:** implementación Python modular (`simulation/`, `processing/`) con 12 tests de regresión y configuración reproducible mediante archivo YAML.

2. **Cargador unificado de capturas IQ:** módulo `acquisition/load_sfcw_capture.py` compatible con formato de archivo único (`.npy`), directorio de capturas per-frecuencia (formato legacy), y sesión estructurada futura, con 18 tests de regresión sobre fixtures sintéticos.

3. **Análisis offline de capturas legacy:** script `experiments/run_legacy_offline_analysis.py` que procesa 99 capturas archivadas, genera perfiles de rango y figuras de respuesta en frecuencia, y escribe un informe Markdown estructurado.

4. **Documentación de tesis reproducible:** todos los capítulos incluyen referencias a commits, scripts y archivos de configuración específicos para garantizar la trazabilidad de los resultados.

---

## 1.7 Estructura de la tesis

La tesis se organiza en los siguientes capítulos:

| Capítulo | Título | Contenido principal |
|----------|--------|---------------------|
| 1 | Introducción | Motivación, objetivos, hipótesis, metodología y estructura |
| 2 | Marco Teórico | SAR, SFCW, retroproyección, resolución, bladeRF |
| 3 | Validación mediante Simulación Sintética | Pipeline de simulación, phantoms sintéticos, resultados de resolución |
| 4 | Sistema de Adquisición SFCW | Hardware bladeRF, protocolo de barrido, cargador de datos |
| 5 | Validación Offline con Capturas Legacy | Análisis de 99 capturas archivadas, perfiles de rango 1D, limitaciones |
| 6 | Experimentos con Fantasma Dieléctrico | *(pendiente)* Adquisición, calibración, imagen SAR 2D |
| 7 | Conclusiones y Trabajo Futuro | Resultados finales, limitaciones, extensiones |

> **Nota para la entrega:** el archivo `thesis/cap4_validacion_offline_legacy.md` actualmente lleva el prefijo `cap4_*` por razones históricas de desarrollo, pero su contenido corresponde al **Capítulo 5** de la estructura anterior. Debe renombrarse antes de la entrega del borrador final.

---

## 1.8 Limitaciones del alcance

Este trabajo declara explícitamente las siguientes limitaciones:

- **Sin afirmaciones clínicas.** Los experimentos se realizan exclusivamente con fantasmas dieléctricos de laboratorio (cilindros, esferas, o moldes de gel de agar con inclusiones). No se realizan experimentos en tejido humano, animal, ni en personas.

- **Sistema de campo cercano.** La plataforma opera en la región de campo cercano (distancia blanco-antena $< 1$ m). Los resultados no son extrapolables directamente a aplicaciones de campo lejano.

- **Modelo monoestático.** La plataforma utiliza una sola antena en modo transmisor/receptor (*monostatic*). No se modela ni mide la respuesta biestática.

- **Medio homogéneo.** El modelo de retroproyección implementado asume propagación en espacio libre (sin pérdidas). No se modelan efectos de permitividad del medio de acoplamiento.

- **Coherencia de fase offline.** La validación offline (Fase 2) utiliza capturas estáticas de una sola posición azimutal. No se ha verificado la coherencia de fase entre barridos independientes con el hardware activo.

---

*Este capítulo es parte de la tesis de pregrado en Telecomunicaciones. Plataforma experimental para investigación en laboratorio. Sin afirmaciones médicas ni clínicas.*
