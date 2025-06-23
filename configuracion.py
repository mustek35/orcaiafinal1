import json
import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QSlider, QCheckBox
from PyQt6.QtCore import Qt

CONFIG_PATH = "config.json"

class ConfiguracionWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.combo_res = QComboBox()
        self.combo_res.addItems(["main", "sub", "low", "more low"])

        self.score_slider = QSlider(Qt.Orientation.Horizontal)
        self.score_slider.setRange(0, 100)
        self.score_slider.setValue(50)

        self.save_checkbox = QCheckBox("Guardar capturas")
        self.centinela_checkbox = QCheckBox("Activar modo centinela")

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Resolución de Stream"))
        layout.addWidget(self.combo_res)
        layout.addWidget(QLabel("Umbral de detección"))
        layout.addWidget(self.score_slider)
        layout.addWidget(self.save_checkbox)
        layout.addWidget(self.centinela_checkbox)
        self.setLayout(layout)

        self.cargar_configuracion()

    def obtener_config(self):
        return {
            "resolucion": self.combo_res.currentText(),
            "umbral": self.score_slider.value() / 100.0,
            "guardar_capturas": self.save_checkbox.isChecked(),
            "modo_centinela": self.centinela_checkbox.isChecked()
        }

    def cargar_configuracion(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                datos = json.load(f)
                config = datos.get("configuracion", {})
                self.combo_res.setCurrentText(config.get("resolucion", "main"))
                self.score_slider.setValue(int(config.get("umbral", 0.5) * 100))
                self.save_checkbox.setChecked(config.get("guardar_capturas", False))
                self.centinela_checkbox.setChecked(config.get("modo_centinela", False))

    def guardar_configuracion(self, datos):
        full_data = {}
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                full_data = json.load(f)
        full_data["configuracion"] = datos
        with open(CONFIG_PATH, "w") as f:
            json.dump(full_data, f, indent=4)
