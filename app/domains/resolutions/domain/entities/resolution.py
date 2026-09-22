from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

VALID_STATUSES = ("pendiente_ocr", "en_proceso", "listo")


@dataclass
class ResolutionPage:
    """Metadata for one scanned resolution page. Image bytes are served separately
    via GetPageUseCase — list/detail only need order and content type."""

    order_index: int
    content_type: str


@dataclass
class PlanPage:
    """One page of the approved floor plan (site plan), used to work out
    colindancias for that floor — a separate photo set from `pages` above
    (those are the "RELACION DE SUPERFICIE" table scans). Each one is tagged
    with which floor it shows (`planta`, one of domain.plantas.PLANTAS_RESUMEN)
    and where it came from (`source`: 'app' o 'web' — ver
    add_plan_pages_use_case.py, ambos canales usan el mismo endpoint)."""

    order_index: int
    content_type: str
    planta: str
    source: str


@dataclass
class Resolution:
    """PH resolution scanned from the mobile app. OCR surface table (and building
    general fields) live in table_data as opaque JSON — backend use cases do not
    interpret it; the frontend does (see Resolutions pages)."""

    resolution_id: str
    name: str
    resolution_number: str
    status: str
    created_at: datetime
    pages: List[ResolutionPage] = field(default_factory=list)
    plan_pages: List[PlanPage] = field(default_factory=list)
    table_data: Optional[Dict[str, Any]] = None

    @property
    def total_pages(self) -> int:
        return len(self.pages)
