from fastapi import APIRouter

from app.domains.geoextraction.presentation.endpoints.captures import router as captures_router
from app.domains.geoextraction.presentation.endpoints.shapefiles import router as shapefiles_router

router = APIRouter()
router.include_router(shapefiles_router)
router.include_router(captures_router)
