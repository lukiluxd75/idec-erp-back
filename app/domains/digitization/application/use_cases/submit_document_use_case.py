from typing import Any, Dict, Optional

from app.domains.digitization.domain.entities import DigitizationJob
from app.domains.digitization.domain.exceptions import InvalidDocumentException
from app.domains.digitization.domain.ports import ImagePreprocessorPort, JobRepositoryPort


class SubmitDocumentUseCase:
    """Validate and preprocess the upload right away (so a bad file is rejected
    to the user instead of failing later in the queue), then enqueue it."""

    def __init__(self, repository: JobRepositoryPort, preprocessor: ImagePreprocessorPort, max_bytes: int):
        self._repository = repository
        self._preprocessor = preprocessor
        self._max_bytes = max_bytes

    def execute(
        self,
        file_name: str,
        mime_type: str,
        content: bytes,
        requested_by: str,
        instructions: Optional[str] = None,
        output_template: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> DigitizationJob:
        if not content:
            raise InvalidDocumentException("El archivo está vacío.")
        if len(content) > self._max_bytes:
            max_mb = self._max_bytes // (1024 * 1024)
            raise InvalidDocumentException(f"El archivo supera el tamaño máximo permitido de {max_mb} MB.")
        if content[:5] == b"%PDF-":
            raise InvalidDocumentException(
                "Por ahora solo se aceptan imágenes (JPG, PNG, TIFF, BMP o WEBP). "
                "Si su documento es un PDF, conviértalo a imagen antes de subirlo."
            )

        prepared = self._preprocessor.prepare(content)
        return self._repository.create(
            file_name=(file_name or "documento")[:255],
            mime_type=(mime_type or "application/octet-stream")[:100],
            image=content,
            prepared_image=prepared,
            requested_by=requested_by,
            instructions=instructions,
            output_template=output_template,
            source=source,
        )
