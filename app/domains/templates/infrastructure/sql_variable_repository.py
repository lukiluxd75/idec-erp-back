from typing import List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.templates.domain.entities.variable import Variable
from app.domains.templates.domain.exceptions import DuplicateVariableKeyException
from app.domains.templates.domain.ports.variable_repository_port import VariableRepositoryPort
from app.domains.templates.infrastructure.models import VariableModel


class SqlVariableRepository(VariableRepositoryPort):
    """Repository adapter implementing VariableRepositoryPort against the real
    `plantillas_dinamicas.variable` table (see infrastructure/models.py)."""

    def __init__(self, db: Session):
        self._db = db

    def list(self) -> List[Variable]:
        models = self._db.query(VariableModel).order_by(VariableModel.nombre).all()
        return [self._to_entity(m) for m in models]

    def get_by_clave(self, clave: str) -> Optional[Variable]:
        model = self._db.query(VariableModel).filter(VariableModel.clave == clave).first()
        return self._to_entity(model) if model else None

    def create(self, variable: Variable) -> Variable:
        model = VariableModel(
            nombre=variable.nombre,
            clave=variable.clave,
            descripcion=variable.descripcion,
            tipo_dato=variable.tipo_dato,
            valor_predeterminado=variable.valor_predeterminado,
            activa=variable.activa,
        )
        self._db.add(model)
        try:
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise DuplicateVariableKeyException(
                f"Ya existe una variable con la clave '{variable.clave}'."
            ) from exc
        self._db.refresh(model)
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: VariableModel) -> Variable:
        return Variable(
            id=model.id,
            nombre=model.nombre,
            clave=model.clave,
            descripcion=model.descripcion,
            tipo_dato=model.tipo_dato,
            valor_predeterminado=model.valor_predeterminado,
            activa=model.activa,
            creado_en=model.creado_en,
            actualizado_en=model.actualizado_en,
        )
