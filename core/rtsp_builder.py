from urllib.parse import quote

def generar_rtsp(cam_data):
    canal = cam_data.get("canal", "2")
    usuario = cam_data.get("usuario", "admin")
    contrasena = quote(cam_data.get("contrasena", ""))
    ip = cam_data["ip"]
    puerto = 554

    if cam_data.get('tipo') == 'nvr':
        perfil = cam_data.get("resolucion", cam_data.get("perfil", "main")).lower()
        perfil_id = {
            "main": "s0",
            "sub": "s1",
            "low": "s2",
            "more low": "s3"
        }.get(perfil, "s1")
        return f"rtsp://{usuario}:{contrasena}@{ip}:{puerto}/unicast/c{canal}/{perfil_id}/live"
    else:
        perfil = cam_data.get("resolucion", cam_data.get("perfil", "main")).lower()
        video_n = {
            "main": "video1",
            "sub": "video2",
            "low": "video3",
            "more low": "video4"
        }.get(perfil, "video1")
        return f"rtsp://{usuario}:{contrasena}@{ip}:{puerto}/media/{video_n}"
