from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional


class JobStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    # Aborted mid-run from the PC monitor.
    STOPPED = "stopped"


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
    # Set by other domains through contracts/: what to extract and the JSON shape to return.
    instructions: Optional[str] = None
    output_template: Optional[Dict[str, Any]] = None
    source: Optional[str] = None
