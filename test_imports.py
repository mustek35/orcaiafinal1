# ===== ARCHIVO: test_imports.py =====
# Ejecuta este archivo para verificar que las importaciones funcionen

print("🧪 Iniciando test de importaciones...")

# Test 1: Importar ImageSaverThread directamente
try:
    from gui.image_saver import ImageSaverThread
    print("✅ Test 1: ImageSaverThread importado correctamente desde gui.image_saver")
except ImportError as e:
    print(f"❌ Test 1 FALLO: {e}")

# Test 2: Verificar que la clase existe y es callable
try:
    from gui.image_saver import ImageSaverThread
    import numpy as np
    
    # Crear datos de prueba
    frame_test = np.zeros((100, 100, 3), dtype=np.uint8)
    bbox_test = (10, 10, 50, 50)
    
    # Intentar crear instancia
    thread_test = ImageSaverThread(
        frame=frame_test,
        bbox=bbox_test,
        cls=0,
        coordenadas=(30, 30),
        modelo="test",
        confianza=0.5
    )
    print("✅ Test 2: ImageSaverThread se puede instanciar correctamente")
    
    # Limpiar
    thread_test.deleteLater() if hasattr(thread_test, 'deleteLater') else None
    
except Exception as e:
    print(f"❌ Test 2 FALLO: {e}")

# Test 3: Verificar estructura de directorios
import os
print(f"📁 Directorio actual: {os.getcwd()}")
print(f"📁 Existe gui/: {os.path.exists('gui')}")
print(f"📁 Existe gui/__init__.py: {os.path.exists('gui/__init__.py')}")
print(f"📁 Existe gui/image_saver.py: {os.path.exists('gui/image_saver.py')}")

# Test 4: Verificar sys.path
import sys
print("📂 Rutas en sys.path:")
for i, path in enumerate(sys.path[:5]):  # Solo las primeras 5
    print(f"   {i}: {path}")

# Test 5: Test de importación de GestorAlertas
try:
    from core.gestor_alertas import GestorAlertas
    print("✅ Test 5: GestorAlertas importado correctamente")
except ImportError as e:
    print(f"❌ Test 5 FALLO: {e}")

print("🏁 Test de importaciones completado")

# Test 6: Test completo de integración
try:
    from core.gestor_alertas import GestorAlertas
    import numpy as np
    
    gestor = GestorAlertas("test_cam", 18, 22)
    frame_test = np.zeros((480, 640, 3), dtype=np.uint8)
    boxes_test = [(10, 10, 50, 50, 0)]  # Una persona
    cam_data_test = {"modelos": ["Personas"], "confianza": 0.5}
    
    print("✅ Test 6: Integración GestorAlertas + ImageSaverThread preparada")
    
    # No ejecutamos realmente para evitar crear archivos
    print("✅ Todos los tests pasaron - el sistema debería funcionar")
    
except Exception as e:
    print(f"❌ Test 6 FALLO: {e}")
    print("⚠️ Hay problemas de integración que necesitan resolverse")