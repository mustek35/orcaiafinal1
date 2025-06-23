import os
os.environ["FFREPORT"] = "file=ffreport.log:level=quiet"
os.environ["FFMPEG_LOGLEVEL"] = "panic"
os.environ["QT_LOGGING_RULES"] = "qt.multimedia.ffmpeg=false;qt.multimedia.playbackengine=false"
os.environ["QT_MEDIA_FFMPEG_LOGLEVEL"] = "fatal"

import cv2
# Establecer nivel de log en OpenCV si el módulo de logging está disponible:
if hasattr(cv2, "utils") and hasattr(cv2.utils, "logging"):
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from ui.main_window import MainGUI

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # Configurar la aplicación para mejor rendimiento
    try:
        app.setAttribute(Qt.ApplicationAttribute.AA_UseOpenGLES, True)
        app.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, False)
        print("✅ Optimizaciones OpenGL aplicadas")
    except Exception as e:
        print(f"⚠️ No se pudieron aplicar optimizaciones OpenGL: {e}")
    
    gui = MainGUI()
    gui.show()
    
    print("🚀 Monitor PTZ Inteligente - Orca iniciado")
    print("🎯 Configuración de FPS optimizada disponible en Configuración > Configurar FPS")
    print("📊 Configuraciones recomendadas:")
    print("   • Hardware potente: Visual=30, Detección=10, UI=20")
    print("   • Hardware moderado: Visual=25, Detección=8, UI=15")
    print("   • Hardware limitado: Visual=20, Detección=5, UI=12")
    
    sys.exit(app.exec())