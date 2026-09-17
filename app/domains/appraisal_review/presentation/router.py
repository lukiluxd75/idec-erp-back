from fastapi import APIRouter

from app.domains.appraisal_review.presentation.endpoints.appraisals import router as appraisals_router

router = APIRouter()
router.include_router(appraisals_router)
