from typing import Any, Dict

from app.domains.resolutions.domain.entities.resolution import VALID_STATUSES, Resolution
from app.domains.resolutions.domain.exceptions import (
    InvalidStatusException,
    ResolutionNotFoundException,
)
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort


class SaveTableUseCase:
    """Use case: save the surface table (reviewed/edited OCR) and the flow
    status of a resolution — 'Guardar borrador' or 'Generar Excel'."""

    def __init__(self, repository: ResolutionRepositoryPort):
        self._repository = repository

    def execute(
        self, resolution_id: str, table_data: Dict[str, Any], status: str, user_sub: str
    ) -> Resolution:
        if status not in VALID_STATUSES:
            raise InvalidStatusException(
                f"Estado '{status}' inválido. Debe ser uno de: {', '.join(VALID_STATUSES)}."
            )

        resolution = self._repository.save_table(resolution_id, table_data, status, user_sub)
        if resolution is None:
            raise ResolutionNotFoundException(f"No existe la resolución '{resolution_id}'.")
        return resolution
