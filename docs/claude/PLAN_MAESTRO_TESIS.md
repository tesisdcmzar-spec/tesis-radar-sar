# PLAN MAESTRO — Tesis Radar SAR de microondas

Documento de planificación operativa generado para el proyecto de tesis.
Repositorio: `C:\tesis-radar-sar` · GitHub: `tesisdcmzar-spec/tesis-radar-sar` (privado)
Entorno: Windows nativo + PowerShell · Python · bladeRF · Claude Code (Sonnet/Opus)

> Este documento contiene 8 entregables. Cada uno es accionable. Los bloques de código se copian
> directamente a los archivos correspondientes del repo.

---

## DELIVERABLE 1 — Estructura del repositorio limpio

```
tesis-radar-sar/
├── CLAUDE.md                  # Memoria permanente de Claude Code (ver Deliverable 2)
├── CLAUDE.local.md            # Preferencias personales NO versionadas (no subir a Git)
├── README.md                  # Descripción general del proyecto
├── .gitignore                 # Protege datos crudos, secretos y settings locales
├── .claude/
│   ├── settings.json          # Permisos conservadores
│   └── skills/                # Las 9 skills (ver Deliverable 4)
│       └── radar-*/SKILL.md
├── docs/
│   └── claude/                # Docs largos que NO se cargan en cada sesión
│       ├── PHASE_PLAN.md
│       ├── TOKEN_BUDGET_RULES.md
│       ├── PROMPT_LIBRARY.md
│       └── SESSION_WORKFLOW.md
├── configs/                   # Configuraciones YAML (parámetros de barrido, phantom, etc.)
│   ├── simulation.yaml
│   ├── phantom_low_power.yaml
│   └── benchmark.yaml
├── hardware/                  # Abstracciones de hardware
│   ├── bladerf_device.py      # Capa bladeRF (TX/RX, full-duplex, dry-run)
│   ├── azimuth_stage.py       # Control del eje azimutal (homing, límites, dry-run)
│   └── safety.py              # Chequeos de seguridad centralizados
├── acquisition/               # Adquisición de señal
│   ├── sfcw_sweep.py          # Barrido en frecuencia
│   ├── full_duplex_capture.py # Captura full-duplex
│   └── scan_session.py        # Orquestación de sesión de escaneo
├── processing/                # Procesamiento DSP
│   ├── background_subtraction.py
│   ├── stitch_frequency_steps.py
│   ├── phase_correction.py
│   ├── range_profile.py
│   └── sar_reconstruction.py
├── simulation/                # Pipeline simulado (sin hardware)
│   ├── phantom_model.py
│   └── synthetic_scan.py
├── experiments/               # Scripts ejecutables
│   ├── run_scan.py
│   └── benchmark_sweep.py
├── data/                      # Datos (IGNORADOS por Git si son grandes)
│   ├── raw/                   # Capturas I/Q crudas .npy — NUNCA versionar ni cargar en contexto
│   └── processed/             # Datos calibrados/intermedios
├── reports/                   # Logs y figuras
│   ├── session_logs/          # Informes de sesión (.md) — ver Deliverable 5
│   └── generated/             # Figuras generadas
├── thesis/                    # Material de tesis
│   ├── chapters/              # Secciones redactadas
│   └── figures/               # Figuras finales con caption
├── legacy/                    # Scripts viejos que ya funcionan — referencia, no se editan
└── tests/                     # Tests unitarios y smoke tests
```

### Qué va a `legacy/` vs qué se refactoriza primero

**A `legacy/` (copiar tal cual, NO editar):** todos tus scripts actuales de pruebas — RX,
TX, full-duplex, barridos, estimación de canal OFDM, graficado. Son tu fuente de verdad de
parámetros de hardware que ya funcionan. Claude Code los lee como referencia pero nunca los modifica.

**Refactorización prioritaria (en este orden):**
1. El script de RX/captura que mejor funcione → base de `hardware/bladerf_device.py`
2. El script de barrido SFCW → base de `acquisition/sfcw_sweep.py`
3. El script de estimación de canal OFDM → referencia para el módulo de sondeo

**Regla:** nada en `legacy/` se borra nunca. Si algo se refactoriza, se crea nuevo en su carpeta
modular y el original queda intacto en `legacy/` como respaldo.

---

## DELIVERABLE 2 — CLAUDE.md mejorado

Tu `CLAUDE.md` actual ya era bueno. Esta versión agrega: regla explícita de `legacy/`, formato
de commits, y una nota sobre el límite de 200 líneas. Sigue bajo 200 líneas. Reemplazá el actual.

```markdown
# CLAUDE.md — Radar SAR Thesis Project

Project: undergraduate telecommunications thesis. Build an experimental microwave SAR radar
platform using bladeRF, SFCW/OFDM sweeps, azimuth motion, DSP, and 2D image reconstruction
for dielectric-contrast phantoms.

## Environment
- Native Windows + PowerShell. Do NOT suggest WSL unless the user explicitly asks.
- Main language: Python. Hardware: bladeRF SDR + Arduino/ESP32/GRBL/FluidNC azimuth stage.
- Scope: simulation, phantom experiments, controlled lab validation.
  No clinical claims, no patient/person tests.

## Working rules
1. Be concise. English for code, filenames, docstrings, technical docs. Spanish only if asked.
2. Before editing code, inspect only relevant files and propose a short plan.
3. Prefer small reversible changes. Do NOT rewrite working acquisition scripts unless requested.
4. Preserve physical meaning: amplitude, phase, sample rate, center frequency, bandwidth, gain,
   azimuth position, timestamps, config version, calibration state.
5. Do NOT read large raw datasets (*.npy, *.bin, large *.csv). Write scripts that report
   shape, dtype, metadata, stats, and small previews instead.
6. Simulation and tests BEFORE real hardware.
7. Keep raw data, processed data, figures, reports, and thesis text separated.
8. Hardware safety first: dry-run mode, homing, soft limits, emergency-stop notes, logs,
   and explicit user approval before RF transmission or motor motion.

## legacy/ rule
- legacy/ contains old working scripts. They are the source of truth for known-good hardware
  parameters. NEVER edit or delete files in legacy/. Read them as reference only.
- When refactoring, create a new modular file in its proper folder. Leave the legacy original intact.

## Repo layout
- hardware/   : bladeRF and azimuth-stage abstractions + safety.py
- acquisition/: SFCW/OFDM capture and scan sessions
- processing/ : background subtraction, stitching, phase correction, range profiles, SAR recon
- simulation/ : synthetic phantoms and synthetic scans
- experiments/: runnable scripts
- configs/    : YAML configs
- tests/      : unit and smoke tests
- reports/    : session_logs/ and generated/ figures
- thesis/     : chapters and figures
- legacy/     : old working scripts (read-only reference)

## Safe commands (no approval needed)
git status / git diff / git log --oneline -10 / python --version / py --version / pytest

## Danger zone (explicit approval required, in the current session, every time)
RF transmission, motor movement, firmware flashing, file deletion, credential access,
long full scans. The user must type CONFIRM HARDWARE RUN before any RF or motor action.

## Commit convention
Short imperative English messages: "Add SFCW sweep dry-run mode", "Fix DC offset in range profile".
Suggest a commit message at the end of each task. The user commits manually.

## This file
Keep under 200 lines. Long procedures live in docs/claude/ or in skills, loaded only when needed.
```

---

## DELIVERABLE 3 — Plan de fases con seguimiento de avance medible

10 fases (incluí Fase 0 de setup, que ya completaste parcialmente). Cada checkbox marcado suma
al porcentaje total. Total de checkboxes: **48**.

```
## Fase 0 — Setup del repositorio  [CASI COMPLETA]
Goal: repo limpio, Git + GitHub, pack de Claude Code instalado.
Deliverable: repo versionado y subido a GitHub privado.
Effort: 0.5 día. Skill: /radar-repo-audit
Checkboxes:
- [x] Carpeta C:\tesis-radar-sar creada
- [x] Git inicializado y conectado a GitHub privado
- [x] Pack de Claude Code commiteado (CLAUDE.md, skills, settings, docs)
- [ ] Scripts viejos movidos a legacy/
- [ ] CLAUDE.md actualizado a la versión mejorada (Deliverable 2)

## Fase 1 — Auditoría y orden  [SIGUIENTE]
Goal: que Claude Code entienda el repo y proponga el primer paso seguro.
Deliverable: informe de auditoría + 3 commits seguros propuestos.
Effort: 0.5 día. Skill: /radar-repo-audit
Checkboxes:
- [ ] Inventario de scripts en legacy/ clasificados (RX/TX/sweep/OFDM/plot)
- [ ] README.md con descripción del proyecto
- [ ] configs/ con plantillas YAML iniciales
- [ ] Primer checkpoint de Git con el repo ordenado

## Fase 2 — Simulación primero
Goal: pipeline SFCW/SAR completo sin hardware.
Deliverable: phantom sintético + imagen 2D reconstruida + tests.
Effort: 4–6 días. Skill: /radar-simulation-first
Checkboxes:
- [ ] simulation/phantom_model.py con blanco conocido
- [ ] simulation/synthetic_scan.py genera H(f, x_az)
- [ ] processing/range_profile.py (IFFT)
- [ ] processing/sar_reconstruction.py (delay-and-sum o backprojection)
- [ ] Test que reconstruye un blanco simulado en posición conocida
- [ ] Figura de ejemplo en reports/generated/

## Fase 3 — Capa bladeRF
Goal: encapsular config/TX/RX/full-duplex sin romper lo que ya funciona.
Deliverable: hardware/bladerf_device.py con dry-run y tests.
Effort: 4–6 días. Skill: /radar-bladerf-layer legacy/<script>
Checkboxes:
- [ ] Clase BladeRFDevice con config de freq/sample rate/BW/ganancia
- [ ] Modo dry-run/mock para tests sin hardware
- [ ] Validación de rangos de parámetros antes de llamar al hardware
- [ ] Comando read-only de info de hardware
- [ ] Generación centralizada de metadata
- [ ] Tests del modo mock pasando

## Fase 4 — Barrido en frecuencia + sondeo OFDM
Goal: automatizar SFCW, medir ancho efectivo, estimar H=Y/X.
Deliverable: acquisition/sfcw_sweep.py + esquema de metadata + benchmarks.
Effort: 5–7 días. Skill: (prompt directo, ver PROMPT_LIBRARY)
Checkboxes:
- [ ] sfcw_sweep.py con modo dry-run
- [ ] full_duplex_capture.py
- [ ] Esquema de metadata JSON por captura
- [ ] Benchmark de tiempos con distintos pasos
- [ ] Gráfico de magnitud/fase de H estimado

## Fase 5 — Movimiento azimutal
Goal: controlar el eje con seguridad, primero en modo seco.
Deliverable: hardware/azimuth_stage.py con simulador dry-run.
Effort: 5–7 días. Skill: (prompt directo)
Checkboxes:
- [ ] AzimuthStage con simulador dry-run primero
- [ ] Homing, movimiento absoluto, soft limits
- [ ] Logs de posición y tiempos de estabilización
- [ ] Notas de botón de emergencia y finales de carrera
- [ ] Wrapper serial real (sin mover hardware aún)

## Fase 6 — Sesión de escaneo integrada
Goal: combinar movimiento + barrido SFCW por punto.
Deliverable: acquisition/scan_session.py con manifest y resume/abort.
Effort: 4–6 días. Skill: /radar-scan-session
Checkboxes:
- [ ] Orquestación posición → settle → sweep → save → validate → continue
- [ ] Modo dry-run por defecto
- [ ] Manifest de sesión con timestamp + git hash + config
- [ ] Metadata por posición azimutal
- [ ] Diseño de abort/resume

## Fase 7 — Pipeline DSP y stitching
Goal: limpiar I/Q, calibrar, unir bloques, obtener perfiles de rango.
Deliverable: pipeline DSP documentado + figuras intermedias.
Effort: 6–8 días. Skill: /radar-dsp-pipeline <metadata>
Checkboxes:
- [ ] Corrección de DC offset + normalización
- [ ] Sustracción de fondo / direct leakage
- [ ] Stitching de bloques con manejo de solapamiento
- [ ] Corrección de fase entre bloques
- [ ] Perfiles de rango por IFFT
- [ ] Métricas: ancho efectivo, range-bin spacing, SNR/fondo

## Fase 8 — Reconstrucción SAR 2D y validación
Goal: backprojection en campo cercano, validar con simulación y phantom.
Deliverable: imagen 2D de phantom conocido + métricas.
Effort: 6–8 días. Skill: (prompt directo)
Checkboxes:
- [ ] Backprojection/delay-and-sum para campo cercano
- [ ] Validación con caso simulado
- [ ] Figura de resultado con phantom
- [ ] Métricas: error de localización, contraste, SNR/fondo, tiempo de escaneo

## Fase 9 — Documentación de tesis
Goal: convertir resultados en texto defendible.
Deliverable: secciones de tesis + figuras con caption + limitaciones.
Effort: continuo. Skill: /radar-thesis-docs reports/<log>
Checkboxes:
- [ ] Logs de experimentos ordenados
- [ ] Figuras con caption y numeración
- [ ] Texto de método/resultado/interpretación/limitación
- [ ] Sección de futuras líneas de trabajo
```

### Cálculo de avance

```
avance % = (checkboxes marcados / 48) × 100
```

### Barra de progreso para informes (formato texto)

```
[██░░░░░░░░░░░░░░░░░░]  8% — Fase 0 de 9 (setup casi completo)
[████░░░░░░░░░░░░░░░░] 20% — Fase 2 activa (simulación)
[██████████░░░░░░░░░░] 50% — Fase 5 activa (movimiento azimutal)
[████████████████████] 100% — Tesis completa
```

Regla: 20 bloques en total; bloques llenos = round(avance% / 5).

> **Camino crítico:** depende de tu fecha de defensa. Decime la fecha límite y marco qué fases
> son críticas y cuáles se pueden recortar si el tiempo aprieta. (Ver pregunta al final.)

---

## DELIVERABLE 4 — Revisión de skills (las 9)

| Skill | Estado | Comentario |
|-------|--------|------------|
| radar-session-start | `[OK]` | Read-only, conciso, correcto. Sin cambios. |
| radar-session-close | `[OK]` | Genera log compacto. Bien. Ver template en Deliverable 5. |
| radar-simulation-first | `[OK]` | Cubre módulos y requisitos. Bien. |
| radar-scan-session | `[OK]` | Dry-run por defecto + manifest. Bien. |
| radar-dsp-pipeline | `[OK]` | Etapas correctas, regla de no cargar arrays. Bien. |
| radar-thesis-docs | `[OK]` | Español, sin claims clínicos. Bien. |
| radar-repo-audit | `[OK]` | Read-only, propone commits. Bien. |
| radar-safe-refactor | `[OK]` | Conservador, preserva parámetros. Bien. |
| radar-bladerf-layer | `[IMPROVED]` | Buena base; ver versión mejorada abajo. |

Las 8 primeras quedan como están. Solo `radar-bladerf-layer` recibe una mejora menor: agregar
la regla explícita de leer desde `legacy/` y exigir `CONFIRM HARDWARE RUN`.

### radar-bladerf-layer (versión mejorada)

```markdown
---
name: radar-bladerf-layer
description: Design or refactor the Python bladeRF abstraction layer while protecting working acquisition scripts.
argument-hint: "<reference-script-or-folder>"
disable-model-invocation: true
---

Reference: $ARGUMENTS

Goal: create or improve hardware/bladerf_device.py without breaking working scripts.

Source of truth: read known-good parameters from legacy/ reference scripts. Do NOT edit legacy/.

Requirements:
1. Preserve known-good hardware parameters from the reference scripts.
2. Support configuration of frequency, sample rate, bandwidth, gains, TX/RX, and full-duplex capture.
3. Add dry-run/mock mode for tests (no USB, no hardware).
4. Centralize metadata generation.
5. Validate parameter ranges before any hardware call.
6. Log configuration and errors.
7. Never run real bladeRF commands. Real RX/TX requires the user to type CONFIRM HARDWARE RUN
   in the current session.

Output a short implementation plan BEFORE editing. Wait for approval.
```

---

## DELIVERABLE 5 — Template de informe de sesión (español)

Guardado por Claude Code vía `/radar-session-close` en `reports/session_logs/AAAA-MM-DD_sesion_N.md`.

```markdown
# Informe de sesión — Tesis Radar SAR

**Fecha:** AAAA-MM-DD
**Sesión N°:** _
**Fase activa:** Fase _ de 9 — [nombre]
**Avance de tesis:** [████░░░░░░░░░░░░░░░░] __% (XX/48 hitos)

## Objetivo de la sesión
[Una o dos oraciones: qué se buscaba lograr.]

## Tareas completadas
- [tarea concreta 1]
- [tarea concreta 2]

## Archivos modificados
- ruta/archivo.py — [qué cambió, en una línea]

## Tests ejecutados
- comando: `python -m pytest tests/...`
- resultado: [pasaron / fallaron / N de M]

## Resultados y figuras
- [figura o métrica producida, con ruta en reports/generated/]

## Acciones de hardware
none / simulado (dry-run) / real (requirió CONFIRM HARDWARE RUN)

## Problemas abiertos
- [lo que quedó sin resolver]

## Próximo paso recomendado
[la acción más segura y útil para la próxima sesión]

## Commit sugerido
`git commit -m "..."`
```

### Cómo subirlo a Notion (costo casi nulo)

Una vez generado el `.md` local, traés el contenido a un chat de Claude.ai con Notion conectado
y pedís: *"subí este informe como página nueva bajo TESIS - Claude"*. La escritura a Notion vía
MCP es una llamada chica, no carga archivos pesados en contexto. Tu página destino es
`TESIS - Claude` (ID `3704f30e-6f4c-8083-b0fa-db1e8b1fde0c`). Desde ahí movés manualmente a la
página de fuentes lo que quieras mostrar.

---

## DELIVERABLE 6 — Reglas de token budget (mejoradas)

Reemplazá `docs/claude/TOKEN_BUDGET_RULES.md` con esto.

```markdown
# Token budget rules — Radar SAR thesis

Goal: maximum thesis progress, minimum wasted context.

## Hard rules
1. NEVER load raw datasets into context. Files in data/raw/ (.npy, .bin) can be 60 MB+.
   Use scripts that report shape, dtype, metadata, frequency range, positions, and stats.
2. Simulation data is small and safe to load when needed.
3. CLAUDE.md is prepended every turn. Keep it under 200 lines. Two-strikes rule: only add a
   note the second time you correct Claude on the same thing.
4. Session logs in reports/session_logs/ are safe to read.

## Workflow rules
1. One task per session. Never "do the whole thesis".
2. /clear when switching to an unrelated task.
3. /compact mid-task with a focused instruction (completed task, changed files, next step).
4. Ask for a plan before edits touching more than 2–3 files.
5. Reference files by path; do not paste whole files.
6. Trim tracebacks to the relevant 20–30 lines before pasting.
7. /usage often to monitor session consumption.
8. Plan with Opus, execute with Sonnet (/model opusplan).

## Tool split
- Claude.ai chat: theory, research, source links, thesis writing, planning.
- Claude Code: local repo only — read, edit, test, refactor, document. No web research.
- Git: local checkpoints before every significant session.

## Research has no internet in Claude Code
Claude Code cannot browse. Do theoretical research in Claude.ai chat first, then pass only the
final decision to Claude Code as a concise instruction.
```

---

## DELIVERABLE 7 — Plan de la primera sesión de Claude Code

```
# Primera sesión — Orden y auditoría (Fase 1)
Goal: que Claude Code entienda el repo, mueva legacy/, y deje todo listo. Riesgo de hardware: ninguno.
Tiempo estimado: 60–90 min.

## Antes de abrir Claude Code (PowerShell)
cd C:\tesis-radar-sar
git status
git add .
git commit -m "Checkpoint before first Claude Code session"

## Copiar scripts viejos a legacy/ (manual, en PowerShell)
mkdir legacy
# Copiá ahí TODOS tus scripts .py de pruebas actuales (RX, TX, sweep, OFDM, plots).
git add legacy
git commit -m "Add legacy working scripts for reference"

## Abrir Claude Code
claude

## Dentro de Claude Code — secuencia exacta
/status
/memory
/usage

# Luego pegá este prompt:
/radar-repo-audit

# Cuando termine la auditoría, pedile el orden básico (sin tocar legacy/):
Create README.md with a short project overview. Create initial YAML config templates in configs/
(simulation.yaml, phantom_low_power.yaml, benchmark.yaml) with placeholder parameters and comments.
Do not edit anything in legacy/. Show me the plan before creating files.

## Al cerrar la sesión
/radar-session-close

## En PowerShell, después de revisar
git status
git diff
git add .
git commit -m "Phase 1: repo audit, README, config templates"
git push

## Resultado esperado
- legacy/ con tus scripts viejos, intactos.
- README.md y configs/ creados.
- Un informe de sesión en reports/session_logs/.
- Commit limpio en GitHub. Cero interacción con hardware.
```

---

## DELIVERABLE 8 — Workflow de investigación y manejo de fuentes

### Parte A — Investigación teórica (en Claude.ai chat, NO en Claude Code)

**Cómo pedir para maximizar valor por mensaje:**
- Un tema por mensaje. No "investigá todo sobre SAR".
- Pedí 5–8 fuentes clave con URL + una línea de por qué sirve. No transcripciones de papers.
- Ejemplo bueno: *"Buscame los papers principales sobre backprojection para SAR de campo cercano
  en imagen biomédica de microondas. Dame título, link y para qué sección de tesis sirve."*

**Formato de log de fuentes en Notion** (página TESIS - Claude):

```
| URL | Título | Por qué es relevante | Sección de tesis |
```

**Orden de investigación por necesidad de las fases:**
1. Estado del arte: radar de microondas para mama, UWB/OFDM, SAR (Fase 0–1, para introducción)
2. Teoría SFCW y stitching (Fase 4)
3. Propiedades dieléctricas de tejido mamario, modelos Cole-Cole (Fase 2, para el phantom)
4. Diseño de phantom (Fase 8)
5. Backprojection / delay-and-sum en campo cercano (Fase 8)
6. Referencias de bladeRF / SDR (Fase 3)

**Fuentes viejas sin URL** (las que guardaste de ChatGPT/Gemini): marcalas como
`[NO VERIFICADA — buscar original]` y, cuando tengas tiempo, pedímelas acá para encontrar
el paper o documento original y conseguir el link real.

### Parte B — Investigación técnica para decisiones de código

1. Preguntás en Claude.ai chat: *"¿qué método de corrección de fase conviene para stitching SFCW?"*
2. Recibís una recomendación con razonamiento.
3. Le pasás SOLO la decisión a Claude Code: *"implementá corrección de fase con [método X] en
   processing/phase_correction.py"*.
4. No copies la investigación completa a Claude Code. Eso quema tokens sin sentido.

### Parte C — Costo en tokens de investigar

**Lo que SÍ gasta:** pegar papers completos, pasar PDFs enteros, muchas idas y vueltas en un
mismo chat largo, pedir resúmenes extensos de cada fuente.

**Lo que NO gasta (casi):** la búsqueda web en sí es barata; guardar a Notion vía MCP es casi cero;
pedir una lista de links con una línea cada uno.

**Estructura recomendada de sesión de investigación:**
una pregunta → lista de fuentes con URLs → guardar a Notion → cerrar. No estires el chat.

---

## PREGUNTA PENDIENTE PARA COMPLETAR EL TIMELINE

Tengo los estimados de esfuerzo por fase (en días), pero para marcar el **camino crítico** y
darte fechas concretas necesito saber: **¿cuándo es la fecha límite de entrega/defensa de la tesis?**

Con esa fecha puedo decirte qué fases entran cómodas, cuáles están ajustadas, y qué se puede
recortar (por ejemplo, validación con phantom más simple) si el tiempo aprieta.

Suma total de esfuerzo estimado: ~45–60 días de trabajo efectivo para 3 personas a tiempo parcial,
sin contar imprevistos de hardware (que en proyectos SDR suelen sumar 30–40% extra).
