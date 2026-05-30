from bladerf import _bladerf
import numpy as np

# Inicializamos la variable del SDR en None antes del bloque try
sdr = None

try:
    # 1. Conexión e Inicialización del hardware
    sdr = _bladerf.BladeRF()
    tx_ch = sdr.Channel(_bladerf.CHANNEL_TX(0)) # usamos el canal 0 (TX1)

    # Parámetros de transmisión
    sample_rate = 10e6
    center_freq = 100e6
    gain = 0 # de -15 a 60 dB. Para transmitir, empieza bajo y asegúrate de tener la antena conectada
    num_samples = int(1e6)
    repeat = 30 # número de veces que repetiremos la señal
    
    print('Duración estimada de transmisión:', num_samples/sample_rate*repeat, 'segundos')

    # 2. Generación de las muestras IQ (En este caso, un tono simple)
    t = np.arange(num_samples) / sample_rate
    f_tone = 1e6
    samples = np.exp(1j * 2 * np.pi * f_tone * t) # genera valores de -1 a +1
    samples = samples.astype(np.complex64)
    samples *= 2048.0 # Escala la señal para usar el DAC de 12 bits (-2048 a +2047)
    samples = samples.view(np.int16)
    buf = samples.tobytes() # convierte las muestras a bytes para el búfer de transmisión

    # 3. Aplicación de parámetros al canal
    tx_ch.frequency = center_freq
    tx_ch.sample_rate = sample_rate
    tx_ch.bandwidth = sample_rate / 2
    tx_ch.gain = gain

    # 4. Configuración del flujo síncrono (Stream de datos hacia el USB)
    sdr.sync_config(layout=_bladerf.ChannelLayout.TX_X1, # o TX_X2 si usas el otro canal
                    fmt=_bladerf.Format.SC16_Q11, # enteros de 16 bits
                    num_buffers=16,
                    buffer_size=8192,
                    num_transfers=8,
                    stream_timeout=3500)

    # 5. Bucle de Transmisión
    print("¡Iniciando transmisión!")
    repeats_remaining = repeat - 1
    tx_ch.enable = True # Enciende el amplificador TX
    
    while True:
        sdr.sync_tx(buf, num_samples) # Escribe los datos en el bladeRF
        print(f"Repeticiones restantes: {repeats_remaining}")
        if repeats_remaining > 0:
            repeats_remaining -= 1
        else:
            break

    print("Deteniendo transmisión...")
    tx_ch.enable = False # Apaga el amplificador TX

# Captura cualquier error que pueda ocurrir durante la ejecución
except Exception as e:
    print(f"\n[!] Ocurrió un error: {e}")

# Este bloque final se ejecuta SIEMPRE, haya habido un error o no
finally:
    if sdr is not None:
        sdr.close()
        print("\n[✓] BladeRF cerrado y puerto USB liberado correctamente.")
