from dataclasses import dataclass
from typing import Optional


@dataclass
class WorkerStatus:
    host: str
    reachable: bool
    model_available: bool
    current_job_id: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.reachable and self.model_available
