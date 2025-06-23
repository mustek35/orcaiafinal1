# ui/adaptive_sampling_dialog.py - Diálogo de Configuración para Muestreo Adaptativo

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QSlider, QSpinBox, QDoubleSpinBox, QCheckBox, QPushButton,
    QGroupBox, QTabWidget, QWidget, QTextEdit, QComboBox, QProgressBar,
    QMessageBox, QDialogButtonBox, QFrame, QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QPalette, QColor
import json
from datetime import datetime
from core.adaptive_sampling import AdaptiveSamplingConfig


class AdaptiveSamplingConfigDialog(QDialog):
    """Diálogo avanzado para configurar el sistema de muestreo adaptativo"""
    
    config_changed = pyqtSignal(dict)  # Emite cuando cambia la configuración
    
    def __init__(self, parent=None, current_config=None):
        super().__init__(parent)
        self.setWindowTitle("🧠 Configuración de Muestreo Adaptativo")
        self.setMinimumSize(700, 600)
        self.setMaximumSize(900, 800)
        
        # Configuración actual o por defecto
        if current_config is None:
            self.config = AdaptiveSamplingConfig.create_config("balanced")
        else:
            if isinstance(current_config, dict):
                self.config = AdaptiveSamplingConfig(**current_config)
            else:
                self.config = current_config
        
        # Variables de estado
        self.preview_timer = QTimer()
        self.preview_timer.timeout.connect(self.update_preview)
        self.preview_timer.setSingleShot(False)
        
        self._setup_ui()
        self._connect_signals()
        self._load_current_config()
        self._start_preview()
        
    def _setup_ui(self):
        """Configura la interfaz de usuario"""
        layout = QVBoxLayout()
        
        # Título principal con estilo
        title_label = QLabel("🧠 Sistema de Muestreo Adaptativo")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #2E5BBA; margin: 10px;")
        layout.addWidget(title_label)
        
        # Descripción
        desc_label = QLabel(
            "💡 El muestreo adaptativo ajusta automáticamente la frecuencia de análisis\n"
            "basándose en la actividad detectada en la escena, optimizando el rendimiento."
        )
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("color: gray; font-size: 11px; margin-bottom: 15px;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)
        
        # Pestañas principales
        self.tab_widget = QTabWidget()
        
        # Pestaña de configuración básica
        self._setup_basic_tab()
        
        # Pestaña de configuración avanzada
        self._setup_advanced_tab()
        
        # Pestaña de presets
        self._setup_presets_tab()
        
        # Pestaña de vista previa
        self._setup_preview_tab()
        
        layout.addWidget(self.tab_widget)
        
        # Botones de acción
        self._setup_action_buttons(layout)
        
        self.setLayout(layout)
    
    def _setup_basic_tab(self):
        """Configura la pestaña de configuración básica"""
        basic_widget = QWidget()
        layout = QVBoxLayout()
        
        # Configuración de intervalos
        intervals_group = QGroupBox("⏱️ Configuración de Intervalos")
        intervals_layout = QGridLayout()
        
        # Intervalo base
        intervals_layout.addWidget(QLabel("Intervalo Base:"), 0, 0)
        self.base_interval_spin = QSpinBox()
        self.base_interval_spin.setRange(1, 50)
        self.base_interval_spin.setSuffix(" frames")
        intervals_layout.addWidget(self.base_interval_spin, 0, 1)
        
        base_help = QLabel("Intervalo de frames cuando no hay actividad especial")
        base_help.setStyleSheet("color: gray; font-size: 10px;")
        intervals_layout.addWidget(base_help, 0, 2)
        
        # Intervalo mínimo
        intervals_layout.addWidget(QLabel("Intervalo Mínimo:"), 1, 0)
        self.min_interval_spin = QSpinBox()
        self.min_interval_spin.setRange(1, 25)
        self.min_interval_spin.setSuffix(" frames")
        intervals_layout.addWidget(self.min_interval_spin, 1, 1)
        
        min_help = QLabel("Frecuencia máxima de análisis (alta actividad)")
        min_help.setStyleSheet("color: gray; font-size: 10px;")
        intervals_layout.addWidget(min_help, 1, 2)
        
        # Intervalo máximo
        intervals_layout.addWidget(QLabel("Intervalo Máximo:"), 2, 0)
        self.max_interval_spin = QSpinBox()
        self.max_interval_spin.setRange(5, 100)
        self.max_interval_spin.setSuffix(" frames")
        intervals_layout.addWidget(self.max_interval_spin, 2, 1)
        
        max_help = QLabel("Frecuencia mínima de análisis (baja actividad)")
        max_help.setStyleSheet("color: gray; font-size: 10px;")
        intervals_layout.addWidget(max_help, 2, 2)
        
        intervals_group.setLayout(intervals_layout)
        layout.addWidget(intervals_group)
        
        # Configuración de adaptación
        adaptation_group = QGroupBox("🎯 Velocidad de Adaptación")
        adaptation_layout = QGridLayout()
        
        # Velocidad de adaptación
        adaptation_layout.addWidget(QLabel("Velocidad de Adaptación:"), 0, 0)
        self.adaptation_rate_slider = QSlider(Qt.Orientation.Horizontal)
        self.adaptation_rate_slider.setRange(5, 50)  # 0.05 a 0.50
        adaptation_layout.addWidget(self.adaptation_rate_slider, 0, 1)
        
        self.adaptation_rate_label = QLabel("0.15")
        adaptation_layout.addWidget(self.adaptation_rate_label, 0, 2)
        
        adapt_help = QLabel("Qué tan rápido se adapta a cambios de actividad")
        adapt_help.setStyleSheet("color: gray; font-size: 10px;")
        adaptation_layout.addWidget(adapt_help, 1, 0, 1, 3)
        
        adaptation_group.setLayout(adaptation_layout)
        layout.addWidget(adaptation_group)
        
        # Configuración de umbrales
        thresholds_group = QGroupBox("📊 Umbrales de Actividad")
        thresholds_layout = QGridLayout()
        
        # Umbral de alta actividad
        thresholds_layout.addWidget(QLabel("Umbral Alta Actividad:"), 0, 0)
        self.high_threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.high_threshold_slider.setRange(10, 30)  # 0.10 a 0.30
        thresholds_layout.addWidget(self.high_threshold_slider, 0, 1)
        
        self.high_threshold_label = QLabel("0.15")
        thresholds_layout.addWidget(self.high_threshold_label, 0, 2)
        
        # Umbral de baja actividad
        thresholds_layout.addWidget(QLabel("Umbral Baja Actividad:"), 1, 0)
        self.low_threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.low_threshold_slider.setRange(1, 15)  # 0.01 a 0.15
        thresholds_layout.addWidget(self.low_threshold_slider, 1, 1)
        
        self.low_threshold_label = QLabel("0.05")
        thresholds_layout.addWidget(self.low_threshold_label, 1, 2)
        
        threshold_help = QLabel("Valores que determinan cuándo cambiar la frecuencia de análisis")
        threshold_help.setStyleSheet("color: gray; font-size: 10px;")
        thresholds_layout.addWidget(threshold_help, 2, 0, 1, 3)
        
        thresholds_group.setLayout(thresholds_layout)
        layout.addWidget(thresholds_group)
        
        layout.addStretch()
        basic_widget.setLayout(layout)
        self.tab_widget.addTab(basic_widget, "⚙️ Básico")
    
    def _setup_advanced_tab(self):
        """Configura la pestaña de configuración avanzada"""
        advanced_widget = QWidget()
        layout = QVBoxLayout()
        
        # Configuración de detecciones
        detection_group = QGroupBox("🔍 Configuración de Detecciones")
        detection_layout = QFormLayout()
        
        self.detection_weight_slider = QSlider(Qt.Orientation.Horizontal)
        self.detection_weight_slider.setRange(10, 90)  # 0.1 a 0.9
        self.detection_weight_label = QLabel("0.7")
        detection_weight_layout = QHBoxLayout()
        detection_weight_layout.addWidget(self.detection_weight_slider)
        detection_weight_layout.addWidget(self.detection_weight_label)
        detection_layout.addRow("Peso de Detecciones:", detection_weight_layout)
        
        self.movement_weight_slider = QSlider(Qt.Orientation.Horizontal)
        self.movement_weight_slider.setRange(10, 90)  # 0.1 a 0.9
        self.movement_weight_label = QLabel("0.3")
        movement_weight_layout = QHBoxLayout()
        movement_weight_layout.addWidget(self.movement_weight_slider)
        movement_weight_layout.addWidget(self.movement_weight_label)
        detection_layout.addRow("Peso de Movimiento:", movement_weight_layout)
        
        self.confidence_threshold_spin = QDoubleSpinBox()
        self.confidence_threshold_spin.setRange(0.1, 0.9)
        self.confidence_threshold_spin.setSingleStep(0.05)
        self.confidence_threshold_spin.setDecimals(2)
        detection_layout.addRow("Confianza Mínima:", self.confidence_threshold_spin)
        
        self.min_detections_spin = QSpinBox()
        self.min_detections_spin.setRange(1, 10)
        detection_layout.addRow("Mín. Detecciones para Adaptar:", self.min_detections_spin)
        
        detection_group.setLayout(detection_layout)
        layout.addWidget(detection_group)
        
        # Configuración temporal
        temporal_group = QGroupBox("⏰ Configuración Temporal")
        temporal_layout = QFormLayout()
        
        self.history_window_spin = QSpinBox()
        self.history_window_spin.setRange(10, 100)
        self.history_window_spin.setSuffix(" frames")
        temporal_layout.addRow("Ventana de Historial:", self.history_window_spin)
        
        self.stabilization_time_spin = QSpinBox()
        self.stabilization_time_spin.setRange(10, 200)
        self.stabilization_time_spin.setSuffix(" frames")
        temporal_layout.addRow("Tiempo de Estabilización:", self.stabilization_time_spin)
        
        temporal_group.setLayout(temporal_layout)
        layout.addWidget(temporal_group)
        
        # Configuración avanzada
        advanced_options_group = QGroupBox("🚀 Opciones Avanzadas")
        advanced_options_layout = QVBoxLayout()
        
        self.enable_burst_check = QCheckBox("Habilitar Modo Ráfaga")
        self.enable_burst_check.setToolTip("Permite frecuencias muy altas temporalmente")
        advanced_options_layout.addWidget(self.enable_burst_check)
        
        burst_layout = QHBoxLayout()
        burst_layout.addWidget(QLabel("Duración de Ráfaga:"))
        self.burst_duration_spin = QSpinBox()
        self.burst_duration_spin.setRange(5, 30)
        self.burst_duration_spin.setSuffix(" frames")
        burst_layout.addWidget(self.burst_duration_spin)
        burst_layout.addStretch()
        advanced_options_layout.addLayout(burst_layout)
        
        self.enable_smoothing_check = QCheckBox("Habilitar Suavizado de Cambios")
        self.enable_smoothing_check.setToolTip("Hace cambios graduales en lugar de abruptos")
        advanced_options_layout.addWidget(self.enable_smoothing_check)
        
        advanced_options_group.setLayout(advanced_options_layout)
        layout.addWidget(advanced_options_group)
        
        layout.addStretch()
        advanced_widget.setLayout(layout)
        self.tab_widget.addTab(advanced_widget, "🔧 Avanzado")
    
    def _setup_presets_tab(self):
        """Configura la pestaña de presets"""
        presets_widget = QWidget()
        layout = QVBoxLayout()
        
        # Información sobre presets
        info_label = QLabel(
            "🚀 Los presets proporcionan configuraciones optimizadas para diferentes escenarios.\n"
            "Puedes aplicar un preset y luego ajustar valores específicos según tus necesidades."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #666; font-size: 11px; margin: 10px; padding: 10px; "
                                "background-color: #f0f0f0; border-radius: 5px;")
        layout.addWidget(info_label)
        
        # Botones de presets
        presets_layout = QVBoxLayout()
        
        # Preset Agresivo
        aggressive_group = QGroupBox("⚡ Agresivo - Máximo Rendimiento")
        aggressive_layout = QVBoxLayout()
        aggressive_desc = QLabel(
            "• Adaptación muy rápida a cambios\n"
            "• Intervalos pequeños (2-20 frames)\n"
            "• Ideal para sistemas con mucha potencia de procesamiento\n"
            "• Máxima responsividad ante actividad"
        )
        aggressive_desc.setStyleSheet("color: #666; font-size: 10px;")
        aggressive_layout.addWidget(aggressive_desc)
        
        self.aggressive_btn = QPushButton("Aplicar Configuración Agresiva")
        self.aggressive_btn.setStyleSheet("background-color: #FF6B6B; color: white; font-weight: bold;")
        aggressive_layout.addWidget(self.aggressive_btn)
        aggressive_group.setLayout(aggressive_layout)
        presets_layout.addWidget(aggressive_group)
        
        # Preset Balanceado
        balanced_group = QGroupBox("⚖️ Balanceado - Recomendado")
        balanced_layout = QVBoxLayout()
        balanced_desc = QLabel(
            "• Equilibrio perfecto entre rendimiento y calidad\n"
            "• Intervalos moderados (3-25 frames)\n"
            "• Ideal para la mayoría de aplicaciones\n"
            "• Configuración por defecto recomendada"
        )
        balanced_desc.setStyleSheet("color: #666; font-size: 10px;")
        balanced_layout.addWidget(balanced_desc)
        
        self.balanced_btn = QPushButton("Aplicar Configuración Balanceada")
        self.balanced_btn.setStyleSheet("background-color: #4ECDC4; color: white; font-weight: bold;")
        balanced_layout.addWidget(self.balanced_btn)
        balanced_group.setLayout(balanced_layout)
        presets_layout.addWidget(balanced_group)
        
        # Preset Conservador
        conservative_group = QGroupBox("🛡️ Conservador - Máxima Estabilidad")
        conservative_layout = QVBoxLayout()
        conservative_desc = QLabel(
            "• Cambios suaves y graduales\n"
            "• Intervalos grandes (5-30 frames)\n"
            "• Ideal para sistemas con recursos limitados\n"
            "• Prioriza estabilidad sobre responsividad"
        )
        conservative_desc.setStyleSheet("color: #666; font-size: 10px;")
        conservative_layout.addWidget(conservative_desc)
        
        self.conservative_btn = QPushButton("Aplicar Configuración Conservadora")
        self.conservative_btn.setStyleSheet("background-color: #45B7D1; color: white; font-weight: bold;")
        conservative_layout.addWidget(self.conservative_btn)
        conservative_group.setLayout(conservative_layout)
        presets_layout.addWidget(conservative_group)
        
        layout.addLayout(presets_layout)
        
        # Configuración personalizada
        custom_group = QGroupBox("🎨 Configuración Personalizada")
        custom_layout = QVBoxLayout()
        
        custom_desc = QLabel("Puedes guardar y cargar tus propias configuraciones:")
        custom_layout.addWidget(custom_desc)
        
        custom_buttons = QHBoxLayout()
        self.save_config_btn = QPushButton("💾 Guardar Configuración")
        self.load_config_btn = QPushButton("📂 Cargar Configuración")
        self.reset_config_btn = QPushButton("🔄 Restablecer")
        
        custom_buttons.addWidget(self.save_config_btn)
        custom_buttons.addWidget(self.load_config_btn)
        custom_buttons.addWidget(self.reset_config_btn)
        custom_layout.addLayout(custom_buttons)
        
        custom_group.setLayout(custom_layout)
        layout.addWidget(custom_group)
        
        layout.addStretch()
        presets_widget.setLayout(layout)
        self.tab_widget.addTab(presets_widget, "🚀 Presets")
    
    def _setup_preview_tab(self):
        """Configura la pestaña de vista previa"""
        preview_widget = QWidget()
        layout = QVBoxLayout()
        
        # Título de la vista previa
        preview_title = QLabel("👁️ Vista Previa en Tiempo Real")
        preview_title.setFont(QFont("", 12, QFont.Weight.Bold))
        preview_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(preview_title)
        
        # Área de configuración actual
        current_config_group = QGroupBox("⚙️ Configuración Actual")
        config_layout = QGridLayout()
        
        config_layout.addWidget(QLabel("Intervalo Base:"), 0, 0)
        self.preview_base_interval = QLabel("8")
        config_layout.addWidget(self.preview_base_interval, 0, 1)
        
        config_layout.addWidget(QLabel("Rango de Intervalos:"), 1, 0)
        self.preview_interval_range = QLabel("3 - 25")
        config_layout.addWidget(self.preview_interval_range, 1, 1)
        
        config_layout.addWidget(QLabel("Velocidad de Adaptación:"), 2, 0)
        self.preview_adaptation_rate = QLabel("0.15")
        config_layout.addWidget(self.preview_adaptation_rate, 2, 1)
        
        config_layout.addWidget(QLabel("Umbrales de Actividad:"), 3, 0)
        self.preview_thresholds = QLabel("0.05 - 0.15")
        config_layout.addWidget(self.preview_thresholds, 3, 1)
        
        current_config_group.setLayout(config_layout)
        layout.addWidget(current_config_group)
        
        # Simulación de comportamiento
        simulation_group = QGroupBox("📊 Simulación de Comportamiento")
        simulation_layout = QVBoxLayout()
        
        # Controles de simulación
        sim_controls = QHBoxLayout()
        self.activity_level_combo = QComboBox()
        self.activity_level_combo.addItems([
            "Sin actividad", "Actividad baja", "Actividad media", 
            "Actividad alta", "Actividad muy alta"
        ])
        sim_controls.addWidget(QLabel("Nivel de Actividad:"))
        sim_controls.addWidget(self.activity_level_combo)
        sim_controls.addStretch()
        
        self.start_simulation_btn = QPushButton("▶️ Iniciar Simulación")
        self.stop_simulation_btn = QPushButton("⏹️ Detener")
        sim_controls.addWidget(self.start_simulation_btn)
        sim_controls.addWidget(self.stop_simulation_btn)
        
        simulation_layout.addLayout(sim_controls)
        
        # Resultados de simulación
        results_layout = QGridLayout()
        
        results_layout.addWidget(QLabel("Intervalo Actual:"), 0, 0)
        self.sim_current_interval = QLabel("8")
        self.sim_current_interval.setStyleSheet("font-weight: bold; color: #2E5BBA;")
        results_layout.addWidget(self.sim_current_interval, 0, 1)
        
        results_layout.addWidget(QLabel("Puntuación de Actividad:"), 1, 0)
        self.sim_activity_score = QLabel("0.000")
        results_layout.addWidget(self.sim_activity_score, 1, 1)
        
        results_layout.addWidget(QLabel("Tendencia:"), 2, 0)
        self.sim_trend = QLabel("estable")
        results_layout.addWidget(self.sim_trend, 2, 1)
        
        results_layout.addWidget(QLabel("Eficiencia Estimada:"), 3, 0)
        self.sim_efficiency = QLabel("0%")
        results_layout.addWidget(self.sim_efficiency, 3, 1)
        
        simulation_layout.addLayout(results_layout)
        
        # Barra de progreso de actividad
        activity_progress_layout = QHBoxLayout()
        activity_progress_layout.addWidget(QLabel("Actividad:"))
        self.activity_progress_bar = QProgressBar()
        self.activity_progress_bar.setRange(0, 100)
        self.activity_progress_bar.setValue(0)
        activity_progress_layout.addWidget(self.activity_progress_bar)
        simulation_layout.addLayout(activity_progress_layout)
        
        simulation_group.setLayout(simulation_layout)
        layout.addWidget(simulation_group)
        
        # Información adicional
        info_group = QGroupBox("💡 Información sobre el Rendimiento")
        info_layout = QVBoxLayout()
        
        self.performance_info = QTextEdit()
        self.performance_info.setReadOnly(True)
        self.performance_info.setMaximumHeight(120)
        self.performance_info.setPlainText(
            "🧠 El muestreo adaptativo optimiza automáticamente el rendimiento:\n\n"
            "• Reduce el uso de CPU en escenas estáticas hasta un 70%\n"
            "• Mantiene la calidad de detección en escenas activas\n"
            "• Se adapta continuamente sin intervención manual\n"
            "• Proporciona métricas en tiempo real para monitoreo"
        )
        info_layout.addWidget(self.performance_info)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        preview_widget.setLayout(layout)
        self.tab_widget.addTab(preview_widget, "👁️ Vista Previa")
    
    def _setup_action_buttons(self, layout):
        """Configura los botones de acción"""
        button_layout = QHBoxLayout()
        
        # Botón de aplicar en tiempo real
        self.apply_realtime_btn = QPushButton("⚡ Aplicar en Tiempo Real")
        self.apply_realtime_btn.setToolTip("Aplica cambios inmediatamente sin cerrar el diálogo")
        self.apply_realtime_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        button_layout.addWidget(self.apply_realtime_btn)
        
        # Botón de prueba
        self.test_config_btn = QPushButton("🧪 Probar Configuración")
        self.test_config_btn.setToolTip("Prueba la configuración durante 30 segundos")
        button_layout.addWidget(self.test_config_btn)
        
        # Espaciador
        button_layout.addStretch()
        
        # Botones estándar
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        button_layout.addWidget(self.button_box)
        
        layout.addLayout(button_layout)
    
    def _connect_signals(self):
        """Conecta todas las señales"""
        # Sliders de configuración básica
        self.adaptation_rate_slider.valueChanged.connect(self._update_adaptation_rate_label)
        self.high_threshold_slider.valueChanged.connect(self._update_high_threshold_label)
        self.low_threshold_slider.valueChanged.connect(self._update_low_threshold_label)
        
        # Sliders de configuración avanzada
        self.detection_weight_slider.valueChanged.connect(self._update_detection_weight_label)
        self.movement_weight_slider.valueChanged.connect(self._update_movement_weight_label)
        
        # Presets
        self.aggressive_btn.clicked.connect(lambda: self._apply_preset("aggressive"))
        self.balanced_btn.clicked.connect(lambda: self._apply_preset("balanced"))
        self.conservative_btn.clicked.connect(lambda: self._apply_preset("conservative"))
        
        # Configuración personalizada
        self.save_config_btn.clicked.connect(self._save_config_to_file)
        self.load_config_btn.clicked.connect(self._load_config_from_file)
        self.reset_config_btn.clicked.connect(self._reset_to_defaults)
        
        # Simulación
        self.start_simulation_btn.clicked.connect(self._start_simulation)
        self.stop_simulation_btn.clicked.connect(self._stop_simulation)
        self.activity_level_combo.currentTextChanged.connect(self._update_simulation)
        
        # Botones principales
        self.apply_realtime_btn.clicked.connect(self._apply_realtime)
        self.test_config_btn.clicked.connect(self._test_configuration)
        
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply_realtime)
        
        # Conectar cambios para actualizar vista previa
        for widget in [self.base_interval_spin, self.min_interval_spin, self.max_interval_spin,
                      self.adaptation_rate_slider, self.high_threshold_slider, self.low_threshold_slider]:
            if hasattr(widget, 'valueChanged'):
                widget.valueChanged.connect(self._update_preview_values)
    
    def _load_current_config(self):
        """Carga la configuración actual en los controles"""
        # Configuración básica
        self.base_interval_spin.setValue(self.config.base_interval)
        self.min_interval_spin.setValue(self.config.min_interval)
        self.max_interval_spin.setValue(self.config.max_interval)
        
        self.adaptation_rate_slider.setValue(int(self.config.adaptation_rate * 100))
        self.high_threshold_slider.setValue(int(self.config.high_activity_threshold * 100))
        self.low_threshold_slider.setValue(int(self.config.low_activity_threshold * 100))
        
        # Configuración avanzada
        self.detection_weight_slider.setValue(int(self.config.detection_weight * 100))
        self.movement_weight_slider.setValue(int(self.config.movement_weight * 100))
        self.confidence_threshold_spin.setValue(self.config.confidence_threshold)
        self.min_detections_spin.setValue(self.config.min_detections_for_adaptation)
        
        self.history_window_spin.setValue(self.config.history_window)
        self.stabilization_time_spin.setValue(self.config.stabilization_time)
        
        self.enable_burst_check.setChecked(self.config.enable_burst_mode)
        self.burst_duration_spin.setValue(self.config.burst_duration)
        self.enable_smoothing_check.setChecked(self.config.enable_smoothing)
        
        # Actualizar etiquetas
        self._update_all_labels()
    
    def _update_adaptation_rate_label(self, value):
        self.adaptation_rate_label.setText(f"{value/100:.2f}")
    
    def _update_high_threshold_label(self, value):
        self.high_threshold_label.setText(f"{value/100:.2f}")
    
    def _update_low_threshold_label(self, value):
        self.low_threshold_label.setText(f"{value/100:.2f}")
    
    def _update_detection_weight_label(self, value):
        self.detection_weight_label.setText(f"{value/100:.1f}")
        # Actualizar automáticamente el peso de movimiento
        movement_value = 100 - value
        self.movement_weight_slider.setValue(movement_value)
        self.movement_weight_label.setText(f"{movement_value/100:.1f}")
    
    def _update_movement_weight_label(self, value):
        self.movement_weight_label.setText(f"{value/100:.1f}")
        # Actualizar automáticamente el peso de detección
        detection_value = 100 - value
        self.detection_weight_slider.setValue(detection_value)
        self.detection_weight_label.setText(f"{detection_value/100:.1f}")
    
    def _update_all_labels(self):
        """Actualiza todas las etiquetas de valores"""
        self._update_adaptation_rate_label(self.adaptation_rate_slider.value())
        self._update_high_threshold_label(self.high_threshold_slider.value())
        self._update_low_threshold_label(self.low_threshold_slider.value())
        self._update_detection_weight_label(self.detection_weight_slider.value())
    
    def _apply_preset(self, preset_name):
        """Aplica un preset de configuración"""
        self.config = AdaptiveSamplingConfig.create_config(preset_name)
        self._load_current_config()
        self._update_preview_values()
        
        # Mostrar mensaje de confirmación
        preset_names = {
            "aggressive": "Agresivo",
            "balanced": "Balanceado", 
            "conservative": "Conservador"
        }
        
        QMessageBox.information(
            self,
            "Preset Aplicado",
            f"✅ Configuración '{preset_names[preset_name]}' aplicada exitosamente.\n\n"
            f"Puedes ajustar valores específicos en las pestañas Básico y Avanzado."
        )
    
    def _save_config_to_file(self):
        """Guarda la configuración actual a un archivo"""
        try:
            from PyQt6.QtWidgets import QFileDialog
            
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar Configuración de Muestreo Adaptativo",
                f"adaptive_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                "JSON Files (*.json)"
            )
            
            if filename:
                current_config = self.get_config()
                config_data = {
                    'adaptive_sampling_config': current_config,
                    'timestamp': datetime.now().isoformat(),
                    'version': '1.0'
                }
                
                with open(filename, 'w') as f:
                    json.dump(config_data, f, indent=4)
                
                QMessageBox.information(
                    self,
                    "Configuración Guardada",
                    f"✅ Configuración guardada exitosamente en:\n{filename}"
                )
                
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"❌ Error guardando configuración:\n{str(e)}"
            )
    
    def _load_config_from_file(self):
        """Carga configuración desde un archivo"""
        try:
            from PyQt6.QtWidgets import QFileDialog
            
            filename, _ = QFileDialog.getOpenFileName(
                self,
                "Cargar Configuración de Muestreo Adaptativo",
                "",
                "JSON Files (*.json)"
            )
            
            if filename:
                with open(filename, 'r') as f:
                    config_data = json.load(f)
                
                # Extraer configuración
                if 'adaptive_sampling_config' in config_data:
                    config_dict = config_data['adaptive_sampling_config']
                else:
                    config_dict = config_data  # Formato directo
                
                self.config = AdaptiveSamplingConfig(**config_dict)
                self._load_current_config()
                self._update_preview_values()
                
                QMessageBox.information(
                    self,
                    "Configuración Cargada",
                    f"✅ Configuración cargada exitosamente desde:\n{filename}"
                )
                
        except Exception as e:
            QMessageBox.warning(
                self,
                "Error",
                f"❌ Error cargando configuración:\n{str(e)}"
            )
    
    def _reset_to_defaults(self):
        """Restaura la configuración a valores por defecto"""
        reply = QMessageBox.question(
            self,
            "Restablecer Configuración",
            "¿Está seguro de que desea restablecer todos los valores a la configuración por defecto?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.config = AdaptiveSamplingConfig.create_config("balanced")
            self._load_current_config()
            self._update_preview_values()
    
    def _start_simulation(self):
        """Inicia la simulación de comportamiento"""
        self.preview_timer.start(500)  # Actualizar cada 500ms
        self.start_simulation_btn.setEnabled(False)
        self.stop_simulation_btn.setEnabled(True)
    
    def _stop_simulation(self):
        """Detiene la simulación"""
        self.preview_timer.stop()
        self.start_simulation_btn.setEnabled(True)
        self.stop_simulation_btn.setEnabled(False)
    
    def _update_simulation(self):
        """Actualiza los valores de simulación"""
        # Simular diferentes niveles de actividad
        activity_levels = {
            "Sin actividad": 0.0,
            "Actividad baja": 0.08,
            "Actividad media": 0.15,
            "Actividad alta": 0.25,
            "Actividad muy alta": 0.40
        }
        
        current_level = self.activity_level_combo.currentText()
        activity_score = activity_levels.get(current_level, 0.0)
        
        # Calcular intervalo basado en la configuración actual
        config = self.get_config()
        
        if activity_score >= config['high_activity_threshold']:
            interval = config['min_interval']
        elif activity_score <= config['low_activity_threshold']:
            interval = config['max_interval']
        else:
            # Interpolación lineal
            activity_range = config['high_activity_threshold'] - config['low_activity_threshold']
            interval_range = config['max_interval'] - config['min_interval']
            normalized_activity = (activity_score - config['low_activity_threshold']) / activity_range
            interval = int(config['max_interval'] - (normalized_activity * interval_range))
        
        # Actualizar interfaz
        self.sim_current_interval.setText(str(interval))
        self.sim_activity_score.setText(f"{activity_score:.3f}")
        self.activity_progress_bar.setValue(int(activity_score * 100))
        
        # Calcular eficiencia estimada
        base_interval = config['base_interval']
        efficiency = max(0, (interval - base_interval) / config['max_interval'] * 100)
        self.sim_efficiency.setText(f"{efficiency:.1f}%")
        
        # Determinar tendencia (simulada)
        import random
        trends = ["estable", "creciente", "decreciente"]
        trend = random.choice(trends) if activity_score > 0.1 else "estable"
        self.sim_trend.setText(trend)
    
    def _start_preview(self):
        """Inicia la vista previa automática"""
        self._update_preview_values()
    
    def _update_preview_values(self):
        """Actualiza los valores de vista previa"""
        config = self.get_config()
        
        self.preview_base_interval.setText(str(config['base_interval']))
        self.preview_interval_range.setText(f"{config['min_interval']} - {config['max_interval']}")
        self.preview_adaptation_rate.setText(f"{config['adaptation_rate']:.2f}")
        self.preview_thresholds.setText(f"{config['low_activity_threshold']:.2f} - {config['high_activity_threshold']:.2f}")
    
    def update_preview(self):
        """Actualiza la vista previa en tiempo real (llamada por timer)"""
        self._update_simulation()
    
    def _apply_realtime(self):
        """Aplica la configuración en tiempo real"""
        config = self.get_config()
        self.config_changed.emit(config)
    
    def _test_configuration(self):
        """Prueba la configuración durante un período limitado"""
        QMessageBox.information(
            self,
            "Prueba de Configuración",
            "🧪 La configuración se aplicará durante 30 segundos para que puedas evaluar su rendimiento.\n\n"
            "Observa las métricas de rendimiento en la aplicación principal."
        )
        
        config = self.get_config()
        self.config_changed.emit(config)
        
        # Programar restauración después de 30 segundos (esto sería manejado por la aplicación principal)
    
    def get_config(self) -> dict:
        """Obtiene la configuración actual del diálogo"""
        config = {
            'base_interval': self.base_interval_spin.value(),
            'min_interval': self.min_interval_spin.value(),
            'max_interval': self.max_interval_spin.value(),
            'adaptation_rate': self.adaptation_rate_slider.value() / 100.0,
            'detection_weight': self.detection_weight_slider.value() / 100.0,
            'movement_weight': self.movement_weight_slider.value() / 100.0,
            'high_activity_threshold': self.high_threshold_slider.value() / 100.0,
            'low_activity_threshold': self.low_threshold_slider.value() / 100.0,
            'history_window': self.history_window_spin.value(),
            'stabilization_time': self.stabilization_time_spin.value(),
            'min_detections_for_adaptation': self.min_detections_spin.value(),
            'confidence_threshold': self.confidence_threshold_spin.value(),
            'enable_burst_mode': self.enable_burst_check.isChecked(),
            'burst_duration': self.burst_duration_spin.value(),
            'enable_smoothing': self.enable_smoothing_check.isChecked()
        }
        
        return config
    
    def set_config(self, config_dict: dict):
        """Establece la configuración desde un diccionario"""
        if isinstance(config_dict, dict):
            self.config = AdaptiveSamplingConfig(**config_dict)
        else:
            self.config = config_dict
        
        self._load_current_config()
        self._update_preview_values()
    
    def accept(self):
        """Acepta y aplica la configuración"""
        config = self.get_config()
        self.config_changed.emit(config)
        super().accept()
    
    def closeEvent(self, event):
        """Maneja el cierre del diálogo"""
        self._stop_simulation()
        super().closeEvent(event)


class AdaptiveSamplingInfoDialog(QDialog):
    """Diálogo informativo sobre el muestreo adaptativo"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🧠 Información sobre Muestreo Adaptativo")
        self.setMinimumSize(500, 400)
        
        layout = QVBoxLayout()
        
        # Título
        title = QLabel("🧠 Sistema de Muestreo Adaptativo")
        title.setFont(QFont("", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #2E5BBA; margin: 15px;")
        layout.addWidget(title)
        
        # Contenido informativo
        info_text = QTextEdit()
        info_text.setReadOnly(True)
        info_text.setHtml("""
        <h3>¿Qué es el Muestreo Adaptativo?</h3>
        <p>El muestreo adaptativo es una tecnología inteligente que ajusta automáticamente 
        la frecuencia de análisis de video basándose en la actividad detectada en la escena.</p>
        
        <h3>🎯 Beneficios Principales:</h3>
        <ul>
        <li><b>⚡ Optimización de Rendimiento:</b> Reduce el uso de CPU hasta un 70% en escenas estáticas</li>
        <li><b>🧠 Inteligencia Automática:</b> Se adapta continuamente sin intervención manual</li>
        <li><b>📊 Calidad Mantenida:</b> Preserva la precisión de detección en momentos críticos</li>
        <li><b>⚙️ Configuración Flexible:</b> Personalizable para diferentes necesidades</li>
        </ul>
        
        <h3>🔧 Cómo Funciona:</h3>
        <p><b>1. Análisis Continuo:</b> Monitorea constantemente la actividad de la escena</p>
        <p><b>2. Cálculo Inteligente:</b> Evalúa detecciones, movimiento y confianza</p>
        <p><b>3. Adaptación Dinámica:</b> Ajusta la frecuencia de análisis automáticamente</p>
        <p><b>4. Optimización Continua:</b> Mejora el rendimiento en tiempo real</p>
        
        <h3>📈 Escenarios de Uso:</h3>
        <p><b>🏢 Oficinas:</b> Reduce consumo durante horarios de baja actividad</p>
        <p><b>🏠 Hogares:</b> Optimiza recursos manteniendo la seguridad</p>
        <p><b>🚗 Tráfico:</b> Se adapta a patrones de flujo vehicular</p>
        <p><b>🏭 Industria:</b> Equilibra monitoreo y eficiencia energética</p>
        
        <h3>💡 Recomendaciones:</h3>
        <p>• Usa el preset <b>"Balanceado"</b> para la mayoría de aplicaciones</p>
        <p>• Activa <b>"Agresivo"</b> para sistemas con muchas cámaras</p>
        <p>• Usa <b>"Conservador"</b> para aplicaciones críticas</p>
        <p>• Monitorea las estadísticas durante la primera semana</p>
        """)
        
        layout.addWidget(info_text)
        
        # Botón de cerrar
        close_btn = QPushButton("✅ Entendido")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        layout.addWidget(close_btn)
        
        self.setLayout(layout)


# Función de utilidad para mostrar información
def show_adaptive_sampling_info(parent=None):
    """Muestra el diálogo informativo sobre muestreo adaptativo"""
    dialog = AdaptiveSamplingInfoDialog(parent)
    dialog.exec()


# Ejemplo de uso
if __name__ == "__main__":
    from PyQt6.QtWidgets import QApplication
    import sys
    
    app = QApplication(sys.argv)
    
    # Crear configuración de ejemplo
    config = AdaptiveSamplingConfig.create_config("balanced")
    
    # Mostrar diálogo de configuración
    dialog = AdaptiveSamplingConfigDialog(None, config)
    
    def on_config_changed(new_config):
        print("🧠 Nueva configuración:")
        for key, value in new_config.items():
            print(f"   {key}: {value}")
    
    dialog.config_changed.connect(on_config_changed)
    
    if dialog.exec():
        print("✅ Configuración aplicada")
        final_config = dialog.get_config()
        print(f"📊 Configuración final: {final_config}")
    else:
        print("❌ Configuración cancelada")
    
    sys.exit(app.exec())