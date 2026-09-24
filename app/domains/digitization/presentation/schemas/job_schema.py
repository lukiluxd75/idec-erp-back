from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel

from app.domains.digitization.domain.entities import DigitizationJob, WorkerStatus


class JobSummary(BaseModel):
    id: str
    status: str
    file_name: str
    attempts: int
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    @classmethod
    def from_entity(cls, job: DigitizationJob) -> "JobSummary":
        return cls(
            id=job.id,
            status=job.status,
            file_name=job.file_name,
            attempts=job.attempts,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class JobDetail(JobSummary):
    result: Optional[Dict[str, Any]] = None

    @classmethod
    def from_entity(cls, job: DigitizationJob) -> "JobDetail":
        return cls(**JobSummary.from_entity(job).model_dump(), result=job.result)


class WorkerStatusResponse(BaseModel):
    host: str
    reachable: bool
    model_available: bool
    current_job_id: Optional[str] = None

    @classmethod
    def from_entity(cls, status: WorkerStatus) -> "WorkerStatusResponse":
        return cls(
            host=status.host,
            reachable=status.reachable,
            model_available=status.model_available,
            current_job_id=status.current_job_id,
        )
