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

## 5.9 Qué valida esta fase y qué no

### Validado

- La arquitectura de abstracción hardware es correcta y testeable sin bladeRF.
- Los validadores de seguridad rechazan parámetros fuera de rango.
- El protocolo de confirmación bloquea el acceso no autorizado a hardware real.
- El modo dry-run produce datos compatibles con el pipeline de procesamiento.
- Todos los módulos de hardware pueden importarse sin el bladeRF presente.

### No validado

- El rendimiento del bladeRF bajo condiciones reales de RF.
- La coherencia entre barridos sucesivos.
- La estabilidad del oscilador local bajo temperatura.
- La transferencia USB a tasas máximas de muestreo.
- El comportamiento del amplificador TX bajo carga.

---

## 5.10 Nota sobre numeración de capítulos

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
