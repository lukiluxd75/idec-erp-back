from app.core.errors.exceptions import DomainException


class ProcedureNotFoundException(DomainException):
    """No procedure exists with the requested code."""
    http_status = 404


class ChatMessageNotFoundException(DomainException):
    """No chat message exists with the requested id (feedback target)."""
    http_status = 404


class EmptyUserMessageException(DomainException):
    """The request carries no user-authored message to answer."""
    http_status = 400


class ChatEngineUnavailableException(DomainException):
    """The external Ollama host is not configured or did not respond. Everything
    that does not depend on the LLM (procedure catalog, admin panel, data
    loading) keeps working — only chat/vision/ingest are affected."""
    http_status = 503


class InvalidUploadException(DomainException):
    """The uploaded file is missing, empty, the wrong type, or too large."""
    http_status = 400


class DocumentIngestFailedException(DomainException):
    """OCR could not read the document, or the LLM could not structure it into a
    procedure (empty/malformed output). `stage` distinguishes which step failed,
    same intent as the ported prototype's per-stage [ETAPA n ...] messages."""
    http_status = 422

    def __init__(self, message: str, stage: str):
        super().__init__(message)
        self.stage = stage


__all__ = [
    "ProcedureNotFoundException",
    "ChatMessageNotFoundException",
    "EmptyUserMessageException",
    "ChatEngineUnavailableException",
    "InvalidUploadException",
    "DocumentIngestFailedException",
]
