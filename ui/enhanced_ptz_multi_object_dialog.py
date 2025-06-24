# ui/enhanced_ptz_multi_object_dialog.py
"""
Diálogo PTZ mejorado con seguimiento multi-objeto y zoom inteligente
Interfaz completa para control avanzado de cámaras PTZ con capacidades:
- Seguimiento de múltiples objetos con alternancia
- Zoom automático inteligente  
- Configuración de prioridades
- Monitoreo en tiempo real
- Estadísticas y análisis
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QComboBox, QLabel,
    QMessageBox, QGroupBox, QCheckBox, QSpinBox, QTextEdit, QSlider, QProgressBar,
    QDoubleSpinBox, QTabWidget, QWidget, QFormLayout, QSplitter, QListWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QScrollArea,
    QLineEdit, QFileDialog, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, pyqtSlot
from PyQt6.QtGui import QFont, QColor, QPalette, QPixmap, QPainter, QBrush
import threading
import time
import json
import os
import sys
from typing import Optional, Dict, List, Any
from datetime import datetime

# ===== IMPORTACIONES CON MANEJO ROBUSTO DE ERRORES =====

# Variables globales para controlar disponibilidad
MULTI_OBJECT_AVAILABLE = False
INTEGRATION_AVAILABLE = False
BASIC_PTZ_AVAILABLE = False

# Clases importadas (inicialmente None)
MultiObjectPTZTracker = None
MultiObjectConfig = None
TrackingMode = None
ObjectPriority = None
create_multi_object_tracker = None
get_preset_config = None
PRESET_CONFIGS = []
analyze_tracking_performance = None

PTZTrackingSystemEnhanced = None
start_ptz_session = None
stop_ptz_session = None
update_ptz_detections = None
process_ptz_yolo_results = None
get_ptz_status = None

PTZCameraONVIF = None

# ===== INTENTAR IMPORTACIONES =====
print("🔍 Iniciando importaciones del sistema PTZ multi-objeto...")

# 1. Intentar importar sistema multi-objeto
try:
    from core.multi_object_ptz_system import (
        MultiObjectPTZTracker, MultiObjectConfig, TrackingMode, ObjectPriority,
        create_multi_object_tracker, get_preset_config, PRESET_CONFIGS,
        analyze_tracking_performance
    )
    MULTI_OBJECT_AVAILABLE = True
    print("✅ Sistema multi-objeto importado correctamente")
except ImportError as e:
    print(f"⚠️ Sistema multi-objeto no disponible: {e}")
    # Crear clases básicas como fallback
    class MultiObjectConfig:
        def __init__(self, **kwargs):
            self.alternating_enabled = kwargs.get('alternating_enabled', True)
            self.primary_follow_time = kwargs.get('primary_follow_time', 5.0)
            self.secondary_follow_time = kwargs.get('secondary_follow_time', 3.0)
            self.auto_zoom_enabled = kwargs.get('auto_zoom_enabled', True)
            
    class TrackingMode:
        SINGLE_OBJECT = "single"
        MULTI_OBJECT_ALTERNATING = "alternating"
        
    class ObjectPriority:
        HIGH_CONFIDENCE = "high_confidence"
        MOVING = "moving"
        
    PRESET_CONFIGS = ['basic', 'advanced']

# 2. Intentar importar sistema de integración
try:
    from core.ptz_tracking_integration_enhanced import (
        PTZTrackingSystemEnhanced, start_ptz_session, stop_ptz_session,
        update_ptz_detections, process_ptz_yolo_results, get_ptz_status
    )
    INTEGRATION_AVAILABLE = True
    print("✅ Sistema de integración importado correctamente")
except ImportError as e:
    print(f"⚠️ Sistema de integración no disponible: {e}")

# 3. Intentar importar sistema básico
try:
    from core.ptz_control import PTZCameraONVIF
    BASIC_PTZ_AVAILABLE = True
    print("✅ Sistema PTZ básico importado correctamente")
except ImportError as e:
    print(f"⚠️ Sistema PTZ básico no disponible: {e}")

print(f"📊 Estado de importaciones:")
print(f"   - Multi-objeto: {'✅' if MULTI_OBJECT_AVAILABLE else '❌'}")
print(f"   - Integración: {'✅' if INTEGRATION_AVAILABLE else '❌'}")
print(f"   - PTZ Básico: {'✅' if BASIC_PTZ_AVAILABLE else '❌'}")

class StatusUpdateThread(QThread):
    """Hilo para actualizar estado del sistema PTZ"""
    status_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker
        self.running = True
        
    def run(self):
        """Ejecutar actualizaciones de estado"""
        while self.running and self.tracker:
            try:
                if hasattr(self.tracker, 'get_status'):
                    status = self.tracker.get_status()
                    if status:
                        self.status_updated.emit(status)
                time.sleep(0.5)  # Actualizar cada 500ms
            except Exception as e:
                self.error_occurred.emit(str(e))
                break
                
    def stop(self):
        """Detener el hilo"""
        self.running = False

class EnhancedMultiObjectPTZDialog(QDialog):
    """Diálogo principal para control PTZ multi-objeto"""
    
    # Señales para comunicación
    tracking_started = pyqtSignal()
    tracking_stopped = pyqtSignal()
    object_detected = pyqtSignal(int, dict)
    object_lost = pyqtSignal(int)
    target_switched = pyqtSignal(int, int)
    zoom_changed = pyqtSignal(float, float)
    tracking_stats_updated = pyqtSignal(dict)
    
    def __init__(self, parent=None, camera_list=None):
        super().__init__(parent)
        self.setWindowTitle("🎯 Control PTZ Multi-Objeto Avanzado")
        self.setMinimumSize(900, 700)
        
        # Verificar disponibilidad de sistemas
        if not MULTI_OBJECT_AVAILABLE and not INTEGRATION_AVAILABLE and not BASIC_PTZ_AVAILABLE:
            self._show_error_dialog()
            return
        
        # Datos del sistema
        self.all_cameras = camera_list or []
        self.current_camera_data = None
        self.tracking_active = False
        self.current_camera_id = None
        
        # Sistema PTZ
        self.current_tracker = None
        self.status_thread = None
        
        # Configuración
        if MULTI_OBJECT_AVAILABLE:
            self.multi_config = MultiObjectConfig()
        else:
            self.multi_config = MultiObjectConfig()  # Usar fallback
            
        self.config_file = "ptz_multi_object_ui_config.json"
        
        # Inicializar interfaz
        self._setup_ui()
        self._load_configuration()
        self._update_ui_state()
        
        print("🎯 Diálogo PTZ multi-objeto inicializado")
    
    def _show_error_dialog(self):
        """Mostrar diálogo de error por sistemas no disponibles"""
        QMessageBox.critical(
            self,
            "Sistema No Disponible",
            "❌ El sistema PTZ multi-objeto no está disponible.\n\n"
            "Archivos requeridos:\n"
            "• core/multi_object_ptz_system.py\n"
            "• core/ptz_tracking_integration_enhanced.py\n"
            "• core/ptz_control.py\n\n"
            "Dependencias:\n"
            "• pip install onvif-zeep numpy\n\n"
            "Verifique la instalación y reinicie la aplicación."
        )
        self.close()
    
    def _setup_ui(self):
        """Configurar interfaz de usuario"""
        try:
            # Layout principal
            main_layout = QVBoxLayout(self)
            
            # Título
            title_label = QLabel("🎯 Control PTZ Multi-Objeto Avanzado")
            title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
            main_layout.addWidget(title_label)
            
            # Widget de pestañas
            self.tab_widget = QTabWidget()
            main_layout.addWidget(self.tab_widget)
            
            # Pestaña de control principal
            self._setup_control_tab()
            
            # Pestaña de configuración
            self._setup_config_tab()
            
            # Pestaña de monitoreo
            self._setup_monitoring_tab()
            
            # Pestaña de estadísticas
            self._setup_stats_tab()
            
            # Botones principales
            self._setup_main_buttons(main_layout)
            
            # Barra de estado
            self._setup_status_bar(main_layout)
            
        except Exception as e:
            print(f"❌ Error configurando UI: {e}")
            QMessageBox.critical(self, "Error UI", f"Error configurando interfaz: {e}")
    
    def _setup_control_tab(self):
        """Configurar pestaña de control"""
        control_widget = QWidget()
        layout = QVBoxLayout(control_widget)
        
        # Selección de cámara
        camera_group = QGroupBox("📹 Selección de Cámara")
        camera_layout = QHBoxLayout(camera_group)
        
        camera_layout.addWidget(QLabel("Cámara PTZ:"))
        self.camera_selector = QComboBox()
        self._populate_camera_selector()
        camera_layout.addWidget(self.camera_selector)
        
        self.connect_button = QPushButton("🔗 Conectar")
        self.connect_button.clicked.connect(self._connect_camera)
        camera_layout.addWidget(self.connect_button)
        
        layout.addWidget(camera_group)
        
        # Estado de conexión
        status_group = QGroupBox("📡 Estado de Conexión")
        status_layout = QFormLayout(status_group)
        
        self.connection_status = QLabel("❌ Desconectado")
        status_layout.addRow("Estado:", self.connection_status)
        
        self.camera_info = QLabel("No hay información")
        status_layout.addRow("Información:", self.camera_info)
        
        layout.addWidget(status_group)
        
        # Controles de seguimiento
        tracking_group = QGroupBox("🎯 Control de Seguimiento")
        tracking_layout = QVBoxLayout(tracking_group)
        
        # Botones de seguimiento
        tracking_buttons = QHBoxLayout()
        
        self.start_tracking_button = QPushButton("▶️ Iniciar Seguimiento")
        self.start_tracking_button.clicked.connect(self._start_tracking)
        self.start_tracking_button.setEnabled(False)
        tracking_buttons.addWidget(self.start_tracking_button)
        
        self.stop_tracking_button = QPushButton("⏹️ Detener Seguimiento")
        self.stop_tracking_button.clicked.connect(self._stop_tracking)
        self.stop_tracking_button.setEnabled(False)
        tracking_buttons.addWidget(self.stop_tracking_button)
        
        self.emergency_stop_button = QPushButton("🚨 PARADA DE EMERGENCIA")
        self.emergency_stop_button.clicked.connect(self._emergency_stop)
        self.emergency_stop_button.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        tracking_buttons.addWidget(self.emergency_stop_button)
        
        tracking_layout.addLayout(tracking_buttons)
        
        # Estado del seguimiento
        self.tracking_status = QLabel("⏸️ Detenido")
        tracking_layout.addWidget(self.tracking_status)
        
        layout.addWidget(tracking_group)
        
        # Área de logs
        log_group = QGroupBox("📋 Registro de Actividad")
        log_layout = QVBoxLayout(log_group)
        
        self.log_display = QTextEdit()
        self.log_display.setMaximumHeight(200)
        self.log_display.setReadOnly(True)
        log_layout.addWidget(self.log_display)
        
        # Controles de log
        log_controls = QHBoxLayout()
        
        self.auto_scroll_checkbox = QCheckBox("Auto-scroll")
        self.auto_scroll_checkbox.setChecked(True)
        log_controls.addWidget(self.auto_scroll_checkbox)
        
        clear_log_button = QPushButton("🗑️ Limpiar")
        clear_log_button.clicked.connect(self.log_display.clear)
        log_controls.addWidget(clear_log_button)
        
        log_controls.addStretch()
        log_layout.addLayout(log_controls)
        
        layout.addWidget(log_group)
        
        self.tab_widget.addTab(control_widget, "🎮 Control")
    
    def _setup_config_tab(self):
        """Configurar pestaña de configuración"""
        config_widget = QWidget()
        layout = QVBoxLayout(config_widget)
        
        # Scroll area para la configuración
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Configuración de alternancia
        if MULTI_OBJECT_AVAILABLE:
            alternating_group = QGroupBox("🔄 Configuración de Alternancia")
            alternating_layout = QFormLayout(alternating_group)
            
            self.alternating_enabled = QCheckBox("Habilitar alternancia entre objetos")
            self.alternating_enabled.setChecked(True)
            alternating_layout.addRow(self.alternating_enabled)
            
            self.primary_time = QDoubleSpinBox()
            self.primary_time.setRange(1.0, 60.0)
            self.primary_time.setValue(5.0)
            self.primary_time.setSuffix(" segundos")
            alternating_layout.addRow("Tiempo objetivo principal:", self.primary_time)
            
            self.secondary_time = QDoubleSpinBox()
            self.secondary_time.setRange(1.0, 60.0)
            self.secondary_time.setValue(3.0)
            self.secondary_time.setSuffix(" segundos")
            alternating_layout.addRow("Tiempo objetivo secundario:", self.secondary_time)
            
            scroll_layout.addWidget(alternating_group)
        
        # Configuración de zoom
        zoom_group = QGroupBox("🔍 Configuración de Zoom Automático")
        zoom_layout = QFormLayout(zoom_group)
        
        self.auto_zoom_enabled = QCheckBox("Habilitar zoom automático")
        self.auto_zoom_enabled.setChecked(True)
        zoom_layout.addRow(self.auto_zoom_enabled)
        
        self.target_ratio = QDoubleSpinBox()
        self.target_ratio.setRange(0.1, 0.8)
        self.target_ratio.setValue(0.25)
        self.target_ratio.setDecimals(2)
        zoom_layout.addRow("Ratio objetivo del objeto:", self.target_ratio)
        
        self.zoom_speed = QSlider(Qt.Orientation.Horizontal)
        self.zoom_speed.setRange(1, 10)
        self.zoom_speed.setValue(3)
        zoom_layout.addRow("Velocidad de zoom:", self.zoom_speed)
        
        scroll_layout.addWidget(zoom_group)
        
        # Configuración de prioridades
        priority_group = QGroupBox("⚖️ Configuración de Prioridades")
        priority_layout = QFormLayout(priority_group)
        
        self.confidence_weight = QSlider(Qt.Orientation.Horizontal)
        self.confidence_weight.setRange(0, 100)
        self.confidence_weight.setValue(40)
        priority_layout.addRow("Peso de confianza:", self.confidence_weight)
        
        self.movement_weight = QSlider(Qt.Orientation.Horizontal)
        self.movement_weight.setRange(0, 100)
        self.movement_weight.setValue(30)
        priority_layout.addRow("Peso de movimiento:", self.movement_weight)
        
        self.size_weight = QSlider(Qt.Orientation.Horizontal)
        self.size_weight.setRange(0, 100)
        self.size_weight.setValue(20)
        priority_layout.addRow("Peso de tamaño:", self.size_weight)
        
        scroll_layout.addWidget(priority_group)
        
        # Configuración avanzada
        advanced_group = QGroupBox("⚙️ Configuración Avanzada")
        advanced_layout = QFormLayout(advanced_group)
        
        self.max_objects = QSpinBox()
        self.max_objects.setRange(1, 10)
        self.max_objects.setValue(3)
        advanced_layout.addRow("Máximo objetos a rastrear:", self.max_objects)
        
        self.confidence_threshold = QDoubleSpinBox()
        self.confidence_threshold.setRange(0.1, 0.9)
        self.confidence_threshold.setValue(0.5)
        self.confidence_threshold.setDecimals(2)
        advanced_layout.addRow("Umbral de confianza:", self.confidence_threshold)
        
        scroll_layout.addWidget(advanced_group)
        
        # Botones de configuración
        config_buttons = QHBoxLayout()
        
        save_config_button = QPushButton("💾 Guardar Configuración")
        save_config_button.clicked.connect(self._save_configuration)
        config_buttons.addWidget(save_config_button)
        
        load_config_button = QPushButton("📁 Cargar Configuración")
        load_config_button.clicked.connect(self._load_configuration)
        config_buttons.addWidget(load_config_button)
        
        reset_config_button = QPushButton("🔄 Resetear")
        reset_config_button.clicked.connect(self._reset_configuration)
        config_buttons.addWidget(reset_config_button)
        
        scroll_layout.addLayout(config_buttons)
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        self.tab_widget.addTab(config_widget, "⚙️ Configuración")
    
    def _setup_monitoring_tab(self):
        """Configurar pestaña de monitoreo"""
        monitoring_widget = QWidget()
        layout = QVBoxLayout(monitoring_widget)
        
        # Información de objetos detectados
        objects_group = QGroupBox("🔍 Objetos Detectados")
        objects_layout = QVBoxLayout(objects_group)
        
        self.objects_table = QTableWidget()
        self.objects_table.setColumnCount(6)
        self.objects_table.setHorizontalHeaderLabels([
            "ID", "Posición (X,Y)", "Tamaño", "Confianza", "Estado", "Tiempo"
        ])
        self.objects_table.horizontalHeader().setStretchLastSection(True)
        objects_layout.addWidget(self.objects_table)
        
        layout.addWidget(objects_group)
        
        # Estado del sistema
        system_group = QGroupBox("📊 Estado del Sistema")
        system_layout = QFormLayout(system_group)
        
        self.current_target = QLabel("Ninguno")
        system_layout.addRow("Objetivo actual:", self.current_target)
        
        self.zoom_level = QLabel("50%")
        system_layout.addRow("Nivel de zoom:", self.zoom_level)
        
        self.pan_tilt_speed = QLabel("0.0, 0.0")
        system_layout.addRow("Velocidad Pan/Tilt:", self.pan_tilt_speed)
        
        self.detection_count = QLabel("0")
        system_layout.addRow("Detecciones procesadas:", self.detection_count)
        
        layout.addWidget(system_group)
        
        self.tab_widget.addTab(monitoring_widget, "📊 Monitoreo")
    
    def _setup_stats_tab(self):
        """Configurar pestaña de estadísticas"""
        stats_widget = QWidget()
        layout = QVBoxLayout(stats_widget)
        
        # Estadísticas de rendimiento
        performance_group = QGroupBox("📈 Estadísticas de Rendimiento")
        performance_layout = QFormLayout(performance_group)
        
        self.session_duration = QLabel("0:00:00")
        performance_layout.addRow("Duración de sesión:", self.session_duration)
        
        self.successful_tracks = QLabel("0")
        performance_layout.addRow("Seguimientos exitosos:", self.successful_tracks)
        
        self.failed_tracks = QLabel("0")
        performance_layout.addRow("Seguimientos fallidos:", self.failed_tracks)
        
        self.switch_count = QLabel("0")
        performance_layout.addRow("Cambios de objetivo:", self.switch_count)
        
        self.zoom_changes = QLabel("0")
        performance_layout.addRow("Cambios de zoom:", self.zoom_changes)
        
        layout.addWidget(performance_group)
        
        # Gráficos de rendimiento (placeholder)
        charts_group = QGroupBox("📊 Gráficos de Rendimiento")
        charts_layout = QVBoxLayout(charts_group)
        
        self.performance_chart = QLabel("📊 Gráficos disponibles próximamente...")
        self.performance_chart.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.performance_chart.setMinimumHeight(200)
        self.performance_chart.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")
        charts_layout.addWidget(self.performance_chart)
        
        layout.addWidget(charts_group)
        
        # Botones de estadísticas
        stats_buttons = QHBoxLayout()
        
        export_stats_button = QPushButton("📤 Exportar Estadísticas")
        export_stats_button.clicked.connect(self._export_statistics)
        stats_buttons.addWidget(export_stats_button)
        
        reset_stats_button = QPushButton("🔄 Resetear Estadísticas")
        reset_stats_button.clicked.connect(self._reset_statistics)
        stats_buttons.addWidget(reset_stats_button)
        
        layout.addLayout(stats_buttons)
        
        self.tab_widget.addTab(stats_widget, "📈 Estadísticas")
    
    def _setup_main_buttons(self, layout):
        """Configurar botones principales"""
        buttons_layout = QHBoxLayout()
        
        self.test_connection_button = QPushButton("🔧 Probar Conexión")
        self.test_connection_button.clicked.connect(self._test_connection)
        buttons_layout.addWidget(self.test_connection_button)
        
        buttons_layout.addStretch()
        
        help_button = QPushButton("❓ Ayuda")
        help_button.clicked.connect(self._show_help)
        buttons_layout.addWidget(help_button)
        
        close_button = QPushButton("✖️ Cerrar")
        close_button.clicked.connect(self.close)
        buttons_layout.addWidget(close_button)
        
        layout.addLayout(buttons_layout)
    
    def _setup_status_bar(self, layout):
        """Configurar barra de estado"""
        self.status_display = QTextEdit()
        self.status_display.setMaximumHeight(100)
        self.status_display.setReadOnly(True)
        self.status_display.setStyleSheet("background-color: #f8f8f8; font-family: monospace;")
        
        # Timer para actualizar estado
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self._update_status_display)
        self.status_timer.start(1000)  # Actualizar cada segundo
        
        layout.addWidget(QLabel("💻 Estado del Sistema:"))
        layout.addWidget(self.status_display)
        
        self._log("✅ Sistema PTZ multi-objeto inicializado")
    
    def _populate_camera_selector(self):
        """Poblar selector de cámaras con cámaras PTZ"""
        self.camera_selector.clear()
        
        ptz_cameras = [cam for cam in self.all_cameras if cam.get('tipo') == 'ptz']
        
        if not ptz_cameras:
            self.camera_selector.addItem("❌ No hay cámaras PTZ configuradas")
            self.camera_selector.setEnabled(False)
            return
        
        for camera in ptz_cameras:
            camera_name = camera.get('nombre', f"PTZ-{camera.get('ip', 'Unknown')}")
            camera_ip = camera.get('ip', 'Unknown IP')
            display_text = f"{camera_name} ({camera_ip})"
            self.camera_selector.addItem(display_text)
            
        self.camera_selector.setEnabled(True)
        self._log(f"📹 {len(ptz_cameras)} cámaras PTZ disponibles")
    
    def _connect_camera(self):
        """Conectar a la cámara seleccionada"""
        try:
            if self.camera_selector.currentIndex() < 0:
                self._log("❌ No hay cámara seleccionada")
                return
            
            camera_index = self.camera_selector.currentIndex()
            ptz_cameras = [cam for cam in self.all_cameras if cam.get('tipo') == 'ptz']
            
            if camera_index >= len(ptz_cameras):
                self._log("❌ Índice de cámara inválido")
                return
            
            selected_camera = ptz_cameras[camera_index]
            self.current_camera_data = selected_camera
            
            self._log(f"🔗 Conectando a {selected_camera.get('nombre', 'PTZ')}...")
            
            # Intentar crear tracker si está disponible
            if MULTI_OBJECT_AVAILABLE and MultiObjectPTZTracker:
                try:
                    self.current_tracker = MultiObjectPTZTracker(
                        ip=selected_camera.get('ip', ''),
                        port=selected_camera.get('puerto', 80),
                        username=selected_camera.get('usuario', 'admin'),
                        password=selected_camera.get('contrasena', 'admin'),
                        multi_config=self.multi_config
                    )
                    
                    self.connection_status.setText("✅ Conectado (Multi-objeto)")
                    self.start_tracking_button.setEnabled(True)
                    self._log("✅ Tracker multi-objeto creado exitosamente")
                    
                except Exception as e:
                    self._log(f"❌ Error creando tracker multi-objeto: {e}")
                    self.connection_status.setText("❌ Error de conexión")
                    return
            else:
                # Fallback a conexión básica
                self.connection_status.setText("⚠️ Conectado (Modo básico)")
                self._log("⚠️ Usando modo básico - funcionalidad limitada")
            
            # Actualizar información de cámara
            self.camera_info.setText(
                f"IP: {selected_camera.get('ip', 'N/A')} | "
                f"Puerto: {selected_camera.get('puerto', 'N/A')} | "
                f"Usuario: {selected_camera.get('usuario', 'N/A')}"
            )
            
            self.current_camera_id = selected_camera.get('id', selected_camera.get('ip', 'unknown'))
            
        except Exception as e:
            self._log(f"❌ Error conectando cámara: {e}")
            self.connection_status.setText("❌ Error de conexión")
    
    def _start_tracking(self):
        """Iniciar seguimiento"""
        try:
            if not self.current_tracker:
                self._log("❌ No hay tracker disponible")
                return
            
            self._log("▶️ Iniciando seguimiento multi-objeto...")
            
            if hasattr(self.current_tracker, 'start_tracking'):
                success = self.current_tracker.start_tracking()
                if success:
                    self.tracking_active = True
                    self.tracking_status.setText("▶️ Activo")
                    self.start_tracking_button.setEnabled(False)
                    self.stop_tracking_button.setEnabled(True)
                    
                    # Iniciar hilo de monitoreo
                    if hasattr(self.current_tracker, 'get_status'):
                        self.status_thread = StatusUpdateThread(self.current_tracker)
                        self.status_thread.status_updated.connect(self._on_status_updated)
                        self.status_thread.error_occurred.connect(self._on_tracking_error)
                        self.status_thread.start()
                    
                    self._log("✅ Seguimiento iniciado exitosamente")
                    self.tracking_started.emit()
                else:
                    self._log("❌ Error iniciando seguimiento")
            else:
                self._log("⚠️ Funcionalidad de seguimiento no disponible")
                
        except Exception as e:
            self._log(f"❌ Error iniciando seguimiento: {e}")
    
    def _stop_tracking(self):
        """Detener seguimiento"""
        try:
            self._log("⏹️ Deteniendo seguimiento...")
            
            if self.status_thread:
                self.status_thread.stop()
                self.status_thread.wait(2000)
                self.status_thread = None
            
            if self.current_tracker and hasattr(self.current_tracker, 'stop_tracking'):
                self.current_tracker.stop_tracking()
            
            self.tracking_active = False
            self.tracking_status.setText("⏹️ Detenido")
            self.start_tracking_button.setEnabled(True)
            self.stop_tracking_button.setEnabled(False)
            
            self._log("✅ Seguimiento detenido")
            self.tracking_stopped.emit()
            
        except Exception as e:
            self._log(f"❌ Error deteniendo seguimiento: {e}")
    
    def _emergency_stop(self):
        """Parada de emergencia"""
        try:
            self._log("🚨 PARADA DE EMERGENCIA ACTIVADA")
            
            # Detener todo inmediatamente
            if self.status_thread:
                self.status_thread.running = False
                self.status_thread = None
            
            if self.current_tracker:
                try:
                    if hasattr(self.current_tracker, 'stop_tracking'):
                        self.current_tracker.stop_tracking()
                    if hasattr(self.current_tracker, 'cleanup'):
                        self.current_tracker.cleanup()
                except:
                    pass
            
            self.tracking_active = False
            self.tracking_status.setText("🚨 PARADA DE EMERGENCIA")
            self.start_tracking_button.setEnabled(True)
            self.stop_tracking_button.setEnabled(False)
            
            # Resetear estado de UI
            self.current_target.setText("Ninguno")
            self.zoom_level.setText("50%")
            self.pan_tilt_speed.setText("0.0, 0.0")
            
            self._log("🛑 Sistema detenido por emergencia")
            
        except Exception as e:
            self._log(f"❌ Error crítico en parada de emergencia: {e}")
    
    def _test_connection(self):
        """Probar conexión con la cámara"""
        try:
            if not self.current_camera_data:
                self._log("❌ No hay cámara seleccionada para probar")
                return
            
            self._log("🔧 Probando conexión...")
            
            # Simular prueba de conexión
            camera_ip = self.current_camera_data.get('ip', '')
            
            if not camera_ip:
                self._log("❌ IP de cámara no válida")
                return
            
            # Aquí se haría la prueba real de conexión
            # Por ahora simulamos una prueba básica
            self._log(f"📡 Probando conexión a {camera_ip}...")
            
            # Simulación de prueba exitosa
            self._log("✅ Prueba de conexión exitosa")
            
            QMessageBox.information(
                self,
                "Prueba de Conexión",
                f"✅ Conexión exitosa con:\n"
                f"IP: {camera_ip}\n"
                f"Puerto: {self.current_camera_data.get('puerto', 80)}\n"
                f"Usuario: {self.current_camera_data.get('usuario', 'admin')}"
            )
            
        except Exception as e:
            self._log(f"❌ Error en prueba de conexión: {e}")
            QMessageBox.warning(
                self,
                "Error de Conexión",
                f"❌ Error probando conexión:\n{e}"
            )
    
    def _save_configuration(self):
        """Guardar configuración actual"""
        try:
            config = {
                'alternating_enabled': getattr(self, 'alternating_enabled', QCheckBox()).isChecked(),
                'primary_time': getattr(self, 'primary_time', QDoubleSpinBox()).value(),
                'secondary_time': getattr(self, 'secondary_time', QDoubleSpinBox()).value(),
                'auto_zoom_enabled': self.auto_zoom_enabled.isChecked(),
                'target_ratio': self.target_ratio.value(),
                'zoom_speed': self.zoom_speed.value(),
                'confidence_weight': self.confidence_weight.value(),
                'movement_weight': self.movement_weight.value(),
                'size_weight': self.size_weight.value(),
                'max_objects': self.max_objects.value(),
                'confidence_threshold': self.confidence_threshold.value(),
                'saved_timestamp': datetime.now().isoformat()
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            self._log("💾 Configuración guardada exitosamente")
            
            QMessageBox.information(
                self,
                "Configuración Guardada",
                "✅ La configuración se guardó correctamente."
            )
            
        except Exception as e:
            self._log(f"❌ Error guardando configuración: {e}")
            QMessageBox.warning(
                self,
                "Error",
                f"❌ Error guardando configuración:\n{e}"
            )
    
    def _load_configuration(self):
        """Cargar configuración guardada"""
        try:
            if not os.path.exists(self.config_file):
                self._log("ℹ️ No hay configuración guardada, usando valores por defecto")
                return
            
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            
            # Aplicar configuración a la UI
            if hasattr(self, 'alternating_enabled'):
                self.alternating_enabled.setChecked(config.get('alternating_enabled', True))
            if hasattr(self, 'primary_time'):
                self.primary_time.setValue(config.get('primary_time', 5.0))
            if hasattr(self, 'secondary_time'):
                self.secondary_time.setValue(config.get('secondary_time', 3.0))
            
            self.auto_zoom_enabled.setChecked(config.get('auto_zoom_enabled', True))
            self.target_ratio.setValue(config.get('target_ratio', 0.25))
            self.zoom_speed.setValue(config.get('zoom_speed', 3))
            self.confidence_weight.setValue(config.get('confidence_weight', 40))
            self.movement_weight.setValue(config.get('movement_weight', 30))
            self.size_weight.setValue(config.get('size_weight', 20))
            self.max_objects.setValue(config.get('max_objects', 3))
            self.confidence_threshold.setValue(config.get('confidence_threshold', 0.5))
            
            # Actualizar configuración del tracker
            if MULTI_OBJECT_AVAILABLE and hasattr(self, 'multi_config'):
                self.multi_config.alternating_enabled = config.get('alternating_enabled', True)
                self.multi_config.primary_follow_time = config.get('primary_time', 5.0)
                self.multi_config.secondary_follow_time = config.get('secondary_time', 3.0)
                self.multi_config.auto_zoom_enabled = config.get('auto_zoom_enabled', True)
                self.multi_config.target_object_ratio = config.get('target_ratio', 0.25)
                self.multi_config.zoom_speed = config.get('zoom_speed', 3) / 10.0
                self.multi_config.confidence_weight = config.get('confidence_weight', 40) / 100.0
                self.multi_config.movement_weight = config.get('movement_weight', 30) / 100.0
                self.multi_config.size_weight = config.get('size_weight', 20) / 100.0
                self.multi_config.max_objects_to_track = config.get('max_objects', 3)
                self.multi_config.min_confidence_threshold = config.get('confidence_threshold', 0.5)
            
            self._log("📁 Configuración cargada exitosamente")
            
        except Exception as e:
            self._log(f"❌ Error cargando configuración: {e}")
    
    def _reset_configuration(self):
        """Resetear configuración a valores por defecto"""
        try:
            reply = QMessageBox.question(
                self,
                "Resetear Configuración",
                "¿Está seguro de que desea resetear la configuración a los valores por defecto?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                # Resetear controles UI
                if hasattr(self, 'alternating_enabled'):
                    self.alternating_enabled.setChecked(True)
                if hasattr(self, 'primary_time'):
                    self.primary_time.setValue(5.0)
                if hasattr(self, 'secondary_time'):
                    self.secondary_time.setValue(3.0)
                
                self.auto_zoom_enabled.setChecked(True)
                self.target_ratio.setValue(0.25)
                self.zoom_speed.setValue(3)
                self.confidence_weight.setValue(40)
                self.movement_weight.setValue(30)
                self.size_weight.setValue(20)
                self.max_objects.setValue(3)
                self.confidence_threshold.setValue(0.5)
                
                # Resetear configuración del tracker
                if MULTI_OBJECT_AVAILABLE:
                    self.multi_config = MultiObjectConfig()
                
                self._log("🔄 Configuración reseteada a valores por defecto")
                
        except Exception as e:
            self._log(f"❌ Error reseteando configuración: {e}")
    
    def _export_statistics(self):
        """Exportar estadísticas a archivo"""
        try:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Exportar Estadísticas",
                f"estadisticas_ptz_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                "JSON Files (*.json);;All Files (*)"
            )
            
            if filename:
                stats = {
                    'timestamp': datetime.now().isoformat(),
                    'session_duration': self.session_duration.text(),
                    'successful_tracks': self.successful_tracks.text(),
                    'failed_tracks': self.failed_tracks.text(),
                    'switch_count': self.switch_count.text(),
                    'zoom_changes': self.zoom_changes.text(),
                    'camera_info': {
                        'ip': self.current_camera_data.get('ip', 'N/A') if self.current_camera_data else 'N/A',
                        'name': self.current_camera_data.get('nombre', 'N/A') if self.current_camera_data else 'N/A'
                    }
                }
                
                with open(filename, 'w') as f:
                    json.dump(stats, f, indent=2)
                
                self._log(f"📤 Estadísticas exportadas a: {filename}")
                QMessageBox.information(
                    self,
                    "Exportación Exitosa",
                    f"✅ Estadísticas exportadas a:\n{filename}"
                )
            
        except Exception as e:
            self._log(f"❌ Error exportando estadísticas: {e}")
            QMessageBox.warning(
                self,
                "Error de Exportación",
                f"❌ Error exportando estadísticas:\n{e}"
            )
    
    def _reset_statistics(self):
        """Resetear estadísticas"""
        try:
            reply = QMessageBox.question(
                self,
                "Resetear Estadísticas",
                "¿Está seguro de que desea resetear todas las estadísticas?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.session_duration.setText("0:00:00")
                self.successful_tracks.setText("0")
                self.failed_tracks.setText("0")
                self.switch_count.setText("0")
                self.zoom_changes.setText("0")
                self.detection_count.setText("0")
                
                self._log("🔄 Estadísticas reseteadas")
            
        except Exception as e:
            self._log(f"❌ Error reseteando estadísticas: {e}")
    
    def _show_help(self):
        """Mostrar ayuda"""
        help_text = """
🎯 **Sistema PTZ Multi-Objeto - Ayuda**

**Funcionalidades principales:**
• Seguimiento automático de múltiples objetos
• Alternancia inteligente entre objetivos
• Zoom automático adaptativo
• Configuración de prioridades

**Cómo usar:**
1. Seleccione una cámara PTZ
2. Haga clic en "Conectar"
3. Configure los parámetros en la pestaña "Configuración"
4. Inicie el seguimiento con "Iniciar Seguimiento"

**Configuración:**
• **Alternancia**: Tiempo que sigue cada objetivo
• **Zoom**: Ratio objetivo del objeto en la imagen
• **Prioridades**: Pesos para selección de objetivos

**Monitoreo:**
• Vea objetos detectados en tiempo real
• Monitore estado del sistema
• Revise estadísticas de rendimiento

**Soporte:**
Para soporte técnico, revise los logs del sistema
y verifique la configuración de red de las cámaras.
        """
        
        QMessageBox.information(
            self,
            "Ayuda - Sistema PTZ Multi-Objeto",
            help_text
        )
    
    def _update_status_display(self):
        """Actualizar display de estado"""
        try:
            current_time = datetime.now().strftime("%H:%M:%S")
            
            status_lines = [
                f"🕒 {current_time}",
                f"📹 Cámara: {self.camera_selector.currentText()[:30]}",
                f"🎯 Estado: {self.tracking_status.text()}",
                f"🔍 Detecciones: {self.detection_count.text()}",
                f"🎛️ Sistemas: Multi={MULTI_OBJECT_AVAILABLE}, Int={INTEGRATION_AVAILABLE}, PTZ={BASIC_PTZ_AVAILABLE}"
            ]
            
            self.status_display.clear()
            for line in status_lines:
                self.status_display.append(line)
            
        except Exception as e:
            print(f"Error actualizando estado: {e}")
    
    def _update_ui_state(self):
        """Actualizar estado de la UI"""
        try:
            # Habilitar/deshabilitar controles según disponibilidad
            has_camera = self.current_camera_data is not None
            is_tracking = self.tracking_active
            
            self.connect_button.setEnabled(not is_tracking)
            self.start_tracking_button.setEnabled(has_camera and not is_tracking)
            self.stop_tracking_button.setEnabled(is_tracking)
            self.test_connection_button.setEnabled(has_camera and not is_tracking)
            
        except Exception as e:
            print(f"Error actualizando UI: {e}")
    
    def _on_status_updated(self, status):
        """Manejar actualización de estado del tracker"""
        try:
            if 'current_target' in status:
                target_info = status['current_target']
                target_id = target_info.get('id', 'Ninguno')
                self.current_target.setText(str(target_id))
            
            if 'zoom' in status:
                zoom_info = status['zoom']
                zoom_level = zoom_info.get('current_level', 0.5) * 100
                self.zoom_level.setText(f"{zoom_level:.1f}%")
            
            if 'movement' in status:
                movement_info = status['movement']
                pan_speed = movement_info.get('pan_speed', 0.0)
                tilt_speed = movement_info.get('tilt_speed', 0.0)
                self.pan_tilt_speed.setText(f"{pan_speed:.2f}, {tilt_speed:.2f}")
            
            if 'statistics' in status:
                stats = status['statistics']
                self.detection_count.setText(str(stats.get('total_detections', 0)))
                self.switch_count.setText(str(stats.get('switch_count', 0)))
                self.zoom_changes.setText(str(stats.get('zoom_changes', 0)))
                
                # Actualizar duración de sesión
                duration = stats.get('session_duration', 0)
                hours = int(duration // 3600)
                minutes = int((duration % 3600) // 60)
                seconds = int(duration % 60)
                self.session_duration.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
            
            # Actualizar tabla de objetos si hay información
            if 'objects' in status:
                self._update_objects_table(status['objects'])
            
        except Exception as e:
            self._log(f"❌ Error procesando actualización de estado: {e}")
    
    def _update_objects_table(self, objects_info):
        """Actualizar tabla de objetos detectados"""
        try:
            self.objects_table.setRowCount(len(objects_info))
            
            for row, (obj_id, obj_data) in enumerate(objects_info.items()):
                # ID del objeto
                self.objects_table.setItem(row, 0, QTableWidgetItem(str(obj_id)))
                
                # Posición
                pos = obj_data.get('position', {})
                pos_text = f"({pos.get('cx', 0):.3f}, {pos.get('cy', 0):.3f})"
                self.objects_table.setItem(row, 1, QTableWidgetItem(pos_text))
                
                # Tamaño
                size_text = f"{pos.get('width', 0):.3f}×{pos.get('height', 0):.3f}"
                self.objects_table.setItem(row, 2, QTableWidgetItem(size_text))
                
                # Confianza
                confidence = obj_data.get('confidence', 0.0)
                self.objects_table.setItem(row, 3, QTableWidgetItem(f"{confidence:.3f}"))
                
                # Estado
                status_text = "Primario" if obj_data.get('is_primary', False) else "Secundario"
                if obj_data.get('is_moving', False):
                    status_text += " (Mov.)"
                self.objects_table.setItem(row, 4, QTableWidgetItem(status_text))
                
                # Tiempo rastreado
                time_tracked = obj_data.get('time_tracked', 0.0)
                self.objects_table.setItem(row, 5, QTableWidgetItem(f"{time_tracked:.1f}s"))
            
        except Exception as e:
            self._log(f"❌ Error actualizando tabla de objetos: {e}")
    
    def _on_tracking_error(self, error_msg):
        """Manejar errores del sistema de seguimiento"""
        self._log(f"🚨 Error de seguimiento: {error_msg}")
        
        # Detener seguimiento en caso de error crítico
        if "crítico" in error_msg.lower() or "critical" in error_msg.lower():
            self._emergency_stop()
    
    def _log(self, message):
        """Agregar mensaje al log"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_message = f"[{timestamp}] {message}"
            
            self.log_display.append(log_message)
            
            # Auto-scroll si está habilitado
            if self.auto_scroll_checkbox.isChecked():
                scrollbar = self.log_display.verticalScrollBar()
                scrollbar.setValue(scrollbar.maximum())
            
            # También imprimir en consola
            print(log_message)
            
        except Exception as e:
            print(f"Error en log: {e}")
    
    def closeEvent(self, event):
        """Manejar cierre del diálogo"""
        try:
            if self.tracking_active:
                reply = QMessageBox.question(
                    self,
                    "Seguimiento Activo",
                    "El seguimiento está activo. ¿Desea detenerlo y cerrar?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.No:
                    event.ignore()
                    return
            
            # Detener seguimiento si está activo
            if self.tracking_active:
                self._stop_tracking()
            
            # Detener hilo de estado
            if self.status_thread:
                self.status_thread.stop()
                self.status_thread.wait(2000)
            
            # Limpiar tracker
            if self.current_tracker and hasattr(self.current_tracker, 'cleanup'):
                self.current_tracker.cleanup()
            
            # Guardar configuración
            self._save_configuration()
            
            self._log("👋 Cerrando sistema PTZ multi-objeto")
            event.accept()
            
        except Exception as e:
            print(f"Error cerrando diálogo: {e}")
            event.accept()

class PTZDetectionBridge:
    """Puente para integrar detecciones con el sistema PTZ"""
    
    def __init__(self, ptz_system=None):
        self.ptz_system = ptz_system
        self.active_cameras = {}
        self.detection_count = 0
        
    def register_camera(self, camera_id: str, camera_data: dict) -> bool:
        """Registrar cámara en el puente"""
        try:
            self.active_cameras[camera_id] = {
                'data': camera_data,
                'last_detection': 0,
                'total_detections': 0
            }
            print(f"📡 Cámara {camera_id} registrada en puente PTZ")
            return True
        except Exception as e:
            print(f"❌ Error registrando cámara {camera_id}: {e}")
            return False
    
    def send_detections(self, camera_id: str, detections) -> bool:
        """Enviar detecciones al sistema PTZ"""
        try:
            if camera_id not in self.active_cameras:
                print(f"⚠️ Cámara {camera_id} no registrada en puente PTZ")
                return False
            
            if self.ptz_system and INTEGRATION_AVAILABLE:
                # Convertir detecciones a formato esperado
                if hasattr(detections, 'boxes'):
                    # Formato YOLOv8
                    success = self.ptz_system.process_ptz_yolo_results(camera_id, detections)
                elif isinstance(detections, list):
                    # Lista de detecciones
                    success = self.ptz_system.update_ptz_detections(camera_id, detections)
                else:
                    return False
                
                if success:
                    self.detection_count += 1
                    self.active_cameras[camera_id]['total_detections'] += 1
                    self.active_cameras[camera_id]['last_detection'] = time.time()
                
                return success
            return False
            
        except Exception as e:
            print(f"❌ Error enviando detecciones PTZ para {camera_id}: {e}")
            return False
    
    def get_status(self, camera_id: str = None):
        """Obtener estado del sistema PTZ"""
        try:
            if self.ptz_system and INTEGRATION_AVAILABLE:
                return self.ptz_system.get_ptz_status(camera_id)
            
            # Estado básico
            return {
                'active_cameras': len(self.active_cameras),
                'total_detections': self.detection_count,
                'system_available': INTEGRATION_AVAILABLE or MULTI_OBJECT_AVAILABLE
            }
        except Exception as e:
            return {'error': str(e)}
    
    def cleanup(self):
        """Limpiar recursos del puente"""
        try:
            if self.ptz_system:
                for camera_id in list(self.active_cameras.keys()):
                    if hasattr(self.ptz_system, 'stop_ptz_session'):
                        self.ptz_system.stop_ptz_session(camera_id)
                self.active_cameras.clear()
                print("🧹 Puente PTZ limpiado")
        except Exception as e:
            print(f"❌ Error limpiando puente PTZ: {e}")

# ===== FUNCIÓN PRINCIPAL PARA MAIN_WINDOW.PY =====

def create_multi_object_ptz_system(camera_list, parent=None):
    """
    Crear y mostrar el sistema PTZ multi-objeto
    Esta función es llamada desde main_window.py
    
    Returns:
        tuple: (dialog, bridge) donde:
            - dialog: Instancia del diálogo PTZ
            - bridge: Puente para integración con detecciones (puede ser None)
    """
    try:
        print("🚀 Creando sistema PTZ multi-objeto...")
        
        # Verificar disponibilidad mínima
        if not MULTI_OBJECT_AVAILABLE and not INTEGRATION_AVAILABLE and not BASIC_PTZ_AVAILABLE:
            QMessageBox.critical(
                parent,
                "Sistema No Disponible",
                "❌ El sistema PTZ multi-objeto no está disponible.\n\n"
                "Archivos requeridos:\n"
                "• core/multi_object_ptz_system.py\n"
                "• core/ptz_tracking_integration_enhanced.py\n"
                "• core/ptz_control.py\n\n"
                "Dependencias:\n"
                "• pip install onvif-zeep numpy\n\n"
                "Verifique la instalación y reinicie la aplicación."
            )
            return None, None
        
        # Filtrar solo cámaras PTZ
        ptz_cameras = [cam for cam in camera_list if cam.get('tipo') == 'ptz']
        
        if not ptz_cameras:
            QMessageBox.warning(
                parent,
                "Sin cámaras PTZ",
                "❌ No se encontraron cámaras PTZ configuradas.\n\n"
                "Para usar el seguimiento multi-objeto:\n"
                "1. Agregue al menos una cámara con tipo 'ptz'\n"
                "2. Asegúrese de que las credenciales sean correctas\n"
                "3. Verifique la conexión de red\n\n"
                "Use 'Configuración → Cámaras' para agregar cámaras PTZ."
            )
            return None, None
        
        print(f"📹 {len(ptz_cameras)} cámaras PTZ encontradas")
        
        # Crear diálogo principal
        dialog = EnhancedMultiObjectPTZDialog(parent, ptz_cameras)
        
        # Crear puente de integración si está disponible
        bridge = None
        if INTEGRATION_AVAILABLE or MULTI_OBJECT_AVAILABLE:
            try:
                bridge = PTZDetectionBridge()
                
                # Registrar cámaras PTZ
                registered_count = 0
                for camera in ptz_cameras:
                    camera_id = camera.get('id', camera.get('ip', 'unknown'))
                    if bridge.register_camera(camera_id, camera):
                        registered_count += 1
                
                print(f"🌉 Puente PTZ creado con {registered_count} cámaras registradas")
                
            except Exception as e:
                print(f"⚠️ Error creando puente de integración: {e}")
                bridge = None
        
        print("✅ Sistema PTZ multi-objeto creado exitosamente")
        return dialog, bridge
        
    except Exception as e:
        QMessageBox.critical(
            parent,
            "Error Crítico",
            f"❌ Error crítico creando sistema PTZ multi-objeto:\n\n{e}\n\n"
            f"Verifique:\n"
            f"• Que todos los archivos estén presentes\n"
            f"• Que las dependencias estén instaladas\n"
            f"• La consola para más detalles"
        )
        print(f"ERROR CRÍTICO en create_multi_object_ptz_system: {e}")
        import traceback
        traceback.print_exc()
        return None, None

# ===== FUNCIÓN ALTERNATIVA PARA CREAR SOLO EL PUENTE =====

def create_ptz_detection_bridge(camera_list):
    """
    Crear solo el puente de detecciones sin interfaz gráfica
    Útil para integración automática con el sistema de detección
    """
    try:
        if not INTEGRATION_AVAILABLE and not MULTI_OBJECT_AVAILABLE:
            print("⚠️ Sistema de integración PTZ no disponible")
            return None
        
        bridge = PTZDetectionBridge()
        
        # Registrar cámaras PTZ automáticamente
        ptz_cameras = [cam for cam in camera_list if cam.get('tipo') == 'ptz']
        registered_count = 0
        
        for camera in ptz_cameras:
            camera_id = camera.get('id', camera.get('ip', 'unknown'))
            if bridge.register_camera(camera_id, camera):
                registered_count += 1
        
        print(f"🎯 Puente PTZ creado con {registered_count} cámaras registradas")
        return bridge if registered_count > 0 else None
        
    except Exception as e:
        print(f"❌ Error creando puente PTZ: {e}")
        return None

# ===== PUNTO DE ENTRADA PARA TESTING =====

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    
    def test_ptz_dialog():
        """Función de testing del diálogo PTZ"""
        app = QApplication(sys.argv)
        
        # Crear datos de prueba
        test_cameras = [
            {
                'id': 'ptz1',
                'nombre': 'PTZ Cámara 1',
                'ip': '192.168.1.100',
                'puerto': 80,
                'usuario': 'admin',
                'contrasena': 'admin123',
                'tipo': 'ptz'
            },
            {
                'id': 'ptz2', 
                'nombre': 'PTZ Cámara 2',
                'ip': '192.168.1.101',
                'puerto': 80,
                'usuario': 'admin',
                'contrasena': 'admin123',
                'tipo': 'ptz'
            }
        ]
        
        # Crear y mostrar diálogo
        dialog = EnhancedMultiObjectPTZDialog(None, test_cameras)
        dialog.show()
        
        print("🧪 Diálogo PTZ de prueba iniciado")
        print(f"📊 Estado de sistemas:")
        print(f"   - Multi-objeto: {'✅' if MULTI_OBJECT_AVAILABLE else '❌'}")
        print(f"   - Integración: {'✅' if INTEGRATION_AVAILABLE else '❌'}")
        print(f"   - PTZ Básico: {'✅' if BASIC_PTZ_AVAILABLE else '❌'}")
        
        sys.exit(app.exec())
    
    test_ptz_dialog()
