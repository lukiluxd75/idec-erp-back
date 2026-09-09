from abc import ABC, abstractmethod

from app.domains.geoextraccion.domain.entities.terreno import Terreno


class ShapefilePort(ABC):
    """
    Puerto que la infraestructura de Geoextracción debe implementar (ver CLAUDE.md §3).
    application/ solo conoce esta interfaz, nunca la librería concreta (GeoPandas/Shapely)
    que la implementa — eso es lo que mantiene extraíble este dominio a futuro.
    """

    @abstractmethod
    def generar(self, terrenos: list[Terreno]) -> bytes:
        """Genera un ZIP con un Shapefile a partir de uno o más terrenos (polígonos)."""

    @abstractmethod
    def fusionar(self, archivos: list[bytes]) -> bytes:
        """Une varios ZIP de Shapefile (bytes crudos) en una sola capa y devuelve el ZIP resultante."""
