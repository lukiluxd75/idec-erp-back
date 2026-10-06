import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from app.domains.resolutions.domain.entities.resolution import PlanPage, PlantaStatus, ResolutionPage, Resolution
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort
from app.domains.resolutions.infrastructure.models import ResolutionModel, ResolutionPageModel
from app.domains.resolutions.infrastructure.plan_page_models import ResolutionPlanPageModel


class SqlResolutionRepository(ResolutionRepositoryPort):
    """Repository adapter implementing ResolutionRepositoryPort against the real
    `resolutions` schema (populated by the mobile app, see infrastructure/models.py).
    """

    def __init__(self, db: Session):
        self._db = db

    def list(self, user_sub: str) -> List[Resolution]:
        models = (
            self._db.query(ResolutionModel)
            .options(self._pages_without_image())
            .filter(ResolutionModel.user_sub == user_sub, ResolutionModel.deleted_at.is_(None))
            .order_by(ResolutionModel.created_at.desc())
            .all()
        )
        return [self._to_entity(m) for m in models]

    def get(self, resolution_id: str, user_sub: str) -> Optional[Resolution]:
        model = self._get_model(resolution_id, user_sub)
        return self._to_entity(model) if model else None

    def get_page(self, resolution_id: str, order_index: int, user_sub: str) -> Optional[Tuple[bytes, str]]:
        owned = (
            self._db.query(ResolutionModel.resolution_id)
            .filter(
                ResolutionModel.resolution_id == resolution_id,
                ResolutionModel.user_sub == user_sub,
                ResolutionModel.deleted_at.is_(None),
            )
            .first()
        )
        if owned is None:
            return None

        page = (
            self._db.query(ResolutionPageModel)
            .filter(
                ResolutionPageModel.resolution_id == resolution_id,
                ResolutionPageModel.order_index == order_index,
            )
            .first()
        )
        return (page.image, page.mime) if page else None

    @staticmethod
    def _pages_without_image():
        return joinedload(ResolutionModel.pages).load_only(
            ResolutionPageModel.order_index, ResolutionPageModel.mime
        )

    def create(
        self,
        name: str,
        resolution_number: str,
        pages: List[Tuple[bytes, str]],
        user_sub: str,
    ) -> Resolution:
        now = datetime.utcnow()
        model = ResolutionModel(
            resolution_id=str(uuid.uuid4()),
            name=name,
            resolution_number=resolution_number,
            status="pendiente_ocr",
            user_sub=user_sub,
            created_at=now,
            updated_at=now,
        )
        model.pages = [
            ResolutionPageModel(
                page_id=str(uuid.uuid4()),
                order_index=i + 1,
                image=content,
                mime=mime,
                file_name=f"pagina_{i + 1}.jpg",
            )
            for i, (content, mime) in enumerate(pages)
        ]
        self._db.add(model)
        self._db.commit()
        self._db.refresh(model)
        return self._to_entity(model)

    def save_table(
        self, resolution_id: str, table_data: Dict[str, Any], status: str, user_sub: str
    ) -> Optional[Resolution]:
        model = self._get_model(resolution_id, user_sub)
        if model is None:
            return None

        model.table_data = table_data
        model.status = status
        model.updated_at = datetime.utcnow()
        self._db.commit()
        self._db.refresh(model)
        return self._to_entity(model)

    def delete(self, resolution_id: str, user_sub: str) -> bool:
        model = self._get_model(resolution_id, user_sub)
        if model is None:
            return False

        model.deleted_at = datetime.utcnow()
        self._db.commit()
        return True

    def add_plan_pages(
        self,
        resolution_id: str,
        pages: List[Tuple[bytes, str, List[str]]],
        source: str,
        user_sub: str,
    ) -> Optional[Resolution]:
        model = self._get_model(resolution_id, user_sub)
        if model is None:
            return None

        siguiente = (
            self._db.query(ResolutionPlanPageModel.order_index)
            .filter(ResolutionPlanPageModel.resolution_id == resolution_id)
            .order_by(ResolutionPlanPageModel.order_index.desc())
            .first()
        )
        inicio = (siguiente[0] + 1) if siguiente else 1
        for i, (content, mime, plantas) in enumerate(pages):
            self._db.add(
                ResolutionPlanPageModel(
                    plan_page_id=str(uuid.uuid4()),
                    resolution_id=resolution_id,
                    order_index=inicio + i,
                    planta=plantas[0] if plantas else "",
                    plantas=list(plantas),
                    planta_status=PlantaStatus.MANUAL if plantas else PlantaStatus.DETECTANDO,
                    image=content,
                    mime=mime,
                    file_name=f"plano_{inicio + i}.jpg",
                    source=source,
                )
            )
        self._db.commit()
        return self._to_entity(model)

    def get_plan_page(self, resolution_id: str, order_index: int, user_sub: str) -> Optional[Tuple[bytes, str]]:
        owned = (
            self._db.query(ResolutionModel.resolution_id)
            .filter(
                ResolutionModel.resolution_id == resolution_id,
                ResolutionModel.user_sub == user_sub,
                ResolutionModel.deleted_at.is_(None),
            )
            .first()
        )
        if owned is None:
            return None

        page = (
            self._db.query(ResolutionPlanPageModel)
            .filter(
                ResolutionPlanPageModel.resolution_id == resolution_id,
                ResolutionPlanPageModel.order_index == order_index,
            )
            .first()
        )
        return (page.image, page.mime) if page else None

    def get_plan_page_for_processing(self, resolution_id: str, order_index: int) -> Optional[Tuple[bytes, str]]:
        page = self._plan_page_model(resolution_id, order_index)
        return (page.image, page.mime) if page else None

    def update_plan_page_planta(
        self,
        resolution_id: str,
        order_index: int,
        plantas: List[str],
        status: str,
        title: Optional[str] = None,
        detection: Optional[Dict[str, Any]] = None,
        user_sub: Optional[str] = None,
    ) -> Optional[PlanPage]:
        if user_sub is not None and self._get_model(resolution_id, user_sub) is None:
            return None
        page = self._plan_page_model(resolution_id, order_index)
        if page is None:
            return None
        page.planta = plantas[0] if plantas else ""
        page.plantas = list(plantas)
        page.planta_status = status
        page.planta_title = title[:200] if title else None
        page.planta_detection = detection
        self._db.commit()
        return self._to_plan_page(page)

    def _plan_page_model(self, resolution_id: str, order_index: int) -> Optional[ResolutionPlanPageModel]:
        return (
            self._db.query(ResolutionPlanPageModel)
            .filter(
                ResolutionPlanPageModel.resolution_id == resolution_id,
                ResolutionPlanPageModel.order_index == order_index,
            )
            .first()
        )

    def delete_plan_page(self, resolution_id: str, order_index: int, user_sub: str) -> Optional[Resolution]:
        model = self._get_model(resolution_id, user_sub)
        if model is None:
            return None

        page = (
            self._db.query(ResolutionPlanPageModel)
            .filter(
                ResolutionPlanPageModel.resolution_id == resolution_id,
                ResolutionPlanPageModel.order_index == order_index,
            )
            .first()
        )
        if page is None:
            return None

        self._db.delete(page)
        self._db.commit()
        return self._to_entity(model)

    def _get_model(self, resolution_id: str, user_sub: str) -> Optional[ResolutionModel]:
        return (
            self._db.query(ResolutionModel)
            .options(self._pages_without_image())
            .filter(
                ResolutionModel.resolution_id == resolution_id,
                ResolutionModel.user_sub == user_sub,
                ResolutionModel.deleted_at.is_(None),
            )
            .first()
        )

    def _get_plan_pages(self, resolution_id: str) -> List[PlanPage]:
        rows = (
            self._db.query(ResolutionPlanPageModel)
            .filter(ResolutionPlanPageModel.resolution_id == resolution_id)
            .order_by(ResolutionPlanPageModel.order_index)
            .all()
        )
        return [self._to_plan_page(p) for p in rows]

    @staticmethod
    def _to_plan_page(p: ResolutionPlanPageModel) -> PlanPage:
        # Filas anteriores a `plantas` (una sola planta por página): se usa `planta`.
        plantas = list(p.plantas) if p.plantas is not None else ([p.planta] if p.planta else [])
        return PlanPage(
            order_index=p.order_index,
            content_type=p.mime,
            plantas=plantas,
            source=p.source,
            planta_status=p.planta_status or PlantaStatus.MANUAL,
            planta_title=p.planta_title,
            planta_detection=p.planta_detection,
        )

    def _to_entity(self, model: ResolutionModel) -> Resolution:
        return Resolution(
            resolution_id=model.resolution_id,
            name=model.name,
            resolution_number=model.resolution_number,
            status=model.status,
            created_at=model.created_at,
            pages=[
                ResolutionPage(order_index=p.order_index, content_type=p.mime)
                for p in sorted(model.pages, key=lambda p: p.order_index)
            ],
            plan_pages=self._get_plan_pages(model.resolution_id),
            table_data=model.table_data,
        )
