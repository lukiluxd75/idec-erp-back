"""Postgres adapter for SectorHistoryPort -- read-only browsing of
`detection_results` for the map overlay and Historial's detail view."""
from typing import Any, Dict, List, Optional

from geoalchemy2.shape import to_shape
from shapely.geometry import mapping as shapely_to_geojson
from sqlalchemy.orm import Session

from app.domains.detection.domain.entities.processed_sector_detail import (
    ParcelDetail,
    ProcessedSectorDetail,
    ReviewRecord,
    RunDetail,
)
from app.domains.detection.domain.entities.processed_sector_map_item import ProcessedSectorMapItem
from app.domains.detection.domain.ports.sector_history_port import SectorHistoryPort
from app.domains.detection.infrastructure.models import (
    AffectedParcelModel,
    AlignmentModel,
    ArchitectReviewModel,
    CampaignModel,
    DetectionModel,
    ProcessedSectorModel,
    ProcessingRunModel,
)
from app.domains.detection.infrastructure.user_lookup import resolve_usernames


def _geom_to_geojson(geom_wkb) -> Dict[str, Any]:
    return shapely_to_geojson(to_shape(geom_wkb))


class SqlSectorHistoryRepository(SectorHistoryPort):
    def __init__(self, db: Session):
        self._db = db

    def list_map_items(
        self, campaign_id: Optional[int] = None, unassigned_only: bool = False
    ) -> List[ProcessedSectorMapItem]:
        query = self._db.query(ProcessedSectorModel).filter(ProcessedSectorModel.deleted_at.is_(None))
        if campaign_id is not None:
            query = query.filter(ProcessedSectorModel.campaign_id == campaign_id)
        elif unassigned_only:
            query = query.filter(ProcessedSectorModel.campaign_id.is_(None))
        rows = query.order_by(ProcessedSectorModel.id.desc()).all()
        sector_ids = [r.id for r in rows]

        campaign_ids = {r.campaign_id for r in rows if r.campaign_id}
        campaigns = (
            {
                c.id: c.code
                for c in self._db.query(CampaignModel).filter(CampaignModel.id.in_(campaign_ids)).all()
            }
            if campaign_ids
            else {}
        )
        usernames = resolve_usernames(self._db, (r.created_by for r in rows))
        validation_counts = self._validation_counts_by_sector(sector_ids)

        return [
            ProcessedSectorMapItem(
                id=r.id,
                name=r.name,
                geom_geojson=_geom_to_geojson(r.geom),
                year_a=r.year_a,
                year_b=r.year_b,
                status=r.status,
                has_changes=r.has_changes,
                n_affected_parcels=r.n_affected_parcels,
                n_new_parcels=r.n_new_parcels,
                n_removed_parcels=r.n_removed_parcels,
                n_changed_parcels=r.n_changed_parcels,
                n_confirmed_parcels=validation_counts.get(r.id, {}).get("confirmed", 0),
                n_rejected_parcels=validation_counts.get(r.id, {}).get("rejected", 0),
                n_pending_parcels=validation_counts.get(r.id, {}).get("pending", 0),
                campaign_code=campaigns.get(r.campaign_id),
                created_by_username=usernames.get(str(r.created_by)) if r.created_by else None,
                created_at=r.created_at,
                processed_at=r.processed_at,
            )
            for r in rows
        ]

    def _validation_counts_by_sector(self, sector_ids: List[int]) -> Dict[int, Dict[str, int]]:
        """confirmed/rejected/pending tallies per sector, scoped to each
        sector's MOST RECENT processing_run only -- what the map polygon's
        color means (see ProcessedSectorMapItem): a superseded auto run's
        leftover verdicts must not muddy the color of a sector that was
        since manually realigned and re-reviewed."""
        if not sector_ids:
            return {}

        latest_run_id_by_sector: Dict[int, int] = {}
        for run in (
            self._db.query(ProcessingRunModel)
            .filter(ProcessingRunModel.processed_sector_id.in_(sector_ids))
            .order_by(ProcessingRunModel.id.asc())
            .all()
        ):
            latest_run_id_by_sector[run.processed_sector_id] = run.id  # last (highest id) wins

        detection_run_by_id: Dict[int, Optional[int]] = {
            d.id: d.processing_run_id
            for d in self._db.query(DetectionModel).filter(DetectionModel.processed_sector_id.in_(sector_ids)).all()
        }

        counts: Dict[int, Dict[str, int]] = {}
        for p in (
            self._db.query(AffectedParcelModel)
            .filter(AffectedParcelModel.processed_sector_id.in_(sector_ids))
            .all()
        ):
            run_id = detection_run_by_id.get(p.detection_id)
            if run_id != latest_run_id_by_sector.get(p.processed_sector_id):
                continue
            bucket = counts.setdefault(p.processed_sector_id, {"confirmed": 0, "rejected": 0, "pending": 0})
            if p.validation_status in bucket:
                bucket[p.validation_status] += 1
        return counts

    def get_detail(self, processed_sector_id: int) -> Optional[ProcessedSectorDetail]:
        sector = self._db.query(ProcessedSectorModel).filter(
            ProcessedSectorModel.id == processed_sector_id
        ).first()
        if sector is None:
            return None

        campaign = (
            self._db.query(CampaignModel).filter(CampaignModel.id == sector.campaign_id).first()
            if sector.campaign_id
            else None
        )

        runs = (
            self._db.query(ProcessingRunModel)
            .filter(ProcessingRunModel.processed_sector_id == processed_sector_id)
            .order_by(ProcessingRunModel.id.asc())
            .all()
        )
        alignments_by_id = {
            a.id: a
            for a in self._db.query(AlignmentModel).filter(
                AlignmentModel.processed_sector_id == processed_sector_id
            ).all()
        }

        detections = (
            self._db.query(DetectionModel)
            .filter(DetectionModel.processed_sector_id == processed_sector_id)
            .all()
        )
        detection_by_id = {d.id: d for d in detections}

        parcels = (
            self._db.query(AffectedParcelModel)
            .filter(AffectedParcelModel.processed_sector_id == processed_sector_id)
            .order_by(AffectedParcelModel.id.asc())
            .all()
        )
        parcel_ids = [p.id for p in parcels]

        reviews_by_parcel: Dict[int, list] = {}
        user_ids = {sector.created_by}
        if parcel_ids:
            for rv in (
                self._db.query(ArchitectReviewModel)
                .filter(ArchitectReviewModel.affected_parcel_id.in_(parcel_ids))
                .order_by(ArchitectReviewModel.id.asc())
                .all()
            ):
                reviews_by_parcel.setdefault(rv.affected_parcel_id, []).append(rv)
                user_ids.add(rv.created_by)
        for p in parcels:
            user_ids.add(p.validated_by)

        usernames = resolve_usernames(self._db, user_ids)

        def _username(uid) -> Optional[str]:
            return usernames.get(str(uid)) if uid else None

        parcels_by_run: Dict[Optional[int], List[ParcelDetail]] = {}
        for p in parcels:
            detection = detection_by_id.get(p.detection_id)
            run_id = detection.processing_run_id if detection else None
            parcels_by_run.setdefault(run_id, []).append(
                ParcelDetail(
                    id=p.id,
                    change_type=p.change_type,
                    validation_status=p.validation_status,
                    cadastral_code=p.cadastral_code,
                    probability=detection.probability if detection else None,
                    area_m2=detection.area_m2 if detection else None,
                    construction_type=p.construction_type,
                    parcel_geom_geojson=_geom_to_geojson(p.parcel_geom) if p.parcel_geom is not None else None,
                    validated_by_username=_username(p.validated_by),
                    validated_at=p.validated_at,
                    reviews=[
                        ReviewRecord(
                            action=rv.action,
                            comment=rv.comment,
                            created_by_username=_username(rv.created_by),
                            created_at=rv.created_at,
                        )
                        for rv in reviews_by_parcel.get(p.id, [])
                    ],
                )
            )

        run_details = [
            RunDetail(
                id=run.id,
                created_at=run.created_at,
                alignment_method=(alignments_by_id.get(run.alignment_id).method if run.alignment_id in alignments_by_id else "unknown"),
                alignment_quality_level=(
                    alignments_by_id[run.alignment_id].quality_level if run.alignment_id in alignments_by_id else None
                ),
                alignment_cc=(alignments_by_id[run.alignment_id].cc if run.alignment_id in alignments_by_id else None),
                alignment_residual_m=(
                    alignments_by_id[run.alignment_id].residual_m if run.alignment_id in alignments_by_id else None
                ),
                alignment_is_main=(
                    bool(alignments_by_id[run.alignment_id].is_accepted) if run.alignment_id in alignments_by_id else False
                ),
                parcels=parcels_by_run.get(run.id, []),
            )
            for run in runs
        ]

        return ProcessedSectorDetail(
            id=sector.id,
            name=sector.name,
            year_a=sector.year_a,
            year_b=sector.year_b,
            status=sector.status,
            n_affected_parcels=sector.n_affected_parcels,
            n_new_parcels=sector.n_new_parcels,
            n_removed_parcels=sector.n_removed_parcels,
            n_changed_parcels=sector.n_changed_parcels,
            campaign_code=campaign.code if campaign else None,
            campaign_name=campaign.name if campaign else None,
            created_by_username=_username(sector.created_by),
            created_at=sector.created_at,
            processed_at=sector.processed_at,
            runs=run_details,
        )
