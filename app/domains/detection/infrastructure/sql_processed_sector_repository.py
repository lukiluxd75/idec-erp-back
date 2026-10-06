"""
Postgres/PostGIS adapter for ProcessedSectorRepositoryPort. Writes a GPU
detection pipeline run into `detection_results` (see doc/bdd.sql), translating
the engine's JSON via `gpu_result_mapper` (georeferencing, enum mappings) —
see that module's docstring for the real sample the mapping was verified
against (doc/ejemplo_resultado_job.json).
"""
from datetime import datetime
from typing import Any, List, Optional

from geoalchemy2.elements import WKTElement
from geoalchemy2.shape import to_shape
from sqlalchemy.orm import Session

from app.domains.detection.domain.entities.affected_parcel_report_row import AffectedParcelReportRow
from app.domains.detection.domain.entities.affected_parcel_summary import AffectedParcelSummary
from app.domains.detection.domain.entities.processed_sector import ProcessedSector, SectorResumeContext
from app.domains.detection.domain.ports.processed_sector_repository_port import (
    ProcessedSectorRepositoryPort,
)
from app.domains.detection.infrastructure import gpu_result_mapper as mapper
from app.domains.detection.infrastructure.models import (
    AffectedParcelModel,
    AlignmentModel,
    ArchitectReviewModel,
    CampaignModel,
    ControlPointModel,
    DetectionModel,
    ModuleParameterModel,
    ProcessedSectorModel,
    ProcessingHistoryModel,
    ProcessingRunModel,
    SectorArtifactModel,
)
from app.domains.detection.infrastructure.user_lookup import resolve_user_id, resolve_usernames

_SRID = 4326
# Statuses a sector can be in before a result has ever been ingested for it.
_PRE_INGESTION_STATUSES = {"pending", "aligning", "removing_shadows", "detecting"}


def _to_entity(row: ProcessedSectorModel) -> ProcessedSector:
    return ProcessedSector(
        id=row.id,
        year_a=row.year_a,
        year_b=row.year_b,
        status=row.status,
        progress_pct=row.progress_pct,
        campaign_id=row.campaign_id,
        name=row.name,
        has_changes=row.has_changes,
        n_affected_parcels=row.n_affected_parcels,
        n_new_parcels=row.n_new_parcels,
        n_removed_parcels=row.n_removed_parcels,
        n_changed_parcels=row.n_changed_parcels,
        created_at=row.created_at,
        processed_at=row.processed_at,
    )


class SqlProcessedSectorRepository(ProcessedSectorRepositoryPort):
    def __init__(self, db: Session):
        self._db = db

    def start(
        self,
        year_a: int,
        year_b: int,
        job_id: str,
        request_params: dict[str, Any],
        bbox: Optional[list[float]] = None,
        polygon: Optional[list[list[float]]] = None,
        campaign_id: Optional[int] = None,
        name: Optional[str] = None,
        created_by_sub: Optional[str] = None,
    ) -> ProcessedSector:
        if polygon:
            geom_wkt = mapper.lonlat_ring_to_wkt_polygon(polygon)
        elif bbox:
            geom_wkt = mapper.geo_bbox_to_wkt_polygon(bbox)
        else:
            raise ValueError("start() requires either bbox or polygon")

        sector = ProcessedSectorModel(
            campaign_id=campaign_id,
            name=name,
            geom=WKTElement(geom_wkt, srid=_SRID),
            year_a=year_a,
            year_b=year_b,
            status="detecting",
            progress_pct=0,
            created_by=resolve_user_id(self._db, created_by_sub),
        )
        self._db.add(sector)
        self._db.flush()  # need sector.id before the processing_run FK

        if campaign_id is not None:
            campaign = self._db.query(CampaignModel).filter(CampaignModel.id == campaign_id).first()
            if campaign is not None:
                campaign.n_sectors += 1

        run = ProcessingRunModel(
            processed_sector_id=sector.id,
            params={**request_params, "job_id": job_id},
        )
        self._db.add(run)
        self._db.commit()
        self._db.refresh(sector)
        return _to_entity(sector)

    def find_by_job_id(self, job_id: str) -> Optional[ProcessedSector]:
        run = (
            self._db.query(ProcessingRunModel)
            .filter(ProcessingRunModel.params["job_id"].astext == job_id)
            .order_by(ProcessingRunModel.id.desc())
            .first()
        )
        if run is None:
            return None
        sector = self._db.query(ProcessedSectorModel).filter(
            ProcessedSectorModel.id == run.processed_sector_id
        ).first()
        return _to_entity(sector) if sector else None

    def _latest_processing_run(self, processed_sector_id: int) -> Optional[ProcessingRunModel]:
        return (
            self._db.query(ProcessingRunModel)
            .filter(ProcessingRunModel.processed_sector_id == processed_sector_id)
            .order_by(ProcessingRunModel.id.desc())
            .first()
        )

    def list_affected_parcels(self, processed_sector_id: int) -> List[AffectedParcelSummary]:
        query = self._db.query(AffectedParcelModel).filter(
            AffectedParcelModel.processed_sector_id == processed_sector_id
        )
        latest_run = self._latest_processing_run(processed_sector_id)
        if latest_run is not None:
            query = query.join(
                DetectionModel, DetectionModel.id == AffectedParcelModel.detection_id
            ).filter(DetectionModel.processing_run_id == latest_run.id)
        rows = query.order_by(AffectedParcelModel.id.asc()).all()
        return [
            AffectedParcelSummary(
                id=r.id,
                detection_id=r.detection_id,
                cadastral_code=r.cadastral_code,
                change_type=r.change_type,
                validation_status=r.validation_status,
            )
            for r in rows
        ]

    def get_resume_context(self, processed_sector_id: int) -> Optional[SectorResumeContext]:
        sector = self._db.query(ProcessedSectorModel).filter(
            ProcessedSectorModel.id == processed_sector_id
        ).first()
        if sector is None:
            return None
        run = self._latest_processing_run(processed_sector_id)
        job_id = (run.params or {}).get("job_id") if run else None

        urls: dict = {}
        if run is not None:
            kind_to_key = {
                "aligned_a": "aligned_a",
                "aligned_b": "aligned_b",
                "result_panel": "panel_resultado",
                "checkerboard": "align_check",
            }
            artifacts = (
                self._db.query(SectorArtifactModel)
                .filter(SectorArtifactModel.processing_run_id == run.id)
                .all()
            )
            for artifact in artifacts:
                key = kind_to_key.get(artifact.kind)
                if key:
                    urls[key] = artifact.path

        return SectorResumeContext(job_id=job_id, status=sector.status, urls=urls)

    def list_report_rows(
        self,
        campaign_id: Optional[int] = None,
        unassigned_only: bool = False,
        all_campaigns: bool = False,
    ) -> List[AffectedParcelReportRow]:
        query = (
            self._db.query(AffectedParcelModel, ProcessedSectorModel, CampaignModel)
            .join(ProcessedSectorModel, ProcessedSectorModel.id == AffectedParcelModel.processed_sector_id)
            .outerjoin(CampaignModel, CampaignModel.id == ProcessedSectorModel.campaign_id)
            .filter(AffectedParcelModel.validation_status.in_(("confirmed", "rejected")))
        )
        if not all_campaigns:
            if campaign_id:
                query = query.filter(ProcessedSectorModel.campaign_id == campaign_id)
            elif unassigned_only:
                query = query.filter(ProcessedSectorModel.campaign_id.is_(None))
        rows = query.order_by(ProcessedSectorModel.id.asc(), AffectedParcelModel.id.asc()).all()

        parcel_ids = [ap.id for ap, _, _ in rows]
        detection_ids = [ap.detection_id for ap, _, _ in rows if ap.detection_id]
        detections_by_id = (
            {d.id: d for d in self._db.query(DetectionModel).filter(DetectionModel.id.in_(detection_ids)).all()}
            if detection_ids
            else {}
        )

        rejection_comments: dict[int, str] = {}
        if parcel_ids:
            for rv in (
                self._db.query(ArchitectReviewModel)
                .filter(
                    ArchitectReviewModel.affected_parcel_id.in_(parcel_ids),
                    ArchitectReviewModel.action == "reject",
                )
                .order_by(ArchitectReviewModel.id.desc())
                .all()
            ):
                rejection_comments.setdefault(rv.affected_parcel_id, rv.comment)

        usernames = resolve_usernames(self._db, (ap.validated_by for ap, _, _ in rows))

        def _username(uid) -> Optional[str]:
            return usernames.get(str(uid)) if uid else None

        result: List[AffectedParcelReportRow] = []
        for ap, sector, campaign in rows:
            detection = detections_by_id.get(ap.detection_id)
            lon, lat = (None, None)
            if ap.parcel_geom is not None:
                centroid = to_shape(ap.parcel_geom).centroid
                lon, lat = centroid.x, centroid.y
            result.append(
                AffectedParcelReportRow(
                    sector_id=sector.id,
                    sector_name=sector.name,
                    year_a=sector.year_a,
                    year_b=sector.year_b,
                    campaign_code=campaign.code if campaign else None,
                    cadastral_code=ap.cadastral_code,
                    change_type=ap.change_type,
                    construction_type=ap.construction_type,
                    validation_status=ap.validation_status,
                    rejection_comment=rejection_comments.get(ap.id),
                    probability_pct=(
                        round(float(detection.probability) * 100)
                        if detection is not None and detection.probability is not None
                        else None
                    ),
                    validated_by_username=_username(ap.validated_by),
                    validated_at=ap.validated_at,
                    lon=lon,
                    lat=lat,
                )
            )
        return result

    def is_ingested(self, processed_sector_id: int) -> bool:
        sector = self._db.query(ProcessedSectorModel).filter(
            ProcessedSectorModel.id == processed_sector_id
        ).first()
        return sector is not None and sector.status not in _PRE_INGESTION_STATUSES

    def _get_module_parameter(self, key: str, default: float) -> float:
        row = (
            self._db.query(ModuleParameterModel)
            .filter(ModuleParameterModel.param_key == key)
            .first()
        )
        if row is None:
            return default
        try:
            return float(row.value)
        except (TypeError, ValueError):
            return default

    def ingest_result(
        self, processed_sector_id: int, engine_result: dict[str, Any], engine_steps: list[dict[str, Any]]
    ) -> ProcessedSector:
        sector = self._db.query(ProcessedSectorModel).filter(
            ProcessedSectorModel.id == processed_sector_id
        ).first()
        if sector is None:
            raise ValueError(f"processed_sector {processed_sector_id} not found")

        img_bbox = engine_result.get("img_bbox")
        img_width = engine_result.get("img_width")
        img_height = engine_result.get("img_height")
        gsd_m = (engine_result.get("resolution") or {}).get("effective_gsd_m") or (
            engine_result.get("align_quality") or {}
        ).get("gsd_m")

        pending_manual_alignment = (
            self._db.query(AlignmentModel)
            .outerjoin(ProcessingRunModel, ProcessingRunModel.alignment_id == AlignmentModel.id)
            .filter(
                AlignmentModel.processed_sector_id == processed_sector_id,
                AlignmentModel.method == "manual_gcp",
                ProcessingRunModel.id.is_(None),
            )
            .order_by(AlignmentModel.id.desc())
            .first()
        )
        previous_run = self._latest_processing_run(processed_sector_id)

        if pending_manual_alignment is not None:
            alignment = pending_manual_alignment
            align_quality = engine_result.get("align_quality") or {}
            cc = engine_result.get("ecc_cc")
            residual_m = engine_result.get("align_residual_m")
            alignment.cc = round(cc, 4) if cc is not None else None
            alignment.residual_m = round(residual_m, 2) if residual_m is not None else None
            alignment.quality_level = align_quality.get("level") or "manual"
            self._pick_best_alignment(processed_sector_id, alignment)

            job_id = (previous_run.params if previous_run else {}).get("job_id")
            run = ProcessingRunModel(
                processed_sector_id=sector.id,
                alignment_id=alignment.id,
                params={
                    "job_id": job_id,
                    "img_bbox": img_bbox,
                    "img_width": img_width,
                    "img_height": img_height,
                },
            )
            self._db.add(run)
            self._db.flush()
        else:
            alignment = self._create_alignment(sector.id, engine_result)
            self._db.add(alignment)
            self._db.flush()
            run = previous_run
            if run is not None:
                run.alignment_id = alignment.id
                run.params = {
                    **run.params,
                    "img_bbox": img_bbox,
                    "img_width": img_width,
                    "img_height": img_height,
                }

        predios_geo = engine_result.get("predios_geo") or []
        parcel_rings_by_code = {p["codigo_catastral"]: p["rings"] for p in predios_geo if p.get("codigo_catastral")}

        counts = {"new": 0, "removed": 0, "changed": 0}
        for finding in engine_result.get("cambios") or []:
            detection = self._create_detection(
                sector.id, run.id if run else None, finding, img_bbox, img_width, img_height, gsd_m
            )
            self._db.add(detection)
            self._db.flush()

            affected_parcel = self._create_affected_parcel(
                sector.id, detection.id, finding, parcel_rings_by_code
            )
            self._db.add(affected_parcel)

            detection_type = mapper.DETECTION_TYPE_MAP.get(finding.get("tipo"))
            if detection_type in counts:
                counts[detection_type] += 1

        for key, url in (engine_result.get("urls") or {}).items():
            kind = mapper.ARTIFACT_KIND_MAP.get(key, mapper.ARTIFACT_KIND_FALLBACK)
            self._db.add(
                SectorArtifactModel(
                    processed_sector_id=sector.id,
                    processing_run_id=run.id if run else None,
                    kind=kind,
                    path=url,
                )
            )

        history_had_error = self._create_processing_history(sector.id, engine_steps)

        needs_manual_align = bool(engine_result.get("needs_manual_align"))
        if history_had_error:
            new_status = "error"
        elif needs_manual_align:
            new_status = "awaiting_manual_alignment"
        else:
            new_status = "awaiting_validation"

        n_nueva = engine_result.get("n_nueva") or 0
        n_eliminada = engine_result.get("n_eliminada") or 0
        n_cambio = engine_result.get("n_cambio") or 0

        previous_n_affected_parcels = sector.n_affected_parcels

        sector.status = new_status
        sector.progress_pct = 100
        sector.has_changes = (n_nueva + n_eliminada + n_cambio) > 0
        sector.n_affected_parcels = sum(counts.values())
        sector.n_new_parcels = counts["new"]
        sector.n_removed_parcels = counts["removed"]
        sector.n_changed_parcels = counts["changed"]
        sector.processed_at = datetime.utcnow()
        sector.updated_at = datetime.utcnow()

        if sector.campaign_id is not None:
            campaign = self._db.query(CampaignModel).filter(CampaignModel.id == sector.campaign_id).first()
            if campaign is not None:
                campaign.n_affected_parcels += sector.n_affected_parcels - previous_n_affected_parcels

        self._db.commit()
        self._db.refresh(sector)
        return _to_entity(sector)

    def record_manual_alignment(
        self,
        processed_sector_id: int,
        points: List[dict],
        gcp_method: str,
        warp_matrix: Optional[dict] = None,
    ) -> None:
        """Called right when apply_align_manual confirms with the engine.
        cc/residual_m are deliberately NOT accepted here: apply's own
        response does not carry them (verified against a real one -- they
        only appear later, in the re-run's result, same fields the auto path
        already reads). ingest_result() fills them in -- and only then
        decides which alignment is "best" -- once this alignment gets reused
        for that second run."""
        sector = self._db.query(ProcessedSectorModel).filter(
            ProcessedSectorModel.id == processed_sector_id
        ).first()
        if sector is None:
            raise ValueError(f"processed_sector {processed_sector_id} not found")

        alignment = AlignmentModel(
            processed_sector_id=processed_sector_id,
            method="manual_gcp",
            cc=None,
            residual_m=None,
            threshold_used=self._get_module_parameter("align_cc_bad", 0.75),
            gcp_method=gcp_method,
            base_image_source="live_wms",
            quality_level="manual",
            is_accepted=False,  # decided later in ingest_result, once residual_m is known
            warp_matrix=warp_matrix,
        )
        self._db.add(alignment)
        self._db.flush()  # need alignment.id for control_point FKs

        for order_index, point in enumerate(points):
            self._db.add(
                ControlPointModel(
                    alignment_id=alignment.id,
                    order_index=order_index,
                    x_ref=point["ax"],
                    y_ref=point["ay"],
                    x_mov=point["bx"],
                    y_mov=point["by"],
                )
            )

        sector.status = "detecting"
        sector.progress_pct = 0
        sector.updated_at = datetime.utcnow()

        self._db.commit()

    def _pick_best_alignment(self, processed_sector_id: int, new_alignment: AlignmentModel) -> None:
        """"La mejor alineación se queda como principal, la otra como
        historial": compares by residual_m, the only metric both auto_ecc and
        manual_gcp alignments report in the same unit (verified against real
        engine responses for each) -- lower is better (tighter registration).
        Purely bookkeeping on `alignment.is_accepted`: does not affect which
        run's detections the sector counts or the review screen use (those
        always follow the latest processing_run, see ingest_result)."""
        current_best = (
            self._db.query(AlignmentModel)
            .filter(
                AlignmentModel.processed_sector_id == processed_sector_id,
                AlignmentModel.is_accepted.is_(True),
                AlignmentModel.id != new_alignment.id,
            )
            .first()
        )
        if current_best is None:
            new_alignment.is_accepted = True
            return
        if new_alignment.residual_m is not None and (
            current_best.residual_m is None or new_alignment.residual_m < current_best.residual_m
        ):
            new_alignment.is_accepted = True
            current_best.is_accepted = False
        else:
            new_alignment.is_accepted = False

    def _create_alignment(self, sector_id: int, engine_result: dict[str, Any]) -> AlignmentModel:
        # Only called when no manual alignment is pending.
        align_quality = engine_result.get("align_quality") or {}
        resumen = engine_result.get("resumen_confiabilidad") or {}
        cc = engine_result.get("ecc_cc")
        residual_m = engine_result.get("align_residual_m")

        return AlignmentModel(
            processed_sector_id=sector_id,
            method="auto_ecc",
            cc=round(cc, 4) if cc is not None else None,
            residual_m=round(residual_m, 2) if residual_m is not None else None,
            threshold_used=self._get_module_parameter("align_cc_bad", 0.75),
            gcp_method=None,
            base_image_source="live_wms",
            quality_level=align_quality.get("level"),
            is_accepted=bool(resumen.get("deteccion_automatica_fiable", align_quality.get("level") in ("good", "warn"))),
            warp_matrix=None,
        )

    def _create_detection(
        self,
        sector_id: int,
        processing_run_id: Optional[int],
        finding: dict[str, Any],
        img_bbox,
        img_width,
        img_height,
        gsd_m: Optional[float],
    ) -> DetectionModel:
        tipo = finding.get("tipo")
        detection_type = mapper.DETECTION_TYPE_MAP.get(tipo, "unchanged")
        geom_wkt = mapper.pixel_bbox_to_wkt_polygon(finding["bbox"], img_bbox, img_width, img_height)

        if tipo == "nueva":
            area_px = finding.get("area_mov")
        elif tipo == "eliminada":
            area_px = finding.get("area_ref")
        else:
            area_px = finding.get("area_mov") or finding.get("area_ref")
        area_m2 = mapper.pixel_area_to_m2(area_px, gsd_m) if area_px and gsd_m else None

        return DetectionModel(
            processed_sector_id=sector_id,
            processing_run_id=processing_run_id,
            type=detection_type,
            geom=WKTElement(geom_wkt, srid=_SRID),
            probability=finding.get("prob"),
            area_m2=area_m2,
            is_included_in_report=True,
            reject_reason=None,
        )

    def _create_affected_parcel(
        self,
        sector_id: int,
        detection_id: int,
        finding: dict[str, Any],
        parcel_rings_by_code: dict[str, Any],
    ) -> AffectedParcelModel:
        cadastral_code = finding.get("codigo_catastral")
        predio_info = finding.get("predio") or {}
        cruce = finding.get("cruce_predio") or {}

        no_match_reason = None
        if cadastral_code is None:
            motivo = cruce.get("motivo")
            no_match_reason = mapper.NO_MATCH_REASON_MAP.get(motivo, mapper.NO_MATCH_REASON_FALLBACK)

        parcel_geom = None
        rings = parcel_rings_by_code.get(cadastral_code) if cadastral_code else None
        if rings:
            parcel_geom = WKTElement(mapper.arcgis_rings_to_wkt_multipolygon(rings), srid=_SRID)

        confianza = cruce.get("confianza")

        return AffectedParcelModel(
            processed_sector_id=sector_id,
            detection_id=detection_id,
            cadastral_code=cadastral_code,
            block_code=predio_info.get("nro_manzana"),
            parcel_geom=parcel_geom,
            match_confidence=mapper.MATCH_CONFIDENCE_MAP.get(confianza) if confianza else None,
            match_distance_m=cruce.get("distancia_predio_m", cruce.get("distancia_m")),
            no_match_reason=no_match_reason,
            change_type=mapper.AFFECTED_PARCEL_CHANGE_TYPE_MAP.get(finding.get("tipo"), "unchanged"),
            construction_type=None,
            validation_status="pending",
        )

    def _create_processing_history(self, sector_id: int, engine_steps: list[dict[str, Any]]) -> bool:
        """Groups the engine's granular steps into the 3 stages the schema
        tracks. Returns True if any stage failed, so the caller can set the
        sector to `error` instead of `awaiting_validation`."""
        had_error = False
        for stage, step_ids in mapper.STAGE_GROUPS.items():
            relevant = [s for s in engine_steps if s.get("id") in step_ids]
            if not relevant:
                continue
            status = "error" if any(s.get("status") == "error" for s in relevant) else "ok"
            had_error = had_error or status == "error"
            self._db.add(
                ProcessingHistoryModel(
                    processed_sector_id=sector_id,
                    stage=stage,
                    status=status,
                    message="; ".join(s.get("label", "") for s in relevant),
                    duration_seconds=None,
                )
            )
        return had_error
