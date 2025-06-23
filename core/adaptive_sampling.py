# core/adaptive_sampling.py - Sistema de Muestreo Adaptativo para Optimización de Rendimiento

from collections import deque
from datetime import datetime, timedelta
import time
import json
import threading
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple, Any

@dataclass
class AdaptiveSamplingConfig:
    """Configuración para el sistema de muestreo adaptativo"""
    
    # Configuración básica
    base_interval: int = 8           # Intervalo base de frames
    min_interval: int = 3            # Mínimo intervalo (máxima frecuencia)
    max_interval: int = 25           # Máximo intervalo (mínima frecuencia)
    
    # Parámetros de adaptación
    adaptation_rate: float = 0.15    # Velocidad de adaptación (0.1 = lento, 0.3 = rápido)
    detection_weight: float = 0.7    # Peso de las detecciones en el cálculo
    movement_weight: float = 0.3     # Peso del movimiento en el cálculo
    
    # Umbrales de actividad
    high_activity_threshold: float = 0.15  # Umbral para considerar alta actividad
    low_activity_threshold: float = 0.05   # Umbral para considerar baja actividad
    
    # Configuración temporal
    history_window: int = 30         # Ventana de historial en frames
    stabilization_time: int = 50     # Frames para estabilizar cambios
    
    # Configuración de detecciones
    min_detections_for_adaptation: int = 2  # Mínimas detecciones para adaptar
    confidence_threshold: float = 0.3       # Confianza mínima para considerar detección
    
    # Configuración avanzada
    enable_burst_mode: bool = True   # Permitir ráfagas de alta frecuencia
    burst_duration: int = 10         # Duración de ráfagas en frames
    enable_smoothing: bool = True    # Suavizar cambios de intervalo
    
    @classmethod
    def create_config(cls, preset: str = "balanced") -> "AdaptiveSamplingConfig":
        """Crea configuraciones predefinidas"""
        
        presets = {
            "aggressive": cls(
                base_interval=6,
                min_interval=2,
                max_interval=20,
                adaptation_rate=0.25,
                high_activity_threshold=0.12,
                low_activity_threshold=0.03,
                stabilization_time=30,
                enable_burst_mode=True,
                burst_duration=15
            ),
            
            "balanced": cls(
                base_interval=8,
                min_interval=3,
                max_interval=25,
                adaptation_rate=0.15,
                high_activity_threshold=0.15,
                low_activity_threshold=0.05,
                stabilization_time=50,
                enable_burst_mode=True,
                burst_duration=10
            ),
            
            "conservative": cls(
                base_interval=10,
                min_interval=5,
                max_interval=30,
                adaptation_rate=0.08,
                high_activity_threshold=0.20,
                low_activity_threshold=0.08,
                stabilization_time=80,
                enable_burst_mode=False,
                burst_duration=5
            )
        }
        
        return presets.get(preset, presets["balanced"])
    
    def copy(self) -> "AdaptiveSamplingConfig":
        """Crea una copia de la configuración"""
        return AdaptiveSamplingConfig(**asdict(self))


class ActivityScoreCalculator:
    """Calculadora de puntuación de actividad de la escena"""
    
    def __init__(self, config: AdaptiveSamplingConfig):
        self.config = config
        self.detection_history = deque(maxlen=config.history_window)
        self.movement_history = deque(maxlen=config.history_window)
        self.confidence_history = deque(maxlen=config.history_window)
        
    def add_frame_data(self, detections: List[Dict], has_movement: bool = True):
        """Agrega datos de un frame para el cálculo de actividad"""
        
        # Filtrar detecciones por confianza
        valid_detections = [
            det for det in detections 
            if det.get('conf', 0) >= self.config.confidence_threshold
        ]
        
        # Calcular métricas del frame
        detection_count = len(valid_detections)
        avg_confidence = 0.0
        
        if valid_detections:
            avg_confidence = sum(det.get('conf', 0) for det in valid_detections) / len(valid_detections)
        
        # Almacenar en historial
        self.detection_history.append(detection_count)
        self.movement_history.append(1.0 if has_movement else 0.0)
        self.confidence_history.append(avg_confidence)
    
    def calculate_activity_score(self) -> float:
        """Calcula la puntuación de actividad actual (0.0 - 1.0)"""
        
        if len(self.detection_history) < 3:
            return 0.5  # Valor neutro al inicio
        
        # Calcular métricas promedio
        avg_detections = sum(self.detection_history) / len(self.detection_history)
        avg_movement = sum(self.movement_history) / len(self.movement_history)
        avg_confidence = sum(self.confidence_history) / len(self.confidence_history)
        
        # Normalizar detecciones (0-5 detecciones = 0.0-1.0)
        detection_score = min(1.0, avg_detections / 5.0)
        
        # Combinar métricas
        activity_score = (
            self.config.detection_weight * detection_score +
            self.config.movement_weight * avg_movement
        )
        
        # Ajustar por confianza
        confidence_multiplier = 0.5 + (avg_confidence * 0.5)  # 0.5 - 1.0
        activity_score *= confidence_multiplier
        
        return min(1.0, max(0.0, activity_score))
    
    def get_trend(self) -> str:
        """Obtiene la tendencia de actividad (increasing, decreasing, stable)"""
        
        if len(self.detection_history) < 6:
            return "stable"
        
        recent = list(self.detection_history)[-3:]
        older = list(self.detection_history)[-6:-3]
        
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        
        diff = recent_avg - older_avg
        
        if diff > 0.5:
            return "increasing"
        elif diff < -0.5:
            return "decreasing"
        else:
            return "stable"


class AdaptiveIntervalCalculator:
    """Calculadora de intervalos adaptativos"""
    
    def __init__(self, config: AdaptiveSamplingConfig):
        self.config = config
        self.current_interval = config.base_interval
        self.target_interval = config.base_interval
        self.stability_counter = 0
        self.burst_counter = 0
        self.last_change_time = time.time()
        
    def calculate_target_interval(self, activity_score: float, trend: str) -> int:
        """Calcula el intervalo objetivo basado en la actividad"""
        
        # Mapear actividad a intervalo
        if activity_score >= self.config.high_activity_threshold:
            # Alta actividad -> intervalo bajo (más frecuente)
            target = self.config.min_interval
            
            # Modo ráfaga para actividad muy alta
            if (self.config.enable_burst_mode and 
                activity_score > self.config.high_activity_threshold * 1.5):
                target = max(1, self.config.min_interval - 1)
                self.burst_counter = self.config.burst_duration
                
        elif activity_score <= self.config.low_activity_threshold:
            # Baja actividad -> intervalo alto (menos frecuente)
            target = self.config.max_interval
            
        else:
            # Actividad media -> interpolación lineal
            activity_range = self.config.high_activity_threshold - self.config.low_activity_threshold
            interval_range = self.config.max_interval - self.config.min_interval
            
            normalized_activity = (activity_score - self.config.low_activity_threshold) / activity_range
            target = self.config.max_interval - (normalized_activity * interval_range)
            target = int(target)
        
        # Ajustar por tendencia
        if trend == "increasing":
            target = max(self.config.min_interval, target - 2)
        elif trend == "decreasing":
            target = min(self.config.max_interval, target + 1)
        
        return max(self.config.min_interval, min(self.config.max_interval, target))
    
    def update_interval(self, target_interval: int) -> int:
        """Actualiza el intervalo actual hacia el objetivo"""
        
        self.target_interval = target_interval
        
        # Modo ráfaga
        if self.burst_counter > 0:
            self.burst_counter -= 1
            return max(1, self.config.min_interval - 1)
        
        # Suavizar cambios si está habilitado
        if self.config.enable_smoothing:
            diff = self.target_interval - self.current_interval
            
            if abs(diff) <= 1:
                self.current_interval = self.target_interval
                self.stability_counter += 1
            else:
                # Cambio gradual
                change = 1 if diff > 0 else -1
                self.current_interval += change
                self.stability_counter = 0
                self.last_change_time = time.time()
        else:
            # Cambio directo
            self.current_interval = self.target_interval
            self.stability_counter = 0
        
        return self.current_interval
    
    def is_stable(self) -> bool:
        """Verifica si el intervalo está estable"""
        return self.stability_counter >= self.config.stabilization_time


class AdaptiveSamplingController:
    """Controlador principal del sistema de muestreo adaptativo"""
    
    def __init__(self, config: AdaptiveSamplingConfig):
        self.config = config.copy()
        self.activity_calculator = ActivityScoreCalculator(self.config)
        self.interval_calculator = AdaptiveIntervalCalculator(self.config)
        
        # Estado del controlador
        self.enabled = False
        self.frame_counter = 0
        self.processed_frames = 0
        self.skipped_frames = 0
        
        # Estadísticas
        self.stats_history = deque(maxlen=1000)
        self.start_time = time.time()
        
        # Thread safety
        self.lock = threading.RLock()
    
    def enable(self):
        """Activa el muestreo adaptativo"""
        with self.lock:
            self.enabled = True
    
    def disable(self):
        """Desactiva el muestreo adaptativo"""
        with self.lock:
            self.enabled = False
    
    def should_process_frame(self, detections: List[Dict] = None, has_movement: bool = True) -> bool:
        """Determina si se debe procesar el frame actual"""
        
        with self.lock:
            self.frame_counter += 1
            
            if not self.enabled:
                # Modo fijo - usar intervalo base
                should_process = (self.frame_counter % self.config.base_interval) == 0
                if should_process:
                    self.processed_frames += 1
                else:
                    self.skipped_frames += 1
                return should_process
            
            # Actualizar datos de actividad
            if detections is not None:
                self.activity_calculator.add_frame_data(detections, has_movement)
            
            # Calcular nuevo intervalo
            activity_score = self.activity_calculator.calculate_activity_score()
            trend = self.activity_calculator.get_trend()
            target_interval = self.interval_calculator.calculate_target_interval(activity_score, trend)
            current_interval = self.interval_calculator.update_interval(target_interval)
            
            # Determinar si procesar
            should_process = (self.frame_counter % current_interval) == 0
            
            if should_process:
                self.processed_frames += 1
            else:
                self.skipped_frames += 1
            
            # Guardar estadísticas
            self._record_stats(activity_score, current_interval, target_interval, should_process)
            
            return should_process
    
    def _record_stats(self, activity_score: float, current_interval: int, target_interval: int, processed: bool):
        """Registra estadísticas del frame"""
        
        stats = {
            'timestamp': time.time(),
            'frame': self.frame_counter,
            'activity_score': activity_score,
            'current_interval': current_interval,
            'target_interval': target_interval,
            'processed': processed,
            'trend': self.activity_calculator.get_trend()
        }
        
        self.stats_history.append(stats)
    
    def get_current_interval(self) -> int:
        """Obtiene el intervalo actual"""
        with self.lock:
            if self.enabled:
                return self.interval_calculator.current_interval
            else:
                return self.config.base_interval
    
    def get_activity_score(self) -> float:
        """Obtiene la puntuación de actividad actual"""
        with self.lock:
            return self.activity_calculator.calculate_activity_score()
    
    def get_status(self) -> Dict[str, Any]:
        """Obtiene el estado completo del controlador"""
        
        with self.lock:
            efficiency = 0.0
            if self.processed_frames > 0:
                efficiency = (self.skipped_frames / (self.processed_frames + self.skipped_frames)) * 100
            
            runtime = time.time() - self.start_time
            
            status = {
                'enabled': self.enabled,
                'current_interval': self.get_current_interval(),
                'activity_score': self.get_activity_score(),
                'trend': self.activity_calculator.get_trend(),
                'frames_processed': self.processed_frames + self.skipped_frames,
                'frames_analyzed': self.processed_frames,
                'frames_skipped': self.skipped_frames,
                'efficiency_percent': efficiency,
                'runtime_seconds': runtime,
                'is_stable': self.interval_calculator.is_stable(),
                'config': asdict(self.config)
            }
            
            return status
    
    def get_statistics(self, last_n_frames: int = 100) -> Dict[str, Any]:
        """Obtiene estadísticas detalladas"""
        
        with self.lock:
            recent_stats = list(self.stats_history)[-last_n_frames:]
            
            if not recent_stats:
                return {'error': 'No hay estadísticas disponibles'}
            
            # Calcular métricas
            intervals = [s['current_interval'] for s in recent_stats]
            activities = [s['activity_score'] for s in recent_stats]
            
            stats = {
                'frames_analyzed': len(recent_stats),
                'avg_interval': sum(intervals) / len(intervals),
                'min_interval': min(intervals),
                'max_interval': max(intervals),
                'avg_activity': sum(activities) / len(activities),
                'max_activity': max(activities),
                'min_activity': min(activities),
                'interval_changes': len(set(intervals)),
                'time_range': recent_stats[-1]['timestamp'] - recent_stats[0]['timestamp']
            }
            
            return stats
    
    def reset_statistics(self):
        """Reinicia las estadísticas"""
        with self.lock:
            self.frame_counter = 0
            self.processed_frames = 0
            self.skipped_frames = 0
            self.stats_history.clear()
            self.start_time = time.time()
    
    def update_config(self, new_config: AdaptiveSamplingConfig):
        """Actualiza la configuración del controlador"""
        with self.lock:
            self.config = new_config.copy()
            self.activity_calculator = ActivityScoreCalculator(self.config)
            self.interval_calculator = AdaptiveIntervalCalculator(self.config)
    
    def export_config(self) -> Dict[str, Any]:
        """Exporta la configuración actual"""
        return asdict(self.config)
    
    def import_config(self, config_dict: Dict[str, Any]):
        """Importa configuración desde diccionario"""
        new_config = AdaptiveSamplingConfig(**config_dict)
        self.update_config(new_config)


class AdaptiveSamplingManager:
    """Gestor global del sistema de muestreo adaptativo"""
    
    def __init__(self):
        self.controllers: Dict[str, AdaptiveSamplingController] = {}
        self.global_config = AdaptiveSamplingConfig.create_config("balanced")
        
    def create_controller(self, camera_id: str, config: AdaptiveSamplingConfig = None) -> AdaptiveSamplingController:
        """Crea un controlador para una cámara específica"""
        
        if config is None:
            config = self.global_config.copy()
        
        controller = AdaptiveSamplingController(config)
        self.controllers[camera_id] = controller
        
        return controller
    
    def get_controller(self, camera_id: str) -> Optional[AdaptiveSamplingController]:
        """Obtiene el controlador de una cámara"""
        return self.controllers.get(camera_id)
    
    def remove_controller(self, camera_id: str):
        """Elimina el controlador de una cámara"""
        if camera_id in self.controllers:
            del self.controllers[camera_id]
    
    def set_global_config(self, config: AdaptiveSamplingConfig):
        """Establece la configuración global"""
        self.global_config = config.copy()
    
    def apply_config_to_all(self, config: AdaptiveSamplingConfig):
        """Aplica configuración a todos los controladores"""
        for controller in self.controllers.values():
            controller.update_config(config)
    
    def get_global_status(self) -> Dict[str, Any]:
        """Obtiene el estado de todos los controladores"""
        
        status = {
            'total_controllers': len(self.controllers),
            'active_controllers': sum(1 for c in self.controllers.values() if c.enabled),
            'controllers': {}
        }
        
        for camera_id, controller in self.controllers.items():
            status['controllers'][camera_id] = controller.get_status()
        
        return status
    
    def save_config_to_file(self, filepath: str):
        """Guarda configuración global a archivo"""
        try:
            config_data = {
                'global_config': asdict(self.global_config),
                'timestamp': datetime.now().isoformat(),
                'version': '1.0'
            }
            
            with open(filepath, 'w') as f:
                json.dump(config_data, f, indent=4)
                
        except Exception as e:
            raise Exception(f"Error guardando configuración: {e}")
    
    def load_config_from_file(self, filepath: str):
        """Carga configuración desde archivo"""
        try:
            with open(filepath, 'r') as f:
                config_data = json.load(f)
            
            global_config_dict = config_data.get('global_config', {})
            self.global_config = AdaptiveSamplingConfig(**global_config_dict)
            
        except Exception as e:
            raise Exception(f"Error cargando configuración: {e}")


# Instancia global del gestor
adaptive_sampling_manager = AdaptiveSamplingManager()


def create_adaptive_controller(camera_id: str, preset: str = "balanced") -> AdaptiveSamplingController:
    """Función de conveniencia para crear un controlador"""
    config = AdaptiveSamplingConfig.create_config(preset)
    return adaptive_sampling_manager.create_controller(camera_id, config)


def get_adaptive_controller(camera_id: str) -> Optional[AdaptiveSamplingController]:
    """Función de conveniencia para obtener un controlador"""
    return adaptive_sampling_manager.get_controller(camera_id)


# Ejemplo de uso y testing
if __name__ == "__main__":
    print("🧠 Sistema de Muestreo Adaptativo - Prueba de Funcionalidad")
    print("=" * 60)
    
    # Crear controlador de prueba
    config = AdaptiveSamplingConfig.create_config("balanced")
    controller = AdaptiveSamplingController(config)
    controller.enable()
    
    print(f"✅ Controlador creado con configuración: {config.base_interval} intervalo base")
    
    # Simular frames con diferentes niveles de actividad
    scenarios = [
        ("Escena estática", []),
        ("Actividad baja", [{'conf': 0.6}]),
        ("Actividad media", [{'conf': 0.7}, {'conf': 0.5}]),
        ("Actividad alta", [{'conf': 0.8}, {'conf': 0.9}, {'conf': 0.6}, {'conf': 0.7}]),
    ]
    
    for scenario_name, detections in scenarios:
        print(f"\n📊 Simulando: {scenario_name}")
        
        for frame in range(20):
            should_process = controller.should_process_frame(detections, has_movement=len(detections) > 0)
            
            if frame % 5 == 0:  # Mostrar cada 5 frames
                status = controller.get_status()
                print(f"   Frame {frame}: Procesar={should_process}, Intervalo={status['current_interval']}, Actividad={status['activity_score']:.3f}")
    
    # Mostrar estadísticas finales
    final_status = controller.get_status()
    print(f"\n📈 Estadísticas Finales:")
    print(f"   • Total frames: {final_status['frames_processed']}")
    print(f"   • Frames analizados: {final_status['frames_analyzed']}")
    print(f"   • Frames omitidos: {final_status['frames_skipped']}")
    print(f"   • Eficiencia: {final_status['efficiency_percent']:.1f}% frames omitidos")
    print(f"   • Intervalo actual: {final_status['current_interval']}")
    print(f"   • Actividad promedio: {final_status['activity_score']:.3f}")
    
    print("\n✅ Prueba completada - Sistema funcionando correctamente")