import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Response

from app.domains.folder_analysis.application.use_cases import (
    GenerateCadastralCroquisUseCase,
    GetDocumentUseCase,
    LookupCadastralParcelUseCase,
)
from app.domains.folder_analysis.domain.exceptions import CadastralLookupFailedException
from app.domains.folder_analysis.presentation.deps import (
    get_generate_cadastral_croquis_use_case,
    get_get_document_use_case,
    get_lookup_cadastral_parcel_use_case,
)
from app.domains.security.contracts import UserProfile, require_permission

logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/cadastral", tags=["Folder analysis · IDE catastral"])


def _plan_text(document) -> Optional[str]:
    """The text the OCR read off the plano. It is in what the PCs extracted; the
    architect's saved review is checked too, in case it is the only copy left."""
    for data in (document.extracted_data, document.reviewed_data):
        if isinstance(data, dict) and data.get("full_text"):
            return data["full_text"]
    return None


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
    text = _plan_text(documents.execute(document_id, user.sub)) if document_id else None
    result = lookup.execute(code, text)
    try:
        # A value JSON cannot carry (NaN) fails AFTER the handler, as a 500 with no
        # CORS headers; better to find out here and say so.
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:
        logger.exception("Folder analysis: la respuesta del predio %s no es serializable", code)
        raise CadastralLookupFailedException(
            f"La respuesta del IDE no se pudo armar ({exc.__class__.__name__})."
        ) from exc
    return result


@router.get("/croquis", response_class=Response, responses={200: {"content": {"image/png": {}}}})
def get_croquis(
    code: str = Query(..., min_length=1, description="Código catastral del predio."),
    use_case: GenerateCadastralCroquisUseCase = Depends(get_generate_cadastral_croquis_use_case),
    _user: UserProfile = Depends(require_permission("folder-analysis.view")),
) -> Response:
    """The croquis de ubicación of the predio as a PNG: the IDE layers with the predio
    in grey, a red circle around it and its number, as the certificates print it."""
    return Response(content=use_case.execute(code), media_type="image/png")
