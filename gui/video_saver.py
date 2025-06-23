from PyQt6.QtCore import QThread
import cv2
import os

class VideoSaverThread(QThread):
    def __init__(self, frames, output_path, fps=10, parent=None):
        super().__init__(parent)
        self.frames = frames
        self.output_path = output_path
        self.fps = fps

    def run(self):
        if not self.frames:
            return
        h, w = self.frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(self.output_path, fourcc, self.fps, (w, h))
        for frame in self.frames:
            if frame.shape[0] != h or frame.shape[1] != w:
                frame = cv2.resize(frame, (w, h))
            writer.write(frame)
        writer.release()