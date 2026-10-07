"""
Schemas Pydantic para el dominio CITE.
Request / Response models usados en los endpoints FastAPI.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ── Requests ──────────────────────────────────────────────────────────────────

class CrearConfiguracionCiteRequest(BaseModel):
    id_area: int = Field(..., gt=0, description="PK del área propietaria del CITE")
    id_gestion: int = Field(..., gt=0, description="PK de la gestión (año) vigente")
    prefijo: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Sigla del área, ej. 'DGC'. Se normaliza a mayúsculas.",
    )

    @field_validator("prefijo")
    @classmethod
    def normalizar_prefijo(cls, v: str) -> str:
        return v.strip().upper()


class GenerarCiteRequest(BaseModel):
    id_configuracion: int = Field(..., gt=0, description="PK de la configuracion_cite")
    referencia: str = Field(
        ...,
        min_length=5,
        max_length=1000,
        description="Asunto o referencia del documento que recibirá el CITE",
    )
    id_funcionario_remitente: int = Field(
        ..., gt=0, description="ID del funcionario que genera el CITE"
    )


# ── Responses ─────────────────────────────────────────────────────────────────

class ConfiguracionCiteResponse(BaseModel):
    id_configuracion: int
    id_area: int
    id_gestion: int
    prefijo: str
    activo: bool

    model_config = {"from_attributes": True}


class DocumentoCiteResponse(BaseModel):
    id_documento: int
    id_configuracion: int
    prefijo: str
    correlativo: int
    codigo_cite_completo: str   # "DGC-001"
    fecha_generacion: datetime
    referencia: str
    id_funcionario_remitente: int

    model_config = {"from_attributes": True}
