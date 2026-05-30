import time
import os
import numpy as np
from bladerf import _bladerf # <-- Usamos el wrapper de bajo nivel directamente

def ejecutar_barrido_emision():
    # --- PARÁMETROS CONFIGURABLES ---
    FREQ_INICIAL = 100e6      
    FREQ_FINAL = 6000e6       
    PASO_FREQ = 60e6          
    SAMPLE_RATE = 40e6        
    BANDWIDTH = 40e6          
    NUM_SAMPLES = 40000       # 1 ms de captura

    tiempos_sintonia_lo = []
    tiempos_transmision = []

    print("Iniciando BladeRF para prueba de EMISIÓN (TX)...")
    print("⚠️ ADVERTENCIA: Asegúrate de tener una antena conectada al puerto TX.")
    time.sleep(2) # Pausa por si te olvidaste de la antena

    sdr = None
    
    try:
        # Iniciamos el objeto usando la capa de bajo nivel
        sdr = _bladerf.BladeRF()
        
        # 1. SELECCIÓN DEL CANAL DE TRANSMISIÓN
        canal_tx = sdr.Channel(_bladerf.CHANNEL_TX(0))
        canal_tx.sample_rate = int(SAMPLE_RATE)
        canal_tx.bandwidth = int(BANDWIDTH)
        canal_tx.gain = 40 
        
        # 2. CONFIGURACIÓN DEL BUFFER SINCRO (TX)
        print("Configurando interfaz sincrónica de transmisión (Modo nativo)...")
        # Usamos las constantes correctas del propio _bladerf
        sdr.sync_config(
            layout=_bladerf.ChannelLayout.TX_X1, 
            fmt=_bladerf.Format.SC16_Q11, 
            num_buffers=16,
            buffer_size=8192,
            num_transfers=8,
            stream_timeout=3500 
        )

        # 3. PREPARAR EL BUFFER A TRANSMITIR (Vacío / Ceros)
        buffer_tx = bytearray(NUM_SAMPLES * 4)
        
        # Habilitamos transmisión
        canal_tx.enable = True

        frecuencia_actual = FREQ_INICIAL
        paso_num = 0

        print(f"🚀 Iniciando barrido de emisión: {FREQ_INICIAL/1e6} MHz a {FREQ_FINAL/1e6} MHz...")

        while frecuencia_actual <= FREQ_FINAL:
            # --- SINTONÍA ---
            t_inicio_lo = time.perf_counter()
            canal_tx.frequency = int(frecuencia_actual) 
            t_fin_lo = time.perf_counter()
            tiempos_sintonia_lo.append((t_fin_lo - t_inicio_lo) * 1000)

            # --- TRANSMISIÓN ---
            t_inicio_tx = time.perf_counter()
            sdr.sync_tx(buffer_tx, NUM_SAMPLES) 
            t_fin_tx = time.perf_counter()
            tiempos_transmision.append((t_fin_tx - t_inicio_tx) * 1000)

            if paso_num % 10 == 0:
                print(f"Progreso: Transmitiendo a {int(frecuencia_actual/1e6)} MHz...")

            frecuencia_actual += PASO_FREQ
            paso_num += 1

        canal_tx.enable = False

        # --- REPORTE FINAL ---
        prom_lo = np.mean(tiempos_sintonia_lo)
        prom_tx = np.mean(tiempos_transmision)

        resumen = (
            "========================================\n"
            "   RESULTADOS DEL EXPERIMENTO (TX)\n"
            "========================================\n"
            f"Pasos totales: {paso_num}\n"
            f"Tiempo Promedio LO (Sintonía TX): {prom_lo:.4f} ms\n"
            f"Tiempo Promedio TX (Transferencia): {prom_tx:.4f} ms\n"
            f"Tiempo Total Real del Barrido: {(sum(tiempos_sintonia_lo) + sum(tiempos_transmision)):.2f} ms\n"
            "========================================"
        )
        print("\n" + resumen)
        with open("estadisticas_barrido_tx.txt", "w") as f:
            f.write(resumen)
            
        print("\n[✓] Barrido de emisión finalizado con éxito.")

    except Exception as e:
        print(f"\n❌ Ocurrió un error inesperado: {e}")
    
    finally:
        if sdr is not None:
            try:
                # Intento forzado de apagado del TX por seguridad
                sdr.Channel(_bladerf.CHANNEL_TX(0)).enable = False
            except:
                pass
            print("Cerrando BladeRF y liberando puerto USB...")
            try:
                sdr.close()
            except:
                pass

if __name__ == "__main__":
    ejecutar_barrido_emision()