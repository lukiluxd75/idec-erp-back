from fastapi import APIRouter

from app.domains.resolutions.presentation.endpoints.resolutions import router as resoluciones_router

router = APIRouter()
router.include_router(resoluciones_router, prefix="/resolutions")
