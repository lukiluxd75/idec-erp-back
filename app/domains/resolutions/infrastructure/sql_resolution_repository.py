import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from app.domains.resolutions.domain.entities.resolution import ResolutionPage, Resolution
from app.domains.resolutions.domain.ports.resolution_repository_port import ResolutionRepositoryPort
from app.domains.resolutions.infrastructure.models import ResolutionModel, ResolutionPageModel


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
        # Ownership check without pulling every page's image (see _get_model):
        # this only needs to know the resolution exists and belongs to user_sub.
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
        # list()/_get_model() only need order_index + mime (see _to_entity) — the
        # `image` BLOB (avg ~550KB/page here) is only ever needed by get_page(),
        # which queries it directly. Eager-loading it everywhere else meant every
        # resolutions list/detail pulled every photo's full bytes across a DB link
        # with ~120ms latency for nothing.
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

        # Soft delete (`deleted_at` column): the row and its pages stay in the DB,
        # they just stop being listed/fetched — see deleted_at IS NULL filter above.
        model.deleted_at = datetime.utcnow()
        self._db.commit()
        return True

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

    @staticmethod
    def _to_entity(model: ResolutionModel) -> Resolution:
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
            table_data=model.table_data,
        )
