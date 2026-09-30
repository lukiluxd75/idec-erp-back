from typing import Sequence

from app.domains.alignment.domain.entities.alignment_block import AlignmentBlock, ControlPointRecord
from app.domains.alignment.domain.exceptions import InvalidControlPoints
from app.domains.alignment.domain.ports.alignment_block_repository_port import (
    AlignmentBlockRepositoryPort,
)
from app.domains.alignment.domain.services.affine_fit import fit_affine


class UpdateAlignmentBlockUseCase:
    """Re-draws a block's polygon and/or re-marks its control points,
    recomputing the fit. See AlignmentBlockRepositoryPort.update -- this
    always drops the block back to 'draft'."""

    def __init__(self, repository: AlignmentBlockRepositoryPort):
        self._repository = repository

    def execute(
        self,
        block_id: int,
        ring: Sequence[Sequence[float]],
        control_points: Sequence[ControlPointRecord],
    ) -> AlignmentBlock:
        if len(ring) < 3:
            raise InvalidControlPoints("El polígono de la manzana necesita al menos 3 vértices.")

        transform_params, rmse_m = fit_affine(control_points)
        return self._repository.update(
            block_id=block_id,
            ring=ring,
            control_points=control_points,
            transform_params=transform_params,
            rmse_m=rmse_m,
        )
