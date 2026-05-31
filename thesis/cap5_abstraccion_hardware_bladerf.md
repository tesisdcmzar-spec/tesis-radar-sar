# Capítulo 5 — Abstracción Hardware para el bladeRF

## 5.1 Motivación: de la validación offline a la adquisición controlada

La cadena de procesamiento validada en los capítulos anteriores opera sobre datos sintéticos y sobre capturas legacy de apertura única. Antes de realizar la primera adquisición real con el bladeRF, es necesario establecer una capa de software que:

1. **Separe el código de procesamiento del hardware físico.** Los módulos `simulation/`, `processing/`, y `acquisition/load_sfcw_capture.py` no deben conocer el API específico del bladeRF; reciben únicamente arrays NumPy con la interfaz `SyntheticScan`.

2. **Prevenga operaciones RF accidentales.** Un script de test o un experimento de procesamiento no debe poder transmitir RF ni abrir un dispositivo USB por descuido.

3. **Valide los parámetros antes del hardware.** Frecuencia, tasa de muestreo, ancho de banda, ganancia y número de muestras deben verificarse contra límites seguros antes de cualquier operación de hardware.

4. **Permita desarrollo y pruebas sin hardware físico.** El modo de ensayo en seco (dry-run) debe producir datos sintéticos compatibles con el pipeline existente, de modo que el flujo completo pueda ser testeado sin el bladeRF conectado.

---

## 5.2 Transición desde la validación offline

Al final de la Fase 2, el repositorio disponía de:

- `acquisition/load_sfcw_capture.py` — carga capturas `.npy` en `SyntheticScan`.
- `processing/range_profile.py` — perfiles de rango por IFFT.
- `processing/sar_reconstruction.py` — retroproyección SAR.
- `experiments/run_legacy_offline_analysis.py` — análisis offline de 99 capturas legacy.

El eslabón faltante era la conexión entre el hardware real y estos módulos de procesamiento. La Fase 3 cubre este eslabón mediante la abstracción `BladeRFDevice`.

La relación entre capas es:

```
[bladeRF hardware]
      |
      v
[hardware/bladerf_device.py]  <-- capa de abstracción (este capítulo)
      |
      v  np.ndarray (N_samples,) complex128
      v
[acquisition/load_sfcw_capture.py]  --builds-->  SyntheticScan
      |
      v
[processing/range_profile.py]       --produces-> perfiles de rango
[processing/sar_reconstruction.py]  --produces-> imagen SAR
```

---

## 5.3 Restricciones del bladeRF 2.0 micro

Las restricciones de hardware que impone el bladeRF 2.0 micro en la configuración de este proyecto son:

| Parámetro | Rango soportado | Valor típico del proyecto |
|-----------|----------------|--------------------------|
| Frecuencia RF | 70 MHz – 6 GHz | 100 – 5 980 MHz (legado) |
| Tasa de muestreo máxima | ~61.44 MS/s | 40 MS/s |
| Ancho de banda analógico máx. | ~56 MHz | 40 MHz |
| Ganancia RX | 0 – 60 dB | 20 dB |
| Ganancia TX | configurable | −20 dB (conservadora) |

Estos límites se codifican como constantes en `hardware/safety.py` y se verifican antes de cualquier operación de hardware.

---

## 5.4 Arquitectura: seguridad como diseño primario

### 5.4.1 `hardware/safety.py`

Define:

- `SafetyError`: excepción lanzada cuando cualquier parámetro viola un límite de seguridad.
- `HardwareConfirmation.PHRASE`: la frase literal `"CONFIRM HARDWARE RUN"` requerida para hardware real.
- `require_hardware_confirmation(confirmation)`: verifica la frase antes de abrir hardware.
- Constantes de límites: `BLADERF_MIN_FREQ_HZ`, `BLADERF_MAX_FREQ_HZ`, etc.
- Funciones de validación: `validate_frequency_hz`, `validate_sample_rate_hz`, `validate_bandwidth_hz`, `validate_gain_db`, `validate_n_samples`.

Cada función de validación lanza `SafetyError` con un mensaje descriptivo que indica el valor recibido, el límite violado, y la acción correctiva.

### 5.4.2 `hardware/bladerf_device.py`

Define:

- `BladeRFConfig` (dataclass): todos los parámetros de una sesión de captura. Valida automáticamente en `__post_init__()`.
- `BladeRFDevice`: interfaz de hardware con modo dry-run y modo real (sin implementar en esta fase).

El módulo **nunca importa las librerias Python de bladeRF a nivel de módulo**. Las importaciones de hardware solo ocurren dentro de métodos, únicamente cuando `dry_run=False` y la confirmación ha sido validada.

---

## 5.5 Modo dry-run

El modo dry-run (`dry_run=True`, valor por defecto) garantiza las siguientes propiedades:

1. No se abre ningún dispositivo USB.
2. No se importa ninguna librería de hardware.
3. `capture_rx()` devuelve un array `(N, )` `complex128` de ruido sintético determinístico (semilla derivada de la configuración).
4. `transmit_tone()` registra la llamada en el log interno sin emitir RF.
5. `configure_rx()` y `configure_tx()` validan los parámetros y los almacenan.
6. Todos los tests del proyecto pueden ejecutarse en modo dry-run sin el bladeRF conectado.

Este enfoque sigue el principio de *dependency inversion*: el código de alto nivel (procesamiento, experimentos) depende de la interfaz `BladeRFDevice`, no de los detalles del hardware físico.

---

## 5.6 Protocolo de confirmación para hardware real

Para activar el hardware real (`dry_run=False`), la cadena de texto exacta `"CONFIRM HARDWARE RUN"` debe pasarse al constructor:

```python
config = BladeRFConfig(center_freq_hz=2.4e9, dry_run=False)
device = BladeRFDevice(config, confirmation="CONFIRM HARDWARE RUN")
```

Sin esta frase exacta, `BladeRFDevice.__init__()` lanza `SafetyError` antes de realizar ninguna operación.

La confirmación es **no persistente entre sesiones**: debe proporcionarse en cada ejecución del script de adquisición. Esto previene que un script de automatización ejecute RF por accidente en una sesión posterior a la originalmente autorizada.

---

## 5.7 Separación entre validación de software y ejecución RF

Esta arquitectura establece una separación explícita en el ciclo de desarrollo:

| Etapa | Hardware | Confirmación necesaria |
|-------|----------|----------------------|
| Desarrollo de algoritmos | Ninguno | No |
| Tests unitarios | Ninguno | No |
| Análisis offline de capturas legacy | Ninguno | No |
| Dry-run del sistema de adquisición | Ninguno | No |
| Primera captura real con blanco conocido | bladeRF | Sí (`CONFIRM HARDWARE RUN`) |
| Barrido SFCW con etapa acimutal | bladeRF + motor | Sí + aprobación explícita de movimiento |

Esta tabla hace explícito en el proceso de tesis cuándo se cruza el umbral entre software y hardware.

---

## 5.8 Habilitación de la adquisición SFCW futura

La arquitectura `BladeRFDevice` permite implementar la adquisición SFCW multi-frecuencia en una fase posterior de la siguiente manera:

```python
# Pseudocódigo — adquisición SFCW futura
scan_data = {}
for f_hz in freq_grid_hz:
    config = BladeRFConfig(center_freq_hz=f_hz, dry_run=False)
    device = BladeRFDevice(config, confirmation=session_confirmation)
    device.configure_rx()
    iq = device.capture_rx()            # (N_samples,) complex128
    scan_data[f_hz] = np.mean(iq)       # H(f_k) por promediado coherente
    device.close()

# Construir SyntheticScan y procesar con el pipeline existente
scan = SyntheticScan(freqs_hz=freq_grid_hz, x_az_m=aperture_positions, H=H_matrix)
range_m, profiles = compute_range_profiles(scan)
```

El pipeline de procesamiento no requiere modificaciones: `SyntheticScan` es el punto de integración entre hardware y software.

---

## 5.9 Fase 3b: Ruta de captura RX real preparada

La Fase 3a estableció el andamiaje de abstracción y seguridad: `BladeRFConfig`, `BladeRFDevice`, modo dry-run y la compuerta de confirmación.  La Fase 3b extiende `hardware/bladerf_device.py` con la implementación completa de la ruta de captura RX real, sin ejecutar ninguna operación sobre hardware físico.  Los tres elementos nuevos son: un helper de conversión de formato de muestra (`sc16q11_to_complex`), un mecanismo de importación diferida (`_import_bladerf`) y la ruta de captura privada (`_capture_rx_real`).  Un cuarto elemento —la inyección de backend falso— permite ejercer esta ruta en tests sin USB.

### 5.9.1 Formato de muestras SC16_Q11 y conversión a IQ

El bladeRF transfiere muestras IQ en formato **SC16_Q11** (*Signed 16-bit, Q1.11 fixed-point*).  Cada muestra IQ ocupa 4 bytes: dos enteros de 16 bits con signo intercalados en el orden [I, Q].  El layout en memoria de una captura de *N* muestras es:

```
[I₀, Q₀, I₁, Q₁, ..., I_{N-1}, Q_{N-1}]   dtype: int16, longitud: 2N
```

El rango de valores es [−2048, +2047], correspondiente al formato Q1.11 (11 bits fraccionarios, escala 2¹¹ = 2048).  Para obtener amplitud normalizada ≈ [−1, +1), se divide por 2048.0.

La función `sc16q11_to_complex` realiza esta conversión:

```python
def sc16q11_to_complex(raw: np.ndarray) -> np.ndarray:
    raw_i16 = raw.astype(np.int16, copy=False)
    i_ch = raw_i16[0::2].astype(np.float64)   # componente I
    q_ch = raw_i16[1::2].astype(np.float64)   # componente Q
    return (i_ch + 1j * q_ch) / 2048.0
```

La función es independiente del hardware: acepta cualquier array NumPy 1-D de longitud par y devuelve un array `complex128` de shape `(N//2,)`.  Lanza `ValueError` si el array no es 1-D o tiene longitud impar.

La elección de `float64` (no `float32`) es deliberada: el pipeline SAR opera en `complex128` para preservar la precisión de fase en la retroproyección.  Este factor de normalización 2048 es coherente con los parámetros de las capturas legacy documentados en §4.1.2 de `cap4_adquisicion.md`, garantizando compatibilidad entre la ruta nueva y los datos históricos.

### 5.9.2 Importación diferida de las bindings Python (`_import_bladerf`)

Las bindings Python del bladeRF (`import bladerf`) intentan acceder al driver USB en el momento de la importación.  Si el módulo `hardware/bladerf_device.py` contuviera `import bladerf` como sentencia de nivel superior, cualquier script de procesamiento que importara este módulo fallaría en máquinas sin bladeRF, violando el principio de separación hardware/software establecido en §5.1.

La función `_import_bladerf` resuelve este problema mediante `importlib.import_module`:

```python
import importlib  # stdlib — siempre disponible

def _import_bladerf():
    try:
        return importlib.import_module("bladerf")
    except ImportError as exc:
        raise ImportError(
            "bladeRF Python bindings not found.  "
            "Install with: pip install bladerf\n"
            "Or build from source: https://github.com/Nuand/bladeRF"
        ) from exc
```

`_import_bladerf()` es invocada **únicamente** dentro de `BladeRFDevice.__init__()`, y solo si se cumplen simultáneamente tres condiciones:

1. `config.dry_run == False` — el modo dry-run nunca la invoca.
2. `confirmation == "CONFIRM HARDWARE RUN"` — la compuerta de seguridad ya fue validada.
3. `_bladerf_module is None` — no se inyectó un módulo falso de test.

El test `test_no_bladerf_import_in_bladerf_device_module` verifica mediante expresión regular sobre el código fuente que la cadena `import bladerf` o `from bladerf` nunca aparece como sentencia de nivel de módulo en `hardware/bladerf_device.py`.

### 5.9.3 Flujo de captura `_capture_rx_real`

El método privado `_capture_rx_real` implementa la captura RX real usando la interfaz *sync* de libbladeRF.  El procedimiento consta de cuatro pasos:

1. **Configurar la interfaz sync**: llama a `sync_config` con `ChannelLayout.RX_X1` (un canal RX), formato `Format.SC16_Q11`, 16 buffers de 8192 muestras, 8 transferencias concurrentes y timeout de 3500 ms.
2. **Alocar el buffer de recepción**: `bytearray(n * 4)` — 4 bytes por muestra (2 × int16).
3. **Llenar el buffer**: `sync_rx(buf, n)` transfiere *n* muestras SC16_Q11 desde el ADC al buffer.
4. **Convertir**: `np.frombuffer(buf, dtype=np.int16)` interpreta el buffer como array int16; `sc16q11_to_complex(raw)` produce el array `complex128` final.

```python
def _capture_rx_real(self) -> np.ndarray:
    n = self._config.n_samples
    self._device.sync_config(
        layout=self._bladerf_mod.ChannelLayout.RX_X1,
        fmt=self._bladerf_mod.Format.SC16_Q11,
        num_buffers=16,
        buffer_size=8192,
        num_transfers=8,
        stream_timeout=3500,
    )
    buf = bytearray(n * 4)
    self._device.sync_rx(buf, n)
    raw = np.frombuffer(buf, dtype=np.int16)
    return sc16q11_to_complex(raw)
```

Los parámetros `num_buffers=16`, `buffer_size=8192`, `num_transfers=8` y `stream_timeout=3500` provienen directamente de las capturas legacy documentadas en §4.1.2.

> **Estado:** esta ruta está implementada y ejercida mediante tests con backend falso.  **No ha sido ejecutada sobre hardware real.**  La primera ejecución requiere bladeRF físicamente conectado, `pip install bladerf` y la frase `"CONFIRM HARDWARE RUN"` en la sesión.

### 5.9.4 Inyección de backend falso para tests

Para ejercer `_capture_rx_real` sin hardware, `BladeRFDevice.__init__` acepta el parámetro interno `_bladerf_module`.  Cuando se pasa un objeto en este parámetro, reemplaza al módulo devuelto por `_import_bladerf()`.

Los tests definen tres clases auxiliares:

| Clase | Simula | Atributos / métodos clave |
|-------|--------|---------------------------|
| `_FakeChannel` | Canal RX del bladeRF | `frequency`, `sample_rate`, `bandwidth`, `gain` |
| `_FakeBladeRFDevice` | Dispositivo bladeRF | `Channel()`, `sync_config()`, `sync_rx()`, `close()` |
| `_FakeBladeRFModule` | Módulo Python `bladerf` | `BladeRF()`, `CHANNEL_RX()`, `ChannelLayout.RX_X1`, `Format.SC16_Q11` |

El patrón de inyección es:

```python
fake_mod = _FakeBladeRFModule()
cfg = BladeRFConfig(dry_run=False, center_freq_hz=2.4e9, n_samples=1000)
dev = BladeRFDevice(cfg, confirmation="CONFIRM HARDWARE RUN",
                    _bladerf_module=fake_mod)
dev.configure_rx()
iq = dev.capture_rx()
assert iq.shape == (1000,)
assert iq.dtype == np.complex128
```

Esto verifica que `configure_rx` aplica correctamente los parámetros al canal y que `capture_rx` produce un array de shape y dtype correctos, sin abrir ningún dispositivo USB ni importar las bindings reales.

---

## 5.10 Qué valida esta fase y qué no

### Validado — Fase 3a (abstracción dry-run)

- La arquitectura de abstracción hardware es correcta y testeable sin bladeRF.
- Los validadores de seguridad rechazan parámetros fuera de rango.
- El protocolo de confirmación bloquea el acceso no autorizado a hardware real.
- El modo dry-run produce datos compatibles con el pipeline de procesamiento.
- Todos los módulos de hardware pueden importarse sin el bladeRF presente.

### Validado — Fase 3b (ruta RX real preparada)

- `sc16q11_to_complex` es correcta para ceros, valores conocidos, normalización y valores negativos.
- `sc16q11_to_complex` rechaza arrays no-1D y de longitud impar con `ValueError`.
- `sc16q11_to_complex` devuelve `complex128` de shape `(N//2,)`.
- `_import_bladerf` lanza `ImportError` descriptivo cuando el paquete no está instalado.
- La ruta real (`_capture_rx_real`) se construye y ejecuta correctamente con backend falso inyectado.
- `configure_rx` en modo real aplica frecuencia, tasa de muestreo, ancho de banda y ganancia al canal.
- `capture_rx` en modo real devuelve un array `complex128` de shape `(n_samples,)`.
- `close` en modo real llama al método `close()` del backend.
- Ninguna sentencia `import bladerf` existe a nivel de módulo (verificado por test regex).
- Sin regresiones: suite completa 82/82 tests aprobados.

### No validado

- La comunicación USB real con el bladeRF (ninguna captura RX fue ejecutada sobre hardware).
- El rendimiento del bladeRF bajo condiciones reales de RF.
- La coherencia de fase entre barridos sucesivos.
- La estabilidad del oscilador local bajo temperatura.
- La transferencia USB a tasas máximas de muestreo.
- El comportamiento del amplificador TX bajo carga.
- La corrección `sc16q11_to_complex` sobre muestras reales del ADC.

---

## 5.11 Nota sobre numeración de capítulos

El capítulo `thesis/cap4_adquisicion.md` cubre el diseño del sistema de adquisición SFCW. El presente capítulo (`cap5`) describe la implementación de la capa de abstracción hardware. Al integrar todos los capítulos en el documento final de tesis, es necesario revisar la numeración para que la secuencia lógica sea:

1. Introducción
2. Marco teórico SFCW-SAR
3. Simulación y validación sintética
4. Validación offline con capturas legacy
5. Abstracción hardware y diseño de seguridad *(este capítulo)*
6. Sistema de adquisición SFCW (contenido de cap4_adquisicion.md)
7. Experimentos con fantasma dieléctrico *(trabajo futuro)*
8. Resultados y conclusiones *(trabajo futuro)*

La renumeración se realizará al consolidar el documento final.

---

*Este capítulo es parte de la tesis de pregrado en Telecomunicaciones. Todo el trabajo descrito es experimental y de validación de software. Sin afirmaciones clínicas ni médicas.*
