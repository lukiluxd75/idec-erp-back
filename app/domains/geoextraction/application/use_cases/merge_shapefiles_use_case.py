from app.domains.geoextraction.domain.exceptions import UnreadableShapefileException
from app.domains.geoextraction.domain.ports.shapefile_port import ShapefilePort


class MergeShapefilesUseCase:
    """Use case: merge several uploaded Shapefile ZIPs into a single layer."""

    def __init__(self, shapefile_service: ShapefilePort):
        self._shapefile_service = shapefile_service

    def execute(self, files: list[bytes]) -> bytes:
        if not files:
            raise UnreadableShapefileException("No se subió ningún archivo para fusionar.")
        return self._shapefile_service.merge(files)
