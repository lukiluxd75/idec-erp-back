"""Entidades del dominio Geoextracción. Sin FastAPI, sin SQLAlchemy, sin geopandas."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Punto:
    """Coordenada plana (proyectada), no geográfica lat/lon."""
    x: float
    y: float


@dataclass(frozen=True)
class Terreno:
    """Un polígono digitalizado (predio) con sus atributos catastrales asociados."""
    puntos: list[Punto]
    atributos: dict[str, str] = field(default_factory=dict)
