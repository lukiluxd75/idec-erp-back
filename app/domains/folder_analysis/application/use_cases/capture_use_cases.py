import threading
from collections import OrderedDict
from typing import List, Optional, Tuple

from app.domains.folder_analysis.domain.entities import Capture, CaptureStatus, CaptureVariant
from app.domains.folder_analysis.domain.exceptions import (
    CaptureNotAvailableException,
    CaptureNotFoundException,
    InvalidCaptureException,
)
from app.domains.folder_analysis.domain.ports import (
    CaptureRepositoryPort,
    PdfRasterizerPort,
    ThumbnailPort,
)

MAX_FILE_BYTES = 15 * 1024 * 1024

# Cuánto pesa, en total, lo que entra en UNA petición.
MAX_UPLOAD_BYTES = 300 * 1024 * 1024

PDF_MAGIC = b"%PDF"

# Web-sized copies of the last photos looked at.
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


def forget_previews(capture_ids: List[str]) -> None:
    """Drops the cached previews of photos that were deleted."""
    for capture_id in capture_ids:
        _previews.drop(capture_id)


class UploadCapturesUseCase:
    """Photos sent from the mobile app, or picked on the web, land in the
    architect's inbox unsorted.

    A PDF -- a folio scanned at the counter, a comprobante downloaded from the
    bank, a plano exported from CAD -- is separated here into one photo per
    page. From the inbox on, nothing can tell those pages apart from photos
    taken with the phone: they are dropped on a lane, ordered and read exactly
    the same, in the three lanes alike."""

    def __init__(
        self, repository: CaptureRepositoryPort, thumbnails: ThumbnailPort, pdfs: PdfRasterizerPort
    ):
        self._repository = repository
        self._thumbnails = thumbnails
        self._pdfs = pdfs

    def execute(self, files: List[Tuple[bytes, str, str]], user_sub: str) -> List[Capture]:
        """`files`: (content, mime, file_name) in the order they were sent."""
        if not files:
            raise InvalidCaptureException("Debe enviar al menos un archivo.")
        # Cuántas fotos vienen no se mira: la bandeja no tiene tope.
        total = sum(len(content or b"") for content, _mime, _name in files)
        if total > MAX_UPLOAD_BYTES:
            raise InvalidCaptureException(
                f"El envío pesa {total / (1024 * 1024):.0f} MB y de una vez entran "
                f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB. Mándelas en dos tandas: "
                "la bandeja no tiene límite de fotos."
            )

        prepared = []
        for number, (content, mime, file_name) in enumerate(files, start=1):
            name = (file_name or f"archivo-{number}").strip() or f"archivo-{number}"
            if not content:
                raise InvalidCaptureException(f"{name}: el archivo llegó vacío.")
            if len(content) > MAX_FILE_BYTES:
                raise InvalidCaptureException(f"{name}: supera los 15 MB.")
            place = (number, 0)
            if self._is_pdf(content, mime, name):
                prepared.extend(self._from_pdf(content, name, number))
            else:
                prepared.append((place, *self._from_image(content, mime, name)))

        created = [
            (order, self._repository.create(user_sub, file_name, mime, content, thumbnail))
            for order, content, mime, file_name, thumbnail in prepared
        ]
        return [capture for _, capture in sorted(created, key=lambda pair: pair[0])]

    @staticmethod
    def _is_pdf(content: bytes, mime: str, file_name: str) -> bool:
        # What the file starts with, not what the browser called it: a Windows file picker often hands over no mime at all.
        if content.startswith(PDF_MAGIC):
            return True
        return (mime or "").lower() == "application/pdf" and file_name.lower().endswith(".pdf")

    def _from_image(self, content: bytes, mime: str, name: str) -> Tuple[bytes, str, str, bytes]:
        try:
            thumbnail = self._thumbnails.make(content)
        except InvalidCaptureException:
            raise InvalidCaptureException(
                f"{name}: no es una imagen válida (se aceptan JPG, PNG, WEBP o PDF)."
            ) from None
        safe_mime = mime if (mime or "").startswith("image/") else "image/jpeg"
        return (content, safe_mime, name[:255], thumbnail)

    def _from_pdf(self, content: bytes, name: str, number: int) -> List[Tuple]:
        try:
            pages = self._pdfs.pages(content)
        except InvalidCaptureException as exc:
            raise InvalidCaptureException(f"{name}: {exc.message}") from None

        label = name[:-4] if name.lower().endswith(".pdf") else name
        prepared = []
        for index in reversed(range(len(pages))):
            page_name = f"{label} · pág. {index + 1}" if len(pages) > 1 else label
            prepared.append(
                ((number, index), pages[index], "image/jpeg", page_name[:255], self._thumbnails.make(pages[index]))
            )
        return prepared


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
            return image
        _previews.put(capture_id, preview)
        return preview, "image/jpeg"


class ClearInboxUseCase:
    """Empties the bandeja in one go.

    Only what is still in the bandeja: a photo that is already a page of a
    document is not the bandeja's to throw away -- it is taken out of the
    document first, and that puts it back here. So after emptying, the documents
    keep every photo they were given.
    """

    def __init__(self, repository: CaptureRepositoryPort):
        self._repository = repository

    def execute(self, user_sub: str) -> int:
        captures = self._repository.list_by_status(user_sub, CaptureStatus.INBOX)
        if not captures:
            return 0
        ids = [capture.id for capture in captures]
        removed = self._repository.delete_many(ids, user_sub)
        for capture_id in ids:
            _previews.drop(capture_id)
        return removed


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
