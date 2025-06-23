from PyQt6.QtCore import QThread, pyqtSignal, QUrl
from PyQt6.QtMultimedia import QMediaPlayer

class CameraWorker(QThread):
    stream_ready = pyqtSignal(QMediaPlayer)

    def __init__(self, camera_data, video_widget, parent=None):
        super().__init__(parent)
        self.camera_data = camera_data
        self.video_widget = video_widget
        self.media_player = None

    def run(self):
        rtsp_url = self.build_rtsp_url()
        print(f"\U0001f4e1 [DEBUG] Iniciando stream: {rtsp_url}")

        self.media_player = QMediaPlayer()
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setSource(QUrl(rtsp_url))
        self.media_player.play()

        self.stream_ready.emit(self.media_player)

    def build_rtsp_url(self):
        ip = self.camera_data.get("ip")
        usuario = self.camera_data.get("usuario")
        contrasena = self.camera_data.get("contrasena").replace("@", "%40")
        canal = self.camera_data.get("canal")
        perfil = self.camera_data.get("perfil", "main").lower()
        tipo = self.camera_data.get("tipo", "fija")

        if tipo == "nvr":
            if perfil == "main":
                perfil_id = "s0"
            elif perfil == "sub":
                perfil_id = "s1"
            elif perfil == "low":
                perfil_id = "s3"
            elif perfil == "more low":
                perfil_id = "s4"
            else:
                perfil_id = "s1"
            return f"rtsp://{usuario}:{contrasena}@{ip}:554/unicast/c{canal}/{perfil_id}/live"
        else:
            return f"rtsp://{usuario}:{contrasena}@{ip}:554/Streaming/Channels/{canal}0{'' if perfil == 'main' else '2'}"
