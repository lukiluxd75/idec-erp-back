from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class DocumentGenerateRequest(BaseModel):
    template_id: int = Field(..., description="ID de la plantilla a utilizar")
    valores: Dict[str, Any] = Field(default_factory=dict, description="Valores dinámicos para inyectar en la plantilla")
    tramite_id: Optional[int] = Field(None, description="ID del trámite asociado")
    registro_catastral_id: Optional[int] = Field(None, description="ID del registro catastral asociado")
    predio_id: Optional[int] = Field(None, description="ID del predio asociado")
    titulo: Optional[str] = Field(None, description="Título opcional para el documento")


class DocumentPreviewRequest(BaseModel):
    template_id: int = Field(..., description="ID de la plantilla a previsualizar")
    valores: Dict[str, Any] = Field(default_factory=dict, description="Valores dinámicos para inyectar")


class DocumentPreviewResponse(BaseModel):
    contenido_html_final: str = Field(..., description="HTML generado con los valores inyectados listos para renderizar o convertir a PDF")


class DocumentDetailResponse(BaseModel):
    id: int
    plantilla_id: int
    tramite_id: Optional[int] = None
    registro_catastral_id: Optional[int] = None
    predio_id: Optional[int] = None
    titulo: Optional[str] = None
    contenido_html_final: str
    valores: Dict[str, Any]
    estado: str
    generado_en: datetime
    generado_por: Optional[str] = None
