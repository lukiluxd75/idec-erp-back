import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session, undefer

from app.domains.digitization.domain.entities import DigitizationJob, JobStatus
from app.domains.digitization.domain.ports import JobRepositoryPort
from app.domains.digitization.infrastructure.models import DigitizationJobModel as Job


def _parse_id(job_id: str) -> Optional[uuid.UUID]:
    try:
        return uuid.UUID(str(job_id))
    except (ValueError, TypeError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_entity(row: Job, with_instructions: bool = False) -> DigitizationJob:
    job = DigitizationJob(
        id=str(row.id),
        status=row.status,
        file_name=row.file_name,
        mime_type=row.mime_type,
        requested_by=row.requested_by,
        attempts=row.attempts,
        created_at=row.created_at,
        updated_at=row.updated_at,
        worker_host=row.worker_host,
        result=row.result,
        error=row.error,
        started_at=row.started_at,
        finished_at=row.finished_at,
        source=row.source,
    )
    if with_instructions:
        job.instructions = row.instructions
        job.output_template = row.output_template
    return job


class SqlJobRepository(JobRepositoryPort):
    def __init__(self, db: Session):
        self._db = db

    def create(
        self,
        file_name: str,
        mime_type: str,
        image: bytes,
        prepared_image: bytes,
        requested_by: str,
        instructions: Optional[str] = None,
        output_template: Optional[Dict[str, Any]] = None,
        source: Optional[str] = None,
    ) -> DigitizationJob:
        row = Job(
            status=JobStatus.PENDING,
            file_name=file_name,
            mime_type=mime_type,
            image=image,
            prepared_image=prepared_image,
            requested_by=requested_by,
            attempts=0,
            instructions=instructions,
            output_template=output_template,
            source=source,
        )
        self._db.add(row)
        self._db.commit()
        self._db.refresh(row)
        return _to_entity(row)

    def get(self, job_id: str) -> Optional[DigitizationJob]:
        parsed = _parse_id(job_id)
        if parsed is None:
            return None
        row = self._db.get(Job, parsed)
        return _to_entity(row) if row else None

    def get_many(self, job_ids: List[str]) -> List[DigitizationJob]:
        parsed = [p for p in (_parse_id(job_id) for job_id in job_ids) if p is not None]
        if not parsed:
            return []
        rows = self._db.execute(select(Job).where(Job.id.in_(parsed))).scalars()
        return [_to_entity(row) for row in rows]

    def get_prepared_image(self, job_id: str) -> Optional[bytes]:
        parsed = _parse_id(job_id)
        if parsed is None:
            return None
        return self._db.execute(select(Job.prepared_image).where(Job.id == parsed)).scalar_one_or_none()

    def list_by_requester(self, requested_by: str, limit: int) -> List[DigitizationJob]:
        rows = self._db.execute(
            select(Job).where(Job.requested_by == requested_by).order_by(Job.created_at.desc()).limit(limit)
        ).scalars()
        return [_to_entity(row) for row in rows]

    def list_processing(self) -> List[DigitizationJob]:
        rows = self._db.execute(select(Job).where(Job.status == JobStatus.PROCESSING)).scalars()
        return [_to_entity(row) for row in rows]

    def find_processing_on(self, worker_host: str) -> Optional[DigitizationJob]:
        row = self._db.execute(
            select(Job)
            .where(Job.status == JobStatus.PROCESSING, Job.worker_host == worker_host)
            .order_by(Job.started_at.desc())
            .limit(1)
        ).scalars().first()
        return _to_entity(row) if row else None

    def has_pending(self) -> bool:
        return self._db.execute(
            select(Job.id).where(Job.status == JobStatus.PENDING).limit(1)
        ).first() is not None

    def claim_next(self, worker_host: str) -> Optional[DigitizationJob]:
        row = self._db.execute(
            select(Job)
            .where(Job.status == JobStatus.PENDING)
            .order_by(Job.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
            .options(undefer(Job.instructions), undefer(Job.output_template))
        ).scalars().first()
        if row is None:
            self._db.rollback()
            return None
        row.status = JobStatus.PROCESSING
        # A flag left over from an earlier run would stop this one on its first token.
        row.stop_requested = False
        row.worker_host = worker_host
        row.attempts = row.attempts + 1
        row.started_at = _now()
        self._db.commit()
        self._db.refresh(row)
        return _to_entity(row, with_instructions=True)

    def mark_done(self, job_id: str, result: Dict[str, Any]) -> None:
        self._update(job_id, status=JobStatus.DONE, result=result, error=None, finished_at=_now())

    def release(self, job_id: str, error: str) -> None:
        self._update(job_id, status=JobStatus.PENDING, error=error, worker_host=None, started_at=None)

    def mark_failed(self, job_id: str, error: str) -> None:
        self._update(job_id, status=JobStatus.FAILED, error=error, finished_at=_now())

    def request_stop(self, job_id: str) -> None:
        self._update(job_id, stop_requested=True)

    def stop_requested(self, job_id: str) -> bool:
        parsed = _parse_id(job_id)
        if parsed is None:
            return False
        # A plain column read: the flag is written by another process, so the
        # session's cached copy of the row must not be consulted.
        return bool(self._db.execute(select(Job.stop_requested).where(Job.id == parsed)).scalar_one_or_none())

    def mark_stopped(self, job_id: str, error: str) -> None:
        self._update(
            job_id, status=JobStatus.STOPPED, error=error, finished_at=_now(), stop_requested=False
        )

    def requeue_orphaned(self, except_hosts: List[str]) -> int:
        statement = update(Job).where(Job.status == JobStatus.PROCESSING)
        if except_hosts:
            statement = statement.where(Job.worker_host.not_in(except_hosts))
        result = self._db.execute(statement.values(status=JobStatus.PENDING, worker_host=None, started_at=None))
        self._db.commit()
        return result.rowcount or 0

    def requeue_failed(self, job_id: str) -> Optional[DigitizationJob]:
        parsed = _parse_id(job_id)
        if parsed is None:
            return None
        result = self._db.execute(
            update(Job)
            .where(Job.id == parsed, Job.status.in_([JobStatus.FAILED, JobStatus.STOPPED]))
            .values(
                status=JobStatus.PENDING, attempts=0, error=None, stop_requested=False,
                worker_host=None, started_at=None, finished_at=None,
            )
        )
        self._db.commit()
        return self.get(job_id) if result.rowcount else None

    def _update(self, job_id: str, **values: Any) -> None:
        parsed = _parse_id(job_id)
        if parsed is None:
            return
        self._db.execute(update(Job).where(Job.id == parsed).values(**values))
        self._db.commit()
