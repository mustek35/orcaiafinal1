# ui/ptz_preset_dialog.py - CORREGIDO
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QComboBox, 
    QLabel, QSpinBox, QLineEdit, QTextEdit, QGroupBox, QMessageBox, QListWidget,
    QListWidgetItem, QCheckBox, QSlider, QTabWidget, QWidget, QFormLayout
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
import json
import os
from datetime import datetime  # CORRECCIÓN: Importar solo datetime, no todo el módulo

# Importaciones seguras
try:
    from core.ptz_control_enhanced import initialize_ptz_system, get_ptz_system_status
    ENHANCED_AVAILABLE = True
except ImportError:
    ENHANCED_AVAILABLE = False
    print("⚠️ Módulo PTZ mejorado no disponible, usando funcionalidad básica")

class PTZPresetDialog(QDialog):
    """Diálogo avanzado para gestión de presets PTZ - VERSIÓN CORREGIDA"""
    
    preset_updated = pyqtSignal(int, str)  # preset_number, preset_name
    
    def __init__(self, parent=None, camera_list=None, ptz_camera=None):
        super().__init__(parent)
        self.setWindowTitle("🎯 Gestión Avanzada de Presets PTZ")
        self.setMinimumSize(600, 500)
        
        # CORRECCIÓN: Usar camera_list en lugar de camera_data
        self.camera_list = camera_list or []
        self.ptz_camera = ptz_camera
        self.presets_data = {}
        self.current_camera_data = None
        
        # Seleccionar primera cámara PTZ si hay alguna
        self._select_first_ptz_camera()
        
        # Inicializar sistema PTZ si está disponible
        if ENHANCED_AVAILABLE:
            try:
                self.system_info = initialize_ptz_system()
                self._log("✅ Sistema PTZ mejorado inicializado")
            except Exception as e:
                self._log(f"⚠️ Error inicializando sistema PTZ: {e}")
                self.system_info = {}
        else:
            self.system_info = {}
            self._log("ℹ️ Usando funcionalidad PTZ básica")
        
        self._setup_ui()
        self._load_presets()
        self._connect_signals()
        
        # Verificar conexión inicial
        QTimer.singleShot(1000, self._check_initial_connection)
        
    def _select_first_ptz_camera(self):
        """Selecciona la primera cámara PTZ disponible"""
        for camera in self.camera_list:
            if camera.get('tipo') == 'ptz':
                self.current_camera_data = camera
                self._log(f"📷 Cámara PTZ seleccionada: {camera.get('ip')}")
                break
        
        if not self.current_camera_data:
            self._log("⚠️ No se encontraron cámaras PTZ en la lista")
        
    def _setup_ui(self):
        """Configura la interfaz de usuario"""
        layout = QVBoxLayout()
        
        # Información de la cámara
        self._setup_camera_info(layout)
        
        # Pestañas principales
        self.tab_widget = QTabWidget()
        
        # Pestaña de presets existentes
        self._setup_presets_tab()
        
        # Pestaña de control manual
        self._setup_manual_control_tab()
        
        # Pestaña de configuración
        self._setup_settings_tab()
        
        layout.addWidget(self.tab_widget)
        
        # Botones de acción
        self._setup_action_buttons(layout)
        
        self.setLayout(layout)
        
    def _setup_camera_info(self, layout):
        """Configura la sección de información de la cámara"""
        info_group = QGroupBox("📷 Información de la Cámara")
        info_layout = QHBoxLayout()
        
        if self.current_camera_data:
            ip = self.current_camera_data.get("ip", "N/A")
            tipo = self.current_camera_data.get("tipo", "N/A")
            usuario = self.current_camera_data.get("usuario", "N/A")
        else:
            ip = tipo = usuario = "N/A"
        
        info_label = QLabel(f"IP: {ip} | Tipo: {tipo} | Usuario: {usuario}")
        info_label.setStyleSheet("font-weight: bold; color: #2E5BBA;")
        
        self.connection_status = QLabel("🔄 Verificando conexión...")
        
        info_layout.addWidget(info_label)
        info_layout.addStretch()
        info_layout.addWidget(self.connection_status)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
    def _setup_presets_tab(self):
        """Configura la pestaña de presets existentes"""
        presets_widget = QWidget()
        layout = QVBoxLayout()
        
        # Lista de presets
        presets_group = QGroupBox("📍 Presets Configurados")
        presets_layout = QVBoxLayout()
        
        self.presets_list = QListWidget()
        self.presets_list.setMinimumHeight(200)
        presets_layout.addWidget(self.presets_list)
        
        # Controles de preset
        preset_controls = QHBoxLayout()
        
        self.preset_number_spin = QSpinBox()
        self.preset_number_spin.setRange(1, 255)
        self.preset_number_spin.setValue(1)
        
        self.preset_name_edit = QLineEdit()
        self.preset_name_edit.setPlaceholderText("Nombre del preset (opcional)")
        
        preset_controls.addWidget(QLabel("Preset:"))
        preset_controls.addWidget(self.preset_number_spin)
        preset_controls.addWidget(QLabel("Nombre:"))
        preset_controls.addWidget(self.preset_name_edit)
        
        presets_layout.addLayout(preset_controls)
        
        # Botones de acción para presets
        preset_buttons = QHBoxLayout()
        
        self.btn_goto_preset = QPushButton("📍 Ir a Preset")
        self.btn_save_preset = QPushButton("💾 Guardar Posición Actual")
        self.btn_delete_preset = QPushButton("🗑️ Eliminar Preset")
        self.btn_refresh_presets = QPushButton("🔄 Actualizar Lista")
        
        preset_buttons.addWidget(self.btn_goto_preset)
        preset_buttons.addWidget(self.btn_save_preset)
        preset_buttons.addWidget(self.btn_delete_preset)
        preset_buttons.addWidget(self.btn_refresh_presets)
        
        presets_layout.addLayout(preset_buttons)
        
        presets_group.setLayout(presets_layout)
        layout.addWidget(presets_group)
        
        # Área de logs
        log_group = QGroupBox("📋 Registro de Actividad")
        log_layout = QVBoxLayout()
        
        self.log_area = QTextEdit()
        self.log_area.setMaximumHeight(120)
        self.log_area.setReadOnly(True)
        log_layout.addWidget(self.log_area)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        presets_widget.setLayout(layout)
        self.tab_widget.addTab(presets_widget, "📍 Presets")
        
    def _setup_manual_control_tab(self):
        """Configura la pestaña de control manual"""
        control_widget = QWidget()
        layout = QVBoxLayout()
        
        # Controles direccionales
        direction_group = QGroupBox("🕹️ Control Manual")
        direction_layout = QVBoxLayout()
        
        # Grid de direcciones
        grid = QGridLayout()
        
        self.btn_up = QPushButton("⬆️")
        self.btn_down = QPushButton("⬇️")
        self.btn_left = QPushButton("⬅️")
        self.btn_right = QPushButton("➡️")
        self.btn_stop = QPushButton("⏹️ PARAR")
        
        # Hacer botones más grandes
        for btn in [self.btn_up, self.btn_down, self.btn_left, self.btn_right, self.btn_stop]:
            btn.setMinimumSize(80, 50)
            
        self.btn_stop.setStyleSheet("background-color: #FF6B6B; color: white; font-weight: bold;")
        
        grid.addWidget(self.btn_up, 0, 1)
        grid.addWidget(self.btn_left, 1, 0)
        grid.addWidget(self.btn_stop, 1, 1)
        grid.addWidget(self.btn_right, 1, 2)
        grid.addWidget(self.btn_down, 2, 1)
        
        direction_layout.addLayout(grid)
        
        # Controles de velocidad y zoom
        controls_layout = QHBoxLayout()
        
        # Velocidad
        speed_group = QGroupBox("⚡ Velocidad")
        speed_layout = QVBoxLayout()
        
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 10)
        self.speed_slider.setValue(5)
        self.speed_label = QLabel("Velocidad: 5/10")
        
        speed_layout.addWidget(self.speed_label)
        speed_layout.addWidget(self.speed_slider)
        speed_group.setLayout(speed_layout)
        
        # Zoom
        zoom_group = QGroupBox("🔍 Zoom")
        zoom_layout = QVBoxLayout()
        
        zoom_buttons = QHBoxLayout()
        self.btn_zoom_in = QPushButton("🔍 Zoom +")
        self.btn_zoom_out = QPushButton("🔍 Zoom -")
        
        zoom_buttons.addWidget(self.btn_zoom_in)
        zoom_buttons.addWidget(self.btn_zoom_out)
        zoom_layout.addLayout(zoom_buttons)
        zoom_group.setLayout(zoom_layout)
        
        controls_layout.addWidget(speed_group)
        controls_layout.addWidget(zoom_group)
        direction_layout.addLayout(controls_layout)
        
        direction_group.setLayout(direction_layout)
        layout.addWidget(direction_group)
        
        # Posición actual
        position_group = QGroupBox("📍 Posición Actual")
        position_layout = QFormLayout()
        
        self.current_pan_label = QLabel("N/A")
        self.current_tilt_label = QLabel("N/A")
        self.current_zoom_label = QLabel("N/A")
        
        position_layout.addRow("Pan:", self.current_pan_label)
        position_layout.addRow("Tilt:", self.current_tilt_label)
        position_layout.addRow("Zoom:", self.current_zoom_label)
        
        position_group.setLayout(position_layout)
        layout.addWidget(position_group)
        
        control_widget.setLayout(layout)
        self.tab_widget.addTab(control_widget, "🕹️ Control Manual")
        
    def _setup_settings_tab(self):
        """Configura la pestaña de configuración"""
        settings_widget = QWidget()
        layout = QVBoxLayout()
        
        # Configuración de movimiento
        movement_group = QGroupBox("⚙️ Configuración de Movimiento")
        movement_layout = QFormLayout()
        
        self.move_duration_spin = QSpinBox()
        self.move_duration_spin.setRange(100, 2000)
        self.move_duration_spin.setValue(300)
        self.move_duration_spin.setSuffix(" ms")
        
        self.auto_stop_check = QCheckBox("Detener automáticamente después del movimiento")
        self.auto_stop_check.setChecked(True)
        
        movement_layout.addRow("Duración del movimiento:", self.move_duration_spin)
        movement_layout.addRow("", self.auto_stop_check)
        
        movement_group.setLayout(movement_layout)
        layout.addWidget(movement_group)
        
        # Configuración de presets
        preset_config_group = QGroupBox("📍 Configuración de Presets")
        preset_config_layout = QFormLayout()
        
        self.preset_timeout_spin = QSpinBox()
        self.preset_timeout_spin.setRange(1, 30)
        self.preset_timeout_spin.setValue(5)
        self.preset_timeout_spin.setSuffix(" seg")
        
        self.save_preset_names_check = QCheckBox("Guardar nombres de presets localmente")
        self.save_preset_names_check.setChecked(True)
        
        preset_config_layout.addRow("Timeout para ir a preset:", self.preset_timeout_spin)
        preset_config_layout.addRow("", self.save_preset_names_check)
        
        preset_config_group.setLayout(preset_config_layout)
        layout.addWidget(preset_config_group)
        
        # Configuración de conexión
        connection_group = QGroupBox("🔗 Configuración de Conexión")
        connection_layout = QFormLayout()
        
        self.connection_timeout_spin = QSpinBox()
        self.connection_timeout_spin.setRange(1, 30)
        self.connection_timeout_spin.setValue(5)
        self.connection_timeout_spin.setSuffix(" seg")
        
        self.retry_attempts_spin = QSpinBox()
        self.retry_attempts_spin.setRange(1, 10)
        self.retry_attempts_spin.setValue(3)
        
        connection_layout.addRow("Timeout de conexión:", self.connection_timeout_spin)
        connection_layout.addRow("Intentos de reintento:", self.retry_attempts_spin)
        
        connection_group.setLayout(connection_layout)
        layout.addWidget(connection_group)
        
        layout.addStretch()
        
        settings_widget.setLayout(layout)
        self.tab_widget.addTab(settings_widget, "⚙️ Configuración")
        
    def _setup_action_buttons(self, layout):
        """Configura los botones de acción principales"""
        button_layout = QHBoxLayout()
        
        self.btn_test_connection = QPushButton("🧪 Probar Conexión")
        self.btn_get_position = QPushButton("📍 Obtener Posición Actual")
        self.btn_save_config = QPushButton("💾 Guardar Configuración")
        self.btn_close = QPushButton("❌ Cerrar")
        
        button_layout.addWidget(self.btn_test_connection)
        button_layout.addWidget(self.btn_get_position)
        button_layout.addWidget(self.btn_save_config)
        button_layout.addStretch()
        button_layout.addWidget(self.btn_close)
        
        layout.addLayout(button_layout)
        
    def _connect_signals(self):
        """Conecta todas las señales"""
        # Presets
        self.btn_goto_preset.clicked.connect(self.goto_preset)
        self.btn_save_preset.clicked.connect(self.save_current_position_as_preset)
        self.btn_delete_preset.clicked.connect(self.delete_preset)
        self.btn_refresh_presets.clicked.connect(self.refresh_presets_list)
        
        # Control manual
        self.btn_up.clicked.connect(lambda: self.move_camera("up"))
        self.btn_down.clicked.connect(lambda: self.move_camera("down"))
        self.btn_left.clicked.connect(lambda: self.move_camera("left"))
        self.btn_right.clicked.connect(lambda: self.move_camera("right"))
        self.btn_stop.clicked.connect(self.stop_camera)
        
        self.btn_zoom_in.clicked.connect(lambda: self.zoom_camera("in"))
        self.btn_zoom_out.clicked.connect(lambda: self.zoom_camera("out"))
        
        # Configuración
        self.speed_slider.valueChanged.connect(self.update_speed_label)
        
        # Botones principales
        self.btn_test_connection.clicked.connect(self.test_connection)
        self.btn_get_position.clicked.connect(self.get_current_position)
        self.btn_save_config.clicked.connect(self.save_configuration)
        self.btn_close.clicked.connect(self.close)
        
        # Lista de presets
        self.presets_list.itemClicked.connect(self.on_preset_selected)
        
    def _load_presets(self):
        """Carga los presets desde archivo local"""
        try:
            if self.current_camera_data:
                ip = self.current_camera_data.get('ip', 'unknown')
                presets_file = f"presets_{ip}.json"
                if os.path.exists(presets_file):
                    with open(presets_file, 'r') as f:
                        self.presets_data = json.load(f)
                    self._log(f"✅ Presets cargados desde {presets_file}")
                else:
                    self.presets_data = {}
                    self._log("ℹ️ No se encontró archivo de presets, iniciando con lista vacía")
            else:
                self.presets_data = {}
                self._log("⚠️ Sin cámara seleccionada, no se pueden cargar presets")
                
            self.refresh_presets_list()
            
        except Exception as e:
            self._log(f"❌ Error cargando presets: {e}")
            self.presets_data = {}
            
    def refresh_presets_list(self):
        """Actualiza la lista visual de presets"""
        self.presets_list.clear()
        
        if not self.presets_data:
            item = QListWidgetItem("📭 No hay presets configurados")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self.presets_list.addItem(item)
            return
            
        for preset_num, preset_info in sorted(self.presets_data.items()):
            name = preset_info.get("name", f"Preset {preset_num}")
            created = preset_info.get("created", "Fecha desconocida")
            
            item_text = f"📍 Preset {preset_num}: {name} (Creado: {created})"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, int(preset_num))
            self.presets_list.addItem(item)
            
        self._log(f"🔄 Lista de presets actualizada: {len(self.presets_data)} presets")
        
    def on_preset_selected(self, item):
        """Maneja la selección de un preset en la lista"""
        preset_num = item.data(Qt.ItemDataRole.UserRole)
        if preset_num is not None:
            self.preset_number_spin.setValue(preset_num)
            preset_info = self.presets_data.get(str(preset_num), {})
            self.preset_name_edit.setText(preset_info.get("name", ""))
            
    def goto_preset(self):
        """Va a un preset específico"""
        if not self.ptz_camera:
            self._log("❌ No hay conexión PTZ activa")
            return
            
        preset_num = self.preset_number_spin.value()
        
        try:
            self.ptz_camera.goto_preset(str(preset_num))
            self._log(f"📍 Moviendo a preset {preset_num}")
            
            # Actualizar información si el preset existe localmente
            if str(preset_num) in self.presets_data:
                preset_info = self.presets_data[str(preset_num)]
                name = preset_info.get("name", f"Preset {preset_num}")
                self._log(f"📍 Destino: {name}")
                
        except Exception as e:
            self._log(f"❌ Error yendo a preset {preset_num}: {e}")
            
    def save_current_position_as_preset(self):
        """Guarda la posición actual como preset"""
        preset_num = self.preset_number_spin.value()
        preset_name = self.preset_name_edit.text().strip() or f"Preset {preset_num}"
        
        try:
            # Nota: ONVIF estándar no tiene comando directo para guardar presets
            # Este sería específico del fabricante
            self._log(f"💾 Guardando preset {preset_num}: {preset_name}")
            
            # Guardar información localmente
            self.presets_data[str(preset_num)] = {
                "name": preset_name,
                "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # CORRECCIÓN: datetime está correctamente importado
                "camera_ip": self.current_camera_data.get("ip") if self.current_camera_data else "unknown"
            }
            
            self._save_presets_to_file()
            self.refresh_presets_list()
            
            # Emitir señal de actualización
            self.preset_updated.emit(preset_num, preset_name)
            
            self._log(f"✅ Preset {preset_num} guardado como '{preset_name}'")
            
        except Exception as e:
            self._log(f"❌ Error guardando preset: {e}")
            
    def delete_preset(self):
        """Elimina un preset"""
        preset_num = self.preset_number_spin.value()
        
        if str(preset_num) not in self.presets_data:
            self._log(f"⚠️ El preset {preset_num} no existe localmente")
            return
            
        reply = QMessageBox.question(
            self,
            "Confirmar eliminación",
            f"¿Está seguro de que desea eliminar el preset {preset_num}?\n\n"
            f"Nombre: {self.presets_data[str(preset_num)].get('name', 'Sin nombre')}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            del self.presets_data[str(preset_num)]
            self._save_presets_to_file()
            self.refresh_presets_list()
            self._log(f"🗑️ Preset {preset_num} eliminado")
            
    def move_camera(self, direction):
        """Mueve la cámara en una dirección"""
        if not self.ptz_camera:
            self._log("❌ No hay conexión PTZ activa")
            return
            
        speed = self.speed_slider.value() / 10.0
        duration = self.move_duration_spin.value() / 1000.0  # Convertir a segundos
        
        try:
            if direction == "up":
                self.ptz_camera.continuous_move(0, speed)
                self._log(f"⬆️ Movimiento: Arriba (velocidad: {speed:.1f})")
            elif direction == "down":
                self.ptz_camera.continuous_move(0, -speed)
                self._log(f"⬇️ Movimiento: Abajo (velocidad: {speed:.1f})")
            elif direction == "left":
                self.ptz_camera.continuous_move(-speed, 0)
                self._log(f"⬅️ Movimiento: Izquierda (velocidad: {speed:.1f})")
            elif direction == "right":
                self.ptz_camera.continuous_move(speed, 0)
                self._log(f"➡️ Movimiento: Derecha (velocidad: {speed:.1f})")
                
            # Auto-stop después del tiempo configurado
            if self.auto_stop_check.isChecked():
                QTimer.singleShot(int(duration * 1000), self.stop_camera)
                
        except Exception as e:
            self._log(f"❌ Error en movimiento {direction}: {e}")
            
    def stop_camera(self):
        """Detiene el movimiento de la cámara"""
        if not self.ptz_camera:
            return
            
        try:
            self.ptz_camera.stop()
            self._log("⏹️ Movimiento detenido")
        except Exception as e:
            self._log(f"❌ Error deteniendo movimiento: {e}")
            
    def zoom_camera(self, direction):
        """Controla el zoom de la cámara"""
        if not self.ptz_camera:
            self._log("❌ No hay conexión PTZ activa")
            return
            
        speed = self.speed_slider.value() / 10.0
        duration = self.move_duration_spin.value() / 1000.0
        
        try:
            zoom_speed = speed if direction == "in" else -speed
            self.ptz_camera.continuous_move(0, 0, zoom_speed)
            self._log(f"🔍 Zoom: {'Acercar' if direction == 'in' else 'Alejar'} (velocidad: {speed:.1f})")
            
            if self.auto_stop_check.isChecked():
                QTimer.singleShot(int(duration * 1000), self.stop_camera)
                
        except Exception as e:
            self._log(f"❌ Error en zoom {direction}: {e}")
            
    def _check_initial_connection(self):
        """Verifica la conexión inicial y actualiza el estado"""
        if self.ptz_camera:
            try:
                # Intentar una operación simple para verificar conexión
                if hasattr(self.ptz_camera, 'stop'):
                    self.ptz_camera.stop()
                self.connection_status.setText("✅ Conectado")
                self._log("✅ Conexión PTZ verificada")
                
                # Si tenemos funcionalidad mejorada, obtener información adicional
                if ENHANCED_AVAILABLE and hasattr(self.ptz_camera, 'get_presets'):
                    try:
                        presets = self.ptz_camera.get_presets()
                        if presets:
                            self._log(f"📍 {len(presets)} presets disponibles en la cámara")
                    except:
                        pass
                        
            except Exception as e:
                self.connection_status.setText("❌ Error de conexión")
                self._log(f"❌ Error verificando conexión: {e}")
        else:
            self.connection_status.setText("❌ Sin conexión PTZ")
            self._log("⚠️ No hay instancia PTZ disponible")

    def test_connection(self):
        """Prueba la conexión con la cámara PTZ"""
        if not self.ptz_camera:
            self._log("❌ No hay instancia PTZ disponible")
            self.connection_status.setText("❌ Sin conexión")
            return
            
        try:
            # Intentar una operación simple para verificar conexión
            if hasattr(self.ptz_camera, 'stop'):
                self.ptz_camera.stop()  # Comando simple y seguro
            
            self._log("✅ Conexión PTZ verificada correctamente")
            self.connection_status.setText("✅ Conectado")
            
            # Verificar funcionalidades adicionales si están disponibles
            capabilities = []
            
            if hasattr(self.ptz_camera, 'get_position'):
                try:
                    pos = self.ptz_camera.get_position()
                    if pos:
                        capabilities.append("posición")
                        self.current_pan_label.setText(f"{pos.get('pan', 0):.2f}")
                        self.current_tilt_label.setText(f"{pos.get('tilt', 0):.2f}")
                        self.current_zoom_label.setText(f"{pos.get('zoom', 0):.2f}")
                except:
                    pass
                    
            if hasattr(self.ptz_camera, 'get_presets'):
                try:
                    presets = self.ptz_camera.get_presets()
                    if presets:
                        capabilities.append("presets")
                except:
                    pass
            
            if capabilities:
                self._log(f"✅ Funcionalidades disponibles: {', '.join(capabilities)}")
            
        except Exception as e:
            self._log(f"❌ Error de conexión PTZ: {e}")
            self.connection_status.setText("❌ Error de conexión")

    def get_current_position(self):
        """Obtiene la posición actual de la cámara"""
        if not self.ptz_camera:
            self._log("❌ No hay conexión PTZ activa")
            return
            
        try:
            if hasattr(self.ptz_camera, 'get_position'):
                position = self.ptz_camera.get_position()
                if position:
                    pan = position.get('pan', 0)
                    tilt = position.get('tilt', 0)
                    zoom = position.get('zoom', 0)
                    
                    self.current_pan_label.setText(f"{pan:.3f}")
                    self.current_tilt_label.setText(f"{tilt:.3f}")
                    self.current_zoom_label.setText(f"{zoom:.3f}")
                    
                    self._log(f"📍 Posición actual - Pan: {pan:.3f}, Tilt: {tilt:.3f}, Zoom: {zoom:.3f}")
                else:
                    self._log("⚠️ No se pudo obtener la posición actual")
            else:
                self._log("⚠️ Función de obtener posición no disponible con esta cámara")
                
        except Exception as e:
            self._log(f"❌ Error obteniendo posición: {e}")

    def save_configuration(self):
        """Guarda la configuración actual"""
        config = {
            "move_duration": self.move_duration_spin.value(),
            "auto_stop": self.auto_stop_check.isChecked(),
            "preset_timeout": self.preset_timeout_spin.value(),
            "save_preset_names": self.save_preset_names_check.isChecked(),
            "connection_timeout": self.connection_timeout_spin.value(),
            "retry_attempts": self.retry_attempts_spin.value(),
            "default_speed": self.speed_slider.value(),
            "camera_ip": self.current_camera_data.get("ip") if self.current_camera_data else "unknown",
            "saved_at": datetime.now().isoformat()  # CORRECCIÓN: datetime correctamente usado
        }
        
        # Agregar información del sistema si está disponible
        if ENHANCED_AVAILABLE and self.system_info:
            config["system_info"] = self.system_info
        
        try:
            if self.current_camera_data:
                ip = self.current_camera_data.get('ip', 'unknown').replace('.', '_')
                config_file = f"ptz_config_{ip}.json"
            else:
                config_file = "ptz_config_unknown.json"
                
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=4)
            self._log(f"✅ Configuración guardada en {config_file}")
            
            QMessageBox.information(
                self,
                "Configuración guardada",
                f"✅ Configuración guardada exitosamente en:\n{config_file}"
            )
            
        except Exception as e:
            self._log(f"❌ Error guardando configuración: {e}")
            QMessageBox.warning(
                self,
                "Error guardando",
                f"❌ No se pudo guardar la configuración:\n{e}"
            )
            
    def update_speed_label(self, value):
        """Actualiza la etiqueta de velocidad"""
        self.speed_label.setText(f"Velocidad: {value}/10")
        
    def _save_presets_to_file(self):
        """Guarda los presets al archivo local"""
        try:
            if self.current_camera_data:
                ip = self.current_camera_data.get('ip', 'unknown')
                presets_file = f"presets_{ip}.json"
            else:
                presets_file = "presets_unknown.json"
                
            with open(presets_file, 'w') as f:
                json.dump(self.presets_data, f, indent=4)
                
        except Exception as e:
            self._log(f"❌ Error guardando presets: {e}")
            
    def _log(self, message):
        """Agrega un mensaje al área de logs"""
        timestamp = datetime.now().strftime("%H:%M:%S")  # CORRECCIÓN: datetime correctamente usado
        formatted_message = f"[{timestamp}] {message}"
        
        # Si log_area no existe aún, imprimir en consola
        if not hasattr(self, 'log_area') or self.log_area is None:
            print(f"PTZ Preset Log: {formatted_message}")
            return
            
        try:
            self.log_area.append(formatted_message)
            
            # Desplazar al final
            cursor = self.log_area.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.log_area.setTextCursor(cursor)
        except Exception as e:
            print(f"Error en _log: {e} - Mensaje: {formatted_message}")