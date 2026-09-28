from app.core.errors.exceptions import DomainException


class FolderAnalysisException(DomainException):
    """Base exception for the folder analysis domain."""


class CaptureNotFoundException(FolderAnalysisException):
    http_status = 404

    def __init__(self, message: str = "No se encontró la foto solicitada."):
        super().__init__(message)


class DocumentNotFoundException(FolderAnalysisException):
    http_status = 404

    def __init__(self, message: str = "No se encontró el documento solicitado."):
        super().__init__(message)


class InvalidCaptureException(FolderAnalysisException):
    http_status = 422


class InvalidDocumentRequestException(FolderAnalysisException):
    http_status = 422


class CaptureNotAvailableException(FolderAnalysisException):
    http_status = 409


class DocumentBusyException(FolderAnalysisException):
    http_status = 409


class TaxStructurerUnavailableException(FolderAnalysisException):
    """The optional LLM step of the tax receipt lane (Ollama) could not run.
    Never fatal: the lane keeps what the rules read and notes it in the
    observations."""

    http_status = 503


class TaxStructurerStoppedException(TaxStructurerUnavailableException):
    """Someone stopped that PC from the digitization monitor while it was writing
    this answer. Handled like any other unavailability, but no other PC is tried
    after a person asked for the work to stop."""

    def __init__(self, message: str = "La consulta se detuvo desde el monitor de computadoras."):
        super().__init__(message)
