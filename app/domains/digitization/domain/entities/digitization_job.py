from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


class JobStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


@dataclass
class DigitizationJob:
    """A queued document. Image bytes are not carried here (they are heavy);
    they are loaded on demand through the repository."""

    id: str
    status: str
    file_name: str
    mime_type: str
    requested_by: str
    attempts: int
    created_at: datetime
    updated_at: datetime
    worker_host: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
