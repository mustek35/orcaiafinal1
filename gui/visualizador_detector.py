from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink, QVideoFrameFormat, QVideoFrame
from PyQt6.QtCore import QObject, pyqtSignal, QUrl
from PyQt6.QtGui import QImage
import numpy as np

from core.detector_worker import DetectorWorker, iou
from core.advanced_tracker import AdvancedTracker

from logging_utils import get_logger

logger = get_logger(__name__)

class VisualizadorDetector(QObject):
    result_ready = pyqtSignal(list) 
    log_signal = pyqtSignal(str)

    def __init__(self, cam_data, parent=None):
        super().__init__(parent)
        self.cam_data = cam_data
        cam_ip_for_name = self.cam_data.get('ip', str(id(self))) 
        self.setObjectName(f"Visualizador_{cam_ip_for_name}")

        self.video_player = QMediaPlayer()
        self.video_sink = QVideoSink()
        self.video_player.setVideoSink(self.video_sink)

        self.video_sink.videoFrameChanged.connect(self.on_frame)
        self.video_player.errorOccurred.connect(
            lambda e: logger.error(
                "MediaPlayer error (%s): %s", self.objectName(), self.video_player.errorString()
            )
        )

        # Configuración de FPS mejorada
        fps_config = cam_data.get("fps_config", {})
        self.visual_fps = fps_config.get("visual_fps", 25)
        self.detection_fps = fps_config.get("detection_fps", cam_data.get("detection_fps", 8))
        
        # Calcular intervalo de detección basado en FPS
        base_fps = 30  # Asumimos que el stream llega a ~30 FPS
        self.detector_frame_interval = max(1, int(base_fps / self.detection_fps))
        
        self.frame_counter = 0

        imgsz_default = cam_data.get("imgsz", 416)
        device = cam_data.get("device", "cpu")
        logger.debug("%s: Inicializando DetectorWorker en %s", self.objectName(), device)

        # Tracker compartido para todas las detecciones
        self.tracker = AdvancedTracker(
            conf_threshold=cam_data.get("confianza", 0.5),
            device=device,
            lost_ttl=cam_data.get("lost_ttl", 5),
        )
        self._pending_detections = {}
        self._last_frame = None
        self._current_frame_id = 0

        modelos = cam_data.get("modelos")
        if not modelos:
            modelo_single = cam_data.get("modelo", "Personas")
            modelos = [modelo_single] if modelo_single else []

        self.detectors = []
        for m in modelos:
            detector = DetectorWorker(
                model_key=m,
                confidence=cam_data.get("confianza", 0.5),
                frame_interval=1,
                imgsz=imgsz_default,
                device=device,
                track=False,
            )
            detector.result_ready.connect(
                lambda res, _mk, fid, mk=m: self._procesar_resultados_detector_worker(res, mk, fid)
            )
            detector.start()
            self.detectors.append(detector)
        logger.debug("%s: %d DetectorWorker(s) started", self.objectName(), len(self.detectors))

    def update_fps_config(self, visual_fps=25, detection_fps=8):
        """Actualizar configuración de FPS en tiempo real"""
        self.visual_fps = visual_fps
        self.detection_fps = detection_fps
        
        base_fps = 30
        self.detector_frame_interval = max(1, int(base_fps / detection_fps))
        
        logger.info("%s: FPS actualizado - Visual: %d, Detección: %d (intervalo: %d)", 
                   self.objectName(), visual_fps, detection_fps, self.detector_frame_interval)

    def _procesar_resultados_detector_worker(self, output_for_signal, model_key, frame_id):
        logger.debug(
            "%s: _procesar_resultados_detector_worker received results for model %s",
            self.objectName(),
            model_key,
        )
        if frame_id != self._current_frame_id:
            logger.debug(
                "%s: Ignoring results for old frame %s (current %s)",
                self.objectName(),
                frame_id,
                self._current_frame_id,
            )
            return

        self._pending_detections[model_key] = output_for_signal
        if len(self._pending_detections) == len(self.detectors):
            merged = []
            for dets in self._pending_detections.values():
                for det in dets:
                    duplicate = False
                    for mdet in merged:
                        # Merge if boxes overlap significantly regardless of class
                        if iou(det['bbox'], mdet['bbox']) > 0.5:
                            if det.get('conf', 0) > mdet.get('conf', 0):
                                mdet.update(det)
                            duplicate = True
                            break
                    if not duplicate:
                        merged.append(det.copy())

            tracks = self.tracker.update(merged, frame=self._last_frame)
            self.result_ready.emit(tracks)
            self._pending_detections = {}

    def iniciar(self):
        rtsp_url = self.cam_data.get("rtsp")
        if rtsp_url:
            logger.info("%s: Reproduciendo RTSP %s", self.objectName(), rtsp_url)
            self.log_signal.emit(f"🎥 [{self.objectName()}] Streaming iniciado: {rtsp_url}")
            self.video_player.setSource(QUrl(rtsp_url))
            self.video_player.play()
        else:
            logger.warning("%s: No se encontró URL RTSP para iniciar", self.objectName())
            self.log_signal.emit(f"⚠️ [{self.objectName()}] No se encontró URL RTSP.")

    def detener(self):
        logger.info("%s: Deteniendo VisualizadorDetector", self.objectName())
        if hasattr(self, 'detectors'):
            for det in self.detectors:
                if det:
                    logger.info("%s: Deteniendo %s", self.objectName(), det.objectName())
                    det.stop()
        if hasattr(self, 'video_player') and self.video_player:
            player_state = self.video_player.playbackState()
            if player_state != QMediaPlayer.PlaybackState.StoppedState:
                logger.info("%s: Deteniendo QMediaPlayer estado %s", self.objectName(), player_state)
                self.video_player.stop()
            logger.info("%s: Desvinculando salida de video del QMediaPlayer", self.objectName())
            self.video_player.setVideoSink(None)
            logger.info("%s: Agendando QMediaPlayer para deleteLater", self.objectName())
            self.video_player.deleteLater()
            self.video_player = None
        if hasattr(self, 'video_sink') and self.video_sink:
            self.video_sink = None
        logger.info("%s: VisualizadorDetector detenido", self.objectName())

    def on_frame(self, frame): # frame es QVideoFrame
        logger.debug(
            "%s: on_frame called %d (interval %d)",
            self.objectName(),
            self.frame_counter,
            self.detector_frame_interval,
        )
        if not frame.isValid():
            return

        handle_type = frame.handleType()
        logger.debug("%s: frame handle type %s", self.objectName(), handle_type)

        self.frame_counter += 1
        
        # Procesar frames para detección según la configuración de FPS
        if self.frame_counter % self.detector_frame_interval == 0:
            try:
                qimg = self._qimage_from_frame(frame)
                if qimg is None:
                    return
                if qimg.format() != QImage.Format.Format_RGB888:
                    img_converted = qimg.convertToFormat(QImage.Format.Format_RGB888)
                else:
                    img_converted = qimg

                buffer = img_converted.constBits()
                bytes_per_pixel = img_converted.depth() // 8
                buffer.setsize(img_converted.height() * img_converted.width() * bytes_per_pixel)

                arr = (
                    np.frombuffer(buffer, dtype=np.uint8)
                    .reshape((img_converted.height(), img_converted.width(), bytes_per_pixel))
                    .copy()
                )

                self._last_frame = arr
                self._pending_detections = {}
                self._current_frame_id += 1

                if hasattr(self, 'detectors'):
                    for det in self.detectors:
                        if det and det.isRunning():
                            det.set_frame(arr, self._current_frame_id)

            except Exception as e:
                logger.error("%s: error procesando frame en on_frame: %s", self.objectName(), e)

    def _qimage_from_frame(self, frame: QVideoFrame) -> QImage | None:
        if frame.map(QVideoFrame.MapMode.ReadOnly):
            try:
                pf = frame.pixelFormat()
                rgb_formats = {
                    getattr(QVideoFrameFormat.PixelFormat, name)
                    for name in [
                        "Format_RGB24",
                        "Format_RGB32",
                        "Format_BGR24",
                        "Format_BGR32",
                        "Format_RGBX8888",
                        "Format_RGBA8888",
                        "Format_BGRX8888",
                        "Format_BGRA8888",
                        "Format_ARGB32",
                    ]
                    if hasattr(QVideoFrameFormat.PixelFormat, name)
                }
                if pf in rgb_formats:
                    img_format = QVideoFrameFormat.imageFormatFromPixelFormat(pf)
                    if img_format != QImage.Format.Format_Invalid:
                        return QImage(
                            frame.bits(),
                            frame.width(),
                            frame.height(),
                            frame.bytesPerLine(),
                            img_format,
                        ).copy()
            finally:
                frame.unmap()
        image = frame.toImage()
        return image if not image.isNull() else None