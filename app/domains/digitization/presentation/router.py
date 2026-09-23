import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.core.database.connection import engine
from app.domains.digitization.infrastructure.models import create_schema_and_tables
from app.domains.digitization.presentation.deps import build_dispatcher
from app.domains.digitization.presentation.endpoints.jobs import router as jobs_router
from app.domains.digitization.presentation.endpoints.workers import router as workers_router

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # FastAPI merges a router's lifespan into the app's, so the domain starts its
    # own schema and dispatcher without touching main.py or core.
    if engine.dialect.name != "postgresql":
        logger.warning("digitization: requires PostgreSQL; schema and dispatcher skipped")
        yield
        return
    try:
        create_schema_and_tables(engine)
    except Exception as exc:
        logger.warning("digitization: could not create schema/tables: %s", exc)
    dispatcher = build_dispatcher()
    dispatcher.start()
    try:
        yield
    finally:
        dispatcher.stop()


router = APIRouter(lifespan=lifespan)
router.include_router(jobs_router)
router.include_router(workers_router)
