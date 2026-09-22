from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CiteConfiguracionOut(BaseModel):
    id: int
    area_codigo: str
    tipo_documento_codigo: str
    nombre: str
    formato: str
    longitud_numero: int
    reinicia_por_gestion: bool
    activa: bool


class CreateCiteConfiguracionRequest(BaseModel):
    area_codigo: str = Field(..., min_length=1, max_length=20)
    tipo_documento_codigo: str = Field(..., min_length=1, max_length=20)
    nombre: str = Field(..., min_length=1, max_length=150)
    formato: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Placeholders disponibles: {area}, {tipo}, {numero}, {gestion}. "
        "Ej. 'GAMC-{area}-{tipo}-{numero}/{gestion}'.",
    )
    longitud_numero: int = Field(5, ge=1, le=12)
    reinicia_por_gestion: bool = True


class GenerateCiteRequest(BaseModel):
    area_codigo: str = Field(..., min_length=1, max_length=20)
    tipo_documento_codigo: str = Field(..., min_length=1, max_length=20)
    tramite_id: Optional[int] = None
    documento_id: Optional[int] = None
    gestion: Optional[int] = Field(None, ge=2000, le=9999, description="Por defecto, el año actual.")


class CiteGeneradoOut(BaseModel):
    id: int
    cite_configuracion_id: int
    gestion: int
    numero_correlativo: int
    codigo: str
    documento_id: Optional[int] = None
    tramite_id: Optional[int] = None
    estado: str
    motivo_anulacion: Optional[str] = None
    generado_en: Optional[datetime] = None
    generado_por: Optional[str] = None
