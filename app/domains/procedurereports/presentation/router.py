from fastapi import APIRouter

from .endpoints.reports import router as reports_router

router = APIRouter()
router.include_router(reports_router)
