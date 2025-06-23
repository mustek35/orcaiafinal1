from PyQt6.QtCore import QThread, pyqtSignal
from logging_utils import get_logger
from ultralytics import YOLO
import numpy as np
from core.advanced_tracker import AdvancedTracker
# ELIMINADA: from gui.image_saver import ImageSaverThread  # ← Esta línea causaba el círculo
import os
from pathlib import Path

logger = get_logger(__name__)

# Caché de modelos YOLO a nivel de módulo
yolo_model_cache = {}

# Ajustar la ruta base usando la ubicación de este archivo
_BASE_MODEL_PATH = Path(__file__).resolve().parent / "models"

MODEL_PATHS = {
    "Embarcaciones": _BASE_MODEL_PATH / "best.pt",
    "Personas": _BASE_MODEL_PATH / "yolov8s.pt",
    "Autos": _BASE_MODEL_PATH / "yolov8s.pt", 
    "Barcos": _BASE_MODEL_PATH / "yolov8s.pt",
}

MODEL_CLASSES = {
    "Embarcaciones": [0],
    "Personas": [0],
    "Autos": [2],
    "Barcos": [8]
}

# Mapear las clases predichas por cada modelo a una clase unificada
CLASS_REMAP = {
    "Embarcaciones": {0: 1},
}

def iou(boxA, boxB):
    xA = max(boxA[0], boxB[0])
    yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2])
    yB = min(boxA[3], boxB[3])
    interArea = max(0, xB - xA) * max(0, yB - yA)
    boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    iou_val = interArea / float(boxAArea + boxBArea - interArea) if (boxAArea + boxBArea - interArea) > 0 else 0
    return iou_val

class DetectorWorker(QThread):
    result_ready = pyqtSignal(list, str, int)

    def __init__(self, model_key="Personas", parent=None, frame_interval=1, confidence=0.5, imgsz=640, device=None, track=True, lost_ttl=5):
        super().__init__(parent)
        self.model_key = model_key
        if device is None:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.setObjectName(f"DetectorWorker_{self.model_key}_{id(self)}")

        logger.info(f"{self.objectName()}: Usando {'GPU' if self.device.startswith('cuda') else 'CPU'} para el modelo '{self.model_key}'")

        # Usar modelo por defecto si no existe el archivo específico
        default_model_path = "yolov8n.pt"  # Modelo que se descarga automáticamente
        model_path = MODEL_PATHS.get(model_key, default_model_path)
        
        # Si el archivo local no existe, usar el modelo por defecto
        if not os.path.exists(model_path):
            logger.warning(f"{self.objectName()}: Archivo del modelo {model_path} no encontrado, usando {default_model_path}")
            model_path = default_model_path

        model_classes_for_key = MODEL_CLASSES.get(model_key)
        if model_classes_for_key is None:
            logger.warning("%s: model_key '%s' no encontrado en MODEL_CLASSES. Usando default [0].", self.objectName(), model_key)
            self.model_classes = [0]
        else:
            self.model_classes = model_classes_for_key

        model_path_str = str(model_path)
        logger.info("YOLO: solicitando modelo '%s' desde %s para %s", self.model_key, model_path_str, self.objectName())
        
        if model_path_str in yolo_model_cache:
            self.model = yolo_model_cache[model_path_str]
            logger.info("YOLO Cache: usando modelo '%s' desde caché para %s", self.model_key, self.objectName())
        else:
            try:
                self.model = YOLO(model_path_str)
                try:
                    self.model.to(self.device)
                except Exception:
                    logger.warning("%s: model.to(%s) failed; relying on predict device parameter", self.objectName(), self.device)
                yolo_model_cache[model_path_str] = self.model
                logger.info("YOLO Cache: modelo '%s' cargado y añadido a caché para %s", self.model_key, self.objectName())
            except Exception as e:
                logger.error("Failed to load model %s for %s: %s", model_path_str, self.objectName(), e)
                raise e

        self.confidence = confidence
        self.imgsz = imgsz
        self.track = track
        self.lost_ttl = lost_ttl
        logger.debug(
            "%s: Initialized with model_key=%s path=%s classes=%s conf=%s imgsz=%s track=%s lost_ttl=%s",
            self.objectName(),
            self.model_key,
            model_path_str,
            self.model_classes,
            self.confidence,
            self.imgsz,
            self.track,
            self.lost_ttl,
        )

        self.frame = None
        self.frame_id = None
        self.running = False
        
        if self.track:
            self.tracker = AdvancedTracker(
                conf_threshold=self.confidence,
                device=self.device,
                lost_ttl=self.lost_ttl,
            )
        else:
            self.tracker = None
        
        self.recently_captured_track_ids = set()
        # ELIMINADA: self.active_savers = []  # Ya no manejamos ImageSaverThread aquí

    # ELIMINADA: def _remove_active_saver() - ya no es necesaria

    def set_frame(self, frame, frame_id=None):
        logger.debug("%s: set_frame called. type=%s is_ndarray=%s", self.objectName(), type(frame), isinstance(frame, np.ndarray))
        if isinstance(frame, np.ndarray):
            logger.debug("%s: Frame shape %s id=%s", self.objectName(), frame.shape, frame_id)
            self.frame = frame
            self.frame_id = frame_id

    def run(self):
        self.running = True
        if not hasattr(self, 'model'):
            logger.error("%s: Modelo no cargado. Deteniendo hilo", self.objectName())
            return

        logger.info("%s: Iniciando bucle de detección", self.objectName())
        
        while self.running:
            if self.frame is not None:
                logger.debug("%s: Processing new frame", self.objectName())
                current_frame_to_process = self.frame
                current_frame_id = self.frame_id if self.frame_id is not None else 0
                frame_h, frame_w = current_frame_to_process.shape[:2]
                self.frame = None
                self.frame_id = None
                
                logger.info(f"%s: Frame dimensions: {frame_w}x{frame_h}", self.objectName())
                
                try:
                    logger.debug("%s: Calling model.predict classes=%s conf=%s imgsz=%s", 
                               self.objectName(), self.model_classes, self.confidence, self.imgsz)
                    
                    # Realizar predicción con YOLO
                    yolo_results = self.model.predict(
                        source=current_frame_to_process, 
                        classes=self.model_classes, 
                        conf=self.confidence, 
                        imgsz=self.imgsz, 
                        verbose=False, 
                        device=self.device,
                        save=False,
                        show=False
                    )[0]
                    
                    logger.info("%s: model.predict successful. Raw boxes count %s", 
                               self.objectName(), len(yolo_results.boxes) if yolo_results.boxes is not None else 0)
                    
                except Exception as e:
                    logger.error("%s: error durante model.predict: %s", self.objectName(), e)
                    self.msleep(100)
                    continue

                current_detections = []
                
                # Procesar resultados de YOLO
                if yolo_results.boxes is not None and len(yolo_results.boxes) > 0:
                    for i, r in enumerate(yolo_results.boxes):
                        try:
                            # Obtener coordenadas originales
                            xyxy = r.xyxy[0].tolist()
                            x1_orig, y1_orig, x2_orig, y2_orig = xyxy
                            
                            # Aplicar límites del frame
                            x1 = int(max(0, min(x1_orig, frame_w - 1)))
                            y1 = int(max(0, min(y1_orig, frame_h - 1)))
                            x2 = int(max(0, min(x2_orig, frame_w - 1)))
                            y2 = int(max(0, min(y2_orig, frame_h - 1)))
                            
                            # Verificar que el box sea válido
                            if x2 <= x1 or y2 <= y1:
                                logger.warning(f"%s: Box inválido ignorado: original=({x1_orig:.1f},{y1_orig:.1f},{x2_orig:.1f},{y2_orig:.1f}) -> clamped=({x1},{y1},{x2},{y2})", self.objectName())
                                continue
                                
                            cls = int(r.cls[0])
                            conf = float(r.conf[0])
                            
                            # Debug: Imprimir coordenadas originales vs procesadas
                            logger.info(f"%s: Detection {i}: original=({x1_orig:.1f},{y1_orig:.1f},{x2_orig:.1f},{y2_orig:.1f}) -> final=({x1},{y1},{x2},{y2}) cls={cls} conf={conf:.3f}", 
                                       self.objectName())
                            
                            # Aplicar remapeo de clases si existe
                            remap_dict = CLASS_REMAP.get(self.model_key)
                            if remap_dict:
                                original_cls = cls
                                cls = remap_dict.get(cls, cls)
                                if original_cls != cls:
                                    logger.info(f"%s: Class remapped: {original_cls} -> {cls}", self.objectName())
                            
                            current_detections.append({
                                'bbox': [x1, y1, x2, y2], 
                                'cls': cls, 
                                'conf': conf
                            })
                            
                        except Exception as e:
                            logger.error("%s: Error procesando detección individual %d: %s", self.objectName(), i, e)
                            continue

                logger.info("%s: Procesadas %d detecciones válidas de %d totales", 
                           self.objectName(), len(current_detections), 
                           len(yolo_results.boxes) if yolo_results.boxes is not None else 0)

                # Aplicar tracking si está habilitado
                if self.track and current_detections:
                    try:
                        tracks = self.tracker.update(current_detections, frame=current_frame_to_process)
                        logger.info("%s: Tracker devolvió %d tracks de %d detecciones", 
                                   self.objectName(), len(tracks), len(current_detections))
                        
                        output_for_signal = []
                        for j, trk in enumerate(tracks):
                            bbox = trk['bbox']
                            x1, y1, x2, y2 = map(int, bbox)
                            
                            # Verificar límites otra vez por seguridad
                            x1 = max(0, min(x1, frame_w - 1))
                            y1 = max(0, min(y1, frame_h - 1))
                            x2 = max(0, min(x2, frame_w - 1))
                            y2 = max(0, min(y2, frame_h - 1))
                            
                            if x2 <= x1 or y2 <= y1:
                                logger.warning(f"%s: Track {j} bbox inválido después de tracking: ({x1},{y1},{x2},{y2})", self.objectName())
                                continue
                            
                            track_data = {
                                'bbox': (x1, y1, x2, y2),
                                'id': trk['id'],
                                'cls': trk['cls'],
                                'conf': trk['conf'],
                                'centers': trk['centers'],
                                'moving': trk.get('moving'),
                            }
                            
                            output_for_signal.append(track_data)
                            
                            logger.info(f"%s: Track {j}: ID={trk['id']} bbox=({x1},{y1},{x2},{y2}) cls={trk['cls']} conf={trk['conf']:.3f}", 
                                       self.objectName())
                            
                    except Exception as e:
                        logger.error("%s: Error en tracker: %s", self.objectName(), e)
                        # Fallback: usar detecciones sin tracking
                        output_for_signal = [
                            {
                                'bbox': (int(d['bbox'][0]), int(d['bbox'][1]), int(d['bbox'][2]), int(d['bbox'][3])),
                                'cls': d['cls'],
                                'conf': d['conf'],
                                'id': i,  # ID temporal
                            }
                            for i, d in enumerate(current_detections)
                        ]
                        logger.info(f"%s: Fallback - usando {len(output_for_signal)} detecciones sin tracking", self.objectName())
                else:
                    # Sin tracking: emitir detecciones directamente
                    output_for_signal = [
                        {
                            'bbox': (int(d['bbox'][0]), int(d['bbox'][1]), int(d['bbox'][2]), int(d['bbox'][3])),
                            'cls': d['cls'],
                            'conf': d['conf'],
                            'id': i,  # ID temporal
                        }
                        for i, d in enumerate(current_detections)
                    ]
                    logger.info(f"%s: Sin tracking - emitiendo {len(output_for_signal)} detecciones directas", self.objectName())

                logger.info("%s: Emitiendo %d detecciones finales para frame %d", 
                           self.objectName(), len(output_for_signal), current_frame_id)
                
                # Debug final: Imprimir todas las detecciones que se van a emitir
                for k, det in enumerate(output_for_signal):
                    bbox = det['bbox']
                    logger.info(f"%s: FINAL Detection {k}: ID={det['id']} bbox={bbox} cls={det['cls']} conf={det['conf']:.3f}", 
                               self.objectName())
                
                # Emitir resultados
                self.result_ready.emit(output_for_signal, self.model_key, current_frame_id)

            self.msleep(10)

    def stop(self):
        logger.info("%s: solicitando detener hilo", self.objectName() or id(self))
        self.running = False
        # ELIMINADO: Manejo de ImageSaverThread - ahora se hace en GestorAlertas
        self.wait()
        logger.info("%s: hilo detenido correctamente", self.objectName())