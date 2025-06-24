# core/multi_object_ptz_system.py
"""
Sistema avanzado de seguimiento PTZ multi-objeto con zoom inteligente
Características:
- Seguimiento de múltiples objetos con alternancia inteligente
- Zoom automático basado en tamaño del objeto
- Priorización por confianza, movimiento, tamaño y proximidad
- Predicción de movimiento y suavizado
- Configuración flexible para diferentes escenarios
"""

import time
import numpy as np
import threading
from enum import Enum
from typing import Optional, Dict, List, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime
import math
import logging

# ===== CORRECCIÓN: Definir ObjectPosition y TrackingState localmente =====
@dataclass
class ObjectPosition:
    """Representa la posición de un objeto detectado en el frame"""
    cx: float          # Centro X normalizado (0-1)
    cy: float          # Centro Y normalizado (0-1) 
    width: float       # Ancho normalizado (0-1)
    height: float      # Altura normalizada (0-1)
    confidence: float  # Confianza de detección (0-1)
    timestamp: float = field(default_factory=time.time)
    frame_w: int = 1920    # Ancho del frame en píxeles
    frame_h: int = 1080    # Alto del frame en píxeles
    object_class: str = "unknown"
    
    def to_pixels(self) -> tuple:
        """Convertir coordenadas normalizadas a píxeles"""
        x1 = int((self.cx - self.width/2) * self.frame_w)
        y1 = int((self.cy - self.height/2) * self.frame_h)
        x2 = int((self.cx + self.width/2) * self.frame_w)
        y2 = int((self.cy + self.height/2) * self.frame_h)
        return (x1, y1, x2, y2)
    
    def get_area(self) -> float:
        """Obtener área del objeto en píxeles cuadrados"""
        return (self.width * self.frame_w) * (self.height * self.frame_h)
    
    def distance_to_center(self) -> float:
        """Calcular distancia al centro del frame (0-1)"""
        return math.sqrt((self.cx - 0.5)**2 + (self.cy - 0.5)**2)

class TrackingState(Enum):
    """Estados del sistema de seguimiento PTZ"""
    IDLE = "idle"
    TRACKING = "tracking"
    SWITCHING = "switching"
    ZOOMING = "zooming"
    ERROR = "error"
    LOST = "lost"

# ===== IMPORTACIONES PTZ CORREGIDAS =====
try:
    from core.ptz_control_enhanced_tracking import SmartPTZTracker
    # Intentar importar versiones mejoradas si existen
    try:
        from core.ptz_control_enhanced_tracking import ObjectPosition as ImportedObjectPosition
        from core.ptz_control_enhanced_tracking import TrackingState as ImportedTrackingState
        # Si se importan correctamente, reemplazar las locales
        ObjectPosition = ImportedObjectPosition
        TrackingState = ImportedTrackingState
        print("✅ Usando ObjectPosition y TrackingState importadas")
    except (ImportError, AttributeError):
        # Si no se pueden importar, usar las definidas arriba
        print("⚠️ Usando ObjectPosition y TrackingState locales")
    
    ENHANCED_TRACKING_AVAILABLE = True
    
except ImportError:
    try:
        from core.ptz_control import PTZCameraONVIF
        ENHANCED_TRACKING_AVAILABLE = False
        print("⚠️ Sistema PTZ mejorado no disponible, usando básico")
    except ImportError:
        print("❌ No hay sistema PTZ disponible")
        raise ImportError("Sistema PTZ requerido no disponible")

class ObjectPriority(Enum):
    """Tipos de prioridad para objetos"""
    HIGH_CONFIDENCE = "high_confidence"
    MOVING = "moving"
    LARGE = "large"
    CLOSE_TO_CENTER = "close"
    RECENT = "recent"

class TrackingMode(Enum):
    """Modos de seguimiento disponibles"""
    SINGLE_OBJECT = "single"
    MULTI_OBJECT_ALTERNATING = "alternating"
    MULTI_OBJECT_PRIORITY = "priority_based"
    AUTO_SWITCH = "auto_switch"

@dataclass
class MultiObjectConfig:
    """Configuración completa para seguimiento multi-objeto"""
    
    # === CONFIGURACIÓN DE ALTERNANCIA ===
    alternating_enabled: bool = True
    primary_follow_time: float = 5.0      # Tiempo siguiendo objeto primario (segundos)
    secondary_follow_time: float = 3.0    # Tiempo siguiendo objeto secundario (segundos)
    min_switch_interval: float = 1.0      # Tiempo mínimo entre cambios
    max_switch_interval: float = 30.0     # Tiempo máximo antes de forzar cambio
    
    # === CONFIGURACIÓN DE PRIORIDAD ===
    confidence_weight: float = 0.4        # Peso de confianza en cálculo de prioridad
    movement_weight: float = 0.3          # Peso de movimiento
    size_weight: float = 0.2              # Peso de tamaño
    proximity_weight: float = 0.1         # Peso de proximidad al centro
    
    # === CONFIGURACIÓN DE ZOOM AUTOMÁTICO ===
    auto_zoom_enabled: bool = True
    target_object_ratio: float = 0.25     # Ratio objetivo del objeto en frame (25%)
    zoom_speed: float = 0.3               # Velocidad de zoom (0.1-1.0)
    min_zoom_level: float = 0.0          # Zoom mínimo
    max_zoom_level: float = 1.0          # Zoom máximo
    zoom_padding: float = 0.1            # Padding alrededor del objeto
    
    # === FILTROS Y UMBRALES ===
    min_confidence_threshold: float = 0.5    # Confianza mínima para detectar
    max_objects_to_track: int = 3             # Máximo número de objetos
    object_lifetime: float = 3.0             # Tiempo antes de considerar perdido
    min_object_size: float = 0.01            # Tamaño mínimo del objeto (ratio)
    max_object_size: float = 0.8             # Tamaño máximo del objeto (ratio)
    
    # === CONTROL DE MOVIMIENTO PTZ ===
    max_pan_speed: float = 0.8           # Velocidad máxima de paneo
    max_tilt_speed: float = 0.8          # Velocidad máxima de inclinación
    movement_smoothing: float = 0.5      # Factor de suavizado (0-1)
    tracking_smoothing: float = 0.3      # Suavizado del seguimiento
    
    # === CONFIGURACIÓN AVANZADA ===
    prediction_enabled: bool = True      # Habilitar predicción de movimiento
    prediction_time: float = 0.1        # Tiempo de predicción (segundos)
    adaptive_zoom: bool = True           # Zoom adaptativo basado en velocidad
    priority_switching: bool = True      # Cambio automático por prioridad
    
    def validate(self) -> bool:
        """Validar que la configuración sea correcta"""
        try:
            assert 0.0 <= self.primary_follow_time <= 60.0
            assert 0.0 <= self.secondary_follow_time <= 60.0
            assert self.min_switch_interval > 0
            assert self.alternating_enabled or self.secondary_follow_time > 0
            assert self.min_zoom_level <= self.max_zoom_level
            assert 0 < self.max_objects_to_track <= 10
            return True
        except AssertionError:
            return False

@dataclass
class TrackedObject:
    """Representa un objeto siendo rastreado con historial completo"""
    id: int
    positions: List[ObjectPosition] = field(default_factory=list)
    last_seen: float = 0.0
    confidence_history: List[float] = field(default_factory=list)
    priority_score: float = 0.0
    
    # Análisis de movimiento
    is_moving: bool = False
    movement_speed: float = 0.0
    movement_direction: float = 0.0  # Ángulo en radianes
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    acceleration: float = 0.0
    
    # Estadísticas temporales
    time_being_tracked: float = 0.0
    first_seen: float = 0.0
    frames_tracked: int = 0
    frames_lost: int = 0
    
    # Características del objeto
    average_size: float = 0.0
    size_stability: float = 0.0  # Qué tan estable es el tamaño
    shape_ratio: float = 1.0     # Width/Height ratio
    
    # Estado de seguimiento
    is_primary_target: bool = False
    last_targeted_time: float = 0.0
    total_tracking_time: float = 0.0
    
    def __post_init__(self):
        if self.first_seen == 0.0:
            self.first_seen = time.time()
    
    def add_position(self, position: ObjectPosition):
        """Agregar nueva posición y actualizar análisis"""
        current_time = time.time()
        
        # Agregar posición
        self.positions.append(position)
        self.confidence_history.append(position.confidence)
        self.last_seen = current_time
        self.frames_tracked += 1
        
        # Mantener historial limitado
        max_history = 20
        if len(self.positions) > max_history:
            self.positions = self.positions[-max_history:]
            self.confidence_history = self.confidence_history[-max_history:]
        
        # Actualizar análisis
        self._update_movement_analysis()
        self._update_size_analysis()
        self._update_tracking_stats()
    
    def _update_movement_analysis(self):
        """Actualizar análisis de movimiento del objeto"""
        if len(self.positions) < 2:
            self.is_moving = False
            self.movement_speed = 0.0
            return
        
        # Calcular velocidades recientes
        recent_positions = self.positions[-5:] if len(self.positions) >= 5 else self.positions
        
        if len(recent_positions) < 2:
            return
        
        # Calcular velocidad promedio
        velocities_x = []
        velocities_y = []
        
        for i in range(1, len(recent_positions)):
            dt = recent_positions[i].timestamp - recent_positions[i-1].timestamp
            if dt > 0:
                vx = (recent_positions[i].cx - recent_positions[i-1].cx) / dt
                vy = (recent_positions[i].cy - recent_positions[i-1].cy) / dt
                velocities_x.append(vx)
                velocities_y.append(vy)
        
        if velocities_x and velocities_y:
            self.velocity_x = sum(velocities_x) / len(velocities_x)
            self.velocity_y = sum(velocities_y) / len(velocities_y)
            self.movement_speed = math.sqrt(self.velocity_x**2 + self.velocity_y**2)
            self.movement_direction = math.atan2(self.velocity_y, self.velocity_x)
            
            # Considerar que se mueve si velocidad > umbral
            self.is_moving = self.movement_speed > 0.01  # 1% del frame por segundo
    
    def _update_size_analysis(self):
        """Actualizar análisis de tamaño del objeto"""
        if not self.positions:
            return
        
        # Calcular tamaño promedio
        sizes = [pos.width * pos.height for pos in self.positions]
        self.average_size = sum(sizes) / len(sizes)
        
        # Calcular estabilidad del tamaño (varianza)
        if len(sizes) > 1:
            variance = sum((s - self.average_size)**2 for s in sizes) / len(sizes)
            self.size_stability = 1.0 / (1.0 + variance)  # 1 = muy estable, 0 = muy variable
        
        # Calcular ratio de forma promedio
        ratios = [pos.width / pos.height if pos.height > 0 else 1.0 for pos in self.positions]
        self.shape_ratio = sum(ratios) / len(ratios)
    
    def _update_tracking_stats(self):
        """Actualizar estadísticas de seguimiento"""
        current_time = time.time()
        self.time_being_tracked = current_time - self.first_seen
        
        if self.is_primary_target:
            self.total_tracking_time += 0.033  # Asumiendo ~30 FPS
    
    def get_average_confidence(self) -> float:
        """Obtener confianza promedio"""
        if not self.confidence_history:
            return 0.0
        return sum(self.confidence_history) / len(self.confidence_history)
    
    def get_current_position(self) -> Optional[ObjectPosition]:
        """Obtener posición más reciente"""
        return self.positions[-1] if self.positions else None
    
    def get_object_size_ratio(self) -> float:
        """Obtener ratio de tamaño del objeto respecto al frame"""
        pos = self.get_current_position()
        if not pos:
            return 0.0
        
        object_area = pos.width * pos.height
        frame_area = pos.frame_w * pos.frame_h
        
        return object_area / frame_area if frame_area > 0 else 0.0
    
    def get_predicted_position(self, time_ahead: float = 0.1) -> Optional[ObjectPosition]:
        """Predecir posición futura basada en velocidad actual"""
        current_pos = self.get_current_position()
        if not current_pos or not self.is_moving:
            return current_pos
        
        # Predicción simple basada en velocidad
        predicted_cx = current_pos.cx + self.velocity_x * time_ahead
        predicted_cy = current_pos.cy + self.velocity_y * time_ahead
        
        # Crear nueva posición predicha
        predicted_pos = ObjectPosition(
            cx=predicted_cx,
            cy=predicted_cy,
            width=current_pos.width,
            height=current_pos.height,
            confidence=current_pos.confidence * 0.8,  # Reducir confianza por predicción
            timestamp=current_pos.timestamp + time_ahead,
            frame_w=current_pos.frame_w,
            frame_h=current_pos.frame_h
        )
        
        return predicted_pos
    
    def is_lost(self, current_time: float, timeout: float = 3.0) -> bool:
        """Determinar si el objeto se considera perdido"""
        return (current_time - self.last_seen) > timeout

class MultiObjectPTZTracker:
    """Tracker PTZ avanzado para seguimiento multi-objeto con zoom inteligente"""
    
    def __init__(self, ip: str, port: int, username: str, password: str, 
                 basic_config=None, multi_config: MultiObjectConfig = None):
        self.ip = ip
        self.port = port
        self.username = username
        self.password = password
        self.basic_config = basic_config
        self.multi_config = multi_config or MultiObjectConfig()
        
        # Validar configuración
        if not self.multi_config.validate():
            raise ValueError("Configuración multi-objeto inválida")
        
        # Estado del sistema
        self.state = TrackingState.IDLE
        self.tracking_active = False
        self.tracking_thread = None
        self.stop_tracking_event = threading.Event()
        
        # Conexión PTZ
        self.camera = None
        self.ptz_service = None
        self.profile_token = None
        self._initialize_camera()
        
        # Estado multi-objeto
        self.tracked_objects: Dict[int, TrackedObject] = {}
        self.next_object_id = 1
        self.current_target_id: Optional[int] = None
        self.secondary_target_id: Optional[int] = None
        
        # Control de alternancia
        self.last_switch_time = 0.0
        self.current_follow_start_time = 0.0
        self.is_following_primary = True
        self.switch_count = 0
        
        # Control de zoom
        self.current_zoom_level = 0.5
        self.target_zoom_level = 0.5
        self.zoom_history = []
        self.zoom_change_count = 0
        
        # Historial de movimiento PTZ
        self.ptz_movement_history = []
        self.current_pan_speed = 0.0
        self.current_tilt_speed = 0.0
        self.target_pan_speed = 0.0
        self.target_tilt_speed = 0.0
        
        # Estadísticas del sistema
        self.session_start_time = time.time()
        self.total_detections_processed = 0
        self.successful_tracks = 0
        self.failed_tracks = 0
        
        # Callbacks para eventos
        self.on_object_detected: Optional[Callable] = None
        self.on_object_lost: Optional[Callable] = None
        self.on_target_switched: Optional[Callable] = None
        self.on_zoom_changed: Optional[Callable] = None
        self.on_state_change: Optional[Callable] = None
        self.on_tracking_update: Optional[Callable] = None
        
        # Logger
        self.logger = logging.getLogger(f'PTZTracker_{ip}')
    
    def _initialize_camera(self):
        """Inicializar conexión con cámara PTZ"""
        try:
            from onvif import ONVIFCamera
            
            self.camera = ONVIFCamera(self.ip, self.port, self.username, self.password)
            self.media = self.camera.create_media_service()
            self.ptz_service = self.camera.create_ptz_service()
            
            # Obtener perfil de medios
            media_profiles = self.media.GetProfiles()
            if media_profiles:
                self.profile_token = media_profiles[0].token
                self.logger.info(f"Cámara PTZ inicializada: {self.ip}:{self.port}")
            else:
                raise Exception("No se encontraron perfiles de medios")
            
        except Exception as e:
            self.logger.error(f"Error inicializando cámara PTZ: {e}")
            raise
    
    def start_tracking(self) -> bool:
        """Iniciar el seguimiento multi-objeto"""
        if self.tracking_active:
            self.logger.warning("El seguimiento ya está activo")
            return False
        
        try:
            self.stop_tracking_event.clear()
            self.tracking_active = True
            self.state = TrackingState.TRACKING
            
            # Iniciar hilo de seguimiento
            self.tracking_thread = threading.Thread(target=self._tracking_loop, daemon=True)
            self.tracking_thread.start()
            
            self.logger.info("Seguimiento multi-objeto iniciado")
            
            if self.on_state_change:
                self.on_state_change(self.state)
            
            return True
        
        except Exception as e:
            self.logger.error(f"Error iniciando seguimiento: {e}")
            self.tracking_active = False
            self.state = TrackingState.ERROR
            return False
    
    def stop_tracking(self):
        """Detener el seguimiento"""
        if not self.tracking_active:
            return
        
        self.stop_tracking_event.set()
        self.tracking_active = False
        
        if self.tracking_thread and self.tracking_thread.is_alive():
            self.tracking_thread.join(timeout=2.0)
        
        # Resetear estado
        self.state = TrackingState.IDLE
        self.current_target_id = None
        self.secondary_target_id = None
        
        self.logger.info("Seguimiento detenido")
        
        if self.on_state_change:
            self.on_state_change(self.state)
    
    def update_detections(self, detections: List[Dict]) -> bool:
        """Actualizar con nuevas detecciones"""
        try:
            current_time = time.time()
            self.total_detections_processed += len(detections)
            
            # Convertir detecciones a ObjectPosition
            new_positions = []
            for det in detections:
                if det.get('confidence', 0) < self.multi_config.min_confidence_threshold:
                    continue
                
                pos = ObjectPosition(
                    cx=det['cx'],
                    cy=det['cy'],
                    width=det['width'],
                    height=det['height'],
                    confidence=det['confidence'],
                    timestamp=current_time,
                    frame_w=det.get('frame_w', 1920),
                    frame_h=det.get('frame_h', 1080),
                    object_class=det.get('class', 'unknown')
                )
                
                # Filtrar por tamaño
                size_ratio = pos.width * pos.height
                if (size_ratio < self.multi_config.min_object_size or 
                    size_ratio > self.multi_config.max_object_size):
                    continue
                
                new_positions.append(pos)
            
            # Actualizar objetos rastreados
            self._update_tracked_objects(new_positions)
            
            # Manejar pérdida de objetos
            self._handle_lost_objects(current_time)
            
            return True
        
        except Exception as e:
            self.logger.error(f"Error actualizando detecciones: {e}")
            return False
    
    def _update_tracked_objects(self, new_positions: List[ObjectPosition]):
        """Actualizar objetos siendo rastreados"""
        current_time = time.time()
        
        # Asociar nuevas posiciones con objetos existentes
        unmatched_positions = new_positions.copy()
        
        for obj_id, tracked_obj in list(self.tracked_objects.items()):
            best_match = None
            best_distance = float('inf')
            
            current_pos = tracked_obj.get_current_position()
            if not current_pos:
                continue
            
            # Buscar la posición más cercana
            for pos in unmatched_positions:
                distance = math.sqrt(
                    (pos.cx - current_pos.cx)**2 + 
                    (pos.cy - current_pos.cy)**2
                )
                
                if distance < best_distance and distance < 0.1:  # Máximo 10% del frame
                    best_distance = distance
                    best_match = pos
            
            # Actualizar objeto si hay coincidencia
            if best_match:
                tracked_obj.add_position(best_match)
                unmatched_positions.remove(best_match)
                
                if self.on_tracking_update:
                    self.on_tracking_update(obj_id, tracked_obj)
        
        # Crear nuevos objetos para posiciones no asociadas
        for pos in unmatched_positions:
            if len(self.tracked_objects) < self.multi_config.max_objects_to_track:
                new_obj = TrackedObject(id=self.next_object_id)
                new_obj.add_position(pos)
                self.tracked_objects[self.next_object_id] = new_obj
                
                if self.on_object_detected:
                    self.on_object_detected(self.next_object_id, new_obj)
                
                self.next_object_id += 1
    
    def _handle_lost_objects(self, current_time: float):
        """Manejar objetos perdidos"""
        lost_objects = []
        
        for obj_id, tracked_obj in list(self.tracked_objects.items()):
            if tracked_obj.is_lost(current_time, self.multi_config.object_lifetime):
                lost_objects.append(obj_id)
        
        for obj_id in lost_objects:
            del self.tracked_objects[obj_id]
            
            if self.on_object_lost:
                self.on_object_lost(obj_id)
            
            # Si se perdió el objetivo actual, cambiar
            if obj_id == self.current_target_id:
                self.current_target_id = None
                self._select_new_target()
    
    def _tracking_loop(self):
        """Bucle principal de seguimiento"""
        while not self.stop_tracking_event.is_set() and self.tracking_active:
            try:
                current_time = time.time()
                
                # Verificar si necesita cambiar de objetivo
                self._check_target_switching(current_time)
                
                # Calcular prioridades
                self._update_object_priorities()
                
                # Ejecutar seguimiento del objetivo actual
                if self.current_target_id and self.current_target_id in self.tracked_objects:
                    self._execute_tracking()
                
                # Control de zoom automático
                if self.multi_config.auto_zoom_enabled:
                    self._update_auto_zoom()
                
                # Dormir un poco para no sobrecargar
                time.sleep(0.033)  # ~30 FPS
                
            except Exception as e:
                self.logger.error(f"Error en bucle de seguimiento: {e}")
                time.sleep(0.1)
        
        self.logger.info("Bucle de seguimiento terminado")
    
    def _check_target_switching(self, current_time: float):
        """Verificar si necesita cambiar de objetivo"""
        if not self.multi_config.alternating_enabled:
            return
        
        # Si no hay objetivo principal, seleccionar uno
        if not self.current_target_id:
            self._select_new_target()
            return
        
        # Verificar tiempo de seguimiento
        follow_time = current_time - self.current_follow_start_time
        
        if self.is_following_primary:
            max_time = self.multi_config.primary_follow_time
        else:
            max_time = self.multi_config.secondary_follow_time
        
        # Cambiar si se excedió el tiempo o se fuerza el cambio
        if (follow_time >= max_time or 
            (current_time - self.last_switch_time) >= self.multi_config.max_switch_interval):
            
            self._switch_target()
    
    def _select_new_target(self):
        """Seleccionar nuevo objetivo principal"""
        if not self.tracked_objects:
            self.current_target_id = None
            return
        
        # Obtener objeto con mayor prioridad
        best_obj_id = max(self.tracked_objects.keys(), 
                         key=lambda oid: self.tracked_objects[oid].priority_score)
        
        if best_obj_id != self.current_target_id:
            old_target = self.current_target_id
            self.current_target_id = best_obj_id
            self.current_follow_start_time = time.time()
            self.is_following_primary = True
            
            # Marcar como objetivo principal
            for obj_id, obj in self.tracked_objects.items():
                obj.is_primary_target = (obj_id == self.current_target_id)
            
            if self.on_target_switched:
                self.on_target_switched(old_target, self.current_target_id)
    
    def _switch_target(self):
        """Cambiar entre objetivos principal y secundario"""
        current_time = time.time()
        
        # Verificar tiempo mínimo entre cambios
        if (current_time - self.last_switch_time) < self.multi_config.min_switch_interval:
            return
        
        if self.is_following_primary:
            # Cambiar a secundario
            if len(self.tracked_objects) > 1:
                # Buscar segundo mejor objeto
                sorted_objects = sorted(self.tracked_objects.items(), 
                                      key=lambda item: item[1].priority_score, 
                                      reverse=True)
                
                if len(sorted_objects) >= 2:
                    old_target = self.current_target_id
                    self.current_target_id = sorted_objects[1][0]
                    self.secondary_target_id = sorted_objects[0][0]
                    self.is_following_primary = False
                    
                    self._update_target_flags()
                    
                    if self.on_target_switched:
                        self.on_target_switched(old_target, self.current_target_id)
        else:
            # Volver al principal
            if self.secondary_target_id and self.secondary_target_id in self.tracked_objects:
                old_target = self.current_target_id
                self.current_target_id = self.secondary_target_id
                self.secondary_target_id = None
                self.is_following_primary = True
                
                self._update_target_flags()
                
                if self.on_target_switched:
                    self.on_target_switched(old_target, self.current_target_id)
        
        self.last_switch_time = current_time
        self.current_follow_start_time = current_time
        self.switch_count += 1
    
    def _update_target_flags(self):
        """Actualizar flags de objetivos en objetos rastreados"""
        for obj_id, obj in self.tracked_objects.items():
            obj.is_primary_target = (obj_id == self.current_target_id)
            if obj.is_primary_target:
                obj.last_targeted_time = time.time()
    
    def _update_object_priorities(self):
        """Actualizar prioridades de todos los objetos"""
        current_time = time.time()
        
        for obj in self.tracked_objects.values():
            # Componentes de prioridad
            confidence_score = obj.get_average_confidence()
            
            movement_score = min(obj.movement_speed * 10, 1.0) if obj.is_moving else 0.0
            
            size_score = min(obj.get_object_size_ratio() * 4, 1.0)
            
            current_pos = obj.get_current_position()
            proximity_score = 1.0 - current_pos.distance_to_center() if current_pos else 0.0
            
            # Calcular prioridad total
            priority = (
                confidence_score * self.multi_config.confidence_weight +
                movement_score * self.multi_config.movement_weight +
                size_score * self.multi_config.size_weight +
                proximity_score * self.multi_config.proximity_weight
            )
            
            # Bonus por tiempo de seguimiento
            tracking_bonus = min(obj.time_being_tracked / 10.0, 0.2)
            priority += tracking_bonus
            
            obj.priority_score = priority
    
    def _execute_tracking(self):
        """Ejecutar seguimiento del objetivo actual"""
        try:
            if not self.current_target_id or self.current_target_id not in self.tracked_objects:
                return
            
            target_obj = self.tracked_objects[self.current_target_id]
            
            # Obtener posición objetivo (con predicción si está habilitada)
            if self.multi_config.prediction_enabled and target_obj.is_moving:
                target_pos = target_obj.get_predicted_position(self.multi_config.prediction_time)
            else:
                target_pos = target_obj.get_current_position()
            
            if not target_pos:
                return
            
            # Calcular comandos PTZ
            pan_speed, tilt_speed = self._calculate_ptz_movement(target_pos)
            
            # Aplicar suavizado
            self.target_pan_speed = pan_speed
            self.target_tilt_speed = tilt_speed
            
            if self.multi_config.movement_smoothing > 0:
                smoothing = self.multi_config.movement_smoothing
                self.current_pan_speed = (self.current_pan_speed * smoothing + 
                                        self.target_pan_speed * (1 - smoothing))
                self.current_tilt_speed = (self.current_tilt_speed * smoothing + 
                                         self.target_tilt_speed * (1 - smoothing))
            else:
                self.current_pan_speed = self.target_pan_speed
                self.current_tilt_speed = self.target_tilt_speed
            
            # Enviar comando PTZ
            self._send_ptz_command(self.current_pan_speed, self.current_tilt_speed)
            
            # Registrar movimiento
            self.ptz_movement_history.append({
                'timestamp': time.time(),
                'pan_speed': self.current_pan_speed,
                'tilt_speed': self.current_tilt_speed,
                'target_id': self.current_target_id,
                'target_pos': (target_pos.cx, target_pos.cy)
            })
            
            # Limitar historial
            if len(self.ptz_movement_history) > 100:
                self.ptz_movement_history = self.ptz_movement_history[-50:]
            
            self.successful_tracks += 1
            
        except Exception as e:
            self.logger.error(f"Error ejecutando seguimiento: {e}")
            self.failed_tracks += 1
    
    def _calculate_ptz_movement(self, target_pos: ObjectPosition) -> Tuple[float, float]:
        """Calcular velocidades de pan y tilt necesarias"""
        # Centro del frame como referencia
        center_x, center_y = 0.5, 0.5
        
        # Calcular error
        error_x = target_pos.cx - center_x
        error_y = target_pos.cy - center_y
        
        # Factor de escala basado en distancia del centro
        distance_factor = math.sqrt(error_x**2 + error_y**2)
        
        # Calcular velocidades base
        pan_speed = error_x * 2.0  # Factor de ganancia
        tilt_speed = -error_y * 2.0  # Invertir Y para tilt
        
        # Aplicar límites de velocidad
        pan_speed = max(-self.multi_config.max_pan_speed, 
                       min(self.multi_config.max_pan_speed, pan_speed))
        tilt_speed = max(-self.multi_config.max_tilt_speed, 
                        min(self.multi_config.max_tilt_speed, tilt_speed))
        
        # Factor de velocidad adaptativo
        if self.multi_config.adaptive_zoom and distance_factor > 0.1:
            # Moverse más rápido si el objeto está lejos del centro
            speed_multiplier = 1.0 + distance_factor
            pan_speed *= speed_multiplier
            tilt_speed *= speed_multiplier
        
        return pan_speed, tilt_speed
    
    def _send_ptz_command(self, pan_speed: float, tilt_speed: float):
        """Enviar comando PTZ a la cámara"""
        try:
            if not self.ptz_service or not self.profile_token:
                return
            
            # Crear request de movimiento continuo
            from onvif import ONVIFCamera
            
            request = self.ptz_service.create_type('ContinuousMove')
            request.ProfileToken = self.profile_token
            
            # Configurar velocidades
            request.Velocity = {
                'PanTilt': {'x': pan_speed, 'y': tilt_speed},
                'Zoom': {'x': 0.0}  # Sin zoom por ahora
            }
            
            # Enviar comando
            self.ptz_service.ContinuousMove(request)
            
        except Exception as e:
            self.logger.error(f"Error enviando comando PTZ: {e}")
    
    def _update_auto_zoom(self):
        """Actualizar zoom automático basado en tamaño del objetivo"""
        try:
            if not self.current_target_id or self.current_target_id not in self.tracked_objects:
                return
            
            target_obj = self.tracked_objects[self.current_target_id]
            current_pos = target_obj.get_current_position()
            
            if not current_pos:
                return
            
            # Calcular ratio actual del objeto
            object_ratio = current_pos.width * current_pos.height
            target_ratio = self.multi_config.target_object_ratio
            
            # Calcular zoom necesario
            if object_ratio < target_ratio * 0.8:  # Objeto muy pequeño
                self.target_zoom_level = min(self.target_zoom_level + 0.1, 
                                           self.multi_config.max_zoom_level)
            elif object_ratio > target_ratio * 1.2:  # Objeto muy grande
                self.target_zoom_level = max(self.target_zoom_level - 0.1, 
                                           self.multi_config.min_zoom_level)
            
            # Aplicar cambio gradual de zoom
            zoom_diff = self.target_zoom_level - self.current_zoom_level
            if abs(zoom_diff) > 0.05:
                zoom_step = zoom_diff * self.multi_config.zoom_speed
                new_zoom = self.current_zoom_level + zoom_step
                
                self._send_zoom_command(new_zoom)
                
                # Registrar cambio de zoom
                self.zoom_history.append({
                    'timestamp': time.time(),
                    'old_zoom': self.current_zoom_level,
                    'new_zoom': new_zoom,
                    'target_id': self.current_target_id,
                    'object_ratio': object_ratio
                })
                
                self.current_zoom_level = new_zoom
                self.zoom_change_count += 1
                
                if self.on_zoom_changed:
                    self.on_zoom_changed(self.current_zoom_level, object_ratio)
            
        except Exception as e:
            self.logger.error(f"Error en auto-zoom: {e}")
    
    def _send_zoom_command(self, zoom_level: float):
        """Enviar comando de zoom a la cámara"""
        try:
            if not self.ptz_service or not self.profile_token:
                return
            
            # Crear request de zoom absoluto
            request = self.ptz_service.create_type('AbsoluteMove')
            request.ProfileToken = self.profile_token
            
            # Configurar zoom (mantener pan/tilt actuales)
            request.Position = {
                'Zoom': {'x': zoom_level}
            }
            
            # Configurar velocidad de zoom
            request.Speed = {
                'Zoom': {'x': self.multi_config.zoom_speed}
            }
            
            # Enviar comando
            self.ptz_service.AbsoluteMove(request)
            
        except Exception as e:
            self.logger.error(f"Error enviando comando de zoom: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Obtener estado completo del tracker"""
        current_time = time.time()
        
        # Información de objetos rastreados
        objects_info = {}
        for obj_id, obj in self.tracked_objects.items():
            current_pos = obj.get_current_position()
            objects_info[obj_id] = {
                'position': {
                    'cx': current_pos.cx if current_pos else None,
                    'cy': current_pos.cy if current_pos else None,
                    'width': current_pos.width if current_pos else None,
                    'height': current_pos.height if current_pos else None
                },
                'confidence': obj.get_average_confidence(),
                'priority': obj.priority_score,
                'is_moving': obj.is_moving,
                'movement_speed': obj.movement_speed,
                'is_primary': obj.is_primary_target,
                'time_tracked': obj.time_being_tracked,
                'frames_tracked': obj.frames_tracked
            }
        
        return {
            'timestamp': current_time,
            'state': self.state.value if hasattr(self.state, 'value') else str(self.state),
            'tracking_active': self.tracking_active,
            'camera_info': {
                'ip': self.ip,
                'port': self.port,
                'connected': self.camera is not None
            },
            'current_target': {
                'id': self.current_target_id,
                'is_primary': self.is_following_primary
            },
            'objects': objects_info,
            'zoom': {
                'current_level': self.current_zoom_level,
                'target_level': self.target_zoom_level
            },
            'movement': {
                'pan_speed': self.current_pan_speed,
                'tilt_speed': self.current_tilt_speed
            },
            'statistics': {
                'session_duration': current_time - self.session_start_time,
                'total_detections': self.total_detections_processed,
                'successful_tracks': self.successful_tracks,
                'failed_tracks': self.failed_tracks,
                'switch_count': self.switch_count,
                'zoom_changes': self.zoom_change_count,
                'objects_count': len(self.tracked_objects)
            },
            'configuration': {
                'alternating_enabled': self.multi_config.alternating_enabled,
                'auto_zoom_enabled': self.multi_config.auto_zoom_enabled,
                'max_objects': self.multi_config.max_objects_to_track,
                'primary_follow_time': self.multi_config.primary_follow_time,
                'secondary_follow_time': self.multi_config.secondary_follow_time
            }
        }
    
    def get_tracking_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas detalladas de seguimiento"""
        current_time = time.time()
        
        # Calcular estadísticas de movimiento PTZ
        ptz_stats = {
            'total_movements': len(self.ptz_movement_history),
            'average_pan_speed': 0.0,
            'average_tilt_speed': 0.0,
            'max_pan_speed': 0.0,
            'max_tilt_speed': 0.0
        }
        
        if self.ptz_movement_history:
            pan_speeds = [move['pan_speed'] for move in self.ptz_movement_history]
            tilt_speeds = [move['tilt_speed'] for move in self.ptz_movement_history]
            
            ptz_stats.update({
                'average_pan_speed': sum(pan_speeds) / len(pan_speeds),
                'average_tilt_speed': sum(tilt_speeds) / len(tilt_speeds),
                'max_pan_speed': max(abs(s) for s in pan_speeds),
                'max_tilt_speed': max(abs(s) for s in tilt_speeds)
            })
        
        # Calcular estadísticas de zoom
        zoom_stats = {
            'total_changes': self.zoom_change_count,
            'current_level': self.current_zoom_level,
            'min_used': self.multi_config.min_zoom_level,
            'max_used': self.multi_config.max_zoom_level
        }
        
        if self.zoom_history:
            zoom_levels = [change['new_zoom'] for change in self.zoom_history]
            zoom_stats.update({
                'min_used': min(zoom_levels),
                'max_used': max(zoom_levels),
                'average_level': sum(zoom_levels) / len(zoom_levels)
            })
        
        # Estadísticas de objetos
        object_stats = {
            'total_tracked': len(self.tracked_objects),
            'with_movement': sum(1 for obj in self.tracked_objects.values() if obj.is_moving),
            'average_confidence': 0.0,
            'average_size': 0.0
        }
        
        if self.tracked_objects:
            confidences = [obj.get_average_confidence() for obj in self.tracked_objects.values()]
            sizes = [obj.get_object_size_ratio() for obj in self.tracked_objects.values()]
            
            object_stats.update({
                'average_confidence': sum(confidences) / len(confidences),
                'average_size': sum(sizes) / len(sizes)
            })
        
        return {
            'session_duration': current_time - self.session_start_time,
            'performance': {
                'detections_per_second': self.total_detections_processed / max(current_time - self.session_start_time, 1),
                'success_rate': self.successful_tracks / max(self.successful_tracks + self.failed_tracks, 1),
                'switches_per_minute': self.switch_count / max((current_time - self.session_start_time) / 60, 1)
            },
            'ptz_movement': ptz_stats,
            'zoom_control': zoom_stats,
            'objects': object_stats
        }
    
    def cleanup(self):
        """Limpiar recursos del tracker"""
        try:
            self.stop_tracking()
            
            # Detener movimiento PTZ
            if self.ptz_service and self.profile_token:
                try:
                    request = self.ptz_service.create_type('Stop')
                    request.ProfileToken = self.profile_token
                    request.PanTilt = True
                    request.Zoom = True
                    self.ptz_service.Stop(request)
                except:
                    pass
            
            # Limpiar datos
            self.tracked_objects.clear()
            self.ptz_movement_history.clear()
            self.zoom_history.clear()
            
            self.logger.info("Tracker limpiado")
            
        except Exception as e:
            self.logger.error(f"Error limpiando tracker: {e}")

# ===== FUNCIONES DE UTILIDAD =====

def create_multi_object_tracker(ip: str, port: int, username: str, password: str,
                               config_name: str = "maritime_standard") -> MultiObjectPTZTracker:
    """Crear tracker multi-objeto con configuración predefinida"""
    
    # Configuraciones predefinidas
    configs = {
        'maritime_standard': MultiObjectConfig(
            alternating_enabled=True,
            primary_follow_time=5.0,
            secondary_follow_time=3.0,
            auto_zoom_enabled=True,
            target_object_ratio=0.25,
            confidence_weight=0.4,
            movement_weight=0.3,
            size_weight=0.2,
            proximity_weight=0.1
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
            zoom_speed=0.2
        ),
        
        'single_object': MultiObjectConfig(
            alternating_enabled=False,
            auto_zoom_enabled=True,
            target_object_ratio=0.35,
            confidence_weight=0.5,
            movement_weight=0.3,
            size_weight=0.2,
            max_objects_to_track=1
        )
    }
    
    config = configs.get(config_name, configs['maritime_standard'])
    return MultiObjectPTZTracker(ip, port, username, password, multi_config=config)

def get_preset_config(config_name: str) -> Optional[MultiObjectConfig]:
    """Obtener configuración predefinida"""
    configs = {
        'maritime_standard': MultiObjectConfig(),
        'maritime_fast': MultiObjectConfig(
            primary_follow_time=3.0,
            secondary_follow_time=2.0,
            movement_weight=0.5,
            zoom_speed=0.5
        ),
        'surveillance_precise': MultiObjectConfig(
            primary_follow_time=8.0,
            secondary_follow_time=4.0,
            confidence_weight=0.6,
            min_confidence_threshold=0.7,
            max_objects_to_track=2
        ),
        'single_object': MultiObjectConfig(
            alternating_enabled=False,
            max_objects_to_track=1
        )
    }
    
    return configs.get(config_name)

# Constante para compatibilidad
PRESET_CONFIGS = ['maritime_standard', 'maritime_fast', 'surveillance_precise', 'single_object']

def analyze_tracking_performance(tracker: MultiObjectPTZTracker) -> Dict[str, Any]:
    """Analizar rendimiento del seguimiento"""
    stats = tracker.get_tracking_statistics()
    
    # Calcular métricas de rendimiento
    performance_score = 0.0
    
    # Factor de éxito (0-40 puntos)
    success_rate = stats['performance']['success_rate']
    performance_score += success_rate * 40
    
    # Factor de detecciones por segundo (0-30 puntos)
    dps = stats['performance']['detections_per_second']
    dps_score = min(dps / 10.0, 1.0) * 30  # Máximo 10 DPS considerado óptimo
    performance_score += dps_score
    
    # Factor de estabilidad de zoom (0-20 puntos)
    zoom_changes = stats['zoom_control']['total_changes']
    session_duration = stats['session_duration']
    zoom_stability = max(0, 1.0 - (zoom_changes / max(session_duration / 60, 1)) / 5.0)  # Máximo 5 cambios por minuto
    performance_score += zoom_stability * 20
    
    # Factor de confianza promedio (0-10 puntos)
    avg_confidence = stats['objects']['average_confidence']
    performance_score += avg_confidence * 10
    
    # Clasificar rendimiento
    if performance_score >= 90:
        grade = "Excelente"
    elif performance_score >= 75:
        grade = "Bueno"
    elif performance_score >= 60:
        grade = "Regular"
    elif performance_score >= 45:
        grade = "Deficiente"
    else:
        grade = "Malo"
    
    return {
        'performance_score': performance_score,
        'grade': grade,
        'metrics': {
            'success_rate': success_rate,
            'detections_per_second': dps,
            'zoom_stability': zoom_stability,
            'average_confidence': avg_confidence
        },
        'recommendations': _generate_recommendations(stats, performance_score)
    }

def _generate_recommendations(stats: Dict, score: float) -> List[str]:
    """Generar recomendaciones para mejorar el rendimiento"""
    recommendations = []
    
    if stats['performance']['success_rate'] < 0.8:
        recommendations.append("Considere ajustar los umbrales de confianza o mejorar la iluminación")
    
    if stats['performance']['detections_per_second'] < 5:
        recommendations.append("Optimice el procesamiento de detecciones o reduzca la resolución")
    
    if stats['zoom_control']['total_changes'] / max(stats['session_duration'] / 60, 1) > 3:
        recommendations.append("Reduzca la velocidad de zoom o aumente los umbrales de cambio")
    
    if stats['objects']['average_confidence'] < 0.6:
        recommendations.append("Mejore las condiciones de detección o ajuste el modelo")
    
    if len(recommendations) == 0:
        recommendations.append("El sistema está funcionando óptimamente")
    
    return recommendations

# ===== FUNCIONES DE TESTING =====

def test_multi_object_tracker():
    """Función de testing básico"""
    print("🧪 Iniciando test del sistema multi-objeto PTZ...")
    
    # Test de configuración
    config = MultiObjectConfig()
    assert config.validate(), "Configuración inválida"
    print("✅ Configuración validada")
    
    # Test de ObjectPosition
    pos = ObjectPosition(cx=0.5, cy=0.5, width=0.1, height=0.1, confidence=0.8)
    assert pos.distance_to_center() == 0.0, "Distancia al centro incorrecta"
    print("✅ ObjectPosition funcionando")
    
    # Test de TrackedObject
    obj = TrackedObject(id=1)
    obj.add_position(pos)
    assert len(obj.positions) == 1, "Error agregando posición"
    print("✅ TrackedObject funcionando")
    
    print("🎉 Todos los tests pasaron exitosamente")

if __name__ == "__main__":
    test_multi_object_tracker()
