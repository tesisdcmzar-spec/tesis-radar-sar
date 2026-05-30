import time
import threading
import numpy as np
from bladerf import _bladerf

# =============================================================================
# HILO DE RECEPCIÓN (RX)
# =============================================================================
def hilo_recepcion(sdr, freq, rate, bw, gain, num_samples, tx_start_event):
    try:
        # 1. Configurar canal RX
        ch_rx = sdr.Channel(_bladerf.CHANNEL_RX(0))
        ch_rx.frequency = int(freq)
        ch_rx.sample_rate = int(rate)
        ch_rx.bandwidth = int(bw)
        ch_rx.gain = gain

        # 2. Configurar buffer
        sdr.sync_config(
            layout=_bladerf.ChannelLayout.RX_X1,
            fmt=_bladerf.Format.SC16_Q11,
            num_buffers=16,
            buffer_size=8192,
            num_transfers=8,
            stream_timeout=3500
        )

        buf_rx = bytearray(num_samples * 4) # 4 bytes por muestra IQ

        print("[RX] Iniciando receptor...")
        ch_rx.enable = True

        # 3. ¡Luz verde para transmitir!
        # Le avisamos al hilo de TX que el receptor ya está encendido y escuchando
        tx_start_event.set()

        # 4. Capturar
        sdr.sync_rx(buf_rx, num_samples)
        
        ch_rx.enable = False
        print("[RX] Captura finalizada. Procesando datos...")

        # 5. Guardar en memoria y archivo .npy
        datos_crudos = np.frombuffer(buf_rx, dtype=np.int16)
        datos_iq = datos_crudos[0::2].astype(float) + 1j * datos_crudos[1::2].astype(float)
        datos_iq /= 2048.0
        
        np.save("captura_fullduplex.npy", datos_iq)
        print("[RX] ✅ Datos guardados exitosamente en 'captura_fullduplex.npy'")

    except Exception as e:
        print(f"[RX] ❌ Error en recepción: {e}")


# =============================================================================
# HILO DE TRANSMISIÓN (TX)
# =============================================================================
def hilo_transmision(sdr, freq, rate, bw, gain, num_samples, tx_start_event):
    try:
        # 1. Configurar canal TX
        ch_tx = sdr.Channel(_bladerf.CHANNEL_TX(0))
        ch_tx.frequency = int(freq)
        ch_tx.sample_rate = int(rate)
        ch_tx.bandwidth = int(bw)
        ch_tx.gain = gain

        # 2. Configurar buffer
        sdr.sync_config(
            layout=_bladerf.ChannelLayout.TX_X1,
            fmt=_bladerf.Format.SC16_Q11,
            num_buffers=16,
            buffer_size=8192,
            num_transfers=8,
            stream_timeout=3500
        )

        # 3. Crear señal en memoria RAM (Sustituye al archivo tx_payload.bin)
        # Generamos un buffer de ceros. Esto transmitirá una portadora pura (Carrier).
        # En el futuro, aquí es donde generarás tu señal OFDM matemática.
        buf_tx = bytearray(num_samples * 4) 

        print("[TX] Preparado. Esperando a que el receptor esté listo...")
        ch_tx.enable = True

        # 4. Esperar luz verde
        # El transmisor se pausa aquí hasta que RX le mande la señal (tx_start_event.set())
        tx_start_event.wait()
        print("[TX] 🚀 ¡Disparando transmisión!")

        # 5. Transmitir
        sdr.sync_tx(buf_tx, num_samples)

        ch_tx.enable = False
        print("[TX] ✅ Transmisión completada.")

    except Exception as e:
        print(f"[TX] ❌ Error en transmisión: {e}")
        try:
            ch_tx.enable = False
        except:
            pass


# =============================================================================
# BLOQUE PRINCIPAL
# =============================================================================
def test_full_duplex():
    print("=== TEST FULL DUPLEX (TX y RX SIMULTÁNEO) ===")
    print("⚠️ Asegúrate de tener las antenas conectadas a TX y RX.")
    time.sleep(2)

    sdr = None

    # Parámetros del Radar (Harcoded en lugar de usar .ini)
    FREQ = 1000e6         # 1 GHz (Asegúrate de tener antenas para esta banda)
    SAMPLE_RATE = 40e6    # 40 MHz
    BANDWIDTH = 40e6      # 40 MHz
    NUM_SAMPLES = 40000   # 1 ms de prueba
    GAIN_TX = 40
    GAIN_RX = 50

    try:
        sdr = _bladerf.BladeRF()
        
        # Evento de sincronización entre hilos
        tx_start_event = threading.Event()

        # Creamos los dos hilos (como si fueran dos miniprogramas en paralelo)
        hilo_rx = threading.Thread(target=hilo_recepcion, args=(sdr, FREQ, SAMPLE_RATE, BANDWIDTH, GAIN_RX, NUM_SAMPLES, tx_start_event))
        hilo_tx = threading.Thread(target=hilo_transmision, args=(sdr, FREQ, SAMPLE_RATE, BANDWIDTH, GAIN_TX, NUM_SAMPLES, tx_start_event))

        # Iniciamos los hilos
        hilo_rx.start()
        hilo_tx.start()

        # Le decimos al programa principal que espere a que ambos hilos terminen
        hilo_rx.join()
        hilo_tx.join()

        print("\n[✓] Experimento Full Duplex finalizado.")

    except Exception as e:
        print(f"\n[!] Ocurrió un error general: {e}")

    finally:
        if sdr is not None:
            sdr.close()
            print("Conexión con BladeRF cerrada.")

if __name__ == "__main__":
    test_full_duplex()