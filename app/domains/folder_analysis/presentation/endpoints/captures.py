from typing import List

from fastapi import APIRouter, Depends, File, Response, UploadFile, status

from app.domains.folder_analysis.application.use_cases import (
    DeleteCaptureUseCase,
    GetCaptureImageUseCase,
    ListInboxUseCase,
    UploadCapturesUseCase,
)
from app.domains.folder_analysis.presentation.deps import (
    get_capture_image_use_case,
    get_delete_capture_use_case,
    get_list_inbox_use_case,
    get_upload_captures_use_case,
)
from app.domains.folder_analysis.presentation.schemas.folder_analysis_schema import CaptureOut
from app.domains.security.contracts import UserProfile, require_permission

router = APIRouter(prefix="/captures", tags=["Folder analysis · Captures"])


@router.post("", response_model=List[CaptureOut], status_code=status.HTTP_201_CREATED)
def upload_captures(
    files: List[UploadFile] = File(...),
    use_case: UploadCapturesUseCase = Depends(get_upload_captures_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    """Mobile app entry point: one or more photos (multipart field `files`) that
    land unsorted in the architect's inbox on the web."""
    contents = [(f.file.read(), f.content_type or "", f.filename or "") for f in files]
    return [CaptureOut.from_entity(c) for c in use_case.execute(contents, user.sub)]


@router.get("", response_model=List[CaptureOut])
def list_inbox(
    use_case: ListInboxUseCase = Depends(get_list_inbox_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """Photos not yet sorted into a document, newest first."""
    return [CaptureOut.from_entity(c) for c in use_case.execute(user.sub)]


@router.get("/{capture_id}/image")
def get_image(
    capture_id: str,
    use_case: GetCaptureImageUseCase = Depends(get_capture_image_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    content, mime = use_case.execute(capture_id, user.sub, thumbnail=False)
    return Response(content=content, media_type=mime)


@router.get("/{capture_id}/thumbnail")
def get_thumbnail(
    capture_id: str,
    use_case: GetCaptureImageUseCase = Depends(get_capture_image_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    content, mime = use_case.execute(capture_id, user.sub, thumbnail=True)
    return Response(content=content, media_type=mime)


@router.delete("/{capture_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_capture(
    capture_id: str,
    use_case: DeleteCaptureUseCase = Depends(get_delete_capture_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    use_case.execute(capture_id, user.sub)
