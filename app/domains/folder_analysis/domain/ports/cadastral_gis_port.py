from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.domains.folder_analysis.domain.services.parcel_geometry import Neighbour, Ring, Street


@dataclass(frozen=True)
class GisParcel:
    """A predio as the cadastre's GIS answers it: its key, its attributes and its
    outline in UTM metres (WGS84 / zone 19 south)."""

    code: str
    ring: Ring
    attributes: Dict[str, Any] = field(default_factory=dict)


class CadastralGisPort(ABC):
    """The municipality's cadastral GIS (the IDE), read-only."""

    @abstractmethod
    def find_parcel(self, gis_code: str) -> Optional[GisParcel]:
        """The predio with this CodCat, or None when the GIS does not have it.
        Raises CadastralGisUnavailableException when the GIS cannot be reached."""

    @abstractmethod
    def parcels_around(self, ring: Ring, distance_m: float) -> List[Neighbour]:
        """The predios within `distance_m` of the outline (the predio itself
        included: the caller tells it apart by code)."""

    @abstractmethod
    def land_use_at(self, point: Tuple[float, float]) -> Dict[str, Any]:
        """The land-use sector that contains the point (uso de suelo, restricción,
        distrito...), or {} when there is none."""

    @abstractmethod
    def block_at(self, point: Tuple[float, float]) -> Dict[str, Any]:
        """The manzana that contains the point, with its surface and perimeter in
        metres, or {} when there is none."""

    @abstractmethod
    def map_image(
        self, layer: str, bbox: Tuple[float, float, float, float], size: int, transparent: bool
    ) -> bytes:
        """One layer of the map, rendered by the GIS as a square PNG."""

    @abstractmethod
    def streets_around(self, ring: Ring, distance_m: float) -> Sequence[Street]:
        """The streets whose axis is within `distance_m` of the outline."""
