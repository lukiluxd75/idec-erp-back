from typing import Optional, Sequence

from app.domains.alignment.domain.entities.alignment_block import AlignmentBlock, ControlPointRecord
from app.domains.alignment.domain.exceptions import InvalidControlPoints
from app.domains.alignment.domain.ports.alignment_block_repository_port import (
    AlignmentBlockRepositoryPort,
)
from app.domains.alignment.domain.services.affine_fit import fit_affine

# The fixed reference year (its own predios/manzanas polygon layer is the
# "ground truth" every other year gets corrected against) -- see
# doc/alignment_schema.sql. Aligning it against itself makes no sense.
REFERENCE_YEAR = 2015


class CreateAlignmentBlockUseCase:
    """Saves a new manzana-sized correction: the architect draws a polygon
    (not crossing predios, not covering the whole street -- see the schema's
    header) and marks control points comparing the target year's current WMS
    position against the fixed 2015 layer. Fits the affine transform here
    (domain/services/affine_fit.py) before handing it to the repository,
    which only persists."""

    def __init__(self, repository: AlignmentBlockRepositoryPort):
        self._repository = repository

    def execute(
        self,
        year: int,
        ring: Sequence[Sequence[float]],
        control_points: Sequence[ControlPointRecord],
        created_by_sub: Optional[str] = None,
    ) -> AlignmentBlock:
        if year == REFERENCE_YEAR:
            raise InvalidControlPoints(
                f"{REFERENCE_YEAR} es el año base -- no se alinea contra sí mismo."
            )
        if len(ring) < 3:
            raise InvalidControlPoints("El polígono de la manzana necesita al menos 3 vértices.")

        transform_params, rmse_m = fit_affine(control_points)
        return self._repository.create(
            year=year,
            ring=ring,
            control_points=control_points,
            transform_params=transform_params,
            rmse_m=rmse_m,
            created_by_sub=created_by_sub,
        )
