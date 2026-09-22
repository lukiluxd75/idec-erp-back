from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class VariableOut(BaseModel):
    id: int
    nombre: str
    clave: str
    tipo_dato: str
    descripcion: Optional[str] = None
    valor_predeterminado: Optional[str] = None
    activa: bool
    creado_en: Optional[datetime] = None


class CreateVariableRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    clave: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z][a-zA-Z0-9_]*$")
    tipo_dato: str = Field(..., min_length=1, max_length=50)
    descripcion: Optional[str] = Field(None, max_length=500)
    valor_predeterminado: Optional[str] = None
