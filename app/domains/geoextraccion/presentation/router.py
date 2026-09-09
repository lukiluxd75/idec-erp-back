from fastapi import APIRouter

from app.domains.geoextraccion.presentation.endpoints.shapefiles import router as shapefiles_router

router = APIRouter()
router.include_router(shapefiles_router)
