from fastapi import APIRouter

from app.domains.detection.presentation.endpoints.affected_parcels import (
    router as affected_parcels_router,
)
from app.domains.detection.presentation.endpoints.campaigns import router as campaigns_router
from app.domains.detection.presentation.endpoints.detection import router as detection_router
from app.domains.detection.presentation.endpoints.reports import router as reports_router
from app.domains.detection.presentation.endpoints.sectors import router as sectors_router

router = APIRouter()
router.include_router(detection_router)
router.include_router(campaigns_router)
router.include_router(affected_parcels_router)
router.include_router(sectors_router)
router.include_router(reports_router)
