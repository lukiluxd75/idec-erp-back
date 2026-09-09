from app.domains.geoextraccion.domain.entities.terreno import Terreno
from app.domains.geoextraccion.domain.exceptions import GeometriaInvalidaException
from app.domains.geoextraccion.domain.ports.shapefile_port import ShapefilePort

MINIMO_PUNTOS_POLIGONO = 3


class GenerarShapefileUseCase:
    """Caso de uso: generar un Shapefile (ZIP) a partir de uno o más terrenos digitalizados."""

    def __init__(self, shapefile_service: ShapefilePort):
        self._shapefile_service = shapefile_service

    def execute(self, terrenos: list[Terreno]) -> bytes:
        terrenos_validos = [t for t in terrenos if len(t.puntos) >= MINIMO_PUNTOS_POLIGONO]
        if not terrenos_validos:
            raise GeometriaInvalidaException(
                f"Cada terreno necesita al menos {MINIMO_PUNTOS_POLIGONO} puntos para formar un polígono."
            )
        return self._shapefile_service.generar(terrenos_validos)
