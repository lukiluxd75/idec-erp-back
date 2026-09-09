from app.domains.geoextraccion.domain.exceptions import ShapefileIlegibleException
from app.domains.geoextraccion.domain.ports.shapefile_port import ShapefilePort


class FusionarShapefilesUseCase:
    """Caso de uso: unir varios Shapefiles (ZIP) subidos en una sola capa."""

    def __init__(self, shapefile_service: ShapefilePort):
        self._shapefile_service = shapefile_service

    def execute(self, archivos: list[bytes]) -> bytes:
        if not archivos:
            raise ShapefileIlegibleException("No se subió ningún archivo para fusionar.")
        return self._shapefile_service.fusionar(archivos)
