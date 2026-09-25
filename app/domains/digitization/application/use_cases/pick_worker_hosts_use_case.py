from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Set

from app.domains.digitization.domain.ports import VisionWorkerPort


class PickWorkerHostsUseCase:
    """The architects' PCs that can run `model` right now, the ones not digitizing
    first. Exposed through contracts/ so another domain can borrow the same pool
    for its own Ollama calls instead of pinning one host."""

    def __init__(self, worker: VisionWorkerPort, hosts: List[str], busy_hosts: Callable[[], Set[str]]):
        self._worker = worker
        self._hosts = hosts
        self._busy_hosts = busy_hosts

    def execute(self, model: str) -> List[str]:
        if not self._hosts:
            return []
        wanted = {model, f"{model}:latest"}
        with ThreadPoolExecutor(max_workers=len(self._hosts)) as pool:
            installed = list(pool.map(self._worker.models, self._hosts))
        ready = [host for host, names in zip(self._hosts, installed) if names and names & wanted]
        busy = self._busy_hosts()
        # Stable sort: free hosts keep their configured order, busy ones go last.
        return sorted(ready, key=lambda host: host in busy)
