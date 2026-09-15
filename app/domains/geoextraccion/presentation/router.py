from fastapi import APIRouter

from app.domains.geoextraccion.presentation.endpoints.capturas import router as capturas_router
from app.domains.geoextraccion.presentation.endpoints.shapefiles import router as shapefiles_router

router = APIRouter()
router.include_router(shapefiles_router)
router.include_router(capturas_router)
