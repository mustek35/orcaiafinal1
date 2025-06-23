# tracker_config.py
"""
Configuración avanzada para el sistema de tracking mejorado.
Ajusta estos parámetros según las características de tus objetos a seguir.
"""

TRACKER_CONFIG = {
    # Configuración básica de Deep Sort
    "max_age": 30,              # Frames máximos antes de eliminar un track perdido
    "n_init": 3,                # Detecciones necesarias para confirmar un track
    "nms_max_overlap": 1.0,     # Non-max suppression overlap threshold
    
    # Control de tamaño de bounding box
    "enable_size_control": True,         # Activar control de tamaño
    "max_size_change_ratio": 2.0,        # Cambio máximo permitido entre frames
    "size_history_length": 10,           # Frames para calcular tamaño promedio
    "size_outlier_threshold": 3.0,       # Desviaciones estándar para detectar outliers
    
    # Predicción de velocidad
    "enable_velocity_prediction": True,   # Activar predicción basada en velocidad
    "max_prediction_distance": 100,       # Distancia máxima de predicción (píxeles)
    "velocity_smoothing_factor": 0.7,     # Factor de suavizado de velocidad (0-1)
    
    # Detección de movimiento
    "movement_history_steps": 7,          # Frames para calcular movimiento promedio
    "movement_threshold": 5.0,            # Umbral de distancia para detectar movimiento
    "movement_smoothing_frames": 5,       # Frames para suavizar detección de movimiento
    
    # Gestión de confianza
    "min_detection_confidence": 0.1,      # Confianza mínima para considerar detección
    "prediction_decay_factor": 0.95,      # Factor de decaimiento para predicciones
    "conf_threshold": 0.25,               # Umbral de confianza para mostrar tracks
    
    # Tracks perdidos
    "lost_ttl": 5,                       # Time-to-live para tracks perdidos
    
    # Configuración específica por tipo de objeto
    "object_configs": {
        "Personas": {
            "max_size_change_ratio": 1.5,    # Las personas cambian menos de tamaño
            "movement_threshold": 3.0,         # Más sensible al movimiento
            "lost_ttl": 10,                   # Mantener personas perdidas más tiempo
        },
        "Barcos": {
            "max_size_change_ratio": 3.0,     # Los barcos pueden parecer más grandes/pequeños
            "movement_threshold": 10.0,        # Menos sensible (movimiento más lento)
            "velocity_smoothing_factor": 0.9,  # Más suavizado (movimiento predecible)
            "lost_ttl": 15,                   # Barcos visibles más tiempo
        },
        "Autos": {
            "max_size_change_ratio": 2.0,     # Tamaño moderadamente variable
            "movement_threshold": 8.0,         # Movimiento medio
            "max_prediction_distance": 150,    # Pueden moverse más rápido
            "lost_ttl": 7,
        },
        "Embarcaciones": {
            "max_size_change_ratio": 2.5,     # Similar a barcos
            "movement_threshold": 12.0,        # Movimiento lento
            "velocity_smoothing_factor": 0.85, # Movimiento suave
            "lost_ttl": 12,
            "size_outlier_threshold": 2.5,     # Más tolerante a cambios
        }
    },
    
    # Configuración de visualización
    "visualization": {
        "show_trajectory": True,              # Mostrar trayectoria
        "trajectory_length": 10,              # Puntos de trayectoria a mostrar
        "show_confidence_decay": True,        # Mostrar indicador de decay
        "show_size_correction": True,         # Mostrar cuando se corrige tamaño
        "show_prediction": True,              # Mostrar cuando es predicción
        "box_colors": {
            "normal": (0, 150, 255),          # Azul para tracks normales
            "predicted": (255, 255, 0),       # Amarillo para predicciones
            "low_confidence": (255, 165, 0),  # Naranja para baja confianza
            "size_corrected": (0, 255, 0),    # Verde para tamaño corregido
        }
    },
    
    # Configuración de rendimiento
    "performance": {
        "enable_gpu": True,                   # Usar GPU si está disponible
        "batch_size": 32,                     # Tamaño de batch para embeddings
        "max_tracks": 100,                    # Máximo número de tracks simultáneos
        "cleanup_interval": 100,              # Frames entre limpiezas de memoria
    }
}

def get_tracker_config(model_key=None, override_config=None):
    """
    Obtiene la configuración del tracker, opcionalmente específica para un modelo.
    
    Args:
        model_key: Nombre del modelo (Personas, Barcos, etc.)
        override_config: Diccionario con valores para sobrescribir
    
    Returns:
        Diccionario con la configuración final
    """
    # Empezar con la configuración base
    config = TRACKER_CONFIG.copy()
    
    # Aplicar configuración específica del modelo si existe
    if model_key and model_key in TRACKER_CONFIG["object_configs"]:
        model_config = TRACKER_CONFIG["object_configs"][model_key]
        for key, value in model_config.items():
            if key in config:
                config[key] = value
    
    # Aplicar sobrescrituras si se proporcionan
    if override_config:
        for key, value in override_config.items():
            if key in config:
                config[key] = value
    
    return config