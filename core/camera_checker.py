import requests
from requests.auth import HTTPDigestAuth

def verificar_configuracion_grilla(ip, usuario, contrasena):
    resultados = []

    def agregar_resultado(endpoint, estado, detalle, extra=None):
        item = {
            "endpoint": endpoint,
            "estado": estado,
            "detalle": detalle
        }
        if extra:
            item.update(extra)
        resultados.append(item)

    try:
        url_info = f"http://{ip}/LAPI/V1.0/System/DeviceInfo"
        response = requests.get(url_info, auth=HTTPDigestAuth(usuario, contrasena), timeout=5)
        r_json = response.json()
        data = r_json.get("Response", {}).get("Data", {})
        modelo = data.get("DeviceModel", data.get("Model", "Desconocido"))
        serial = data.get("SerialNumber", "?")
        agregar_resultado("System/DeviceInfo", "✅", f"Modelo {modelo}, Serial {serial}")
    except Exception as e:
        agregar_resultado("System/DeviceInfo", "❌", str(e))
        return resultados

    endpoints = [
        "System/FunctionList",
        "Channels/0/Alarm/MotionDetection",
        "Channels/0/Alarm/MotionDetection/Areas/Grid",
        "Channels/0/Alarm/MotionDetection/WeekPlan",
        "Channels/0/Smart/IntrusionDetection",
        "Channels/0/Smart/IntrusionDetection/Areas",
        "Channels/0/Smart/IntrusionDetection/WeekPlan",
        "Channels/0/Smart/CrossLineDetection",
        "Channels/0/Smart/CrossLineDetection/Areas",
        "Channels/0/Smart/CrossLineDetection/WeekPlan",
        "Media/Snapshot",
        "PTZ/AbsoluteMove",
        "PTZ/GotoPreset"
    ]

    for endpoint in endpoints:
        url = f"http://{ip}/LAPI/V1.0/{endpoint}"
        try:
            r = requests.get(url, auth=HTTPDigestAuth(usuario, contrasena), timeout=5)
            try:
                json_data = r.json()
                detalle = "JSON válido"
                extra = {}
                if endpoint.endswith("/MotionDetection/Areas/Grid"):
                    grid_data = json_data.get("Response", {}).get("Data", {}).get("GridArea", {})
                    extra = {
                        "filas": grid_data.get("Rows"),
                        "columnas": grid_data.get("Columns"),
                        "area": grid_data.get("Area", [])
                    }
                    detalle += f" – Área recibida ({extra['filas']}x{extra['columnas']})"
                agregar_resultado(endpoint, "✅", detalle, extra)
            except Exception:
                texto = r.text.strip().replace("\n", " ")[:200]
                agregar_resultado(endpoint, "⚠️", f"No JSON: {texto}...")
        except Exception as e:
            agregar_resultado(endpoint, "❌", str(e))

    return resultados
