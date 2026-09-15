from typing import List

from app.domains.geoextraction.domain.entities.capture import Capture
from app.domains.geoextraction.domain.ports.capture_store_port import CaptureStorePort


class ListPendingCapturesUseCase:
    """Use case: list captures the user sent from the phone that are not yet
    loaded in CapturePage."""

    def __init__(self, store: CaptureStorePort):
        self._store = store

    def execute(self, user_sub: str) -> List[Capture]:
        return self._store.list_pending(user_sub)
