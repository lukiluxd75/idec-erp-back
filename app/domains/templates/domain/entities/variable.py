from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Variable:
    """Campo reutilizable (placeholder) que una plantilla puede referenciar en su
    contenido HTML, ej. {{nombre_solicitante}} (ver plantillas_dinamicas.variable)."""

    id: Optional[int]
    nombre: str
    clave: str
    tipo_dato: str
    descripcion: Optional[str] = None
    valor_predeterminado: Optional[str] = None
    activa: bool = True
    creado_en: Optional[datetime] = None
    actualizado_en: Optional[datetime] = None
