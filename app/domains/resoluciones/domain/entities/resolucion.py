from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

ESTADOS_VALIDOS = ("pendiente_ocr", "en_proceso", "listo")


@dataclass
class PaginaResolucion:
    """Una página escaneada de la resolución. La imagen en sí no viaja en esta
    entidad (se sirve aparte, como blob, vía ObtenerPaginaUseCase) — acá solo
    viven sus metadatos, que es lo único que necesita el listado/detalle."""

    orden: int
    content_type: str


@dataclass
class Resolucion:
    """Una resolución de PH escaneada desde la app móvil. La tabla de superficies
    extraída por OCR (y los 3 campos de datos generales del edificio) viven en
    `tabla` como JSON opaco: ningún caso de uso del backend necesita mirar
    adentro, es el frontend el que sabe interpretarlo (ver ResolucionPage.jsx)."""

    id_resolucion: str
    nombre: str
    nro_resolucion: str
    estado: str
    fecha_creacion: datetime
    paginas: List[PaginaResolucion] = field(default_factory=list)
    tabla: Optional[Dict[str, Any]] = None

    @property
    def total_paginas(self) -> int:
        return len(self.paginas)
