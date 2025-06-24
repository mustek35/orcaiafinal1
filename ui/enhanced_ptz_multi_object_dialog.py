# ui/enhanced_ptz_multi_object_dialog.py
"""""""
Diálogo PTZ mejorado con seguimiento multi-objeto y zoom inteligente
Interfaz completa para control avanzado de cámaras PTZ con capacidades:
- Seguimiento de múltiples objetos con alternancia
- Zoom automático inteligente  
- Configuración de prioridades
- Monitoreo en tiempo real
- Estadísticas y análisis
""""""""

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
    print(f"⚠️ Sistema multi-objeto no disponible: {e}")"
    MULTI_OBJECT_AVAILABLE = False

# Importar sistema de integración
try:
    from core.ptz_tracking_integration_enhanced import (
        PTZTrackingSystemEnhanced, start_ptz_session, stop_ptz_session,
        update_ptz_detections, process_ptz_yolo_results, get_ptz_status
    )
    INTEGRATION_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Sistema de integración no disponible: {e}")"
    INTEGRATION_AVAILABLE = False

# Importar sistema básico como fallback
try:
    from core.ptz_control import PTZCameraONVIF
    BASIC_PTZ_AVAILABLE = True
except ImportError:
    BASIC_PTZ_AVAILABLE = False

class StatusUpdateThread(QThread):
    """Hilo para actualizar estado del sistema PTZ - VERSIÓN MEJORADA""""
    status_updated = pyqtSignal(dict)
    
    def __init__(self, camera_id: str):
        super().__init__()
        self.camera_id = camera_id
        self.running = True
        self._should_stop = False
    
    def run(self):
        """Ejecutar hilo con manejo mejorado de errores""""
        try:
            while self.running and not self._should_stop:
                try:
                    if INTEGRATION_AVAILABLE and self.camera_id:
                        status = get_ptz_status(self.camera_id)
                        if status and self.running:
                            self.status_updated.emit(status)
                    
                    # Usar QThread.msleep para mejor integración con Qt
                    if not self._should_stop:
                        self.msleep(500)  # 500ms
                        
                except Exception as e:
                    print(f"Error en status thread (recuperable): {e}")"
                    if not self._should_stop:
                        self.msleep(1000)  # Esperar más tiempo en caso de error
                        
        except Exception as e:
            print(f"Error crítico en status thread: {e}")"
        finally:
            print("INFO: StatusUpdateThread terminando...")"
    
    def stop(self):
        """Detener hilo de forma segura""""
        print("INFO: Deteniendo StatusUpdateThread...")"
        self._should_stop = True
        self.running = False
        
        # Despertar el hilo si está durmiendo
        self.requestInterruption()
        
        # Esperar a que termine
        if not self.wait(3000):  # Esperar máximo 3 segundos
            print("WARN: StatusUpdateThread no terminó en tiempo esperado")"
            self.terminate()  # Forzar terminación como último recurso
            self.wait(1000)  # Dar tiempo para la terminación forzada
        
        print("INFO: StatusUpdateThread detenido")"
class EnhancedMultiObjectPTZDialog(QDialog):
    """Diálogo PTZ avanzado con capacidades multi-objeto y zoom inteligente""""
    
    # Señales para comunicación entre hilos
    object_detected = pyqtSignal(int, dict)
    object_lost = pyqtSignal(int)
    target_switched = pyqtSignal(int, int)
    zoom_changed = pyqtSignal(float, float)
    tracking_stats_updated = pyqtSignal(dict)
    
    def __init__(self, parent=None, camera_list=None):
        super().__init__(parent)
        self.setWindowTitle("🎯 Control PTZ Multi-Objeto Avanzado")"
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
        self.current_tracker: Optional[MultiObjectPTZTracker] = None
        self.status_thread: Optional[StatusUpdateThread] = None
        
        # Configuración
        self.multi_config = MultiObjectConfig()
        self.config_file = "ptz_multi_object_ui_config.json""
        
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
        
        self._log("🎯 Sistema PTZ Multi-Objeto inicializado")"

    def closeEvent(self, event):
        """Manejar cierre del diálogo con limpieza completa de recursos""""
        print("INFO: Iniciando cierre de EnhancedMultiObjectPTZDialog...")"
        
        try:
            # Detener seguimiento si está activo
            if hasattr(self, 'tracking_active') and self.tracking_active:'
                self._log("🛑 Deteniendo seguimiento antes del cierre...")"
                self._stop_multi_object_tracking()
            
            # Detener hilo de actualización de estado
            if hasattr(self, 'status_thread') and self.status_thread:'
                self._log("🧹 Deteniendo hilo de estado...")"
                try:
                    self.status_thread.stop()
                    if self.status_thread.isRunning():
                        self.status_thread.wait(3000)  # Esperar máximo 3 segundos
                    self.status_thread = None
                    print("INFO: Hilo de estado detenido")"
                except Exception as e:
                    print(f"WARN: Error deteniendo hilo de estado: {e}")"
            
            # Detener timer de UI
            if hasattr(self, 'ui_update_timer') and self.ui_update_timer:'
                self._log("⏰ Deteniendo timer de UI...")"
                try:
                    self.ui_update_timer.stop()
                    print("INFO: Timer de UI detenido")"
                except Exception as e:
                    print(f"WARN: Error deteniendo timer UI: {e}")"
            
            # Limpiar tracker actual
            if hasattr(self, 'current_tracker') and self.current_tracker:'
                self._log("🎯 Limpiando tracker PTZ...")"
                try:
                    # Intentar diferentes métodos de limpieza
                    if hasattr(self.current_tracker, 'cleanup'):'
                        self.current_tracker.cleanup()
                    elif hasattr(self.current_tracker, 'stop'):'
                        self.current_tracker.stop()
                    elif hasattr(self.current_tracker, 'close'):'
                        self.current_tracker.close()
                    
                    # Detener cualquier hilo interno del tracker
                    if hasattr(self.current_tracker, '_tracking_thread'):'
                        if self.current_tracker._tracking_thread and self.current_tracker._tracking_thread.is_alive():
                            self.current_tracker._tracking_thread.join(timeout=2)
                    
                    self.current_tracker = None
                    print("INFO: Tracker PTZ limpiado")"
                except Exception as e:
                    print(f"WARN: Error limpiando tracker: {e}")"
            
            # Limpiar cualquier sesión PTZ activa
            if hasattr(self, 'current_camera_id') and self.current_camera_id and INTEGRATION_AVAILABLE:'
                try:
                    from core.ptz_tracking_integration_enhanced import stop_ptz_session
                    stop_ptz_session(self.current_camera_id)
                    print(f"INFO: Sesión PTZ detenida para {self.current_camera_id}")"
                except Exception as e:
                    print(f"WARN: Error deteniendo sesión PTZ: {e}")"
            
            # Guardar configuración UI antes del cierre
            try:
                self._save_ui_configuration()
                if hasattr(self, '_log'):'
                    self._log("💾 Configuración UI guardada")"
            except Exception as e:
                print(f"WARN: Error guardando configuración UI: {e}")"
            
            if hasattr(self, '_log'):'
                self._log("✅ Diálogo PTZ multi-objeto cerrado correctamente")"
            
        except Exception as e:
            print(f"ERROR en closeEvent: {e}")"
        finally:
            # Asegurar que el evento de cierre se acepte
            print("INFO: Cierre de EnhancedMultiObjectPTZDialog completado")"
            event.accept()

    def _emergency_stop(self):
        """Parada de emergencia completa del sistema""""
        try:
            if hasattr(self, '_log'):'
                self._log("🚨 PARADA DE EMERGENCIA ACTIVADA")"
            
            # Detener todo inmediatamente
            if hasattr(self, 'tracking_active'):'
                self.tracking_active = False
            
            # Detener tracker
            if hasattr(self, 'current_tracker') and self.current_tracker:'
                try:
                    if hasattr(self.current_tracker, 'emergency_stop'):'
                        self.current_tracker.emergency_stop()
                    elif hasattr(self.current_tracker, 'stop'):'
                        self.current_tracker.stop()
                    self.current_tracker = None
                except Exception as e:
                    if hasattr(self, '_log'):'
                        self._log(f"⚠️ Error en parada de emergencia del tracker: {e}")"
            
            # Detener hilo de estado
            if hasattr(self, 'status_thread') and self.status_thread:'
                try:
                    self.status_thread.stop()
                    self.status_thread = None
                except Exception as e:
                    if hasattr(self, '_log'):'
                        self._log(f"⚠️ Error deteniendo hilo en emergencia: {e}")"
            
            # Detener timer
            if hasattr(self, 'ui_update_timer') and self.ui_update_timer:'
                self.ui_update_timer.stop()
            
            # Detener sesión PTZ
            if (hasattr(self, 'current_camera_id') and self.current_camera_id and '
                'INTEGRATION_AVAILABLE' in globals() and INTEGRATION_AVAILABLE):'
                try:
                    from core.ptz_tracking_integration_enhanced import stop_ptz_session
                    stop_ptz_session(self.current_camera_id)
                except Exception as e:
                    if hasattr(self, '_log'):'
                        self._log(f"⚠️ Error deteniendo sesión PTZ en emergencia: {e}")"
            
            # Actualizar UI si existe
            if hasattr(self, 'btn_start_tracking'):'
                self.btn_start_tracking.setEnabled(True)
            if hasattr(self, 'btn_stop_tracking'):'
                self.btn_stop_tracking.setEnabled(False)
            if hasattr(self, 'tracking_indicator'):'
                self.tracking_indicator.setText("🚨 PARADA DE EMERGENCIA")"
                self.tracking_indicator.setStyleSheet("color: #d32f2f; font-weight: bold;")"
            
            # Mostrar mensaje
            if 'QMessageBox' in globals():'
                QMessageBox.warning(
                    self,
                    "Parada de Emergencia","
                    "🚨 Sistema PTZ detenido por emergencia."

""
                    "Todas las operaciones han sido interrumpidas."
""
                    "Revise el sistema antes de continuar.""
                )
            
            if hasattr(self, '_log'):'
                self._log("✅ Parada de emergencia completada")"
            
        except Exception as e:
            if hasattr(self, '_log'):'
                self._log(f"❌ Error crítico en parada de emergencia: {e}")"
            print(f"CRITICAL ERROR en emergency_stop: {e}")"

    def cleanup_resources(self):
        """Método específico para limpiar todos los recursos""""
        try:
            # Detener todas las operaciones en curso
            if hasattr(self, 'tracking_active') and self.tracking_active:'
                self.tracking_active = False
            
            # Limpiar hilos
            if hasattr(self, 'status_thread') and self.status_thread:'
                self.status_thread.stop()
                self.status_thread.wait(2000)
                self.status_thread = None
            
            # Limpiar timers
            if hasattr(self, 'ui_update_timer') and self.ui_update_timer:'
                self.ui_update_timer.stop()
                self.ui_update_timer = None
            
            # Limpiar tracker
            if hasattr(self, 'current_tracker') and self.current_tracker:'
                if hasattr(self.current_tracker, 'cleanup'):'
                    self.current_tracker.cleanup()
                self.current_tracker = None
            
            print("INFO: Recursos del diálogo PTZ limpiados exitosamente")"
            
        except Exception as e:
            print(f"ERROR limpiando recursos: {e}")"

    def _save_ui_configuration(self):
        """Guardar configuración de la UI""""
        try:
            if not hasattr(self, 'config_file'):'
                self.config_file = "ptz_multi_object_ui_config.json""
            
            ui_config = {
                "window_geometry": {"
                    "width": self.width(),"
                    "height": self.height(),"
                    "x": self.x(),"
                    "y": self.y()"
                },
                "last_session": {"
                    "timestamp": datetime.now().isoformat() if 'datetime' in globals() else str(time.time()),"'
                    "total_detections": getattr(self, 'detection_count', 0)"'
                }
            }
            
            # Agregar configuraciones adicionales si existen
            if hasattr(self, 'camera_selector'):'
                ui_config["selected_camera"] = self.camera_selector.currentText()"
            if hasattr(self, 'tab_widget'):'
                ui_config["current_tab"] = self.tab_widget.currentIndex()"
            if hasattr(self, 'auto_scroll_checkbox'):'
                ui_config["auto_scroll_enabled"] = self.auto_scroll_checkbox.isChecked()"
            
            import json
            with open(self.config_file, 'w') as f:'
                json.dump(ui_config, f, indent=2)
                
        except Exception as e:
            print(f"Error guardando configuración UI: {e}")"
    
    def _show_error_dialog(self):
        """Mostrar diálogo de error cuando no hay sistemas disponibles""""
        layout = QVBoxLayout()
        
        error_label = QLabel(
            "❌ Sistema PTZ Multi-Objeto No Disponible\n"\n"
            "Archivos requeridos faltantes:\n""
            "• core/multi_object_ptz_system.py\n""
            "• core/ptz_tracking_integration_enhanced.py\n"\n"
            "Dependencias requeridas:\n""
            "• onvif-zeep\n""
            "• numpy\n""
            "• PyQt6\n"\n"
            "Instale las dependencias:\n""
            "pip install onvif-zeep numpy""
        )
        error_label.setStyleSheet("""""""
            QLabel {
                color: #ff6b6b;
                font-size: 12px;
                padding: 20px;
                background-color: #2d1b1b;
                border: 2px solid #ff6b6b;
                border-radius: 8px;
            }
        """)""""
        layout.addWidget(error_label)
        
        close_btn = QPushButton("Cerrar")"
        close_btn.setStyleSheet("""""""
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
        """)""""
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)
    
    def _setup_enhanced_ui(self):
        """Configurar interfaz de usuario completa""""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Header con información del sistema
        self._setup_header_panel(layout)
        
        # Splitter principal
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Panel izquierdo - Controles
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        # Selector de cámara
        self._setup_camera_selector(left_layout)
        
        # Pestañas de control
        self._setup_control_tabs(left_layout)
        
        main_splitter.addWidget(left_widget)
        
        # Panel derecho - Monitoreo
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Estado del sistema
        self._setup_system_status(right_layout)
        
        # Estadísticas en tiempo real
        self._setup_realtime_stats(right_layout)
        
        main_splitter.addWidget(right_widget)
        
        # Configurar proporciones del splitter
        main_splitter.setSizes([600, 300])
        layout.addWidget(main_splitter)
        
        # Panel inferior - Logs y controles
        self._setup_bottom_panel(layout)
    
    def _setup_header_panel(self, layout):
        """Configurar panel superior con información del sistema""""
        header_frame = QFrame()
        header_frame.setFrameStyle(QFrame.Shape.Box)
        header_frame.setStyleSheet("""""""
            QFrame {
                background-color: #2b2b2b;
                border: 1px solid #555;
                border-radius: 8px;
                padding: 5px;
            }
        """)""""
        
        header_layout = QHBoxLayout(header_frame)
        
        # Título
        title_label = QLabel("🎯 Sistema PTZ Multi-Objeto Avanzado")"
        title_label.setStyleSheet("""""""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #4CAF50;
                border: none;
            }
        """)""""
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Estado de conexión
        self.connection_indicator = QLabel("🔴 Desconectado")"
        self.connection_indicator.setStyleSheet("""""""
            QLabel {
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                border: none;
            }
        """)""""
        header_layout.addWidget(self.connection_indicator)
        
        # Estado de seguimiento
        self.tracking_indicator = QLabel("⏹️ Inactivo")"
        self.tracking_indicator.setStyleSheet("""""""
            QLabel {
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                border: none;
            }
        """)""""
        header_layout.addWidget(self.tracking_indicator)
        
        layout.addWidget(header_frame)
    
    def _setup_camera_selector(self, layout):
        """Configurar selector de cámara""""
        camera_group = QGroupBox("📹 Selección de Cámara")"
        camera_layout = QVBoxLayout()
        
        # Selector principal
        selector_layout = QHBoxLayout()
        
        self.camera_selector = QComboBox()
        self.camera_selector.setMinimumHeight(30)
        self.camera_selector.currentTextChanged.connect(self._on_camera_changed)
        selector_layout.addWidget(QLabel("Cámara:"))"
        selector_layout.addWidget(self.camera_selector)
        
        # Botón de test
        self.btn_test_connection = QPushButton("🔧 Probar")"
        self.btn_test_connection.setMaximumWidth(80)
        self.btn_test_connection.clicked.connect(self._test_camera_connection)
        selector_layout.addWidget(self.btn_test_connection)
        
        camera_layout.addLayout(selector_layout)
        
        # Información de cámara
        self.camera_info_label = QLabel("Seleccione una cámara para ver detalles")"
        self.camera_info_label.setStyleSheet("color: #888; font-size: 11px; padding: 5px;")"
        self.camera_info_label.setWordWrap(True)
        camera_layout.addWidget(self.camera_info_label)
        
        camera_group.setLayout(camera_layout)
        layout.addWidget(camera_group)
    
    def _setup_control_tabs(self, layout):
        """Configurar pestañas de control""""
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        
        # Pestaña de seguimiento multi-objeto
        self._setup_multi_object_tab()
        
        # Pestaña de control manual
        self._setup_manual_control_tab()
        
        # Pestaña de configuración avanzada
        self._setup_advanced_config_tab()
        
        # Pestaña de análisis
        self._setup_analysis_tab()
        
        layout.addWidget(self.tab_widget)
    
    def _setup_multi_object_tab(self):
        """Configurar pestaña de seguimiento multi-objeto""""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Configuración principal
        main_config_group = QGroupBox("🎯 Configuración de Seguimiento")"
        main_config_layout = QFormLayout()
        
        # Preset inicial
        self.preset_selector = QSpinBox()
        self.preset_selector.setRange(1, 255)
        self.preset_selector.setValue(1)
        main_config_layout.addRow("Preset inicial:", self.preset_selector)"
        
        # Configuración predefinida
        self.config_preset_combo = QComboBox()
        self.config_preset_combo.addItems(list(PRESET_CONFIGS.keys()) if MULTI_OBJECT_AVAILABLE else ["Básico"])"
        self.config_preset_combo.setCurrentText("maritime_patrol")"
        self.config_preset_combo.currentTextChanged.connect(self._load_preset_config)
        main_config_layout.addRow("Configuración:", self.config_preset_combo)"
        
        main_config_group.setLayout(main_config_layout)
        layout.addWidget(main_config_group)
        
        # Configuración de alternancia
        alternating_group = QGroupBox("🔄 Alternancia de Objetos")"
        alternating_layout = QFormLayout()
        
        self.alternating_enabled = QCheckBox("Habilitar alternancia entre objetos")"
        self.alternating_enabled.setChecked(True)
        self.alternating_enabled.toggled.connect(self._update_config_from_ui)
        alternating_layout.addRow("", self.alternating_enabled)"
        
        self.primary_time_spinbox = QDoubleSpinBox()
        self.primary_time_spinbox.setRange(1.0, 60.0)
        self.primary_time_spinbox.setValue(5.0)
        self.primary_time_spinbox.setSuffix(" seg")"
        self.primary_time_spinbox.valueChanged.connect(self._update_config_from_ui)
        alternating_layout.addRow("Tiempo objetivo principal:", self.primary_time_spinbox)"
        
        self.secondary_time_spinbox = QDoubleSpinBox()
        self.secondary_time_spinbox.setRange(1.0, 60.0)
        self.secondary_time_spinbox.setValue(3.0)
        self.secondary_time_spinbox.setSuffix(" seg")"
        self.secondary_time_spinbox.valueChanged.connect(self._update_config_from_ui)
        alternating_layout.addRow("Tiempo objetivo secundario:", self.secondary_time_spinbox)"
        
        alternating_group.setLayout(alternating_layout)
        layout.addWidget(alternating_group)
        
        # Configuración de zoom
        zoom_group = QGroupBox("🔍 Zoom Automático")"
        zoom_layout = QFormLayout()
        
        self.auto_zoom_enabled = QCheckBox("Habilitar zoom automático")"
        self.auto_zoom_enabled.setChecked(True)
        self.auto_zoom_enabled.toggled.connect(self._update_config_from_ui)
        zoom_layout.addRow("", self.auto_zoom_enabled)"
        
        self.target_ratio_spinbox = QDoubleSpinBox()
        self.target_ratio_spinbox.setRange(0.1, 0.8)
        self.target_ratio_spinbox.setValue(0.25)
        self.target_ratio_spinbox.setSingleStep(0.05)
        self.target_ratio_spinbox.setDecimals(2)
        self.target_ratio_spinbox.valueChanged.connect(self._update_config_from_ui)
        zoom_layout.addRow("Ratio objetivo del objeto:", self.target_ratio_spinbox)"
        
        self.zoom_speed_spinbox = QDoubleSpinBox()
        self.zoom_speed_spinbox.setRange(0.1, 1.0)
        self.zoom_speed_spinbox.setValue(0.3)
        self.zoom_speed_spinbox.setSingleStep(0.1)
        self.zoom_speed_spinbox.valueChanged.connect(self._update_config_from_ui)
        zoom_layout.addRow("Velocidad de zoom:", self.zoom_speed_spinbox)"
        
        zoom_group.setLayout(zoom_layout)
        layout.addWidget(zoom_group)
        
        # Controles de seguimiento
        controls_layout = QHBoxLayout()
        
        self.btn_start_tracking = QPushButton("🚀 Iniciar Seguimiento Multi-Objeto")"
        self.btn_start_tracking.setMinimumHeight(40)
        self.btn_start_tracking.setStyleSheet("""""""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #555;
                color: #999;
            }
        """)""""
        self.btn_start_tracking.clicked.connect(self._start_multi_object_tracking)
        
        self.btn_stop_tracking = QPushButton("⏹️ Detener Seguimiento")"
        self.btn_stop_tracking.setMinimumHeight(40)
        self.btn_stop_tracking.setStyleSheet("""""""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
            QPushButton:disabled {
                background-color: #555;
                color: #999;
            }
        """)""""
        self.btn_stop_tracking.clicked.connect(self._stop_multi_object_tracking)
        self.btn_stop_tracking.setEnabled(False)
        
        controls_layout.addWidget(self.btn_start_tracking)
        controls_layout.addWidget(self.btn_stop_tracking)
        layout.addLayout(controls_layout)
        
        self.tab_widget.addTab(tab, "🎯 Multi-Objeto")"
    
    def _setup_manual_control_tab(self):
        """Configurar pestaña de control manual""""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Controles de movimiento
        movement_group = QGroupBox("🕹️ Control Manual PTZ")"
        movement_layout = QVBoxLayout()
        
        # Grid de direcciones
        direction_grid = QGridLayout()
        
        self.btn_up = QPushButton("⬆️")"
        self.btn_down = QPushButton("⬇️")"
        self.btn_left = QPushButton("⬅️")"
        self.btn_right = QPushButton("➡️")"
        self.btn_stop = QPushButton("⏹️ Stop")"
        
        # Configurar botones de dirección
        direction_buttons = [self.btn_up, self.btn_down, self.btn_left, self.btn_right, self.btn_stop]
        for btn in direction_buttons:
            btn.setMinimumSize(60, 50)
            btn.setStyleSheet("""""""
                QPushButton {
                    background-color: #363636;
                    border: 2px solid #555;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #4a4a4a;
                    border-color: #777;
                }
                QPushButton:pressed {
                    background-color: #2a2a2a;
                }
            """)""""
        
        direction_grid.addWidget(self.btn_up, 0, 1)
        direction_grid.addWidget(self.btn_left, 1, 0)
        direction_grid.addWidget(self.btn_stop, 1, 1)
        direction_grid.addWidget(self.btn_right, 1, 2)
        direction_grid.addWidget(self.btn_down, 2, 1)
        movement_layout.addLayout(direction_grid)
        
        # Control de velocidad
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Velocidad:"))"
        
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 10)
        self.speed_slider.setValue(5)
        self.speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.speed_slider.setTickInterval(1)
        
        self.speed_label = QLabel("5/10")"
        self.speed_label.setMinimumWidth(40)
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_slider.valueChanged.connect(lambda v: self.speed_label.setText(f"{v}/10"))"
        
        speed_layout.addWidget(self.speed_slider)
        speed_layout.addWidget(self.speed_label)
        movement_layout.addLayout(speed_layout)
        
        movement_group.setLayout(movement_layout)
        layout.addWidget(movement_group)
        
        # Controles de zoom
        zoom_group = QGroupBox("🔍 Control de Zoom")"
        zoom_layout = QVBoxLayout()
        
        zoom_buttons_layout = QHBoxLayout()
        
        self.btn_zoom_in = QPushButton("🔍 Zoom +")"
        self.btn_zoom_out = QPushButton("🔍 Zoom -")"
        self.btn_zoom_reset = QPushButton("🔄 Reset")"
        
        zoom_buttons = [self.btn_zoom_in, self.btn_zoom_out, self.btn_zoom_reset]
        for btn in zoom_buttons:
            btn.setMinimumHeight(35)
            btn.setStyleSheet("""""""
                QPushButton {
                    background-color: #2196F3;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #1976D2;
                }
            """)""""
        
        zoom_buttons_layout.addWidget(self.btn_zoom_in)
        zoom_buttons_layout.addWidget(self.btn_zoom_out)
        zoom_buttons_layout.addWidget(self.btn_zoom_reset)
        zoom_layout.addLayout(zoom_buttons_layout)
        
        # Slider de zoom
        zoom_slider_layout = QHBoxLayout()
        zoom_slider_layout.addWidget(QLabel("Nivel:"))"
        
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(0, 100)
        self.zoom_slider.setValue(50)
        self.zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.zoom_slider.setTickInterval(25)
        
        self.zoom_level_label = QLabel("50%")"
        self.zoom_level_label.setMinimumWidth(40)
        self.zoom_level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_slider.valueChanged.connect(lambda v: self.zoom_level_label.setText(f"{v}%"))"
        
        zoom_slider_layout.addWidget(self.zoom_slider)
        zoom_slider_layout.addWidget(self.zoom_level_label)
        zoom_layout.addLayout(zoom_slider_layout)
        
        zoom_group.setLayout(zoom_layout)
        layout.addWidget(zoom_group)
        
        # Controles de presets
        preset_group = QGroupBox("📍 Gestión de Presets")"
        preset_layout = QFormLayout()
        
        preset_controls = QHBoxLayout()
        
        self.manual_preset_spinbox = QSpinBox()
        self.manual_preset_spinbox.setRange(1, 255)
        self.manual_preset_spinbox.setValue(1)
        preset_controls.addWidget(self.manual_preset_spinbox)
        
        self.btn_goto_preset = QPushButton("📍 Ir")"
        self.btn_goto_preset.clicked.connect(self._goto_preset)
        self.btn_set_preset = QPushButton("💾 Guardar")"
        self.btn_set_preset.clicked.connect(self._set_preset)
        
        preset_controls.addWidget(self.btn_goto_preset)
        preset_controls.addWidget(self.btn_set_preset)
        
        preset_layout.addRow("Preset:", preset_controls)"
        preset_group.setLayout(preset_layout)
        layout.addWidget(preset_group)
        
        layout.addStretch()
        
        self.tab_widget.addTab(tab, "🕹️ Control Manual")"
    
    def _setup_advanced_config_tab(self):
        """Configurar pestaña de configuración avanzada""""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Scroll area para configuraciones
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Configuración de prioridades
        priority_group = QGroupBox("⚖️ Pesos de Prioridad")"
        priority_layout = QFormLayout()
        
        self.confidence_weight_spinbox = QDoubleSpinBox()
        self.confidence_weight_spinbox.setRange(0.0, 1.0)
        self.confidence_weight_spinbox.setValue(0.4)
        self.confidence_weight_spinbox.setSingleStep(0.1)
        self.confidence_weight_spinbox.setDecimals(2)
        self.confidence_weight_spinbox.valueChanged.connect(self._update_config_from_ui)
        priority_layout.addRow("Peso confianza:", self.confidence_weight_spinbox)"
        
        self.movement_weight_spinbox = QDoubleSpinBox()
        self.movement_weight_spinbox.setRange(0.0, 1.0)
        self.movement_weight_spinbox.setValue(0.3)
        self.movement_weight_spinbox.setSingleStep(0.1)
        self.movement_weight_spinbox.setDecimals(2)
        self.movement_weight_spinbox.valueChanged.connect(self._update_config_from_ui)
        priority_layout.addRow("Peso movimiento:", self.movement_weight_spinbox)"
        
        self.size_weight_spinbox = QDoubleSpinBox()
        self.size_weight_spinbox.setRange(0.0, 1.0)
        self.size_weight_spinbox.setValue(0.2)
        self.size_weight_spinbox.setSingleStep(0.1)
        self.size_weight_spinbox.setDecimals(2)
        self.size_weight_spinbox.valueChanged.connect(self._update_config_from_ui)
        priority_layout.addRow("Peso tamaño:", self.size_weight_spinbox)"
        
        self.proximity_weight_spinbox = QDoubleSpinBox()
        self.proximity_weight_spinbox.setRange(0.0, 1.0)
        self.proximity_weight_spinbox.setValue(0.1)
        self.proximity_weight_spinbox.setSingleStep(0.1)
        self.proximity_weight_spinbox.setDecimals(2)
        self.proximity_weight_spinbox.valueChanged.connect(self._update_config_from_ui)
        priority_layout.addRow("Peso proximidad:", self.proximity_weight_spinbox)"
        
        priority_group.setLayout(priority_layout)
        scroll_layout.addWidget(priority_group)
        
        # Configuración de detección
        detection_group = QGroupBox("🔍 Parámetros de Detección")"
        detection_layout = QFormLayout()
        
        self.min_confidence_spinbox = QDoubleSpinBox()
        self.min_confidence_spinbox.setRange(0.1, 1.0)
        self.min_confidence_spinbox.setValue(0.5)
        self.min_confidence_spinbox.setSingleStep(0.1)
        self.min_confidence_spinbox.setDecimals(2)
        self.min_confidence_spinbox.valueChanged.connect(self._update_config_from_ui)
        detection_layout.addRow("Confianza mínima:", self.min_confidence_spinbox)"
        
        self.max_objects_spinbox = QSpinBox()
        self.max_objects_spinbox.setRange(1, 10)
        self.max_objects_spinbox.setValue(3)
        self.max_objects_spinbox.valueChanged.connect(self._update_config_from_ui)
        detection_layout.addRow("Máximo objetos:", self.max_objects_spinbox)"
        
        self.min_object_size_spinbox = QDoubleSpinBox()
        self.min_object_size_spinbox.setRange(0.001, 0.1)
        self.min_object_size_spinbox.setValue(0.01)
        self.min_object_size_spinbox.setSingleStep(0.005)
        self.min_object_size_spinbox.setDecimals(3)
        self.min_object_size_spinbox.valueChanged.connect(self._update_config_from_ui)
        detection_layout.addRow("Tamaño mínimo (ratio):", self.min_object_size_spinbox"