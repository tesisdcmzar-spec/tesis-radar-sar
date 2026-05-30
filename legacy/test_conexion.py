import os
import sys

# --- CONFIGURACIÓN DE RUTAS ---
# 1. Ruta de las DLLs (donde pegaste bladerf.dll y libusb-1.0.dll)
directorio_actual = os.path.dirname(os.path.abspath(__file__))
os.add_dll_directory(directorio_actual)

# 2. Ruta de la FPGA (Busca el archivo .rbf que bajaste o que está en C:\Program Files\bladeRF\fpga)
# Si no tenés el archivo .rbf, avisame y lo bajamos.
ruta_fpga = r'X:\RUTA\A\TU\ARCHIVO\hostedxA4.rbf' # <--- CAMBIA ESTO

try:
    from bladerf import _bladerf
    
    # Abrir la placa
    sdr = _bladerf.BladeRF()
    
    print("✅ CONEXIÓN EXITOSA")
    # Atributos correctos en esta versión:
    print(f"📡 Placa: {sdr.board_name}")
    print(f"🆔 Serial: {sdr.serial}")
    
    # Verificar si la FPGA está cargada
    if sdr.is_fpga_configured():
        print("🧠 FPGA: Ya estaba cargada.")
    else:
        print("🧠 FPGA: No cargada. Intentando cargar...")
        if os.path.exists(ruta_fpga):
            sdr.load_fpga(ruta_fpga)
            print("🚀 FPGA cargada con éxito.")
        else:
            print("⚠️ No se encontró el archivo .rbf para cargar la FPGA.")

    sdr.close()
    print("\nTodo listo para empezar la tesis.")

except Exception as e:
    print(f"❌ Error: {e}")