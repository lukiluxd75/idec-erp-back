"""
Shared "phone connected" presence, readable and writable from any domain.

Lives in core/ rather than in a domain because three domains show the same
badge (geoextraction, resolutions, folder analysis) and a domain may not import
another domain's internals. Replaces the per-process registries that made the
badge flicker under `--workers 4` -- see models.py for the full story.
"""
from app.core.presence.models import DevicePresenceModel
from app.core.presence.store import (
    ACTIVITY_TTL,
    HEARTBEAT_SECONDS,
    SESSION_TTL,
    SOCKET_TTL,
    SqlPresenceStore,
    device_id_for_request,
)

# Channel names. Constants rather than loose strings so a typo cannot make a
# writer and a reader disagree silently (the badge would just never light up).
CHANNEL_GEOEXTRACTION = "geoextraction"
CHANNEL_RESOLUTIONS = "resolutions"
CHANNEL_FOLDER_ANALYSIS = "folder-analysis"
# Canal transversal: "la app movil tiene sesion abierta con el ERP". No pertenece
# a ningun modulo -- lo escribe el login/refresh/logout (dominio security) y lo
# puede leer cualquier pantalla que quiera mostrar "celular conectado".
CHANNEL_SESSION = "session"

__all__ = [
    "DevicePresenceModel",
    "SqlPresenceStore",
    "device_id_for_request",
    "HEARTBEAT_SECONDS",
    "SOCKET_TTL",
    "ACTIVITY_TTL",
    "SESSION_TTL",
    "CHANNEL_GEOEXTRACTION",
    "CHANNEL_RESOLUTIONS",
    "CHANNEL_FOLDER_ANALYSIS",
    "CHANNEL_SESSION",
]
