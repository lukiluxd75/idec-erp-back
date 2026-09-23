from fastapi import APIRouter

from app.domains.folios.presentation.endpoints.folios import router as folios_router

router = APIRouter()
router.include_router(folios_router)
