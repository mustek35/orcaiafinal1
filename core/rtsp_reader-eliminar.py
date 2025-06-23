import cv2
import time

class RTSPReader:
    def __init__(self, rtsp_url, target_width=320, target_height=180, skip_frames=15):
        """
        Inicializa el lector de RTSP.

        Args:
            rtsp_url (str): URL del stream RTSP.
            target_width (int): Ancho al que se redimensionará el frame.
            target_height (int): Alto al que se redimensionará el frame.
            skip_frames (int): Número de frames que se omitirán entre lecturas.
        """
        self.rtsp_url = rtsp_url
        self.target_width = target_width
        self.target_height = target_height
        self.skip_frames = skip_frames
        self.cap = cv2.VideoCapture(rtsp_url)
        self.frame_count = 0

        if not self.cap.isOpened():
            raise RuntimeError(f"No se pudo abrir el stream RTSP: {rtsp_url}")

    def read(self):
        """
        Lee el siguiente frame válido según el salto configurado.

        Returns:
            frame (ndarray): Frame redimensionado o None si falló.
        """
        ret, frame = self.cap.read()
        if not ret:
            print("⚠️ Error al leer frame RTSP.")
            time.sleep(0.5)
            return None

        self.frame_count += 1
        if self.frame_count % self.skip_frames != 0:
            return None  # Saltar este frame

        resized = cv2.resize(frame, (self.target_width, self.target_height))
        return resized

    def release(self):
        """Libera el stream."""
        self.cap.release()
