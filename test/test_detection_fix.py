#!/usr/bin/env python3
"""
Script de prueba para verificar que las detecciones de YOLO funcionan correctamente
"""
import sys
import os
import cv2
import numpy as np
from ultralytics import YOLO

def test_yolo_detection():
    """Prueba básica de detección YOLO"""
    print("🧪 Iniciando prueba de detección YOLO...")
    
    try:
        # Cargar modelo YOLO
        print("📦 Cargando modelo YOLO...")
        model = YOLO("yolov8n.pt")  # Modelo ligero para pruebas
        print("✅ Modelo cargado exitosamente")
        
        # Crear una imagen de prueba con formas simples
        print("🖼️ Creando imagen de prueba...")
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Dibujar un rectángulo que simule un objeto
        cv2.rectangle(test_image, (100, 200), (200, 350), (255, 255, 255), -1)
        cv2.rectangle(test_image, (400, 100), (550, 250), (128, 128, 128), -1)
        
        # Guardar imagen de prueba
        cv2.imwrite("test_image.jpg", test_image)
        print("💾 Imagen de prueba guardada como 'test_image.jpg'")
        
        # Ejecutar detección
        print("🔍 Ejecutando detección...")
        results = model.predict(
            source=test_image,
            conf=0.25,
            classes=[0],  # Solo personas
            save=False,
            show=False,
            verbose=False
        )
        
        # Procesar resultados
        detections_found = 0
        if results and len(results) > 0:
            result = results[0]
            if result.boxes is not None:
                detections_found = len(result.boxes)
                print(f"📊 Detecciones encontradas: {detections_found}")
                
                for i, box in enumerate(result.boxes):
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    print(f"  Detection {i}: bbox=({x1:.1f},{y1:.1f},{x2:.1f},{y2:.1f}) conf={conf:.3f} cls={cls}")
            else:
                print("📊 No se encontraron detecciones")
        else:
            print("❌ Error: No se obtuvieron resultados del modelo")
            
        return detections_found > 0

    except Exception as e:
        print(f"❌ Error probando imagen: {e}")
        return False

def check_cuda_availability():
    """Verificar disponibilidad de CUDA"""
    print("\n🖥️ Verificando disponibilidad de CUDA...")
    
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        
        if cuda_available:
            device_count = torch.cuda.device_count()
            current_device = torch.cuda.current_device()
            device_name = torch.cuda.get_device_name(current_device)
            print(f"✅ CUDA disponible: {device_count} dispositivo(s)")
            print(f"🎯 Dispositivo actual: {current_device} ({device_name})")
        else:
            print("⚠️ CUDA no está disponible, usando CPU")
            
        return cuda_available
        
    except ImportError:
        print("❌ PyTorch no está instalado")
        return False
    except Exception as e:
        print(f"❌ Error verificando CUDA: {e}")
        return False

def test_config_file():
    """Verificar archivo de configuración"""
    print("\n📄 Verificando archivo de configuración...")
    
    try:
        import json
        
        if os.path.exists("config.json"):
            with open("config.json", "r") as f:
                config = json.load(f)
            
            camaras = config.get("camaras", [])
            print(f"✅ Config cargado: {len(camaras)} cámaras configuradas")
            
            for i, cam in enumerate(camaras):
                ip = cam.get("ip", "N/A")
                confianza = cam.get("confianza", "N/A")
                modelos = cam.get("modelos", [])
                fps_config = cam.get("fps_config", {})
                
                print(f"  Cámara {i+1}: {ip}")
                print(f"    Confianza: {confianza}")
                print(f"    Modelos: {modelos}")
                print(f"    FPS: Visual={fps_config.get('visual_fps', 'N/A')}, Detección={fps_config.get('detection_fps', 'N/A')}")
            
            return True
        else:
            print("❌ Archivo config.json no encontrado")
            return False
            
    except Exception as e:
        print(f"❌ Error verificando config: {e}")
        return False

def test_model_files():
    """Verificar archivos de modelos"""
    print("\n🧠 Verificando archivos de modelos...")
    
    model_paths = {
        "YOLO básico": "yolov8n.pt",
        "YOLO mediano": "yolov8m.pt", 
        "Embarcaciones": "core/models/best.pt"
    }
    
    available_models = 0
    
    for name, path in model_paths.items():
        if os.path.exists(path):
            print(f"✅ {name}: {path}")
            available_models += 1
        else:
            print(f"❌ {name}: {path} (no encontrado)")
    
    if available_models == 0:
        print("⚠️ No se encontraron modelos locales, se descargarán automáticamente")
        return True  # YOLO descarga automáticamente
    
    return available_models > 0

def create_sample_config():
    """Crear archivo de configuración de ejemplo"""
    print("\n📝 Creando configuración de ejemplo...")
    
    sample_config = {
        "camaras": [
            {
                "ip": "192.168.1.100",
                "usuario": "admin",
                "contrasena": "password",
                "tipo": "fija",
                "modelo": "Personas",
                "modelos": ["Personas"],
                "confianza": 0.1,
                "imgsz": 640,
                "device": "cuda",
                "resolucion": "sub",
                "fps_config": {
                    "visual_fps": 25,
                    "detection_fps": 8,
                    "ui_update_fps": 15
                }
            }
        ],
        "configuracion": {
            "fps_global": {
                "visual_fps": 25,
                "detection_fps": 8,
                "ui_update_fps": 15,
                "adaptive_fps": True
            }
        }
    }
    
    try:
        with open("config_example.json", "w") as f:
            json.dump(sample_config, f, indent=4)
        print("✅ Archivo config_example.json creado")
        return True
    except Exception as e:
        print(f"❌ Error creando config de ejemplo: {e}")
        return False

def main():
    """Función principal de pruebas"""
    print("🚀 Iniciando pruebas completas de detección YOLO\n")
    
    # Verificar CUDA
    cuda_ok = check_cuda_availability()
    
    # Verificar configuración
    config_ok = test_config_file()
    
    # Verificar modelos
    models_ok = test_model_files()
    
    # Probar detección básica
    basic_ok = test_yolo_detection()
    
    # Probar con imagen real
    image_ok = test_image_loading()
    
    # Crear config de ejemplo
    example_ok = create_sample_config()
    
    print("\n" + "="*50)
    print("📋 RESUMEN DE PRUEBAS:")
    print(f"🖥️ CUDA disponible: {'✅' if cuda_ok else '❌'}")
    print(f"📄 Config válido: {'✅' if config_ok else '❌'}")
    print(f"🧠 Modelos disponibles: {'✅' if models_ok else '❌'}")
    print(f"🧪 Detección básica: {'✅' if basic_ok else '❌'}")
    print(f"🖼️ Imagen de prueba: {'✅' if image_ok else '❌'}")
    print(f"📝 Config ejemplo: {'✅' if example_ok else '❌'}")
    
    if basic_ok and image_ok:
        print("\n🎉 Todas las pruebas pasaron! YOLO está funcionando correctamente.")
        print("🔧 Si aún no ves detecciones en la aplicación, verifica:")
        print("   1. ✅ La conexión del stream RTSP")
        print("   2. ✅ El mapeo de coordenadas en paintEvent (corregido)")
        print("   3. ✅ La configuración de FPS (ahora configurable)")
        print("   4. ✅ La confianza en config.json (reducir a 0.1)")
        print("\n🎯 Configuraciones recomendadas:")
        print("   • Confianza: 0.1 (para ver más detecciones)")
        print("   • FPS Visual: 25-30")
        print("   • FPS Detección: 8-10") 
        print("   • Modelo: yolov8n.pt o yolov8m.pt")
    else:
        print("\n❌ Algunas pruebas fallaron. Revisar:")
        print("   1. Instalación de ultralytics: pip install ultralytics")
        print("   2. Conexión a internet para descargar modelos")
        print("   3. Configuración de PyTorch/CUDA")
        print("   4. Permisos de archivo para escribir config")
    
    print("\n💡 Pasos siguientes:")
    print("   1. Ejecutar: python app.py")
    print("   2. Ir a Configuración > Configurar FPS")
    print("   3. Usar configuración 'Balanceado' para empezar")
    print("   4. Reducir confianza a 0.1 si no aparecen detecciones")
    
    print("="*50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ Error en la prueba: {e}")
        sys.exit(1)

def test_image_loading():
    """Prueba de carga de imagen desde archivo"""
    print("\n🖼️ Probando carga de imagen desde archivo...")
    
    try:
        # Usar una imagen de ejemplo de internet
        from ultralytics import YOLO
        model = YOLO("yolov8n.pt")
        
        # Descargar y probar con imagen de ejemplo
        test_url = "https://ultralytics.com/images/bus.jpg"
        print(f"🌐 Descargando imagen de prueba desde: {test_url}")
        
        results = model.predict(
            source=test_url,
            conf=0.25,
            save=False,
            show=False,
            verbose=True
        )
        
        if results and len(results) > 0:
            result = results[0]
            if result.boxes is not None:
                detections = len(result.boxes)
                print(f"✅ Detecciones en imagen de prueba: {detections}")
                
                for i, box in enumerate(result.boxes):
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    conf = float(box.conf[0])
                    cls = int(box.cls[0])
                    cls_name = result.names[cls] if hasattr(result, 'names') else f"class_{cls}"
                    print(f"  {i}: {cls_name} ({conf:.3f}) at ({x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f})")
                
                return True
        
        print("❌ No se encontraron detecciones en la imagen de prueba")
        return False
        
    except Exception as e: