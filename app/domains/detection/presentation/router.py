from fastapi import APIRouter

from app.domains.detection.presentation.endpoints.detection import router as detection_router

router = APIRouter()
router.include_router(detection_router)
