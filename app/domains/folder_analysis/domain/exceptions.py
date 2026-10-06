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


class RegisteredFolderNotFoundException(FolderAnalysisException):
    http_status = 404

    def __init__(self, message: str = "No se encontró la carpeta registrada."):
        super().__init__(message)


class InvalidRegisteredFolderException(FolderAnalysisException):
    """The name is empty or too long, or the selection is not usable."""

    http_status = 422


class RegisteredFolderNameTakenException(FolderAnalysisException):
    """Two carpetas with the same name could not be told apart in the list."""

    http_status = 409


class DocumentAlreadyFiledException(FolderAnalysisException):
    """A document sits in a single carpeta, like the paper it came from."""

    http_status = 409


class CadastralGisUnavailableException(FolderAnalysisException):
    """The cadastral GIS (the IDE) did not answer. Nothing is lost: the sheet can
    still be filled by hand, as before."""

    http_status = 503


class CadastralLookupFailedException(FolderAnalysisException):
    """Something unexpected broke while looking a predio up. Raised so the screen
    gets a message (and the log a traceback) instead of a dropped connection."""

    http_status = 502


class CadastralParcelNotFoundException(FolderAnalysisException):
    http_status = 404


class VisionReadingUnavailableException(FolderAnalysisException):
    """La pasada final con el modelo de visión (las computadoras de los
    arquitectos) no se pudo hacer. Nunca es fatal: la lectura se queda en lo que
    dieron el OCR, las reglas y el sello, y queda dicho en las observaciones."""

    http_status = 503


class VisionReadingStoppedException(VisionReadingUnavailableException):
    """Alguien detuvo esa computadora desde el monitor de digitalización mientras
    miraba la foto. Se trata como cualquier otra falta de disponibilidad, pero no
    se prueba con otra computadora después de que una persona pidió parar."""

    def __init__(self, message: str = "La lectura se detuvo desde el monitor de computadoras."):
        super().__init__(message)
