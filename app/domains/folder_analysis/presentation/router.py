import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.core.database.connection import engine
from app.domains.folder_analysis.infrastructure.models import create_schema_and_tables
from app.domains.folder_analysis.presentation.endpoints.cadastral import router as cadastral_router
from app.domains.folder_analysis.presentation.endpoints.captures import router as captures_router
from app.domains.folder_analysis.presentation.endpoints.catalog import router as catalog_router
from app.domains.folder_analysis.presentation.endpoints.documents import router as documents_router
from app.domains.folder_analysis.presentation.endpoints.registered_folders import (
    router as registered_folders_router,
)

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Merged into the app's lifespan by FastAPI: the domain creates its own
    # schema without touching main.py or core.
    if engine.dialect.name == "postgresql":
        try:
            create_schema_and_tables(engine)
        except Exception as exc:
            logger.warning("folder_analysis: could not create schema/tables: %s", exc)
    else:
        logger.warning("folder_analysis: requires PostgreSQL; schema not created")
    yield


router = APIRouter(lifespan=lifespan)
router.include_router(catalog_router)
router.include_router(cadastral_router)
router.include_router(captures_router)
router.include_router(documents_router)
router.include_router(registered_folders_router)
