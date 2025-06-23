from PyQt6.QtCore import QThread, pyqtSignal
import os

class ImageLoaderThread(QThread):
    images_loaded = pyqtSignal(list)

    def run(self):
        base_dir = os.path.join("capturas")
        imagenes_recientes = []

        if os.path.exists(base_dir):
            for categoria in os.listdir(base_dir):
                categoria_dir = os.path.join(base_dir, categoria)
                if os.path.isdir(categoria_dir):
                    archivos = sorted(os.listdir(categoria_dir), reverse=True)[:10]
                    for archivo in archivos:
                        ruta = os.path.join(categoria_dir, archivo)
                        imagenes_recientes.append(ruta)

        self.images_loaded.emit(imagenes_recientes)
