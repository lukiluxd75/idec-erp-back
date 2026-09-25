from app.core.errors.exceptions import DomainException


class ResolutionNotFoundException(DomainException):
    """No resolution exists with the requested id."""
    http_status = 404


class PageNotFoundException(DomainException):
    """The resolution exists but has no page with that order index."""
    http_status = 404


class InvalidStatusException(DomainException):
    """The received status is not one recognized by the flow (pendiente_ocr/en_proceso/listo)."""
    http_status = 400


class ResolutionWithoutPagesException(DomainException):
    """Attempted to create a resolution without attaching any page image."""
    http_status = 400


class PlanPageNotFoundException(DomainException):
    """The resolution exists but has no PLAN page with that order index."""
    http_status = 404


class InvalidPlantaException(DomainException):
    """The received 'planta' for a plan page is not one of PLANTAS_RESUMEN."""
    http_status = 400


class NoPlanPagesException(DomainException):
    """Attempted to add plan pages without attaching any image."""
    http_status = 400


class PlanOcrUnavailableException(DomainException):
    """The OCR service could not read a plan page (to detect its planta)."""
    http_status = 503


__all__ = [
    "ResolutionNotFoundException",
    "PageNotFoundException",
    "InvalidStatusException",
    "ResolutionWithoutPagesException",
    "PlanPageNotFoundException",
    "InvalidPlantaException",
    "NoPlanPagesException",
    "PlanOcrUnavailableException",
]
