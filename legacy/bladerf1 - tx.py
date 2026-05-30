import time
import numpy as np
from bladerf import _bladerf, BladeRF

def crear_simbolo_ofdm_tx():
    # Parámetros OFDM
    N = 1024  # Número de subportadoras
    CP_len = 64  # Prefijo Cíclico cortito
    
    # Creamos las subportadoras (frecuencia)
    subportadoras = np.zeros(N, dtype=complex)
    
    # Inyectamos "datos" aleatorios (QPSK básico) en las subportadoras útiles
    # Dejamos las bandas de guarda vacías (ej. 100 de cada lado)
    # Y dejamos la del medio (DC Null) en cero
    for i in range(100, N - 100):
        if i != (N // 2): # Evitamos el centro exacto
            # Fase aleatoria para mantener el PAPR bajo
            fase = np.random.choice([0, np.pi/2, np.pi, 3*np.pi/2])
            subportadoras[i] = np.exp(1j * fase)
            
    # IFFT para pasar al dominio del tiempo
    simbolo_tiempo = np.fft.ifft(subportadoras)
    
    # Agregamos el Prefijo Cíclico
    simbolo_con_cp = np.concatenate([simbolo_tiempo[-CP_len:], simbolo_tiempo])
    
    # Normalizamos para no saturar el DAC (rango -1.0 a 1.0) y multiplicamos por 2047
    simbolo_normalizado = simbolo_con_cp / np.max(np.abs(simbolo_con_cp))
    simbolo_entero = (simbolo_normalizado * 2047).astype(np.int16)
    
    # Empaquetamos I y Q intercalados (Formato SC16_Q11)
    iq_intercalado = np.empty(simbolo_entero.size * 2, dtype=np.int16)
    iq_intercalado[0::2] = np.real(simbolo_entero)
    iq_intercalado[1::2] = np.imag(simbolo_entero)
    
    return bytearray(iq_intercalado.tobytes())

def transmitir_ofdm():
    print("🚀 Iniciando Transmisor OFDM...")
    sdr = None
    try:
        sdr = BladeRF()
        ch_tx = sdr.Channel(_bladerf.CHANNEL_TX(0))
        
        # Parámetros (Ajustá la frecuencia a una libre de ruido)
        ch_tx.frequency = int(2400e6) 
        ch_tx.sample_rate = int(40e6)
        ch_tx.bandwidth = int(40e6)
        ch_tx.gain = 40
        
        print("Configurando buffers TX...")
        sdr.sync_config(
            layout=_bladerf.ChannelLayout.TX_X1,
            fmt=_bladerf.Format.SC16_Q11,
            num_buffers=16,
            buffer_size=8192,
            num_transfers=8,
            stream_timeout=3500
        )
        
        # Generamos un mega-buffer repitiendo el símbolo para que la transmisión dure
        buffer_base = crear_simbolo_ofdm_tx()
        
        # Repetimos el símbolo muchas veces para llenar una ventana de 1ms aprox
        buffer_tx = buffer_base * (40000 // (1024 + 64)) 
        
        ch_tx.enable = True
        print("📡 Transmitiendo señal OFDM en bucle... (Ctrl+C para cortar)")
        
        # Transmitimos sin parar para que el receptor tenga tiempo de "engancharlo"
        while True:
            sdr.sync_tx(buffer_tx, len(buffer_tx) // 4)
            
    except KeyboardInterrupt:
        print("\n⏹️ Transmisión detenida por el usuario.")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if sdr:
            try:
                ch_tx.enable = False
            except:
                pass
            sdr.close()
            print("Cerrando BladeRF TX.")

if __name__ == "__main__":
    transmitir_ofdm()