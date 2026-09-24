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
