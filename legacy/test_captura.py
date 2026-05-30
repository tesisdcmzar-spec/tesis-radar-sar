import os
import numpy as np
import matplotlib.pyplot as plt
import bladerf

# 1. CONFIGURACIÓN DE ACCESO AL HARDWARE
# Registramos la carpeta donde están las DLLs para que Python pueda hablar con la placa
directorio_actual = os.path.dirname(os.path.abspath(__file__))
os.add_dll_directory(directorio_actual)

# 2. SOLUCIÓN DE COMPATIBILIDAD (HACK)
# Creamos un objeto que imita el formato SC16_Q11 (16 bits complejos) 
# Esto evita errores de nombres en diferentes versiones de la librería
class BladeRFConst:
    def __init__(self, val): self.value = val
SC16_Q11 = BladeRFConst(0)

def test_captura():
    sdr = None
    try:
        # 3. INICIALIZACIÓN
        print("Conectando con bladeRF...")
        sdr = bladerf.BladeRF()
        
        # Parámetros de la prueba
        f_central = 95_500_000   # Frecuencia en Hercios (95.5 MHz)
        f_muestreo = 2_000_000   # Ancho de banda a capturar (2 MHz)
        ganancia = 25            # Nivel de amplificación (dB)
        n_muestras = 32768       # Cantidad de puntos (potencia de 2 para velocidad)

        # 4. CONFIGURACIÓN DEL CANAL RX
        canal = sdr.Channel(bladerf.CHANNEL_RX(0))
        canal.frequency = f_central
        canal.sample_rate = f_muestreo
        canal.gain = ganancia

        # 5. CONFIGURACIÓN DEL FLUJO DE DATOS (BUFFERS)
        # Preparamos la "tubería" por donde viajarán las muestras IQ
        sdr.sync_config(layout=SC16_Q11, fmt=SC16_Q11, num_buffers=16, 
                        buffer_size=8192, num_transfers=8, stream_timeout=1000)

        # 6. CAPTURA REAL
        canal.enable = True
        muestras_raw = np.empty(n_muestras * 2, dtype=np.int16) # Espacio para I y Q
        print(f"Capturando {f_muestreo/1e6} MHz de espectro...")
        sdr.sync_rx(muestras_raw, n_muestras)
        
        # Cerramos conexión para liberar la placa
        canal.enable = False
        sdr.close()

        # 7. PROCESAMIENTO MATEMÁTICO (DSP)
        # Convertimos los números enteros en números complejos (I + jQ)
        iq = muestras_raw[0::2].astype(float) + 1j * muestras_raw[1::2].astype(float)
        iq -= np.mean(iq) # Eliminamos el pico central (DC Offset)

        # Transformada de Fourier: Convertimos el tiempo en frecuencia
        # La fórmula es: $$X(f) = \int_{-\infty}^{\infty} x(t) e^{-j2\pi ft} dt$$
        espectro = np.fft.fftshift(np.fft.fft(iq))
        # Pasamos a escala logarítmica (Decibelios) para visualizar mejor la potencia
        psd = 20 * np.log10(np.abs(espectro) / n_muestras + 1e-12)

        # 8. GENERACIÓN DE LA IMAGEN
        f_eje = np.linspace(f_central - f_muestreo/2, f_central + f_muestreo/2, len(psd))
        plt.figure(figsize=(10, 5))
        plt.plot(f_eje / 1e6, psd, color='red', linewidth=0.7)
        plt.title(f"Testeo de Espectro - bladeRF ({f_central/1e6} MHz)")
        plt.xlabel("Frecuencia [MHz]")
        plt.ylabel("Potencia [dBFS]")
        plt.grid(True, alpha=0.3)
        plt.show()

    except Exception as e:
        print(f"Error en el testeo: {e}")
        if sdr: sdr.close()

if __name__ == "__main__":
    test_captura()