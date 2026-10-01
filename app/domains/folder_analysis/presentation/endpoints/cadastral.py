from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Response

from app.domains.folder_analysis.application.use_cases import (
    GenerateCadastralCroquisUseCase,
    GetDocumentUseCase,
    LookupCadastralParcelUseCase,
)
from app.domains.folder_analysis.presentation.deps import (
    get_generate_cadastral_croquis_use_case,
    get_get_document_use_case,
    get_lookup_cadastral_parcel_use_case,
)
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(prefix="/cadastral", tags=["Folder analysis · IDE catastral"])


@router.get("/parcel")
def lookup_parcel(
    code: str = Query(..., min_length=1, description="Código catastral, como figura en el plano o como lo guarda el GIS."),
    document_id: Optional[str] = Query(
        None, description="El plano del que sale el código: se compara lo que dice con lo que mide el GIS."
    ),
    lookup: LookupCadastralParcelUseCase = Depends(get_lookup_cadastral_parcel_use_case),
    documents: GetDocumentUseCase = Depends(get_get_document_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
) -> Dict[str, Any]:
    """The predio of a code catastral, placed on the IDE: its outline, who is on each
    side of it (by the eight points of the compass), the streets it faces and its
    surface -- measured on the GIS geometry and, with the plano, next to what the
    plano declares."""
    text = None
    if document_id:
        document = documents.execute(document_id, user.sub)
        data = document.data or document.extracted_data or {}
        text = data.get("full_text") if isinstance(data, dict) else None
    return lookup.execute(code, text)


@router.get("/croquis", response_class=Response, responses={200: {"content": {"image/png": {}}}})
def get_croquis(
    code: str = Query(..., min_length=1, description="Código catastral del predio."),
    use_case: GenerateCadastralCroquisUseCase = Depends(get_generate_cadastral_croquis_use_case),
    _user: UserProfile = Depends(require_permission("folder-analysis.view")),
) -> Response:
    """The croquis de ubicación of the predio as a PNG: the IDE layers with the predio
    in grey, a red circle around it and its number, as the certificates print it."""
    return Response(content=use_case.execute(code), media_type="image/png")
