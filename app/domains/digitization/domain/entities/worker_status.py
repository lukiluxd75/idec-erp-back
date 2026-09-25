from dataclasses import dataclass
from typing import Optional


@dataclass
class WorkerStatus:
    host: str
    reachable: bool
    model_available: bool
    current_job_id: Optional[str] = None
    # Domain currently occupying the PC ("digitization", "folios", "chatbot"…),
    # so the monitor shows it as working whoever started the work.
    used_by: Optional[str] = None

    @property
    def available(self) -> bool:
        return self.reachable and self.model_available

    @property
    def busy(self) -> bool:
        return self.used_by is not None
