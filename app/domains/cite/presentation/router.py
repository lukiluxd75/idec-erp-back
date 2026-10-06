from fastapi import APIRouter

from app.domains.cite.presentation.endpoints import router as cite_endpoints_router

router = APIRouter()
router.include_router(cite_endpoints_router)
