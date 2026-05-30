import time
import os
import numpy as np
import bladerf
from bladerf import BladeRF

# --- EL "HACK" MÁGICO PARA LA LIBRERÍA [cite: 1031]
class FormatoFalso: [cite: 1032]
    def __init__(self, val): [cite: 1033]
        self.value = val [cite: 1034]

SC16_Q11 = FormatoFalso(0) [cite: 1035]
RX_X1 = FormatoFalso(0) [cite: 1037]

def recibir_ofdm():
    print("🎧 Iniciando Receptor OFDM...")
    sdr = None
    NUM_SAMPLES = 80000 # Capturamos 2ms para asegurarnos de agarrar símbolos completos
    
    try:
        sdr = BladeRF()
        ch_rx = sdr.Channel(bladerf.CHANNEL_RX(0)) [cite: 1060]
        
        # Mismos parámetros que el TX
        ch_rx.frequency = int(2400e6)
        ch_rx.sample_rate = int(40e6)
        ch_rx.bandwidth = int(40e6)
        ch_rx.gain = 50 
        
        print("Configurando buffers RX...")
        sdr.sync_config(
            layout=RX_X1, [cite: 1070]
            fmt=SC16_Q11, [cite: 1071]
            num_buffers=16, [cite: 1072]
            buffer_size=8192, [cite: 1073]
            num_transfers=8, [cite: 1074]
            stream_timeout=3500 [cite: 1075]
        )
        
        buffer_rx = bytearray(NUM_SAMPLES * 4) [cite: 1078]
        ch_rx.enable = True [cite: 1080]
        
        print("📥 Escuchando el espectro...")
        # Capturamos un bloque de datos
        sdr.sync_rx(buffer_rx, NUM_SAMPLES) [cite: 1094]
        
        ch_rx.enable = False
        
        print("🧠 Procesando IQ...")
        # Pasamos de bytes a numpy array usando tu lógica validada [cite: 1100, 1101]
        datos_crudos = np.frombuffer(buffer_rx, dtype=np.int16)
        datos_iq = datos_crudos[0::2].astype(float) + 1j * datos_crudos[1::2].astype(float)
        datos_iq /= 2048.0
        
        np.save("mensaje_ofdm_recibido.npy", datos_iq)
        print("✅ Captura guardada en 'mensaje_ofdm_recibido.npy'. ¡Listo para analizar!")

    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        if sdr:
            try:
                ch_rx.enable = False
            except:
                pass
            sdr.close()
            print("Cerrando BladeRF RX.")

if __name__ == "__main__":
    recibir_ofdm()