---
name: radar-session-close
description: Cierra una sesión de trabajo generando un informe técnico completo de ingeniería para la tesis Radar SAR.
disable-model-invocation: true
---

Crear o actualizar un informe de sesión detallado para la tesis.

Salida principal:

* Crear un archivo nuevo en `reports/session_reports/` con nombre:
  `YYYY-MM-DD_sesion_<tema>.md`

Salida secundaria:

* Actualizar `reports/ai_session_log.md` solo como índice/resumen breve que apunte al informe completo.

El informe completo DEBE estar en español y debe ser suficientemente detallado para que el usuario pueda explicar el trabajo como propio en una tesis de ingeniería.

Longitud mínima:

* Si hubo cambios de código: mínimo 1200 palabras.
* Si solo hubo revisión/documentación: mínimo 600 palabras.
* Si no hubo actividad nueva: escribir una nota breve indicando que no hubo cambios, sin duplicar informes.

Estructura obligatoria del informe completo:

# Informe de sesión — Tesis Radar SAR

## 1. Objetivo de la sesión

Explicar qué se intentó lograr, por qué era importante y con qué fase del plan maestro se relaciona.

## 2. Contexto técnico previo

Explicar el estado del repo antes de la sesión: qué existía, qué faltaba y qué problema técnico se buscaba resolver.

## 3. Archivos creados

Por cada archivo nuevo:

* path completo
* propósito
* cantidad aproximada de líneas
* módulos o funciones principales
* por qué fue necesario
* cómo se conecta con el resto del sistema

## 4. Archivos modificados

Por cada archivo modificado:

* path completo
* qué había antes
* qué cambió
* por qué se cambió
* qué problema resolvió
* riesgos o limitaciones del cambio

## 5. Código relevante incorporado o modificado

Incluir fragmentos cortos de código cuando sean necesarios para entender la implementación.
Cada fragmento debe tener:

* path del archivo
* nombre de la función/clase
* explicación línea por línea o bloque por bloque
  No pegar archivos completos salvo que sean muy cortos.

## 6. Lógica técnica y decisiones de diseño

Explicar las decisiones de ingeniería:

* algoritmo elegido
* parámetros usados
* alternativas posibles
* por qué se eligió esta opción
* limitaciones conocidas
  Escribir como si el lector no hubiera visto el código.

## 7. Errores encontrados y solución

Por cada error:

* síntoma
* comando o test que lo detectó
* causa raíz
* cambio aplicado
* cómo se verificó que quedó resuelto

## 8. Comandos ejecutados

Listar los comandos ejecutados en orden, con resultado:

* comando
* pasó/falló
* salida importante
* si afectó archivos, datos, tests o commits

## 9. Tests y validación

Indicar:

* cuántos tests existen
* cuántos pasaron
* qué verifica cada grupo de tests
* qué falló, si algo falló
* por qué la validación es suficiente o insuficiente

## 10. Resultados y figuras

Por cada figura o salida:

* path
* qué representa
* qué muestran los ejes
* qué se esperaba ver
* qué se observó
* interpretación técnica
* limitaciones

## 11. Relación con la tesis

Explicar cómo este trabajo contribuye al objetivo general:

* adquisición
* simulación
* procesamiento DSP
* reconstrucción SAR
* validación con phantom
* redacción de capítulos
  No hacer claims clínicos. No decir que detecta cáncer real.

## 12. Fuentes y trazabilidad

Separar:

* Fuentes internas: archivos del repo, scripts legacy, configs, commits, tests, logs.
* Fuentes externas: solo si fueron proporcionadas explícitamente en el repo o por el usuario.
  Si no hubo internet, escribir: `No se consultaron fuentes externas durante esta sesión`.
  No inventar papers, links ni bibliografía.

## 13. Problemas abiertos

Listar dudas, riesgos técnicos, tareas incompletas y supuestos que deben verificarse.

## 14. Próximo paso exacto

Indicar una sola acción siguiente:

* archivo exacto a crear/modificar
* comando exacto a ejecutar
* por qué ese paso es el más lógico
* qué NO conviene hacer todavía

## 15. Commit sugerido

Proponer un mensaje de commit claro.

También actualizar `reports/ai_session_log.md` con un resumen breve de 5 a 10 líneas y un link relativo al informe completo.
