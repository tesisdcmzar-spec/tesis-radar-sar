import numpy as np
import matplotlib.pyplot as plt
import os

def ver_espectro(archivo_npy, sample_rate=40e6):
    print(f"Abriendo {archivo_npy}...")
    if not os.path.exists(archivo_npy):
        print("¡El archivo no existe! Revisa el nombre o la ruta.")
        return

    datos = np.load(archivo_npy)
    datos -= np.mean(datos) # Eliminar offset de la portadora central
    
    # Calcular FFT y convertir a escala logarítmica (dB)
    espectro = np.fft.fftshift(np.fft.fft(datos))
    magnitud_db = 20 * np.log10(np.abs(espectro) + 1e-12)
    
    # Eje X en MHz
    frecuencias = np.linspace(-sample_rate/2, sample_rate/2, len(magnitud_db)) / 1e6

    plt.figure(figsize=(10, 5))
    plt.plot(frecuencias, magnitud_db, color='blue', linewidth=1)
    plt.axvline(x=5.0, color='red', linestyle='--', label='Tono Enviado (5 MHz)')
    plt.title(f"Espectro Capturado - {os.path.basename(archivo_npy)}")
    plt.xlabel("Frecuencia Baseband (MHz)")
    plt.ylabel("Potencia (dB)")
    plt.grid(True, alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    # Apunta a un archivo que sepas que se generó
    archivo = "capturas_fullduplex_offset/cap_offset_010_700MHz.npy" 
    ver_espectro(archivo)