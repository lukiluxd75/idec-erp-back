"""
Postgres adapter for CaptureStorePort. Replaces MemoriaCapturaStore: with the
backend running several workers (`--workers 4` in production), each process had
its own separate memory, so a photo saved by the worker that handled the phone
POST was invisible to the worker serving the web GET — this adapter persists it
in the same Postgres the 4 processes already share, so any of them sees the same.

Still not a business record: 30 min TTL (lazy purge, no background job) and a
per-user cap, same as the in-memory version. The real difference of this change
is only the "where", not how permanent it is.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.domains.geoextraction.domain.entities.capture import Capture
from app.domains.geoextraction.domain.ports.capture_store_port import CaptureStorePort
from app.domains.geoextraction.infrastructure.models import CaptureModel

TTL = timedelta(minutes=30)
MAX_CAPTURES_PER_USER = 5


def _to_entity(row: CaptureModel) -> Capture:
    return Capture(capture_id=row.capture_id, mime=row.mime, created_at=row.created_at)


class SqlCaptureStore(CaptureStorePort):
    def __init__(self, db: Session):
        self._db = db

    def _purge_expired(self) -> None:
        """Delete captures (any user) past the TTL. Called at the start of each
        public operation — no background task; lazy purge is enough for expected volume."""
        limit = datetime.now(timezone.utc) - TTL
        self._db.query(CaptureModel).filter(CaptureModel.created_at < limit).delete(
            synchronize_session=False
        )
        self._db.commit()

    def save(self, content: bytes, mime: str, user_sub: str) -> Capture:
        self._purge_expired()

        pending = (
            self._db.query(CaptureModel)
            .filter(CaptureModel.user_sub == user_sub)
            .order_by(CaptureModel.created_at.asc())
            .all()
        )
        while len(pending) >= MAX_CAPTURES_PER_USER:
            self._db.delete(pending.pop(0))  # discard oldest (FIFO)

        row = CaptureModel(
            capture_id=str(uuid.uuid4()),
            user_sub=user_sub,
            mime=mime,
            image=content,
            created_at=datetime.now(timezone.utc),
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return _to_entity(row)

    def list_pending(self, user_sub: str) -> List[Capture]:
        self._purge_expired()
        rows = (
            self._db.query(CaptureModel)
            .filter(CaptureModel.user_sub == user_sub)
            .order_by(CaptureModel.created_at.desc())
            .all()
        )
        return [_to_entity(r) for r in rows]

    def get_image(self, id_captura: str, user_sub: str) -> Optional[Tuple[bytes, str]]:
        self._purge_expired()
        row = (
            self._db.query(CaptureModel)
            .filter(CaptureModel.capture_id == id_captura, CaptureModel.user_sub == user_sub)
            .first()
        )
        if row is None:
            return None
        return row.image, row.mime

    def discard(self, id_captura: str, user_sub: str) -> bool:
        self._purge_expired()
        row = (
            self._db.query(CaptureModel)
            .filter(CaptureModel.capture_id == id_captura, CaptureModel.user_sub == user_sub)
            .first()
        )
        if row is None:
            return False
        self._db.delete(row)
        self._db.commit()
        return True
