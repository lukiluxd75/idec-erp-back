from abc import ABC, abstractmethod
from typing import List, Optional, Sequence

from app.domains.alignment.domain.entities.alignment_block import (
    AlignmentBlock,
    AlignmentBlockDetail,
    AlignmentCoverage,
    ControlPointRecord,
)


class AlignmentBlockRepositoryPort(ABC):
    """Port the `alignment` infrastructure must implement to persist
    `alignment_results.alignment_block`/`alignment_control_point`. Mirrors
    the hexagonal convention used across this backend's other domains
    (see CLAUDE.md §3) -- application/ only knows this interface, never
    SQLAlchemy or PostGIS directly."""

    @abstractmethod
    def create(
        self,
        year: int,
        ring: Sequence[Sequence[float]],
        control_points: Sequence[ControlPointRecord],
        transform_params: dict,
        rmse_m: float,
        created_by_sub: Optional[str] = None,
    ) -> AlignmentBlock:
        """Persists a new block in 'draft' status with its control points and
        the already-fitted transform (see domain/services/affine_fit.py --
        the use case computes it, the repository only stores it)."""

    @abstractmethod
    def list_by_year(self, year: int) -> List[AlignmentBlock]:
        """Every non-deleted block for a year, for the map overlay."""

    @abstractmethod
    def get(self, block_id: int) -> Optional[AlignmentBlockDetail]:
        """One block with its control points and transform, or None."""

    @abstractmethod
    def update(
        self,
        block_id: int,
        ring: Sequence[Sequence[float]],
        control_points: Sequence[ControlPointRecord],
        transform_params: dict,
        rmse_m: float,
    ) -> AlignmentBlock:
        """Replaces a block's polygon/control points/transform. Resets a
        previously 'confirmed' block back to 'draft' -- an edited block needs
        re-confirming, its old confirmation no longer describes the new fit."""

    @abstractmethod
    def confirm(self, block_id: int, confirmed_by_sub: Optional[str] = None) -> AlignmentBlock:
        """Marks a block 'confirmed' -- the point at which it counts toward
        coverage() and is trusted as a base layer elsewhere."""

    @abstractmethod
    def delete(self, block_id: int) -> None:
        """Soft-deletes a block (sets deleted_at)."""

    @abstractmethod
    def coverage(self, year: int) -> AlignmentCoverage:
        """Confirmed-only area covered so far for a year, out of all of
        Cercado -- the progress indicator for the module."""
