from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.templates.domain.entities.template import Template
from app.domains.templates.domain.exceptions import DuplicateTemplateCodeException
from app.domains.templates.domain.ports.template_repository_port import TemplateRepositoryPort
from app.domains.templates.infrastructure.models import TemplateModel


class SqlTemplateRepository(TemplateRepositoryPort):
    """Repository adapter implementing TemplateRepositoryPort against the real
    `plantillas_dinamicas.plantilla` table (see infrastructure/models.py)."""

    def __init__(self, db: Session):
        self._db = db

    def list(self) -> List[Template]:
        models = self._db.query(TemplateModel).order_by(TemplateModel.creado_en.desc()).all()
        return [self._to_entity(m) for m in models]

    def get(self, template_id: int) -> Optional[Template]:
        model = self._db.get(TemplateModel, template_id)
        return self._to_entity(model) if model else None

    def get_by_codigo(self, codigo: str) -> Optional[Template]:
        model = self._db.query(TemplateModel).filter(TemplateModel.codigo == codigo).first()
        return self._to_entity(model) if model else None

    def create(self, template: Template, user_sub: str) -> Template:
        model = TemplateModel(
            nombre=template.nombre,
            codigo=template.codigo,
            area=template.area,
            tipo_documento=template.tipo_documento,
            descripcion=template.descripcion,
            contenido_html=template.contenido_html,
            version=template.version,
            activa=template.activa,
            creado_por=user_sub,
        )
        self._db.add(model)
        try:
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise DuplicateTemplateCodeException(
                f"Ya existe una plantilla con el código '{template.codigo}'."
            ) from exc
        self._db.refresh(model)
        return self._to_entity(model)

    def update(self, template_id: int, changes: Dict[str, Any], user_sub: str) -> Optional[Template]:
        model = self._db.get(TemplateModel, template_id)
        if model is None:
            return None

        for field, value in changes.items():
            setattr(model, field, value)
        model.version += 1
        model.actualizado_en = datetime.utcnow()
        model.actualizado_por = user_sub
        try:
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            raise DuplicateTemplateCodeException(
                f"Ya existe una plantilla con el código '{changes.get('codigo')}'."
            ) from exc
        self._db.refresh(model)
        return self._to_entity(model)

    def set_active(self, template_id: int, activa: bool, user_sub: str) -> Optional[Template]:
        model = self._db.get(TemplateModel, template_id)
        if model is None:
            return None

        model.activa = activa
        model.actualizado_en = datetime.utcnow()
        model.actualizado_por = user_sub
        self._db.commit()
        self._db.refresh(model)
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: TemplateModel) -> Template:
        return Template(
            id=model.id,
            nombre=model.nombre,
            codigo=model.codigo,
            area=model.area,
            tipo_documento=model.tipo_documento,
            contenido_html=model.contenido_html,
            descripcion=model.descripcion,
            version=model.version,
            activa=model.activa,
            creado_en=model.creado_en,
            actualizado_en=model.actualizado_en,
            creado_por=model.creado_por,
            actualizado_por=model.actualizado_por,
        )
