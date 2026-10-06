import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.core.database.connection import engine
from app.domains.resolutions.infrastructure.plan_page_models import ensure_added_columns
from app.domains.resolutions.presentation.endpoints.resolutions import router as resoluciones_router

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if engine.dialect.name == "postgresql":
        try:
            ensure_added_columns(engine)
        except Exception as exc:
            logger.warning("resolutions: no se pudieron agregar columnas a resolution_plan_pages: %s", exc)
    yield


router = APIRouter(lifespan=lifespan)
router.include_router(resoluciones_router, prefix="/resolutions")
