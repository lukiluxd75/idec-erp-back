from typing import List

from app.domains.chatbot.domain.entities.procedure import Procedure
from app.domains.chatbot.domain.ports.procedure_repository_port import ProcedureRepositoryPort


class ListProceduresUseCase:
    """Use case: full procedure catalog for the admin screen (active and inactive)."""

    def __init__(self, procedure_repository: ProcedureRepositoryPort):
        self._procedures = procedure_repository

    def execute(self) -> List[Procedure]:
        return self._procedures.list_for_admin()
