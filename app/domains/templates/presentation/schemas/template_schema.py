from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TemplateListItem(BaseModel):
    """One row of the templates catalog."""
    id: int
    nombre: str
    codigo: str
    area: str
    tipo_documento: str
    version: int
    activa: bool
    creado_en: Optional[datetime] = None


class TemplateDetail(TemplateListItem):
    """Full template detail, including the HTML content with variable placeholders."""
    descripcion: Optional[str] = None
    contenido_html: str
    actualizado_en: Optional[datetime] = None
    creado_por: Optional[str] = None
    actualizado_por: Optional[str] = None


class CreateTemplateRequest(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=200)
    codigo: str = Field(..., min_length=1, max_length=100)
    area: str = Field(..., min_length=1, max_length=100)
    tipo_documento: str = Field(..., min_length=1, max_length=100)
    contenido_html: str = Field(..., min_length=1)
    descripcion: Optional[str] = Field(None, max_length=500)


class UpdateTemplateRequest(BaseModel):
    """Partial update: only the fields actually sent are changed (see
    `save_table`-style PUT bodies elsewhere in this backend). `activa` lets the
    catalog UI reactivate a template without a dedicated endpoint -- DELETE
    already deactivates one-way, this is the way back."""
    nombre: Optional[str] = Field(None, min_length=1, max_length=200)
    codigo: Optional[str] = Field(None, min_length=1, max_length=100)
    area: Optional[str] = Field(None, min_length=1, max_length=100)
    tipo_documento: Optional[str] = Field(None, min_length=1, max_length=100)
    contenido_html: Optional[str] = Field(None, min_length=1)
    descripcion: Optional[str] = Field(None, max_length=500)
    activa: Optional[bool] = None
