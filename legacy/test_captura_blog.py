from bladerf import _bladerf
import numpy as np
import matplotlib.pyplot as plt

# Inicializamos la variable del SDR
sdr = None

try:
    # 1. Conexión e Inicialización del hardware
    sdr = _bladerf.BladeRF()
    rx_ch = sdr.Channel(_bladerf.CHANNEL_RX(0)) # Usamos el canal 0 (RX1)

    # Parámetros de recepción
    sample_rate = 10e6    # 10 MHz
    center_freq = 100e6   # 100 MHz (Sintoniza aquí tu portadora)
    gain = 60             # Ganancia al máximo (útil si la señal es débil)
    num_samples = int(1e6) # Vamos a capturar 1 millón de muestras (0.1 segundos)

    print("Configurando receptor...")
    rx_ch.frequency = center_freq
    rx_ch.sample_rate = sample_rate
    rx_ch.bandwidth = sample_rate / 2
    rx_ch.gain = gain

    # 2. Configuración del flujo síncrono (Stream de lectura)
    sdr.sync_config(layout=_bladerf.ChannelLayout.RX_X1,
                    fmt=_bladerf.Format.SC16_Q11, # El hardware entregará enteros de 16 bits
                    num_buffers=16,
                    buffer_size=8192,
                    num_transfers=8,
                    stream_timeout=3500)

    # 3. Preparar la "caja" (búfer) donde guardaremos los datos
    # 1 muestra IQ = 16 bits I + 16 bits Q = 32 bits = 4 bytes.
    bytes_per_sample = 4
    buf = bytearray(num_samples * bytes_per_sample)

    # 4. Iniciar la Recepción
    print("¡Habilitando RX y capturando el espectro!")
    rx_ch.enable = True # Enciende el amplificador de recepción
    
    # La siguiente función se queda "esperando" hasta llenar el buffer con 1 millón de muestras
    sdr.sync_rx(buf, num_samples) 
    
    rx_ch.enable = False # Apaga la recepción por seguridad
    print("Captura finalizada.")

    # 5. Traducción de Bytes a Matemáticas (Señales IQ)
    # Convertimos la tira de bytes crudos en un arreglo de enteros de 16 bits
    samples_int16 = np.frombuffer(buf, dtype=np.int16)
    
    # Los datos llegan intercalados: [I, Q, I, Q, I, Q...]
    # Tomamos los pares y construimos el número complejo usando slicing de arrays en Python
    samples_iq = samples_int16[0::2] + 1j * samples_int16[1::2]
    
    # Escalamos de vuelta para tener valores en el rango de -1.0 a +1.0
    samples_iq = samples_iq / 2048.0

    print(f"Total de muestras complejas procesadas: {len(samples_iq)}")

    # 6. Visualización de los datos (Las primeras 1000 muestras)
    plt.figure(figsize=(10, 4))
    plt.plot(np.real(samples_iq[:1000]), label='I (Fase)')
    plt.plot(np.imag(samples_iq[:1000]), label='Q (Cuadratura)', alpha=0.7)
    plt.title('Primeras 1000 muestras de RF recibidas')
    plt.xlabel('Tiempo (Muestras)')
    plt.ylabel('Amplitud')
    plt.legend()
    plt.grid(True)
    plt.show()

except Exception as e:
    print(f"\n[!] Ocurrió un error: {e}")

finally:
    if sdr is not None:
        sdr.close()
        print("\n[✓] BladeRF cerrado y puerto USB liberado correctamente.")