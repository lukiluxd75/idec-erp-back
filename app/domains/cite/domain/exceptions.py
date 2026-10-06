"""
Excepciones de dominio específicas del módulo CITE.
Heredan de DomainException → el handler global las convierte a JSONResponse
sin necesidad de try/except en los endpoints.
"""
from app.core.errors.exceptions import DomainException


class ConfiguracionNotFoundException(DomainException):
    """La configuracion_cite solicitada no existe."""
    http_status = 404


class GestionInactivaException(DomainException):
    """La gestión asociada a la configuración no está activa."""
    http_status = 409


class PrefijoDuplicadoException(DomainException):
    """Ya existe un prefijo igual para esa gestión."""
    http_status = 409


class GestionNotFoundException(DomainException):
    """La gestión solicitada no existe."""
    http_status = 404


class AreaNotFoundException(DomainException):
    """El área solicitada no existe."""
    http_status = 404


class CiteGenerationException(DomainException):
    """Error irrecuperable durante la generación transaccional del CITE."""
    http_status = 500
