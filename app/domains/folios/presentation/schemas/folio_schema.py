from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FolioPageItem(BaseModel):
    page_index: int
    rotation_deg: Optional[float] = None
    detected_page_number: Optional[int] = None


class FolioListItem(BaseModel):
    id: str
    status: str
    matricula: Optional[str] = None
    page_count: int
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class FolioDetail(FolioListItem):
    pages: List[FolioPageItem]
    # What the pipeline extracted, what the reviewer saved, and the one to show
    # (reviewed if any, else extracted).
    extracted_data: Optional[Dict[str, Any]] = None
    reviewed_data: Optional[Dict[str, Any]] = None
    data: Optional[Dict[str, Any]] = None
    confirmed_by_sub: Optional[str] = None


class FolioReviewRequest(BaseModel):
    data: Dict[str, Any] = Field(..., description="JSON completo del folio corregido")
    confirm: bool = False
