# ===== SCRIPT DE VERIFICACIÓN: verificar_gestor.py =====
# Ejecuta este script para verificar el estado actual del archivo

import os

def verificar_gestor_alertas():
    archivo = "core/gestor_alertas.py"
    
    if not os.path.exists(archivo):
        print(f"❌ El archivo {archivo} NO existe")
        return
    
    print(f"📁 Verificando archivo: {archivo}")
    
    with open(archivo, 'r', encoding='utf-8') as f:
        contenido = f.read()
    
    # Verificar importaciones
    if "from gui.image_saver import ImageSaverThread" in contenido:
        print("✅ Importación de ImageSaverThread encontrada")
    else:
        print("❌ Importación de ImageSaverThread NO encontrada")
    
    # Verificar método _procesar_y_guardar
    if "_procesar_y_guardar" in contenido:
        print("✅ Método _procesar_y_guardar encontrado")
    else:
        print("❌ Método _procesar_y_guardar NO encontrado")
    
    # Contar líneas
    lineas = contenido.split('\n')
    print(f"📊 El archivo tiene {len(lineas)} líneas")
    
    # Verificar línea 241 específicamente
    if len(lineas) >= 241:
        linea_241 = lineas[240].strip()  # línea 241 (índice 240)
        print(f"📍 Línea 241: '{linea_241}'")
        
        # Buscar context alrededor de línea 241
        inicio = max(0, 240 - 3)
        fin = min(len(lineas), 240 + 4)
        print("🔍 Contexto alrededor de línea 241:")
        for i in range(inicio, fin):
            marcador = ">>> " if i == 240 else "    "
            print(f"{marcador}{i+1:3d}: {lineas[i]}")
    else:
        print(f"❌ El archivo solo tiene {len(lineas)} líneas, no llega a la línea 241")
    
    # Buscar todas las ocurrencias de ImageSaverThread
    print("\n🔍 Ocurrencias de 'ImageSaverThread' en el archivo:")
    for i, linea in enumerate(lineas, 1):
        if "ImageSaverThread" in linea:
            print(f"    Línea {i}: {linea.strip()}")
    
    return contenido

def backup_y_reemplazar():
    """Crear backup del archivo actual y reemplazarlo con la versión corregida."""
    archivo_original = "core/gestor_alertas.py"
    archivo_backup = "core/gestor_alertas.py.backup"
    
    # Hacer backup
    if os.path.exists(archivo_original):
        with open(archivo_original, 'r', encoding='utf-8') as f:
            contenido_original = f.read()
        with open(archivo_backup, 'w', encoding='utf-8') as f:
            f.write(contenido_original)
        print(f"💾 Backup creado: {archivo_backup}")
    
    # Escribir la versión corregida
    contenido_nuevo = '''import os
import uuid
import cv2
from datetime import datetime, timedelta

# Importación específica y clara de ImageSaverThread
try:
    from gui.image_saver import ImageSaverThread
    print("✅ ImageSaverThread importado correctamente")
except ImportError as e:
    print(f"❌ Error importando ImageSaverThread: {e}")
    # Fallback: crear una clase mock para evitar crashes
    from PyQt6.QtCore import QThread
    class ImageSaverThread(QThread):
        def __init__(self, *args, **kwargs):
            super().__init__()
            print("⚠️ Usando ImageSaverThread mock - revisar importaciones")
        def run(self):
            print("⚠️ ImageSaverThread mock ejecutado")

class GestorAlertas:
    def __init__(self, cam_id, filas, columnas):
        self.cam_id = cam_id
        self.filas = filas
        self.columnas = columnas
        self.box_streak = 0
        self.deteccion_bote_streak = 0
        self.capturas_realizadas = 0
        self.max_capturas = 3
        self.ultimo_reset = datetime.now()
        self.temporal = set()
        self.hilos_guardado = []
        self.ultimas_posiciones = {}

    def procesar_detecciones(self, boxes, last_frame, log_callback, cam_data):
        """Procesa las detecciones y activa las alertas correspondientes."""
        if datetime.now() - self.ultimo_reset > timedelta(minutes=1):
            self.capturas_realizadas = 0
            self.ultimo_reset = datetime.now()

        hay_persona = hay_bote = hay_auto = hay_embarcacion = False
        boxes_personas, boxes_botes, boxes_autos, boxes_embarcaciones = [], [], [], []

        for box in boxes:
            if len(box) != 5:
                continue

            x1, y1, x2, y2, cls = box
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)

            modelos_cam = cam_data.get("modelos") or [cam_data.get("modelo")]
            # Only treat detections as coming from the specialised
            # "Embarcaciones" model when the remapped class id (1) matches.
            if "Embarcaciones" in modelos_cam and cls == 1:
                boxes_embarcaciones.append((x1, y1, x2, y2, cls, cx, cy))
                hay_embarcacion = True
                continue

            if cls == 0:
                boxes_personas.append((x1, y1, x2, y2, cls, cx, cy))
                hay_persona = True
            elif cls == 2:
                boxes_autos.append((x1, y1, x2, y2, cls, cx, cy))
                hay_auto = True
            elif cls == 8:
                boxes_botes.append((x1, y1, x2, y2, cls, cx, cy))
                hay_bote = True

        if hay_persona:
            self.box_streak += 1
        else:
            self.box_streak = 0

        if self.box_streak >= 3:
            self._procesar_y_guardar(boxes_personas, last_frame, log_callback, 'personas', cam_data)

        if hay_bote:
            self._procesar_y_guardar(boxes_botes, last_frame, log_callback, 'barcos', cam_data)

        if hay_auto:
            self._procesar_y_guardar(boxes_autos, last_frame, log_callback, 'autos', cam_data)

        if hay_embarcacion:
            self._procesar_y_guardar(boxes_embarcaciones, last_frame, log_callback, 'embarcaciones', cam_data)

        self.temporal.clear()
        if last_frame is not None:
            h, w, _ = last_frame.shape
            for box in boxes:
                if len(box) != 5:
                    continue
                x1, y1, x2, y2, cls = box
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                fila = int(cy / h * self.filas)
                columna = int(cx / w * self.columnas)
                index = fila * self.columnas + columna
                self.temporal.add(index)

    def _ha_habido_movimiento(self, clase, cx, cy, umbral=25):
        """Verifica si ha habido movimiento significativo."""
        cx_prev, cy_prev = self.ultimas_posiciones.get(clase, (None, None))
        if cx_prev is None:
            self.ultimas_posiciones[clase] = (cx, cy)
            return True

        distancia = ((cx - cx_prev)**2 + (cy - cy_prev)**2)**0.5
        if distancia > umbral:
            self.ultimas_posiciones[clase] = (cx, cy)
            return True
        return False

    def _procesar_y_guardar(self, boxes, frame, log_callback, tipo, cam_data):
        """Método unificado para procesar y guardar detecciones."""
        print(f"🎯 _procesar_y_guardar llamado para tipo={tipo}, boxes={len(boxes)}")
        
        for (x1, y1, x2, y2, cls, cx, cy) in boxes:
            if self.capturas_realizadas >= self.max_capturas:
                break
                
            if frame is not None:
                if not self._ha_habido_movimiento(cls, cx, cy):
                    continue

                modelos_cam = cam_data.get("modelos") or [cam_data.get("modelo", "desconocido")]
                modelo = modelos_cam[0] if modelos_cam else "desconocido"
                confianza = cam_data.get("confianza", 0.5)

                try:
                    print(f"🔧 Creando ImageSaverThread para clase {cls}, tipo {tipo}")
                    hilo = ImageSaverThread(
                        frame=frame,
                        bbox=(x1, y1, x2, y2),
                        cls=cls,
                        coordenadas=(cx, cy),
                        modelo=modelo,
                        confianza=confianza
                    )
                    hilo.finished.connect(lambda h=hilo: self._eliminar_hilo(h))
                    self.hilos_guardado.append(hilo)
                    hilo.start()

                    self.capturas_realizadas += 1
                    log_callback(f"🟢 Movimiento detectado - {tipo[:-1].capitalize()} (clase {cls}) en ({cx}, {cy})")
                    log_callback(f"🖼️ Captura {tipo} guardada en segundo plano")
                    
                except Exception as e:
                    error_msg = f"❌ Error creando ImageSaverThread: {e}"
                    print(error_msg)
                    log_callback(error_msg)

    # Métodos de compatibilidad hacia atrás
    def _guardar(self, boxes, frame, log_callback, tipo, cam_data):
        """Método de compatibilidad - redirige al método principal."""
        return self._procesar_y_guardar(boxes, frame, log_callback, tipo, cam_data)

    def _guardar_optimizado(self, boxes, frame, log_callback, tipo, cam_data):
        """Método de compatibilidad - redirige al método principal."""
        return self._procesar_y_guardar(boxes, frame, log_callback, tipo, cam_data)

    def _eliminar_hilo(self, hilo):
        """Elimina un hilo terminado de la lista."""
        if hilo in self.hilos_guardado:
            self.hilos_guardado.remove(hilo)
'''
    
    with open(archivo_original, 'w', encoding='utf-8') as f:
        f.write(contenido_nuevo)
    
    print(f"✅ Archivo actualizado: {archivo_original}")

if __name__ == "__main__":
    print("🔍 VERIFICACIÓN DEL ARCHIVO GESTOR_ALERTAS.PY")
    print("=" * 50)
    
    contenido_actual = verificar_gestor_alertas()
    
    print("\n" + "=" * 50)
    respuesta = input("¿Quieres reemplazar el archivo con la versión corregida? (s/N): ")
    
    if respuesta.lower() in ['s', 'si', 'sí', 'y', 'yes']:
        backup_y_reemplazar()
        print("✅ Archivo reemplazado. Reinicia tu aplicación.")
    else:
        print("❌ No se realizaron cambios.")