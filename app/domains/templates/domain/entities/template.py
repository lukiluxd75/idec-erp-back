from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Template:
    """Plantilla dinámica: formato HTML institucional con placeholders de variables,
    versionado y activable/desactivable (ver plantillas_dinamicas.plantilla)."""

    id: Optional[int]
    nombre: str
    codigo: str
    area: str
    tipo_documento: str
    contenido_html: str
    descripcion: Optional[str] = None
    version: int = 1
    activa: bool = True
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
    creado_por: Optional[str] = None
    actualizado_por: Optional[str] = None
