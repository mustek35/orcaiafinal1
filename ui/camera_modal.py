from PyQt6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QComboBox, QPushButton, QDialogButtonBox

class CameraDialog(QDialog):
    def __init__(self, parent=None, existing_data=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar/Editar Cámara")
        self.setMinimumSize(300, 200)

        self.layout = QVBoxLayout()
        self.form_layout = QFormLayout()

        self.ip_input = QLineEdit()
        self.usuario_input = QLineEdit()
        self.contrasena_input = QLineEdit()
        self.tipo_input = QComboBox()
        self.tipo_input.addItems(["fija", "ptz", "nvr"])

        self.form_layout.addRow("IP:", self.ip_input)
        self.form_layout.addRow("Usuario:", self.usuario_input)
        self.form_layout.addRow("Contraseña:", self.contrasena_input)
        self.form_layout.addRow("Tipo:", self.tipo_input)

        self.layout.addLayout(self.form_layout)

        self.button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addWidget(self.button_box)

        self.setLayout(self.layout)

        if existing_data:
            self.ip_input.setText(existing_data.get("ip", ""))
            self.usuario_input.setText(existing_data.get("usuario", ""))
            self.contrasena_input.setText(existing_data.get("contrasena", ""))
            tipo = existing_data.get("tipo", "fija")
            index = self.tipo_input.findText(tipo)
            self.tipo_input.setCurrentIndex(index if index >= 0 else 0)

    def get_camera_data(self):
        return {
            "ip": self.ip_input.text(),
            "usuario": self.usuario_input.text(),
            "contrasena": self.contrasena_input.text(),
            "tipo": self.tipo_input.currentText()
        }
