import logging
import time
from contextlib import contextmanager
from typing import Callable, Iterator, Optional

from app.domains.digitization.domain.ports import HostUsagePort

logger = logging.getLogger("uvicorn.error")

# How often a borrowed PC re-reads its stop flag.
_STOP_POLL_SECONDS = 2.0


class BorrowHostUseCase:
    """Marks one of the architects' PCs as taken while another domain runs its own
    LLM call on it, so the monitor screen shows it working no matter who started
    the work. Bookkeeping never breaks the caller: if it cannot be recorded, the
    call still goes through, just not shown as busy.

    The context manager hands back a `should_stop()` the borrower is expected to
    ask while its answer is being written: it turns True when someone pressed
    "Detener" on that PC in the monitor."""

    def __init__(self, usage: HostUsagePort, used_by: str):
        self._usage = usage
        self._used_by = used_by

    @contextmanager
    def execute(self, host: str, seconds: float) -> Iterator[Callable[[], bool]]:
        usage_id: Optional[str] = None
        try:
            usage_id = self._usage.start(host, self._used_by, seconds)
        except Exception:
            logger.warning("digitization: could not record %s using %s", self._used_by, host, exc_info=True)
        try:
            yield self._watcher(usage_id)
        finally:
            if usage_id is not None:
                try:
                    self._usage.finish(usage_id)
                except Exception:
                    logger.warning("digitization: could not release %s", host, exc_info=True)

    def _watcher(self, usage_id: Optional[str]) -> Callable[[], bool]:
        """A call nobody could record cannot be stopped either: there is no row to
        raise the flag on, so the borrower is told to carry on."""
        if usage_id is None:
            return lambda: False

        state = {"asked_at": 0.0, "stop": False}

        def watcher() -> bool:
            now = time.monotonic()
            if not state["stop"] and now - state["asked_at"] >= _STOP_POLL_SECONDS:
                state["asked_at"] = now
                try:
                    state["stop"] = self._usage.stop_requested(usage_id)
                except Exception:
                    # A hiccup reading the flag must not break the call underway.
                    logger.warning("digitization: could not read the stop flag of %s", usage_id, exc_info=True)
            return bool(state["stop"])

        return watcher
