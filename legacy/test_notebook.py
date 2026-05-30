import time
import threading
import numpy as np
from bladerf import _bladerf

# ====================================================================
# PARÁMETROS DEL RADAR
# ====================================================================
FREQ = 1000e6         # Frecuencia central (1 GHz de ejemplo)
SAMPLE_RATE = 40e6    # 40 MHz para máxima estabilidad en USB 3.0
BANDWIDTH = 40e6      # 40 MHz de Ancho de Banda
NUM_SAMPLES = 40000   # 1 ms de captura/emisión
GAIN_TX = 40
GAIN_RX = 50

# ====================================================================
# GENERACIÓN DE LA SEÑAL OFDM MATEMÁTICA
# ====================================================================
def generar_simbolo_ofdm(num_samples):
    print("Generando símbolo OFDM en RAM...")
    # 1. Definir parámetros básicos de OFDM
    N_subcarriers = 64
    CP_len = 16  # Prefijo Cíclico
    
    # 2. Generar símbolos de información
    # Usamos QPSK aleatorio como base. Para estimar el medio (Channel Sounding), 
    # usar una semilla fija asegura que siempre transmitas los mismos "Pilotos".
    np.random.seed(42) 
    simbolos = np.random.choice([1+1j, 1-1j, -1+1j, -1-1j], N_subcarriers)
    
    # Subportadora DC en cero (elimina el DC offset/Carrier leakage)
    simbolos = 0 + 0j 
    
    # 3. Transformada Inversa de Fourier (IFFT) para pasar al dominio del tiempo
    simbolo_tiempo = np.fft.ifft(simbolos)
    
    # 4. Añadir Prefijo Cíclico (CP) copiando el final al principio
    simbolo_ofdm = np.concatenate([simbolo_tiempo[-CP_len:], simbolo_tiempo])
    
    # 5. Repetir el símbolo para llenar la ráfaga (ventana de observación)
    repeticiones = int(np.ceil(num_samples / len(simbolo_ofdm)))
    senal_tx = np.tile(simbolo_ofdm, repeticiones)[:num_samples]
    
    # 6. Normalización de amplitud para no saturar el DAC
    senal_tx = senal_tx / np.max(np.abs(senal_tx))
    
    # 7. Escalar al formato SC16_Q11 (-2048 a 2047) del hardware bladeRF
    senal_tx_escalada = senal_tx * 2047.0
    
    # 8. Intercalar muestras In-Phase (I) y Quadrature (Q) en enteros de 16 bits
    iq_intercalado = np.empty(num_samples * 2, dtype=np.int16)
    iq_intercalado[0::2] = np.real(senal_tx_escalada).astype(np.int16)
    iq_intercalado[1::2] = np.imag(senal_tx_escalada).astype(np.int16)
    
    # Retornamos el bytearray listo para ser inyectado en el bus
    return bytearray(iq_intercalado.tobytes())

# ====================================================================
# BLOQUE PRINCIPAL DEL EXPERIMENTO FULL DUPLEX
# ====================================================================
def estimar_medio_ofdm():
    print("=========================================================")
    print("=== RADAR OFDM: ESTIMACIÓN DEL MEDIO EN FULL DUPLEX ===")
    print("=========================================================")
    print("⚠ Asegúrate de tener carga fantasma o antena en TX1/RX1.")
    time.sleep(2)
    
    sdr = None
    try:
        # Usamos la capa de bajo nivel recomendada
        sdr = _bladerf.BladeRF()

        # --- A. CONFIGURACIÓN DE CANALES ---
        ch_tx = sdr.Channel(_bladerf.CHANNEL_TX(0))
        ch_tx.frequency = int(FREQ)
        ch_tx.sample_rate = int(SAMPLE_RATE)
        ch_tx.bandwidth = int(BANDWIDTH)
        ch_tx.gain = GAIN_TX

        ch_rx = sdr.Channel(_bladerf.CHANNEL_RX(0))
        ch_rx.frequency = int(FREQ)
        ch_rx.sample_rate = int(SAMPLE_RATE)
        ch_rx.bandwidth = int(BANDWIDTH)
        ch_rx.gain = GAIN_RX

        # --- B. CONFIGURACIÓN DE INTERFAZ SINCRÓNICA ---
        print("Configurando buffers TX y RX en modo SC16_Q11...")
        sdr.sync_config(
            layout=_bladerf.ChannelLayout.TX_X1,
            fmt=_bladerf.Format.SC16_Q11,
            num_buffers=16, buffer_size=8192, num_transfers=8, stream_timeout=3500
        )
        sdr.sync_config(
            layout=_bladerf.ChannelLayout.RX_X1,
            fmt=_bladerf.Format.SC16_Q11,
            num_buffers=16, buffer_size=8192, num_transfers=8, stream_timeout=3500
        )

        # --- C. PREPARACIÓN DE BUFFERS Y SEÑAL ---
        buf_tx = generar_simbolo_ofdm(NUM_SAMPLES)
        buf_rx = bytearray(NUM_SAMPLES * 4) # Buffer receptor vacío

        # Habilitar amplificadores físicos
        ch_tx.enable = True
        ch_rx.enable = True

        # --- D. SINCRONIZACIÓN MILIMÉTRICA Y DISPARO ---
        senal_fuego = threading.Event()
        tx_listo = threading.Event()

        # Función del Hilo Transmisor
        def trabajo_tx():
            tx_listo.set()           # El TX avisa que está en posición
            senal_fuego.wait()       # El TX se congela esperando la luz verde
            sdr.sync_tx(buf_tx, NUM_SAMPLES) # Disparo del OFDM al aire

        # Iniciamos el hilo TX y lo dejamos "pausado"
        hilo_tx = threading.Thread(target=trabajo_tx)
        hilo_tx.start()

        # Hilo principal asegura que TX llegó al punto de espera
        tx_listo.wait()
        
        print("[RX] ¡Receptor y Transmisor listos! Disparando en 3, 2, 1...")
        
        # Al dar la luz verde, TX emite y RX captura el eco en la misma ventana t0
        t0 = time.perf_counter()
        senal_fuego.set() 
        sdr.sync_rx(buf_rx, NUM_SAMPLES)
        t1 = time.perf_counter()

        print(f"[✓] Captura y emisión finalizadas en {(t1 - t0)*1000:.2f} ms.")

        # Aseguramos el cierre del hilo
        hilo_tx.join()

        # --- E. PROCESAMIENTO Y GUARDADO ---
        print("Traduciendo bytes de RX a números complejos...")
        datos_crudos = np.frombuffer(buf_rx, dtype=np.int16)
        datos_iq = datos_crudos[0::2].astype(float) + 1j * datos_crudos[1::2].astype(float)
        
        # Normalizamos la amplitud igual que al transmitir
        datos_iq /= 2048.0  

        np.save("estimacion_medio_ofdm.npy", datos_iq)
        print("✅ ¡Éxito! El eco del medio OFDM está guardado en 'estimacion_medio_ofdm.npy'")

    except Exception as e:
        print(f"❌ Ocurrió un error en el hardware/SDR: {e}")
        
    finally:
        # Cierre y limpieza de hardware (Mantiene segura la placa)
        if sdr is not None:
            try:
                sdr.Channel(_bladerf.CHANNEL_TX(0)).enable = False
                sdr.Channel(_bladerf.CHANNEL_RX(0)).enable = False
            except:
                pass
            sdr.close()
            print("Conexión con BladeRF cerrada y puertos liberados.")

if __name__ == "__main__":
    estimar_medio_ofdm()