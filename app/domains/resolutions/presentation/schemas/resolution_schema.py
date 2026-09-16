from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.domains.resolutions.domain.entities.resolution import VALID_STATUSES


class PageOut(BaseModel):
    """Metadata for a scanned page. The image is fetched separately as a blob
    (GET .../pages/{order_index}) because that endpoint requires Bearer."""
    order_index: int


class ResolutionListItem(BaseModel):
    """One row of the 'Mis resoluciones' list."""
    resolution_id: str
    name: str
    resolution_number: str
    status: str
    total_pages: int
    created_at: Optional[datetime] = None


class ResolutionDetail(ResolutionListItem):
    """Full resolution detail, including the surface table (opaque JSON: OCR
    pages + building general data — the backend does not inspect it; see
    ResolutionPage.jsx on the frontend)."""
    pages: List[PageOut] = Field(default_factory=list)
    table_data: Optional[Dict[str, Any]] = None


class SaveTableRequest(BaseModel):
    """Body of PUT .../table: 'Guardar borrador' or 'Generar Excel' from ResolutionPage."""
    table_data: Dict[str, Any]
    status: str = Field(..., description=f"Uno de: {', '.join(VALID_STATUSES)}")
