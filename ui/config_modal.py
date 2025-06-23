from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QDialogButtonBox,
    QComboBox,
    QLabel,
    QSpinBox,
    QListWidget,
    QListWidgetItem,
    QAbstractItemView,
    QDoubleSpinBox,
)
from configuracion import ConfiguracionWidget
from PyQt6.QtCore import pyqtSignal, Qt

class ConfiguracionDialog(QDialog):
    iniciar_camara_secundaria = pyqtSignal(object)

    def __init__(self, parent=None, camera_list=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración del Sistema")
        self.setMinimumSize(400, 400)

        self.camera_list = camera_list or []
        self.selected_camera = None

        self.layout = QVBoxLayout()

        self.camera_selector = QComboBox()
        self.camera_selector.addItems([
            f"{cam.get('ip', 'IP desconocida')} - {cam.get('tipo', 'Tipo desconocido')}"
            for cam in self.camera_list
        ])
        self.camera_selector.currentIndexChanged.connect(self.update_camera_selection)
        self.layout.addWidget(QLabel("Seleccionar Cámara"))
        self.layout.addWidget(self.camera_selector)

        self.modelo_selector = QListWidget()
        self.modelo_selector.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        for m in ["Embarcaciones", "Personas", "Autos", "Barcos"]:
            item = QListWidgetItem(m)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.modelo_selector.addItem(item)
        self.modelo_selector.itemChanged.connect(self.limitar_modelos)
        self.layout.addWidget(QLabel("Modelos de detección (máx. 2)"))
        self.layout.addWidget(self.modelo_selector)

        self.conf_selector = QDoubleSpinBox()
        self.conf_selector.setRange(0.0, 1.0)
        self.conf_selector.setSingleStep(0.05)
        self.conf_selector.setDecimals(2)
        self.conf_selector.setValue(0.5)
        self.layout.addWidget(QLabel("Confianza mínima"))
        self.layout.addWidget(self.conf_selector)

        self.imgsz_selector = QComboBox()
        self.imgsz_selector.addItems(["640", "960", "1280", "1920"])
        self.layout.addWidget(QLabel("Resolución de análisis (imgsz)"))
        self.layout.addWidget(self.imgsz_selector)

        self.intervalo_label = QLabel("Intervalo de detección (frames)")
        self.intervalo_input = QSpinBox()
        self.intervalo_input.setRange(1, 500)
        self.intervalo_input.setValue(80)
        self.layout.addWidget(self.intervalo_label)
        self.layout.addWidget(self.intervalo_input)

        self.config_widget = ConfiguracionWidget()
        self.layout.addWidget(self.config_widget)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.guardar_button = self.buttons.addButton("Guardar", QDialogButtonBox.ButtonRole.ActionRole)
        self.buttons.accepted.connect(self.aceptar_configuracion)
        self.buttons.rejected.connect(self.reject)
        self.guardar_button.clicked.connect(self.guardar_cambios)
        self.layout.addWidget(self.buttons)

        self.setLayout(self.layout)

        if self.camera_list:
            self.camera_selector.setCurrentIndex(0)
            self.update_camera_selection()

    def update_camera_selection(self):
        idx = self.camera_selector.currentIndex()
        if idx >= 0:
            self.selected_camera = self.camera_list[idx]

            modelos = self.selected_camera.get("modelos")
            if not modelos:
                modelo = self.selected_camera.get("modelo")
                modelos = [modelo] if modelo else []

            conf = float(self.selected_camera.get("confianza", 0.5))
            imgsz = str(self.selected_camera.get("imgsz", 640))
            intervalo = int(self.selected_camera.get("intervalo", 80))

            for i in range(self.modelo_selector.count()):
                item = self.modelo_selector.item(i)
                item.setCheckState(Qt.CheckState.Checked if item.text() in modelos else Qt.CheckState.Unchecked)

            self.conf_selector.setValue(conf)
            imgsz_idx = self.imgsz_selector.findText(imgsz)
            self.imgsz_selector.setCurrentIndex(imgsz_idx if imgsz_idx >= 0 else 0)
            self.intervalo_input.setValue(intervalo)

            self.config_widget.combo_res.setCurrentText(self.selected_camera.get("resolucion", "main"))
            self.config_widget.score_slider.setValue(int(self.selected_camera.get("umbral", 0.5) * 100))
            self.config_widget.save_checkbox.setChecked(self.selected_camera.get("guardar_capturas", False))
            self.config_widget.centinela_checkbox.setChecked(self.selected_camera.get("modo_centinela", False))

    def obtener_config(self):
        if self.selected_camera is not None:
            modelos = [
                self.modelo_selector.item(i).text()
                for i in range(self.modelo_selector.count())
                if self.modelo_selector.item(i).checkState() == Qt.CheckState.Checked
            ]
            self.selected_camera["modelos"] = modelos
            self.selected_camera["modelo"] = modelos[0] if modelos else ""
            self.selected_camera["confianza"] = float(self.conf_selector.value())
            self.selected_camera["intervalo"] = self.intervalo_input.value()
            self.selected_camera["imgsz"] = int(self.imgsz_selector.currentText())

            config = self.config_widget.obtener_config()
            self.selected_camera.update(config)

            return {
                "camara": self.selected_camera,
                "configuracion": config
            }

    def aceptar_configuracion(self):
        result = self.obtener_config()
        self.iniciar_camara_secundaria.emit(result["camara"])
        self.accept()

    def guardar_cambios(self):
        result = self.obtener_config()
        if self.parent() and hasattr(self.parent(), "restart_all_cameras"):
            self.parent().restart_all_cameras()
        self.accept()

    def limitar_modelos(self, item):
        seleccionados = [
            self.modelo_selector.item(i)
            for i in range(self.modelo_selector.count())
            if self.modelo_selector.item(i).checkState() == Qt.CheckState.Checked
        ]
        if len(seleccionados) > 2:
            item.setCheckState(Qt.CheckState.Unchecked)