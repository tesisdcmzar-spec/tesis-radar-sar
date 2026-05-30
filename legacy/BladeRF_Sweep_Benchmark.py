import time
import os
import threading
import numpy as np
import matplotlib.pyplot as plt
from bladerf import _bladerf

def realizar_benchmark_tiempos():
    print("==================================================")
    print("   INICIANDO BENCHMARK DE TIEMPOS (RADAR MAMA)    ")
    print("==================================================")
    print("⚠️ ADVERTENCIA: Asegúrate de tener las antenas conectadas a TX1/TX2.")
    time.sleep(2)

    # --- PARÁMETROS GLOBALES ---
    FREQ_INICIAL = 100e6      
    FREQ_FINAL = 6000e6       
    NUM_SAMPLES = 40000       
    GAIN_TX = 30              
    GAIN_RX = 40              
    
    # ⚠️ Control de almacenamiento para no colapsar el disco en el test
    GUARDAR_ARCHIVOS = False 
    directorio_salida = "capturas_benchmark"
    if GUARDAR_ARCHIVOS and not os.path.exists(directorio_salida):
        os.makedirs(directorio_salida)

    # Lista de saltos de frecuencia a testear (en Hz)
    pasos_a_testear_mhz = [10, 20, 30, 40, 45, 50, 55, 60]
    pasos_a_testear_hz = [p * 1e6 for p in pasos_a_testear_mhz]
    
    # Aquí guardaremos los resultados (Tiempo en segundos)
    tiempos_totales_segundos = []

    sdr = None
    
    try:
        sdr = _bladerf.BladeRF()
        
        # 1. CONFIGURACIÓN BASE DE CANALES
        ch_tx = sdr.Channel(_bladerf.CHANNEL_TX(0))
        ch_tx.gain = GAIN_TX

        ch_rx = sdr.Channel(_bladerf.CHANNEL_RX(0))
        ch_rx.gain = GAIN_RX
        
        # Pre-asignamos la memoria RAM para los datos (llena de ceros al inicio)
        buf_tx = bytearray(NUM_SAMPLES * 4) 
        buf_rx = bytearray(NUM_SAMPLES * 4) 

        # =========================================================
        # INICIO DEL BUCLE DE TESTEO MASTER
        # =========================================================
        for paso_hz in pasos_a_testear_hz:
            paso_mhz = int(paso_hz / 1e6)
            print(f"\n==================================================")
            print(f"▶ TESTEANDO CAPTURAS DE: {paso_mhz} MHz")
            print(f"==================================================")
            
            # Ajustamos el ancho de banda y sample rate del hardware (límite físico 40MHz)
            sr_bw_actual = min(paso_hz, 40e6) 
            ch_tx.sample_rate = int(sr_bw_actual)
            ch_tx.bandwidth = int(sr_bw_actual)
            ch_rx.sample_rate = int(sr_bw_actual)
            ch_rx.bandwidth = int(sr_bw_actual)

            # Configuramos los buffers USB en cada ciclo para evitar errores de memoria
            sdr.sync_config(layout=_bladerf.ChannelLayout.TX_X1, fmt=_bladerf.Format.SC16_Q11, 
                            num_buffers=16, buffer_size=8192, num_transfers=8, stream_timeout=3500)
            sdr.sync_config(layout=_bladerf.ChannelLayout.RX_X1, fmt=_bladerf.Format.SC16_Q11, 
                            num_buffers=16, buffer_size=8192, num_transfers=8, stream_timeout=3500)

            # Ahora encendemos los amplificadores
            ch_tx.enable = True
            ch_rx.enable = True

            frecuencia_actual = FREQ_INICIAL
            paso_num = 0

            # CRONÓMETRO INICIAL (Empieza a correr el tiempo real)
            t_inicio_barrido = time.perf_counter()

            while frecuencia_actual <= FREQ_FINAL:
                freq_entera = int(frecuencia_actual)

                # --- Sintonía ---
                ch_tx.frequency = freq_entera 
                ch_rx.frequency = freq_entera 

                # --- Hilos y Sincronización ---
                señal_fuego = threading.Event()
                tx_listo = threading.Event()

                def trabajo_tx():
                    tx_listo.set()
                    señal_fuego.wait()
                    sdr.sync_tx(buf_tx, NUM_SAMPLES)

                hilo_tx = threading.Thread(target=trabajo_tx)
                hilo_tx.start()
                
                # Esperar microsegundos a que el hilo TX se prepare
                tx_listo.wait() 

                # ¡FUEGO! Disparamos RX y destrabamos TX
                señal_fuego.set() 
                sdr.sync_rx(buf_rx, NUM_SAMPLES)
                
                # Asegurar que TX terminó
                hilo_tx.join() 

                # --- Procesamiento y Guardado ---
                if GUARDAR_ARCHIVOS:
                    datos_crudos = np.frombuffer(buf_rx, dtype=np.int16)
                    datos_iq = datos_crudos[0::2].astype(float) + 1j * datos_crudos[1::2].astype(float)
                    datos_iq /= 2048.0
                    nombre_archivo = os.path.join(directorio_salida, f"cap_{paso_mhz}MHz_fd_{paso_num:03d}_{int(freq_entera/1e6)}MHz.npy")
                    np.save(nombre_archivo, datos_iq)

                frecuencia_actual += paso_hz
                paso_num += 1

            # CRONÓMETRO FINAL
            t_fin_barrido = time.perf_counter()
            tiempo_total = t_fin_barrido - t_inicio_barrido
            tiempos_totales_segundos.append(tiempo_total)

            # Apagamos canales para reiniciar limpio en el siguiente test
            ch_tx.enable = False
            ch_rx.enable = False
            
            print(f"[✓] Terminado. Pasos dados: {paso_num}. Tiempo total: {tiempo_total:.4f} Segundos.")

        print("\n🎉 BENCHMARK COMPLETADO. Generando gráfico...")

        # =========================================================
        # GENERACIÓN DEL GRÁFICO (Eje X = MHz, Eje Y = Tiempo)
        # =========================================================
        plt.figure(figsize=(10, 6))
        
        plt.plot(pasos_a_testear_mhz, tiempos_totales_segundos, marker='o', linestyle='-', color='b', linewidth=2, markersize=8)
        
        # Decoración del gráfico
        plt.title('Rendimiento de Barrido Full-Duplex (100 MHz a 6 GHz)', fontsize=14, fontweight='bold')
        plt.xlabel('Ancho de Captura (Paso en MHz)', fontsize=12)
        plt.ylabel('Tiempo Total de Barrido (Segundos)', fontsize=12)
        
        # Añadir las etiquetas de tiempo en cada punto centradas arriba
        for i, txt in enumerate(tiempos_totales_segundos):
            plt.annotate(f"{txt:.2f}s", (pasos_a_testear_mhz[i], tiempos_totales_segundos[i]), 
                         textcoords="offset points", xytext=(0,10), ha='center')

        plt.grid(True, linestyle='--', alpha=0.7)
        plt.tight_layout()
        
        # Guardamos la imagen
        plt.savefig('grafico_rendimiento_barrido.png', dpi=300)
        print("Gráfico guardado como 'grafico_rendimiento_barrido.png'")
        
        # Mostramos la ventana interactiva
        plt.show()

    except Exception as e:
        print(f"\n❌ Ocurrió un error inesperado: {e}")
    
    finally:
        # Limpieza segura del hardware
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
    realizar_benchmark_tiempos()