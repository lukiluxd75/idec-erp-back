from fastapi import APIRouter, Depends

from app.domains.folder_analysis.presentation.schemas.folder_analysis_schema import CatalogOut
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(prefix="/catalog", tags=["Folder analysis · Catálogo"])


@router.get("", response_model=CatalogOut)
def get_catalog(
    _user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """The kinds of carpeta and of document the module works with.

    The screen reads this once and draws itself from it: the lanes of a carpeta
    and the fields of its sheet are the catalogue's business, so a new kind of
    carpeta is an entry in domain/folder_types.py and nothing else -- no labels
    written again on the web side, which is where the two would drift apart.
    """
    return CatalogOut.current()
