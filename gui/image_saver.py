from PyQt6.QtCore import QThread
import os
import uuid
import cv2
import json
from datetime import datetime

class ImageSaverThread(QThread):
    MIN_CROP_WIDTH = 300
    MIN_CROP_HEIGHT = 300

    def __init__(self, frame, bbox, cls, coordenadas, modelo, confianza, parent=None):
        super().__init__(parent)
        self.frame = frame
        self.bbox = bbox 
        self.cls = cls
        self.coordenadas = coordenadas 
        self.modelo = modelo
        self.confianza = confianza

    def run(self):
        if self.frame is None or self.bbox is None:
            print("ImageSaverThread: Frame or bbox is None, returning.")
            return

        padding_percentage = 0.15 

        original_x1, original_y1, original_x2, original_y2 = map(int, self.bbox)
        
        if original_x1 >= original_x2 or original_y1 >= original_y2:
            print(f"ImageSaverThread: Original bbox coordinates are invalid: {self.bbox}, returning.")
            return

        bbox_width = original_x2 - original_x1
        bbox_height = original_y2 - original_y1

        padding_w = int(bbox_width * padding_percentage)
        padding_h = int(bbox_height * padding_percentage)

        padded_x1 = original_x1 - padding_w
        padded_y1 = original_y1 - padding_h
        padded_x2 = original_x2 + padding_w
        padded_y2 = original_y2 + padding_h

        frame_h, frame_w, _ = self.frame.shape

        final_x1 = max(0, padded_x1)
        final_y1 = max(0, padded_y1)
        final_x2 = min(frame_w, padded_x2)
        final_y2 = min(frame_h, padded_y2)

        # --- Lógica de Tamaño Mínimo ---
        current_padded_width = final_x2 - final_x1
        current_padded_height = final_y2 - final_y1

        # Ajuste de Ancho
        if current_padded_width < self.MIN_CROP_WIDTH:
            needed_expansion_w = self.MIN_CROP_WIDTH - current_padded_width
            expand_left = needed_expansion_w // 2
            expand_right = needed_expansion_w - expand_left

            new_x1_candidate = final_x1 - expand_left
            new_x2_candidate = final_x2 + expand_right

            if new_x1_candidate < 0:
                new_x2_candidate = min(frame_w, new_x2_candidate - new_x1_candidate) 
                new_x1_candidate = 0
            if new_x2_candidate > frame_w:
                new_x1_candidate = max(0, new_x1_candidate - (new_x2_candidate - frame_w))
                new_x2_candidate = frame_w
            
            final_x1 = new_x1_candidate
            final_x2 = new_x2_candidate
            
            current_padded_width = final_x2 - final_x1 # Recalcular
            if current_padded_width < self.MIN_CROP_WIDTH: # Intentar expansión unilateral si aún es pequeño
                if final_x1 == 0 and final_x2 < frame_w: 
                    final_x2 = min(frame_w, final_x1 + self.MIN_CROP_WIDTH)
                elif final_x2 == frame_w and final_x1 > 0: 
                    final_x1 = max(0, final_x2 - self.MIN_CROP_WIDTH)
        
        # Ajuste de Alto
        current_padded_height = final_y2 - final_y1 # Recalcular por si el ajuste de ancho cambió algo (no debería)
        if current_padded_height < self.MIN_CROP_HEIGHT:
            needed_expansion_h = self.MIN_CROP_HEIGHT - current_padded_height
            expand_top = needed_expansion_h // 2
            expand_bottom = needed_expansion_h - expand_top

            new_y1_candidate = final_y1 - expand_top
            new_y2_candidate = final_y2 + expand_bottom

            if new_y1_candidate < 0:
                new_y2_candidate = min(frame_h, new_y2_candidate - new_y1_candidate)
                new_y1_candidate = 0
            if new_y2_candidate > frame_h:
                new_y1_candidate = max(0, new_y1_candidate - (new_y2_candidate - frame_h))
                new_y2_candidate = frame_h
            
            final_y1 = new_y1_candidate
            final_y2 = new_y2_candidate

            current_padded_height = final_y2 - final_y1 # Recalcular
            if current_padded_height < self.MIN_CROP_HEIGHT: # Intentar expansión unilateral
                if final_y1 == 0 and final_y2 < frame_h:
                    final_y2 = min(frame_h, final_y1 + self.MIN_CROP_HEIGHT)
                elif final_y2 == frame_h and final_y1 > 0:
                    final_y1 = max(0, final_y2 - self.MIN_CROP_HEIGHT)
        # --- Fin Lógica de Tamaño Mínimo ---

        if final_y1 >= final_y2 or final_x1 >= final_x2:
            print(f"ImageSaverThread: Coordenadas finales inválidas después del ajuste de tamaño mínimo ({final_x1},{final_y1},{final_x2},{final_y2}). Usando BBox original.")
            final_x1 = max(0, original_x1)
            final_y1 = max(0, original_y1)
            final_x2 = min(frame_w, original_x2)
            final_y2 = min(frame_h, original_y2)
            if final_y1 >= final_y2 or final_x1 >= final_x2:
                 print(f"ImageSaverThread: BBox original de fallback también inválido ({final_x1},{final_y1},{final_x2},{final_y2}), returning.")
                 return

        crop = self.frame[final_y1:final_y2, final_x1:final_x2]
        if crop.size == 0:
            print("ImageSaverThread: Crop size is 0, returning.")
            return

        rect_x1_on_crop = original_x1 - final_x1
        rect_y1_on_crop = original_y1 - final_y1
        rect_x2_on_crop = original_x2 - final_x1 
        rect_y2_on_crop = original_y2 - final_y1
        
        crop_h, crop_w, _ = crop.shape
        rect_x1_on_crop = max(0, rect_x1_on_crop)
        rect_y1_on_crop = max(0, rect_y1_on_crop)
        rect_x2_on_crop = min(crop_w, rect_x2_on_crop) 
        rect_y2_on_crop = min(crop_h, rect_y2_on_crop) 

        if rect_x1_on_crop < rect_x2_on_crop and rect_y1_on_crop < rect_y2_on_crop:
            cv2.rectangle(crop, (rect_x1_on_crop, rect_y1_on_crop), (rect_x2_on_crop, rect_y2_on_crop), (0, 255, 0), 2)
        else:
            print(f"ImageSaverThread: Coordenadas inválidas para dibujar rectángulo en crop: ({rect_x1_on_crop},{rect_y1_on_crop}) to ({rect_x2_on_crop},{rect_y2_on_crop}). Crop shape: {crop.shape}")

        if self.cls == 0 and self.modelo == "Embarcaciones":
            carpeta_base = "embarcaciones"
        elif self.cls == 0: 
            carpeta_base = "personas"
        elif self.cls == 2:
            carpeta_base = "autos"
        elif self.cls == 8:
            carpeta_base = "barcos"
        else:
            carpeta_base = "otros"

        now = datetime.now()
        fecha = now.strftime("%Y-%m-%d")
        hora = now.strftime("%H-%M-%S")
        ruta = os.path.join("capturas", carpeta_base, fecha)
        os.makedirs(ruta, exist_ok=True)
        nombre = f"{fecha}_{hora}_{uuid.uuid4().hex[:6]}"
        path_final = os.path.join(ruta, f"{nombre}.jpg")
        
        try:
            cv2.imwrite(path_final, crop)
        except Exception as e:
            print(f"ImageSaverThread: Error guardando imagen {path_final}: {e}")
            return 
        metadata = {
            "fecha": fecha, "hora": hora.replace("-", ":"), "modelo": self.modelo,
            "coordenadas_frame_original": self.bbox, 
            "coordenadas_padding_aplicado": (final_x1, final_y1, final_x2, final_y2), 
            "coordenadas_ptz": self.coordenadas, 
            "confianza": self.confianza
        }
        try:
            with open(os.path.join(ruta, f"{nombre}.json"), "w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"ImageSaverThread: Error guardando metadata para {path_final}: {e}")
