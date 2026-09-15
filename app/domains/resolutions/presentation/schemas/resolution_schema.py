from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.domains.resolutions.domain.entities.resolution import VALID_STATUSES


class PageOut(BaseModel):
    """Metadata for a scanned page. The image is fetched separately as a blob
    (GET .../pages/{orden}) because that endpoint requires Bearer.
    Spanish JSON key `orden` kept for frontend compatibility."""
    orden: int


class ResolutionListItem(BaseModel):
    """One row of the 'Mis resoluciones' list. Spanish keys for the front."""
    resolution_id: str
    nombre: str
    resolution_number: str
    estado: str
    total_pages: int
    created_at: Optional[datetime] = None


class ResolutionDetail(ResolutionListItem):
    """Full resolution detail, including the surface table (opaque JSON: OCR
    pages + building general data — the backend does not inspect it; see
    ResolucionPage.jsx on the frontend)."""
    paginas: List[PageOut] = Field(default_factory=list)
    tabla: Optional[Dict[str, Any]] = None


class SaveTableRequest(BaseModel):
    """Body of PUT .../table: 'Guardar borrador' or 'Generar Excel' from ResolucionPage."""
    tabla: Dict[str, Any]
    estado: str = Field(..., description=f"Uno de: {', '.join(VALID_STATUSES)}")
