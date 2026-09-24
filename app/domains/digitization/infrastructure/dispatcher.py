"""
Background dispatcher: takes pending jobs from the queue and hands each one to a
free architect PC, one job per PC at a time.

Several uvicorn processes may run this backend, but only the one holding a
Postgres advisory lock dispatches (the others wait to take over), so a PC never
receives two jobs and a job is never sent twice. The lock is tied to a DB
connection, so it is released automatically if that process dies; the next
leader puts that process's in-flight jobs back into the queue.
"""
import logging
import threading
import time
from typing import Callable, Dict, List, Optional, Set

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from app.domains.digitization.application.use_cases import ProcessJobUseCase
from app.domains.digitization.domain.entities import DigitizationJob
from app.domains.digitization.domain.exceptions import WorkerUnavailableException
from app.domains.digitization.domain.ports import JobRepositoryPort, VisionWorkerPort

logger = logging.getLogger("uvicorn.error")

# Arbitrary constant identifying this dispatcher's advisory lock in idec_erp.
_LEADER_LOCK_KEY = 820_260_923_001
_FOLLOWER_RETRY_SECONDS = 15.0
# How often a running job re-reads its stop flag. The vision worker asks between
# tokens, several times a second, so without this the database would be hammered.
_STOP_POLL_SECONDS = 2.0


class JobDispatcher:
    def __init__(
        self,
        engine: Engine,
        session_factory: Callable[[], Session],
        repository_factory: Callable[[Session], JobRepositoryPort],
        worker: VisionWorkerPort,
        hosts: List[str],
        max_attempts: int,
        poll_interval: float,
        host_cooldown: float,
    ):
        self._engine = engine
        self._session_factory = session_factory
        self._repository_factory = repository_factory
        self._worker = worker
        self._hosts = hosts
        self._max_attempts = max_attempts
        self._poll_interval = poll_interval
        self._host_cooldown = host_cooldown

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._busy: Set[str] = set()
        self._resting_until: Dict[str, float] = {}

    def start(self) -> None:
        if not self._hosts:
            logger.warning("digitization: DIGITIZATION_WORKER_URLS is empty; jobs will stay queued")
            return
        if self._engine.dialect.name != "postgresql":
            logger.warning("digitization: dispatcher needs PostgreSQL; not started")
            return
        self._thread = threading.Thread(target=self._run, name="digitization-dispatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                with self._engine.connect() as leader_conn:
                    if self._try_lead(leader_conn):
                        logger.info("digitization: this process is now dispatching to %d PCs", len(self._hosts))
                        self._lead(leader_conn)
            except Exception:
                logger.exception("digitization: dispatcher error, retrying")
            self._stop.wait(_FOLLOWER_RETRY_SECONDS)

    @staticmethod
    def _try_lead(conn: Connection) -> bool:
        acquired = conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _LEADER_LOCK_KEY}).scalar()
        conn.commit()
        return bool(acquired)

    def _lead(self, leader_conn: Connection) -> None:
        with self._lock:
            still_running_here = list(self._busy)
        with self._session_factory() as db:
            orphaned = self._repository_factory(db).requeue_orphaned(except_hosts=still_running_here)
        if orphaned:
            logger.warning("digitization: %d interrupted job(s) put back in the queue", orphaned)

        while not self._stop.is_set():
            # Fails (and drops leadership) if the connection holding the lock died.
            leader_conn.execute(text("SELECT 1"))
            leader_conn.commit()
            self._dispatch_round()
            self._stop.wait(self._poll_interval)

    def _dispatch_round(self) -> None:
        free_hosts = self._free_hosts()
        if not free_hosts:
            return
        with self._session_factory() as db:
            repository = self._repository_factory(db)
            if not repository.has_pending():
                return
            for host in free_hosts:
                if not self._worker.check(host).available:
                    self._rest(host)
                    continue
                job = repository.claim_next(host)
                if job is None:
                    return
                with self._lock:
                    self._busy.add(host)
                threading.Thread(
                    target=self._process, args=(job, host), name=f"digitization-{host}", daemon=True
                ).start()

    def _free_hosts(self) -> List[str]:
        now = time.monotonic()
        with self._lock:
            return [h for h in self._hosts if h not in self._busy and self._resting_until.get(h, 0) <= now]

    def _rest(self, host: str) -> None:
        with self._lock:
            self._resting_until[host] = time.monotonic() + self._host_cooldown

    def _process(self, job: DigitizationJob, host: str) -> None:
        try:
            with self._session_factory() as db:
                ProcessJobUseCase(self._repository_factory(db), self._worker, self._max_attempts).execute(
                    job, host, should_stop=self._stop_watcher(job.id)
                )
        except WorkerUnavailableException:
            logger.warning("digitization: PC %s failed on job %s; resting it", host, job.id)
            self._rest(host)
        except Exception as exc:
            logger.exception("digitization: unexpected error on job %s", job.id)
            try:
                with self._session_factory() as db:
                    self._repository_factory(db).mark_failed(job.id, f"Error interno: {exc}")
            except Exception:
                logger.exception("digitization: could not mark job %s as failed", job.id)
        finally:
            with self._lock:
                self._busy.discard(host)

    def _stop_watcher(self, job_id: str) -> Callable[[], bool]:
        """Reads this job's stop flag, at most once every _STOP_POLL_SECONDS and on
        its own session: the flag is written by whichever process served the
        request, which is usually not this one."""
        state = {"asked_at": 0.0, "stop": False}

        def watcher() -> bool:
            now = time.monotonic()
            if not state["stop"] and now - state["asked_at"] >= _STOP_POLL_SECONDS:
                state["asked_at"] = now
                try:
                    with self._session_factory() as db:
                        state["stop"] = self._repository_factory(db).stop_requested(job_id)
                except Exception:
                    # A hiccup reading the flag must not lose the digitization.
                    logger.exception("digitization: could not read the stop flag of job %s", job_id)
            return bool(state["stop"])

        return watcher
