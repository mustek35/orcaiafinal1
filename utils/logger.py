import json
import os
from datetime import datetime

class Logger:
    def __init__(self, log_dir="logs"):
        """
        Inicializa el logger y crea la carpeta si no existe.

        Args:
            log_dir (str): Directorio donde guardar los logs.
        """
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

    def guardar_evento(self, evento_data):
        """
        Guarda un evento detallado en un archivo JSON por día.

        Args:
            evento_data (dict): Información del evento.
        """
        fecha = datetime.utcnow().strftime("%Y-%m-%d")
        ruta = os.path.join(self.log_dir, f"log_{fecha}.json")

        # Adjunta timestamp si no lo incluye
        if "timestamp" not in evento_data:
            evento_data["timestamp"] = datetime.utcnow().isoformat()

        # Escribe en modo append
        with open(ruta, "a", encoding="utf-8") as archivo:
            json.dump(evento_data, archivo, ensure_ascii=False)
            archivo.write("\n")  # separa cada línea

    def generar_evento(
        self,
        tipo_evento,
        camara_info,
        accion=None,
        bbox=None,
        ia_info=None,
        modo=None,
        debug_extra=None
    ):
        """
        Crea una estructura de log completa y la guarda.

        Args:
            tipo_evento (str): Descripción del evento (ej: 'Movimiento detectado').
            camara_info (dict): ID, modelo, IP, MAC, tipo.
            accion (dict): Detalles del movimiento PTZ.
            bbox (dict): x, y, w, h del objeto detectado.
            ia_info (dict): Resultado IA, clase, confianza.
            modo (str): Modo actual del sistema.
            debug_extra (dict): Info adicional opcional.
        """
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "evento": tipo_evento,
            "camara": camara_info,
            "bbox": bbox,
            "accion": accion,
            "ia": ia_info,
            "modo": modo,
            "debug_info": debug_extra,
        }
        self.guardar_evento(data)
