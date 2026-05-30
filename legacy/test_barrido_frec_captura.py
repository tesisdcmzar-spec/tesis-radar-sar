import time
import os
import numpy as np
import bladerf

# --- EL "HACK" MÁGICO PARA LA LIBRERÍA ---
# Creamos un objeto que imita a los enumeradores de BladeRF
class FormatoFalso:
    def __init__(self, val):
        self.value = val

# 0 es el valor numérico interno en C para SC16_Q11 y RX_X1
SC16_Q11 = FormatoFalso(0)
RX_X1 = FormatoFalso(0)

def ejecutar_barrido_prueba():
    # --- PARÁMETROS CONFIGURABLES ---
    FREQ_INICIAL = 100e6      
    FREQ_FINAL = 6000e6       
    PASO_FREQ = 60e6          
    SAMPLE_RATE = 40e6        # 40 MHz para estabilidad
    BANDWIDTH = 40e6          
    NUM_SAMPLES = 40000       # 1 ms de captura

    tiempos_sintonia_lo = []
    tiempos_captura = []
    tamanos_archivos = []
    
    directorio_salida = "capturas_barrido"
    if not os.path.exists(directorio_salida):
        os.makedirs(directorio_salida)

    print("Iniciando BladeRF...")
    sdr = None
    
    try:
        sdr = bladerf.BladeRF()
        
        # 1. SELECCIÓN DEL CANAL
        canal = sdr.Channel(bladerf.CHANNEL_RX(0))
        canal.sample_rate = int(SAMPLE_RATE)
        canal.bandwidth = int(BANDWIDTH)
        canal.gain = 60 # Ganancia alta como en el blog para asegurar que vemos el ruido de fondo
        
        # 2. CONFIGURACIÓN DEL BUFFER SINCRO (Usando el Hack)
        print("Configurando interfaz sincrónica con el 'Hack' de formato...")
        sdr.sync_config(
            layout=RX_X1, 
            fmt=SC16_Q11, 
            num_buffers=16,
            buffer_size=8192,
            num_transfers=8,
            stream_timeout=3500 # Subimos el timeout a 3.5s como en el blog por seguridad
        )

        # 3. PREPARAR EL BUFFER (4 bytes por muestra)
        buffer_rx = bytearray(NUM_SAMPLES * 4)
        
        # Habilitamos recepción
        canal.enable = True

        frecuencia_actual = FREQ_INICIAL
        paso_num = 0

        print(f"🚀 Iniciando barrido: {FREQ_INICIAL/1e6} MHz a {FREQ_FINAL/1e6} MHz...")

        while frecuencia_actual <= FREQ_FINAL:
            # --- SINTONÍA ---
            t_inicio_lo = time.perf_counter()
            canal.frequency = int(frecuencia_actual) 
            t_fin_lo = time.perf_counter()
            tiempos_sintonia_lo.append((t_fin_lo - t_inicio_lo) * 1000)

            # --- CAPTURA ---
            t_inicio_rx = time.perf_counter()
            sdr.sync_rx(buffer_rx, NUM_SAMPLES) 
            t_fin_rx = time.perf_counter()
            tiempos_captura.append((t_fin_rx - t_inicio_rx) * 1000)

            # --- PROCESAMIENTO Y GUARDADO ---
            # Mismo procesamiento del blog
            datos_crudos = np.frombuffer(buffer_rx, dtype=np.int16)
            datos_iq = datos_crudos[0::2].astype(float) + 1j * datos_crudos[1::2].astype(float)
            datos_iq /= 2048.0 # Normalizamos la amplitud (-1.0 a 1.0)

            nombre_archivo = os.path.join(directorio_salida, f"cap_{paso_num:03d}_{int(frecuencia_actual/1e6)}MHz.npy")
            np.save(nombre_archivo, datos_iq)
            tamanos_archivos.append(os.path.getsize(nombre_archivo) / 1024)

            # Imprimir progreso cada 10 saltos para no saturar la consola
            if paso_num % 10 == 0:
                print(f"Progreso: Capturado {int(frecuencia_actual/1e6)} MHz...")

            frecuencia_actual += PASO_FREQ
            paso_num += 1

        canal.enable = False

        # --- REPORTE FINAL ---
        prom_lo = np.mean(tiempos_sintonia_lo)
        prom_rx = np.mean(tiempos_captura)
        peso_total = sum(tamanos_archivos)/1024

        resumen = (
            "========================================\n"
            "   RESULTADOS DEL EXPERIMENTO\n"
            "========================================\n"
            f"Pasos totales: {paso_num}\n"
            f"Tiempo Promedio LO (Sintonía): {prom_lo:.4f} ms\n"
            f"Tiempo Promedio RX (Captura): {prom_rx:.4f} ms\n"
            f"Tiempo Total Real del Barrido: {(sum(tiempos_sintonia_lo) + sum(tiempos_captura)):.2f} ms\n"
            f"Peso TOTAL en disco: {peso_total:.2f} MB\n"
            "========================================"
        )
        print("\n" + resumen)
        with open("estadisticas_barrido.txt", "w") as f:
            f.write(resumen)
            
        print("\n[✓] Barrido finalizado con éxito.")

    except Exception as e:
        print(f"\n❌ Ocurrió un error inesperado: {e}")
    
    finally:
        if sdr is not None:
            print("Cerrando BladeRF y liberando puerto USB...")
            try:
                sdr.close()
            except:
                pass

if __name__ == "__main__":
    ejecutar_barrido_prueba()