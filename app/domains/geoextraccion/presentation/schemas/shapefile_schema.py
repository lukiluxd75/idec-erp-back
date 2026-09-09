from pydantic import BaseModel


class PuntoRequest(BaseModel):
    x: float
    y: float


class TerrenoRequest(BaseModel):
    puntos: list[PuntoRequest]
    atributos: dict[str, str] = {}


class GenerarShapefileRequest(BaseModel):
    terrenos: list[TerrenoRequest]
