from app.core.errors.exceptions import DomainException


class AppraisalNotFoundException(DomainException):
    """No appraisal exists in catastro_operativo with the given form number."""
    http_status = 404


class OperativoUnavailableException(DomainException):
    """Could not reach catastro_operativo (the external Avalúos system's DB)."""
    http_status = 502


__all__ = [
    "AppraisalNotFoundException",
    "OperativoUnavailableException",
]
