from app.core.errors.exceptions import DomainException


class FolioNotFoundException(DomainException):
    """No folio with that id exists for the current user."""
    http_status = 404


class InvalidFolioUploadException(DomainException):
    """Missing/empty pages, unsupported format, too many or too large pages."""
    http_status = 400


class FolioNotEditableException(DomainException):
    """The folio is in a state that does not allow the requested change (e.g.
    reprocessing an already confirmed folio, or editing one still processing)."""
    http_status = 409


class OcrUnavailableException(DomainException):
    """The external GAMC OCR service is not configured, unreachable, timed out
    or reported the job as failed. Stored on the folio as its error message
    (the pipeline runs in background, nobody is waiting on an HTTP response)."""
    http_status = 503


class AsientoStructurerUnavailableException(DomainException):
    """The optional LLM step (Ollama) could not run. Never fatal: the pipeline
    keeps the rule-based parse and just notes it in the observations."""
    http_status = 503


__all__ = [
    "FolioNotFoundException",
    "InvalidFolioUploadException",
    "FolioNotEditableException",
    "OcrUnavailableException",
    "AsientoStructurerUnavailableException",
]
