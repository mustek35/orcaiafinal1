import cv2
import numpy as np
from datetime import datetime

class MotionDetector:
    def __init__(self, min_area=500):
        """
        Inicializa el detector de movimiento.

        Args:
            min_area (int): Área mínima para considerar un contorno como movimiento válido.
        """
        self.previous_frame = None
        self.min_area = min_area

    def detect(self, frame):
        """
        Detecta movimiento en el frame comparado con el anterior.

        Args:
            frame (ndarray): Frame actual del video (BGR).

        Returns:
            list[dict]: Lista de bounding boxes detectados con timestamp y área.
        """
        motion_boxes = []

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        if self.previous_frame is None:
            self.previous_frame = gray
            return motion_boxes

        frame_diff = cv2.absdiff(self.previous_frame, gray)
        self.previous_frame = gray

        _, thresh = cv2.threshold(frame_diff, 25, 255, cv2.THRESH_BINARY)
        dilated = cv2.dilate(thresh, None, iterations=2)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < self.min_area:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            motion_boxes.append({
                "timestamp": datetime.utcnow().isoformat(),
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "area": int(area)
            })

        return motion_boxes
