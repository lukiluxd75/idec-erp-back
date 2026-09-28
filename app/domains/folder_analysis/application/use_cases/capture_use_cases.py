import threading
from collections import OrderedDict
from typing import List, Optional, Tuple

from app.domains.folder_analysis.domain.entities import Capture, CaptureStatus, CaptureVariant
from app.domains.folder_analysis.domain.exceptions import (
    CaptureNotAvailableException,
    CaptureNotFoundException,
    InvalidCaptureException,
)
from app.domains.folder_analysis.domain.ports import CaptureRepositoryPort, ThumbnailPort

MAX_FILES_PER_UPLOAD = 10
MAX_FILE_BYTES = 15 * 1024 * 1024

# Web-sized copies of the last photos looked at. A photo never changes once it is
# uploaded, so a copy made for one architect is the copy for everyone; without it
# every page turn in the review screen pays the resize again.
PREVIEW_CACHE_SIZE = 48


class _PreviewCache:
    """Small LRU of finished previews, shared by every request of the process."""

    def __init__(self, size: int = PREVIEW_CACHE_SIZE):
        self._size = size
        self._items: "OrderedDict[str, bytes]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[bytes]:
        with self._lock:
            if key not in self._items:
                return None
            self._items.move_to_end(key)
            return self._items[key]

    def put(self, key: str, content: bytes) -> None:
        with self._lock:
            self._items[key] = content
            self._items.move_to_end(key)
            while len(self._items) > self._size:
                self._items.popitem(last=False)

    def drop(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)


_previews = _PreviewCache()


class UploadCapturesUseCase:
    """Photos sent from the mobile app land in the architect's inbox, unsorted."""

    def __init__(self, repository: CaptureRepositoryPort, thumbnails: ThumbnailPort):
        self._repository = repository
        self._thumbnails = thumbnails

    def execute(self, files: List[Tuple[bytes, str, str]], user_sub: str) -> List[Capture]:
        """`files`: (content, mime, file_name) in the order they were sent."""
        if not files:
            raise InvalidCaptureException("Debe enviar al menos una foto.")
        if len(files) > MAX_FILES_PER_UPLOAD:
            raise InvalidCaptureException(f"Puede enviar como máximo {MAX_FILES_PER_UPLOAD} fotos a la vez.")

        prepared = []
        for number, (content, mime, file_name) in enumerate(files, start=1):
            if not content:
                raise InvalidCaptureException(f"La foto {number} llegó vacía.")
            if len(content) > MAX_FILE_BYTES:
                raise InvalidCaptureException(f"La foto {number} supera los 15 MB.")
            try:
                thumbnail = self._thumbnails.make(content)
            except InvalidCaptureException:
                raise InvalidCaptureException(
                    f"La foto {number} no es una imagen válida (se aceptan JPG, PNG o WEBP)."
                ) from None
            safe_mime = mime if (mime or "").startswith("image/") else "image/jpeg"
            prepared.append((content, safe_mime, (file_name or f"foto-{number}.jpg")[:255], thumbnail))

        return [
            self._repository.create(user_sub, file_name, mime, content, thumbnail)
            for content, mime, file_name, thumbnail in prepared
        ]


class ListInboxUseCase:
    def __init__(self, repository: CaptureRepositoryPort):
        self._repository = repository

    def execute(self, user_sub: str) -> List[Capture]:
        return self._repository.list_by_status(user_sub, CaptureStatus.INBOX)


class GetCaptureImageUseCase:
    """One of the three copies of a photo (see CaptureVariant). The preview is
    made from the original the first time it is asked for and kept in memory
    afterwards; the thumbnail was already made when the photo was uploaded."""

    def __init__(self, repository: CaptureRepositoryPort, thumbnails: ThumbnailPort):
        self._repository = repository
        self._thumbnails = thumbnails

    def execute(self, capture_id: str, user_sub: str, variant: str = CaptureVariant.PREVIEW) -> Tuple[bytes, str]:
        if variant == CaptureVariant.PREVIEW:
            cached = _previews.get(capture_id)
            if cached is not None:
                return cached, "image/jpeg"

        image = self._repository.get_image(capture_id, user_sub, variant == CaptureVariant.THUMBNAIL)
        if image is None:
            raise CaptureNotFoundException()
        if variant != CaptureVariant.PREVIEW:
            return image

        try:
            preview = self._thumbnails.preview(image[0])
        except InvalidCaptureException:
            # Unreadable here but readable when it was uploaded: send the original
            # rather than leaving the architect without the photo.
            return image
        _previews.put(capture_id, preview)
        return preview, "image/jpeg"


class DeleteCaptureUseCase:
    def __init__(self, repository: CaptureRepositoryPort):
        self._repository = repository

    def execute(self, capture_id: str, user_sub: str) -> None:
        capture = self._repository.get(capture_id, user_sub)
        if capture is None:
            raise CaptureNotFoundException()
        if capture.status != CaptureStatus.INBOX:
            raise CaptureNotAvailableException(
                "La foto forma parte de un documento. Quítela del documento antes de eliminarla."
            )
        self._repository.delete(capture_id, user_sub)
        _previews.drop(capture_id)
