from app.core.errors.exceptions import DomainException


class ResolucionNoEncontradaException(DomainException):
    """No existe ninguna resolución con el id solicitado."""
    http_status = 404


class PaginaNoEncontradaException(DomainException):
    """La resolución existe pero no tiene una página con ese número de orden."""
    http_status = 404


class EstadoInvalidoException(DomainException):
    """El estado recibido no es uno de los que reconoce el flujo (pendiente_ocr/en_proceso/listo)."""
    http_status = 400


class ResolucionSinPaginasException(DomainException):
    """Se intentó crear una resolución sin adjuntar ninguna imagen de página."""
    http_status = 400


__all__ = [
    "ResolucionNoEncontradaException",
    "PaginaNoEncontradaException",
    "EstadoInvalidoException",
    "ResolucionSinPaginasException",
]
