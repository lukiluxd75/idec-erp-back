from fastapi import APIRouter

from app.domains.alignment.presentation.endpoints.alignment_blocks import (
    router as alignment_blocks_router,
)

router = APIRouter()
router.include_router(alignment_blocks_router)
