from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QPushButton,
    QGroupBox, QCheckBox, QDialogButtonBox, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal

class FPSConfigDialog(QDialog):
    fps_config_changed = pyqtSignal(dict)
    
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Configuración de FPS")
        self.setMinimumSize(500, 450)
        
        # Configuración actual o por defecto
        if current_config is None:
            current_config = {
                "visual_fps": 25,
                "detection_fps": 8,
                "ui_update_fps": 15,
                "adaptive_fps": True
            }
        
        self.config = current_config.copy()
        
        layout = QVBoxLayout()
        
        # Grupo de FPS Visual
        visual_group = QGroupBox("🎥 FPS de Visualización")
        visual_layout = QVBoxLayout()
        
        self.visual_fps_label = QLabel(f"FPS Visual: {self.config['visual_fps']}")
        self.visual_fps_slider = QSlider(Qt.Orientation.Horizontal)
        self.visual_fps_slider.setRange(5, 60)
        self.visual_fps_slider.setValue(self.config['visual_fps'])
        self.visual_fps_slider.valueChanged.connect(self.update_visual_fps)
        
        visual_desc = QLabel("Controla la fluidez del video. Más alto = más fluido, más CPU.")
        visual_desc.setStyleSheet("color: gray; font-size: 11px;")
        
        visual_layout.addWidget(self.visual_fps_label)
        visual_layout.addWidget(self.visual_fps_slider)
        visual_layout.addWidget(visual_desc)
        visual_group.setLayout(visual_layout)
        
        # Grupo de FPS de Detección
        detection_group = QGroupBox("🤖 FPS de Detección IA")
        detection_layout = QVBoxLayout()
        
        self.detection_fps_label = QLabel(f"FPS Detección: {self.config['detection_fps']}")
        self.detection_fps_slider = QSlider(Qt.Orientation.Horizontal)
        self.detection_fps_slider.setRange(1, 30)
        self.detection_fps_slider.setValue(self.config['detection_fps'])
        self.detection_fps_slider.valueChanged.connect(self.update_detection_fps)
        
        detection_desc = QLabel("Frecuencia de análisis IA. Más bajo = menos CPU, detección más lenta.")
        detection_desc.setStyleSheet("color: gray; font-size: 11px;")
        
        detection_layout.addWidget(self.detection_fps_label)
        detection_layout.addWidget(self.detection_fps_slider)
        detection_layout.addWidget(detection_desc)
        detection_group.setLayout(detection_layout)
        
        # Grupo de FPS de UI
        ui_group = QGroupBox("🖼️ FPS de Interfaz")
        ui_layout = QVBoxLayout()
        
        self.ui_fps_label = QLabel(f"FPS UI: {self.config['ui_update_fps']}")
        self.ui_fps_slider = QSlider(Qt.Orientation.Horizontal)
        self.ui_fps_slider.setRange(5, 30)
        self.ui_fps_slider.setValue(self.config['ui_update_fps'])
        self.ui_fps_slider.valueChanged.connect(self.update_ui_fps)
        
        ui_desc = QLabel("Actualización de la interfaz. Balance entre responsividad y rendimiento.")
        ui_desc.setStyleSheet("color: gray; font-size: 11px;")
        
        ui_layout.addWidget(self.ui_fps_label)
        ui_layout.addWidget(self.ui_fps_slider)
        ui_layout.addWidget(ui_desc)
        ui_group.setLayout(ui_layout)
        
        # Opciones adicionales
        options_group = QGroupBox("⚙️ Opciones Avanzadas")
        options_layout = QVBoxLayout()
        
        self.adaptive_fps_check = QCheckBox("FPS Adaptativo (ajusta automáticamente según rendimiento)")
        self.adaptive_fps_check.setChecked(self.config.get('adaptive_fps', True))
        
        options_layout.addWidget(self.adaptive_fps_check)
        options_group.setLayout(options_layout)
        
        # Botones preestablecidos
        presets_group = QGroupBox("🚀 Configuraciones Preestablecidas")
        presets_layout = QHBoxLayout()
        
        smooth_btn = QPushButton("Fluido\n(30/10/20)")
        smooth_btn.clicked.connect(lambda: self.apply_preset(30, 10, 20))
        smooth_btn.setToolTip("Máxima fluidez para hardware potente")
        
        balanced_btn = QPushButton("Balanceado\n(25/8/15)")
        balanced_btn.clicked.connect(lambda: self.apply_preset(25, 8, 15))
        balanced_btn.setToolTip("Balance ideal entre rendimiento y calidad")
        
        performance_btn = QPushButton("Rendimiento\n(20/5/12)")
        performance_btn.clicked.connect(lambda: self.apply_preset(20, 5, 12))
        performance_btn.setToolTip("Optimizado para hardware limitado")
        
        eco_btn = QPushButton("Eco\n(15/3/10)")
        eco_btn.clicked.connect(lambda: self.apply_preset(15, 3, 10))
        eco_btn.setToolTip("Mínimo consumo de recursos")
        
        presets_layout.addWidget(smooth_btn)
        presets_layout.addWidget(balanced_btn)
        presets_layout.addWidget(performance_btn)
        presets_layout.addWidget(eco_btn)
        presets_group.setLayout(presets_layout)
        
        # Información y estadísticas en tiempo real
        stats_group = QGroupBox("📊 Información")
        stats_layout = QVBoxLayout()
        
        self.stats_text = QTextEdit()
        self.stats_text.setMaximumHeight(80)
        self.stats_text.setReadOnly(True)
        self.update_stats_display()
        
        stats_layout.addWidget(self.stats_text)
        stats_group.setLayout(stats_layout)
        
        # Botones del diálogo
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        buttons.accepted.connect(self.accept_and_apply)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self.apply_config)
        
        # Agregar todo al layout
        layout.addWidget(visual_group)
        layout.addWidget(detection_group)
        layout.addWidget(ui_group)
        layout.addWidget(options_group)
        layout.addWidget(presets_group)
        layout.addWidget(stats_group)
        layout.addWidget(buttons)
        
        self.setLayout(layout)
    
    def update_visual_fps(self, value):
        self.config['visual_fps'] = value
        self.visual_fps_label.setText(f"FPS Visual: {value}")
        self.update_stats_display()
    
    def update_detection_fps(self, value):
        self.config['detection_fps'] = value
        self.detection_fps_label.setText(f"FPS Detección: {value}")
        self.update_stats_display()
    
    def update_ui_fps(self, value):
        self.config['ui_update_fps'] = value
        self.ui_fps_label.setText(f"FPS UI: {value}")
        self.update_stats_display()
    
    def update_stats_display(self):
        visual = self.config['visual_fps']
        detection = self.config['detection_fps']
        ui = self.config['ui_update_fps']
        
        # Calcular intervalos
        visual_interval = max(1, int(30 / visual))
        detection_interval = max(1, int(30 / detection))
        ui_interval = int(1000 / ui)
        
        # Estimar carga de CPU (simplificado)
        cpu_load = min(100, (visual * 0.8 + detection * 2.5 + ui * 0.3))
        
        stats_text = f"""
💻 Carga estimada de CPU: {cpu_load:.0f}%
🔄 Intervalos calculados:
   • Visual: procesa 1 de cada {visual_interval} frames
   • Detección: procesa 1 de cada {detection_interval} frames  
   • UI: actualiza cada {ui_interval}ms
        """
        
        self.stats_text.setPlainText(stats_text.strip())
    
    def apply_preset(self, visual, detection, ui):
        self.visual_fps_slider.setValue(visual)
        self.detection_fps_slider.setValue(detection)
        self.ui_fps_slider.setValue(ui)
    
    def get_config(self):
        self.config['adaptive_fps'] = self.adaptive_fps_check.isChecked()
        return self.config.copy()
    
    def apply_config(self):
        config = self.get_config()
        self.fps_config_changed.emit(config)
    
    def accept_and_apply(self):
        self.apply_config()
        self.accept()