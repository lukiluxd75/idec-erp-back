from typing import List

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status

from app.domains.folder_analysis.domain.entities import CaptureVariant

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


# A photo never changes once it is uploaded, so the browser may keep any of its
# copies for as long as it likes: turning a page back, or coming back to the
# screen tomorrow, costs nothing.
IMMUTABLE_CACHE = "private, max-age=604800, immutable"


def _cached_image(request: Request, use_case: GetCaptureImageUseCase, capture_id: str, user_sub: str, variant: str):
    """The photo's copy, or 304 when the browser already has it. The tag is the
    capture and the copy asked for: neither ever changes."""
    etag = f'"{capture_id}-{variant}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag, "Cache-Control": IMMUTABLE_CACHE})
    content, mime = use_case.execute(capture_id, user_sub, variant)
    return Response(content=content, media_type=mime, headers={"ETag": etag, "Cache-Control": IMMUTABLE_CACHE})


@router.get("/{capture_id}/image")
def get_image(
    capture_id: str,
    request: Request,
    use_case: GetCaptureImageUseCase = Depends(get_capture_image_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """The photo as it was uploaded -- several megabytes. Only the viewer asks
    for it, and only when the architect zooms past what the preview shows."""
    return _cached_image(request, use_case, capture_id, user.sub, CaptureVariant.ORIGINAL)


@router.get("/{capture_id}/preview")
def get_preview(
    capture_id: str,
    request: Request,
    use_case: GetCaptureImageUseCase = Depends(get_capture_image_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    """Web-sized copy: what the review screen opens with."""
    return _cached_image(request, use_case, capture_id, user.sub, CaptureVariant.PREVIEW)


@router.get("/{capture_id}/thumbnail")
def get_thumbnail(
    capture_id: str,
    request: Request,
    use_case: GetCaptureImageUseCase = Depends(get_capture_image_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.view")),
):
    return _cached_image(request, use_case, capture_id, user.sub, CaptureVariant.THUMBNAIL)


@router.delete("/{capture_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_capture(
    capture_id: str,
    use_case: DeleteCaptureUseCase = Depends(get_delete_capture_use_case),
    user: UserProfile = Depends(require_permission("folder-analysis.edit")),
):
    use_case.execute(capture_id, user.sub)
