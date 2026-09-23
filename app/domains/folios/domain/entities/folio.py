"""Entities for a scanned `folio real` (Derechos Reales property record). No
FastAPI, no storage infrastructure."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


class FolioStatus:
    PENDING = "pending"          # uploaded, processing not started yet
    PROCESSING = "processing"    # background pipeline running
    READY = "ready"              # extracted, nothing flagged
    NEEDS_REVIEW = "needs_review"  # extracted, with observations / low-confidence fields
    FAILED = "failed"            # pipeline could not run (OCR down, unreadable pages...)
    CONFIRMED = "confirmed"      # a person reviewed/corrected it on the web

    ALL = {PENDING, PROCESSING, READY, NEEDS_REVIEW, FAILED, CONFIRMED}


@dataclass
class FolioPage:
    """Page metadata. Image bytes do NOT travel in this entity -- fetched
    separately, same as resolutions' pages and geoextraction's captures."""

    page_index: int
    mime: str
    rotation_deg: Optional[float] = None
    detected_page_number: Optional[int] = None


@dataclass
class Folio:
    id: str
    user_sub: str
    status: str
    created_at: datetime
    updated_at: datetime
    pages: List[FolioPage] = field(default_factory=list)
    matricula: Optional[str] = None
    # What the pipeline extracted (never overwritten by the reviewer)...
    extracted_data: Optional[Dict[str, Any]] = None
    # ...and what the reviewer saved on top of it (None until first save).
    reviewed_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    confirmed_by_sub: Optional[str] = None

    @property
    def current_data(self) -> Optional[Dict[str, Any]]:
        return self.reviewed_data if self.reviewed_data is not None else self.extracted_data
