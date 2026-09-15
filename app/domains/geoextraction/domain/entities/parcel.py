"""Geoextraction domain entities. No FastAPI, SQLAlchemy, or geopandas here."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Point:
    """Planar projected coordinate (not geographic lat/lon)."""

    x: float
    y: float


@dataclass(frozen=True)
class Parcel:
    """Digitized polygon (parcel) with associated cadastral attributes."""

    points: list[Point]
    attributes: dict[str, str] = field(default_factory=dict)
