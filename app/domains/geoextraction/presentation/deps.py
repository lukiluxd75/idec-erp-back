from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.domains.geoextraction.application.use_cases import (
    GenerateShapefileUseCase,
    MergeShapefilesUseCase,
    CreateCaptureUseCase,
    ListPendingCapturesUseCase,
    GetCaptureImageUseCase,
    DiscardCaptureUseCase,
)
from app.domains.geoextraction.domain.ports.capture_store_port import CaptureStorePort
from app.domains.geoextraction.domain.ports.shapefile_port import ShapefilePort
from app.domains.geoextraction.infrastructure.geopandas_shapefile_adapter import GeoPandasShapefileAdapter
from app.domains.geoextraction.infrastructure.sql_capture_store import SqlCaptureStore
from app.domains.geoextraction.infrastructure.ws_connection_manager import CapturesConnectionManager


@lru_cache()
def get_shapefile_service() -> ShapefilePort:
    """Cached singleton instance of the GeoPandas adapter."""
    return GeoPandasShapefileAdapter()


def get_generate_shapefile_use_case(
    shapefile_service: ShapefilePort = Depends(get_shapefile_service),
) -> GenerateShapefileUseCase:
    return GenerateShapefileUseCase(shapefile_service=shapefile_service)


def get_merge_shapefiles_use_case(
    shapefile_service: ShapefilePort = Depends(get_shapefile_service),
) -> MergeShapefilesUseCase:
    return MergeShapefilesUseCase(shapefile_service=shapefile_service)


def get_capture_store(db: Session = Depends(get_db)) -> CaptureStorePort:
    """DB session per request (not a singleton: unlike the in-memory store it
    replaced, this lives in Postgres — shared across the N backend workers
    instead of isolated per process; see SqlCaptureStore)."""
    return SqlCaptureStore(db=db)


@lru_cache()
def get_connection_manager() -> CapturesConnectionManager:
    """Cached singleton: all requests/sockets of the same uvicorn process must
    share the same connection registry."""
    return CapturesConnectionManager()


def get_create_capture_use_case(
    store: CaptureStorePort = Depends(get_capture_store),
) -> CreateCaptureUseCase:
    return CreateCaptureUseCase(store=store)


def get_list_pending_captures_use_case(
    store: CaptureStorePort = Depends(get_capture_store),
) -> ListPendingCapturesUseCase:
    return ListPendingCapturesUseCase(store=store)


def get_capture_image_use_case(
    store: CaptureStorePort = Depends(get_capture_store),
) -> GetCaptureImageUseCase:
    return GetCaptureImageUseCase(store=store)


def get_discard_capture_use_case(
    store: CaptureStorePort = Depends(get_capture_store),
) -> DiscardCaptureUseCase:
    return DiscardCaptureUseCase(store=store)
