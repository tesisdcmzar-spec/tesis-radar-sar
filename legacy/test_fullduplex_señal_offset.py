import time
import os
import threading
import numpy as np
from bladerf import _bladerf

def ejecutar_barrido_fullduplex_offset():
    print("==================================================")
    print("   INICIANDO BARRIDO FULL DUPLEX (TONO OFFSET)    ")
    print("==================================================")
    print("⚠️ ADVERTENCIA: Asegúrate de tener las antenas conectadas a TX1 y RX1.")
    # Coloca las antenas un poco separadas sobre la mesa para que el RX escuche al TX.
    time.sleep(2) # Pausa de seguridad

    # --- PARÁMETROS CONFIGURABLES ---
    FREQ_INICIAL = 100e6      
    FREQ_FINAL = 6000e6       
    PASO_FREQ = 60e6          
    SAMPLE_RATE = 40e6        
    BANDWIDTH = 40e6          
    NUM_SAMPLES = 40000       # 1 ms de captura/emisión por paso
    GAIN_TX = 30              # Ganancia segura para TX
    GAIN_RX = 40              # Ganancia fija de RX para calibración

    # --- VARIABLES ESTADÍSTICAS ---
    tiempos_lo_tx = []
    tiempos_lo_rx = []
    tiempos_transferencia_tx = []
    tiempos_transferencia_rx = []
    tamanos_archivos = []
    
    # Creamos una nueva carpeta para no mezclar con las pruebas anteriores
    directorio_salida = "capturas_fullduplex_offset"
    if not os.path.exists(directorio_salida):
        os.makedirs(directorio_salida)

    sdr = None
    
    try:
        sdr = _bladerf.BladeRF()
        
        # 1. CONFIGURACIÓN DE CANALES
        ch_tx = sdr.Channel(_bladerf.CHANNEL_TX(0))
        ch_tx.sample_rate = int(SAMPLE_RATE)
        ch_tx.bandwidth = int(BANDWIDTH)
        ch_tx.gain = GAIN_TX

        ch_rx = sdr.Channel(_bladerf.CHANNEL_RX(0))
        ch_rx.sample_rate = int(SAMPLE_RATE)
        ch_rx.bandwidth = int(BANDWIDTH)
        ch_rx.gain = GAIN_RX
        
        # 2. CONFIGURACIÓN DE INTERFAZ SINCRÓNICA
        print("Configurando memorias para TX y RX...")
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

        # 3. CREAR SEÑAL EN MEMORIA RAM (Tono de Prueba de 5 MHz)
        print("[TX] Generando pulso de prueba (Tono 5 MHz) en RAM...")
        t = np.arange(NUM_SAMPLES) / SAMPLE_RATE
        f_tone = 5e6 # Frecuencia del offset (5 MHz)
        
        # Fórmula de onda matemática: e^(j*2*pi*f*t)
        señal_tx = np.exp(1j * 2 * np.pi * f_tone * t)
        señal_tx *= 2000.0 # Escalado para el DAC de 12 bits (máximo 2047)
        
        # Convertimos a enteros de 16 bits intercalados [Real, Imag, Real, Imag...]
        señal_tx_int = np.zeros(NUM_SAMPLES * 2, dtype=np.int16)
        señal_tx_int[0::2] = np.real(señal_tx).astype(np.int16)
        señal_tx_int[1::2] = np.imag(señal_tx).astype(np.int16)
        
        buf_tx = señal_tx_int.tobytes()
        buf_rx = bytearray(NUM_SAMPLES * 4) # Aquí aterrizarán los datos recibidos
        
        # Habilitar amplificadores
        ch_tx.enable = True
        ch_rx.enable = True

        frecuencia_actual = FREQ_INICIAL
        paso_num = 0

        print(f"\n🚀 Iniciando barrido: {FREQ_INICIAL/1e6} MHz a {FREQ_FINAL/1e6} MHz...\n")

        # Cronómetro general
        t_inicio_barrido = time.perf_counter()

        while frecuencia_actual <= FREQ_FINAL:
            freq_entera = int(frecuencia_actual)

            # --- A. SINTONIZAR TX ---
            t0_lo_tx = time.perf_counter()
            ch_tx.frequency = freq_entera 
            tiempos_lo_tx.append((time.perf_counter() - t0_lo_tx) * 1000)

            # --- B. SINTONIZAR RX ---
            t0_lo_rx = time.perf_counter()
            ch_rx.frequency = freq_entera 
            tiempos_lo_rx.append((time.perf_counter() - t0_lo_rx) * 1000)

            # --- C. DISPARO SIMULTÁNEO (TX Y RX) ---
            señal_fuego = threading.Event()
            tx_listo = threading.Event()
            tiempo_tx_local = [0.0] 

            def trabajo_tx():
                tx_listo.set() 
                señal_fuego.wait() 
                tt0 = time.perf_counter()
                sdr.sync_tx(buf_tx, NUM_SAMPLES)
                tiempo_tx_local[0] = (time.perf_counter() - tt0) * 1000

            hilo_tx = threading.Thread(target=trabajo_tx)
            hilo_tx.start()
            
            tx_listo.wait() 

            # ¡FUEGO! (Apertura de micrófonos y disparo de antena)
            tr0 = time.perf_counter()
            señal_fuego.set() 
            sdr.sync_rx(buf_rx, NUM_SAMPLES)
            tr1 = time.perf_counter()
            
            hilo_tx.join() 

            tiempos_transferencia_rx.append((tr1 - tr0) * 1000)
            tiempos_transferencia_tx.append(tiempo_tx_local[0])

            # --- D. PROCESAR Y GUARDAR ---
            datos_crudos = np.frombuffer(buf_rx, dtype=np.int16)
            datos_iq = datos_crudos[0::2].astype(float) + 1j * datos_crudos[1::2].astype(float)
            datos_iq /= 2048.0 # Normalizamos -1.0 a 1.0

            # Guardamos con un prefijo nuevo para identificarlos
            nombre_archivo = os.path.join(directorio_salida, f"cap_offset_{paso_num:03d}_{int(frecuencia_actual/1e6)}MHz.npy")
            np.save(nombre_archivo, datos_iq)
            tamanos_archivos.append(os.path.getsize(nombre_archivo) / 1024)

            # Reporte de progreso
            if paso_num % 10 == 0 or frecuencia_actual == FREQ_FINAL:
                print(f"Progreso: Escaneado {freq_entera/1e6} MHz...")

            frecuencia_actual += PASO_FREQ
            paso_num += 1

        t_fin_barrido = time.perf_counter()

        ch_tx.enable = False
        ch_rx.enable = False

        # --- REPORTE ESTADÍSTICO FINAL ---
        resumen = (
            "==================================================\n"
            "   REPORTE TÉCNICO BARRIDO FULL DUPLEX (OFFSET)\n"
            "==================================================\n"
            f"Pasos totales completados: {paso_num}\n"
            f"Rango de frecuencias: {FREQ_INICIAL/1e6} MHz - {FREQ_FINAL/1e6} MHz\n\n"
            "--- TIEMPOS DE OSCILADORES (SINTONÍA) ---\n"
            f"Promedio LO TX: {np.mean(tiempos_lo_tx):.4f} ms\n"
            f"Promedio LO RX: {np.mean(tiempos_lo_rx):.4f} ms\n\n"
            "--- TIEMPOS DE TRANSFERENCIA DE DATOS ---\n"
            f"Promedio Transferencia TX: {np.mean(tiempos_transferencia_tx):.4f} ms\n"
            f"Promedio Transferencia RX: {np.mean(tiempos_transferencia_rx):.4f} ms\n\n"
            "--- ESTADÍSTICAS GLOBALES ---\n"
            f"Tiempo Operativo Acumulado: {(sum(tiempos_lo_tx) + sum(tiempos_lo_rx) + sum(tiempos_transferencia_rx)):.2f} ms\n"
            f"Tiempo de Reloj Real (Wall time): {(t_fin_barrido - t_inicio_barrido):.4f} Segundos\n"
            f"Peso Total de Datos Crudos en Disco: {sum(tamanos_archivos)/1024:.2f} MB\n"
            "=================================================="
        )
        print("\n" + resumen)
        with open("estadisticas_barrido_offset.txt", "w") as f:
            f.write(resumen)
            
        print("\n[✓] Barrido maestro con tono offset finalizado exitosamente.")

    except Exception as e:
        print(f"\n❌ Ocurrió un error inesperado: {e}")
    
    finally:
        if sdr is not None:
            try:
                sdr.Channel(_bladerf.CHANNEL_TX(0)).enable = False
                sdr.Channel(_bladerf.CHANNEL_RX(0)).enable = False
            except:
                pass
            print("Cerrando BladeRF y liberando puerto USB...")
            try:
                sdr.close()
            except:
                pass

if __name__ == "__main__":
    ejecutar_barrido_fullduplex_offset()