"""Postgres adapter for AlignmentBlockRepositoryPort against
`alignment_results.alignment_block`/`alignment_control_point`."""
from datetime import datetime
from typing import List, Optional, Sequence

from geoalchemy2.elements import WKTElement
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.domains.alignment.domain.entities.alignment_block import (
    AlignmentBlock,
    AlignmentBlockDetail,
    AlignmentCoverage,
    ControlPointRecord,
)
from app.domains.alignment.domain.exceptions import AlignmentBlockNotFound
from app.domains.alignment.domain.ports.alignment_block_repository_port import (
    AlignmentBlockRepositoryPort,
)
from app.domains.alignment.infrastructure.geom_utils import geom_to_geojson, ring_to_wkt_polygon
from app.domains.alignment.infrastructure.models import AlignmentBlockModel, AlignmentControlPointModel
from app.domains.alignment.infrastructure.user_lookup import resolve_user_id, resolve_usernames

_SRID = 4326


def _to_entity(row: AlignmentBlockModel, usernames: dict) -> AlignmentBlock:
    return AlignmentBlock(
        id=row.id,
        year=row.year,
        geom_geojson=geom_to_geojson(row.geom),
        status=row.status,
        transform_method=row.transform_method,
        rmse_m=float(row.rmse_m) if row.rmse_m is not None else None,
        cropped_image_path=row.cropped_image_path,
        created_by_username=usernames.get(str(row.created_by)) if row.created_by else None,
        created_at=row.created_at,
        confirmed_by_username=usernames.get(str(row.confirmed_by)) if row.confirmed_by else None,
        confirmed_at=row.confirmed_at,
    )


def _to_detail_entity(row: AlignmentBlockModel, usernames: dict) -> AlignmentBlockDetail:
    base = _to_entity(row, usernames)
    return AlignmentBlockDetail(
        **base.__dict__,
        transform_params=row.transform_params,
        control_points=[
            ControlPointRecord(
                order_index=cp.order_index,
                lon_ref=float(cp.lon_ref),
                lat_ref=float(cp.lat_ref),
                lon_mov=float(cp.lon_mov),
                lat_mov=float(cp.lat_mov),
            )
            for cp in row.control_points
        ],
    )


class SqlAlignmentBlockRepository(AlignmentBlockRepositoryPort):
    def __init__(self, db: Session):
        self._db = db

    def _get_row(self, block_id: int) -> AlignmentBlockModel:
        row = (
            self._db.query(AlignmentBlockModel)
            .filter(AlignmentBlockModel.id == block_id, AlignmentBlockModel.deleted_at.is_(None))
            .first()
        )
        if row is None:
            raise AlignmentBlockNotFound(block_id)
        return row

    def create(
        self,
        year: int,
        ring: Sequence[Sequence[float]],
        control_points: Sequence[ControlPointRecord],
        transform_params: dict,
        rmse_m: float,
        created_by_sub: Optional[str] = None,
    ) -> AlignmentBlock:
        user_id = resolve_user_id(self._db, created_by_sub)
        row = AlignmentBlockModel(
            year=year,
            geom=WKTElement(ring_to_wkt_polygon(ring), srid=_SRID),
            transform_params=transform_params,
            rmse_m=rmse_m,
            created_by=user_id,
        )
        self._db.add(row)
        self._db.flush()
        for cp in control_points:
            self._db.add(
                AlignmentControlPointModel(
                    alignment_block_id=row.id,
                    order_index=cp.order_index,
                    lon_ref=cp.lon_ref,
                    lat_ref=cp.lat_ref,
                    lon_mov=cp.lon_mov,
                    lat_mov=cp.lat_mov,
                )
            )
        self._db.commit()
        self._db.refresh(row)
        usernames = resolve_usernames(self._db, [row.created_by])
        return _to_entity(row, usernames)

    def list_by_year(self, year: int) -> List[AlignmentBlock]:
        rows = (
            self._db.query(AlignmentBlockModel)
            .filter(AlignmentBlockModel.year == year, AlignmentBlockModel.deleted_at.is_(None))
            .order_by(AlignmentBlockModel.id.asc())
            .all()
        )
        usernames = resolve_usernames(self._db, [r.created_by for r in rows] + [r.confirmed_by for r in rows])
        return [_to_entity(r, usernames) for r in rows]

    def get(self, block_id: int) -> Optional[AlignmentBlockDetail]:
        row = (
            self._db.query(AlignmentBlockModel)
            .filter(AlignmentBlockModel.id == block_id, AlignmentBlockModel.deleted_at.is_(None))
            .first()
        )
        if row is None:
            return None
        usernames = resolve_usernames(self._db, [row.created_by, row.confirmed_by])
        return _to_detail_entity(row, usernames)

    def update(
        self,
        block_id: int,
        ring: Sequence[Sequence[float]],
        control_points: Sequence[ControlPointRecord],
        transform_params: dict,
        rmse_m: float,
    ) -> AlignmentBlock:
        row = self._get_row(block_id)
        row.geom = WKTElement(ring_to_wkt_polygon(ring), srid=_SRID)
        row.transform_params = transform_params
        row.rmse_m = rmse_m
        row.updated_at = datetime.utcnow()
        # An edited block no longer matches its old confirmation -- back to
        # draft, needs re-confirming (see AlignmentBlockRepositoryPort.update).
        row.status = "draft"
        row.confirmed_by = None
        row.confirmed_at = None

        for cp in list(row.control_points):
            self._db.delete(cp)
        self._db.flush()
        for cp in control_points:
            self._db.add(
                AlignmentControlPointModel(
                    alignment_block_id=row.id,
                    order_index=cp.order_index,
                    lon_ref=cp.lon_ref,
                    lat_ref=cp.lat_ref,
                    lon_mov=cp.lon_mov,
                    lat_mov=cp.lat_mov,
                )
            )
        self._db.commit()
        self._db.refresh(row)
        usernames = resolve_usernames(self._db, [row.created_by])
        return _to_entity(row, usernames)

    def confirm(self, block_id: int, confirmed_by_sub: Optional[str] = None) -> AlignmentBlock:
        row = self._get_row(block_id)
        row.status = "confirmed"
        row.confirmed_by = resolve_user_id(self._db, confirmed_by_sub)
        row.confirmed_at = datetime.utcnow()
        row.updated_at = datetime.utcnow()
        self._db.commit()
        self._db.refresh(row)
        usernames = resolve_usernames(self._db, [row.created_by, row.confirmed_by])
        return _to_entity(row, usernames)

    def delete(self, block_id: int) -> None:
        row = self._get_row(block_id)
        row.deleted_at = datetime.utcnow()
        self._db.commit()

    def coverage(self, year: int) -> AlignmentCoverage:
        result = self._db.execute(
            text(
                """
                SELECT count(*) AS n_blocks,
                       coalesce(ST_Area(ST_Union(geom)::geography), 0) AS covered_area_m2
                FROM alignment_results.alignment_block
                WHERE year = :year AND status = 'confirmed' AND deleted_at IS NULL
                """
            ),
            {"year": year},
        ).mappings().first()
        return AlignmentCoverage(
            year=year,
            n_blocks=result["n_blocks"],
            covered_area_m2=float(result["covered_area_m2"]),
        )
