import uuid
from typing import List, Optional, Tuple

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.domains.folder_analysis.domain.entities import Capture, CaptureStatus
from app.domains.folder_analysis.domain.ports import CaptureRepositoryPort
from app.domains.folder_analysis.infrastructure.models import CaptureModel


def parse_uuid(value: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _to_entity(row: CaptureModel) -> Capture:
    return Capture(
        id=str(row.id),
        user_sub=row.user_sub,
        file_name=row.file_name,
        mime=row.mime,
        status=row.status,
        created_at=row.created_at,
    )


class SqlCaptureRepository(CaptureRepositoryPort):
    def __init__(self, db: Session):
        self._db = db

    def create(self, user_sub: str, file_name: str, mime: str, image: bytes, thumbnail: bytes) -> Capture:
        row = CaptureModel(
            user_sub=user_sub,
            file_name=file_name,
            mime=mime[:40],
            image=image,
            thumbnail=thumbnail,
            status=CaptureStatus.INBOX,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return _to_entity(row)

    def _owned(self, capture_id: str, user_sub: str) -> Optional[CaptureModel]:
        parsed = parse_uuid(capture_id)
        if parsed is None:
            return None
        return self._db.execute(
            select(CaptureModel).where(CaptureModel.id == parsed, CaptureModel.user_sub == user_sub)
        ).scalar_one_or_none()

    def get(self, capture_id: str, user_sub: str) -> Optional[Capture]:
        row = self._owned(capture_id, user_sub)
        return _to_entity(row) if row else None

    def get_many(self, capture_ids: List[str], user_sub: str) -> List[Capture]:
        parsed = [p for p in map(parse_uuid, capture_ids) if p is not None]
        if not parsed:
            return []
        rows = self._db.execute(
            select(CaptureModel).where(CaptureModel.id.in_(parsed), CaptureModel.user_sub == user_sub)
        ).scalars()
        return [_to_entity(row) for row in rows]

    def list_by_status(self, user_sub: str, status: str) -> List[Capture]:
        rows = self._db.execute(
            select(CaptureModel)
            .where(CaptureModel.user_sub == user_sub, CaptureModel.status == status)
            .order_by(CaptureModel.created_at.desc())
        ).scalars()
        return [_to_entity(row) for row in rows]

    def get_image(self, capture_id: str, user_sub: str, thumbnail: bool = False) -> Optional[Tuple[bytes, str]]:
        parsed = parse_uuid(capture_id)
        if parsed is None:
            return None
        column = CaptureModel.thumbnail if thumbnail else CaptureModel.image
        row = self._db.execute(
            select(column, CaptureModel.mime).where(CaptureModel.id == parsed, CaptureModel.user_sub == user_sub)
        ).first()
        if row is None:
            return None
        return row[0], ("image/jpeg" if thumbnail else row[1])

    def set_status(self, capture_ids: List[str], status: str) -> None:
        parsed = [p for p in map(parse_uuid, capture_ids) if p is not None]
        if not parsed:
            return
        self._db.execute(update(CaptureModel).where(CaptureModel.id.in_(parsed)).values(status=status))
        self._db.commit()

    def delete_many(self, capture_ids: List[str], user_sub: str) -> int:
        parsed = [i for i in (parse_uuid(c) for c in capture_ids) if i is not None]
        if not parsed:
            return 0
        result = self._db.execute(
            delete(CaptureModel).where(
                CaptureModel.id.in_(parsed), CaptureModel.user_sub == user_sub
            )
        )
        self._db.commit()
        return result.rowcount or 0

    def delete(self, capture_id: str, user_sub: str) -> None:
        parsed = parse_uuid(capture_id)
        if parsed is None:
            return
        self._db.execute(
            delete(CaptureModel).where(CaptureModel.id == parsed, CaptureModel.user_sub == user_sub)
        )
        self._db.commit()
