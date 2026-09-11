from fastapi import APIRouter

from app.domains.resoluciones.presentation.endpoints.resoluciones import router as resoluciones_router

router = APIRouter()
router.include_router(resoluciones_router, prefix="/resoluciones")
