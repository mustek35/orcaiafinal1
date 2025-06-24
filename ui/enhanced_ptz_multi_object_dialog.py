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

# Importar sistema multi-objeto
try:
    from core.multi_object_ptz_system import (
        MultiObjectPTZTracker, MultiObjectConfig, TrackingMode, ObjectPriority,
        create_multi_object_tracker, get_preset_config, PRESET_CONFIGS,
        analyze_tracking_performance
    )
    MULTI_OBJECT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Sistema multi-objeto no disponible: {e}")
    MULTI_OBJECT_AVAILABLE = False

# Importar sistema de integración
try:
    from core.ptz_tracking_integration_enhanced import (
        PTZTrackingSystemEnhanced, start_ptz_session, stop_ptz_session,
        update_ptz_detections, process_ptz_yolo_results, get_ptz_status
    )
    INTEGRATION_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Sistema de integración no disponible: {e}")
    INTEGRATION_AVAILABLE = False

# Importar sistema básico como fallback
try:
    from core.ptz_control import PTZCameraONVIF
    BASIC_PTZ_AVAILABLE = True
except ImportError:
    BASIC_PTZ_AVAILABLE = False

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
        if not MULTI_OBJECT_AVAILABLE and not INTEGRATION_AVAILABLE:
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
            self.multi_config = None
            
        self.config_file = "ptz_multi_object_ui_config.json"
        
        # Estadísticas
        self.detection_count = 0
        self.session_start_time = 0
        self.performance_history = []
        
        # Timer para actualización de UI
        self.ui_update_timer = QTimer()
        self.ui_update_timer.timeout.connect(self._update_ui_displays)
        self.ui_update_timer.start(1000)  # Cada segundo
        
        # Configurar interfaz
        self._setup_enhanced_ui()
        self._connect_all_signals()
        self._load_camera_configuration()
        self._load_ui_configuration()
        
        # Aplicar tema
        self._apply_dark_theme()
        
        self._log("🎯 Sistema PTZ Multi-Objeto inicializado")

    def closeEvent(self, event):
        """Manejar cierre del diálogo con limpieza completa de recursos"""
        print("INFO: Iniciando cierre de EnhancedMultiObjectPTZDialog...")
        
        try:
            # Detener seguimiento si está activo
            if hasattr(self, 'tracking_active') and self.tracking_active:
                self._log("🛑 Deteniendo seguimiento antes del cierre...")
                self._stop_tracking()
            
            # Detener hilo de estado
            if hasattr(self, 'status_thread') and self.status_thread:
                self.status_thread.stop()
                self.status_thread.wait(2000)  # Esperar máximo 2 segundos
                
            # Detener timer de UI
            if hasattr(self, 'ui_update_timer') and self.ui_update_timer:
                self.ui_update_timer.stop()
            
            # Limpiar tracker
            if hasattr(self, 'current_tracker') and self.current_tracker:
                try:
                    if hasattr(self.current_tracker, 'cleanup'):
                        self.current_tracker.cleanup()
                    self.current_tracker = None
                    print("INFO: Tracker PTZ limpiado")
                except Exception as e:
                    print(f"WARN: Error limpiando tracker: {e}")
            
            # Limpiar cualquier sesión PTZ activa
            if hasattr(self, 'current_camera_id') and self.current_camera_id and INTEGRATION_AVAILABLE:
                try:
                    stop_ptz_session(self.current_camera_id)
                    print(f"INFO: Sesión PTZ detenida para {self.current_camera_id}")
                except Exception as e:
                    print(f"WARN: Error deteniendo sesión PTZ: {e}")
            
            # Guardar configuración UI antes del cierre
            try:
                self._save_ui_configuration()
                if hasattr(self, '_log'):
                    self._log("💾 Configuración UI guardada")
            except Exception as e:
                print(f"WARN: Error guardando configuración UI: {e}")
            
            if hasattr(self, '_log'):
                self._log("✅ Diálogo PTZ multi-objeto cerrado correctamente")
            
        except Exception as e:
            print(f"ERROR en closeEvent: {e}")
        finally:
            # Asegurar que el evento de cierre se acepte
            print("INFO: Cierre de EnhancedMultiObjectPTZDialog completado")
            event.accept()

    def _emergency_stop(self):
        """Parada de emergencia completa del sistema"""
        try:
            if hasattr(self, '_log'):
                self._log("🚨 PARADA DE EMERGENCIA ACTIVADA")
            
            # Detener todo inmediatamente
            if hasattr(self, 'tracking_active'):
                self.tracking_active = False
            
            # Detener tracker
            if hasattr(self, 'current_tracker') and self.current_tracker:
                try:
                    if hasattr(self.current_tracker, 'emergency_stop'):
                        self.current_tracker.emergency_stop()
                    elif hasattr(self.current_tracker, 'stop_tracking'):
                        self.current_tracker.stop_tracking()
                except Exception as e:
                    print(f"Error en parada de emergencia del tracker: {e}")
            
            # Mostrar mensaje de emergencia
            if hasattr(self, 'status_display'):
                self.status_display.append("🚨 PARADA DE EMERGENCIA COMPLETADA")
                self.status_display.append("Todas las operaciones han sido interrumpidas.")
                self.status_display.append("Revise el sistema antes de continuar.")
            
            if hasattr(self, '_log'):
                self._log("✅ Parada de emergencia completada")
            
        except Exception as e:
            if hasattr(self, '_log'):
                self._log(f"❌ Error crítico en parada de emergencia: {e}")
            print(f"CRITICAL ERROR en emergency_stop: {e}")

    def _save_ui_configuration(self):
        """Guardar configuración de la UI"""
        try:
            if not hasattr(self, 'config_file'):
                self.config_file = "ptz_multi_object_ui_config.json"
            
            ui_config = {
                "window_geometry": {
                    "width": self.width(),
                    "height": self.height(),
                    "x": self.x(),
                    "y": self.y()
                },
                "last_session": {
                    "timestamp": datetime.now().isoformat() if 'datetime' in globals() else str(time.time()),
                    "total_detections": getattr(self, 'detection_count', 0)
                }
            }
            
            # Agregar configuraciones adicionales si existen
            if hasattr(self, 'camera_selector'):
                ui_config["selected_camera"] = self.camera_selector.currentText()
            if hasattr(self, 'tab_widget'):
                ui_config["current_tab"] = self.tab_widget.currentIndex()
            if hasattr(self, 'auto_scroll_checkbox'):
                ui_config["auto_scroll_enabled"] = self.auto_scroll_checkbox.isChecked()
            
            with open(self.config_file, 'w') as f:
                json.dump(ui_config, f, indent=2)
                
        except Exception as e:
            print(f"Error guardando configuración UI: {e}")

    def _setup_enhanced_ui(self):
        """Configurar interfaz de usuario completa"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Header con información del sistema
        self._setup_header_panel(layout)
        
        # Splitter principal
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Panel izquierdo: Controles
        self._setup_control_panel(main_splitter)
        
        # Panel derecho: Monitoreo
        self._setup_monitoring_panel(main_splitter)
        
        layout.addWidget(main_splitter)
        
        # Panel inferior: Estados y logs
        self._setup_status_panel(layout)
        
        # Botones de acción
        self._setup_action_buttons(layout)

    def _setup_header_panel(self, parent_layout):
        """Configurar panel superior con información del sistema"""
        header_frame = QFrame()
        header_frame.setFrameStyle(QFrame.Shape.StyledPanel)
        header_layout = QHBoxLayout(header_frame)
        
        # Título del sistema
        title_label = QLabel("🎯 Sistema PTZ Multi-Objeto Avanzado")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #4a9eff;
                padding: 5px;
            }
        """)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Indicador de estado del sistema
        self.system_status_label = QLabel("🔴 Sistema Desconectado")
        self.system_status_label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                padding: 5px 10px;
                border-radius: 15px;
                background-color: #2d1b1b;
                color: #ff6b6b;
            }
        """)
        header_layout.addWidget(self.system_status_label)
        
        parent_layout.addWidget(header_frame)

    def _setup_control_panel(self, parent_splitter):
        """Configurar panel de controles"""
        control_widget = QWidget()
        control_layout = QVBoxLayout(control_widget)
        
        # Selección de cámara
        camera_group = QGroupBox("📹 Selección de Cámara")
        camera_layout = QFormLayout(camera_group)
        
        self.camera_selector = QComboBox()
        self._populate_camera_list()
        camera_layout.addRow("Cámara PTZ:", self.camera_selector)
        
        control_layout.addWidget(camera_group)
        
        # Configuración básica si no hay sistema avanzado
        if not MULTI_OBJECT_AVAILABLE:
            basic_group = QGroupBox("⚠️ Modo Básico")
            basic_layout = QVBoxLayout(basic_group)
            basic_label = QLabel("Sistema multi-objeto no disponible.\nFuncionalidad limitada.")
            basic_label.setStyleSheet("color: #ffba08; padding: 10px;")
            basic_layout.addWidget(basic_label)
            control_layout.addWidget(basic_group)
        else:
            # Configuración de seguimiento
            tracking_group = QGroupBox("🎯 Configuración de Seguimiento")
            tracking_layout = QFormLayout(tracking_group)
            
            self.tracking_mode_combo = QComboBox()
            self.tracking_mode_combo.addItems([
                "Objeto Individual",
                "Multi-Objeto Alternante", 
                "Basado en Prioridad",
                "Cambio Automático"
            ])
            tracking_layout.addRow("Modo:", self.tracking_mode_combo)
            
            self.auto_zoom_checkbox = QCheckBox("Zoom Automático")
            self.auto_zoom_checkbox.setChecked(True)
            tracking_layout.addRow("", self.auto_zoom_checkbox)
            
            control_layout.addWidget(tracking_group)
            
            # Configuración avanzada
            advanced_group = QGroupBox("⚙️ Configuración Avanzada")
            advanced_layout = QFormLayout(advanced_group)
            
            self.confidence_threshold = QDoubleSpinBox()
            self.confidence_threshold.setRange(0.1, 1.0)
            self.confidence_threshold.setValue(0.5)
            self.confidence_threshold.setSingleStep(0.1)
            advanced_layout.addRow("Confianza mínima:", self.confidence_threshold)
            
            self.switch_interval = QSpinBox()
            self.switch_interval.setRange(1, 30)
            self.switch_interval.setValue(5)
            self.switch_interval.setSuffix(" seg")
            advanced_layout.addRow("Intervalo de cambio:", self.switch_interval)
            
            control_layout.addWidget(advanced_group)
        
        control_layout.addStretch()
        parent_splitter.addWidget(control_widget)

    def _setup_monitoring_panel(self, parent_splitter):
        """Configurar panel de monitoreo"""
        monitoring_widget = QWidget()
        monitoring_layout = QVBoxLayout(monitoring_widget)
        
        # Estadísticas en tiempo real
        stats_group = QGroupBox("📊 Estadísticas en Tiempo Real")
        stats_layout = QGridLayout(stats_group)
        
        self.detection_count_label = QLabel("0")
        self.detection_count_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4a9eff;")
        stats_layout.addWidget(QLabel("Detecciones:"), 0, 0)
        stats_layout.addWidget(self.detection_count_label, 0, 1)
        
        self.tracking_time_label = QLabel("00:00:00")
        self.tracking_time_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #4a9eff;")
        stats_layout.addWidget(QLabel("Tiempo activo:"), 1, 0)
        stats_layout.addWidget(self.tracking_time_label, 1, 1)
        
        self.current_target_label = QLabel("Ninguno")
        self.current_target_label.setStyleSheet("font-size: 14px; color: #ffba08;")
        stats_layout.addWidget(QLabel("Objetivo actual:"), 2, 0)
        stats_layout.addWidget(self.current_target_label, 2, 1)
        
        monitoring_layout.addWidget(stats_group)
        
        # Lista de objetos detectados
        objects_group = QGroupBox("🎯 Objetos Detectados")
        objects_layout = QVBoxLayout(objects_group)
        
        self.objects_table = QTableWidget()
        self.objects_table.setColumnCount(4)
        self.objects_table.setHorizontalHeaderLabels(["ID", "Tipo", "Confianza", "Estado"])
        self.objects_table.horizontalHeader().setStretchLastSection(True)
        objects_layout.addWidget(self.objects_table)
        
        monitoring_layout.addWidget(objects_group)
        
        parent_splitter.addWidget(monitoring_widget)

    def _setup_status_panel(self, parent_layout):
        """Configurar panel de estado y logs"""
        status_group = QGroupBox("📜 Estado del Sistema")
        status_layout = QVBoxLayout(status_group)
        
        self.status_display = QTextEdit()
        self.status_display.setMaximumHeight(150)
        self.status_display.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #444;
                font-family: monospace;
                font-size: 10px;
            }
        """)
        status_layout.addWidget(self.status_display)
        
        # Opciones de auto-scroll
        options_layout = QHBoxLayout()
        self.auto_scroll_checkbox = QCheckBox("Auto-scroll")
        self.auto_scroll_checkbox.setChecked(True)
        options_layout.addWidget(self.auto_scroll_checkbox)
        
        clear_btn = QPushButton("Limpiar")
        clear_btn.clicked.connect(self.status_display.clear)
        options_layout.addWidget(clear_btn)
        
        options_layout.addStretch()
        status_layout.addLayout(options_layout)
        
        parent_layout.addWidget(status_group)

    def _setup_action_buttons(self, parent_layout):
        """Configurar botones de acción"""
        button_layout = QHBoxLayout()
        
        self.start_btn = QPushButton("▶️ Iniciar Seguimiento")
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        self.start_btn.clicked.connect(self._start_tracking)
        button_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("⏸️ Detener Seguimiento")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
            QPushButton:disabled {
                background-color: #6c757d;
            }
        """)
        self.stop_btn.clicked.connect(self._stop_tracking)
        self.stop_btn.setEnabled(False)
        button_layout.addWidget(self.stop_btn)
        
        emergency_btn = QPushButton("🚨 Parada de Emergencia")
        emergency_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6b6b;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ff5252;
            }
        """)
        emergency_btn.clicked.connect(self._emergency_stop)
        button_layout.addWidget(emergency_btn)
        
        button_layout.addStretch()
        
        close_btn = QPushButton("❌ Cerrar")
        close_btn.clicked.connect(self.close)
        button_layout.addWidget(close_btn)
        
        parent_layout.addLayout(button_layout)

    def _populate_camera_list(self):
        """Poblar lista de cámaras PTZ disponibles"""
        self.camera_selector.clear()
        self.camera_selector.addItem("Seleccionar cámara...")
        
        for camera in self.all_cameras:
            if camera.get('tipo') == 'ptz':
                camera_name = f"{camera.get('nombre', 'Sin nombre')} - {camera.get('ip', 'Sin IP')}"
                self.camera_selector.addItem(camera_name, camera)

    def _connect_all_signals(self):
        """Conectar todas las señales de la interfaz"""
        self.camera_selector.currentIndexChanged.connect(self._on_camera_changed)
        if hasattr(self, 'tracking_mode_combo'):
            self.tracking_mode_combo.currentTextChanged.connect(self._on_mode_changed)
        if hasattr(self, 'confidence_threshold'):
            self.confidence_threshold.valueChanged.connect(self._on_config_changed)
        if hasattr(self, 'switch_interval'):
            self.switch_interval.valueChanged.connect(self._on_config_changed)

    def _load_camera_configuration(self):
        """Cargar configuración de cámaras"""
        pass  # Implementar según necesidades

    def _load_ui_configuration(self):
        """Cargar configuración de la UI"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    
                # Restaurar geometría de ventana
                geom = config.get('window_geometry', {})
                if geom:
                    self.resize(geom.get('width', 900), geom.get('height', 700))
                    self.move(geom.get('x', 100), geom.get('y', 100))
                    
        except Exception as e:
            print(f"Error cargando configuración UI: {e}")

    def _apply_dark_theme(self):
        """Aplicar tema oscuro a la interfaz"""
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #444;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QComboBox, QSpinBox, QDoubleSpinBox {
                padding: 5px;
                border: 1px solid #444;
                border-radius: 3px;
                background-color: #3b3b3b;
                color: #ffffff;
            }
            QCheckBox {
                spacing: 5px;
            }
            QTableWidget {
                gridline-color: #444;
                background-color: #3b3b3b;
                alternate-background-color: #404040;
            }
            QHeaderView::section {
                background-color: #555;
                color: #ffffff;
                padding: 5px;
                border: 1px solid #444;
            }
        """)

    def _log(self, message):
        """Agregar mensaje al log del sistema"""
        if hasattr(self, 'status_display'):
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {message}"
            self.status_display.append(formatted_message)
            
            if hasattr(self, 'auto_scroll_checkbox') and self.auto_scroll_checkbox.isChecked():
                self.status_display.ensureCursorVisible()

    def _start_tracking(self):
        """Iniciar seguimiento PTZ multi-objeto"""
        try:
            if self.camera_selector.currentIndex() == 0:
                QMessageBox.warning(self, "Error", "Seleccione una cámara PTZ")
                return
            
            camera_data = self.camera_selector.currentData()
            if not camera_data:
                QMessageBox.warning(self, "Error", "Datos de cámara no válidos")
                return
            
            self._log("🚀 Iniciando sistema de seguimiento PTZ...")
            
            # Crear y configurar tracker si está disponible
            if MULTI_OBJECT_AVAILABLE:
                self.current_tracker = create_multi_object_tracker(camera_data, self.multi_config)
                if self.current_tracker:
                    success = self.current_tracker.start_tracking()
                    if not success:
                        raise Exception("Error iniciando tracker")
            
            # Configurar UI para estado activo
            self.tracking_active = True
            self.session_start_time = time.time()
            self.detection_count = 0
            
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.system_status_label.setText("🟢 Sistema Activo")
            self.system_status_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    padding: 5px 10px;
                    border-radius: 15px;
                    background-color: #1b2d1b;
                    color: #28a745;
                }
            """)
            
            # Iniciar hilo de actualización de estado
            if self.current_tracker:
                self.status_thread = StatusUpdateThread(self.current_tracker)
                self.status_thread.status_updated.connect(self._update_status_display)
                self.status_thread.error_occurred.connect(self._handle_tracking_error)
                self.status_thread.start()
            
            self._log("✅ Seguimiento PTZ multi-objeto iniciado exitosamente")
            self.tracking_started.emit()
            
        except Exception as e:
            self._log(f"❌ Error iniciando seguimiento: {e}")
            QMessageBox.critical(self, "Error", f"Error iniciando seguimiento:\n{e}")
            self._cleanup_after_error()

    def _stop_tracking(self):
        """Detener seguimiento PTZ"""
        try:
            self._log("🛑 Deteniendo seguimiento PTZ...")
            
            # Detener tracker
            if self.current_tracker:
                self.current_tracker.stop_tracking()
                if hasattr(self.current_tracker, 'cleanup'):
                    self.current_tracker.cleanup()
                self.current_tracker = None
            
            # Detener hilo de estado
            if self.status_thread:
                self.status_thread.stop()
                self.status_thread.wait(2000)
                self.status_thread = None
            
            # Actualizar UI
            self.tracking_active = False
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.system_status_label.setText("🔴 Sistema Detenido")
            self.system_status_label.setStyleSheet("""
                QLabel {
                    font-size: 12px;
                    padding: 5px 10px;
                    border-radius: 15px;
                    background-color: #2d1b1b;
                    color: #ff6b6b;
                }
            """)
            
            self._log("✅ Seguimiento PTZ detenido")
            self.tracking_stopped.emit()
            
        except Exception as e:
            self._log(f"❌ Error deteniendo seguimiento: {e}")

    def _cleanup_after_error(self):
        """Limpiar recursos después de un error"""
        self.tracking_active = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        
        if self.current_tracker:
            try:
                if hasattr(self.current_tracker, 'cleanup'):
                    self.current_tracker.cleanup()
            except:
                pass
            self.current_tracker = None
        
        if self.status_thread:
            try:
                self.status_thread.stop()
                self.status_thread.wait(1000)
            except:
                pass
            self.status_thread = None

    def _update_status_display(self, status_data):
        """Actualizar display de estado con datos del tracker"""
        if not status_data:
            return
            
        try:
            # Actualizar estadísticas
            if 'detection_count' in status_data:
                self.detection_count_label.setText(str(status_data['detection_count']))
            
            if 'tracking_time' in status_data:
                self.tracking_time_label.setText(status_data['tracking_time'])
            
            if 'current_target' in status_data:
                target_info = status_data['current_target']
                if target_info:
                    target_text = f"ID: {target_info.get('id', 'N/A')} - {target_info.get('class', 'Desconocido')}"
                    self.current_target_label.setText(target_text)
                else:
                    self.current_target_label.setText("Ninguno")
            
            # Actualizar tabla de objetos
            if 'detected_objects' in status_data:
                self._update_objects_table(status_data['detected_objects'])
                
        except Exception as e:
            print(f"Error actualizando display de estado: {e}")

    def _update_objects_table(self, objects):
        """Actualizar tabla de objetos detectados"""
        try:
            self.objects_table.setRowCount(len(objects))
            
            for i, obj in enumerate(objects):
                # ID del objeto
                id_item = QTableWidgetItem(str(obj.get('id', i)))
                self.objects_table.setItem(i, 0, id_item)
                
                # Tipo/clase del objeto
                type_item = QTableWidgetItem(obj.get('class', 'Desconocido'))
                self.objects_table.setItem(i, 1, type_item)
                
                # Confianza
                confidence = obj.get('confidence', 0)
                conf_item = QTableWidgetItem(f"{confidence:.2f}")
                self.objects_table.setItem(i, 2, conf_item)
                
                # Estado (siendo seguido, detectado, perdido)
                status = obj.get('status', 'detectado')
                status_item = QTableWidgetItem(status)
                
                # Colorear según estado
                if status == 'siguiendo':
                    status_item.setBackground(QColor('#28a745'))
                elif status == 'perdido':
                    status_item.setBackground(QColor('#dc3545'))
                else:
                    status_item.setBackground(QColor('#ffc107'))
                    
                self.objects_table.setItem(i, 3, status_item)
                
        except Exception as e:
            print(f"Error actualizando tabla de objetos: {e}")

    def _handle_tracking_error(self, error_message):
        """Manejar errores del sistema de seguimiento"""
        self._log(f"❌ Error en seguimiento: {error_message}")
        
        # Detener seguimiento si hay error crítico
        if "crítico" in error_message.lower() or "critical" in error_message.lower():
            self._stop_tracking()
            QMessageBox.critical(self, "Error Crítico", f"Error crítico en seguimiento:\n{error_message}")

    def _update_ui_displays(self):
        """Actualizar displays de la UI cada segundo"""
        if self.tracking_active and self.session_start_time > 0:
            # Calcular tiempo de sesión
            elapsed = time.time() - self.session_start_time
            hours = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = int(elapsed % 60)
            time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            self.tracking_time_label.setText(time_str)

    def _on_camera_changed(self, index):
        """Manejar cambio de cámara seleccionada"""
        if index > 0:  # Ignorar "Seleccionar cámara..."
            camera_data = self.camera_selector.currentData()
            self.current_camera_data = camera_data
            self.current_camera_id = camera_data.get('id') if camera_data else None
            self._log(f"📹 Cámara seleccionada: {camera_data.get('nombre', 'Sin nombre')}")

    def _on_mode_changed(self, mode_text):
        """Manejar cambio de modo de seguimiento"""
        if MULTI_OBJECT_AVAILABLE and self.multi_config:
            mode_map = {
                "Objeto Individual": TrackingMode.SINGLE_OBJECT,
                "Multi-Objeto Alternante": TrackingMode.MULTI_OBJECT_ALTERNATING,
                "Basado en Prioridad": TrackingMode.MULTI_OBJECT_PRIORITY,
                "Cambio Automático": TrackingMode.AUTO_SWITCH
            }
            
            if mode_text in mode_map:
                self.multi_config.tracking_mode = mode_map[mode_text]
                self._log(f"🎯 Modo de seguimiento: {mode_text}")

    def _on_config_changed(self):
        """Manejar cambios en configuración"""
        if MULTI_OBJECT_AVAILABLE and self.multi_config:
            if hasattr(self, 'confidence_threshold'):
                self.multi_config.min_confidence_threshold = self.confidence_threshold.value()
            if hasattr(self, 'switch_interval'):
                self.multi_config.primary_follow_time = self.switch_interval.value()
            self._log("⚙️ Configuración actualizada")

    def _show_error_dialog(self):
        """Mostrar diálogo de error cuando no hay sistemas disponibles"""
        layout = QVBoxLayout()
        
        error_label = QLabel(
            "❌ Sistema PTZ Multi-Objeto No Disponible\n\n"
            "Archivos requeridos faltantes:\n"
            "• core/multi_object_ptz_system.py\n"
            "• core/ptz_tracking_integration_enhanced.py\n\n"
            "Dependencias requeridas:\n"
            "• onvif-zeep\n"
            "• numpy\n"
            "• PyQt6\n\n"
            "Instale las dependencias:\n"
            "pip install onvif-zeep numpy"
        )
        error_label.setStyleSheet("""
            QLabel {
                color: #ff6b6b;
                font-size: 12px;
                padding: 20px;
                background-color: #2d1b1b;
                border: 2px solid #ff6b6b;
                border-radius: 8px;
            }
        """)
        layout.addWidget(error_label)
        
        close_btn = QPushButton("Cerrar")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff6b6b;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ff5252;
            }
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)


# ===== CLASE PARA MANEJAR INTEGRACIÓN CON DETECCIONES =====

class PTZDetectionBridge:
    """
    Puente para conectar detecciones YOLO con sistema PTZ multi-objeto
    Esta clase facilita la integración desde main_window.py
    """
    
    def __init__(self, ptz_system=None):
        self.ptz_system = ptz_system
        self.active_cameras = {}
        self.detection_count = 0
        
    def register_camera(self, camera_id: str, camera_data: dict):
        """Registrar una cámara para seguimiento PTZ"""
        try:
            if self.ptz_system and INTEGRATION_AVAILABLE:
                success = self.ptz_system.start_ptz_session(camera_id, camera_data)
                if success:
                    self.active_cameras[camera_id] = camera_data
                    print(f"✅ Cámara PTZ registrada: {camera_id}")
                    return True
            return False
        except Exception as e:
            print(f"❌ Error registrando cámara PTZ {camera_id}: {e}")
            return False
    
    def send_detections(self, camera_id: str, detections):
        """Enviar detecciones al sistema PTZ"""
        try:
            if (self.ptz_system and camera_id in self.active_cameras and 
                INTEGRATION_AVAILABLE):
                
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
            return {'error': 'Sistema PTZ no disponible'}
        except Exception as e:
            return {'error': str(e)}
    
    def cleanup(self):
        """Limpiar recursos del puente"""
        try:
            if self.ptz_system:
                for camera_id in list(self.active_cameras.keys()):
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
        # Verificar disponibilidad de sistemas
        if not MULTI_OBJECT_AVAILABLE and not INTEGRATION_AVAILABLE:
            QMessageBox.warning(
                parent,
                "Sistema No Disponible",
                "❌ Sistema PTZ multi-objeto no disponible.\n\n"
                "Archivos requeridos:\n"
                "• core/multi_object_ptz_system.py\n"
                "• core/ptz_tracking_integration_enhanced.py\n\n"
                "Dependencias:\n"
                "• pip install onvif-zeep numpy\n\n"
                "El sistema funcionará en modo básico."
            )
            # Aún así crear el diálogo para funcionalidad básica
        
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
                "3. Verifique la conexión de red"
            )
            return None, None
        
        # Crear diálogo principal
        dialog = EnhancedMultiObjectPTZDialog(parent, ptz_cameras)
        
        # Crear puente de integración si está disponible
        bridge = None
        if INTEGRATION_AVAILABLE:
            try:
                from core.ptz_tracking_integration_enhanced import get_ptz_system
                ptz_system = get_ptz_system()
                bridge = PTZDetectionBridge(ptz_system)
                
                # Inicializar sesiones para cámaras PTZ
                registered_count = 0
                for camera in ptz_cameras:
                    camera_id = camera.get('id', camera.get('ip', 'unknown'))
                    if bridge.register_camera(camera_id, camera):
                        registered_count += 1
                
                print(f"🎯 Puente PTZ creado con {registered_count} cámaras registradas")
                    
            except Exception as e:
                print(f"⚠️ Error creando puente de integración: {e}")
                bridge = None
        
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
        if not INTEGRATION_AVAILABLE:
            print("⚠️ Sistema de integración PTZ no disponible")
            return None
        
        from core.ptz_tracking_integration_enhanced import get_ptz_system
        ptz_system = get_ptz_system()
        bridge = PTZDetectionBridge(ptz_system)
        
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
    
    app = QApplication(sys.argv)
    
    # Datos de cámara de prueba
    test_cameras = [
        {
            'id': 'cam1',
            'nombre': 'Cámara PTZ Test 1',
            'tipo': 'ptz',
            'ip': '192.168.1.100',
            'puerto': 80,
            'usuario': 'admin',
            'password': 'admin123'
        },
        {
            'id': 'cam2', 
            'nombre': 'Cámara PTZ Test 2',
            'tipo': 'ptz',
            'ip': '192.168.1.101',
            'puerto': 80,
            'usuario': 'admin',
            'password': 'admin123'
        }
    ]
    
    # Crear sistema completo
    dialog, bridge = create_multi_object_ptz_system(test_cameras, None)
    
    if dialog:
        dialog.show()
        print("✅ Sistema PTZ multi-objeto iniciado para testing")
        
        # Simular algunas detecciones si hay puente
        if bridge:
            test_detections = [
                {
                    'cx': 960, 'cy': 540,
                    'width': 100, 'height': 150,
                    'confidence': 0.85, 'class': 'person',
                    'frame_w': 1920, 'frame_h': 1080
                }
            ]
            bridge.send_detections('cam1', test_detections)
            print("🎯 Detecciones de prueba enviadas")
        
        sys.exit(app.exec())
    else:
        print("❌ No se pudo crear el sistema PTZ multi-objeto")
        sys.exit(1)
