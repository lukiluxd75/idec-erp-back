from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from app.domains.folder_analysis.domain.entities import Capture


class CaptureRepositoryPort(ABC):
    @abstractmethod
    def create(self, user_sub: str, file_name: str, mime: str, image: bytes, thumbnail: bytes) -> Capture: ...

    @abstractmethod
    def get(self, capture_id: str, user_sub: str) -> Optional[Capture]: ...

    @abstractmethod
    def get_many(self, capture_ids: List[str], user_sub: str) -> List[Capture]: ...

    @abstractmethod
    def list_by_status(self, user_sub: str, status: str) -> List[Capture]: ...

    @abstractmethod
    def get_image(self, capture_id: str, user_sub: str, thumbnail: bool = False) -> Optional[Tuple[bytes, str]]:
        """(bytes, mime). The thumbnail is always JPEG."""

    @abstractmethod
    def set_status(self, capture_ids: List[str], status: str) -> None: ...

    @abstractmethod
    def delete(self, capture_id: str, user_sub: str) -> None: ...

    @abstractmethod
    def delete_many(self, capture_ids: List[str], user_sub: str) -> int:
        """Deletes those of the user's photos in one go and says how many went.
        Emptying a bandeja of eighty photos one delete at a time is eighty round
        trips for something the architect asked for once."""
