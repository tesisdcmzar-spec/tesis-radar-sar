# Seguridad del Hardware bladeRF — Guía de la Capa de Abstracción

## 1. Propósito de la capa de abstracción

El módulo `hardware/bladerf_device.py` encapsula todas las operaciones del dispositivo bladeRF detrás de una interfaz Python con controles de seguridad integrados. Su propósito es garantizar que:

- Ningún script del proyecto pueda transmitir RF ni abrir el hardware real por accidente.
- Toda la validación de parámetros ocurra antes de cualquier operación de hardware.
- El modo de ensayo en seco («dry-run») sea el comportamiento por defecto, activado incluso si el argumento se omite.
- El código de procesamiento y los tests puedan ejecutarse sin el bladeRF conectado.

## 2. Por qué existe el modo dry-run

El modo dry-run (`dry_run=True`) permite:

1. **Desarrollar y testear código de adquisición** sin necesitar el bladeRF físicamente conectado.
2. **Validar la cadena de procesamiento** con datos sintéticos antes de usar datos reales.
3. **Integrar en CI/CD** sin riesgo de transmisión RF accidental.
4. **Entrenar al usuario** en el flujo de adquisición sin consecuencias RF.

En modo dry-run:
- No se importan las librerias `bladeRF` en Python.
- No se accede a ningún dispositivo USB.
- `capture_rx()` devuelve un array IQ sintético determinístico (ruido de baja amplitud).
- `transmit_tone()` registra la llamada en el log interno sin emitir RF.
- `configure_rx()` y `configure_tx()` validan los parámetros y los registran.

## 3. Operaciones bloqueadas

Las siguientes operaciones están bloqueadas actualmente:

| Operación | Estado |
|-----------|--------|
| Transmisión RF (`transmit_tone`) con `dry_run=False` | Bloqueado — `SafetyError` |
| Captura RX real (`capture_rx`) con `dry_run=False` | Stub — `NotImplementedError` |
| Configuración RX/TX real con `dry_run=False` | Stub — `NotImplementedError` |
| Importación de `bladerf` Python a nivel de módulo | Bloqueado — no existe en ningún `import` de nivel superior |

## 4. Qué es `CONFIRM HARDWARE RUN`

`"CONFIRM HARDWARE RUN"` es la frase de confirmación exacta que debe pasarse al parámetro `confirmation` de `BladeRFDevice.__init__()` cuando `dry_run=False`.

```python
device = BladeRFDevice(config, confirmation="CONFIRM HARDWARE RUN")
```

**Propósito:** Exige que el usuario tome una decisión consciente y explícita antes de cualquier operación RF real. No es una contraseña de seguridad; es una barrera de intención que:
- Documenta en el código que el desarrollador sabe que está usando hardware real.
- Evita que scripts de prueba o automatizados ejecuten RF por error.
- Hace auditable en el historial de git y logs cuándo se autorizó hardware real.

### Por qué la confirmación no es persistente entre sesiones

La confirmación **no** se guarda en ningún archivo de configuración ni variable de entorno. Debe proporcionarse en cada sesión donde se use hardware real. Esto es intencional:

- Previene que una confirmación de una sesión de prueba autorice inadvertidamente sesiones futuras.
- Obliga a una decisión consciente en cada ejecución.
- Reduce el riesgo de transmisiones RF accidentales en entornos de CI/CD.

## 5. Lista de verificación antes de usar hardware real

Antes de cambiar `dry_run` a `false` y proporcionar `"CONFIRM HARDWARE RUN"`, verificar:

### 5.1 Antenas y carga RF
- [ ] La antena está conectada al puerto TX del bladeRF, o bien hay una carga terminada de 50 Ω.
- [ ] No hay conexión abierta (sin carga) en el puerto TX — puede dañar el amplificador.
- [ ] El cable y los conectores están en buen estado y tienen especificación para la frecuencia objetivo.

### 5.2 Ganancia TX
- [ ] La ganancia TX configurada es conservadora (actualmente: máximo −20 dBm por defecto).
- [ ] Se ha calculado la potencia de salida esperada y está dentro de límites regulatorios y de seguridad.
- [ ] Se han revisado los límites regulatorios locales para la frecuencia y potencia de transmisión.

### 5.3 Frecuencia
- [ ] La frecuencia está dentro del rango del bladeRF: 70 MHz – 6 GHz.
- [ ] La frecuencia no interfiere con espectro protegido (bandas de vuelo, emergencias, medicina).
- [ ] Se dispone de licencia o exención regulatoria aplicable.

### 5.4 Tasa de muestreo y ancho de banda
- [ ] `sample_rate_hz <= 61.44e6` S/s.
- [ ] `bandwidth_hz <= 56e6` Hz.
- [ ] `bandwidth_hz <= sample_rate_hz` (para anti-aliasing correcto).

### 5.5 Duración de captura
- [ ] `n_samples` está dentro del límite de ráfaga (actualmente: 10,000,000 muestras).
- [ ] El buffer de USB del sistema es suficiente para la tasa de transferencia requerida.

### 5.6 Logs y metadatos
- [ ] El script de adquisición registra: frecuencia, ganancia, tasa de muestreo, timestamp, posición acimutal.
- [ ] Los archivos de captura se guardan con nombre descriptivo que incluye parámetros clave.
- [ ] El informe de sesión describe el escenario de medición (distancia al blanco, tipo de blanco).

### 5.7 Sujetos de prueba
- [ ] **No hay seres humanos en el camino de la antena durante la transmisión.**
- [ ] El experimento usa únicamente fantasmas dieléctricos de geometría conocida.
- [ ] No se realizarán afirmaciones clínicas de ningún tipo.

## 6. Cómo ejecutar el modo dry-run

```bash
# Desde la raíz del repositorio:
py experiments/run_bladerf_dry_run.py
```

Salida esperada:
- Imprime configuración cargada desde `configs/bladerf_dry_run.yaml`.
- Ejecuta `configure_rx()`, `configure_tx()`, `capture_rx()`, `transmit_tone()` (simulado), `status()`, `close()`.
- Guarda `reports/generated/bladerf_dry_run_summary.md` y `bladerf_dry_run_iq_preview.png`.
- **No abre ningún dispositivo USB. No emite RF.**

## 7. Qué aún no está implementado

| Funcionalidad | Estado |
|--------------|--------|
| `BladeRFDevice.capture_rx()` real | Stub (`NotImplementedError`) |
| `BladeRFDevice.configure_rx()` con `libbladeRF` | Stub |
| `BladeRFDevice.configure_tx()` con `libbladeRF` | Stub |
| `BladeRFDevice.transmit_tone()` real | Stub — `SafetyError` en modo real |
| Barrido SFCW multi-frecuencia automático | No implementado |
| Control de etapa acimutal | No implementado (módulo separado) |
| Sustracción de fondo automática | No implementado |

## 8. Estructura de módulos

```
hardware/
    __init__.py              # Documentación de la API pública
    safety.py                # SafetyError, validadores, constantes de límites
    bladerf_device.py        # BladeRFConfig, BladeRFDevice

configs/
    bladerf_dry_run.yaml     # Configuración de referencia en modo dry-run

experiments/
    run_bladerf_dry_run.py   # Script de demostración dry-run

tests/
    test_bladerf_device.py   # Tests de unidad (sin hardware)
```

## 9. Referencia rápida de la API

```python
from hardware.bladerf_device import BladeRFConfig, BladeRFDevice
from hardware.safety import SafetyError

# Dry-run (seguro, sin hardware)
config = BladeRFConfig(center_freq_hz=2.4e9, dry_run=True)
device = BladeRFDevice(config)
device.configure_rx()
iq = device.capture_rx()   # array (n_samples,) complex128 sintetico
st = device.status()
device.close()

# Real (requiere confirmacion explícita - no implementado aún)
# config = BladeRFConfig(dry_run=False, ...)
# device = BladeRFDevice(config, confirmation="CONFIRM HARDWARE RUN")
```
