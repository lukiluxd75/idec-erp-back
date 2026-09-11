from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.domains.resoluciones.domain.entities.resolucion import ESTADOS_VALIDOS


class PaginaOut(BaseModel):
    """Metadatos de una página escaneada. La imagen se pide aparte, como blob
    (GET .../paginas/{orden}) porque ese endpoint exige Bearer."""
    orden: int


class ResolucionListItem(BaseModel):
    """Una fila del listado 'Mis resoluciones'."""
    id_resolucion: str
    nombre: str
    nro_resolucion: str
    estado: str
    total_paginas: int
    fecha_creacion: Optional[datetime] = None


class ResolucionDetalle(ResolucionListItem):
    """El detalle completo de una resolución, incluida la tabla de superficies
    (JSON opaco: paginas OCR + datos generales del edificio — el backend no mira
    adentro, ver ResolucionPage.jsx en el frontend)."""
    paginas: List[PaginaOut] = Field(default_factory=list)
    tabla: Optional[Dict[str, Any]] = None


class GuardarTablaRequest(BaseModel):
    """Body de PUT .../tabla: 'Guardar borrador' o 'Generar Excel' desde ResolucionPage."""
    tabla: Dict[str, Any]
    estado: str = Field(..., description=f"Uno de: {', '.join(ESTADOS_VALIDOS)}")
