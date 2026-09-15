from functools import lru_cache

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database.connection import get_db
from app.domains.geoextraccion.application.use_cases import (
    GenerarShapefileUseCase,
    FusionarShapefilesUseCase,
    CrearCapturaUseCase,
    ListarCapturasPendientesUseCase,
    ObtenerImagenCapturaUseCase,
    DescartarCapturaUseCase,
)
from app.domains.geoextraccion.domain.ports.captura_store_port import CapturaStorePort
from app.domains.geoextraccion.domain.ports.shapefile_port import ShapefilePort
from app.domains.geoextraccion.infrastructure.geopandas_shapefile_adapter import GeoPandasShapefileAdapter
from app.domains.geoextraccion.infrastructure.sql_captura_store import SqlCapturaStore
from app.domains.geoextraccion.infrastructure.ws_connection_manager import CapturasConnectionManager


@lru_cache()
def get_shapefile_service() -> ShapefilePort:
    """Instancia única (singleton cacheado) del adaptador GeoPandas."""
    return GeoPandasShapefileAdapter()


def get_generar_shapefile_use_case(
    shapefile_service: ShapefilePort = Depends(get_shapefile_service),
) -> GenerarShapefileUseCase:
    return GenerarShapefileUseCase(shapefile_service=shapefile_service)


def get_fusionar_shapefiles_use_case(
    shapefile_service: ShapefilePort = Depends(get_shapefile_service),
) -> FusionarShapefilesUseCase:
    return FusionarShapefilesUseCase(shapefile_service=shapefile_service)


def get_captura_store(db: Session = Depends(get_db)) -> CapturaStorePort:
    """Sesión de DB por request (no singleton: a diferencia del store en memoria que
    reemplazó, este vive en Postgres — compartido entre los N workers del backend
    en vez de aislado por proceso, ver SqlCapturaStore)."""
    return SqlCapturaStore(db=db)


@lru_cache()
def get_connection_manager() -> CapturasConnectionManager:
    """Instancia única (singleton cacheado): todos los requests/sockets del mismo
    proceso uvicorn tienen que compartir el mismo registro de conexiones."""
    return CapturasConnectionManager()


def get_crear_captura_use_case(
    store: CapturaStorePort = Depends(get_captura_store),
) -> CrearCapturaUseCase:
    return CrearCapturaUseCase(store=store)


def get_listar_capturas_pendientes_use_case(
    store: CapturaStorePort = Depends(get_captura_store),
) -> ListarCapturasPendientesUseCase:
    return ListarCapturasPendientesUseCase(store=store)


def get_obtener_imagen_captura_use_case(
    store: CapturaStorePort = Depends(get_captura_store),
) -> ObtenerImagenCapturaUseCase:
    return ObtenerImagenCapturaUseCase(store=store)


def get_descartar_captura_use_case(
    store: CapturaStorePort = Depends(get_captura_store),
) -> DescartarCapturaUseCase:
    return DescartarCapturaUseCase(store=store)
