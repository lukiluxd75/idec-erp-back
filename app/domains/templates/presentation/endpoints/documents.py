from typing import List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status, HTTPException

from app.domains.security.contracts import UserProfile, require_permission
from app.domains.templates.presentation.schemas.document_schema import (
    DocumentGenerateRequest,
    DocumentPreviewRequest,
    DocumentPreviewResponse,
    DocumentDetailResponse,
)

from app.domains.templates.presentation.deps import (
    get_preview_document_use_case,
)
from app.domains.templates.application.use_cases.preview_document_use_case import PreviewDocumentUseCase

# Placeholder para GenerateDocumentUseCase (aún requiere acceso a persistir el DocumentoGenerado en BD)
def get_generate_document_use_case():
    return None

router = APIRouter(tags=["Documentos (Motor)"])


@router.post("/preview", response_model=DocumentPreviewResponse)
def preview_document(
    payload: DocumentPreviewRequest,
    use_case: PreviewDocumentUseCase = Depends(get_preview_document_use_case),
    _user: UserProfile = Depends(require_permission("templates.view")),
):
    """
    Previsualiza el HTML resultante al inyectar los valores en la plantilla usando el motor externo,
    sin generar CITE ni persistir en la base de datos.
    """
    html_result = use_case.execute(payload.template_id, payload.valores)
    return DocumentPreviewResponse(
        contenido_html_final=html_result
    )


@router.post("/generate", response_model=DocumentDetailResponse, status_code=status.HTTP_201_CREATED)
def generate_document(
    payload: DocumentGenerateRequest,
    # use_case = Depends(get_generate_document_use_case),
    user: UserProfile = Depends(require_permission("templates.edit")),
):
    """
    Genera un documento a partir de una plantilla.
    Si corresponde, dispara la generación de CITE.
    Guarda el documento en estado BORRADOR o GENERADO.
    """
    # MOCK RESPONSE (El ingeniero conectará el use_case aquí)
    return DocumentDetailResponse(
        id=999,
        plantilla_id=payload.template_id,
        tramite_id=payload.tramite_id,
        registro_catastral_id=payload.registro_catastral_id,
        predio_id=payload.predio_id,
        titulo=payload.titulo,
        contenido_html_final="<h1>Mock HTML Generado</h1>",
        valores=payload.valores,
        estado="BORRADOR",
        generado_en=datetime.now(timezone.utc),
        generado_por=user.sub,
    )


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def get_document(
    document_id: int,
    _user: UserProfile = Depends(require_permission("templates.view")),
):
    """
    Obtiene el detalle de un documento generado previamente.
    """
    # MOCK RESPONSE (El ingeniero conectará el use_case aquí)
    return DocumentDetailResponse(
        id=document_id,
        plantilla_id=1,
        contenido_html_final="<h1>Documento Recuperado</h1>",
        valores={},
        estado="GENERADO",
        generado_en=datetime.now(timezone.utc),
    )
