from app.core.errors.exceptions import DomainException


class GeometriaInvalidaException(DomainException):
    """Ningún terreno recibido tiene suficientes puntos para formar un polígono válido."""
    http_status = 400


class ShapefileIlegibleException(DomainException):
    """Un archivo subido no pudo leerse como Shapefile válido, o no se subió ninguno."""
    http_status = 400


__all__ = ["GeometriaInvalidaException", "ShapefileIlegibleException"]
