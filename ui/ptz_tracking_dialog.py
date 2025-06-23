# ui/ptz_tracking_dialog.py - CORREGIDO
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QComboBox, QLabel,
    QMessageBox, QGroupBox, QCheckBox, QSpinBox, QTextEdit
)
from PyQt6.QtCore import Qt
import threading
import time
import json
import os

# IMPORTACIONES CORREGIDAS - usando solo las clases que existen
try:
    from core.ptz_control import PTZCameraONVIF, track_object_continuous
    PTZ_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Error importando módulos PTZ básicos: {e}")
    PTZ_AVAILABLE = False

# Importaciones opcionales para funcionalidades avanzadas
try:
    from core.ptz_control_enhanced import PTZCameraEnhanced, create_enhanced_ptz_camera
    ENHANCED_PTZ_AVAILABLE = True
except ImportError:
    print("ℹ️ Módulo PTZ mejorado no disponible, usando funcionalidad básica")
    ENHANCED_PTZ_AVAILABLE = False

try:
    from ui.ptz_preset_dialog import PTZPresetDialog
    PRESET_DIALOG_AVAILABLE = True
except ImportError:
    print("ℹ️ Diálogo de presets no disponible")
    PRESET_DIALOG_AVAILABLE = False

CONFIG_FILE_PATH = "config.json"

class PTZTrackingDialog(QDialog):
    """Diálogo para control y seguimiento PTZ - VERSIÓN CORREGIDA"""

    def __init__(self, parent=None, camera_list=None):
        super().__init__(parent)
        self.setWindowTitle("🎯 Control PTZ")
        self.setMinimumSize(450, 400)

        # Verificar disponibilidad de módulos
        if not PTZ_AVAILABLE:
            self._show_module_error()
            return

        # CORRECCIÓN: Inicializar variables antes de usar _log
        self.all_cameras = camera_list or []
        self.ptz_cameras = []
        self.credentials_cache = {}
        self.ptz_objects = {}
        self.current_camera_data = None
        
        # Buffer temporal para logs antes de que se cree la UI
        self._log_buffer = []

        # CORRECCIÓN: Configurar UI ANTES de cargar configuración
        self._setup_ui()
        self._connect_signals()
        
        # Ahora cargar configuración (puede usar _log sin problemas)
        self._load_camera_configuration()
        
        # Aplicar logs buffereados
        self._flush_log_buffer()
        
        self._update_ui_state()
        
        # Seleccionar primera cámara por defecto
        if self.selector.count() > 0:
            self.selector.setCurrentIndex(0)
            self._on_camera_changed(0)

    def _show_module_error(self):
        """Muestra error cuando no están disponibles los módulos PTZ"""
        layout = QVBoxLayout()
        
        error_label = QLabel(
            "❌ Error: Módulos PTZ no disponibles\n\n"
            "Archivos requeridos:\n"
            "• core/ptz_control.py\n"
            "• PyQt6\n"
            "• python-onvif-zeep\n\n"
            "Instale las dependencias:\n"
            "pip install onvif-zeep"
        )
        error_label.setStyleSheet("color: red; font-size: 12px; padding: 20px;")
        layout.addWidget(error_label)
        
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)

    def _setup_ui(self):
        """Configura la interfaz de usuario"""
        layout = QVBoxLayout()

        # Grupo de selección de cámara
        camera_group = QGroupBox("📷 Selección de Cámara")
        camera_layout = QVBoxLayout()
        
        self.selector = QComboBox()
        # NOTA: _populate_camera_selector se llamará después de cargar la configuración
        self.selector.currentIndexChanged.connect(self._on_camera_changed)
        
        camera_layout.addWidget(QLabel("Seleccionar cámara para control PTZ:"))
        camera_layout.addWidget(self.selector)
        
        # Información de la cámara seleccionada
        self.camera_info_label = QLabel("Selecciona una cámara para ver detalles")
        self.camera_info_label.setStyleSheet("color: gray; font-size: 11px; margin: 5px;")
        camera_layout.addWidget(self.camera_info_label)
        
        camera_group.setLayout(camera_layout)
        layout.addWidget(camera_group)

        # Grupo de controles PTZ
        control_group = QGroupBox("🕹️ Controles PTZ")
        control_layout = QVBoxLayout()
        
        # Controles direccionales
        grid = QGridLayout()
        self.btn_up = QPushButton("↑")
        self.btn_down = QPushButton("↓")
        self.btn_left = QPushButton("←")
        self.btn_right = QPushButton("→")
        self.btn_center = QPushButton("⏹️ Parar")

        # Hacer botones más grandes
        for btn in [self.btn_up, self.btn_down, self.btn_left, self.btn_right, self.btn_center]:
            btn.setMinimumSize(60, 40)

        grid.addWidget(self.btn_up, 0, 1)
        grid.addWidget(self.btn_left, 1, 0)
        grid.addWidget(self.btn_center, 1, 1)
        grid.addWidget(self.btn_right, 1, 2)
        grid.addWidget(self.btn_down, 2, 1)
        control_layout.addLayout(grid)

        # Controles de zoom
        zoom_layout = QHBoxLayout()
        self.btn_zoom_in = QPushButton("🔍 Zoom +")
        self.btn_zoom_out = QPushButton("🔍 Zoom -")
        zoom_layout.addWidget(self.btn_zoom_in)
        zoom_layout.addWidget(self.btn_zoom_out)
        control_layout.addLayout(zoom_layout)

        # Controles de velocidad
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Velocidad:"))
        self.speed_spinbox = QSpinBox()
        self.speed_spinbox.setRange(1, 10)
        self.speed_spinbox.setValue(3)
        self.speed_spinbox.setSuffix("/10")
        speed_layout.addWidget(self.speed_spinbox)
        control_layout.addLayout(speed_layout)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # Grupo de presets
        preset_group = QGroupBox("📍 Gestión de Presets")
        preset_layout = QVBoxLayout()
        
        preset_controls = QHBoxLayout()
        self.preset_spinbox = QSpinBox()
        self.preset_spinbox.setRange(1, 255)
        self.preset_spinbox.setValue(1)
        preset_controls.addWidget(QLabel("Preset:"))
        preset_controls.addWidget(self.preset_spinbox)
        
        self.btn_goto_preset = QPushButton("📍 Ir a Preset")
        self.btn_set_preset = QPushButton("💾 Guardar Preset")
        preset_controls.addWidget(self.btn_goto_preset)
        preset_controls.addWidget(self.btn_set_preset)
        
        preset_layout.addLayout(preset_controls)
        
        # Botón para gestión avanzada (solo si está disponible)
        if PRESET_DIALOG_AVAILABLE:
            self.btn_advanced_presets = QPushButton("⚙️ Gestión Avanzada")
            self.btn_advanced_presets.clicked.connect(self.open_advanced_presets)
            preset_layout.addWidget(self.btn_advanced_presets)
        
        preset_group.setLayout(preset_layout)
        layout.addWidget(preset_group)

        # Grupo de seguimiento automático
        tracking_group = QGroupBox("🎯 Seguimiento Automático")
        tracking_layout = QVBoxLayout()
        
        self.auto_track_enabled = QCheckBox("Habilitar seguimiento automático")
        tracking_layout.addWidget(self.auto_track_enabled)
        
        self.btn_start_tracking = QPushButton("▶️ Iniciar Seguimiento")
        self.btn_stop_tracking = QPushButton("⏹️ Detener Seguimiento")
        
        track_controls = QHBoxLayout()
        track_controls.addWidget(self.btn_start_tracking)
        track_controls.addWidget(self.btn_stop_tracking)
        tracking_layout.addLayout(track_controls)
        
        tracking_group.setLayout(tracking_layout)
        layout.addWidget(tracking_group)

        # Área de logs - CRÍTICO: Crear esto ANTES de llamar _log
        log_group = QGroupBox("📋 Registro de Actividad")
        log_layout = QVBoxLayout()
        
        self.log_area = QTextEdit()
        self.log_area.setMaximumHeight(100)
        self.log_area.setReadOnly(True)
        log_layout.addWidget(self.log_area)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # Botones de acción
        button_layout = QHBoxLayout()
        self.btn_test_connection = QPushButton("🧪 Probar Conexión")
        self.btn_close = QPushButton("❌ Cerrar")
        button_layout.addWidget(self.btn_test_connection)
        button_layout.addStretch()
        button_layout.addWidget(self.btn_close)
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def _load_camera_configuration(self):
        """Carga la configuración de cámaras desde config.json"""
        self.ptz_cameras = []
        self.credentials_cache = {}
        
        try:
            if os.path.exists(CONFIG_FILE_PATH):
                with open(CONFIG_FILE_PATH, 'r') as f:
                    config_data = json.load(f)
                    
                cameras_config = config_data.get("camaras", [])
                for cam_config in cameras_config:
                    ip = cam_config.get("ip")
                    if ip:
                        # Cachear credenciales para TODAS las cámaras
                        self.credentials_cache[ip] = {
                            "usuario": cam_config.get("usuario", "admin"),
                            "contrasena": cam_config.get("contrasena", ""),
                            "puerto": cam_config.get("puerto", 80),
                            "tipo": cam_config.get("tipo", "fija"),
                            "rtsp": cam_config.get("rtsp", "")
                        }
                        
                        # Identificar cámaras PTZ
                        if cam_config.get("tipo") == "ptz":
                            self.ptz_cameras.append(ip)
                            
                self._log(f"✅ Configuración cargada: {len(self.credentials_cache)} cámaras, {len(self.ptz_cameras)} PTZ")
                
                # Ahora que tenemos la configuración, poblar el selector
                self._populate_camera_selector()
            else:
                self._log("⚠️ Archivo config.json no encontrado")
                self._populate_camera_selector()  # Poblar con lista vacía
                
        except Exception as e:
            self._log(f"❌ Error cargando configuración: {e}")
            self._populate_camera_selector()  # Poblar con lista vacía

    def _populate_camera_selector(self):
        """Puebla el selector de cámaras con información detallada"""
        self.selector.clear()
        
        if not self.all_cameras:
            self.selector.addItem("❌ No hay cámaras configuradas")
            return
            
        for i, cam in enumerate(self.all_cameras):
            ip = cam.get("ip", "IP desconocida")
            tipo = cam.get("tipo", "desconocido")
            usuario = cam.get("usuario", "admin")
            
            # Verificar si tiene credenciales
            has_creds = ip in self.credentials_cache
            creds_indicator = "🔑" if has_creds else "❌"
            
            # Verificar si es PTZ
            is_ptz = tipo == "ptz"
            ptz_indicator = "🎯" if is_ptz else "📹"
            
            display_text = f"{ptz_indicator} {ip} ({usuario}) {creds_indicator}"
            self.selector.addItem(display_text, cam)  # Guardar datos de la cámara

    def _flush_log_buffer(self):
        """Aplica los logs que estaban en el buffer temporal"""
        if hasattr(self, '_log_buffer') and self._log_buffer:
            for message in self._log_buffer:
                if hasattr(self, 'log_area'):
                    self.log_area.append(message)
            self._log_buffer.clear()

    def _on_camera_changed(self, index):
        """Maneja el cambio de cámara seleccionada"""
        if index < 0 or index >= self.selector.count():
            return
            
        camera_data = self.selector.itemData(index)
        if not camera_data:
            return
            
        self.current_camera_data = camera_data
        ip = camera_data.get("ip")
        tipo = camera_data.get("tipo", "desconocido")
        
        # Actualizar información de la cámara
        creds = self.credentials_cache.get(ip, {})
        has_creds = bool(creds.get("usuario")) and bool(creds.get("contrasena"))
        
        info_parts = [
            f"IP: {ip}",
            f"Tipo: {tipo}",
            f"Usuario: {creds.get('usuario', 'N/A')}",
            f"Puerto: {creds.get('puerto', 'N/A')}",
        ]
        
        if has_creds:
            info_parts.append("✅ Credenciales disponibles")
        else:
            info_parts.append("❌ Sin credenciales")
            
        if tipo == "ptz":
            info_parts.append("🎯 Control PTZ disponible")
        else:
            info_parts.append("📹 Solo visualización (no PTZ)")
            
        self.camera_info_label.setText(" | ".join(info_parts))
        
        # Actualizar estado de la UI
        self._update_ui_state()
        
        self._log(f"📷 Cámara seleccionada: {ip} ({tipo})")

    def _update_ui_state(self):
        """Actualiza el estado de la interfaz según la cámara seleccionada"""
        if not self.current_camera_data:
            # Deshabilitar todos los controles
            self._set_controls_enabled(False)
            return
            
        ip = self.current_camera_data.get("ip")
        tipo = self.current_camera_data.get("tipo")
        has_creds = ip in self.credentials_cache and \
                   bool(self.credentials_cache[ip].get("usuario")) and \
                   bool(self.credentials_cache[ip].get("contrasena"))
        
        # Habilitar controles solo si hay credenciales
        self._set_controls_enabled(has_creds)
        
        # Mostrar advertencias si es necesario
        if not has_creds:
            self._log(f"⚠️ Sin credenciales para {ip} - controles deshabilitados")
        elif tipo != "ptz":
            self._log(f"ℹ️ {ip} no es PTZ - algunos controles pueden no funcionar")

    def _set_controls_enabled(self, enabled):
        """Habilita/deshabilita los controles PTZ"""
        controls = [
            self.btn_up, self.btn_down, self.btn_left, self.btn_right, self.btn_center,
            self.btn_zoom_in, self.btn_zoom_out, self.btn_goto_preset, self.btn_set_preset,
            self.btn_start_tracking, self.btn_stop_tracking, self.speed_spinbox, self.preset_spinbox
        ]
        
        for control in controls:
            control.setEnabled(enabled)
            
        # Habilitar gestión avanzada solo si está disponible Y hay credenciales
        if PRESET_DIALOG_AVAILABLE and hasattr(self, 'btn_advanced_presets'):
            self.btn_advanced_presets.setEnabled(enabled)
            
        # El botón de prueba siempre está habilitado si hay una cámara seleccionada
        self.btn_test_connection.setEnabled(bool(self.current_camera_data))

    def _connect_signals(self):
        """Conecta todas las señales de los controles"""
        # Controles direccionales
        self.btn_up.clicked.connect(lambda: self.move_command("Up"))
        self.btn_down.clicked.connect(lambda: self.move_command("Down"))
        self.btn_left.clicked.connect(lambda: self.move_command("Left"))
        self.btn_right.clicked.connect(lambda: self.move_command("Right"))
        self.btn_center.clicked.connect(lambda: self.move_command("Stop"))
        
        # Controles de zoom
        self.btn_zoom_in.clicked.connect(lambda: self.zoom_command("Tele"))
        self.btn_zoom_out.clicked.connect(lambda: self.zoom_command("Wide"))
        
        # Presets
        self.btn_goto_preset.clicked.connect(self.goto_preset)
        self.btn_set_preset.clicked.connect(self.set_preset)
        
        # Seguimiento
        self.btn_start_tracking.clicked.connect(self.start_tracking)
        self.btn_stop_tracking.clicked.connect(self.stop_tracking)
        
        # Otros
        self.btn_test_connection.clicked.connect(self.test_connection)
        self.btn_close.clicked.connect(self.close)

    def current_cam(self):
        """Retorna los datos de la cámara actual"""
        return self.current_camera_data

    def get_credentials(self, ip):
        """Obtiene las credenciales para una IP específica"""
        return self.credentials_cache.get(ip)

    def onvif_cam(self):
        """Obtiene/crea la instancia ONVIF para la cámara actual"""
        cam = self.current_cam()
        if not cam:
            self._log("❌ No hay cámara seleccionada")
            return None
            
        ip = cam.get("ip")
        creds = self.get_credentials(ip)
        
        if not creds:
            self._log(f"❌ No se encontraron credenciales para {ip}")
            return None
            
        port = creds.get('puerto', 80)
        user = creds.get('usuario')
        pwd = creds.get('contrasena')
        
        if not user or not pwd:
            self._log(f"❌ Credenciales incompletas para {ip}")
            return None
            
        key = f"{ip}:{port}"
        if key not in self.ptz_objects:
            try:
                self._log(f"🔧 Conectando a PTZ {ip}:{port} con usuario {user}")
                
                # Usar PTZ mejorado si está disponible, si no el básico
                if ENHANCED_PTZ_AVAILABLE:
                    self.ptz_objects[key] = create_enhanced_ptz_camera(ip, port, user, pwd)
                else:
                    self.ptz_objects[key] = PTZCameraONVIF(ip, port, user, pwd)
                    
                if self.ptz_objects[key]:
                    self._log(f"✅ Conexión PTZ establecida: {ip}")
                else:
                    self._log(f"❌ No se pudo crear instancia PTZ para {ip}")
                    return None
                    
            except Exception as e:
                self._log(f"❌ Error creando conexión PTZ {ip}: {e}")
                return None
                
        return self.ptz_objects[key]

    def move_command(self, direction: str):
        """Ejecuta comando de movimiento PTZ"""
        cam = self.onvif_cam()
        if not cam:
            return
            
        speed = self.speed_spinbox.value() / 10.0  # Convertir a rango 0.1-1.0
        
        try:
            if direction == "Up":
                cam.continuous_move(0, speed)
                self._log(f"⬆️ Movimiento: Arriba (velocidad: {speed})")
            elif direction == "Down":
                cam.continuous_move(0, -speed)
                self._log(f"⬇️ Movimiento: Abajo (velocidad: {speed})")
            elif direction == "Left":
                cam.continuous_move(-speed, 0)
                self._log(f"⬅️ Movimiento: Izquierda (velocidad: {speed})")
            elif direction == "Right":
                cam.continuous_move(speed, 0)
                self._log(f"➡️ Movimiento: Derecha (velocidad: {speed})")
            elif direction == "Stop":
                cam.stop()
                self._log("⏹️ Movimiento detenido")
                return  # No aplicar delay para stop
                
            # Aplicar movimiento por un tiempo corto
            time.sleep(0.3)
            cam.stop()
            
        except Exception as e:
            self._log(f"❌ Error en movimiento {direction}: {e}")

    def zoom_command(self, action: str):
        """Ejecuta comando de zoom"""
        cam = self.onvif_cam()
        if not cam:
            return
            
        speed = self.speed_spinbox.value() / 10.0
        
        try:
            z = speed if action == "Tele" else -speed
            cam.continuous_move(0, 0, z)
            self._log(f"🔍 Zoom: {action} (velocidad: {speed})")
            time.sleep(0.3)
            cam.stop()
        except Exception as e:
            self._log(f"❌ Error en zoom {action}: {e}")

    def goto_preset(self):
        """Va a un preset específico"""
        cam = self.onvif_cam()
        if not cam:
            return
            
        preset = self.preset_spinbox.value()
        
        try:
            cam.goto_preset(str(preset))
            self._log(f"📍 Movimiento a preset {preset}")
        except Exception as e:
            self._log(f"❌ Error yendo a preset {preset}: {e}")

    def set_preset(self):
        """Guarda la posición actual como preset"""
        preset = self.preset_spinbox.value()
        
        # Si tenemos PTZ mejorado, intentar usarlo
        cam = self.onvif_cam()
        if cam and ENHANCED_PTZ_AVAILABLE and hasattr(cam, 'set_preset'):
            try:
                success = cam.set_preset(str(preset), f"Preset {preset}")
                if success:
                    self._log(f"💾 Preset {preset} guardado exitosamente")
                else:
                    self._log(f"❌ Error guardando preset {preset}")
            except Exception as e:
                self._log(f"❌ Error guardando preset {preset}: {e}")
        else:
            self._log(f"💾 Funcionalidad de guardar preset {preset} no disponible con PTZ básico")

    def open_advanced_presets(self):
        """Abre el diálogo de gestión avanzada de presets"""
        if not PRESET_DIALOG_AVAILABLE:
            QMessageBox.information(
                self,
                "Función no disponible",
                "El diálogo de gestión avanzada de presets no está disponible.\n\n"
                "Archivo requerido: ui/ptz_preset_dialog.py"
            )
            return
            
        cam = self.onvif_cam()
        if not cam:
            QMessageBox.warning(
                self,
                "Sin conexión PTZ",
                "No hay conexión PTZ activa.\n"
                "Primero pruebe la conexión con la cámara seleccionada."
            )
            return
            
        try:
            dialog = PTZPresetDialog(self, self.current_camera_data, cam)
            dialog.preset_updated.connect(self._on_preset_updated)
            dialog.exec()
        except Exception as e:
            self._log(f"❌ Error abriendo gestión avanzada: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"❌ Error: No se pudo cargar el diálogo PTZ avanzado: {e}\n\n"
                f"💡 Asegúrese de que los archivos ptz_control_enhanced.py y ptz_preset_dialog.py estén presentes"
            )

    def _on_preset_updated(self, preset_number, preset_name):
        """Maneja la actualización de un preset"""
        self._log(f"✅ Preset {preset_number} actualizado: {preset_name}")

    def start_tracking(self):
        """Inicia seguimiento automático"""
        cam = self.current_cam()
        if not cam:
            return
            
        ip = cam.get("ip")
        creds = self.get_credentials(ip)
        
        if not creds:
            self._log(f"❌ No se pueden iniciar seguimiento sin credenciales para {ip}")
            return
            
        try:
            thread = threading.Thread(
                target=track_object_continuous,
                args=(ip, creds['puerto'], creds['usuario'], creds['contrasena'], 0, 0, 1920, 1080),
                daemon=True
            )
            thread.start()
            self.btn_start_tracking.setEnabled(False)
            self.btn_stop_tracking.setEnabled(True)
            self._log(f"🎯 Seguimiento iniciado para {ip}")
        except Exception as e:
            self._log(f"❌ Error iniciando seguimiento: {e}")

    def stop_tracking(self):
        """Detiene seguimiento automático"""
        self.btn_start_tracking.setEnabled(True)
        self.btn_stop_tracking.setEnabled(False)
        self._log("⏹️ Seguimiento detenido")

    def test_connection(self):
        """Prueba la conexión con la cámara seleccionada"""
        cam = self.current_cam()
        if not cam:
            return
            
        ip = cam.get("ip")
        creds = self.get_credentials(ip)
        
        if not creds:
            QMessageBox.warning(
                self, 
                "Sin credenciales", 
                f"No se encontraron credenciales para {ip}.\n\n"
                f"Verifica que la cámara esté configurada correctamente."
            )
            return
            
        try:
            self._log(f"🧪 Probando conexión a {ip}...")
            
            # Usar la clase básica para prueba de conexión
            test_cam = PTZCameraONVIF(ip, creds['puerto'], creds['usuario'], creds['contrasena'])
            
            QMessageBox.information(
                self, 
                "Conexión exitosa", 
                f"✅ Conexión establecida correctamente\n\n"
                f"IP: {ip}\n"
                f"Usuario: {creds['usuario']}\n"
                f"Puerto: {creds['puerto']}\n"
                f"Tipo: {creds.get('tipo', 'N/A')}"
            )
            self._log(f"✅ Conexión exitosa a {ip}")
            
        except Exception as e:
            QMessageBox.warning(
                self, 
                "Error de conexión", 
                f"❌ No se pudo conectar a {ip}\n\n"
                f"Error: {str(e)}\n\n"
                f"Verifica:\n"
                f"• IP y puerto correctos\n"
                f"• Usuario y contraseña\n"
                f"• Conexión de red\n"
                f"• Cámara encendida"
            )
            self._log(f"❌ Error de conexión a {ip}: {e}")

    def _log(self, message):
        """Agrega un mensaje al área de logs - VERSIÓN CORREGIDA"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        # Si log_area no existe aún, guardar en buffer temporal
        if not hasattr(self, 'log_area') or self.log_area is None:
            if not hasattr(self, '_log_buffer'):
                self._log_buffer = []
            self._log_buffer.append(formatted_message)
            print(f"PTZ Log (buffered): {formatted_message}")  # También imprimir en consola
            return
        
        # Si log_area existe, agregar el mensaje
        try:
            self.log_area.append(formatted_message)
            
            # Desplazar al final
            cursor = self.log_area.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.log_area.setTextCursor(cursor)
        except Exception as e:
            print(f"Error agregando mensaje al log: {e}")
            print(f"Mensaje original: {formatted_message}")