# gui/grilla_widget.py - VERSIÓN MEJORADA CON MUESTREO ADAPTATIVO - CORREGIDA
from PyQt6.QtWidgets import (
    QWidget, QSizePolicy, QMenu, QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QLineEdit, QPushButton, QMessageBox,
)
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QFont, QImage
from PyQt6.QtCore import Qt, pyqtSignal, QRectF, QSizeF, QSize, QPointF, QTimer
from PyQt6.QtMultimedia import QVideoFrame, QVideoFrameFormat
from gui.visualizador_detector import VisualizadorDetector
from core.gestor_alertas import GestorAlertas
from core.rtsp_builder import generar_rtsp
from core.analytics_processor import AnalyticsProcessor
from gui.video_saver import VideoSaverThread
from core.cross_line_counter import CrossLineCounter
from core.ptz_control import PTZCameraONVIF
from collections import defaultdict, deque
import numpy as np
from datetime import datetime
import uuid
import json
import os
import time

# NUEVA IMPORTACIÓN: Sistema de muestreo adaptativo
try:
    from core.adaptive_sampling import AdaptiveSamplingController, AdaptiveSamplingConfig
    ADAPTIVE_SAMPLING_AVAILABLE = True
except ImportError:
    ADAPTIVE_SAMPLING_AVAILABLE = False
    print("⚠️ Muestreo adaptativo no disponible - usando muestreo fijo")

DEBUG_LOGS = False  # Deshabilitado para producción

CONFIG_FILE_PATH = "config.json"

class GrillaWidget(QWidget):
    log_signal = pyqtSignal(str)

    def __init__(self, filas=18, columnas=22, area=None, parent=None, fps_config=None):
        super().__init__(parent)
        self.filas = filas
        self.columnas = columnas
        self.area = area if area else [0] * (filas * columnas)
        self.temporal = set()
        self.pixmap = None
        self.last_frame = None 
        self.original_frame_size = None 
        self.latest_tracked_boxes = []
        self.selected_cells = set()
        self.discarded_cells = set()
        self.cell_presets = {}
        self.cell_ptz_map = {}
        self.ptz_objects = {}
        self.credentials_cache = {}
        self.ptz_cameras = []

        self.cam_data = None
        self.alertas = None
        self.objetos_previos = {}
        self.umbral_movimiento = 20
        self.detectors = None 
        self.analytics_processor = AnalyticsProcessor(self)

        # Configuración de FPS personalizable
        if fps_config is None:
            fps_config = {
                "visual_fps": 25,
                "detection_fps": 8,
                "ui_update_fps": 15
            }
        
        self.fps_config = fps_config
        
        # NUEVA FUNCIONALIDAD: Sistema de muestreo adaptativo
        self.adaptive_sampling_enabled = False
        self.adaptive_controller = None
        self.fixed_detection_interval = max(1, int(30 / fps_config["detection_fps"]))  # Fallback fijo
        self.current_detection_interval = self.fixed_detection_interval
        
        # Métricas para muestreo adaptativo
        self.frame_processing_times = deque(maxlen=20)
        self.last_detection_count = 0
        self.movement_metrics = {"moving_objects": 0, "total_objects": 0, "average_speed": 0.0}
        
        # Configurar sistema adaptativo si está disponible
        self._setup_adaptive_sampling()
        
        # Calcular intervalos basados en FPS deseados
        self.PAINT_UPDATE_INTERVAL = int(1000 / fps_config["ui_update_fps"])
        self.UI_UPDATE_INTERVAL = max(1, int(30 / fps_config["visual_fps"]))

        self.cross_counter = CrossLineCounter()
        self.cross_counter.counts_updated.connect(self._update_cross_counts)
        self.cross_counter.log_signal.connect(self.registrar_log)
        self.cross_counter.cross_event.connect(self._handle_cross_event)
        self.cross_counter.start()
        self.cross_counter.active = False
        self.cross_counts = {}
        self.cross_line_enabled = False
        self.cross_line_edit_mode = False
        self._temp_line_start = None
        self._dragging_line = None
        self._last_mouse_pos = None

        self.frame_buffer = deque(maxlen=50)
        self.pending_videos = []
        self.active_video_threads = []

        self.setFixedSize(640, 480)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._grid_lines_pixmap = None
        self._generate_grid_lines_pixmap()

        self.paint_update_timer = QTimer(self)
        self.paint_update_timer.setSingleShot(True)
        self.paint_update_timer.timeout.connect(self.perform_paint_update)
        self.paint_scheduled = False

        self.ui_frame_counter = 1
        
        # Contadores para estadísticas
        self.detection_count = 0
        self.total_frames_processed = 0
        self.frames_skipped_adaptive = 0

    def _setup_adaptive_sampling(self):
        """Configura el sistema de muestreo adaptativo"""
        if not ADAPTIVE_SAMPLING_AVAILABLE:
            self.registrar_log("⚠️ Muestreo adaptativo no disponible - usando intervalo fijo")
            return
        
        try:
            # Cargar configuración del muestreo adaptativo desde config.json si existe
            adaptive_config = self._load_adaptive_config()
            
            # Crear controlador adaptativo
            self.adaptive_controller = AdaptiveSamplingController(adaptive_config)
            self.adaptive_controller.enable()  # Activar el controlador
            self.adaptive_sampling_enabled = True
            
            self.registrar_log(f"✅ Muestreo adaptativo inicializado (base: {adaptive_config.get('base_interval', 10)})")
            
        except Exception as e:
            self.registrar_log(f"❌ Error configurando muestreo adaptativo: {e}")
            self.adaptive_sampling_enabled = False

    def _load_adaptive_config(self):
        """Carga la configuración del muestreo adaptativo"""
        try:
            # Intentar cargar desde config.json
            if os.path.exists(CONFIG_FILE_PATH):
                with open(CONFIG_FILE_PATH, 'r') as f:
                    config_data = json.load(f)
                
                # Buscar configuración específica de muestreo adaptativo
                adaptive_config = config_data.get("adaptive_sampling", {})
                
                # Si no existe, usar configuración específica de la cámara actual
                if not adaptive_config and self.cam_data:
                    cam_ip = self.cam_data.get("ip")
                    for cam in config_data.get("camaras", []):
                        if cam.get("ip") == cam_ip:
                            adaptive_config = cam.get("adaptive_sampling", {})
                            break
                
                # Combinar con configuración por defecto
                default_config = AdaptiveSamplingConfig.create_config("balanced")
                # Convertir a dict para poder hacer update
                default_dict = {
                    'base_interval': default_config.base_interval,
                    'min_interval': default_config.min_interval,
                    'max_interval': default_config.max_interval,
                    'adaptation_rate': default_config.adaptation_rate,
                    'detection_weight': default_config.detection_weight,
                    'movement_weight': default_config.movement_weight,
                    'high_activity_threshold': default_config.high_activity_threshold,
                    'low_activity_threshold': default_config.low_activity_threshold,
                    'history_window': default_config.history_window,
                    'stabilization_time': default_config.stabilization_time,
                    'min_detections_for_adaptation': default_config.min_detections_for_adaptation,
                    'confidence_threshold': default_config.confidence_threshold,
                    'enable_burst_mode': default_config.enable_burst_mode,
                    'burst_duration': default_config.burst_duration,
                    'enable_smoothing': default_config.enable_smoothing
                }
                default_dict.update(adaptive_config)
                
                return AdaptiveSamplingConfig(**default_dict)
            
        except Exception as e:
            self.registrar_log(f"⚠️ Error cargando config adaptativo: {e}")
        
        # Fallback: configuración por defecto
        return AdaptiveSamplingConfig.create_config("balanced")

    def set_fps_config(self, visual_fps=25, detection_fps=8, ui_update_fps=15):
        """Actualizar configuración de FPS en tiempo real"""
        self.fps_config = {
            "visual_fps": visual_fps,
            "detection_fps": detection_fps, 
            "ui_update_fps": ui_update_fps
        }
        
        # Actualizar intervalos fijos (fallback)
        self.fixed_detection_interval = max(1, int(30 / detection_fps))
        self.PAINT_UPDATE_INTERVAL = int(1000 / ui_update_fps)
        self.UI_UPDATE_INTERVAL = max(1, int(30 / visual_fps))
        
        # Actualizar configuración del sistema adaptativo si está disponible
        if self.adaptive_sampling_enabled and self.adaptive_controller:
            # Actualizar el intervalo base del sistema adaptativo
            new_base_interval = max(1, int(30 / detection_fps))
            adaptive_config_update = AdaptiveSamplingConfig(
                base_interval=new_base_interval,
                min_interval=max(1, new_base_interval // 3),
                max_interval=min(50, new_base_interval * 3),
                adaptation_rate=0.15,
                detection_weight=0.7,
                movement_weight=0.3,
                high_activity_threshold=0.15,
                low_activity_threshold=0.05,
                history_window=30,
                stabilization_time=50,
                min_detections_for_adaptation=2,
                confidence_threshold=0.3,
                enable_burst_mode=True,
                burst_duration=10,
                enable_smoothing=True
            )
            self.adaptive_controller.update_config(adaptive_config_update)
            self.registrar_log(f"🧠 Muestreo adaptativo actualizado - Base: {new_base_interval}")
        
        if hasattr(self, 'visualizador') and self.visualizador:
            self.visualizador.update_fps_config(visual_fps, detection_fps)
        
        self.registrar_log(f"🎯 FPS actualizado - Visual: {visual_fps}, Detección: {detection_fps}, UI: {ui_update_fps}")

    def configure_adaptive_sampling(self, config):
        """Configura el sistema de muestreo adaptativo con nueva configuración"""
        if not ADAPTIVE_SAMPLING_AVAILABLE:
            self.registrar_log("⚠️ Muestreo adaptativo no disponible")
            return False
        
        try:
            if isinstance(config, dict):
                config = AdaptiveSamplingConfig(**config)
            
            if self.adaptive_controller:
                self.adaptive_controller.update_config(config)
            else:
                self.adaptive_controller = AdaptiveSamplingController(config)
                self.adaptive_controller.enable()
                self.adaptive_sampling_enabled = True
            
            self.registrar_log(f"✅ Configuración de muestreo adaptativo actualizada")
            self.registrar_log(f"   📊 Base: {config.base_interval}, Min: {config.min_interval}, Max: {config.max_interval}")
            return True
            
        except Exception as e:
            self.registrar_log(f"❌ Error configurando muestreo adaptativo: {e}")
            return False

    def toggle_adaptive_sampling(self, enabled):
        """Activa/desactiva el muestreo adaptativo"""
        if not ADAPTIVE_SAMPLING_AVAILABLE:
            self.registrar_log("⚠️ Muestreo adaptativo no disponible")
            return
        
        self.adaptive_sampling_enabled = enabled
        
        if enabled:
            if not self.adaptive_controller:
                self._setup_adaptive_sampling()
            else:
                self.adaptive_controller.enable()
            self.registrar_log("🧠 Muestreo adaptativo ACTIVADO")
        else:
            if self.adaptive_controller:
                self.adaptive_controller.disable()
            self.registrar_log(f"📊 Muestreo adaptativo DESACTIVADO - usando intervalo fijo: {self.fixed_detection_interval}")

    def get_adaptive_sampling_status(self):
        """Retorna el estado del sistema de muestreo adaptativo"""
        if not self.adaptive_sampling_enabled or not self.adaptive_controller:
            return {
                "enabled": False,
                "current_interval": self.fixed_detection_interval,
                "mode": "fixed",
                "activity_score": 0.0,
                "avg_detections": 0.0,
                "frames_processed": self.total_frames_processed,
                "frames_skipped": self.frames_skipped_adaptive
            }
        
        status = self.adaptive_controller.get_status()
        status.update({
            "enabled": True,
            "mode": "adaptive",
            "frames_processed": self.total_frames_processed,
            "frames_skipped": self.frames_skipped_adaptive
        })
        return status

    def should_analyze_frame_adaptive(self, frame_number, detections=None):
        """Determina si un frame debe ser analizado usando muestreo adaptativo o fijo"""
        self.total_frames_processed += 1
        
        if self.adaptive_sampling_enabled and self.adaptive_controller:
            # Usar sistema adaptativo
            if detections:
                # Convertir detecciones al formato esperado
                formatted_detections = []
                for detection in detections:
                    if isinstance(detection, dict):
                        formatted_detections.append({
                            'conf': detection.get('conf', 0),
                            'cls': detection.get('cls', 0),
                            'bbox': detection.get('bbox', (0, 0, 0, 0))
                        })
                
                # Determinar si hay movimiento
                has_movement = any(det.get('moving', False) for det in detections if isinstance(det, dict))
                should_analyze = self.adaptive_controller.should_process_frame(formatted_detections, has_movement)
            else:
                # Sin detecciones específicas, usar comportamiento por defecto
                should_analyze = self.adaptive_controller.should_process_frame()
            
            if not should_analyze:
                self.frames_skipped_adaptive += 1
            
            # Actualizar intervalo actual para estadísticas
            self.current_detection_interval = self.adaptive_controller.get_current_interval()
            
            return should_analyze
        else:
            # Usar sistema fijo tradicional
            should_analyze = (frame_number % self.fixed_detection_interval) == 0
            if not should_analyze:
                self.frames_skipped_adaptive += 1
            
            self.current_detection_interval = self.fixed_detection_interval
            return should_analyze

    def update_adaptive_metrics(self, detections, processing_time=None):
        """Actualiza las métricas para el sistema de muestreo adaptativo"""
        if not self.adaptive_sampling_enabled or not self.adaptive_controller:
            return
        
        # Calcular métricas de movimiento
        moving_objects = 0
        total_objects = len(detections) if detections else 0
        total_speed = 0.0
        
        for detection in detections:
            if isinstance(detection, dict):
                moving = detection.get('moving', None)
                if moving is True:
                    moving_objects += 1
                
                # Calcular velocidad aproximada si tenemos centros
                centers = detection.get('centers', [])
                if len(centers) > 1:
                    # Velocidad basada en últimos dos puntos
                    last_center = centers[-1]
                    prev_center = centers[-2]
                    speed = ((last_center[0] - prev_center[0])**2 + (last_center[1] - prev_center[1])**2)**0.5
                    total_speed += speed
        
        # Actualizar métricas de movimiento
        self.movement_metrics = {
            'moving_objects': moving_objects,
            'total_objects': total_objects,
            'average_speed': total_speed / total_objects if total_objects > 0 else 0.0
        }
        
        # Registrar tiempo de procesamiento
        if processing_time:
            self.frame_processing_times.append(processing_time)
        
        # CORRECCIÓN: El AdaptiveSamplingController actualiza sus métricas automáticamente
        # cuando se llama a should_process_frame(). No necesitamos llamar a un método separado.
        
        # Log de debug ocasional
        if DEBUG_LOGS and self.total_frames_processed % 100 == 0:
            status = self.adaptive_controller.get_status()
            self.registrar_log(f"📊 Adaptativo - Intervalo: {status['current_interval']}, "
                              f"Actividad: {status['activity_score']:.2f}, "
                              f"Detecciones: {total_objects}")

    def enable_cross_line(self):
        self.cross_line_enabled = True
        self.cross_counter.active = True
        self.cross_counts.clear()
        self.cross_counter.prev_sides.clear()
        self.cross_counter.counts = {"Entrada": defaultdict(int), "Salida": defaultdict(int)}
        self.request_paint_update()

    def disable_cross_line(self):
        self.cross_line_enabled = False
        self.cross_counter.active = False
        self.cross_counts.clear()
        self.cross_counter.prev_sides.clear()
        self.cross_counter.counts = {"Entrada": defaultdict(int), "Salida": defaultdict(int)}
        self.request_paint_update()

    def start_line_edit(self):
        self.enable_cross_line()
        self.cross_line_edit_mode = True
        self._temp_line_start = None
        self._dragging_line = None
        self._last_mouse_pos = None

    def finish_line_edit(self):
        self.cross_line_edit_mode = False
        self._temp_line_start = None
        self._dragging_line = None
        self._last_mouse_pos = None

    def _update_cross_counts(self, counts):
        self.cross_counts = counts
        self.request_paint_update()

    def _handle_cross_event(self, info):
        if self.last_frame is None:
            return
        now = datetime.now()
        fecha = now.strftime("%Y-%m-%d")
        hora = now.strftime("%H-%M-%S")
        ruta = os.path.join("capturas", "videos", fecha)
        os.makedirs(ruta, exist_ok=True)
        nombre = f"{fecha}_{hora}_{uuid.uuid4().hex[:6]}.mp4"
        path_final = os.path.join(ruta, nombre)
        frames_copy = list(self.frame_buffer)
        self.pending_videos.append({
            "frames": frames_copy,
            "frames_left": 50,
            "path": path_final,
        })
        self.registrar_log(f"🎥 Grabación iniciada: {nombre}")

    def perform_paint_update(self):
        self.paint_scheduled = False
        self.update()

    def request_paint_update(self):
        if not self.paint_scheduled:
            self.paint_scheduled = True
            self.paint_update_timer.start(self.PAINT_UPDATE_INTERVAL)

    def _point_to_segment_distance(self, p, a, b):
        ax, ay = a.x(), a.y()
        bx, by = b.x(), b.y()
        px, py = p.x(), p.y()
        dx = bx - ax
        dy = by - ay
        if dx == 0 and dy == 0:
            return (p - a).manhattanLength()
        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        t = max(0, min(1, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._generate_grid_lines_pixmap()

    def _generate_grid_lines_pixmap(self):
        if self.width() <= 0 or self.height() <= 0:
            self._grid_lines_pixmap = None
            return
        pixmap = QPixmap(self.size())
        pixmap.fill(Qt.GlobalColor.transparent)
        qp = QPainter(pixmap)
        qp.setPen(QColor(100, 100, 100, 100))
        cell_w = self.width() / self.columnas
        cell_h = self.height() / self.filas
        for row in range(self.filas + 1):
            y = row * cell_h
            qp.drawLine(0, int(y), self.width(), int(y))
        for col in range(self.columnas + 1):
            x = col * cell_w
            qp.drawLine(int(x), 0, int(x), self.height())
        qp.end()
        self._grid_lines_pixmap = pixmap

    def mostrar_vista(self, cam_data):
        if hasattr(self, 'visualizador') and self.visualizador: 
            self.visualizador.detener()

        if "rtsp" not in cam_data:
            cam_data["rtsp"] = generar_rtsp(cam_data)

        if "fps_config" not in cam_data:
            cam_data["fps_config"] = self.fps_config

        self.cam_data = cam_data
        self.discarded_cells = set()
        self.cell_presets = {}

        # MEJORA: Cargar configuración y recargar cámaras PTZ
        current_cam_ip = self.cam_data.get("ip")
        if current_cam_ip:
            try:
                with open(CONFIG_FILE_PATH, 'r') as f:
                    config_data = json.load(f)
                
                camaras_config = config_data.get("camaras", [])
                
                # IMPORTANTE: Limpiar y recargar listas PTZ
                self.ptz_cameras.clear()
                self.credentials_cache.clear()
                
                # Procesar todas las cámaras para identificar PTZ y cachear credenciales
                for cam_config in camaras_config:
                    ip_cfg = cam_config.get("ip")
                    tipo_cfg = cam_config.get("tipo")
                    
                    if ip_cfg:
                        # Cachear credenciales para TODAS las cámaras (PTZ y fijas)
                        self.credentials_cache[ip_cfg] = {
                            "usuario": cam_config.get("usuario"),
                            "contrasena": cam_config.get("contrasena"),
                            "puerto": cam_config.get("puerto", 80),
                            "tipo": tipo_cfg
                        }
                        
                        # Identificar cámaras PTZ específicamente
                        if tipo_cfg == "ptz":
                            if ip_cfg not in self.ptz_cameras:
                                self.ptz_cameras.append(ip_cfg)
                                self.registrar_log(f"📷 Cámara PTZ detectada: {ip_cfg}")

                    # Cargar configuración específica de la cámara actual
                    if ip_cfg == current_cam_ip:
                        discarded_list = cam_config.get("discarded_grid_cells")
                        if isinstance(discarded_list, list):
                            for cell_coords in discarded_list:
                                if isinstance(cell_coords, list) and len(cell_coords) == 2:
                                    self.discarded_cells.add(tuple(cell_coords))
                            self.registrar_log(f"Cargadas {len(self.discarded_cells)} celdas descartadas")

                        presets = cam_config.get("cell_presets", {})
                        if isinstance(presets, dict):
                            for key, val in presets.items():
                                try:
                                    row, col = map(int, key.split('_'))
                                    self.cell_presets[(row, col)] = str(val)
                                except Exception:
                                    continue
                            if presets:
                                self.registrar_log(f"Cargados {len(self.cell_presets)} presets de celdas")

                        ptz_map = cam_config.get("cell_ptz_map", {})
                        if isinstance(ptz_map, dict):
                            for key, val in ptz_map.items():
                                try:
                                    row, col = map(int, key.split('_'))
                                    if isinstance(val, dict):
                                        self.cell_ptz_map[(row, col)] = {
                                            "ip": val.get("ip"),
                                            "preset": str(val.get("preset", "")),
                                        }
                                except Exception:
                                    continue
                            if ptz_map:
                                self.registrar_log(f"Cargados {len(self.cell_ptz_map)} mapeos PTZ")
                        
                        # NUEVA FUNCIONALIDAD: Cargar configuración de muestreo adaptativo específica
                        adaptive_config = cam_config.get("adaptive_sampling")
                        if adaptive_config and ADAPTIVE_SAMPLING_AVAILABLE:
                            self.configure_adaptive_sampling(adaptive_config)
                            self.registrar_log(f"🧠 Configuración adaptativa específica cargada para {current_cam_ip}")
                        
                        break
                        
                # Log del resultado de carga
                self.registrar_log(f"🔄 Sistema inicializado:")
                self.registrar_log(f"   📷 Cámaras PTZ disponibles: {len(self.ptz_cameras)}")
                self.registrar_log(f"   🔑 Credenciales cacheadas: {len(self.credentials_cache)}")
                if self.adaptive_sampling_enabled:
                    self.registrar_log(f"   🧠 Muestreo adaptativo: ACTIVO")
                else:
                    self.registrar_log(f"   📊 Muestreo fijo: {self.fixed_detection_interval} frames")
                
            except Exception as e:
                self.registrar_log(f"Error cargando configuración: {e}")
        
        # MODIFICACIÓN: Inicializar GestorAlertas optimizado
        self.alertas = GestorAlertas(cam_id=str(uuid.uuid4())[:8], filas=self.filas, columnas=self.columnas)
        
        # Configurar el sistema optimizado de capturas
        if hasattr(self.alertas, 'configurar_capturas'):
            self.alertas.configurar_capturas(
                confidence_threshold=0.50,  # Umbral recomendado
                min_time_between=30,        # 30 segundos entre capturas del mismo track
                max_capturas=3              # Máximo 3 capturas por minuto
            )
            self.registrar_log(f"🎯 Sistema optimizado configurado: Confianza ≥ 0.50, Intervalo: 30s")

        self.visualizador = VisualizadorDetector(cam_data)
        if self.visualizador:
            self.detector = getattr(self.visualizador, "detectors", [])

        self.visualizador.result_ready.connect(self.actualizar_boxes)
        self.visualizador.log_signal.connect(self.registrar_log)
        self.visualizador.iniciar()
        
        if self.visualizador and self.visualizador.video_sink:
            self.visualizador.video_sink.videoFrameChanged.connect(self.actualizar_pixmap_y_frame)

        self.registrar_log(f"🎥 Vista configurada para {current_cam_ip}")

        # =================================================================
        # NUEVA INTEGRACIÓN PTZ: Registrar cámara con sistema PTZ
        # =================================================================
        try:
            # Intentar registrar esta cámara con el sistema PTZ
            self.register_with_ptz_system()
        except Exception as e:
            self.registrar_log(f"⚠️ No se pudo registrar con sistema PTZ: {e}")

        # Información adicional para debugging
        if DEBUG_LOGS:
            self.registrar_log("🔧 DEBUG - Configuración cámara:")
            self.registrar_log(f"   📷 IP: {current_cam_ip}")
            self.registrar_log(f"   🎯 Tipo: {cam_data.get('tipo', 'fija')}")
            self.registrar_log(
                f"   🧠 Muestreo adaptativo: {'ACTIVO' if self.adaptive_sampling_enabled else 'FIJO'}"
            )
            self.registrar_log(f"   🎮 PTZ disponible: {len(self.ptz_cameras)} cámaras")

    def actualizar_boxes(self, boxes):
        """Método principal que recibe las detecciones del visualizador - MEJORADO CON MUESTREO ADAPTATIVO"""
        start_time = time.time()
        self.detection_count += 1
        
        # Solo mostrar log cada 100 detecciones para evitar spam
        if DEBUG_LOGS and self.detection_count % 100 == 0:
            self.registrar_log(f"📊 Detecciones procesadas: {self.detection_count}")
        
        self.latest_tracked_boxes = boxes
        
        if self.cross_line_enabled and self.original_frame_size:
            size = (
                self.original_frame_size.width(),
                self.original_frame_size.height(),
            )
            self.cross_counter.update_boxes(boxes, size)
        
        # MODIFICACIÓN: Procesar detecciones con información completa de tracking
        nuevas_detecciones_para_alertas = []
        for box_data in boxes:
            if not isinstance(box_data, dict):
                continue

            x1, y1, x2, y2 = box_data.get('bbox', (0, 0, 0, 0))
            tracker_id = box_data.get('id')
            cls = box_data.get('cls')
            conf = box_data.get('conf', 0)
            
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            current_cls_positions = self.objetos_previos.get(cls, [])
            se_ha_movido = all(
                abs(cx - prev_cx) > self.umbral_movimiento or abs(cy - prev_cy) > self.umbral_movimiento
                for prev_cx, prev_cy in current_cls_positions
            )

            if se_ha_movido:
                # NUEVA ESTRUCTURA: Incluir track_id y confianza para el sistema optimizado
                nuevas_detecciones_para_alertas.append((x1, y1, x2, y2, cls, cx, cy, tracker_id, conf)) 
                current_cls_positions.append((cx, cy))
                
                # Log de debug para verificar formato
                if DEBUG_LOGS:
                    self.registrar_log(f"🔧 Detección preparada: Track={tracker_id}, cls={cls}, conf={conf:.2f}, coords=({cx},{cy})")
                
                # Determinar nombre de clase
                modelos_cam = []
                if self.cam_data:
                    modelos_cam = self.cam_data.get("modelos") or [self.cam_data.get("modelo")]
                
                if "Embarcaciones" in modelos_cam and cls == 1:
                    clase_nombre = "Embarcación"
                elif cls == 0 and "Embarcaciones" not in modelos_cam:
                    clase_nombre = "Persona"
                elif cls == 2:
                    clase_nombre = "Auto"
                elif cls == 8 or cls == 9:
                    clase_nombre = "Barco"
                else:
                    clase_nombre = f"Clase {cls}"
                
                conf_val = conf if isinstance(conf, (int, float)) else 0.0
                
                # Solo log para movimientos con confianza alta (reduce spam significativamente)
                if conf_val >= 0.70:  # Solo mostrar detecciones de alta calidad
                    self.registrar_log(f"🟢 {clase_nombre} detectada (ID: {tracker_id}, Conf: {conf_val:.2f})")
                    
            self.objetos_previos[cls] = current_cls_positions[-10:]

        # Log de debug del total de detecciones preparadas
        if nuevas_detecciones_para_alertas:
            self.registrar_log(f"📋 Total detecciones preparadas para alertas: {len(nuevas_detecciones_para_alertas)}")
        elif DEBUG_LOGS:
            self.registrar_log(f"📋 No hay detecciones con movimiento para procesar")

        # MODIFICACIÓN: Filtrado de celdas mejorado con manejo de formato optimizado
        if self.alertas and self.last_frame is not None:
            detecciones_filtradas = []
            if self.original_frame_size and self.original_frame_size.width() > 0 and self.original_frame_size.height() > 0:
                cell_w_video = self.original_frame_size.width() / self.columnas
                cell_h_video = self.original_frame_size.height() / self.filas

                if cell_w_video > 0 and cell_h_video > 0:
                    for detection_data in nuevas_detecciones_para_alertas:
                        # Extraer coordenadas del nuevo formato (x1, y1, x2, y2, cls, cx, cy, track_id, conf)
                        x1_orig, y1_orig, x2_orig, y2_orig = detection_data[:4]
                        
                        cx_orig = (x1_orig + x2_orig) / 2
                        cy_orig = (y1_orig + y2_orig) / 2

                        if not (0 <= cx_orig < self.original_frame_size.width() and \
                                0 <= cy_orig < self.original_frame_size.height()):
                            detecciones_filtradas.append(detection_data)
                            continue

                        col_video = int(cx_orig / cell_w_video)
                        row_video = int(cy_orig / cell_h_video)
                        
                        col_video = max(0, min(col_video, self.columnas - 1))
                        row_video = max(0, min(row_video, self.filas - 1))

                        if (row_video, col_video) not in self.discarded_cells:
                            detecciones_filtradas.append(detection_data)
                            cell_key = (row_video, col_video)
                            if cell_key in self.cell_ptz_map:
                                mapping = self.cell_ptz_map[cell_key]
                                ip_tgt = mapping.get("ip")
                                preset_tgt = mapping.get("preset")
                                if ip_tgt and preset_tgt is not None:
                                    self._trigger_ptz_move(ip_tgt, preset_tgt)
                        elif DEBUG_LOGS:
                            track_id = detection_data[7] if len(detection_data) > 7 else 'N/A'
                            self.registrar_log(f"🔶 Track {track_id} ignorado - celda descartada ({row_video}, {col_video})")
                else: 
                    detecciones_filtradas = list(nuevas_detecciones_para_alertas) 
            else: 
                detecciones_filtradas = list(nuevas_detecciones_para_alertas)

            # Limpiar periódicamente el historial de tracks inactivos
            if hasattr(self.alertas, 'limpiar_historial_tracks'):
                tracks_activos = {box_data.get('id') for box_data in boxes if box_data.get('id') is not None}
                self.alertas.limpiar_historial_tracks(tracks_activos)

            # Procesar con el sistema optimizado
            self.alertas.procesar_detecciones(
                detecciones_filtradas, 
                self.last_frame,
                self.registrar_log,
                self.cam_data
            )
            self.temporal = self.alertas.temporal
        
        # NUEVA FUNCIONALIDAD: Actualizar métricas del sistema adaptativo
        processing_time = time.time() - start_time
        self.update_adaptive_metrics(boxes, processing_time)

        # =================================================================
        # NUEVA INTEGRACIÓN PTZ: Enviar detecciones al sistema PTZ si está activo
        # =================================================================
        try:
            # Verificar si hay un sistema PTZ disponible en la ventana principal
            main_window = self._get_main_window()
            if main_window and hasattr(main_window, 'send_detections_to_ptz'):
                camera_id = self.cam_data.get('ip', 'unknown') if self.cam_data else 'unknown'

                # Convertir detecciones al formato esperado por el PTZ
                ptz_detections = self._convert_boxes_for_ptz(boxes)

                if ptz_detections:
                    # Intentar enviar al sistema PTZ
                    success = main_window.send_detections_to_ptz(camera_id, ptz_detections)

                    # Log de debug solo para primera detección exitosa o errores
                    if success and self.detection_count <= 5:
                        self.registrar_log(f"🎯 Detecciones enviadas al sistema PTZ para {camera_id}")
                    elif not success and DEBUG_LOGS:
                        self.registrar_log(f"⚠️ No se pudieron enviar detecciones al PTZ para {camera_id}")

        except Exception as e:
            # Solo log de errores críticos para evitar spam
            if DEBUG_LOGS:
                self.registrar_log(f"❌ Error integrando con PTZ: {e}")

        self.request_paint_update()

    def actualizar_pixmap_y_frame(self, frame):
        if not frame.isValid():
            return

        self.ui_frame_counter += 1

        # NUEVA LÓGICA: Usar muestreo adaptativo para determinar si procesar este frame
        should_process_ui = (self.ui_frame_counter % self.UI_UPDATE_INTERVAL) == 0
        should_analyze_detection = self.should_analyze_frame_adaptive(self.ui_frame_counter, None)

        # Solo procesar UI si corresponde
        if not should_process_ui:
            return

        image = None
        numpy_frame = None
        img_converted = None

        if frame.map(QVideoFrame.MapMode.ReadOnly):
            try:
                pf = frame.pixelFormat()
                rgb_formats = set()
                for name in [
                    "Format_RGB24", "Format_RGB32", "Format_BGR24", "Format_BGR32",
                    "Format_RGBX8888", "Format_RGBA8888", "Format_BGRX8888", 
                    "Format_BGRA8888", "Format_ARGB32",
                ]:
                    fmt = getattr(QVideoFrameFormat.PixelFormat, name, None)
                    if fmt is not None:
                        rgb_formats.add(fmt)

                if pf in rgb_formats:
                    img_format = QVideoFrameFormat.imageFormatFromPixelFormat(pf)
                    if img_format != QImage.Format.Format_Invalid:
                        qimg = QImage(
                            frame.bits(),
                            frame.width(),
                            frame.height(),
                            frame.bytesPerLine(),
                            img_format,
                        ).copy()
                        image = qimg
                        img_converted = qimg.convertToFormat(QImage.Format.Format_RGB888)
                        ptr = img_converted.constBits()
                        ptr.setsize(img_converted.width() * img_converted.height() * 3)
                        numpy_frame = (
                            np.frombuffer(ptr, dtype=np.uint8)
                            .reshape((img_converted.height(), img_converted.width(), 3))
                            .copy()
                        )
            finally:
                frame.unmap()

        if image is None:
            image = frame.toImage()
            if image.isNull():
                return
            img_converted = image.convertToFormat(QImage.Format.Format_RGB888)
            ptr = img_converted.constBits()
            ptr.setsize(img_converted.width() * img_converted.height() * 3)
            numpy_frame = (
                np.frombuffer(ptr, dtype=np.uint8)
                .reshape((img_converted.height(), img_converted.width(), 3))
                .copy()
            )

        current_frame_width = img_converted.width()
        current_frame_height = img_converted.height()
        if (
            self.original_frame_size is None
            or self.original_frame_size.width() != current_frame_width
            or self.original_frame_size.height() != current_frame_height
        ):
            self.original_frame_size = QSize(current_frame_width, current_frame_height)

        self.last_frame = numpy_frame
        self.frame_buffer.append(numpy_frame)
        
        # Procesar videos pendientes
        for rec in list(self.pending_videos):
            if rec["frames_left"] > 0:
                rec["frames"].append(numpy_frame)
                rec["frames_left"] -= 1
            if rec["frames_left"] <= 0:
                thread = VideoSaverThread(rec["frames"], rec["path"], fps=10)
                thread.finished.connect(lambda r=thread: self._remove_video_thread(r))
                self.active_video_threads.append(thread)
                thread.start()
                self.pending_videos.remove(rec)
                self.registrar_log(f"🎥 Video guardado: {os.path.basename(rec['path'])}")

        self.pixmap = QPixmap.fromImage(img_converted)
        self.request_paint_update()

    def registrar_log(self, mensaje):
        fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ip = self.cam_data.get("ip", "IP-desconocida") if self.cam_data else "IP-indefinida"
        mensaje_completo = f"[{fecha_hora}] Cámara {ip}: {mensaje}"
        self.log_signal.emit(mensaje_completo)
        with open("eventos_detectados.txt", "a", encoding="utf-8") as f:
            f.write(mensaje_completo + "\n")

    def _remove_video_thread(self, thread):
        if thread in self.active_video_threads:
            self.active_video_threads.remove(thread)

    def detener(self):
        # Log de estadísticas finales del muestreo adaptativo
        if self.adaptive_sampling_enabled:
            status = self.get_adaptive_sampling_status()
            self.registrar_log(f"📊 Estadísticas finales de muestreo adaptativo:")
            self.registrar_log(f"   🎯 Frames procesados: {status['frames_processed']}")
            self.registrar_log(f"   ⏭️ Frames saltados: {status['frames_skipped']}")
            efficiency = (status['frames_skipped'] / status['frames_processed']) * 100 if status['frames_processed'] > 0 else 0
            self.registrar_log(f"   📈 Eficiencia: {efficiency:.1f}% frames omitidos")
            self.registrar_log(f"   📊 Último intervalo: {status['current_interval']}")
            
        if hasattr(self, 'visualizador') and self.visualizador: 
            self.visualizador.detener()
        
        if hasattr(self, 'analytics_processor') and self.analytics_processor:
            self.analytics_processor.stop_processing()

        if hasattr(self, 'visualizador') and self.visualizador:
            self.visualizador = None
        if self.detector:
             self.detector = None
        self.paint_update_timer.stop()
        if hasattr(self, 'cross_counter') and self.cross_counter:
            self.cross_counter.stop()
        for th in list(self.active_video_threads):
            if th.isRunning():
                th.wait(1000)

    def mousePressEvent(self, event):
        if self.cross_line_edit_mode:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = event.position()
                x_rel = pos.x() / self.width()
                y_rel = pos.y() / self.height()
                x1_rel, y1_rel = self.cross_counter.line[0]
                x2_rel, y2_rel = self.cross_counter.line[1]
                p1 = QPointF(x1_rel * self.width(), y1_rel * self.height())
                p2 = QPointF(x2_rel * self.width(), y2_rel * self.height())
                thresh = 10.0
                if (pos - p1).manhattanLength() <= thresh:
                    self._dragging_line = 'p1'
                elif (pos - p2).manhattanLength() <= thresh:
                    self._dragging_line = 'p2'
                elif self._point_to_segment_distance(pos, p1, p2) <= thresh:
                    self._dragging_line = 'line'
                    self._last_mouse_pos = pos
                else:
                    self._dragging_line = 'new'
                    self._temp_line_start = pos
                    self.cross_counter.set_line(((x_rel, y_rel), (x_rel, y_rel)))
                self.request_paint_update()
            elif event.button() == Qt.MouseButton.RightButton:
                self.finish_line_edit()
            return
        
        pos = event.position()
        cell_w = self.width() / self.columnas
        cell_h = self.height() / self.filas

        if cell_w == 0 or cell_h == 0:
            return

        col = int(pos.x() / cell_w)
        row = int(pos.y() / cell_h)

        if not (0 <= row < self.filas and 0 <= col < self.columnas):
            return

        clicked_cell = (row, col)

        if event.button() == Qt.MouseButton.LeftButton:
            if clicked_cell in self.selected_cells:
                self.selected_cells.remove(clicked_cell)
            else:
                self.selected_cells.add(clicked_cell)
            self.request_paint_update()
        elif event.button() == Qt.MouseButton.RightButton:
            menu = QMenu(self)
            if self.selected_cells:
                discard_action = menu.addAction("Descartar celdas para analíticas")
                discard_action.triggered.connect(self.handle_discard_cells)

                enable_action = menu.addAction("Habilitar celdas para analíticas")
                enable_action.triggered.connect(self.handle_enable_discarded_cells)

                set_preset_action = menu.addAction("Asignar preset…")
                set_preset_action.triggered.connect(self.handle_set_preset)

                clear_preset_action = menu.addAction("Quitar preset")
                clear_preset_action.triggered.connect(self.handle_clear_preset)

                set_ptz_action = menu.addAction("Asignar PTZ remoto…")
                set_ptz_action.triggered.connect(self.handle_set_ptz_map)

                clear_ptz_action = menu.addAction("Quitar PTZ remoto")
                clear_ptz_action.triggered.connect(self.handle_clear_ptz_map)

            if self.cross_line_enabled:
                disable_line = menu.addAction("Desactivar línea de conteo")
                disable_line.triggered.connect(self.disable_cross_line)
            else:
                enable_line = menu.addAction("Activar línea de conteo")
                enable_line.triggered.connect(self.start_line_edit)

            # NUEVA FUNCIONALIDAD: Menú de muestreo adaptativo
            if ADAPTIVE_SAMPLING_AVAILABLE:
                menu.addSeparator()
                adaptive_menu = menu.addMenu("🧠 Muestreo Adaptativo")
                
                if self.adaptive_sampling_enabled:
                    disable_adaptive_action = adaptive_menu.addAction("📊 Desactivar (usar fijo)")
                    disable_adaptive_action.triggered.connect(lambda: self.toggle_adaptive_sampling(False))
                    
                    status_action = adaptive_menu.addAction("📈 Ver Estado")
                    status_action.triggered.connect(self.show_adaptive_status)
                else:
                    enable_adaptive_action = adaptive_menu.addAction("🧠 Activar Adaptativo")
                    enable_adaptive_action.triggered.connect(lambda: self.toggle_adaptive_sampling(True))
                
                config_action = adaptive_menu.addAction("⚙️ Configurar...")
                config_action.triggered.connect(self.open_adaptive_config)

            menu.exec(event.globalPosition().toPoint())

    def show_adaptive_status(self):
        """Muestra el estado del muestreo adaptativo"""
        if not self.adaptive_sampling_enabled:
            QMessageBox.information(self, "Muestreo Adaptativo", 
                                   "El muestreo adaptativo está desactivado.\n"
                                   f"Usando intervalo fijo: {self.fixed_detection_interval}")
            return
        
        status = self.get_adaptive_sampling_status()
        
        message = f"""🧠 Estado del Muestreo Adaptativo

📊 Configuración Actual:
• Intervalo actual: {status['current_interval']} frames
• Puntuación de actividad: {status.get('activity_score', 0):.2f}
• Promedio de detecciones: {status.get('avg_detections', 0):.1f}

📈 Estadísticas:
• Frames procesados: {status['frames_processed']}
• Frames saltados: {status['frames_skipped']}"""

        if status['frames_processed'] > 0:
            efficiency = (status['frames_skipped'] / status['frames_processed']) * 100
            message += f"\n• Eficiencia: {efficiency:.1f}% frames omitidos"
        
        QMessageBox.information(self, "Estado del Muestreo Adaptativo", message)

    def open_adaptive_config(self):
        """Abre el diálogo de configuración del muestreo adaptativo"""
        if not ADAPTIVE_SAMPLING_AVAILABLE:
            QMessageBox.warning(self, "No disponible", 
                               "El sistema de muestreo adaptativo no está disponible.\n"
                               "Asegúrese de que el módulo core/adaptive_sampling.py esté instalado.")
            return
        
        try:
            from ui.adaptive_sampling_dialog import AdaptiveSamplingConfigDialog
            
            # Obtener configuración actual
            current_config = None
            if self.adaptive_controller:
                current_config = self.adaptive_controller.export_config()
            
            dialog = AdaptiveSamplingConfigDialog(self, current_config)
            dialog.config_changed.connect(self.configure_adaptive_sampling)
            
            if dialog.exec():
                new_config = dialog.get_config()
                self.configure_adaptive_sampling(new_config)
                self.registrar_log("✅ Configuración de muestreo adaptativo actualizada")
                
        except ImportError:
            QMessageBox.warning(self, "Módulo no disponible",
                               "El diálogo de configuración no está disponible.\n"
                               "Archivo requerido: ui/adaptive_sampling_dialog.py")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error abriendo configuración: {e}")

    def handle_discard_cells(self):
        if not self.selected_cells:
            return

        self.discarded_cells.update(self.selected_cells)
        self._save_discarded_cells_to_config() 
        self.selected_cells.clear()
        self.request_paint_update()

    def handle_enable_discarded_cells(self):
        if not self.selected_cells:
            return

        cells_to_enable = self.selected_cells.intersection(self.discarded_cells)
        if not cells_to_enable:
            self.selected_cells.clear()
            self.request_paint_update()
            return

        for cell in cells_to_enable:
            self.discarded_cells.remove(cell)
        
        self.registrar_log(f"Celdas habilitadas: {len(cells_to_enable)}")
        self._save_discarded_cells_to_config()
        self.selected_cells.clear()
        self.request_paint_update()

    def handle_set_preset(self):
        if not self.selected_cells:
            return

        from PyQt6.QtWidgets import QInputDialog
        preset, ok = QInputDialog.getText(self, "Asignar preset", "Número de preset:")
        if not ok or not preset:
            return

        for cell in self.selected_cells:
            self.cell_presets[cell] = str(preset)

        self._save_cell_presets_to_config()
        self.request_paint_update()

    def handle_clear_preset(self):
        if not self.selected_cells:
            return

        for cell in list(self.selected_cells):
            if cell in self.cell_presets:
                del self.cell_presets[cell]

        self._save_cell_presets_to_config()
        self.request_paint_update()

    def handle_set_ptz_map(self):
        """Asignar PTZ a celda - MEJORADO"""
        if not self.selected_cells:
            self.registrar_log("⚠️ No hay celdas seleccionadas para asignar PTZ")
            return

        # MEJORA: Recargar cámaras PTZ disponibles dinámicamente
        self._reload_ptz_cameras()
        
        if not self.ptz_cameras:
            QMessageBox.warning(
                self, 
                "No hay cámaras PTZ", 
                "No se encontraron cámaras PTZ configuradas en el sistema.\n\n"
                "Para asignar PTZ remoto:\n"
                "1. Asegúrate de tener cámaras con tipo 'ptz' configuradas\n"
                "2. Ve a Inicio > Agregar Cámara y agrega una cámara PTZ\n"
                "3. Reinicia la aplicación o vuelve a cargar la configuración"
            )
            self.registrar_log("❌ No hay cámaras PTZ disponibles para asignar")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("📍 Asignar PTZ Remoto")
        dialog.setMinimumSize(400, 280)

        layout = QVBoxLayout(dialog)
        
        # Información de las celdas seleccionadas
        info_label = QLabel(f"Configurando PTZ para {len(self.selected_cells)} celda(s) seleccionada(s)")
        info_label.setStyleSheet("font-weight: bold; margin-bottom: 10px; color: #2E5BBA;")
        layout.addWidget(info_label)
        
        # Mostrar celdas seleccionadas
        cells_text = ", ".join([f"({row},{col})" for row, col in sorted(self.selected_cells)])
        cells_label = QLabel(f"Celdas: {cells_text}")
        cells_label.setStyleSheet("color: gray; font-size: 11px; margin-bottom: 15px;")
        cells_label.setWordWrap(True)
        layout.addWidget(cells_label)
        
        layout.addWidget(QLabel("Cámara PTZ disponible:"))
        combo = QComboBox(dialog)
        
        # MEJORA: Mostrar información más detallada de las cámaras PTZ
        for ptz_ip in self.ptz_cameras:
            ptz_info = self._get_ptz_camera_info(ptz_ip)
            if ptz_info:
                display_text = f"🎯 {ptz_ip} ({ptz_info.get('usuario', 'admin')})"
                combo.addItem(display_text, ptz_ip)  # Usar ptz_ip como data
            else:
                combo.addItem(f"🎯 {ptz_ip}", ptz_ip)
        
        layout.addWidget(combo)

        layout.addWidget(QLabel("Número de preset:"))
        preset_edit = QLineEdit(dialog)
        preset_edit.setPlaceholderText("Ej: 1, 2, 3...")
        preset_edit.setToolTip("Introduce el número del preset (1-255)")
        layout.addWidget(preset_edit)
        
        # Información adicional mejorada
        help_label = QLabel(
            "💡 Información importante:\n"
            "• El preset debe existir previamente en la cámara PTZ\n"
            "• Puedes crear presets usando PTZ > Gestión Avanzada PTZ\n"
            "• El número aparecerá en la esquina de la celda\n"
            "• Celdas con PTZ se marcan en morado"
        )
        help_label.setStyleSheet("color: #555; font-size: 11px; margin: 10px; padding: 8px; "
                                "background-color: #f0f0f0; border-radius: 5px;")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("✅ Asignar PTZ")
        cancel_btn = QPushButton("❌ Cancelar")
        test_btn = QPushButton("🧪 Probar PTZ")  # Botón para probar la conexión
        
        # Mejorar estilo de botones
        ok_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; }")
        cancel_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; }")
        test_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; }")
        
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(test_btn)
        layout.addLayout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        test_btn.clicked.connect(lambda: self._test_ptz_connection(combo.currentData()))

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        ip = combo.currentData() or combo.currentText().split()[1]  # Extraer IP
        preset = preset_edit.text().strip()
        
        if not ip or not preset:
            QMessageBox.warning(self, "Datos incompletos", 
                               "❌ Debe especificar tanto la IP como el preset")
            self.registrar_log("❌ Debe especificar tanto la IP como el preset")
            return

        # Validar que el preset sea numérico
        try:
            preset_num = int(preset)
            if preset_num < 1 or preset_num > 255:
                raise ValueError("Preset fuera de rango")
        except ValueError:
            QMessageBox.warning(self, "Preset inválido", 
                               "❌ El preset debe ser un número entre 1 y 255")
            return

        # Aplicar el mapeo a todas las celdas seleccionadas
        cells_count = len(self.selected_cells)
        for cell in self.selected_cells:
            self.cell_ptz_map[cell] = {"ip": ip, "preset": str(preset)}

        self._save_cell_ptz_map_to_config()
        self.selected_cells.clear()
        self.request_paint_update()
        
        # Log mejorado
        cells_list = ", ".join([f"({row},{col})" for row, col in sorted(self.cell_ptz_map.keys()) 
                               if self.cell_ptz_map[(row, col)]["ip"] == ip and 
                               self.cell_ptz_map[(row, col)]["preset"] == preset])
        
        self.registrar_log(f"✅ PTZ asignado exitosamente:")
        self.registrar_log(f"   📍 Celdas: {cells_list}")
        self.registrar_log(f"   🎯 PTZ: {ip} → Preset {preset}")
        self.registrar_log(f"   📊 Total configurado: {cells_count} celdas")

    def _reload_ptz_cameras(self):
        """Recarga la lista de cámaras PTZ desde la configuración"""
        self.ptz_cameras = []
        
        try:
            with open(CONFIG_FILE_PATH, 'r') as f:
                config_data = json.load(f)
            
            camaras_config = config_data.get("camaras", [])
            for cam_config in camaras_config:
                ip_cfg = cam_config.get("ip")
                tipo_cfg = cam_config.get("tipo")
                
                if tipo_cfg == "ptz" and ip_cfg:
                    if ip_cfg not in self.ptz_cameras:
                        self.ptz_cameras.append(ip_cfg)
                        
                    # Actualizar caché de credenciales
                    self.credentials_cache[ip_cfg] = {
                        "usuario": cam_config.get("usuario"),
                        "contrasena": cam_config.get("contrasena"),
                        "puerto": cam_config.get("puerto", 80),
                        "tipo": tipo_cfg
                    }
            
            self.registrar_log(f"🔄 Cámaras PTZ recargadas: {len(self.ptz_cameras)} encontradas")
            if self.ptz_cameras:
                for ip in self.ptz_cameras:
                    self.registrar_log(f"   📷 PTZ disponible: {ip}")
            
        except Exception as e:
            self.registrar_log(f"❌ Error recargando cámaras PTZ: {e}")

    def _get_ptz_camera_info(self, ptz_ip):
        """Obtiene información detallada de una cámara PTZ"""
        return self.credentials_cache.get(ptz_ip, {})

    def _test_ptz_connection(self, ptz_ip):
        """Prueba la conexión con una cámara PTZ"""
        if not ptz_ip:
            return
            
        self.registrar_log(f"🧪 Probando conexión PTZ a {ptz_ip}...")
        
        try:
            cred = self._get_camera_credentials(ptz_ip)
            if not cred:
                self.registrar_log(f"❌ No se encontraron credenciales para {ptz_ip}")
                return
                
            # Crear instancia PTZ temporalmente para probar
            test_cam = PTZCameraONVIF(
                ptz_ip, cred['puerto'], cred['usuario'], cred['contrasena']
            )
            
            # Si llegamos aquí, la conexión fue exitosa
            self.registrar_log(f"✅ Conexión PTZ exitosa a {ptz_ip}")
            
            QMessageBox.information(
                self, 
                "Prueba PTZ exitosa", 
                f"✅ Conexión establecida correctamente con {ptz_ip}\n\n"
                f"Usuario: {cred['usuario']}\n"
                f"Puerto: {cred['puerto']}"
            )
            
        except Exception as e:
            self.registrar_log(f"❌ Error de conexión PTZ a {ptz_ip}: {e}")
            QMessageBox.warning(
                self, 
                "Error de conexión PTZ", 
                f"❌ No se pudo conectar a {ptz_ip}\n\n"
                f"Error: {str(e)}\n\n"
                f"Verifica:\n"
                f"• IP y puerto correctos\n"
                f"• Usuario y contraseña\n"
                f"• Conexión de red\n"
                f"• Cámara encendida"
            )

    def handle_clear_ptz_map(self):
        """Elimina mapeo PTZ de las celdas seleccionadas - MEJORADO"""
        if not self.selected_cells:
            return

        removed_count = 0
        removed_info = []
        
        for cell in list(self.selected_cells):
            if cell in self.cell_ptz_map:
                ptz_info = self.cell_ptz_map[cell]
                removed_info.append(f"({cell[0]},{cell[1]}) → {ptz_info['ip']} P{ptz_info['preset']}")
                del self.cell_ptz_map[cell]
                removed_count += 1

        if removed_count > 0:
            self._save_cell_ptz_map_to_config()
            self.request_paint_update()
            
            self.registrar_log(f"🗑️ PTZ eliminado de {removed_count} celdas:")
            for info in removed_info:
                self.registrar_log(f"   - {info}")
        else:
            self.registrar_log("⚠️ Las celdas seleccionadas no tenían mapeo PTZ")

    def mouseMoveEvent(self, event):
        if self.cross_line_edit_mode and self._dragging_line:
            pos = event.position()
            x_rel = pos.x() / self.width()
            y_rel = pos.y() / self.height()
            if self._dragging_line == 'new':
                rel_start = (
                    self._temp_line_start.x() / self.width(),
                    self._temp_line_start.y() / self.height(),
                )
                self.cross_counter.set_line((rel_start, (x_rel, y_rel)))
            elif self._dragging_line == 'p1':
                _, p2 = self.cross_counter.line
                self.cross_counter.set_line(((x_rel, y_rel), p2))
            elif self._dragging_line == 'p2':
                p1, _ = self.cross_counter.line
                self.cross_counter.set_line((p1, (x_rel, y_rel)))
            elif self._dragging_line == 'line' and self._last_mouse_pos is not None:
                dx = (pos.x() - self._last_mouse_pos.x()) / self.width()
                dy = (pos.y() - self._last_mouse_pos.y()) / self.height()
                x1_rel, y1_rel = self.cross_counter.line[0]
                x2_rel, y2_rel = self.cross_counter.line[1]
                self.cross_counter.set_line(
                    (
                        (x1_rel + dx, y1_rel + dy),
                        (x2_rel + dx, y2_rel + dy),
                    )
                )
                self._last_mouse_pos = pos
            self.request_paint_update()

    def mouseReleaseEvent(self, event):
        if self.cross_line_edit_mode and self._dragging_line:
            if self._dragging_line == 'new':
                pos = event.position()
                rel_start = (
                    self._temp_line_start.x() / self.width(),
                    self._temp_line_start.y() / self.height(),
                )
                rel_end = (
                    pos.x() / self.width(),
                    pos.y() / self.height(),
                )
                self.cross_counter.set_line((rel_start, rel_end))
            self._dragging_line = None
            self._temp_line_start = None
            self._last_mouse_pos = None
            self.request_paint_update()
        else:
            super().mouseReleaseEvent(event)

    def _save_discarded_cells_to_config(self):
        if not self.cam_data or not self.cam_data.get("ip"):
            self.registrar_log("Error: No se pudo obtener la IP de la cámara")
            return

        current_cam_ip = self.cam_data.get("ip")
        discarded_list_for_json = sorted([list(cell) for cell in self.discarded_cells])

        config_data = None
        try:
            with open(CONFIG_FILE_PATH, 'r') as f:
                config_data = json.load(f)
        except FileNotFoundError:
            config_data = {"camaras": [], "configuracion": {}}
        except json.JSONDecodeError:
            self.registrar_log("Error: Archivo de configuración corrupto")
            return
        except Exception as e:
            self.registrar_log(f"Error leyendo configuración: {e}")
            return

        camara_encontrada = False
        if "camaras" not in config_data:
            config_data["camaras"] = []

        for cam_config in config_data["camaras"]:
            if cam_config.get("ip") == current_cam_ip:
                cam_config["discarded_grid_cells"] = discarded_list_for_json
                camara_encontrada = True
                break
        
        if not camara_encontrada:
            new_cam_entry = self.cam_data.copy() 
            new_cam_entry["discarded_grid_cells"] = discarded_list_for_json
            config_data["camaras"].append(new_cam_entry)

        try:
            with open(CONFIG_FILE_PATH, 'w') as f:
                json.dump(config_data, f, indent=4)
            self.registrar_log("✅ Configuración guardada")
        except Exception as e:
            self.registrar_log(f"Error guardando configuración: {e}")

    def _save_cell_presets_to_config(self):
        if not self.cam_data or not self.cam_data.get("ip"):
            return

        current_cam_ip = self.cam_data.get("ip")
        presets_for_json = {f"{row}_{col}": preset for (row, col), preset in self.cell_presets.items()}

        try:
            with open(CONFIG_FILE_PATH, 'r') as f:
                config_data = json.load(f)
        except FileNotFoundError:
            config_data = {"camaras": [], "configuracion": {}}
        except Exception:
            return

        if "camaras" not in config_data:
            config_data["camaras"] = []

        camera_found = False
        for cam_config in config_data["camaras"]:
            if cam_config.get("ip") == current_cam_ip:
                cam_config["cell_presets"] = presets_for_json
                camera_found = True
                break

        if not camera_found:
            new_cam_entry = self.cam_data.copy()
            new_cam_entry["cell_presets"] = presets_for_json
            config_data["camaras"].append(new_cam_entry)

        try:
            with open(CONFIG_FILE_PATH, 'w') as f:
                json.dump(config_data, f, indent=4)
        except Exception:
            pass

    def _save_cell_ptz_map_to_config(self):
        if not self.cam_data or not self.cam_data.get("ip"):
            return

        current_cam_ip = self.cam_data.get("ip")
        map_for_json = {
            f"{row}_{col}": {"ip": data.get("ip"), "preset": str(data.get("preset", ""))}
            for (row, col), data in self.cell_ptz_map.items()
        }

        try:
            with open(CONFIG_FILE_PATH, 'r') as f:
                config_data = json.load(f)
        except FileNotFoundError:
            config_data = {"camaras": [], "configuracion": {}}
        except Exception:
            return

        if "camaras" not in config_data:
            config_data["camaras"] = []

        found = False
        for cam_config in config_data["camaras"]:
            if cam_config.get("ip") == current_cam_ip:
                cam_config["cell_ptz_map"] = map_for_json
                found = True
                break

        if not found:
            new_cam_entry = self.cam_data.copy()
            new_cam_entry["cell_ptz_map"] = map_for_json
            config_data["camaras"].append(new_cam_entry)

        try:
            with open(CONFIG_FILE_PATH, 'w') as f:
                json.dump(config_data, f, indent=4)
        except Exception:
            pass

    def _get_camera_credentials(self, ip):
        """CORREGIDO: Busca credenciales para cualquier IP, PTZ o fija"""
        # Primero intentar desde el caché
        if ip in self.credentials_cache:
            cred = self.credentials_cache[ip]
            self.registrar_log(f"🔑 Credenciales encontradas en caché para {ip}: usuario={cred.get('usuario')}")
            return cred
            
        # Si no está en caché, buscar en config.json
        try:
            with open(CONFIG_FILE_PATH, 'r') as f:
                data = json.load(f)
            for cam in data.get("camaras", []):
                if cam.get("ip") == ip:
                    cred = {
                        "usuario": cam.get("usuario"),
                        "contrasena": cam.get("contrasena"),
                        "puerto": cam.get("puerto", 80),
                        "tipo": cam.get("tipo")
                    }
                    # Agregar al caché para futuras consultas
                    self.credentials_cache[ip] = cred
                    self.registrar_log(f"🔑 Credenciales cargadas desde config para {ip}: usuario={cred.get('usuario')}")
                    return cred
        except Exception as e:
            self.registrar_log(f"❌ Error buscando credenciales para {ip}: {e}")
            
        self.registrar_log(f"❌ No se encontraron credenciales para {ip}")
        return None

    def _trigger_ptz_move(self, ip, preset):
        cred = self._get_camera_credentials(ip)
        if not cred:
            self.registrar_log(f"❌ Credenciales no encontradas para PTZ {ip}")
            return

        key = f"{ip}:{cred['puerto']}"
        if key not in self.ptz_objects:
            try:
                self.ptz_objects[key] = PTZCameraONVIF(
                    ip, cred['puerto'], cred['usuario'], cred['contrasena']
                )
            except Exception as e:
                self.registrar_log(f"❌ Error inicializando PTZ {ip}: {e}")
                return

        cam = self.ptz_objects[key]
        try:
            cam.goto_preset(preset)
            self.registrar_log(f"✅ PTZ {ip} movido a preset {preset}")
        except Exception as e:
            self.registrar_log(f"❌ Error moviendo PTZ {ip} a preset {preset}: {e}")

    def paintEvent(self, event):
        """Método paintEvent corregido con información de muestreo adaptativo"""
        super().paintEvent(event) 
        qp = QPainter(self)
        
        if not self.pixmap or self.pixmap.isNull():
            qp.fillRect(self.rect(), QColor("black"))
            qp.setPen(QColor("white"))
            qp.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Sin señal")
            return

        # Calcular el área donde se dibuja el video (manteniendo aspect ratio)
        widget_rect = QRectF(self.rect())
        pixmap_size = QSizeF(self.pixmap.size())
        
        # Calcular el tamaño escalado manteniendo aspect ratio
        scaled_size = pixmap_size.scaled(widget_rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
        
        # Centrar el video en el widget
        video_rect = QRectF()
        video_rect.setSize(scaled_size)
        video_rect.moveCenter(widget_rect.center())
        
        # Dibujar el video
        qp.drawPixmap(video_rect, self.pixmap, QRectF(self.pixmap.rect()))

        # Dibujar la grilla de celdas
        cell_w = self.width() / self.columnas
        cell_h = self.height() / self.filas
        
        for row in range(self.filas):
            for col in range(self.columnas):
                index = row * self.columnas + col
                estado_area = self.area[index] if index < len(self.area) else 0
                cell_tuple = (row, col)
                brush_color = None

                if cell_tuple in self.discarded_cells:
                    brush_color = QColor(200, 0, 0, 150)
                elif cell_tuple in self.cell_presets:
                    brush_color = QColor(0, 0, 255, 80)
                elif cell_tuple in self.cell_ptz_map:
                    brush_color = QColor(128, 0, 128, 80)
                elif cell_tuple in self.selected_cells:
                    brush_color = QColor(255, 0, 0, 100)
                elif index in self.temporal:
                    brush_color = QColor(0, 255, 0, 100)
                elif estado_area == 1:
                    brush_color = QColor(255, 165, 0, 100)

                if brush_color is not None:
                    rect_to_draw = QRectF(col * cell_w, row * cell_h, cell_w, cell_h)
                    qp.fillRect(rect_to_draw, brush_color)
                
                # Mostrar preset local (P + número)
                if (row, col) in self.cell_presets:
                    qp.setPen(QColor("white"))
                    preset_text = f"P{self.cell_presets[(row, col)]}"
                    qp.drawText(QPointF(col * cell_w + 2, row * cell_h + 12), preset_text)
                
                # Mostrar preset PTZ remoto (número del preset)
                if (row, col) in self.cell_ptz_map:
                    ptz_info = self.cell_ptz_map[(row, col)]
                    preset_num = ptz_info.get("preset", "?")
                    
                    qp.setPen(QColor("yellow"))
                    font = qp.font()
                    font.setPointSize(8)
                    qp.setFont(font)
                    
                    preset_text = str(preset_num)
                    text_rect = qp.fontMetrics().boundingRect(preset_text)
                    text_width = text_rect.width()
                    
                    qp.drawText(
                        QPointF(col * cell_w + cell_w - text_width - 2, row * cell_h + 10), 
                        preset_text
                    )
                    
                    # Restaurar fuente original
                    font.setPointSize(10)
                    qp.setFont(font)

        # Dibujar líneas de la grilla
        if self._grid_lines_pixmap:
            qp.drawPixmap(self.rect(), self._grid_lines_pixmap)

        # NUEVA FUNCIONALIDAD: Información de muestreo adaptativo en pantalla
        if self.adaptive_sampling_enabled and hasattr(self, 'adaptive_controller') and self.adaptive_controller:
            status = self.get_adaptive_sampling_status()
            
            # Dibujar información del muestreo adaptativo en la esquina superior derecha
            info_text = f"🧠 Adaptativo: {status['current_interval']}"
            activity_score = status.get('activity_score', 0)
            if activity_score > 0:
                info_text += f" | Act: {activity_score:.2f}"
            
            # Fondo semi-transparente
            qp.setPen(QColor("white"))
            font = qp.font()
            font.setPointSize(9)
            qp.setFont(font)
            
            text_rect = qp.fontMetrics().boundingRect(info_text)
            bg_rect = QRectF(
                self.width() - text_rect.width() - 10,
                5,
                text_rect.width() + 6,
                text_rect.height() + 4
            )
            
            qp.fillRect(bg_rect, QColor(0, 0, 0, 180))
            
            # Dibujar texto
            qp.drawText(
                QPointF(self.width() - text_rect.width() - 7, text_rect.height() + 7),
                info_text
            )
        elif not self.adaptive_sampling_enabled:
            # Mostrar información de muestreo fijo
            info_text = f"📊 Fijo: {self.fixed_detection_interval}"
            
            qp.setPen(QColor("lightgray"))
            font = qp.font()
            font.setPointSize(9)
            qp.setFont(font)
            
            text_rect = qp.fontMetrics().boundingRect(info_text)
            bg_rect = QRectF(
                self.width() - text_rect.width() - 10,
                5,
                text_rect.width() + 6,
                text_rect.height() + 4
            )
            
            qp.fillRect(bg_rect, QColor(0, 0, 0, 180))
            qp.drawText(
                QPointF(self.width() - text_rect.width() - 7, text_rect.height() + 7),
                info_text
            )

        # Dibujar las cajas de detección con coordenadas corregidas
        if self.latest_tracked_boxes and self.original_frame_size:
            orig_frame_w = self.original_frame_size.width()
            orig_frame_h = self.original_frame_size.height()
            
            if orig_frame_w == 0 or orig_frame_h == 0:
                return

            # CORRECCIÓN CLAVE: Usar las dimensiones del área real del video, no del widget completo
            scale_x = video_rect.width() / orig_frame_w
            scale_y = video_rect.height() / orig_frame_h
            offset_x = video_rect.left()
            offset_y = video_rect.top()
            
            font = QFont()
            font.setPointSize(10)
            qp.setFont(font)

            for box_data in self.latest_tracked_boxes:
                if not isinstance(box_data, dict):
                    continue

                bbox = box_data.get('bbox', (0, 0, 0, 0))
                if len(bbox) != 4:
                    continue
                    
                x1, y1, x2, y2 = bbox
                tracker_id = box_data.get('id', 'N/A')
                conf = box_data.get('conf', 0)
                conf_val = conf if isinstance(conf, (int, float)) else 0.0

                # Aplicar escalado y offset correctos
                scaled_x1 = (x1 * scale_x) + offset_x
                scaled_y1 = (y1 * scale_y) + offset_y
                scaled_x2 = (x2 * scale_x) + offset_x
                scaled_y2 = (y2 * scale_y) + offset_y
                
                scaled_w = scaled_x2 - scaled_x1
                scaled_h = scaled_y2 - scaled_y1
                
                # Verificar que las coordenadas estén dentro del área del video
                if (scaled_x1 < video_rect.left() or scaled_y1 < video_rect.top() or 
                    scaled_x2 > video_rect.right() or scaled_y2 > video_rect.bottom()):
                    # Las coordenadas están fuera del área del video, skip
                    continue
                
                # MEJORA: Colores dinámicos según confianza
                if conf_val >= 0.70:
                    box_color = QColor("lime")      # Verde brillante para alta confianza
                elif conf_val >= 0.50:
                    box_color = QColor("yellow")    # Amarillo para confianza media
                else:
                    box_color = QColor("orange")    # Naranja para confianza baja
                
                # Dibujar el rectángulo de detección
                pen = QPen()
                pen.setWidth(3)
                pen.setColor(box_color)
                qp.setPen(pen)
                qp.setBrush(Qt.BrushStyle.NoBrush)
                qp.drawRect(QRectF(scaled_x1, scaled_y1, scaled_w, scaled_h))
                
                # Determinar estado de movimiento
                moving_state = box_data.get('moving')
                if moving_state is None:
                    estado = 'Procesando'
                elif moving_state:
                    estado = '🚶 Movimiento'
                else:
                    estado = '🚏 Detenido'
                
                # MEJORA: Indicador visual de si se capturará o no
                capture_indicator = ""
                if hasattr(self.alertas, '_should_capture_track') and tracker_id:
                    # Simular verificación de captura (sin realizar la captura)
                    try:
                        would_capture = conf_val >= 0.50  # Verificación simplificada
                        capture_indicator = " 📸" if would_capture else " 🚫"
                    except:
                        capture_indicator = ""
                
                # Preparar texto de la etiqueta
                label_text = f"ID:{tracker_id} C:{conf_val:.2f} {estado}{capture_indicator}"
                
                # Dibujar fondo para el texto
                text_rect = qp.fontMetrics().boundingRect(label_text)
                text_bg_rect = QRectF(scaled_x1, scaled_y1 - text_rect.height() - 4, 
                                     text_rect.width() + 8, text_rect.height() + 4)
                
                # Si el texto se sale por arriba, ponerlo abajo del box
                if text_bg_rect.top() < video_rect.top():
                    text_bg_rect.moveTop(scaled_y2 + 2)
                
                # Fondo con transparencia
                qp.fillRect(text_bg_rect, QColor(0, 0, 0, 200))
                
                # Dibujar el texto
                qp.setPen(QColor("white"))
                text_x = text_bg_rect.left() + 4
                text_y = text_bg_rect.bottom() - 4
                qp.drawText(QPointF(text_x, text_y), label_text)

        # Dibujar línea de conteo si está activa
        if hasattr(self, 'cross_counter') and self.cross_line_enabled:
            x1_rel, y1_rel = self.cross_counter.line[0]
            x2_rel, y2_rel = self.cross_counter.line[1]
            
            pen = QPen(QColor('yellow'))
            pen.setWidth(3)
            qp.setPen(pen)
            qp.drawLine(
                QPointF(x1_rel * self.width(), y1_rel * self.height()),
                QPointF(x2_rel * self.width(), y2_rel * self.height()),
            )
            
            if self.cross_line_edit_mode:
                handle_pen = QPen(QColor('red'))
                handle_pen.setWidth(4)
                qp.setPen(handle_pen)
                qp.setBrush(QBrush(QColor('red')))
                size = 6
                qp.drawEllipse(QPointF(x1_rel * self.width(), y1_rel * self.height()), size, size)
                qp.drawEllipse(QPointF(x2_rel * self.width(), y2_rel * self.height()), size, size)
            
            # Mostrar conteos
            counts_parts = []
            for direc in ("Entrada", "Salida"):
                sub = self.cross_counts.get(direc, {})
                if sub:
                    sub_text = ", ".join(f"{v} {k}" for k, v in sub.items())
                    counts_parts.append(f"{direc}: {sub_text}")
            
            counts_text = " | ".join(counts_parts)
            if counts_text:
                qp.setPen(QColor('yellow'))
                qp.drawText(QPointF(x2_rel * self.width() + 5, y2_rel * self.height()), counts_text)

    def save_adaptive_config_to_file(self, filename=None):
        """Guarda la configuración actual del muestreo adaptativo a un archivo"""
        if not self.adaptive_sampling_enabled or not self.adaptive_controller:
            self.registrar_log("⚠️ Muestreo adaptativo no está activo")
            return False
        
        try:
            config = self.adaptive_controller.export_config()
            
            if filename is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"adaptive_sampling_{self.cam_data.get('ip', 'unknown')}_{timestamp}.json"
            
            with open(filename, 'w') as f:
                json.dump(config, f, indent=4)
            
            self.registrar_log(f"✅ Configuración de muestreo adaptativo guardada en: {filename}")
            return True
            
        except Exception as e:
            self.registrar_log(f"❌ Error guardando configuración adaptativa: {e}")
            return False

    def load_adaptive_config_from_file(self, filename):
        """Carga configuración del muestreo adaptativo desde un archivo"""
        try:
            with open(filename, 'r') as f:
                config = json.load(f)
            
            # Validar configuración
            if ADAPTIVE_SAMPLING_AVAILABLE:
                success = self.configure_adaptive_sampling(config)
                if success:
                    self.registrar_log(f"✅ Configuración de muestreo adaptativo cargada desde: {filename}")
                    return True
                else:
                    self.registrar_log(f"❌ Error aplicando configuración desde: {filename}")
                    return False
            else:
                self.registrar_log("⚠️ Muestreo adaptativo no disponible")
                return False
                
        except Exception as e:
            self.registrar_log(f"❌ Error cargando configuración adaptativa desde {filename}: {e}")
            return False

    def _get_main_window(self):
        """Obtener referencia a la ventana principal"""
        try:
            widget = self.parent()
            while widget is not None:
                if hasattr(widget, 'send_detections_to_ptz'):
                    return widget
                widget = widget.parent()
            return None
        except Exception:
            return None

    def _convert_boxes_for_ptz(self, boxes):
        """Convertir detecciones al formato esperado por el sistema PTZ"""
        try:
            if not boxes or not self.original_frame_size:
                return []

            ptz_detections = []
            frame_w = self.original_frame_size.width()
            frame_h = self.original_frame_size.height()

            for box_data in boxes:
                if not isinstance(box_data, dict):
                    continue

                bbox = box_data.get('bbox', (0, 0, 0, 0))
                if len(bbox) != 4:
                    continue

                x1, y1, x2, y2 = bbox
                tracker_id = box_data.get('id')
                cls = box_data.get('cls', 0)
                conf = box_data.get('conf', 0)

                cx = float((x1 + x2) / 2)
                cy = float((y1 + y2) / 2)
                width = float(x2 - x1)
                height = float(y2 - y1)

                ptz_detection = {
                    'cx': cx,
                    'cy': cy,
                    'width': width,
                    'height': height,
                    'confidence': float(conf) if isinstance(conf, (int, float)) else 0.0,
                    'class': int(cls),
                    'bbox': [float(x1), float(y1), float(x2), float(y2)],
                    'frame_w': frame_w,
                    'frame_h': frame_h,
                    'track_id': tracker_id,
                    'timestamp': time.time()
                }

                if 'moving' in box_data:
                    ptz_detection['moving'] = box_data['moving']

                if 'centers' in box_data:
                    ptz_detection['centers'] = box_data['centers']

                ptz_detections.append(ptz_detection)

            return ptz_detections

        except Exception as e:
            if DEBUG_LOGS:
                self.registrar_log(f"❌ Error convirtiendo detecciones para PTZ: {e}")
            return []

    def register_with_ptz_system(self):
        """Registrar esta cámara con el sistema PTZ si está disponible"""
        try:
            main_window = self._get_main_window()
            if main_window and hasattr(main_window, 'register_camera_with_ptz') and self.cam_data:
                success = main_window.register_camera_with_ptz(self.cam_data)
                if success:
                    camera_id = self.cam_data.get('ip', 'unknown')
                    self.registrar_log(f"📷 Cámara registrada con sistema PTZ: {camera_id}")
                    return True
            return False
        except Exception as e:
            self.registrar_log(f"❌ Error registrando con sistema PTZ: {e}")
            return False
