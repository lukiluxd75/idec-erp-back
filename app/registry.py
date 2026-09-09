"""
Único lugar que conoce todos los dominios del ERP y los ensambla en la aplicación
(ver CLAUDE.md §3). Para agregar un dominio nuevo: registrar su router acá — no hace
falta tocar ningún otro dominio existente. Si un dominio falla al importar, se omite
con una advertencia en vez de tumbar el arranque de toda la aplicación.
"""
import logging
from fastapi import APIRouter

logger = logging.getLogger("uvicorn.error")

api_router = APIRouter()

try:
    from app.domains.seguridad.presentation.router import router as seguridad_router
    api_router.include_router(seguridad_router)
except Exception as exc:
    logger.warning(f"No se pudo cargar el dominio 'seguridad': {exc}")

try:
    from app.domains.geoextraccion.presentation.router import router as geoextraccion_router
    api_router.include_router(geoextraccion_router, prefix="/geoextraccion")
except Exception as exc:
    logger.warning(f"No se pudo cargar el dominio 'geoextraccion': {exc}")