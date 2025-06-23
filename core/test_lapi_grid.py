import requests
from requests.auth import HTTPDigestAuth
import base64

def decodificar_grid_base64(grid_b64):
    """
    Decodifica la cadena Base64 del campo 'Grid' y devuelve una lista de bits (0 o 1).
    """
    grid_bytes = base64.b64decode(grid_b64)
    bits = []
    for byte in grid_bytes:
        for i in range(8):
            bits.append((byte >> (7 - i)) & 1)
    return bits

def escanear_grillas(ip, usuario, contrasena, max_canales=8):
    print(f"📡 Escaneando {ip} para detectar grillas activas...\n")

    for canal in range(max_canales):
        url = f"http://{ip}/LAPI/V1.0/Channels/{canal}/Alarm/MotionDetection/Areas/Grid"
        try:
            response = requests.get(url, auth=HTTPDigestAuth(usuario, contrasena), timeout=5)
            data = response.json()
            response_data = data.get("Response", {})

            print(f"🟦 Canal {canal} - Código: {response_data.get('ResponseCode')}")

            grid_data = response_data.get("Data", {})
            grid_b64 = grid_data.get("Grid")

            if grid_b64:
                bits = decodificar_grid_base64(grid_b64)
                activadas = sum(bits)
                print(f"✅ Grid encontrada: {len(bits)} celdas totales")
                print(f"🟩 Celdas activadas: {activadas}")
                print(f"🧪 Primeros 50 bits: {bits[:50]}")
            else:
                print("⚠️ No se encontró el campo 'Grid' o está vacío.")

            print("-" * 70)

        except Exception as e:
            print(f"❌ Error en canal {canal}: {e}")

if __name__ == "__main__":
    ip = "19.10.10.132"
    usuario = "admin"
    contrasena = "/remoto753524"
    escanear_grillas(ip, usuario, contrasena)
