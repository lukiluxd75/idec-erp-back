from app.core.errors.exceptions import DomainException


class DigitizationException(DomainException):
    """Base exception for the digitization domain."""


class JobNotFoundException(DigitizationException):
    http_status = 404

    def __init__(self, message: str = "No se encontró el trabajo de digitalización solicitado."):
        super().__init__(message)


class InvalidDocumentException(DigitizationException):
    http_status = 422


class JobNotRetryableException(DigitizationException):
    http_status = 409

    def __init__(self, message: str = "Solo se pueden reintentar trabajos que hayan fallado."):
        super().__init__(message)


class WorkerUnavailableException(Exception):
    """The PC did not answer, timed out or rejected the request (e.g. no free VRAM
    because the architect is using it). Retryable on another PC."""


class WorkerOutputException(Exception):
    """The PC answered but the model output could not be used. Retryable."""
