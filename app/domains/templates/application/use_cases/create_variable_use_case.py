from typing import Optional

from app.domains.templates.domain.entities.variable import Variable
from app.domains.templates.domain.ports.variable_repository_port import VariableRepositoryPort


class CreateVariableUseCase:
    """Use case: register a new reusable variable (placeholder)."""

    def __init__(self, repository: VariableRepositoryPort):
        self._repository = repository

    def execute(
        self,
        nombre: str,
        clave: str,
        tipo_dato: str,
        descripcion: Optional[str],
        valor_predeterminado: Optional[str],
    ) -> Variable:
        variable = Variable(
            id=None,
            nombre=nombre,
            clave=clave,
            tipo_dato=tipo_dato,
            descripcion=descripcion,
            valor_predeterminado=valor_predeterminado,
        )
        return self._repository.create(variable)
