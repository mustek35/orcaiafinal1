# core/ptz_tracking_integration_enhanced.py
"""
Sistema de integración PTZ mejorado que conecta:
- Sistema multi-objeto con alternancia
- Control de zoom inteligente
- Integración con detección YOLO/OpenCV
- Gestión de múltiples cámaras PTZ
- Configuración persistente
"""

import threading
import time
import json
import os
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, asdict
from datetime import datetime
import queue
import logging

# Importar sistemas PTZ
try:
    from core.multi_object_ptz_system import (
        MultiObjectPTZTracker, MultiObjectConfig, TrackingMode, 
        create_multi_object_tracker
    )
    MULTI_OBJECT_AVAILABLE = True
except ImportError:
    print("⚠️ Sistema multi-objeto PTZ no disponible")
    MULTI_OBJECT_AVAILABLE = False

# Importar sistema básico como fallback
try:
    from core.ptz_control import PTZCameraONVIF, track_object_continuous
    BASIC_PTZ_AVAILABLE = True
except ImportError:
    print("⚠️ Sistema básico PTZ no disponible")
    BASIC_PTZ_AVAILABLE = False

@dataclass
class CameraSession:
    """Información de una sesión de seguimiento PTZ"""
    camera_id: str
    ip: str
    port: int
    username: str
    password: str
    tracker: Optional[MultiObjectPTZTracker] = None
    thread: Optional[threading.Thread] = None
    active: bool = False
    preset_token: Optional[str] = None
    config: Optional[MultiObjectConfig] = None
    last_detection_time: float = 0.0
    detection_count: int = 0
    switches_count: int = 0
    start_time: float = 0.0
    
class PTZTrackingSystemEnhanced:
    """Sistema PTZ mejorado con capacidades multi-objeto y zoom inteligente"""
    
    def __init__(self, config_file: str = "ptz_enhanced_config.json"):
        self.config_file = config_file
        self.sessions: Dict[str, CameraSession] = {}
        self.detection_queue = queue.Queue(maxsize=1000)
        self.running = True
        
        # Configuraciones predefinidas
        self.predefined_configs = {
            'maritime_standard': MultiObjectConfig(
                alternating_enabled=True,
                primary_follow_time=5.0,
                secondary_follow_time=3.0,
                auto_zoom_enabled=True,
                target_object_ratio=0.25,
                confidence_weight=0.4,
                movement_weight=0.3,
                size_weight=0.2,
                proximity_weight=0.1,
                min_confidence_threshold=0.5,
                max_objects_to_track=3
            ),
            
            'maritime_fast': MultiObjectConfig(
                alternating_enabled=True,
                primary_follow_time=3.0,
                secondary_follow_time=2.0,
                auto_zoom_enabled=True,
                target_object_ratio=0.3,
                confidence_weight=0.3,
                movement_weight=0.5,
                size_weight=0.1,
                proximity_weight=0.1,
                min_confidence_threshold=0.4,
                max_objects_to_track=4,
                zoom_speed=0.5
            ),
            
            'surveillance_precise': MultiObjectConfig(
                alternating_enabled=True,
                primary_follow_time=8.0,
                secondary_follow_time=4.0,
                auto_zoom_enabled=True,
                target_object_ratio=0.4,
                confidence_weight=0.6,
                movement_weight=0.2,
                size_weight=0.1,
                proximity_weight=0.1,
                min_confidence_threshold=0.7,
                max_objects_to_track=2,
                zoom_speed=0.2,
                tracking_smoothing=0.8
            ),
            
            'single_object': MultiObjectConfig(
                alternating_enabled=False,
                primary_follow_time=0.0,
                secondary_follow_time=0.0,
                auto_zoom_enabled=True,
                target_object_ratio=0.35,
                confidence_weight=0.5,
                movement_weight=0.3,
                size_weight=0.2,
                proximity_weight=0.0,
                min_confidence_threshold=0.6,
                max_objects_to_track=1
            )
        }
        
        # Callbacks para eventos
        self.callbacks = {
            'on_session_started': [],
            'on_session_stopped': [],
            'on_object_detected': [],
            'on_object_lost': [],
            'on_target_switched': [],
            'on_zoom_changed': [],
            'on_error': []
        }
        
        # Estadísticas globales
        self.global_stats = {
            'total_sessions': 0,
            'active_sessions': 0,
            'total_detections': 0,
            'total_switches': 0,
            'uptime_start': time.time()
        }
        
        # Cargar configuración
        self._load_system_config()
        
        # Iniciar hilo de procesamiento
        self.processing_thread = threading.Thread(target=self._detection_processing_loop, daemon=True)
        self.processing_thread.start()
        
        # Configurar logging
        self._setup_logging()
    
    def _setup_logging(self):
        """Configurar sistema de logging"""
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        logging.basicConfig(
            level=logging.INFO,
            format=log_format,
            handlers=[
                logging.FileHandler('ptz_tracking.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('PTZTracking')
    
    def register_callback(self, event: str, callback: Callable):
        """Registrar callback para eventos del sistema"""
        if event in self.callbacks:
            self.callbacks[event].append(callback)
    
    def _emit_event(self, event: str, *args, **kwargs):
        """Emitir evento a todos los callbacks registrados"""
        for callback in self.callbacks.get(event, []):
            try:
                callback(*args, **kwargs)
            except Exception as e:
                self.logger.error(f"Error en callback {event}: {e}")
    
    def start_session(self, camera_id: str, ip: str, port: int, username: str, password: str,
                     preset_token: str = "1", config_name: str = "maritime_standard") -> bool:
        """
        Iniciar sesión de seguimiento PTZ para una cámara
        
        Args:
            camera_id: Identificador único de la cámara
            ip: Dirección IP de la cámara
            port: Puerto ONVIF
            username: Usuario de autenticación
            password: Contraseña
            preset_token: Token del preset inicial
            config_name: Nombre de la configuración predefinida
            
        Returns:
            bool: True si se inició correctamente
        """
        if not MULTI_OBJECT_AVAILABLE:
            self.logger.error("Sistema multi-objeto no disponible")
            self._emit_event('on_error', camera_id, "Sistema multi-objeto no disponible")
            return False
        
        if camera_id in self.sessions:
            self.logger.warning(f"Sesión ya existe para {camera_id}, deteniendo anterior")
            self.stop_session(camera_id)
        
        try:
            # Obtener configuración
            config = self.predefined_configs.get(config_name, self.predefined_configs['maritime_standard'])
            
            # Crear sesión
            session = CameraSession(
                camera_id=camera_id,
                ip=ip,
                port=port,
                username=username,
                password=password,
                preset_token=preset_token,
                config=config,
                start_time=time.time()
            )
            
            # Crear tracker
            session.tracker = create_multi_object_tracker(ip, port, username, password, config)
            
            # Configurar callbacks del tracker
            session.tracker.on_object_detected = lambda obj_id, pos: self._on_tracker_object_detected(camera_id, obj_id, pos)
            session.tracker.on_object_lost = lambda obj_id, obj: self._on_tracker_object_lost(camera_id, obj_id, obj)
            session.tracker.on_target_switched = lambda old, new: self._on_tracker_target_switched(camera_id, old, new)
            session.tracker.on_zoom_changed = lambda zoom, speed: self._on_tracker_zoom_changed(camera_id, zoom, speed)
            
            # Iniciar hilo de seguimiento
            session.thread = threading.Thread(
                target=self._session_tracking_loop,
                args=(camera_id, session),
                daemon=True
            )
            
            session.active = True
            self.sessions[camera_id] = session
            session.thread.start()
            
            # Actualizar estadísticas
            self.global_stats['total_sessions'] += 1
            self.global_stats['active_sessions'] += 1
            
            self.logger.info(f"Sesión PTZ iniciada: {camera_id} ({ip}:{port}) con preset {preset_token}")
            self._emit_event('on_session_started', camera_id, session)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error iniciando sesión {camera_id}: {e}")
            self._emit_event('on_error', camera_id, str(e))
            return False
    
    def stop_session(self, camera_id: str) -> bool:
        """Detener sesión de seguimiento PTZ"""
        if camera_id not in self.sessions:
            self.logger.warning(f"Sesión {camera_id} no existe")
            return False
        
        session = self.sessions[camera_id]
        
        try:
            # Marcar como inactiva
            session.active = False
            
            # Detener tracker
            if session.tracker:
                session.tracker.stop_tracking()
            
            # Esperar que termine el hilo
            if session.thread and session.thread.is_alive():
                session.thread.join(timeout=5.0)
            
            # Remover de sesiones activas
            del self.sessions[camera_id]
            
            # Actualizar estadísticas
            self.global_stats['active_sessions'] -= 1
            
            self.logger.info(f"Sesión PTZ detenida: {camera_id}")
            self._emit_event('on_session_stopped', camera_id, session)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error deteniendo sesión {camera_id}: {e}")
            self._emit_event('on_error', camera_id, str(e))
            return False
    
    def stop_all_sessions(self):
        """Detener todas las sesiones activas"""
        session_ids = list(self.sessions.keys())
        for session_id in session_ids:
            self.stop_session(session_id)
        
        self.logger.info("Todas las sesiones PTZ detenidas")
    
    def update_detections(self, camera_id: str, detections: List[Dict]) -> bool:
        """
        Actualizar detecciones para una cámara específica
        
        Args:
            camera_id: ID de la cámara
            detections: Lista de detecciones con formato:
            [
                {
                    'bbox': [x1, y1, x2, y2],
                    'confidence': float,
                    'class': str,
                    'track_id': int (opcional),
                    'frame_w': int,
                    'frame_h': int
                }
            ]
        """
        if camera_id not in self.sessions:
            return False
        
        try:
            # Agregar a cola de procesamiento
            detection_data = {
                'camera_id': camera_id,
                'detections': detections,
                'timestamp': time.time()
            }
            
            # Usar put_nowait para no bloquear
            try:
                self.detection_queue.put_nowait(detection_data)
                return True
            except queue.Full:
                self.logger.warning(f"Cola de detecciones llena para {camera_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error actualizando detecciones para {camera_id}: {e}")
            return False
    
    def process_yolo_results(self, camera_id: str, results, frame_shape: tuple) -> int:
        """
        Procesar resultados de YOLO para una cámara
        
        Args:
            camera_id: ID de la cámara
            results: Resultados de YOLOv8/v5
            frame_shape: (height, width, channels)
            
        Returns:
            int: Número de detecciones procesadas
        """
        try:
            detections = []
            
            if hasattr(results, 'boxes') and len(results.boxes) > 0:
                for i, box in enumerate(results.boxes):
                    try:
                        confidence = float(box.conf[0]) if hasattr(box, 'conf') else 0.0
                        
                        if confidence < 0.3:  # Filtro mínimo
                            continue
                        
                        # Extraer bounding box
                        if hasattr(box, 'xyxy'):
                            bbox = box.xyxy[0].cpu().numpy().tolist()
                        elif hasattr(box, 'xywh'):
                            xywh = box.xywh[0].cpu().numpy()
                            x_center, y_center, width, height = xywh
                            x1 = x_center - width/2
                            y1 = y_center - height/2
                            x2 = x_center + width/2
                            y2 = y_center + height/2
                            bbox = [x1, y1, x2, y2]
                        else:
                            continue
                        
                        # Clase del objeto
                        class_name = "object"
                        if hasattr(box, 'cls') and hasattr(results, 'names'):
                            class_id = int(box.cls[0])
                            class_name = results.names.get(class_id, "object")
                        
                        # Track ID si está disponible
                        track_id = None
                        if hasattr(box, 'id') and box.id is not None:
                            track_id = int(box.id[0])
                        
                        detection = {
                            'bbox': bbox,
                            'confidence': confidence,
                            'class': class_name,
                            'track_id': track_id,
                            'frame_w': frame_shape[1],
                            'frame_h': frame_shape[0]
                        }
                        
                        detections.append(detection)
                        
                    except Exception as e:
                        self.logger.warning(f"Error procesando detección {i}: {e}")
                        continue
            
            # Actualizar con las detecciones procesadas
            if self.update_detections(camera_id, detections):
                return len(detections)
            else:
                return 0
                
        except Exception as e:
            self.logger.error(f"Error procesando resultados YOLO para {camera_id}: {e}")
            return 0
    
    def get_session_status(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """Obtener estado de una sesión"""
        if camera_id not in self.sessions:
            return None
        
        session = self.sessions[camera_id]
        
        status = {
            'camera_id': camera_id,
            'ip': session.ip,
            'active': session.active,
            'preset_token': session.preset_token,
            'detection_count': session.detection_count,
            'switches_count': session.switches_count,
            'uptime': time.time() - session.start_time,
            'last_detection_time': session.last_detection_time,
            'config_name': self._get_config_name(session.config)
        }
        
        if session.tracker:
            tracker_stats = session.tracker.get_tracking_stats()
            status.update({
                'tracking_stats': tracker_stats,
                'current_target': tracker_stats.get('current_target'),
                'total_objects': tracker_stats.get('total_objects', 0),
                'current_zoom': tracker_stats.get('current_zoom', 0.5)
            })
        
        return status
    
    def get_global_status(self) -> Dict[str, Any]:
        """Obtener estado global del sistema"""
        return {
            'total_sessions': self.global_stats['total_sessions'],
            'active_sessions': self.global_stats['active_sessions'],
            'total_detections': self.global_stats['total_detections'],
            'total_switches': self.global_stats['total_switches'],
            'system_uptime': time.time() - self.global_stats['uptime_start'],
            'available_configs': list(self.predefined_configs.keys()),
            'queue_size': self.detection_queue.qsize()
        }
    
    def _session_tracking_loop(self, camera_id: str, session: CameraSession):
        """Loop principal de seguimiento para una sesión"""
        try:
            tracker = session.tracker
            if not tracker:
                return
            
            # Ir al preset inicial
            if session.preset_token:
                self.logger.info(f"[{camera_id}] Moviendo a preset {session.preset_token}")
                if not tracker.goto_preset_and_track(session.preset_token, True):
                    self.logger.error(f"[{camera_id}] Error yendo a preset {session.preset_token}")
                    session.active = False
                    return
            else:
                tracker.start_tracking()
            
            self.logger.info(f"[{camera_id}] Seguimiento iniciado")
            
            # Loop principal
            while session.active and tracker.tracking_active:
                try:
                    time.sleep(0.033)  # ~30 FPS
                except Exception as e:
                    self.logger.error(f"[{camera_id}] Error en loop: {e}")
                    time.sleep(1)
            
        except Exception as e:
            self.logger.error(f"[{camera_id}] Error crítico en seguimiento: {e}")
        finally:
            session.active = False
            if session.tracker:
                session.tracker.stop_tracking()
    
    def _detection_processing_loop(self):
        """Loop de procesamiento de detecciones"""
        while self.running:
            try:
                # Obtener detección de la cola (timeout para permitir salida limpia)
                detection_data = self.detection_queue.get(timeout=1.0)
                
                camera_id = detection_data['camera_id']
                detections = detection_data['detections']
                
                if camera_id in self.sessions:
                    session = self.sessions[camera_id]
                    if session.active and session.tracker:
                        # Convertir formato para el tracker
                        converted_detections = self._convert_detections_format(detections)
                        
                        # Actualizar tracker
                        session.tracker.update_multi_object_tracking(converted_detections)
                        
                        # Actualizar estadísticas
                        session.detection_count += len(detections)
                        session.last_detection_time = time.time()
                        self.global_stats['total_detections'] += len(detections)
                
                self.detection_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error procesando detecciones: {e}")
    
    def _convert_detections_format(self, detections: List[Dict]) -> List[Dict]:
        """Convertir formato de detecciones para el tracker"""
        converted = []
        
        for det in detections:
            if 'bbox' in det and len(det['bbox']) == 4:
                x1, y1, x2, y2 = det['bbox']
                
                converted_det = {
                    'cx': (x1 + x2) / 2,
                    'cy': (y1 + y2) / 2,
                    'width': x2 - x1,
                    'height': y2 - y1,
                    'confidence': det.get('confidence', 0.0),
                    'frame_w': det.get('frame_w', 1920),
                    'frame_h': det.get('frame_h', 1080),
                    'class': det.get('class', 'object'),
                    'track_id': det.get('track_id')
                }
                
                converted.append(converted_det)
        
        return converted
    
    def _get_config_name(self, config: MultiObjectConfig) -> str:
        """Obtener nombre de configuración"""
        for name, predefined_config in self.predefined_configs.items():
            if self._configs_equal(config, predefined_config):
                return name
        return "custom"
    
    def _configs_equal(self, config1: MultiObjectConfig, config2: MultiObjectConfig) -> bool:
        """Comparar si dos configuraciones son iguales"""
        return asdict(config1) == asdict(config2)
    
    # Callbacks del tracker
    def _on_tracker_object_detected(self, camera_id: str, obj_id: int, position):
        """Callback cuando se detecta objeto"""
        self.logger.debug(f"[{camera_id}] Objeto {obj_id} detectado")
        self._emit_event('on_object_detected', camera_id, obj_id, position)
    
    def _on_tracker_object_lost(self, camera_id: str, obj_id: int, tracked_obj):
        """Callback cuando se pierde objeto"""
        self.logger.debug(f"[{camera_id}] Objeto {obj_id} perdido")
        self._emit_event('on_object_lost', camera_id, obj_id, tracked_obj)
    
    def _on_tracker_target_switched(self, camera_id: str, old_target: int, new_target: int):
        """Callback cuando cambia objetivo de seguimiento"""
        if camera_id in self.sessions:
            self.sessions[camera_id].switches_count += 1
            self.global_stats['total_switches'] += 1
        
        self.logger.info(f"[{camera_id}] Cambio de objetivo: {old_target} → {new_target}")
        self._emit_event('on_target_switched', camera_id, old_target, new_target)
    
    def _on_tracker_zoom_changed(self, camera_id: str, zoom_level: float, zoom_speed: float):
        """Callback cuando cambia zoom"""
        self.logger.debug(f"[{camera_id}] Zoom: {zoom_level:.1%} (velocidad: {zoom_speed:.2f})")
        self._emit_event('on_zoom_changed', camera_id, zoom_level, zoom_speed)
    
    def _load_system_config(self):
        """Cargar configuración del sistema"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
                
                # Cargar configuraciones personalizadas
                custom_configs = config_data.get('custom_configs', {})
                for name, config_dict in custom_configs.items():
                    try:
                        custom_config = MultiObjectConfig(**config_dict)
                        self.predefined_configs[name] = custom_config
                    except Exception as e:
                        self.logger.warning(f"Error cargando configuración {name}: {e}")
                
                self.logger.info(f"Configuración cargada desde {self.config_file}")
                
            except Exception as e:
                self.logger.warning(f"Error cargando configuración: {e}")
    
    def save_system_config(self):
        """Guardar configuración del sistema"""
        try:
            config_data = {
                'custom_configs': {},
                'last_updated': datetime.now().isoformat()
            }
            
            # Guardar configuraciones personalizadas
            for name, config in self.predefined_configs.items():
                if name not in ['maritime_standard', 'maritime_fast', 'surveillance_precise', 'single_object']:
                    config_data['custom_configs'][name] = asdict(config)
            
            with open(self.config_file, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            self.logger.info(f"Configuración guardada en {self.config_file}")
            
        except Exception as e:
            self.logger.error(f"Error guardando configuración: {e}")
    
    def add_custom_config(self, name: str, config: MultiObjectConfig):
        """Agregar configuración personalizada"""
        self.predefined_configs[name] = config
        self.save_system_config()
        self.logger.info(f"Configuración personalizada '{name}' agregada")
    
    def shutdown(self):
        """Apagar sistema limpiamente"""
        self.logger.info("Iniciando apagado del sistema PTZ")
        
        # Detener procesamiento
        self.running = False
        
        # Detener todas las sesiones
        self.stop_all_sessions()
        
        # Esperar que termine el hilo de procesamiento
        if self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5.0)
        
        # Guardar configuración
        self.save_system_config()
        
        self.logger.info("Sistema PTZ apagado completamente")


# Instancia global para uso fácil
ptz_system = PTZTrackingSystemEnhanced()

# Funciones de conveniencia
def start_ptz_session(camera_id: str, ip: str, port: int, username: str, password: str,
                     preset: str = "1", config: str = "maritime_standard") -> bool:
    """Función de conveniencia para iniciar sesión PTZ"""
    return ptz_system.start_session(camera_id, ip, port, username, password, preset, config)

def stop_ptz_session(camera_id: str) -> bool:
    """Función de conveniencia para detener sesión PTZ"""
    return ptz_system.stop_session(camera_id)

def update_ptz_detections(camera_id: str, detections: List[Dict]) -> bool:
    """Función de conveniencia para actualizar detecciones"""
    return ptz_system.update_detections(camera_id, detections)

def process_ptz_yolo_results(camera_id: str, results, frame_shape: tuple) -> int:
    """Función de conveniencia para procesar YOLO"""
    return ptz_system.process_yolo_results(camera_id, results, frame_shape)

def get_ptz_status(camera_id: str = None) -> Dict:
    """Función de conveniencia para obtener estado"""
    if camera_id:
        return ptz_system.get_session_status(camera_id)
    else:
        return ptz_system.get_global_status()

# Configuración para uso en aplicaciones
def setup_ptz_logging(log_file: str = None, log_level: str = "INFO"):
    """Configurar logging personalizado"""
    if log_file:
        handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        logger = logging.getLogger('PTZTracking')
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, log_level.upper()))

if __name__ == "__main__":
    # Ejemplo de uso del sistema
    print("🧪 Probando sistema PTZ mejorado...")
    
    # Configurar logging
    setup_ptz_logging("ptz_test.log", "DEBUG")
    
    # Registrar callbacks de ejemplo
    def on_target_switch(camera_id, old_target, new_target):
        print(f"[{camera_id}] 🔄 Cambio: {old_target} → {new_target}")
    
    ptz_system.register_callback('on_target_switched', on_target_switch)
    
    # Simular uso
    camera_id = "test_camera_1"
    
    if start_ptz_session(camera_id, "192.168.1.100", 80, "admin", "password123"):
        print(f"✅ Sesión iniciada para {camera_id}")
        
        # Simular detecciones
        for i in range(10):
            detections = [
                {
                    'bbox': [800 + i*10, 400, 950 + i*10, 550],
                    'confidence': 0.8,
                    'class': 'boat',
                    'frame_w': 1920,
                    'frame_h': 1080
                }
            ]
            
            update_ptz_detections(camera_id, detections)
            time.sleep(1)
        
        # Obtener estado
        status = get_ptz_status(camera_id)
        print(f"📊 Estado: {status}")
        
        # Detener
        stop_ptz_session(camera_id)
        print(f"⏹️ Sesión detenida para {camera_id}")
    
    # Apagar sistema
    ptz_system.shutdown()
    print("✅ Prueba completada")