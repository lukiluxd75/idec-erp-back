from pydantic import BaseModel


class PointRequest(BaseModel):
    x: float
    y: float


class ParcelRequest(BaseModel):
    """Spanish JSON keys kept for frontend compatibility; mapped to Parcel.points/attributes."""
    puntos: list[PointRequest]
    atributos: dict[str, str] = {}


class GenerateShapefileRequest(BaseModel):
    terrenos: list[ParcelRequest]
