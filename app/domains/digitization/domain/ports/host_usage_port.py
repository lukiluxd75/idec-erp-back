from abc import ABC, abstractmethod
from typing import Dict


class HostUsagePort(ABC):
    """Who is using each architect PC right now, shared across backend processes
    so the monitor screen sees work started anywhere (digitization's own queue is
    read from the jobs table instead)."""

    @abstractmethod
    def start(self, host: str, used_by: str, seconds: float) -> str:
        """Records that `used_by` took the PC and returns the usage id. The record
        expires after `seconds` so a process that dies does not leave it busy."""

    @abstractmethod
    def finish(self, usage_id: str) -> None: ...

    @abstractmethod
    def active(self) -> Dict[str, str]:
        """host -> who is using it, ignoring expired records."""

    @abstractmethod
    def request_stop(self, host: str) -> int:
        """Asks whoever is using that PC to drop the call. Returns how many live
        usages were flagged, so the caller knows whether there was anything to stop."""

    @abstractmethod
    def stop_requested(self, usage_id: str) -> bool: ...
