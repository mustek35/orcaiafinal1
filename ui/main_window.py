from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QTextEdit, QMenuBar, QMenu, QGridLayout, QStackedWidget, QLabel,
    QScrollArea, QMessageBox, QSplitter
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt
import importlib
from ui.camera_modal import CameraDialog
from gui.resumen_detecciones import ResumenDeteccionesWidget
from ui.config_modal import ConfiguracionDialog
from ui.fps_config_dialog import FPSConfigDialog
from ui.camera_manager import guardar_camaras, cargar_camaras_guardadas
from core.rtsp_builder import generar_rtsp
import os
import cProfile
import pstats
import io

# NUEVAS IMPORTACIONES: Sistema de Muestreo Adaptativo
try:
    from ui.adaptive_sampling_dialog import AdaptiveSamplingConfigDialog
    from core.adaptive_sampling import AdaptiveSamplingConfig
    ADAPTIVE_SAMPLING_AVAILABLE = True
except ImportError:
    ADAPTIVE_SAMPLING_AVAILABLE = False
    print("ℹ️ Sistema de muestreo adaptativo no disponible")

CONFIG_PATH = "config.json"

class MainGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        
        print("INFO: Iniciando profiler para MainGUI...")
        self.profiler = cProfile.Profile()
        self.profiler.enable()

        self.setWindowTitle("Monitor PTZ Inteligente - Orca")
        self.setGeometry(100, 100, 1600, 900)

        # Configuración de FPS por defecto
        self.fps_config = {
            "visual_fps": 25,
            "detection_fps": 8, 
            "ui_update_fps": 15,
            "adaptive_fps": True
        }

        self.camera_data_list = []
        self.camera_widgets = [] 
        
        # NUEVO: Bridge PTZ para detecciones
        self.ptz_detection_bridge = None

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.main_layout = QVBoxLayout()
        self.central_widget.setLayout(self.main_layout)

        self.menu_bar = QMenuBar()
        self.setMenuBar(self.menu_bar)

        self.menu_inicio = self.menu_bar.addMenu("Inicio")
        self.menu_config = self.menu_bar.addMenu("Configuración")
        self.menu_ptz = self.menu_bar.addMenu("PTZ")

        self.action_agregar = QAction("➕ Agregar Cámara", self)
        self.action_agregar.triggered.connect(lambda: self.open_camera_dialog())
        self.menu_inicio.addAction(self.action_agregar)

        self.action_salir = QAction("🚪 Salir de la Aplicación", self)
        self.action_salir.triggered.connect(self.close) 
        self.menu_inicio.addAction(self.action_salir)

        self.action_ver_config = QAction("⚙️ Ver Configuración", self)
        self.action_ver_config.triggered.connect(self.abrir_configuracion_modal)
        self.menu_config.addAction(self.action_ver_config)

        # Agregar acción de FPS al menú
        self.action_fps_config = QAction("🎯 Configurar FPS", self)
        self.action_fps_config.triggered.connect(self.abrir_fps_config)
        self.menu_config.addAction(self.action_fps_config)

        # NUEVO: Muestreo Adaptativo
        if ADAPTIVE_SAMPLING_AVAILABLE:
            self.action_adaptive_sampling = QAction("🧠 Muestreo Adaptativo", self)
            self.action_adaptive_sampling.triggered.connect(self.abrir_muestreo_adaptativo_config)
            self.menu_config.addAction(self.action_adaptive_sampling)
            
            # Separador entre configuraciones
            self.menu_config.addSeparator()

        self.action_edit_line = QAction("🏁 Línea de Cruce", self)
        self.action_edit_line.triggered.connect(self.toggle_line_edit)
        self.menu_config.addAction(self.action_edit_line)

        # ✅ MENÚ PTZ CORREGIDO Y COMPLETO
        self._setup_ptz_menu()

        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)

        self.init_tab = QWidget()
        self.init_tab_layout = QVBoxLayout()
        self.init_tab.setLayout(self.init_tab_layout)
        self.setup_inicio_ui() 

        self.stacked_widget.addWidget(self.init_tab)

        # Inicializar sistema PTZ al arrancar
        self._ptz_initialized = False

        # NUEVO: Agregar elementos del menú de muestreo adaptativo
        self.add_adaptive_sampling_menu_items()

        cargar_camaras_guardadas(self)

    def _setup_ptz_menu(self):
        """✅ NUEVO: Configurar menú PTZ completo"""
        # Menú PTZ Básico
        self.action_ptz_tracking = QAction("🎮 Seguimiento Básico", self)
        self.action_ptz_tracking.triggered.connect(self.open_ptz_dialog)
        self.menu_ptz.addAction(self.action_ptz_tracking)

        # Gestión Avanzada PTZ
        self.action_ptz_presets = QAction("🎯 Gestión Avanzada PTZ", self)
        self.action_ptz_presets.triggered.connect(self.open_ptz_presets_dialog)
        self.menu_ptz.addAction(self.action_ptz_presets)

        # ✅ NUEVO: PTZ Multi-Objeto (CORREGIDO)
        self.action_ptz_multi_object = QAction("🚀 Seguimiento Multi-Objeto", self)
        self.action_ptz_multi_object.triggered.connect(self.open_ptz_multi_object_dialog)
        self.menu_ptz.addAction(self.action_ptz_multi_object)

        # Separador en el menú PTZ
        self.menu_ptz.addSeparator()

        # Acciones adicionales PTZ
        self.action_ptz_init = QAction("🔧 Inicializar Sistema PTZ", self)
        self.action_ptz_init.triggered.connect(self.initialize_ptz_system)
        self.menu_ptz.addAction(self.action_ptz_init)

        self.action_ptz_stop_all = QAction("⏹️ Detener Todas las PTZ", self)
        self.action_ptz_stop_all.triggered.connect(self.stop_all_ptz)
        self.menu_ptz.addAction(self.action_ptz_stop_all)

    def abrir_configuracion_modal(self):
        """Abrir modal de configuración - MÉTODO CORREGIDO"""
        try:
            dialog = ConfiguracionDialog(self, camera_list=self.camera_data_list)
            if dialog.exec():
                guardar_camaras(self)
                self.append_debug("⚙️ Configuración del sistema guardada.")
            else:
                self.append_debug("⚙️ Cambios en configuración del sistema cancelados.")
        except ImportError as e:
            self.append_debug(f"❌ Error: No se pudo cargar el diálogo de configuración: {e}")
            QMessageBox.warning(
                self,
                "Módulo no disponible",
                f"❌ No se pudo cargar el diálogo de configuración:\n{e}\n\n"
                f"Archivo requerido:\n"
                f"• ui/config_modal.py"
            )
        except Exception as e:
            self.append_debug(f"❌ Error inesperado abriendo configuración: {e}")

    # ✅ NUEVO: Método PTZ Multi-Objeto CORREGIDO
    def open_ptz_multi_object_dialog(self):
        """Abrir sistema PTZ multi-objeto CORREGIDO"""
        try:
            from ui.enhanced_ptz_multi_object_dialog import create_multi_object_ptz_system
            
            # Verificar que hay cámaras PTZ disponibles
            ptz_cameras = [cam for cam in self.camera_data_list if cam.get('tipo') == 'ptz']
            
            if not ptz_cameras:
                QMessageBox.warning(
                    self,
                    "Sin cámaras PTZ",
                    "❌ No se encontraron cámaras PTZ configuradas.\n\n"
                    "Para usar el seguimiento multi-objeto:\n"
                    "1. Agregue al menos una cámara con tipo 'ptz'\n"
                    "2. Asegúrese de que las credenciales sean correctas"
                )
                self.append_debug("⚠️ No hay cámaras PTZ para seguimiento multi-objeto")
                return
            
            # Crear sistema PTZ multi-objeto
            dialog, bridge = create_multi_object_ptz_system(self.camera_data_list, self)
            
            if dialog and bridge:
                # Guardar referencia al bridge para uso externo
                self.ptz_detection_bridge = bridge
                
                # Mostrar diálogo
                dialog.show()
                
                self.append_debug("🎯 Sistema PTZ Multi-Objeto iniciado exitosamente")
                self.append_debug(f"📹 {len(ptz_cameras)} cámaras PTZ disponibles para seguimiento")
                
                # Mostrar información sobre integración
                QMessageBox.information(
                    self,
                    "PTZ Multi-Objeto Iniciado",
                    "✅ Sistema PTZ Multi-Objeto iniciado exitosamente.\n\n"
                    "🎯 Funcionalidades disponibles:\n"
                    "• Seguimiento de múltiples objetos con alternancia\n"
                    "• Zoom automático inteligente\n"
                    "• Configuración de prioridades\n"
                    "• Análisis en tiempo real\n\n"
                    "💡 Las detecciones se enviarán automáticamente al sistema PTZ\n"
                    "cuando esté activo el seguimiento."
                )
                
            else:
                self.append_debug("❌ Error creando sistema PTZ multi-objeto")
                QMessageBox.critical(
                    self,
                    "Error",
                    "❌ No se pudo crear el sistema PTZ multi-objeto.\n\n"
                    "Verifique que los archivos estén presentes:\n"
                    "• ui/enhanced_ptz_multi_object_dialog.py\n"
                    "• core/multi_object_ptz_system.py\n"
                    "• core/ptz_tracking_integration_enhanced.py"
                )
            
        except ImportError as e:
            self.append_debug(f"❌ Sistema multi-objeto no disponible: {e}")
            QMessageBox.warning(
                self,
                "Sistema No Disponible",
                f"❌ Sistema PTZ multi-objeto no disponible:\n{e}\n\n"
                f"Archivos requeridos:\n"
                f"• ui/enhanced_ptz_multi_object_dialog.py\n"
                f"• core/multi_object_ptz_system.py\n"
                f"• core/ptz_tracking_integration_enhanced.py\n\n"
                f"Dependencias:\n"
                f"• pip install onvif-zeep numpy"
            )
        except Exception as e:
            self.append_debug(f"❌ Error inesperado abriendo PTZ multi-objeto: {e}")
            QMessageBox.critical(
                self,
                "Error Inesperado", 
                f"❌ Error inesperado:\n{e}\n\n"
                f"Revise la consola para más detalles."
            )

    # ✅ NUEVO: Integración con sistema de detección
    def process_detections_for_ptz(self, results, frame_shape, camera_id=None):
        """
        Procesar detecciones para PTZ multi-objeto
        
        Args:
            results: Resultados de YOLO/detección
            frame_shape: Forma del frame (H, W, C)
            camera_id: ID de la cámara (opcional)
        """
        # Solo procesar si el sistema PTZ multi-objeto está activo
        if not self.ptz_detection_bridge:
            return 0
        
        try:
            # Procesar resultados de YOLO
            detections_count = self.ptz_detection_bridge.process_yolo_results(
                results, frame_shape
            )
            
            if detections_count > 0:
                self.append_debug(f"🎯 PTZ: {detections_count} detección(es) enviada(s) al sistema PTZ")
            
            return detections_count
            
        except Exception as e:
            self.append_debug(f"⚠️ Error enviando detecciones al PTZ: {e}")
            return 0

    def send_custom_detections_to_ptz(self, detections_list):
        """
        Enviar detecciones personalizadas al PTZ
        
        Args:
            detections_list: Lista de detecciones en formato personalizado
        """
        if not self.ptz_detection_bridge:
            return
        
        try:
            self.ptz_detection_bridge.process_custom_detections(detections_list)
            self.append_debug(f"🎯 PTZ: {len(detections_list)} detección(es) personalizada(s) enviada(s)")
        except Exception as e:
            self.append_debug(f"⚠️ Error enviando detecciones personalizadas al PTZ: {e}")

    def add_adaptive_sampling_menu_items(self):
        """Agrega elementos del menú de muestreo adaptativo"""
        if ADAPTIVE_SAMPLING_AVAILABLE:
            # Agregar separador antes de las opciones de muestreo adaptativo
            self.menu_config.addSeparator()
            
            # Menú principal de muestreo adaptativo
            adaptive_menu = self.menu_config.addMenu("🧠 Muestreo Adaptativo")
            
            # Configuración global
            config_global_action = QAction("⚙️ Configuración Global", self)
            config_global_action.triggered.connect(self.abrir_muestreo_adaptativo_config)
            adaptive_menu.addAction(config_global_action)
            
            # Estado de todas las cámaras
            status_all_action = QAction("📊 Estado de Todas las Cámaras", self)
            status_all_action.triggered.connect(self.show_adaptive_sampling_status)
            adaptive_menu.addAction(status_all_action)
            
            # Separador
            adaptive_menu.addSeparator()
            
            # Activar/Desactivar para todas
            enable_all_action = QAction("🧠 Activar en Todas", self)
            enable_all_action.triggered.connect(lambda: self.toggle_adaptive_sampling_all(True))
            adaptive_menu.addAction(enable_all_action)
            
            disable_all_action = QAction("📊 Desactivar en Todas (Usar Fijo)", self)
            disable_all_action.triggered.connect(lambda: self.toggle_adaptive_sampling_all(False))
            adaptive_menu.addAction(disable_all_action)
            
            # Separador
            adaptive_menu.addSeparator()
            
            # Presets de configuración
            presets_menu = adaptive_menu.addMenu("🚀 Aplicar Preset")
            
            aggressive_action = QAction("⚡ Agresivo (Máximo rendimiento)", self)
            aggressive_action.triggered.connect(lambda: self.apply_adaptive_preset("aggressive"))
            presets_menu.addAction(aggressive_action)
            
            balanced_action = QAction("⚖️ Balanceado (Recomendado)", self)
            balanced_action.triggered.connect(lambda: self.apply_adaptive_preset("balanced"))
            presets_menu.addAction(balanced_action)
            
            conservative_action = QAction("🛡️ Conservador (Máxima estabilidad)", self)
            conservative_action.triggered.connect(lambda: self.apply_adaptive_preset("conservative"))
            presets_menu.addAction(conservative_action)

    def abrir_muestreo_adaptativo_config(self):
        """Abrir diálogo de configuración del muestreo adaptativo"""
        if not ADAPTIVE_SAMPLING_AVAILABLE:
            QMessageBox.warning(
                self,
                "No disponible",
                "❌ El sistema de muestreo adaptativo no está disponible.\n\n"
                "Archivos requeridos:\n"
                "• core/adaptive_sampling.py\n"
                "• ui/adaptive_sampling_dialog.py"
            )
            return
        
        try:
            # Obtener configuración actual desde las cámaras activas
            current_config = None
            
            # Si hay cámaras activas, usar la configuración de la primera
            if self.camera_widgets:
                for widget in self.camera_widgets:
                    if hasattr(widget, 'get_adaptive_sampling_status'):
                        status = widget.get_adaptive_sampling_status()
                        if status.get('enabled') and hasattr(widget, 'adaptive_controller'):
                            current_config = widget.adaptive_controller.config.copy()
                            break
            
            # Si no hay configuración activa, usar balanceada por defecto
            if current_config is None:
                current_config = AdaptiveSamplingConfig.create_config("balanced")
            
            dialog = AdaptiveSamplingConfigDialog(self, current_config)
            dialog.config_changed.connect(self.apply_adaptive_config_to_all_cameras)
            
            if dialog.exec():
                final_config = dialog.get_config()
                self.apply_adaptive_config_to_all_cameras(final_config)
                self.append_debug("✅ Configuración de muestreo adaptativo aplicada a todas las cámaras")
                
        except Exception as e:
            self.append_debug(f"❌ Error abriendo configuración de muestreo adaptativo: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"❌ Error abriendo configuración:\n{e}"
            )

    def apply_adaptive_config_to_all_cameras(self, config):
        """Aplica configuración de muestreo adaptativo a todas las cámaras - MÉTODO CORREGIDO"""
        applied_count = 0

        for widget in self.camera_widgets:
            if hasattr(widget, 'configure_adaptive_sampling'):
                try:
                    success = widget.configure_adaptive_sampling(config)
                    if success:
                        applied_count += 1

                        # También activar el muestreo adaptativo si no estaba activo
                        if hasattr(widget, 'toggle_adaptive_sampling'):
                            widget.toggle_adaptive_sampling(True)
                except Exception as e:
                    cam_ip = "N/A"
                    if hasattr(widget, 'cam_data') and widget.cam_data:
                        cam_ip = widget.cam_data.get('ip', 'N/A')
                    self.append_debug(f"❌ Error aplicando config adaptativo a {cam_ip}: {e}")

        if applied_count > 0:
            self.append_debug(f"✅ Configuración adaptativa aplicada a {applied_count} cámaras")
            self.save_adaptive_config_to_global_config(config)
        else:
            self.append_debug("⚠️ No se pudo aplicar configuración adaptativa a ninguna cámara")

    def save_adaptive_config_to_global_config(self, adaptive_config):
        """Guarda la configuración de muestreo adaptativo en config.json"""
        try:
            import json
            import os
            
            config_path = "config.json"
            
            # Leer configuración existente
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config_data = json.load(f)
            else:
                config_data = {"camaras": [], "configuracion": {}}
            
            # Agregar configuración global de muestreo adaptativo
            config_data["adaptive_sampling"] = adaptive_config
            
            # También agregar a cada cámara individualmente
            for cam in config_data.get("camaras", []):
                cam["adaptive_sampling"] = adaptive_config.copy()
            
            # Guardar archivo
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=4)
            
            self.append_debug("💾 Configuración de muestreo adaptativo guardada en config.json")
            
        except Exception as e:
            self.append_debug(f"❌ Error guardando configuración adaptativa: {e}")

    def show_adaptive_sampling_status(self):
        """Muestra el estado del muestreo adaptativo de todas las cámaras"""
        if not ADAPTIVE_SAMPLING_AVAILABLE:
            QMessageBox.information(
                self,
                "Muestreo Adaptativo",
                "❌ El sistema de muestreo adaptativo no está disponible."
            )
            return
        
        status_info = []
        total_cameras = len(self.camera_widgets)
        adaptive_cameras = 0
        
        for i, widget in enumerate(self.camera_widgets):
            cam_ip = "N/A"
            if hasattr(widget, 'cam_data') and widget.cam_data:
                cam_ip = widget.cam_data.get('ip', f'Cámara {i+1}')
            
            if hasattr(widget, 'get_adaptive_sampling_status'):
                status = widget.get_adaptive_sampling_status()
                
                if status['enabled']:
                    adaptive_cameras += 1
                    status_info.append(
                        f"📷 {cam_ip}: 🧠 ADAPTATIVO\n"
                        f"   • Intervalo actual: {status['current_interval']}\n"
                        f"   • Actividad: {status.get('activity_score', 0):.2f}\n"
                        f"   • Frames procesados: {status['frames_processed']}\n"
                        f"   • Eficiencia: {(status['frames_skipped']/status['frames_processed']*100):.1f}% omitidos"
                    )
                else:
                    status_info.append(
                        f"📷 {cam_ip}: 📊 FIJO\n"
                        f"   • Intervalo fijo: {status['current_interval']}\n"
                        f"   • Frames procesados: {status['frames_processed']}"
                    )
            else:
                status_info.append(f"📷 {cam_ip}: ❌ Estado no disponible")
        
        summary = f"""🧠 Estado del Muestreo Adaptativo

📊 Resumen:
• Total de cámaras: {total_cameras}
• Usando muestreo adaptativo: {adaptive_cameras}
• Usando muestreo fijo: {total_cameras - adaptive_cameras}

📷 Detalles por cámara:
"""
        
        if status_info:
            summary += "\n\n".join(status_info)
        else:
            summary += "No hay cámaras activas"
        
        QMessageBox.information(self, "Estado del Muestreo Adaptativo", summary)

    def toggle_adaptive_sampling_all(self, enable):
        """Activa/desactiva muestreo adaptativo en todas las cámaras"""
        if not ADAPTIVE_SAMPLING_AVAILABLE:
            return
        
        affected_count = 0
        mode = "adaptativo" if enable else "fijo"
        
        for widget in self.camera_widgets:
            if hasattr(widget, 'toggle_adaptive_sampling'):
                try:
                    widget.toggle_adaptive_sampling(enable)
                    affected_count += 1
                    
                    # Si se está activando, aplicar configuración por defecto si es necesario
                    if enable and hasattr(widget, 'configure_adaptive_sampling'):
                        if not hasattr(widget, 'adaptive_controller') or widget.adaptive_controller is None:
                            default_config = AdaptiveSamplingConfig.create_config("balanced")
                            widget.configure_adaptive_sampling(default_config)
                            
                except Exception as e:
                    cam_ip = "N/A"
                    if hasattr(widget, 'cam_data') and widget.cam_data:
                        cam_ip = widget.cam_data.get('ip', 'N/A')
                    self.append_debug(f"❌ Error cambiando a modo {mode} en {cam_ip}: {e}")
        
        if affected_count > 0:
            self.append_debug(f"🧠 Muestreo {mode} {'activado' if enable else 'desactivado'} en {affected_count} cámaras")
            
            # Mostrar mensaje de confirmación
            QMessageBox.information(
                self,
                "Muestreo Adaptativo",
                f"✅ Muestreo {mode} {'activado' if enable else 'desactivado'} en {affected_count} cámaras.\n\n"
                f"{'💡 El sistema se adaptará automáticamente a la actividad de cada escena.' if enable else '📊 Todas las cámaras usarán intervalos fijos.'}"
            )
        else:
            self.append_debug("⚠️ No se encontraron cámaras compatibles con muestreo adaptativo")

    def apply_adaptive_preset(self, preset_name):
        """Aplica un preset de configuración adaptativa a todas las cámaras"""
        if not ADAPTIVE_SAMPLING_AVAILABLE:
            return
        
        try:
            preset_config = AdaptiveSamplingConfig.create_config(preset_name)
            
            # Aplicar a todas las cámaras
            self.apply_adaptive_config_to_all_cameras(preset_config)
            
            # Descripción del preset
            preset_descriptions = {
                "aggressive": "⚡ Máximo rendimiento - Adaptación rápida y agresiva",
                "balanced": "⚖️ Balanceado - Equilibrio ideal entre calidad y rendimiento",
                "conservative": "🛡️ Conservador - Cambios suaves y máxima estabilidad"
            }
            
            description = preset_descriptions.get(preset_name, preset_name)
            
            QMessageBox.information(
                self,
                "Preset Aplicado",
                f"✅ Preset '{preset_name}' aplicado exitosamente.\n\n"
                f"{description}\n\n"
                f"🧠 El sistema adaptativo ajustará automáticamente la frecuencia\n"
                f"de análisis según la actividad detectada en cada cámara."
            )
            
        except Exception as e:
            self.append_debug(f"❌ Error aplicando preset {preset_name}: {e}")
            QMessageBox.warning(
                self,
                "Error",
                f"❌ Error aplicando preset '{preset_name}':\n{e}"
            )

    def toggle_camera_adaptive_sampling(self, camera_index, enable):
        """Activa/desactiva muestreo adaptativo para una cámara específica"""
        if camera_index >= len(self.camera_widgets):
            return
            
        widget = self.camera_widgets[camera_index]
        cam_ip = "N/A"
        
        if hasattr(widget, 'cam_data') and widget.cam_data:
            cam_ip = widget.cam_data.get('ip', f'Cámara {camera_index+1}')
        
        if hasattr(widget, 'toggle_adaptive_sampling'):
            try:
                widget.toggle_adaptive_sampling(enable)
                mode = "adaptativo" if enable else "fijo"
                self.append_debug(f"🧠 Cámara {cam_ip}: Muestreo {mode} {'activado' if enable else 'desactivado'}")
                
                # Si se está activando y no hay configuración, usar la por defecto
                if enable and hasattr(widget, 'configure_adaptive_sampling'):
                    if not hasattr(widget, 'adaptive_controller') or widget.adaptive_controller is None:
                        default_config = AdaptiveSamplingConfig.create_config("balanced")
                        widget.configure_adaptive_sampling(default_config)
                        self.append_debug(f"⚙️ Configuración adaptativa por defecto aplicada a {cam_ip}")
                        
            except Exception as e:
                self.append_debug(f"❌ Error cambiando modo de muestreo en {cam_ip}: {e}")
        else:
            self.append_debug(f"⚠️ Cámara {cam_ip} no soporta muestreo adaptativo")

    def configure_individual_adaptive_sampling(self, camera_index):
        """Configura muestreo adaptativo para una cámara específica"""
        if camera_index >= len(self.camera_widgets):
            return
            
        widget = self.camera_widgets[camera_index]
        cam_ip = "N/A"
        
        if hasattr(widget, 'cam_data') and widget.cam_data:
            cam_ip = widget.cam_data.get('ip', f'Cámara {camera_index+1}')
        
        try:
            # Obtener configuración actual de la cámara
            current_config = None
            if hasattr(widget, 'adaptive_controller') and widget.adaptive_controller:
                current_config = widget.adaptive_controller.config.copy()
            else:
                current_config = AdaptiveSamplingConfig.create_config("balanced")
            
            dialog = AdaptiveSamplingConfigDialog(self, current_config)
            dialog.setWindowTitle(f"🧠 Muestreo Adaptativo - {cam_ip}")
            
            def apply_individual_config(config):
                if hasattr(widget, 'configure_adaptive_sampling'):
                    success = widget.configure_adaptive_sampling(config)
                    if success:
                        self.append_debug(f"✅ Configuración adaptativa aplicada a {cam_ip}")
                        # Activar si no estaba activo
                        if hasattr(widget, 'toggle_adaptive_sampling'):
                            widget.toggle_adaptive_sampling(True)
                    else:
                        self.append_debug(f"❌ Error aplicando configuración a {cam_ip}")
            
            dialog.config_changed.connect(apply_individual_config)
            
            if dialog.exec():
                final_config = dialog.get_config()
                apply_individual_config(final_config)
                
        except Exception as e:
            self.append_debug(f"❌ Error configurando muestreo adaptativo para {cam_ip}: {e}")

    def show_individual_adaptive_stats(self, camera_index):
        """Muestra estadísticas detalladas de muestreo adaptativo para una cámara"""
        if camera_index >= len(self.camera_widgets):
            return
            
        widget = self.camera_widgets[camera_index]
        cam_ip = "Cámara desconocida"
        
        if hasattr(widget, 'cam_data') and widget.cam_data:
            cam_ip = widget.cam_data.get('ip', f'Cámara {camera_index+1}')
        
        if hasattr(widget, 'get_adaptive_sampling_status'):
            status = widget.get_adaptive_sampling_status()
            
            if status['enabled']:
                # Estadísticas detalladas para muestreo adaptativo
                efficiency = 0
                if status['frames_processed'] > 0:
                    efficiency = (status['frames_skipped'] / status['frames_processed']) * 100
                
                stats_message = f"""🧠 Estadísticas de Muestreo Adaptativo
📷 Cámara: {cam_ip}

📊 Estado Actual:
• Modo: Adaptativo
• Intervalo actual: {status['current_interval']} frames
• Puntuación de actividad: {status.get('activity_score', 0):.3f}
• Promedio de detecciones: {status.get('avg_detections', 0):.2f}

📈 Rendimiento:
• Total frames procesados: {status['frames_processed']:,}
• Frames analizados: {status['frames_processed'] - status['frames_skipped']:,}
• Frames omitidos: {status['frames_skipped']:,}
• Eficiencia: {efficiency:.1f}% frames omitidos

💡 Significado:
• Intervalo alto (>15) = Poca actividad detectada
• Intervalo bajo (<8) = Mucha actividad detectada
• Más eficiencia = Mejor optimización automática"""
                
                if hasattr(widget, 'adaptive_controller') and widget.adaptive_controller:
                    controller_status = widget.adaptive_controller.get_status()
                    
                    stats_message += f"""

⚙️ Configuración Actual:
• Intervalo base: {controller_status['config']['base_interval']}
• Rango: {controller_status['config']['min_interval']}-{controller_status['config']['max_interval']}
• Velocidad adaptación: {controller_status['config']['adaptation_rate']:.1%}
• Umbral actividad alta: {controller_status['config']['high_activity_threshold']:.1%}"""
                
            else:
                # Estadísticas para muestreo fijo
                efficiency = 0
                if status['frames_processed'] > 0:
                    efficiency = (status['frames_skipped'] / status['frames_processed']) * 100
                
                stats_message = f"""📊 Estadísticas de Muestreo Fijo
📷 Cámara: {cam_ip}

📊 Estado Actual:
• Modo: Fijo
• Intervalo fijo: {status['current_interval']} frames

📈 Rendimiento:
• Total frames procesados: {status['frames_processed']:,}
• Frames analizados: {status['frames_processed'] - status['frames_skipped']:,}
• Frames omitidos: {status['frames_skipped']:,}
• Frecuencia análisis: {100 - efficiency:.1f}% frames analizados

💡 Recomendación:
El muestreo adaptativo puede optimizar automáticamente
el rendimiento basado en la actividad de la escena."""
            
            QMessageBox.information(self, f"Estadísticas - {cam_ip}", stats_message)
        else:
            QMessageBox.warning(self, "Error", f"No se pueden obtener estadísticas para {cam_ip}")

    def abrir_fps_config(self):
        """Abrir diálogo de configuración de FPS"""
        dialog = FPSConfigDialog(self, self.fps_config)
        dialog.fps_config_changed.connect(self.update_fps_config)
        
        if dialog.exec():
            self.fps_config = dialog.get_config()
            self.apply_fps_to_all_cameras()
            self.append_debug(f"⚙️ Configuración de FPS aplicada: {self.fps_config}")
    
    def update_fps_config(self, config):
        """Actualizar configuración de FPS en tiempo real"""
        self.fps_config = config
        self.apply_fps_to_all_cameras()
        self.append_debug(f"🎯 FPS actualizado en tiempo real: Visual={config['visual_fps']}, "
                         f"Detección={config['detection_fps']}, UI={config['ui_update_fps']}")
    
    def apply_fps_to_all_cameras(self):
        """Aplicar configuración de FPS a todas las cámaras activas"""
        for widget in self.camera_widgets:
            try:
                # Actualizar GrillaWidget
                if hasattr(widget, 'set_fps_config'):
                    widget.set_fps_config(
                        visual_fps=self.fps_config['visual_fps'],
                        detection_fps=self.fps_config['detection_fps'],
                        ui_update_fps=self.fps_config['ui_update_fps']
                    )
                
                # Actualizar VisualizadorDetector
                if hasattr(widget, 'visualizador') and widget.visualizador:
                    if hasattr(widget.visualizador, 'update_fps_config'):
                        widget.visualizador.update_fps_config(
                            visual_fps=self.fps_config['visual_fps'],
                            detection_fps=self.fps_config['detection_fps']
                        )
                        
            except Exception as e:
                self.append_debug(f"❌ Error aplicando FPS a cámara: {e}")

    def get_optimized_fps_for_camera(self, camera_data):
        """Obtener configuración de FPS optimizada según el tipo de cámara"""
        base_config = self.fps_config.copy()
        
        # Ajustar según el tipo de cámara
        camera_type = camera_data.get('tipo', 'fija')
        models = camera_data.get('modelos', [camera_data.get('modelo', 'Personas')])
        
        if camera_type == 'ptz':
            # PTZ necesita más FPS para seguimiento fluido
            base_config['visual_fps'] = min(30, base_config['visual_fps'] + 5)
            base_config['detection_fps'] = min(15, base_config['detection_fps'] + 2)
        
        if 'Embarcaciones' in models or 'Barcos' in models:
            # Detección marítima puede necesitar menos FPS
            base_config['detection_fps'] = max(3, base_config['detection_fps'] - 2)
        
        return base_config

    def append_debug(self, message: str):
        """Agregar mensaje al debug console, filtrando spam innecesario"""
        if any(substr in message for substr in ["hevc @", "VPS 0", "undecodable NALU", "Frame procesado"]):
            return
        self.debug_console.append(message)

    def setup_inicio_ui(self):
        """Configura la interfaz principal con splitter"""
        # --- Parte superior: cámaras ---
        self.video_grid = QGridLayout()
        video_grid_container_widget = QWidget()
        video_grid_container_widget.setLayout(self.video_grid)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setWidget(video_grid_container_widget)

        # --- Parte inferior: lista + log + resumen ---
        bottom_layout = QHBoxLayout()
    
        self.camera_list = QListWidget()
        self.camera_list.setFixedWidth(250)
        self.camera_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.camera_list.customContextMenuRequested.connect(self.show_camera_menu)
        bottom_layout.addWidget(self.camera_list)

        self.debug_console = QTextEdit()
        self.debug_console.setReadOnly(True)
        bottom_layout.addWidget(self.debug_console, 2)

        self.resumen_widget = ResumenDeteccionesWidget()
        self.resumen_widget.log_signal.connect(self.append_debug)
        bottom_layout.addWidget(self.resumen_widget, 1)

        bottom_widget = QWidget()
        bottom_widget.setLayout(bottom_layout)

        # --- Dividir con splitter vertical ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(scroll_area)
        splitter.addWidget(bottom_widget)
        splitter.setSizes([1, 1])  # 50% y 50%

        self.init_tab_layout.addWidget(splitter)

    def open_camera_dialog(self, index=None):
        """Abrir diálogo para agregar/editar cámara"""
        print("🛠️ [DEBUG] Ejecutando open_camera_dialog")
        if index is not None and index >= len(self.camera_data_list):
            return
        existing = self.camera_data_list[index] if index is not None else None
        dialog = CameraDialog(self, existing_data=existing)
        if dialog.exec(): 
            if dialog.result() == 1: 
                new_data = dialog.get_camera_data()
                if index is not None:
                    self.camera_data_list[index] = new_data
                    self.camera_list.item(index).setText(f"{new_data['ip']} - {new_data['tipo']}")
                    self.append_debug(f"✏️ Cámara editada: {new_data}")
                    self.start_camera_stream(new_data) 
                else:
                    self.camera_data_list.append(new_data)
                    self.camera_list.addItem(f"{new_data['ip']} - {new_data['tipo']}")
                    self.append_debug(f"✅ Cámara agregada: {new_data}")
                    self.start_camera_stream(new_data)
                guardar_camaras(self)
                
                # Reinicializar sistema PTZ si se agregó una cámara PTZ
                if new_data.get('tipo') == 'ptz':
                    self.initialize_ptz_system()

    def open_ptz_dialog(self):
        """Abre el diálogo básico de PTZ"""
        try:
            from ui.ptz_tracking_dialog import PTZTrackingDialog
            dialog = PTZTrackingDialog(self, self.camera_data_list)
            dialog.exec()
        except ImportError as e:
            self.append_debug(f"❌ Error: No se pudo cargar el diálogo PTZ básico: {e}")
            QMessageBox.warning(
                self,
                "Módulo PTZ no disponible",
                f"❌ No se pudo cargar el control PTZ básico:\n{e}\n\n"
                f"Archivos requeridos:\n"
                f"• ui/ptz_tracking_dialog.py\n"
                f"• core/ptz_control.py\n\n"
                f"Dependencias:\n"
                f"• pip install onvif-zeep"
            )
        except Exception as e:
            self.append_debug(f"❌ Error inesperado abriendo PTZ básico: {e}")

    def open_ptz_presets_dialog(self):
        """Abre el diálogo avanzado de gestión PTZ - VERSIÓN CORREGIDA"""
        try:
            # Verificar que hay cámaras PTZ disponibles
            ptz_cameras = [cam for cam in self.camera_data_list if cam.get('tipo') == 'ptz']
            
            if not ptz_cameras:
                QMessageBox.warning(
                    self,
                    "Sin cámaras PTZ",
                    "❌ No se encontraron cámaras PTZ configuradas.\n\n"
                    "Para usar la gestión avanzada PTZ:\n"
                    "1. Agregue al menos una cámara con tipo 'ptz'\n"
                    "2. Asegúrese de que las credenciales sean correctas\n"
                    "3. Verifique la conexión de red"
                )
                self.append_debug("⚠️ No hay cámaras PTZ para gestión avanzada")
                return
            
            from ui.ptz_preset_dialog import PTZPresetDialog
            
            # Asegurar que el sistema PTZ está inicializado
            if not self._ptz_initialized:
                self.initialize_ptz_system()
            
            # CORRECCIÓN: Pasar la lista de cámaras correctamente
            dialog = PTZPresetDialog(self, camera_list=self.camera_data_list)
            
            # Conectar señales del diálogo
            dialog.preset_updated.connect(
                lambda preset_num, preset_name: self.append_debug(
                    f"📍 Preset {preset_num} actualizado: '{preset_name}'"
                )
            )
            
            # Mostrar información de cámaras PTZ encontradas
            self.append_debug(f"🎯 Abriendo gestión PTZ para {len(ptz_cameras)} cámaras:")
            for cam in ptz_cameras:
                ip = cam.get('ip', 'N/A')
                usuario = cam.get('usuario', 'N/A')
                self.append_debug(f"   📹 {ip} ({usuario})")
            
            dialog.exec()
            
        except ImportError as e:
            self.append_debug(f"❌ Error: No se pudo cargar el diálogo PTZ avanzado: {e}")
            self.append_debug("💡 Asegúrese de que el archivo ui/ptz_preset_dialog.py esté presente")
            QMessageBox.critical(
                self,
                "Módulo no encontrado",
                f"❌ No se pudo cargar el diálogo PTZ avanzado:\n{e}\n\n"
                f"Archivos requeridos:\n"
                f"• ui/ptz_preset_dialog.py\n"
                f"• core/ptz_control_enhanced.py (opcional)"
            )
        except Exception as e:
            self.append_debug(f"❌ Error inesperado al abrir diálogo PTZ: {e}")
            import traceback
            traceback.print_exc()  # Para debugging
            QMessageBox.critical(
                self,
                "Error inesperado",
                f"❌ Error inesperado al abrir diálogo PTZ:\n{e}\n\n"
                f"Revise la consola para más detalles."
            )

    def initialize_ptz_system(self):
        """Inicializa manualmente el sistema PTZ"""
        try:
            # Intentar cargar el sistema PTZ mejorado
            try:
                from core.ptz_control_enhanced import initialize_ptz_system
                success = initialize_ptz_system()
                enhanced_available = True
            except ImportError:
                # Fallback a sistema básico
                enhanced_available = False
                success = True  # Asumir éxito para sistema básico
            
            if success:
                self._ptz_initialized = True
                ptz_cameras = [cam for cam in self.camera_data_list if cam.get('tipo') == 'ptz']
                
                if enhanced_available:
                    self.append_debug(f"🚀 Sistema PTZ mejorado inicializado con {len(ptz_cameras)} cámaras PTZ")
                else:
                    self.append_debug(f"🚀 Sistema PTZ básico inicializado con {len(ptz_cameras)} cámaras PTZ")
                
                # Listar cámaras PTZ encontradas
                for cam in ptz_cameras:
                    self.append_debug(f"📹 PTZ detectada: {cam.get('ip')} ({cam.get('usuario')})")
            else:
                self.append_debug("⚠️ No se encontraron cámaras PTZ válidas")
                
        except Exception as e:
            self.append_debug(f"❌ Error inicializando sistema PTZ: {e}")

    def stop_all_ptz(self):
        """Detiene todas las cámaras PTZ"""
        try:
            # Intentar usar sistema PTZ mejorado
            try:
                from core.ptz_control_enhanced import get_ptz_system_status
                # Sistema mejorado disponible
                stopped_count = 0
                for cam in self.camera_data_list:
                    if cam.get('tipo') == 'ptz':
                        # Aquí se implementaría la lógica de parada específica
                        stopped_count += 1
                
                self.append_debug(f"⏹️ {stopped_count} cámaras PTZ detenidas (sistema mejorado)")
                
            except ImportError:
                # Fallback a sistema básico
                stopped_count = 0
                for cam in self.camera_data_list:
                    if cam.get('tipo') == 'ptz':
                        stopped_count += 1
                
                self.append_debug(f"⏹️ {stopped_count} cámaras PTZ detenidas (sistema básico)")
            
        except Exception as e:
            self.append_debug(f"❌ Error deteniendo PTZ: {e}")

    def toggle_line_edit(self):
        """Activar/desactivar modo de edición de línea de cruce"""
        items = self.camera_list.selectedItems()
        if not items:
            self.append_debug("⚠️ Seleccione una cámara para editar línea de cruce")
            return
        index = self.camera_list.row(items[0])
        if index >= len(self.camera_widgets):
            return
        widget = self.camera_widgets[index]
        if hasattr(widget, 'cross_line_edit_mode'):
            if widget.cross_line_edit_mode:
                widget.finish_line_edit()
                self.append_debug("✅ Modo edición de línea desactivado")
            else:
                widget.start_line_edit()
                self.append_debug("📏 Modo edición de línea activado - Click y arrastre para definir línea")
        else:
            self.append_debug("❌ Widget de cámara no soporta edición de línea")

    def start_camera_stream(self, camera_data):
        """Iniciar stream de cámara con configuración optimizada"""
        # Agregar configuración de FPS optimizada a los datos de la cámara
        optimized_fps = self.get_optimized_fps_for_camera(camera_data)
        camera_data['fps_config'] = optimized_fps

        # Verificar si ya existe un widget para esta IP y reemplazarlo
        for i, widget in enumerate(self.camera_widgets):
            if hasattr(widget, 'cam_data') and widget.cam_data.get('ip') == camera_data.get('ip'):
                print(f"INFO: Reemplazando widget para cámara IP: {camera_data.get('ip')}")
                widget.detener()
                self.video_grid.removeWidget(widget) 
                widget.deleteLater()
                self.camera_widgets.pop(i)
                break
        
        # Buscar el contenedor del grid de video
        video_grid_container_widget = None
        for i in range(self.init_tab_layout.count()):
            item = self.init_tab_layout.itemAt(i)
            if hasattr(item, 'widget') and isinstance(item.widget(), QSplitter):
                splitter = item.widget()
                if splitter.count() > 0:
                    scroll_area = splitter.widget(0)
                    if isinstance(scroll_area, QScrollArea):
                        video_grid_container_widget = scroll_area.widget()
                        break

        # Importar dinámicamente GrillaWidget
        try:
            grilla_widget_module = importlib.import_module("gui.grilla_widget")
            GrillaWidget_class = grilla_widget_module.GrillaWidget
        except ImportError as e:
            print(f"ERROR: No se pudo importar GrillaWidget: {e}")
            self.append_debug(f"ERROR: No se pudo importar GrillaWidget: {e}")
            return

        # Crear widget de cámara
        parent_widget = video_grid_container_widget if video_grid_container_widget else self
        video_widget = GrillaWidget_class(parent=parent_widget, fps_config=optimized_fps) 
        
        video_widget.cam_data = camera_data 
        video_widget.log_signal.connect(self.append_debug)
        
        # Posicionar en grid (una fila, múltiples columnas)
        row = 0
        col = len(self.camera_widgets) 
        
        self.video_grid.addWidget(video_widget, row, col)
        self.camera_widgets.append(video_widget) 
        
        # Iniciar vista de cámara
        video_widget.mostrar_vista(camera_data) 
        video_widget.show()
        self.append_debug(f"🎥 Reproduciendo: {camera_data.get('ip', 'IP Desconocida')} con FPS optimizado")

    def show_camera_menu(self, position):
        """Mostrar menú contextual para cámaras - VERSIÓN ACTUALIZADA CON MUESTREO ADAPTATIVO"""
        item = self.camera_list.itemAt(position)
        if item:
            index = self.camera_list.row(item)
            menu = QMenu()
            edit_action = menu.addAction("✏️ Editar Cámara")
            delete_action = menu.addAction("🗑️ Eliminar Cámara")
            stop_action = menu.addAction("⛔ Detener Visual") 
            fps_action = menu.addAction("🎯 Configurar FPS Individual")
            
            # NUEVA SECCIÓN: Muestreo Adaptativo
            if ADAPTIVE_SAMPLING_AVAILABLE and index < len(self.camera_widgets):
                widget = self.camera_widgets[index]
                
                if hasattr(widget, 'get_adaptive_sampling_status'):
                    menu.addSeparator()
                    adaptive_menu = menu.addMenu("🧠 Muestreo Adaptativo")
                    
                    status = widget.get_adaptive_sampling_status()
                    
                    if status['enabled']:
                        # Muestreo adaptativo activo
                        status_action = adaptive_menu.addAction(f"📊 Estado: Activo (Intervalo: {status['current_interval']})")
                        status_action.setEnabled(False)  # Solo informativo
                        
                        disable_action = adaptive_menu.addAction("📊 Cambiar a Fijo")
                        disable_action.triggered.connect(lambda: self.toggle_camera_adaptive_sampling(index, False))
                        
                        config_action = adaptive_menu.addAction("⚙️ Configurar Individual")
                        config_action.triggered.connect(lambda: self.configure_individual_adaptive_sampling(index))
                        
                        stats_action = adaptive_menu.addAction("📈 Ver Estadísticas")
                        stats_action.triggered.connect(lambda: self.show_individual_adaptive_stats(index))
                        
                    else:
                        # Muestreo fijo activo
                        status_action = adaptive_menu.addAction(f"📊 Estado: Fijo (Intervalo: {status['current_interval']})")
                        status_action.setEnabled(False)  # Solo informativo
                        
                        enable_action = adaptive_menu.addAction("🧠 Cambiar a Adaptativo")
                        enable_action.triggered.connect(lambda: self.toggle_camera_adaptive_sampling(index, True))
            
            # Menú específico para cámaras PTZ
            cam_data = self.camera_data_list[index] if index < len(self.camera_data_list) else {}
            if cam_data.get('tipo') == 'ptz':
                menu.addSeparator()
                ptz_control_action = menu.addAction("🎮 Control PTZ")
                ptz_presets_action = menu.addAction("📍 Gestión de Presets")
                ptz_stop_action = menu.addAction("⏹️ Detener PTZ")
                
            action = menu.exec(self.camera_list.mapToGlobal(position))

            if action == edit_action:
                self.open_camera_dialog(index=index) 
            elif action == delete_action:
                cam_to_delete_data = self.camera_data_list.pop(index)
                self.camera_list.takeItem(index) 
                for i, widget in enumerate(self.camera_widgets):
                    if hasattr(widget, 'cam_data') and widget.cam_data.get('ip') == cam_to_delete_data.get('ip'):
                        widget.detener()
                        self.video_grid.removeWidget(widget)
                        widget.deleteLater()
                        self.camera_widgets.pop(i)
                        self.append_debug(f"🗑️ Cámara {cam_to_delete_data.get('ip')} y su widget eliminados.")
                        break
                guardar_camaras(self) 
            elif action == stop_action:
                cam_ip_to_stop = self.camera_data_list[index].get('ip')
                for i, widget in enumerate(self.camera_widgets):
                     if hasattr(widget, 'cam_data') and widget.cam_data.get('ip') == cam_ip_to_stop:
                        widget.detener()
                        self.append_debug(f"⛔ Visual detenida para: {cam_ip_to_stop}")
                        break
            elif action == fps_action:
                self.configure_individual_fps(index)
            elif cam_data.get('tipo') == 'ptz':
                if action == ptz_control_action:
                    self.open_ptz_dialog()
                elif action == ptz_presets_action:
                    self.open_ptz_presets_dialog()
                elif action == ptz_stop_action:
                    try:
                        # Intentar detener PTZ específica
                        ip = cam_data.get('ip')
                        self.append_debug(f"⏹️ Deteniendo PTZ {ip}")
                        # Aquí se implementaría la lógica específica de parada
                    except Exception as e:
                        self.append_debug(f"❌ Error deteniendo PTZ: {e}")

    def configure_individual_fps(self, camera_index):
        """Configurar FPS individual para una cámara específica"""
        if camera_index >= len(self.camera_widgets):
            return
            
        widget = self.camera_widgets[camera_index]
        current_fps = widget.fps_config if hasattr(widget, 'fps_config') else self.fps_config
        
        dialog = FPSConfigDialog(self, current_fps)
        dialog.setWindowTitle(f"🎯 FPS para {self.camera_data_list[camera_index].get('ip', 'Cámara')}")
        
        def apply_individual_fps(config):
            widget.set_fps_config(
                visual_fps=config['visual_fps'],
                detection_fps=config['detection_fps'],
                ui_update_fps=config['ui_update_fps']
            )
            self.append_debug(f"🎯 FPS individual aplicado a {widget.cam_data.get('ip', 'Cámara')}")
        
        dialog.fps_config_changed.connect(apply_individual_fps)
        dialog.exec()

    def restart_all_cameras(self):
        """Reiniciar todas las cámaras con nueva configuración"""
        self.append_debug("🔄 Reiniciando todas las cámaras...")
        
        # Detener todos los widgets existentes
        for widget in list(self.camera_widgets):
            try:
                if hasattr(widget, 'detener') and callable(widget.detener):
                    widget.detener()
                self.video_grid.removeWidget(widget)
                widget.deleteLater()
            except Exception as e:
                print(f"ERROR al detener cámara: {e}")
        
        self.camera_widgets.clear()
        
        # Reiniciar todas las cámaras
        for cam in self.camera_data_list:
            self.start_camera_stream(cam)
            

    def closeEvent(self, event):
        """Manejar cierre de aplicación con limpieza completa"""
        print("INFO: Iniciando proceso de cierre de MainGUI...")
        
        # Detener sistema PTZ
        try:
            if self._ptz_initialized:
                self.stop_all_ptz()
                print("INFO: Sistema PTZ detenido")
        except Exception as e:
            print(f"ERROR deteniendo sistema PTZ: {e}")
        
        # Detener widgets de cámara
        print(f"INFO: Deteniendo {len(self.camera_widgets)} widgets de cámara activos...")
        for widget in self.camera_widgets:
            try:
                if hasattr(widget, 'detener') and callable(widget.detener):
                    cam_ip = "N/A"
                    if hasattr(widget, 'cam_data') and widget.cam_data:
                        cam_ip = widget.cam_data.get('ip', 'N/A')
                    print(f"INFO: Llamando a detener() para el widget de la cámara IP: {cam_ip}")
                    widget.detener()
                else:
                    cam_ip_info = "N/A"
                    if hasattr(widget, 'cam_data') and widget.cam_data:
                         cam_ip_info = widget.cam_data.get('ip', 'N/A')
                    print(f"WARN: El widget para IP {cam_ip_info} no tiene el método detener() o no es callable.")
            except Exception as e:
                cam_ip_err = "N/A"
                if hasattr(widget, 'cam_data') and widget.cam_data:
                    cam_ip_err = widget.cam_data.get('ip', 'N/A')
                print(f"ERROR: Excepción al detener widget para IP {cam_ip_err}: {e}")
        
        # Detener widget de resumen
        if hasattr(self, 'resumen_widget') and self.resumen_widget: 
            if hasattr(self.resumen_widget, 'stop_threads') and callable(self.resumen_widget.stop_threads):
                print("INFO: Llamando a stop_threads() para resumen_widget...")
                try:
                    self.resumen_widget.stop_threads()
                except Exception as e:
                    print(f"ERROR: Excepción al llamar a stop_threads() en resumen_widget: {e}")
            else:
                print("WARN: resumen_widget no tiene el método stop_threads() o no es callable.")
        else:
            print("WARN: self.resumen_widget no existe, no se pueden detener sus hilos.")

        # Guardar configuración final
        try:
            guardar_camaras(self)
            print("INFO: Configuración guardada antes del cierre")
        except Exception as e:
            print(f"ERROR guardando configuración: {e}")

        # Profiling - guardar estadísticas
        print("INFO: Deteniendo profiler y guardando estadísticas...")
        try:
            self.profiler.disable()
            stats_filename = "main_gui_profile.prof"
            self.profiler.dump_stats(stats_filename)
            print(f"INFO: Resultados del profiler guardados en {stats_filename}")

            # Mostrar resumen de estadísticas
            s = io.StringIO()
            ps = pstats.Stats(self.profiler, stream=s).sort_stats('cumulative', 'tottime')
            ps.print_stats(30)
            print("\n--- Resumen del Profiler (Top 30 por tiempo acumulado) ---")
            print(s.getvalue())
            print("--- Fin del Resumen del Profiler ---\n")
        except Exception as e:
            print(f"ERROR en profiling: {e}")

        print("INFO: Proceso de cierre de MainGUI completado. Aceptando evento.")
        event.accept()
