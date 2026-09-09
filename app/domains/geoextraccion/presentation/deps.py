from functools import lru_cache

from fastapi import Depends

from app.domains.geoextraccion.application.use_cases import (
    GenerarShapefileUseCase,
    FusionarShapefilesUseCase,
)
from app.domains.geoextraccion.domain.ports.shapefile_port import ShapefilePort
from app.domains.geoextraccion.infrastructure.geopandas_shapefile_adapter import GeoPandasShapefileAdapter


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
