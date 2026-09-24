import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session, undefer

from app.domains.folios.domain.entities.folio import Folio, FolioPage, FolioStatus
from app.domains.folios.domain.exceptions import FolioNotFoundException
from app.domains.folios.domain.ports.folio_repository_port import FolioRepositoryPort
from app.domains.folios.infrastructure.models import FolioModel, FolioPageModel


# A folio still PENDING/PROCESSING with no progress for this long was cut off
# (backend restarted mid-pipeline: BackgroundTasks do not survive it). The
# pipeline touches updated_at after every page, and one page at worst takes
# ~10 min (every OCR call hitting its timeout), so 15 min means "dead".
STALE_AFTER = timedelta(minutes=15)
STALE_MESSAGE = "El procesamiento se interrumpió (posible reinicio del servidor). Reprocese el folio."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_entity(row: FolioModel, with_data: bool) -> Folio:
    return Folio(
        id=row.id,
        user_sub=row.user_sub,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
        pages=[
            FolioPage(
                page_index=p.page_index,
                mime=p.mime,
                rotation_deg=p.rotation_deg,
                detected_page_number=p.detected_page_number,
            )
            for p in row.pages
        ],
        matricula=row.matricula,
        extracted_data=row.extracted_data if with_data else None,
        reviewed_data=row.reviewed_data if with_data else None,
        error_message=row.error_message,
        processed_at=row.processed_at,
        confirmed_at=row.confirmed_at,
        confirmed_by_sub=row.confirmed_by_sub,
    )


def _matricula_of(data: Optional[Dict[str, Any]]) -> Optional[str]:
    numero = ((data or {}).get("matricula") or {}).get("numero")
    return str(numero)[:40] if numero else None


class SqlFolioRepository(FolioRepositoryPort):
    def __init__(self, db: Session):
        self._db = db

    def _fail_stale(self, user_sub: str) -> None:
        """Lazy cleanup (same idea as SqlCaptureStore._purge_expired): run at the
        start of user-facing reads, no background job needed. Compared as naive
        UTC -- the columns are `timestamp without time zone` holding UTC."""
        limit = (_now() - STALE_AFTER).replace(tzinfo=None)
        stale = self._query(user_sub).filter(
            FolioModel.status.in_([FolioStatus.PENDING, FolioStatus.PROCESSING]),
            FolioModel.updated_at < limit,
        )
        if stale.update({"status": FolioStatus.FAILED, "error_message": STALE_MESSAGE}, synchronize_session=False):
            self._db.commit()

    def _query(self, user_sub: Optional[str]):
        q = self._db.query(FolioModel).filter(FolioModel.deleted_at.is_(None))
        return q.filter(FolioModel.user_sub == user_sub) if user_sub is not None else q

    def _row(self, folio_id: str, user_sub: Optional[str], with_data: bool = False) -> Optional[FolioModel]:
        q = self._query(user_sub).filter(FolioModel.id == folio_id)
        if with_data:
            q = q.options(undefer(FolioModel.extracted_data), undefer(FolioModel.reviewed_data))
        return q.first()

    def _require(self, folio_id: str, user_sub: Optional[str], with_data: bool = False) -> FolioModel:
        row = self._row(folio_id, user_sub, with_data)
        if row is None:
            raise FolioNotFoundException("El folio no existe.")
        return row

    # ---- user-scoped ----

    def create(self, user_sub: str, pages: List[Tuple[bytes, str]]) -> Folio:
        now = _now()
        row = FolioModel(
            id=str(uuid.uuid4()),
            user_sub=user_sub,
            status=FolioStatus.PENDING,
            page_count=len(pages),
            created_at=now,
            updated_at=now,
        )
        row.pages = [
            FolioPageModel(id=str(uuid.uuid4()), page_index=i, mime=mime, image=content, created_at=now)
            for i, (content, mime) in enumerate(pages)
        ]
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return _to_entity(row, with_data=False)

    def list(self, user_sub: str) -> List[Folio]:
        self._fail_stale(user_sub)
        rows = self._query(user_sub).order_by(FolioModel.created_at.desc()).all()
        return [_to_entity(r, with_data=False) for r in rows]

    def get(self, folio_id: str, user_sub: str) -> Optional[Folio]:
        self._fail_stale(user_sub)
        row = self._row(folio_id, user_sub, with_data=True)
        return _to_entity(row, with_data=True) if row is not None else None

    def get_page_image(
        self, folio_id: str, page_index: int, user_sub: str, upright: bool
    ) -> Optional[Tuple[bytes, str]]:
        if self._row(folio_id, user_sub) is None:
            return None
        page = (
            self._db.query(FolioPageModel)
            .options(undefer(FolioPageModel.image), undefer(FolioPageModel.upright_image))
            .filter(FolioPageModel.folio_id == folio_id, FolioPageModel.page_index == page_index)
            .first()
        )
        if page is None:
            return None
        if upright and page.upright_image:
            return page.upright_image, "image/jpeg"
        return page.image, page.mime

    def get_diagnostics(self, folio_id: str, user_sub: str) -> Optional[List[Dict[str, Any]]]:
        if self._row(folio_id, user_sub) is None:
            return None
        pages = (
            self._db.query(FolioPageModel)
            .options(undefer(FolioPageModel.diagnostics))
            .filter(FolioPageModel.folio_id == folio_id)
            .order_by(FolioPageModel.page_index)
            .all()
        )
        return [{"page_index": p.page_index, **(p.diagnostics or {})} for p in pages]

    def get_fill_log(self, folio_id: str, user_sub: str) -> Optional[Dict[str, Any]]:
        row = (
            self._query(user_sub)
            .options(undefer(FolioModel.fill_log))
            .filter(FolioModel.id == folio_id)
            .first()
        )
        if row is None:
            return None
        return row.fill_log or {}

    def save_review(self, folio_id: str, user_sub: str, data: Dict[str, Any], confirm: bool) -> Folio:
        row = self._require(folio_id, user_sub, with_data=True)
        now = _now()
        row.reviewed_data = data
        row.matricula = _matricula_of(data) or row.matricula
        row.updated_at = now
        if confirm:
            row.status = FolioStatus.CONFIRMED
            row.confirmed_at = now
            row.confirmed_by_sub = user_sub
        self._db.commit()
        self._db.refresh(row)
        return _to_entity(row, with_data=True)

    def soft_delete(self, folio_id: str, user_sub: str) -> bool:
        row = self._row(folio_id, user_sub)
        if row is None:
            return False
        row.deleted_at = _now()
        self._db.commit()
        return True

    # ---- background pipeline ----

    def get_for_processing(self, folio_id: str) -> Optional[Folio]:
        row = self._row(folio_id, None, with_data=True)
        return _to_entity(row, with_data=True) if row is not None else None

    def get_page_bytes_for_processing(self, folio_id: str) -> List[Tuple[int, bytes, str]]:
        pages = (
            self._db.query(FolioPageModel)
            .options(undefer(FolioPageModel.image))
            .filter(FolioPageModel.folio_id == folio_id)
            .order_by(FolioPageModel.page_index)
            .all()
        )
        return [(p.page_index, p.image, p.mime) for p in pages]

    def mark_processing(self, folio_id: str) -> None:
        row = self._require(folio_id, None, with_data=True)
        row.status = FolioStatus.PROCESSING
        row.error_message = None
        # Reprocessing = start over from a fresh extraction; an unconfirmed
        # draft review would otherwise keep hiding it (confirmed folios are
        # never reprocessed -- see RequestReprocessUseCase).
        row.reviewed_data = None
        row.fill_log = None
        row.updated_at = _now()
        self._db.commit()

    def save_page_result(
        self,
        folio_id: str,
        page_index: int,
        upright_jpeg: Optional[bytes],
        rotation_deg: Optional[float],
        detected_page_number: Optional[int],
        diagnostics: Dict[str, Any],
    ) -> None:
        page = (
            self._db.query(FolioPageModel)
            .filter(FolioPageModel.folio_id == folio_id, FolioPageModel.page_index == page_index)
            .first()
        )
        if page is None:
            return
        page.upright_image = upright_jpeg
        page.rotation_deg = rotation_deg
        page.detected_page_number = detected_page_number
        page.diagnostics = diagnostics
        page.folio.updated_at = _now()  # progress mark, see STALE_AFTER
        self._db.commit()

    def save_extraction(
        self,
        folio_id: str,
        data: Dict[str, Any],
        status: str,
        matricula: Optional[str],
        fill_log: Optional[Dict[str, Any]] = None,
    ) -> None:
        row = self._require(folio_id, None)
        now = _now()
        row.extracted_data = data
        row.fill_log = fill_log
        row.status = status
        row.matricula = matricula
        row.error_message = None
        row.processed_at = now
        row.updated_at = now
        self._db.commit()

    def mark_failed(self, folio_id: str, message: str) -> None:
        row = self._row(folio_id, None)
        if row is None:
            return
        row.status = FolioStatus.FAILED
        row.error_message = message[:2000]
        row.updated_at = _now()
        self._db.commit()
