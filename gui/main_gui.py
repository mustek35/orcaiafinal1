# main_gui.py

import sys
from PyQt6.QtWidgets import QApplication
from gui.components import MainGUI  # Asegúrate que el archivo 'components.py' esté en la carpeta gui/

if __name__ == "__main__":
    app = QApplication(sys.argv)
    gui = MainGUI()
    gui.show()
    sys.exit(app.exec_())
    self.cam_config = {}  # Para guardar IP, usuario, pass, tipo
