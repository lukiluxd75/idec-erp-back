from abc import ABC, abstractmethod

from app.domains.geoextraction.domain.entities.parcel import Parcel


class ShapefilePort(ABC):
    """
    Port that Geoextraction infrastructure must implement (see CLAUDE.md §3).
    application/ only knows this interface, never the concrete library
    (GeoPandas/Shapely) that implements it — that is what keeps this domain
    extractable later.
    """

    @abstractmethod
    def generate(self, parcels: list[Parcel]) -> bytes:
        """Build a ZIP containing a Shapefile from one or more parcels (polygons)."""

    @abstractmethod
    def merge(self, files: list[bytes]) -> bytes:
        """Merge several Shapefile ZIPs (raw bytes) into one layer and return the resulting ZIP."""
