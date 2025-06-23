from PyQt6.QtCore import QThread, pyqtSignal, QUrl
from PyQt6.QtMultimedia import QMediaPlayer, QVideoSink, QVideoFrame, QVideoFrameFormat
from PyQt6.QtGui import QImage
from urllib.parse import quote
import numpy as np

class CamaraSecundariaWorker(QThread):
    frame_ready = pyqtSignal(object)
    log_signal = pyqtSignal(str)

    def __init__(self, cam_data, parent=None):
        super().__init__(parent)
        self.cam_data = cam_data
        self.video_player = None
        self.video_sink = None

    def run(self):
        ip = self.cam_data['ip']
        usuario = self.cam_data['usuario']
        contrasena = quote(self.cam_data['contrasena'])
        puerto = 554
        tipo = self.cam_data.get("tipo", "fija")
        canal = self.cam_data.get("canal", "2")
        perfil = self.cam_data.get("resolucion", "main").lower()

        if tipo == "nvr":
            perfil_id = {
                "main": "s0",
                "sub": "s1",
                "low": "s2",
                "more low": "s3",
            }.get(perfil, "s1")
            rtsp_url = f"rtsp://{usuario}:{contrasena}@{ip}:{puerto}/unicast/c{canal}/{perfil_id}/live"
        else:
            video_n = {
                "main": "video1",
                "sub": "video2",
                "low": "video3",
                "more low": "video4",
            }.get(perfil, "video1")
            rtsp_url = f"rtsp://{usuario}:{contrasena}@{ip}:{puerto}/media/{video_n}"

        self.log_signal.emit(f"🎬 Cámara secundaria conectando a: {rtsp_url}")

        self.video_player = QMediaPlayer()
        self.video_sink = QVideoSink()
        self.video_player.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self.on_frame)

        self.video_player.setSource(QUrl(rtsp_url))
        self.video_player.play()

        self.exec()

        if self.video_player:
            try:
                self.video_sink.videoFrameChanged.disconnect(self.on_frame)
            except Exception:
                pass
            self.video_player.stop()
            self.video_player.setVideoSink(None)
            self.video_player.deleteLater()
            self.video_player = None
            self.video_sink = None
        self.log_signal.emit("🛑 Cámara secundaria detenida")

    def stop(self):
        if self.video_player:
            self.video_player.stop()
        self.quit()
        self.wait()

    def on_frame(self, frame: QVideoFrame):
        if not frame.isValid():
            return
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
        self.frame_ready.emit(arr)

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