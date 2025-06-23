import ctypes
import threading
from ctypes import c_int, c_uint, c_char_p, c_void_p, POINTER, Structure
from datetime import datetime
from PyQt6.QtCore import QTimer
from core import detector
from collections import deque

SDK_PATH = "./UNV_LAPI/NetDEVSDK.dll"
sdk = ctypes.CDLL(SDK_PATH)

class NETDEV_EVENT_INFO_S(Structure):
    _fields_ = [
        ("dwChannelID", c_int),
        ("dwEventType", c_uint)
    ]

NETDEV_AlarmMessCallBack_V30 = ctypes.CFUNCTYPE(
    None, c_void_p, POINTER(NETDEV_EVENT_INFO_S), c_void_p, c_int, c_void_p
)

gui_ref = None  # GUI se puede inyectar desde app.py
event_queue = deque()
procesando = False

def procesar_evento():
    global procesando
    if not event_queue or procesando:
        return

    evento = event_queue.popleft()
    rtsp, grilla, log_view = evento

    def ejecutar():
        global procesando
        procesando = True
        print("🧠 Ejecutando análisis con IA...")
        try:
            detector.analizar_evento_y_pintar(grilla, rtsp, log_view)
            print("✅ Análisis IA finalizado.")
        except Exception as e:
            print(f"❌ Error en análisis IA: {e}")
            if log_view:
                QTimer.singleShot(0, lambda: log_view.append(f"❌ Error en análisis IA: {e}"))
        finally:
            procesando = False
            if event_queue:
                QTimer.singleShot(100, procesar_evento)

    threading.Thread(target=ejecutar).start()

@NETDEV_AlarmMessCallBack_V30
def alarm_callback(lpUserID, pstEventInfo, lpBuf, dwBufLen, pUserData):
    try:
        event = pstEventInfo.contents
        canal = event.dwChannelID
        tipo_hex = f"0x{event.dwEventType:08X}"
        timestamp = datetime.now().strftime("%H:%M:%S")

        print(f"📡 Evento V30 recibido desde el SDK - {timestamp}")
        print(f"↪ Canal: {canal}, Tipo: {tipo_hex}")
        print(f"📝 Evento encolado. Total en cola: {len(event_queue)+1}")

        if gui_ref and hasattr(gui_ref, "get_cam1_rtsp") and hasattr(gui_ref, "grilla_cam1") and hasattr(gui_ref, "log_view"):
            rtsp = gui_ref.get_cam1_rtsp()
            grilla = gui_ref.grilla_cam1
            log_view = gui_ref.log_view
            event_queue.append((rtsp, grilla, log_view))
            QTimer.singleShot(100, procesar_evento)

        if gui_ref and hasattr(gui_ref, "log_evento_sdk"):
            QTimer.singleShot(0, lambda: gui_ref.log_evento_sdk(canal, event.dwEventType))

    except Exception as e:
        error_msg = f"⚠️ Error en callback SDK: {e}"
        print(error_msg)
        if gui_ref and hasattr(gui_ref, "log_view"):
            QTimer.singleShot(0, lambda: gui_ref.log_view.append(error_msg))

def iniciar_sdk(ip, puerto, usuario, contrasena):
    print("🔧 Inicializando SDK...")
    sdk.NETDEV_Init()

    sdk.NETDEV_Login.argtypes = [c_char_p, c_int, c_char_p, c_char_p, POINTER(c_int)]
    sdk.NETDEV_Login.restype = c_void_p
    err_code = c_int(0)

    user_handle = sdk.NETDEV_Login(
        ip.encode(), int(puerto),
        usuario.encode(), contrasena.encode(),
        ctypes.byref(err_code)
    )

    if not user_handle:
        print("❌ Error de login al SDK.")
        return

    print("✅ Login exitoso. Registrando callback...")

    sdk.NETDEV_SetAlarmCallBack_V30.argtypes = [c_void_p, NETDEV_AlarmMessCallBack_V30, c_void_p]
    sdk.NETDEV_SetAlarmCallBack_V30.restype = c_int

    result = sdk.NETDEV_SetAlarmCallBack_V30(user_handle, alarm_callback, None)
    if result != 1:
        print("⚠️ Error al registrar el callback.")
    else:
        print("📶 Callback registrado correctamente")

def lanzar_listener_en_hilo(ip, puerto, usuario, contrasena):
    hilo = threading.Thread(target=iniciar_sdk, args=(ip, puerto, usuario, contrasena))
    hilo.start()