from datetime import datetime, timedelta, timezone
from typing import Callable, Dict

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.domains.digitization.domain.ports import HostUsagePort
from app.domains.digitization.infrastructure.models import HostUsageModel


class SqlHostUsageRepository(HostUsagePort):
    """Opens its own short session per call: a usage wraps an LLM request that can
    take minutes, much longer than the caller's request session lives."""

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def start(self, host: str, used_by: str, seconds: float) -> str:
        now = datetime.now(timezone.utc)
        with self._session_factory() as db:
            db.execute(delete(HostUsageModel).where(HostUsageModel.expires_at < now))
            row = HostUsageModel(host=host, used_by=used_by, expires_at=now + timedelta(seconds=seconds))
            db.add(row)
            db.flush()
            usage_id = str(row.id)
            db.commit()
        return usage_id

    def finish(self, usage_id: str) -> None:
        with self._session_factory() as db:
            db.execute(delete(HostUsageModel).where(HostUsageModel.id == usage_id))
            db.commit()

    def request_stop(self, host: str) -> int:
        now = datetime.now(timezone.utc)
        with self._session_factory() as db:
            result = db.execute(
                update(HostUsageModel)
                .where(HostUsageModel.host == host, HostUsageModel.expires_at > now)
                .values(stop_requested=True)
            )
            db.commit()
        return result.rowcount or 0

    def stop_requested(self, usage_id: str) -> bool:
        with self._session_factory() as db:
            return bool(
                db.execute(
                    select(HostUsageModel.stop_requested).where(HostUsageModel.id == usage_id)
                ).scalar_one_or_none()
            )

    def active(self) -> Dict[str, str]:
        now = datetime.now(timezone.utc)
        with self._session_factory() as db:
            rows = db.execute(
                select(HostUsageModel.host, HostUsageModel.used_by)
                .where(HostUsageModel.expires_at > now)
                .order_by(HostUsageModel.started_at)
            ).all()
        return {host: used_by for host, used_by in rows}
