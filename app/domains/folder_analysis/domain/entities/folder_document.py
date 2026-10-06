from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class DocumentType:
    """The kinds of document the board can hold. Which of them a carpeta shows is
    the carpeta's business, not this list's: see domain/folder_types.py."""

    FOLIO = "folio"
    TAX_RECEIPT = "tax_receipt"
    PLAN = "plan"
    # The documents the carpeta de poseedores brought in.
    APPRAISAL = "appraisal"
    FORM = "form"
    SWORN_STATEMENT = "sworn_statement"
    ID_CARD = "id_card"

    ALL = (FOLIO, TAX_RECEIPT, PLAN, APPRAISAL, FORM, SWORN_STATEMENT, ID_CARD)
    # Lo que la carpeta guarda sin leer.
    NOT_READ = (ID_CARD,)
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


class ReadingStage:
    """En qué está la lectura en servidor, mientras dura.

    El estado del documento y el de cada foto no alcanzan para contarlo: cuando
    la última foto queda leída, todavía faltan las dos pasadas que trabajan sobre
    el documento entero -- buscar los sellos en las fotos y, al final, mirarlas
    con el modelo de visión en las computadoras de los arquitectos. Esa última
    tarda entre veinte y treinta segundos por foto, y sin esto la pantalla decía
    "Interpretando" y se quedaba quieta un minuto, sin forma de saber si estaba
    trabajando o colgada.

    Vacío mientras se leen las fotos (eso ya lo cuenta el estado de cada una) y
    cuando la lectura terminó.
    """

    SEALS = "seals"    # buscando y leyendo los sellos estampados en las fotos
    VISION = "vision"  # qwen3-vl mirando la foto en una computadora prestada

    ALL = (SEALS, VISION)


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
    # The carpeta it was opened in, when it was opened in one.
    folder_id: Optional[str] = None
    # The kind of carpeta it was classified under, which is what says what to pull out of it.
    folder_type: Optional[str] = None
    # What the PCs extracted (never overwritten by the reviewer)...
    extracted_data: Optional[Dict[str, Any]] = None
    # ...and what the architect saved on top of it.
    reviewed_data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    # En qué anda la lectura ahora mismo (ReadingStage), para la pantalla que la mira.
    stage: Optional[str] = None
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
