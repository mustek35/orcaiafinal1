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

# Importar sistema PTZ básico
try:
    from core.ptz_control_enhanced_tracking import SmartPTZTracker, TrackingState, ObjectPosition
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
    zoom_speed: float = 0.3               # Velocidad de cambio de zoom (0.1-1.0)
    zoom_deadzone: float = 0.05           # Zona muerta para evitar oscilaciones
    min_zoom_level: float = 0.0           # Zoom mínimo permitido
    max_zoom_level: float = 1.0           # Zoom máximo permitido
    zoom_smoothing: float = 0.7           # Factor de suavizado de zoom (0-1)
    zoom_adaptation_speed: float = 0.1    # Velocidad de adaptación del zoom
    
    # === UMBRALES DE DETECCIÓN ===
    min_confidence_threshold: float = 0.5  # Confianza mínima para considerar objeto
    min_object_size: float = 0.01          # Tamaño mínimo como ratio del frame
    max_object_size: float = 0.8           # Tamaño máximo como ratio del frame
    max_objects_to_track: int = 3          # Máximo número de objetos a rastrear
    
    # === CONFIGURACIÓN DE MOVIMIENTO ===
    movement_detection_frames: int = 5     # Frames para detectar movimiento
    movement_threshold: float = 10.0       # Píxeles mínimos para considerar movimiento
    movement_history_size: int = 10        # Tamaño del historial de movimiento
    
    # === CONFIGURACIÓN DE PÉRDIDA DE OBJETOS ===
    max_lost_frames: int = 15              # Frames máximos antes de considerar perdido
    object_timeout: float = 5.0            # Segundos antes de eliminar objeto inactivo
    
    # === CONFIGURACIÓN DE SEGUIMIENTO ===
    tracking_smoothing: float = 0.7        # Suavizado de movimiento PTZ
    prediction_enabled: bool = True        # Habilitar predicción de movimiento
    prediction_strength: float = 0.3       # Fuerza de la predicción
    velocity_smoothing: float = 0.5        # Suavizado de velocidad
    
    # === CONFIGURACIÓN DE PRESET ===
    preset_wait_time: float = 2.0          # Tiempo de espera en preset
    preset_move_timeout: float = 10.0      # Timeout para movimiento a preset
    
    # === CONFIGURACIÓN AVANZADA ===
    adaptive_sensitivity: bool = True      # Ajustar sensibilidad según contexto
    scene_analysis_enabled: bool = True    # Análisis de escena para optimización
    multi_camera_sync: bool = False        # Sincronización multi-cámara
    
    def validate(self) -> bool:
        """Validar configuración"""
        try:
            assert 0.0 <= self.confidence_weight <= 1.0
            assert 0.0 <= self.movement_weight <= 1.0
            assert 0.0 <= self.size_weight <= 1.0
            assert 0.0 <= self.proximity_weight <= 1.0
            assert abs((self.confidence_weight + self.movement_weight + 
                       self.size_weight + self.proximity_weight) - 1.0) < 0.1
            assert self.primary_follow_time > 0
            assert self.secondary_follow_time > 0
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
        
        # Calcular desplazamiento total y tiempo
        total_distance = 0.0
        total_time = 0.0
        velocities_x = []
        velocities_y = []
        
        for i in range(1, len(recent_positions)):
            prev_pos = recent_positions[i-1]
            curr_pos = recent_positions[i]
            
            # Desplazamiento
            dx = curr_pos.cx - prev_pos.cx
            dy = curr_pos.cy - prev_pos.cy
            distance = math.sqrt(dx*dx + dy*dy)
            
            # Tiempo transcurrido
            dt = curr_pos.timestamp - prev_pos.timestamp
            
            if dt > 0:
                total_distance += distance
                total_time += dt
                velocities_x.append(dx / dt)
                velocities_y.append(dy / dt)
        
        if total_time > 0:
            # Velocidad promedio
            self.movement_speed = total_distance / total_time
            
            # Velocidad en componentes
            if velocities_x and velocities_y:
                self.velocity_x = sum(velocities_x) / len(velocities_x)
                self.velocity_y = sum(velocities_y) / len(velocities_y)
                
                # Dirección de movimiento
                if abs(self.velocity_x) > 0.1 or abs(self.velocity_y) > 0.1:
                    self.movement_direction = math.atan2(self.velocity_y, self.velocity_x)
            
            # Determinar si está en movimiento
            self.is_moving = self.movement_speed > 8.0  # Umbral de movimiento
        else:
            self.movement_speed = 0.0
            self.is_moving = False
    
    def _update_size_analysis(self):
        """Actualizar análisis de tamaño del objeto"""
        if not self.positions:
            return
        
        # Calcular tamaño promedio
        recent_positions = self.positions[-10:]
        areas = []
        ratios = []
        
        for pos in recent_positions:
            area = pos.width * pos.height
            areas.append(area)
            
            if pos.height > 0:
                ratio = pos.width / pos.height
                ratios.append(ratio)
        
        if areas:
            self.average_size = sum(areas) / len(areas)
            
            # Calcular estabilidad del tamaño (menor varianza = más estable)
            if len(areas) > 1:
                mean_area = self.average_size
                variance = sum((area - mean_area)**2 for area in areas) / len(areas)
                self.size_stability = 1.0 / (1.0 + variance / mean_area) if mean_area > 0 else 0.0
        
        if ratios:
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
        self.state = TrackingState.IDLE if ENHANCED_TRACKING_AVAILABLE else "idle"
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
            self.profile_token = self.media.GetProfiles()[0].token
            
            self.logger.info(f"Cámara PTZ inicializada: {self.ip}:{self.port}")
            
        except Exception as e:
            self.logger.error(f"Error inicializando cámara PTZ {self.ip}:{self.port}: {e}")
            self.camera = None
    
    def _set_state(self, new_state):
        """Cambiar estado del sistema"""
        if self.state != new_state:
            old_state = self.state
            self.state = new_state
            self.logger.info(f"Estado PTZ: {old_state} → {new_state}")
            if self.on_state_change:
                self.on_state_change(old_state, new_state)
    
    def goto_preset_and_track(self, preset_token: str, tracking_enabled: bool = True) -> bool:
        """Mover a preset específico y comenzar seguimiento"""
        if not self.camera:
            self.logger.error("Cámara no inicializada")
            return False
        
        try:
            # Detener seguimiento activo
            self.stop_tracking()
            
            # Cambiar estado
            self._set_state(TrackingState.MOVING_TO_PRESET if ENHANCED_TRACKING_AVAILABLE else "moving_to_preset")
            
            # Ejecutar movimiento a preset
            self.logger.info(f"Moviendo a preset {preset_token}...")
            req = self.ptz_service.create_type('GotoPreset')
            req.ProfileToken = self.profile_token
            req.PresetToken = str(preset_token)
            self.ptz_service.GotoPreset(req)
            
            # Esperar en preset
            self._set_state(TrackingState.WAITING_AT_PRESET if ENHANCED_TRACKING_AVAILABLE else "waiting_at_preset")
            self.logger.info(f"Esperando {self.multi_config.preset_wait_time}s en preset...")
            time.sleep(self.multi_config.preset_wait_time)
            
            # Iniciar seguimiento si está habilitado
            if tracking_enabled:
                return self.start_tracking()
            else:
                self._set_state(TrackingState.IDLE if ENHANCED_TRACKING_AVAILABLE else "idle")
                return True
                
        except Exception as e:
            self.logger.error(f"Error yendo a preset {preset_token}: {e}")
            self._set_state(TrackingState.ERROR if ENHANCED_TRACKING_AVAILABLE else "error")
            return False
    
    def start_tracking(self) -> bool:
        """Iniciar seguimiento multi-objeto"""
        if self.tracking_active:
            self.logger.warning("Seguimiento ya activo")
            return True
        
        if not self.camera:
            self.logger.error("No se puede iniciar seguimiento sin cámara")
            return False
        
        try:
            self.tracking_active = True
            self.stop_tracking_event.clear()
            self._set_state(TrackingState.TRACKING_ACTIVE if ENHANCED_TRACKING_AVAILABLE else "tracking_active")
            
            # Reiniciar contadores y estado
            self.tracked_objects.clear()
            self.next_object_id = 1
            self.current_target_id = None
            self.secondary_target_id = None
            self.switch_count = 0
            self.session_start_time = time.time()
            
            self.logger.info("Seguimiento multi-objeto iniciado")
            return True
            
        except Exception as e:
            self.logger.error(f"Error iniciando seguimiento: {e}")
            return False
    
    def stop_tracking(self):
        """Detener seguimiento multi-objeto"""
        if not self.tracking_active:
            return
        
        try:
            self.tracking_active = False
            self.stop_tracking_event.set()
            
            # Detener movimiento de cámara
            if self.camera and self.ptz_service:
                self.ptz_service.Stop({'ProfileToken': self.profile_token})
            
            self._set_state(TrackingState.IDLE if ENHANCED_TRACKING_AVAILABLE else "idle")
            self.logger.info("Seguimiento multi-objeto detenido")
            
        except Exception as e:
            self.logger.error(f"Error deteniendo seguimiento: {e}")
    
    def update_multi_object_tracking(self, detections: List[Dict]) -> bool:
        """Actualizar seguimiento con múltiples detecciones"""
        if not self.tracking_active or not self.camera:
            return False
        
        try:
            current_time = time.time()
            self.total_detections_processed += len(detections)
            
            # Filtrar detecciones válidas
            valid_detections = self._filter_valid_detections(detections)
            
            if not valid_detections:
                self.tracking_lost()
                return False
            
            # Actualizar objetos rastreados
            self._update_tracked_objects(valid_detections, current_time)
            
            # Limpiar objetos perdidos
            self._cleanup_lost_objects(current_time)
            
            # Determinar objetivo actual
            target_id = self._determine_current_target(current_time)
            
            if target_id and target_id in self.tracked_objects:
                target_obj = self.tracked_objects[target_id]
                
                # Usar predicción si está habilitada
                if self.multi_config.prediction_enabled and target_obj.is_moving:
                    target_pos = target_obj.get_predicted_position(0.1)
                else:
                    target_pos = target_obj.get_current_position()
                
                if target_pos:
                    # Actualizar zoom automático
                    if self.multi_config.auto_zoom_enabled:
                        self._update_auto_zoom(target_obj)
                    
                    # Ejecutar seguimiento con zoom
                    success = self._execute_tracking_with_zoom(target_pos)
                    
                    # Verificar cambio de objetivo
                    if success and self.current_target_id != target_id:
                        old_target = self.current_target_id
                        self.current_target_id = target_id
                        self.switch_count += 1
                        
                        # Actualizar estados de objetivo
                        if old_target and old_target in self.tracked_objects:
                            self.tracked_objects[old_target].is_primary_target = False
                        
                        self.tracked_objects[target_id].is_primary_target = True
                        self.tracked_objects[target_id].last_targeted_time = current_time
                        
                        if self.on_target_switched:
                            self.on_target_switched(old_target, target_id)
                        
                        self.logger.info(f"Cambio de objetivo: {old_target} → {target_id}")
                    
                    self.successful_tracks += 1
                    return success
            else:
                # No hay objetivos válidos
                self._handle_no_targets()
                return False
                
        except Exception as e:
            self.logger.error(f"Error en seguimiento multi-objeto: {e}")
            self.failed_tracks += 1
            return False
    
    def tracking_lost(self):
        """Manejar pérdida de seguimiento"""
        try:
            if self.camera and self.ptz_service:
                self.ptz_service.Stop({'ProfileToken': self.profile_token})
            
            self._set_state(TrackingState.TRACKING_LOST if ENHANCED_TRACKING_AVAILABLE else "tracking_lost")
            self.logger.debug("Seguimiento perdido - deteniendo movimiento")
            
        except Exception as e:
            self.logger.error(f"Error manejando pérdida de seguimiento: {e}")
    
    def _filter_valid_detections(self, detections: List[Dict]) -> List[ObjectPosition]:
        """Filtrar y convertir detecciones válidas"""
        valid_detections = []
        
        for det in detections:
            try:
                # Verificar campos requeridos
                required_fields = ['cx', 'cy', 'width', 'height', 'confidence']
                if not all(key in det for key in required_fields):
                    continue
                
                confidence = det['confidence']
                if confidence < self.multi_config.min_confidence_threshold:
                    continue
                
                # Crear ObjectPosition
                obj_pos = ObjectPosition(
                    cx=float(det['cx']),
                    cy=float(det['cy']),
                    width=float(det['width']),
                    height=float(det['height']),
                    confidence=confidence,
                    timestamp=time.time(),
                    frame_w=det.get('frame_w', 1920),
                    frame_h=det.get('frame_h', 1080)
                )
                
                # Verificar tamaño
                size_ratio = (obj_pos.width * obj_pos.height) / (obj_pos.frame_w * obj_pos.frame_h)
                if (size_ratio < self.multi_config.min_object_size or 
                    size_ratio > self.multi_config.max_object_size):
                    continue
                
                valid_detections.append(obj_pos)
                
            except Exception as e:
                self.logger.warning(f"Error procesando detección: {e}")
                continue
        
        return valid_detections
    
    def _update_tracked_objects(self, detections: List[ObjectPosition], current_time: float):
        """Actualizar objetos rastreados con nuevas detecciones"""
        # Asociar detecciones con objetos existentes usando distancia
        unassigned_detections = detections.copy()
        
        for obj_id, tracked_obj in list(self.tracked_objects.items()):
            if not unassigned_detections:
                break
            
            best_detection = None
            best_distance = float('inf')
            
            last_pos = tracked_obj.get_current_position()
            if last_pos:
                for detection in unassigned_detections:
                    # Distancia euclidiana
                    distance = math.sqrt(
                        (detection.cx - last_pos.cx)**2 + 
                        (detection.cy - last_pos.cy)**2
                    )
                    
                    # Factor de tamaño
                    size_diff = abs(detection.width - last_pos.width) + abs(detection.height - last_pos.height)
                    
                    # Distancia combinada
                    combined_distance = distance + size_diff * 0.1
                    
                    # Umbral adaptativo basado en velocidad del objeto
                    max_distance = 50 if not tracked_obj.is_moving else min(100, tracked_obj.movement_speed * 2)
                    
                    if combined_distance < best_distance and distance < max_distance:
                        best_distance = combined_distance
                        best_detection = detection
            
            # Asignar detección al objeto
            if best_detection:
                tracked_obj.add_position(best_detection)
                unassigned_detections.remove(best_detection)
        
        # Crear nuevos objetos para detecciones no asignadas
        for detection in unassigned_detections:
            if len(self.tracked_objects) < self.multi_config.max_objects_to_track:
                new_obj = TrackedObject(id=self.next_object_id)
                new_obj.add_position(detection)
                self.tracked_objects[self.next_object_id] = new_obj
                
                if self.on_object_detected:
                    self.on_object_detected(self.next_object_id, detection)
                
                self.logger.info(f"Nuevo objeto detectado: ID {self.next_object_id}")
                self.next_object_id += 1
    
    def _cleanup_lost_objects(self, current_time: float):
        """Limpiar objetos perdidos"""
        lost_objects = []
        
        for obj_id, tracked_obj in self.tracked_objects.items():
            if tracked_obj.is_lost(current_time, self.multi_config.object_timeout):
                lost_objects.append(obj_id)
        
        for obj_id in lost_objects:
            lost_obj = self.tracked_objects[obj_id]
            
            if self.on_object_lost:
                self.on_object_lost(obj_id, lost_obj)
            
            self.logger.info(f"Objeto perdido: ID {obj_id} (rastreado {lost_obj.time_being_tracked:.1f}s)")
            del self.tracked_objects[obj_id]
            
            # Limpiar referencias
            if self.current_target_id == obj_id:
                self.current_target_id = None
            if self.secondary_target_id == obj_id:
                self.secondary_target_id = None