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

    def __init__(self, message: str = "Solo se pueden reintentar trabajos que hayan fallado o se hayan detenido."):
        super().__init__(message)


class WorkerNotFoundException(DigitizationException):
    http_status = 404

    def __init__(self, message: str = "Esa computadora no está configurada en el sistema."):
        super().__init__(message)


class NoJobRunningException(DigitizationException):
    http_status = 409

    def __init__(self, message: str = "Esa computadora no está digitalizando nada en este momento."):
        super().__init__(message)


class WorkerUnavailableException(Exception):
    """The PC did not answer, timed out or rejected the request (e.g. no free VRAM
    because the architect is using it). Retryable on another PC."""


class WorkerOutputException(Exception):
    """The PC answered but the model output could not be used. Retryable."""


class WorkerTimeoutException(Exception):
    """The PC was still writing its answer when DIGITIZATION_REQUEST_TIMEOUT_SECONDS
    ran out. Not retried on its own: the next attempt would hit the same ceiling."""


class JobStoppedException(Exception):
    """Someone pressed "Detener" on the monitor while this job was running. Not a
    fault: the run is dropped where it was and nothing is retried."""
