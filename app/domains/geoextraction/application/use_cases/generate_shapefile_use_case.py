from app.domains.geoextraction.domain.entities.parcel import Parcel
from app.domains.geoextraction.domain.exceptions import InvalidGeometryException
from app.domains.geoextraction.domain.ports.shapefile_port import ShapefilePort

MIN_POLYGON_POINTS = 3


class GenerateShapefileUseCase:
    """Use case: generate a Shapefile (ZIP) from one or more digitized parcels."""

    def __init__(self, shapefile_service: ShapefilePort):
        self._shapefile_service = shapefile_service

    def execute(self, parcels: list[Parcel]) -> bytes:
        valid_parcels = [p for p in parcels if len(p.points) >= MIN_POLYGON_POINTS]
        if not valid_parcels:
            raise InvalidGeometryException(
                f"Cada terreno necesita al menos {MIN_POLYGON_POINTS} puntos para formar un polígono."
            )
        return self._shapefile_service.generate(valid_parcels)
