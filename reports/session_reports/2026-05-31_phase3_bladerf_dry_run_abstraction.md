# Informe de Sesión — Fase 3: Abstracción Hardware bladeRF (Dry-Run)

**Fecha:** 2026-05-31
**Tipo:** Inicio de Fase 3 — solo software, modo dry-run, sin hardware real
**Autor:** Claude Code (claude-sonnet-4-6) — asistente de tesis
**Estado:** Completado (dry-run)

---

## 1. Objetivo de la Fase 3 (inicio en dry-run)

El objetivo de esta sesión es iniciar la Fase 3 del proyecto de tesis SAR creando la capa de abstracción hardware para el bladeRF, con las siguientes restricciones absolutas:

- **Sin transmisión RF.** Ningún script activa TX ni emite señal.
- **Sin acceso a hardware.** No se importan las librerias bladeRF en Python a nivel de módulo. No se abre ningún dispositivo USB.
- **Sin movimiento de motores.** No se comanda la etapa acimutal.
- **Sin operaciones destructivas.** No se modifican drivers, firmware, ni configuración de sistema operativo.

Esta fase crea la infraestructura de software que habilitará la adquisición real en fases posteriores, pero no realiza ninguna operación RF.

---

## 2. Por qué esto no es una ejecución de hardware real

El modo dry-run (`dry_run=True`) es el único modo ejecutado en esta sesión. En dry-run:

- `BladeRFDevice.__init__()` no llama a ningún driver.
- `capture_rx()` devuelve un array NumPy sintético generado por `np.random.default_rng()`.
- `transmit_tone()` registra la llamada en un log interno sin emitir RF.
- Ningún import de `bladerf` Python existe en el árbol del código.

La frase `"CONFIRM HARDWARE RUN"` no fue proporcionada en esta sesión, por diseño.

---

## 3. Estado previo del repositorio

Al inicio, el repositorio estaba en el commit `53d65f2` (Phase 2 Offline cerrada):

- `acquisition/load_sfcw_capture.py` — cargador SFCW operativo.
- `processing/range_profile.py`, `sar_reconstruction.py` — pipeline de procesamiento.
- `experiments/run_legacy_offline_analysis.py` — análisis offline de capturas legacy.
- `tests/` — 31 tests pasando.
- **Ningún módulo `hardware/`** existía en el repositorio.
- **Ningún directorio `docs/`** existía en el repositorio.

---

## 4. Archivos creados o modificados

| Archivo | Acción | Descripción |
|---------|--------|-------------|
| `hardware/__init__.py` | Creado | Documentación de la API pública del paquete |
| `hardware/safety.py` | Creado | Validadores, SafetyError, HardwareConfirmation, constantes de límites |
| `hardware/bladerf_device.py` | Creado | BladeRFConfig, BladeRFDevice con dry-run y stubs de hardware real |
| `configs/bladerf_dry_run.yaml` | Creado | Configuración YAML de referencia en modo dry-run |
| `experiments/run_bladerf_dry_run.py` | Creado | Script de demostración dry-run |
| `tests/test_bladerf_device.py` | Creado | 30 tests de hardware, validación y seguridad |
| `docs/hardware_bladerf_safety.md` | Creado | Guía de seguridad en español |
| `thesis/cap5_abstraccion_hardware_bladerf.md` | Creado | Nota de tesis Capítulo 5 |
| `reports/session_reports/2026-05-31_phase3_bladerf_dry_run_abstraction.md` | Creado | Este informe |
| `reports/ai_session_log.md` | Actualizado | Entrada de Fase 3 |

---

## 5. Arquitectura de `hardware/safety.py`

### 5.1 Excepción central

```python
class SafetyError(Exception):
    """Raised when a requested hardware operation violates a safety constraint."""
```

### 5.2 Protocolo de confirmación

```python
class HardwareConfirmation:
    PHRASE = "CONFIRM HARDWARE RUN"

def require_hardware_confirmation(confirmation: str | None) -> None:
    if confirmation != HardwareConfirmation.PHRASE:
        raise SafetyError(...)
```

### 5.3 Constantes de límites (bladeRF 2.0 micro, conservadoras)

| Constante | Valor | Justificación |
|-----------|-------|---------------|
| `BLADERF_MIN_FREQ_HZ` | 70 MHz | Límite inferior del bladeRF |
| `BLADERF_MAX_FREQ_HZ` | 6 GHz | Límite superior del bladeRF |
| `BLADERF_MAX_SAMPLE_RATE_HZ` | 61.44 MS/s | Máximo del ADC/DAC |
| `BLADERF_MAX_BANDWIDTH_HZ` | 56 MHz | Máximo del filtro analógico |
| `BLADERF_MAX_TX_GAIN_DB` | −20 dBm | Conservadora para evitar potencia alta accidental |
| `BLADERF_MAX_RX_GAIN_DB` | 60 dB | Rango típico del bladeRF |
| `BLADERF_MAX_CAPTURE_SAMPLES` | 10,000,000 | Límite de ráfaga por captura |

### 5.4 Funciones de validación

- `validate_frequency_hz(freq_hz)` — verifica [70 MHz, 6 GHz]
- `validate_sample_rate_hz(rate_hz)` — verifica (0, 61.44 MS/s]
- `validate_bandwidth_hz(bw_hz)` — verifica (0, 56 MHz]
- `validate_gain_db(gain_db, kind)` — verifica límites por 'tx'/'rx'
- `validate_n_samples(n)` — verifica (0, 10,000,000]

Todas lanzan `SafetyError` con mensaje descriptivo.

---

## 6. Arquitectura de `hardware/bladerf_device.py`

### 6.1 `BladeRFConfig` (dataclass)

Encapsula todos los parámetros de una sesión de captura. Valida en `__post_init__()`.

```python
@dataclass
class BladeRFConfig:
    center_freq_hz: float = 2.4e9
    sample_rate_hz: float = 40.0e6
    bandwidth_hz:   float = 40.0e6
    rx_gain_db:     float = 20.0
    tx_gain_db:     float = -20.0
    n_samples:      int   = 40_000
    channel:        str   = "x1"
    dry_run:        bool  = True
```

### 6.2 `BladeRFDevice`

| Método | Dry-run | Real |
|--------|---------|------|
| `__init__` | Valida config | Requiere CONFIRM HARDWARE RUN |
| `configure_rx()` | Log + estado | `NotImplementedError` |
| `configure_tx()` | Log + estado | `NotImplementedError` |
| `capture_rx()` | Array sintético (40000, complex128) | `NotImplementedError` |
| `transmit_tone()` | Log, sin RF | `SafetyError` |
| `close()` | Marca cerrado | (stub) |
| `status()` | Dict de estado | Dict de estado |

---

## 7. Explicación del modo dry-run

En dry-run (`dry_run=True`, default):

1. `BladeRFDevice.__init__()` no invoca ningún driver ni USB.
2. `capture_rx()` genera ruido sintético con `np.random.default_rng(seed)` donde `seed` se deriva de la frecuencia y tasa de muestreo — **determinístico y reproducible**.
3. La amplitud del ruido sintético es 0.01 (ruido térmico simulado).
4. `transmit_tone()` añade una entrada al log interno marcada `"NOT TRANSMITTED"`.
5. Todos los tests pasan sin bladeRF conectado.

---

## 8. Compuertas de seguridad

La seguridad se implementa en múltiples capas:

1. **Capa 1 — Importación:** `bladerf` Python nunca se importa a nivel de módulo en ningún archivo del proyecto.
2. **Capa 2 — Confirmación:** `require_hardware_confirmation()` bloquea `dry_run=False` sin la frase exacta.
3. **Capa 3 — Validación:** `BladeRFConfig.__post_init__()` valida todos los parámetros antes de cualquier operación.
4. **Capa 4 — Método:** `transmit_tone()` con `dry_run=False` lanza `SafetyError` explícita.
5. **Capa 5 — Stubs:** Los métodos de hardware real lanzan `NotImplementedError` con mensaje explicativo.

---

## 9. Tests añadidos

`tests/test_bladerf_device.py` — 30 tests nuevos:

| Grupo | Tests |
|-------|-------|
| Config construction | `test_dry_run_config_construction`, `test_default_dry_run_is_true` |
| Freq validation | 3 tests (accepts valid, rejects below min, rejects above max) |
| Bandwidth validation | 3 tests |
| Sample rate validation | 2 tests |
| Gain validation | 3 tests (TX limit, RX range, invalid kind) |
| n_samples validation | 2 tests (too large, zero) |
| Real hardware gate | 3 tests (no confirmation, wrong confirmation, phrase check) |
| Dry-run lifecycle | configure, capture, close, post-close errors |
| IQ array properties | shape, dtype, determinism, low amplitude |
| transmit_tone | dry-run no-raise, log-only |
| status | returns dict |
| No bladeRF import | 2 tests (bladerf_device, safety) |
| YAML loader | tests load_bladerf_config_from_yaml() |

**Total sesión:** 31 tests previos + 30 nuevos = **61 tests pasando.**

---

## 10. Comandos ejecutados

```
py -m compileall hardware experiments tests     # sin errores
py -m pytest tests -v                           # 61/61 passed
py experiments/run_bladerf_dry_run.py           # completado, figuras generadas
git add ...
git commit -m "Start Phase 3 with safe bladeRF dry-run abstraction"
git push
```

---

## 11. Outputs generados

Los siguientes archivos se generan en `reports/generated/` (gitignored):

| Archivo | Contenido |
|---------|-----------|
| `bladerf_dry_run_summary.md` | Config, estadísticas IQ, estado del dispositivo |
| `bladerf_dry_run_iq_preview.png` | Primeros 200 muestras I y Q del ruido sintético |

Regenerar con:
```
py experiments/run_bladerf_dry_run.py
```

---

## 12. Qué valida esta fase

Al cerrar esta sesión:

1. **Arquitectura de abstracción hardware** correcta: `BladeRFConfig` + `BladeRFDevice` con dry-run funcional.
2. **Protocolo de seguridad** verificado: `CONFIRM HARDWARE RUN` bloquea acceso no autorizado.
3. **Validadores de parámetros** cubren todos los límites del bladeRF.
4. **IQ sintético determinístico** compatible con el pipeline de procesamiento.
5. **Tests exhaustivos** (30 nuevos) sin dependencia de hardware.
6. **Documentación de tesis** (Cap. 5) y guía de seguridad completas.
7. **Ninguna acción de hardware** fue ejecutada.

---

## 13. Qué no valida esta fase

| Aspecto | Estado |
|---------|--------|
| Comunicación USB real con bladeRF | No evaluada |
| Coherencia RF bajo temperatura | No evaluada |
| Latencia de transferencia de datos | No evaluada |
| Implementación real de `capture_rx()` | Stub — NotImplementedError |
| Barrido SFCW automático multi-frecuencia | No implementado |
| Control de etapa acimutal | No implementado |
| Calibración RF | No implementado |

---

## 14. Relación con la tesis

- **Capítulo 5** (`thesis/cap5_abstraccion_hardware_bladerf.md`) documenta la motivación, arquitectura y protocolo de seguridad de esta fase.
- Se añadió una nota sobre la numeración de capítulos: el documento `thesis/cap4_adquisicion.md` existente necesita renumeración al consolidar la tesis final. El orden sugerido es: Intro → Marco teórico → Simulación → Validación offline → Abstracción hardware → Sistema de adquisición → Experimentos → Conclusiones.

---

## 15. Riesgos antes del primer RF real

Antes de cambiar a `dry_run=False` y ejecutar RF, los siguientes riesgos deben mitigarse:

| Riesgo | Mitigación |
|--------|-----------|
| Puerto TX sin carga | Verificar carga 50 Ω o antena antes de TX |
| Ganancia TX demasiado alta | Mantener en −20 dBm hasta caracterización del sistema |
| Interferencia con espectro protegido | Verificar frecuencia y regulación local |
| Captura muy larga — desbordamiento USB | Mantener `n_samples <= 10,000,000` |
| Script de CI ejecutando RF | `CONFIRM HARDWARE RUN` no persistente previene esto |

---

## 16. Próximo paso exacto

**Tarea inmediata siguiente:** Implementar el método `capture_rx()` real en `BladeRFDevice`, usando la librería Python de bladeRF (libbladeRF), con:

- `import bladeRF` solo dentro del método (lazy import).
- Streaming RX limitado por `n_samples` y `BLADERF_MAX_CAPTURE_SAMPLES`.
- Log de todos los parámetros y timestamp de captura.
- Modo de ensayo: si la librería no está disponible, sugiere instalarla (`pip install bladeRF`).

Esta tarea puede comenzarse offline creando los stubs de la API. La primera ejecución real requiere el `"CONFIRM HARDWARE RUN"` en la sesión y hardware conectado.

---

*Informe generado por Claude Code como parte del flujo de trabajo de tesis SAR. Sin acciones de hardware en esta sesión.*
