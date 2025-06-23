import os
import uuid
import cv2
from datetime import datetime, timedelta
from collections import defaultdict

# Importación robusta de ImageSaverThread con manejo de errores
try:
    from gui.image_saver import ImageSaverThread
    IMAGESAVER_AVAILABLE = True
    print("✅ ImageSaverThread importado correctamente en gestor_alertas optimizado")
except ImportError as e:
    print(f"❌ Error importando ImageSaverThread: {e}")
    IMAGESAVER_AVAILABLE = False
    # Fallback: crear una clase mock
    from PyQt6.QtCore import QThread
    class ImageSaverThread(QThread):
        def __init__(self, *args, **kwargs):
            super().__init__()
            print("⚠️ Usando ImageSaverThread mock - revisar importaciones")
        def run(self):
            print("⚠️ ImageSaverThread mock ejecutado")

# Configuración de debug para logs detallados
DEBUG_LOGS = False  # Cambiar a True solo para debugging

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
        
        # VARIABLES PARA CONTROL OPTIMIZADO DE CAPTURAS
        self.track_capture_history = {}  # track_id -> {"captured": bool, "best_conf": float, "last_capture_time": datetime}
        self.confidence_threshold = 0.70  # Umbral mínimo de confianza para captura
        self.min_time_between_captures = 30  # Segundos mínimos entre capturas del mismo track
        self.track_confidence_buffer = defaultdict(list)  # track_id -> [conf1, conf2, ...] para promedio

    def procesar_detecciones(self, boxes, last_frame, log_callback, cam_data):
        if datetime.now() - self.ultimo_reset > timedelta(minutes=1):
            self.capturas_realizadas = 0
            self.ultimo_reset = datetime.now()

        hay_persona = hay_bote = hay_auto = hay_embarcacion = False
        boxes_personas, boxes_botes, boxes_autos, boxes_embarcaciones = [], [], [], []

        modelos_cam = cam_data.get("modelos") or [cam_data.get("modelo")]
        
        # Solo log si hay detecciones para procesar
        if len(boxes) > 0:
            log_callback(f"GestorAlertas: Procesando {len(boxes)} detecciones")

        for box in boxes:
            # Soportar ambos formatos: (x1,y1,x2,y2,cls) y (x1,y1,x2,y2,cls,cx,cy,track_id,conf)
            if len(box) == 5:
                x1, y1, x2, y2, cls = box
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                track_id = f"legacy_{cls}_{cx}_{cy}"
                conf = cam_data.get("confianza", 0.5)
            elif len(box) >= 9:
                x1, y1, x2, y2, cls, cx, cy, track_id, conf = box[:9]
            else:
                log_callback(f"⚠️ Formato de box no soportado: {len(box)} elementos")
                continue

            log_callback(f"GestorAlertas: Track={track_id} cls={cls} conf={conf:.2f} en ({cx}, {cy})")

            # Manejo mejorado de las clases según el modelo
            if "Embarcaciones" in modelos_cam and cls == 1:
                boxes_embarcaciones.append((x1, y1, x2, y2, cls, cx, cy, track_id, conf))
                hay_embarcacion = True
                # Solo log para primeras detecciones o altas confianzas
                if conf >= 0.70:
                    log_callback(f"🚢 Embarcación detectada (Track={track_id}, conf={conf:.2f})")
                continue

            # Detecciones de otros modelos
            if cls == 0:
                boxes_personas.append((x1, y1, x2, y2, cls, cx, cy, track_id, conf))
                hay_persona = True
                if conf >= 0.70:
                    log_callback(f"👤 Persona detectada (Track={track_id}, conf={conf:.2f})")
            elif cls == 2:
                boxes_autos.append((x1, y1, x2, y2, cls, cx, cy, track_id, conf))
                hay_auto = True
                if conf >= 0.70:
                    log_callback(f"🚗 Auto detectado (Track={track_id}, conf={conf:.2f})")
            elif cls == 8 or cls == 9:
                boxes_botes.append((x1, y1, x2, y2, cls, cx, cy, track_id, conf))
                hay_bote = True
                if conf >= 0.70:
                    log_callback(f"⛵ Barco detectado (Track={track_id}, conf={conf:.2f})")

        # Procesar cada tipo de detección
        if hay_persona:
            self.box_streak += 1
        else:
            self.box_streak = 0

        if self.box_streak >= 3:
            self._guardar_optimizado(boxes_personas, last_frame, log_callback, tipo='personas', cam_data=cam_data)

        if hay_bote:
            self._guardar_optimizado(boxes_botes, last_frame, log_callback, tipo='barcos', cam_data=cam_data)

        if hay_auto:
            self._guardar_optimizado(boxes_autos, last_frame, log_callback, tipo='autos', cam_data=cam_data)

        if hay_embarcacion:
            self._guardar_optimizado(boxes_embarcaciones, last_frame, log_callback, tipo='embarcaciones', cam_data=cam_data)

        # Actualizar temporal (para visualización en grilla)
        self.temporal.clear()
        if last_frame is not None:
            h, w, _ = last_frame.shape
            for box in boxes:
                # Extraer coordenadas según el formato
                if len(box) == 5:
                    x1, y1, x2, y2, cls = box
                elif len(box) >= 9:
                    x1, y1, x2, y2, cls = box[:5]
                else:
                    continue
                    
                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2
                fila = int(cy / h * self.filas)
                columna = int(cx / w * self.columnas)
                index = fila * self.columnas + columna
                self.temporal.add(index)

    def _ha_habido_movimiento(self, clase, cx, cy, umbral=25):
        cx_prev, cy_prev = self.ultimas_posiciones.get(clase, (None, None))
        if cx_prev is None:
            self.ultimas_posiciones[clase] = (cx, cy)
            return True

        distancia = ((cx - cx_prev)**2 + (cy - cy_prev)**2)**0.5
        if distancia > umbral:
            self.ultimas_posiciones[clase] = (cx, cy)
            return True
        return False

    def _should_capture_track(self, track_id, confidence, log_callback):
        """
        Determina si se debe capturar una imagen del track basado en:
        1. Confianza mínima
        2. Si ya se capturó antes
        3. Tiempo mínimo entre capturas del mismo track
        """
        now = datetime.now()
        
        # Obtener historial del track
        track_history = self.track_capture_history.get(track_id, {
            "captured": False, 
            "best_conf": 0.0, 
            "last_capture_time": None
        })
        
        # Agregar confianza al buffer para promedio
        conf_buffer = self.track_confidence_buffer[track_id]
        conf_buffer.append(confidence)
        if len(conf_buffer) > 5:  # Mantener solo las últimas 5 detecciones
            conf_buffer.pop(0)
        
        # Calcular confianza promedio
        avg_confidence = sum(conf_buffer) / len(conf_buffer)
        
        # Verificar si la confianza promedio supera el umbral
        if avg_confidence < self.confidence_threshold:
            if DEBUG_LOGS:  # Solo mostrar en modo debug
                log_callback(f"🔶 Track {track_id}: Confianza promedio {avg_confidence:.2f} < {self.confidence_threshold}")
            return False
        
        # Si ya se capturó este track, verificar tiempo mínimo
        if track_history["captured"] and track_history["last_capture_time"]:
            time_since_last = (now - track_history["last_capture_time"]).total_seconds()
            if time_since_last < self.min_time_between_captures:
                if DEBUG_LOGS:  # Solo mostrar en modo debug
                    log_callback(f"🔶 Track {track_id}: Solo han pasado {time_since_last:.1f}s desde última captura")
                return False
        
        # Si la confianza actual es significativamente mejor que la anterior
        confidence_improvement = confidence - track_history["best_conf"]
        if track_history["captured"] and confidence_improvement < 0.10:
            if DEBUG_LOGS:  # Solo mostrar en modo debug
                log_callback(f"🔶 Track {track_id}: Confianza {confidence:.2f} no es suficientemente mejor que {track_history['best_conf']:.2f}")
            return False
        
        # Solo log cuando se apruebe una captura
        log_callback(f"✅ Track {track_id}: Aprobado para captura (conf: {confidence:.2f}, prom: {avg_confidence:.2f})")
        return True

    def _update_track_capture_history(self, track_id, confidence):
        """Actualiza el historial de capturas del track"""
        now = datetime.now()
        self.track_capture_history[track_id] = {
            "captured": True,
            "best_conf": max(confidence, self.track_capture_history.get(track_id, {}).get("best_conf", 0.0)),
            "last_capture_time": now
        }

    def _guardar_optimizado(self, boxes, frame, log_callback, tipo, cam_data):
        """
        Versión optimizada del guardado que evita capturas repetitivas
        y solo captura cuando se alcanza confianza mínima
        """
        if not boxes:  # No procesar si no hay detecciones
            return
            
        if DEBUG_LOGS:
            log_callback(f"GestorAlertas._guardar_optimizado: Evaluando {len(boxes)} detecciones de tipo '{tipo}'")
        
        if self.capturas_realizadas >= self.max_capturas:
            if DEBUG_LOGS:
                log_callback(f"🔶 Límite de capturas alcanzado ({self.capturas_realizadas}/{self.max_capturas})")
            return
        
        # VERIFICACIÓN DE DISPONIBILIDAD DE IMAGESAVER
        if not IMAGESAVER_AVAILABLE:
            log_callback(f"⚠️ ImageSaverThread no disponible - saltando captura de {tipo}")
            return
        
        for box_data in boxes:
            if len(box_data) >= 7:  # Con track_id
                x1, y1, x2, y2, cls, cx, cy, track_id, confidence = box_data[:9] 
            else:  # Sin track_id (fallback)
                x1, y1, x2, y2, cls, cx, cy = box_data
                track_id = f"unknown_{cls}_{cx}_{cy}"  # ID temporal
                confidence = cam_data.get("confianza", 0.5)  # Confianza por defecto
            
            if frame is not None:
                # Verificar movimiento (criterio existente)
                if not self._ha_habido_movimiento(cls, cx, cy):
                    if DEBUG_LOGS:
                        log_callback(f"🔶 Track {track_id}: Sin movimiento suficiente")
                    continue

                # NUEVA LÓGICA: Verificar si se debe capturar basado en confianza y historial
                if not self._should_capture_track(track_id, confidence, log_callback):
                    continue

                if self.capturas_realizadas >= self.max_capturas:
                    if DEBUG_LOGS:
                        log_callback(f"🔶 Límite de capturas alcanzado durante procesamiento")
                    break

                modelos_cam = cam_data.get("modelos") or [cam_data.get("modelo", "desconocido")]
                modelo = modelos_cam[0] if modelos_cam else "desconocido"
                
                if DEBUG_LOGS:
                    log_callback(f"GestorAlertas._guardar_optimizado: Capturando track {track_id}, cls={cls}, conf={confidence:.2f}, modelo={modelo}, tipo={tipo}")

                # CREACIÓN PROTEGIDA DE IMAGESAVERTHREAD
                try:
                    hilo = ImageSaverThread(
                        frame=frame,
                        bbox=(x1, y1, x2, y2),
                        cls=cls,
                        coordenadas=(cx, cy),
                        modelo=modelo,
                        confianza=confidence
                    )
                    hilo.finished.connect(lambda h=hilo: self._eliminar_hilo(h))
                    self.hilos_guardado.append(hilo)
                    hilo.start()

                    # Actualizar historial y contadores
                    self._update_track_capture_history(track_id, confidence)
                    self.capturas_realizadas += 1
                    
                    # Solo mostrar log importante: captura realizada
                    log_callback(f"📸 Captura realizada - Track {track_id} - {tipo[:-1].capitalize()} (conf: {confidence:.2f})")
                    if DEBUG_LOGS:
                        log_callback(f"🖼️ Total capturas: {self.capturas_realizadas}/{self.max_capturas}")
                
                except Exception as e:
                    error_msg = f"❌ Error creando ImageSaverThread para track {track_id}: {e}"
                    print(error_msg)
                    log_callback(error_msg)

    def _guardar(self, boxes, frame, log_callback, tipo, cam_data):
        """Método original mantenido para compatibilidad (ahora usa la versión optimizada)"""
        # Convertir formato si es necesario
        boxes_with_track = []
        for box_data in boxes:
            if len(box_data) == 7:  # (x1, y1, x2, y2, cls, cx, cy)
                x1, y1, x2, y2, cls, cx, cy = box_data
                # Generar track_id temporal y confianza por defecto
                track_id = f"legacy_{cls}_{cx}_{cy}"
                confidence = cam_data.get("confianza", 0.5)
                boxes_with_track.append((x1, y1, x2, y2, cls, cx, cy, track_id, confidence))
            else:
                boxes_with_track.append(box_data)
        
        self._guardar_optimizado(boxes_with_track, frame, log_callback, tipo, cam_data)

    def _eliminar_hilo(self, hilo):
        if hilo in self.hilos_guardado:
            self.hilos_guardado.remove(hilo)

    def limpiar_historial_tracks(self, tracks_activos):
        """
        Limpia el historial de tracks que ya no están activos
        Llamar periódicamente para evitar acumulación de memoria
        """
        tracks_a_eliminar = []
        for track_id in self.track_capture_history.keys():
            if track_id not in tracks_activos:
                tracks_a_eliminar.append(track_id)
        
        for track_id in tracks_a_eliminar:
            self.track_capture_history.pop(track_id, None)
            self.track_confidence_buffer.pop(track_id, None)

    def configurar_capturas(self, confidence_threshold=0.70, min_time_between=30, max_capturas=3):
        """
        Permite configurar los parámetros de captura
        """
        self.confidence_threshold = confidence_threshold
        self.min_time_between_captures = min_time_between
        self.max_capturas = max_capturas