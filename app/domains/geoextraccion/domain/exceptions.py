from app.core.errors.exceptions import DomainException


class GeometriaInvalidaException(DomainException):
    """Ningún terreno recibido tiene suficientes puntos para formar un polígono válido."""
    http_status = 400


class ShapefileIlegibleException(DomainException):
    """Un archivo subido no pudo leerse como Shapefile válido, o no se subió ninguno."""
    http_status = 400


class CapturaNoEncontradaException(DomainException):
    """No hay ninguna captura pendiente con ese id para el usuario (no existe, no es
    suya, o ya expiró/fue consumida — el store en memoria no distingue los tres casos,
    ver MemoriaCapturaStore)."""
    http_status = 404


class CapturaInvalidaException(DomainException):
    """La foto subida desde el celular llegó vacía o en un formato no soportado."""
    http_status = 400


__all__ = [
    "GeometriaInvalidaException",
    "ShapefileIlegibleException",
    "CapturaNoEncontradaException",
    "CapturaInvalidaException",
]
