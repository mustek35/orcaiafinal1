import json
import os
from datetime import datetime

class ConfigValidator:
    """Validador y reparador de archivos de configuración."""
    
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        self.backup_path = f"{config_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def validate_and_repair(self):
        """
        Valida y repara el archivo de configuración.
        
        Returns:
            tuple: (success: bool, message: str, config_data: dict)
        """
        try:
            # Verificar si existe el archivo
            if not os.path.exists(self.config_path):
                return self._create_default_config()
            
            # Cargar configuración actual
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Crear backup antes de cualquier modificación
            self._create_backup(config_data)
            
            # Validar estructura
            config_data = self._validate_structure(config_data)
            
            # Validar cada cámara
            config_data = self._validate_cameras(config_data)
            
            # Guardar configuración reparada
            self._save_config(config_data)
            
            return True, "Configuración validada y reparada exitosamente", config_data
            
        except json.JSONDecodeError as e:
            return False, f"Error de formato JSON: {e}", {}
        except Exception as e:
            return False, f"Error inesperado: {e}", {}
    
    def _create_default_config(self):
        """Crea una configuración por defecto."""
        default_config = {
            "camaras": [],
            "configuracion": {
                "resolucion": "main",
                "umbral": 0.5,
                "guardar_capturas": False,
                "modo_centinela": False
            }
        }
        
        self._save_config(default_config)
        return True, "Archivo de configuración creado con valores por defecto", default_config
    
    def _create_backup(self, config_data):
        """Crea un backup de la configuración actual."""
        try:
            with open(self.backup_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            print(f"✅ Backup creado: {self.backup_path}")
        except Exception as e:
            print(f"⚠️ No se pudo crear backup: {e}")
    
    def _validate_structure(self, config_data):
        """Valida la estructura principal del archivo de configuración."""
        if not isinstance(config_data, dict):
            config_data = {}
        
        # Asegurar que existan las claves principales
        if "camaras" not in config_data:
            config_data["camaras"] = []
            print("⚠️ Añadida clave 'camaras' faltante")
        
        if "configuracion" not in config_data:
            config_data["configuracion"] = {
                "resolucion": "main",
                "umbral": 0.5,
                "guardar_capturas": False,
                "modo_centinela": False
            }
            print("⚠️ Añadida configuración global faltante")
        
        # Validar que camaras sea una lista
        if not isinstance(config_data["camaras"], list):
            config_data["camaras"] = []
            print("⚠️ Corregido: 'camaras' debe ser una lista")
        
        return config_data
    
    def _validate_cameras(self, config_data):
        """Valida cada configuración de cámara."""
        valid_cameras = []

        # Mapa de IP -> tipo para validar referencias a camaras PTZ
        ip_tipo_map = {}
        for cam in config_data.get("camaras", []):
            if isinstance(cam, dict) and cam.get("ip"):
                ip_tipo_map[cam.get("ip")] = cam.get("tipo")

        for i, cam in enumerate(config_data["camaras"]):
            if not isinstance(cam, dict):
                print(f"⚠️ Cámara {i} no es un diccionario válido, omitiendo")
                continue
            
            # Validar campos obligatorios
            if not cam.get("ip"):
                print(f"⚠️ Cámara {i} sin IP, omitiendo")
                continue
            
            # Validar y reparar celdas descartadas
            cam = self._validate_discarded_cells(cam, i)
            cam = self._validate_cell_presets(cam, i)
            cam = self._validate_cell_ptz_map(cam, i, ip_tipo_map)
            
            # Asegurar campos por defecto
            cam.setdefault("usuario", "admin")
            cam.setdefault("contrasena", "")
            cam.setdefault("tipo", "fija")
            cam.setdefault("confianza", 0.5)
            cam.setdefault("intervalo", 80)
            cam.setdefault("imgsz", 640)
            cam.setdefault("device", "cpu")
            cam.setdefault("resolucion", "main")
            cam.setdefault("umbral", 0.5)
            cam.setdefault("guardar_capturas", False)
            cam.setdefault("modo_centinela", False)
            cam.setdefault("lost_ttl", 5)
            cam.setdefault("modelos", ["Personas"])
            cam.setdefault("cell_presets", {})
            cam.setdefault("cell_ptz_map", {})
            
            # Validar valores numéricos
            cam["confianza"] = max(0.0, min(1.0, float(cam.get("confianza", 0.5))))
            cam["umbral"] = max(0.0, min(1.0, float(cam.get("umbral", 0.5))))
            cam["intervalo"] = max(1, int(cam.get("intervalo", 80)))
            cam["imgsz"] = int(cam.get("imgsz", 640))
            cam["lost_ttl"] = max(1, int(cam.get("lost_ttl", 5)))
            
            # Validar modelos
            if not isinstance(cam.get("modelos"), list):
                cam["modelos"] = [cam.get("modelo", "Personas")]
            
            valid_cameras.append(cam)
            print(f"✅ Cámara {cam['ip']} validada correctamente")
        
        config_data["camaras"] = valid_cameras
        return config_data
    
    def _validate_discarded_cells(self, cam, cam_index):
        """Valida las celdas descartadas de una cámara."""
        discarded_cells = cam.get("discarded_grid_cells", [])
        
        if not isinstance(discarded_cells, list):
            print(f"⚠️ Cámara {cam_index}: discarded_grid_cells no es una lista, corrigiendo")
            cam["discarded_grid_cells"] = []
            return cam
        
        valid_cells = []
        filas, columnas = 18, 22  # Valores por defecto de la grilla
        
        for cell in discarded_cells:
            if not isinstance(cell, list) or len(cell) != 2:
                print(f"⚠️ Cámara {cam_index}: celda con formato inválido {cell}, omitiendo")
                continue
            
            try:
                row, col = int(cell[0]), int(cell[1])
                if 0 <= row < filas and 0 <= col < columnas:
                    valid_cells.append([row, col])
                else:
                    print(f"⚠️ Cámara {cam_index}: celda fuera de límites ({row}, {col}), omitiendo")
            except (ValueError, TypeError):
                print(f"⚠️ Cámara {cam_index}: coordenadas inválidas {cell}, omitiendo")
        
        # Eliminar duplicados manteniendo el orden
        seen = set()
        unique_cells = []
        for cell in valid_cells:
            cell_tuple = tuple(cell)
            if cell_tuple not in seen:
                seen.add(cell_tuple)
                unique_cells.append(cell)
        
        cam["discarded_grid_cells"] = unique_cells
        
        if len(unique_cells) != len(discarded_cells):
            print(f"🔧 Cámara {cam_index}: {len(discarded_cells)} → {len(unique_cells)} celdas descartadas después de validación")
        
        return cam

    def _validate_cell_presets(self, cam, cam_index):
        presets = cam.get("cell_presets", {})

        if not isinstance(presets, dict):
            print(f"⚠️ Cámara {cam_index}: cell_presets no es un dict, corrigiendo")
            cam["cell_presets"] = {}
            return cam

        valid = {}
        for key, val in presets.items():
            try:
                row, col = map(int, str(key).split('_'))
                valid[f"{row}_{col}"] = str(val)
            except Exception:
                print(f"⚠️ Cámara {cam_index}: preset inválido {key}:{val}, omitiendo")

        cam["cell_presets"] = valid
        return cam

    def _validate_cell_ptz_map(self, cam, cam_index, ip_tipo_map):
        mapping = cam.get("cell_ptz_map", {})

        if not isinstance(mapping, dict):
            print(f"⚠️ Cámara {cam_index}: cell_ptz_map no es un dict, corrigiendo")
            cam["cell_ptz_map"] = {}
            return cam

        valid = {}
        for key, val in mapping.items():
            try:
                row, col = map(int, str(key).split('_'))
                if isinstance(val, dict):
                    ip = str(val.get("ip", ""))
                    preset = str(val.get("preset", ""))
                    tipo = ip_tipo_map.get(ip)
                    if tipo != "ptz":
                        msg = f"⚠️ Cámara {cam_index}: IP PTZ desconocida {ip}, omitiendo mapeo {key}"
                        if ip in ip_tipo_map:
                            msg = f"⚠️ Cámara {cam_index}: cámara {ip} no es PTZ, omitiendo mapeo {key}"
                        print(msg)
                        continue
                    valid[f"{row}_{col}"] = {"ip": ip, "preset": preset}
            except Exception:
                print(f"⚠️ Cámara {cam_index}: mapeo PTZ inválido {key}:{val}, omitiendo")

        cam["cell_ptz_map"] = valid
        return cam
    
    def _save_config(self, config_data):
        """Guarda la configuración validada."""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
    
    def get_camera_discarded_cells(self, camera_ip):
        """
        Obtiene las celdas descartadas para una cámara específica.
        
        Args:
            camera_ip (str): IP de la cámara
            
        Returns:
            set: Conjunto de tuplas (row, col) de celdas descartadas
        """
        try:
            if not os.path.exists(self.config_path):
                return set()
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            for cam in config_data.get("camaras", []):
                if cam.get("ip") == camera_ip:
                    discarded_list = cam.get("discarded_grid_cells", [])
                    return {(row, col) for row, col in discarded_list if isinstance(row, int) and isinstance(col, int)}
            
            return set()
            
        except Exception as e:
            print(f"❌ Error al obtener celdas descartadas para {camera_ip}: {e}")
            return set()
    
    def update_camera_discarded_cells(self, camera_ip, discarded_cells):
        """
        Actualiza las celdas descartadas para una cámara específica.
        
        Args:
            camera_ip (str): IP de la cámara
            discarded_cells (set): Conjunto de tuplas (row, col) de celdas descartadas
            
        Returns:
            bool: True si se actualizó correctamente
        """
        try:
            # Validar configuración primero
            success, message, config_data = self.validate_and_repair()
            if not success:
                print(f"❌ Error validando configuración: {message}")
                return False
            
            # Convertir set a lista para JSON
            discarded_list = sorted([[row, col] for row, col in discarded_cells])
            
            # Buscar la cámara y actualizar
            camera_found = False
            for cam in config_data["camaras"]:
                if cam.get("ip") == camera_ip:
                    cam["discarded_grid_cells"] = discarded_list
                    camera_found = True
                    break
            
            if not camera_found:
                print(f"⚠️ Cámara {camera_ip} no encontrada en configuración")
                return False
            
            # Guardar configuración actualizada
            self._save_config(config_data)
            print(f"✅ Celdas descartadas actualizadas para {camera_ip}: {len(discarded_list)} celdas")
            return True
            
        except Exception as e:
            print(f"❌ Error al actualizar celdas descartadas para {camera_ip}: {e}")
            return False
    
    def list_camera_ips(self):
        """
        Lista todas las IPs de cámaras en la configuración.
        
        Returns:
            list: Lista de IPs de cámaras
        """
        try:
            if not os.path.exists(self.config_path):
                return []
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            return [cam.get("ip") for cam in config_data.get("camaras", []) if cam.get("ip")]
            
        except Exception as e:
            print(f"❌ Error al listar IPs de cámaras: {e}")
            return []
    
    def validate_camera_config(self, camera_ip):
        """
        Valida la configuración de una cámara específica.
        
        Args:
            camera_ip (str): IP de la cámara
            
        Returns:
            tuple: (is_valid: bool, issues: list, config: dict)
        """
        try:
            if not os.path.exists(self.config_path):
                return False, ["Archivo de configuración no existe"], {}
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            for cam in config_data.get("camaras", []):
                if cam.get("ip") == camera_ip:
                    issues = []
                    
                    # Validar campos requeridos
                    required_fields = ["ip", "usuario", "contrasena", "tipo"]
                    for field in required_fields:
                        if not cam.get(field):
                            issues.append(f"Campo requerido faltante: {field}")
                    
                    # Validar celdas descartadas
                    discarded = cam.get("discarded_grid_cells", [])
                    if not isinstance(discarded, list):
                        issues.append("discarded_grid_cells debe ser una lista")
                    else:
                        for i, cell in enumerate(discarded):
                            if not isinstance(cell, list) or len(cell) != 2:
                                issues.append(f"Celda descartada {i} tiene formato inválido: {cell}")
                            else:
                                try:
                                    row, col = int(cell[0]), int(cell[1])
                                    if not (0 <= row < 18 and 0 <= col < 22):
                                        issues.append(f"Celda descartada {i} fuera de límites: ({row}, {col})")
                                except (ValueError, TypeError):
                                    issues.append(f"Celda descartada {i} con coordenadas inválidas: {cell}")
                    
                    # Validar valores numéricos
                    numeric_fields = {
                        "confianza": (0.0, 1.0),
                        "umbral": (0.0, 1.0),
                        "intervalo": (1, 1000),
                        "imgsz": (64, 2048),
                        "lost_ttl": (1, 100)
                    }
                    
                    for field, (min_val, max_val) in numeric_fields.items():
                        value = cam.get(field)
                        if value is not None:
                            try:
                                num_value = float(value)
                                if not (min_val <= num_value <= max_val):
                                    issues.append(f"{field} fuera de rango [{min_val}, {max_val}]: {num_value}")
                            except (ValueError, TypeError):
                                issues.append(f"{field} no es un número válido: {value}")
                    
                    return len(issues) == 0, issues, cam
            
            return False, [f"Cámara {camera_ip} no encontrada"], {}
            
        except Exception as e:
            return False, [f"Error al validar configuración: {e}"], {}


def validate_config_file(config_path="config.json"):
    """
    Función de utilidad para validar un archivo de configuración.
    
    Args:
        config_path (str): Ruta al archivo de configuración
        
    Returns:
        bool: True si la validación fue exitosa
    """
    validator = ConfigValidator(config_path)
    success, message, _ = validator.validate_and_repair()
    
    if success:
        print(f"✅ {message}")
    else:
        print(f"❌ {message}")
    
    return success


def repair_discarded_cells(config_path="config.json"):
    """
    Función de utilidad para reparar específicamente las celdas descartadas.
    
    Args:
        config_path (str): Ruta al archivo de configuración
        
    Returns:
        int: Número de cámaras reparadas
    """
    validator = ConfigValidator(config_path)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        repaired_count = 0
        
        for i, cam in enumerate(config_data.get("camaras", [])):
            original_cells = cam.get("discarded_grid_cells", [])
            cam = validator._validate_discarded_cells(cam, i)
            new_cells = cam.get("discarded_grid_cells", [])
            
            if len(original_cells) != len(new_cells):
                repaired_count += 1
                print(f"🔧 Cámara {cam.get('ip', i)}: {len(original_cells)} → {len(new_cells)} celdas")
        
        # Guardar configuración reparada
        validator._save_config(config_data)
        
        print(f"✅ Reparación completada: {repaired_count} cámaras modificadas")
        return repaired_count
        
    except Exception as e:
        print(f"❌ Error durante la reparación: {e}")
        return 0


if __name__ == "__main__":
    # Ejemplo de uso del validador
    print("🔍 Iniciando validación de configuración...")
    
    # Validar archivo completo
    if validate_config_file():
        print("\n📋 Listando cámaras configuradas:")
        validator = ConfigValidator()
        camera_ips = validator.list_camera_ips()
        
        for ip in camera_ips:
            print(f"📷 {ip}")
            
            # Validar cada cámara individualmente
            is_valid, issues, config = validator.validate_camera_config(ip)
            if is_valid:
                discarded_count = len(config.get("discarded_grid_cells", []))
                print(f"   ✅ Configuración válida ({discarded_count} celdas descartadas)")
            else:
                print(f"   ❌ Problemas encontrados:")
                for issue in issues:
                    print(f"      - {issue}")
        
        print(f"\n🏁 Validación completada para {len(camera_ips)} cámaras")
    else:
        print("\n🔧 Intentando reparar configuración...")
        repair_discarded_cells()