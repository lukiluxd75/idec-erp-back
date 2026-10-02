from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class DocumentType:
    """The kinds of document the board can hold. Which of them a carpeta shows is
    the carpeta's business, not this list's: see domain/folder_types.py."""

    FOLIO = "folio"
    TAX_RECEIPT = "tax_receipt"
    PLAN = "plan"
    # The documents the carpeta de poseedores brought in. None of them has rules
    # of its own yet, so they are read with the generic OCR (text, labelled
    # values and tables) until someone writes down what to pull out of each.
    APPRAISAL = "appraisal"
    FORM = "form"
    SWORN_STATEMENT = "sworn_statement"
    ID_CARD = "id_card"

    ALL = (FOLIO, TAX_RECEIPT, PLAN, APPRAISAL, FORM, SWORN_STATEMENT, ID_CARD)
    # Lo que la carpeta guarda sin leer. Es el carril de "otros documentos": lo
    # que el poseedor trae de respaldo y no tiene datos que sacarle, sino que
    # acompaña a la carpeta. Se archiva con sus fotos y nada más -- ni OCR, ni
    # cola, ni pantalla de revisión -- porque leerlo solo gastaría el servidor
    # para guardar un texto que nadie va a mirar.
    NOT_READ = (ID_CARD,)
    # Every lane is read here on the server, with the GAMC PaddleOCR service and
    # OpenCV (seconds), and none is queued to the architects' PCs for the vision
    # model any more (minutes per sheet). A folio and a comprobante are forms, so
    # rules read them; a plano has no fixed layout, so what is stored is its text,
    # its labelled values and its tables -- and that same generic reading is what
    # a document without rules gets. None of them carries a job id:
    # RunServerReadingUseCase writes their result.
    # Los dos de arriba juntos son ALL, sin repetidos. Va escrito a mano porque
    # dentro del cuerpo de una clase una comprensión no ve NOT_READ; hay un test
    # que lo comprueba para que no se desincronicen al agregar un carril.
    SERVER_READ = (FOLIO, TAX_RECEIPT, PLAN, APPRAISAL, FORM, SWORN_STATEMENT)


class DocumentStatus:
    DRAFT = "draft"            # pages being arranged, not sent yet
    QUEUED = "queued"          # analysis asked for, no page started yet
    PROCESSING = "processing"  # at least one page being read
    EXTRACTED = "extracted"    # every page done, merged result ready for review
    FAILED = "failed"          # a page could not be analyzed after its retries
    REVIEWED = "reviewed"      # the architect saved the corrected data
    FILED = "filed"            # guardado con sus fotos, sin leer (DocumentType.NOT_READ)

    IN_PROGRESS = (QUEUED, PROCESSING)


class PageStatus:
    DRAFT = "draft"
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"

    IN_PROGRESS = (QUEUED, PROCESSING)


@dataclass
class DocumentPage:
    capture_id: str
    page_index: int
    status: str = PageStatus.DRAFT
    job_id: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


@dataclass
class FolderDocument:
    id: str
    user_sub: str
    doc_type: str
    status: str
    created_at: datetime
    updated_at: datetime
    pages: List[DocumentPage] = field(default_factory=list)
    # The carpeta it was opened in, when it was opened in one. A document from
    # before the carpetas -- or one classified on the loose board -- has none.
    folder_id: Optional[str] = None
    # The kind of carpeta it was classified under, which is what says what to
    # pull out of it. A document opened inside a carpeta takes the carpeta's
    # kind; one classified on the loose board takes the kind chosen there.
    folder_type: Optional[str] = None
    # What the PCs extracted (never overwritten by the reviewer)...
    extracted_data: Optional[Dict[str, Any]] = None
    # ...and what the architect saved on top of it.
    reviewed_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    analyzed_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None

    @property
    def current_data(self) -> Optional[Dict[str, Any]]:
        return self.reviewed_data if self.reviewed_data is not None else self.extracted_data


@dataclass(frozen=True)
class QueuedJob:
    """Status of one page's extraction job as reported by the digitization queue."""

    status: str  # pending | processing | done | failed
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
