"""Utilities for creating a corrected PTZ tracker."""
from typing import Dict, Any

from core.multi_object_ptz_system import create_multi_object_tracker


def create_fixed_tracker(camera_data: Dict[str, Any]):
    """Return a MultiObjectPTZTracker with minor compatibility fixes."""
    ip = camera_data.get("ip", "")
    port = int(camera_data.get("puerto", 80))
    user = camera_data.get("usuario", "admin")
    password = camera_data.get("contrasena", "admin")
    config_name = camera_data.get("config", "maritime_standard")

    tracker = create_multi_object_tracker(ip, port, user, password, config_name)

    # Some versions expect an ``initialize`` method. Provide a dummy one if missing.
    if not hasattr(tracker, "initialize"):
        tracker.initialize = lambda: True

    return tracker
