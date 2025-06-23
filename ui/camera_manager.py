import json
import os

CONFIG_PATH = "config.json"

def guardar_camaras(main_window):
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
    else:
        data = {}

    data["camaras"] = main_window.camera_data_list

    if hasattr(main_window, 'config_tab'):
        data["configuracion"] = main_window.config_tab.obtener_config()

    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)

def cargar_camaras_guardadas(main_window):
    if not os.path.exists(CONFIG_PATH):
        return

    with open(CONFIG_PATH, "r") as f:
        data = json.load(f)

    camaras = data.get("camaras", [])
    for cam in camaras:
        main_window.camera_data_list.append(cam)
        main_window.camera_list.addItem(f"{cam['ip']} - {cam['tipo']}")
        main_window.start_camera_stream(cam)
