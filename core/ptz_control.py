import time
import numpy as np
from onvif import ONVIFCamera

# Movimiento actual
current_pan_speed = 0.0
current_tilt_speed = 0.0
current_zoom_speed = 0.0

# Sensibilidad ajustable
PAN_SENSITIVITY = 0.005
TILT_SENSITIVITY = 0.005
MAX_PT_SPEED = 0.5
DEADZONE_X = 0.03
DEADZONE_Y = 0.03

deteccion_confirmada_streak = 0


class PTZCameraONVIF:
    """Wrapper sencillo para enviar comandos PTZ vía ONVIF."""

    def __init__(self, ip: str, puerto: int, usuario: str, contrasena: str):
        self.cam = ONVIFCamera(ip, int(puerto), usuario, contrasena)
        self.media = self.cam.create_media_service()
        self.ptz = self.cam.create_ptz_service()
        self.profile_token = self.media.GetProfiles()[0].token


    def goto_preset(self, preset_token: str):
        """Mover la cámara a un preset específico."""
        req = self.ptz.create_type('GotoPreset')
        req.ProfileToken = self.profile_token
        req.PresetToken = str(preset_token)
        self.ptz.GotoPreset(req)


    def continuous_move(self, pan_speed: float, tilt_speed: float, zoom_speed: float = 0.0):
        req = self.ptz.create_type('ContinuousMove')
        req.ProfileToken = self.profile_token
        req.Velocity = {
            'PanTilt': {'x': pan_speed, 'y': tilt_speed},
            'Zoom': {'x': zoom_speed}
        }
        self.ptz.ContinuousMove(req)

    def stop(self):
        self.ptz.Stop({'ProfileToken': self.profile_token})


def track_object_continuous(ip, puerto, usuario, contrasena, cx, cy, frame_w, frame_h):
    """Realiza seguimiento continuo utilizando ONVIF."""
    try:
        cam = PTZCameraONVIF(ip, puerto, usuario, contrasena)

        center_x = frame_w / 2
        center_y = frame_h / 2

        dx = cx - center_x
        dy = cy - center_y

        # Aplicar deadzone
        if abs(dx) < frame_w * DEADZONE_X:
            dx = 0
        if abs(dy) < frame_h * DEADZONE_Y:
            dy = 0

        # Convertir a velocidades proporcionales
        pan_speed = float(np.clip(dx * PAN_SENSITIVITY, -MAX_PT_SPEED, MAX_PT_SPEED))
        tilt_speed = float(np.clip(-dy * TILT_SENSITIVITY, -MAX_PT_SPEED, MAX_PT_SPEED))

        global current_pan_speed, current_tilt_speed
        global deteccion_confirmada_streak

        if pan_speed == 0 and tilt_speed == 0:
            deteccion_confirmada_streak = 0
            print("📍 Objetivo centrado. Enviando Stop.")
            try:
                cam.stop()
            except Exception:
                pass
            current_pan_speed = 0.0
            current_tilt_speed = 0.0
            return

        deteccion_confirmada_streak += 1
        if deteccion_confirmada_streak < 3:
            print(f"⏳ Esperando confirmación de embarcación ({deteccion_confirmada_streak}/3)...")
            return

        # Enviar comando ContinuousMove vía ONVIF
        try:
            cam.continuous_move(pan_speed, tilt_speed)
        except Exception:
            pass
        current_pan_speed = pan_speed
        current_tilt_speed = tilt_speed
        print(f"🎯 PTZ seguimiento continuo: pan_speed={pan_speed:.3f}, tilt_speed={tilt_speed:.3f}")

    except Exception as e:
        print(f"❌ Error en track_object_continuous: {e}")