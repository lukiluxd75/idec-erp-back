from typing import List, Tuple

from app.domains.folder_analysis.domain.entities import Capture, CaptureStatus
from app.domains.folder_analysis.domain.exceptions import (
    CaptureNotAvailableException,
    CaptureNotFoundException,
    InvalidCaptureException,
)
from app.domains.folder_analysis.domain.ports import CaptureRepositoryPort, ThumbnailPort

MAX_FILES_PER_UPLOAD = 10
MAX_FILE_BYTES = 15 * 1024 * 1024


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
    def __init__(self, repository: CaptureRepositoryPort):
        self._repository = repository

    def execute(self, capture_id: str, user_sub: str, thumbnail: bool) -> Tuple[bytes, str]:
        image = self._repository.get_image(capture_id, user_sub, thumbnail)
        if image is None:
            raise CaptureNotFoundException()
        return image


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
