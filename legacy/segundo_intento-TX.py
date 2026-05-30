import time
import numpy as np
from bladerf import _bladerf, BladeRF

# --- PARÁMETROS RF (MODO USB 2.0) ---
FREQ = 2400e6       
SAMPLE_RATE = 1e6   # Bajado a 1 MHz para no asfixiar el USB negro
BANDWIDTH = 1e6
GAIN_TX = 40

# --- PARÁMETROS OFDM ---
N_SUBCARRIERS = 64
CP_LEN = 16
PREAMBLE = np.array([1, 1, 1, 1, 1, -1, -1, 1, 1, -1, 1, -1, 1]) 

def generar_trama_ofdm(mensaje):
    bits = np.unpackbits(np.frombuffer(mensaje.encode('utf-8'), dtype=np.uint8))
    
    bits_por_bloque = 50 
    pads = (bits_por_bloque - (len(bits) % bits_por_bloque)) % bits_por_bloque
    bits_padded = np.append(bits, np.zeros(pads, dtype=np.uint8))
    
    bpsk_raw = np.where(bits_padded == 1, 1, -1).astype(int)
    bloques_ofdm = []
    
    for i in range(0, len(bpsk_raw), bits_por_bloque):
        chunk = bpsk_raw[i:i+bits_por_bloque]
        
        dbpsk_pos = np.zeros(26, dtype=complex)
        dbpsk_pos[0] = 1.0 + 0j 
        for k in range(25): 
            dbpsk_pos[k+1] = dbpsk_pos[k] * chunk[k]
            
        dbpsk_neg = np.zeros(26, dtype=complex)
        dbpsk_neg[0] = 1.0 + 0j 
        for k in range(25): 
            dbpsk_neg[k+1] = dbpsk_neg[k] * chunk[25+k]
            
        bloque = np.zeros(N_SUBCARRIERS, dtype=complex)
        bloque[1:27] = dbpsk_pos
        bloque[-26:] = dbpsk_neg
        
        ofdm_time = np.fft.ifft(bloque) * np.sqrt(N_SUBCARRIERS)
        ofdm_time_cp = np.concatenate((ofdm_time[-CP_LEN:], ofdm_time))
        bloques_ofdm.extend(ofdm_time_cp)
        
    bloques_ofdm = np.array(bloques_ofdm)
    bloques_ofdm = bloques_ofdm / np.max(np.abs(bloques_ofdm)) 
    
    preambulo_upsampled = np.repeat(PREAMBLE, 4)
    trama_base = np.concatenate((preambulo_upsampled, bloques_ofdm))
    
    # Alinear exactamente a 4096 para que el USB 2.0 pueda digerirlo
    faltantes = 4096 - len(trama_base)
    silencio = np.zeros(faltantes, dtype=complex)
    trama_completa = np.concatenate((trama_base, silencio))
    
    return trama_completa

def iniciar_emision():
    mensaje = "Zavoiski re puto"
    print(f"[*] Generando OFDM Modo USB 2.0: '{mensaje}'")
    
    senal_baseband = generar_trama_ofdm(mensaje)
    
    iq_scaled = np.empty(len(senal_baseband) * 2, dtype=np.int16)
    iq_scaled[0::2] = np.real(senal_baseband) * 2047
    iq_scaled[1::2] = np.imag(senal_baseband) * 2047
    
    # 2 repeticiones = Exactamente 8192 muestras (1 Buffer perfecto de hardware)
    repeticiones = 2
    buffer_tx = bytearray(np.tile(iq_scaled, repeticiones).tobytes())
    muestras_por_buffer = len(senal_baseband) * repeticiones

    print("Iniciando BladeRF TX...")
    try:
        sdr = BladeRF()
        ch_tx = sdr.Channel(_bladerf.CHANNEL_TX(0))
        ch_tx.frequency = int(FREQ)
        ch_tx.sample_rate = int(SAMPLE_RATE)
        ch_tx.bandwidth = int(BANDWIDTH)
        ch_tx.gain = GAIN_TX

        # Ajuste de tolerancia extrema para USB 2.0 (32 buffers, 16 transfers)
        sdr.sync_config(
            layout=_bladerf.ChannelLayout.TX_X1,
            fmt=_bladerf.Format.SC16_Q11,
            num_buffers=32,      
            buffer_size=8192,
            num_transfers=16,    
            stream_timeout=3500
        )

        ch_tx.enable = True
        print("\n[+] EMITIENDO... (Presiona Ctrl+C para detener)")
        
        paquetes_enviados = 0
        while True:
            # Mandamos a sorbos que el USB 2.0 puede tragar
            sdr.sync_tx(buffer_tx, muestras_por_buffer)
            paquetes_enviados += 1
            if paquetes_enviados % 500 == 0:
                print(f"  -> {paquetes_enviados} paquetes 8K enviados correctamente...")
                
    except KeyboardInterrupt:
        print("\n[!] Transmisión detenida por el usuario.")
    except Exception as e:
        print(f"\n[X] ERROR FATAL EN TX: {e}")
    finally:
        try:
            ch_tx.enable = False
            sdr.close()
            print("[*] Hardware liberado.")
        except:
            pass

if __name__ == "__main__":
    iniciar_emision()