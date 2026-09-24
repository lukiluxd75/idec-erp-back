from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class DocumentType:
    FOLIO = "folio"
    TAX_RECEIPT = "tax_receipt"
    PLAN = "plan"

    ALL = (FOLIO, TAX_RECEIPT, PLAN)


class DocumentStatus:
    DRAFT = "draft"            # pages being arranged, not sent yet
    QUEUED = "queued"          # sent to the PCs, none started
    PROCESSING = "processing"  # at least one page running on a PC
    EXTRACTED = "extracted"    # every page done, merged result ready for review
    FAILED = "failed"          # a page could not be analyzed after its retries
    REVIEWED = "reviewed"      # the architect saved the corrected data

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
