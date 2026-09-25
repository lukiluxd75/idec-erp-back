from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

VALID_STATUSES = ("pendiente_ocr", "en_proceso", "listo")


class PlantaStatus:
    """Cómo se asignó la planta de una página del plano."""

    MANUAL = "manual"          # la eligió quien subió la foto o la corrigieron en la web
    DETECTANDO = "detectando"  # subida sin planta, leyendo el título del plano en segundo plano
    DETECTADA = "detectada"    # sacada del título del plano ("PLANTA TIPO 2° - 4° PISO")
    SIN_TITULO = "sin_titulo"  # no se encontró un título claro: hay que asignarla a mano
    ERROR = "error"            # el OCR falló: se puede reintentar o asignar a mano


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
    with which floor(s) it shows (`plantas`, names from
    domain.plantas.PLANTAS_RESUMEN -- varias cuando la hoja vale para varios
    pisos iguales, "PLANTA TIPO 2° - 4° PISO") and where it came from
    (`source`: 'app' o 'web' — ver add_plan_pages_use_case.py, ambos canales
    usan el mismo endpoint).

    Si se sube sin planta, se detecta sola del título del plano (ver
    domain/plan_title.py y `planta_status`). `planta` es la primera de
    `plantas` ("" mientras no tenga), para clientes que conocen una sola."""

    order_index: int
    content_type: str
    plantas: List[str]
    source: str
    planta_status: str = PlantaStatus.MANUAL
    planta_title: Optional[str] = None  # texto del título del que salió la planta
    planta_detection: Optional[Dict[str, Any]] = None  # detalle para depurar (candidatos, motivo)

    @property
    def planta(self) -> str:
        return self.plantas[0] if self.plantas else ""


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
