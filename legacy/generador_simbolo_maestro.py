import numpy as np
import matplotlib.pyplot as plt

def generar_simbolo_ofdm_radar():
    # --- CONFIGURACIÓN ---
    N = 1024              # Número total de subportadoras
    BW = 60e6             # Ancho de banda (60 MHz)
    FS = BW               # Sample Rate coincidente
    
    # 1. Crear el vector de subportadoras en el dominio de la FRECUENCIA
    # Inicialmente todas en cero
    X = np.zeros(N, dtype=np.complex128)
    
    # 2. Definir las bandas de guarda y el centro (DC)
    # Dejamos 100 subportadoras vacías en cada borde para proteger el hardware
    # y 1 subportadora vacía en el centro (DC Null)
    guardia_bordes = 100
    centro = N // 2
    
    # Índices de las subportadoras que SÍ vamos a usar (Activas)
    indices_activas = []
    for i in range(guardia_bordes, N - guardia_bordes):
        if i != centro: # Evitamos la frecuencia central
            indices_activas.append(i)
    
    # 3. Asignar FASES ALEATORIAS a las subportadoras activas
    # Fijamos la semilla (seed) para que siempre genere el mismo símbolo
    np.random.seed(42) 
    fases = np.random.uniform(0, 2*np.pi, len(indices_activas))
    
    # Amplitud constante (1.0) para todas, solo cambia la fase
    # Esto asegura una potencia uniforme en todo el espectro
    X[indices_activas] = np.exp(1j * fases)
    
    # 4. Transformar al dominio del TIEMPO (IFFT)
    x_tiempo = np.fft.ifft(X)
    
    # 5. NORMALIZACIÓN (Paso crítico para el BladeRF)
    # El DAC es de 12 bits, rango -2048 a 2047. 
    # Dejamos un margen de seguridad (Headroom) normalizando a un pico de 1800.
    pico_actual = np.max(np.abs(x_tiempo))
    x_tiempo_escalado = (x_tiempo / pico_actual) * 1800.0
    
    # 6. GUARDAR ARCHIVOS
    # Guardamos el símbolo en tiempo (lo que el BladeRF va a transmitir)
    # Formato complejo de 64 bits para no perder precisión
    np.save("simbolo_ofdm_tiempo.npy", x_tiempo_escalado)
    
    # Guardamos el símbolo en frecuencia (lo que usaremos para dividir RX/TX)
    # Esto es vital para el procesamiento SAR después
    np.save("referencia_ofdm_frecuencia.npy", X)
    
    print("=== SÍMBOLO MAESTRO GENERADO ===")
    print(f"Subportadoras activas: {len(indices_activas)}")
    print(f"Ancho de banda efectivo: {(len(indices_activas) * BW / N) / 1e6:.2f} MHz")
    print("Archivos guardados: 'simbolo_ofdm_tiempo.npy' y 'referencia_ofdm_frecuencia.npy'")

    # --- MINI VISUALIZACIÓN ---
    plt.figure(figsize=(12, 5))
    
    # Ver cómo se ve en el espectro (Frecuencia)
    plt.subplot(1, 2, 1)
    plt.stem(np.abs(X), markerfmt=" ", basefmt="b")
    plt.title("Diseño en Frecuencia (Subportadoras)")
    plt.xlabel("Índice k")
    plt.ylabel("Amplitud")
    
    # Ver cómo se ve en el tiempo (lo que viaja por el aire)
    plt.subplot(1, 2, 2)
    plt.plot(np.real(x_tiempo_escalado), label='Real (I)')
    plt.plot(np.imag(x_tiempo_escalado), label='Imag (Q)', alpha=0.7)
    plt.title("Señal en el Tiempo (1 Símbolo)")
    plt.xlabel("Muestras")
    plt.legend()
    
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    generar_simbolo_ofdm_radar()